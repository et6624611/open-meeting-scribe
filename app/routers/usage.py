"""
app/routers/usage.py — 用量查询 API / Usage query API

端点 / Endpoints:
  GET /api/usage/summary   → 本月汇总（底部状态栏用） / Monthly summary (for bottom status bar)
  GET /api/usage/history   → 逐日明细（设置页图表用） / Daily details (for settings page chart)
  GET /api/usage/check     → 配额预检（任务开始前调用） / Quota pre-check (called before task starts)
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from core.i18n import _
from core.metering import (
    DEFAULT_QUOTA,
    check_quota,
    get_daily_history,
    get_monthly_usage,
    is_metered,
)
from core.users import get_current_user

router = APIRouter(prefix="/api/usage", tags=["用量"])


@router.get("/summary")
def usage_summary():
    """本月用量汇总（底部状态栏 + 设置页用量面板用） / Monthly usage summary (for bottom status bar + settings panel).

    云端启用时优先使用云端权威数据 / When cloud is enabled, prefer cloud-authoritative data.
    """
    user = get_current_user()
    if not user:
        return {"metered": False, "message": _("Not logged in")}

    if not is_metered():
        return {
            "metered": False,
            "message": _("Self-hosted Key, not metered"),
            "quota": user.get("quota", DEFAULT_QUOTA),
        }

    month_key = datetime.now(timezone.utc).strftime("%Y-%m")

    # 云端优先：从云端获取权威用量数据 / Cloud-first: get authoritative usage data from cloud
    from core.cloud_client import check_quota_from_cloud, is_cloud_enabled
    if is_cloud_enabled():
        cloud_result = check_quota_from_cloud(user["id"])
        if cloud_result:
            used = cloud_result.get("used", 0)
            quota = cloud_result.get("quota", user.get("quota", DEFAULT_QUOTA))
            remaining = cloud_result.get("remaining", 0)
            pct = round(remaining / quota * 100) if quota > 0 else 0
            return {
                "metered": True,
                "month": month_key,
                "quota": quota,
                "used": round(used, 1),
                "remaining": round(remaining, 1),
                "percentage": pct,
            }
        # 云端不可达 → 降级到本地 / Cloud unreachable → fall back to local

    used = get_monthly_usage(user["id"], month_key)

    quota = user.get("quota", DEFAULT_QUOTA)
    remaining = max(0, quota - used)
    pct = round(remaining / quota * 100) if quota > 0 else 0

    return {
        "metered": True,
        "month": month_key,
        "quota": quota,
        "used": round(used, 1),
        "remaining": round(remaining, 1),
        "percentage": pct,
    }


@router.get("/history")
def usage_history(days: int = 30):
    """逐日用量明细（设置页图表用） / Daily usage details (for settings page chart)."""
    user = get_current_user()
    if not user:
        return {"history": []}
    return {"history": get_daily_history(user["id"], days)}


@router.get("/check")
def quota_check(estimated_minutes: float = 0):
    """配额预检 / Quota pre-check."""
    user = get_current_user()
    if not user:
        return {"allowed": True, "metered": False}

    result = check_quota(user["id"], estimated_minutes)
    result["metered"] = is_metered()
    return result
