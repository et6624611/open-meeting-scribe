"""
core/agent_loop.py — Agent 循环执行器（ReAct 模式） / Agent loop executor (ReAct pattern)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-16
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 定义 Agent 可用工具（JSON Schema） / Define agent-available tools (JSON Schema)
  - 工具执行分发器 / Tool execution dispatcher
  - ReAct 循环：LLM 思考 → 工具调用 → 结果回传 → 最终回复 / ReAct loop: think → tool call → result → final answer
  - SSE 事件生成（stage / tool_call / tool_result） / SSE event generation
  - 双模式支持：原生 function calling + 文本格式回退 / Dual-mode: native function calling + text-based fallback

设计 / Design:
  - 工具调用阶段使用非流式 LLM（需完整解析 tool_calls） / Tool-calling phase uses non-streaming LLM
  - 最终回复阶段使用流式 LLM（逐 token 推送） / Final answer phase uses streaming LLM
  - 安全限制：最多 8 轮迭代、60 秒超时、重复调用检测 / Safety: max 8 iterations, 60s timeout, duplicate detection
"""

import asyncio
import json
import logging
import re
import time
from typing import AsyncGenerator

from app.store import tasks
from core import hotwords as hw_module
from core import projects as proj_module
from core.project_index import get_project_context_for_chat

logger = logging.getLogger(__name__)

# ============================================================
# 常量 / Constants
# ============================================================

MAX_AGENT_ITERATIONS = 8
AGENT_TIMEOUT_SECONDS = 60

# ============================================================
# 工具定义（OpenAI function calling 格式） / Tool definitions
# ============================================================

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_meeting_info",
            "description": "获取当前会议的元数据信息，包括标题、状态、时长、说话人数量等。当需要了解会议基本情况时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_meeting_transcript",
            "description": "获取当前会议的转写内容（对话记录）。当需要查看会议中某人说了什么、查找具体发言内容时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回的最大发言条数，默认 20，最大 50",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_meeting_todos",
            "description": "获取当前会议的待办事项列表。当用户询问待办、任务、跟进事项时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_project_files",
            "description": "按关键词搜索当前关联项目的资料文件内容。当用户询问项目相关资料、文件内容、业务问题时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，描述你要查找的信息",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hotwords",
            "description": "获取系统自定义热词列表。当用户询问热词配置、ASR 识别优化时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_settings",
            "description": "获取系统配置信息（语言、默认模型、主题等）。当用户询问系统设置、配置时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# 工具名 → 中文标签（供前端显示） / Tool name → Chinese label for frontend display
TOOL_LABELS = {
    "get_meeting_info": "获取会议信息",
    "get_meeting_transcript": "读取会议转写",
    "get_meeting_todos": "查询待办事项",
    "search_project_files": "搜索项目资料",
    "get_hotwords": "获取热词列表",
    "get_system_settings": "获取系统设置",
}

TOOL_ICONS = {
    "get_meeting_info": "📋",
    "get_meeting_transcript": "💬",
    "get_meeting_todos": "✅",
    "search_project_files": "📂",
    "get_hotwords": "🔤",
    "get_system_settings": "⚙️",
}


# ============================================================
# 工具执行器 / Tool Executor
# ============================================================


def execute_tool(name: str, arguments: dict, task_id: str | None = None, project_id: str | None = None) -> str:
    """执行工具并返回 JSON 字符串结果 / Execute tool and return JSON string result."""
    try:
        if name == "get_meeting_info":
            return _tool_get_meeting_info(task_id)
        elif name == "get_meeting_transcript":
            return _tool_get_meeting_transcript(task_id, arguments.get("limit", 20))
        elif name == "get_meeting_todos":
            return _tool_get_meeting_todos(task_id)
        elif name == "search_project_files":
            return _tool_search_project_files(project_id, arguments.get("query", ""))
        elif name == "get_hotwords":
            return _tool_get_hotwords()
        elif name == "get_system_settings":
            return _tool_get_system_settings()
        else:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    except Exception as e:
        logger.error("工具执行失败 [%s]: %s", name, e)
        return json.dumps({"error": f"工具执行失败: {e}"}, ensure_ascii=False)


