"""EP0-BE 增量2 端点层集成测试（TestClient 全流程）。"""
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
def client(tmp_path, monkeypatch):
    root = tmp_path / "ENTERPRISE_DATA"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    enterprise_api.reset_store_cache()

    # 初始化实例库并 seed bootstrap admin（模拟初始化向导第一步）
    store = EnterpriseStore(DataRoot(root=root))
    migrate(store.conn)
    now = "2026-10-29T00:00:00+00:00"
    with store.conn:
        store.conn.execute(
            "INSERT INTO users(user_id, login_account, phone, display_name, password_hash, role, status, created_at, updated_at)"
            " VALUES ('usr_admin','13373013103','13373013103','管理员',?,'admin','active',?,?)",
            (hash_password("Admin-Pw-001"), now, now),
        )

    app = FastAPI()
    enterprise_api.register_enterprise_routes(app)
    c = TestClient(app)
    yield c
    enterprise_api.reset_store_cache()


PAYLOAD = {
    "meta": {"title": "周会", "meeting_time": "2026-10-29T09:00:00+00:00", "participants_text": "甲", "source": "client"},
    "formal": "定稿文本",
    "summary": "纪要",
    "decisions": [],
    "notes": "n",
}


def login(client, account, password):
    r = client.post("/api/v1/auth/login", json={"account": account, "password": password})
    assert r.status_code == 200, r.text
    return r


def make_member(client, account="emp1"):
    r = login(client, "13373013103", "Admin-Pw-001")
    admin_cookie = r.cookies
    c = client.post("/api/v1/admin/users", json={"display_name": "员工", "account": account}, cookies=admin_cookie)
    assert c.status_code == 200, c.text
    invite = c.json()["invite_code"]
    act = client.post("/api/v1/auth/activate", json={"invite_code": invite, "password": "Emp-Pw-0001"})
    assert act.status_code == 200, act.text
    return act.cookies


