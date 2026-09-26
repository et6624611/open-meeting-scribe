"""
tests/test_cli_engine.py — 智能体模式（本地 CLI 引擎）适配层单元测试

覆盖 / Covers:
  - event_bridge：stream-json → 规范 SSE 事件（工具配对/思考/整段 text/done/额度错误映射）
  - manifest：工具中文标签解析（含 mcp__ 归一、未知降级）、授权档位 argv 编译
  - probe：三段探针（安装/版本/登录）成功与各失败分支（打桩，不触真机 CLI）
  - context_export：工作区落盘于 agent-workspace/（非 data/，M3）、体量截断
  - M1 打字机切片
  - chat 路由：引擎不可用时 yield __fallback__ 哨兵（不触真机）

全部离线，不依赖本机 qoder 安装/登录/额度，也不发起任何网络或子进程。
运行 / Run: pytest tests/test_cli_engine.py -v
"""

import json
import time

import pytest

from core.cli_engine import event_bridge as eb
from core.cli_engine import manifest as mf
from core.cli_engine import probe as probe_mod

# ============================================================
# 真实 stream-json 样本（取自 .spike_qoder 取证，内联以保持自包含）
# ============================================================

LINE_INIT = json.dumps({
    "type": "system", "subtype": "init", "protocol_version": "1.4.0",
    "model": "Qwen3.8-Flash", "permissionMode": "dontAsk",
    "mcp_servers": [{"name": "spike-ping", "status": "connected"}],
    "session_id": "sess-abc",
})
LINE_HOOK = json.dumps({"type": "system", "subtype": "hook_response", "hook_name": "init"})
LINE_ARTIFACTS = json.dumps({"type": "system", "subtype": "artifacts_update", "artifacts": []})
LINE_ASSISTANT_TEXT = json.dumps({
    "type": "assistant",
    "message": {"content": [{"type": "text", "text": "三个文件读取完成"}]},
})
LINE_ASSISTANT_THINK = json.dumps({
    "type": "assistant",
    "message": {"content": [{"type": "thinking", "thinking": "需要并行读三个文件"}]},
})
LINE_TOOL_USE = json.dumps({
    "type": "assistant",
    "message": {"content": [
        {"type": "tool_use", "id": "call_1", "name": "Read", "input": {"file_path": "a.txt"}},
        {"type": "tool_use", "id": "call_2", "name": "Bash", "input": {"command": "ls"}},
    ]},
})
# tool_result 乱序回传（取证 §3.4：顺序 b→a），必须靠 tool_use_id 配对
LINE_TOOL_RESULT_2 = json.dumps({
    "type": "user",
    "message": {"content": [{"type": "tool_result", "tool_use_id": "call_2",
                             "content": "total 0", "is_error": None}]},
})
LINE_TOOL_RESULT_1 = json.dumps({
    "type": "user",
    "message": {"content": [{"type": "tool_result", "tool_use_id": "call_1",
                             "content": [{"type": "text", "text": "A内容1"}], "is_error": None}]},
})
LINE_DONE = json.dumps({
    "type": "result", "subtype": "success", "is_error": False, "num_turns": 2,
    "duration_ms": 10086, "stop_reason": "end_turn", "uuid": "u1",
    "usage": {"input_tokens": 5}, "modelUsage": {}, "permission_denials": [],
})
LINE_CREDIT_ERROR = json.dumps({
    "type": "result", "subtype": "error_during_execution", "is_error": True,
    "error_code": 118, "errors": ["You've reached your credit usage limit."],
    "usage": {}, "permission_denials": [], "duration_ms": 690,
})
LINE_DENIAL = json.dumps({
    "type": "result", "subtype": "success", "is_error": False, "num_turns": 1,
    "usage": {}, "duration_ms": 100,
    "permission_denials": [{"tool_name": "Write", "decision_reason": "needs approval"}],
})


@pytest.fixture
def manifest():
    return mf.load_manifest("qoder-cli")


# ============================================================
# event_bridge
# ============================================================

