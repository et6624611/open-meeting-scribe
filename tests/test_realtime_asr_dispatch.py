"""tests/test_realtime_asr_dispatch.py — 实时转写厂商分派与会话失效。"""

import core.realtime_asr as ra
import core.realtime_asr_providers as providers
from core.realtime_asr_providers import RealtimeSessionClosed


class _FakeProvider:
    def __init__(self):
        self.started = False
        self.frames: list[bytes] = []
        self.stopped = False

    def start(self):
        self.started = True

    def send_audio_frame(self, pcm):
        self.frames.append(pcm)

    def stop(self):
        self.stopped = True


def test_explicit_volcengine_uses_provider(monkeypatch):
    import core.settings_store as ss

    fake = _FakeProvider()
    monkeypatch.setattr(
        ss,
        "get_realtime_asr_config",
        lambda: {
            "provider": "volcengine",
            "resolved_provider": "volcengine",
            "model": "bigmodel",
            "diarization": "auto",
            "credentials": {"api_key": "k", "resource_id": "volc.seedasr.sauc.duration"},
        },
    )
    monkeypatch.setattr(providers, "create_provider", lambda *a, **kw: fake)

    tr = ra.RealtimeTranscriber()
    tr.start()

    assert fake.started is True
    assert tr.is_running is True

    tr.feed_audio(b"pcm")
    assert fake.frames == [b"pcm"]

    tr.stop()
    assert fake.stopped is True


def test_session_closed_triggers_single_notice(monkeypatch):
    errors: list[str] = []

    class _Closed(_FakeProvider):
        def send_audio_frame(self, pcm):
            raise RealtimeSessionClosed("closed")

    tr = ra.RealtimeTranscriber(on_error=errors.append)
    tr._started = True
    tr._recognition = _Closed()
    monkeypatch.setattr(tr, "_try_self_heal", lambda: None)

    tr.feed_audio(b"x")
    assert tr.is_running is False
    assert tr._recognition is None
    assert len(errors) == 1

    tr.feed_audio(b"x")
    assert len(errors) == 1
