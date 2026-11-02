"""EP0-BE 第一增量测试：DATA_ROOT/schema 迁移/账号域/快照幂等/越权/配对/CLI。

契约基线：P0-BACKEND-DESIGN-MULTIUSER-20261029.md v1.0。
"""
from __future__ import annotations

import sqlite3

import pytest

from app.db.config import DataRoot
from app.db.dao import (
    ActorRequiredError,
    EnterpriseStore,
    NotFoundError,
    PayloadNotAllowedError,
    StaleRevisionError,
)
from app.db.database import connect, migrate
from app.db.security import hash_password, verify_password


@pytest.fixture()
def store(tmp_path) -> EnterpriseStore:
    dr = DataRoot(root=tmp_path / "DATA_ROOT")
    s = EnterpriseStore(dr)
    applied = migrate(s.conn)
    assert applied == ["0001_enterprise_p0"]
    now = "2026-10-29T00:00:00+00:00"
    with s.conn:
        s.conn.execute(
            "INSERT INTO users(user_id, login_account, phone, display_name, password_hash, role, status, created_at, updated_at)"
            " VALUES ('usr_admin','13373013103','13373013103','超级管理员',?,'admin','active',?,?)",
            (hash_password("Bootstrap-Adm!n-Pw"), now, now),
        )
    return s


ADMIN = "usr_admin"


def make_member(store: EnterpriseStore, account: str) -> tuple[str, str]:
    user_id, code = store.create_user(
        actor_user_id=ADMIN, display_name=f"user-{account}", login_account=account
    )
    store.activate_invite(invite_code=code, password=f"Passw0rd-{account}")
    return user_id, f"Passw0rd-{account}"


# ---------------- 迁移 runner ----------------


def test_migrate_is_idempotent(store: EnterpriseStore):
    assert migrate(store.conn) == []  # 重复执行为 no-op
    versions = {r[0] for r in store.conn.execute("SELECT version FROM schema_version")}
    assert versions == {1}


def test_migrate_creates_wal_mode(tmp_path):
    s = EnterpriseStore(DataRoot(root=tmp_path / "r"))
    migrate(s.conn)
    assert s.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    s.close()


# ---------------- actor 强制（QA 越权框架结构断言） ----------------


def test_dao_requires_actor(store: EnterpriseStore):
    with pytest.raises(ActorRequiredError):
        store.list_tasks(actor_user_id="")
    with pytest.raises(ActorRequiredError):
        store.get_task(actor_user_id=None, task_id="tsk_x")  # type: ignore[arg-type]


# ---------------- 账号域：邀请码自助设密、无初始密码 ----------------


def test_invite_self_password_flow(store: EnterpriseStore):
    user_id, code = store.create_user(
        actor_user_id=ADMIN, display_name="员工甲", login_account="empA"
    )
    row = store.conn.execute("SELECT status, password_hash FROM users WHERE user_id=?", (user_id,)).fetchone()
    assert row["status"] == "pending" and row["password_hash"] is None  # 无初始密码下发
    assert store.verify_login(login_account="empA", password="anything") is None  # 未激活不可登录

    store.activate_invite(invite_code=code, password="Emp-A-Pw-001")
    assert store.verify_login(login_account="empA", password="Emp-A-Pw-001") == user_id
    assert store.verify_login(login_account="empA", password="wrong-pw-0000") is None
    # 邀请码单用：重复激活失败
    with pytest.raises(NotFoundError):
        store.activate_invite(invite_code=code, password="Emp-A-Pw-002")
    # 服务端只存 hash
    assert store.conn.execute("SELECT COUNT(*) c FROM invites WHERE code_hash=?", (code,)).fetchone()["c"] == 0


def test_non_admin_cannot_create_user(store: EnterpriseStore):
    member, _ = make_member(store, "empB")
    with pytest.raises(NotFoundError):
        store.create_user(actor_user_id=member, display_name="x", login_account="empX")


# ---------------- 快照域：幂等、串行 rev、白名单、越权 ----------------

PAYLOAD = {
    "meta": {"title": "周会", "meeting_time": "2026-10-29T09:00:00+00:00", "participants_text": "甲、乙", "source": "client"},
    "formal": "甲：定稿文本……",
    "summary": "纪要……",
    "decisions": [{"decision_id": "d1", "text": "选 A 方案", "status_id": "s1"}],
    "notes": "笔记",
    "insights_html": None,
}


