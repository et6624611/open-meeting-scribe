"""
tests/test_cli_engine.py — 智能体模式（本地 CLI 引擎）适配层单元测试

覆盖 / Covers:
  - event_bridge：stream-json → 规范 SSE 事件（工具配对/思考/整段 text/done/额度错误映射）
    + event_schema 通用映射（非 stream-json 形状引擎）
  - manifest：工具双语标签解析（含 mcp__ 归一、未知降级）、授权档位 argv 编译（含逐档 flag 覆盖）
  - probe：三段探针（安装/版本/登录）成功与各失败分支（打桩，不触真机 CLI）
  - context_export：工作区落盘于 agent-workspace/（非 data/，M3）、体量截断
  - M1 打字机切片
  - chat 路由：引擎不可用时 yield __fallback__ 哨兵（不触真机）
  - 多 CLI 适配：claude-code 清单加载/argv 编译、chat-engine 端点引擎枚举、engine_id 动态白名单

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
        # i18n 化：携前端键与插值参数（引擎名不硬嵌厂商）
        assert e["hint_key"] == "cli_engine_credit_exhausted"
        assert e["hint_params"]["engine"] == "Qoder CLI"

    def test_init_and_tool_call_carry_i18n_fields(self, manifest):
        init = eb.parse_line(LINE_INIT, manifest)[0]
        assert init["hint_key"] == "cli_engine_started"
        tool = eb.parse_line(LINE_TOOL_USE, manifest)[0]
        assert tool["label"] == "读取文件" and tool["label_en"] == "Read file"
        assert tool["icon"] == "file-text"  # lucide 名（前端内联 SVG 渲染）

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
# event_schema 通用映射（非 stream-json 形状引擎的预留扩展点）
# ============================================================

class TestEventSchema:
    SCHEMA_MANIFEST = {
        "display_name": "Some CLI",
        "event_schema": {
            "type_path": "kind",
            "text_path": "payload.message",
            "done_types": ["finished"],
            "error_types": ["failed"],
            "error_path": "payload.reason",
        },
    }

    def test_schema_text_and_done(self):
        tok = eb.parse_line(json.dumps({"kind": "delta", "payload": {"message": "hi"}}), self.SCHEMA_MANIFEST)
        assert tok[0]["type"] == "token" and tok[0]["content"] == "hi"
        done = eb.parse_line(json.dumps({"kind": "finished", "payload": {}}), self.SCHEMA_MANIFEST)
        assert done[-1]["type"] == "done"

    def test_schema_error_carries_i18n(self):
        evs = eb.parse_line(json.dumps({"kind": "failed", "payload": {"reason": "boom"}}), self.SCHEMA_MANIFEST)
        assert evs[0]["type"] == "error" and evs[0]["hint_key"] == "cli_engine_error"
        assert evs[0]["hint_params"]["engine"] == "Some CLI" and evs[0]["hint_params"]["detail"] == "boom"

    def test_schema_unknown_shapes_ignored(self):
        assert eb.parse_line(json.dumps({"kind": "noise", "whatever": 1}), self.SCHEMA_MANIFEST) == []
        assert eb.parse_line(json.dumps({"no_kind": True}), self.SCHEMA_MANIFEST) == []


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
        lab, lab_en, icon = mf.resolve_tool_label(manifest, "mcp__oms__add_todos")
        assert "add_todos" in lab and "add_todos" in lab_en and icon == "plug"
        lab2, _en2, icon2 = mf.resolve_tool_label(manifest, "TotallyNewTool")
        assert icon2 == "wrench"  # 未知降级样式，不裸显英文 name

    def test_tool_label_bilingual_and_fallback(self, manifest):
        # 双语：zh/en 同时可得（前端按 locale 选取）
        zh, en, icon = mf.resolve_tool_label(manifest, "Read", locale="en")
        assert zh == "读取文件" and en == "Read file" and icon == "file-text"
        # 缺失语言回退另一语言（不阻断解析）
        partial = {"tool_labels": {"OnlyZh": {"zh": "仅中文", "icon": "wrench"}}}
        assert mf.resolve_tool_label(partial, "OnlyZh") == ("仅中文", "仅中文", "wrench")
        only_en = {"tool_labels": {"OnlyEn": {"en": "Write doc", "icon": "pen-line"}}}
        assert mf.resolve_tool_label(only_en, "OnlyEn") == ("Write doc", "Write doc", "pen-line")

    def test_auth_argv_tiers(self, manifest):
        ro = mf.compile_auth_argv(manifest, "readonly")
        assert "dont_ask" in ro and "Write" in ro and "Bash" in ro
        full = mf.compile_auth_argv(manifest, "full_task")
        assert "auto" in full and "Write" not in full
        # 未知档位安全回退 readonly（最小权限）
        assert mf.compile_auth_argv(manifest, "garbage") == ro

    def test_claude_code_manifest_loads(self):
        """多 CLI 适配样例：claude-code 清单可加载，能力诚实声明（无 add_dir，工作区走 cwd）。"""
        m = mf.load_manifest("claude-code")
        assert m["binary"] == "claude"
        assert m["capabilities"]["add_dir"] is False
        assert m["argv"]["workspace_flag"] is None  # 无 -w 类标志 → runner 用进程 cwd 兜底
        assert m["name_key"] == "cliengine_engine_claude_code"

    def test_claude_code_auth_argv(self):
        """逐档 flag 覆盖：Claude 用 --disallowedTools（驼峰），权限模式取值与 Qoder 不同。"""
        m = mf.load_manifest("claude-code")
        ro = mf.compile_auth_argv(m, "readonly")
        assert "--permission-mode" in ro and "default" in ro
        assert "--disallowedTools" in ro and "Bash" in ro
        ww = mf.compile_auth_argv(m, "workspace_write")
        assert "acceptEdits" in ww
        full = mf.compile_auth_argv(m, "full_task")
        assert "bypassPermissions" in full and "Write" not in full
        # 未知档位回退 readonly（最小权限）
        assert mf.compile_auth_argv(m, "garbage") == ro


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


class TestListModels:
    """list_models：就地切换的 CLI 模型清单发现（全离线，不触真机）。"""

    def test_unsupported_without_models_cmd(self, monkeypatch):
        monkeypatch.setattr(probe_mod.shutil, "which", lambda x: "/usr/bin/x")
        r = probe_mod.list_models({"binary": "x", "probe": {}})
        assert r["ok"] is False and r["reason"] == "unsupported" and r["models"] == []

    def test_not_logged_in(self, manifest, monkeypatch):
        monkeypatch.setattr(probe_mod.shutil, "which", lambda x: "/usr/bin/qoder")
        monkeypatch.setattr(probe_mod.subprocess, "run",
                            lambda *a, **k: _FakeCompleted("Not logged in. Run `qodercli login`."))
        r = probe_mod.list_models(manifest)
        assert r["ok"] is False and r["reason"] == "not_logged_in"

    def test_parses_models_and_filters_header(self, manifest, monkeypatch):
        monkeypatch.setattr(probe_mod.shutil, "which", lambda x: "/usr/bin/qoder")
        out = "MODEL\tCONTEXT\n--------\nAuto\nQwen3.8-Max\nQwen3.8-Flash  轻量\n"
        monkeypatch.setattr(probe_mod.subprocess, "run", lambda *a, **k: _FakeCompleted(out))
        r = probe_mod.list_models(manifest)
        assert r["ok"] is True
        assert r["models"] == ["Auto", "Qwen3.8-Max", "Qwen3.8-Flash"]


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

    def test_export_includes_notes_and_final_summary(self, monkeypatch, tmp_path):
        """随记（user_notes）必须入工作区；纪要取定稿口径（user_summary 优先）。"""
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        task = {
            "dialogue": [{"speaker_name": "张三", "sentences": [{"text": "预算口径待定", "begin_time": 0}]}],
            "summary": "AI 初稿纪要",
            "user_summary": "用户手改后的纪要：以 PMS 可用额度为准",
            "user_notes": "共识：星瀚标品预算模块作为差旅预算主控平台",
            "todos": [],
        }
        meta = ce.export_context(engine_id="qoder-cli", task=task, task_id="t-notes",
                                 user_message="按随记更新决策")
        notes_md = (tmp_path / "agent-workspace" / "qoder-cli" / "t-notes"
                    / "context" / "notes.md")
        assert notes_md.is_file()
        text = notes_md.read_text(encoding="utf-8")
        assert "星瀚标品预算模块" in text and "用户手写原文" in text
        assert "context/notes.md" in meta["brief"]
        # 纪要基线等于用户看到的定稿，而非 AI 初稿
        summary_md = (tmp_path / "agent-workspace" / "qoder-cli" / "t-notes"
                      / "context" / "summary.md").read_text(encoding="utf-8")
        assert "以 PMS 可用额度为准" in summary_md and "AI 初稿纪要" not in summary_md

    def test_export_skips_notes_when_absent(self, monkeypatch, tmp_path):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        meta = ce.export_context(engine_id="qoder-cli", task={"dialogue": [], "summary": ""},
                                 task_id="t-nonotes", user_message="你好")
        assert "context/notes.md" not in meta["brief"]
        assert not (tmp_path / "agent-workspace" / "qoder-cli" / "t-nonotes"
                    / "context" / "notes.md").exists()

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


class TestPermissionSection:
    """模式即权限 §5.2：AGENTS.md 按落档注入"本轮权限段"，置于角色段之后（后声明者胜）。"""

    def _agents_md(self, monkeypatch, tmp_path, **kw):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        ce.export_context(engine_id="qoder-cli", task=None, task_id="perm-1",
                          user_message="重新生成板", **kw)
        return (tmp_path / "agent-workspace" / "qoder-cli" / "perm-1" / "AGENTS.md").read_text(encoding="utf-8")

    def test_write_tier_grants_writeback_duty(self, monkeypatch, tmp_path):
        md = self._agents_md(monkeypatch, tmp_path, auth_tier="workspace_write",
                             role_prompt="你**没有执行权**：不能修改、删除、写入任何数据")
        assert "本轮权限段" in md and "协助写回权" in md
        assert "仅在对话里描述计划" in md
        # 纪要改写必须走 propose_summary（提案式），不得直接覆盖
        assert "propose_summary" in md
        # 注入段必须在角色段之后（覆写存量禁令的语义前提）
        assert md.index("没有执行权") < md.index("本轮权限段")

    def test_readonly_tier_keeps_prohibition(self, monkeypatch, tmp_path):
        md = self._agents_md(monkeypatch, tmp_path, auth_tier="readonly")
        assert "当前为只读档" in md and "已重新生成" in md
        assert "协助写回权" not in md

    def test_default_none_falls_back_readonly_section(self, monkeypatch, tmp_path):
        """未传档（历史调用方/存量测试）→ 降级只读段，绝不默认许诺写权。"""
        md = self._agents_md(monkeypatch, tmp_path)
        assert "当前为只读档" in md


# ============================================================
# 模式即权限 §5.1：授权档优先级链（纯函数）
# ============================================================

class TestAuthTierResolution:
    def _cfg(self, tier="readonly", explicit=False):
        return {"auth_tier": tier, "auth_tier_explicit": explicit}

    def test_request_tier_wins(self):
        import app.routers.chat as chat
        assert chat._resolve_agent_auth_tier("readonly", self._cfg("workspace_write", True)) == "readonly"

    def test_explicit_downgrade_beats_mode_default(self):
        import app.routers.chat as chat
        assert chat._resolve_agent_auth_tier(None, self._cfg("readonly", True)) == "readonly"

    def test_mode_default_when_unconfigured(self):
        """存量默认 readonly（未显式声明）不得截胡：agent 轮默认抬到 workspace_write。"""
        import app.routers.chat as chat
        assert chat._resolve_agent_auth_tier(None, self._cfg("readonly", False)) == "workspace_write"

    def test_invalid_request_tier_falls_through(self):
        import app.routers.chat as chat
        assert chat._resolve_agent_auth_tier("god_mode", self._cfg()) == "workspace_write"


# ============================================================
# 完成护栏 §5.4：runner 写工具成功回调 → done.metadata.rewritten 事实源
# ============================================================

class TestOnWriteSuccess:
    def test_write_tool_result_triggers_callback(self):
        """直接验证配对逻辑的单元切片：工具名集来自 catalog，mcp__ 前缀剥除后命中。"""
        from core.agent_tools.catalog import TOOL_CATALOG
        write_names = {t["name"] for t in TOOL_CATALOG if t.get("kind") == "write"}
        assert {"update_summary", "inject_items", "revise_insight_board",
                "revise_insight_board_section"} <= write_names
        assert "revise_insight_board" == "mcp__oms-tools__revise_insight_board".rsplit("__", 1)[-1]
        assert "get_hotwords" not in write_names

    def test_propose_summary_excluded_from_rewritten_trigger(self):
        """提案工具（propose_summary / propose_notes）不落盘，runner 按 persists 剔除，
        否则提案轮被误标 rewritten=true（完成护栏谎报）。"""
        from core.agent_tools.catalog import TOOL_CATALOG
        writes = {t["name"] for t in TOOL_CATALOG if t.get("kind") == "write"}
        # 与 runner.write_names 同一派生规约（不再硬写工具名）
        trigger = {t["name"] for t in TOOL_CATALOG
                   if t.get("kind") == "write" and t.get("persists", True)}
        assert {"propose_summary", "propose_notes"} <= writes
        assert not {"propose_summary", "propose_notes"} & trigger
        assert {"update_summary", "inject_items", "revise_insight_board",
                "update_decision_node", "delete_decision_node"} <= trigger


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
# 多 CLI 适配：引擎枚举与 engine_id 动态白名单（打桩，不触真机）
# ============================================================

class TestEngineRegistry:
    def _base_cfg(self, engine_id="qoder-cli"):
        return {"enabled": False, "engine_id": engine_id, "model": None,
                "auth_tier": "readonly", "session_persistence": True,
                "retention_days": 7, "cli_path_override": None}

    def test_chat_engine_endpoint_lists_engines(self, monkeypatch):
        import shutil as _shutil

        import app.routers.settings as st
        monkeypatch.setattr(st, "get_chat_engine_config", self._base_cfg)
        monkeypatch.setattr(_shutil, "which", lambda x: None)  # 全部未安装：探针落 path 失败段，不触 subprocess
        resp = st.get_chat_engine_status()
        ids = {e["engine_id"] for e in resp["engines"]}
        assert {"qoder-cli", "qoder-cli-cn", "claude-code",
                "codebuddy", "trae-cli", "kimi-code", "codex"} <= ids
        cc = next(e for e in resp["engines"] if e["engine_id"] == "claude-code")
        assert cc["display_name"] == "Claude Code" and cc["installed"] is False
        assert cc["name_key"] == "cliengine_engine_claude_code"
        assert resp["probe"]["available"] is False and resp["probe"]["failed_stage"] == "path"

    def test_save_rejects_unknown_engine_id(self, monkeypatch):
        import app.routers.settings as st
        saved: dict = {}
        monkeypatch.setattr(st, "load_settings",
                            lambda: {"chat_engine": self._base_cfg("qoder-cli")})
        monkeypatch.setattr(st, "save_settings_to_disk", lambda m: saved.update(m))
        st.save_settings({"chat_engine": {"enabled": True, "engine_id": "evil-engine"}})
        # 非法 id 被丢弃，保留既有合法值（绝不写入未注册引擎）
        assert saved["chat_engine"]["engine_id"] == "qoder-cli"

    def test_save_accepts_registered_engine_id(self, monkeypatch):
        import app.routers.settings as st
        saved: dict = {}
        monkeypatch.setattr(st, "load_settings", lambda: {"chat_engine": self._base_cfg("qoder-cli")})
        monkeypatch.setattr(st, "save_settings_to_disk", lambda m: saved.update(m))
        st.save_settings({"chat_engine": {"enabled": True, "engine_id": "claude-code"}})
        assert saved["chat_engine"]["engine_id"] == "claude-code"


# ============================================================
# 意图自动分流器 v1 —— 用例已随「AI 算力入口治理」退役删除
# （auto 规则分流下线，会话模式收敛为问答/智能体两态；
#  core/cli_engine/intent.py 模块保留，供后续策略复用）
# ============================================================


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
