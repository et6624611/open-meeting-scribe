"""
tests/test_agent_tools.py — Phase 2 MCP Bridge：反向工具面与令牌链路测试

覆盖 / Covers:
  - core.agent_tools.tokens：签发/校验/撤销/过期/写权限推导
  - app/routers/agent_tools /api/agent-tools/invoke：读工具分发、写工具（update_summary /
    inject_items）、只读档拒绝写、非法令牌 401、未知工具 404
  - mcp-bridge/server.py：JSON-RPC initialize/tools/list/tools/call（打桩 HTTP）
  - core.cli_engine.mcp_bridge：临时 config 生成（0600、含令牌）、teardown 撤令牌

全部离线，不触真机 CLI、不发网络（桥内 urlopen 被打桩）。
运行 / Run: pytest tests/test_agent_tools.py -v
"""

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.settings_store as settings_store
from app.server import app
from core.agent_tools import tokens as tk
from core.agent_tools.catalog import TOOLS_BY_NAME, mcp_tool_specs
from core.cli_engine import mcp_bridge as mb


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "iso-settings.json")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# 载入独立脚本 mcp-bridge/server.py 为模块（非包，需按路径加载）
def _load_bridge():
    spec = importlib.util.spec_from_file_location(
        "oms_mcp_bridge", Path(__file__).resolve().parents[1] / "mcp-bridge" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================
# tokens
# ============================================================

class TestTokens:
    def test_issue_verify_revoke(self):
        ctx = tk.issue_token(task_id="t1", project_id=None, auth_tier="workspace_write")
        assert ctx.writable is True
        got = tk.verify_token(ctx.token)
        assert got and got.task_id == "t1"
        tk.revoke_token(ctx.token)
        assert tk.verify_token(ctx.token) is None

    def test_readonly_not_writable(self):
        ctx = tk.issue_token(task_id="t1", project_id=None, auth_tier="readonly")
        assert ctx.writable is False

    def test_expiry(self):
        ctx = tk.issue_token(task_id="t1", project_id=None, auth_tier="full_task", ttl=-1)
        assert tk.verify_token(ctx.token) is None

    def test_unknown_token(self):
        assert tk.verify_token("nope") is None
        assert tk.verify_token("") is None


# ============================================================
# invoke 端点
# ============================================================

class TestInvokeEndpoint:
    def _issue(self, tier, task_id=None, project_id=None):
        return tk.issue_token(task_id=task_id, project_id=project_id, auth_tier=tier)

    def test_invalid_token_401(self, client):
        r = client.post("/api/agent-tools/invoke",
                        json={"name": "get_hotwords", "arguments": {}},
                        headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401

    def test_read_tool_dispatch(self, client, monkeypatch):
        import core.agent_tools.impl as al
        monkeypatch.setattr(al, "execute_tool",
                            lambda name, args, task_id=None, project_id=None: json.dumps({"ok": name}))
        ctx = self._issue("readonly", task_id="t1")
        r = client.post("/api/agent-tools/invoke",
                        json={"name": "get_meeting_info", "arguments": {}},
                        headers={"Authorization": f"Bearer {ctx.token}"})
        assert r.status_code == 200
        assert r.json()["tool"] == "get_meeting_info"

    def test_write_denied_in_readonly(self, client):
        ctx = self._issue("readonly", task_id="t1")
        r = client.post("/api/agent-tools/invoke",
                        json={"name": "update_summary", "arguments": {"summary": "x"}},
                        headers={"Authorization": f"Bearer {ctx.token}"})
        assert r.status_code == 403

    def test_unknown_tool_404(self, client):
        ctx = self._issue("full_task", task_id="t1")
        r = client.post("/api/agent-tools/invoke",
                        json={"name": "not_a_tool", "arguments": {}},
                        headers={"Authorization": f"Bearer {ctx.token}"})
        assert r.status_code == 404

    def test_write_tool_via_notes_reuse(self, client, monkeypatch):
        # 注入一个内存任务，走真实 inject_content 落库路径（TestClient 与服务同进程）
        # 打桩 save_task_to_disk 避免向 data/tasks/ 写残留文件
        import app.routers.notes as notes_mod
        from app.store import tasks
        monkeypatch.setattr(notes_mod, "save_task_to_disk", lambda tid: None)
        tid = "tooltest-0001"
        tasks[tid] = {"task_id": tid, "status": "completed", "todos": [], "title": "T"}
        try:
            ctx = self._issue("full_task", task_id=tid)
            r = client.post("/api/agent-tools/invoke",
                            json={"name": "inject_items",
                                  "arguments": {"items": [{"type": "todo", "content": "出方案"}]}},
                            headers={"Authorization": f"Bearer {ctx.token}"})
            assert r.status_code == 200
            assert r.json()["result"]["injected"] == 1
            # 写操作确实落到共享 tasks（复用受控入口，非另开写路径）
            assert any(t["text"] == "出方案" for t in tasks[tid]["todos"])
        finally:
            tasks.pop(tid, None)

    # ── 纪要提案式改写（propose_summary）：名义 write、实际不落盘 ──
    def test_propose_summary_is_registered_write_tool(self):
        t = TOOLS_BY_NAME.get("propose_summary")
        assert t and t["kind"] == "write" and t["needs_task"] is True
        assert any(s["name"] == "propose_summary" for s in mcp_tool_specs())

    def test_propose_summary_does_not_persist(self, client):
        # 注入一个带 user_summary 的任务，invoke propose_summary 后应返回 ok/proposed，但 user_summary 不变
        from app.store import tasks
        tid = "propstest-0001"
        tasks[tid] = {"task_id": tid, "status": "completed", "summary": "旧纪要", "user_summary": "旧纪要", "todos": []}
        try:
            ctx = self._issue("workspace_write", task_id=tid)
            r = client.post("/api/agent-tools/invoke",
                            json={"name": "propose_summary", "arguments": {"summary": "新纪要提案"}},
                            headers={"Authorization": f"Bearer {ctx.token}"})
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is True and body["result"]["proposed"] is True
            # 关键：后端不写 task，user_summary 仍为旧值（落盘由前端接受时的 PUT /summary 完成）
            assert tasks[tid]["user_summary"] == "旧纪要"
        finally:
            tasks.pop(tid, None)

    def test_propose_summary_denied_in_readonly(self, client):
        ctx = self._issue("readonly", task_id="t1")
        r = client.post("/api/agent-tools/invoke",
                        json={"name": "propose_summary", "arguments": {"summary": "x"}},
                        headers={"Authorization": f"Bearer {ctx.token}"})
        assert r.status_code == 403

    def test_allowlist_includes_propose_summary_when_writable(self):
        # _tool_allowlist 返回 mcp 全名（mcp__oms-tools__<tool>），故按拼接子串判定
        assert "propose_summary" in " ".join(mb._tool_allowlist("workspace_write"))
        assert "propose_summary" not in " ".join(mb._tool_allowlist("readonly"))

    # ── 随记提案式改写（propose_notes）：用户原创区，名义 write、实际不落盘 ──
    def test_propose_notes_is_registered_write_tool(self):
        t = TOOLS_BY_NAME.get("propose_notes")
        assert t and t["kind"] == "write" and t["needs_task"] is True
        assert t.get("persists") is False, "不落盘的提案工具必须标 persists=False"
        assert any(s["name"] == "propose_notes" for s in mcp_tool_specs())

    def test_propose_notes_does_not_persist(self, client):
        from app.store import tasks
        tid = "propntest-0001"
        tasks[tid] = {"task_id": tid, "status": "completed", "user_notes": "旧随记", "todos": []}
        try:
            ctx = self._issue("workspace_write", task_id=tid)
            r = client.post("/api/agent-tools/invoke",
                            json={"name": "propose_notes", "arguments": {"notes": "新随记提案"}},
                            headers={"Authorization": f"Bearer {ctx.token}"})
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is True and body["result"]["proposed"] is True
            # 关键：后端不写 task，user_notes 仍为用户原文（落盘由接受时的 PUT /notes 完成）
            assert tasks[tid]["user_notes"] == "旧随记"
        finally:
            tasks.pop(tid, None)

    def test_propose_notes_denied_in_readonly(self, client):
        ctx = self._issue("readonly", task_id="t1")
        r = client.post("/api/agent-tools/invoke",
                        json={"name": "propose_notes", "arguments": {"notes": "x"}},
                        headers={"Authorization": f"Bearer {ctx.token}"})
        assert r.status_code == 403

    def test_propose_notes_in_allowlist_only_when_writable(self):
        assert "propose_notes" in " ".join(mb._tool_allowlist("workspace_write"))
        assert "propose_notes" not in " ".join(mb._tool_allowlist("readonly"))

    def test_proposal_tools_excluded_from_rewritten_trigger(self):
        """完成护栏触发集按 persists 派生：两个提案工具不得被当作"已落盘"。"""
        from core.agent_tools.catalog import TOOL_CATALOG
        trigger = {t["name"] for t in TOOL_CATALOG
                   if t.get("kind") == "write" and t.get("persists", True)}
        assert "propose_summary" not in trigger and "propose_notes" not in trigger
        assert {"update_decision_node", "delete_decision_node", "inject_items"} <= trigger

    # ── 洞察共创板工具（读写双语义） / Insight board co-create tool ──
    def test_board_read_allowed_in_readonly(self, client, monkeypatch, tmp_path):
        # 不带 html = 读基线，只读档放行（写档门控的例外）
        import core.insight_board as ib
        monkeypatch.setattr(ib, "BOARD_TASKS_DIR", tmp_path)
        ctx = self._issue("readonly", task_id="t1")
        r = client.post("/api/agent-tools/invoke",
                        json={"name": "revise_insight_board", "arguments": {}},
                        headers={"Authorization": f"Bearer {ctx.token}"})
        assert r.status_code == 200
        assert r.json()["result"]["html"] is None and r.json()["result"]["revision"] == 0

    def test_board_write_denied_in_readonly(self, client, monkeypatch, tmp_path):
        import core.insight_board as ib
        monkeypatch.setattr(ib, "BOARD_TASKS_DIR", tmp_path)
        ctx = self._issue("readonly", task_id="t1")
        r = client.post("/api/agent-tools/invoke",
                        json={"name": "revise_insight_board", "arguments": {"html": "<p>x</p>"}},
                        headers={"Authorization": f"Bearer {ctx.token}"})
        assert r.status_code == 403

    def test_board_write_then_read_consistent(self, client, monkeypatch, tmp_path):
        import core.insight_board as ib
        monkeypatch.setattr(ib, "BOARD_TASKS_DIR", tmp_path)
        ctx = self._issue("full_task", task_id="t1")
        w = client.post("/api/agent-tools/invoke",
                        json={"name": "revise_insight_board", "arguments": {"html": "<h1>板</h1>"}},
                        headers={"Authorization": f"Bearer {ctx.token}"})
        assert w.status_code == 200 and w.json()["result"]["revision"] == 1
        rd = client.post("/api/agent-tools/invoke",
                         json={"name": "revise_insight_board", "arguments": {}},
                         headers={"Authorization": f"Bearer {ctx.token}"})
        assert rd.json()["result"]["html"] == "<h1>板</h1>"


# ============================================================
# MCP bridge JSON-RPC（打桩 urlopen）
# ============================================================

class TestBridgeProtocol:
    def test_initialize_and_tools_list(self, capsys):
        br = _load_bridge()
        br.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        out = json.loads(capsys.readouterr().out.strip())
        assert out["result"]["serverInfo"]["name"] == "oms-tools"
        br.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        out = json.loads(capsys.readouterr().out.strip())
        names = {t["name"] for t in out["result"]["tools"]}
        assert "get_meeting_info" in names and "inject_items" in names
        # inputSchema 存在（MCP 要求）
        assert all("inputSchema" in t for t in out["result"]["tools"])

    def test_tools_call_ok(self, capsys, monkeypatch):
        br = _load_bridge()
        br._TOKEN = "tok"
        class _Resp:
            # 真实 urlopen 返回 bytes，桥内 .read().decode() —— 桩保持一致
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"result": {"injected": 2}}).encode("utf-8")
        monkeypatch.setattr(br.urllib.request, "urlopen",
                            lambda req, timeout=None: _Resp())
        br.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "inject_items", "arguments": {"items": []}}})
        out = json.loads(capsys.readouterr().out.strip())
        assert out["result"]["isError"] is False
        assert json.loads(out["result"]["content"][0]["text"])["injected"] == 2

    def test_tools_call_missing_token(self, capsys):
        br = _load_bridge()
        br._TOKEN = ""
        br.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                   "params": {"name": "get_hotwords", "arguments": {}}})
        out = json.loads(capsys.readouterr().out.strip())
        assert out["result"]["isError"] is True

    def test_unknown_method_error(self, capsys):
        br = _load_bridge()
        br.handle({"jsonrpc": "2.0", "id": 5, "method": "bogus/method", "params": {}})
        out = json.loads(capsys.readouterr().out.strip())
        assert out["error"]["code"] == -32601