class TestEventBridge:
    def test_init_maps_to_stage_with_engine_info(self, manifest):
        evs = eb.parse_line(LINE_INIT, manifest)
        assert len(evs) == 1 and evs[0]["type"] == "stage"
        assert evs[0]["engine_init"]["session_id"] == "sess-abc"
        assert evs[0]["engine_init"]["mcp_servers"][0]["status"] == "connected"

    def test_noise_events_dropped(self, manifest):
        assert eb.parse_line(LINE_HOOK, manifest) == []
        assert eb.parse_line(LINE_ARTIFACTS, manifest) == []
        assert eb.parse_line("not json at all", manifest) == []
        assert eb.parse_line("", manifest) == []
        assert eb.parse_line("   ", manifest) == []

    def test_thinking_to_stage_text_to_token(self, manifest):
        assert eb.parse_line(LINE_ASSISTANT_THINK, manifest)[0]["type"] == "stage"
        tok = eb.parse_line(LINE_ASSISTANT_TEXT, manifest)[0]
        assert tok["type"] == "token" and tok["content"] == "三个文件读取完成"

    def test_parallel_tool_pairing_by_id(self, manifest):
        uses = eb.parse_line(LINE_TOOL_USE, manifest)
        assert [u["type"] for u in uses] == ["tool_call", "tool_call"]
        assert {u["id"] for u in uses} == {"call_1", "call_2"}
        assert uses[0]["label"] == "读取文件" and uses[1]["label"] == "执行命令"
        # 乱序结果按 tool_use_id 关联（不靠数组下标）
        r2 = eb.parse_line(LINE_TOOL_RESULT_2, manifest)[0]
        r1 = eb.parse_line(LINE_TOOL_RESULT_1, manifest)[0]
        assert r2["tool_use_id"] == "call_2" and r2["success"] is True
        assert r1["tool_use_id"] == "call_1" and "A内容1" in r1["summary"]

    def test_done_carries_latency_and_iterations(self, manifest):
        d = eb.parse_line(LINE_DONE, manifest)[0]
        assert d["type"] == "done"
        assert d["latency_ms"] == 10086 and d["engine_iterations"] == 2
        assert d["metadata"]["finish_reason"] == "end_turn"

    def test_credit_error_mapped(self, manifest):
        e = eb.parse_line(LINE_CREDIT_ERROR, manifest)[0]
        assert e["type"] == "error"
        assert e["engine_error"] == "credit_exhausted"
        assert "额度不足" in e["content"]

    def test_denials_forwarded_on_done(self, manifest):
        d = eb.parse_line(LINE_DENIAL, manifest)[0]
        assert d["type"] == "done" and len(d.get("permission_denials", [])) == 1

    def test_chunk_text_typewriter(self):
        pieces = eb.chunk_text("a" * 40, size=16)
        assert "".join(pieces) == "a" * 40
        assert all(len(p) <= 16 for p in pieces)
        assert eb.chunk_text("", 16) == []
        assert eb.chunk_text("short", 16) == ["short"]


# ============================================================
# manifest
# ============================================================

class TestManifest:
    def test_qoder_manifest_loads(self):
        m = mf.load_manifest("qoder-cli")
        assert m["binary"] == "qoder"
        assert m["capabilities"]["session_resume"] is True

    def test_unknown_engine_raises(self):
        with pytest.raises(FileNotFoundError):
            mf.load_manifest("no-such-engine")

    def test_tool_label_mcp_and_unknown(self, manifest):
        assert mf.resolve_tool_label(manifest, "Write")[0] == "写入文件"
        lab, icon = mf.resolve_tool_label(manifest, "mcp__oms__add_todos")
        assert "add_todos" in lab and icon == "🔌"
        lab2, icon2 = mf.resolve_tool_label(manifest, "TotallyNewTool")
        assert icon2 == "🔧"  # 未知降级样式，不裸显英文 name

    def test_auth_argv_tiers(self, manifest):
        ro = mf.compile_auth_argv(manifest, "readonly")
        assert "dont_ask" in ro and "Write" in ro and "Bash" in ro
        full = mf.compile_auth_argv(manifest, "full_task")
        assert "auto" in full and "Write" not in full
        # 未知档位安全回退 readonly（最小权限）
        assert mf.compile_auth_argv(manifest, "garbage") == ro


# ============================================================
# probe（打桩，不触真机）
# ============================================================

class _FakeCompleted:
    def __init__(self, out):
        self.stdout = out
        self.stderr = ""


