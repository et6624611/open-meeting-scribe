"""
core/audio.py — 音频归一化（ffmpeg） / Audio normalization (ffmpeg)

职责 / Responsibilities:
  1. 将任意音频文件归一化为 16kHz / 单声道 / WAV（DashScope 转写最优格式） / Normalize any audio to 16kHz / mono / WAV (optimal for DashScope ASR)
  2. 说话人分离仅支持单声道，必须在此步强制下混 / Diarization only supports mono; downmix is enforced here
  3. 音频时长查询 / Audio duration query

录制控制已拆分至 core/audio_recording.py / Recording control split to core/audio_recording.py

依赖 / Dependency: ffmpeg（系统已装 / system-installed）
"""

import logging
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


# ── PyInstaller frozen 环境下 ffmpeg 路径解析 ──
# 打包后 ffmpeg 位于 exe 同级的 ffmpeg/ 子目录中，不在系统 PATH 里。
# 需要在启动时将 ffmpeg 所在目录加入 PATH，使 shutil.which("ffmpeg") 和
# subprocess 调用都能找到它。
def _ensure_ffmpeg_in_path() -> None:
    """
    确保 ffmpeg 在 PATH 中。

    优先级：
      1. 系统 PATH 中已有的 ffmpeg（用户自行安装）
      2. PyInstaller frozen 环境下 exe 同级 ffmpeg/ 目录
      3. 项目根目录下的 ffmpeg/ 目录（开发环境）
    """
    if shutil.which("ffmpeg"):
        return  # 系统 PATH 中已有，无需处理

    # PyInstaller frozen 环境：ffmpeg 在 exe 同级 ffmpeg/ 目录
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        ffmpeg_dir = exe_dir / "ffmpeg"
        if ffmpeg_dir.is_dir():
            _add_to_path(ffmpeg_dir)
            return

    # 开发环境：项目根目录下的 ffmpeg/ 目录
    project_root = Path(__file__).parent.parent
    ffmpeg_dir = project_root / "ffmpeg"
    if ffmpeg_dir.is_dir():
        _add_to_path(ffmpeg_dir)


def _add_to_path(directory: Path) -> None:
    """将目录加入 PATH 环境变量（去重）"""
    dir_str = str(directory)
    current_path = os.environ.get("PATH", "")
    if dir_str not in current_path.split(os.pathsep):
        os.environ["PATH"] = f"{dir_str}{os.pathsep}{current_path}"
        logger.info(f"已将 ffmpeg 目录加入 PATH: {dir_str}")


# 模块加载时立即执行，确保后续所有调用都能找到 ffmpeg
_ensure_ffmpeg_in_path()


def check_ffmpeg() -> bool:
    """检查 ffmpeg 是否可用 / Check if ffmpeg is available"""
    return shutil.which("ffmpeg") is not None


