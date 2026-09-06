"""
app/routers/usage.py — 用量查询 API

端点：
  GET /api/usage/summary   → 本月汇总（底部状态栏用）
  GET /api/usage/history   → 逐日明细（设置页图表用）
  GET /api/usage/check     → 配额预检（任务开始前调用）
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from core.users import get_current_user
from core.metering import (
    get_monthly_usage, get_daily_history, check_quota,
    is_metered, TIER_QUOTAS,
)

router = APIRouter(prefix="/api/usage", tags=["用量"])


@router.get("/summary")
def usage_summary():
    """本月用量汇总（底部状态栏用）"""
    user = get_current_user()
    if not user:
        return {"metered": False, "message": "未登录"}

    if not is_metered():
        return {"metered": False, "message": "自带 Key，不计量"}

    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    used = get_monthly_usage(user["id"], month_key)

    subscription = user.get("subscription", {})
    tier = subscription.get("tier", "free")
    quota = TIER_QUOTAS.get(tier, 0)
    remaining = max(0, quota - used)
    pct = round(remaining / quota * 100) if quota > 0 else 0

    return {
        "metered": True,
        "tier": tier,
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