class TestProbe:
    def test_probe_success(self, manifest, monkeypatch):
        monkeypatch.setattr(probe_mod.shutil, "which", lambda x: "/usr/bin/qoder")
        monkeypatch.setattr(probe_mod.subprocess, "run",
                            lambda *a, **k: _FakeCompleted("1.1.53") if "--version" in (a[0] if a else [])
                            else _FakeCompleted("Version: 1.1.53\nUsername: 永亮 王"))
        r = probe_mod.probe_engine(manifest)
        assert r["available"] is True and r["reason"] == "ok" and r["logged_in"] is True

    def test_probe_not_installed(self, manifest, monkeypatch):
        monkeypatch.setattr(probe_mod.shutil, "which", lambda x: None)
        r = probe_mod.probe_engine(manifest)
        assert r["available"] is False and r["reason"] == "not_installed"

    def test_probe_version_low(self, manifest, monkeypatch):
        monkeypatch.setattr(probe_mod.shutil, "which", lambda x: "/usr/bin/qoder")
        monkeypatch.setattr(probe_mod.subprocess, "run", lambda *a, **k: _FakeCompleted("0.9.1"))
        r = probe_mod.probe_engine(manifest)
        assert r["available"] is False and r["reason"] == "version_low"

    def test_probe_not_logged_in(self, manifest, monkeypatch):
        monkeypatch.setattr(probe_mod.shutil, "which", lambda x: "/usr/bin/qoder")
        calls = {"n": 0}

        def _run(cmd, *a, **k):
            calls["n"] += 1
            return _FakeCompleted("1.1.53") if "--version" in cmd else _FakeCompleted("Please login")
        monkeypatch.setattr(probe_mod.subprocess, "run", _run)
        r = probe_mod.probe_engine(manifest)
        assert r["available"] is False and r["reason"] == "not_logged_in"


# ============================================================
# context_export（写入临时仓库根，验证不落 data/）
# ============================================================

