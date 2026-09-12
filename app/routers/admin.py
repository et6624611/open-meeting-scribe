"""
app/routers/admin.py — 管理后台 API 路由

职责：
  1. 管理员登录/登出（独立密码认证，与用户 JWT 互不干扰）
  2. 用户管理（列表、详情、禁用/启用）
  3. 授权管理（修改用户配额档位）
  4. 系统概览（统计摘要）

远程配置（消息/功能开关）已拆分至 admin_config.py

认证方式：
  - 环境变量 ADMIN_PASSWORD 设定管理员密码
  - 登录后签发独立 JWT（cookie: oms_admin_session），与用户端 cookie 完全隔离
  - 所有 /api/admin/* 端点须携带管理员 cookie
"""

import os
import time
import logging
import hashlib
import secrets

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import jwt

from core.users import (
    _load_user_data, _save_user_data,
    get_user_by_id, set_user_subscription,
)
from core.metering import get_monthly_usage, TIER_QUOTAS
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["管理后台"])

# ============================================================
# 管理员认证
# ============================================================

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_JWT_SECRET = os.getenv("JWT_SECRET", "admin-fallback-secret")
ADMIN_COOKIE = "oms_admin_session"
ADMIN_JWT_EXPIRE_SECONDS = 12 * 3600  # 12 小时


def _hash_password(password: str) -> str:
    """对密码做 SHA-256 哈希（管理后台专用，不与用户密码混用）"""
    return hashlib.sha256(password.encode()).hexdigest()


def _create_admin_token() -> str:
    """签发管理员 JWT"""
    now = int(time.time())
    payload = {
        "sub": "admin",
        "role": "admin",
        "iat": now,
        "exp": now + ADMIN_JWT_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, ADMIN_JWT_SECRET, algorithm="HS256")


def _verify_admin_token(token: str) -> dict | None:
    """验证管理员 JWT"""
    try:
        payload = jwt.decode(token, ADMIN_JWT_SECRET, algorithms=["HS256"])
        if payload.get("role") != "admin":
            return None
        return payload
    except jwt.InvalidTokenError:
        return None


def require_admin(request: Request):
    """依赖注入：验证管理员身份"""
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        raise HTTPException(401, _("Please log in to the admin console first"))
    payload = _verify_admin_token(token)
    if not payload:
        raise HTTPException(401, _("Admin login expired"))
    return payload


# ============================================================
# 登录/登出
# ============================================================

class AdminLoginRequest(BaseModel):
    password: str = Field(..., description="管理员密码")


@router.post("/login")
def admin_login(req: AdminLoginRequest):
    """管理员登录"""
    if not ADMIN_PASSWORD:
        raise HTTPException(500, _("Admin password not configured (ADMIN_PASSWORD)"))

    if not secrets.compare_digest(req.password, ADMIN_PASSWORD):
        logger.warning("管理员登录失败：密码错误")
        raise HTTPException(401, _("Incorrect password"))

    token = _create_admin_token()
    logger.info("管理员登录成功")

    response = JSONResponse({"success": True})
    response.set_cookie(
        key=ADMIN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=ADMIN_JWT_EXPIRE_SECONDS,
        path="/",
    )
    return response


@router.post("/logout")
def admin_logout():
    """管理员登出"""
    response = JSONResponse({"message": _("Logged out")})
    response.delete_cookie(key=ADMIN_COOKIE, path="/")
    logger.info("管理员已登出")
    return response


@router.get("/me")
def admin_me(_: dict = Depends(require_admin)):
    """验证管理员登录状态"""
    return {"role": "admin", "logged_in": True}


# ============================================================
# 系统概览
# ============================================================

@router.get("/overview")
def admin_overview(_: dict = Depends(require_admin)):
    """
    系统概览统计。

    返回：用户总数、各授权档位分布、本月总用量、最近注册用户。
    """
    data = _load_user_data()
    users = data.get("users", [])

    # 体验期用户统计
    tier_counts = {"free": 0}
    for user in users:
        tier = user.get("subscription", {}).get("tier", "free")
        if tier in tier_counts:
            tier_counts[tier] += 1
        # 非 free 档位视为自持 Key 用户（不计入配额统计）

    # 本月总用量
    month_key = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m")
    total_monthly_minutes = 0.0
    for user in users:
        total_monthly_minutes += get_monthly_usage(user["id"], month_key)

    # 最近 10 个注册用户（按创建时间倒序）
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
            "tier": u.get("subscription", {}).get("tier", "free"),
            "created_at": u.get("created_at", ""),
            "last_login": u.get("last_login", ""),
        })

    return {
        "total_users": len(users),
        "tier_counts": tier_counts,
        "total_monthly_minutes": round(total_monthly_minutes, 1),
        "month_key": month_key,
        "recent_users": recent_list,
    }


