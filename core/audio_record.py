"""
core/audio_record.py — 普通录音控制（从 audio_recording.py 拆出）
"""
"""
core/audio_recording.py — macOS 系统内录与流式录音控制

职责：
  1. macOS 系统内录：通过 ffmpeg + avfoundation 从 BlackHole 2ch 采集系统音频
  2. 流式录音：PCM pipe 输出，供实时 ASR 消费
  3. 暂停/恢复控制
  4. 音频设备列表查询

依赖：
  core.audio — check_ffmpeg
  ffmpeg（系统已装）、BlackHole 2ch（虚拟声卡）
"""

import logging
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from core.audio import check_ffmpeg

logger = logging.getLogger(__name__)



from .audio_devices import (
    _detect_windows_audio_device,
    _is_windows,
    _should_auto_detect_on_windows,
)

_record_process: subprocess.Popen | None = None
_record_task_id: str | None = None
_record_output_path: Path | None = None
_record_start_time: float | None = None


def _build_ffmpeg_record_cmd(device: str, wav_path: Path) -> list[str]:
    """根据平台构建 ffmpeg 录音命令（单输出写 WAV）。
    Build platform-specific ffmpeg recording command (single output WAV).

    macOS: avfoundation（BlackHole 等虚拟声卡）
    Windows: dshow（DirectShow 音频输入）
    """
    if _is_windows():
        return [
            "ffmpeg", "-y",
            "-f", "dshow",
            "-i", f"audio={device}",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            str(wav_path),
        ]
    else:  # macOS
        return [
            "ffmpeg", "-y",
            "-f", "avfoundation",
            "-i", f":{device}",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            str(wav_path),
        ]


def start_recording(
    device: str = "BlackHole 2ch",
    output_dir: str | Path = "data/recordings",
    task_id: str | None = None,
) -> dict:
    """
    开始系统内录（从 BlackHole 采集系统音频输出）。

    前提：
      - macOS「音频 MIDI 设置」已建多输出设备 = BlackHole 2ch + 扬声器
      - 系统输出切到「多输出设备」

    Args:
        device: avfoundation 音频输入设备名
        output_dir: 录制文件存放目录
        task_id: 关联的任务 ID

    Returns:
        {"output_path": 录制文件路径, "task_id": 任务 ID}

    Raises:
        RuntimeError: ffmpeg 不可用 / 设备未指定 / 已在录制中
    """
    global _record_process, _record_task_id, _record_output_path, _record_start_time

    if _record_process and _record_process.poll() is None:
        raise RuntimeError("已在录制中")

    if not check_ffmpeg():
        raise RuntimeError("ffmpeg 不可用")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if task_id is None:
        task_id = str(uuid.uuid4())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{task_id[:8]}_{timestamp}.wav"

    # Windows 上若设备名为空或为 macOS 专属名称，自动检测可用设备
    # On Windows, auto-detect if device is empty or a macOS-only name
    if _is_windows() and _should_auto_detect_on_windows(device):
        detected = _detect_windows_audio_device()
        if detected:
            device = detected
            logger.info(f"Windows 自动检测音频输入设备: {device}")
        else:
            logger.warning("Windows 未检测到音频输入设备，使用原始值")
            logger.error(
                "自动检测失败。请设置环境变量指定录音设备: "
                "set RECORD_DEVICE=你的设备名 或 "
                "在 Windows 设置 > 声音 > 输入 中确认默认设备"
            )

    if not device:
        raise RuntimeError(
            "录制设备未配置。请在 Windows 设置中确认有已启用的麦克风，"
            "或设置环境变量 RECORD_DEVICE=设备名称"
        )

    # 根据平台构建 ffmpeg 命令 / Build platform-specific ffmpeg command
    cmd = _build_ffmpeg_record_cmd(device, output_path)

    logger.info(f"开始录制: 设备={device}, 输出={output_path.name}, 平台={'Windows' if _is_windows() else 'macOS'}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        # 短暂等待，确认进程没有立即退出（设备不存在等情况）
        time.sleep(0.5)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"ffmpeg 启动失败: {stderr[:500]}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg 未安装")

    _record_process = proc
    _record_task_id = task_id
    _record_output_path = output_path
    _record_start_time = time.time()

    return {"output_path": output_path, "task_id": task_id}


def stop_recording() -> dict:
    """
    停止录制，返回录制结果。

    Returns:
        {"output_path": 录制文件路径, "duration": 时长秒, "task_id": 任务 ID}

    Raises:
        RuntimeError: 未在录制中 / 录制文件无效
    """
    global _record_process, _record_task_id, _record_output_path, _record_start_time

    if not _record_process:
        raise RuntimeError("未在录制中")

    proc = _record_process
    output_path = _record_output_path
    task_id = _record_task_id
    start_time = _record_start_time

    try:
        # ffmpeg 收到 SIGTERM 会 finalize 文件后退出
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg 未在 10s 内退出，强制终止")
            proc.kill()
            proc.wait(timeout=5)
    finally:
        _record_process = None
        _record_task_id = None
        _record_output_path = None
        _record_start_time = None

    if not output_path or not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("录制文件无效，可能录制时间过短")

    duration = time.time() - start_time if start_time else 0

    logger.info(f"录制完成: {output_path.name} ({duration:.1f}s)")

    return {
        "output_path": output_path,
        "duration": duration,
        "task_id": task_id,
    }


def is_recording() -> bool:
    """是否正在录制"""
    return _record_process is not None and _record_process.poll() is None


def get_recording_info() -> dict | None:
    """获取当前录制信息"""
    if not is_recording():
        return None
    return {
        "task_id": _record_task_id,
        "output_path": str(_record_output_path) if _record_output_path else None,
        "elapsed": time.time() - _record_start_time if _record_start_time else 0,
    }
