"""确定性统计（白名单聚合）单测。"""
from datetime import date

import pytest

from core import meeting_facts, meeting_search
from core.meeting_facts import aggregate_facts, classify_query
from core.meeting_search import build_scope_context

NOW = date(2026, 11, 26)


@pytest.fixture(autouse=True)
def _clean_tasks(monkeypatch):
    """每个用例使用独立任务集，避免其他测试残留污染计数。"""
    monkeypatch.setattr(meeting_search, "tasks", {})


def _task(**overrides):
    task = {
        "title": "未命名",
        "summary": "",
        "decisions": [],
        "dialogue": [],
        "meeting_date": "2026-11-01",
    }
    task.update(overrides)
    return task


def test_classify_query():
    assert classify_query("本月与星瀚项目相关有哪些关键决策？") == "retrieval"
    assert classify_query("本月关键决策") == "retrieval"
    assert classify_query("本月几场") == "aggregate"
    assert classify_query("多少待决策") == "aggregate"
    assert classify_query("本月有几场会议讨论了星瀚") == "mixed"
    assert classify_query("随便聊聊") == "retrieval"


def test_meeting_count_is_exact_and_includes_current_meeting(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_1", _task(meeting_date="2026-11-03"))
    monkeypatch.setitem(meeting_search.tasks, "t_2", _task(meeting_date="2026-10-03"))
    monkeypatch.setitem(meeting_search.tasks, "t_3", _task(meeting_date="2026-11-20"))

    facts = aggregate_facts("本月几场", now=NOW)
    assert facts == [{
        "kind": "meeting_count",
        "value": 2,
        "unit": "meeting",
        "status": "ok",
        "time_range": "2026-11-01..2026-12-01",
        "time_label": "2026-11",
        "filters": {},
    }]

    # 聚合包含符合条件的本场会议，不受检索 exclude 影响
    _block, retrieval = build_scope_context(
        "all", "本月几场", now=NOW, exclude_task_id="t_1")
    assert retrieval["verified_facts"][0]["value"] == 2
    assert retrieval["searched"] is False
    assert retrieval["candidates"] == 0
    assert retrieval["matched"] == 0
    assert retrieval["injected"] == 0


def test_decision_count_total_and_status_filter(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_1", _task(decisions=[
        {"id": "d1", "text": "采用方案 B", "status": "done"},
        {"id": "d2", "text": "采用方案 A", "status": "superseded"},
    ]))
    monkeypatch.setitem(meeting_search.tasks, "t_2", _task(decisions=[
        {"id": "d3", "text": "补齐灰度方案", "status": "to_decide"},
    ]))

    assert aggregate_facts("有多少条决策", now=NOW)[0]["value"] == 3
    assert aggregate_facts("多少待决策", now=NOW)[0]["value"] == 1
    assert aggregate_facts("多少已替代", now=NOW)[0]["value"] == 1


def test_decision_count_group_by_status(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_1", _task(decisions=[
        {"id": "d1", "text": "采用方案 B", "status": "done"},
        {"id": "d2", "text": "补齐灰度", "status": "to_decide"},
        {"id": "d3", "text": "上线时间", "status": "to_decide"},
    ]))

    fact = aggregate_facts("各状态分别有多少条决策", now=NOW)[0]
    assert fact["kind"] == "decision_count"
    assert fact["value"] == 3
    groups = {g["status"]: g["value"] for g in fact["groups"]}
    assert groups["to_decide"] == 2
    assert groups["done"] == 1
    assert groups["in_progress"] == 0


def test_aggregate_ignores_limit_and_idf(monkeypatch):
    for i in range(5):
        monkeypatch.setitem(meeting_search.tasks, f"t_{i}", _task(
            decisions=[{"id": f"d{i}", "text": "待定事项", "status": "to_decide"}]))

    _block, retrieval = build_scope_context(
        "all", "有多少待决策", now=NOW, limit=1)
    assert retrieval["verified_facts"][0]["value"] == 5
    assert retrieval["injected"] == 0
    assert "verified_facts" in _block
    assert "<verified_facts>" in _block


def test_aggregate_failure_is_error_not_zero(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_1", _task(decisions=[
        {"id": "d1", "text": "采用方案 B", "status": "done"},
    ]))

    def _boom():
        raise RuntimeError("statuses unavailable")

    monkeypatch.setattr(meeting_facts, "load_statuses", _boom)
    monkeypatch.setattr("core.decision_status.load_statuses", _boom)
    with pytest.raises(RuntimeError):
        aggregate_facts("多少条决策", now=NOW)

    block, retrieval = build_scope_context("all", "多少条决策", now=NOW)
    assert block == ""
    assert retrieval["status"] == "error"
    assert retrieval["error_kind"] == "aggregation"
    assert retrieval["candidates"] is None
    assert retrieval["matched"] is None
    assert retrieval["injected"] is None
    assert retrieval["verified_facts"] == []


def test_empty_collection_returns_zero_not_error(monkeypatch):
    facts = aggregate_facts("本月几场", now=NOW)
    assert facts[0]["value"] == 0
    assert facts[0]["status"] == "ok"
