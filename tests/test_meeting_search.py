"""跨会议关键词检索单测（提问范围唯一检索器）。"""
from core import meeting_search
from core.meeting_search import build_scope_context, normalize_scope


def _task(**overrides):
    task = {
        "title": "未命名",
        "summary": "",
        "user_summary": "",
        "decisions": [],
        "dialogue": [],
        "meeting_date": "2026-11-01",
    }
    task.update(overrides)
    return task


def _dialogue(*lines):
    return [{"sentences": [{"text": line} for line in lines]}]


def test_normalize_scope_defaults_to_meeting():
    assert normalize_scope(None) == "meeting"
    assert normalize_scope("project") == "meeting"
    assert normalize_scope("x") == "meeting"
    assert normalize_scope("all") == "all"


def test_title_hit_ranks_above_dialogue(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_title", _task(
        title="预算评审会", summary="讨论预算", meeting_date="2026-11-02"))
    monkeypatch.setitem(meeting_search.tasks, "t_dialogue", _task(
        title="周会", dialogue=_dialogue("预算还需要再核对一次"), meeting_date="2026-11-03"))

    hits = meeting_search.search_meetings("预算")
    assert [h["task_id"] for h in hits] == ["t_title", "t_dialogue"]


def test_exclude_task_id_and_empty_text(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(
        title="发布计划", summary="发布节奏讨论"))
    monkeypatch.setitem(meeting_search.tasks, "t_empty", _task(title=""))

    hits = meeting_search.search_meetings("发布", exclude_task_id="t_a")
    assert hits == []


def test_meeting_scope_returns_empty_block(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(
        title="发布计划", summary="发布节奏讨论"))

    block, retrieval = build_scope_context("meeting", "发布")
    assert block == ""
    assert retrieval["searched"] is False
    assert retrieval["hits"] == 0


def test_all_scope_returns_block_with_scope_and_sources(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_a", _task(
        title="发布计划", summary="发布节奏讨论"))

    block, retrieval = build_scope_context("all", "发布")
    assert "提问范围：全部会议" in block
    assert "说明：" in block
    assert retrieval["searched"] is True
    assert retrieval["hits"] == 1
    assert retrieval["meetings"][0]["task_id"] == "t_a"


def test_decision_intent_puts_decision_evidence_first(monkeypatch):
    monkeypatch.setitem(meeting_search.tasks, "t_decide", _task(
        title="会计事件库方案讨论",
        summary="讨论会计事件库的定位、范围与协同方式，涉及多个业务线。",
        decisions=[{"text": "决定启用会计事件库模块", "done": True, "assignee": "财务组"}],
    ))

    hits = meeting_search.search_meetings("是否决定采用会计事件库")
    assert hits
    snippets = hits[0]["snippets"]
    assert snippets[0].startswith("决策：决定启用会计事件库模块")
    # 摘要只出现一次，不按命中词重复占位
    summary_like = [s for s in snippets if s.startswith("讨论会计事件库")]
    assert len(summary_like) <= 1


def test_hits_report_total_and_shown(monkeypatch):
    for i in range(6):
        monkeypatch.setitem(meeting_search.tasks, f"t_{i}", _task(
            title=f"发布计划 {i}", summary="发布节奏讨论"))

    block, retrieval = build_scope_context("all", "发布", limit=4)
    assert retrieval["hits"] == 6
    assert retrieval["shown"] == 4
    assert "共 6 场命中" in block
    assert "展示前 4 场" in block