# ============================================================
# mcp_bridge 配置生成
# ============================================================

class TestBridgeConfig:
    def test_build_and_teardown(self):
        path, ctx, allow = mb.build_bridge_config(
            task_id="t1", project_id=None, auth_tier="full_task", base_url="http://127.0.0.1:8000")
        try:
            cfg = json.loads(Path(path).read_text(encoding="utf-8"))
            server = cfg["mcpServers"]["oms-tools"]
            assert server["env"]["OMS_MCP_TOKEN"] == ctx.token
            assert server["args"][0].endswith("mcp-bridge/server.py")
            # 令牌在签发进程内可校验
            assert tk.verify_token(ctx.token) is not None
            # full_task 允许写工具 → 7 个工具全放行
            assert len(allow) == len(TOOLS_BY_NAME)
            assert any(a.startswith("mcp__oms-tools__") for a in allow)
        finally:
            mb.teardown_bridge(path, ctx.token)
        assert tk.verify_token(ctx.token) is None
        assert not Path(path).exists()

    def test_readonly_allowlist_excludes_write(self):
        path, ctx, allow = mb.build_bridge_config(
            task_id=None, project_id=None, auth_tier="readonly", base_url="http://x")
        try:
            joined = " ".join(allow)
            assert "update_summary" not in joined and "inject_items" not in joined
            assert "get_meeting_info" in joined
        finally:
            mb.teardown_bridge(path, ctx.token)

    def test_manifest_has_mcp(self):
        assert mb.manifest_has_mcp("qoder-cli") is True
        assert mb.manifest_has_mcp("no-such-engine") is False

    def test_mcp_tool_specs_shape(self):
        specs = mcp_tool_specs()
        assert all({"name", "description", "inputSchema"} <= set(s) for s in specs)


