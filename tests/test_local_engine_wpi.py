"""
tests/test_local_engine_wpi.py — WP-I（R9 分段增量上屏，引擎侧）回归测试

覆盖 AC（见 WPH/WPI 本地上屏方案 20260924）：
- AC-I1: 段按能量 VAD 静音 / max_segment 兜底闭合；句子经 on_sentence_end
         以绝对毫秒时间戳逐段产出
- AC-I2: 单段 infer 失败/超时 → 只丢该段、引擎不 stop、推非错误 segment_skipped、
         后续段继续出句
- AC-I3: EngineHost 两级健康语义——单次超时不 stop；连续 N 次（可配置）才 stop；
         过期响应按 id 重同步丢弃；stdout 关闭（哨兵）即时 RuntimeError
- AC-I4: 句子负载不透传 FunASR 局部 spk（跨段说话人归属由 diarizer 增量聚类承担）
- AC-I5: 热词映射每段闭合时都过一遍
- AC-I6: D-I2 定稿——transcript_finalized_incremental 任务跳过 stage1 全量重跑，
         以 realtime_full_transcript 拼接定稿；增量内容为空时回退 stage1 兜底
- AC-I7: flag 默认开（WP-I 验收后 enabled=True，段参数默认 5/0.8/30）；显式关闭时
         local 录音仍走 RealtimeTranscriber → realtime_degraded_to_batch 状态声明
         （WP-H 逃生通道）；默认/开启时选用 LocalSegmentTranscriber
- AC-I8: 内存纪律——段闭合即释放缓冲；待推理队列有界，超限丢最旧段

打桩约定沿用 tests/test_local_engine_r1r2r3.py（主 venv 无 funasr/torch）。
"""

import json
import queue
import threading
import time
from pathlib import Path

import pytest

from core.errors import LocalEngineError
from core.realtime_local_asr import LocalSegmentTranscriber

SAMPLE_RATE = 16000
CHUNK_BYTES = 3200  # 100ms @ 16kHz/16bit/mono

# 测试用小段参数（真机默认 5/0.8/30，见 AC-I7 配置测试）
SEG_CFG = {"enabled": True, "min_segment_s": 1.0, "min_silence_s": 0.3, "max_segment_s": 4.0}


