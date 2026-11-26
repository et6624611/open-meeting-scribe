"""跨会议关键词检索单测（提问范围唯一检索器）。

契约见 docs/specs/context-asset-management/spec.md：
三计数、时间/项目过滤、IDF 阈值、结构化块与证据锚点。
"""
from datetime import date

import pytest

from core import meeting_search
from core.meeting_search import (
    build_scope_context,
    normalize_scope,
    search_meeting_list,
    search_meetings,
)


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


def _dialogue(*lines):
    return [{"sentences": [{"text": line} for line in lines]}]


def _seed_fillers(monkeypatch, count=20, date_text="2026-08-01"):
    for i in range(count):
        monkeypatch.setitem(meeting_search.tasks, f"filler_{i}", _task(
            title=f"例行同步 {i}", summary="例行同步与进度对齐", meeting_date=date_text))


def test_normalize_scope_defaults_to_meeting():
    assert normalize_scope(None) == "meeting"
    assert normalize_scope("project") == "meeting"
    assert normalize_scope("x") == "meeting"
    assert normalize_scope("all") == "all"


def test_title_hit_ranks_above_dialogue(monkeypatch):
    _seed_fillers(monkeypatch, 50)
    monkeypatch.setitem(meeting_search.tasks, "t_title", _task(
        title="预算评审会", summary="讨论预算", meeting_date="2026-11-02"))
    monkeypatch.setitem(meeting_search.tasks, "t_dialogue", _task(
        title="周会", dialogue=_dialogue("预算还需要再核对一次预算"), meeting_date="2026-11-03"))

    hits = search_meetings("预算")
    ids = [h["task_id"] for h in hits]
    assert "t_title" in ids and "t_dialogue" in ids
    assert ids.index("t_title") < ids.index("t_dialogue")


def test_exclude_task_id_and_empty_text(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(
        title="发布计划", summary="发布节奏讨论"))
    monkeypatch.setitem(meeting_search.tasks, "t_empty", _task(title=""))

    hits = search_meetings("发布", exclude_task_id="t_a")
    assert hits == []


def test_meeting_scope_returns_disabled_state(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(
        title="发布计划", summary="发布节奏讨论"))

    block, retrieval = build_scope_context("meeting", "发布")
    assert block == ""
    assert retrieval["status"] == "disabled"
    assert retrieval["searched"] is False
    assert retrieval["hits"] == 0
    assert retrieval["candidates"] == 0
    assert retrieval["matched"] == 0
    assert retrieval["injected"] == 0
    assert retrieval["time_range"] == "none"
    assert retrieval["time_label"] == "未限定"
    assert retrieval["verified_facts"] == []


def test_all_scope_returns_structured_block(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(
        title="发布计划", summary="发布节奏讨论"))

    block, retrieval = build_scope_context("all", "发布")
    assert block.startswith("<retrieval ")
    assert 'scope="all"' in block
    assert 'status="ok"' in block
    assert 'query_kind="retrieval"' in block
    assert 'time_range="none"' in block
    assert 'time_label="未限定"' in block
    assert "检索问题：发布" in block
    assert retrieval["searched"] is True
    assert retrieval["matched"] == 1
    assert retrieval["meetings"][0]["task_id"] == "t_a"


def test_decision_intent_puts_decision_evidence_first(monkeypatch):
    _seed_fillers(monkeypatch, 3)
    monkeypatch.setitem(meeting_search.tasks, "t_decide", _task(
        title="会计事件库方案讨论",
        summary="讨论会计事件库的定位、范围与协同方式，涉及多个业务线。",
        decisions=[{"id": "d1", "text": "决定启用会计事件库模块", "status": "done", "assignee": "财务组"}],
    ))

    hits = search_meetings("是否决定采用会计事件库")
    assert hits
    lines = hits[0]["lines"]
    assert lines[0]["label"] == "决策项："
    assert "决定启用会计事件库模块" in lines[0]["text"]
    assert lines[0]["evidence"]["asset_type"] == "decision"
    summary_like = [line for line in lines if line["label"] == "纪要摘录："]
    assert len(summary_like) == 1


def test_three_counts_report_total_and_injected(monkeypatch):
    for i in range(6):
        monkeypatch.setitem(meeting_search.tasks, f"t_{i}", _task(
            title=f"发布计划 {i}", summary="发布节奏讨论"))

    block, retrieval = build_scope_context("all", "发布", limit=4)
    assert retrieval["candidates"] >= retrieval["matched"] >= retrieval["injected"]
    assert retrieval["matched"] == 6
    assert retrieval["injected"] == 4
    assert retrieval["hits"] == retrieval["matched"]
    assert retrieval["shown"] == retrieval["injected"]
    assert retrieval["truncated"] is True
    assert retrieval["dropped_reason"] == "limit"
    assert 'matched="6"' in block
    assert 'injected="4"' in block
    assert 'truncated="true"' in block
    assert 'dropped_reason="limit"' in block


