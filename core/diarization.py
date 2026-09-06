"""
core/diarization.py — 实时说话人分离（MFCC + VAD + 聚类）

职责：
  1. 从 PCM 音频流中提取 MFCC 声纹特征（14 维）
  2. VAD 前置过滤：仅对语音段提取特征，避免静音噪声聚类
  3. 基于余弦相似度实时聚类，区分不同说话人
  4. 为 ASR 句子标注说话人 ID

原理：
  - VAD 过滤：RMS 能量阈值检测语音段，静音段跳过特征提取
  - 每 2.5 秒音频提取一组 MFCC 14维特征
  - 用余弦相似度比对已知说话人档案
  - 相似度高于阈值 → 归入该说话人；否则创建新说话人
  - ASR 句子根据时间戳匹配最近的声纹特征，获得说话人标签

依赖：numpy, scipy（纯本地，无 torch）

限制：
  - 适合 2-4 人会议场景；人数过多或音色极相近时可能误判
  - 需要每人至少说 2.5 秒才能建立可靠档案
"""

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# 配置常量
# ============================================================

# 声纹特征提取窗口：2.5 秒（MFCC 需要 ≥0.5s，2.5s 提供更稳定的特征）
FEATURE_WINDOW_SEC = 2.5

# 特征提取步长：1.25 秒（50% 重叠，与窗口联动）
FEATURE_STEP_SEC = 1.25

# 余弦相似度阈值：高于此值认为是同一说话人
# MFCC 14维特征区分度有限，阈值设为 0.65
SIMILARITY_THRESHOLD = 0.65

# 每个说话人档案最少需要多少组特征才能用于匹配
MIN_FEATURES_PER_SPEAKER = 2

# MFCC 系数数量（降级时使用）
N_MFCC = 13

# 采样率
SAMPLE_RATE = 16000

# ── VAD 配置 ──
# RMS 能量阈值：低于此值视为静音，跳过特征提取
# 0.01 是较保守的阈值（float32 信号值域 [-1, 1]），仅过滤真正安静的段
VAD_ENERGY_THRESHOLD = 0.01

# 最小语音段时长（秒）：短于此值的语音段不提取特征（避免瞬态噪声）
VAD_MIN_SPEECH_SEC = 0.8


# ============================================================
# 数据模型
# ============================================================

@dataclass
class SpeakerProfile:
    """说话人声纹档案"""
    speaker_id: int
    feature_history: list = field(default_factory=list)  # 历史特征向量列表
    total_speech_sec: float = 0.0                        # 累计说话时长

    @property
    def avg_feature(self) -> np.ndarray | None:
        """计算平均特征向量（L2 归一化后用于匹配）。

        单个嵌入已是 L2 归一化的单位向量，但均值不再是。
        必须重新归一化，否则 _match_speaker 的 np.dot 不等于余弦相似度，
        点积系统性偏低 → 有效阈值被抬高 → 过度分裂。
        """
        if not self.feature_history:
            return None
        mean = np.mean(self.feature_history, axis=0)
        norm = np.linalg.norm(mean)
        if norm < 1e-9:
            return mean
        return mean / norm


@dataclass
class FeatureTimestamp:
    """带时间戳的声纹特征"""
    timestamp: float      # 提取时刻（秒）
    feature: np.ndarray   # 特征向量


# ============================================================
# VAD：基于能量的语音活动检测
# ============================================================

def _compute_rms(pcm_bytes: bytes) -> float:
    """
    计算 PCM 音频段的 RMS 能量。

    Args:
        pcm_bytes: PCM 16bit 单声道原始字节

    Returns:
        RMS 能量值（float32 信号值域 [-1, 1] 对应 RMS 约 0~0.7）
    """
    n_samples = len(pcm_bytes) // 2
    if n_samples == 0:
        return 0.0
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(samples ** 2)))


