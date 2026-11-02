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


class TeamRoleError(RuntimeError):
    """成员门槛不足 —— 403 明示语义（契约 §8：角色是明示语义非资源隐藏）。"""

    def __init__(self, min_role: str):
        super().__init__(f"需要团队角色 ≥ {min_role}")
        self.min_role = min_role


class TeamConflictError(RuntimeError):
    """团队域 409/422 冲突（last_admin、already_member、归档态等，端点层映射语义码）。"""


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
        # P1 承接（契约 §2 离职撤权）：撤全部 effective 团队成员身份，行保留审计；发布的团队副本不随人走
        self.deactivate_membership(user_id=user_id)

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

    def _canonical_task_id(self, actor_user_id: str, task_id: str) -> str:
        """请求携带的标识 → 服务端权威 task_id（解析不出即原样返回，由调用方走统一 NotFound）。

        存量迁移按契约 §1.1 以 `tsk_`+ULID 入库、旧本机 task_id 另存 `legacy_id` 列；而 Web 首页
        最近会议、浏览器书签、助手 outbox 仍持旧 UUID。只按 task_id 查会让同一场会议出现两个面：
        旧引用一律 404（“会议不存在或已被删除”），且客户端按 UUID 重推会另建一份副本。
        解析严格限定在本人名下（含 legacy_id 命中也需 owner 匹配）：他人资源解析不出，落回原有
        统一 NotFound 口径，不新增存在性 oracle。
        """
        _require_actor(actor_user_id)
        if not task_id:
            return task_id
        exact = self.conn.execute(
            "SELECT task_id FROM ctx_tasks WHERE task_id=? AND owner_user_id=?", (task_id, actor_user_id)
        ).fetchone()
        if exact is not None:
            return exact["task_id"]
        legacy = self.conn.execute(
            "SELECT task_id FROM ctx_tasks WHERE legacy_id=? AND owner_user_id=? AND status='active'",
            (task_id, actor_user_id),
        ).fetchone()
        return legacy["task_id"] if legacy is not None else task_id

    def task_current_rev(self, actor_user_id: str, task_id: str) -> int:
        _require_actor(actor_user_id)
        row = self.conn.execute(
            "SELECT current_rev FROM ctx_tasks WHERE task_id=? AND owner_user_id=?",
            (self._canonical_task_id(actor_user_id, task_id), actor_user_id),
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
        # 旧 UUID 引用先解析为权威 task_id，幂等重放判断必须在解析之后（否则同 mutation 记到两个键上）
        task_id = self._canonical_task_id(actor_user_id, task_id)
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
        task_id = self._canonical_task_id(actor_user_id, task_id)
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
            "published_copies": self._published_copies(actor_user_id, [task_id]).get(task_id, []),
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
        copies = self._published_copies(actor_user_id, [r["task_id"] for r in rows])
        return [{**dict(r), "visibility": r["scope"], "sync_status": "synced",
                 "published_copies": copies.get(r["task_id"], [])} for r in rows]

    def delete_task(self, *, actor_user_id: str, task_id: str) -> None:
        """软删 30 天回收站（PRD 定稿口径）；管理员不可读内容。"""
        _require_actor(actor_user_id)
        task_id = self._canonical_task_id(actor_user_id, task_id)
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

    # ---------------- 团队域（契约 v1.0 §2/§8：三档 ACL + K1 留痕） ----------------

    TEAM_ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}

    def _audit(
        self,
        *,
        team_id: str,
        actor_user_id: str,
        action: str,
        task_id: str | None = None,
        rev: int | None = None,
        target_ref: str | None = None,
        pre_delete_rev: int | None = None,
        content_hash: str | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO team_edit_audit(audit_id, team_id, task_id, rev, actor_user_id, action,"
                " target_ref, pre_delete_rev, content_hash, ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id("aud"), team_id, task_id, rev, actor_user_id, action,
                 target_ref, pre_delete_rev, content_hash, utcnow()),
            )

    def team_role(self, team_id: str, user_id: str) -> str | None:
        """effective 成员角色；非成员/停用成员返回 None（§2 离职撤权）。"""
        _require_actor(user_id)
        row = self.conn.execute(
            "SELECT role FROM team_members WHERE team_id=? AND user_id=? AND effective=1",
            (team_id, user_id),
        ).fetchone()
        return row["role"] if row else None

    def require_team_role(self, team_id: str, user_id: str, min_role: str) -> str:
        """ACL 判定（契约 §8 错误语义）：非成员=NotFoundError(404 防枚举)；角色不足=TeamRoleError(403 明示)。"""
        role = self.team_role(team_id, user_id)
        if role is None:
            raise NotFoundError(team_id)
        if self.TEAM_ROLE_RANK[role] < self.TEAM_ROLE_RANK[min_role]:
            raise TeamRoleError(min_role)
        return role

    def _live_team(self, team_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM teams WHERE team_id=?", (team_id,)).fetchone()
        if row is None:
            raise NotFoundError(team_id)
        return dict(row)

    def create_team(self, *, actor_user_id: str, name: str) -> dict:
        """裁决2：任何 active 用户可建团队；创建者自动 admin（§2"至少一名 admin"的应用层约束起点）。"""
        _require_actor(actor_user_id)
        if not name or not name.strip():
            raise TeamConflictError("team_name_required")
        u = self.conn.execute("SELECT tenant_id, status FROM users WHERE user_id=?", (actor_user_id,)).fetchone()
        if u is None or u["status"] != "active":
            raise NotFoundError(actor_user_id)
        team_id = new_id("team")
        now = utcnow()
        with self.conn:
            self.conn.execute(
                "INSERT INTO teams(team_id, tenant_id, name, created_by, status, created_at) VALUES (?,?,?,?, 'active', ?)",
                (team_id, u["tenant_id"], name.strip(), actor_user_id, now),
            )
            self.conn.execute(
                "INSERT INTO team_members(team_id, user_id, role, added_by, joined_at, effective) VALUES (?,?,?,?,?,1)",
                (team_id, actor_user_id, "admin", actor_user_id, now),
            )
        self._audit(team_id=team_id, actor_user_id=actor_user_id, action="member_add")
        return {"team_id": team_id, "name": name.strip(), "my_role": "admin", "created_at": now, "status": "active"}

    def list_my_teams(self, *, actor_user_id: str) -> list[dict]:
        """UI 切换器数据源（契约 §8.1 逐字字段）。"""
        _require_actor(actor_user_id)
        rows = self.conn.execute(
            "SELECT t.team_id, t.name, t.status, m.role AS my_role, m.joined_at,"
            " (SELECT COUNT(*) FROM team_members x WHERE x.team_id=t.team_id AND x.effective=1) AS member_count"
            " FROM teams t JOIN team_members m ON m.team_id=t.team_id"
            " WHERE m.user_id=? AND m.effective=1 ORDER BY m.joined_at",
            (actor_user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_team(self, *, actor_user_id: str, team_id: str) -> dict:
        self.require_team_role(team_id, actor_user_id, "viewer")
        t = self._live_team(team_id)
        members = [
            dict(r)
            for r in self.conn.execute(
                "SELECT m.user_id, u.display_name, m.role, m.joined_at FROM team_members m"
                " JOIN users u ON u.user_id=m.user_id WHERE m.team_id=? AND m.effective=1 ORDER BY m.joined_at",
                (team_id,),
            ).fetchall()
        ]
        return {
            "team_id": t["team_id"], "name": t["name"], "status": t["status"],
            "my_role": self.team_role(team_id, actor_user_id), "members": members,
        }

    def rename_team(self, *, actor_user_id: str, team_id: str, name: str) -> dict:
        self.require_team_role(team_id, actor_user_id, "admin")
        if not name or not name.strip():
            raise TeamConflictError("team_name_required")
        with self.conn:
            self.conn.execute("UPDATE teams SET name=? WHERE team_id=?", (name.strip(), team_id))
        return {"team_id": team_id, "name": name.strip()}

    def add_member(self, *, actor_user_id: str, team_id: str, user_id: str, role: str = "editor") -> dict:
        self.require_team_role(team_id, actor_user_id, "admin")
        self._live_team(team_id)
        if role not in self.TEAM_ROLE_RANK:
            raise TeamConflictError(f"非法角色 {role}")
        target = self.conn.execute("SELECT status FROM users WHERE user_id=?", (user_id,)).fetchone()
        if target is None or target["status"] != "active":
            raise NotFoundError(user_id)
        if self.team_role(team_id, user_id) is not None:
            raise TeamConflictError("already_member")
        with self.conn:
            self.conn.execute(
                "INSERT INTO team_members(team_id, user_id, role, added_by, joined_at, effective) VALUES (?,?,?,?,?,1)",
                (team_id, user_id, role, actor_user_id, utcnow()),
            )
        self._audit(team_id=team_id, actor_user_id=actor_user_id, action="member_add")
        return {"team_id": team_id, "user_id": user_id, "role": role}

    def change_member_role(self, *, actor_user_id: str, team_id: str, user_id: str, role: str) -> dict:
        self.require_team_role(team_id, actor_user_id, "admin")
        if role not in self.TEAM_ROLE_RANK:
            raise TeamConflictError(f"非法角色 {role}")
        cur = self.team_role(team_id, user_id)
        if cur is None:
            raise NotFoundError(user_id)
        if cur == "admin" and role != "admin" and self._admin_count(team_id) <= 1:
            raise TeamConflictError("last_admin")  # §1 应用层约束：最后一名 admin 离开前必须移交
        with self.conn:
            self.conn.execute(
                "UPDATE team_members SET role=? WHERE team_id=? AND user_id=?", (role, team_id, user_id)
            )
        self._audit(team_id=team_id, actor_user_id=actor_user_id, action="member_role_change")
        return {"team_id": team_id, "user_id": user_id, "role": role}

    def _admin_count(self, team_id: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) c FROM team_members WHERE team_id=? AND role='admin' AND effective=1", (team_id,)
        ).fetchone()["c"]

    def transfer_admin(self, *, actor_user_id: str, team_id: str, to_user_id: str) -> dict:
        """转让团队管理员：目标升 admin，actor 降 editor；单事务（K1 role_transfer）。"""
        self.require_team_role(team_id, actor_user_id, "admin")
        if self.team_role(team_id, to_user_id) is None:
            raise NotFoundError(to_user_id)
        with self.conn:
            self.conn.execute(
                "UPDATE team_members SET role='editor' WHERE team_id=? AND user_id=?", (team_id, actor_user_id)
            )
            self.conn.execute(
                "UPDATE team_members SET role='admin' WHERE team_id=? AND user_id=?", (team_id, to_user_id)
            )
        self._audit(team_id=team_id, actor_user_id=actor_user_id, action="role_transfer")
        return {"team_id": team_id, "new_admin": to_user_id}

    def remove_member(self, *, actor_user_id: str, team_id: str, user_id: str) -> dict:
        self.require_team_role(team_id, actor_user_id, "admin")
        cur = self.team_role(team_id, user_id)
        if cur is None:
            raise NotFoundError(user_id)
        if cur == "admin" and self._admin_count(team_id) <= 1:
            raise TeamConflictError("last_admin")
        with self.conn:
            self.conn.execute(
                "UPDATE team_members SET effective=0 WHERE team_id=? AND user_id=?", (team_id, user_id)
            )
        self._audit(team_id=team_id, actor_user_id=actor_user_id, action="member_remove")
        return {"team_id": team_id, "user_id": user_id, "removed": True}

    def archive_team(self, *, actor_user_id: str, team_id: str) -> dict:
        """裁决④归档只读：拒绝新写入（409 team_archived 由端点层判定），既有副本仍可撤回。"""
        self.require_team_role(team_id, actor_user_id, "admin")
        t = self._live_team(team_id)
        if t["status"] == "archived":
            raise TeamConflictError("already_archived")
        with self.conn:
            self.conn.execute("UPDATE teams SET status='archived', archived_at=? WHERE team_id=?", (utcnow(), team_id))
        self._audit(team_id=team_id, actor_user_id=actor_user_id, action="team_archive")
        return {"team_id": team_id, "status": "archived"}

    def deactivate_membership(self, *, user_id: str) -> int:
        """P0 停用级联承接（§2 离职撤权）：全部 effective 成员身份置 0，行保留审计。返回撤权数。"""
        _require_actor(user_id)
        with self.conn:
            n = self.conn.execute(
                "UPDATE team_members SET effective=0 WHERE user_id=? AND effective=1", (user_id,)
            ).rowcount
        return n

    def audit_page(self, *, actor_user_id: str, team_id: str, cursor: str | None, limit: int) -> dict:
        """变更记录端点数据源（§8.4 倒序分页；K1 十二值原样透出）。"""
        self.require_team_role(team_id, actor_user_id, "viewer")
        rows = self.conn.execute(
            "SELECT a.audit_id, a.action, a.actor_user_id, u.display_name AS actor_name,"
            " a.task_id, a.rev, a.target_ref, a.pre_delete_rev, a.ts"
            " FROM team_edit_audit a JOIN users u ON u.user_id=a.actor_user_id"
            " WHERE a.team_id=? AND (a.ts < ? OR ? IS NULL) ORDER BY a.ts DESC LIMIT ?",
            (team_id, cursor, cursor, limit + 1),
        ).fetchall()
        items = [dict(r) for r in rows[:limit]]
        return {"items": items, "next_cursor": rows[limit - 1]["ts"] if len(rows) > limit else None}

    def search_users(self, *, actor_user_id: str, q: str) -> list[dict]:
        """契约 §8.5：任何 active 用户可调（建团队选成员）；只回 user_id/display_name，不暴露联系面。"""
        _require_actor(actor_user_id)
        me = self.conn.execute("SELECT status FROM users WHERE user_id=?", (actor_user_id,)).fetchone()
        if me is None or me["status"] != "active":
            raise NotFoundError(actor_user_id)
        like = f"%{q.strip()}%" if q and q.strip() else "%"
        rows = self.conn.execute(
            "SELECT user_id, display_name FROM users WHERE status='active' AND display_name LIKE ?"
            " ORDER BY display_name LIMIT 20",
            (like,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 团队副本域（契约 §3 发布/编辑/撤回；裁决⑤白名单结构性排除） ----------------

    def _published_copies(self, owner: str, src_ids: list[str]) -> dict[str, list[dict]]:
        """发布态读面（规格 §4.3 角标+逐团队撤回；PM 拍板二定版：内嵌原件 DTO，不建独立端点）。"""
        if not src_ids:
            return {}
        marks = ",".join("?" * len(src_ids))
        rows = self.conn.execute(
            "SELECT c.source_task_id, c.task_id AS copy_task_id, c.team_id, t.name AS team_name,"
            " c.acl AS granularity_marker, c.current_rev, c.updated_at"
            f" FROM ctx_tasks c JOIN teams t ON t.team_id=c.team_id"
            f" WHERE c.owner_user_id=? AND c.scope='team' AND c.status='active'"
            f" AND c.source_task_id IN ({marks}) ORDER BY c.updated_at",
            (owner, *src_ids),
        ).fetchall()
        out: dict[str, list[dict]] = {}
        for r in rows:
            d = dict(r)
            marker = d.pop("granularity_marker")
            d["granularity"] = "task" if marker is None else "decision"
            out.setdefault(d["source_task_id"], []).append(d)
        return out

    TEAM_EXCLUDED_FIELDS = ("formal",)  # 逐字稿永不进团队空间；音频字段本就不在 P0 白名单——双保险

    def _team_copy_payload(self, payload: dict) -> dict:
        out = {k: v for k, v in payload.items() if k in SNAPSHOT_FIELDS and k not in self.TEAM_EXCLUDED_FIELDS}
        meta = payload.get("meta") or {}
        out["meta"] = {k: meta[k] for k in ("title", "meeting_time", "participants_text") if meta.get(k) is not None}
        out["meta"]["source"] = meta.get("source", "client")
        return out

    def _copy_row(self, team_id: str, task_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM ctx_tasks WHERE task_id=? AND team_id=? AND scope='team' AND status='active'",
            (task_id, team_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(task_id)
        return dict(row)

    def _read_rev_payload(self, task_id: str, rev: int) -> dict:
        r = self.conn.execute(
            "SELECT blob_path FROM ctx_revisions WHERE task_id=? AND rev=?", (task_id, rev)
        ).fetchone()
        if r is None:
            raise NotFoundError(f"{task_id}@{rev}")
        return json.loads(gzip.decompress(Path(r["blob_path"]).read_bytes()).decode("utf-8"))

    def _current_payload(self, task_id: str) -> dict:
        d = self.conn.execute("SELECT * FROM ctx_tasks WHERE task_id=?", (task_id,)).fetchone()
        if d is None:
            raise NotFoundError(task_id)
        payload = {
            r["kind"]: json.loads(r["payload_json"])
            for r in self.conn.execute("SELECT kind, payload_json FROM ctx_entities WHERE task_id=?", (task_id,))
        }
        payload["meta"] = {
            "title": d["title"], "meeting_time": d["meeting_time"],
            "participants_text": d["participants_text"], "source": d["source"],
        }
        return payload

    def apply_team_snapshot(
        self,
        *,
        actor_user_id: str,
        team_id: str,
        task_id: str,
        client_mutation_id: str,
        base_rev: int,
        payload: dict,
        audit_action: str | None = "edit",
        audit_target_ref: str | None = None,
        audit_pre_delete_rev: int | None = None,
    ) -> SnapshotResult:
        """团队副本快照 PUT（契约 §3.2/§8.3）：editor+ 可写；actor=写作者、owner 仍为行归属人（§6B）。"""
        self.require_team_role(team_id, actor_user_id, "editor")
        if self._live_team(team_id)["status"] != "active":
            raise TeamConflictError("team_archived")  # 裁决④：归档拒绝新写入（撤回路径不走本函数）
        row = self._copy_row(team_id, task_id)
        if any(k in payload for k in self.TEAM_EXCLUDED_FIELDS):
            raise PayloadNotAllowedError("团队副本不包含逐字转写（裁决⑤结构性排除）")
        self._validate_payload(payload)
        existing = self.conn.execute(
            "SELECT r.rev, r.content_hash, r.created_at, r.task_id FROM ctx_revisions r"
            " WHERE r.owner_user_id=? AND r.client_mutation_id=?",
            (actor_user_id, client_mutation_id),
        ).fetchone()
        if existing is not None:
            if existing["task_id"] != task_id:
                raise ValueError("client_mutation_id 已用于其他 task")
            return SnapshotResult(existing["rev"], existing["content_hash"], existing["created_at"], idempotent_replay=True)
        current_rev = row["current_rev"]
        if base_rev != current_rev:
            raise StaleRevisionError(current_rev)
        blob_bytes = gzip.compress(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        digest = _sha256(blob_bytes)
        now = utcnow()
        new_rev = current_rev + 1
        blob_path = self.dr.blob_path(actor_user_id, task_id, new_rev)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = blob_path.with_suffix(".tmp")
        tmp.write_bytes(blob_bytes)
        tmp.replace(blob_path)
        meta = payload.get("meta") or {}
        with self.conn:
            self.conn.execute(
                "UPDATE ctx_tasks SET current_rev=?, content_hash=?, updated_at=?"
                " , title=COALESCE(?, title), meeting_time=COALESCE(?, meeting_time),"
                " participants_text=COALESCE(?, participants_text)"
                " WHERE task_id=? AND team_id=? AND current_rev=?",
                (
                    new_rev, digest, now,
                    meta.get("title") or None, meta.get("meeting_time"), meta.get("participants_text"),
                    task_id, team_id, current_rev,
                ),
            )
            self.conn.execute(
                "INSERT INTO ctx_revisions(rev_id, task_id, owner_user_id, actor_user_id, rev,"
                " client_mutation_id, blob_path, content_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (new_id("rvw"), task_id, actor_user_id, actor_user_id, new_rev, client_mutation_id,
                 str(blob_path), digest, now),
            )
            for kind in ("summary", "decisions", "notes", "insights_html"):  # formal 结构性不在列
                if payload.get(kind) is not None:
                    self.conn.execute("DELETE FROM ctx_entities WHERE task_id=? AND kind=?", (task_id, kind))
                    self.conn.execute(
                        "INSERT INTO ctx_entities(task_id, kind, payload_json, current) VALUES (?,?,?,1)",
                        (task_id, kind, json.dumps(payload[kind], ensure_ascii=False)),
                    )
        if audit_action is not None:
            self._audit(
                team_id=team_id, actor_user_id=actor_user_id, action=audit_action, task_id=task_id,
                rev=new_rev, content_hash=digest, target_ref=audit_target_ref,
                pre_delete_rev=audit_pre_delete_rev,
            )
        if payload.get("decisions") is not None:
            self.collect_team_decisions(
                team_id=team_id, task_id=task_id, rev=new_rev,
                decisions=payload["decisions"], actor_user_id=actor_user_id,
            )
        return SnapshotResult(new_rev, digest, now)

    def collect_team_decisions(self, *, team_id: str, task_id: str, rev: int,
                               decisions: list, actor_user_id: str) -> None:
        """契约 §5：副本 decisions 任何变化 → 同幂等键 upsert 资产快照（只收集不消费，追溯锚=rev+哈希）。"""
        seen: list[str] = []
        now = utcnow()
        with self.conn:
            for d in decisions or []:
                if not isinstance(d, dict) or d.get("id") is None:
                    continue
                did = str(d["id"])
                seen.append(did)
                snap = json.dumps(d, ensure_ascii=False, sort_keys=True)
                digest = _sha256(snap.encode("utf-8"))
                self.conn.execute(
                    "INSERT INTO enterprise_decision_assets(asset_id, source_task_id, source_team_id,"
                    " source_rev, decision_id, snapshot_json, content_hash, collected_by, collected_at, status)"
                    " VALUES (?,?,?,?,?,?,?,?,?, 'collected')"
                    " ON CONFLICT(source_task_id, decision_id) DO UPDATE SET"
                    " source_rev=excluded.source_rev, snapshot_json=excluded.snapshot_json,"
                    " content_hash=excluded.content_hash, collected_by=excluded.collected_by,"
                    " collected_at=excluded.collected_at,"
                    " withdrawn_at=NULL,"
                    " status=CASE WHEN enterprise_decision_assets.status='withdrawn'"
                    "        THEN 'withdrawn' ELSE 'collected' END",
                    (new_id("edas"), task_id, team_id, rev, did, snap, digest, actor_user_id, now),
                )
            if seen:
                marks = ",".join("?" * len(seen))
                self.conn.execute(
                    f"UPDATE enterprise_decision_assets SET status='stale'"
                    f" WHERE source_task_id=? AND status='collected' AND decision_id NOT IN ({marks})",
                    (task_id, *seen),
                )
            else:
                self.conn.execute(
                    "UPDATE enterprise_decision_assets SET status='stale' WHERE source_task_id=?"
                    " AND status='collected'",
                    (task_id,),
                )

    def publish_to_team(
        self,
        *,
        actor_user_id: str,
        task_id: str,
        team_id: str,
        mode: str = "task",
        decision_id: str | None = None,
    ) -> dict:
        """发布=创建/刷新团队副本（契约 §3.1；裁决①多团队独立副本；K2 形态：同团队重复发布=刷新既有副本）。"""
        _require_actor(actor_user_id)
        if mode not in ("task", "decision"):
            raise TeamConflictError(f"unknown_mode:{mode}")
        if mode == "decision" and not decision_id:
            raise TeamConflictError("decision_id_required")
        src = self.conn.execute(
            "SELECT * FROM ctx_tasks WHERE task_id=? AND owner_user_id=? AND status='active' AND scope='personal'",
            (task_id, actor_user_id),
        ).fetchone()
        if src is None:
            raise NotFoundError(task_id)
        self.require_team_role(team_id, actor_user_id, "editor")
        if self._live_team(team_id)["status"] != "active":
            raise TeamConflictError("team_archived")
        src_payload = self._read_rev_payload(task_id, src["current_rev"]) if src["current_rev"] > 0 else {}
        copy_payload = self._team_copy_payload(src_payload)
        if mode == "decision":
            keep = [d for d in (copy_payload.get("decisions") or [])
                    if isinstance(d, dict) and d.get("id") == decision_id]
            if not keep:
                raise NotFoundError(decision_id)
            copy_payload = {"meta": copy_payload["meta"], "decisions": keep}
        # K2 形态（本实现定版，报数待 QA 实测）：
        # - 纪要粒度发布：同(源,团队)已有纪要粒度副本 → 刷新之（不产生第二份）；
        # - 单条决策粒度发布：按 decision 独立行（acl 标记 decision:<id>），重复发布同一决策刷新对应行；
        #   两种粒度互不覆盖——"整会副本"与"单决策副本"是两条时间线。
        pub_key = f"{mode}-{decision_id or 'all'}"
        if mode == "task":
            existing = self.conn.execute(
                "SELECT task_id, current_rev FROM ctx_tasks WHERE source_task_id=? AND team_id=?"
                " AND status='active' AND acl IS NULL",
                (task_id, team_id),
            ).fetchone()
        else:
            existing = self.conn.execute(
                "SELECT task_id, current_rev FROM ctx_tasks WHERE source_task_id=? AND team_id=?"
                " AND status='active' AND acl=?",
                (task_id, team_id, f"decision:{decision_id}"),
            ).fetchone()
        if existing is not None:
            self.apply_team_snapshot(
                actor_user_id=actor_user_id, team_id=team_id, task_id=existing["task_id"],
                client_mutation_id=f"pub-{task_id}-{team_id}-{pub_key}-r{src['current_rev']}",
                base_rev=existing["current_rev"], payload=copy_payload,
                audit_action="decision_publish" if mode == "decision" else "publish",
            )
            return {**self.get_team_task(actor_user_id=actor_user_id, team_id=team_id, task_id=existing["task_id"]),
                    "republished": True}
        copy_task_id = new_id("tsk")
        now = utcnow()
        meta = copy_payload.get("meta") or {}
        with self.conn:
            self.conn.execute(
                "INSERT INTO ctx_tasks(task_id, owner_user_id, scope, team_id, source_task_id, acl, tenant_id,"
                " title, meeting_time, participants_text, source, status, current_rev, updated_at)"
                " VALUES (?,?, 'team', ?, ?, ?, (SELECT tenant_id FROM users WHERE user_id=?),"
                " ?,?,?,'client', 'active', 0, ?)",
                (copy_task_id, actor_user_id, team_id, task_id,
                 None if mode == "task" else f"decision:{decision_id}", actor_user_id,
                 meta.get("title", ""), meta.get("meeting_time"), meta.get("participants_text"), now),
            )
        self.apply_team_snapshot(
            actor_user_id=actor_user_id, team_id=team_id, task_id=copy_task_id,
            client_mutation_id=f"pub-{task_id}-{team_id}-{pub_key}-v1", base_rev=0, payload=copy_payload,
            audit_action="decision_publish" if mode == "decision" else "publish",
        )
        return {**self.get_team_task(actor_user_id=actor_user_id, team_id=team_id, task_id=copy_task_id),
                "republished": False}

    def get_team_task(self, *, actor_user_id: str, team_id: str, task_id: str) -> dict:
        self.require_team_role(team_id, actor_user_id, "viewer")
        d = self._copy_row(team_id, task_id)
        entities = {
            r["kind"]: json.loads(r["payload_json"])
            for r in self.conn.execute("SELECT kind, payload_json FROM ctx_entities WHERE task_id=?", (task_id,))
        }
        return {
            "task_id": d["task_id"], "visibility": "team", "team_id": team_id,
            "source_task_id": d["source_task_id"], "publisher_user_id": d["owner_user_id"],
            "my_role": self.team_role(team_id, actor_user_id),
            "server_rev": d["current_rev"], "content_hash": d["content_hash"],
            "meta": {
                "title": d["title"], "meeting_time": d["meeting_time"],
                "participants_text": d["participants_text"], "source": d["source"],
            },
            "updated_at": d["updated_at"],
            **entities,
        }

    def list_team_tasks(self, *, actor_user_id: str, team_id: str) -> list[dict]:
        self.require_team_role(team_id, actor_user_id, "viewer")
        rows = self.conn.execute(
            "SELECT task_id, title, current_rev, content_hash, source_task_id, owner_user_id AS publisher_user_id,"
            " updated_at FROM ctx_tasks WHERE team_id=? AND scope='team' AND status='active'"
            " ORDER BY updated_at DESC",
            (team_id,),
        ).fetchall()
        return [{**dict(r), "visibility": "team"} for r in rows]

    def get_team_task_revision(self, *, actor_user_id: str, team_id: str, task_id: str, rev: int) -> dict:
        """历史版本全文（§6 并排 diff 与"恢复"按钮的数据面；viewer+）。"""
        self.require_team_role(team_id, actor_user_id, "viewer")
        self._copy_row(team_id, task_id)
        payload = self._read_rev_payload(task_id, rev)
        return {"task_id": task_id, "team_id": team_id, "rev": rev, "payload": payload}

    def withdraw_team_task(self, *, actor_user_id: str, team_id: str, task_id: str) -> dict:
        """撤回（契约 §3.3）：editor 撤自己发布、admin 撤任意；归档团队仍可撤回中项（裁决④）。原件不受影响。"""
        row = self._copy_row(team_id, task_id)
        role = self.require_team_role(team_id, actor_user_id, "editor")
        if row["owner_user_id"] != actor_user_id and role != "admin":
            raise TeamRoleError("admin")
        now = utcnow()
        with self.conn:
            self.conn.execute(
                "UPDATE ctx_tasks SET status='deleted', deleted_at=?, updated_at=?"
                " WHERE task_id=? AND status='active'",
                (now, now, task_id),
            )
        self.mark_assets_withdrawn(source_task_id=task_id)
        self._audit(team_id=team_id, actor_user_id=actor_user_id, action="withdraw", task_id=task_id)
        return {"task_id": task_id, "withdrawn": True}

    def delete_team_decision(self, *, actor_user_id: str, team_id: str, task_id: str, decision_id: str) -> dict:
        """裁决③：editor 删他人副本内决策条目；留痕 decision_delete 携 target_ref+pre_delete_rev。"""
        payload = self._current_payload(task_id)
        decisions = payload.get("decisions") or []
        keep = [d for d in decisions if not (isinstance(d, dict) and d.get("id") == decision_id)]
        if len(keep) == len(decisions):
            raise NotFoundError(decision_id)
        pre_rev = self._copy_row(team_id, task_id)["current_rev"]
        result = self.apply_team_snapshot(
            actor_user_id=actor_user_id, team_id=team_id, task_id=task_id,
            client_mutation_id=f"del-dec-{decision_id}-r{pre_rev}-{utcnow()}",
            base_rev=pre_rev, payload={**payload, "decisions": keep}, audit_action=None,
        )
        self._audit(
            team_id=team_id, actor_user_id=actor_user_id, action="decision_delete", task_id=task_id,
            rev=result.server_rev, target_ref=decision_id, pre_delete_rev=pre_rev,
            content_hash=result.content_hash,
        )
        self.mark_asset_stale(source_task_id=task_id, decision_id=decision_id)
        return {"task_id": task_id, "decision_id": decision_id, "server_rev": result.server_rev,
                "pre_delete_rev": pre_rev}

    def restore_team_decision(self, *, actor_user_id: str, team_id: str, task_id: str,
                              decision_id: str, from_rev: int) -> dict:
        """恢复=从 pre_delete_rev 历史版本重推该条目为新版（裁决③闭环；恢复本身新留痕 decision_restore）。"""
        old_payload = self._read_rev_payload(task_id, from_rev)
        item = [d for d in (old_payload.get("decisions") or [])
                if isinstance(d, dict) and d.get("id") == decision_id]
        if not item:
            raise NotFoundError(decision_id)
        payload = self._current_payload(task_id)
        cur = payload.get("decisions") or []
        if any(isinstance(d, dict) and d.get("id") == decision_id for d in cur):
            raise TeamConflictError("already_present")
        cur_row = self._copy_row(team_id, task_id)
        result = self.apply_team_snapshot(
            actor_user_id=actor_user_id, team_id=team_id, task_id=task_id,
            client_mutation_id=f"res-dec-{decision_id}-from{from_rev}-{utcnow()}",
            base_rev=cur_row["current_rev"], payload={**payload, "decisions": [*cur, item[0]]},
            audit_action=None,
        )
        self._audit(
            team_id=team_id, actor_user_id=actor_user_id, action="decision_restore", task_id=task_id,
            rev=result.server_rev, target_ref=decision_id, pre_delete_rev=from_rev,
            content_hash=result.content_hash,
        )
        return {"task_id": task_id, "decision_id": decision_id, "server_rev": result.server_rev,
                "restored_from_rev": from_rev}

    # ---------------- 决策资产只收集层维护原语（契约 §5；零读端点） ----------------

    def mark_assets_withdrawn(self, *, source_task_id: str) -> int:
        """撤回副本 → 该副本源资产行转 withdrawn 保留（Q1：前台只显示"已撤回"，资产层零界面）。"""
        now = utcnow()
        with self.conn:
            n = self.conn.execute(
                "UPDATE enterprise_decision_assets SET status='withdrawn', withdrawn_at=?"
                " WHERE source_task_id=? AND status='collected'",
                (now, source_task_id),
            ).rowcount
        return n

    def mark_asset_stale(self, *, source_task_id: str, decision_id: str) -> int:
        """源决策其后被修改或删除 → 标 stale 不删除（追溯性是裁决4核心承诺）。"""
        with self.conn:
            n = self.conn.execute(
                "UPDATE enterprise_decision_assets SET status='stale'"
                " WHERE source_task_id=? AND decision_id=? AND status='collected'",
                (source_task_id, decision_id),
            ).rowcount
        return n


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
