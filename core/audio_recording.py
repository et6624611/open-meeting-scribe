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
import re
import struct
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from core.audio import check_ffmpeg

logger = logging.getLogger(__name__)


# ============================================================
# macOS 系统内录（BlackHole + ffmpeg avfoundation）
# ============================================================

# 录制状态（模块级单例，同一时刻只允许一路录制）
_record_process: subprocess.Popen | None = None
_record_task_id: str | None = None
_record_output_path: Path | None = None
_record_start_time: float | None = None


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

    if not device:
        raise RuntimeError("录制设备未配置（需要 BlackHole 2ch）")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if task_id is None:
        task_id = str(uuid.uuid4())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{task_id[:8]}_{timestamp}.wav"

    # ffmpeg avfoundation 采集系统音频
    # -f avfoundation    macOS 音视频采集框架
    # -i :device_name    仅音频输入（冒号前为空 = 不采集视频）
    # -ar 16000 -ac 1    直接录成 16kHz 单声道（转写最优格式）
    cmd = [
        "ffmpeg", "-y",
        "-f", "avfoundation",
        "-i", f":{device}",
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        str(output_path),
    ]

    logger.info(f"开始录制: 设备={device}, 输出={output_path.name}")

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


# ============================================================
# 流式录音（PCM pipe 输出，供实时 ASR 消费）
# ============================================================

# 流式录制状态
_stream_process: subprocess.Popen | None = None
_stream_task_id: str | None = None
_stream_output_path: Path | None = None
_stream_start_time: float | None = None
_stream_reader_thread: threading.Thread | None = None
_stream_running: bool = False
_stream_paused: bool = False          # 暂停标志：暂停时仍读取 pipe（防堵），但丢弃数据
_stream_pcm_callback = None  # Callable[[bytes], None] | None
_stream_raw_path: Path | None = None
_stream_paused_total: float = 0.0     # 累计暂停秒数（用于准确计算录制时长）
_stream_pause_start: float | None = None  # 本次暂停开始时间


