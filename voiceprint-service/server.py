"""
voiceprint-service/server.py — 云端声纹嵌入提取服务

独立部署的 FastAPI 服务，加载 CAM++ 模型提供声纹嵌入提取 API。
客户端通过 HTTP 发送 base64 编码的 WAV 音频，服务返回 192 维嵌入向量。

API 契约见：docs/adr/0009-声纹识别服务云端拆分.md
"""

import base64
import io
import logging
import wave
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import torch
import torchaudio.compliance.kaldi as K
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from models.cam_plus import CAMPPlus, load_camplus
from pydantic import BaseModel, Field

# ============================================================
# 日志
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voiceprint-service")

# ============================================================
# 全局模型实例
# ============================================================

_model: CAMPPlus | None = None
MODEL_VERSION = "cam++-v1-cloud"
EMBEDDING_DIM = 192


def get_model() -> CAMPPlus:
    """获取全局 CAM++ 模型（启动时已加载）"""
    if _model is None:
        raise RuntimeError("模型未加载")
    return _model


# ============================================================
# 请求/响应模型
# ============================================================

class EmbeddingRequest(BaseModel):
    """单个 embedding 提取请求"""
    audio: str = Field(..., description="Base64 编码的 WAV 数据（16kHz 单声道）")
    sample_rate: int = Field(default=16000, description="采样率")
    model: str = Field(default="campplus-v1", description="模型标识")


class EmbeddingBatchItem(BaseModel):
    """批量请求中的单项"""
    audio: str = Field(..., description="Base64 编码的 WAV 数据")
    sample_rate: int = Field(default=16000)
    speaker_id: int = Field(default=0, description="说话人编号（透传回客户端）")


class EmbeddingBatchRequest(BaseModel):
    """批量 embedding 提取请求"""
    items: list[EmbeddingBatchItem]
    model: str = Field(default="campplus-v1")


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    dim: int = EMBEDDING_DIM
    model_version: str = MODEL_VERSION
    duration_sec: float = 0.0
    usage: dict = Field(default_factory=lambda: {"credits_consumed": 1})


class BatchResultItem(BaseModel):
    speaker_id: int
    embedding: list[float] | None = None
    dim: int = EMBEDDING_DIM
    error: str | None = None


class BatchEmbeddingResponse(BaseModel):
    results: list[BatchResultItem]
    model_version: str = MODEL_VERSION
    usage: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = "ok"
    model_version: str = MODEL_VERSION
    dim: int = EMBEDDING_DIM
    device: str = "cpu"


# ============================================================
# 应用生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时加载模型"""
    global _model
    weights_path = Path(__file__).parent / "models" / "campplus_cn_common.bin"
    if not weights_path.exists():
        raise RuntimeError(f"CAM++ 权重文件缺失: {weights_path}")

    logger.info("正在加载 CAM++ 模型...")
    _model = load_camplus(str(weights_path), device="cpu")
    _model.eval()
    logger.info(f"CAM++ 模型已加载（device=cpu, dim={EMBEDDING_DIM}）")

    yield

    logger.info("服务关闭")


