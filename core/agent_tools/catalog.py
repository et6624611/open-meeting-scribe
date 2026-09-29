"""
core/agent_tools/catalog.py — 反向工具目录（单一来源） / Reverse tool catalog (single source of truth)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

被两处消费（避免定义漂移，方案 §3.4）：
  - app/routers/agent_tools.py  — 服务端按 name 分发到受控 handler
  - mcp-bridge/server.py        — 向 CLI 声明 tools/list（SSE 协议里的 MCP 工具面）

读工具复用 core.agent_tools.impl.execute_tool（自建 Agent 循环退役后为唯一实现）；
写工具复用 app.routers.notes 的既有函数（同一 tasks 内存 + save_task_to_disk + 脏标记）。
"""

from __future__ import annotations

# 每项：name / description / input_schema(JSON Schema) / kind(read|write) / needs_task(bool)
TOOL_CATALOG: list[dict] = [
    # ── 读工具（实现在 core/agent_tools/impl.py，单一来源） ──
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
        "description": "用给定的 Markdown 覆盖当前会议纪要（用户可见的正式纪要）。【已弃用】纪要改写请改用 propose_summary（提案式，需用户确认后才落盘），本工具仅供历史兼容。",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string", "description": "完整的新纪要正文（Markdown）"}},
            "required": ["summary"],
        },
    },
    {
        # 纪要改写的唯一会话通道（提案式，不落盘）：产出一条待用户确认的建议，
        # proposed 正文经 tool_call 事件回前端 diff 卡，用户接受后才经 PUT /summary 落盘。
        # 实现在 app/routers/agent_tools.py（不写 task），mcp_bridge 按 kind=write 预授权。
        "name": "propose_summary", "kind": "write", "needs_task": True,
        "description": (
            "对会议纪要提出改写建议（提案式，不会立即写入）。这是纪要改写的唯一通道："
            "先用工作区内的基线纪要（context/summary.md）做增量，summary 传入修订后的完整纪要正文（Markdown），"
            "系统会向用户展示旧/新行级 diff，由用户点击「接受」才真正落盘、「拒绝」则丢弃。"
            "不得为了直接生效而调用 update_summary。只需一个建议就调一次，summary 为最终替换全文。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string", "description": "建议的新纪要正文（完整 Markdown，未经用户确认不落盘）"}},
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
    {
        # 洞察共创 HTML 产物（会话驱动唯一写入路径）；实现在 core.insight_board.invoke_revise_board，
        # schema 变更需同步工具描述消费方（自建 agent_loop 已退役，此处为唯一工具定义来源）。
        "name": "revise_insight_board", "kind": "write", "needs_task": True,
        "description": (
            "读取或修订当前会议的洞察板（一份自包含 HTML 文档）。"
            "不带 html 参数 = 读取当前板 HTML 原文（改写前先取基线，只读档也可用）；"
            "带 html 参数 = 整份落盘为新版本（需可写档）。"
            "共创契约：只输出一个 HTML 片段（不要 <!DOCTYPE>/<html>/<head>/<body> 外壳）；"
            "不得写 :root/html/body/* 等全局选择器，也不写硬编码颜色（后端会剥除全局块）；"
            "颜色/字号/圆角一律用本应用 CSS 变量以随主题自适应，可用令牌："
            "--surface/--surface-2/--surface-3/--bg/--fg/--muted/--subtle/--border/--accent/--accent-soft/--ok/--warn/--info/--error/--purple（及 -soft 背景变体）；"
            "需要关联转写位置时用 <a data-seek-ms=\"毫秒\"> 锚点；"
            "顶层每个逻辑节包成扁平的 <section data-ib-id=\"s1\" data-ib-title=\"节标题\">…</section>（节不嵌套、id 稳定），以便支持单节共创；"
            "先读当前 HTML 做增量修改，每次聚焦用户诉求，不推倒重来。"
            "版式一致性（重要）：首版（无基线）时先选定一套版式骨架（标题条 + 分节卡片/流程图等）并沿用；"
            "此后每次修订必须继承基线已有的版式与视觉语言——同样的节结构、卡片/流程图样式、配色令牌用法，只改内容不改排版；"
            "严禁在修订中把文字段落式布局整体换成卡片/流程图式（或反向切换）等风格跳变，除非用户明确要求「重做版式 / 换一种排版」。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "html": {"type": "string", "description": "完整的新版洞察板 HTML 文档（整份替换语义）；缺省则读取当前板"},
            },
        },
    },
    {
        # 单节共创：只替换板内指定 data-ib-id 的一节，其余节硬隔离。
        "name": "revise_insight_board_section", "kind": "write", "needs_task": True,
        "description": (
            "只修订洞察板中某一节（按节锈点 id 定位替换），其余节逐字节不动。"
            "需先调 revise_insight_board（不带 html）读到当前板，定位目标节的 data-ib-id。"
            "html 传入修订后的完整节块（<section data-ib-id=\"\u2026\">…</section>，保持同一 id）；"
            "同样只写片段、用应用 CSS 变量、禁全局选择器与硬编码色。适用于用户只关心改某一节的场景。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string", "description": "目标节的 data-ib-id 值"},
                "html": {"type": "string", "description": "修订后的完整单节 HTML（<section data-ib-id=…>…</section>）"},
            },
            "required": ["section_id", "html"],
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
