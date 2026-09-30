"""
tests/test_rewrite_snapshots.py — AI 写回快照与撤销（PROPOSAL-AGENT-REWRITE-CHANNEL §5.3/§5.4）

覆盖 / Covers:
  - core.rewrite_snapshots：追写/列表/每 target 保留上限/过期清理/恢复语义（含撤销创建）
  - 写工具 update_decision_node / delete_decision_node：按节点 id 寻址、只读档拒绝、
    未知节点 404、空补丁 400、写回前强制快照
  - inject_items 新建节点也进快照（撤销 = 删掉新建）
  - 按轮撤销（turn_id 逆序回滚）与 /api/tasks/{id}/rewrites 端点
  - get_meeting_todos 下发节点 id 与状态字典（否则模型只能猜 status）

全部离线：SNAPSHOT_DIR 与 TASKS_DIR 已由 conftest 会话级隔离。
运行 / Run: pytest tests/test_rewrite_snapshots.py -v
"""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.settings_store as settings_store
import core.rewrite_snapshots as rsv
from app.server import app
from core.agent_tools import tokens as tk
from core.agent_tools.catalog import TOOLS_BY_NAME


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "iso-settings.json")


@pytest.fixture(autouse=True)
def _isolate_snapshot_dir(tmp_path, monkeypatch):
    """每用例一个空快照库（conftest 的会话级隔离会让同 id 任务的快照跨用例泄漏）。"""
    monkeypatch.setattr(rsv, "SNAPSHOT_DIR", tmp_path / "snaps")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def flow_task(monkeypatch):
    """注入一场含两条待决策节点的会议（走真实 tasks 内存对象）。"""
    from app.store import tasks
    tid = "rewtest-flow"
    tasks[tid] = {
        "task_id": tid, "status": "completed", "title": "差旅预算机制讨论",
        "summary": "AI 初稿纪要",
        "user_notes": "共识：差旅预算统一纳入星瀚标品预算模块",
        "todos": [
            {"id": "node-a", "title": "版本双轨", "text": "预算版本管理规则明确定义",
             "status": "to_decide", "done": False, "assignee": "张三", "source": "auto"},
            {"id": "node-b", "title": "接口同步", "text": "商旅平台提供结构化接口同步执行数据",
             "status": "to_decide", "done": False, "assignee": "", "source": "auto"},
        ],
    }
    yield tid
    tasks.pop(tid, None)


def _invoke(client, name, arguments, *, tier="workspace_write", task_id, turn_id=""):
    ctx = tk.issue_token(task_id=task_id, project_id=None, auth_tier=tier, turn_id=turn_id)
    return client.post("/api/agent-tools/invoke",
                       json={"name": name, "arguments": arguments},
                       headers={"Authorization": f"Bearer {ctx.token}"})


# ============================================================
# 快照存储本体
# ============================================================

class TestSnapshotStore:
    def test_append_list_latest(self):
        sid = rsv.snapshot_write("t-store", rsv.TARGET_SUMMARY, "旧值", tool="update_summary")
        assert sid
        recs = rsv.list_snapshots("t-store")
        assert len(recs) == 1 and recs[0]["old"] == "旧值" and recs[0]["tool"] == "update_summary"
        assert rsv.latest_snapshot("t-store", rsv.TARGET_SUMMARY)["id"] == sid

    def test_per_target_retention_cap(self):
        for i in range(rsv.MAX_VERSIONS_PER_TARGET + 5):
            rsv.snapshot_write("t-cap", rsv.decision_node_target("n1"), {"text": f"v{i}"})
        recs = rsv.list_snapshots("t-cap")
        assert len(recs) == rsv.MAX_VERSIONS_PER_TARGET
        # 保留的是最近 N 版，最旧的被裁掉
        assert recs[0]["old"]["text"] == "v5"
        assert recs[-1]["old"]["text"] == f"v{rsv.MAX_VERSIONS_PER_TARGET + 4}"

    def test_other_targets_not_trimmed(self):
        for i in range(rsv.MAX_VERSIONS_PER_TARGET + 3):
            rsv.snapshot_write("t-mix", rsv.decision_node_target("n1"), {"i": i})
        rsv.snapshot_write("t-mix", rsv.TARGET_NOTES, "随记旧值")
        assert len(rsv.list_snapshots("t-mix", target=rsv.TARGET_NOTES)) == 1

    def test_sweep_expired_snapshots(self):
        rsv.snapshot_write("t-old", rsv.TARGET_SUMMARY, "x")
        f = rsv.snapshot_path("t-old")
        old = (datetime.now() - timedelta(days=30)).timestamp()
        import os
        os.utime(f, (old, old))
        assert rsv.sweep_expired_snapshots(7) >= 1
        assert not f.exists()

    def test_sweep_zero_days_is_noop(self):
        rsv.snapshot_write("t-keep", rsv.TARGET_SUMMARY, "x")
        assert rsv.sweep_expired_snapshots(0) == 0
        assert rsv.snapshot_path("t-keep").exists()

    def test_describe_change_readable(self):
        rec = {"target": rsv.decision_node_target("abc12345-1"), "old": {"title": "版本双轨", "status": "to_decide"}}
        assert "版本双轨" in rsv.describe_change(rec) and "to_decide" in rsv.describe_change(rec)


