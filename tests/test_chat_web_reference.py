"""tests/test_chat_web_reference.py — 学习辅导员角色契约 + 内置问答联网检索增强。

覆盖范围：
1. learning-tutor/insights.md 经 get_role_insight_prompt 解析后含新契约锚点
   （body 两段式 + 正反例、solution 可执行步骤、web_search 授权），旧占位符契约已移除。
2. app.routers.chat_shared.build_web_reference_block（内置问答路径预判-注入式联网增强）：
   注入 / 问答模式跳过 / 无任务跳过 / 未配置 key 跳过 / 判定失败降级 / 空对话跳过。
"""

import json

from app.routers.chat_shared import ChatRequest, build_web_reference_block, tasks
from core.agent_workspace import get_role_insight_prompt

JUDGE_REPLY = json.dumps({"need": True, "queries": ["代扣代缴 完税证明"]})
BRAVE_REPLY = json.dumps({
    "query": "代扣代缴 完税证明",
    "count": 1,
    "results": [{
        "title": "自然人代扣代缴指南",
        "description": "扣缴义务人代扣后可向税务机关申请开具完税凭证",
        "url": "https://example.com/tax",
    }],
}, ensure_ascii=False)

TASK_ID = "t-web-ref"


def _seed_task(monkeypatch, dialogue=True):
    """向共享 tasks 注入一个含对话与章节的测试任务（monkeypatch 自动还原）。"""
    task = {
        "title": "税务讨论",
        "dialogue": ([{"sentences": [
            {"text": "代扣代缴增值税到底怎么操作", "begin_time": 500},
            {"text": "讲者自己交钱才能开发票吗", "begin_time": 1600},
        ]}] if dialogue else []),
        "chapters": [{"title": "税务讨论"}],
    }
    monkeypatch.setitem(tasks, TASK_ID, task)


def _patch_search_on(monkeypatch, judge_reply=JUDGE_REPLY):
    """联网前置全开（mock execute_tool + mock 判定调用），返回调用捕获。

    联网检索已改为免密实现（Bing/DuckDuckGo），不再需要 API key 前置。
    """
    monkeypatch.setattr(
        "core.agent_tools.impl.execute_tool",
        lambda name, kwargs: BRAVE_REPLY if name == "web_search" else json.dumps({"error": "unknown"}),
    )
    calls = []

    async def fake_chat(messages, model=None, temperature=0.7, max_tokens=4096):
        calls.append({"messages": messages, "max_tokens": max_tokens})
        return judge_reply

    monkeypatch.setattr("core.insights.async_chat_completion", fake_chat)
    return calls


class TestLearningTutorContract:
    """角色契约经真实解析路径（get_role_insight_prompt）服务新约束。"""

    def test_role_prompt_has_body_and_solution_anchors(self):
        prompt = get_role_insight_prompt("learning-tutor")
        assert prompt is not None
        for anchor in (
            "完整句子",
            "不少于 15 字",
            "禁止把「阶段名」三个字当作前缀原样输出",
            "正例",
            "反例（禁止这样写）",
            "可执行的学习步骤",
            "web_search",
        ):
            assert anchor in prompt, f"角色契约缺少锚点: {anchor}"

    def test_role_prompt_old_placeholder_contract_removed(self):
        prompt = get_role_insight_prompt("learning-tutor")
        # 旧契约「阶段名：一句话」与可选口号式 solution 已被替换
        assert "阶段名：一句话" not in prompt
        assert "填补盲区的学习建议或思考问题（可选）" not in prompt


class TestBuildWebReferenceBlock:
    """内置问答路径联网增强：注入 / 各类跳过 / 降级。"""

    async def test_injects_reference_when_configured(self, monkeypatch):
        _seed_task(monkeypatch)
        calls = _patch_search_on(monkeypatch)
        data = ChatRequest(message="代扣代缴怎么操作", task_id=TASK_ID)
        block = await build_web_reference_block(data, is_qa_mode=False)
        assert "## 外部参考（联网检索" in block
        assert "自然人代扣代缴指南" in block
        # 仅一次判定调用（内置路径无主分析调用）
        assert len(calls) == 1
        assert calls[0]["max_tokens"] == 200

    async def test_qa_mode_skips(self, monkeypatch):
        _seed_task(monkeypatch)
        calls = _patch_search_on(monkeypatch)
        data = ChatRequest(message="x", task_id=TASK_ID, mode="qa")
        assert await build_web_reference_block(data, is_qa_mode=True) == ""
        assert calls == []

    async def test_no_task_skips(self, monkeypatch):
        calls = _patch_search_on(monkeypatch)
        data = ChatRequest(message="x")
        assert await build_web_reference_block(data, is_qa_mode=False) == ""
        assert calls == []

    async def test_unknown_task_skips(self, monkeypatch):
        calls = _patch_search_on(monkeypatch)
        data = ChatRequest(message="x", task_id="missing-task")
        assert await build_web_reference_block(data, is_qa_mode=False) == ""
        assert calls == []

    async def test_judge_failure_degrades(self, monkeypatch):
        _seed_task(monkeypatch)

        async def fake_chat(messages, model=None, temperature=0.7, max_tokens=4096):
            raise RuntimeError("judge down")

        monkeypatch.setattr("core.insights.async_chat_completion", fake_chat)
        data = ChatRequest(message="x", task_id=TASK_ID)
        assert await build_web_reference_block(data, is_qa_mode=False) == ""

    async def test_empty_dialogue_skips(self, monkeypatch):
        _seed_task(monkeypatch, dialogue=False)
        calls = _patch_search_on(monkeypatch)
        data = ChatRequest(message="x", task_id=TASK_ID)
        assert await build_web_reference_block(data, is_qa_mode=False) == ""
        assert calls == []