def _measure_max_volume_db(input_path: str | Path) -> float | None:
    """测量音频峰值音量（dB） / Measure audio peak volume (dB).

    使用 ffmpeg volumedetect 滤镜探测 max_volume，供条件式响度归一化判断。
    Uses ffmpeg volumedetect filter to probe max_volume for conditional loudness normalization.

    Returns:
        峰值音量（dB，通常为负值）；解析失败或 ffmpeg 不可用时返回 None /
        Peak volume (dB, usually negative); None if parsing fails or ffmpeg unavailable.
    """
    try:
        cmd = [
            "ffmpeg", "-i", str(input_path),
            "-af", "volumedetect",
            "-f", "null", "-",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(f"volumedetect 探测失败: {e}，跳过响度归一化")
        return None

    # volumedetect 结果输出在 stderr 中，格式: [Parsed_volumedetect_...] max_volume: -XX.X dB
    import re as _re
    match = _re.search(r"max_volume:\s*(-?[\d.]+)\s*dB", result.stderr)
    if not match:
        logger.debug("未能从 volumedetect 输出解析 max_volume，跳过响度归一化")
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def normalize_audio(
    input_path: str | Path,
    output_path: str | Path | None = None,
    sample_rate: int = 16000,
    channels: int = 1,
    loudness_normalize: bool = True,
    quiet_threshold_db: float = -20.0,
    target_peak_db: float = -3.0,
    max_gain_db: float = 40.0,
) -> Path:
    """
    将音频归一化为指定格式（默认 16kHz/单声道/WAV） / Normalize audio to specified format (default 16kHz/mono/WAV).

    对音量过低的音频做条件式增益（响度归一化），避免离线 ASR（paraformer-v2）服务端 VAD
    将整段判为静音而返回 SUCCESS_WITH_NO_VALID_FRAGMENT；正常音量音频保持不变，避免回归与底噪放大。
    Conditionally boosts low-volume audio (loudness normalization) to prevent offline ASR (paraformer-v2)
    server-side VAD from rejecting the whole clip as silence (SUCCESS_WITH_NO_VALID_FRAGMENT);
    normal-volume audio is left untouched to avoid regressions and noise-floor amplification.

    Args:
        input_path: 输入音频文件路径 / Input audio file path
        output_path: 输出路径；若为 None，则在输入文件同目录生成 _normalized.wav / Output path; if None, generates _normalized.wav in input directory
        sample_rate: 采样率（默认 16000） / Sample rate (default 16000)
        channels: 声道数（默认 1，说话人分离必须单声道） / Channels (default 1, mono required for diarization)
        loudness_normalize: 是否对过低音量做条件式增益（默认 True） / Whether to conditionally boost low volume (default True)
        quiet_threshold_db: 峰值低于此阈值才视为音量过低（默认 -20.0 dB） / Peak below this is considered too quiet (default -20.0 dB)
        target_peak_db: 增益后的目标峰值（默认 -3.0 dB） / Target peak after gain (default -3.0 dB)
        max_gain_db: 最大增益上限，防止过度放大底噪（默认 40.0 dB） / Max gain cap to avoid over-amplifying noise floor (default 40.0 dB)

    Returns:
        归一化后的文件路径 / Normalized file path

    Raises:
        FileNotFoundError: 输入文件不存在 / Input file not found
        RuntimeError: ffmpeg 执行失败 / ffmpeg execution failed
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {input_path}")

    # 幂等性检查：如果文件名已含 _normalized 且为 WAV，说明已经归一化过，直接返回 / Idempotency check: if already normalized, return directly
    if "_normalized" in input_path.stem and input_path.suffix.lower() == ".wav":
        logger.info(f"音频已归一化，跳过: {input_path.name}")
        return input_path

    if output_path is None:
        output_path = input_path.with_stem(f"{input_path.stem}_normalized")
        output_path = output_path.with_suffix(".wav")
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── 条件式响度归一化：仅对音量过低的音频计算增益 ── / Conditional loudness normalization: compute gain only for too-quiet audio
    audio_filter = None
    if loudness_normalize:
        max_volume = _measure_max_volume_db(input_path)
        if max_volume is not None and max_volume < quiet_threshold_db:
            gain = min(target_peak_db - max_volume, max_gain_db)
            if gain > 0:
                # 先增益后限幅防削波 / Boost first, then limit to prevent clipping
                audio_filter = f"volume={gain:.1f}dB,alimiter=limit=0.95"
                logger.info(f"[归一化] 检测到音量过低 max={max_volume:.1f}dB，应用增益 +{gain:.1f}dB")

    # ffmpeg 参数 / ffmpeg arguments:
    # -y           覆盖输出 / overwrite output
    # -i           输入文件 / input file
    # -ar          采样率 / sample rate
    # -ac          声道数（下混单声道） / channels (downmix to mono)
    # -af          音频滤镜（仅音量过低时加入增益+限幅） / audio filter (gain+limiter only when too quiet)
    # -f wav       输出格式 / output format
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ar", str(sample_rate),
        "-ac", str(channels),
    ]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += [
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
            timeout=300,  # 5 分钟超时 / 5-minute timeout
            stdin=subprocess.DEVNULL,  # 防后台进程组读终端触发 SIGTTIN 挂起 / Prevent SIGTTIN hang from background process group reading terminal
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
    获取音频时长（秒） / Get audio duration (seconds).

    优先使用 ffprobe，不可用时降级为 WAV header 解析或 ffmpeg -i 探测。
    Prefer ffprobe; fall back to WAV header parsing or ffmpeg -i probing.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {input_path}")

    # 方案 1: ffprobe（最精确，支持所有格式） / Option 1: ffprobe (most accurate, all formats)
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                stdin=subprocess.DEVNULL)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except FileNotFoundError:
        logger.debug("ffprobe 不可用，尝试降级方案")
    except (subprocess.TimeoutExpired, ValueError) as e:
        logger.warning(f"ffprobe 查询失败: {e}，尝试降级方案")

    # 方案 2: WAV header 解析（零依赖，仅支持 WAV） / Option 2: WAV header parsing (zero deps, WAV only)
    if input_path.suffix.lower() == ".wav":
        try:
            duration = _wav_duration_from_header(input_path)
            if duration > 0:
                logger.debug(f"WAV header 解析成功: {duration:.2f}s")
                return duration
        except Exception as e:
            logger.warning(f"WAV header 解析失败: {e}")

    # 方案 3: ffmpeg -i 探测（支持所有格式，从 stderr 解析时长） / Option 3: ffmpeg -i probing (all formats, parse duration from stderr)
    try:
        cmd = ["ffmpeg", "-i", str(input_path), "-f", "null", "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                stdin=subprocess.DEVNULL)
        # ffmpeg 输出时长在 stderr 中，格式: Duration: HH:MM:SS.ss
        import re as _re
        match = _re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', result.stderr)
        if match:
            h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
            return h * 3600 + m * 60 + s
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(f"ffmpeg -i 探测失败: {e}")

    raise RuntimeError(f"无法获取音频时长: ffprobe 不可用且降级方案均失败")


def _wav_duration_from_header(wav_path: Path) -> float:
    """从 WAV 文件头计算时长（不读取全部数据）。"""
    import struct
    with open(wav_path, "rb") as f:
        # 读取 RIFF header (12 bytes) + fmt chunk (至少 24 bytes)
        header = f.read(36)
        if len(header) < 36 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            return 0
        # 解析 fmt chunk
        sample_rate = struct.unpack("<I", header[24:28])[0]
        bits_per_sample = struct.unpack("<H", header[34:36])[0]
        channels = struct.unpack("<H", header[22:24])[0]
        if sample_rate == 0 or channels == 0 or bits_per_sample == 0:
            return 0
        # 查找 data chunk 获取数据大小
        # 先检查 header 中是否已有 data chunk
        if header[36:40] == b"data":
            data_size = struct.unpack("<I", header[40:44])[0]
        else:
            # data chunk 不在前 36 字节内，需要搜索
            f.seek(36)
            while True:
                chunk_header = f.read(8)
                if len(chunk_header) < 8:
                    return 0
                chunk_id = chunk_header[:4]
                chunk_size = struct.unpack("<I", chunk_header[4:8])[0]
                if chunk_id == b"data":
                    data_size = chunk_size
                    break
                f.seek(chunk_size, 1)  # 跳过此 chunk
        byte_rate = sample_rate * channels * bits_per_sample // 8
        if byte_rate == 0:
            return 0
        return data_size / byte_rate


# ============================================================
# WAV 读取工具（替代 scipy.io.wavfile，零额外依赖） / WAV reader utility (replaces scipy.io.wavfile, zero extra deps)
# ============================================================

def read_wav_float32(path: str | Path) -> tuple[int, np.ndarray]:
    """读取 WAV 文件并返回 (采样率, float32 信号数组) / Read WAV file and return (sample_rate, float32 signal array).

    支持 16-bit PCM 和 float32 格式的 WAV 文件 / Supports 16-bit PCM and float32 WAV formats.
    多声道音频自动下混为单声道 / Multi-channel audio is automatically downmixed to mono.

    Args:
        path: WAV 文件路径 / WAV file path

    Returns:
        (sample_rate, audio_data) 元组 / tuple，audio_data 为 float32 一维数组 / float32 1D array

    Raises:
        ValueError: 不支持的音频格式 / Unsupported audio format
        FileNotFoundError: 文件不存在 / File not found
    """
    with wave.open(str(path), 'rb') as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        framerate = wf.getframerate()
        raw_data = wf.readframes(n_frames)

    if sampwidth == 2:
        # 16-bit PCM（项目最常见格式，ffmpeg 归一化输出） / 16-bit PCM (most common format, ffmpeg normalize output)
        audio = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        # 32-bit float / 32-bit float
        audio = np.frombuffer(raw_data, dtype=np.float32)
    elif sampwidth == 1:
        # 8-bit unsigned PCM / 8-bit unsigned PCM
        audio = (np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"不支持的采样位深: {sampwidth}")

    # 多声道下混为单声道 / Downmix multi-channel to mono
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)

    return framerate, audio


# ============================================================
# Re-export（兼容现有 import 路径） / Re-export (backward-compatible import paths)
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
