"""
core/diarization_cluster.py — 实时说话人聚类器 / Realtime speaker diarizer

职责 / Responsibilities:
  1. 说话人声纹档案维护（SpeakerProfile） / Speaker voiceprint profile maintenance (SpeakerProfile)
  2. 基于余弦相似度的实时聚类（SpeakerDiarizer） / Realtime cosine-similarity clustering (SpeakerDiarizer)
  3. 后处理相似簇合并 / Post-processing similar cluster merging
  4. 工厂函数：根据用户订阅状态创建分离器 / Factory function: create diarizer based on subscription status

依赖 / Dependencies:
  core.diarization — VAD、MFCC 特征提取、配置常量 / VAD, MFCC feature extraction, config constants
"""

import logging
from dataclasses import dataclass, field

import numpy as np

from core.diarization import (
    CLOUD_MERGE_THRESHOLD,
    CLOUD_SIMILARITY_THRESHOLD,
    FEATURE_STEP_SEC,
    FEATURE_WINDOW_SEC,
    MIN_FEATURES_PER_SPEAKER,
    SAMPLE_RATE,
    SIMILARITY_THRESHOLD,
    VAD_ENERGY_THRESHOLD,
    _compute_rms,
    _is_speech,
)

logger = logging.getLogger(__name__)


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
# 核心：实时说话人聚类器
# ============================================================

class SpeakerDiarizer:
    """
    实时说话人分离器（声纹嵌入 + VAD + 余弦聚类）。

    特征提取通过 embedding_provider 抽象层：云端 CAM++ 192 维优先，
    云端不可用时自动降级为 MFCC 14 维。阈值根据 provider 维度自动选择。

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
        similarity_threshold: float | None = None,
        min_features: int = MIN_FEATURES_PER_SPEAKER,
        provider=None,
    ):
        """
        Args:
            feature_window_sec: 特征提取窗口（秒）
            feature_step_sec: 特征提取步长（秒）
            similarity_threshold: 余弦相似度阈值；None 时根据 provider 维度自动选择
            min_features: 每个说话人最少特征数
            provider: EmbeddingProvider 实例；None 时从 get_embedding_provider() 获取
        """
        from core.embedding_provider import get_embedding_provider
        self._provider = provider if provider is not None else get_embedding_provider()

        self._window_sec = feature_window_sec
        self._step_sec = feature_step_sec

        # 根据 provider 维度自动选择阈值
        if similarity_threshold is not None:
            self._threshold = similarity_threshold
        elif self._provider.dim >= 192:
            self._threshold = CLOUD_SIMILARITY_THRESHOLD
        else:
            self._threshold = SIMILARITY_THRESHOLD

        self._min_features = min_features

        # 说话人档案：speaker_id → SpeakerProfile
        self._profiles: dict[int, SpeakerProfile] = {}
        self._next_speaker_id = 0

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
        if self._provider.dim >= 192:
            # CAM++ 192 维跨时段稳定性好，可激进合并
            self._merge_threshold: float = CLOUD_MERGE_THRESHOLD
        else:
            # MFCC 14 维区分度有限，偏保守：宁可保留轻微过度分裂
            self._merge_threshold = 0.52

        # 线程锁
        import threading
        self._lock = threading.Lock()

        logger.info(
            f"[声纹聚类] 初始化: provider={self._provider.model_version}"
            f"({self._provider.dim}维), 窗口={feature_window_sec}s, "
            f"匹配阈值={self._threshold}, 合并阈值={self._merge_threshold}, "
            f"VAD阈值={VAD_ENERGY_THRESHOLD}"
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

        # 提取声纹嵌入（通过 provider：云端 CAM++ 优先，MFCC 降级）
        feature = self._provider.extract_from_pcm(chunk)
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

            return best_id if best_id is not None else 0

    def get_speaker_count(self) -> int:
        """当前识别到的说话人数量（原始值，不含后处理合并）"""
        with self._lock:
            return len(self._profiles)

    def get_active_speaker_count(self, min_speech_sec: float = 2.0) -> int:
        """有效说话人数量：仅统计累计语音时长 >= min_speech_sec 的说话人。

        过滤掉因 VAD 误触发或瞬态噪声产生的伪说话人（语音时长极短）。
        """
        with self._lock:
            return sum(
                1 for p in self._profiles.values()
                if p.total_speech_sec >= min_speech_sec
            )

    def get_active_speaker_ids(self, min_speech_sec: float = 2.0) -> list[int]:
        """有效说话人 ID 列表（仅统计语音时长 >= min_speech_sec 的说话人）"""
        with self._lock:
            return sorted(
                sid for sid, p in self._profiles.items()
                if p.total_speech_sec >= min_speech_sec
            )

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
            self._next_speaker_id = 0
            self._audio_buffer = bytearray()
            self._feature_timeline.clear()
            self._read_pos = 0
            self._buffer_time_offset = 0.0
            self._vad_speech_count = 0
            self._vad_silence_count = 0
            self._finalized = False
            logger.info("[声纹聚类] 已重置")


# ============================================================
# 工厂函数：根据用户授权状态创建实时分离器
# ============================================================

def create_realtime_diarizer(**kwargs) -> SpeakerDiarizer:
    """根据用户授权状态和偏好创建实时说话人分离器。

    策略：
      - 体验期用户（free）/ 未登录 → 强制 MFCC 14 维本地（节约共享 proxy 成本）
      - 自持 Key 用户 → 默认云端 CAM++ 192 维，
        用户可通过 prefs.local_diarization=True 切换为本地 MFCC

    额外的 kwargs 透传给 SpeakerDiarizer 构造函数。
    """
    from core.users import should_use_local_diarization

    if should_use_local_diarization():
        from core.embedding_provider import MfccFallbackProvider
        logger.info("[声纹聚类] 用户策略: 本地 MFCC 14 维（体验期默认）")
        return SpeakerDiarizer(provider=MfccFallbackProvider(), **kwargs)

    logger.info("[声纹聚类] 用户策略: 云端 CAM++ 192 维")
    return SpeakerDiarizer(**kwargs)