def test_budget_truncates_without_losing_injected_evidence(monkeypatch):
    for i in range(3):
        monkeypatch.setitem(meeting_search.tasks, f"t_{i}", _task(
            title=f"发布计划 {i}", summary="发布节奏讨论" * 20))
    monkeypatch.setattr(meeting_search, "INJECT_MAX_CHARS", 60)

    block, retrieval = build_scope_context("all", "发布")
    assert retrieval["matched"] == 3
    assert retrieval["injected"] == 1
    assert retrieval["truncated"] is True
    assert retrieval["dropped_reason"] == "budget"
    assert len(retrieval["meetings"]) == 1
    assert retrieval["meetings"][0]["evidence"]


def test_time_range_filters_and_reports(monkeypatch):
    _seed_fillers(monkeypatch, 30)
    monkeypatch.setitem(meeting_search.tasks, "t_nov", _task(
        title="星瀚预算评审", summary="星瀚预算", meeting_date="2026-11-05"))
    monkeypatch.setitem(meeting_search.tasks, "t_oct", _task(
        title="星瀚预算评审", summary="星瀚预算", meeting_date="2026-10-05"))
    monkeypatch.setitem(meeting_search.tasks, "t_undated", _task(
        title="星瀚预算评审", summary="星瀚预算", meeting_date=""))
    monkeypatch.setitem(meeting_search.tasks["t_undated"], "created_at", "")

    _block, retrieval = build_scope_context(
        "all", "本月星瀚预算", now=date(2026, 11, 26), limit=10)
    assert retrieval["time_range"] == "2026-11-01..2026-12-01"
    assert retrieval["time_label"] == "2026-11"
    assert [m["task_id"] for m in retrieval["meetings"]] == ["t_nov"]
    assert retrieval["candidates"] == 1
    assert retrieval["undated_excluded"] == 1


def test_no_time_word_never_defaults_to_current_month(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_oct", _task(
        title="星瀚预算", summary="星瀚预算", meeting_date="2026-10-05"))

    _block, retrieval = build_scope_context("all", "星瀚预算", now=date(2026, 11, 26))
    assert retrieval["time_range"] == "none"
    assert retrieval["time_label"] == "未限定"
    assert retrieval["matched"] == 1


def test_project_filter_requires_known_project(monkeypatch):
    monkeypatch.setattr(
        "core.projects.list_projects",
        lambda: [{"id": "p1", "name": "星瀚"}, {"id": "p2", "name": "海外"}],
    )
    monkeypatch.setitem(meeting_search.tasks, "t_p1", _task(
        title="星瀚评审", summary="星瀚项目评审", project_id="p1"))
    monkeypatch.setitem(meeting_search.tasks, "t_p2", _task(
        title="星瀚评审", summary="星瀚项目评审", project_id="p2"))
    monkeypatch.setitem(meeting_search.tasks, "t_no_project", _task(
        title="星瀚评审", summary="星瀚项目评审"))

    _block, retrieval = build_scope_context("all", "星瀚评审", limit=10)
    assert retrieval["filters"] == {"project": "星瀚"}
    assert [m["task_id"] for m in retrieval["meetings"]] == ["t_p1"]


def test_evidence_anchor_matches_every_injected_meeting(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(
        title="发布计划",
        summary="发布节奏讨论",
        decisions=[{"id": "d1", "text": "决定周五发布", "status": "done"}],
        dialogue=_dialogue("发布前先回归"),
    ))

    block, retrieval = build_scope_context("all", "发布")
    meeting = retrieval["meetings"][0]
    assert meeting["evidence"]
    ids = [item["evidence_id"] for item in meeting["evidence"]]
    assert len(ids) == len(set(ids))
    for item in meeting["evidence"]:
        assert item["evidence_id"] == f"{item['task_id']}:{item['asset_type']}:{item['asset_id']}"
        assert item["excerpt"]
        assert f"[evidence:{item['evidence_id']}]" in block
    dialogue = [item for item in meeting["evidence"] if item["asset_type"] == "dialogue"]
    assert dialogue and dialogue[0]["locator"]["sentence_index"] == 0