# ============================================================
# 决策节点改写 / 删除（按 id 寻址 + 强制快照）
# ============================================================

class TestDecisionNodeRewrite:
    def test_tools_registered_as_write(self):
        for n in ("update_decision_node", "delete_decision_node"):
            t = TOOLS_BY_NAME[n]
            assert t["kind"] == "write" and t["needs_task"] is True

    def test_readonly_denied(self, client, flow_task):
        r = _invoke(client, "update_decision_node",
                    {"node_id": "node-a", "status": "done"}, tier="readonly", task_id=flow_task)
        assert r.status_code == 403

    def test_update_by_id_writes_and_snapshots(self, client, flow_task):
        r = _invoke(client, "update_decision_node",
                    {"node_id": "node-a", "status": "done", "title": "版本双轨已确认"},
                    task_id=flow_task, turn_id="turn-1")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"]["updated"] is True and body["result"]["restorable"] is True
        from app.store import tasks
        node = next(t for t in tasks[flow_task]["todos"] if t["id"] == "node-a")
        assert node["status"] == "done" and node["done"] is True and node["title"] == "版本双轨已确认"
        # 快照存的是改写前的整节点
        snap = rsv.latest_snapshot(flow_task, rsv.decision_node_target("node-a"))
        assert snap["old"]["status"] == "to_decide" and snap["turn_id"] == "turn-1"

    def test_unknown_node_404(self, client, flow_task):
        r = _invoke(client, "update_decision_node", {"node_id": "nope", "status": "done"},
                    task_id=flow_task)
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "node_not_found"

    def test_empty_patch_400(self, client, flow_task):
        r = _invoke(client, "update_decision_node", {"node_id": "node-a"}, task_id=flow_task)
        assert r.status_code == 400

    def test_invalid_status_422_not_snapshotted(self, client, flow_task):
        """非法状态由状态字典挡下（422），且不得留下"看起来能撤销"的空快照。"""
        r = _invoke(client, "update_decision_node", {"node_id": "node-a", "status": "已拍板"},
                    task_id=flow_task)
        assert r.status_code == 422
        assert rsv.list_snapshots(flow_task) == []

    def test_delete_removes_and_restore_reinserts(self, client, flow_task):
        r = _invoke(client, "delete_decision_node", {"node_id": "node-b"}, task_id=flow_task)
        assert r.status_code == 200 and r.json()["result"]["deleted"] is True
        from app.store import tasks
        assert all(t["id"] != "node-b" for t in tasks[flow_task]["todos"])
        # 删除的 auto 节点应落防复活墓碑（复用 notes.delete_todo 口径）
        assert tasks[flow_task].get("decision_deletions")
        snap = rsv.latest_snapshot(flow_task, rsv.decision_node_target("node-b"))
        res = rsv.restore_task(flow_task, snapshot_id=snap["id"])
        assert res["ok"] is True
        back = next(t for t in tasks[flow_task]["todos"] if t["id"] == "node-b")
        assert back["text"].startswith("商旅平台")

    def test_inject_then_restore_removes_created_node(self, client, flow_task):
        from app.store import tasks
        before = len(tasks[flow_task]["todos"])
        r = _invoke(client, "inject_items",
                    {"items": [{"type": "todo", "content": "补录：手工导入值口径"}]},
                    task_id=flow_task, turn_id="turn-inj")
        assert r.status_code == 200 and r.json()["result"]["injected"] == 1
        assert len(tasks[flow_task]["todos"]) == before + 1
        res = rsv.restore_task(flow_task, turn_id="turn-inj")
        assert res["ok"] is True and res["restored"] == 1
        assert len(tasks[flow_task]["todos"]) == before, "撤销创建应删掉新建节点"

    def test_overlong_field_rejected_without_snapshot(self, client, flow_task):
        """被校验拦下的写不应留下快照，否则撤销面板会出现空条目。"""
        r = _invoke(client, "update_decision_node",
                    {"node_id": "node-a", "title": "超" * 300}, task_id=flow_task)
        assert r.status_code == 400
        assert rsv.list_snapshots(flow_task) == []


# ============================================================
# 按轮撤销与恢复端点
# ============================================================

