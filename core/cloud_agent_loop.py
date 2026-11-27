"""云端模型 ReAct 循环。

自建 Agent 循环曾为 CLI 引擎让路而退役；CLI 模式由 CLI 原生工具驱动，
内置/云端模型则以本模块补齐 ReAct：模型可多轮调用只读工具（联网搜索、
网页抓取、会议数据检索），每轮把工具结果回填消息后继续推理，直至给出答复。

事件协议与 CLI 引擎保持一致：
  {"type": "tool_call", "id", "name", "args"}
  {"type": "tool_result", "id", "name", "output", "success"}
  {"type": "token", "content"}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from core.agent_tools.catalog import TOOL_CATALOG
from core.agent_tools.impl import execute_tool
from core.llm import async_chat_completion_with_tools

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6
MAX_TOOL_OUTPUT_CHARS = 8000
TOOL_HINT = (
    "你可以调用工具补足信息。涉及会外实时知识、行业标准、竞品方案、外部产品能力时，"
    "先调用 web_search；需要细读某个网页时调用 web_fetch。工具结果是外部参考，"
    "最终答复必须区分「会议内事实」与「外部资料」，并标注来源链接。"
    "只要 web_search 返回了 results，就必须基于这些结果作答；"
    "不要把某一次检索失败夸大为全部不可用，更不要凭空编造来源。"
)


def _tool_specs(task_id: str | None) -> list[dict]:
    """从统一 catalog 生成 OpenAI function tools；只暴露只读工具。"""
    specs: list[dict] = []
    for tool in TOOL_CATALOG:
        if tool.get("kind") != "read":
            continue
        if tool.get("needs_task") and not task_id:
            continue
        specs.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
            },
        })
    return specs


def _inject_tool_hint(messages: list[dict]) -> list[dict]:
    """把工具使用约束并入系统消息，避免模型把外部资料当会议事实。"""
    out: list[dict] = []
    injected = False
    for msg in messages:
        if not injected and msg.get("role") == "system":
            out.append({**msg, "content": (msg.get("content") or "") + "\n\n" + TOOL_HINT})
            injected = True
        else:
            out.append(dict(msg))
    if not injected:
        out.insert(0, {"role": "system", "content": TOOL_HINT})
    return out


def _is_error_result(raw: str) -> bool:
    try:
        data = json.loads(raw)
        return isinstance(data, dict) and bool(data.get("error"))
    except Exception:
        return False


def _split_chunks(text: str, size: int = 24) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


async def run_cloud_agent(
    *,
    messages: list[dict],
    model: str | None = None,
    task_id: str | None = None,
    project_id: str | None = None,
    temperature: float = 0.5,
    max_tokens: int = 4096,
) -> AsyncGenerator[dict, None]:
    """多轮工具调用直至产出最终答复；事件逐条 yield 给 SSE 层。"""
    tools = _tool_specs(task_id)
    convo = _inject_tool_hint(messages)
    called: set[str] = set()

    for _ in range(MAX_ITERATIONS):
        try:
            message = await async_chat_completion_with_tools(
                convo,
                tools=tools,
                model=model,
                temperature=temperature,
                max_tokens=min(max_tokens, 2048),
                tool_choice="auto",
            )
        except Exception as e:
            logger.warning("[云端ReAct] LLM 调用失败: %s", e)
            yield {"type": "error", "content": str(e)}
            return

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content = str(message.get("content") or "")
            for chunk in _split_chunks(content):
                yield {"type": "token", "content": chunk}
            return

        convo.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
        })

        for call in tool_calls:
            fn = (call.get("function") or {})
            name = str(fn.get("name") or "")
            call_id = str(call.get("id") or "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except Exception:
                args = {}

            yield {"type": "tool_call", "id": call_id, "name": name, "args": args}

            signature = name + ":" + json.dumps(args, ensure_ascii=False, sort_keys=True)
            if signature in called:
                output = json.dumps({"error": "duplicate_call", "message": "重复调用已跳过"}, ensure_ascii=False)
            else:
                called.add(signature)
                try:
                    output = await asyncio.to_thread(execute_tool, name, args, task_id, project_id)
                except Exception as e:
                    logger.warning("[云端ReAct] 工具 %s 执行失败: %s", name, e)
                    output = json.dumps({"error": "tool_execution_failed", "message": str(e)}, ensure_ascii=False)

            success = not _is_error_result(output)
            yield {
                "type": "tool_result",
                "id": call_id,
                "name": name,
                "output": str(output)[:MAX_TOOL_OUTPUT_CHARS],
                "success": success,
            }
            convo.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": str(output)[:MAX_TOOL_OUTPUT_CHARS],
            })

    yield {"type": "token", "content": "（工具调用次数已达上限，基于现有信息作答）"}