def test_snapshot_flow(store: EnterpriseStore):
    a, _ = make_member(store, "empC")
    r1 = store.apply_snapshot(actor_user_id=a, task_id="tsk_1", client_mutation_id="mut-1", base_rev=0, payload=PAYLOAD)
    assert r1.server_rev == 1 and not r1.idempotent_replay
    # 同 mutation 重放 = 幂等返回首次结果
    replay = store.apply_snapshot(actor_user_id=a, task_id="tsk_1", client_mutation_id="mut-1", base_rev=0, payload=PAYLOAD)
    assert replay.idempotent_replay and replay.server_rev == 1
    # 乱序：base_rev 过期 → StaleRevisionError 携带 current_rev（契约 409）
    # mut-2 以 base_rev=0 提交，但 task 已由 mut-1 推进到 rev=1
    with pytest.raises(StaleRevisionError) as exc:
        store.apply_snapshot(actor_user_id=a, task_id="tsk_1", client_mutation_id="mut-2", base_rev=0, payload=PAYLOAD)
    assert exc.value.current_rev == 1
    # mut-2 以正确的 base_rev=1 重试成功
    r2 = store.apply_snapshot(actor_user_id=a, task_id="tsk_1", client_mutation_id="mut-2", base_rev=1, payload=PAYLOAD)
    assert r2.server_rev == 2
    task = store.get_task(actor_user_id=a, task_id="tsk_1")
    assert task["visibility"] == "personal" and task["sync_status"] == "synced"  # 插单①②
    # blob 落盘且不可被他人路径绕过（行级归属校验）
    b, _ = make_member(store, "empD")
    with pytest.raises(NotFoundError):
        store.get_task(actor_user_id=b, task_id="tsk_1")  # B 越权读 A → 统一 NotFound（防枚举）
    with pytest.raises(NotFoundError):
        store.apply_snapshot(actor_user_id=b, task_id="tsk_1", client_mutation_id="mut-9", base_rev=2, payload=PAYLOAD)


# ---------------- 迁移存量的旧 task_id 引用 ----------------


def test_legacy_task_reference_resolves(store: EnterpriseStore):
    """旧本机 task_id（UUID）作为引用可读/可写/可删，且不产生第二份副本。"""
    a, _ = make_member(store, "empLegacy")
    legacy = "8ad489d1-d893-4e59-a020-d03d6736190e"
    store.apply_snapshot(
        actor_user_id=a,
        task_id="tsk_legacy",
        client_mutation_id="mut-L0",
        base_rev=0,
        payload=dict(PAYLOAD, meta={**PAYLOAD["meta"], "legacy_id": legacy}),
    )
    got = store.get_task(actor_user_id=a, task_id=legacy)  # Web 首页/书签持旧键
    assert got["task_id"] == "tsk_legacy" and got["meta"]["legacy_id"] == legacy
    # 助手 outbox 按旧 task_id 重推 → 命中同一行（契约 §1.1 legacy_id 映射的意义所在）
    store.apply_snapshot(actor_user_id=a, task_id=legacy, client_mutation_id="mut-L1", base_rev=1, payload=PAYLOAD)
    assert store.task_current_rev(a, legacy) == 2
    assert store.task_current_rev(a, "tsk_legacy") == 2
    assert store.conn.execute("SELECT COUNT(*) c FROM ctx_tasks").fetchone()["c"] == 1
    # 越权与不存在同码：他人的 legacy_id 解析不出，落回统一 NotFound
    b, _ = make_member(store, "empLegacy2")
    with pytest.raises(NotFoundError):
        store.get_task(actor_user_id=b, task_id=legacy)
    # 按旧引用删除同样命中（软删后旧引用不再可解）
    store.delete_task(actor_user_id=a, task_id=legacy)
    with pytest.raises(NotFoundError):
        store.get_task(actor_user_id=a, task_id=legacy)


def test_snapshot_egress_whitelist(store: EnterpriseStore):
    a, _ = make_member(store, "empE")
    bad = dict(PAYLOAD, audio_base64="...")
    with pytest.raises(PayloadNotAllowedError):
        store.apply_snapshot(actor_user_id=a, task_id="tsk_w", client_mutation_id="mut-w1", base_rev=0, payload=bad)
    bad_meta = dict(PAYLOAD, meta={**PAYLOAD["meta"], "voiceprint_embedding": [0.1]})
    with pytest.raises(PayloadNotAllowedError):
        store.apply_snapshot(actor_user_id=a, task_id="tsk_w", client_mutation_id="mut-w2", base_rev=0, payload=bad_meta)


# ---------------- 配对 token 与停用级联 ----------------