def _chunk(voiced: bool) -> bytes:
    """100ms PCM 块：voiced=3000 幅值方波（RMS≫阈值）；静音=全零。"""
    n = CHUNK_BYTES // 2
    if not voiced:
        return b"\x00\x00" * n
    out = bytearray()
    for i in range(n):
        v = 3000 if (i // 8) % 2 == 0 else -3000
        out += int(v).to_bytes(2, "little", signed=True)
    return bytes(out)


def _wait_for(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return pred()


class _FakeHost:
    """替身 EngineHost：start 恒 ok；infer 按 responses 序列回 canned/抛异常。

    responses 元素：Exception 实例 → 抛出；dict → 原样返回；None → 默认单句响应。
    block_event 置位前 infer 阻塞（用于队列背压测试）。
    """

    def __init__(self, responses=None, block_event=None):
        self.responses = list(responses or [])
        self.calls = []
        self.stop_calls = 0
        self.block_event = block_event

    def start(self):
        return {"ok": True, "already_running": True, "pid": 12345}

    def stop(self):
        self.stop_calls += 1
        return {"ok": True}

    def infer(self, task, params=None, timeout=None):
        if self.block_event is not None:
            assert self.block_event.wait(timeout=10), "block_event 未释放"
        idx = len(self.calls)
        self.calls.append({"task": task, "params": params, "timeout": timeout})
        resp = self.responses[idx] if idx < len(self.responses) else None
        if isinstance(resp, Exception):
            raise resp
        if isinstance(resp, dict):
            return resp
        return {
            "ok": True, "task": "asr", "engine": "local-funasr",
            "sentence_info": [{"start": 100, "end": 900, "spk": 0, "text": f"句{idx}"}],
        }


def _make_transcriber(monkeypatch, host, **kw):
    import core.realtime_local_asr as rla

    monkeypatch.setattr(rla, "get_engine_host", lambda: host)
    sentences, errors, statuses = [], [], []
    tr = LocalSegmentTranscriber(
        on_sentence_end=sentences.append,
        on_error=errors.append,
        on_status=statuses.append,
        segment_config=SEG_CFG,
        **kw,
    )
    return tr, sentences, errors, statuses


# ============================================================
# AC-I1 / AC-I4 / AC-I8 — 分段闭合与绝对时间轴
# ============================================================

class TestSegmentation:
    def test_segments_close_on_silence_and_emit_absolute_timestamps(self, monkeypatch):
        """AC-I1：静音≥min_silence 且段≥min_segment → 闭合；句子绝对毫秒时间戳逐段产出。"""
        host = _FakeHost()
        tr, sentences, errors, _ = _make_transcriber(monkeypatch, host)
        tr.start()
        try:
            for _ in range(20):  # 2.0s 语音
                tr.feed_audio(_chunk(voiced=True))
            for _ in range(3):   # 0.3s 静音 → 触发闭合（段=2.3s）
                tr.feed_audio(_chunk(voiced=False))
            assert _wait_for(lambda: len(host.calls) == 1), "第一段未闭合推理"
            # 增量产出：stop 前第一句已上屏（R9 目标「段闭合→上屏」）
            assert _wait_for(lambda: len(sentences) == 1)
            first = sentences[0]
            assert first["begin_time"] == 100        # offset 0 + 句内 100ms
            assert first["end_time"] == 900

            for _ in range(10):  # 1.0s 语音（不足闭合条件，留待 stop 末段）
                tr.feed_audio(_chunk(voiced=True))
            tr.stop()

            assert len(host.calls) == 2
            assert len(sentences) == 2
            second = sentences[1]
            # 第二段绝对偏移 = 第一段 23 chunks × 100ms = 2300ms
            assert second["begin_time"] == 2300 + 100
            assert second["end_time"] == 2300 + 900
            assert errors == []
        finally:
            if tr.is_running:
                tr.stop()

    def test_max_segment_forces_close_without_silence(self, monkeypatch):
        """AC-I1 边界：持续语音无静音 → max_segment_s 兜底强制闭合。"""
        host = _FakeHost()
        tr, sentences, _, _ = _make_transcriber(monkeypatch, host)
        tr.start()
        try:
            for _ in range(45):  # 4.5s 连续语音 > max_segment_s=4.0
                tr.feed_audio(_chunk(voiced=True))
            assert _wait_for(lambda: len(host.calls) >= 1), "max_segment 兜底未触发"
        finally:
            tr.stop()

    def test_sentence_payload_has_no_funasr_spk(self, monkeypatch):
        """AC-I4：不透传 FunASR 局部 spk（跨段不稳定）；说话人归属留给 diarizer。"""
        host = _FakeHost(responses=[{
            "ok": True, "engine": "local-funasr",
            "sentence_info": [
                {"start": 0, "end": 800, "spk": 3, "text": "甲说话"},
                {"start": 800, "end": 1600, "spk": 0, "text": "乙说话"},
            ],
        }])
        tr, sentences, _, _ = _make_transcriber(monkeypatch, host)
        tr.start()
        try:
            for _ in range(12):
                tr.feed_audio(_chunk(voiced=True))
            tr.stop()
            assert len(sentences) == 2
            for s in sentences:
                assert set(s.keys()) == {"text", "begin_time", "end_time"}
        finally:
            if tr.is_running:
                tr.stop()

    def test_buffer_released_after_close_and_queue_bounded(self, monkeypatch):
        """AC-I8：段闭合即释放缓冲；队列有界，超限丢最旧段并推 segment_skipped。"""
        import core.realtime_local_asr as rla

        gate = threading.Event()
        host = _FakeHost(block_event=gate)
        tr, _, _, statuses = _make_transcriber(monkeypatch, host)
        monkeypatch.setattr(rla, "MAX_PENDING_SEGMENTS", 2)
        tr.start()
        try:
            # 闭合 4 段（每段 1.0s 语音 + 0.3s 静音），worker 被 gate 阻塞 → 队列积压
            for _seg in range(4):
                for _ in range(10):
                    tr.feed_audio(_chunk(voiced=True))
                for _ in range(3):
                    tr.feed_audio(_chunk(voiced=False))
                # 闭合后当前缓冲必须已释放（不持有已闭合段 PCM）
                assert len(tr._buf) == 0
            assert _wait_for(lambda: tr.segments_dropped >= 1), "队列背压未丢段"
            assert tr._queue.qsize() <= 2
            skipped = [s for s in statuses if s.get("status") == "segment_skipped"]
            assert skipped, "丢段未推 segment_skipped 状态声明"
        finally:
            gate.set()
            tr.stop()
        assert tr._queue.qsize() == 0  # stop 排空后无残留


# ============================================================
# AC-I2 / AC-I5 — 单段失败隔离与热词
# ============================================================

class TestSegmentFailureIsolation:
    def test_failed_segment_dropped_engine_kept_next_segments_continue(self, monkeypatch):
        """AC-I2：首段 infer 抛 engine_timeout → 丢该段、不 stop 引擎、推非错误
        segment_skipped、后续段继续出句；on_error 绝不触发。"""
        host = _FakeHost(responses=[
            LocalEngineError("引擎响应超时（180s）", error_code="engine_timeout"),
            None,  # 第二段成功
        ])
        tr, sentences, errors, statuses = _make_transcriber(monkeypatch, host)
        tr.start()
        try:
            for _seg in range(2):
                for _ in range(10):
                    tr.feed_audio(_chunk(voiced=True))
                for _ in range(3):
                    tr.feed_audio(_chunk(voiced=False))
            tr.stop()

            assert len(sentences) == 1, "失败段之后的段未继续出句"
            # 第二段偏移 = 第一段 13 chunks × 100ms = 1300ms
            assert sentences[0]["begin_time"] == 1300 + 100
            assert errors == [], "丢段不得推 on_error（红色报错）"
            skipped = [s for s in statuses if s.get("status") == "segment_skipped"]
            assert len(skipped) == 1
            assert host.stop_calls == 0, "单段失败不得停引擎（D-I1）"
            assert tr.segments_dropped == 1
            assert tr.segments_inferred == 1
        finally:
            if tr.is_running:
                tr.stop()

    def test_hotword_mapping_applied_per_segment(self, monkeypatch):
        """AC-I5：热词映射每段闭合时都过一遍（坑②）。"""
        import core.realtime_local_asr as rla

        applied = []

        def _fake_apply(text, *a, **k):
            applied.append(text)
            return text.replace("吉达科技", "云端科技")

        monkeypatch.setattr(rla, "apply_hotword_mappings", _fake_apply)
        host = _FakeHost(responses=[
            {"ok": True, "sentence_info": [{"start": 0, "end": 800, "spk": 0, "text": "吉达科技开场"}]},
            {"ok": True, "sentence_info": [{"start": 0, "end": 800, "spk": 0, "text": "吉达科技收尾"}]},
        ])
        tr, sentences, _, _ = _make_transcriber(monkeypatch, host)
        tr.start()
        try:
            for _seg in range(2):
                for _ in range(10):
                    tr.feed_audio(_chunk(voiced=True))
                for _ in range(3):
                    tr.feed_audio(_chunk(voiced=False))
            tr.stop()
            assert len(applied) == 2, "热词映射必须每段都施加"
            assert [s["text"] for s in sentences] == ["云端科技开场", "云端科技收尾"]
        finally:
            if tr.is_running:
                tr.stop()


# ============================================================
# AC-I3 — EngineHost 两级健康语义
# ============================================================

class _FakeStdin:
    def write(self, s):
        pass

    def flush(self):
        pass


class _FakeProc:
    stdin = _FakeStdin()

    def poll(self):
        return None


def _bare_host() -> "object":
    import core.engine_host as eh

    host = eh.EngineHost()
    host._proc = _FakeProc()
    host._resp_queue = queue.Queue()
    return host


class TestEngineHostTwoLevelHealth:
    def test_single_timeout_keeps_process_consecutive_restarts(self, monkeypatch):
        """AC-I3：单次超时不 stop；连续 N 次（默认阈值改 3）才 stop。"""
        import core.engine_host as eh

        monkeypatch.setattr(eh, "ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS", 3)
        host = _bare_host()
        stopped = []
        monkeypatch.setattr(host, "stop", lambda: stopped.append(1) or {"ok": True})

        for i in range(2):
            with pytest.raises(TimeoutError):
                host.request("infer", {"task": "asr"}, timeout=0.05)
            assert stopped == [], f"第 {i + 1} 次超时不得 stop（请求级失败）"
        with pytest.raises(TimeoutError):
            host.request("infer", {"task": "asr"}, timeout=0.05)
        assert len(stopped) == 1, "连续 3 次超时应判进程级不健康并 stop"

    def test_threshold_configurable(self, monkeypatch):
        """AC-I3：N 可配置（阈值 1 → 单次超时即 stop）。"""
        import core.engine_host as eh

        monkeypatch.setattr(eh, "ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS", 1)
        host = _bare_host()
        stopped = []
        monkeypatch.setattr(host, "stop", lambda: stopped.append(1) or {"ok": True})
        with pytest.raises(TimeoutError):
            host.request("infer", timeout=0.05)
        assert len(stopped) == 1

    def test_success_resets_consecutive_counter(self, monkeypatch):
        """AC-I3：成功响应清零连续超时计数（2 次超时 + 1 次成功 + 2 次超时 ≠ 不健康）。"""
        import core.engine_host as eh

        monkeypatch.setattr(eh, "ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS", 3)
        host = _bare_host()
        stopped = []
        monkeypatch.setattr(host, "stop", lambda: stopped.append(1) or {"ok": True})

        for _ in range(2):
            with pytest.raises(TimeoutError):
                host.request("ping", timeout=0.05)
        # 第 3 次请求成功（响应 id=r3）
        host._resp_queue.put(json.dumps({"id": "r3", "ok": True}) + "\n")
        assert host.request("ping", timeout=1)["ok"] is True
        assert host._consecutive_timeouts == 0
        for _ in range(2):
            with pytest.raises(TimeoutError):
                host.request("ping", timeout=0.05)
        assert stopped == [], "计数被成功响应重置后不应触发重启"

    def test_stale_response_resync_by_id(self, monkeypatch):
        """AC-I3：超时请求的迟到响应按 id 重同步丢弃，不误配给后续请求。"""
        host = _bare_host()
        host._req_counter = 2          # 本次请求将拿到 id=r3
        host._stale_ids.update({"r1", "r2"})
        # r1/r2 为此前超时请求的迟到响应；r3 才是本次请求
        host._resp_queue.put(json.dumps({"id": "r1", "ok": True, "stale": True}) + "\n")
        host._resp_queue.put(json.dumps({"id": "r2", "ok": True, "stale": True}) + "\n")
        host._resp_queue.put(json.dumps({"id": "r3", "ok": True, "task": "asr"}) + "\n")
        resp = host.request("infer", timeout=2)
        assert resp["id"] == "r3"
        assert "stale" not in resp

    def test_stdout_sentinel_raises_unhealthy(self, monkeypatch):
        """AC-I3：stdout 关闭（None 哨兵=进程死亡/OOM）仍即时 RuntimeError。"""
        host = _bare_host()
        host._resp_queue.put(None)
        with pytest.raises(RuntimeError, match="意外退出"):
            host.request("ping", timeout=2)

    def test_id_mismatch_raises(self, monkeypatch):
        """AC-I3：非过期集合内的未知 id → ID 不匹配错误（协议异常）。"""
        host = _bare_host()
        host._resp_queue.put(json.dumps({"id": "zzz", "ok": True}) + "\n")
        with pytest.raises(RuntimeError, match="ID 不匹配"):
            host.request("ping", timeout=2)


# ============================================================
# AC-I6 — D-I2 定稿（pipeline_runner）
# ============================================================

class TestIncrementalFinalization:
    def _prepare(self, monkeypatch, task_extra):
        import core.pipeline_runner as pr

        tid = "task-wpi-test"
        task = {"task_id": tid, "audio_duration": 10.0, **task_extra}
        monkeypatch.setitem(pr.tasks, tid, task)
        stage2 = []
        monkeypatch.setattr(pr, "_run_stage2_for_task", lambda *a, **k: stage2.append(a))
        monkeypatch.setattr(pr, "save_task_to_disk", lambda *a, **k: None)
        monkeypatch.setattr(pr, "_cleanup_normalized_intermediate", lambda *a, **k: None)

        class _Joblog:
            STAGE_TRANSCRIBE = "transcribe"
            STAGE_VOICEPRINT = "voiceprint"
            STAGE_BIND = "bind"
            STAGE_SUMMARY = "summary"
            STAGE_ERROR = "error"

            @staticmethod
            def append_event(*a, **k):
                pass

        monkeypatch.setattr(pr, "joblog", _Joblog)
        return pr, tid, task, stage2

    def test_finalized_incremental_skips_stage1(self, monkeypatch):
        """AC-I6：增量定稿标记任务跳过 stage1 全量重跑，直接拼接进 stage2。"""
        pr, tid, task, stage2 = self._prepare(monkeypatch, {
            "transcript_finalized_incremental": True,
            "realtime_full_transcript": [
                {"text": "大家好", "speaker_id": 0, "speaker_name": "", "begin_time": 0, "end_time": 900},
                {"text": "开始开会", "speaker_id": 1, "speaker_name": "", "begin_time": 900, "end_time": 1800},
            ],
        })

        def _boom(*a, **k):
            raise AssertionError("D-I2 定稿任务不得重跑 stage1 全量转写")

        monkeypatch.setattr(pr, "run_pipeline_stage1", _boom)
        pr.run_pipeline_task(tid, Path("/tmp/x.wav"), "录音", None, 2)

        assert task["transcript_source"] == "local_incremental"
        assert [b["text"] for b in task["dialogue"]] == ["大家好", "开始开会"]
        assert task["speaker_count"] == 2
        assert len(stage2) == 1

    def test_empty_incremental_falls_back_to_stage1(self, monkeypatch):
        """AC-I6 边界：增量内容为空 → 撤销标记，回退 stage1 全量批转写兜底。"""
        pr, tid, task, _ = self._prepare(monkeypatch, {
            "transcript_finalized_incremental": True,
            # 无 realtime_full_transcript（如全部段被丢/纯静音）
        })
        stage1_hits = []

        def _stage1(*a, **k):
            stage1_hits.append(True)
            raise RuntimeError("stage1-reached-sentinel")

        monkeypatch.setattr(pr, "run_pipeline_stage1", _stage1)
        monkeypatch.setattr(pr, "estimate_speaker_count", lambda p: None)
        monkeypatch.setattr(pr, "classify_error", lambda e: {
            "category": "unknown", "message": str(e), "suggestion": "",
        })
        pr.run_pipeline_task(tid, Path("/tmp/x.wav"), "录音", None, 2)

        assert stage1_hits, "空增量未回退 stage1 兜底"
        assert task["transcript_finalized_incremental"] is False

    def test_finalize_helper_returns_false_on_empty(self, monkeypatch):
        """AC-I6：_finalize_incremental_transcript 对空转写返回 False（不触发 stage2）。"""
        pr, tid, task, stage2 = self._prepare(monkeypatch, {"realtime_full_transcript": []})
        assert pr._finalize_incremental_transcript(tid, Path("/tmp/x.wav")) is False
        assert stage2 == []


# ============================================================
# AC-I7 — 配置面与接线回归
# ============================================================

class TestConfigAndWiring:
    def test_segments_enabled_by_default(self, monkeypatch):
        """AC-I7/D-I3：WP-I 验收后默认 enabled=True；段参数默认 5/0.8/30（可经配置覆盖）。"""
        import app.settings_store as ss

        monkeypatch.delenv("ENGINE_MODE", raising=False)
        monkeypatch.setattr(ss, "load_settings", lambda: {})
        cfg = ss.get_engine_config()["local"]["realtime_segments"]
        assert cfg == {"enabled": True, "min_segment_s": 5.0, "min_silence_s": 0.8, "max_segment_s": 30.0}

    def test_segments_explicit_opt_out_preserved(self, monkeypatch):
        """逃生通道：settings.json 显式 enabled=false 时回到 WP-H 批转写口径。"""
        import app.settings_store as ss

        monkeypatch.delenv("ENGINE_MODE", raising=False)
        monkeypatch.setattr(ss, "load_settings", lambda: {
            "engine": {"mode": "local", "local": {"realtime_segments": {"enabled": False}}},
        })
        cfg = ss.get_engine_config()["local"]["realtime_segments"]
        assert cfg["enabled"] is False

    def test_segments_override_from_settings(self, monkeypatch):
        """AC-I7/D-I3：段参数可经 settings.json 覆盖（段长不拍死）。"""
        import app.settings_store as ss

        monkeypatch.delenv("ENGINE_MODE", raising=False)
        monkeypatch.setattr(ss, "load_settings", lambda: {
            "engine": {"mode": "local", "local": {"realtime_segments": {
                "enabled": True, "max_segment_s": 60,
            }}},
        })
        cfg = ss.get_engine_config()["local"]["realtime_segments"]
        assert cfg["enabled"] is True
        assert cfg["max_segment_s"] == 60.0
        assert cfg["min_segment_s"] == 5.0  # 未覆盖项取默认

    # ── record.start_record 接线（沿用 WP-H 测试的替身打法） ──

    def _run_start_record(self, monkeypatch, tmp_path, segments_enabled):
        import app.routers.record as rec
        import app.settings_store as ss
        import core.realtime_asr as ra
        import core.realtime_local_asr as rla
        import core.users
        from tests.test_local_engine_wph import (
            _cleanup_record_state,
            _FakeBG,
            _FakeDiarizer,
            _Flags,
        )

        constructed = {"realtime": 0, "local": 0}
        pushed = []
        done = threading.Event()

        class _FakeRealtime:
            def __init__(self, *a, **k):
                constructed["realtime"] += 1

            def start(self):
                raise LocalEngineError(
                    "本地引擎模式下实时预览降级为分段批处理",
                    error_code="realtime_degraded_to_batch", can_fallback_cloud=False,
                )

        class _FakeLocal:
            is_local_incremental = True

            def __init__(self, *a, **k):
                constructed["local"] += 1
                self.kwargs = k

            def start(self):
                pass

            @property
            def is_running(self):
                return True

            def stop(self):
                pass

        def _capture(task_id, msg):
            pushed.append(msg)
            done.set()

        monkeypatch.setattr(rec, "is_stream_recording", lambda: False)
        monkeypatch.setattr(core.users, "get_current_user", lambda: None)
        monkeypatch.setattr(rec, "create_realtime_diarizer", lambda: _FakeDiarizer())
        monkeypatch.setattr(rec, "get_feature_flags", lambda: _Flags())
        monkeypatch.setattr(rec, "start_recording_with_stream",
                            lambda **kw: {"output_path": str(tmp_path / "rec.wav")})
        monkeypatch.setattr(rec, "RealtimeTranscriber", _FakeRealtime)
        monkeypatch.setattr(rec, "push_realtime_msg", _capture)
        monkeypatch.setattr(ra, "_get_asr_mode", lambda: "local")
        monkeypatch.setattr(rla, "LocalSegmentTranscriber", _FakeLocal)
        monkeypatch.setattr(ss, "get_engine_config", lambda: {
            "mode": "local",
            "local": {"realtime_segments": {"enabled": segments_enabled,
                                            "min_segment_s": 5.0, "min_silence_s": 0.8,
                                            "max_segment_s": 30.0}},
        })

        result = rec.start_record(_FakeBG())
        return result, pushed, constructed, done, _cleanup_record_state

    def test_flag_off_keeps_degraded_status_declaration(self, monkeypatch, tmp_path):
        """AC-I7：flag 显式关闭（逃生通道）→ local 录音走 RealtimeTranscriber 降级状态声明（WP-H 行为）。"""
        result, pushed, constructed, done, cleanup = self._run_start_record(
            monkeypatch, tmp_path, segments_enabled=False)
        try:
            assert done.wait(timeout=5)
            assert constructed == {"realtime": 1, "local": 0}
            status = [m for m in pushed if m.get("type") == "status"]
            assert len(status) == 1 and status[0]["status"] == "local_batch_mode"
            assert not any(m.get("type") == "error" for m in pushed)
        finally:
            cleanup(result["task_id"])

    def test_flag_on_selects_local_segment_transcriber(self, monkeypatch, tmp_path):
        """AC-I7：flag 开启 → 选用 LocalSegmentTranscriber，正常启动无降级声明。"""
        result, pushed, constructed, done, cleanup = self._run_start_record(
            monkeypatch, tmp_path, segments_enabled=True)
        try:
            task_id = result["task_id"]
            import app.routers.record as rec
            assert _wait_for(lambda: constructed["local"] == 1), "未选用 LocalSegmentTranscriber"
            assert constructed["realtime"] == 0
            assert _wait_for(lambda: task_id in rec.realtime_transcribers), "增量转写器未注册"
            assert not any(m.get("type") in ("error", "status") for m in pushed)
        finally:
            cleanup(result["task_id"])
