"""
tests/test_decision_flow.py — DC-UNIFY-01 单一决策流回归（2026-09-27 项目方裁决）

契约事实源：docs/API_CONTRACTS.md §12（DC-UNIFY-01 修订）。
覆盖口径：
  1. 纪要「主要结论」自动解析 → 决策流节点（todos），统一落「待决策」态
  2. 重新生成合并：只覆盖 auto、保留手动/注入、墓碑防复活、文本去重
  3. 节点级 CRUD：状态字典校验、done 跟随 closing、title/owner_id 承接三要素
  4. 跨会议聚合：数据源为 todos、过滤/分组/状态元信息随行、未知状态降级
  5. 注入联动：todo 与 decision 类型同写决策流
  6. 状态字典：三态默认集、锚点仅 done、旧结构自动迁移、删除回落 todos

旧 decision 对象的回归（test_decision_center / test_dc_r2_b / test_dc_r2_be /
test_dc_r2_c）随对象下线一并移除，其仍有效的断言已并入本文件。
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.server import app
from app.store import tasks
from core.summarize import (
    decision_text_key,
    merge_flow_after_regen,
    parse_decisions_with_status,
)

SUMMARY = """# 会议纪要

## 一、会议概要
讨论了方案选型与排期。

## 二、主要结论
1. **方案选型**：项目采用方案A推进
2. [待确认] 预算需财务复核
3. 上线时间定在10月1日

## 三、待办事项
- [ ] **张三**：出排期（本周五前）
"""

SUMMARY_NEGATIVE = """## 二、主要结论
本次会议未形成明确结论

