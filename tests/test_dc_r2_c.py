"""
tests/test_dc_r2_c.py — DC-R2-c 决策状态字典回归（REQ-DECISION-CENTER-R2 §11-D6/D7）

隔离口径：monkeypatch core.decision_status.STATUSES_FILE / DATA_DIR → tmp_path，
不触碰真实 data/decision_statuses.json。
"""
import json

import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """状态字典文件指向临时目录（首次读取即触发默认集迁移落盘）。"""
    import core.decision_status as ds

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(ds, "DATA_DIR", data_dir)
    monkeypatch.setattr(ds, "STATUSES_FILE", data_dir / "decision_statuses.json")
    yield ds


@pytest.fixture()
def client(store):
    from fastapi.testclient import TestClient

    from app.server import app
    with TestClient(app) as c:
        yield c


# ============================================================
# 1. 迁移与系统锚点（D6）
# ============================================================

def test_first_read_seeds_defaults_with_two_anchors(store):
    statuses = store.load_statuses()
    ids = [s["id"] for s in statuses]
    assert ids[:2] == ["active", "done"]
    by_id = {s["id"]: s for s in statuses}
    # 锚点：不可改名不可删（system=True）
    assert by_id["active"]["system"] is True and by_id["active"]["closing"] is False
    assert by_id["done"]["system"] is True and by_id["done"]["closing"] is True
    # 历史 superseded/revoked 降级为可编辑普通状态，且默认闭档（语义不丢）
    assert by_id["superseded"]["system"] is False and by_id["superseded"]["closing"] is True
    assert by_id["revoked"]["system"] is False and by_id["revoked"]["closing"] is True
    # 迁移即落盘，二次读取稳定
    assert store.STATUSES_FILE.exists()
    assert [s["id"] for s in store.load_statuses()] == ids


def test_tampered_file_missing_anchors_falls_back_to_defaults(store):
    store.STATUSES_FILE.write_text(json.dumps([{"id": "custom", "name": "自定义"}]), encoding="utf-8")
    ids = {s["id"] for s in store.load_statuses()}
    assert {"active", "done"} <= ids


# ============================================================
# 2. 锚点保护与自定义状态 CRUD
# ============================================================

def test_anchor_rename_and_delete_and_closing_are_rejected(store):
    with pytest.raises(store.StatusError):
        store.update_status("done", name="搞定了")
    with pytest.raises(store.StatusError):
        store.update_status("active", closing=True)
    with pytest.raises(store.StatusError):
        store.delete_status("active")
    # 锚点允许改色（视觉自定义仍是全量的）
    updated = store.update_status("done", color="#123456")
    assert updated["color"] == "#123456" and updated["name"] == "完成"


def test_custom_status_lifecycle(store):
    created = store.create_status("跟进中", color="#0ea5e9")
    assert created["system"] is False and created["closing"] is False
    assert created["id"] in store.known_ids()
    with pytest.raises(store.StatusError):
        store.create_status("跟进中")           # 重名拒绝
    renamed = store.update_status(created["id"], name="推进中", closing=True)
    assert renamed["name"] == "推进中" and renamed["closing"] is True
    assert renamed["id"] in store.closing_ids()
    assert store.delete_status(created["id"])["removed"] == created["id"]
    assert created["id"] not in store.known_ids()


def test_reorder_requires_full_coverage(store):
    ids = [s["id"] for s in store.load_statuses()]
    reordered = store.reorder(list(reversed(ids)))
    assert [s["id"] for s in reordered] == list(reversed(ids))
    with pytest.raises(store.StatusError):
        store.reorder(ids[:-1])                 # 缺项
    with pytest.raises(store.StatusError):
        store.reorder(ids + [ids[0]])           # 重复


# ============================================================
# 3. 决策写入与聚合的状态合法性
# ============================================================

def _seed_task(client, tasks_dict):
    task_id = "dc-r2c-task"
    tasks_dict[task_id] = {
        "task_id": task_id, "title": "状态字典验证会", "status": "completed",
        "meeting_date": "2026-09-25", "decisions": [{
            "id": "d1", "title": "", "text": "一条待办决策", "owner_id": None, "owner_name": "",
            "status": "active", "pending_confirmation": False, "source": "manual",
            "created_at": "2026-09-25T09:00:00", "updated_at": "2026-09-25T09:00:00",
            "superseded_by": None, "related_todo_ids": [],
        }],
    }
    return task_id


