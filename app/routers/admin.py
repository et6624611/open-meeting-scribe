"""
app/routers/admin.py — 管理后台 API 路由 / Admin backend API routes

职责 / Responsibilities:
  1. 管理员登录/登出（独立密码认证，与用户 JWT 互不干扰） / Admin login/logout (independent password auth; isolated from user JWT)
  2. 用户管理（列表、详情、禁用/启用） / User management (list, details, disable/enable)
  3. 配额管理（修改用户月度配额） / Quota management (modify user monthly quota)
  4. 系统概览（统计摘要） / System overview (statistics summary)

远程配置（消息/功能开关）已拆分至 admin_config.py / Remote config (messages/feature flags) split to admin_config.py

认证方式 / Auth method:
  - 环境变量 ADMIN_PASSWORD 设定管理员密码 / Set admin password via ADMIN_PASSWORD env var
  - 登录后签发独立 JWT（cookie: oms_admin_session），与用户端 cookie 完全隔离 / Independent JWT (cookie: oms_admin_session) after login; fully isolated from user cookie
  - 所有 /api/admin/* 端点须携带管理员 cookie / All /api/admin/* endpoints require admin cookie
"""

import hashlib
import logging
import os
import secrets
import time

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.i18n import _
from core.metering import DEFAULT_QUOTA, get_monthly_usage
from core.users import (
    _load_user_data,
    _save_user_data,
    get_user_by_id,
    set_user_quota,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["管理后台"])

# ============================================================
# 管理员认证 / Admin Authentication
# ============================================================

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
# 复用 core.auth 中已校验的 JWT_SECRET（永不为空，未配置时为进程级随机密钥）， / Reuse verified JWT_SECRET from core.auth (never empty; process-level random key if unconfigured);
# 不再使用硬编码兆底密钥，避免密钥可预测导致管理员 JWT 被伪造。 / no longer use hardcoded fallback key to avoid predictable key allowing admin JWT forgery.
from core.auth import JWT_SECRET as ADMIN_JWT_SECRET

ADMIN_COOKIE = "oms_admin_session"
ADMIN_JWT_EXPIRE_SECONDS = 12 * 3600  # 12 小时 / 12 hours

# Cookie Secure 标志：HTTPS 部署时设为 true，本地开发保持 false / Cookie Secure flag: true for HTTPS deployment; false for local dev
_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# 占位符/弱口令黑名单：避免直接沿用 .env.example 中的可猜测密码 / Placeholder/weak password blacklist: avoid using guessable passwords from .env.example
_WEAK_ADMIN_PASSWORDS = {
    "your-strong-password-here", "admin", "password", "changeme",
    "123456", "12345678", "admin123", "root",
}
_ADMIN_PASSWORD_MIN_LEN = 8

# 管理员登录速率限制（内存计数，单实例够用） / Admin login rate limiting (in-memory counter; sufficient for single instance)
_login_attempts: dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 5          # 窗口内最大失败次数 / Max failed attempts within window
_LOGIN_WINDOW_SEC = 300          # 计数窗口 5 分钟 / Counting window 5 minutes


def _prune_attempts(ip: str) -> list[float]:
    """清理过期计数并返回当前窗口内的失败时间戳 / Prune expired counts and return failed timestamps within current window"""
    now = time.time()
    recent = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW_SEC]
    _login_attempts[ip] = recent
    return recent


def _record_failed_login(ip: str) -> None:
    """记录一次失败尝试 / Record a failed attempt"""
    _login_attempts.setdefault(ip, []).append(time.time())


def _hash_password(password: str) -> str:
    """对密码做 SHA-256 哈希（管理后台专用，不与用户密码混用） / SHA-256 hash password (admin console only; not mixed with user passwords)"""
    return hashlib.sha256(password.encode()).hexdigest()


def _create_admin_token() -> str:
    """签发管理员 JWT / Issue admin JWT"""
    now = int(time.time())
    payload = {
        "sub": "admin",
        "role": "admin",
        "iat": now,
        "exp": now + ADMIN_JWT_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, ADMIN_JWT_SECRET, algorithm="HS256")


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


# 认证网关开关：与 app/server.py 的 enforce_auth_middleware 读取同一环境变量。 / Auth gateway flag: same env var as enforce_auth_middleware.
_REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"


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


