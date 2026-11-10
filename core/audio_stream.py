"""
core/audio_stream.py — 流式录音控制（从 audio_recording.py 拆出）

职责：
  1. 流式录音：ffmpeg 单进程直接写 WAV（无 pipe），实时 ASR 从文件尾 tail 读取
  2. 暂停/恢复控制
  3. 时长校验（WAV 实测 vs 墙钟，用于发现采集端丢帧）

依赖：
  core.audio — check_ffmpeg
  ffmpeg（系统已装）、BlackHole 2ch（虚拟声卡）
"""

import logging
import queue
import struct
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)



from .audio_devices import (
    _detect_macos_audio_device,
    _detect_windows_audio_device,
    _is_windows,
    _should_auto_detect_on_windows,
)

_stream_process: subprocess.Popen | None = None      # 单进程：直接写 WAV，无 pipe
_stream_task_id: str | None = None
_stream_output_path: Path | None = None
_stream_start_time: float | None = None
_stream_reader_thread: threading.Thread | None = None
_stream_running: bool = False
_stream_paused: bool = False          # 暂停标志：暂停时仍 tail 文件（保持偏移推进），但丢弃数据
_stream_pcm_callback = None  # Callable[[bytes], None] | None
_stream_paused_total: float = 0.0     # 累计暂停秒数（用于准确计算录制时长）
_stream_pause_start: float | None = None  # 本次暂停开始时间

# PCM 回调解耦队列：读线程只做 read + 入队，回调在独立线程消费。
# 目的：回调（尤其声纹 embedding 推理，单次可达 1s）绝不可反压 ffmpeg——
# 一旦反压，avfoundation 输入队列溢出丢帧，WAV 会比墙钟短数倍。
# PCM callback decoupling queue: reader thread only reads + enqueues; callbacks run in
# a separate thread. Backpressure on ffmpeg would overflow the avfoundation input queue
# and silently drop audio, making the WAV far shorter than wall-clock.
_stream_cb_queue: queue.Queue | None = None
_stream_cb_thread: threading.Thread | None = None
_stream_cb_stop = threading.Event()
_stream_cb_dropped: int = 0
# 队列上限：200 块 × 200ms ≈ 40 秒积压，足够吸收推理抖动；超出说明回调持续跑不动
# Queue cap: 200 chunks × 200ms ≈ 40s backlog, enough to absorb inference jitter.
_CB_QUEUE_MAXSIZE = 200


def _input_args(device: str) -> list[str]:
    """平台相关的 ffmpeg 输入参数 / Platform-specific ffmpeg input args."""
    if _is_windows():
        return ["-f", "dshow", "-i", f"audio={device}"]
    return ["-f", "avfoundation", "-i", f":{device}"]


def _build_ffmpeg_wav_cmd(device: str, wav_path: Path) -> list[str]:
    """
    构建唯一的录音命令：直接写 WAV 文件，不产生任何 pipe 输出。

    为什么不用 pipe：macOS 的 pipe 缓冲仅 16KB（≈0.5 秒音频）。任何读取侧的
    延迟（GIL 争用、ASR 推理、调度抖动）都会让 pipe 写满 → ffmpeg 阻塞 →
    avfoundation 输入队列溢出丢帧，WAV 会比墙钟短数倍。实时 ASR 改为从本文件
    tail 读取，彻底消除这条反压路径。

    No pipes: macOS pipe buffers are only 16KB (~0.5s). Any reader-side delay
    (GIL contention, inference, scheduling jitter) fills the pipe, blocks ffmpeg,
    and overflows the avfoundation input queue — the WAV ends up several times
    shorter than wall-clock. Realtime ASR now tails this file instead.

    `-flush_packets 1` 保证数据及时落盘（实测延迟 <1 秒），实时转写不受影响。
    """
    return [
        "ffmpeg", "-y",
        *_input_args(device),
        "-ar", "16000", "-ac", "1",
        "-flush_packets", "1",
        str(wav_path),
    ]