class TestTurnRestore:
    def test_restore_turn_reverses_all_writes(self, client, flow_task):
        _invoke(client, "update_decision_node", {"node_id": "node-a", "status": "done"},
                task_id=flow_task, turn_id="turn-x")
        _invoke(client, "update_decision_node", {"node_id": "node-b", "status": "in_progress"},
                task_id=flow_task, turn_id="turn-x")
        from app.store import tasks
        assert [t["status"] for t in tasks[flow_task]["todos"]] == ["done", "in_progress"]
        res = rsv.restore_task(flow_task, turn_id="turn-x")
        assert res["ok"] is True and res["restored"] == 2
        assert [t["status"] for t in tasks[flow_task]["todos"]] == ["to_decide", "to_decide"]

    def test_restore_turn_without_snapshots_404_path(self, flow_task):
        res = rsv.restore_task(flow_task, turn_id="never-happened")
        assert res["ok"] is False and res["error"] == "turn_not_found"

    def test_restore_requires_snapshot_id_or_turn_id(self, flow_task):
        assert rsv.restore_task(flow_task)["error"] == "missing_target"

    def test_restore_missing_task(self):
        assert rsv.restore_task("no-such-task", turn_id="t")["error"] == "task_not_found"

    def test_endpoints_list_and_restore(self, client, flow_task):
        r = _invoke(client, "update_decision_node", {"node_id": "node-a", "status": "done"},
                    task_id=flow_task, turn_id="turn-e2e")
        assert r.status_code == 200 and r.json()["result"]["restorable"] is True
        snap_id = rsv.latest_snapshot(flow_task, rsv.decision_node_target("node-a"))["id"]

        lst = client.get(f"/api/tasks/{flow_task}/rewrites", params={"turn_id": "turn-e2e"})
        assert lst.status_code == 200
        snaps = lst.json()["snapshots"]
        assert len(snaps) == 1 and snaps[0]["id"] == snap_id
        assert "old" not in snaps[0], "列表不回旧值全文"
        assert "版本双轨" in snaps[0]["description"]

        back = client.post(f"/api/tasks/{flow_task}/rewrites/restore",
                           json={"turn_id": "turn-e2e"})
        assert back.status_code == 200 and back.json()["restored"] == 1
        from app.store import tasks
        assert tasks[flow_task]["todos"][0]["status"] == "to_decide"
        assert tasks[flow_task].get("last_modified_at")

    def test_restore_endpoint_400_without_args(self, client, flow_task):
        r = client.post(f"/api/tasks/{flow_task}/rewrites/restore", json={})
        assert r.status_code == 400

    def test_restore_writes_audit_entry(self, client, flow_task, caplog):
        """恢复也是内容变更，必须落 [agent-engine] 审计条目（AC5/AC6）。"""
        import logging
        _invoke(client, "update_decision_node", {"node_id": "node-a", "status": "done"},
                task_id=flow_task, turn_id="turn-audit")
        with caplog.at_level(logging.INFO, logger="audit"):
            r = client.post(f"/api/tasks/{flow_task}/rewrites/restore",
                            json={"turn_id": "turn-audit"})
        assert r.status_code == 200
        msgs = [rec.getMessage() for rec in caplog.records if rec.name == "audit"]
        assert any("restore_rewrites" in m and "turn:turn-audit" in m for m in msgs)

    def test_restore_endpoint_404_unknown_task(self, client):
        r = client.post("/api/tasks/no-such-task/rewrites/restore", json={"turn_id": "t"})
        assert r.status_code == 404

    def test_summary_update_snapshots_and_restores(self, client, flow_task):
        r = _invoke(client, "update_summary", {"summary": "AI 覆盖的新纪要"},
                    task_id=flow_task, turn_id="turn-sum")
        assert r.status_code == 200 and r.json()["result"]["restorable"] is True
        from app.store import tasks
        assert tasks[flow_task]["user_summary"] == "AI 覆盖的新纪要"
        # 此前无 user_summary → 撤销后回到"未编辑态"（回退到生成稿口径）
        res = rsv.restore_task(flow_task, turn_id="turn-sum")
        assert res["ok"] is True
        assert "user_summary" not in tasks[flow_task]


# ============================================================
# 读侧配套：节点 id 与状态字典必须下发给工具面
# ============================================================

class TestTodosToolFeedsRewrite:
    def test_todos_output_has_ids_and_status_dictionary(self, flow_task):
        from core.agent_tools.impl import _tool_get_meeting_todos
        out = json.loads(_tool_get_meeting_todos(flow_task))
        assert {t["id"] for t in out["todos"]} == {"node-a", "node-b"}
        ids = {s["id"] for s in out["available_statuses"]}
        assert {"to_decide", "done"} <= ids
        assert any(s["closing"] for s in out["available_statuses"])
        assert "status_note" in out

    def test_legacy_node_without_status_reports_derived(self, monkeypatch):
        """历史 task JSON 无 status 字段时，读侧按 done 推导（不空报）。"""
        from app.store import tasks
        from core.agent_tools.impl import _tool_get_meeting_todos
        tid = "rewtest-legacy"
        tasks[tid] = {"task_id": tid, "todos": [{"id": "n1", "text": "旧节点", "done": True}]}
        try:
            out = json.loads(_tool_get_meeting_todos(tid))
            assert out["todos"][0]["status"] == "done"
        finally:
            tasks.pop(tid, None)