# ============================================================
# 用户管理
# ============================================================

@router.get("/users")
def admin_list_users(
    search: str = "",
    tier: str = "",
    _: dict = Depends(require_admin),
):
    """
    用户列表。

    支持按名称/手机号搜索，按授权档位筛选。
    """
    data = _load_user_data()
    users = data.get("users", [])

    result = []
    for u in users:
        # 搜索过滤
        if search:
            name = u.get("name", "").lower()
            provider_id = u.get("provider_id", "")
            email = u.get("email", "").lower()
            if (search.lower() not in name
                    and search not in provider_id
                    and search.lower() not in email):
                continue

        # 授权档位过滤
        user_tier = u.get("subscription", {}).get("tier", "free")
        if tier and user_tier != tier:
            continue

        # 本月用量
        month_key = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).strftime("%Y-%m")
        monthly_minutes = get_monthly_usage(u["id"], month_key)
        quota = TIER_QUOTAS.get(user_tier, 0)

        phone = u.get("provider_id", "") if u.get("provider") == "sms" else ""

        result.append({
            "id": u["id"],
            "name": u.get("name", ""),
            "provider": u.get("provider", ""),
            "provider_id": u.get("provider_id", ""),
            "phone_masked": f"{phone[:3]}****{phone[-4:]}" if len(phone) == 11 else "",
            "email": u.get("email", ""),
            "role": u.get("role", "personal"),
            "tier": user_tier,
            "monthly_minutes": round(monthly_minutes, 1),
            "quota": quota,
            "status": u.get("status", "active"),
            "created_at": u.get("created_at", ""),
            "last_login": u.get("last_login", ""),
        })

    # 按创建时间倒序
    result.sort(key=lambda u: u.get("created_at", ""), reverse=True)
    return {"users": result, "total": len(result)}


@router.get("/users/{user_id}")
def admin_get_user(user_id: str, _: dict = Depends(require_admin)):
    """用户详情（含用量历史）"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    month_key = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m")
    monthly_minutes = get_monthly_usage(user_id, month_key)
    tier = user.get("subscription", {}).get("tier", "free")
    quota = TIER_QUOTAS.get(tier, 0)

    # 最近 7 天用量
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
        "subscription": user.get("subscription", {"tier": "free"}),
        "prefs": user.get("prefs", {}),
        "monthly_minutes": round(monthly_minutes, 1),
        "quota": quota,
        "daily_usage": daily,
        "created_at": user.get("created_at", ""),
        "last_login": user.get("last_login", ""),
    }


# ============================================================
# 授权管理
# ============================================================

class UpdateSubscriptionRequest(BaseModel):
    tier: str = Field(..., description="授权档位: free")
    expires_at: str = Field(default=None, description="到期时间（ISO 8601）")


@router.put("/users/{user_id}/subscription")
def admin_update_subscription(
    user_id: str,
    req: UpdateSubscriptionRequest,
    _: dict = Depends(require_admin),
):
    """修改用户授权档位"""
    valid_tiers = list(TIER_QUOTAS.keys())
    if req.tier not in valid_tiers:
        raise HTTPException(400, _("Invalid tier, options: {opts}").format(opts=', '.join(valid_tiers)))

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    updated = set_user_subscription(
        user_id=user_id,
        tier=req.tier,
        expires_at=req.expires_at,
    )

    if not updated:
        raise HTTPException(500, _("Update failed"))

    logger.info(f"管理员修改授权: user={user_id[:8]}, tier={req.tier}")
    return {
        "success": True,
        "user_id": user_id,
        "new_tier": req.tier,
    }


# ============================================================
# 用户状态管理
# ============================================================

class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="账号状态: active/disabled")


@router.put("/users/{user_id}/status")
def admin_update_user_status(
    user_id: str,
    req: UpdateStatusRequest,
    _: dict = Depends(require_admin),
):
    """禁用/启用用户账号"""
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