def _wav_data_offset(path: Path) -> int | None:
    """解析 RIFF/WAVE 找出 data chunk 的起始偏移，供 tail 读取使用。
    Locate the `data` chunk offset in a RIFF/WAVE file for tail reading."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"RIFF":
                return None
            f.seek(12)  # 跳过 RIFF header + "WAVE" / skip RIFF header + "WAVE"
            for _ in range(16):  # 防御性上限 / defensive bound
                cid = f.read(4)
                if len(cid) < 4:
                    return None
                size = struct.unpack("<I", f.read(4))[0]
                if cid == b"data":
                    return f.tell()
                f.seek(size + (size & 1), 1)  # chunk 按偶数字节对齐 / chunks are word-aligned
    except Exception:
        return None
    return None


def start_recording_with_stream(
    device: str | None = None,
    output_dir: str | Path = "data/recordings",
    task_id: str | None = None,
    pcm_callback=None,
) -> dict:
    """
    开始流式录音：ffmpeg 单进程直接把音频写成 WAV 文件。

    架构（v3：取消 pipe，彻底消除反压）：
      - ffmpeg 只写 WAV 落盘，stdout/stderr 都不参与音频通路
      - 后台线程用文件尾 tail 的方式读出新增 PCM，送入实时 ASR
      - 停止时 WAV 已由 ffmpeg 原生 finalize，无需二次转换

    Args:
        device: avfoundation 音频输入设备名；None 时按 settings > env > 平台默认解析
               （与 /api/record/devices 显示的生效来源一致）
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
    global _stream_cb_queue, _stream_cb_thread, _stream_cb_dropped

    if _stream_process and _stream_process.poll() is None:
        raise RuntimeError("已在流式录制中")

    # 延迟导入 core.audio：该模块末尾会反向 re-export 本模块的符号，
    # 顶部硬导入会在"直接 import core.audio_stream"时踩循环依赖。
    # Import lazily: core.audio re-exports this module's symbols at its tail,
    # so a top-level import would break a direct `import core.audio_stream`.
    from core.audio import check_ffmpeg

    if not check_ffmpeg():
        raise RuntimeError("ffmpeg 不可用")

    # 未显式指定设备时走统一解析（settings > env > 平台默认），不再把 v1 内录时代的
    # "BlackHole 2ch" 硬编码当默认值——那会让麦克风用户在漏传参数时静默录到空音频。
    # Resolve via settings > env > platform default; a hardcoded BlackHole default would
    # silently capture silence for microphone users.
    if device is None:
        from core.settings_store import get_record_device
        device = get_record_device()[0]

    # 保留值：__system__ 让系统内录走 BlackHole（仅 macOS）
    # Sentinel value resolution: __system__ → loopback device on macOS
    if device == "__system__":
        import platform as _platform
        if _platform.system() != "Darwin":
            raise RuntimeError("系统内录（__system__）仅在 macOS 下可用，依赖 BlackHole 虚拟声卡")
        device = "BlackHole 2ch"

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

    # macOS "自动选择"（空串）：解析成第一个非 BlackHole 物理输入设备。
    # 硬编码 "MacBook Pro麦克风" 会在设备改名时静默录空音频，动态枚举更稳。
    if not device and not _is_windows():
        detected_mac = _detect_macos_audio_device()
        if detected_mac:
            device = detected_mac
            logger.info(f"macOS 自动选择音频输入设备: {device}")

    if not device:
        if _is_windows():
            raise RuntimeError(
                "录制设备未配置。请在 Windows 设置中确认有已启用的麦克风，"
                "或设置环境变量 RECORD_DEVICE=设备名称"
            )
        raise RuntimeError(
            "录制设备未配置。请在 macOS 系统设置 > 声音 > 输入中确认有已启用的麦克风，"
            "或在设置页选择具体录音设备"
        )

    wav_cmd = _build_ffmpeg_wav_cmd(device, wav_path)

    logger.info(
        f"开始流式录制（单进程落盘 + 文件 tail）: 设备={device}, WAV={wav_path.name}, "
        f"平台={'Windows' if _is_windows() else 'macOS'}"
    )

    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    _ffmpeg_err_path = log_dir / "ffmpeg-stderr.log"

    try:
        with open(_ffmpeg_err_path, "ab") as err_fh:
            proc = subprocess.Popen(
                wav_cmd,
                stdout=subprocess.DEVNULL,
                stderr=err_fh,
                stdin=subprocess.DEVNULL,
            )
        time.sleep(0.5)
        if proc.poll() is not None:
            # 启动失败：从日志尾部提取真实原因（设备未找到/权限缺失等）
            # Startup failed: extract the real reason from the log tail
            stderr_text = ""
            try:
                stderr_text = _ffmpeg_err_path.read_text(errors="replace")[-4000:]
            except Exception:
                pass
            _ERR_KEYWORDS = ("error", "not found", "no such", "failed", "denied", "cannot", "could not", "unavailable")
            key_lines = [ln.strip() for ln in stderr_text.splitlines()
                         if any(k in ln.lower() for k in _ERR_KEYWORDS)]
            stderr_msg = " | ".join(key_lines)[-500:] if key_lines else stderr_text.strip()[-500:]
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
    _stream_cb_stop.clear()
    _stream_cb_dropped = 0

    # 回调消费线程（无回调时不启动，避免无谓线程）
    # Start consumer thread (skip when there is no callback)
    _stream_cb_queue = queue.Queue(maxsize=_CB_QUEUE_MAXSIZE)
    if pcm_callback is not None:
        _stream_cb_thread = threading.Thread(
            target=_stream_callback_loop,
            args=(_stream_cb_queue,),
            daemon=True,
        )
        _stream_cb_thread.start()

    # 从 WAV 文件尾部 tail 出新数据（只搬运，不做处理）
    # Tail new bytes off the WAV file — never blocks ffmpeg
    if pcm_callback is not None:
        _stream_reader_thread = threading.Thread(
            target=_stream_reader_loop,
            args=(wav_path,),
            daemon=True,
        )
        _stream_reader_thread.start()

    return {"output_path": wav_path, "task_id": task_id}


