"""
core/audio.py — 音频归一化（ffmpeg）

职责：
  1. 将任意音频文件归一化为 16kHz / 单声道 / WAV（DashScope 转写最优格式）
  2. 说话人分离仅支持单声道，必须在此步强制下混
  3. 音频时长查询

录制控制已拆分至 core/audio_recording.py

依赖：ffmpeg（系统已装）
"""

import logging
import shutil
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def check_ffmpeg() -> bool:
    """检查 ffmpeg 是否可用"""
    return shutil.which("ffmpeg") is not None


def normalize_audio(
    input_path: str | Path,
    output_path: str | Path | None = None,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Path:
    """
    将音频归一化为指定格式（默认 16kHz/单声道/WAV）。

    Args:
        input_path: 输入音频文件路径
        output_path: 输出路径；若为 None，则在输入文件同目录生成 _normalized.wav
        sample_rate: 采样率（默认 16000）
        channels: 声道数（默认 1，说话人分离必须单声道）

    Returns:
        归一化后的文件路径

    Raises:
        FileNotFoundError: 输入文件不存在
        RuntimeError: ffmpeg 执行失败
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {input_path}")

    # 幂等性检查：如果文件名已含 _normalized 且为 WAV，说明已经归一化过，直接返回
    if "_normalized" in input_path.stem and input_path.suffix.lower() == ".wav":
        logger.info(f"音频已归一化，跳过: {input_path.name}")
        return input_path

    if output_path is None:
        output_path = input_path.with_stem(f"{input_path.stem}_normalized")
        output_path = output_path.with_suffix(".wav")
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # ffmpeg 参数：
    # -y           覆盖输出
    # -i           输入文件
    # -ar          采样率
    # -ac          声道数（下混单声道）
    # -f wav       输出格式
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-f", "wav",
        str(output_path),
    ]

    logger.info(f"音频归一化: {input_path.name} → {output_path.name} "
                f"({sample_rate}Hz, {channels}ch)")

    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 分钟超时
            stdin=subprocess.DEVNULL,  # 防后台进程组读终端触发 SIGTTIN 挂起
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 失败: {result.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg 超时（>5分钟）")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg 未安装，请先安装 ffmpeg")

    elapsed = time.perf_counter() - start
    logger.info(f"[PERF] ffmpeg 归一化: {elapsed:.3f}s, "
                f"输出 {output_path.stat().st_size / 1024 / 1024:.1f} MB")
    return output_path


def get_audio_duration(input_path: str | Path) -> float:
    """
    获取音频时长（秒）。

    使用 ffprobe 查询，不依赖额外库。
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {input_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                stdin=subprocess.DEVNULL)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe 失败: {result.stderr}")
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError) as e:
        raise RuntimeError(f"无法获取音频时长: {e}")


# ============================================================
# WAV 读取工具（替代 scipy.io.wavfile，零额外依赖）
# ============================================================

def read_wav_float32(path: str | Path) -> tuple[int, np.ndarray]:
    """读取 WAV 文件并返回 (采样率, float32 信号数组)。

    支持 16-bit PCM 和 float32 格式的 WAV 文件。
    多声道音频自动下混为单声道。

    Args:
        path: WAV 文件路径

    Returns:
        (sample_rate, audio_data) 元组，audio_data 为 float32 一维数组

    Raises:
        ValueError: 不支持的音频格式
        FileNotFoundError: 文件不存在
    """
    with wave.open(str(path), 'rb') as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        framerate = wf.getframerate()
        raw_data = wf.readframes(n_frames)

    if sampwidth == 2:
        # 16-bit PCM（项目最常见格式，ffmpeg 归一化输出）
        audio = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        # 32-bit float
        audio = np.frombuffer(raw_data, dtype=np.float32)
    elif sampwidth == 1:
        # 8-bit unsigned PCM
        audio = (np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"不支持的采样位深: {sampwidth}")

    # 多声道下混为单声道
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)

    return framerate, audio


# ============================================================
# Re-export（兼容现有 import 路径）
# ============================================================

from core.audio_recording import (  # noqa: E402,F401
    get_recording_info,
    get_stream_recording_info,
    is_recording,
    is_stream_recording,
    list_audio_devices,
    pause_recording_with_stream,
    resume_recording_with_stream,
    start_recording,
    start_recording_with_stream,
    stop_recording,
    stop_recording_with_stream,
)
