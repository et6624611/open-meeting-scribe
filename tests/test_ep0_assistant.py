"""EP0-BE 增量4 测试：助手本地面路由 + outbox 状态机 + 真实 uvicorn 双端 e2e。

e2e 证据链：assistant 配对 → 定稿入队 → flush 经真实 HTTP 推送企业实例 → instance.db 入库 → Web 会话读取。
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.config import DataRoot
from app.db.dao import EnterpriseStore
from app.db.database import migrate
from app.db.security import hash_password
from app.local_sync import AssistantPlane
from app.routers import assistant_plane, enterprise_api


# ---------------------------------------------------------------------------
# 助手路由单测（TestClient，无需企业实例）
# ---------------------------------------------------------------------------


@pytest.fixture()
def assistant_client(tmp_path, monkeypatch):
    root = tmp_path / "ASSISTANT_DATA"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    monkeypatch.setenv("OMS_EDITION", "assistant")
    from app import local_sync

    local_sync.reset_plane()
    app = FastAPI()
    assistant_plane.register_assistant_routes(app)
    c = TestClient(app)
    yield c
    local_sync.reset_plane()


def _token(client) -> str:
    hs = client.get("/api/local/handshake")
    assert hs.status_code == 200
    return hs.json()["local_token"]


def test_handshake_and_guard(assistant_client):
    hs = assistant_client.get("/api/local/handshake").json()
    assert hs["paired"] is False and hs["local_token"]
    # 无 token → 401 local_unauthenticated
    q = assistant_client.get("/api/sync/queue")
    assert q.status_code == 401 and q.json()["error"]["code"] == "local_unauthenticated"
    # header 承载
    tok = _token(assistant_client)
    q = assistant_client.get("/api/sync/queue", headers={"X-OMS-Local-Token": tok})
    assert q.status_code == 200 and q.json()["queue"] == []
    # query 承载（WS 裁决同源规则）
    q2 = assistant_client.get(f"/api/sync/queue?oms_local_token={tok}")
    assert q2.status_code == 200
    # 旧 token 仍有效（TTL 内多握手并存），伪造 token 拒绝
    assert assistant_client.get("/api/sync/queue?oms_local_token=forged").status_code == 401


def test_enqueue_queue_flush_unpaired(assistant_client):
    tok = _token(assistant_client)
    headers = {"X-OMS-Local-Token": tok}
    r = assistant_client.post(
        "/api/local/sync/enqueue", json={"task_id": "tsk_u1", "payload": {"formal": "定稿"}}, headers=headers
    )
    assert r.status_code == 200 and r.json()["status"] == "pending"
    q = assistant_client.get("/api/sync/queue", headers=headers).json()["queue"]
    assert len(q) == 1 and q[0]["task_id"] == "tsk_u1" and q[0]["status"] == "pending"
    f = assistant_client.post("/api/local/sync/flush", headers=headers).json()
    assert f == {"synced": 0, "failed": 0, "skipped_unpaired": 1}  # 未配对不崩、不丢队列
    st = assistant_client.get("/api/local/state", headers=headers).json()
    assert st["paired"] is False


# ---------------------------------------------------------------------------
# 真实 e2e：企业实例（uvicorn 独立线程端口）× 助手引擎（进程内直调）
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def live_instance(tmp_path, monkeypatch):
    """起真实企业实例 HTTP 服务；返回 (base_url, store, member_uid, pairing_code)。"""
    root = tmp_path / "ENTERPRISE_DATA"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    enterprise_api.reset_store_cache()
    store = EnterpriseStore(DataRoot(root=root))
    migrate(store.conn)
    now = "2026-10-29T00:00:00+00:00"
    with store.conn:
        store.conn.execute(
            "INSERT INTO users(user_id, login_account, display_name, password_hash, role, status, created_at, updated_at)"
            " VALUES ('usr_a','adminacct','admin',?,'admin','active',?,?)",
            (hash_password("Admin-Pw-0001"), now, now),
        )
    uid, invite = store.create_user(actor_user_id="usr_a", display_name="员工", login_account="emp1")
    store.activate_invite(invite_code=invite, password="Emp-Pw-00001")
    pairing_code = store.create_pairing(actor_user_id=uid)

    app = FastAPI()
    enterprise_api.register_enterprise_routes(app)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        assert time.time() < deadline, "企业实例启动超时"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", store, uid
    server.should_exit = True
    thread.join(timeout=5)
    enterprise_api.reset_store_cache()


def test_local_storage_and_migrate(assistant_client, tmp_path):
    tok = _token(assistant_client)
    headers = {"X-OMS-Local-Token": tok}
    st = assistant_client.get("/api/local/storage", headers=headers)
    assert st.status_code == 200
    body = st.json()
    assert body["exists"] is True and body["writable"] is True
    assert {"data_dir", "total_bytes", "disk_free_bytes", "tasks_files"} <= set(body)
    # 未配对队列=200 空数组（v1.1 口径确认：前端两态兼容成立，本地面不设 409 语义）
    assert assistant_client.get("/api/sync/queue", headers=headers).json() == {"queue": []}

    # 迁移：源=当前 assistant 根（造点文件）；目标嵌套/同目录拒绝
    root = assistant_client.get("/api/local/storage", headers=headers).json()["data_dir"]
    (Path(root) / "recordings").mkdir(exist_ok=True)
    (Path(root) / "recordings" / "a.wav").write_bytes(b"12345")
    nested = str(Path(root) / "sub")
    assert assistant_client.post(
        "/api/local/storage/migrate", json={"target_dir": nested}, headers=headers
    ).status_code == 422
    assert assistant_client.post(
        "/api/local/storage/migrate", json={"target_dir": root}, headers=headers
    ).status_code == 422

    target = str(tmp_path / "NEW_DIR")
    r = assistant_client.post("/api/local/storage/migrate", json={"target_dir": target}, headers=headers)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["copied"] >= 1 and rep["source_retained"] is True
    assert (Path(target) / "recordings" / "a.wav").read_bytes() == b"12345"
    assert (Path(root) / "recordings" / "a.wav").exists()  # 保留源
    rep2 = assistant_client.post(
        "/api/local/storage/migrate", json={"target_dir": target}, headers=headers
    ).json()
    assert rep2["copied"] == 0 and rep2["skipped_identical"] >= 1  # 幂等重跑


def test_e2e_assistant_sync_to_instance(tmp_path, live_instance):
    base_url, store, member_uid = live_instance
    plane = AssistantPlane(DataRoot(root=tmp_path / "ASSISTANT_DATA"))
    # 1. 配对注册（真实 HTTP：device-activate）——先验错码路径
    with pytest.raises(ValueError):
        plane.register(server_url=base_url, pairing_code="bad-code")
    assert plane.paired is False

    reg = plane.register(server_url=base_url, pairing_code=_live_pairing(store, member_uid))
    assert reg["paired"] is True
    assert plane.state_path.exists() and plane.state_path.stat().st_mode & 0o077 == 0  # 0600 凭据保护

    # 2. 入队 → 3. flush 推送
    payload = {
        "meta": {"title": "e2e 会议", "meeting_time": "2026-10-29T10:00:00+00:00", "participants_text": "员工", "source": "client"},
        "formal": "员工: 这是经助手通道同步上来的定稿文本。",
        "summary": "e2e 纪要",
        "decisions": [],
        "notes": None,
        "insights_html": None,
    }
    plane.enqueue(task_id="tsk_e2e", payload=payload)
    q0 = plane.queue_view()
    assert q0[0]["status"] == "pending"
    counters = plane.flush_once()
    assert counters == {"synced": 1, "failed": 0, "skipped_unpaired": 0}
    assert plane.queue_view()[0]["status"] == "synced"

    # 4. 实例入库 + Web 会话读取（目标态"本地助手连接同步+Web 查看"最小闭环）
    task = store.get_task(actor_user_id=member_uid, task_id="tsk_e2e")
    assert task["formal"].startswith("员工: 这是经助手通道")
    assert task["visibility"] == "personal"
    client_nx = httpx.Client(trust_env=False, timeout=10)
    r = client_nx.post(f"{base_url}/api/v1/auth/login", json={"account": "emp1", "password": "Emp-Pw-00001"})
    assert r.status_code == 200
    lst = client_nx.get(f"{base_url}/api/v1/context/tasks", cookies=r.cookies).json()["tasks"]
    client_nx.close()
    assert [t["task_id"] for t in lst] == ["tsk_e2e"]

    # 5. 网络故障路径：实例不可达 → error+退避重试字段（断网安全）
    plane.enqueue(task_id="tsk_off", payload=payload)
    bad_url_backup = plane.state()["server_url"]
    plane._save_state({**plane.state(), "server_url": "http://127.0.0.1:1"})
    counters2 = plane.flush_once()
    assert counters2["failed"] >= 1
    off = [x for x in plane.queue_view() if x["task_id"] == "tsk_off"][0]
    assert off["status"] == "error" and off["retry_after"] and off["last_error"].startswith("network:")
    plane._save_state({**plane.state(), "server_url": bad_url_backup})
    # 退避窗口内不重试（断网不空转）：立即 flush 应跳过
    assert plane.flush_once()["synced"] == 0
    # 模拟退避到期后收敛（重放安全：同 mutation 幂等）
    off_item = plane._read_item([x for x in plane.queue_view() if x["task_id"] == "tsk_off"][0]["mutation_id"])
    plane._update_item(off_item["mutation_id"], retry_after="2000-01-01T00:00:00+00:00")
    assert plane.flush_once()["synced"] >= 1


def _live_pairing(store: EnterpriseStore, member_uid: str) -> str:
    return store.create_pairing(actor_user_id=member_uid)