# ============================================================
# 会中实时转写回退（2026-09-29 会中问答复盘：dialogue 落盘前工具面/工作区不得谎报"无转写"）
# ============================================================

class TestInProgressRealtimeFallback:
    _SENTENCES = [
        {"text": "我们讨论一下标准方案的选型", "speaker_id": 0, "speaker_name": "", "begin_time": 5000, "end_time": 8000},
        {"text": "标准方案采用星三架构", "speaker_id": 1, "speaker_name": "王工", "begin_time": 65000, "end_time": 69000},
    ]

    def test_transcript_tool_falls_back_to_realtime_buffer(self, monkeypatch):
        import app.realtime_store as rs
        from app.store import tasks
        from core.agent_tools import impl
        task_id = "rt-fallback-1"
        tasks[task_id] = {"task_id": task_id, "status": "recording", "dialogue": None}
        monkeypatch.setitem(rs.realtime_full_transcripts, task_id, list(self._SENTENCES))
        try:
            out = json.loads(impl._tool_get_meeting_transcript(task_id, 20))
            assert out.get("in_progress") is True
            assert len(out["transcript_lines"]) == 2
            assert "[01:05] 王工" in out["transcript_lines"][1]
            # 会中 get_meeting_info 也应提示实时句数而非沉默
            info = json.loads(impl._tool_get_meeting_info(task_id))
            assert info.get("realtime_sentence_count") == 2
        finally:
            tasks.pop(task_id, None)
            rs.realtime_full_transcripts.pop(task_id, None)

    def test_transcript_tool_no_data_still_reports_empty(self, monkeypatch):
        import app.realtime_store as rs
        from app.store import tasks
        from core.agent_tools import impl
        task_id = "rt-fallback-empty"
        tasks[task_id] = {"task_id": task_id, "status": "recording", "dialogue": None}
        monkeypatch.setattr(rs, "realtime_full_transcripts", {})
        monkeypatch.setattr(rs, "realtime_transcript_buffers", {})
        try:
            out = json.loads(impl._tool_get_meeting_transcript(task_id, 20))
            assert "暂无转写记录" in out.get("info", "")
        finally:
            tasks.pop(task_id, None)

    def test_export_context_writes_transcript_from_realtime(self, monkeypatch, tmp_path):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        task = {"task_id": "rt-2", "status": "recording", "dialogue": None,
                "speaker_mapping": {"0": "李工"}}
        meta = ce.export_context(engine_id="qoder-cli", task=task, task_id="rt-2",
                                 user_message="标准方案是什么",
                                 realtime_entries=list(self._SENTENCES))
        assert "context/transcript.md" in meta["brief"]
        text = (Path(meta["workspace"]) / "context" / "transcript.md").read_text(encoding="utf-8")
        assert "录音进行中" in text
        assert "李工：我们讨论一下标准方案的选型" in text  # speaker_mapping 解析 id→名
        assert "王工：标准方案采用星三架构" in text  # 条目自带实名优先


