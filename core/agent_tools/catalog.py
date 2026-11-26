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
        "name": "get_meeting_decisions", "kind": "read", "needs_task": True,
        "description": "获取当前会议的决策事项列表（含节点稳定 id 与状态，供按节点寻址）。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        # 跨会议清单（spec §4 第 5 级「原文回捞」的入口）：不受当前会话 task 绑定，
        # 否则「把 11 月所有涉及 X 的会议列全」这类需求只能靠注入样本抽样作答。
        "name": "search_meetings", "kind": "read", "needs_task": False,
        "description": (
            "跨全部会议检索（不只当前这场）。返回紧凑清单：标题、日期、相关度、一句摘录、task_id。"
            "用 offset 翻页取全；要看某场全文再调 get_meeting_detail。"
            "用户要求「所有/全部/汇总/列清单」时，必须翻页到 has_more=false 再作答，"
            "不得只凭系统注入的少量片段下结论，也不得编造未返回的会议。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索词，可含时间词（如「11月」）与项目名"},
                "limit": {"type": "integer", "description": "每页条数，默认 20，最大 50"},
                "offset": {"type": "integer", "description": "分页偏移，从 0 开始；翻页时按上次 returned 递增"},
            },
            "required": ["query"],
        },
    },
    {
        # 任意会议详情的只读入口：与写工具不同，不绑定当前会话 task_id。
        "name": "get_meeting_detail", "kind": "read", "needs_task": False,
        "description": (
            "按 task_id 读取任意一场会议的详情（元信息、纪要、决策列表、随记）。只读。"
            "task_id 来自 search_meetings 结果或检索证据锚点；"
            "用户问某一场会议「定了什么」时用它取全文，而不是靠清单里的摘录猜测。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "会议 id（来自 search_meetings）"},
                "transcript_limit": {"type": "integer", "description": "附带转写句数，默认 0（不返回逐字稿）"},
            },
            "required": ["task_id"],
        },
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
    {
        # 联网搜索：调用 Brave Search API（默认）或用户配置的 provider，
        # 需在设置页填入对应 API key；未配置时返回明确错误而非静默失败。
        # kind=read 但涉及外部网络调用，readonly 档也可用（无本地落盘副作用）。
        "name": "web_search", "kind": "read", "needs_task": False,
        "description": (
            "联网搜索外部信息。当会议涉及会上没人提到的行业知识、标准实践、竞品方案、外部产品时调用，"
            "用搜索结果补足你训练数据可能缺的实时信息。返回标题、摘要、URL（取前 8 条）。"
            "注意：若返回 error=web_search_not_configured，说明用户尚未在设置页填入搜索 API key，"
            "此时直接说明无法联网搜索，不要假装查过。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "搜索关键词（≤200 字）"}},
            "required": ["query"],
        },
    },
    {
        # 网页抓取：用于跟进 web_search 结果的全文阅读，或 AI 需要读取特定已知 URL。
        # SSRF 防护：禁内网地址（127.0.0.1/10.x/172.16-31.x/192.168.x）、仅 HTTPS、15s 超时、
        # 响应体截断上限 ~10KB。
        "name": "web_fetch", "kind": "read", "needs_task": False,
        "description": (
            "抓取单个公网 URL 的网页正文（纯文本，HTML 自动剥离）。"
            "用于在 web_search 返回的候选里深挖详情，或直接读取已知 URL。"
            "禁止内网地址（localhost/127.0.0.1/10.x/172.16-31.x/192.168.x），仅支持 HTTPS。"
            "响应体上限 10KB，超时 15s。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "目标 URL（必须 HTTPS、公网）"}},
            "required": ["url"],
        },
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
        "description": "向会议注入结构化条目（决策 decision / 结论 conclusion），逐条落库并进入决策中心。仅用于新增；修改已有节点请改用 update_decision_node。",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "待注入条目数组",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["decision", "conclusion"]},
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
        # 决策节点改写（P3）：按节点 id 寻址，收口到 notes.update_decision 同一口径（DC-UNIFY-01）。
        # 写回前强制字段级快照（core.rewrite_snapshots），因此“AI 误写可回退”成立。
        "name": "update_decision_node", "kind": "write", "needs_task": True,
        "description": (
            "改写已有的决策流节点（按节点 id 精准定位，不新建第二条）。"
            "必先调 get_meeting_decisions 拿到节点 id、当前状态与可用状态字典（status 只能取其中的 id）。"
            "只传需要改的字段：title（一句话结论）、text（决策正文）、status（如用户已拍板→推进到闭档态）、"
            "why（依据）、outcome（结果）、owner_type（推进方）。"
            "用户说「按随记/纪要把这几条定为已确认」类需求时，逐条按 id 更新，不要用 inject_items 重复追加。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "节点稳定 id（来自 get_meeting_decisions）"},
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
        # 决策节点删除（P3）：复用 notes.delete_decision，auto 节点同步落防复活墓碑。
        "name": "delete_decision_node", "kind": "write", "needs_task": True,
        "description": (
            "按节点 id 删除一条决策流节点（仅当用户明确要求删除/合并时）。"
            "删前建议先 get_meeting_decisions 确认对象；删错可由本轮快照撤销。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"node_id": {"type": "string", "description": "待删除节点的稳定 id"}},
            "required": ["node_id"],
        },
    },
    {
        # 洞察共创 Markdown（单份整板覆盖）；实现在 core.insight_board.invoke_revise_board，
        # schema 变更需同步工具描述消费方（自建 agent_loop 已退役，此处为唯一工具定义来源）。
        "name": "revise_insight_board", "kind": "write", "needs_task": True,
        # 读写双语义：空参/无 markdown = 读；带 markdown = 整板覆盖
        "bidirectional": True, "write_arg": "markdown",
        "description": (
            "读取或修订当前会议的洞察板（一场会议一份 Markdown 文件，用户主动驱动生成）。"
            "【调用契约·必读】① 先读基线（不带 markdown 参数）：拿到当前板 markdown + revision；"
            "② 需要外部知识时 web_search ≤2 次；"
            "③ 传 markdown=<完整新版> + expected_revision=<读到的版本号> 覆盖落盘，"
            "回执 revision≥1 才算完成——只读只搜索就回复用户算失败。"
            "不带 markdown = 读：返回当前 insight.md 正文 + revision/title。"
            "收到 error=stale_baseline 说明你手里的基线已过期（用户可能在别的窗口共创过），"
            "重读基线后再改，不要硬写覆盖。"
            "收到 error=board_is_recap 或 board_is_text_wall 时按 guidance 重做再提交。"
            "【内容底线·违反会被拒收 error=board_is_recap】"
            "洞察板唯一任务：针对本场会议暴露的困境，给出会上没人想到的 AI 最优解法。"
            "你被授权调用外部行业知识、标准实践、成熟架构来构造解法；会议内容只用于界定问题，不用于复述。"
            "每节按「困境一句话界定 → 外部最优解法（可执行） → 落地步骤 → 取舍」组织；"
            "风险/未决项必须每条紧跟一个可落地解法，禁止只罗列问题。"
            "严禁入板：决策清单（含 DC 编号）、议题归类、决策与人员分工（谁做什么、截止日期）、"
            "参会人立场与「谁说了什么」、带说话人/时间戳的依据流水、会议概览与摘要复述。"
            "若读到的旧基线是复述结构，直接推倒重做为解法结构。"
            "【图形化·硬约束 error=board_is_text_wall】板是图不是文章：每个困境一节，先画后主文；"
            "每节必须有一个按**形态**识别的主视觉，优先 ```mermaid fence（首词必须是 "
            "flowchart/graph/sequenceDiagram/stateDiagram/mindmap/timeline/gantt/classDiagram/erDiagram "
            "等图类型关键字）；也可用 data URI 内联的 ![图](data:image/...) 图片。"
            "mermaid 节点文字≤12字、每图≤10节点；源码禁 < > &（用中文替代）；禁 click 语句。"
            "【锚点语法·AI 写的每节都必须前置】"
            "<!-- section-id: s1 section-title: 审核阻塞 -->"
            "这是 HTML 注释，GFM 里不可见但能让：① 前端定位「@洞察 s1」引用；"
            "② 后端防线识别每个节是否有主视觉；③ 前端悬停时高亮对应节。"
            "section-id 固定 s1/s2/s3…（递增），section-title 是节标题短名（≤20字）。"
            "所有节都要有这个注释锚点，不要漏掉任何一节。"
            "【转写跳转】保留 <a data-seek-ms=毫秒> 锚点（应用负责接线跳转）。"
            "【front-matter·你不写也行】系统会从正文第一个 h1 猜 title、自动写 revision/updated_at。"
            "如果想显式写可以开头加："
            "---\ntitle: 餐饮供应链困境最优解法\n---"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "markdown": {"type": "string",
                             "description": "完整的新版洞察板 Markdown（整份覆盖语义）；缺省则读取当前板"},
                "expected_revision": {"type": "integer",
                                      "description": "你读到的基线版本号；读到的是哪一版就带哪一版"},
            },
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