def _stream_reader_loop(wav_path: Path) -> None:
    """
    后台线程：tail 读取 ffmpeg 正在写入的 WAV 文件，把新增 PCM 入队。

    与旧 pipe 方案的根本区别：这里读的是普通文件，写端（ffmpeg）永远
    不会被反压。无论本线程被阻塞多久，录音都照常完整落盘。

    Tails the WAV file ffmpeg is writing. Unlike the old pipe approach, the writer
    can never be back-pressured — no matter how long this thread stalls, the
    recording stays complete.
    """
    global _stream_running, _stream_cb_dropped

    chunk_size = 6400  # 200ms @16kHz/16bit/mono = 3200 samples × 2 bytes
    chunk_count = 0

    # 等 header 就绪（ffmpeg 启动后才会写 WAV 头）
    # Wait for the WAV header to appear
    offset = None
    deadline = time.time() + 5
    while _stream_running and time.time() < deadline:
        if wav_path.exists() and wav_path.stat().st_size > 44:
            offset = _wav_data_offset(wav_path)
            if offset is not None:
                break
        time.sleep(0.05)

    if offset is None:
        logger.error(f"WAV 头解析失败，实时转写未启动: {wav_path.name}")
        return

    try:
        with open(wav_path, "rb") as f:
            f.seek(offset)
            while _stream_running:
                data = f.read(chunk_size)
                if not data:
                    time.sleep(0.05)  # 暂无新数据，稍后再试 / no new data yet
                    continue
                chunk_count += 1
                if _stream_paused:
                    continue
                q = _stream_cb_queue
                if q is None:
                    continue
                try:
                    q.put_nowait(data)
                except queue.Full:
                    # 回调持续跑不动时丢弃——保 WAV 完整是硬底线
                    # Drop when the consumer cannot keep up; WAV integrity is the hard floor
                    _stream_cb_dropped += 1
                    if _stream_cb_dropped % 50 == 1:
                        logger.warning(
                            f"[stream] 回调积压，已丢弃 {_stream_cb_dropped} 块 "
                            f"（音频落盘不受影响；实时转写/声纹会缺片段）"
                        )
                if chunk_count % 100 == 1:  # 每 20 秒报一次
                    logger.info(
                        f"[stream] 已读 {chunk_count} 块, "
                        f"队列 {q.qsize()}, 丢弃 {_stream_cb_dropped}"
                    )
    except Exception as e:
        logger.error(f"流式读取线程异常: {e}")
    finally:
        _stream_running = False
        logger.info(
            f"流式读取线程退出, 共读 {chunk_count} 块, 丢弃 {_stream_cb_dropped} 块"
        )