def _tool_get_meeting_info(task_id: str | None) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    info = {
        "title": task.get("title") or task.get("audio_name") or "未命名会议",
        "status": task.get("status", "未知"),
        "audio_duration_seconds": task.get("audio_duration"),
        "speaker_count": task.get("speaker_count"),
        "created_at": task.get("created_at", ""),
    }
    if task.get("summary"):
        info["summary_preview"] = task["summary"][:300]
    return json.dumps(info, ensure_ascii=False)


def _tool_get_meeting_transcript(task_id: str | None, limit: int) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    dialogue = task.get("dialogue") or []
    if not dialogue:
        return json.dumps({"info": "该会议暂无转写记录"}, ensure_ascii=False)

    lines = []
    count = 0
    limit = min(limit, 50)
    for item in dialogue:
        if count >= limit:
            break
        name = item.get("speaker_name") or f"Speaker {item.get('speaker_id', 0) + 1}"
        sents = item.get("sentences") or []
        for s in sents:
            if count >= limit:
                break
            text = s.get("text", "").strip()
            if text:
                ts_ms = s.get("begin_time", 0)
                total_sec = int(ts_ms / 1000)
                m, sec = divmod(total_sec, 60)
                h, m = divmod(m, 60)
                ts = f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
                lines.append(f"[{ts}] {name}: {text}")
                count += 1
        if not sents:
            text = item.get("text", "").strip()
            if text:
                lines.append(f"{name}: {text}")
                count += 1

    return json.dumps({"transcript_lines": lines, "total": count}, ensure_ascii=False)


def _tool_get_meeting_todos(task_id: str | None) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    todos = task.get("todos") or []
    if not todos:
        return json.dumps({"info": "该会议暂无待办事项", "count": 0}, ensure_ascii=False)
    items = []
    for t in todos:
        items.append({
            "text": t.get("text", ""),
            "done": t.get("done", False),
            "assignee": t.get("assignee", "未分配"),
        })
    return json.dumps({"todos": items, "count": len(items)}, ensure_ascii=False)


def _tool_search_project_files(project_id: str | None, query: str) -> str:
    if not project_id:
        return json.dumps({"info": "当前没有关联的项目资料"}, ensure_ascii=False)
    if not query:
        return json.dumps({"info": "请提供搜索关键词"}, ensure_ascii=False)
    context_text, source_files = get_project_context_for_chat(project_id, query)
    if not context_text:
        return json.dumps({"info": f"未找到与「{query}」相关的项目资料", "files_found": 0}, ensure_ascii=False)
    file_names = [f.get("title") or f.get("name", "") for f in source_files]
    return json.dumps({
        "content": context_text[:3000],
        "files_found": len(file_names),
        "file_names": file_names,
    }, ensure_ascii=False)


def _tool_get_hotwords() -> str:
    words = hw_module.load_hotwords()
    if not words:
        return json.dumps({"info": "暂无自定义热词", "count": 0}, ensure_ascii=False)
    return json.dumps({"hotwords": words[:50], "count": len(words)}, ensure_ascii=False)


def _tool_get_system_settings() -> str:
    from app.store import load_settings
    settings = load_settings()
    safe_keys = ["language", "default_model", "theme", "hotwords_enabled"]
    info = {k: settings.get(k) for k in safe_keys if settings.get(k) is not None}
    return json.dumps(info, ensure_ascii=False)


# ============================================================
# 文本格式回退：工具描述注入 / Text-based fallback: tool description injection
# ============================================================

TEXT_TOOLS_INJECTION = """
<tools>
你可以调用以下工具来获取信息。当你需要查看数据时，输出工具调用指令（系统会执行并返回结果）：

格式：每个工具调用独占一行

## 可用工具
1. get_meeting_info() — 获取当前会议元数据（标题、状态、时长等）
2. get_meeting_transcript(limit=20) — 获取会议转写内容，limit 为最大条数
3. get_meeting_todos() — 获取会议待办事项列表
4. search_project_files(query="关键词") — 搜索项目资料文件内容
5. get_hotwords() — 获取自定义热词列表
6. get_system_settings() — 获取系统配置信息

## 调用格式
要调用工具时，输出如下格式（每行一个调用）：

[TOOL_CALL] tool_name(arg1=value1, arg2=value2)

例如：
[TOOL_CALL] search_project_files(query="预算方案")

## 重要规则
- 当你需要查看数据才能回答时，先调用工具获取数据
- 可以一次调用多个工具（每行一个）
- 工具调用后，系统会返回结果，你再基于结果生成最终回复
- 如果不需要工具就能回答，直接回复即可
</tools>
"""


