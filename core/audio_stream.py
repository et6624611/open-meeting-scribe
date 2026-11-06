"""
core/audio_stream.py — 流式录音控制（从 audio_recording.py 拆出）
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
import struct
import subprocess
import threading
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

_stream_process: subprocess.Popen | None = None
_stream_task_id: str | None = None
_stream_output_path: Path | None = None
_stream_start_time: float | None = None
_stream_reader_thread: threading.Thread | None = None
_stream_running: bool = False
_stream_paused: bool = False          # 暂停标志：暂停时仍读取 pipe（防堵），但丢弃数据
_stream_pcm_callback = None  # Callable[[bytes], None] | None
_stream_paused_total: float = 0.0     # 累计暂停秒数（用于准确计算录制时长）
_stream_pause_start: float | None = None  # 本次暂停开始时间


def _build_ffmpeg_stream_cmd(device: str, wav_path: Path) -> list[str]:
    """根据平台构建 ffmpeg 流式录音命令（双输出：WAV + PCM pipe）。
    Build platform-specific ffmpeg streaming command (dual output: WAV + PCM pipe).

    macOS: avfoundation
    Windows: dshow
    """
    if _is_windows():
        input_args = ["-f", "dshow", "-i", f"audio={device}"]
    else:  # macOS
        input_args = ["-f", "avfoundation", "-i", f":{device}"]

    return [
        "ffmpeg", "-y",
        *input_args,
        "-filter_complex", "[0]aresample=16000,asplit=2[a1][a2]",
        "-map", "[a1]", "-ac", "1", "-f", "wav", str(wav_path),
        "-map", "[a2]", "-ac", "1", "-f", "s16le", "pipe:1",
    ]


def start_recording_with_stream(
    device: str = "BlackHole 2ch",
    output_dir: str | Path = "data/recordings",
    task_id: str | None = None,
    pcm_callback=None,
) -> dict:
    """
    开始流式录音：ffmpeg 双输出 — 直接写 WAV 文件到磁盘 + pipe 送实时 ASR。

    架构（v2：消除 raw 中间文件，ffmpeg 原生管理 WAV）：
      - filter_complex: aresample → asplit 将音频一分为二
      - 输出 1: ffmpeg 直接写 WAV 到磁盘（等同系统录音的可靠性）
      - 输出 2: raw PCM 到 stdout pipe（后台线程读取，送入实时 ASR）
      - 停止时 WAV 已由 ffmpeg 原生 finalize，无需二次转换

    与 start_recording() 的区别：
      - 额外提供 pipe 输出供实时 ASR 消费
      - 后台线程仅读取 pipe 并调用 pcm_callback（不写文件）

    Args:
        device: avfoundation 音频输入设备名
        output_dir: 录制文件存放目录
        task_id: 关联的任务 ID
        pcm_callback: 每收到一段 PCM 数据时的回调函数（用于实时 ASR）

    Returns:
        {"output_path": WAV 文件路径, "task_id": 任务 ID}

    Raises:
        RuntimeError: ffmpeg 不可用 / 设备未指定 / 已在录制中
    """
    global _stream_process, _stream_task_id, _stream_output_path
    global _stream_start_time, _stream_reader_thread, _stream_running
    global _stream_pcm_callback

    if _stream_process and _stream_process.poll() is None:
        raise RuntimeError("已在流式录制中")

    if not check_ffmpeg():
        raise RuntimeError("ffmpeg 不可用")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if task_id is None:
        task_id = str(uuid.uuid4())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_path = output_dir / f"{task_id[:8]}_{timestamp}.wav"

    # Windows 上若设备名为空或为 macOS 专属名称，自动检测可用设备
    # On Windows, auto-detect if device is empty or a macOS-only name
    if _is_windows() and _should_auto_detect_on_windows(device):
        detected = _detect_windows_audio_device()
        if detected:
            device = detected
            logger.info(f"Windows 自动检测音频输入设备: {device}")
        else:
            logger.warning("Windows 未检测到音频输入设备，使用默认值")
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

    cmd = _build_ffmpeg_stream_cmd(device, wav_path)

    logger.info(f"开始流式录制（双输出）: 设备={device}, WAV={wav_path.name}, 平台={'Windows' if _is_windows() else 'macOS'}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        # 短暂等待，确认进程没有立即退出。实测 avfoundation 设备不存在时 ffmpeg ~0.3s 才退出，
        # 0.2s 会误判为启动成功 → 后续 WAV 为空 → 任务「处理失败」。0.5s 与非流式 start_recording 对齐。
        # Brief wait to confirm process didn't exit immediately. Measured: avfoundation exits ~0.3s on
        # missing device; 0.2s falsely marks success → empty WAV → task "处理失败". Align with start_recording's 0.5s.
        time.sleep(0.5)
        if proc.poll() is not None:
            # 进程已退出，安全读取 stderr 获取真实失败原因（设备未找到/权限缺失/BlackHole 缺失等）
            # Process exited, safely read stderr for real failure reason (device not found/permission missing/BlackHole missing etc.)
            # stderr 开头是 ffmpeg banner/配置，真实错误在末尾；按错误关键词精准提取，避免被 banner 挤掉
            # stderr begins with ffmpeg banner/config; real error is at the end — filter by keywords to avoid banner crowding it out
            try:
                _, stderr_bytes = proc.communicate(timeout=2)
                stderr_text = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
            except Exception:
                stderr_text = ""
            _ERR_KEYWORDS = ("error", "not found", "no such", "failed", "denied", "cannot", "could not", "unavailable")
            key_lines = [ln.strip() for ln in stderr_text.splitlines()
                         if any(k in ln.lower() for k in _ERR_KEYWORDS)]
            stderr_msg = " | ".join(key_lines)[:500] if key_lines else stderr_text.strip()[-500:]
            raise RuntimeError(
                f"ffmpeg 启动失败（设备可能不可用）: {stderr_msg}" if stderr_msg
                else "ffmpeg 启动失败（设备可能不可用）"
            )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg 未安装")

    _stream_process = proc
    _stream_task_id = task_id
    _stream_output_path = wav_path
    _stream_start_time = time.time()
    _stream_pcm_callback = pcm_callback
    _stream_running = True

    # 启动后台线程从 pipe 读取 PCM 数据送实时 ASR
    _stream_reader_thread = threading.Thread(
        target=_stream_reader_loop,
        args=(proc,),
        daemon=True,
    )
    _stream_reader_thread.start()

    return {"output_path": wav_path, "task_id": task_id}


def _stream_reader_loop(proc: subprocess.Popen) -> None:
    """
    后台线程：从 ffmpeg stdout pipe 读取 PCM 数据送实时 ASR。

    v2 架构：WAV 文件由 ffmpeg 直接写磁盘，此线程仅负责读取 pipe
    数据并调用 pcm_callback（不再写任何文件）。
    """
    global _stream_running

    chunk_size = 6400  # 100ms @16kHz/16bit/mono = 3200 samples × 2 bytes
    chunk_count = 0
    cb_count = 0

    try:
        while _stream_running:
            data = proc.stdout.read(chunk_size)
            if not data:
                break
            chunk_count += 1
            # 暂停时丢弃数据（仍读取 pipe 防止 ffmpeg 阻塞）
            if _stream_paused:
                continue
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
    停止流式录音，验证 ffmpeg 直接写入的 WAV 文件，返回录制结果。

    v2 架构：WAV 文件由 ffmpeg 在录音期间实时写入磁盘，
    SIGTERM 后 ffmpeg 自动 finalize WAV header，无需二次转换。

    Returns:
        {"output_path": WAV 文件路径, "duration": 时长秒, "task_id": 任务 ID}

    Raises:
        RuntimeError: 未在流式录制中 / WAV 文件无效
    """
    global _stream_process, _stream_task_id, _stream_output_path
    global _stream_start_time, _stream_reader_thread, _stream_running
    global _stream_pcm_callback
    global _stream_paused, _stream_paused_total, _stream_pause_start

    if not _stream_process:
        raise RuntimeError("未在流式录制中")

    proc = _stream_process
    output_path = _stream_output_path
    task_id = _stream_task_id
    start_time = _stream_start_time

    # 1. 标记停止读取
    _stream_running = False
    _stream_paused = False

    # 2. 终止 ffmpeg（SIGTERM 使其 finalize WAV header 后退出）
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg 未在 10s 内退出，强制终止（WAV 可能未 finalize）")
            proc.kill()
            proc.wait(timeout=5)
    finally:
        pass

    # 3. 等待读取线程退出
    if _stream_reader_thread and _stream_reader_thread.is_alive():
        _stream_reader_thread.join(timeout=5)

    # 4. 验证 WAV 文件（ffmpeg 直接写入，无需 raw→wav 转换）
    wall_elapsed = time.time() - start_time if start_time else 0
    duration = max(0, wall_elapsed - _stream_paused_total)

    if output_path and output_path.exists() and output_path.stat().st_size > 44:
        # WAV 文件有效（至少包含 44 字节 header + 数据）
        wav_size_mb = output_path.stat().st_size / 1024 / 1024
        logger.info(f"WAV 文件验证通过: {output_path.name} ({wav_size_mb:.1f} MB, {duration:.1f}s)")
    else:
        # WAV 无效 — 尝试从残留 raw 文件降级恢复（兼容旧架构遗留场景）
        raw_path = output_path.with_suffix(".raw") if output_path else None
        if raw_path and raw_path.exists() and raw_path.stat().st_size > 0:
            logger.warning(f"WAV 无效，从残留 raw 文件降级恢复: {raw_path.name}")
            _raw_to_wav(raw_path, output_path, sample_rate=16000, channels=1, bits=16)
            try:
                raw_path.unlink()
            except Exception:
                pass
        else:
            logger.error(f"录音文件丢失: {output_path}")
            # 不抛异常 — 保留任务记录，让上层决定如何处理

    # 5. 清理状态
    _stream_process = None
    _stream_task_id = None
    _stream_output_path = None
    _stream_start_time = None
    _stream_reader_thread = None
    _stream_pcm_callback = None
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
