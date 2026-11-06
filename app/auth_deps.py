"""
app/auth_deps.py — 管理员/本地模式鉴权依赖（跨路由共享）

T-24：这些依赖原定义在 app/routers/admin.py，admin_config / engine_component / models
只能 `from app.routers.admin import ...` 反查，形成 router → router 耦合。
鉴权是横切关注点，与具体端点无关，抽为独立 app 模块供各路由引用。

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-06
"""

import os

import jwt
from fastapi import HTTPException, Request

from core.auth import JWT_SECRET as ADMIN_JWT_SECRET
from core.i18n import _

ADMIN_COOKIE = "oms_admin_session"


def _verify_admin_token(token: str) -> dict | None:
    """验证管理员 JWT / Verify admin JWT"""
    try:
        payload = jwt.decode(token, ADMIN_JWT_SECRET, algorithms=["HS256"])
        if payload.get("role") != "admin":
            return None
        return payload
    except jwt.InvalidTokenError:
        return None


def require_admin(request: Request):
    """依赖注入：验证管理员身份 / Dependency injection: verify admin identity"""
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        raise HTTPException(401, _("Please log in to the admin console first"))
    payload = _verify_admin_token(token)
    if not payload:
        raise HTTPException(401, _("Admin login expired"))
    return payload


def is_local_single_user() -> bool:
    """是否本地单机部署（REQUIRE_AUTH 非 true）/ Whether this is a local single-user deployment.

    动态读取环境变量（而非缓存的模块常量），以便测试用 monkeypatch.setenv 切换。
    """
    return os.getenv("REQUIRE_AUTH", "false").lower() != "true"


def require_admin_or_local(request: Request):
    """依赖注入：管理员或本地单机模式放行 / Dependency: admin session OR local single-user mode.

    单机桌面部署（REQUIRE_AUTH=false，默认）下操作者即机器所有者，直接视为管理员；
    多用户服务器部署仍要求管理后台签发的 oms_admin_session cookie（D-R2 不变）。
    仅用于 /api/engine/* 等客户端可触发的变更面；/api/admin/*（用户/配额治理）
    维持 require_admin 严格校验，不受本地模式影响。
    """
    if is_local_single_user():
        return {"sub": "local", "role": "admin", "source": "local_mode"}
    return require_admin(request)
