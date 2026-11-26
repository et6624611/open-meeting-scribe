"""版本化金样本验收（docs/specs/context-asset-management/spec.md §10）。

断言命中对象、排除对象、排序、权限、统计与证据，而不只断言数量。
"""
import json
import time
from datetime import date
from pathlib import Path

from core import meeting_search
from core.meeting_search import build_scope_context, search_meetings

GOLD_PATH = Path(__file__).parent / "fixtures" / "meeting_search_gold.json"


def _load_gold() -> dict:
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def _build_corpus(gold: dict) -> tuple[dict, dict]:
    """把金样本展开为 tasks 字典；返回 (tasks, project_by_name)。"""
    project_by_name = {p["name"]: p for p in gold["projects"]}
    corpus: dict = {}
    for item in gold["meetings"]:
        task = {
            "title": item.get("title"),
            "meeting_date": item.get("meeting_date") or "",
            "summary": item.get("summary") or "",
            "decisions": item.get("decisions") or [],
            "dialogue": [{"sentences": [{"text": line}]} for line in item.get("dialogue") or []],
        }
        project = item.get("project")
        if project:
            task["project_id"] = project_by_name[project]["id"]
        for key in ("archived_at", "deleted"):
            if item.get(key):
                task[key] = item[key]
        corpus[item["task_id"]] = task

    for i in range(gold.get("filler_count", 0)):
        corpus[f"filler_{i}"] = {
            "title": f"例行同步 {i}",
            "meeting_date": "2026-07-15",
            "summary": "例行同步与进度对齐。",
            "decisions": [],
            "dialogue": [],
        }
    return corpus, project_by_name


def _install(monkeypatch, corpus: dict, gold: dict) -> dict:
    monkeypatch.setattr(meeting_search, "tasks", corpus)
    monkeypatch.setattr(
        "core.projects.list_projects",
        lambda: [{"id": p["id"], "name": p["name"]} for p in gold["projects"]],
    )
    return {"visible_task_ids": [
        task_id for task_id in corpus if task_id not in set(gold["hidden_task_ids"])
    ]}


def test_gold_queries(monkeypatch):
    gold = _load_gold()
    corpus, _projects = _build_corpus(gold)
    access = _install(monkeypatch, corpus, gold)
    now = date.fromisoformat(gold["now"])

    for case in gold["queries"]:
        block, retrieval = build_scope_context(
            "all", case["query"], now=now, access_context=access, limit=20)
        ids = [m["task_id"] for m in retrieval["meetings"]]

        for task_id in case["must_include"]:
            assert task_id in ids, (case["query"], task_id, ids)
        for task_id in case["must_exclude"]:
            assert task_id not in ids, (case["query"], task_id, ids)
        if case["expected_top"]:
            assert ids and ids[0] == case["expected_top"][0], (case["query"], ids)

        for expected in case["expected_facts"]:
            facts = [f for f in retrieval["verified_facts"] if f["kind"] == expected["kind"]]
            assert facts and facts[0]["value"] == expected["value"], (case["query"], facts)

        if case.get("max_candidates") is not None:
            assert retrieval["candidates"] <= case["max_candidates"], (case["query"], retrieval["candidates"])
        if case.get("max_matched") is not None:
            assert retrieval["matched"] <= case["max_matched"], (case["query"], retrieval["matched"])

        if retrieval["status"] == "ok":
            assert retrieval["candidates"] >= retrieval["matched"] >= retrieval["injected"]
        if case["expected_facts"]:
            assert "<verified_facts>" in block


def test_current_decision_only_yields_main_record(monkeypatch):
    gold = _load_gold()
    corpus, _projects = _build_corpus(gold)
    access = _install(monkeypatch, corpus, gold)
    now = date.fromisoformat(gold["now"])

    _block, retrieval = build_scope_context(
        "all", "当前星瀚决策怎么定", now=now, access_context=access, limit=20)
    decision_evidence = [
        item
        for meeting in retrieval["meetings"]
        for item in meeting["evidence"]
        if item["asset_type"] == "decision"
    ]
    assert decision_evidence
    assert all(item.get("is_current") is True for item in decision_evidence)
    assert all(item["status"] != "superseded" for item in decision_evidence)


