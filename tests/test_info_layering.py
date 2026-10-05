"""
tests/test_info_layering.py — 三层信息写作契约（PROPOSAL-INFO-LAYERING）回归

覆盖：
- 纪要清单条目内联注（（注：…））与 split_decision_title / parse_decisions_with_status 的兼容；
- 议题引用块注释不污染结论章节提取；
- chat 上下文块与 CLI 导出携带 note；
- 预算块含「注释层不计入预算」声明。
"""

import json

from core.summarize import (
    split_decision_title,
    parse_decisions_with_status,
    extract_conclusions_section,
    build_page_budget_block,
)
from core.chat_context import build_insights_context_block


# ─── 纪要侧：内联注与解析器兼容 ───

class TestSummaryInlineNote:

    def test_split_title_keeps_note_in_content(self):
        text = "**差旅报销口径统一**：所有超标单据改由部门负责人事前审批（注：说话人2 07:34 提出）"
        title, content = split_decision_title(text)
        assert title == "差旅报销口径统一"
        assert "（注：说话人2 07:34 提出）" in content

    def test_parse_decisions_with_note(self):
        summary = (
            "## 二、主要结论\n\n"
            "1. **口径统一**：超标单据改由负责人事前审批（注：说话人2 07:34 提出）\n"
            "2. **数据源切换**：Q4 前迁移费控报表\n"
        )
        nodes, status = parse_decisions_with_status(summary)
        assert status is None
        assert len(nodes) == 2
        assert "（注：" in nodes[0]["text"]
        assert nodes[0]["title"] == "口径统一"

    def test_pending_prefix_with_note(self):
        summary = (
            "## 二、主要结论\n\n"
            "1. [待确认] **切换窗口**：暂定 Q4（注：原文或作\u201c四季度\u201d，未最终敲定）\n"
        )
        nodes, status = parse_decisions_with_status(summary)
        assert status is None
        assert len(nodes) == 1
        assert nodes[0]["pending_confirmation"] is True

    def test_topic_blockquote_not_extracted(self):
        """议题章节的 > 引用块注释不在决策解析范围，且不被结论章节吞并。"""
        summary = (
            "## 二、主要结论\n\n"
            "1. **口径统一**：超标单据改由负责人事前审批\n\n"
            "## 四、议题归类\n\n"
            "### 议题1：数据源切换\n"
            "讨论倾向 Q4 前迁移。\n"
            "> 依据：说话人3（22:10）；切换窗口未敲定[待确认]\n"
        )
        nodes, _ = parse_decisions_with_status(summary)
        assert len(nodes) == 1
        concl = extract_conclusions_section(summary)
        assert "依据：说话人3" not in concl


# ─── 上下文注入通道 ───

class TestContextInjectionNote:

    def test_chat_context_block_carries_note(self, tmp_path, monkeypatch):
        import core.chat_context as cc
        monkeypatch.setattr(cc, "INSIGHTS_TASKS_DIR", tmp_path)
        msgs = [{"title": "口径盲区", "body": "是否缺了审批链？", "note": "说话人2 07:34",
                 "has_finding": True}]
        (tmp_path / "task-1.insights.json").write_text(
            json.dumps({"messages": msgs}, ensure_ascii=False), encoding="utf-8")
        block = build_insights_context_block("task-1")
        assert block and "（注：说话人2 07:34）" in block

    def test_cli_export_carries_note(self, tmp_path, monkeypatch):
        from core.cli_engine import context_export as ce
        monkeypatch.setattr(ce, "INSIGHTS_TASKS_DIR", tmp_path)
        msgs = [{"title": "口径盲区", "body": "是否缺了审批链？", "note": "说话人2 07:34"}]
        (tmp_path / "task-2.insights.json").write_text(
            json.dumps({"messages": msgs}, ensure_ascii=False), encoding="utf-8")
        out = ce._render_insights("task-2")
        assert "> 注：说话人2 07:34" in out


# ─── 预算块：注释层豁免声明 ───

class TestBudgetBlockNoteExemption:

    def test_budget_block_declares_note_exemption(self):
        block = build_page_budget_block(1.0)
        assert "不计入" in block and "（注：…）" in block