def test_healthz_and_instance_info(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    info = client.get("/api/v1/instance/info").json()
    assert info["product"] == "oms-enterprise"
    assert info["service_open"] is True and info["needs_bootstrap"] is False
    assert info["ai_enabled"] is False


def test_auth_flows(client):
    assert client.post("/api/v1/auth/login", json={"account": "13373013103", "password": "bad"}).status_code == 401
    cookies = make_member(client)
    me = client.get("/api/v1/auth/me", cookies=cookies)
    assert me.status_code == 200 and me.json()["role"] == "member"
    # 邀请码自助设密后才有密码——建号响应无 password 字段（插单③）
    # change-password
    cp = client.post(
        "/api/v1/auth/change-password", json={"old_password": "Emp-Pw-0001", "new_password": "Emp-Pw-0002"}, cookies=cookies
    )
    assert cp.status_code == 200, cp.text
    assert client.post("/api/v1/auth/login", json={"account": "emp1", "password": "Emp-Pw-0002"}).status_code == 200
    out = client.post("/api/v1/auth/logout", cookies=cookies)
    assert out.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401  # 登出后会话吊销


def test_admin_surface_guards(client):
    emp = make_member(client, "emp2")
    r = client.get("/api/v1/admin/users", cookies=emp)  # 员工访问管理面
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    adm = login(client, "13373013103", "Admin-Pw-001").cookies
    users = client.get("/api/v1/admin/users", cookies=adm)
    assert users.status_code == 200
    assert all("password_hash" not in u for u in users.json()["users"])


def test_snapshot_contract(client):
    emp = make_member(client, "emp3")
    r = client.put(
        "/api/v1/context/tasks/tsk_api1/snapshot",
        json=PAYLOAD,
        headers={"Idempotency-Key": "mut-a", "If-Match-Rev": "0"},
        cookies=emp,
    )
    assert r.status_code == 201 and r.json()["server_rev"] == 1
    rep = client.put(
        "/api/v1/context/tasks/tsk_api1/snapshot",
        json=PAYLOAD,
        headers={"Idempotency-Key": "mut-a", "If-Match-Rev": "0"},
        cookies=emp,
    )
    assert rep.status_code == 200 and rep.json()["idempotent_replay"] is True
    stale = client.put(
        "/api/v1/context/tasks/tsk_api1/snapshot",
        json=PAYLOAD,
        headers={"Idempotency-Key": "mut-b", "If-Match-Rev": "0"},
        cookies=emp,
    )
    assert stale.status_code == 409 and stale.json()["error"]["current_rev"] == 1
    bad = client.put(
        "/api/v1/context/tasks/tsk_api1/snapshot",
        json={**PAYLOAD, "audio_base64": "x"},
        headers={"Idempotency-Key": "mut-c", "If-Match-Rev": "1"},
        cookies=emp,
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "payload_not_allowed"
    task = client.get("/api/v1/context/tasks/tsk_api1", cookies=emp).json()
    assert task["visibility"] == "personal" and task["sync_status"] == "synced"  # 插单①②

    # 跨用户：另一员工读/写该 task → 统一 404（防枚举）
    other = make_member(client, "emp4")
    assert client.get("/api/v1/context/tasks/tsk_api1", cookies=other).status_code == 404
    w = client.put(
        "/api/v1/context/tasks/tsk_api1/snapshot",
        json=PAYLOAD,
        headers={"Idempotency-Key": "mut-x", "If-Match-Rev": "1"},
        cookies=other,
    )
    assert w.status_code == 404 and w.json()["error"]["code"] == "not_found"
    # 未登录一律 401（清空 TestClient cookie jar，模拟无 cookie 客户端）
    client.cookies.clear()
    assert client.get("/api/v1/context/tasks").status_code == 401


def test_service_closed_semantics(client):
    emp = make_member(client, "emp5")
    adm = login(client, "13373013103", "Admin-Pw-001").cookies
    client.put(
        "/api/v1/context/tasks/tsk_c/snapshot", json=PAYLOAD,
        headers={"Idempotency-Key": "mut-c1", "If-Match-Rev": "0"}, cookies=emp,
    )
    assert client.post("/api/v1/admin/instance/close", cookies=adm).json()["service_open"] is False
    # 已登录会话不踢出、读放行（裁决 #4）
    g = client.get("/api/v1/context/tasks/tsk_c", cookies=emp)
    assert g.status_code == 200
    # 写禁用
    wr = client.put(
        "/api/v1/context/tasks/tsk_c/snapshot", json=PAYLOAD,
        headers={"Idempotency-Key": "mut-c2", "If-Match-Rev": "1"}, cookies=emp,
    )
    assert wr.status_code == 503 and wr.json()["error"]["code"] == "service_closed"
    # 新登录拦截
    li = client.post("/api/v1/auth/login", json={"account": "emp5", "password": "Emp-Pw-0001"})
    assert li.status_code == 403 and li.json()["error"]["code"] == "service_closed"
    # 横幅数据源
    assert client.get("/api/v1/instance/info").json()["service_open"] is False
    assert client.post("/api/v1/admin/instance/open", cookies=adm).status_code == 200


def test_pairing_device_token(client):
    emp = make_member(client, "emp6")
    pr = client.post("/api/v1/pairings", cookies=emp)
    assert pr.status_code == 200
    da = client.post("/api/v1/auth/device-activate", json={"pairing_code": pr.json()["pairing_code"], "device_name": "助手"})
    assert da.status_code == 200
    token = da.json()["device_token"]
    r = client.put(
        "/api/v1/context/tasks/tsk_dev/snapshot", json=PAYLOAD,
        headers={"Idempotency-Key": "mut-d1", "If-Match-Rev": "0", "Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201  # 助手写入
    devs = client.get("/api/v1/devices", cookies=emp).json()["devices"]
    assert len(devs) == 1
    client.delete(f"/api/v1/devices/{devs[0]['device_id']}", cookies=emp)
    client.cookies.clear()  # 剥离会话 cookie：仅凭已吊销 device token
    revoked = client.put(
        "/api/v1/context/tasks/tsk_dev/snapshot", json=PAYLOAD,
        headers={"Idempotency-Key": "mut-d2", "If-Match-Rev": "1", "Authorization": f"Bearer {token}"},
    )
    assert revoked.status_code == 401  # device 吊销后写入被拒


def test_disable_and_bulk_delete(client):
    emp = make_member(client, "emp7")
    adm = login(client, "13373013103", "Admin-Pw-001").cookies
    client.put(
        "/api/v1/context/tasks/tsk_k/snapshot", json=PAYLOAD,
        headers={"Idempotency-Key": "mut-k", "If-Match-Rev": "0"}, cookies=emp,
    )
    uid = client.get("/api/v1/auth/me", cookies=emp).json()["user_id"]
    assert client.put(f"/api/v1/admin/users/{uid}/status", json={"status": "disabled"}, cookies=adm).status_code == 200
    assert client.get("/api/v1/auth/me", cookies=emp).status_code == 401  # 停用即刻踢出读取
    # 数据保留（QA-Q3）：整包删除前员工数据行仍在（管理员视角仅见计数）
    dl = client.delete(f"/api/v1/admin/users/{uid}/data", cookies=adm)
    assert dl.status_code == 200 and dl.json()["deleted_tasks"] == 1


def test_admin_reset_password_invite(client):
    emp = make_member(client, "emp8")
    adm = login(client, "13373013103", "Admin-Pw-001").cookies
    uid = client.get("/api/v1/auth/me", cookies=emp).json()["user_id"]
    rc = client.post(f"/api/v1/admin/users/{uid}/reset", cookies=adm)
    assert rc.status_code == 200
    assert "invite_code" in rc.json() and "password" not in rc.json()
    assert client.post("/api/v1/auth/login", json={"account": "emp8", "password": "Emp-Pw-0001"}).status_code == 401
    na = client.post("/api/v1/auth/activate", json={"invite_code": rc.json()["invite_code"], "password": "Emp-Pw-New1"})
    assert na.status_code == 200
    assert client.get("/api/v1/auth/me", cookies=na.cookies).status_code == 200


def test_assets_and_ai_disabled(client):
    emp = make_member(client, "emp9")
    put = client.put(
        "/api/v1/context/assets/hotwords", json={"payload": ["消歧", "上下文"]},
        headers={"Idempotency-Key": "mut-h1", "If-Match-Rev": "0"}, cookies=emp,
    )
    assert put.status_code == 200 and put.json()["current_rev"] == 1
    get = client.get("/api/v1/context/assets/hotwords", cookies=emp).json()
    assert get["visibility"] == "personal" and get["payload"] == ["消歧", "上下文"]
    sp = client.put(
        "/api/v1/context/assets/speaker-aliases", json={"payload": {"spk1": "张三"}},
        headers={"Idempotency-Key": "mut-s1", "If-Match-Rev": "0"}, cookies=emp,
    )
    assert sp.status_code == 200
    ai = client.post("/api/v1/ai/summary/generate", json={"task_id": "tsk_z"}, cookies=emp)
    assert ai.status_code == 409 and ai.json()["error"]["code"] == "ai_disabled"


def test_qa_http_mappings(client):
    """QA 移交映射①②：禁 5xx。"""
    emp = make_member(client, "emp10")
    client.put(
        "/api/v1/context/tasks/tsk_q1/snapshot", json=PAYLOAD,
        headers={"Idempotency-Key": "mut-q1", "If-Match-Rev": "0"}, cookies=emp,
    )
    # ① 同 mutation 跨 task 复用 → 422（非 500）
    cross = client.put(
        "/api/v1/context/tasks/tsk_q2/snapshot", json=PAYLOAD,
        headers={"Idempotency-Key": "mut-q1", "If-Match-Rev": "0"}, cookies=emp,
    )
    assert cross.status_code == 422 and cross.json()["error"]["code"] == "client_mutation_conflict"
    # ② 弱密码激活 → 422（非 500）
    adm = login(client, "13373013103", "Admin-Pw-001").cookies
    c = client.post("/api/v1/admin/users", json={"display_name": "x", "account": "emp11"}, cookies=adm)
    weak = client.post("/api/v1/auth/activate", json={"invite_code": c.json()["invite_code"], "password": "short"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "activation_failed"
    # 资产 embedding 夹带 → 422 内容级拒收
    emb = client.put(
        "/api/v1/context/assets/speaker-aliases", json={"payload": {"spk1": [0.1, 0.2]}},
        headers={"Idempotency-Key": "mut-e1", "If-Match-Rev": "0"}, cookies=emp,
    )
    assert emb.status_code == 422 and emb.json()["error"]["code"] == "payload_not_allowed"


def test_personal_edition_not_mounted(monkeypatch):
    monkeypatch.delenv("OMS_EDITION", raising=False)
    assert enterprise_api.enterprise_mode() is False
    monkeypatch.setenv("OMS_EDITION", "enterprise")
    assert enterprise_api.enterprise_mode() is True