# ============================================================
# 登录/登出 / Login/Logout
# ============================================================

class AdminLoginRequest(BaseModel):
    password: str = Field(..., description="管理员密码")


@router.post("/login")
def admin_login(req: AdminLoginRequest, request: Request):
    """管理员登录（带速率限制与弱口令校验） / Admin login (with rate limiting and weak password check)"""
    client_ip = request.client.host if request.client else "unknown"

    # 速率限制：窗口内失败次数超限则拒绝 / Rate limiting: reject when failed attempts exceed window limit
    if len(_prune_attempts(client_ip)) >= _LOGIN_MAX_ATTEMPTS:
        logger.warning(f"管理员登录频率超限: ip={client_ip}")
        raise HTTPException(429, _("Too many login attempts, please try again later"))

    if not ADMIN_PASSWORD:
        raise HTTPException(500, _("Admin password not configured (ADMIN_PASSWORD)"))

    # 弱口令/占位符拒绝：避免使用 .env.example 默认值或过短密码 / Reject weak/placeholder passwords: avoid using .env.example defaults or too-short passwords
    if (ADMIN_PASSWORD.strip().lower() in _WEAK_ADMIN_PASSWORDS
            or len(ADMIN_PASSWORD) < _ADMIN_PASSWORD_MIN_LEN):
        logger.error("ADMIN_PASSWORD 为弱口令/占位符，拒绝登录，请立即修改")
        raise HTTPException(
            500,
            _("Admin password is too weak, please set a strong ADMIN_PASSWORD"),
        )

    if not secrets.compare_digest(req.password, ADMIN_PASSWORD):
        _record_failed_login(client_ip)
        logger.warning(f"管理员登录失败：密码错误 | ip={client_ip}")
        raise HTTPException(401, _("Incorrect password"))

    # 登录成功，清空该 IP 的失败计数 / Login successful; clear failed attempt count for this IP
    _login_attempts.pop(client_ip, None)
    token = _create_admin_token()
    logger.info(f"管理员登录成功 | ip={client_ip}")

    response = JSONResponse({"success": True})
    response.set_cookie(
        key=ADMIN_COOKIE,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=ADMIN_JWT_EXPIRE_SECONDS,
        path="/",
    )
    return response


@router.post("/logout")
def admin_logout():
    """管理员登出 / Admin logout"""
    response = JSONResponse({"message": _("Logged out")})
    response.delete_cookie(key=ADMIN_COOKIE, path="/")
    logger.info("管理员已登出")
    return response


@router.get("/me")
def admin_me(_: dict = Depends(require_admin)):
    """验证管理员登录状态 / Verify admin login status"""
    return {"role": "admin", "logged_in": True}


# ============================================================
# 系统概览 / System Overview
# ============================================================

@router.get("/overview")
def admin_overview(_: dict = Depends(require_admin)):
    """系统概览统计。 / System overview statistics.

    返回：用户总数、各授权档位分布、本月总用量、最近注册用户。 / Returns: total users, tier distribution, monthly usage, recently registered users.
    """
    data = _load_user_data()
    users = data.get("users", [])

    # 用户总数 / Total users
    total_users = len(users)

    # 本月总用量 / Total usage this month
    month_key = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m")
    total_monthly_minutes = 0.0
    for user in users:
        total_monthly_minutes += get_monthly_usage(user["id"], month_key)

    # 最近 10 个注册用户（按创建时间倒序） / Last 10 registered users (by creation time, descending)
    recent_users = sorted(
        users,
        key=lambda u: u.get("created_at", ""),
        reverse=True,
    )[:10]

    recent_list = []
    for u in recent_users:
        phone = u.get("provider_id", "") if u.get("provider") == "sms" else ""
        recent_list.append({
            "id": u["id"],
            "name": u.get("name", ""),
            "provider": u.get("provider", ""),
            "phone_masked": f"{phone[:3]}****{phone[-4:]}" if len(phone) == 11 else "",
            "quota": u.get("quota", DEFAULT_QUOTA),
            "created_at": u.get("created_at", ""),
            "last_login": u.get("last_login", ""),
        })

    return {
        "total_users": total_users,
        "total_monthly_minutes": round(total_monthly_minutes, 1),
        "month_key": month_key,
        "recent_users": recent_list,
    }


# ============================================================
# 用户管理 / User Management
# ============================================================

