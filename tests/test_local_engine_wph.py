"""
tests/test_local_engine_wph.py — WP-H（超时与降级口径收口）回归测试

覆盖 AC（见 WPH/WPI 本地上屏方案 20260924）：
- AC-H1: 本地批转写单请求超时按时长动态估算（不再固定 180s 整场判死）
- AC-H2: 超过支持上限（4h）报 audio_too_long 分类错误，不发引擎请求，音频文件保留
- AC-H3: 本地模式实时预览降级推 type:"status"（非错误状态声明），不再推 type:"error"；
         其余故障（其他 LocalEngineError / 普通异常）仍推 type:"error"
- AC-H4: 云端路径不回归（由既有测试套件全量回归承担，本文件不重复）

打桩约定沿用 tests/test_local_engine_r1r2r3.py（主 venv 无 funasr/torch）。
"""

import threading
import wave
from pathlib import Path

import pytest

from core.engine_host import (
    ENGINE_REQUEST_TIMEOUT,
    LOCAL_ASR_MAX_SUPPORTED_SECONDS,
    estimate_local_asr_timeout,
)
from core.errors import LocalEngineError, classify_error


def _write_wav(path, seconds=1.0, sample_rate=16000):
    """写一个最小合法 16k 单声道 wav（供 audio_path 存在性校验）。"""
    n = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n)
    return str(path)


class _FakeEngineHost:
    """替身常驻子进程宿主：捕获 infer 调用参数（含 timeout），回传 canned 响应。"""

    def __init__(self, resp=None):
        self._resp = resp if resp is not None else {
            "ok": True, "task": "asr", "engine": "local-funasr",
            "text": "", "sentence_info": [],
        }
        self.calls = []

    def infer(self, task, params=None, timeout=None):
        self.calls.append({"task": task, "params": params, "timeout": timeout})
        return self._resp


# ============================================================
# AC-H1 — estimate_local_asr_timeout 口径（单元）
# ============================================================

class TestEstimateTimeout:
    def test_none_or_nonpositive_falls_back_to_default(self):
        assert estimate_local_asr_timeout(None) == float(ENGINE_REQUEST_TIMEOUT)
        assert estimate_local_asr_timeout(0) == float(ENGINE_REQUEST_TIMEOUT)
        assert estimate_local_asr_timeout(-5) == float(ENGINE_REQUEST_TIMEOUT)

    def test_short_audio_clamped_to_floor(self):
        # 60s 音频：60×0.5+60=90s < 180s 下限 → 取下限
        assert estimate_local_asr_timeout(60) == float(ENGINE_REQUEST_TIMEOUT)

    def test_60min_audio_scales_with_duration(self):
        # 3600s：3600×0.5+60 = 1860s（> 180s 下限，< 上限）
        assert estimate_local_asr_timeout(3600) == pytest.approx(1860.0)

    def test_ceiling_caps_at_max_supported(self):
        ceiling = LOCAL_ASR_MAX_SUPPORTED_SECONDS * 0.5 + 60  # 4h → 7260s
        assert estimate_local_asr_timeout(LOCAL_ASR_MAX_SUPPORTED_SECONDS) == pytest.approx(ceiling)
        # 超过支持上限的入参也被封顶（防御性；transcribe 层会先报 audio_too_long）
        assert estimate_local_asr_timeout(LOCAL_ASR_MAX_SUPPORTED_SECONDS * 2) == pytest.approx(ceiling)

    def test_long_file_no_longer_bound_by_fixed_180s(self):
        # WP-H 缺陷复现的反证：90 分钟音频在旧口径（固定 180s）必被判死，
        # 新口径超时必须显著大于 180s
        assert estimate_local_asr_timeout(90 * 60) > ENGINE_REQUEST_TIMEOUT


# ============================================================
# AC-H1/H2 — _transcribe_local 接线（替身 EngineHost）
# ============================================================

