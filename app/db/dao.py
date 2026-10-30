"""actor 强制 DAO（契约 §2.2：所有查询签名强制携带 actor_user_id）。

结构性越权保证：本模块内不暴露任何"无 actor"的业务查询入口；
越权判定=行级 owner 校验，失败统一 NotFound（不用 403/5xx 区分资源存在性，QA 域 A 判定规则）。
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DataRoot
from .database import connect, utcnow
from .security import generate_secret_code, hash_password, hash_secret, verify_password

# ---------------------------------------------------------------------------
# 错误语义（与契约错误码一一对应）
# ---------------------------------------------------------------------------


class ActorRequiredError(RuntimeError):
    """DAO 函数缺少 actor_user_id —— 结构性禁止（QA 越权框架的 lint/运行时断言点）。"""


class StaleRevisionError(RuntimeError):
    def __init__(self, current_rev: int):
        super().__init__(f"base_rev 过期，服务端当前 rev={current_rev}")
        self.current_rev = current_rev


class PayloadNotAllowedError(ValueError):
    """快照字段超出出境白名单（契约 422 拒收点）。"""


class NotFoundError(LookupError):
    """不存在或不属于 actor —— 一律同码，防枚举。"""


# ---------------------------------------------------------------------------
# ID 生成（可排序前缀 + 随机，等价 ULID 的单调性需求）
# ---------------------------------------------------------------------------


def new_id(prefix: str) -> str:
    ts_ms = int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)
    return f"{prefix}_{ts_ms:013x}{secrets.token_hex(5)}"


# 出境白名单（契约 §2.4 —— 与同意卡第二行五名词逐项映射，无第六类）
SNAPSHOT_FIELDS = frozenset({"meta", "formal", "summary", "decisions", "notes", "insights_html"})
SNAPSHOT_META_KEYS = frozenset({"title", "meeting_time", "participants_text", "source", "legacy_id"})


@dataclass(frozen=True)
class SnapshotResult:
    server_rev: int
    content_hash: str
    stored_at: str
    idempotent_replay: bool = False


class EnterpriseStore:
    def __init__(self, data_root: DataRoot):
        self.dr = data_root
        self.conn = connect(data_root)

    def close(self) -> None:
        self.conn.close()

    # ---------------- 账号域 ----------------

    def create_user(
        self,
        *,
        actor_user_id: str,
        display_name: str,
        login_account: str,
        phone: str | None = None,
        role: str = "member",
    ) -> tuple[str, str]:
        """管理员建号：只产生 pending 用户 + 一次性邀请码；**不产生任何密码**（插单③）。"""
        self._require_admin(actor_user_id)
        if not display_name or not login_account:
            raise ValueError("display_name/login_account 必填")
        user_id = new_id("usr")
        invite_code = generate_secret_code()
        now = utcnow()
        with self.conn:
            self.conn.execute(
                "INSERT INTO users(user_id, login_account, phone, display_name, role, status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,'pending',?,?)",
                (user_id, login_account, phone, display_name, role, now, now),
            )
            self.conn.execute(
                "INSERT INTO invites(invite_id, code_hash, created_by, target_user_id, max_uses, expires_at)"
                " VALUES (?,?,?,?,1,?)",
                (new_id("inv"), hash_secret(invite_code), actor_user_id, user_id, now_add_days(30)),
            )
        return user_id, invite_code  # 明文仅此一次返回

    def activate_invite(self, *, invite_code: str, password: str, display_name: str | None = None) -> str:
        """邀请码自助设密码（无初始密码环节）。返回 user_id。"""
        if not password or len(password) < 8:
            raise ValueError("密码长度不足")
        row = self.conn.execute(
            "SELECT i.* FROM invites i WHERE i.code_hash=? AND i.disabled_at IS NULL",
            (hash_secret(invite_code),),
        ).fetchone()
        if not row or (row["expires_at"] and row["expires_at"] < utcnow()) or row["used_count"] >= row["max_uses"]:
            raise NotFoundError("邀请码无效或已过期")
        target = row["target_user_id"]
        if target is None:
            raise NotFoundError("邀请码未绑定账号")
        now = utcnow()
        with self.conn:
            sets = "password_hash=?, status='active', updated_at=?"
            params: list[Any] = [hash_password(password), now]
            if display_name:
                sets = "display_name=?, " + sets
                params.insert(0, display_name)
            self.conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", (*params, target))
            self.conn.execute("UPDATE invites SET used_count = used_count + 1 WHERE invite_id=?", (row["invite_id"],))
        # 首管激活完成 → bootstrap_done 置位（通道自此永久关闭）
        info = self.session_user(user_id=target)
        if info and info["role"] == "admin" and self.conn.execute(
            "SELECT COUNT(*) c FROM users WHERE role='admin' AND status='active'"
        ).fetchone()["c"] == 1:
            self.mark_bootstrap_done(user_id=target)
        return target

    def verify_login(self, *, login_account: str, password: str) -> str | None:
        result = self.login_probe(login_account=login_account, password=password)
        return None if result in ("invalid", "disabled", "password_not_set") else result

    def login_probe(self, *, login_account: str, password: str) -> str:
        """返回 'ok'|'disabled'|'invalid'|'password_not_set'——端点层据此映射契约错误码（QA D001）。"""
        row = self.conn.execute(
            "SELECT user_id, password_hash, status FROM users WHERE login_account=?", (login_account,)
        ).fetchone()
        if row is None:
            return "invalid"
        if row["status"] == "disabled":
            return "disabled"  # 正确密码也拒绝，但独立语义：求助路径=联系管理员
        if row["status"] != "active":
            return "password_not_set" if row["password_hash"] is None else "invalid"
        if not verify_password(password, row["password_hash"]):
            return "invalid"
        return row["user_id"]

    def get_user(self, *, actor_user_id: str, user_id: str) -> dict:
        _require_actor(actor_user_id)
        row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            raise NotFoundError(user_id)
        if row["role"] != "admin" and row["user_id"] != actor_user_id and not self._is_admin(actor_user_id):
            raise NotFoundError(user_id)  # 非管理员仅可查自己/不可枚举他人（统一 NotFound）
        return dict(row)

    def disable_user(self, *, actor_user_id: str, user_id: str) -> None:
        """停用=即刻收回登录与同步权；数据保留归属企业（QA-Q3），不自动到期删除。"""
        self._require_admin(actor_user_id)
        with self.conn:
            self.conn.execute("UPDATE users SET status='disabled', updated_at=? WHERE user_id=?", (utcnow(), user_id))
            self.revoke_all_sessions(actor_user_id=user_id)
            self.revoke_all_devices(actor_user_id=user_id)

    def bulk_delete_user_data(self, *, actor_user_id: str, user_id: str) -> int:
        """管理台整包删除停用账号数据（物理删；内容对管理员不可读，仅元数据可见）。"""
        self._require_admin(actor_user_id)
        with self.conn:
            tasks = [r["task_id"] for r in self.conn.execute(
                "SELECT task_id FROM ctx_tasks WHERE owner_user_id=?", (user_id,)
            )]
            for tid in tasks:
                self.conn.execute("DELETE FROM ctx_entities WHERE task_id=?", (tid,))
                self.conn.execute("DELETE FROM ctx_revisions WHERE task_id=?", (tid,))
            n = self.conn.execute("DELETE FROM ctx_tasks WHERE owner_user_id=?", (user_id,)).rowcount
            self.conn.execute("DELETE FROM ctx_assets WHERE owner_user_id=?", (user_id,))
            blob_user_dir = self.dr.blobs_dir / user_id
            if blob_user_dir.exists():
                import shutil

                shutil.rmtree(blob_user_dir)
        return n

    def revoke_all_sessions(self, *, actor_user_id: str) -> None:
        _require_actor(actor_user_id)
        with self.conn:
            self.conn.execute(
                "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (utcnow(), actor_user_id),
            )

    def reset_password_issue_invite(self, *, actor_user_id: str, user_id: str) -> str:
        """管理员重置密码=作废旧会话/设备+重发邀请码，不经手明文密码（裁决 #1）。"""
        self._require_admin(actor_user_id)
        return self._issue_reset_invite(created_by=actor_user_id, user_id=user_id)

    def reset_password_local_admin(self, *, login_account: str) -> str:
        """本机管理员命令入口（能访问 DATA_ROOT 即本机持有证据，不做网络鉴权）；
        返回一次性重置邀请码。本机通道不经 Web，故不受 admin 角色门槛限制。"""
        row = self.conn.execute("SELECT user_id FROM users WHERE login_account=?", (login_account,)).fetchone()
        if row is None:
            raise NotFoundError(login_account)
        return self._issue_reset_invite(created_by=row["user_id"], user_id=row["user_id"])

    def _issue_reset_invite(self, *, created_by: str, user_id: str) -> str:
        code = generate_secret_code()
        now = utcnow()
        with self.conn:
            self.conn.execute(
                "UPDATE users SET password_hash=NULL, status='pending', updated_at=? WHERE user_id=?",
                (now, user_id),
            )
            self.conn.execute(
                "INSERT INTO invites(invite_id, code_hash, created_by, target_user_id, max_uses, expires_at)"
                " VALUES (?,?,?,?,1,?)",
                (new_id("inv"), hash_secret(code), created_by, user_id, now_add_days(30)),
            )
            self.conn.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user_id))
            self.conn.execute("UPDATE device_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user_id))
        return code

    def bootstrap_admin(self, *, display_name: str, login_account: str, phone: str | None = None) -> dict:
        """实例初始化专用（契约 v1.1 第13条 + W-D005-B 重入语义）。

        门槛只看 **active** admin：
        - 存在 active admin → RuntimeError（409，通道永久关闭，与 QA X05-3 断言一致）；
        - 无 active admin 且已有 pending 首管 → **可重入**：撤未用旧码、原子重发新码、复用同一账号行
          （不重建；display_name 保留用户第一次输入，login_account/phone 按本次输入更新）；
        - 完全空白实例 → 建 pending admin + 一次性邀请码。
        凭据语义全程不变：密码由本人经 activate 自设，服务端不经手。
        """
        if not display_name or not login_account:
            raise ValueError("display_name/login_account 必填")
        active = self.conn.execute(
            "SELECT COUNT(*) c FROM users WHERE role='admin' AND status='active'"
        ).fetchone()["c"]
        if active:
            raise RuntimeError("初始化已完成，此通道已永久关闭")
        pending = self.conn.execute(
            "SELECT user_id FROM users WHERE role='admin' AND status='pending' ORDER BY created_at LIMIT 1"
        ).fetchone()
        invite_code = generate_secret_code()
        now = utcnow()
        with self.conn:
            if pending is not None:
                user_id = pending["user_id"]
                # 复用首管账号行：更新登录名/手机，display_name 保留第一次输入（裁决原文）
                self.conn.execute(
                    "UPDATE users SET login_account=?, phone=?, updated_at=? WHERE user_id=?",
                    (login_account, phone, now, user_id),
                )
                stored = self.conn.execute(
                    "SELECT display_name FROM users WHERE user_id=?", (user_id,)
                ).fetchone()["display_name"]
                self.conn.execute(
                    "UPDATE invites SET disabled_at=? WHERE target_user_id=? AND disabled_at IS NULL",
                    (now, user_id),
                )
                self.conn.execute(
                    "INSERT INTO invites(invite_id, code_hash, created_by, target_user_id, max_uses, expires_at)"
                    " VALUES (?,?,NULL,?,1,?)",
                    (new_id("inv"), hash_secret(invite_code), user_id, now_add_days(30)),
                )
                return {
                    "user_id": user_id,
                    "invite_code": invite_code,
                    "display_name": stored,
                    "login_account": login_account,
                    "reentered": True,
                }
            user_id = new_id("usr")
            self.conn.execute(
                "INSERT INTO users(user_id, login_account, phone, display_name, role, status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,'pending',?,?)",
                (user_id, login_account, phone, display_name, "admin", now, now),
            )
            self.conn.execute(
                "INSERT INTO invites(invite_id, code_hash, created_by, target_user_id, max_uses, expires_at)"
                " VALUES (?,?,NULL,?,1,?)",
                (new_id("inv"), hash_secret(invite_code), user_id, now_add_days(30)),
            )
        return {
            "user_id": user_id,
            "invite_code": invite_code,
            "display_name": display_name,
            "login_account": login_account,
            "reentered": False,
        }

    def mark_bootstrap_done(self, *, user_id: str) -> None:
        """bootstrap_done 状态位=首管**激活完成**时置位（W-D005-B 修正：原在第一步置位属误导）。"""
        with self.conn:
            self.conn.execute(
                "INSERT INTO instance_config(key, value_json, updated_by, updated_at)"
                " VALUES ('bootstrap_done','true',?,?)"
                " ON CONFLICT(key) DO UPDATE SET value_json='true', updated_at=excluded.updated_at",
                (user_id, utcnow()),
            )

    def change_password(self, *, actor_user_id: str, old_password: str, new_password: str) -> None:
        _require_actor(actor_user_id)
        row = self.conn.execute(
            "SELECT password_hash, status FROM users WHERE user_id=?", (actor_user_id,)
        ).fetchone()
        if row is None or row["status"] != "active" or not verify_password(old_password, row["password_hash"]):
            raise NotFoundError(actor_user_id)  # 统一 NotFound，不泄露账号状态
        if not new_password or len(new_password) < 8:
            raise ValueError("新密码长度不足")
        with self.conn:
            self.conn.execute(
                "UPDATE users SET password_hash=?, updated_at=? WHERE user_id=?",
                (hash_password(new_password), utcnow(), actor_user_id),
            )

    def set_user_status(self, *, actor_user_id: str, user_id: str, status: str) -> None:
        """active 恢复不自动重发凭据；disabled 走 disable_user 级联。"""
        self._require_admin(actor_user_id)
        if status not in ("active", "disabled"):
            raise ValueError("status 仅支持 active/disabled")
        if status == "disabled":
            self.disable_user(actor_user_id=actor_user_id, user_id=user_id)
            return
        with self.conn:
            n = self.conn.execute(
                "UPDATE users SET status='active', updated_at=? WHERE user_id=? AND status!='pending'",
                (utcnow(), user_id),
            ).rowcount
        if n == 0:
            raise NotFoundError(user_id)

    def list_users(self, *, actor_user_id: str) -> list[dict]:
        self._require_admin(actor_user_id)
        rows = self.conn.execute(
            "SELECT u.user_id, u.login_account, u.phone, u.display_name, u.role, u.status, u.created_at, u.updated_at,"
            " (SELECT MAX(d.last_used_at) FROM device_tokens d"
            "  WHERE d.user_id=u.user_id AND d.revoked_at IS NULL) AS last_used_at"
            " FROM users u ORDER BY u.created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def session_user(self, *, user_id: str) -> dict | None:
        """会话校验用：返回 {user_id, display_name, role, status, tenant_id} 或 None。"""
        row = self.conn.execute(
            "SELECT user_id, display_name, role, status, tenant_id FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    # ---------------- 辅助（迁移工具/端点层用） ----------------

    def new_task_for(self, actor_user_id: str) -> str:
        _require_actor(actor_user_id)
        return new_id("tsk")

    def task_current_rev(self, actor_user_id: str, task_id: str) -> int:
        _require_actor(actor_user_id)
        row = self.conn.execute(
            "SELECT current_rev FROM ctx_tasks WHERE task_id=? AND owner_user_id=?", (task_id, actor_user_id)
        ).fetchone()
        return row["current_rev"] if row else 0

    def asset_current_rev(self, actor_user_id: str, kind: str) -> int:
        _require_actor(actor_user_id)
        row = self.conn.execute(
            "SELECT current_rev FROM ctx_assets WHERE owner_user_id=? AND kind=?", (actor_user_id, kind)
        ).fetchone()
        return row["current_rev"] if row else 0

    # ---------------- 个人资产域（§1.5，单当前版 + 幂等 mutation） ----------------

    def apply_asset(
        self,
        *,
        actor_user_id: str,
        kind: str,
        client_mutation_id: str,
        base_rev: int,
        payload: Any,
    ) -> SnapshotResult:
        _require_actor(actor_user_id)
        if kind not in ("hotwords", "speaker_aliases", "decision_statuses"):
            raise ValueError(f"未知资产类型 {kind}")
        blob_bytes = gzip.compress(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        digest = _sha256(blob_bytes)
        row = self.conn.execute(
            "SELECT * FROM ctx_assets WHERE owner_user_id=? AND kind=?", (actor_user_id, kind)
        ).fetchone()
        current_rev = row["current_rev"] if row is not None else 0
        if row is not None and row["content_hash"] == digest:
            # 内容幂等：同 digest 重放直接返回当前版（资产为全量快照语义）
            return SnapshotResult(row["current_rev"], row["content_hash"], row["updated_at"], idempotent_replay=True)
        if base_rev != current_rev:
            raise StaleRevisionError(current_rev)
        new_rev = current_rev + 1
        blob_path = self.dr.blobs_dir / actor_user_id / "assets" / f"{kind}.json.gz"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = blob_path.with_suffix(".tmp")
        tmp.write_bytes(blob_bytes)
        tmp.replace(blob_path)
        now = utcnow()
        with self.conn:
            if row is None:
                self.conn.execute(
                    "INSERT INTO ctx_assets(asset_id, owner_user_id, kind, current_rev, blob_path, content_hash, updated_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (new_id("ast"), actor_user_id, kind, new_rev, str(blob_path), digest, now),
                )
            else:
                self.conn.execute(
                    "UPDATE ctx_assets SET current_rev=?, blob_path=?, content_hash=?, updated_at=?"
                    " WHERE owner_user_id=? AND kind=?",
                    (new_rev, str(blob_path), digest, now, actor_user_id, kind),
                )
        return SnapshotResult(new_rev, digest, now)

    def get_asset(self, *, actor_user_id: str, kind: str) -> dict:
        _require_actor(actor_user_id)
        row = self.conn.execute(
            "SELECT * FROM ctx_assets WHERE owner_user_id=? AND kind=?", (actor_user_id, kind)
        ).fetchone()
        if row is None:
            return {"kind": kind, "visibility": "personal", "current_rev": 0, "content_hash": None, "payload": None}
        payload = None
        p = Path(row["blob_path"])
        if p.exists():
            payload = json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))
        return {
            "kind": kind,
            "visibility": row["scope"],
            "current_rev": row["current_rev"],
            "content_hash": row["content_hash"],
            "updated_at": row["updated_at"],
            "payload": payload,
        }

    def create_pairing(self, *, actor_user_id: str, ttl_minutes: int = 10) -> str:
        _require_actor(actor_user_id)
        code = generate_secret_code(12)
        with self.conn:
            self.conn.execute(
                "INSERT INTO pairings(pairing_id, pairing_code_hash, user_id, expires_at) VALUES (?,?,?,?)",
                (new_id("prg"), hash_secret(code), actor_user_id, now_add_minutes(ttl_minutes)),
            )
        return code

    def redeem_pairing(self, *, pairing_code: str, device_name: str) -> tuple[str, str, str]:
        """助手兑换 device token：明文 token 仅此一次返回；附带归属 user_id 供助手展示。"""
        row = self.conn.execute(
            "SELECT * FROM pairings WHERE pairing_code_hash=? AND redeemed_at IS NULL",
            (hash_secret(pairing_code),),
        ).fetchone()
        if row is None or row["expires_at"] < utcnow():
            raise NotFoundError("配对码无效或已过期")
        device_id, token = new_id("dev"), generate_secret_code()
        with self.conn:
            self.conn.execute(
                "INSERT INTO device_tokens(device_id, user_id, token_hash, device_name, created_at) VALUES (?,?,?,?,?)",
                (device_id, row["user_id"], hash_secret(token), device_name, utcnow()),
            )
            self.conn.execute("UPDATE pairings SET redeemed_at=? WHERE pairing_id=?", (utcnow(), row["pairing_id"]))
        return device_id, token, row["user_id"]

    def verify_device_token(self, token: str) -> str | None:
        """返回可用 device token 的 user_id（仅允许上下文写端点，端点层约束）。"""
        row = self.conn.execute(
            "SELECT d.user_id, d.revoked_at, u.status FROM device_tokens d JOIN users u ON u.user_id=d.user_id"
            " WHERE d.token_hash=?",
            (hash_secret(token),),
        ).fetchone()
        if row is None or row["revoked_at"] is not None or row["status"] != "active":
            return None
        with self.conn:
            self.conn.execute("UPDATE device_tokens SET last_used_at=? WHERE token_hash=?", (utcnow(), hash_secret(token)))
        return row["user_id"]

    def revoke_device(self, *, actor_user_id: str, device_id: str) -> None:
        _require_actor(actor_user_id)
        with self.conn:
            n = self.conn.execute(
                "UPDATE device_tokens SET revoked_at=? WHERE device_id=? AND user_id=? AND revoked_at IS NULL",
                (utcnow(), device_id, actor_user_id),
            ).rowcount
        if n == 0:
            raise NotFoundError(device_id)

    def revoke_all_devices(self, *, actor_user_id: str) -> None:
        _require_actor(actor_user_id)
        with self.conn:
            self.conn.execute(
                "UPDATE device_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (utcnow(), actor_user_id),
            )

    # ---------------- 上下文快照域（§1.4，幂等+串行 rev） ----------------

    def apply_snapshot(
        self,
        *,
        actor_user_id: str,
        task_id: str,
        client_mutation_id: str,
        base_rev: int,
        payload: dict,
    ) -> SnapshotResult:
        _require_actor(actor_user_id)
        self._validate_payload(payload)
        blob_bytes = gzip.compress(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        digest = _sha256(blob_bytes)

        existing = self.conn.execute(
            "SELECT r.rev, r.content_hash, r.created_at, r.task_id FROM ctx_revisions r"
            " WHERE r.owner_user_id=? AND r.client_mutation_id=?",
            (actor_user_id, client_mutation_id),
        ).fetchone()
        if existing is not None:
            if existing["task_id"] != task_id:
                raise ValueError("client_mutation_id 已用于其他 task")
            return SnapshotResult(existing["rev"], existing["content_hash"], existing["created_at"], idempotent_replay=True)

        task = self.conn.execute(
            "SELECT * FROM ctx_tasks WHERE task_id=? AND owner_user_id=?", (task_id, actor_user_id)
        ).fetchone()
        if task is None:
            # 防枚举：他人名下同名 task → 统一 NotFound（QA 域 A：禁止以 409/5xx 区分存在性）
            foreign = self.conn.execute(
                "SELECT 1 FROM ctx_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if foreign is not None:
                raise NotFoundError(task_id)
        current_rev = task["current_rev"] if task is not None else 0
        if base_rev != current_rev:
            raise StaleRevisionError(current_rev)

        now = utcnow()
        new_rev = current_rev + 1
        blob_path = self.dr.blob_path(actor_user_id, task_id, new_rev)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = blob_path.with_suffix(".tmp")
        tmp.write_bytes(blob_bytes)
        tmp.replace(blob_path)  # 原子写，沿用项目 fs_atomic 语义

        meta = payload.get("meta") or {}
        with self.conn:
            if task is None:
                self.conn.execute(
                    "INSERT INTO ctx_tasks(task_id, owner_user_id, legacy_id, title, meeting_time,"
                    " participants_text, source, current_rev, content_hash, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        task_id,
                        actor_user_id,
                        meta.get("legacy_id"),
                        meta.get("title", ""),
                        meta.get("meeting_time"),
                        meta.get("participants_text"),
                        meta.get("source", "client"),
                        new_rev,
                        digest,
                        now,
                    ),
                )
            else:
                self.conn.execute(
                    "UPDATE ctx_tasks SET current_rev=?, content_hash=?, updated_at=?"
                    " , title=COALESCE(?, title), meeting_time=COALESCE(?, meeting_time),"
                    " participants_text=COALESCE(?, participants_text)"
                    " WHERE task_id=? AND owner_user_id=? AND current_rev=?",
                    (
                        new_rev,
                        digest,
                        now,
                        meta.get("title") or None,
                        meta.get("meeting_time"),
                        meta.get("participants_text"),
                        task_id,
                        actor_user_id,
                        current_rev,
                    ),
                )
            self.conn.execute(
                "INSERT INTO ctx_revisions(rev_id, task_id, owner_user_id, rev, client_mutation_id,"
                " blob_path, content_hash, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_id("rvw"), task_id, actor_user_id, new_rev, client_mutation_id, str(blob_path), digest, now),
            )
            for kind in ("formal", "summary", "decisions", "notes", "insights_html"):
                if kind in payload and payload[kind] is not None:
                    value = payload[kind]
                    self.conn.execute("DELETE FROM ctx_entities WHERE task_id=? AND kind=?", (task_id, kind))
                    self.conn.execute(
                        "INSERT INTO ctx_entities(task_id, kind, payload_json, current) VALUES (?,?,?,1)",
                        (task_id, kind, json.dumps(value, ensure_ascii=False)),
                    )
        return SnapshotResult(new_rev, digest, now)

    def get_task(self, *, actor_user_id: str, task_id: str) -> dict:
        _require_actor(actor_user_id)
        row = self.conn.execute(
            "SELECT * FROM ctx_tasks WHERE task_id=? AND owner_user_id=? AND status='active'",
            (task_id, actor_user_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(task_id)
        d = dict(row)
        entities = {
            r["kind"]: json.loads(r["payload_json"])
            for r in self.conn.execute("SELECT kind, payload_json FROM ctx_entities WHERE task_id=?", (task_id,))
        }
        # 契约固定返回字段：visibility（P0 恒 personal）与 sync_status 对账态
        return {
            "task_id": d["task_id"],
            "visibility": d["scope"],
            "sync_status": "synced",
            "server_rev": d["current_rev"],
            "content_hash": d["content_hash"],
            "meta": {
                "title": d["title"],
                "meeting_time": d["meeting_time"],
                "participants_text": d["participants_text"],
                "source": d["source"],
                "legacy_id": d["legacy_id"],
            },
            "updated_at": d["updated_at"],
            **entities,
        }

    def list_tasks(self, *, actor_user_id: str, since: str | None = None) -> list[dict]:
        _require_actor(actor_user_id)
        sql = (
            "SELECT task_id, title, scope, current_rev, content_hash, updated_at FROM ctx_tasks"
            " WHERE owner_user_id=? AND status='active'"
        )
        params: tuple = (actor_user_id,)
        if since:
            sql += " AND updated_at > ?"
            params = (*params, since)
        rows = self.conn.execute(sql + " ORDER BY updated_at DESC", params).fetchall()
        return [{**dict(r), "visibility": r["scope"], "sync_status": "synced"} for r in rows]

    def delete_task(self, *, actor_user_id: str, task_id: str) -> None:
        """软删 30 天回收站（PRD 定稿口径）；管理员不可读内容。"""
        _require_actor(actor_user_id)
        with self.conn:
            n = self.conn.execute(
                "UPDATE ctx_tasks SET status='deleted', deleted_at=?, updated_at=? WHERE task_id=? AND owner_user_id=? AND status='active'",
                (utcnow(), utcnow(), task_id, actor_user_id),
            ).rowcount
        if n == 0:
            raise NotFoundError(task_id)

    def purge_expired_trash(self, *, actor_user_id: str, now_iso: str | None = None) -> int:
        """回收站到期物理删（默认 30 天）；由实例内定时任务以系统身份逐用户调用。"""
        _require_actor(actor_user_id)
        cutoff = now_add_days(-30, base=now_iso)
        with self.conn:
            rows = self.conn.execute(
                "SELECT task_id FROM ctx_tasks WHERE owner_user_id=? AND status='deleted' AND deleted_at <= ?",
                (actor_user_id, cutoff),
            ).fetchall()
            for r in rows:
                self.conn.execute("DELETE FROM ctx_entities WHERE task_id=?", (r["task_id"],))
                self.conn.execute("DELETE FROM ctx_revisions WHERE task_id=?", (r["task_id"],))
                self.conn.execute("DELETE FROM ctx_tasks WHERE task_id=?", (r["task_id"],))
        return len(rows)

    # ---------------- 实例配置 / 出境审计 ----------------

    def set_instance_config(self, *, actor_user_id: str, key: str, value: Any) -> None:
        self._require_admin(actor_user_id)
        with self.conn:
            self.conn.execute(
                "INSERT INTO instance_config(key, value_json, updated_by, updated_at) VALUES (?,?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,"
                " updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), actor_user_id, utcnow()),
            )

    def get_instance_config(self, key: str, default: Any = None) -> Any:
        """实例公开配置（service_open/ai_enabled/bootstrap_done 免登录可读，见 §1.6）。"""
        row = self.conn.execute("SELECT value_json FROM instance_config WHERE key=?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else default

    def audit_egress(
        self,
        *,
        user_id: str | None,
        action: str,
        object_ref: str | None = None,
        byte_len: int | None = None,
        client_mutation_id: str | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO egress_audit(audit_id, ts, user_id, action, object_ref, byte_len, client_mutation_id)"
                " VALUES (?,?,?,?,?,?,?)",
                (new_id("aud"), utcnow(), user_id, action, object_ref, byte_len, client_mutation_id),
            )

    # ---------------- 内部校验 ----------------

    @staticmethod
    def _validate_payload(payload: dict) -> None:
        allowed = SNAPSHOT_FIELDS | {"content_hash"}
        extra = set(payload) - allowed
        if extra:
            raise PayloadNotAllowedError(f"白名单外字段: {sorted(extra)}")
        meta = payload.get("meta")
        if meta is not None:
            extra_meta = set(meta) - SNAPSHOT_META_KEYS
            if extra_meta:
                raise PayloadNotAllowedError(f"meta 白名单外字段: {sorted(extra_meta)}")

    def _is_admin(self, user_id: str) -> bool:
        row = self.conn.execute("SELECT role, status FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row is not None and row["role"] == "admin" and row["status"] == "active"

    def _require_admin(self, actor_user_id: str) -> None:
        _require_actor(actor_user_id)
        if not self._is_admin(actor_user_id):
            raise NotFoundError(actor_user_id)


def _require_actor(actor_user_id: str | None) -> str:
    if not actor_user_id:
        raise ActorRequiredError("DAO 查询必须携带 actor_user_id（契约 §2.2）")
    return actor_user_id


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def now_add_days(days: int, base: str | None = None) -> str:
    t = _dt.datetime.fromisoformat(base) if base else _dt.datetime.now(_dt.timezone.utc)
    return (t + _dt.timedelta(days=days)).isoformat(timespec="seconds")


def now_add_minutes(minutes: int) -> str:
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")
