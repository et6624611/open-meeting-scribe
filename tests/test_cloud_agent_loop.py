"""云端 ReAct 循环（core.cloud_agent_loop）单元测试。"""

import json

import pytest

import core.cloud_agent_loop as loop


def _tool_call(call_id: str, name: str, args: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


@pytest.mark.asyncio
async def test_react_calls_tool_then_answers(monkeypatch):
    """第一轮返回工具调用，执行后回填消息；第二轮给出最终答复。"""
    rounds = [
        {"content": "", "tool_calls": [_tool_call("c1", "web_search", {"query": "ERP 组织变更"})]},
        {"content": "根据检索，结论如下。", "tool_calls": []},
    ]
    seen_messages = []

    async def fake_llm(messages, **kwargs):
        seen_messages.append(list(messages))
        return rounds.pop(0)

    monkeypatch.setattr(loop, "async_chat_completion_with_tools", fake_llm)
    monkeypatch.setattr(
        loop, "execute_tool",
        lambda name, args, task_id=None, project_id=None: json.dumps(
            {"query": args["query"], "results": [{"title": "T", "url": "https://example.com"}]},
            ensure_ascii=False,
        ),
    )

    events = [e async for e in loop.run_cloud_agent(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "问"}],
    )]

    types = [e["type"] for e in events]
    assert types == ["tool_call", "tool_result", "token"]
    assert events[0]["name"] == "web_search"
    assert events[0]["args"] == {"query": "ERP 组织变更"}
    assert events[1]["success"] is True
    assert "T" in events[1]["output"]
    assert events[2]["content"] == "根据检索，结论如下。"
    # 工具结果已作为 tool 消息回填
    assert seen_messages[1][-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_duplicate_tool_call_skipped(monkeypatch):
    """同一工具同一参数重复调用不再执行。"""
    calls = [
        _tool_call("c1", "web_fetch", {"url": "https://example.com"}),
        _tool_call("c2", "web_fetch", {"url": "https://example.com"}),
    ]
    rounds = [
        {"content": "", "tool_calls": calls},
        {"content": "done", "tool_calls": []},
    ]

    async def fake_llm(messages, **kwargs):
        return rounds.pop(0)

    executed = []
    monkeypatch.setattr(loop, "async_chat_completion_with_tools", fake_llm)
    monkeypatch.setattr(
        loop, "execute_tool",
        lambda name, args, task_id=None, project_id=None: executed.append(name) or json.dumps({"ok": True}),
    )

    events = [e async for e in loop.run_cloud_agent(
        messages=[{"role": "user", "content": "x"}], task_id=None,
    )]
    assert len(executed) == 1
    dup = [e for e in events if e["type"] == "tool_result" and not e["success"]]
    assert len(dup) == 1
    assert json.loads(dup[0]["output"])["error"] == "duplicate_call"


def test_tool_specs_exclude_write_and_task_bound():
    """只暴露只读工具；无 task_id 时剔除需要会议的检索工具。"""
    specs = loop._tool_specs(None)
    names = {s["function"]["name"] for s in specs}
    assert "web_search" in names
    assert "update_summary" not in names
    assert "get_meeting_transcript" not in names
