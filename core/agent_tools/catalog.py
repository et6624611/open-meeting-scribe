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
        # 洞察共创 HTML 产物（会话驱动唯一写入路径）；实现在 core.insight_board.invoke_revise_board，
        # schema 变更需同步工具描述消费方（自建 agent_loop 已退役，此处为唯一工具定义来源）。
        # 【版式归 CLI】描述只保留三件事：内容底线、三条最小契约、基线/版本协议。
        "name": "revise_insight_board", "kind": "write", "needs_task": True,
        # 读写双语义：空参/无 html = 读（只回板清单）；带 html = 整版落盘
        "bidirectional": True, "write_arg": "html",
        "description": (
                "读取或修订当前会议的洞察板（一份由你完全自持的自包含 HTML 文档）。"
                "【调用契约·必读】① 先读基线：工作区 `context/boards/index.md` 选板，再 Read "
                "`context/boards/<board_id>.html`（没有该文件就是首版，revision=0）；"
                "② 需要外部知识时 web_search ≤2 次；"
                "③ 本工具传 board_id + html + expected_revision（读到的版本号）落盘，"
                "回执 revision≥1 才算完成——只读只搜索就回复用户算失败。"
                "不带 html = 读：空参只回板清单（board_id/title/revision/exists），带 board_id 才回正文。"
                "收到 error=stale_baseline 说明你手里的基线已过期（用户可能在别的窗口共创过），"
                "重读基线后再改，不要硬写覆盖。"
                "【内容底线·违反会被整份拒收 error=board_is_recap】"
                "洞察板唯一任务：针对本场会议暴露的困境，给出会上没人想到的 AI 最优解法。"
                "你被授权调用外部行业知识、标准实践、成熟架构来构造解法；会议内容只用于界定问题，不用于复述。"
                "每节按「困境（一句话界定）→ 外部最优解法（具体、可执行，附原理或出处）→ 落地步骤与取舍」组织；"
                "风险/未决项必须每条紧跟一个可落地解法，禁止只罗列问题。"
                "严禁入板：决策清单（含 DC-1 类编号）、议题/章节归类、决策与人员分工（谁做什么、截止日期）、"
                "参会人立场与「谁说了什么」、带说话人/时间戳的依据流水、会议概览与摘要复述"
                "——这些已由逐字稿、纪要页、决策中心承载，再写一遍就是失败。"
                "若读到的旧基线是上述复述结构，允许且应当推倒重做为解法结构。"
                "【图形化·硬约束 error=board_is_text_wall】板是图不是文章：每个困境一节，先画后主文；"
                "每节必须有一个按**形态**识别的主视觉：内联 <svg> / mermaid 形态的 <pre> / <canvas> / "
                "src 为 data URI 的 <img>。表格、div 色块、纯 CSS 条形不计主视觉；"
                "用 ol/ul/p 文字列表冒充主视觉同样被拒收。"
                "mermaid 首词必须是图类型关键字（flowchart/graph/sequenceDiagram/stateDiagram/mindmap/timeline），"
                "边标签是标配：A -->|按开票日汇率| B；节点文字≤12 字、每图≤10 节点；"
                "源码内禁写 < > &（用中文替代，防止截断 HTML）、禁 click 语句。"
                "【三条最小契约·其余版式全归你】"
                "① 顶层每个逻辑节包成扁平的 <section data-ib-id=\"s1\" data-ib-title=\"节标题\">…</section>"
                "（节不嵌套、id 稳定），以支持单节共创与悬停定位；"
                "② 需关联转写位置时用 <a data-seek-ms=\"毫秒\"> 锚点（应用负责接线跳转）；"
                "③ 每节存在一个主视觉（判据见上）。"
                "除此之外应用不提任何排版意见：可以输出完整文档（doctype/<html>/<head>/<style>）或片段，"
                "可以用 :root/html/body 等全局选择器与硬编码色（渲染在独立文档里，影响不到宿主主题）；"
                "字体、配色、栅格、断点、卡片形态、交互脚本均由你自定。"
                "只有三条硬约束，且都与排版审美无关、只决定板能不能看清："
                "① 资源不靠相对路径：图片/字体一律 data URI 内联——同一份 HTML 还要经 raw 端点在"
                "浏览器里打开，两处 base 解析不一致；"
                "② 底色与正文色默认跟随宿主主题：应用把宿主当前主题的令牌以**低优先级样式表**注入"
                "板文档（插在你的样式之前），因此 **底色、正文色、卡片面、边框四个必须写成带兜底值的"
                "宿主令牌**：background:var(--bg,#0f1420); color:var(--fg,#e8edf6) 与 "
                "var(--surface,#161d2e)、var(--border,#26314a)——带兜底是因为 raw 端点不注入任何令牌。"
                "两条禁区：**不得重定义宿主同名令牌**（你在 :root 里写 --bg 就会盖掉宿主值，"
                "板将永远不跟随主题；要自己的中间色请在 --ib-* 命名空间下派生），"
                "**不得只依赖宿主令牌而不写兜底值**；语义状态色（成功/警告/错误等）"
                "可硬编码，但必须与上面四个底色正文色共用同一深浅关系，避免背景跟宿主、文字跟硬编码拼出白底白字；"
                "③ 宽度自适应由你负责：板视口宽度就是容器宽度（窄栏与浏览器宽屏都要能站住），"
                "用相对单位与 @media 断点组织，图与 SVG 写 max-width:100%，长串加 overflow-wrap:anywhere；"
                "不要写死大值固定宽度——旧容器的 overflow-x 兜底已废弃，板不管断点就会横向溢出。"
                "【真实字节】on* 内联事件与 javascript: 类危险 URL、iframe/form/object/embed/base 标签会被安全清洗剔除，"
                "剔除项在回执 removed 里如实列出：磁盘字节 = 你提交的内容 − removed，不要假设逐字节相等。"
                "【建板权】board_id 必须已在板清单内；未知 board_id 会被拒（error=unknown_board_id）——"
                "一场会议要不要第二份板由用户决定，想拆板先调 create_insight_board 向用户提议，不要自己写新 id 顺手建板。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string",
                             "description": "目标板 id（来自 context/boards/index.md 或空参读回的清单）；缺省取默认板"},
                "html": {"type": "string",
                         "description": "完整的新版洞察板 HTML（整份替换语义）；缺省则读取当前板"},
                "expected_revision": {"type": "integer",
                                      "description": "你读到的基线版本号；从 context/boards/ 读到的是哪一版就带哪一版"},
            },
        },
    },
    {
        # 单节共创：只替换板内指定 data-ib-id 的一节，其余节硬隔离。
        "name": "revise_insight_board_section", "kind": "write", "needs_task": True,
        # 读写双语义：需同时带 section_id 和 html 才算真落盘
        "bidirectional": True, "write_arg": "html",
        "description": (
            "只修订洞察板中某一节（按节锈点 id 定位替换），其余节逐字节不动。"
            "需先读到当前板（工作区 context/boards/<board_id>.html，或本工具带 board_id 空参读），"
            "定位目标节的 data-ib-id。"
            "html 传入修订后的完整节块（<section data-ib-id=“…”>…</section>，保持同一 id）；"
            "可传 board_id 指定哪份板（缺省取默认板）、expected_revision 标记基线版本。"
            "版式仍归你（节内可自带 <style>，但注意节块不独立渲染，全局选择器请写在整版里）；"
            "资源仍须 data URI 内联。"
            "内容底线与整版相同：该节必须是「困境一句话界定 → 一个按形态识别的主视觉（内联 SVG / "
            "mermaid 形态 pre / canvas / data URI 图片）→ 简短图文 → 落地步骤 → 取舍与兜底」结构，"
            "禁止把一节写成决策/议题/分工清单、发言人记录或纯文字墙，"
            "否则整版落盘会被后端拒收（error=board_is_recap / board_is_text_wall）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "目标板 id；缺省取默认板"},
                "section_id": {"type": "string", "description": "目标节的 data-ib-id 值"},
                "html": {"type": "string", "description": "修订后的完整节块（<section data-ib-id=…>…</section>）"},
                "expected_revision": {"type": "integer", "description": "读到的基线版本号"},
            },
            "required": ["section_id", "html"],
        },
    },
    {
        # 板清单（只读）：多板下让 CLI 先看到全景再选目标板，避免盲写默认板。
        "name": "list_insight_boards", "kind": "read", "needs_task": True,
        "description": (
            "列出当前会议的全部洞察板（board_id / 标题 / revision / 是否已有内容）。"
            "与空白板写入前先用本工具确认目标；需要第二份板时走 create_insight_board 提案，"
            "而不是直接往新 board_id 写。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        # 建板提案（不落盘）：与 propose_summary/propose_notes 同构——
        # “要不要多一份板”会改变用户工作区结构，因此执行权收回用户侧（AI 只保留提议权）。
        "name": "create_insight_board", "kind": "write", "needs_task": True, "persists": False,
        "description": (
            "向用户提议新建一份洞察板（提案式，**不会直接建板**）。"
            "使用场景：内容已超出单份板的承载力、或用户提出了与现有板不同主题的第二份分析。"
            "禁止在未经用户点「接受」前声称已建板，也禁止用 revise_insight_board 写一个未知 board_id 来“顺手建板”"
            "（会被 error=unknown_board_id 拒收）。"
            "board_id 可缺省（由服务端生成 board-2/board-3…）；title 必填且短（≤ 60 字）。"
            "提案被接受后，用户确认的那一份板 revision=0，你再调 revise_insight_board 写入首版内容。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "期望的新板 id（[\\w-]{1,48}）；缺省由服务端生成"},
                "title": {"type": "string", "description": "新板标题（必填，建议 ≤ 20 字）"},
                "reason": {"type": "string", "description": "为什么要多一份板（给用户看的一句话理由）"},
            },
            "required": ["title"],
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
