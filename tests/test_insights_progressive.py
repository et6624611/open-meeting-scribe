"""
tests/test_insights_progressive.py — 洞察台只读累进（Phase 1）单元测试
Read-only progressive insights (Phase 1) unit tests

覆盖范围 / Covers:
1. _build_user_message 携带/不携带 existing_insights 的三态输出
2. _format_existing_insights 的条数与字符双层截断预算
3. run_analysis 签名向后兼容（existing_insights 可选、缺省等价旧行为）
4. 无状态 /analyze 端点已随「洞察共创 · 会话驱动」退役（路由不再存在）
5. 提示词契约锚点（v5.3：body 阶段描述 few-shot 正反例 + solution 可执行约束）
6. 联网检索增强三态（注入 / 未配置 key 跳过 / 判定失败降级）

不触发真实 LLM 调用 / Never calls a real LLM.
"""

import inspect
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.server import app
from core.insights import (
    EXISTING_INSIGHTS_MAX_CHARS,
    EXISTING_INSIGHTS_MAX_ITEMS,
    INSIGHT_ANALYSIS_PROMPT,
    _augment_with_web_search,
    _build_user_message,
    _format_existing_insights,
    _parse_analysis_result,
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

class TestAnalyzeEndpointRetired:
    """无状态 /analyze 与会后补分析 /analyze/task 已退役：洞察产生/修订改走会话 agent 工具链。
    守卫测试确保旧路由不被意外复活（僵尸端点比 404 危险）。"""

    def test_stateless_analyze_route_gone(self, client):
        resp = client.post("/api/insights/analyze", json={
            "recent_lines": LINES, "chapter_titles": TITLES,
        })
        # 404 = 无路由；405 = 仅 SPA catch-all（GET/HEAD）命中。两者都意味 API 端点已退役
        assert resp.status_code in (404, 405)

    def test_post_meeting_analyze_route_gone(self, client):
        resp = client.post("/api/insights/analyze/task/nonexistent", json={})
        assert resp.status_code in (404, 405)

    def test_request_model_removed_from_router(self):
        """路由模块不再导出请求模型与 core 转发句柄"""
        import app.routers.insights as insights_router
        assert not hasattr(insights_router, "InsightAnalysisRequest")
        assert not hasattr(insights_router, "core_run_analysis")


# ============================================================
# 提示词契约锚点（v5.3：body 阶段描述 + solution 可执行性）
# ============================================================

class TestInsightPromptContract:
    """防「阶段名」占位符复读与方向性口号回归：契约锚点 + 退化检测日志。"""

    def test_prompt_contains_body_contract_anchors(self):
        # 硬约束与正反例 few-shot 均已写入契约
        assert "禁止只重复阶段标题" in INSIGHT_ANALYSIS_PROMPT
        assert "不少于 15 字" in INSIGHT_ANALYSIS_PROMPT
        assert "完整句子" in INSIGHT_ANALYSIS_PROMPT
        assert "正例" in INSIGHT_ANALYSIS_PROMPT
        assert "反例（禁止这样写）" in INSIGHT_ANALYSIS_PROMPT

    def test_prompt_contains_solution_contract(self):
        assert "可执行的建议" in INSIGHT_ANALYSIS_PROMPT
        assert "1-3 条步骤" in INSIGHT_ANALYSIS_PROMPT
        assert "方向性口号" in INSIGHT_ANALYSIS_PROMPT

    def test_placeholder_body_logged(self, caplog):
        """body 出现「阶段名：」占位符时记 warning（前端兜底之外的排查线索）"""
        raw = json.dumps({
            "title": "代扣与开票断点",
            "body": "阶段名：流程断点\n阶段名：权责错配",
            "solution": "", "note": "", "has_finding": True, "diagram": "",
        }, ensure_ascii=False)
        with caplog.at_level(logging.WARNING, logger="core.insights"):
            parsed = _parse_analysis_result(raw)
        assert parsed["has_finding"] is True
        assert any("占位符退化" in rec.message for rec in caplog.records)

    def test_clean_body_not_logged(self, caplog):
        """合规 body（实际阶段标题前缀）不触发退化告警"""
        raw = json.dumps({
            "title": "t",
            "body": "最关键的盲区是 X。流程断点：企业代扣劳务费后税务系统仍推开票二维码，未识别已缴状态。",
            "solution": "", "note": "", "has_finding": True, "diagram": "",
        }, ensure_ascii=False)
        with caplog.at_level(logging.WARNING, logger="core.insights"):
            _parse_analysis_result(raw)
        assert not any("占位符退化" in rec.message for rec in caplog.records)


# ============================================================
# 联网检索增强（v5.3）
# ============================================================

ANALYSIS_REPLY = json.dumps({
    "title": "代扣与开票存在系统断点",
    "body": "最关键的盲区是完税链路无单据。流程断点：企业代扣劳务费后税务系统仍推开票二维码，未识别已缴状态。",
    "solution": "1) 向税务大厅确认代扣代缴后是否免推二维码；2) 由经办人比对缴款记录开具完税证明。",
    "note": "讨论 05:11-06:33",
    "has_finding": True,
    "diagram": "flowchart LR\n  subgraph S1[\"流程断点\"]\n    S1a[\"代扣 @@311000\"]\n  end",
}, ensure_ascii=False)

BRAVE_REPLY = json.dumps({
    "query": "代扣代缴 完税证明",
    "count": 1,
    "results": [{
        "title": "自然人代扣代缴指南",
        "description": "扣缴义务人代扣后可向税务机关申请开具完税凭证",
        "url": "https://example.com/tax",
    }],
}, ensure_ascii=False)


def _patch_web_search_on(monkeypatch, judge_reply):
    """联网前置全开（mock execute_tool + mock async_chat_completion），返回调用捕获。

    联网检索已改为免密实现，不再需要 API key 前置。
    """
    monkeypatch.setattr(
        "core.agent_tools.impl.execute_tool",
        lambda name, kwargs: BRAVE_REPLY if name == "web_search" else json.dumps({"error": "unknown"}),
    )
    calls = []

    async def fake_chat(messages, model=None, temperature=0.7, max_tokens=4096):
        calls.append({"messages": messages, "max_tokens": max_tokens})
        if len(calls) == 1:
            return judge_reply
        return ANALYSIS_REPLY

    monkeypatch.setattr("core.insights.async_chat_completion", fake_chat)
    return calls


class TestInsightWebSearchAugment:
    """联网检索增强三态：注入 / 未配置 key / 判定失败降级。"""

    async def test_web_reference_injected_when_needed(self, monkeypatch):
        judge = json.dumps({"need": True, "queries": ["代扣代缴 完税证明"]})
        calls = _patch_web_search_on(monkeypatch, judge)
        result = await run_analysis(LINES, TITLES)
        assert result["web_searched"] is True
        assert result["has_finding"] is True
        # 两次 LLM 调用：判定 + 主分析
        assert len(calls) == 2
        main_user = calls[1]["messages"][-1]["content"]
        assert "## 外部参考（联网检索" in main_user
        assert "自然人代扣代缴指南" in main_user

    async def test_judge_need_false_skips_search(self, monkeypatch):
        judge = json.dumps({"need": False, "queries": []})
        calls = _patch_web_search_on(monkeypatch, judge)
        result = await run_analysis(LINES, TITLES)
        assert result["web_searched"] is False
        assert len(calls) == 2
        main_user = calls[1]["messages"][-1]["content"]
        assert "外部参考" not in main_user

    async def test_search_failure_degrades(self, monkeypatch):
        """检索源全部失败：不注入外部参考，主流程照常完成"""
        calls = _patch_web_search_on(
            monkeypatch, json.dumps({"need": True, "queries": ["代扣代缴 完税证明"]}))
        monkeypatch.setattr(
            "core.agent_tools.impl.execute_tool",
            lambda name, kwargs: json.dumps({"error": "web_search_network", "message": "不可用"}),
        )
        result = await run_analysis(LINES, TITLES)
        assert result["web_searched"] is False
        assert result["has_finding"] is True
        assert "外部参考" not in calls[1]["messages"][-1]["content"]

    async def test_judge_failure_degrades_gracefully(self, monkeypatch):
        """判定调用抛异常：静默降级为无检索分析，主流程照常完成"""

        async def fake_chat(messages, model=None, temperature=0.7, max_tokens=4096):
            if max_tokens == 200:
                raise RuntimeError("judge down")
            return ANALYSIS_REPLY

        monkeypatch.setattr("core.insights.async_chat_completion", fake_chat)
        result = await run_analysis(LINES, TITLES)
        assert result["has_finding"] is True
        assert result["web_searched"] is False

    async def test_augment_empty_when_search_fails(self, monkeypatch):
        monkeypatch.setattr(
            "core.agent_tools.impl.execute_tool",
            lambda name, kwargs: json.dumps({"error": "web_search_network"}),
        )
        assert await _augment_with_web_search(LINES, TITLES) == ""
