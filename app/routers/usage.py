"""
app/routers/usage.py — 用量查询 API

端点：
  GET /api/usage/summary   → 本月汇总（底部状态栏用）
  GET /api/usage/history   → 逐日明细（设置页图表用）
  GET /api/usage/check     → 配额预检（任务开始前调用）
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from core.i18n import _
from core.metering import (
    TIER_QUOTAS,
    check_quota,
    get_daily_history,
    get_monthly_usage,
    is_metered,
)
from core.users import get_current_user

router = APIRouter(prefix="/api/usage", tags=["用量"])


@router.get("/summary")
def usage_summary():
    """本月用量汇总（底部状态栏 + 设置页用量面板用）"""
    user = get_current_user()
    if not user:
        return {"metered": False, "message": _("Not logged in")}

    subscription = user.get("subscription", {})
    tier = subscription.get("tier", "free")
    TIER_NAMES = {"free": "体验期"}

    if not is_metered():
        return {
            "metered": False,
            "message": _("Self-hosted Key, not metered"),
            "tier": tier,
            "tier_name": TIER_NAMES.get(tier, tier),
            "quota": TIER_QUOTAS.get(tier, 0),
        }

    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    used = get_monthly_usage(user["id"], month_key)

    quota = TIER_QUOTAS.get(tier, 0)
    remaining = max(0, quota - used)
    pct = round(remaining / quota * 100) if quota > 0 else 0

    return {
        "metered": True,
        "tier": tier,
        "tier_name": TIER_NAMES.get(tier, tier),
        "month": month_key,
        "quota": quota,
        "used": round(used, 1),
        "remaining": round(remaining, 1),
        "percentage": pct,
    }


@router.get("/history")
def usage_history(days: int = 30):
    """逐日用量明细（设置页图表用）"""
    user = get_current_user()
    if not user:
        return {"history": []}
    return {"history": get_daily_history(user["id"], days)}


@router.get("/check")
def quota_check(estimated_minutes: float = 0):
    """配额预检"""
    user = get_current_user()
    if not user:
        return {"allowed": True, "metered": False}

    result = check_quota(user["id"], estimated_minutes)
    result["metered"] = is_metered()
    return result