# ============================================================
# 随记读工具（2026-09-30 复盘：用户把共识结论写进随记，AI 读不到导致无法同步决策面板）
# ============================================================

class TestMeetingNotesTool:
    def test_get_meeting_notes_registered_as_read(self):
        t = TOOLS_BY_NAME.get("get_meeting_notes")
        assert t and t["kind"] == "read" and t["needs_task"] is True
        assert any(s["name"] == "get_meeting_notes" for s in mcp_tool_specs())

    def test_read_tool_returns_user_notes(self):
        from app.store import tasks
        from core.agent_tools import impl
        tid = "notestool-1"
        tasks[tid] = {"task_id": tid, "status": "completed", "user_notes": "共识：预算主控放在星瀚"}
        try:
            out = json.loads(impl.execute_tool("get_meeting_notes", {}, task_id=tid))
            assert "预算主控放在星瀚" in out["notes"]
            assert out["characters"] == len("共识：预算主控放在星瀚")
            assert "truncated" not in out
        finally:
            tasks.pop(tid, None)

    def test_empty_notes_reports_absent_not_error(self):
        from app.store import tasks
        from core.agent_tools import impl
        tid = "notestool-2"
        tasks[tid] = {"task_id": tid, "status": "completed"}
        try:
            out = json.loads(impl._tool_get_meeting_notes(tid))
            assert "暂无随记" in out["info"] and out["characters"] == 0
        finally:
            tasks.pop(tid, None)

    def test_meeting_info_admits_notes_exist(self):
        """get_meeting_info 必须报出随记存在性与预览，否则模型不会知道去读。"""
        from app.store import tasks
        from core.agent_tools import impl
        tid = "notestool-3"
        tasks[tid] = {"task_id": tid, "status": "completed", "summary": "AI 初稿",
                      "user_summary": "用户定稿纪要", "user_notes": "最终结论：手工补入抵消灭失"}
        try:
            info = json.loads(impl._tool_get_meeting_info(tid))
            assert info["has_notes"] is True
            assert "最终结论" in info["notes_preview"]
            assert "get_meeting_notes" in info["notes_note"]
            # 纪要预览同取定稿口径，与前端纪要 Tab 一致
            assert info["summary_preview"] == "用户定稿纪要"
        finally:
            tasks.pop(tid, None)

    def test_notes_tool_allowed_in_readonly_via_invoke(self, client):
        from app.store import tasks
        tid = "notestool-4"
        tasks[tid] = {"task_id": tid, "status": "completed", "user_notes": "只读档也要能读随记"}
        try:
            ctx = tk.issue_token(task_id=tid, project_id=None, auth_tier="readonly")
            r = client.post("/api/agent-tools/invoke",
                            json={"name": "get_meeting_notes", "arguments": {}},
                            headers={"Authorization": f"Bearer {ctx.token}"})
            assert r.status_code == 200
            assert "只读档也要能读随记" in json.loads(r.json()["result"])["notes"]
        finally:
            tasks.pop(tid, None)

    def test_todos_tool_exposes_node_ids(self):
        """决策节点稳定 id 必须回给工具面（改写/删除按 id 寻址的前置项）。"""
        from app.store import tasks
        from core.agent_tools import impl
        tid = "notestool-5"
        tasks[tid] = {"task_id": tid, "status": "completed",
                      "todos": [{"id": "node-1", "text": "预算版本双轨", "title": "版本双轨",
                                  "status": "to_decide", "done": False, "assignee": "张三"}]}
        try:
            out = json.loads(impl._tool_get_meeting_todos(tid))
            item = out["todos"][0]
            assert item["id"] == "node-1" and item["status"] == "to_decide"
            assert item["title"] == "版本双轨"
        finally:
            tasks.pop(tid, None)