app = FastAPI(
    title="声纹嵌入提取服务",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# 鉴权中间件
# ============================================================

def _get_api_key() -> str:
    """从环境变量读取 API Key"""
    import os
    return os.getenv("VOICEPRINT_API_KEY", "")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Bearer Token 鉴权（/health 豁免）"""
    if request.url.path == "/health":
        return await call_next(request)

    api_key = _get_api_key()
    if api_key:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "API Key 无效"},
            )

    return await call_next(request)


# ============================================================
# 核心推理
# ============================================================

def _decode_wav(wav_bytes: bytes, expected_sr: int = 16000) -> tuple[np.ndarray, int]:
    """从 WAV 字节解码为 float32 音频"""
    buf = io.BytesIO(wav_bytes)
    try:
        with wave.open(buf, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
    except Exception as e:
        raise ValueError(f"WAV 解码失败: {e}")

    if sampwidth == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"不支持的采样宽度: {sampwidth}")

    # 多声道→单声道
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    duration_sec = len(samples) / sample_rate
    return samples, sample_rate, duration_sec


def _extract_fbank(audio: np.ndarray, sample_rate: int) -> torch.Tensor:
    """提取 80 维 fbank 特征（含 CMN 倒谱均值归一化）"""
    # 重采样到 16kHz
    if sample_rate != 16000:
        ratio = 16000 / sample_rate
        new_len = int(len(audio) * ratio)
        audio = np.interp(
            np.linspace(0, len(audio) - 1, new_len),
            np.arange(len(audio)),
            audio,
        ).astype(np.float32)

    x = torch.from_numpy(audio).unsqueeze(0)
    fbank = K.fbank(x, num_mel_bins=80, frame_length=25, frame_shift=10)
    # CMN（倒谱均值归一化）：减去时间维均值，与本地 FunASR CAM++ 前处理口径统一，
    # 使云端 cam++-v1-cloud 与本地 cam++-v1 嵌入落在同一空间（AC-6 跨端零迁移兼容）。
    # 缺陷根因与 cos=1.0 双向复刻证据见 tests/eval_local_engine/EVAL-AC2-LOCAL-ENGINE.md §6.3。
    fbank = fbank - fbank.mean(dim=0, keepdim=True)
    return fbank


def extract_embedding(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray | None:
    """
    从音频信号提取 192 维声纹嵌入。

    Args:
        audio: float32 音频信号，值域 [-1, 1]
        sample_rate: 采样率

    Returns:
        192 维 L2 归一化嵌入向量，或 None（音频太短）
    """
    if len(audio) < sample_rate * 0.3:
        return None

    model = get_model()

    fbank = _extract_fbank(audio, sample_rate)

    with torch.no_grad():
        emb = model(fbank)

    return emb[0].cpu().numpy().astype(np.float32)


# ============================================================
# 路由
# ============================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    return HealthResponse(status="ok", device="cpu")


@app.post("/api/v1/voiceprint/embedding", response_model=EmbeddingResponse)
def create_embedding(req: EmbeddingRequest):
    """
    单个 embedding 提取。

    接收 base64 编码的 WAV 音频，返回 192 维嵌入向量。
    注意：使用 def 而非 async def，因为包含同步阻塞操作（base64 解码、WAV 解码、torch 推理），
    FastAPI 会自动分配到线程池执行，避免阻塞事件循环。
    """
    try:
        wav_bytes = base64.b64decode(req.audio)
    except Exception:
        raise HTTPException(status_code=400, detail="Base64 解码失败")

    try:
        audio, sr, duration = _decode_wav(wav_bytes, req.sample_rate)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    emb = extract_embedding(audio, sr)
    if emb is None:
        raise HTTPException(status_code=400, detail="音频太短（需 ≥ 0.3 秒）")

    return EmbeddingResponse(
        embedding=emb.tolist(),
        duration_sec=round(duration, 2),
    )


@app.post("/api/v1/voiceprint/embedding/batch", response_model=BatchEmbeddingResponse)
def create_embedding_batch(req: EmbeddingBatchRequest):
    """
    批量 embedding 提取。

    接收多个 base64 WAV，一次性返回所有嵌入。
    注意：使用 def 而非 async def，避免 torch 推理阻塞事件循环。
    """
    results = []
    total_credits = 0

    for item in req.items:
        try:
            wav_bytes = base64.b64decode(item.audio)
            audio, sr, _ = _decode_wav(wav_bytes, item.sample_rate)
            emb = extract_embedding(audio, sr)

            if emb is not None:
                results.append(BatchResultItem(
                    speaker_id=item.speaker_id,
                    embedding=emb.tolist(),
                ))
                total_credits += 1
            else:
                results.append(BatchResultItem(
                    speaker_id=item.speaker_id,
                    error="音频太短",
                ))
        except Exception as e:
            results.append(BatchResultItem(
                speaker_id=item.speaker_id,
                error=str(e),
            ))

    return BatchEmbeddingResponse(
        results=results,
        usage={"credits_consumed": total_credits},
    )


# ============================================================
# 启动入口（开发用，生产用 run.py）
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8100,
        log_level="info",
    )
