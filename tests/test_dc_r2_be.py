"""
tests/test_dc_r2_be.py — DC-R2-BE auto 决策删除墓碑回归

覆盖：墓碑建（DELETE auto）/ 不建（非 auto）/ merge 过滤复活 / 文本编辑后不拦截新表述 /
无墓碑向后兼容 / 归一键空白容忍。
"""
from core.summarize import (
    build_decision_tombstone,
    decision_text_key,
    merge_decisions_after_regen,
)


def _auto(text, did="a1"):
    return {"id": did, "text": text, "source": "auto", "status": "active"}


def _manual(text="补录决策", did="m1"):
    return {"id": did, "text": text, "source": "manual", "status": "active"}


def test_tombstone_only_for_auto():
    tb = build_decision_tombstone(_auto("Q4 预算维持 120 万"))
    assert tb and tb["text_key"] == "Q4 预算维持 120 万"
    assert build_decision_tombstone(_manual()) is None
    assert build_decision_tombstone({"source": "backfill", "text": "x"}) is None
    assert build_decision_tombstone(_auto("   ")) is None  # 空文本不建


def test_merge_filters_resurrection():
    existing = [_manual()]
    parsed = [_auto("决策A"), _auto("决策B")]
    deletions = [{"text_key": "决策A", "deleted_at": "2026-09-25T13:00:00"}]
    merged = merge_decisions_after_regen(existing, parsed, deletions)
    texts = [d["text"] for d in merged]
    assert "决策A" not in texts, "被删 auto 重生成不得复活"
    assert texts == ["补录决策", "决策B"]


def test_merge_without_deletions_backward_compatible():
    """无墓碑（含 None/缺省/旧调用两参形态）= 既有行为不变。"""
    existing = [_manual()]
    parsed = [_auto("决策A")]
    assert merge_decisions_after_regen(existing, parsed) == existing + parsed
    assert merge_decisions_after_regen(existing, parsed, None) == existing + parsed
    assert merge_decisions_after_regen(existing, parsed, []) == existing + parsed


def test_text_key_whitespace_tolerance_and_edit_not_blocked():
    """归一键：首尾/内部多余空白等价；用户改表述后的新文本不被墓碑误杀。"""
    assert decision_text_key("  Q4  预算\n维持 ") == "Q4 预算 维持"
    deletions = [{"text_key": decision_text_key("Q4 预算维持 120 万"), "deleted_at": "x"}]
    # 重解析产出同文本（哪怕空白差异）→ 过滤
    same = _auto("Q4  预算维持 120 万 ")
    assert merge_decisions_after_regen([], [same], deletions) == []
    # 用户改过表述 → 视为新决策放行
    edited = _auto("Q4 预算调整为 130 万")
    assert len(merge_decisions_after_regen([], [edited], deletions)) == 1


def test_delete_endpoint_writes_tombstone(tmp_path, monkeypatch):
    """API 面：DELETE auto 决策 → task.decision_deletions 落碑；DELETE manual → 不落。"""
    from app.routers import decisions as dr

    task_id = "dc-r2-be-task"
    task = {
        "task_id": task_id,
        "title": "t",
        "status": "completed",
        "decisions": [_auto("将被删除的决策", "d1"), _manual("手工决策", "d2")],
    }
    store = {task_id: task}
    # 路由依赖函数级打桩（取 task/取决策/列表/脏标/落盘），不碰真实 data/
    monkeypatch.setattr(dr, "_require_task", lambda tid: store[tid])
    monkeypatch.setattr(dr, "_require_decision", lambda t, did: next(d for d in t["decisions"] if d["id"] == did))
    monkeypatch.setattr(dr, "_get_decisions", lambda t: t.get("decisions", []))
    monkeypatch.setattr(dr, "_mark_modified", lambda tid: None)
    monkeypatch.setattr(dr, "save_task_to_disk", lambda tid: None)

    resp = dr.delete_task_decision(task_id, "d1")
    assert resp == {"ok": True}
    keys = [t["text_key"] for t in task.get("decision_deletions", [])]
    assert "将被删除的决策" in keys
    assert all(d["id"] != "d1" for d in task["decisions"])

    # 再删 manual：不追加墓碑
    before = len(task["decision_deletions"])
    dr.delete_task_decision(task_id, "d2")
    assert len(task["decision_deletions"]) == before

    # 幂等：重复删除同文本 auto 不产生重复碑
    task["decisions"].append(_auto("将被删除的决策", "d3"))
    dr.delete_task_decision(task_id, "d3")
    assert keys == [t["text_key"] for t in task["decision_deletions"]]
