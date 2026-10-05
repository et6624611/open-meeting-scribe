"""
tests/test_transcript_formal.py — WP-2 AI 书面版单测

覆盖：扁平化/签名、提示词契约、回填严格校验、切块与重试、running→done、
选区 upsert、stale 判定、会中/路由闸门 409、auto 开关、FastAPI 端点。
全程 monkeypatch 假 LLM，不发起任何真实网络调用。
"""

import json

import pytest

from core import transcript_formal as tf


# ============================================================
# 工厂 / 假 LLM
# ============================================================

def _dialogue(n=6, texts=None):
    sents = []
    for i in range(n):
        sents.append({
            "sentence_id": i,
            "begin_time": i * 1000,
            "end_time": i * 1000 + 900,
            "text": (texts[i] if texts else f"嗯，这个方案{i}吧，我们下周再说。"),
        })
    return [{"speaker_id": 0, "text": "".join(s["text"] for s in sents), "sentences": sents}]


def _task(dialogue, status="completed"):
    return {"task_id": "t1", "status": status, "dialogue": dialogue}


class _FakeResult:
    def __init__(self, content, tokens=10):
        self.content = content
        self.usage = {"prompt_tokens": tokens, "completion_tokens": tokens, "total_tokens": tokens * 2}


def _extract_ids(messages):
    """从 user prompt 中抽出输入 JSON 的 sentence_id 列表。"""
    user = messages[-1]["content"]
    for line in user.splitlines():
        line = line.strip()
        if line.startswith("["):
            return [it["sentence_id"] for it in json.loads(line)]
    raise AssertionError("input array not found in prompt")


def _make_fake_llm(*, fail_times=0, hard=False, call_log=None):
    """返回假 chat_completion_full：原文加「书面」前缀，含“吧”置 weakened。"""
    state = {"calls": 0}

    def _fake(messages, model=None, temperature=0.2):
        state["calls"] += 1
        if call_log is not None:
            call_log.append(messages)
        if state["calls"] <= fail_times:
            if hard:
                raise RuntimeError("llm down")
            raise RuntimeError("transient")
        ids = _extract_ids(messages)
        # 从输入数组拿原文（简单再解析一次）
        user = messages[-1]["content"]
        inputs = None
        for line in user.splitlines():
            line = line.strip()
            if line.startswith("["):
                inputs = json.loads(line)
        out = []
        for it, sid in zip(inputs, ids):
            text = it["text"]
            out.append({
                "sentence_id": sid,
                "text": f"书面化：{text}",
                "tone_flag": "weakened" if "吧" in text or "再说" in text else None,
            })
        return _FakeResult(json.dumps(out, ensure_ascii=False))
    _fake.state = state
    return _fake


@pytest.fixture
def _guards(monkeypatch):
    """统一的存储/路由/LLM 闸门：默认路由可用，无网络调用。"""
    import app.store
    # 清理同会话其它用例可能残留的 sidecar / in-flight
    p = tf.formal_sidecar_path("t1")
    if p.exists():
        p.unlink()
    tf._inflight.discard("t1")
    monkeypatch.setitem(app.store.tasks, "t1", _task(_dialogue()))
    monkeypatch.setattr(tf, "llm_route_guard", lambda: {"route": "direct", "source": "byok", "reason": ""})
    return app.store


# ============================================================
# 纯函数
# ============================================================

class TestFlattenAndSignature:
    def test_flatten_keeps_ids_and_order(self):
        flat = tf.flatten_sentences(_dialogue(3))
        assert [s["sentence_id"] for s in flat] == [0, 1, 2]
        assert flat[1]["begin_time"] == 1000

    def test_flatten_fallback_index_when_missing_id(self):
        d = _dialogue(2)
        del d[0]["sentences"][0]["sentence_id"]
        flat = tf.flatten_sentences(d)
        assert [s["sentence_id"] for s in flat] == [0, 1]

    def test_signature_stable_then_drifts_on_text_edit(self):
        d = _dialogue()
        s1 = tf.source_signature(d)
        s2 = tf.source_signature(json.loads(json.dumps(d, ensure_ascii=False)))
        assert s1 == s2 and s1["count"] == 6
        d[0]["sentences"][2]["text"] = "被回溯修正的句子"
        s3 = tf.source_signature(d)
        assert s3["hash"] != s1["hash"]

    def test_prompt_contract_locks(self):
        prompt = tf.build_user_prompt([{"sentence_id": 7, "begin_time": 0, "text": "行吧"}])
        assert '"sentence_id": 7' in prompt
        assert "tone_flag" in tf.SYSTEM_PROMPT and "weakened" in tf.SYSTEM_PROMPT
        # 事实/数字/专名保留是硬契约
        assert "不得增删任何事实" in tf.SYSTEM_PROMPT