def test_search_failure_returns_error_not_zero(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(title="发布计划"))

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(meeting_search, "_search_prepared", _boom)
    block, retrieval = build_scope_context("all", "发布")
    assert block == ""
    assert retrieval["status"] == "error"
    assert retrieval["error_kind"] == "retrieval"
    assert retrieval["candidates"] is None
    assert retrieval["matched"] is None
    assert retrieval["injected"] is None
    assert retrieval["hits"] == 0
    assert retrieval["shown"] == 0
    assert retrieval["meetings"] == []


# ============================================================
# 薄清单（工具分页）：渐进式下钻的第一级
# ============================================================

def _seed_term_hits(monkeypatch, count, term="预算", date_text="2026-11-05"):
    for i in range(count):
        monkeypatch.setitem(meeting_search.tasks, f"m_{i:03d}", _task(
            title=f"{term}评审 {i}", summary=f"{term}口径对齐", meeting_date=date_text))


def test_meeting_list_pages_without_overlap(monkeypatch):
    _seed_term_hits(monkeypatch, 25)

    first = search_meeting_list("预算", limit=10, offset=0)
    second = search_meeting_list("预算", limit=10, offset=10)
    third = search_meeting_list("预算", limit=10, offset=20)

    assert first["total"] == 25 and first["returned"] == 10 and first["has_more"] is True
    assert second["returned"] == 10 and second["has_more"] is True
    assert third["returned"] == 5 and third["has_more"] is False

    ids = [item["task_id"] for page in (first, second, third) for item in page["items"]]
    assert len(ids) == 25 and len(set(ids)) == 25


def test_meeting_list_is_compact_one_excerpt_per_meeting(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(
        title="预算评审",
        summary="预算口径讨论",
        decisions=[{"id": "d1", "text": "预算定 30 万"}, {"id": "d2", "text": "预算下月复核"}],
        dialogue=_dialogue("预算还要再核一次", "预算口径谁定"),
    ))

    result = search_meeting_list("预算")
    item = result["items"][0]
    assert item["task_id"] == "t_a"
    assert item["snippet"]
    # 薄清单不带证据链字段，避免一次调用把详情体积搬进上下文
    assert "evidence" not in item and "summary" not in item


def test_meeting_list_offset_beyond_total(monkeypatch):
    _seed_term_hits(monkeypatch, 3)
    result = search_meeting_list("预算", offset=100)
    assert result["returned"] == 0 and result["has_more"] is False


def test_meeting_list_time_filter_still_applies(monkeypatch):
    # IDF 需要足够语料量，否则单条命中过不了相关度阈值（与注入路径同口径）
    _seed_fillers(monkeypatch, 20)
    monkeypatch.setitem(meeting_search.tasks, "t_nov", _task(
        title="预算评审", summary="预算口径", meeting_date="2026-11-08"))
    monkeypatch.setitem(meeting_search.tasks, "t_oct", _task(
        title="预算评审", summary="预算口径", meeting_date="2026-10-08"))

    result = search_meeting_list("11月预算", now=date(2026, 11, 26))
    assert [item["task_id"] for item in result["items"]] == ["t_nov"]
    assert result["time_label"] == "2026-11"


def test_meeting_list_narrow_hint_when_too_many(monkeypatch):
    _seed_term_hits(monkeypatch, meeting_search.LIST_NARROW_HINT_TOTAL + 1)
    result = search_meeting_list("预算", limit=5)
    assert result["total"] > meeting_search.LIST_NARROW_HINT_TOTAL
    assert "hint" in result


def test_dropped_meetings_listed_in_block(monkeypatch):
    _seed_term_hits(monkeypatch, 6)

    block, retrieval = build_scope_context("all", "预算", limit=4)
    assert retrieval["injected"] == 4
    assert retrieval["dropped_total"] == 2
    assert len(retrieval["dropped_meetings"]) == 2
    assert '<dropped_meetings total="2" shown="2">' in block
    for item in retrieval["dropped_meetings"]:
        assert item["task_id"] in block
        # 只给标题/日期/id，不给内容
        assert "snippet" not in item and "excerpt" not in item


def test_no_dropped_block_when_all_injected(monkeypatch):
    _seed_term_hits(monkeypatch, 2)

    block, retrieval = build_scope_context("all", "预算", limit=10)
    assert retrieval["dropped_total"] == 0
    assert "<dropped_meetings" not in block


def test_access_context_hides_invisible_tasks(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_visible", _task(
        title="星瀚评审", summary="星瀚评审"))
    monkeypatch.setitem(meeting_search.tasks, "t_hidden", _task(
        title="星瀚评审", summary="星瀚评审"))

    _block, retrieval = build_scope_context(
        "all", "星瀚评审", limit=10,
        access_context={"visible_task_ids": ["t_visible"]})
    assert [m["task_id"] for m in retrieval["meetings"]] == ["t_visible"]