class TestTranscribeLocalTimeout:
    def _call(self, tmp_path, monkeypatch, duration_s, host=None):
        import core.audio
        import core.transcribe as t

        wav = _write_wav(tmp_path / "long.wav")
        if isinstance(duration_s, Exception):
            def _raise(_path):
                raise duration_s
            monkeypatch.setattr(core.audio, "get_audio_duration", _raise)
        else:
            monkeypatch.setattr(core.audio, "get_audio_duration", lambda _p: duration_s)
        host = host if host is not None else _FakeEngineHost()
        monkeypatch.setattr(t, "_apply_local_hotword_mappings", lambda dialogue: dialogue)
        # get_engine_host / _cloud_fallback_available 在函数内 from core.engine_host import
        import core.engine_host as eh
        monkeypatch.setattr(eh, "get_engine_host", lambda: host)
        monkeypatch.setattr(eh, "_cloud_fallback_available", lambda: True)
        dialogue, transcription = t._transcribe_local(
            Path(wav), "paraformer-v2", True, None, None, None
        )
        return wav, host, dialogue, transcription

    def test_dynamic_timeout_passed_to_engine(self, tmp_path, monkeypatch):
        """AC-H1：60 分钟音频 → infer 收到时长感知超时（1860s），而非固定 180s。"""
        wav, host, _, _ = self._call(tmp_path, monkeypatch, 3600.0)
        assert len(host.calls) == 1
        assert host.calls[0]["task"] == "asr"
        assert host.calls[0]["timeout"] == pytest.approx(1860.0)
        assert host.calls[0]["params"]["audio_path"] == wav

    def test_duration_probe_failure_falls_back_to_default(self, tmp_path, monkeypatch):
        """AC-H1 边界：时长探测失败 → 退回默认 180s，转写照常发起（不整场失败）。"""
        _, host, _, _ = self._call(tmp_path, monkeypatch, RuntimeError("ffprobe boom"))
        assert len(host.calls) == 1
        assert host.calls[0]["timeout"] == pytest.approx(float(ENGINE_REQUEST_TIMEOUT))

    def test_over_limit_raises_audio_too_long_without_engine_call(self, tmp_path, monkeypatch):
        """AC-H2：超过 4h 支持上限 → audio_too_long，不发引擎请求，文件保留。"""
        over = LOCAL_ASR_MAX_SUPPORTED_SECONDS + 1
        host = _FakeEngineHost()
        wav, _, _, _ = None, None, None, None
        with pytest.raises(LocalEngineError) as ei:
            wav, host, _, _ = self._call(tmp_path, monkeypatch, float(over), host=host)
        err = ei.value
        assert err.error_code == "audio_too_long"
        assert err.can_fallback_cloud is True  # 桩定 _cloud_fallback_available=True
        assert err.detail["duration_s"] == float(over)
        assert err.detail["max_supported_s"] == LOCAL_ASR_MAX_SUPPORTED_SECONDS
        assert host.calls == []  # 未发起引擎请求
        # 音频文件保留（失败可恢复、不丢录音）
        wavs = list(tmp_path.glob("*.wav"))
        assert len(wavs) == 1 and wavs[0].exists()

    def test_exactly_at_limit_is_allowed(self, tmp_path, monkeypatch):
        """AC-H2 边界：恰好等于上限（4h）不报错，正常发起转写。"""
        _, host, _, _ = self._call(tmp_path, monkeypatch, float(LOCAL_ASR_MAX_SUPPORTED_SECONDS))
        assert len(host.calls) == 1


class TestClassifyAudioTooLong:
    def test_classify_error_has_actionable_suggestion(self):
        """AC-H2：audio_too_long 有专门的用户建议（切分文件/回退云端，音频保留）。"""
        err = LocalEngineError("too long", error_code="audio_too_long", can_fallback_cloud=True)
        info = classify_error(err)
        assert info["category"] == "local_engine"
        assert info["error_code"] == "audio_too_long"
        assert info["can_fallback_cloud"] is True
        assert info["suggestion"]
        assert info["suggestion"] != classify_error(
            LocalEngineError("x", error_code="inference_failed")
        )["suggestion"]


# ============================================================
# AC-H3 — record.start_record 本地降级状态声明（替身转写器）
# ============================================================

class _FakeBG:
    """替身 BackgroundTasks：记录但不执行后台任务。"""

    def __init__(self):
        self.added = []

    def add_task(self, fn, *a, **k):
        self.added.append(fn)


class _Flags(dict):
    """替身 feature flags：任意键默认 False。"""

    def __missing__(self, key):
        return False

    def get(self, key, default=None):
        return dict.get(self, key, False if default is None else default)


class _FakeDiarizer:
    def feed_audio(self, data, timestamp=None):
        pass

    def get_speaker(self, *a):
        return 0

    def get_active_speaker_count(self):
        return 0

    def get_active_speaker_ids(self):
        return []


