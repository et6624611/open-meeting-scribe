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
        import core.agent_loop as al
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
