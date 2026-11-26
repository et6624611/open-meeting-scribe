"""
core/time_query.py — 提问时间表达的规则解析 / Rule-based time expression parsing

背景（context-asset-management R1）：「本月 / 10月 / 9月」曾被当成普通词元参与关键词
匹配，既不做相对时间换算，也不按 meeting_date 过滤，导致同一会话三个统计口径互相矛盾。
本模块只做确定性规则解析，**不调用 LLM**，解析不出就返回 ``kind="none"``，
绝不默认当月。

契约见 docs/specs/context-asset-management/spec.md §5.3：

    parse_time_range(query, now=None) -> {kind, start, end, label}

    kind: "range" | "recent_count" | "none"
    start/end: ISO 日期字符串，左闭右开
    label: 用于回显与块头，如 "2026-11"
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# 「最近 3 次 / 近 5 场」：数量检索，不做日期过滤
_RECENT_COUNT_RE = re.compile(r"(?:最近|近)\s*(\d+)\s*[次场]")
# 「近 7 天 / 最近 30 天」
_RECENT_DAYS_RE = re.compile(r"(?:最近|近)\s*(\d+)\s*天")
# 完整日期 YYYY-MM-DD / YYYY/M/D / YYYY年M月D日
_FULL_DATE_RE = re.compile(
    r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*日?"
)
# 年月 YYYY-MM / YYYY年M月
_YEAR_MONTH_RE = re.compile(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*月?")
# 单独 N 月 / N 月份：只认不是紧跟在数字/年/个后面的月份
_MONTH_RE = re.compile(r"(?<![\d年个])(\d{1,2})\s*月份?")

# 相对表达按「最长优先」手工排序，避免「上个月」被「上月」抢先
_RELATIVE_MONTHS = (
    (("这个月", "当月", "本月"), 0),
    (("上个月", "上月"), -1),
)
_QUARTERS = (
    (("这季度", "本季度"), 0),
    (("上季度",), -1),
)
_WEEKS = (
    (("这周", "本周"), 0),
    (("上周",), -1),
)

_NONE = {"kind": "none", "start": None, "end": None, "label": "未限定"}


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _quarter_start_month(month: int) -> int:
    return ((month - 1) // 3) * 3 + 1


def _quarter_bounds(year: int, start_month: int) -> tuple[str, str]:
    start = date(year, start_month, 1)
    ny, nm = _shift_month(year, start_month, 3)
    end = date(ny, nm, 1)
    return start.isoformat(), end.isoformat()


def _week_bounds(day: date) -> tuple[str, str]:
    monday = day - timedelta(days=day.weekday())
    return monday.isoformat(), (monday + timedelta(days=7)).isoformat()


def _range(start: str, end: str, label: str) -> dict:
    return {"kind": "range", "start": start, "end": end, "label": label}


def parse_time_range(query: str, now: date | None = None) -> dict:
    """从自然语言提问中解析时间范围。

    返回 ``{kind, start, end, label}``；``kind="recent_count"`` 时额外带 ``limit``。
    无时间表达返回 ``kind="none"``，调用方不得把它当成「本月」。
    """
    text = str(query or "").strip()
    if not text:
        return dict(_NONE)
    today = now or date.today()

    # 1) 最近 N 次 / N 场：数量检索，不做日期过滤
    match = _RECENT_COUNT_RE.search(text)
    if match:
        return {
            "kind": "recent_count",
            "start": None,
            "end": None,
            "limit": int(match.group(1)),
            "label": f"最近 {int(match.group(1))} 场",
        }

    # 2) 近 N 天
    match = _RECENT_DAYS_RE.search(text)
    if match:
        days = int(match.group(1))
        start = today - timedelta(days=days)
        end = today + timedelta(days=1)
        return _range(start.isoformat(), end.isoformat(), f"近 {days} 天")

    # 3) 完整日期（先于年月，避免被截成月度）
    match = _FULL_DATE_RE.search(text)
    if match:
        try:
            day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            day = None
        if day is not None:
            return _range(day.isoformat(), (day + timedelta(days=1)).isoformat(), day.isoformat())

    # 4) 年月 YYYY-MM / YYYY年M月
    match = _YEAR_MONTH_RE.search(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            start, end = _month_bounds(year, month)
            return _range(start, end, f"{year:04d}-{month:02d}")

    # 5) 本月 / 上月
    for words, delta in _RELATIVE_MONTHS:
        if any(w in text for w in words):
            year, month = _shift_month(today.year, today.month, delta)
            start, end = _month_bounds(year, month)
            return _range(start, end, f"{year:04d}-{month:02d}")

    # 6) 本季度 / 上季度
    for words, delta in _QUARTERS:
        if any(w in text for w in words):
            year, month = today.year, today.month
            if delta:
                year, month = _shift_month(year, _quarter_start_month(month), delta * 3)
            start_month = _quarter_start_month(month)
            start, end = _quarter_bounds(year, start_month)
            return _range(start, end, f"{year}Q{(start_month - 1) // 3 + 1}")

    # 7) 本周 / 上周
    for words, delta in _WEEKS:
        if any(w in text for w in words):
            start, end = _week_bounds(today + timedelta(days=delta * 7))
            return _range(start, end, f"{start}..{end}")

    # 8) 单独 N 月：当年该月；若晚于当前月，回落上一年
    match = _MONTH_RE.search(text)
    if match:
        month = int(match.group(1))
        if 1 <= month <= 12:
            year = today.year if month <= today.month else today.year - 1
            start, end = _month_bounds(year, month)
            return _range(start, end, f"{year:04d}-{month:02d}")

    return dict(_NONE)


def in_range(day_text: str, time_range: dict | None) -> bool:
    """日期字符串是否落在解析结果内（左闭右开）。

    ``kind != "range"`` 时不做日期过滤；无日期在 range 下视为不命中。
    """
    if not time_range or time_range.get("kind") != "range":
        return True
    day = str(day_text or "")[:10]
    if not day:
        return False
    return str(time_range.get("start")) <= day < str(time_range.get("end"))