class _RaisingTranscriber:
    """替身 RealtimeTranscriber：start() 抛指定异常。"""

    exc = None
    instances = []

    def __init__(self, *a, **k):
        _RaisingTranscriber.instances.append(self)

    def start(self):
        raise _RaisingTranscriber.exc

    @property
    def is_running(self):
        return False


def _run_start_record(monkeypatch, tmp_path, start_exc):
    """在替身环境下调用 record.start_record，返回 (result, pushed_messages, task_id)。

    只打桩到能安全走到 _start_transcriber_bg 的程度；不触发真实录音/ffmpeg。
    """
    import app.routers.record as rec
    import core.realtime_asr as ra
    import core.users

    _RaisingTranscriber.exc = start_exc
    _RaisingTranscriber.instances = []

    pushed = []
    done = threading.Event()

    def _capture(task_id, msg):
        pushed.append((task_id, msg))
        done.set()

    monkeypatch.setattr(rec, "is_stream_recording", lambda: False)
    monkeypatch.setattr(core.users, "get_current_user", lambda: None)
    monkeypatch.setattr(rec, "create_realtime_diarizer", lambda: _FakeDiarizer())
    monkeypatch.setattr(rec, "get_feature_flags", lambda: _Flags())
    monkeypatch.setattr(
        rec, "start_recording_with_stream",
        lambda **kw: {"output_path": str(tmp_path / "rec.wav")},
    )
    monkeypatch.setattr(rec, "RealtimeTranscriber", _RaisingTranscriber)
    monkeypatch.setattr(rec, "push_realtime_msg", _capture)
    monkeypatch.setattr(ra, "_get_asr_mode", lambda: "local")
    # WP-I 分段增量默认开后，本用例要覆盖的是逃生通道（segments 关闭）下
    # RealtimeTranscriber 启动抛错的降级口径——显式关闭分段，否则会走 LocalSegmentTranscriber。
    import app.settings_store as ss
    monkeypatch.setattr(ss, "get_engine_config", lambda: {
        "mode": "local",
        "local": {"realtime_segments": {"enabled": False}},
    })

    result = rec.start_record(_FakeBG())
    assert done.wait(timeout=5), "_start_transcriber_bg 未推送任何消息"
    return result, pushed, result["task_id"]


def _cleanup_record_state(task_id):
    import app.routers.record as rec

    for store_map in (
        rec.realtime_queues, rec.realtime_diarizers, rec.realtime_speaker_maps,
        rec.realtime_full_transcripts, rec.realtime_transcribers, rec.tasks,
    ):
        store_map.pop(task_id, None)


class TestLocalDegradationStatus:
    def test_degraded_to_batch_pushes_status_not_error(self, monkeypatch, tmp_path):
        """AC-H3：realtime_degraded_to_batch → type:"status" 状态声明，且不推 error。"""
        exc = LocalEngineError(
            "本地模式实时预览降级为分段批处理", error_code="realtime_degraded_to_batch",
            can_fallback_cloud=False,
        )
        result, pushed, task_id = _run_start_record(monkeypatch, tmp_path, exc)
        try:
            assert result["status"] == "recording"  # 录音本身不受影响
            types = [m.get("type") for _, m in pushed]
            assert "error" not in types
            status_msgs = [m for _, m in pushed if m.get("type") == "status"]
            assert len(status_msgs) == 1
            assert status_msgs[0]["status"] == "local_batch_mode"
            assert str(exc) in status_msgs[0]["message"]
        finally:
            _cleanup_record_state(task_id)

    def test_other_local_engine_error_still_pushes_error(self, monkeypatch, tmp_path):
        """AC-H3 边界：非降级类 LocalEngineError（如模型未就绪）仍按失败推 error。"""
        exc = LocalEngineError("模型未就绪", error_code="models_missing")
        _, pushed, task_id = _run_start_record(monkeypatch, tmp_path, exc)
        try:
            msgs = [m for _, m in pushed]
            assert any(m.get("type") == "error" for m in msgs)
            assert not any(m.get("type") == "status" for m in msgs)
        finally:
            _cleanup_record_state(task_id)

    def test_generic_exception_still_pushes_error(self, monkeypatch, tmp_path):
        """AC-H3 回归：普通异常路径行为不变（仍推 type:"error"）。"""
        _, pushed, task_id = _run_start_record(monkeypatch, tmp_path, RuntimeError("boom"))
        try:
            msgs = [m for _, m in pushed]
            assert any(m.get("type") == "error" for m in msgs)
        finally:
            _cleanup_record_state(task_id)
