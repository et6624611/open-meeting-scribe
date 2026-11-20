"""RealtimeTranscriber 会话失效自愈 + 暂停恢复重建（2026-11-19）。

事故：暂停录制 33s 后恢复，DashScope 直连识别器已被服务端空闲超时关闭，
feed_audio 每块只打一行 "Speech recognition has stopped." 日志，_started 仍为
True，整场后半段无转写且 UI 无感；本地声纹聚类不受影响，表现为
「人物识别到有人说话，但转写没有发生」。
"""

import asyncio

import core.realtime_asr as ra


class _DeadRecognition:
    def send_audio_frame(self, pcm: bytes) -> None:
        raise RuntimeError("Speech recognition has stopped.")


class _BrokenRecognition:
    def send_audio_frame(self, pcm: bytes) -> None:
        raise RuntimeError("audio frame too short")


def test_stopped_marks_dead_and_notifies_once(monkeypatch):
    errors: list[str] = []
    tr = ra.RealtimeTranscriber(on_error=errors.append)
    tr._started = True
    tr._recognition = _DeadRecognition()
    monkeypatch.setattr(tr, "_try_self_heal", lambda: None)

    tr.feed_audio(b"\x00\x00")

    assert tr.is_running is False
    assert tr._recognition is None
    assert len(errors) == 1 and "自动恢复" in errors[0]

    # 再次送帧不重复通知（_started 已为 False，由调用方 is_running 拦下）
    tr.feed_audio(b"\x00\x00")
    assert len(errors) == 1


def test_transient_failure_keeps_session():
    tr = ra.RealtimeTranscriber()
    tr._started = True
    tr._recognition = _BrokenRecognition()

    tr.feed_audio(b"\x00\x00")

    assert tr.is_running is True
    assert tr._recognition is not None


def test_restart_preserves_sentence_count(monkeypatch):
    tr = ra.RealtimeTranscriber()
    tr._started = True
    tr._sentence_count = 7
    monkeypatch.setattr(ra, "_get_asr_mode", lambda: "direct")

    def _fake_start_direct() -> None:
        tr._started = True

    monkeypatch.setattr(tr, "_start_direct", _fake_start_direct)

    assert tr.restart("测试重建") is True
    assert tr._sentence_count == 7


def test_restart_skipped_after_stop(monkeypatch):
    tr = ra.RealtimeTranscriber()
    tr._stopping = True
    monkeypatch.setattr(ra, "_get_asr_mode", lambda: "direct")

    assert tr.restart("测试重建") is False


def test_resume_restarts_after_long_pause(monkeypatch):
    import app.routers.record_state as rs

    calls: list[str] = []

    class _FakeTranscriber:
        def restart(self, reason: str = "") -> bool:
            calls.append(reason)
            return True

    monkeypatch.setattr(rs, "is_stream_recording", lambda: True)
    monkeypatch.setattr(
        rs,
        "get_stream_recording_info",
        lambda: {"task_id": "tid1234", "elapsed": 10, "paused": True},
    )
    monkeypatch.setattr(rs, "resume_recording_with_stream", lambda: None)
    monkeypatch.setattr(rs, "get_last_pause_duration", lambda: 33.8)
    rs.realtime_transcribers["tid1234"] = _FakeTranscriber()
    try:
        result = asyncio.run(rs.resume_record())
    finally:
        rs.realtime_transcribers.pop("tid1234", None)

    assert result["asr_restarted"] is True
    assert calls and "34s" in calls[0]


def test_resume_skips_short_pause(monkeypatch):
    import app.routers.record_state as rs

    calls: list[str] = []

    class _FakeTranscriber:
        def restart(self, reason: str = "") -> bool:
            calls.append(reason)
            return True

    monkeypatch.setattr(rs, "is_stream_recording", lambda: True)
    monkeypatch.setattr(
        rs,
        "get_stream_recording_info",
        lambda: {"task_id": "tid5678", "elapsed": 10, "paused": True},
    )
    monkeypatch.setattr(rs, "resume_recording_with_stream", lambda: None)
    monkeypatch.setattr(rs, "get_last_pause_duration", lambda: 3.0)
    rs.realtime_transcribers["tid5678"] = _FakeTranscriber()
    try:
        result = asyncio.run(rs.resume_record())
    finally:
        rs.realtime_transcribers.pop("tid5678", None)

    assert result["asr_restarted"] is False
    assert calls == []
