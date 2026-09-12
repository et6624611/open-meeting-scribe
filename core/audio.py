"""
core/audio.py — 音频归一化（ffmpeg）

职责：
  1. 将任意音频文件归一化为 16kHz / 单声道 / WAV（DashScope 转写最优格式）
  2. 说话人分离仅支持单声道，必须在此步强制下混
  3. 音频时长查询

录制控制已拆分至 core/audio_recording.py

依赖：ffmpeg（系统已装）
"""

import subprocess
import shutil
import logging
import time
from pathlib import Path

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

    # 幂等性检查：如果文件名已含 _normalized 后缀且为 WAV，说明已经归一化过，直接返回
    if input_path.stem.endswith("_normalized") and input_path.suffix.lower() == ".wav":
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
# Re-export（兼容现有 import 路径）
# ============================================================

from core.audio_recording import (  # noqa: E402
    start_recording,
    stop_recording,
    is_recording,
    get_recording_info,
    start_recording_with_stream,
    stop_recording_with_stream,
    pause_recording_with_stream,
    resume_recording_with_stream,
    is_stream_recording,
    get_stream_recording_info,
    list_audio_devices,
)
