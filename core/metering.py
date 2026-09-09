"""
core/metering.py — 用量计量

职责：
  1. 记录每次转写的用量事件（追加写入 JSONL）
  2. 按月汇总用量
  3. 预检配额是否充足
  4. 判断当前用户是否需要计量（自带 Key 则跳过）

设计决策（已确认）：
  - 实时转写按录制时长计量（后续优化为字节数）
  - 体验版额度用尽后允许用户配置自有 Key 继续
  - 团队版先扣共享池，超出后扣个人额度（v1 暂不实现共享池）
  - 月度额度跨月清零
  - v1 不做异常告警风控
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

USAGE_DIR = Path("data/usage")

# ── 订阅档位配额（分钟/月）──
TIER_QUOTAS = {
    "free":       300,    # 体验版
    "personal":   1500,   # 个人版
    "pro":        5000,   # 专业版
    "team":       3000,   # 团队版（每人）
}


def is_metered() -> bool:
    """
    判断当前用户是否需要计量。

    代理模式下（详见 docs/adr/0012），所有 ASR 请求通过云端代理中转，
    客户端不再持有 API Key，因此所有已登录用户均走计量模式。

    Returns:
        True = 需要计量（消耗平台配额）
        False = 未登录（本地模式）
    """
    from core.users import get_current_user

    user = get_current_user()
    if not user:
        return False  # 未登录 = 本地模式，不计量

    # 有订阅信息且档位为有效档位 → 需要计量
    subscription = user.get("subscription", {})
    return subscription.get("tier") in TIER_QUOTAS


def record_usage(
    user_id: str,
    service: str,          # "asr_batch" | "asr_realtime" | "llm_summary"
    duration_seconds: float,
    task_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """
    记录一次用量事件。

    Args:
        user_id: 用户 ID
        service: 服务类型
        duration_seconds: 音频时长（秒）
        task_id: 关联的任务 ID（可选）
        metadata: 附加信息（模型名、厂商等）

    Returns:
        本次用量记录 {minutes, cumulative_monthly, remaining}
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

    # 追加写入当月 JSONL
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    log_path = USAGE_DIR / f"usage-{month_key}.jsonl"
    USAGE_DIR.mkdir(parents=True, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # 计算当月累计
    cumulative = get_monthly_usage(user_id, month_key)
    quota = _get_user_quota(user_id)
    remaining = max(0, quota - cumulative)

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
    查询某用户某月的累计用量（分钟）。

    Args:
        user_id: 用户 ID
        month_key: "2026-09" 格式，默认当月

    Returns:
        累计分钟数
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
    查询逐日用量明细。

    Returns:
        [{"date": "2026-09-05", "minutes": 45.5, "tasks": 3}, ...]
    """
    from collections import defaultdict
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    daily = defaultdict(lambda: {"minutes": 0.0, "tasks": 0})

    # 扫描最近 N 天的月份文件
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

    # 转为列表并按日期排序
    result = [
        {"date": date, "minutes": round(v["minutes"], 1), "tasks": v["tasks"]}
        for date, v in sorted(daily.items())
    ]
    return result[-days:]  # 只返回最近 N 天


def check_quota(user_id: str, estimated_minutes: float = 0) -> dict:
    """
    配额预检。在任务开始前调用，判断是否有足够配额。

    Args:
        user_id: 用户 ID
        estimated_minutes: 预估消耗（可选，用于提前预警）

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

    # 不需要计量的用户直接放行
    subscription = user.get("subscription", {})
    tier = subscription.get("tier")
    if tier not in TIER_QUOTAS:
        return {"allowed": True, "remaining": -1, "quota": -1, "used": 0, "warning": None}

    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    used = get_monthly_usage(user_id, month_key)
    quota = TIER_QUOTAS.get(tier, 0)
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
    """获取用户的月度配额"""
    from core.users import get_user_by_id
    user = get_user_by_id(user_id)
    if not user:
        return 0
    tier = user.get("subscription", {}).get("tier", "free")
    return TIER_QUOTAS.get(tier, 0)
