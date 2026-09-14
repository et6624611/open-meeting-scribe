"""
app/routers/cloud_api.py — 云端用户服务 API / Cloud user service API

职责 / Responsibilities:
  1. 接收桌面客户端的用户同步请求（SMS 登录后上报） / Receive desktop client user sync requests (after SMS login)
  2. 接收桌面客户端的用量上报 / Receive desktop client usage reports
  3. 提供配额查询接口 / Provide quota query endpoint

认证方式 / Authentication:
  - HMAC-SHA256 签名（与 SMS 代理同一模式） / HMAC-SHA256 signature (same pattern as SMS proxy)
  - 请求头：X-Cloud-Timestamp + X-Cloud-Sign / Headers: X-Cloud-Timestamp + X-Cloud-Sign
  - 密钥由 CLOUD_API_TOKEN 环境变量配置 / Secret configured via CLOUD_API_TOKEN env var
  - timestamp 超过 TTL（默认 5 分钟）视为过期 / timestamp beyond TTL (default 5 min) treated as expired

端点 / Endpoints:
  POST /api/cloud/users/sync    — 桌面端 SMS 登录后同步用户 / Sync user after desktop SMS login
  POST /api/cloud/usage/report  — 上报一次用量事件 / Report a usage event
  GET  /api/cloud/usage/quota   — 查询用户配额 / Query user quota
"""

import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.i18n import _
from core.metering import TIER_QUOTAS, get_daily_history, get_monthly_usage, record_usage
from core.users import find_or_create_sms_user, get_user_by_id, set_user_subscription

logger = logging.getLogger(__name__)

# ============================================================
# 配置 / Configuration
# ============================================================

CLOUD_API_TOKEN = os.getenv("CLOUD_API_TOKEN", "").strip()
CLOUD_SIGN_TTL = int(os.getenv("CLOUD_SIGN_TTL", "300"))  # 签名有效期（秒） / Signature validity (seconds)

router = APIRouter(prefix="/api/cloud", tags=["云端用户服务"])


# ============================================================
# 签名校验 / Signature Verification
# ============================================================


