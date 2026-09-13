"""
core/embedding_provider.py — 声纹嵌入提取抽象层

职责：
  定义 EmbeddingProvider 接口，支持两种实现：
    1. CloudEmbeddingProvider — 云端 HTTP 调用（通过环境变量配置地址）
    2. MfccFallbackProvider — 14 维 MFCC 降级（零依赖兜底）

  通过 get_embedding_provider() 按配置自动选择提供者。

设计原则：
  - 批处理链路（voiceprint.py）和实时链路（diarization.py）均通过 provider 提取嵌入
  - provider 可热切换，调用方无感知
  - 云端不可用时降级为 MFCC 14 维

参见：docs/adr/0009-声纹识别服务云端拆分.md
"""

import base64
import logging
from typing import Optional, Protocol, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# 接口定义
# ============================================================

@runtime_checkable
class EmbeddingProvider(Protocol):
    """声纹嵌入提取提供者接口"""

    @property
    def dim(self) -> int:
        """嵌入向量维度"""
        ...

    @property
    def model_version(self) -> str:
        """模型版本标识"""
        ...

    def extract(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> Optional[np.ndarray]:
        """
        从音频信号提取声纹嵌入向量。

        Args:
            audio: float32 音频信号，值域 [-1, 1]
            sample_rate: 采样率

        Returns:
            嵌入向量（已 L2 归一化），或 None（提取失败）
        """
        ...

    def extract_from_pcm(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
    ) -> Optional[np.ndarray]:
        """从 PCM 16bit 字节数据提取嵌入"""
        ...

    def is_available(self) -> bool:
        """检查提供者是否可用（模型已加载 / 网络可达）"""
        ...


# ============================================================
# 实现 1：云端 HTTP 调用（已部署）
# ============================================================

class CloudEmbeddingProvider:
    """
    云端 HTTP 调用。
    通过 RESTful API 将音频发送到云端，返回 embedding。
    需要 VOICEPRINT_API_KEY 环境变量或 settings.json 配置。
    """

    dim = 192
    model_version = "cam++-v1-cloud"

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def extract(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> Optional[np.ndarray]:
        if len(audio) < sample_rate * 0.5:
            return None

        if audio.dtype not in (np.float32, np.float64):
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.float64:
            audio = audio.astype(np.float32)

        # 转为 16kHz WAV 字节
        if sample_rate != 16000:
            ratio = 16000 / sample_rate
            new_len = int(len(audio) * ratio)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, new_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)
            sample_rate = 16000

        wav_bytes = _float32_to_wav(audio, sample_rate)
        return self._call_api(wav_bytes, sample_rate)

    def extract_from_pcm(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
    ) -> Optional[np.ndarray]:
        n_samples = len(pcm_bytes) // 2
        if n_samples == 0:
            return None
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return self.extract(samples, sample_rate)

    def _call_api(self, wav_bytes: bytes, sample_rate: int) -> Optional[np.ndarray]:
        """调用云端 embedding 提取 API"""
        try:
            import httpx

            audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
            payload = {
                "audio": audio_b64,
                "sample_rate": sample_rate,
                "model": "campplus-v1",
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            resp = httpx.post(
                f"{self.base_url}/voiceprint/embedding",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            if resp.status_code == 401:
                logger.error("[声纹Provider] 云端 API Key 无效")
                return None
            if resp.status_code == 402:
                logger.warning("[声纹Provider] 云端额度不足")
                return None
            if resp.status_code == 429:
                logger.warning("[声纹Provider] 云端请求频率超限")
                return None
            if resp.status_code != 200:
                logger.warning(f"[声纹Provider] 云端返回 HTTP {resp.status_code}")
                return None

            data = resp.json()
            embedding = np.array(data["embedding"], dtype=np.float32)
            return embedding

        except Exception as e:
            logger.warning(f"[声纹Provider] 云端调用失败: {e}")
            return None

    def is_available(self) -> bool:
        """检查云端服务是否可达"""
        try:
            import httpx
            resp = httpx.get(
                f"{self.base_url}/health",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception:
            return False


def _float32_to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    """将 float32 音频转为 WAV 格式字节（16bit PCM）"""
    import io
    import struct

    pcm_data = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    data_bytes = pcm_data.tobytes()

    buf = io.BytesIO()
    # WAV header
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(data_bytes)

    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))  # chunk size
    buf.write(struct.pack("<H", 1))   # PCM format
    buf.write(struct.pack("<H", num_channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", byte_rate))
    buf.write(struct.pack("<H", block_align))
    buf.write(struct.pack("<H", bits_per_sample))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(data_bytes)

    return buf.getvalue()


# ============================================================
# 实现 2：MFCC 降级（零依赖兜底）
# ============================================================

class MfccFallbackProvider:
    """
    MFCC 14 维特征降级方案。
    不依赖 torch，仅用 numpy。精度较低但功能可用。
    复用 diarization.py 的 MFCC 提取代码。
    """

    dim = 14
    model_version = "mfcc-fallback"

    def extract(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> Optional[np.ndarray]:
        if len(audio) < sample_rate * 0.5:
            return None

        if audio.dtype not in (np.float32, np.float64):
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.float64:
            audio = audio.astype(np.float32)

        return self._extract_mfcc_feature(audio, sample_rate)

    def extract_from_pcm(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
    ) -> Optional[np.ndarray]:
        n_samples = len(pcm_bytes) // 2
        if n_samples == 0:
            return None
        signal = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return self.extract(signal, sample_rate)

    def _extract_mfcc_feature(
        self, signal: np.ndarray, sample_rate: int = 16000
    ) -> Optional[np.ndarray]:
        """
        MFCC 特征提取：提取 14 维特征向量。
        特征 = [MFCC 均值(12维), 能量(1维), MFCC 标准差均值(1维)]
        """
        if len(signal) < sample_rate * 0.5:
            return None

        mfcc = self._extract_mfcc(signal, sample_rate)
        if mfcc.size == 0:
            return None

        mfcc_mean = np.mean(mfcc[:, 1:], axis=0)  # 12 维
        energy = float(np.sqrt(np.mean(signal ** 2)))
        mfcc_std = np.std(mfcc[:, 1:], axis=0)
        feature = np.concatenate([mfcc_mean, [energy], [np.mean(mfcc_std)]])

        norm = np.linalg.norm(feature)
        if norm > 0:
            feature = feature / norm
        return feature.astype(np.float32)

    def _extract_mfcc(
        self, signal: np.ndarray, sample_rate: int = 16000, n_mfcc: int = 13
    ) -> np.ndarray:
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
        mel_filterbank = self._build_mel_filterbank(n_filters, fft_size, sample_rate)
        mel_spectrum = np.dot(power_spectrum, mel_filterbank.T)
        mel_spectrum = np.where(mel_spectrum == 0, np.finfo(float).eps, mel_spectrum)

        log_mel = np.log(mel_spectrum)
        mfcc = self._dct(log_mel, n_mfcc)
        return mfcc

    def _build_mel_filterbank(
        self, n_filters: int, fft_size: int, sample_rate: int
    ) -> np.ndarray:
        low_freq_mel = 2595.0 * np.log10(1.0 + 0 / 700.0)
        high_freq_mel = 2595.0 * np.log10(1.0 + (sample_rate / 2) / 700.0)
        mel_points = np.linspace(low_freq_mel, high_freq_mel, n_filters + 2)
        hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
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

    def _dct(self, input_matrix: np.ndarray, n_coefficients: int) -> np.ndarray:
        n_frames, n_filters = input_matrix.shape
        indices = np.arange(n_coefficients)
        dct_matrix = np.cos(
            np.pi * indices[:, None] * (2 * np.arange(n_filters)[None, :] + 1) / (2 * n_filters)
        )
        return np.dot(input_matrix, dct_matrix.T)

    def is_available(self) -> bool:
        return True  # MFCC 始终可用（仅需 numpy）


# ============================================================
# Provider 选择逻辑
# ============================================================

_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    """
    获取当前生效的 embedding 提供者。

    选择优先级：
      1. 云端 CloudEmbeddingProvider（settings.json 配置 + 服务可达）
      2. 兜底 MfccFallbackProvider（14 维，精度较低但零依赖）

    环境变量 VOICEPRINT_PROVIDER 可覆盖 settings.json。
    """
    global _provider
    if _provider is not None:
        return _provider

    settings = _load_voiceprint_settings()
    env_provider = __import__("os").getenv("VOICEPRINT_PROVIDER", "")

    # 确定 provider 模式
    provider_mode = env_provider or settings.get("provider", "auto")

    # 1. 云端优先
    if provider_mode in ("cloud", "auto"):
        cloud_config = settings.get("cloud", {})
        api_key = __import__("os").getenv("VOICEPRINT_API_KEY", "") or cloud_config.get("api_key", "")
        base_url = __import__("os").getenv(
            "VOICEPRINT_BASE_URL", ""
        ) or cloud_config.get("base_url", "")

        if api_key and base_url:
            try:
                candidate = CloudEmbeddingProvider(
                    base_url=base_url,
                    api_key=api_key,
                )
                if candidate.is_available():
                    _provider = candidate
                    logger.info("[声纹Provider] 使用云端 embedding 提供者")
                    return _provider
                else:
                    logger.warning("[声纹Provider] 云端服务不可达，降级为 MFCC")
            except Exception as e:
                logger.warning(f"[声纹Provider] 云端提供者初始化失败: {e}")

    # 2. MFCC 兜底
    logger.warning("[声纹Provider] 云端不可用，降级为 MFCC 14 维特征")
    _provider = MfccFallbackProvider()
    return _provider


def reset_provider() -> None:
    """重置 provider 缓存（配置变更后调用）"""
    global _provider
    _provider = None


def _load_voiceprint_settings() -> dict:
    """从 settings.json 加载声纹配置"""
    try:
        from app.store import load_settings
        settings = load_settings()
        return settings.get("voiceprint", {})
    except Exception:
        return {}
