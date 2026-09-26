"""
core/agent_tools/catalog.py — 反向工具目录（单一来源） / Reverse tool catalog (single source of truth)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

被两处消费（避免定义漂移，方案 §3.4）：
  - app/routers/agent_tools.py  — 服务端按 name 分发到受控 handler
  - mcp-bridge/server.py        — 向 CLI 声明 tools/list（SSE 协议里的 MCP 工具面）

读工具复用 core.agent_loop.execute_tool（与内置 Agent 循环同一实现）；
写工具复用 app.routers.notes 的既有函数（同一 tasks 内存 + save_task_to_disk + 脏标记）。
"""

from __future__ import annotations

# 每项：name / description / input_schema(JSON Schema) / kind(read|write) / needs_task(bool)
TOOL_CATALOG: list[dict] = [
    # ── 读工具（与内置 agent 循环共享实现） ──
    {
        "name": "get_meeting_info", "kind": "read", "needs_task": True,
        "description": "获取当前会议的结构化元信息与纪要摘要。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_meeting_transcript", "kind": "read", "needs_task": True,
        "description": "获取会议转写原文（可限量）。当工作区 transcript.md 不足以回答时调用。",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "最多返回句数，默认全量的采样"}},
        },
    },
    {
        "name": "get_meeting_todos", "kind": "read", "needs_task": True,
        "description": "获取当前会议的待办/决策事项列表。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_project_files", "kind": "read", "needs_task": False,
        "description": "在关联项目知识库中按关键词检索文档内容。",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "检索关键词"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_hotwords", "kind": "read", "needs_task": False,
        "description": "获取热词表（专有名词/人名校正词）。",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ── 写工具（复用 notes 路由的受控入口；仅 workspace_write/full_task 档可用） ──
    {
        "name": "update_summary", "kind": "write", "needs_task": True,
        "description": "用给定的 Markdown 覆盖当前会议纪要（用户可见的正式纪要）。",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string", "description": "完整的新纪要正文（Markdown）"}},
            "required": ["summary"],
        },
    },
    {
        "name": "inject_items", "kind": "write", "needs_task": True,
        "description": "向会议注入结构化条目（待办 todo / 结论 conclusion / 决策 decision），逐条落库并进入决策中心。",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "待注入条目数组",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["todo", "conclusion", "decision"]},
                            "content": {"type": "string"},
                        },
                        "required": ["type", "content"],
                    },
                }
            },
            "required": ["items"],
        },
    },
]

# 快速索引 / name → tool
TOOLS_BY_NAME: dict[str, dict] = {t["name"]: t for t in TOOL_CATALOG}

# MCP tools/list 形状（剥离内部 kind/needs_task 字段）
def mcp_tool_specs() -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
        for t in TOOL_CATALOG
    ]
