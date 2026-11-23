"""录制看门狗暂停豁免与强杀联动测试。

背景（2026-11-23 事故）：暂停期间系统休眠导致 avfoundation 停采，WAV 停增
599s 被看门狗按「采集僵死」强杀；任务卡在假 paused，恢复按钮永远 400。
覆盖三层：
  1. audio_record.start_record_guard — 暂停期豁免停增、文件增长不杀、强杀回调
  2. audio_stream._handle_guard_forced_stop — 清流状态 + 僵尸清理联动
  3. recording_recovery.cleanup_zombie_recording — paused 任务可清理、定向清理
"""

import asyncio
import threading
import time

import pytest

import core.audio_record as audio_record
import core.audio_stream as audio_stream
import core.recording_recovery as recording_recovery

# 毫秒级看门狗节奏：真实间隔 2s/120s，测试下加速 1000 倍
_FAST_GUARD = {
    "_RECORD_GUARD_INTERVAL": 0.01,
    "_RECORD_STALL_GRACE": 0.0,
    "_RECORD_STALL_TIMEOUT": 0.05,
}


class _FakeProc:
    """只实现 poll 的假 ffmpeg 进程；alive=False 让看门狗线程自然退出。"""

    def __init__(self):
        self.alive = True
        self.pid = 0

    def poll(self):
        return None if self.alive else 0


@pytest.fixture()
def fast_guard(monkeypatch):
    for name, value in _FAST_GUARD.items():
        monkeypatch.setattr(audio_record, name, value)


def _wait_until(predicate, timeout=2.0, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# ---------- 看门狗：停增判定 ----------


def test_guard_kills_on_stall_when_not_paused(monkeypatch, fast_guard, tmp_path):
    """未暂停 + 文件停增 → 到期强杀并回调 reason；回调异常不影响强杀。"""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"\x00" * 100)
    proc = _FakeProc()
    killed, reasons = [], []
    monkeypatch.setattr(
        audio_record, "terminate_ffmpeg_proc", lambda p: killed.append(p)
    )

    def _bad_callback(reason):
        reasons.append(reason)
        raise RuntimeError("callback boom")

    audio_record.start_record_guard(proc, wav, on_force_terminate=_bad_callback)
    try:
        assert _wait_until(lambda: bool(killed))
    finally:
        proc.alive = False

    assert killed == [proc]
    assert reasons and "无增长" in reasons[0]


def test_guard_exempts_stall_while_paused(monkeypatch, fast_guard, tmp_path):
    """暂停期文件停增是预期（休眠停采）→ 不杀；恢复后采集仍死 → 照杀。"""
    wav = tmp_path / "b.wav"
    wav.write_bytes(b"\x00" * 100)
    proc = _FakeProc()
    killed = []
    monkeypatch.setattr(
        audio_record, "terminate_ffmpeg_proc", lambda p: killed.append(p)
    )
    paused = {"flag": True}
    audio_record.start_record_guard(
        proc, wav, is_paused=lambda: paused["flag"]
    )
    try:
        # 暂停期：停增阈值 5 倍时长内不得强杀
        time.sleep(_FAST_GUARD["_RECORD_STALL_TIMEOUT"] * 5)
        assert not killed

        # 恢复：停增窗口重新起算，到期照杀
        paused["flag"] = False
        assert _wait_until(lambda: bool(killed))
    finally:
        proc.alive = False


def test_guard_no_kill_while_file_grows(monkeypatch, fast_guard, tmp_path):
    """文件持续增长（正常录制）→ 不杀；写入停止 → 停增到期杀。"""
    wav = tmp_path / "c.wav"
    wav.write_bytes(b"\x00" * 100)
    proc = _FakeProc()
    killed = []
    monkeypatch.setattr(
        audio_record, "terminate_ffmpeg_proc", lambda p: killed.append(p)
    )
    audio_record.start_record_guard(proc, wav)
    stop_writing = threading.Event()

    def _writer():
        while not stop_writing.is_set():
            with open(wav, "ab") as f:
                f.write(b"\x01" * 32)
            time.sleep(0.01)

    writer = threading.Thread(target=_writer, daemon=True)
    writer.start()
    try:
        time.sleep(_FAST_GUARD["_RECORD_STALL_TIMEOUT"] * 5)
        assert not killed

        stop_writing.set()
        writer.join(timeout=1)
        assert _wait_until(lambda: bool(killed))
    finally:
        stop_writing.set()
        proc.alive = False


