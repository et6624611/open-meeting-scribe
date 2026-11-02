"""EP1-BE 第二段：teams/成员/ACL/留痕端点集成测试（TestClient 全流程）。

契约基线：DESIGN-P1-SPACES-BACKEND v1.0 §2/§8；错误语义断言：非成员=404、角色不足=403。
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
    yield c, store
    enterprise_api.reset_store_cache()
    store.close()


def create_member(client, account: str, display: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-001"})
    admin_cookie = r.cookies
    c = client.post(
        "/api/v1/admin/users", json={"display_name": display, "account": account}, cookies=admin_cookie
    )
    invite = c.json()["invite_code"]
    act = client.post("/api/v1/auth/activate", json={"invite_code": invite, "password": f"Passw0rd-{account}"})
    assert act.status_code == 200, act.text
    body = act.json()
    return {"cookies": act.cookies, "user_id": body["user_id"], "display_name": display}


# ---------------- 建团队 + 切换器数据源（依赖 1 字段逐字） ----------------


def test_create_team_and_switcher_fields(env):
    c, _ = env
    alice = create_member(c, "alice", "Alice 工")
    t = c.post("/api/v1/teams", json={"name": "研发一组"}, cookies=alice["cookies"])
    assert t.status_code == 201, t.text
    tid = t.json()["team_id"]
    lst = c.get("/api/v1/context/teams", cookies=alice["cookies"]).json()["teams"]
    assert [x["team_id"] for x in lst] == [tid]
    row = lst[0]
    for key in ("team_id", "name", "my_role", "member_count", "joined_at", "status"):
        assert key in row, f"切换器缺字段 {key}"
    assert row["my_role"] == "admin" and row["member_count"] == 1 and row["status"] == "active"
    # 空名拒建（422），未登录 401
    assert c.post("/api/v1/teams", json={"name": "  "}, cookies=alice["cookies"]).status_code == 422
    c.cookies.clear()
    assert c.get("/api/v1/teams").status_code == 401
    assert c.get("/api/v1/users/search").status_code == 401


# ---------------- ACL 矩阵核心格（§2） ----------------


def test_acl_matrix(env):
    c, _ = env
    owner = create_member(c, "boss", "组长")
    bob = create_member(c, "bob", "Bob")
    carol = create_member(c, "carol", "Carol")
    out = create_member(c, "out", "局外人")
    tid = c.post("/api/v1/teams", json={"name": "T"}, cookies=owner["cookies"]).json()["team_id"]

    for acc, role in ((bob, "editor"), (carol, "viewer")):
        r = c.post("/api/v1/teams/{t}/members".replace("{t}", tid),
                   json={"user_ids": [acc["user_id"]], "role": role}, cookies=owner["cookies"])
        assert r.status_code == 201, r.text

    # 局外人：读团队=404（防枚举），加成员=404
    assert c.get(f"/api/v1/teams/{tid}", cookies=out["cookies"]).status_code == 404
    assert c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [out["user_id"]]},
                  cookies=out["cookies"]).status_code == 404
    # viewer 调角色：403 明示（角色是明示语义非资源隐藏）
    d403 = c.put(f"/api/v1/teams/{tid}/members/{bob['user_id']}/role", json={"role": "viewer"},
                 cookies=carol["cookies"])
    assert d403.status_code == 403 and d403.json()["error"]["code"] == "team_role_required"
    # editor 加成员：403
    assert c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [carol["user_id"]]},
                  cookies=bob["cookies"]).status_code == 403
    # D010 终态：重复加同一人 → 批量形态 failed 列表承载 already_member（不整体 409/404）
    dup = c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [bob["user_id"]]},
                 cookies=owner["cookies"])
    assert dup.status_code == 201 and dup.json()["added"] == []
    assert dup.json()["failed"] == [{"user_id": bob["user_id"], "code": "already_member"}]
    # 团队详情成员表
    detail = c.get(f"/api/v1/teams/{tid}", cookies=bob["cookies"]).json()
    assert {m["role"] for m in detail["members"]} == {"admin", "editor", "viewer"}


# ---------------- 最后 admin 守护 + 转让（K1 role_transfer 留痕） ----------------


def test_last_admin_guard_and_transfer(env):
    c, _ = env
    owner = create_member(c, "o2", "组长二")
    dave = create_member(c, "dave", "Dave")
    tid = c.post("/api/v1/teams", json={"name": "T2"}, cookies=owner["cookies"]).json()["team_id"]
    c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [dave["user_id"]], "role": "editor"},
           cookies=owner["cookies"])
    # 降级/移除最后一名 admin → 409 last_admin
    assert c.put(f"/api/v1/teams/{tid}/members/{owner['user_id']}/role", json={"role": "editor"},
                 cookies=owner["cookies"]).status_code == 409
    assert c.delete(f"/api/v1/teams/{tid}/members/{owner['user_id']}",
                    cookies=owner["cookies"]).status_code == 409
    # 转让：dave 升 admin、owner 降 editor；留痕 role_transfer
    tr = c.post(f"/api/v1/teams/{tid}/transfer-admin", json={"to_user_id": dave["user_id"]},
                cookies=owner["cookies"])
    assert tr.status_code == 200, tr.text
    det = c.get(f"/api/v1/teams/{tid}", cookies=dave["cookies"]).json()
    roles = {m["user_id"]: m["role"] for m in det["members"]}
    assert roles[dave["user_id"]] == "admin" and roles[owner["user_id"]] == "editor"
    # editor（原组长）已无转移权
    assert c.post(f"/api/v1/teams/{tid}/transfer-admin", json={"to_user_id": owner["user_id"]},
                  cookies=owner["cookies"]).status_code == 403


# ---------------- 归档（裁决④）+ 变更记录端点（§8.4 倒序分页、viewer 可读） ----------------


def test_archive_and_audit_feed(env):
    c, _ = env
    owner = create_member(c, "o3", "组长三")
    viewer = create_member(c, "v3", "读三")
    tid = c.post("/api/v1/teams", json={"name": "T3"}, cookies=owner["cookies"]).json()["team_id"]
    c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [viewer["user_id"]], "role": "viewer"},
           cookies=owner["cookies"])
    ar = c.put(f"/api/v1/teams/{tid}/archive", cookies=owner["cookies"])
    assert ar.status_code == 200 and ar.json()["status"] == "archived"
    # 重复归档 409
    assert c.put(f"/api/v1/teams/{tid}/archive", cookies=owner["cookies"]).status_code == 409
    # 切换器仍见（只读标记由 status 字段承载，规格 §2）
    assert c.get("/api/v1/context/teams", cookies=owner["cookies"]).json()["teams"][0]["status"] == "archived"
    # viewer 可读留痕；倒序；枚举值原样透出
    feed = c.get(f"/api/v1/teams/{tid}/audit", cookies=viewer["cookies"]).json()
    actions = [i["action"] for i in feed["items"]]
    assert actions[0] == "team_archive" and "member_add" in actions and "member_role_change" not in actions
    assert all(i["actor_name"] for i in feed["items"])
    # 分页参数边界仍 200
    assert c.get(f"/api/v1/teams/{tid}/audit?limit=1", cookies=viewer["cookies"]).status_code == 200


# ---------------- users/search 隐私面（§8.5 只回两字段） ----------------


def test_users_search_shape(env):
    c, _ = env
    alice = create_member(c, "sea", "Searchable 人")
    r = c.get("/api/v1/users/search?q=Searchable", cookies=alice["cookies"])
    assert r.status_code == 200
    hits = r.json()["users"]
    assert any(h["user_id"] == alice["user_id"] for h in hits)
    assert all(set(h) == {"user_id", "display_name"} for h in hits)  # 不暴露联系面/状态
    c.cookies.clear()
    assert c.get("/api/v1/users/search").status_code == 401


# ---------------- 停用级联撤权（§2 离职撤权，DAO 直连断言） ----------------


def test_disable_user_revokes_membership(env):
    c, store = env
    owner = create_member(c, "o4", "组长四")
    gone = create_member(c, "g4", "将离")
    tid = c.post("/api/v1/teams", json={"name": "T4"}, cookies=owner["cookies"]).json()["team_id"]
    c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [gone["user_id"]], "role": "editor"},
           cookies=owner["cookies"])
    adm = c.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-001"}).cookies
    assert c.put(f"/api/v1/admin/users/{gone['user_id']}/status", json={"status": "disabled"},
                 cookies=adm).status_code == 200
    assert store.team_role(tid, gone["user_id"]) is None  # effective 撤权
    n_eff = store.conn.execute(
        "SELECT COUNT(*) c FROM team_members WHERE user_id=? AND effective=1", (gone["user_id"],)
    ).fetchone()["c"]
    assert n_eff == 0
    # 行保留审计：撤权后原成员行仍可查（QA 追溯面）
    kept = store.conn.execute(
        "SELECT effective FROM team_members WHERE team_id=? AND user_id=?", (tid, gone["user_id"])
    ).fetchone()
    assert kept is not None and kept["effective"] == 0


# ---------------- D010 缺陷回归：批量终态 + 错误面明示（禁 404 静默） ----------------


def test_d010_batch_member_payload(env):
    c, _ = env
    boss = create_member(c, "d10_boss", "老板")
    u1, u2 = create_member(c, "d10_u1", "成员一"), create_member(c, "d10_u2", "成员二")
    tid = c.post("/api/v1/teams", json={"name": "D10"}, cookies=boss["cookies"]).json()["team_id"]
    # FE 终态形态：user_ids 批量 → 201，added 两条
    ok = c.post(f"/api/v1/teams/{tid}/members",
                json={"user_ids": [u1["user_id"], u2["user_id"]], "role": "editor"}, cookies=boss["cookies"])
    assert ok.status_code == 201, ok.text
    assert len(ok.json()["added"]) == 2 and ok.json()["failed"] == []
    # 旧单值形态 = 客户端构造错误 → 422 明示（缺陷原形态为 404 静默，整改依据即 PM 拍板三）
    legacy = c.post(f"/api/v1/teams/{tid}/members", json={"user_id": u1["user_id"]}, cookies=boss["cookies"])
    assert legacy.status_code == 422 and legacy.json()["error"]["code"] == "invalid_member_payload"
    # 缺字段/空数组/非数组 → 422
    for bad in ({}, {"user_ids": []}, {"user_ids": "not-a-list"}):
        r = c.post(f"/api/v1/teams/{tid}/members", json=bad, cookies=boss["cookies"])
        assert r.status_code == 422, bad
    # 混合批量：合法+幽灵 id → added 1 条 + failed 承载，不整体失败
    ghost = c.post(f"/api/v1/teams/{tid}/members",
                   json={"user_ids": ["usr_ghost", u2["user_id"]]}, cookies=boss["cookies"])
    assert ghost.status_code == 201
    assert ghost.json()["added"] == [] and ghost.json()["failed"][0]["code"] == "user_not_found"
    assert ghost.json()["failed"][1]["code"] == "already_member"