def _parse_text_tool_calls(content: str) -> tuple[list[dict], str]:
    """从文本内容中解析工具调用，返回 (tool_calls, remaining_content)。
    Parse tool calls from text content, return (tool_calls, remaining_content).
    """
    tool_calls = []
    remaining_lines = []
    pattern = re.compile(r'\[TOOL_CALL\]\s*(\w+)\((.*?)\)', re.DOTALL)

    for line in content.split('\n'):
        match = pattern.search(line.strip())
        if match:
            func_name = match.group(1)
            args_str = match.group(2).strip()
            args = _parse_tool_args(args_str)
            tool_calls.append({
                "function": {"name": func_name, "arguments": json.dumps(args, ensure_ascii=False)},
            })
        else:
            remaining_lines.append(line)

    return tool_calls, '\n'.join(remaining_lines).strip()


def _parse_tool_args(args_str: str) -> dict:
    """解析工具参数字符串（key=value 格式） / Parse tool argument string (key=value format)."""
    if not args_str:
        return {}
    args = {}
    # 匹配 key="value" 或 key=number
    for m in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*?)"|(\S+?))(?:,|$)', args_str):
        key = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        # 尝试转换数字
        try:
            value = int(value)
        except (ValueError, TypeError):
            pass
        args[key] = value
    return args


# ============================================================
# Agent 循环核心 / Agent Loop Core
# ============================================================