# ---------- 僵尸清理：paused 覆盖与定向清理 ----------


@pytest.fixture()
def recovery_env(monkeypatch):
    """隔离 task_store 与 realtime_store：全部替换为测试内假容器。"""
    saved_tasks = {}
    fake_dicts = {name: {} for name in (
        "realtime_transcribers", "realtime_diarizers", "realtime_summarizers",
        "realtime_chapter_generators", "realtime_translators",
        "realtime_speaker_maps", "realtime_full_transcripts",
        "realtime_full_sealed", "realtime_queues",
    )}
    monkeypatch.setattr(recording_recovery, "tasks", saved_tasks)
    monkeypatch.setattr(
        recording_recovery, "save_task_to_disk", lambda tid: None
    )
    monkeypatch.setattr(
        recording_recovery, "cleanup_silence_detection", lambda tid: None
    )
    for name, fake in fake_dicts.items():
        monkeypatch.setattr(recording_recovery, name, fake)
    return saved_tasks, fake_dicts


def test_zombie_cleanup_covers_paused_task(recovery_env):
    """paused 任务 + 无 task_id → 扫描命中并置 failed，实时资源被 pop。"""
    saved_tasks, fake_dicts = recovery_env
    saved_tasks["t1"] = {"id": "t1", "status": "paused"}
    for fake in fake_dicts.values():
        fake["t1"] = object()

    recording_recovery.cleanup_zombie_recording(reason="watchdog killed ffmpeg")

    assert saved_tasks["t1"]["status"] == "failed"
    assert saved_tasks["t1"]["error"] == "watchdog killed ffmpeg"
    for fake in fake_dicts.values():
        assert "t1" not in fake


def test_zombie_cleanup_covers_recording_task(recovery_env):
    """recording 任务（既有语义）不回归。"""
    saved_tasks, _ = recovery_env
    saved_tasks["t2"] = {"id": "t2", "status": "recording"}

    recording_recovery.cleanup_zombie_recording()

    assert saved_tasks["t2"]["status"] == "failed"


def test_zombie_cleanup_targeted_task_id(recovery_env):
    """指定 task_id → 只清该任务，其他 paused/recording 脏数据不受影响。"""
    saved_tasks, _ = recovery_env
    saved_tasks["t3"] = {"id": "t3", "status": "paused"}
    saved_tasks["t4"] = {"id": "t4", "status": "paused"}

    recording_recovery.cleanup_zombie_recording(
        task_id="t3", reason="targeted kill"
    )

    assert saved_tasks["t3"]["status"] == "failed"
    assert saved_tasks["t3"]["error"] == "targeted kill"
    assert saved_tasks["t4"]["status"] == "paused"


def test_zombie_cleanup_ignores_terminal_status(recovery_env):
    """completed/failed 等终态不触发清理。"""
    saved_tasks, _ = recovery_env
    saved_tasks["t5"] = {"id": "t5", "status": "completed"}
    saved_tasks["t6"] = {"id": "t6", "status": "failed"}

    recording_recovery.cleanup_zombie_recording()

    assert saved_tasks["t5"]["status"] == "completed"
    assert saved_tasks["t6"]["status"] == "failed"


# ---------- audio_stream 强杀联动 ----------


def test_handle_guard_forced_stop_syncs_paused_task(monkeypatch, recovery_env):
    """看门狗回调：置 _stream_running=False + 指定任务状态同步为 failed。"""
    saved_tasks, fake_dicts = recovery_env
    saved_tasks["t7"] = {"id": "t7", "status": "paused"}
    fake_dicts["realtime_transcribers"]["t7"] = object()

    monkeypatch.setattr(audio_stream, "_stream_task_id", "t7")
    monkeypatch.setattr(audio_stream, "_stream_running", True)

    audio_stream._handle_guard_forced_stop("guard reason")

    assert audio_stream._stream_running is False
    assert saved_tasks["t7"]["status"] == "failed"
    assert saved_tasks["t7"]["error"] == "guard reason"
    assert "t7" not in fake_dicts["realtime_transcribers"]