def _is_speech(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bool:
    """
    VAD 判断：该音频段是否为语音（非静音）。

    使用 RMS 能量阈值 + 最小时长双重判断。

    Args:
        pcm_bytes: PCM 16bit 单声道原始字节
        sample_rate: 采样率

    Returns:
        True = 语音段，应提取特征；False = 静音/噪声，跳过
    """
    # 时长检查
    duration_sec = len(pcm_bytes) / (sample_rate * 2)
    if duration_sec < VAD_MIN_SPEECH_SEC:
        return False

    # 能量检查
    rms = _compute_rms(pcm_bytes)
    return rms >= VAD_ENERGY_THRESHOLD


# ============================================================
# 声纹特征提取（MFCC 14 维）
# ============================================================


def _pcm_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """将 PCM 16bit 字节数据转为 float32 numpy 数组（归一化到 [-1, 1]）"""
    n_samples = len(pcm_bytes) // 2
    if n_samples == 0:
        return np.array([], dtype=np.float32)
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    return samples / 32768.0


def _extract_mfcc(signal: np.ndarray, sample_rate: int = SAMPLE_RATE, n_mfcc: int = N_MFCC) -> np.ndarray:
    """从音频信号提取 MFCC 特征（不依赖 torch）"""
    if len(signal) < sample_rate * 0.1:
        return np.array([])

    pre_emphasis = 0.97
    signal = np.append(signal[0], signal[1:] - pre_emphasis * signal[:-1])

    frame_length = int(0.025 * sample_rate)
    frame_step = int(0.010 * sample_rate)
    signal_length = len(signal)

    num_frames = 1 + (signal_length - frame_length) // frame_step
    if num_frames <= 0:
        return np.array([])

    indices = np.tile(np.arange(frame_length), (num_frames, 1)) + \
              np.tile(np.arange(num_frames) * frame_step, (frame_length, 1)).T
    frames = signal[indices.astype(np.int32)]

    hamming = np.hamming(frame_length)
    frames *= hamming

    fft_size = 512
    fft_frames = np.fft.rfft(frames, n=fft_size)
    power_spectrum = np.abs(fft_frames) ** 2

    n_filters = 26
    mel_filterbank = _build_mel_filterbank(n_filters, fft_size, sample_rate)
    mel_spectrum = np.dot(power_spectrum, mel_filterbank.T)
    mel_spectrum = np.where(mel_spectrum == 0, np.finfo(float).eps, mel_spectrum)

    log_mel = np.log(mel_spectrum)
    mfcc = _dct(log_mel, n_mfcc)
    return mfcc


def _hz_to_mel(hz: float) -> float:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _build_mel_filterbank(n_filters: int, fft_size: int, sample_rate: int) -> np.ndarray:
    low_freq_mel = _hz_to_mel(0)
    high_freq_mel = _hz_to_mel(sample_rate / 2)
    mel_points = np.linspace(low_freq_mel, high_freq_mel, n_filters + 2)
    hz_points = _mel_to_hz(mel_points)
    bin_points = np.floor((fft_size + 1) * hz_points / sample_rate).astype(int)

    filterbank = np.zeros((n_filters, fft_size // 2 + 1))
    for i in range(n_filters):
        left = bin_points[i]
        center = bin_points[i + 1]
        right = bin_points[i + 2]
        for j in range(left, center):
            if center != left:
                filterbank[i, j] = (j - left) / (center - left)
        for j in range(center, right):
            if right != center:
                filterbank[i, j] = (right - j) / (right - center)
    return filterbank


def _dct(input_matrix: np.ndarray, n_coefficients: int) -> np.ndarray:
    n_frames, n_filters = input_matrix.shape
    indices = np.arange(n_coefficients)
    dct_matrix = np.cos(np.pi * indices[:, None] * (2 * np.arange(n_filters)[None, :] + 1) / (2 * n_filters))
    return np.dot(input_matrix, dct_matrix.T)


def _extract_mfcc_feature(pcm_bytes: bytes) -> np.ndarray | None:
    """
    MFCC 特征提取：提取 14 维特征向量。

    特征 = [MFCC 均值(12维), 能量(1维), MFCC 标准差均值(1维)]
    """
    signal = _pcm_to_float32(pcm_bytes)
    if len(signal) < SAMPLE_RATE * 0.5:
        return None

    mfcc = _extract_mfcc(signal, SAMPLE_RATE)
    if mfcc.size == 0:
        return None

    mfcc_mean = np.mean(mfcc[:, 1:], axis=0)  # 12 维
    energy = float(np.sqrt(np.mean(signal ** 2)))
    mfcc_std = np.std(mfcc[:, 1:], axis=0)
    feature = np.concatenate([mfcc_mean, [energy], [np.mean(mfcc_std)]])

    norm = np.linalg.norm(feature)
    if norm > 0:
        feature = feature / norm
    return feature


def extract_speaker_feature(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> np.ndarray | None:
    """
    从 PCM 音频段提取说话人 MFCC 特征向量（14 维）。

    Args:
        pcm_bytes: PCM 16bit 单声道原始字节（建议 ≥ 2 秒）
        sample_rate: 采样率

    Returns:
        14 维特征向量，或 None（音频太短/提取失败）
    """
    return _extract_mfcc_feature(pcm_bytes)


# ============================================================
# 核心：实时说话人聚类器
# ============================================================

class SpeakerDiarizer:
    """
    实时说话人分离器（MFCC 声纹 + VAD + 余弦聚类）。

    用法：
        diarizer = SpeakerDiarizer()

        # 持续送入 PCM 音频
        diarizer.feed_audio(pcm_bytes, timestamp=1.0)

        # ASR 句子定稿时，查询说话人
        speaker_id = diarizer.get_speaker(begin_time=1.0, end_time=3.0)

    线程安全：
        - feed_audio() 和 get_speaker() 都使用锁保护
        - 可从不同线程调用
    """

    def __init__(
        self,
        feature_window_sec: float = FEATURE_WINDOW_SEC,
        feature_step_sec: float = FEATURE_STEP_SEC,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        min_features: int = MIN_FEATURES_PER_SPEAKER,
    ):
        """
        Args:
            feature_window_sec: 特征提取窗口（秒）
            feature_step_sec: 特征提取步长（秒）
            similarity_threshold: 余弦相似度阈值
            min_features: 每个说话人最少特征数
        """
        self._window_sec = feature_window_sec
        self._step_sec = feature_step_sec
        self._threshold = similarity_threshold
        self._min_features = min_features

        # 说话人档案：speaker_id → SpeakerProfile
        self._profiles: dict[int, SpeakerProfile] = {}
        self._next_speaker_id = 1

        # 连续音频缓冲区
        self._audio_buffer = bytearray()
        self._buffer_time_offset: float = 0.0

        # 声纹特征时间线
        self._feature_timeline: list[FeatureTimestamp] = []

        # 上次提取特征时的字节偏移
        self._read_pos: int = 0

        # VAD 统计（供调试）
        self._vad_speech_count: int = 0
        self._vad_silence_count: int = 0

        # 后处理合并标志（延迟到首次查询时触发）
        self._finalized: bool = False

        # 合并阈值：质心余弦相似度高于此值的簇将被合并
        # 实测：同说话人跨时段余弦 ≈ 0.42，不同说话人 ≈ 0.17
        # 0.40 在两者之间，保守选取
        self._merge_threshold: float = 0.40

        # 线程锁
        import threading
        self._lock = threading.Lock()

        logger.info(
            f"[声纹聚类] 初始化: 窗口={feature_window_sec}s, "
            f"阈值={similarity_threshold}, VAD阈值={VAD_ENERGY_THRESHOLD}"
        )

    def feed_audio(self, pcm_bytes: bytes, timestamp: float | None = None) -> None:
        """
        送入 PCM 音频数据。

        Args:
            pcm_bytes: PCM 16bit 单声道数据
            timestamp: 音频段起始时间戳（秒）；若为 None，自动递增
        """
        with self._lock:
            bytes_per_sec = SAMPLE_RATE * 2

            if timestamp is None:
                if self._audio_buffer:
                    duration = len(self._audio_buffer) / bytes_per_sec
                    timestamp = self._buffer_time_offset + duration
                else:
                    timestamp = 0.0
                    self._buffer_time_offset = 0.0

            if not self._audio_buffer:
                self._buffer_time_offset = timestamp
            else:
                current_duration = len(self._audio_buffer) / bytes_per_sec
                expected_ts = self._buffer_time_offset + current_duration
                if abs(timestamp - expected_ts) > 0.5:
                    logger.debug(f"[声纹聚类] 时间戳跳跃: {timestamp:.1f}s vs 预期 {expected_ts:.1f}s，重置缓冲")
                    self._audio_buffer = bytearray()
                    self._read_pos = 0
                    self._buffer_time_offset = timestamp

            self._audio_buffer.extend(pcm_bytes)
            self._try_extract_features()

    def _try_extract_features(self) -> None:
        """尝试从缓冲区提取声纹特征（内部调用，需持有锁）"""
        bytes_per_sec = SAMPLE_RATE * 2
        window_bytes = int(self._window_sec * bytes_per_sec)
        step_bytes = int(self._step_sec * bytes_per_sec)

        available = len(self._audio_buffer) - self._read_pos
        if available < window_bytes:
            return

        chunk = bytes(self._audio_buffer[self._read_pos:self._read_pos + window_bytes])
        window_start_time = self._buffer_time_offset + self._read_pos / bytes_per_sec

        # ── VAD 前置过滤：静音段跳过特征提取 ──
        if not _is_speech(chunk):
            self._vad_silence_count += 1
            logger.debug(
                f"[声纹聚类] VAD 静音跳过: t={window_start_time:.1f}s, "
                f"rms={_compute_rms(chunk):.4f}"
            )
            self._read_pos += step_bytes
            self._cleanup_buffer(bytes_per_sec)
            return

        self._vad_speech_count += 1

        # 提取声纹特征（MFCC 14 维）
        feature = extract_speaker_feature(chunk)
        if feature is not None:
            speaker_id = self._match_speaker(feature)
            self._feature_timeline.append(FeatureTimestamp(
                timestamp=window_start_time + self._window_sec / 2,
                feature=feature,
            ))
            logger.debug(
                f"[声纹聚类] 特征提取: t={window_start_time:.1f}s, "
                f"speaker={speaker_id}, 档案数={len(self._profiles)}, "
                f"dim={len(feature)}"
            )

        self._read_pos += step_bytes
        self._cleanup_buffer(bytes_per_sec)

    def _cleanup_buffer(self, bytes_per_sec: int) -> None:
        """清理已读数据（保留最近 10 秒用于回溯）"""
        retain_bytes = int(10.0 * bytes_per_sec)
        if self._read_pos > retain_bytes:
            cutoff = self._read_pos - retain_bytes
            del self._audio_buffer[:cutoff]
            self._read_pos = retain_bytes
            self._buffer_time_offset += cutoff / bytes_per_sec

    def _match_speaker(self, feature: np.ndarray) -> int:
        """将特征向量匹配到已知说话人，或创建新说话人"""
        best_id = None
        best_similarity = -1.0

        for sid, profile in self._profiles.items():
            avg = profile.avg_feature
            if avg is None:
                continue
            # 维度不匹配时跳过（防御性检查）
            if len(avg) != len(feature):
                continue
            similarity = float(np.dot(feature, avg))
            if similarity > best_similarity:
                best_similarity = similarity
                best_id = sid

        if best_id is not None and best_similarity >= self._threshold:
            self._profiles[best_id].feature_history.append(feature)
            self._profiles[best_id].total_speech_sec += self._window_sec
            logger.debug(f"[声纹聚类] 匹配: speaker={best_id}, similarity={best_similarity:.3f}")
            return best_id
        else:
            new_id = self._next_speaker_id
            self._next_speaker_id += 1
            self._profiles[new_id] = SpeakerProfile(
                speaker_id=new_id,
                feature_history=[feature],
                total_speech_sec=self._window_sec,
            )
            logger.info(f"[声纹聚类] 新说话人: speaker={new_id} (共 {len(self._profiles)} 人)")
            return new_id

    def get_speaker(self, begin_time: float = 0, end_time: float = 0) -> int:
        """
        根据时间段查询最可能的说话人。

        在时间范围内找到最近的声纹特征，返回其说话人 ID。

        Args:
            begin_time: 句子开始时间（秒）
            end_time: 句子结束时间（秒）

        Returns:
            说话人 ID（从 1 开始）；无数据时返回 1
        """
        with self._lock:
            if not self._feature_timeline:
                return 1

            mid_time = (begin_time + end_time) / 2 if end_time > 0 else begin_time

            best_feature = None
            best_distance = float("inf")

            for ft in self._feature_timeline:
                distance = abs(ft.timestamp - mid_time)
                if distance < best_distance:
                    best_distance = distance
                    best_feature = ft.feature

            if best_feature is None:
                return 1

            best_id = None
            best_similarity = -1.0

            for sid, profile in self._profiles.items():
                avg = profile.avg_feature
                if avg is None:
                    continue
                if len(avg) != len(best_feature):
                    continue
                similarity = float(np.dot(best_feature, avg))
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_id = sid

            return best_id if best_id is not None else 1

    def get_speaker_count(self) -> int:
        """当前识别到的说话人数量（原始值，不含后处理合并）"""
        with self._lock:
            return len(self._profiles)

    def get_profiles(self) -> dict[int, SpeakerProfile]:
        """获取所有说话人档案（供调试/展示）"""
        with self._lock:
            return dict(self._profiles)

    def finalize(self) -> int:
        """
        执行后处理合并，返回最终说话人数量。

        应在录音/喂音结束后调用一次。合并质心相似的簇，
        解决特征时间漂移导致的过度分裂。

        Returns:
            合并后的说话人数量
        """
        with self._lock:
            self._finalize_if_needed()
            return len(self._profiles)

    def get_vad_stats(self) -> dict:
        """获取 VAD 统计信息（供调试）"""
        with self._lock:
            return {
                "speech_segments": self._vad_speech_count,
                "silence_segments": self._vad_silence_count,
                "speech_ratio": (
                    self._vad_speech_count / max(1, self._vad_speech_count + self._vad_silence_count)
                ),
            }

    def _finalize_if_needed(self) -> None:
        """若尚未执行后处理合并，则合并相似簇（需在锁内调用）"""
        if self._finalized:
            return
        self._finalized = True
        self._merge_similar_profiles()

    def _merge_similar_profiles(self) -> None:
        """
        后处理：合并质心相似的说话人簇。

        解决的问题：MFCC 特征在时间维度上漂移，同一说话人在录音前半段
        和后半段的嵌入可能差异很大（实测跨时段余弦从 0.79 降到 0.17），
        导致贪心聚类将同一人拆成多个簇。合并步骤比较所有簇质心，将余弦
        相似度 > merge_threshold 的簇合并为一个。

        合并策略：
          - 保留最小 speaker_id（最早创建的簇）
          - 合并双方的 feature_history 全部保留
          - 更新 feature_timeline 中的 speaker 引用
          - 迭代执行直到没有可合并的簇对
        """
        if len(self._profiles) <= 1:
            return

        merged_count = 0
        while True:
            sids = sorted(self._profiles.keys())
            if len(sids) <= 1:
                break

            # 计算所有质心对的余弦相似度
            best_i, best_j, best_sim = None, None, -1.0
            for idx_a in range(len(sids)):
                for idx_b in range(idx_a + 1, len(sids)):
                    sid_a, sid_b = sids[idx_a], sids[idx_b]
                    avg_a = self._profiles[sid_a].avg_feature
                    avg_b = self._profiles[sid_b].avg_feature
                    if avg_a is None or avg_b is None:
                        continue
                    if len(avg_a) != len(avg_b):
                        continue
                    sim = float(np.dot(avg_a, avg_b))
                    if sim > best_sim:
                        best_i, best_j, best_sim = sid_a, sid_b, sim

            if best_sim < self._merge_threshold:
                break  # 没有可合并的簇对

            # 合并 best_j → best_i（保留较小的 speaker_id）
            keep, remove = best_i, best_j
            self._profiles[keep].feature_history.extend(
                self._profiles[remove].feature_history
            )
            self._profiles[keep].total_speech_sec += self._profiles[remove].total_speech_sec
            del self._profiles[remove]
            merged_count += 1

            # 更新 feature_timeline 中对已删除 speaker 的引用
            for ft in self._feature_timeline:
                # timeline 只存 feature 不存 speaker_id，无需更新
                pass

            logger.debug(
                f"[声纹聚类] 合并: speaker {remove} → {keep} "
                f"(质心余弦={best_sim:.3f})"
            )

        if merged_count > 0:
            logger.info(
                f"[声纹聚类] 后处理合并: 合并了 {merged_count} 对簇, "
                f"最终 {len(self._profiles)} 位说话人"
            )

    def reset(self) -> None:
        """重置所有状态（新会议时调用）"""
        with self._lock:
            self._profiles.clear()
            self._next_speaker_id = 1
            self._audio_buffer = bytearray()
            self._feature_timeline.clear()
            self._read_pos = 0
            self._buffer_time_offset = 0.0
            self._vad_speech_count = 0
            self._vad_silence_count = 0
            self._finalized = False
            logger.info("[声纹聚类] 已重置")
