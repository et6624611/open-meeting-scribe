"""
core/metering.py — 用量计量 / Usage metering

职责 / Responsibilities:
  1. 记录每次转写的用量事件（追加写入 JSONL） / Record usage events per transcription (append to JSONL)
  2. 按月汇总用量 / Monthly usage aggregation
  3. 预检配额是否充足 / Pre-check quota sufficiency
  4. 判断当前用户是否需要计量（自持 Key 则跳过） / Determine if current user needs metering (skip if self-hosted key)

设计决策 / Design decisions:
  - 实时转写按录制时长计量（后续优化为字节数） / Realtime transcription metered by recording duration (later optimize to byte count)
  - 体验期额度用尽后允许用户配置自有 Key 继续 / After trial quota exhausted, user can configure own key to continue
  - 月度额度跨月清零 / Monthly quota resets each month
  - v1 不做异常告警风控 / v1 does not implement anomaly alerting
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

USAGE_DIR = Path("data/usage")

# ─ 默认配额（分钟/月）── / Default quota (minutes/month) ──
# 本项目为个人开发者维护的开源软件，不提供商业订阅服务 / This is an open-source project maintained by an individual developer; no commercial subscription.
# 每位用户的配额可在管理后台独立调整，此表仅作为未设置配额时的默认值 / Per-user quota is adjustable in admin panel; this table is only the default fallback.
#
# 体验期共享 proxy 仅限通过国内手机号（SMS）注册的用户 / Trial shared proxy limited to users registered via domestic phone (SMS).
# 原因：开发者 API Key 部署在国内阿里云服务器，境外用户访问 / Reason: developer API Key deployed on domestic Alibaba Cloud server; overseas access
# 可能涉及 DashScope 服务区域限制与数据跨境合规问题 / may involve DashScope service region restrictions and cross-border data compliance.
# GitHub OAuth / 本地账户用户需自行配置 API Key / GitHub OAuth / local account users must configure their own API Key.
DEFAULT_QUOTA = 300  # 默认体验期配额（分钟/月） / Default trial quota (minutes/month)


def is_metered() -> bool:
    """
    判断当前用户是否需要计量（消耗体验期配额） / Check if current user needs metering (consumes trial quota).

    体验期共享 proxy 仅限通过国内手机号（SMS）注册的用户 / Trial shared proxy limited to SMS-registered users,
    因为开发者 API Key 部署在国内阿里云服务器 / because developer API Key is deployed on domestic Alibaba Cloud.
    GitHub OAuth / 本地账户用户需自行配置 API Key，不走计量 / GitHub OAuth / local users must use own key; not metered.

    Returns:
        True = 需要计量（SMS 注册用户，消耗体验期配额） / Needs metering (SMS user, consumes trial quota)
        False = 未登录 / 非 SMS 用户（需自持 Key） / Not logged in / non-SMS user (must use own key)

    REQ-ACCESS-MODE-CARDS AC-T2②：local（离线接入）不计量——离线模式数据不出本机、
    不触达任何计费通道，即使 SMS 注册用户处于 local 路由也不扣配额。
    """
    # local 不计量（判定唯一入口 core/routing，不额外读 engine.mode/prefer_subscription）
    try:
        from core.routing import get_routing_decision
        if get_routing_decision("asr")["route"] == "local":
            return False
    except Exception:
        pass

    from core.users import get_current_user

    user = get_current_user()
    if not user:
        return False  # 未登录 = 本地模式，不计量 / Not logged in = local mode, not metered

    # 仅 SMS（国内手机号）注册用户可使用体验期共享 proxy / Only SMS (domestic phone) users can use trial shared proxy
    if user.get("provider") != "sms":
        return False  # GitHub OAuth / 本地账户 → 需自持 Key / GitHub OAuth / local account → must use own key

    # 有配额（显式或默认）→ 需要计量 / Has quota (explicit or default) → needs metering
    if user.get("quota") is not None:
        return user["quota"] > 0
    # 无显式配额时，SMS 用户使用默认配额 / No explicit quota: SMS users get default quota
    return DEFAULT_QUOTA > 0


def record_usage(
    user_id: str,
    service: str,          # "asr_batch" | "asr_realtime" | "llm_summary"  服务类型 / Service type
    duration_seconds: float,
    task_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """
    记录一次用量事件 / Record a usage event.

    Args:
        user_id: 用户 ID / User ID
        service: 服务类型 / Service type
        duration_seconds: 音频时长（秒） / Audio duration (seconds)
        task_id: 关联的任务 ID（可选） / Associated task ID (optional)
        metadata: 附加信息（模型名、厂商等） / Additional info (model name, vendor, etc.)

    Returns:
        本次用量记录 / This usage record {minutes, cumulative_monthly, remaining}
    """
    audio_minutes = round(duration_seconds / 60, 2)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "service": service,
        "duration_seconds": round(duration_seconds, 1),
        "audio_minutes": audio_minutes,
        "task_id": task_id,
        "metadata": metadata or {},
    }

    # 追加写入当月 JSONL / Append to monthly JSONL
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    log_path = USAGE_DIR / f"usage-{month_key}.jsonl"
    USAGE_DIR.mkdir(parents=True, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # 计算当月累计 / Calculate monthly cumulative
    cumulative = get_monthly_usage(user_id, month_key)
    quota = _get_user_quota(user_id)
    remaining = max(0, quota - cumulative)

    # 云端同步：上报用量，以云端返回的剩余配额为准 / Cloud sync: report usage; use cloud's remaining quota if available
    from core.cloud_client import is_cloud_enabled, report_usage_to_cloud
    if is_cloud_enabled():
        cloud_result = report_usage_to_cloud(user_id, service, duration_seconds, task_id)
        if cloud_result:
            remaining = cloud_result.get("remaining", remaining)
            cumulative = cloud_result.get("cumulative", cumulative)

    logger.info(
        f"用量记录: user={user_id[:8]}, service={service}, "
        f"+{audio_minutes}min, 月累计={cumulative}min, 剩余={remaining}min"
    )

    return {
        "minutes": audio_minutes,
        "cumulative_monthly": cumulative,
        "remaining": remaining,
        "quota": quota,
    }


def get_monthly_usage(user_id: str, month_key: str | None = None) -> float:
    """
    查询某用户某月的累计用量（分钟） / Query user's cumulative monthly usage (minutes).

    Args:
        user_id: 用户 ID / User ID
        month_key: "2026-09" 格式，默认当月 / "2026-09" format; defaults to current month

    Returns:
        累计分钟数 / Cumulative minutes
    """
    if month_key is None:
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")

    log_path = USAGE_DIR / f"usage-{month_key}.jsonl"
    if not log_path.exists():
        return 0.0

    total = 0.0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("user_id") == user_id:
                total += event.get("audio_minutes", 0)

    return round(total, 2)


def get_daily_history(user_id: str, days: int = 30) -> list[dict]:
    """
    查询逐日用量明细 / Query daily usage details.

    Returns:
        [{"date": "2026-09-05", "minutes": 45.5, "tasks": 3}, ...]
    """
    from collections import defaultdict
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    daily = defaultdict(lambda: {"minutes": 0.0, "tasks": 0})

    # 扫描最近 N 天的月份文件 / Scan month files for last N days
    months_needed = set()
    for d in range(days):
        day = now - timedelta(days=d)
        months_needed.add(day.strftime("%Y-%m"))

    for month_key in months_needed:
        log_path = USAGE_DIR / f"usage-{month_key}.jsonl"
        if not log_path.exists():
            continue
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("user_id") != user_id:
                    continue
                ts = event.get("timestamp", "")
                date_str = ts[:10]  # "2026-09-05"
                daily[date_str]["minutes"] += event.get("audio_minutes", 0)
                if event.get("task_id"):
                    daily[date_str]["tasks"] += 1

    # 转为列表并按日期排序 / Convert to list and sort by date
    result = [
        {"date": date, "minutes": round(v["minutes"], 1), "tasks": v["tasks"]}
        for date, v in sorted(daily.items())
    ]
    return result[-days:]  # 只返回最近 N 天 / Return last N days only


def check_quota(user_id: str, estimated_minutes: float = 0) -> dict:
    """
    配额预检 / Quota pre-check. 在任务开始前调用，判断是否有足够配额 / Called before task starts to check if quota is sufficient.

    云端启用时优先查询云端配额，云端不可达则降级到本地 / When cloud is enabled, prefer cloud quota; fall back to local if unreachable.

    Args:
        user_id: 用户 ID / User ID
        estimated_minutes: 预估消耗（可选，用于提前预警） / Estimated consumption (optional, for early warning)

    Returns:
        {
            "allowed": bool,
            "remaining": float,
            "quota": float,
            "used": float,
            "warning": str | None,  # "low" | "critical" | None
        }
    """
    from core.users import get_user_by_id

    user = get_user_by_id(user_id)
    if not user:
        return {"allowed": True, "remaining": -1, "quota": -1, "used": 0, "warning": None}

    # 不需要计量的用户直接放行 / Non-metered users pass through
    user_quota = user.get("quota")
    if user_quota is not None and user_quota <= 0:
        return {"allowed": False, "remaining": 0, "quota": 0, "used": 0, "warning": "critical"}
    # 无显式配额时，非 SMS 用户不计量 / No explicit quota: non-SMS users not metered
    if user_quota is None and user.get("provider") != "sms":
        return {"allowed": True, "remaining": -1, "quota": -1, "used": 0, "warning": None}

    # 云端优先：从云端查询配额 / Cloud-first: query quota from cloud
    from core.cloud_client import check_quota_from_cloud, is_cloud_enabled
    if is_cloud_enabled():
        cloud_result = check_quota_from_cloud(user_id, estimated_minutes)
        if cloud_result:
            used = cloud_result.get("used", 0)
            quota = cloud_result.get("quota", 0)
            remaining = cloud_result.get("remaining", 0)
            pct = remaining / quota if quota > 0 else 0
            warning = None
            if pct < 0.1:
                warning = "critical"
            elif pct < 0.2:
                warning = "low"
            return {
                "allowed": cloud_result.get("allowed", remaining > estimated_minutes),
                "remaining": round(remaining, 1),
                "quota": quota,
                "used": round(used, 1),
                "warning": warning,
            }
        # 云端不可达 → 降级到本地逻辑 / Cloud unreachable → fall back to local logic

    # 本地计量 / Local metering
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    used = get_monthly_usage(user_id, month_key)
    quota = user.get("quota", DEFAULT_QUOTA)
    remaining = max(0, quota - used)
    pct = remaining / quota if quota > 0 else 0

    warning = None
    if pct < 0.1:
        warning = "critical"
    elif pct < 0.2:
        warning = "low"

    allowed = remaining > estimated_minutes

    return {
        "allowed": allowed,
        "remaining": round(remaining, 1),
        "quota": quota,
        "used": round(used, 1),
        "warning": warning,
    }


def _get_user_quota(user_id: str) -> int:
    """获取用户的月度配额 / Get user's monthly quota.

    优先读取用户显式 quota 字段，未设置时使用默认值 / Prefer user's explicit quota field; fall back to default.
    """
    from core.users import get_user_by_id
    user = get_user_by_id(user_id)
    if not user:
        return 0
    if user.get("quota") is not None:
        return user["quota"]
    return DEFAULT_QUOTA