@router.get("/users")
def admin_list_users(
    search: str = "",
    _: dict = Depends(require_admin),
):
    """用户列表。 / User list.

    支持按名称/手机号搜索。 / Supports search by name/phone.
    """
    data = _load_user_data()
    users = data.get("users", [])

    result = []
    for u in users:
        # 搜索过滤 / Search filter
        if search:
            name = u.get("name", "").lower()
            provider_id = u.get("provider_id", "")
            email = u.get("email", "").lower()
            if (search.lower() not in name
                    and search not in provider_id
                    and search.lower() not in email):
                continue

        # 本月用量 / Monthly usage
        month_key = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).strftime("%Y-%m")
        monthly_minutes = get_monthly_usage(u["id"], month_key)
        quota = u.get("quota", DEFAULT_QUOTA)

        phone = u.get("provider_id", "") if u.get("provider") == "sms" else ""

        result.append({
            "id": u["id"],
            "name": u.get("name", ""),
            "provider": u.get("provider", ""),
            "provider_id": u.get("provider_id", ""),
            "phone_masked": f"{phone[:3]}****{phone[-4:]}" if len(phone) == 11 else "",
            "email": u.get("email", ""),
            "role": u.get("role", "personal"),
            "monthly_minutes": round(monthly_minutes, 1),
            "quota": quota,
            "status": u.get("status", "active"),
            "created_at": u.get("created_at", ""),
            "last_login": u.get("last_login", ""),
        })

    # 按创建时间倒序 / Sort by creation time, descending
    result.sort(key=lambda u: u.get("created_at", ""), reverse=True)
    return {"users": result, "total": len(result)}


@router.get("/users/{user_id}")
def admin_get_user(user_id: str, _: dict = Depends(require_admin)):
    """用户详情（含用量历史） / User details (incl. usage history)"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    month_key = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m")
    monthly_minutes = get_monthly_usage(user_id, month_key)
    quota = user.get("quota", DEFAULT_QUOTA)

    # 最近 7 天用量 / Last 7 days usage
    from core.metering import get_daily_history
    daily = get_daily_history(user_id, days=7)

    return {
        "id": user["id"],
        "name": user.get("name", ""),
        "provider": user.get("provider", ""),
        "provider_id": user.get("provider_id", ""),
        "email": user.get("email", ""),
        "avatar_url": user.get("avatar_url", ""),
        "role": user.get("role", "personal"),
        "status": user.get("status", "active"),
        "prefs": user.get("prefs", {}),
        "monthly_minutes": round(monthly_minutes, 1),
        "quota": quota,
        "daily_usage": daily,
        "created_at": user.get("created_at", ""),
        "last_login": user.get("last_login", ""),
    }


# ============================================================
# 配额管理 / Quota Management
# ============================================================

class UpdateQuotaRequest(BaseModel):
    quota: int = Field(..., description="月度配额（分钟），0 表示不计量 / Monthly quota (minutes); 0 = not metered", ge=0)


@router.put("/users/{user_id}/quota")
def admin_update_quota(
    user_id: str,
    req: UpdateQuotaRequest,
    _: dict = Depends(require_admin),
):
    """修改用户月度配额 / Modify user monthly quota"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    updated = set_user_quota(user_id=user_id, quota=req.quota)

    if not updated:
        raise HTTPException(500, _("Update failed"))

    logger.info(f"管理员修改配额: user={user_id[:8]}, quota={req.quota}min")
    return {
        "success": True,
        "user_id": user_id,
        "new_quota": req.quota,
    }


# ============================================================
# 用户状态管理 / User Status Management
# ============================================================

class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="账号状态: active/disabled")


@router.put("/users/{user_id}/status")
def admin_update_user_status(
    user_id: str,
    req: UpdateStatusRequest,
    _: dict = Depends(require_admin),
):
    """禁用/启用用户账号 / Disable/enable user account"""
    if req.status not in ("active", "disabled"):
        raise HTTPException(400, _("Invalid status, options: active, disabled"))

    data = _load_user_data()
    for user in data.get("users", []):
        if user["id"] == user_id:
            user["status"] = req.status
            _save_user_data(data)
            logger.info(f"管理员修改用户状态: user={user_id[:8]}, status={req.status}")
            return {"success": True, "user_id": user_id, "status": req.status}

    raise HTTPException(404, _("User not found"))
