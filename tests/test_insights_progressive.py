"""
tests/test_insights_progressive.py — 洞察台只读累进（Phase 1）单元测试
Read-only progressive insights (Phase 1) unit tests

覆盖范围 / Covers:
1. _build_user_message 携带/不携带 existing_insights 的三态输出
2. _format_existing_insights 的条数与字符双层截断预算
3. run_analysis 签名向后兼容（existing_insights 可选、缺省等价旧行为）
4. 路由模型 InsightAnalysisRequest 对 existing_insights 的透传与缺省

不触发真实 LLM 调用 / Never calls a real LLM.
"""

import inspect

import pytest
from fastapi.testclient import TestClient

from app.server import app
from core.insights import (
    EXISTING_INSIGHTS_MAX_CHARS,
    EXISTING_INSIGHTS_MAX_ITEMS,
    _build_user_message,
    _format_existing_insights,
    run_analysis,
)


@pytest.fixture
def client():
    """创建测试客户端 / Create test client."""
    with TestClient(app) as c:
        yield c

LINES = [{"text": "测试讨论内容", "speaker_id": 0, "begin_time": 5000}]
TITLES = ["第一章"]


def _existing(n: int, body_len: int = 300):
    return [{"title": f"洞察{i}", "body": "x" * body_len} for i in range(n)]


# ============================================================
# user message 构建
# ============================================================

class TestBuildUserMessageProgressive:

    def test_block_injected_when_existing_provided(self):
        """传入已有洞察时，注入「已产出的洞察卡片」块与去重约束"""
        msg = _build_user_message(LINES, TITLES, _existing(3))
        assert "## 已产出的洞察卡片" in msg
        assert "同主题" in msg and "重复" in msg
        # 块位于章节主题之后、最近讨论之前
        assert msg.index("## 会议章节主题") < msg.index("## 已产出的洞察卡片") < msg.index("## 最近讨论内容")

    def test_block_absent_when_none_or_empty(self):
        """缺省 / 空列表时输出与旧版等价（无新块）——向后兼容核心断言"""
        legacy = _build_user_message(LINES, TITLES)
        assert "已产出的洞察卡片" not in legacy
        assert "已产出的洞察卡片" not in _build_user_message(LINES, TITLES, None)
        assert "已产出的洞察卡片" not in _build_user_message(LINES, TITLES, [])

    def test_transcript_and_chapters_kept(self):
        """注入新块不挤占既有章节与转写内容"""
        msg = _build_user_message(LINES, TITLES, _existing(3))
        assert "- 第一章" in msg
        assert "测试讨论内容" in msg


# ============================================================
# 截断预算
# ============================================================

class TestExistingInsightsBudget:

    def test_item_cap_keeps_latest(self):
        """超过条数上限时仅保留最近 N 条（丢弃最早的）"""
        block = _format_existing_insights(_existing(EXISTING_INSIGHTS_MAX_ITEMS + 4))
        assert f"洞察{EXISTING_INSIGHTS_MAX_ITEMS + 3}" in block
        assert "- 洞察0" not in block

    def test_char_cap_respected(self):
        """整块字符不超预算（含标题与约束语的计数由实现保证条目部分受控）"""
        block = _format_existing_insights(_existing(20, body_len=500))
        # 标题行 + 约束语的固定开销之外，条目部分受 MAX_CHARS 约束
        assert len(block) < EXISTING_INSIGHTS_MAX_CHARS + 400

    def test_skips_titleless_and_returns_empty(self):
        """无标题条目被过滤；空输入返回空串"""
        assert _format_existing_insights([]) == ""
        assert _format_existing_insights(None) == ""
        assert _format_existing_insights([{"title": "  ", "body": "x"}]) == ""

    def test_body_truncated_per_item(self):
        """单条 body 截断到预算内（120 字）"""
        block = _format_existing_insights(_existing(1, body_len=500))
        assert "x" * 121 not in block


# ============================================================
# 签名与路由契约
# ============================================================

class TestBackwardCompatContract:

    def test_run_analysis_signature_optional(self):
        """末位均为可选参数，旧位置参数调用不受影响（一页纸系数 card_budget 追加在尾）"""
        sig = inspect.signature(run_analysis)
        param = sig.parameters["existing_insights"]
        assert param.default is None
        assert list(sig.parameters) == [
            "recent_lines", "chapter_titles", "role_name", "existing_insights", "card_budget",
        ]
        assert sig.parameters["card_budget"].default is None

    def test_request_model_field_optional(self):
        """InsightAnalysisRequest 缺省 None（旧客户端等价）、传入可透传"""
        from app.routers.insights import InsightAnalysisRequest
        m = InsightAnalysisRequest(recent_lines=LINES, chapter_titles=TITLES)
        assert m.existing_insights is None
        payload = [{"title": "x", "body": "y"}]
        m2 = InsightAnalysisRequest(recent_lines=LINES, chapter_titles=TITLES, existing_insights=payload)
        assert m2.existing_insights == payload

    def test_analyze_endpoint_accepts_and_forwards(self, client, monkeypatch):
        """端点接收 existing_insights 并透传给 core.run_analysis（打桩不发 LLM 请求）"""
        import app.routers.insights as insights_router

        captured = {}

        async def fake_run_analysis(recent_lines, chapter_titles, role_name=None, existing_insights=None, card_budget=None):
            captured["existing"] = existing_insights
            return {"title": "", "body": "", "solution": "", "has_finding": False, "diagram": "", "graph": None}

        monkeypatch.setattr(insights_router, "core_run_analysis", fake_run_analysis)
        resp = client.post("/api/insights/analyze", json={
            "recent_lines": LINES,
            "chapter_titles": TITLES,
            "existing_insights": [{"title": "已有卡", "body": "摘要"}],
        })
        assert resp.status_code == 200
        assert captured["existing"] == [{"title": "已有卡", "body": "摘要"}]

    def test_analyze_endpoint_omitting_field(self, client, monkeypatch):
        """不传字段时透传 None，与旧请求体完全等价"""
        import app.routers.insights as insights_router

        captured = {}

        async def fake_run_analysis(recent_lines, chapter_titles, role_name=None, existing_insights=None, card_budget=None):
            captured["existing"] = existing_insights
            return {"title": "", "body": "", "solution": "", "has_finding": False, "diagram": "", "graph": None}

        monkeypatch.setattr(insights_router, "core_run_analysis", fake_run_analysis)
        resp = client.post("/api/insights/analyze", json={
            "recent_lines": LINES,
            "chapter_titles": TITLES,
        })
        assert resp.status_code == 200
        assert captured["existing"] is None