def _verify_signature(timestamp: str, sign: str) -> bool:
    """校验请求签名 / Verify request signature.

    Args:
        timestamp: 请求时间戳（Unix 秒） / Request timestamp (Unix seconds)
        sign: 请求签名 / Request signature

    Returns:
        校验通过返回 True / True if verification passes
    """
    if not CLOUD_API_TOKEN:
        return False

    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    now = int(time.time())
    if abs(now - ts) > CLOUD_SIGN_TTL:
        logger.warning(f"云端 API 签名过期: timestamp={timestamp}, now={now}, ttl={CLOUD_SIGN_TTL}")
        return False

    expected = hmac.new(
        CLOUD_API_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(sign, expected)


def _check_cloud_auth(request: Request) -> None:
    """校验请求的 HMAC 签名，失败时抛出 HTTPException / Verify HMAC signature; raise HTTPException on failure."""
    if not CLOUD_API_TOKEN:
        raise HTTPException(500, _("Cloud API not configured (CLOUD_API_TOKEN)"))

    timestamp = request.headers.get("X-Cloud-Timestamp", "")
    sign = request.headers.get("X-Cloud-Sign", "")

    if not timestamp or not sign:
        raise HTTPException(401, _("Missing auth headers X-Cloud-Timestamp / X-Cloud-Sign"))

    if not _verify_signature(timestamp, sign):
        raise HTTPException(401, _("Signature verification failed"))


# ============================================================
# 请求模型 / Request Models
# ============================================================


class SyncUserRequest(BaseModel):
    """桌面端 SMS 登录后同步用户 / Sync user after desktop SMS login."""
    user_id: str = Field(..., description="桌面端生成的用户 ID / Desktop-generated user ID")
    phone: str = Field(..., description="手机号 / Phone number")
    name: str = Field(default="", description="用户名称 / User name")
    created_at: str = Field(default="", description="用户创建时间 / User creation time")


class ReportUsageRequest(BaseModel):
    """上报用量事件 / Report usage event."""
    user_id: str = Field(..., description="用户 ID / User ID")
    service: str = Field(..., description="服务类型: asr_batch / asr_realtime / llm_summary / Service type")
    duration_seconds: float = Field(..., description="音频时长（秒） / Audio duration (seconds)")
    task_id: str = Field(default=None, description="关联任务 ID / Associated task ID")


# ============================================================
# 端点 / Endpoints
# ============================================================


@router.post("/users/sync")
def cloud_sync_user(req: SyncUserRequest, request: Request):
    """
    桌面端 SMS 登录后同步用户到云端 / Sync user to cloud after desktop SMS login.

    在服务器 data/users.json 中创建或更新用户记录，使管理后台可见。
    Create or update user record in server's data/users.json; makes user visible to admin panel.
    """
    _check_cloud_auth(request)

    phone = req.phone.strip()
    if not phone:
        raise HTTPException(400, "phone is required")

    # 在服务器创建/查找 SMS 用户 / Create/find SMS user on server
    user = find_or_create_sms_user(phone)

    # 确保用户数据完整 / Ensure user data is complete
    if req.name and user.get("name") != req.name:
        user["name"] = req.name

    # 返回配额信息 / Return quota info
    subscription = user.get("subscription", {"tier": "free"})
    tier = subscription.get("tier", "free")
    quota = TIER_QUOTAS.get(tier, 0)

    month_key = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m")
    used = get_monthly_usage(user["id"], month_key)
    remaining = max(0, quota - used)

    logger.info(
        f"云端用户同步: phone={phone[:3]}****{phone[-4:]}, "
        f"user_id={user['id'][:8]}, tier={tier}, used={used}min, remaining={remaining}min"
    )

    return {
        "user_id": user["id"],
        "tier": tier,
        "quota": quota,
        "used": round(used, 1),
        "remaining": round(remaining, 1),
    }


@router.post("/usage/report")
def cloud_report_usage(req: ReportUsageRequest, request: Request):
    """
    桌面端上报用量事件 / Desktop client reports usage event.

    写入服务器 data/usage/ JSONL，作为权威用量记录。
    Write to server's data/usage/ JSONL as authoritative usage record.
    """
    _check_cloud_auth(request)

    user = get_user_by_id(req.user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    # 调用已有的 record_usage 写入服务器 JSONL / Use existing record_usage to write to server JSONL
    result = record_usage(
        user_id=req.user_id,
        service=req.service,
        duration_seconds=req.duration_seconds,
        task_id=req.task_id,
    )

    logger.info(
        f"云端用量上报: user={req.user_id[:8]}, service={req.service}, "
        f"+{result['minutes']}min, 月累计={result['cumulative_monthly']}min, "
        f"剩余={result['remaining']}min"
    )

    return {
        "minutes": result["minutes"],
        "cumulative": result["cumulative_monthly"],
        "remaining": result["remaining"],
        "quota": result["quota"],
    }


@router.get("/usage/quota")
def cloud_check_quota(
    request: Request,
    user_id: str = Query(..., description="用户 ID / User ID"),
    estimated_minutes: float = Query(0, description="预估消耗（可选） / Estimated consumption (optional)"),
):
    """
    桌面端查询用户配额 / Desktop client queries user quota.

    返回云端权威的配额信息（含逐日用量明细）。
    Return cloud-authoritative quota info (incl. daily usage details).
    """
    _check_cloud_auth(request)

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    subscription = user.get("subscription", {"tier": "free"})
    tier = subscription.get("tier", "free")
    quota = TIER_QUOTAS.get(tier, 0)

    # 非计量用户直接放行 / Non-metered users pass through
    if tier not in TIER_QUOTAS:
        return {
            "allowed": True,
            "used": 0,
            "remaining": -1,
            "quota": -1,
            "tier": tier,
            "daily_history": [],
        }

    month_key = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m")
    used = get_monthly_usage(user_id, month_key)
    remaining = max(0, quota - used)
    allowed = remaining > estimated_minutes

    # 最近 7 天用量明细 / Last 7 days usage details
    daily = get_daily_history(user_id, days=7)

    return {
        "allowed": allowed,
        "used": round(used, 1),
        "remaining": round(remaining, 1),
        "quota": quota,
        "tier": tier,
        "daily_history": daily,
    }