async def run_agent_loop(
    user_message: str,
    system_prompt: str,
    history: list[dict],
    task_id: str | None,
    project_id: str | None,
    model: str,
) -> AsyncGenerator[dict, None]:
    """
    Agent 循环执行器（ReAct 模式）。

    Yields SSE 事件 dict：
      - {"type": "stage", "stage": "thinking"|"generating"|"done", "label": "..."}
      - {"type": "tool_call", "name": "...", "label": "...", "icon": "...", "args": {...}}
      - {"type": "tool_result", "name": "...", "summary": "...", "success": true}
      - {"type": "token", "content": "..."}
      - {"type": "done", "metadata": {...}, "latency_ms": ..., ...}
      - {"type": "error", "content": "..."}
    """
    start_time = time.perf_counter()
    iteration = 0

    # 构建消息列表 / Build messages
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-10:]:
        role = "user" if msg.get("role") == "user" else "assistant"
        content = msg.get("content", "")
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    # 判断是否支持原生 function calling / Check if native function calling is supported
    use_native_tools = _supports_native_tools(model)

    if not use_native_tools:
        # 文本格式回退：注入工具描述到 system prompt / Text fallback: inject tool descriptions
        messages[0]["content"] += TEXT_TOOLS_INJECTION

    # 记录已调用的工具（防重复） / Track called tools (prevent duplicates)
    called_tools: set[str] = set()

    # 发送初始思考阶段 / Emit initial thinking stage
    yield {"type": "stage", "stage": "thinking", "label": "分析用户意图..."}

    while iteration < MAX_AGENT_ITERATIONS:
        iteration += 1
        elapsed = time.perf_counter() - start_time
        if elapsed > AGENT_TIMEOUT_SECONDS:
            logger.warning("Agent 循环超时 (%.1fs)", elapsed)
            break

        logger.info("Agent 循环第 %d 轮, 已耗时 %.1fs", iteration, elapsed)

        # 调用 LLM / Call LLM
        try:
            if use_native_tools:
                response = await _call_llm_with_tools(messages, model)
            else:
                from core.llm import async_chat_completion_full
                response = await async_chat_completion_full(messages, model=model, max_tokens=4096)
        except Exception as e:
            logger.error("Agent LLM 调用失败: %s", e)
            yield {"type": "error", "content": f"AI 调用失败: {e}"}
            return

        # 解析响应 / Parse response
        tool_calls = []
        content = ""

        if use_native_tools and isinstance(response, dict):
            # 原生 function calling 响应 / Native function calling response
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "") or ""
            raw_tool_calls = message.get("tool_calls") or []
            for tc in raw_tool_calls:
                func = tc.get("function", {})
                tool_calls.append({
                    "function": {
                        "name": func.get("name", ""),
                        "arguments": func.get("arguments", "{}"),
                    },
                    "id": tc.get("id", ""),
                })
        elif hasattr(response, "content"):
            # LlmResult 对象（文本回退路径） / LlmResult object (text fallback path)
            content = response.content or ""
            # 尝试解析文本格式工具调用 / Try parsing text-format tool calls
            tool_calls, remaining = _parse_text_tool_calls(content)
            if tool_calls:
                content = remaining  # 保留非工具调用的文本
            else:
                # 无工具调用，content 就是最终回复 / No tool calls, content is the final answer
                pass
        else:
            content = str(response)

        # 如果没有工具调用，进入最终回复流式输出 / No tool calls → final answer streaming
        if not tool_calls:
            logger.info("Agent 第 %d 轮: 无工具调用，进入最终回复", iteration)
            yield {"type": "stage", "stage": "generating", "label": "整合信息，生成回复..."}

            # 如果之前有工具调用结果，需要重新调用 LLM 流式生成最终回复
            # If there were previous tool call results, re-call LLM with streaming for final answer
            if iteration > 1:
                # 把之前的完整回复作为 assistant 消息，再请求流式最终回复
                # This shouldn't normally happen — if there were tool calls, the last iteration
                # should have content="" and we stream from the messages context
                pass

            # 流式输出最终回复 / Stream final answer
            try:
                from core.llm import async_chat_completion_stream
                async for token in async_chat_completion_stream(messages, model=model, max_tokens=4096):
                    yield {"type": "token", "content": token}
            except Exception as e:
                logger.error("Agent 流式回复失败: %s", e)
                # 如果流式失败但有内容，用 content 作为兜底
                if content:
                    yield {"type": "token", "content": content}
                else:
                    yield {"type": "error", "content": f"回复生成失败: {e}"}
                return

            # 完成 / Done
            total_ms = round((time.perf_counter() - start_time) * 1000)
            yield {
                "type": "done",
                "metadata": {"model": model},
                "latency_ms": total_ms,
                "agent_iterations": iteration,
            }
            return

        # 有工具调用 → 执行工具 / Tool calls present → execute tools
        logger.info("Agent 第 %d 轮: %d 个工具调用", iteration, len(tool_calls))

        # 构建 assistant 消息（含工具调用） / Build assistant message with tool calls
        if use_native_tools:
            assistant_msg = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls,
            }
        else:
            # 文本模式：assistant 消息只包含原始内容 / Text mode: assistant message contains original content
            assistant_msg = {"role": "assistant", "content": content or ""}
        messages.append(assistant_msg)

        # 逐个执行工具 / Execute each tool
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments", "{}"))
            except json.JSONDecodeError:
                args = _parse_tool_args(tc["function"].get("arguments", ""))

            # 防重复调用检查 / Duplicate call detection
            call_key = f"{func_name}:{json.dumps(args, sort=True, ensure_ascii=False)}"
            if call_key in called_tools:
                logger.info("跳过重复工具调用: %s", func_name)
                result_text = json.dumps({"info": "该工具已调用过，结果已在上下文中"}, ensure_ascii=False)
            else:
                called_tools.add(call_key)
                label = TOOL_LABELS.get(func_name, func_name)
                icon = TOOL_ICONS.get(func_name, "🔧")

                # 发送工具调用事件 / Emit tool_call event
                yield {
                    "type": "tool_call",
                    "name": func_name,
                    "label": label,
                    "icon": icon,
                    "args": args,
                }

                # 执行工具（线程池中运行，避免阻塞事件循环） / Execute tool in thread pool
                result_text = await asyncio.to_thread(
                    execute_tool, func_name, args, task_id, project_id
                )

            # 发送工具结果事件 / Emit tool_result event
            result_summary = _summarize_tool_result(func_name, result_text)
            yield {
                "type": "tool_result",
                "name": func_name,
                "summary": result_summary,
                "success": '"error"' not in result_text.lower(),
            }

            # 将工具结果追加到消息列表 / Append tool result to messages
            if use_native_tools:
                tool_msg = {
                    "role": "tool",
                    "content": result_text,
                    "tool_call_id": tc.get("id", ""),
                }
            else:
                # 文本模式：以 system 消息形式注入 / Text mode: inject as system message
                tool_msg = {
                    "role": "system",
                    "content": f"[工具 {func_name} 返回结果]\n{result_text}",
                }
            messages.append(tool_msg)

        # 继续下一轮 LLM 调用 / Continue to next LLM iteration
        yield {"type": "stage", "stage": "thinking", "label": "分析工具结果..."}

    # 超出最大迭代次数 / Max iterations exceeded
    total_ms = round((time.perf_counter() - start_time) * 1000)
    yield {
        "type": "done",
        "metadata": {"model": model},
        "latency_ms": total_ms,
        "agent_iterations": iteration,
        "warning": "达到最大迭代次数",
    }