# ============================================================
# 删除会话联动清理工作区（Phase 4 D5）
# ============================================================

class TestWorkspaceCleanup:
    def test_export_honors_workspace_key(self, monkeypatch, tmp_path):
        """workspace_key 优先于 task_id 作为工作区目录名（会话对齐）。"""
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        meta = ce.export_context(engine_id="qoder-cli", task=None, task_id="task-9",
                                 user_message="hi", workspace_key="sess-abc")
        assert (tmp_path / "agent-workspace" / "qoder-cli" / "sess-abc" / "AGENTS.md").is_file()
        assert "sess-abc" in meta["workspace"]

    def test_cleanup_endpoint_deletes_workspace(self, client, monkeypatch, tmp_path):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "WORKSPACE_ROOT", tmp_path / "agent-workspace")
        sess_dir = tmp_path / "agent-workspace" / "qoder-cli" / "sess-del"
        sess_dir.mkdir(parents=True)
        r = client.post("/api/agent-tools/cleanup", json={"chat_session_id": "sess-del"})
        assert r.status_code == 200 and r.json()["cleaned"] == "sess-del"
        assert not sess_dir.exists()

    def test_cleanup_missing_key_400(self, client):
        r = client.post("/api/agent-tools/cleanup", json={})
        assert r.status_code == 400

    def test_cleanup_blocks_traversal(self, client, tmp_path):
        # 穿越键会被 resolve 后判定不在 WORKSPACE_ROOT 下 → 不删除、不报错（幂等 no-op）
        r = client.post("/api/agent-tools/cleanup", json={"chat_session_id": "../../etc"})
        assert r.status_code == 200  # 幂等，不因越界而崩