def test_handle_guard_forced_stop_without_stream_task(monkeypatch, recovery_env):
    """无进行中流式录制（task_id=None）→ 回调只置标志，不动任务。"""
    saved_tasks, _ = recovery_env
    saved_tasks["t8"] = {"id": "t8", "status": "paused"}

    monkeypatch.setattr(audio_stream, "_stream_task_id", None)
    monkeypatch.setattr(audio_stream, "_stream_running", True)

    audio_stream._handle_guard_forced_stop("guard reason")

    assert audio_stream._stream_running is False
    assert saved_tasks["t8"]["status"] == "paused"


# ---------- 静默检测：暂停时长扣除（2026-11-23 误关停事故） ----------


def test_get_stream_paused_seconds(monkeypatch):
    """累计暂停 = 已累计段 + 当前进行中的暂停段。"""
    base = time.time()
    monkeypatch.setattr(audio_stream, "_stream_paused_total", 30.0)
    monkeypatch.setattr(audio_stream, "_stream_paused", True)
    monkeypatch.setattr(audio_stream, "_stream_pause_start", base - 10.0)
    val = audio_stream.get_stream_paused_seconds()
    assert 39.9 <= val <= 40.5

    monkeypatch.setattr(audio_stream, "_stream_paused", False)
    monkeypatch.setattr(audio_stream, "_stream_pause_start", None)
    assert audio_stream.get_stream_paused_seconds() == 30.0


def _make_monitor_env(monkeypatch, *, asr_silent_sec, paused_sec):
    """构造 silence_monitor_loop 的受控环境，返回 (msgs, auto_stops)。"""
    import core.silence_detection as sd

    now = time.time()
    config = {
        "enabled": True,
        "presence": {"heartbeat_timeout_sec": 90, "threshold_warning": 50},
        "audio": {"asr_no_sentence_timeout_sec": 300},
        "action": {
            "gentle_countdown_sec": 120,
            "urgent_countdown_sec": 60,
            "max_warnings_per_session": 2,
        },
    }
    msgs, auto_stops = [], []
    monkeypatch.setattr(sd, "_MONITOR_INTERVAL", 0.01)
    monkeypatch.setattr(sd, "get_silence_detection_config", lambda: config)
    monkeypatch.setattr(sd, "get_stream_paused_seconds", lambda: paused_sec)
    monkeypatch.setattr(sd, "realtime_last_heartbeat", {"t1": now})
    monkeypatch.setattr(
        sd, "realtime_last_sentence", {"t1": now - asr_silent_sec}
    )
    monkeypatch.setattr(sd, "realtime_presence_scores", {"t1": 0.0})
    monkeypatch.setattr(
        sd, "push_realtime_msg",
        lambda tid, payload: msgs.append(payload),
    )

    async def _fake_auto_stop(tid, reason="unknown"):
        auto_stops.append(reason)

    monkeypatch.setattr(sd, "auto_stop_recording", _fake_auto_stop)
    return sd, msgs, auto_stops


def _make_recording_limiter(monkeypatch, sd, rounds):
    """允许监测循环跑 rounds 轮后自动退出（is_stream_recording 翻 False）。"""
    calls = {"n": 0}

    def _recording():
        calls["n"] += 1
        return calls["n"] <= rounds

    monkeypatch.setattr(sd, "is_stream_recording", _recording)


def test_silence_monitor_freezes_during_pause(monkeypatch):
    """暂停时长被扣除 → ASR 静默冻结在暂停前的值，不触发提醒/关停。"""
    # ASR 已静默 600s（>300s 阈值），但其中 590s 处于暂停 → 有效静默仅 10s
    sd, msgs, auto_stops = _make_monitor_env(
        monkeypatch, asr_silent_sec=600, paused_sec=590
    )
    _make_recording_limiter(monkeypatch, sd, rounds=2)

    asyncio.run(sd.silence_monitor_loop("t1"))

    assert msgs == []
    assert auto_stops == []


def test_silence_monitor_warns_when_not_paused(monkeypatch):
    """无暂停时 ASR 长静默 + 低存在感 → 照常触发温和提醒（既有语义不回归）。"""
    sd, msgs, auto_stops = _make_monitor_env(
        monkeypatch, asr_silent_sec=600, paused_sec=0
    )
    _make_recording_limiter(monkeypatch, sd, rounds=3)

    asyncio.run(sd.silence_monitor_loop("t1"))

    assert len(msgs) == 1
    assert msgs[0]["type"] == "presence_warning"
    assert msgs[0]["level"] == "gentle"
    assert auto_stops == []  # 温和提醒阶段未到关停
