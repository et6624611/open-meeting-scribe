"""
tests/test_insight_budget.py — 洞察台一页纸系数：卡位换算、预算重排与端点接入

覆盖：
1. card_slots / diagram_slots 换算表与非法值兜底
2. apply_budget：降级顺序（最旧未确认优先）、acknowledged 保护、图卡上限、纯函数无副作用
3. 端点：POST messages 写盘前重排；PATCH task one_page.insights 改档立即重排落盘；非法档位 422
4. chat 上下文两处读取过滤 deferred
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.server import app
from core.insight_budget import (
    apply_budget,
    budget_block,
    card_slots,
    diagram_slots_for,
    normalize_factor,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _msg(i: int, diagram: bool = False, acknowledged: bool = False) -> dict:
    m = {"id": f"m{i}", "title": f"洞察{i}", "body": f"正文{i}", "timestamp": i * 1000,
         "acknowledged": acknowledged}
    if diagram:
        m["diagram"] = "flowchart LR"
    return m


class TestConversion:
    def test_slot_table(self):
        assert card_slots(0.5) == 1
        assert card_slots(1) == 2
        assert card_slots(1.5) == 3
        assert card_slots(2) == 4

    def test_illegal_factor_defaults_to_one_page(self):
        assert normalize_factor(None) == 1.0
        assert normalize_factor(0.7) == 1.0
        assert normalize_factor("abc") == 1.0
        assert card_slots(0.7) == 2

    def test_diagram_cap(self):
        assert diagram_slots_for(1) == 1
        assert diagram_slots_for(2) == 1   # 1 页 2 张时图 ≤1
        assert diagram_slots_for(3) == 2
        assert diagram_slots_for(4) == 2


class TestApplyBudget:
    def test_oldest_unacknowledged_deferred_first(self):
        msgs = [_msg(i) for i in range(1, 5)]
        out = apply_budget(msgs, 1.0)
        flags = [m["deferred"] for m in out]
        assert flags == [True, True, False, False]  # 最新 2 张留有效层

    def test_acknowledged_never_deferred(self):
        # 最旧一张已确认：改档再小也不降级它，挤占新卡位
        msgs = [_msg(1, acknowledged=True), _msg(2), _msg(3), _msg(4)]
        out = apply_budget(msgs, 0.5)  # slots=1
        by_id = {m["id"]: m for m in out}
        assert by_id["m1"]["deferred"] is False
        # 确认卡占满唯一卡位 → 其余全部降级
        assert by_id["m2"]["deferred"] is True
        assert by_id["m4"]["deferred"] is True

    def test_diagram_cap_respected(self):
        msgs = [_msg(1, diagram=True), _msg(2), _msg(3, diagram=True)]
        out = apply_budget(msgs, 1.0)  # slots=2, 图 ≤1
        by_id = {m["id"]: m for m in out}
        assert by_id["m3"]["deferred"] is False   # 最新图卡入选
        assert by_id["m2"]["deferred"] is False   # 再回填一张文字卡
        assert by_id["m1"]["deferred"] is True    # 旧图卡降级（图位已被占）

    def test_over_capacity_no_forced_defer(self):
        # 三张全部已确认但 slots=1：不强降（人是最终作者）
        msgs = [_msg(i, acknowledged=True) for i in range(1, 4)]
        out = apply_budget(msgs, 0.5)
        assert all(m["deferred"] is False for m in out)

    def test_placeholder_feedback_yields_to_substantive(self):
        """无正文实质的系统反馈卡不得挤占卡位，把更旧的实质洞察卡踢入历史层。"""
        real = _msg(1, diagram=True)  # 旧但实质
        placeholder = {"id": "m2", "title": "未发现盲点", "body": "一切正常",
                       "timestamp": 2000, "source": "system", "acknowledged": False}
        out = apply_budget([real, placeholder], 0.5)  # slots=1
        by_id = {m["id"]: m for m in out}
        assert by_id["m1"]["deferred"] is False
        assert by_id["m2"]["deferred"] is True

    def test_pure_function_no_mutation(self):
        msgs = [_msg(i) for i in range(1, 5)]
        apply_budget(msgs, 1.0)
        assert all("deferred" not in m for m in msgs)  # 入参不被改写

    def test_budget_block_text(self):
        block = budget_block(slots=2, active=2)
        assert "2 张" in block
        assert "卡位已满" in block
        block2 = budget_block(slots=4, active=1)
        assert "4 张" in block2
        assert "卡位已满" not in block2


class TestSaveEndpointRebalance:
    def test_save_applies_budget_and_returns_messages(self, client, tmp_path, monkeypatch):
        import app.routers.insights as insights_router
        monkeypatch.setattr(insights_router, "TASKS_DIR", tmp_path)
        monkeypatch.setattr(insights_router, "tasks", {"t-b1": {"task_id": "t-b1", "one_page": {"insights": 0.5}}})
        msgs = [_msg(i) for i in range(1, 4)]
        resp = client.post("/api/insights/messages/t-b1", json={"messages": msgs})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 3
        # 0.5 页 = 1 个卡位：仅最新一张有效
        assert [m["deferred"] for m in body["messages"]] == [True, True, False]
        stored = json.loads((tmp_path / "t-b1.insights.json").read_text(encoding="utf-8"))
        assert [m["deferred"] for m in stored["messages"]] == [True, True, False]

    def test_save_unknown_task_defaults_to_one_page(self, client, tmp_path, monkeypatch):
        import app.routers.insights as insights_router
        monkeypatch.setattr(insights_router, "TASKS_DIR", tmp_path)
        monkeypatch.setattr(insights_router, "tasks", {})
        msgs = [_msg(i) for i in range(1, 5)]
        resp = client.post("/api/insights/messages/t-ghost", json={"messages": msgs})
        assert resp.status_code == 200
        # 缺省系数 1 → 2 个卡位
        assert [m["deferred"] for m in resp.json()["messages"]] == [True, True, False, False]


class TestPatchOnePage:
    def _seed(self, monkeypatch, tmp_path):
        import app.routers.insights as insights_router
        import app.routers.tasks as tasks_router
        task = {"task_id": "t-op", "status": "completed"}
        store = {"t-op": task}
        monkeypatch.setattr(tasks_router, "tasks", store)
        monkeypatch.setattr(tasks_router, "save_task_to_disk", lambda tid: None)
        monkeypatch.setattr(insights_router, "TASKS_DIR", tmp_path)
        messages = [_msg(i) for i in range(1, 5)]
        (tmp_path / "t-op.insights.json").write_text(
            json.dumps({"messages": messages}, ensure_ascii=False), encoding="utf-8")
        return store, insights_router

    def test_patch_valid_levels(self, client, monkeypatch, tmp_path):
        store, _ = self._seed(monkeypatch, tmp_path)
        resp = client.patch("/api/tasks/t-op", json={"one_page": {"summary": 0.5, "insights": 2}})
        assert resp.status_code == 200
        assert store["t-op"]["one_page"] == {"summary": 0.5, "insights": 2}

    def test_patch_illegal_level_422(self, client, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path)
        resp = client.patch("/api/tasks/t-op", json={"one_page": {"summary": 0.7}})
        assert resp.status_code == 422

    def test_patch_insights_change_rebalances(self, client, monkeypatch, tmp_path):
        store, insights_router = self._seed(monkeypatch, tmp_path)
        # 先按默认（系数 1）无关；改档 0.5 → 立即重排落盘（slots=1）
        resp = client.patch("/api/tasks/t-op", json={"one_page": {"insights": 0.5}})
        assert resp.status_code == 200
        assert store["t-op"]["one_page"]["insights"] == 0.5
        stored = json.loads((tmp_path / "t-op.insights.json").read_text(encoding="utf-8"))
        assert sum(1 for m in stored["messages"] if not m.get("deferred")) == 1

    def test_patch_partial_keeps_other_key(self, client, monkeypatch, tmp_path):
        store, _ = self._seed(monkeypatch, tmp_path)
        client.patch("/api/tasks/t-op", json={"one_page": {"summary": 2}})
        client.patch("/api/tasks/t-op", json={"one_page": {"insights": 0.5}})
        assert store["t-op"]["one_page"] == {"summary": 2, "insights": 0.5}

    def test_patch_summary_change_does_not_touch_cards(self, client, monkeypatch, tmp_path):
        _, insights_router = self._seed(monkeypatch, tmp_path)
        before = (tmp_path / "t-op.insights.json").read_text(encoding="utf-8")
        client.patch("/api/tasks/t-op", json={"one_page": {"summary": 0.5}})
        assert (tmp_path / "t-op.insights.json").read_text(encoding="utf-8") == before


class TestContextInjectionFiltersDeferred:
    def _write(self, tmp_path, messages):
        (tmp_path / "t1.insights.json").write_text(
            json.dumps({"messages": messages}, ensure_ascii=False), encoding="utf-8")

    def test_chat_context_block(self, tmp_path, monkeypatch):
        import core.chat_context as chat_context
        monkeypatch.setattr(chat_context, "INSIGHTS_TASKS_DIR", tmp_path)
        self._write(tmp_path, [_msg(1), {**_msg(2), "body": "正文2", "deferred": True}])
        # 有效卡仅 1 张；降级卡不进 AI 引用口径
        block = chat_context.build_insights_context_block("t1")
        assert block is not None and "洞察1" in block and "洞察2" not in block

    def test_cli_context_export(self, tmp_path, monkeypatch):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "INSIGHTS_TASKS_DIR", tmp_path)
        self._write(tmp_path, [_msg(1), {**_msg(2), "deferred": True}])
        rendered = ce._render_insights("t1")
        assert "洞察1" in rendered and "洞察2" not in rendered
