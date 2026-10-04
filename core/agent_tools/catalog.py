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
# 可选字段 persists（仅对 kind=write 有意义）：False = 名义可写、实际不落盘（提案信号），
# 必须从完成护栏的 rewritten 触发集中剔除（runner 据此字段派生，不再硬写工具名）。
TOOL_CATALOG: list[dict] = [
    # ── 读工具（实现在 core/agent_tools/impl.py，单一来源） ──
    {
        "name": "get_meeting_info", "kind": "read", "needs_task": True,
        "description": "获取当前会议的结构化元信息与纪要摘要（含随记存在性与预览）。",
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
        # 随记（user_notes）：四域中唯一的用户原创区，此前工具面/工作区都读不到（2026-09-30 复盘）
        "name": "get_meeting_notes", "kind": "read", "needs_task": True,
        "description": (
            "获取用户在会议期间手写的随记原文（user_notes）。随记是用户原创区、可信度高于转写推断："
            "当用户说「我写在随记里了」「按随记更新纪要/决策」时，先调本工具读随记再动手。"
            "本工具只读，不得用它声称已改写随记（随记改写需用户在前端确认）。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_meeting_todos", "kind": "read", "needs_task": True,
        "description": "获取当前会议的待办/决策事项列表（含节点稳定 id 与状态，供按节点寻址）。",
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
        "name": "propose_summary", "kind": "write", "needs_task": True, "persists": False,
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
        # 随记改写的唯一会话通道（提案式，不落盘）：user_notes 是用户原创区（PROPOSAL §5.3 市场模式 D），
        # 与其他域不同构：工具只产出建议，前端行级 diff 预览，用户点「接受」才经 PUT /notes 落盘。
        # 实现在 app/routers/agent_tools.py（不写 task）；mcp_bridge 按 kind=write 预授权。
        "name": "propose_notes", "kind": "write", "needs_task": True, "persists": False,
        "description": (
            "对用户随记提出改写建议（提案式，不会立即写入）。这是随记改写的唯一通道："
            "先读工作区 context/notes.md（或调 get_meeting_notes）拿到用户原文，在其基础上做增量，"
            "notes 传入修订后的**完整随记正文**（纯文本，保留用户自己的口吻与条目写法）。"
            "系统会向用户展示旧/新行级 diff，由用户点「接受」才真正落盘、「拒绝」则丢弃。"
            "严禁在提案被接受前声称已写入随记；也不要拿随记去覆盖纪要（纪要走 propose_summary）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"notes": {"type": "string", "description": "建议的新随记正文（完整替换；未经用户确认不落盘）"}},
            "required": ["notes"],
        },
    },
    {
        "name": "inject_items", "kind": "write", "needs_task": True,
        "description": "向会议注入结构化条目（待办 todo / 结论 conclusion / 决策 decision），逐条落库并进入决策中心。仅用于新增；修改已有节点请改用 update_decision_node。",
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
        # 决策节点改写（P3）：按节点 id 寻址，收口到 notes.update_todo 同一口径（DC-UNIFY-01）。
        # 写回前强制字段级快照（core.rewrite_snapshots），因此“AI 误写可回退”成立。
        "name": "update_decision_node", "kind": "write", "needs_task": True,
        "description": (
            "改写已有的决策流节点（按节点 id 精准定位，不新建第二条）。"
            "必先调 get_meeting_todos 拿到节点 id、当前状态与可用状态字典（status 只能取其中的 id）。"
            "只传需要改的字段：title（一句话结论）、text（决策正文）、status（如用户已拍板→推进到闭档态）、"
            "why（依据）、outcome（结果）、owner_type（推进方）。"
            "用户说「按随记/纪要把这几条定为已确认」类需求时，逐条按 id 更新，不要用 inject_items 重复追加。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "节点稳定 id（来自 get_meeting_todos）"},
                "title": {"type": "string", "description": "新标题（一句话结论）"},
                "text": {"type": "string", "description": "新的决策正文"},
                "status": {"type": "string", "description": "状态字典中的 id（如 to_decide / done）"},
                "why": {"type": "string", "description": "决策依据"},
                "outcome": {"type": "string", "description": "执行结果/落地情况"},
                "owner_type": {"type": "string", "enum": ["self", "agent", "colleague", "enterprise"]},
            },
            "required": ["node_id"],
        },
    },
    {
        # 决策节点删除（P3）：复用 notes.delete_todo，auto 节点同步落防复活墓碑。
        "name": "delete_decision_node", "kind": "write", "needs_task": True,
        "description": (
            "按节点 id 删除一条决策流节点（仅当用户明确要求删除/合并时）。"
            "删前建议先 get_meeting_todos 确认对象；删错可由本轮快照撤销。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"node_id": {"type": "string", "description": "待删除节点的稳定 id"}},
            "required": ["node_id"],
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
            "【内容底线·最重要，违反会被后端整份拒收并返回 error=board_is_recap】"
            "洞察板唯一任务：针对本场会议暴露的困境，给出会上没人想到的 AI 最优解法。"
            "你被授权调用外部行业知识、标准实践、成熟架构来构造解法；会议内容只用于界定问题，不用于复述。"
            "每节按「困境（一句话界定）→ 外部最优解法（具体、可执行，附原理或出处）→ 落地步骤与取舍」组织；"
            "风险/未决项必须每条紧跟一个可落地解法，禁止只罗列问题。"
            "严禁入板：决策清单（含 DC-1 类编号）、议题/章节归类、待办与人员分工（谁做什么、截止日期）、"
            "参会人立场与「谁说了什么」、带说话人/时间戳的依据流水、会议概览与摘要复述"
            "——这些已由逐字稿、纪要页、决策中心承载，再写一遍就是失败。"
            "若读到的旧基线是上述复述结构，允许且应当推倒重做为解法结构，不受下方版式继承条款约束。"
            "【图形化·硬约束，纯文字墙会被后端拒收 error=board_is_text_wall】"
            "板是图不是文章：每个困境一节，先画后主文，顺序固定为 h3 短标题 → div.ib-dilemma 困境条（困境出处挂 <a data-seek-ms=毫秒>）"
            "→ div.ib-visual 主视觉（每节必须恰好一个）→ span.ib-kicker + 简短图文 → ol.ib-roadmap 落地步骤 → div.ib-tradeoff 取舍。"
            "主视觉只能用内置组件类：①流程/链路 div.ib-flow（div.ib-node 用 div.ib-arrow 串联；节点状态 is-bad 问题/is-block 阻断/is-good 目标/is-new 新增机制/is-hub 系统枢纽/is-auto 自动动作（虚线）；竖排加 is-stack 与箭头 is-down）；"
            "②分发/聚合 div.ib-tree（.ib-node.is-hub + .ib-branches>.ib-branch 多分支）；"
            "③现状目标对照 div.ib-compare（.ib-col.is-now / .ib-col.is-goal，列内竖排 flow）；"
            "④并列机制 div.ib-grid>.ib-sol（.ib-sol-h 标题+一句说明）。"
            "落地步骤必须是 .ib-roadmap>.ib-phase（.ib-when 时期 + .ib-what 内容）；关键数字用 span.ib-chip（is-ok/is-new/is-warn）。"
            "禁止：用 ol/ul/p 文字列表冒充主视觉、自带 <style> 重定义这些类、mermaid/图片/外链（容器不渲染脚本）；节点文字≤12 字、每图≤8 节点。"
            "组件详细骨架见角色 insights.md；自定义角色无该文件时按本描述结构输出。"
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
            "html 传入修订后的完整节块（<section data-ib-id=\"…\">…</section>，保持同一 id）；"
            "同样只写片段、用应用 CSS 变量、禁全局选择器与硬编码色。适用于用户只关心改某一节的场景。"
            "内容底线与整版相同：该节必须是「困境条 .ib-dilemma → 主视觉 .ib-visual（.ib-flow/.ib-tree/.ib-compare/.ib-grid 之一，不可缺）→ 图文 → .ib-roadmap → .ib-tradeoff」结构，"
            "禁止把一节写成决策/议题/待办/分工清单、发言人记录或纯文字墙，否则整版落盘会被后端拒收（error=board_is_recap / board_is_text_wall）。"
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
