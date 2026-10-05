"""
core/diarization.py — 声纹特征提取与 VAD / Speaker feature extraction and VAD

职责 / Responsibilities:
  1. VAD 基于能量的语音活动检测 / Energy-based VAD (Voice Activity Detection)
  2. MFCC 14 维声纹特征提取（零依赖降级方案） / 14-dim MFCC speaker feature extraction (zero-dep fallback)
  3. 云端 CAM++ 声纹嵌入提取（通过 embedding_provider 抽象层） / Cloud CAM++ embedding extraction (via embedding_provider abstraction)
  4. 配置常量 / Configuration constants

聚类引擎已拆分至 core/diarization_cluster.py / Clustering engine split to core/diarization_cluster.py
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# 配置常量 / Configuration constants
# ============================================================

# 声纹特征提取窗口：2.5 秒（MFCC 需要 ≥0.5s，2.5s 提供更稳定的特征） / Feature extraction window: 2.5s (MFCC needs ≥0.5s, 2.5s for more stable features)
FEATURE_WINDOW_SEC = 2.5

# 特征提取步长：1.25 秒（50% 重叠，与窗口联动） / Feature extraction step: 1.25s (50% overlap, linked to window)
FEATURE_STEP_SEC = 1.25

# 余弦相似度阈值：高于此值认为是同一说话人 / Cosine similarity threshold: above this = same speaker
# MFCC 14维特征区分度有限，阈值设为 0.65 / MFCC 14-dim features have limited discrimination, threshold set to 0.65
SIMILARITY_THRESHOLD = 0.65

# 每个说话人档案最少需要多少组特征才能用于匹配 / Minimum feature groups per speaker profile for matching
MIN_FEATURES_PER_SPEAKER = 2

# MFCC 系数数量（降级时使用） / MFCC coefficient count (used in fallback)
N_MFCC = 13

# 采样率 / Sample rate
SAMPLE_RATE = 16000

# ── 云端 CAM++ 192 维阈值（区分度远优于 MFCC，阈值更宽松） / Cloud CAM++ 192-dim thresholds (much better discrimination than MFCC, more lenient thresholds) ──
# CAM++ 同一说话人跨时段余弦相似度稳定在 0.65+，不同说话人通常 < 0.40 / CAM++ same-speaker cross-segment cosine stable at 0.65+, different speakers typically < 0.40
CLOUD_SIMILARITY_THRESHOLD = 0.55
CLOUD_MERGE_THRESHOLD = 0.65

# ── VAD 配置 / VAD configuration ──
# RMS 能量阈值：低于此值视为静音，跳过特征提取 / RMS energy threshold: below this = silence, skip feature extraction
# 0.01 是较保守的阈值（float32 信号值域 [-1, 1]），仅过滤真正安静的段 / 0.01 is conservative (float32 range [-1, 1]), only filters truly quiet segments
VAD_ENERGY_THRESHOLD = 0.01

# 最小语音段时长（秒）：短于此值的语音段不提取特征（避免瞬态噪声） / Minimum speech segment duration (seconds): skip shorter segments (avoid transient noise)
VAD_MIN_SPEECH_SEC = 0.8


# ============================================================
# VAD：基于能量的语音活动检测 / VAD: Energy-based Voice Activity Detection
# ============================================================

def _compute_rms(pcm_bytes: bytes) -> float:
    """
    计算 PCM 音频段的 RMS 能量 / Compute RMS energy of PCM audio segment.

    Args:
        pcm_bytes: PCM 16bit 单声道原始字节 / PCM 16-bit mono raw bytes

    Returns:
        RMS 能量值 / RMS energy value (float32 range [-1, 1] corresponds to RMS ~0-0.7)
    """
    n_samples = len(pcm_bytes) // 2
    if n_samples == 0:
        return 0.0
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(samples ** 2)))


def _is_speech(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bool:
    """
    VAD 判断：该音频段是否为语音（非静音） / VAD detection: whether audio segment is speech (non-silence).

    使用 RMS 能量阈值 + 最小时长双重判断 / Dual criteria: RMS energy threshold + minimum duration.

    Args:
        pcm_bytes: PCM 16bit 单声道原始字节 / PCM 16-bit mono raw bytes
        sample_rate: 采样率 / Sample rate

    Returns:
        True = 语音段，应提取特征 / Speech segment, extract features; False = 静音/噪声，跳过 / Silence/noise, skip
    """
    # 时长检查 / Duration check
    duration_sec = len(pcm_bytes) / (sample_rate * 2)
    if duration_sec < VAD_MIN_SPEECH_SEC:
        return False

    # 能量检查 / Energy check
    rms = _compute_rms(pcm_bytes)
    return rms >= VAD_ENERGY_THRESHOLD


# ============================================================
# 声纹特征提取（MFCC 14 维） / Speaker feature extraction (14-dim MFCC)
# ============================================================


def _pcm_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """将 PCM 16bit 字节数据转为 float32 numpy 数组（归一化到 [-1, 1]） / Convert PCM 16-bit bytes to float32 numpy array (normalized to [-1, 1])"""
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
    从 PCM 音频段提取说话人声纹嵌入向量。

    通过 embedding_provider 抽象层：云端 CAM++ 192 维优先，
    云端不可用时自动降级为 MFCC 14 维。

    Args:
        pcm_bytes: PCM 16bit 单声道原始字节（建议 ≥ 2 秒）
        sample_rate: 采样率

    Returns:
        声纹嵌入向量（维度取决于 provider），或 None（音频太短/提取失败）
    """
    from core.embedding_provider import get_embedding_provider
    provider = get_embedding_provider()
    return provider.extract_from_pcm(pcm_bytes, sample_rate)


# ============================================================
# Re-export（兼容现有 import 路径）
# ============================================================

from core.diarization_cluster import (  # noqa: E402,F401
    FeatureTimestamp,
    SpeakerDiarizer,
    SpeakerProfile,
    create_realtime_diarizer,
)