## 三、待办事项
无明确待办事项
"""


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def task_factory():
    """创建内存任务并在用例后清理 / in-memory task with cleanup."""
    created: list[str] = []

    def _make(**overrides) -> str:
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "status": "completed",
            "progress": 100,
            "title": "测试会议",
            "meeting_date": "2026-09-20",
            "created_at": "2026-09-20T10:00:00",
        }
        task.update(overrides)
        tasks[task_id] = task
        created.append(task_id)
        return task_id

    yield _make
    for tid in created:
        tasks.pop(tid, None)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """状态字典文件隔离到临时目录 / isolate the status dictionary file."""
    import core.decision_status as ds
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(ds, "DATA_DIR", data_dir)
    monkeypatch.setattr(ds, "STATUSES_FILE", data_dir / "decision_statuses.json")
    yield ds


# ============================================================
# 1. 自动解析：结论 → 决策流节点（待确认）
# ============================================================

def test_conclusions_parse_into_flow_nodes_pending_confirmation():
    nodes, degrade = parse_decisions_with_status(SUMMARY)
    assert degrade is None
    assert len(nodes) == 3
    for n in nodes:
        # 节点形状 = todos：有 text/assignee/status/how，不再有 owner_name/superseded_by
        assert {"id", "text", "assignee", "owner_id", "done", "status", "how", "source"} <= set(n)
        assert n["status"] == "to_decide" and n["source"] == "auto" and n["done"] is False
    # 「**标题**：正文」拆出 title，正文不含 [待确认] 前缀
    assert nodes[0]["title"] == "方案选型" and nodes[0]["text"] == "项目采用方案A推进"
    assert nodes[1]["title"] == "" and nodes[1]["pending_confirmation"] is True


def test_negative_conclusion_is_normal_empty_not_degradation():
    nodes, degrade = parse_decisions_with_status(SUMMARY_NEGATIVE)
    assert nodes == [] and degrade is None


def test_missing_section_reports_degradation():
    nodes, degrade = parse_decisions_with_status("# 纪要\n没有结论章节")
    assert nodes == [] and degrade == "missing_section"


# ============================================================
# 2. 重新生成合并：只覆盖 auto + 墓碑 + 去重
# ============================================================

def test_merge_keeps_manual_and_replaces_auto():
    existing = [
        {"id": "m1", "text": "手动记录", "source": "manual"},
        {"id": "a1", "text": "旧结论", "source": "auto"},
    ]
    parsed = [{"id": "a2", "text": "新结论", "source": "auto"}]
    merged = merge_flow_after_regen(existing, parsed)
    texts = [t["text"] for t in merged]
    assert texts == ["手动记录", "新结论"]


def test_merge_drops_tombstoned_auto_nodes():
    parsed = [{"id": "a1", "text": "被删过的结论", "source": "auto"}]
    tombstones = [{"text_key": decision_text_key("被删过的结论")}]
    assert merge_flow_after_regen([], parsed, tombstones) == []


def test_merge_dedupes_against_kept_nodes():
    existing = [{"id": "m1", "text": "同一句话", "source": "manual"}]
    parsed = [{"id": "a1", "text": "同一句话", "source": "auto"}]
    merged = merge_flow_after_regen(existing, parsed)
    assert [t["id"] for t in merged] == ["m1"]


# ============================================================
# 3. 节点级 CRUD
# ============================================================

def test_create_node_carries_title_and_resolves_owner_from_archive(client, task_factory, monkeypatch):
    import core.decision_flow as flow
    monkeypatch.setattr(flow, "get_speaker_name_map", lambda: {"sp-1": "李四"})
    tid = task_factory()
    resp = client.post(f"/api/tasks/{tid}/todos", json={
        "text": "采用方案A", "title": "方案选型", "owner_id": "sp-1",
    })
    assert resp.status_code == 200
    node = resp.json()["todo"]
    assert node["title"] == "方案选型"
    assert node["assignee"] == "李四" and node["owner_id"] == "sp-1"
    # 手动添加落默认开放态（待决策），而非退役的待确认态
    assert node["status"] == "to_decide" and node["source"] == "manual"


def test_status_must_exist_in_dictionary(client, task_factory, store):
    store.load_statuses()
    tid = task_factory(todos=[])
    ok = client.put(f"/api/tasks/{tid}/todos/x", json={"status": "in_progress"})
    assert ok.status_code == 404  # 节点不存在，但状态校验通过（未 422）
    bad = client.post(f"/api/tasks/{tid}/todos", json={"text": "一条决策", "status": "not-a-status"})
    assert bad.status_code == 422


def test_done_follows_closing_flag(client, task_factory, store):
    store.load_statuses()
    tid = task_factory(todos=[])
    created = client.post(f"/api/tasks/{tid}/todos", json={"text": "上线时间定在10月1日"}).json()["todo"]
    done = client.put(f"/api/tasks/{tid}/todos/{created['id']}", json={"status": "done"}).json()["todo"]
    assert done["done"] is True
    reopened = client.put(f"/api/tasks/{tid}/todos/{done['id']}", json={"status": "in_progress"}).json()["todo"]
    assert reopened["done"] is False and reopened["status"] == "in_progress"


def test_delete_auto_node_writes_tombstone(client, task_factory):
    tid = task_factory(todos=[{"id": "a1", "text": "自动结论", "source": "auto", "status": "to_decide", "done": False}])
    assert client.delete(f"/api/tasks/{tid}/todos/a1").status_code == 200
    tombstones = tasks[tid].get("decision_deletions") or []
    assert [t["text_key"] for t in tombstones] == [decision_text_key("自动结论")]


def test_get_todos_carries_status_dictionary_meta(client, task_factory, store):
    store.load_statuses()
    tid = task_factory(todos=[{"id": "t1", "text": "决策", "status": "in_progress", "done": False}])
    node = client.get(f"/api/tasks/{tid}/todos").json()["todos"][0]
    assert node["status_name"] == "进行中" and node["status_closing"] is False
    assert node["meeting_title"] == "测试会议"


# ============================================================
# 4. 跨会议聚合（决策中心数据源）
# ============================================================

def test_aggregation_reads_decision_flow(client, task_factory, store):
    store.load_statuses()
    tid = task_factory(todos=[
        {"id": "n1", "title": "方案选型", "text": "采用方案A", "status": "in_progress",
         "source": "auto", "done": False, "created_at": "2026-09-20T10:00:00"},
    ])
    rows = client.get("/api/decisions").json()["decisions"]
    row = next(r for r in rows if r["id"] == "n1")
    assert row["task_id"] == tid and row["meeting_title"] == "测试会议"
    assert row["title"] == "方案选型"          # 决策自身标题，不与会议标题混用
    assert row["status_name"] == "进行中" and row["status_color"]

    # 旧 decision 对象不再被任何读路径消费
    task_factory(decisions=[{"id": "legacy", "text": "已下线的 decision 记录", "status": "active"}])
    assert all(r["id"] != "legacy" for r in client.get("/api/decisions").json()["decisions"])


def test_aggregation_filters_and_groups(client, task_factory, store):
    store.load_statuses()
    # 真实环下会加载数百个存量任务，因此用唯一 kb/日期隔离断言范围
    kb_a, kb_b = f"kb-{uuid.uuid4().hex[:8]}-a", f"kb-{uuid.uuid4().hex[:8]}-b"
    t1 = task_factory(title="甲会议", meeting_date="2026-09-20", project_id=kb_a,
                      todos=[{"id": "x1", "text": "甲会议决策", "status": "in_progress", "done": False}])
    task_factory(title="乙会议", meeting_date="2026-08-01", project_id=kb_b,
                 todos=[{"id": "x2", "text": "乙会议决策", "status": "done", "done": True}])

    assert {r["id"] for r in client.get("/api/decisions", params={"kb_id": kb_a}).json()["decisions"]} == {"x1"}
    assert {r["id"] for r in client.get("/api/decisions", params={"kb_id": kb_b}).json()["decisions"]} == {"x2"}
    assert {r["id"] for r in client.get("/api/decisions", params={"status": "in_progress", "kb_id": kb_a}).json()["decisions"]} == {"x1"}
    assert client.get("/api/decisions", params={"status": "nope"}).status_code == 422
    assert {r["id"] for r in client.get("/api/decisions", params={"q": "甲会议决策"}).json()["decisions"]} == {"x1"}
    assert {r["id"] for r in client.get("/api/decisions", params={"task_id": t1}).json()["decisions"]} == {"x1"}

    groups = client.get("/api/decisions", params={"kb_id": kb_a, "group_by": "meeting"}).json()["groups"]
    g = next(x for x in groups if x["task_id"] == t1)
    assert g["label"] == "甲会议" and [d["id"] for d in g["decisions"]] == ["x1"]


def test_aggregation_degrades_unknown_status_to_open_state(client, task_factory, store):
    store.load_statuses()
    task_factory(todos=[{"id": "z1", "text": "历史状态节点", "status": "deleted-custom-state", "done": False}])
    row = next(r for r in client.get("/api/decisions").json()["decisions"] if r["id"] == "z1")
    # 字典外的历史值 → 降级到首个开放态（待决策），不抛错不丢行
    assert row["status"] == "to_decide" and row["status_name"] == "待决策"


def test_legacy_task_without_status_derives_from_done(client, task_factory, store):
    store.load_statuses()
    task_factory(todos=[{"id": "old1", "text": "无状态字段的历史节点", "done": True}])
    row = next(r for r in client.get("/api/decisions").json()["decisions"] if r["id"] == "old1")
    assert row["status"] == "done" and row["status_closing"] is True


# ============================================================
# 5. 注入联动：todo 与 decision 同写决策流
# ============================================================

def test_decision_injection_joins_the_flow(client, task_factory):
    tid = task_factory()
    resp = client.post(f"/api/tasks/{tid}/inject", json={
        "type": "decision", "content": "**预算**：Q4 预算封顶 80 万", "source_message": "m1",
    })
    assert resp.status_code == 200
    assert "decisions" not in tasks[tid]           # 不再产生第二套对象
    node = tasks[tid]["todos"][0]
    assert node["title"] == "预算" and node["text"] == "Q4 预算封顶 80 万"
    assert node["status"] == "to_decide" and node["source"] == "injection"

    inj_id = resp.json()["item"]["id"]
    client.delete(f"/api/tasks/{tid}/injections/{inj_id}")
    assert tasks[tid]["todos"] == []


# ============================================================
# 6. 状态字典：三态默认 / 锚点 / 旧结构迁移 / 删除回落
# ============================================================

def test_dictionary_seeds_three_flow_statuses_with_single_anchor(store):
    ids = [s["id"] for s in store.load_statuses()]
    assert ids == ["to_decide", "in_progress", "done"]
    by_id = {s["id"]: s for s in store.load_statuses()}
    assert by_id["done"]["system"] is True and by_id["done"]["closing"] is True
    assert all(not by_id[k]["system"] for k in ("to_decide", "in_progress"))
    assert store.SYSTEM_ANCHORS == ("done",)


def test_legacy_dictionary_is_migrated_once_and_persisted(store):
    legacy = [
        {"id": "active", "name": "生效中", "name_en": "Active", "color": "var(--st-done)", "closing": False, "system": True},
        {"id": "done", "name": "完成", "name_en": "Done", "color": "var(--accent)", "closing": True, "system": True},
        {"id": "superseded", "name": "已被取代", "name_en": "Superseded", "color": "var(--st-decide)", "closing": True, "system": False},
    ]
    store.STATUSES_FILE.write_text(json.dumps(legacy), encoding="utf-8")
    ids = [s["id"] for s in store.load_statuses()]
    # 未改名的遗留态被剪除，三态种子补齐且完成态保持沉底
    assert "active" not in ids and "superseded" not in ids
    assert ids == ["to_decide", "in_progress", "done"]
    on_disk = json.loads(store.STATUSES_FILE.read_text(encoding="utf-8"))
    assert [s["id"] for s in on_disk] == ids


def test_user_renamed_legacy_status_survives_migration(store):
    legacy = [
        {"id": "active", "name": "已定案", "name_en": "Active", "color": "var(--ok)", "closing": False, "system": True},
        {"id": "done", "name": "完成", "name_en": "Done", "color": "var(--accent)", "closing": True, "system": True},
    ]
    store.STATUSES_FILE.write_text(json.dumps(legacy), encoding="utf-8")
    ids = [s["id"] for s in store.load_statuses()]
    assert "active" in ids          # 被用户改过名 → 保留，不静默丢失
    assert "to_decide" in ids       # 三态种子照样补齐


def test_anchor_protection_and_custom_status_crud(client, store):
    with pytest.MonkeyPatch.context() as mp:
        import core.decision_status as ds
        mp.setattr(ds, "STATUSES_FILE", store.STATUSES_FILE)
        mp.setattr(ds, "DATA_DIR", store.STATUSES_FILE.parent)
        with TestClient(app) as c:
            assert c.put("/api/decision-statuses/done", json={"name": "结项"}).status_code == 400
            assert c.delete("/api/decision-statuses/done").status_code == 400
            created = c.post("/api/decision-statuses", json={"name": "阻塞中", "color": "#d97706"}).json()["status"]
            assert created["id"].startswith("st-") and created["closing"] is False
            assert c.put(f"/api/decision-statuses/{created['id']}", json={"closing": True}).status_code == 200
            assert c.delete(f"/api/decision-statuses/{created['id']}").json()["ok"] is True


def test_backfill_script_writes_flow_and_is_idempotent():
    """R4 回填：存量纪要的结论合入决策流（backfill/待决策），连跑两次不重复。"""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("backfill_decisions", root / "scripts" / "backfill_decisions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    task = {
        "task_id": "bf-1", "status": "completed", "title": "存量会议", "summary": SUMMARY,
        "todos": [{"id": "keep", "text": "手动记录的决策", "source": "manual", "status": "in_progress", "done": False}],
    }
    category, added, _ = mod.backfill_task(task)
    assert category == "backfilled" and added == 3
    assert task["todos"][0]["id"] == "keep"                     # 手动节点保留
    backfilled = [t for t in task["todos"] if t.get("source") == "backfill"]
    assert len(backfilled) == 3 and all(t["status"] == "to_decide" for t in backfilled)

    # 幂等：第二次直接跳过，不重复入流
    assert mod.backfill_task(task) == ("skipped_has_decisions", 0, "")
    assert len([t for t in task["todos"] if t.get("source") == "backfill"]) == 3


def test_delete_status_reassigns_flow_nodes(client, task_factory, store, monkeypatch):
    import core.decision_status as ds
    import app.routers.decision_statuses as dst
    monkeypatch.setattr(ds, "STATUSES_FILE", store.STATUSES_FILE)
    monkeypatch.setattr(ds, "DATA_DIR", store.STATUSES_FILE.parent)
    monkeypatch.setattr(dst, "STATUSES_FILE", store.STATUSES_FILE, raising=False)
    store.load_statuses()
    # 新增一个自定义状态并让节点引用它
    ds.create_status("阻塞中", "#d97706", False)
    custom = next(s for s in ds.load_statuses() if s["name"] == "阻塞中")
    tid = task_factory(todos=[{"id": "b1", "text": "被阻塞的决策", "status": custom["id"], "done": False}])

    resp = client.delete(f"/api/decision-statuses/{custom['id']}")
    assert resp.status_code == 200 and resp.json()["reassigned"] == 1
    # 被删状态下的节点回落到删后字典的首个开放态
    assert tasks[tid]["todos"][0]["status"] == "to_decide"
