"""EP1-BE 0002 迁移演练：缺口A expand-contract 升级回归（QA TB3）+ 失败回滚演练。

契约基线：DESIGN-P1-SPACES-BACKEND-DRAFT.md v1.0 §1/§6/§8。
纪律点：
- 迁移前后个人词表内容 diff=∅（QA 指定首批升级回归断言）；
- runner 单事务失败回滚不切流——本文件是 DevOps 升级三件套的首个正式用例证据。
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.db.config import DataRoot
from app.db.dao import EnterpriseStore
from app.db.database import MIGRATIONS_DIR, connect, migrate
from app.db.security import hash_password

P0_SQL = "0001_enterprise_p0.sql"
P1_SQL = "0002_enterprise_p1.sql"


def _p0_only_dir(tmp_path):
    d = tmp_path / "migrations_p0"
    d.mkdir()
    shutil.copy(MIGRATIONS_DIR / P0_SQL, d / P0_SQL)
    return d


def _boot_store(tmp_path, migrations_dir) -> EnterpriseStore:
    dr = DataRoot(root=tmp_path / "DATA_ROOT")
    s = EnterpriseStore(dr)
    migrate(s.conn, migrations_dir)
    now = "2026-10-29T00:00:00+00:00"
    with s.conn:
        s.conn.execute(
            "INSERT INTO users(user_id, login_account, phone, display_name, password_hash, role, status, created_at, updated_at)"
            " VALUES ('usr_admin','13373013103','13373013103','超级管理员',?,'admin','active',?,?)",
            (hash_password("Bootstrap-Adm!n-Pw"), now, now),
        )
        s.conn.execute(
            "INSERT INTO users(user_id, login_account, display_name, role, status, created_at, updated_at)"
            " VALUES ('usr_mem','mem1','成员一','member','active',?,?)",
            (now, now),
        )
    return s


# ---------------- 缺口A：P0→P1 升级后个人词表 diff=∅ ----------------


def test_upgrade_personal_assets_diff_empty(tmp_path):
    s = _boot_store(tmp_path, _p0_only_dir(tmp_path))
    payloads = {
        "hotwords": {"words": ["词元A", "词元 B", "ünïcode 检查"]},
        "speaker_aliases": {"aliases": {"spk_1": "张三"}, "empty_ok": 1},
        "decision_statuses": {"statuses": ["进行中", "已完成"]},
    }
    for kind, p in payloads.items():
        s.apply_asset(actor_user_id="usr_mem", kind=kind, client_mutation_id=f"mut-{kind}", base_rev=0, payload=p)
    before_rows = [dict(r) for r in s.conn.execute("SELECT * FROM ctx_assets ORDER BY asset_id")]
    before_payloads = {kind: s.get_asset(actor_user_id="usr_mem", kind=kind)["payload"] for kind in payloads}
    before_blobs = {r["blob_path"]: Path(r["blob_path"]) for r in before_rows}
    before_bytes = {p: path.read_bytes() for p, path in before_blobs.items()}

    applied = migrate(s.conn)  # 真迁移目录 → 应用 0002（含 expand-contract 重建）
    assert applied == ["0002_enterprise_p1"]

    after_rows = [dict(r) for r in s.conn.execute("SELECT * FROM ctx_assets ORDER BY asset_id")]
    # 逐字段 diff=∅：列集合只增不减（team_id 为新增），存量字段值逐一相等
    for b, a in zip(before_rows, after_rows):
        assert len(after_rows) == len(before_rows)
        for key in b:
            assert a[key] == b[key], f"迁移改变了存量字段 {key}"
        assert a["team_id"] is None and a["owner_user_id"] is not None
    after_payloads = {kind: s.get_asset(actor_user_id="usr_mem", kind=kind)["payload"] for kind in payloads}
    assert after_payloads == before_payloads
    after_bytes = {r["blob_path"]: Path(r["blob_path"]) for r in after_rows}
    assert set(after_bytes) == set(before_bytes)
    for p, path in after_bytes.items():
        assert path.read_bytes() == before_bytes[p], "blob 文件字节发生变化"

    # 升级后同一 owner+kind 仍可正常续写（部分唯一索引承接旧 UNIQUE 语义）
    s.apply_asset(
        actor_user_id="usr_mem", kind="hotwords", client_mutation_id="mut-hw2", base_rev=1,
        payload={"words": ["追加"]}
    )
    assert s.asset_current_rev("usr_mem", "hotwords") == 2


# ---------------- 缺口A：团队拥有资产在重建表上可表达（P0 旧约束不可表达的点） ----------------


def test_team_owned_asset_expressible_after_rebuild(tmp_path):
    s = _boot_store(tmp_path, MIGRATIONS_DIR)
    now = "2026-11-02T00:00:00+00:00"
    with s.conn:
        s.conn.execute(
            "INSERT INTO teams(team_id, name, created_by, status, created_at) VALUES ('t1','团队一','usr_admin','active',?)",
            (now,),
        )
        # 同一用户建两团队的词表——旧 UNIQUE(owner_user_id,kind) 会撞，重建后按团队归属不撞
        s.conn.execute(
            "INSERT INTO teams(team_id, name, created_by, status, created_at) VALUES ('t2','团队二','usr_admin','active',?)",
            (now,),
        )
        for tid in ("t1", "t2"):
            s.conn.execute(
                "INSERT INTO ctx_assets(asset_id, team_id, kind, scope, current_rev, blob_path, updated_at)"
                " VALUES (?, ?, 'hotwords', 'team', 0, ?, ?)",
                (f"ast_{tid}", tid, f"/dev/{tid}", now),
            )
        # 双归属恰一非空 CHECK 必须拒绝"user+team 同时填"
        with pytest.raises(sqlite3.IntegrityError):
            s.conn.execute(
                "INSERT INTO ctx_assets(asset_id, owner_user_id, team_id, kind, blob_path, updated_at)"
                " VALUES ('bad','usr_mem','t1','hotwords','/dev/bad',?)", (now,)
            )
        # 同团队同 kind 唯一（部分索引 ux_assets_team）
        with pytest.raises(sqlite3.IntegrityError):
            s.conn.execute(
                "INSERT INTO ctx_assets(asset_id, team_id, kind, blob_path, updated_at)"
                " VALUES ('bad2','t1','hotwords','/dev/bad2',?)", (now,)
            )


# ---------------- K1 枚举契约面：CHECK 十二值逐字 + 审批态/解散值拒绝 + 闭环字段 ----------------


def test_audit_enum_matches_contract_k1(tmp_path):
    s = _boot_store(tmp_path, MIGRATIONS_DIR)
    now = "2026-11-02T00:00:00+00:00"
    with s.conn:
        s.conn.execute("INSERT INTO teams(team_id,name,created_by,created_at) VALUES ('t1','A','usr_admin',?)", (now,))
    contract_values = [
        "publish", "edit", "withdraw", "decision_publish", "decision_withdraw",
        "decision_delete", "decision_restore",
        "member_add", "member_role_change", "member_remove", "role_transfer", "team_archive",
    ]
    ddl = (MIGRATIONS_DIR / P1_SQL).read_text(encoding="utf-8")
    for v in contract_values:
        assert f"'{v}'" in ddl, f"0002 CHECK 缺契约值 {v}"
        s.conn.execute(
            "INSERT INTO team_edit_audit(audit_id, team_id, actor_user_id, action, ts) VALUES (?,?,?,?,?)",
            (f"aud_{v}", "t1", "usr_admin", v, now),
        )
    n = s.conn.execute("SELECT COUNT(*) c FROM team_edit_audit").fetchone()["c"]
    assert n == len(contract_values)
    # 红线反断言：审批/待确认态与"解散"类值必须被 CHECK 拒绝
    for bad in ("pending_approval", "approval_required", "dissolve", "delete", "restore", "archive"):
        with pytest.raises(sqlite3.IntegrityError):
            s.conn.execute(
                "INSERT INTO team_edit_audit(audit_id, team_id, actor_user_id, action, ts) VALUES (?,?,?,?,?)",
                (f"bad_{bad}", "t1", "usr_admin", bad, now),
            )
    # 闭环承载：decision_delete 必须带 target_ref+pre_delete_rev 行（列存在且可空由应用层强制非空）
    cols = {r["name"] for r in s.conn.execute("PRAGMA table_info(team_edit_audit)")}
    assert {"target_ref", "pre_delete_rev"} <= cols


# ---------------- 必含项①承接列 & 语义修正 B 回填 ----------------


def test_revisions_actor_backfill_and_p1_columns(tmp_path):
    s = _boot_store(tmp_path, _p0_only_dir(tmp_path))
    # 以 P0 老代码形态裸写存量行（不填 actor 列）——生产态 DAO 恒在迁移后运行，存量行只能来自 P0
    now = "2026-10-29T00:00:00+00:00"
    with s.conn:
        s.conn.execute(
            "INSERT INTO ctx_tasks(task_id, owner_user_id, title, source, status, current_rev, updated_at)"
            " VALUES ('tsk_x','usr_mem','T','client','active',1,?)", (now,)
        )
        s.conn.execute(
            "INSERT INTO ctx_revisions(rev_id, task_id, owner_user_id, rev, client_mutation_id,"
            " blob_path, content_hash, created_at) VALUES ('rvw_x','tsk_x','usr_mem',1,'mut-1','/dev/x','h',?)",
            (now,),
        )
    migrate(s.conn)
    row = s.conn.execute("SELECT owner_user_id, actor_user_id FROM ctx_revisions").fetchone()
    assert row["actor_user_id"] == row["owner_user_id"]  # 旧行回填 owner=actor
    task_cols = {r["name"] for r in s.conn.execute("PRAGMA table_info(ctx_tasks)")}
    assert {"team_id", "source_task_id"} <= task_cols


# ---------------- 升级三件套之"失败回滚不切流"演练（DevOps 运维基线证据） ----------------


def test_failed_migration_rolls_back_fully(tmp_path):
    d = _p0_only_dir(tmp_path)
    shutil.copy(MIGRATIONS_DIR / P1_SQL, d / P1_SQL)
    s = _boot_store(tmp_path, d)
    s.apply_asset(actor_user_id="usr_mem", kind="hotwords", client_mutation_id="mut-h", base_rev=0, payload={"w": [1]})
    # 注入一个"前半成功、后半失败"的 0003——模拟迁移中途炸裂
    (d / "0003_broken.sql").write_text(
        "CREATE TABLE inject_probe(x);\nINSERT INTO inject_probe VALUES (1);\nTHIS IS NOT SQL;\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="0003_broken"):
        migrate(s.conn, d)
    # 数据库保持上一版本可读：0002 效果仍在、0003 无任何残留、存量资产未被波及
    assert "inject_probe" not in {
        r["name"] for r in s.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    versions = {r["version"] for r in s.conn.execute("SELECT version FROM schema_version")}
    assert versions == {1, 2}
    assert s.asset_current_rev("usr_mem", "hotwords") == 1
    got = s.get_asset(actor_user_id="usr_mem", kind="hotwords")
    assert got["payload"] == {"w": [1]}