class TestParseChunk:
    def test_ok_with_fence(self):
        ids = [1, 2]
        raw = "```json\n" + json.dumps([
            {"sentence_id": 1, "text": "a", "tone_flag": None},
            {"sentence_id": 2, "text": "b", "tone_flag": "weakened"},
        ]) + "\n```"
        items = tf.parse_chunk_response(raw, ids)
        assert items[1]["tone_flag"] == "weakened"

    def test_unknown_flag_treated_as_none_when_falsy(self):
        items = tf.parse_chunk_response(
            json.dumps([{"sentence_id": 0, "text": "a", "tone_flag": ""}]), [0])
        assert items[0]["tone_flag"] is None

    def test_count_mismatch(self):
        with pytest.raises(ValueError, match="count_mismatch"):
            tf.parse_chunk_response(json.dumps([{"sentence_id": 0, "text": "a"}]), [0, 1])

    def test_id_mismatch(self):
        with pytest.raises(ValueError, match="id_mismatch"):
            tf.parse_chunk_response(
                json.dumps([{"sentence_id": 9, "text": "a"}]), [0])

    def test_non_array_and_empty_text(self):
        with pytest.raises(ValueError, match="not_array"):
            tf.parse_chunk_response("{}", [0])
        with pytest.raises(ValueError, match="empty_text"):
            tf.parse_chunk_response(json.dumps([{"sentence_id": 0, "text": "  "}]), [0])

    def test_garbage_non_json(self):
        with pytest.raises(ValueError, match="json_parse_failed"):
            tf.parse_chunk_response("不是JSON", [0])


# ============================================================
# 生成主流程
# ============================================================

class TestGenerate:
    def test_full_generation_done_sidecar(self, _guards, monkeypatch):
        fake = _make_fake_llm()
        monkeypatch.setattr("core.llm.chat_completion_full", fake)
        doc = tf.generate_formal_version("t1")
        assert doc["status"] == "done"
        assert doc["scope"] == "full"
        assert [it["sentence_id"] for it in doc["items"]] == [0, 1, 2, 3, 4, 5]
        # 含“吧/再说”的句子被置 weakened
        assert all(it["tone_flag"] == "weakened" for it in doc["items"])
        assert doc["usage"]["total_tokens"] == 20
        assert doc["finished_at"]
        # 落盘可回读
        loaded = tf.load_formal("t1", _dialogue())
        assert loaded["status"] == "done"

    def test_chunking_25_boundary(self, _guards, monkeypatch):
        import app.store
        app.store.tasks["t1"] = _task(_dialogue(30))
        calls = []
        fake = _make_fake_llm(call_log=calls)
        monkeypatch.setattr("core.llm.chat_completion_full", fake)
        doc = tf.generate_formal_version("t1")
        assert doc["status"] == "done"
        assert len(doc["items"]) == 30
        assert len(calls) == 2  # 25 + 5
        assert len(_extract_ids(calls[0])) == 25
        assert len(_extract_ids(calls[1])) == 5

    def test_chunk_retry_once_then_success(self, _guards, monkeypatch):
        fake = _make_fake_llm(fail_times=1)
        monkeypatch.setattr("core.llm.chat_completion_full", fake)
        doc = tf.generate_formal_version("t1")
        assert doc["status"] == "done"
        assert fake.state["calls"] == 2

    def test_chunk_hard_fail_marks_error_no_half_items(self, _guards, monkeypatch):
        fake = _make_fake_llm(fail_times=2, hard=True)
        monkeypatch.setattr("core.llm.chat_completion_full", fake)
        doc = tf.generate_formal_version("t1")
        assert doc["status"] == "error"
        assert doc["items"] == []  # 整场失败不留半截
        assert doc["error"].startswith("chunk_failed")

    def test_requires_postmeeting(self, _guards, monkeypatch):
        import app.store
        app.store.tasks["t1"] = _task(_dialogue(), status="recording")
        with pytest.raises(tf.FormalizeError) as ei:
            tf.generate_formal_version("t1")
        assert ei.value.code == "formalize_requires_postmeeting"

    def test_route_unavailable_blocks(self, _guards, monkeypatch):
        def _boom():
            raise tf.FormalizeError("formalize_route_unavailable", reason="byok_key_missing_cloud_unavailable")
        monkeypatch.setattr(tf, "llm_route_guard", _boom)
        with pytest.raises(tf.FormalizeError, match="formalize_route_unavailable"):
            tf.generate_formal_version("t1")

    def test_route_guard_maps_blocked_reasons(self, monkeypatch):
        import core.routing
        for reason in ("source_not_set", "trial_quota_exhausted",
                       "byok_key_missing_cloud_unavailable", "local_endpoint_misconfigured"):
            monkeypatch.setattr(
                core.routing, "get_routing_decision",
                lambda _ctx, r=reason: {"route": "direct", "source": "byok", "reason": r},
            )
            with pytest.raises(tf.FormalizeError):
                tf.llm_route_guard()
        # 同意自动改用后落到体验配额（route=cloud）仍可用
        monkeypatch.setattr(
            core.routing, "get_routing_decision",
            lambda _ctx: {"route": "cloud", "source": "trial",
                          "reason": "byok_key_missing", "auto_switched": True},
        )
        d = tf.llm_route_guard()
        assert d["source"] == "trial"

    def test_already_running(self, _guards, monkeypatch):
        tf._inflight.add("t1")
        try:
            with pytest.raises(tf.FormalizeError, match="formalize_already_running"):
                tf.generate_formal_version("t1")
        finally:
            tf._inflight.discard("t1")

    def test_auto_disabled_skips_without_llm(self, _guards, monkeypatch):
        import app.store
        monkeypatch.setattr(app.store, "get_transcript_config",
                            lambda: {"formal": {"auto_generate": False}})
        called = {"n": 0}
        monkeypatch.setattr("core.llm.chat_completion_full",
                            lambda *a, **k: called.__setitem__("n", called["n"] + 1))
        assert tf.generate_formal_version("t1", auto=True) == {"skipped": "auto_disabled"}
        assert called["n"] == 0

    def test_auto_enabled_runs(self, _guards, monkeypatch):
        import app.store
        monkeypatch.setattr(app.store, "get_transcript_config",
                            lambda: {"formal": {"auto_generate": True}})
        monkeypatch.setattr("core.llm.chat_completion_full", _make_fake_llm())
        doc = tf.generate_formal_version("t1", auto=True)
        assert doc["status"] == "done" and doc["auto"] is True