# ============================================================
# 辅助函数 / Helper Functions
# ============================================================


def _supports_native_tools(model: str) -> bool:
    """判断模型是否支持原生 function calling / Check if model supports native function calling."""
    # DashScope qwen 系列支持 function calling
    supported_prefixes = ("qwen-", "qwen2", "qwen3")
    model_lower = (model or "").lower()
    return any(model_lower.startswith(p) for p in supported_prefixes)


async def _call_llm_with_tools(messages: list[dict], model: str) -> dict:
    """调用 LLM 并传递工具定义（原生 function calling） / Call LLM with tool definitions (native function calling).

    云端代理不支持 tools 时自动回退到无工具调用。
    Falls back to no-tools call when cloud proxy doesn't support tools.
    """
    from core.llm import _should_use_cloud, _get_cloud_user_id

    if _should_use_cloud():
        try:
            return await asyncio.to_thread(
                _cloud_llm_with_tools, messages, model
            )
        except Exception as e:
            # 云端代理不支持 tools，回退到普通调用 / Cloud proxy doesn't support tools, fallback
            logger.info("云端代理不支持 function calling，回退到普通调用: %s", e)
            from core.llm import async_chat_completion_full
            result = await async_chat_completion_full(messages, model=model, max_tokens=4096)
            # 转换为 dict 格式以兼容调用方 / Convert to dict format for caller compatibility
            return {
                "choices": [{"message": {"content": result.content, "tool_calls": None}}],
                "model": model,
            }

    # 本地 API Key 路径：直接调用 DashScope / Local API key path: call DashScope directly
    from core.llm import _get_base_url, _get_headers, _get_async_client

    base_url = _get_base_url()
    client = _get_async_client()
    headers = _get_headers()
    body = {
        "model": model or "qwen-plus",
        "messages": messages,
        "tools": AGENT_TOOLS,
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=body)
    resp.raise_for_status()
    return resp.json()


def _cloud_llm_with_tools(messages: list[dict], model: str) -> dict:
    """通过云端代理调用 LLM（带工具定义） / Call LLM via cloud proxy (with tool definitions)."""
    from core.cloud_client import cloud_llm_chat_with_tools, is_cloud_enabled
    from core.llm import _get_cloud_user_id

    user_id = _get_cloud_user_id()
    effective_model = model or "qwen-plus"

    result = cloud_llm_chat_with_tools(
        messages, AGENT_TOOLS, effective_model,
        temperature=0.3, max_tokens=4096, user_id=user_id,
    )

    if result is None:
        if not is_cloud_enabled():
            raise RuntimeError("AI 功能未配置")
        raise RuntimeError("云端 AI 服务调用失败")
    return result


def _summarize_tool_result(name: str, result_text: str) -> str:
    """生成工具结果的简短摘要 / Generate short summary of tool result."""
    try:
        data = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        return result_text[:80]

    if "error" in data:
        return f"失败: {data['error'][:60]}"
    if "info" in data:
        return data["info"][:80]

    # 按工具类型生成摘要 / Generate summary per tool type
    if name == "get_meeting_info":
        return f"会议: {data.get('title', '未知')} ({data.get('status', '')})"
    elif name == "get_meeting_transcript":
        count = data.get("total", 0)
        return f"获取 {count} 条发言记录"
    elif name == "get_meeting_todos":
        count = data.get("count", 0)
        return f"获取 {count} 条待办事项"
    elif name == "search_project_files":
        found = data.get("files_found", 0)
        names = data.get("file_names", [])
        if found > 0:
            return f"找到 {found} 个文件: {', '.join(names[:3])}"
        return "未找到相关文件"
    elif name == "get_hotwords":
        count = data.get("count", 0)
        return f"获取 {count} 个热词"
    elif name == "get_system_settings":
        return "获取系统设置成功"
    else:
        return result_text[:80]