def start_recording_with_stream(
    device: str = "BlackHole 2ch",
    output_dir: str | Path = "data/recordings",
    task_id: str | None = None,
    pcm_callback=None,
) -> dict:
    """
    开始流式录音：ffmpeg 采集音频 → raw PCM stdout → 同时写文件 + 回调。

    与 start_recording() 的区别：
      - 输出 raw PCM 到 stdout pipe（而非直接写 WAV）
      - 后台线程读取 pipe，同时写 raw 文件 + 调用 pcm_callback
      - pcm_callback 用于将音频数据送入实时 ASR

    Args:
        device: avfoundation 音频输入设备名
        output_dir: 录制文件存放目录
        task_id: 关联的任务 ID
        pcm_callback: 每收到一段 PCM 数据时的回调函数（用于实时 ASR）

    Returns:
        {"output_path": 最终 WAV 文件路径, "task_id": 任务 ID}

    Raises:
        RuntimeError: ffmpeg 不可用 / 设备未指定 / 已在录制中
    """
    global _stream_process, _stream_task_id, _stream_output_path
    global _stream_start_time, _stream_reader_thread, _stream_running
    global _stream_pcm_callback, _stream_raw_path

    if _stream_process and _stream_process.poll() is None:
        raise RuntimeError("已在流式录制中")

    if not check_ffmpeg():
        raise RuntimeError("ffmpeg 不可用")

    if not device:
        raise RuntimeError("录制设备未配置")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if task_id is None:
        task_id = str(uuid.uuid4())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 最终 WAV 文件路径
    wav_path = output_dir / f"{task_id[:8]}_{timestamp}.wav"
    # 临时 raw PCM 文件路径
    raw_path = output_dir / f"{task_id[:8]}_{timestamp}.raw"

    # ffmpeg 输出 raw PCM 到 stdout
    cmd = [
        "ffmpeg", "-y",
        "-f", "avfoundation",
        "-i", f":{device}",
        "-ar", "16000",
        "-ac", "1",
        "-f", "s16le",        # raw PCM 16bit little-endian
        "pipe:1",             # 输出到 stdout
    ]

    logger.info(f"开始流式录制: 设备={device}, 输出={wav_path.name}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        # 短暂等待，确认进程没有立即退出
        time.sleep(0.5)
        if proc.poll() is not None:
            raise RuntimeError("ffmpeg 启动失败（设备可能不可用）")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg 未安装")

    _stream_process = proc
    _stream_task_id = task_id
    _stream_output_path = wav_path
    _stream_raw_path = raw_path
    _stream_start_time = time.time()
    _stream_pcm_callback = pcm_callback
    _stream_running = True

    # 启动后台线程读取 PCM 数据
    _stream_reader_thread = threading.Thread(
        target=_stream_reader_loop,
        args=(proc, raw_path),
        daemon=True,
    )
    _stream_reader_thread.start()

    return {"output_path": wav_path, "task_id": task_id}


def _stream_reader_loop(proc: subprocess.Popen, raw_path: Path) -> None:
    """
    后台线程：从 ffmpeg stdout 读取 PCM 数据。

    每读一块数据：
      1. 写入 raw 文件（用于停止后转 WAV）
      2. 调用 pcm_callback（送入实时 ASR）
    """
    global _stream_running

    chunk_size = 6400  # 100ms @16kHz/16bit/mono = 3200 samples × 2 bytes
    chunk_count = 0
    cb_count = 0

    try:
        with open(raw_path, "wb") as f:
            while _stream_running:
                data = proc.stdout.read(chunk_size)
                if not data:
                    break
                chunk_count += 1
                # 暂停时丢弃数据（仍读取 pipe 防止 ffmpeg 阻塞）
                if _stream_paused:
                    continue
                f.write(data)
                # 送入实时 ASR
                if _stream_pcm_callback:
                    try:
                        _stream_pcm_callback(data)
                        cb_count += 1
                    except Exception as e:
                        logger.error(f"PCM 回调异常: {e}")
                if chunk_count % 100 == 1:  # 每 10 秒报一次
                    logger.info(f"[stream] 已读 {chunk_count} 块, 回调 {cb_count} 次")
    except Exception as e:
        logger.error(f"流式读取线程异常: {e}")
    finally:
        _stream_running = False
        logger.info(f"流式读取线程退出, 共读 {chunk_count} 块, 回调 {cb_count} 次")


def stop_recording_with_stream() -> dict:
    """
    停止流式录音，将 raw PCM 转为 WAV，返回录制结果。

    Returns:
        {"output_path": WAV 文件路径, "duration": 时长秒, "task_id": 任务 ID}

    Raises:
        RuntimeError: 未在流式录制中
    """
    global _stream_process, _stream_task_id, _stream_output_path
    global _stream_start_time, _stream_reader_thread, _stream_running
    global _stream_pcm_callback, _stream_raw_path
    global _stream_paused, _stream_paused_total, _stream_pause_start

    if not _stream_process:
        raise RuntimeError("未在流式录制中")

    proc = _stream_process
    output_path = _stream_output_path
    raw_path = _stream_raw_path
    task_id = _stream_task_id
    start_time = _stream_start_time

    # 1. 标记停止读取
    _stream_running = False
    _stream_paused = False

    # 2. 终止 ffmpeg
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg 未在 10s 内退出，强制终止")
            proc.kill()
            proc.wait(timeout=5)
    finally:
        pass

    # 3. 等待读取线程退出
    if _stream_reader_thread and _stream_reader_thread.is_alive():
        _stream_reader_thread.join(timeout=5)

    # 4. 将 raw PCM 转为 WAV（扣除暂停时间）
    wall_elapsed = time.time() - start_time if start_time else 0
    duration = max(0, wall_elapsed - _stream_paused_total)
    if raw_path and raw_path.exists() and raw_path.stat().st_size > 0:
        _raw_to_wav(raw_path, output_path, sample_rate=16000, channels=1, bits=16)
        # 清理 raw 文件
        try:
            raw_path.unlink()
        except Exception:
            pass
    else:
        logger.warning("录制文件为空")

    # 5. 清理状态
    _stream_process = None
    _stream_task_id = None
    _stream_output_path = None
    _stream_start_time = None
    _stream_reader_thread = None
    _stream_pcm_callback = None
    _stream_raw_path = None
    _stream_paused = False
    _stream_paused_total = 0.0
    _stream_pause_start = None

    logger.info(f"流式录制完成: {output_path.name} ({duration:.1f}s)")

    return {
        "output_path": output_path,
        "duration": duration,
        "task_id": task_id,
    }


def pause_recording_with_stream() -> None:
    """
    暂停流式录音。

    ffmpeg 进程保持运行（pipe 继续读取，防止缓冲区满阻塞），
    但数据不写入 raw 文件、不送入 pcm_callback（实时 ASR 停止接收）。
    """
    global _stream_paused, _stream_pause_start

    if not is_stream_recording():
        raise RuntimeError("未在流式录制中")
    if _stream_paused:
        return  # 已经暂停，幂等

    _stream_paused = True
    _stream_pause_start = time.time()
    logger.info("[stream] 录制已暂停")


def resume_recording_with_stream() -> None:
    """
    恢复流式录音。

    累计暂停时长，恢复数据写入和 pcm_callback。
    """
    global _stream_paused, _stream_pause_start, _stream_paused_total

    if not _stream_process:
        raise RuntimeError("未在流式录制中")
    if not _stream_paused:
        return  # 未在暂停，幂等

    # 累计本次暂停时长
    if _stream_pause_start:
        _stream_paused_total += time.time() - _stream_pause_start

    _stream_paused = False
    _stream_pause_start = None
    logger.info(f"[stream] 录制已恢复，累计暂停 {_stream_paused_total:.1f}s")


def _raw_to_wav(
    raw_path: Path,
    wav_path: Path,
    sample_rate: int = 16000,
    channels: int = 1,
    bits: int = 16,
) -> None:
    """将 raw PCM 文件转为 WAV（加 44 字节 WAV header）"""
    data_size = raw_path.stat().st_size

    with open(raw_path, "rb") as fin, open(wav_path, "wb") as fout:
        # WAV header (44 bytes)
        byte_rate = sample_rate * channels * bits // 8
        block_align = channels * bits // 8
        fout.write(b"RIFF")
        fout.write(struct.pack("<I", 36 + data_size))  # file size - 8
        fout.write(b"WAVE")
        fout.write(b"fmt ")
        fout.write(struct.pack("<I", 16))              # fmt chunk size
        fout.write(struct.pack("<H", 1))               # PCM format
        fout.write(struct.pack("<H", channels))
        fout.write(struct.pack("<I", sample_rate))
        fout.write(struct.pack("<I", byte_rate))
        fout.write(struct.pack("<H", block_align))
        fout.write(struct.pack("<H", bits))
        fout.write(b"data")
        fout.write(struct.pack("<I", data_size))

        # 复制 PCM 数据
        while True:
            chunk = fin.read(65536)
            if not chunk:
                break
            fout.write(chunk)

    logger.info(f"raw → wav: {wav_path.name} ({data_size / 1024 / 1024:.1f} MB)")


def is_stream_recording() -> bool:
    """是否正在流式录制"""
    return (
        _stream_process is not None
        and _stream_process.poll() is None
        and _stream_running
    )


def get_stream_recording_info() -> dict | None:
    """获取当前流式录制信息（含暂停状态）"""
    if not is_stream_recording():
        return None
    # 计算有效录制时长（扣除暂停时间）
    wall_elapsed = time.time() - _stream_start_time if _stream_start_time else 0
    # 如果当前正在暂停中，加上尚未累计的暂停段
    current_pause = 0.0
    if _stream_paused and _stream_pause_start:
        current_pause = time.time() - _stream_pause_start
    effective_elapsed = max(0, wall_elapsed - _stream_paused_total - current_pause)
    return {
        "task_id": _stream_task_id,
        "output_path": str(_stream_output_path) if _stream_output_path else None,
        "elapsed": effective_elapsed,
        "paused": _stream_paused,
    }


def list_audio_devices() -> list[dict]:
    """
    列出系统可用的音频输入设备（macOS avfoundation）。

    Returns:
        [{"index": 0, "name": "设备名", "type": "audio"}, ...]
    """
    cmd = ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
        # avfoundation 设备列表输出在 stderr
        output = result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    devices = []
    in_audio = False
    for line in output.split("\n"):
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if "AVFoundation video devices" in line:
            in_audio = False
            continue
        if in_audio:
            # 格式: [AVFoundation indev @ 0x...] [0] BlackHole 2ch
            match = re.search(r'\[(\d+)\]\s+(.+)', line)
            if match:
                devices.append({
                    "index": int(match.group(1)),
                    "name": match.group(2).strip(),
                    "type": "audio",
                })

    return devices