def _stream_callback_loop(q: queue.Queue) -> None:
    """回调消费线程：串行执行 pcm_callback，慢也只影响自身，不影响 ffmpeg 落盘。"""
    cb_count = 0
    while True:
        try:
            data = q.get(timeout=0.3)
        except queue.Empty:
            # 停止信号已置且队列排空 → 退出
            if _stream_cb_stop.is_set():
                break
            continue
        cb = _stream_pcm_callback
        if cb is None:
            continue
        try:
            cb(data)
            cb_count += 1
        except Exception as e:
            logger.error(f"PCM 回调异常: {e}")
    logger.info(
        f"PCM 回调线程退出, 共处理 {cb_count} 块, 丢弃 {_stream_cb_dropped} 块"
    )


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
    global _stream_cb_queue, _stream_cb_thread, _stream_cb_dropped

    if not _stream_process:
        raise RuntimeError("未在流式录制中")

    proc = _stream_process
    output_path = _stream_output_path
    task_id = _stream_task_id
    start_time = _stream_start_time

    # 1. 标记停止读取，并立刻冻结墙钟时间点——
    #    下面的线程 join / 队列排空属于收尾开销，不能计入录音时长
    #    Freeze wall-clock now: the joins/drain below are teardown cost, not recording time
    _stream_running = False
    _stream_paused = False
    stop_ts = time.time()

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

    # 3.5 排空回调队列：置停止信号后消费者会把已入队数据跑完再退出，
    #     避免丢弃录音末段的实时转写；超时则放弃剩余（会后全量转写兜底）
    #     Drain callback queue so the tail of realtime transcription is not lost
    _stream_cb_stop.set()
    if _stream_cb_thread and _stream_cb_thread.is_alive():
        # 只等 5 秒：回调快时瞬间排空，慢时不必让用户干等——
        # 末段实时字幕丢失由会后全量转写兜底
        _stream_cb_thread.join(timeout=5)
        if _stream_cb_thread.is_alive():
            logger.warning(
                "PCM 回调排空超时（5s），放弃剩余积压；录音落盘不受影响"
            )
    if _stream_cb_dropped:
        logger.warning(
            f"本次录制回调积压丢弃 {_stream_cb_dropped} 块"
            f"（≈{_stream_cb_dropped * 0.2:.1f}s，实时转写/声纹缺片段，WAV 完整）"
        )

    # 4. 验证 WAV 文件（ffmpeg 直接写入，无需 raw→wav 转换）
    wall_elapsed = stop_ts - start_time if start_time else 0
    wall_duration = max(0, wall_elapsed - _stream_paused_total)

    # 时长以 WAV 实际数据量为准，而不是墙钟：两者出现明显偏差说明
    # 设备侧丢帧（历史上表现为"墙钟 90s / 文件 22s"却无人察觉）
    # Use the real WAV data length, not wall-clock: a large divergence means the device
    # dropped frames (historically "90s wall-clock / 22s file" went unnoticed).
    wav_duration = 0.0
    if output_path and output_path.exists() and output_path.stat().st_size > 44:
        # WAV 文件有效（至少包含 44 字节 header + 数据）
        wav_size_mb = output_path.stat().st_size / 1024 / 1024
        wav_duration = (output_path.stat().st_size - 44) / 2 / 16000
        gap = wall_duration - wav_duration
        if gap > max(2.0, wall_duration * 0.05):
            logger.warning(
                f"录音时长异常: WAV 实际 {wav_duration:.1f}s vs 墙钟 {wall_duration:.1f}s "
                f"(丢失 {gap:.1f}s, {gap / wall_duration * 100:.0f}%) — "
                f"音频在采集端被丢弃，转写结果不可信"
            )
        logger.info(
            f"WAV 文件验证通过: {output_path.name} "
            f"({wav_size_mb:.1f} MB, {wav_duration:.1f}s, 墙钟 {wall_duration:.1f}s)"
        )
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

    # 落盘时长优先采用 WAV 实测值；文件缺失时退回墙钟
    duration = wav_duration if wav_duration > 0 else wall_duration

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
    _stream_cb_queue = None
    _stream_cb_thread = None
    _stream_cb_dropped = 0
    _stream_cb_stop.clear()

    logger.info(f"流式录制完成: {output_path.name} ({duration:.1f}s)")

    return {
        "output_path": output_path,
        "duration": duration,
        "wall_duration": wall_duration,
        "task_id": task_id,
    }


def pause_recording_with_stream() -> None:
    """
    暂停流式录音。

    ffmpeg 进程继续落盘（保证录音连续完整），
    但 tail 出的数据不再送入 pcm_callback（实时 ASR 停止接收）。
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
