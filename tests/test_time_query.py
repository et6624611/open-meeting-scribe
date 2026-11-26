"""时间表达解析单测（规则实现，不调 LLM）。"""
from datetime import date

from core.time_query import in_range, parse_time_range

NOW = date(2026, 11, 26)


def test_this_month():
    result = parse_time_range("本月与星瀚项目相关有哪些关键决策？", NOW)
    assert result == {"kind": "range", "start": "2026-11-01", "end": "2026-12-01", "label": "2026-11"}


def test_aliases_for_this_month():
    for text in ("这个月", "当月"):
        assert parse_time_range(text, NOW)["start"] == "2026-11-01"


def test_last_month():
    result = parse_time_range("上个月怎么样", NOW)
    assert result["start"] == "2026-10-01"
    assert result["end"] == "2026-11-01"
    assert result["label"] == "2026-10"


def test_month_number_falls_back_to_previous_year():
    assert parse_time_range("10月呢", NOW)["start"] == "2026-10-01"
    assert parse_time_range("9月呢", NOW)["start"] == "2026-09-01"
    # 12 月晚于当前 11 月 → 回落 2025
    result = parse_time_range("12月", NOW)
    assert result["start"] == "2025-12-01"
    assert result["end"] == "2026-01-01"


def test_year_month_and_full_date():
    assert parse_time_range("2026-03 的决策", NOW)["start"] == "2026-03-01"
    assert parse_time_range("2026年3月", NOW)["label"] == "2026-03"
    full = parse_time_range("2026-11-02 说了什么", NOW)
    assert full == {"kind": "range", "start": "2026-11-02", "end": "2026-11-03", "label": "2026-11-02"}


def test_quarters():
    this_q = parse_time_range("本季度复盘", NOW)
    assert (this_q["start"], this_q["end"]) == ("2026-10-01", "2027-01-01")
    last_q = parse_time_range("上季度", NOW)
    assert (last_q["start"], last_q["end"]) == ("2026-07-01", "2026-10-01")


def test_weeks():
    this_week = parse_time_range("这周", NOW)
    assert (this_week["start"], this_week["end"]) == ("2026-11-23", "2026-11-30")
    last_week = parse_time_range("上周", NOW)
    assert (last_week["start"], last_week["end"]) == ("2026-11-16", "2026-11-23")


def test_recent_days_and_recent_count():
    days = parse_time_range("最近 7 天", NOW)
    assert (days["start"], days["end"]) == ("2026-11-19", "2026-11-27")
    count = parse_time_range("最近 3 场", NOW)
    assert count["kind"] == "recent_count"
    assert count["limit"] == 3
    assert count["start"] is None and count["end"] is None


def test_none_when_no_time_word_never_defaults_to_month():
    for text in ("星瀚项目有哪些决策", "随便聊聊", "下周三", "三季度目标", ""):
        result = parse_time_range(text, NOW)
        assert result["kind"] == "none"
        assert result["start"] is None and result["end"] is None
        assert result["label"] == "未限定"


def test_in_range_left_closed_right_open():
    time_range = parse_time_range("本月", NOW)
    assert in_range("2026-11-01", time_range) is True
    assert in_range("2026-11-30", time_range) is True
    assert in_range("2026-12-01", time_range) is False
    assert in_range("2026-10-31", time_range) is False
    # 无日期在 range 下排除；无范围时不过滤
    assert in_range("", time_range) is False
    assert in_range("", {"kind": "none"}) is True