def test_pairing_and_disable_cascade(store: EnterpriseStore):
    a, _ = make_member(store, "empF")
    store.apply_snapshot(actor_user_id=a, task_id="tsk_keep", client_mutation_id="mut-keep", base_rev=0, payload=PAYLOAD)
    code = store.create_pairing(actor_user_id=a)
    device_id, token, _uid = store.redeem_pairing(pairing_code=code, device_name="录音助手-甲")
    assert store.verify_device_token(token) == a
    with pytest.raises(NotFoundError):  # 配对码一次性
        store.redeem_pairing(pairing_code=code, device_name="dup")

    store.disable_user(actor_user_id=ADMIN, user_id=a)  # QA-Q3：停用即刻收回登录与同步权
    assert store.verify_login(login_account="empF", password="Passw0rd-empF") is None
    assert store.verify_device_token(token) is None
    # 数据保留归属企业（QA-Q3：不自动到期删除，仅管理台整包删除才物理删）
    assert store.conn.execute(
        "SELECT COUNT(*) c FROM ctx_tasks WHERE owner_user_id=? AND status='active'", (a,)
    ).fetchone()["c"] == 1
    n = store.bulk_delete_user_data(actor_user_id=ADMIN, user_id=a)  # 整包删除=显式管理员动作
    assert n == 1
    assert store.conn.execute("SELECT COUNT(*) c FROM ctx_revisions WHERE owner_user_id=?", (a,)).fetchone()["c"] == 0


def test_revoke_device_single(store: EnterpriseStore):
    a, _ = make_member(store, "empG")
    code = store.create_pairing(actor_user_id=a)
    device_id, token, _uid = store.redeem_pairing(pairing_code=code, device_name="助手")
    store.revoke_device(actor_user_id=a, device_id=device_id)
    assert store.verify_device_token(token) is None
    b, _ = make_member(store, "empH")
    with pytest.raises(NotFoundError):  # 他人设备不可见（防枚举）
        store.revoke_device(actor_user_id=b, device_id=device_id)


def test_reset_password_local_admin(store: EnterpriseStore):
    store.conn.execute("INSERT INTO sessions(session_id, user_id, jwt_jti, expires_at) VALUES ('ss1','usr_admin','jti1','2027-01-01T00:00:00+00:00')")
    store.conn.commit()
    code = store.reset_password_local_admin(login_account="13373013103")
    assert store.verify_login(login_account="13373013103", password="Bootstrap-Adm!n-Pw") is None  # 旧凭据作废
    assert store.conn.execute("SELECT revoked_at FROM sessions WHERE session_id='ss1'").fetchone()["revoked_at"]
    store.activate_invite(invite_code=code, password="New-Admin-Pw-2")
    assert store.verify_login(login_account="13373013103", password="New-Admin-Pw-2") == ADMIN


# ---------------- 回收站软删 30 天（PRD 定稿口径） ----------------


def test_soft_delete_and_purge(store: EnterpriseStore):
    a, _ = make_member(store, "empI")
    store.apply_snapshot(actor_user_id=a, task_id="tsk_d", client_mutation_id="mut-d1", base_rev=0, payload=PAYLOAD)
    store.delete_task(actor_user_id=a, task_id="tsk_d")
    with pytest.raises(NotFoundError):
        store.get_task(actor_user_id=a, task_id="tsk_d")
    assert store.purge_expired_trash(actor_user_id=a) == 0  # 未满 30 天不动
    assert store.purge_expired_trash(actor_user_id=a, now_iso="2026-12-31T00:00:00+00:00") == 1
    assert store.conn.execute("SELECT COUNT(*) c FROM ctx_revisions WHERE task_id='tsk_d'").fetchone()["c"] == 0


# ---------------- CLI：backup-snapshot 一致性 ----------------


def test_cli_backup_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("OMS_DATA_ROOT", str(tmp_path / "RL"))
    from app.db.__main__ import main
    from app.db.config import resolve_data_root

    dr = resolve_data_root()
    s = EnterpriseStore(dr)
    migrate(s.conn)
    dest = tmp_path / "backup.db"
    assert main(["backup-snapshot", str(dest)]) == 0
    conn = sqlite3.connect(dest)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
    s.close()


def test_password_hashing_roundtrip():
    h = hash_password("S3cret-Test-Pw")
    assert h.startswith("pbkdf2-sha256$")
    assert verify_password("S3cret-Test-Pw", h)
    assert not verify_password("other", h)
    assert not verify_password("x", None)
