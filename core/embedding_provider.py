"""
core/embedding_provider.py — 声纹嵌入提取抽象层 / Speaker embedding extraction abstraction layer

职责 / Responsibilities:
  定义 EmbeddingProvider 接口，两种实现 / Define EmbeddingProvider interface, two implementations:
    1. LocalCamPlusProvider — 本机 CAM++ 192 维（经引擎常驻子进程） / Local CAM++ 192-dim via engine subprocess
    2. MfccFallbackProvider — 14 维 MFCC 兜底（零依赖） / 14-dim MFCC fallback (zero-dep)

  通过 get_embedding_provider() 选择提供者 / Provider selected via get_embedding_provider().

设计原则 / Design principles:
  - 批处理链路（voiceprint.py）和实时链路（diarization.py）均通过 provider 提取嵌入 / Both pipelines extract embeddings via provider
  - REQ-SETTINGS-IA 第 4 刀（2026-09-26 项目方裁决①）：云端声纹链路整体下架，
    声纹仅本机 CAM++，「零出网」从文案承诺升级为结构性为真（无云端代码路径可走）；
    CloudEmbeddingProvider 与 voiceprint.provider / cloud_base_url / cloud_api_key
    配置面同步删除（存量注册特征无需迁移：cam++-v1-cloud 与 cam++-v1 在
    voiceprint_registry.COMPATIBLE_VERSIONS 互兼容，同一嵌入空间，ADR-0009）
  - CAM++ 未就绪时直接兜底 MFCC / Fall back to MFCC when CAM++ is not ready

参见 / See: docs/adr/0009-声纹识别服务云端拆分.md（云侧链路已按 REQ-SETTINGS-IA 废止）
"""

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
# CloudEmbeddingProvider 已随 REQ-SETTINGS-IA 第 4 刀整体下架（2026-09-26 裁决①）：
# 声纹仅本机 CAM++，不再保留任何可触达云端的代码路径，使「零出网」结构性为真。
# 跨端兼容由 voiceprint_registry.COMPATIBLE_VERSIONS 承担（存量云标记特征继续可匹配）。
# ============================================================


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
# 实现 3：本地 CAM++（R3 / 离线声纹，经引擎常驻子进程）
# ============================================================

class LocalCamPlusProvider:
    """本地 CAM++ 声纹（R3，离线模式）。

    经 core.engine_host 常驻子进程跑 FunASR `iic/speech_campplus_sv_zh-cn_16k-common`
    （28MB，与说话人分离共用同一份权重），返回 192 维 L2 归一化嵌入。

    跨端零迁移兼容（AC-6 / ADR-0009）：
      - model_version = "cam++-v1"（本地标识），与云端 "cam++-v1-cloud" 在
        voiceprint_registry.COMPATIBLE_VERSIONS 中互兼容，注册表双向零迁移；
      - FunASR CAM++ 内建 CMN 前处理，口径与 fix(ac6-cmn) 后的云侧
        voiceprint-service 一致（同片段 cos=1.0 已验证，见
        tests/eval_local_engine/results/vp_cmn_fix.json），故云/本地嵌入落在同一空间。

    主进程不加载 torch/funasr：重依赖只在引擎子进程内，云精简包安全。
    """

    dim = 192
    model_version = "cam++-v1"

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def extract(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> Optional[np.ndarray]:
        if audio is None or len(audio) < sample_rate * 0.5:
            return None

        if audio.dtype not in (np.float32, np.float64):
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.float64:
            audio = audio.astype(np.float32)

        # 重采样到 16kHz（CAM++ 要求）/ Resample to 16kHz
        if sample_rate != 16000:
            ratio = 16000 / sample_rate
            new_len = int(len(audio) * ratio)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, new_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)
            sample_rate = 16000

        wav_bytes = _float32_to_wav(audio.astype(np.float32), sample_rate)
        return self._infer_embedding(wav_bytes)

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

    def _infer_embedding(self, wav_bytes: bytes) -> Optional[np.ndarray]:
        """写临时 wav → 引擎子进程 task=embedding → 192 维 L2 归一化嵌入。"""
        import os
        import tempfile

        from core.engine_host import get_engine_host
        from core.errors import LocalEngineError

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav_bytes)
                tmp_path = tmp.name
            resp = get_engine_host().infer(
                "embedding", {"audio_path": tmp_path}, timeout=self.timeout
            )
            emb = resp.get("embedding")
            if not emb:
                return None
            vec = np.array(emb, dtype=np.float32)
            if vec.shape[0] != self.dim:
                logger.warning(f"[声纹Provider] 本地 CAM++ 维度异常: {vec.shape[0]} != {self.dim}")
                return None
            # L2 归一化（契约：provider 返回已归一化嵌入；余弦匹配对归一化不敏感）
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec = vec / norm
            return vec.astype(np.float32)
        except LocalEngineError as e:
            logger.warning(f"[声纹Provider] 本地 CAM++ 推理失败({e.error_code}): {e}")
            return None
        except Exception as e:
            logger.warning(f"[声纹Provider] 本地 CAM++ 调用异常: {e}")
            return None
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def is_available(self) -> bool:
        """本地引擎模型就绪（必需模型完整）即视为可用。"""
        try:
            from core.engine_host import check_required_models, get_engine_host
            if get_engine_host().is_running():
                return True
            return bool(check_required_models().get("ready"))
        except Exception:
            return False


# ============================================================
# Provider 选择逻辑（第 4 刀后只剩两级：本机 CAM++ → MFCC 兜底）
# ============================================================

_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    """
    获取当前生效的 embedding 提供者（声纹仅本机，结构性零出网）。

    选择优先级：
      1. 本机 CAM++ LocalCamPlusProvider（引擎子进程就绪）
      2. 兜底 MfccFallbackProvider（14 维，精度较低但零依赖）

    不再读取任何 voiceprint.provider 配置（字段已下架）；不存在云端代码路径。
    注：实时聚类 MFCC 路径（diarization_cluster.should_use_local_diarization）直接构造
    MfccFallbackProvider，不经本函数。
    """
    global _provider
    if _provider is not None:
        return _provider

    try:
        candidate = LocalCamPlusProvider()
        if candidate.is_available():
            _provider = candidate
            logger.info("[声纹Provider] 使用本机 CAM++ embedding 提供者（cam++-v1，零出网）")
            return _provider
    except Exception as e:
        logger.warning(f"[声纹Provider] 本机 CAM++ 提供者初始化失败: {e}")

    logger.info("[声纹Provider] 本机 CAM++ 未就绪（模型未安装），直接使用 MFCC 兜底（不触达云端）")
    _provider = MfccFallbackProvider()
    return _provider


def reset_provider() -> None:
    """重置 provider 缓存（模型安装/引擎状态变更后调用）"""
    global _provider
    _provider = None