def test_permission_lifecycle_and_freshness(monkeypatch):
    gold = _load_gold()
    corpus, _projects = _build_corpus(gold)
    access = _install(monkeypatch, corpus, gold)
    now = date.fromisoformat(gold["now"])

    _block, retrieval = build_scope_context(
        "all", "本月与星瀚项目相关有哪些关键决策？", now=now, access_context=access, limit=20)
    ids = [m["task_id"] for m in retrieval["meetings"]]
    # 无权 / 已删除不得进入任何计数或证据；已归档可见
    assert "g_4" not in ids and "g_8" not in ids
    assert "g_7" in ids or retrieval["matched"] >= 1

    # 归档会议在统计中可查
    _block, facts = build_scope_context("all", "本月几场", now=now, access_context=access)
    assert facts["verified_facts"][0]["value"] == 3

    # 新鲜度：修改内容后下一次请求立即生效
    corpus["g_1"]["title"] = "无关会议"
    corpus["g_1"]["summary"] = ""
    corpus["g_1"]["decisions"] = []
    corpus["g_1"]["dialogue"] = []
    _block, retrieval = build_scope_context(
        "all", "本月与星瀚项目相关有哪些关键决策？", now=now, access_context=access, limit=20)
    assert "g_1" not in [m["task_id"] for m in retrieval["meetings"]]


def test_every_injected_meeting_has_unique_evidence(monkeypatch):
    gold = _load_gold()
    corpus, _projects = _build_corpus(gold)
    access = _install(monkeypatch, corpus, gold)
    now = date.fromisoformat(gold["now"])

    block, retrieval = build_scope_context(
        "all", "星瀚项目关键决策", now=now, access_context=access, limit=20)
    seen: set[str] = set()
    for meeting in retrieval["meetings"]:
        assert meeting["evidence"], meeting["task_id"]
        for item in meeting["evidence"]:
            assert item["evidence_id"] not in seen
            seen.add(item["evidence_id"])
            assert f"[evidence:{item['evidence_id']}]" in block
            assert item["excerpt"]
            assert item["asset_type"] in ("title", "summary", "decision", "dialogue")


def test_empty_and_ambiguous_query_do_not_guess(monkeypatch):
    gold = _load_gold()
    corpus, _projects = _build_corpus(gold)
    access = _install(monkeypatch, corpus, gold)
    now = date.fromisoformat(gold["now"])

    for query in ("", "多少"):
        block, retrieval = build_scope_context(
            "all", query, now=now, access_context=access)
        assert retrieval["status"] == "ok"
        assert retrieval["matched"] == 0
        assert retrieval["injected"] == 0
        assert block == ""
        assert retrieval["verified_facts"] == []


def test_idf_ignores_invisible_tasks(monkeypatch):
    gold = _load_gold()
    corpus, _projects = _build_corpus(gold)
    access = _install(monkeypatch, corpus, gold)
    now = date.fromisoformat(gold["now"])

    restricted = search_meetings("星瀚项目关键决策", access_context=access, now=now)
    solo_corpus = {k: v for k, v in corpus.items() if k not in set(gold["hidden_task_ids"])}
    monkeypatch.setattr(meeting_search, "tasks", solo_corpus)
    solo = search_meetings("星瀚项目关键决策", now=now)

    restricted_scores = {hit["task_id"]: hit["score"] for hit in restricted}
    solo_scores = {hit["task_id"]: hit["score"] for hit in solo}
    assert restricted_scores == solo_scores


def test_history_query_returns_superseded_evidence(monkeypatch):
    gold = _load_gold()
    corpus, _projects = _build_corpus(gold)
    access = _install(monkeypatch, corpus, gold)
    now = date.fromisoformat(gold["now"])

    _block, retrieval = build_scope_context(
        "all", "星瀚决策历史怎么演变", now=now, access_context=access, limit=20)
    superseded = [
        item
        for meeting in retrieval["meetings"]
        for item in meeting["evidence"]
        if item["asset_type"] == "decision" and item["status"] == "superseded"
    ]
    assert superseded
    assert all(item.get("is_current") is False for item in superseded)


def test_search_latency_under_50ms_for_500_meetings(monkeypatch):
    corpus = {
        f"perf_{i}": {
            "title": f"例行同步 {i}",
            "meeting_date": "2026-07-15",
            "summary": "例行同步与进度对齐，讨论预算与排期。",
            "decisions": [{"id": f"pd{i}", "text": "按计划推进", "status": "in_progress"}],
            "dialogue": [{"sentences": [{"text": "本周先做灰度"}]}],
        }
        for i in range(500)
    }
    corpus["perf_target"] = {
        "title": "星瀚项目关键决策评审",
        "meeting_date": "2026-11-01",
        "summary": "星瀚项目关键决策评审。",
        "decisions": [{"id": "pt1", "text": "星瀚项目采用方案B", "status": "in_progress"}],
        "dialogue": [],
    }
    monkeypatch.setattr(meeting_search, "tasks", corpus)

    started = time.perf_counter()
    hits = search_meetings("星瀚项目关键决策")
    elapsed = time.perf_counter() - started
    print(f"500 场检索耗时: {elapsed * 1000:.1f}ms")
    assert hits
    assert elapsed <= 0.05