class TestStalenessAndSelection:
    def test_stale_after_text_correction(self, _guards, monkeypatch):
        monkeypatch.setattr("core.llm.chat_completion_full", _make_fake_llm())
        tf.generate_formal_version("t1")
        changed = _dialogue()
        changed[0]["sentences"][0]["text"] = "嗯，修正后的句子。"
        loaded = tf.load_formal("t1", changed)
        assert loaded["status"] == "stale"
        # 文件本身未被改写
        assert tf.load_formal("t1")["status"] == "done"

    def test_selection_upsert_merges_items(self, _guards, monkeypatch):
        import app.store
        # 整场
        monkeypatch.setattr("core.llm.chat_completion_full", _make_fake_llm())
        tf.generate_formal_version("t1")
        # 选区重写 id=2，返回不同文本
        class Sel:
            def __call__(self, messages, model=None, temperature=0.2):
                return _FakeResult(json.dumps(
                    [{"sentence_id": 2, "text": "选区书面句", "tone_flag": None}],
                    ensure_ascii=False))
        monkeypatch.setattr("core.llm.chat_completion_full", Sel())
        doc = tf.generate_formal_version("t1", [2])
        assert doc["scope"] == "selection"
        assert len(doc["items"]) == 6  # upsert，不丢其余句
        assert next(i for i in doc["items"] if i["sentence_id"] == 2)["text"] == "选区书面句"

    def test_full_generation_replaces_items(self, _guards, monkeypatch):
        import app.store
        monkeypatch.setattr("core.llm.chat_completion_full", _make_fake_llm())
        tf.generate_formal_version("t1")
        # 原文变化后整场重生成（签名以当前 dialogue 为准，不判 stale）
        d = _dialogue(4)
        app.store.tasks["t1"] = _task(d)
        doc = tf.generate_formal_version("t1")
        assert doc["status"] == "done" and len(doc["items"]) == 4


# ============================================================
# HTTP 端点
# ============================================================

class TestEndpoints:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.server import app
        with TestClient(app) as c:
            yield c

    def test_post_requires_postmeeting_409(self, client, _guards, monkeypatch):
        import app.store
        app.store.tasks["t1"] = _task(_dialogue(), status="processing")
        r = client.post("/api/tasks/t1/formalize", json={})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "formalize_requires_postmeeting"

    def test_post_route_blocked_409(self, client, _guards, monkeypatch):
        def _boom():
            raise tf.FormalizeError("formalize_route_unavailable", reason="source_not_set")
        monkeypatch.setattr(tf, "llm_route_guard", _boom)
        r = client.post("/api/tasks/t1/formalize", json={})
        assert r.status_code == 409
        assert r.json()["detail"]["reason"] == "source_not_set"

    def test_get_404_when_never_generated(self, client, _guards):
        r = client.get("/api/tasks/t1/formal")
        assert r.status_code == 404

    def test_post_then_get_running_then_done(self, client, _guards, monkeypatch):
        # BackgroundTasks 在 TestClient 中同步执行：假 LLM 立即跑完
        monkeypatch.setattr("core.llm.chat_completion_full", _make_fake_llm())
        r = client.post("/api/tasks/t1/formalize", json={})
        assert r.status_code == 200 and r.json()["status"] == "running"
        r2 = client.get("/api/tasks/t1/formal")
        assert r2.status_code == 200 and r2.json()["status"] == "done"

    def test_post_invalid_ids_422(self, client, _guards):
        assert client.post("/api/tasks/t1/formalize", json={"sentence_ids": []}).status_code == 422
        assert client.post("/api/tasks/t1/formalize", json={"sentence_ids": ["x"]}).status_code == 422

    def test_task_missing_404(self, client, _guards):
        assert client.post("/api/tasks/nope/formalize", json={}).status_code == 404
