"""EP1-BE 第四段：决策资产只收集层（契约 §5，裁决4"只收集不消费"）。

断言面：收集幂等 upsert、修改→stale/重集、撤回→withdrawn 保留、全站零读端点。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.config import DataRoot
from app.db.dao import EnterpriseStore
from app.db.database import migrate
from app.db.security import hash_password
from app.routers import enterprise_api

SRC = "tsk_asset_src"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = tmp_path / "ENTERPRISE_DATA"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    enterprise_api.reset_store_cache()
    store = EnterpriseStore(DataRoot(root=root))
    migrate(store.conn)
    now = "2026-10-29T00:00:00+00:00"
    with store.conn:
        store.conn.execute(
            "INSERT INTO users(user_id, login_account, display_name, password_hash, role, status, created_at, updated_at)"
            " VALUES ('usr_admin','13373013103','管理员',?,'admin','active',?,?)",
            (hash_password("Admin-Pw-001"), now, now),
        )
    app = FastAPI()
    enterprise_api.register_enterprise_routes(app)
    c = TestClient(app)
    yield c, store, app
    enterprise_api.reset_store_cache()
    store.close()


def member(client, account):
    r = client.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-001"})
    c = client.post("/api/v1/admin/users", json={"display_name": account, "account": account}, cookies=r.cookies)
    act = client.post("/api/v1/auth/activate", json={"invite_code": c.json()["invite_code"], "password": f"Passw0rd-{account}"})
    return {"cookies": act.cookies, "user_id": act.json()["user_id"]}


def rows(store, task_id=None):
    q = "SELECT * FROM enterprise_decision_assets"
    if task_id:
        return [dict(r) for r in store.conn.execute(q + " WHERE source_task_id=? ORDER BY decision_id", (task_id,))]
    return [dict(r) for r in store.conn.execute(q + " ORDER BY decision_id")]


def publish_two_decisions(c, store, alice):
    tid = c.post("/api/v1/teams", json={"name": "资产组"}, cookies=alice["cookies"]).json()["team_id"]
    payload = {
        "meta": {"title": "资产演练"},
        "summary": "s", "notes": "n",
        "decisions": [{"id": "d1", "text": "原一", "status": "open"}, {"id": "d2", "text": "原二", "status": "done"}],
    }
    c.put(f"/api/v1/context/tasks/{SRC}/snapshot", json=payload,
          headers={"Idempotency-Key": "mut-a0", "If-Match-Rev": "0"}, cookies=alice["cookies"])
    copy = c.post(f"/api/v1/context/tasks/{SRC}/publish", json={"team_id": tid},
                  cookies=alice["cookies"]).json()
    return tid, copy["task_id"]


def test_collect_on_publish_and_idempotent(env):
    c, store, _ = env
    alice = member(c, "as_a")
    tid, copy_id = publish_two_decisions(c, store, alice)
    got = rows(store, copy_id)
    assert [g["decision_id"] for g in got] == ["d1", "d2"]
    assert all(g["status"] == "collected" and g["source_team_id"] == tid for g in got)
    assert got[0]["source_rev"] == 1 and got[0]["content_hash"]
    # 同 mutation 重放（助手重试）→ 不产生第二行
    c.post(f"/api/v1/context/tasks/{SRC}/publish", json={"team_id": tid}, cookies=alice["cookies"])
    assert len(rows(store, copy_id)) == 2


def test_edit_marks_stale_and_recollects(env):
    c, store, _ = env
    alice = member(c, "as_b")
    tid, copy_id = publish_two_decisions(c, store, alice)
    # editor 改 d1 文本、删 d2 → d1 快照刷新 rev=2，d2 标 stale 不删除（可追溯性承诺）
    r = c.put(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/snapshot",
              json={"summary": "s", "decisions": [{"id": "d1", "text": "改一", "status": "open"}]},
              headers={"Idempotency-Key": "mut-a1", "If-Match-Rev": "1"}, cookies=alice["cookies"])
    assert r.status_code == 200
    got = {g["decision_id"]: g for g in rows(store, copy_id)}
    assert got["d2"]["status"] == "stale"
    assert got["d1"]["status"] == "collected" and got["d1"]["source_rev"] == 2
    assert "改一" in got["d1"]["snapshot_json"]
    # 恢复 d2（走删除前历史 rev=1）→ 重新 collected
    rs = c.post(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/decisions/d2/restore",
                json={"from_rev": 1}, cookies=alice["cookies"])
    assert rs.status_code == 200
    # restore 走的是历史 blob，d1 也会以历史值合并回——重点断言 d2 生命周期
    got2 = {g["decision_id"]: g for g in rows(store, copy_id)}
    assert got2["d2"]["status"] == "collected" and got2["d2"]["source_rev"] == 3
    # 行从不物理删除
    assert store.conn.execute("SELECT COUNT(*) c FROM enterprise_decision_assets").fetchone()["c"] == 2


def test_withdraw_keeps_rows_as_withdrawn(env):
    c, store, _ = env
    alice = member(c, "as_c")
    tid, copy_id = publish_two_decisions(c, store, alice)
    c.delete(f"/api/v1/context/teams/{tid}/tasks/{copy_id}", cookies=alice["cookies"])
    got = rows(store, copy_id)
    assert len(got) == 2 and all(g["status"] == "withdrawn" and g["withdrawn_at"] for g in got)


def test_zero_consumer_surface(env):
    c, store, app = env
    alice = member(c, "as_d")
    publish_two_decisions(c, store, alice)
    # 无读端点：猜测路径全部 404（by design，QA 断言点）
    for path in ("/api/v1/enterprise/assets", "/api/v1/enterprise/decision-assets",
                 "/api/v1/context/enterprise/tasks", "/api/v1/admin/assets"):
        assert c.get(path, cookies=alice["cookies"]).status_code == 404
    # 路由表级反断言：注册的所有企业路由均不含资产读路径
    routes = [getattr(r, "path", "") for r in app.routes]
    assert not [p for p in routes if "enterprise" in p or "decision-assets" in p]
    # 实例管理员也无内容读面（§2 QA-Q2 延续）——管理员 cookie 拉团队列表也只回自己的
    adm = c.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-001"}).cookies
    assert c.get("/api/v1/context/teams", cookies=adm).json()["teams"] == []