class TestContextExport:
    def test_export_writes_files_outside_data(self, monkeypatch, tmp_path):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        task = {
            "dialogue": [{"speaker_name": "张三", "sentences": [{"text": "建议 Q3 上线", "begin_time": 0}]}],
            "summary": "决定 Q3 上线。",
            "todos": [{"text": "出方案", "done": False}],
        }
        meta = ce.export_context(engine_id="qoder-cli", task=task, task_id="t1",
                                 user_message="总结决策", page_context="当前在会议页",
                                 role_prompt="你是纪要助手")
        ws = tmp_path / "agent-workspace" / "qoder-cli" / "t1"
        assert (ws / "AGENTS.md").is_file()
        assert (ws / "context" / "transcript.md").is_file()
        assert (ws / "context" / "summary.md").is_file()
        assert "张三" in (ws / "context" / "transcript.md").read_text(encoding="utf-8")
        assert "总结决策" in meta["brief"]
        # M3：工作区绝不在 data/ 之下
        assert "data" not in ws.parts

    def test_export_no_task_still_writes_agents(self, monkeypatch, tmp_path):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        meta = ce.export_context(engine_id="qoder-cli", task=None, task_id=None,
                                 user_message="你是谁")
        assert (tmp_path / "agent-workspace" / "qoder-cli" / "general" / "AGENTS.md").is_file()
        assert "你是谁" in meta["brief"]

    def test_export_writes_insights_md(self, monkeypatch, tmp_path):
        """REQ-INSIGHT-DECK-POSTMEETING R3：有洞察时导出 context/insights.md，无则不生成"""
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "t1.insights.json").write_text(json.dumps({"messages": [
            {"title": "资源冲突", "body": "测试与上线窗口重叠", "solution": "错峰", "diagram": "flowchart LR", "phase": "post_meeting"},
        ]}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(ce, "INSIGHTS_TASKS_DIR", tasks_dir)
        task = {"dialogue": [], "summary": "", "todos": []}
        ce.export_context(engine_id="qoder-cli", task=task, task_id="t1", user_message="写跟进邮件")
        f = tmp_path / "agent-workspace" / "qoder-cli" / "t1" / "context" / "insights.md"
        assert f.is_file()
        md = f.read_text(encoding="utf-8")
        assert "[会后] 资源冲突" in md
        assert "错峰" in md
        assert "```mermaid" in md

    def test_export_skips_insights_when_absent(self, monkeypatch, tmp_path):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        monkeypatch.setattr(ce, "INSIGHTS_TASKS_DIR", tmp_path / "no-here")
        task = {"dialogue": [], "summary": "", "todos": []}
        ce.export_context(engine_id="qoder-cli", task=task, task_id="t9", user_message="你好")
        assert not (tmp_path / "agent-workspace" / "qoder-cli" / "t9" / "context" / "insights.md").exists()


# ============================================================
# chat 路由回退（引擎不可用 → __fallback__，不触真机）
# ============================================================

class TestChatFallback:
    def test_probe_unavailable_yields_fallback(self, monkeypatch):
        import asyncio

        import app.routers.chat as chat
        monkeypatch.setattr(chat, "get_chat_engine_config", lambda: {
            "enabled": True, "engine_id": "qoder-cli", "model": None,
            "auth_tier": "readonly", "session_persistence": True, "cli_path_override": None})
        monkeypatch.setattr(chat, "load_manifest", lambda eid: mf.load_manifest("qoder-cli"))
        monkeypatch.setattr(chat, "probe_engine", lambda m, cli_path_override=None: {
            "available": False, "reason": "not_installed", "display_name": "Qoder CLI",
            "hint": "chatEngine.notInstalled"})
        data = chat.ChatRequest(message="hi", engine="agent", stream_id="s1")

        async def _collect():
            return [e async for e in chat._agent_engine_events(data, "hi", None)]

        evs = asyncio.run(_collect())
        assert any(e.get("type") == "stage" for e in evs)
        assert evs[-1]["type"] == "__fallback__"


class TestSessionIdDerivation:
    def test_chat_session_id_takes_priority_and_is_deterministic(self):
        import app.routers.chat as chat
        s1 = chat._deterministic_session_id("task-a", None, "sess-x")
        s2 = chat._deterministic_session_id("task-a", None, "sess-x")
        s3 = chat._deterministic_session_id("task-a", None, "sess-y")
        assert s1 == s2                      # 同面板会话 → 同 CLI 会话（可恢复）
        assert s1 != s3                      # 不同面板会话 → 不同 CLI 会话（互不串扰）
        # 无 chat_session_id 时回退 task_id
        assert chat._deterministic_session_id("task-a", None, None) == \
               chat._deterministic_session_id("task-a", None, None)


# ============================================================
# 意图自动分流器 v1（Phase 3）
# ============================================================

class TestIntentClassifier:
    def test_engineering_signals_route_to_agent(self):
        from core.cli_engine.intent import classify_engine_intent as c
        assert c("把这份纪要按公司模板整理成正式报告并保存到项目文件夹") == "agent"
        assert c("对比这几次会议的行动项完成情况，生成跟踪表") == "agent"
        assert c("更新纪要，补充待办") == "agent"
        assert c("写个脚本跑一下") == "agent"

    def test_light_qa_stays_builtin(self):
        from core.cli_engine.intent import classify_engine_intent as c
        assert c("这个会议谁提到了预算") == "qa"
        assert c("刚才那段总结一下") == "qa"

    def test_empty_and_none_default_qa(self):
        from core.cli_engine.intent import classify_engine_intent as c
        assert c("") == "qa"
        assert c(None) == "qa"


# ============================================================
# 工作区按保留期清理（Phase 3，R7/§3.10）
# ============================================================

class TestWorkspaceRetention:
    def test_sweep_removes_expired_only(self, monkeypatch, tmp_path):
        import os

        from core.cli_engine import context_export as ce
        root = tmp_path / "agent-workspace"
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", root)
        old = root / "qoder-cli" / "oldtask"
        fresh = root / "qoder-cli" / "newtask"
        old.mkdir(parents=True)
        fresh.mkdir(parents=True)
        # 把 old 的 mtime 拨到 30 天前
        past = 30 * 86400
        os.utime(old, (time.time() - past, time.time() - past))
        removed = ce.sweep_expired_workspaces(7)
        assert removed == 1
        assert not old.exists() and fresh.exists()

    def test_sweep_disabled_when_zero(self, monkeypatch, tmp_path):
        from core.cli_engine import context_export as ce
        root = tmp_path / "agent-workspace"
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", root)
        (root / "qoder-cli" / "t").mkdir(parents=True)
        assert ce.sweep_expired_workspaces(0) == 0
        assert (root / "qoder-cli" / "t").exists()
