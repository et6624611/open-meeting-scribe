"""企业版 P0 /api/v1 端点层 + /healthz（契约 v1.0 §1，EP0-BE 增量2）。

挂载纪律：仅 ``OMS_EDITION=enterprise`` 时由 server.py 注册；个人版进程零路由、零行为变化。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from typing import Any

import jwt as pyjwt
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from ..db.config import resolve_data_root
from ..db.dao import (
    EnterpriseStore,
    NotFoundError,
    PayloadNotAllowedError,
    StaleRevisionError,
)
from ..db.database import instance_key, migrate

COOKIE_NAME = "oms_e_session"
SESSION_TTL_DAYS = 7

_store_cache: dict[str, EnterpriseStore] = {}


def get_store() -> EnterpriseStore:
    dr = resolve_data_root()
    key = str(dr.root.resolve()) if dr.root.exists() else str(dr.root)
    if key not in _store_cache:
        store = EnterpriseStore(dr)
        migrate(store.conn)  # 进程启动即保证 schema 最新（幂等）
        _store_cache[key] = store
    return _store_cache[key]


def reset_store_cache() -> None:
    """测试钩子：切换 OMS_DATA_ROOT 后重建。"""
    for s in _store_cache.values():
        s.close()
    _store_cache.clear()


class EHttp(Exception):
    """契约统一错误体 {"error": {"code", "message", ...}}"""

    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(code)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def to_response(self) -> JSONResponse:
        err = {"code": self.code, "message": self.message, **self.extra}
        return JSONResponse(status_code=self.status, content={"error": err})


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------


def _jwt_secret() -> bytes:
    return instance_key(resolve_data_root())


def _issue_session(store: EnterpriseStore, user_id: str, response: Response) -> None:
    jti = uuid.uuid4().hex
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=SESSION_TTL_DAYS)
    with store.conn:
        store.conn.execute(
            "INSERT INTO sessions(session_id, user_id, jwt_jti, expires_at) VALUES (?,?,?,?)",
            ("ss_" + jti, user_id, jti, exp.isoformat(timespec="seconds")),
        )
    token = pyjwt.encode({"uid": user_id, "jti": jti, "exp": exp}, _jwt_secret(), algorithm="HS256")
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", max_age=SESSION_TTL_DAYS * 86400, path="/"
    )


def _session_user_id(request: Request) -> str | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    store = get_store()
    try:
        data = pyjwt.decode(raw, _jwt_secret(), algorithms=["HS256"])
    except pyjwt.InvalidTokenError:
        return None
    row = store.conn.execute(
        "SELECT s.revoked_at, s.expires_at, u.status FROM sessions s JOIN users u ON u.user_id=s.user_id"
        " WHERE s.jwt_jti=?",
        (data.get("jti"),),
    ).fetchone()
    if row is None or row["revoked_at"] is not None or row["status"] != "active":
        return None
    return data["uid"]


def current_user(request: Request) -> str:
    uid = _session_user_id(request)
    if uid is None:
        raise EHttp(401, "unauthenticated", "需要登录")
    return uid


def current_admin(user_id: str = Depends(current_user)) -> str:
    store = get_store()
    info = store.session_user(user_id=user_id)
    if info is None or info["role"] != "admin":
        raise EHttp(403, "forbidden", "需要管理员")  # 管理面动作显式 403（角色泄露不涉及资源存在性）
    return user_id


def _service_open(store: EnterpriseStore) -> bool:
    return bool(store.get_instance_config("service_open", default=True))


def _device_user(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return get_store().verify_device_token(auth.removeprefix("Bearer ").strip())


def write_guard(request: Request, user_id: str) -> str:
    """写操作统一门禁：服务停用 503；device token 仅限上下文写（§1.8）。"""
    store = get_store()
    if not _service_open(store):
        raise EHttp(503, "service_closed", "企业服务已暂停，写操作不可用")
    return user_id


def actor_for_write(request: Request) -> str:
    """会话（Web）或 device token（助手）均可作为写入主体；device 停用/账号停用在此统一拒绝。"""
    uid = _device_user(request)
    if uid:
        return uid
    return current_user(request)


def _read_actor(request: Request) -> str:
    return current_user(request)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1")


@router.get("/instance/info")
def instance_info():
    store = get_store()
    row = store.conn.execute(
        "SELECT COUNT(*) c FROM users WHERE role='admin' AND status='active'"
    ).fetchone()
    version = "0"
    try:
        from pathlib import Path

        vf = Path(__file__).resolve().parents[2] / "VERSION"
        version = vf.read_text().strip() if vf.exists() else "0"
    except OSError:
        pass
    return {
        "product": "oms-enterprise",
        "version": version,
        "service_open": _service_open(store),
        "ai_enabled": bool(store.get_instance_config("ai_enabled", default=False)),
        "needs_bootstrap": row["c"] == 0,
    }


# ---- 认证面 ----


@router.post("/auth/login")
def auth_login(request: Request, response: Response, body: dict):
    store = get_store()
    if not _service_open(store):
        raise EHttp(403, "service_closed", "企业服务已暂停，请联系管理员")
    uid = store.verify_login(login_account=body.get("account") or "", password=body.get("password") or "")
    if uid is None:
        raise EHttp(401, "bad_credentials", "账号或密码错误")
    _issue_session(store, uid, response)
    info = store.session_user(user_id=uid)
    return {"user_id": uid, "display_name": info["display_name"], "role": info["role"]}


@router.post("/auth/activate")
def auth_activate(response: Response, body: dict):
    """邀请码自助设密；维护期（service_closed）仍放行——bootstrap admin 依赖本通道。"""
    store = get_store()
    try:
        uid = store.activate_invite(
            invite_code=body.get("invite_code") or "",
            password=body.get("password") or "",
            display_name=body.get("display_name"),
        )
    except (NotFoundError, ValueError) as exc:
        raise EHttp(422, "activation_failed", str(exc))
    _issue_session(store, uid, response)
    return {"user_id": uid, "role": store.session_user(user_id=uid)["role"]}


@router.post("/auth/logout")
def auth_logout(request: Request, response: Response):
    store = get_store()
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        try:
            data = pyjwt.decode(raw, _jwt_secret(), algorithms=["HS256"])
            with store.conn:
                store.conn.execute(
                    "UPDATE sessions SET revoked_at=? WHERE jwt_jti=?",
                    (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), data["jti"]),
                )
        except pyjwt.InvalidTokenError:
            pass
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
def auth_me(user_id: str = Depends(current_user)):
    info = get_store().session_user(user_id=user_id)
    return info


@router.post("/auth/change-password")
def auth_change_password(body: dict, user_id: str = Depends(current_user)):
    try:
        get_store().change_password(
            actor_user_id=user_id, old_password=body.get("old_password") or "", new_password=body.get("new_password") or ""
        )
    except NotFoundError:
        raise EHttp(401, "bad_credentials", "旧密码不正确")
    except ValueError as exc:
        raise EHttp(422, "weak_password", str(exc))
    return {"ok": True}


# ---- 配对与设备 ----


@router.post("/pairings")
def create_pairing(user_id: str = Depends(current_user)):
    code = get_store().create_pairing(actor_user_id=user_id)
    return {"pairing_code": code, "expires_in_minutes": 10}


@router.post("/auth/device-activate")
def device_activate(body: dict):
    store = get_store()
    if not _service_open(store):
        raise EHttp(403, "service_closed", "企业服务已暂停")
    try:
        device_id, token = store.redeem_pairing(
            pairing_code=body.get("pairing_code") or "", device_name=body.get("device_name") or ""
        )
    except NotFoundError:
        raise EHttp(404, "pairing_invalid", "配对码无效或已过期")
    return {"device_id": device_id, "device_token": token}  # 明文仅此一次


@router.get("/devices")
def list_devices(user_id: str = Depends(current_user)):
    rows = get_store().conn.execute(
        "SELECT device_id, device_name, created_at, last_used_at, revoked_at FROM device_tokens WHERE user_id=?"
        " ORDER BY created_at",
        (user_id,),
    ).fetchall()
    return {"devices": [dict(r) for r in rows]}


@router.delete("/devices/{device_id}")
def delete_device(device_id: str, user_id: str = Depends(current_user)):
    try:
        get_store().revoke_device(actor_user_id=user_id, device_id=device_id)
    except NotFoundError:
        raise EHttp(404, "not_found", "设备不存在或不属于当前用户")
    return {"ok": True}


# ---- 管理面 ----


@router.get("/admin/users")
def admin_users(admin: str = Depends(current_admin)):
    return {"users": get_store().list_users(actor_user_id=admin)}


@router.post("/admin/users")
def admin_create_user(body: dict, admin: str = Depends(current_admin)):
    store = get_store()
    try:
        user_id, invite = store.create_user(
            actor_user_id=admin,
            display_name=body.get("display_name") or "",
            login_account=body.get("account") or "",
            phone=body.get("phone"),
            role=body.get("role", "member"),
        )
    except Exception as exc:  # 登录名/手机号唯一冲突等均归 422
        raise EHttp(422, "invalid_user", str(exc))
    return {"user_id": user_id, "invite_code": invite}  # 明文邀请码仅此一次；无密码字段


@router.put("/admin/users/{user_id}/status")
def admin_user_status(user_id: str, body: dict, admin: str = Depends(current_admin)):
    try:
        get_store().set_user_status(actor_user_id=admin, user_id=user_id, status=body.get("status") or "")
    except (ValueError, NotFoundError):
        raise EHttp(404, "not_found", "状态变更失败")
    return {"ok": True}


@router.post("/admin/users/{user_id}/reset")
def admin_user_reset(user_id: str, admin: str = Depends(current_admin)):
    try:
        code = get_store().reset_password_issue_invite(actor_user_id=admin, user_id=user_id)
    except NotFoundError:
        raise EHttp(404, "not_found", "账号不存在")
    return {"invite_code": code}


@router.delete("/admin/users/{user_id}/data")
def admin_user_data_delete(user_id: str, admin: str = Depends(current_admin)):
    """整包删除停用账号数据（QA-Q3：管理台显式动作，二次确认属前端职责）。"""
    n = get_store().bulk_delete_user_data(actor_user_id=admin, user_id=user_id)
    return {"deleted_tasks": n}


@router.post("/admin/instance/close")
def admin_instance_close(admin: str = Depends(current_admin)):
    get_store().set_instance_config(actor_user_id=admin, key="service_open", value=False)
    return {"service_open": False}


@router.post("/admin/instance/open")
def admin_instance_open(admin: str = Depends(current_admin)):
    get_store().set_instance_config(actor_user_id=admin, key="service_open", value=True)
    return {"service_open": True}


@router.get("/admin/instance/ai")
def admin_ai_config(admin: str = Depends(current_admin)):
    store = get_store()
    provider = store.get_instance_config("ai_provider", default={}) or {}
    return {
        "enabled": bool(store.get_instance_config("ai_enabled", default=False)),
        "base_url": provider.get("base_url"),
        "model": provider.get("model"),
        "egress_allowlist": store.get_instance_config("egress_allowlist", default=[]),
    }  # api_key 永不回显


@router.put("/admin/instance/ai")
def admin_ai_update(body: dict, admin: str = Depends(current_admin)):
    store = get_store()
    enabled = bool(body.get("enabled", False))
    provider = {
        "base_url": body.get("base_url"),
        "model": body.get("model"),
    }
    allowlist: list[str] = []
    if body.get("api_key"):
        from cryptography.fernet import Fernet

        from ..db.database import instance_key as _ik

        f = Fernet(_derive_fernet_key(_ik(resolve_data_root())))
        provider["api_key_enc"] = f.encrypt(body["api_key"].encode()).decode()
        provider.pop("api_key", None)
    if enabled:
        if not body.get("base_url"):
            raise EHttp(422, "ai_config_invalid", "开启 AI 必须提供 base_url")
        from urllib.parse import urlparse

        allowlist = [urlparse(body["base_url"]).hostname]
    with store.conn:
        store.set_instance_config(actor_user_id=admin, key="ai_enabled", value=enabled)
        store.set_instance_config(actor_user_id=admin, key="ai_provider", value=provider)
        store.set_instance_config(actor_user_id=admin, key="egress_allowlist", value=allowlist)
    return {"enabled": enabled, "egress_allowlist": allowlist}


def _validate_asset_payload(payload: Any) -> None:
    """出境内容级门禁（QA 域 B）：资产只允许纯文本结构，拒收 embedding/二进制。"""
    ok = isinstance(payload, (list, dict, str))
    if isinstance(payload, str):
        return
    if isinstance(payload, list):
        ok = all(isinstance(x, str) for x in payload)
    elif isinstance(payload, dict):
        ok = all(isinstance(k, str) and isinstance(v, str) for k, v in payload.items())
    if not ok:
        raise EHttp(422, "payload_not_allowed", "资产仅允许纯文本结构（str/list[str]/dict[str,str]）")


def _derive_fernet_key(raw: bytes) -> bytes:
    import base64
    import hashlib

    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())


# ---- 上下文数据面 ----


@router.get("/context/tasks")
def ctx_list(request: Request, since: str | None = None):
    uid = _read_actor(request)
    return {"tasks": get_store().list_tasks(actor_user_id=uid, since=since)}


@router.get("/context/tasks/{task_id}")
def ctx_get(task_id: str, request: Request):
    uid = _read_actor(request)
    try:
        return get_store().get_task(actor_user_id=uid, task_id=task_id)
    except NotFoundError:
        raise EHttp(404, "not_found", "资源不存在")


@router.put("/context/tasks/{task_id}/snapshot")
def ctx_snapshot(task_id: str, request: Request, body: dict):
    uid = actor_for_write(request)
    write_guard(request, uid)
    mutation = request.headers.get("idempotency-key") or body.pop("client_mutation_id", None)
    if not mutation:
        raise EHttp(422, "missing_idempotency_key", "必须携带 Idempotency-Key 头")
    base_rev = int(request.headers.get("if-match-rev", "0") or 0)
    store = get_store()
    try:
        result = store.apply_snapshot(
            actor_user_id=uid, task_id=task_id, client_mutation_id=mutation, base_rev=base_rev, payload=body
        )
    except StaleRevisionError as exc:
        raise EHttp(409, "rev_conflict", "版本冲突，请拉取最新后重推", current_rev=exc.current_rev)
    except PayloadNotAllowedError as exc:
        store.audit_egress(user_id=uid, action="snapshot_rejected", object_ref=task_id)
        raise EHttp(422, "payload_not_allowed", str(exc))
    except NotFoundError:
        raise EHttp(404, "not_found", "资源不存在")
    except ValueError as exc:  # QA 映射要求①：mutation 跨 task 复用等 → 422，禁 5xx
        raise EHttp(422, "client_mutation_conflict", str(exc))
    store.audit_egress(user_id=uid, action="snapshot_applied", object_ref=task_id, byte_len=len(json.dumps(body)), client_mutation_id=mutation)
    status = 200 if (result.idempotent_replay or base_rev > 0) else 201
    content = {
        "server_rev": result.server_rev,
        "content_hash": result.content_hash,
        "stored_at": result.stored_at,
        "idempotent_replay": result.idempotent_replay,
    }
    return JSONResponse(status_code=status, content=content)


@router.delete("/context/tasks/{task_id}")
def ctx_delete(task_id: str, request: Request):
    uid = actor_for_write(request)
    write_guard(request, uid)
    try:
        get_store().delete_task(actor_user_id=uid, task_id=task_id)
    except NotFoundError:
        raise EHttp(404, "not_found", "资源不存在")
    return {"ok": True}


ASSET_KIND_MAP = {"hotwords": "hotwords", "speaker-aliases": "speaker_aliases"}


def _asset_kind(segment: str) -> str:
    kind = ASSET_KIND_MAP.get(segment)
    if kind is None:
        raise EHttp(404, "not_found", "资产类型不存在")
    return kind


@router.get("/context/assets/{kind_seg}")
def asset_get(kind_seg: str, request: Request):
    uid = _read_actor(request)
    return get_store().get_asset(actor_user_id=uid, kind=_asset_kind(kind_seg))


@router.put("/context/assets/{kind_seg}")
def asset_put(kind_seg: str, request: Request, body: dict):
    uid = actor_for_write(request)
    write_guard(request, uid)
    kind = _asset_kind(kind_seg)
    mutation = request.headers.get("idempotency-key") or body.pop("client_mutation_id", None)
    if not mutation:
        raise EHttp(422, "missing_idempotency_key", "必须携带 Idempotency-Key 头")
    base_rev = int(request.headers.get("if-match-rev", "0") or 0)
    payload = body.get("payload", body)
    _validate_asset_payload(payload)
    try:
        result = get_store().apply_asset(
            actor_user_id=uid, kind=kind, client_mutation_id=mutation, base_rev=base_rev, payload=payload
        )
    except StaleRevisionError as exc:
        raise EHttp(409, "rev_conflict", "版本冲突", current_rev=exc.current_rev)
    except ValueError as exc:
        raise EHttp(422, "client_mutation_conflict", str(exc))
    return {
        "current_rev": result.server_rev,
        "content_hash": result.content_hash,
        "idempotent_replay": result.idempotent_replay,
    }


# ---- AI 面（默认关闭；代理执行属增量3） ----


@router.post("/ai/summary/generate")
def ai_summary(body: dict, request: Request):
    uid = _read_actor(request)
    store = get_store()
    if not store.get_instance_config("ai_enabled", default=False):
        raise EHttp(409, "ai_disabled", "AI 助手未开启，联系管理员")
    raise EHttp(501, "ai_proxy_pending", "服务端 AI 代理为增量3交付；默认关闭态验收不受影响")


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------


def register_enterprise_routes(app: FastAPI) -> None:
    app.include_router(router)

    # P0 并发口径：实例级串行锁包住每个请求的全部 DB 访问（WAL+单写者语义的保守实现；
    # 企业单实例并发量级下可接受，P1 随快照域改为行级事务优化）。
    import threading

    api_lock = threading.Lock()

    @app.middleware("http")
    async def _serialize_db(request: Request, call_next):
        if request.url.path == "/healthz" or request.url.path.startswith("/api/v1"):
            with api_lock:
                return await call_next(request)
        return await call_next(request)

    @app.get("/healthz")
    def healthz():
        """存活+就绪复合探针：进程可达且实例库可读（DevOps compose healthcheck 判定）。"""
        store = get_store()
        store.conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.exception_handler(EHttp)
    async def _eh(request: Request, exc: EHttp):  # noqa: ARG001
        return exc.to_response()

    @app.exception_handler(StaleRevisionError)
    async def _stale(request: Request, exc: StaleRevisionError):  # noqa: ARG001
        return JSONResponse(
            status_code=409, content={"error": {"code": "rev_conflict", "message": str(exc), "current_rev": exc.current_rev}}
        )

    @app.exception_handler(NotFoundError)
    async def _nf(request: Request, exc: NotFoundError):  # noqa: ARG001
        return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "资源不存在"}})


def enterprise_mode() -> bool:
    return os.environ.get("OMS_EDITION", "").strip().lower() == "enterprise"