@pytest.fixture()
def patched_tasks(store, monkeypatch):
    """决策路由的任务表指向临时字典（不触碰真实 data/tasks/）。"""
    from app.routers import decision_statuses as dsr
    from app.routers import decisions as dr

    fake: dict = {}
    monkeypatch.setattr(dr, "tasks", fake)
    monkeypatch.setattr(dsr, "tasks", fake)
    monkeypatch.setattr(dr, "save_task_to_disk", lambda tid: None)
    monkeypatch.setattr(dsr, "save_task_to_disk", lambda tid: None)
    return fake


def test_put_decision_status_accepts_custom_and_rejects_unknown(client, patched_tasks):
    tid = _seed_task(client, patched_tasks)
    created = client.post("/api/decision-statuses", json={"name": "搁置"}).json()["status"]

    resp = client.put(f"/api/tasks/{tid}/decisions/d1", json={"status": created["id"]})
    assert resp.status_code == 200
    assert resp.json()["decision"]["status"] == created["id"]

    assert client.put(f"/api/tasks/{tid}/decisions/d1", json={"status": "nope"}).status_code == 422
    # 锚点之外的历史值同样合法（superseded 现为普通状态，存量数据不破）
    assert client.put(f"/api/tasks/{tid}/decisions/d1", json={"status": "superseded"}).status_code == 200


def test_aggregation_carries_status_metadata(client, patched_tasks):
    tid = _seed_task(client, patched_tasks)
    row = client.get("/api/decisions").json()["decisions"][0]
    assert row["status_name"] == "生效中"
    assert row["status_closing"] is False
    assert row["status_color"].startswith("var(")

    client.put(f"/api/tasks/{tid}/decisions/d1", json={"status": "done"})
    row = client.get("/api/decisions").json()["decisions"][0]
    assert row["status_name"] == "完成" and row["status_closing"] is True


def test_aggregation_status_filter_accepts_dictionary_ids(client, patched_tasks):
    _seed_task(client, patched_tasks)
    assert client.get("/api/decisions", params={"status": "superseded"}).status_code == 200
    custom = client.post("/api/decision-statuses", json={"name": "复核中"}).json()["status"]
    assert client.get("/api/decisions", params={"status": custom["id"]}).status_code == 200
    assert client.get("/api/decisions", params={"status": "bogus"}).status_code == 422


def test_default_visible_ids_follow_closing_flag(store):
    """D7：默认视图 = 非闭档状态；新建不勾闭档的状态自动进入默认可见集。"""
    visible = store.default_visible_ids()
    assert "active" in visible
    assert not visible & {"done", "superseded", "revoked"}
    plain = store.create_status("跟进中")
    closed = store.create_status("已作废", closing=True)
    assert plain["id"] in store.default_visible_ids()
    assert closed["id"] not in store.default_visible_ids()


# ============================================================
# 4. supersede / revoke 写回入口下线（D6）
# ============================================================

def test_supersede_endpoint_removed(client, patched_tasks):
    tid = _seed_task(client, patched_tasks)
    resp = client.patch(f"/api/tasks/{tid}/decisions/d1/supersede",
                        json={"task_id": tid, "decision_id": "d1"})
    # 路由不存在：405（方法不允许）或 404，二者都表示写回入口已摘除
    assert resp.status_code in (404, 405), resp.status_code


def test_legacy_superseded_by_still_readable(client, patched_tasks):
    """存量取代关系不再写入，但读取与聚合不得因字段存在而报错（数据诚实）。"""
    tid = _seed_task(client, patched_tasks)
    patched_tasks[tid]["decisions"][0]["superseded_by"] = {"task_id": "gone", "decision_id": "gone"}
    patched_tasks[tid]["decisions"][0]["status"] = "superseded"
    rows = client.get("/api/decisions").json()["decisions"]
    assert rows[0]["superseded_by"] == {"task_id": "gone", "decision_id": "gone"}
    assert rows[0]["status_name"] == "已被取代"


# ============================================================
# 5. 删除自定义状态：引用决策回落 active
# ============================================================

def test_delete_status_reassigns_referencing_decisions(client, patched_tasks, store, monkeypatch):
    tid = _seed_task(client, patched_tasks)
    custom = client.post("/api/decision-statuses", json={"name": "待供应商确认"}).json()["status"]
    client.put(f"/api/tasks/{tid}/decisions/d1", json={"status": custom["id"]})

    saved = []
    from app.routers import decision_statuses as dsr
    monkeypatch.setattr(dsr, "save_task_to_disk", lambda t: saved.append(t))

    resp = client.delete(f"/api/decision-statuses/{custom['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["removed"] == custom["id"] and body["reassigned"] == 1
    assert patched_tasks[tid]["decisions"][0]["status"] == "active"
    assert saved == [tid]
    # 锚点删除仍被拒
    assert client.delete("/api/decision-statuses/done").status_code == 400
