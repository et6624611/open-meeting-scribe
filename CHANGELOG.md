---
title: 迭代日志
description: 版本迭代记录，配合 git tag
author: et6624611
created_at: 2026-09-03
updated_at: "2026-10-05"
status: published
---

# CHANGELOG — 迭代日志

> 每版一条，配合 git tag。分类：新增 / 变更 / 决策 / 修复。最新的在最上面。
>
> **记录门槛**：仅记录影响用户行为、API 契约、架构决策或跨模块的变更；单文件修复、注释修改、内部重构不单独记录。

## [1.0.0] - 2026-10-05 — 首个公开发布版本

Open Meeting Scribe 首次以 MIT 许可公开发布。本版本对早期内部迭代史做了收敛：源码以干净首提交形式进入公开仓库，历史决策与建设复盘由本 CHANGELOG 与 `docs/adr/` 承接。

### 能力概览
- **音频输入即一切**：本地导入音视频文件，不绑定任何会议平台；内置 ffmpeg 解码
- **转写与说话人分离**：云端 DashScope paraformer-v2 通道，或本地 FunASR 全管线（可离线）
- **声纹识别**：CAM++ 192 维嵌入 + 群嵌入多数表决，本地或云端注册表互认
- **结构化纪要**：议题 / 结论 / 待办 / 风险 自动产出；决策中心跨会议跟踪议题演变
- **AI 会话**：基于会议内容的问答与智能体两档模式，支持工具调用、决策写回、洞察板共创
- **数据归属**：全部业务数据落盘在本机 `data/`，云端仅用用户配置的 API Key

### 安装路径
- **源码安装**（推荐开发者）：Python 3.11+ / Node 20+，见 README「快速开始」
- **Docker**：单容器包含云模式与内置 ffmpeg，本地引擎权重按需挂载下载；不提供预编译二进制包

### 已知边界
- 多人重叠场景的本地说话人分离仍为短板（近似 DER 见 `tests/eval_local_engine/EVAL-AC2-LOCAL-ENGINE.md`），手动修正入口是必要补偿
- 桌面壳（pywebview）在 macOS 上走 WKWebView，与 Chrome 渲染存在差异，麦克风权限与文件桥需要在真机复核

### 合规与归档
- 代码内不含任何真实会议语料、用户数据、密钥；评测样本为合成或化名，原始语料属私有归档
- 第三方组件许可证汇总见 `THIRD_PARTY_NOTICES.md`

---

以下为早期内部迭代叙事（v0.x → v7.x），保留以承接架构决策背景：

---

## [未发布] - 2026-09-30 — 随记改写通道：propose_notes 建议模式（四域闭环）

### 新增
- **写工具 `propose_notes`（提案式，后端不落盘）**：随记是用户原创区（PROPOSAL §5.3 市场模式 D），因此与其他域不同构——工具只产出建议全文，**用户点「接受」才经 `PUT /api/tasks/{id}/notes` 落盘**，与 `propose_summary` 同一语义。只读档 403 拒绝，可写档预授权放行。
- **随记 Tab 原位 diff 预览**：新建 `useNotesProposal.ts`（模块级单例，复用 `useSummaryProposal.buildDiffSegments` 与 `.gen-prop-*` 样式体系），提案产生即自动起跳到随记 Tab 并锁定编辑；AI 侧栏只留规模摘要 + 入口 + 拒绝（与纪要入口卡同一形状）。**接受前不写盘**（AC7）。
- **基线漂移轻防护**：接受前先回拉服务端当前随记与提案 baseline 比对，发生过手动编辑则写入但仍 warn 提示复核，不静默吞掉用户手改。
- **catalog 新增 `persists` 字段**：标记"名义 write、实际不落盘"的提案工具；`runner` 的完成护栏触发集改按该字段派生（不再硬写工具名），否则提案轮会被误标 `rewritten=true`。
- **权限段与工作区声明改写**：可写档从"随记无写回工具，只能给建议文本"改为"随记改写必须走 `propose_notes`，未经接受严禁声称已写入"；`context/notes.md` 头部声明同步。
- **AI 面板「上下文」清单补上随记一项**：清单原本只列 原文/纪要/决策/文件/相关会议，而 AI 现已能读随记 → 展示层比实际能力少报一项。现在「会议产出」区新增一行（字数 + 手写标签 + 点击跳随记 Tab），顶部概览与各项计数（`contextStats`/`contextResourceCount`/`meetingOutputCount`/`isContextEmpty`）同步计入；图标沿用组内统一的 accent 色相（不新增色相，遵守既有视觉规则）。数据取 task 快照的 `user_notes`（`/api/tasks` 返回完整任务对象），不额外发请求。实测 9-30 那场会议：清单计数 11 → 12。

### 修复
- **接受提案后旧文本回写隐患**：随记编辑器有 1s 防抖自动保存，外部重拉（接受提案/写回刷新）后旧缓冲仍会在 1s 后 `PUT` 回去、静默覆盖刚接受的内容。现 `loadNotes()` 先取消挂起定时器；`task-written` 事件也改为按受影响域（todos/notes）定向刷新，不再一律重拉。

### 涉及文件
- `core/agent_tools/catalog.py`、`core/agent_tools/impl.py`、`app/routers/agent_tools.py`、`core/cli_engine/{context_export,runner}.py`、`frontend/src/composables/{useNotesProposal.ts,useAiChat.ts,useNotesAndTodos.ts,useAiContext.ts}`、`components/layout/AIPanel.vue`、`components/layout/ai/{AiChatPanel.vue,AiContextPanel.vue}`、`views/generating/NotesPanel.vue`、`views/GeneratingView.vue`、`styles/ai-panel.css`、i18n（ai-panel/generating 中英）、`tests/test_agent_tools.py`、`tests/test_cli_engine.py`

### 验证
- pytest 692 passed（新增 5 例：注册/不落盘/只读档 403/allowlist/触发集剔除）；`vue-tsc --noEmit` 无错；ESLint 对本次改动文件零错误（AiContextPanel 余留 3 项 `no-use-v-if-with-v-for` 为存量，HEAD 版本已存在）；`npm run test:parser` 25 passed；`cli.py build` 已部署，随记提案文案与上下文清单文案均已进产物。
- 待实机：在应用里对智能体说"把我随记里的口径整理得更条理些"→ 应弹随记 Tab 原位 diff → 接受后落盘、拒绝则丢弃。

## [未发布] - 2026-09-30 — 改写通道 P2/P3：写前快照 + 决策节点按 id 改写 + 本轮撤销

### 新增
- **字段级写前快照 `core/rewrite_snapshots.py`**（PROPOSAL §5.3 快照强制契约）：`data/tasks/<task_id>.rewrites.jsonl` 追加式 sidecar，记录 task_id / target / 旧值 / turn_id / tool / ts；每 target 保留上限 N=20（超出整表原子重写裁剪），过期清理并入智能体工作区同一 `retention_days` 口径（启动时 `sweep_expired_snapshots`）。只快照 AI 写回，用户手改不快照。
- **写工具 `update_decision_node` / `delete_decision_node`**（PROPOSAL P3）：按节点稳定 id 寻址，收口到 `notes.update_todo` / `notes.delete_todo` 同一口径（状态字典校验、`updated_at`、脏标记、`save_task_to_disk`、auto 节点防复活墓碑），**不在 `inject_items` 旁开第二套写路径**。写回前强制整节点快照；非法 status 先行 422、字段超长/枚举非法 400，**被拒的写不留空快照**。
- **`get_meeting_todos` 下发状态字典**（`available_statuses` + `status_note`）：否则模型只能猜 status id，每写必 422。
- **恢复入口**：`GET /api/tasks/{id}/rewrites`（只回摘要不回旧值全文）+ `POST /api/tasks/{id}/rewrites/restore`（`snapshot_id` 单点恢复或 `turn_id` 整轮**逆序**回滚）；恢复本身不再快照，避免撤销无限套娃。`inject_items` 新建节点也进快照（old_absent 语义），撤销 = 删掉新建。
- **令牌携带 `turn_id`**：`TokenContext.turn_id` ← `build_bridge_config(turn_id=stream_id)`，写工具据此把同一轮的多次落盘归到一个回滚单元。
- **前端「本轮已改写 + 撤销」条**：`done.metadata` 新增 `rewritten_tools / turn_id / task_id`；`AiChatPanel` 在回复尾部以 ok 绿系展示改了哪个域并提供「撤销本轮改写」（与 amber 护栏横幅形成"已成事/未成事"对偶）。
- **写回后呈现侧即时重拉 `useTaskWrites.ts`**：沿用 `board-written` 的 CustomEvent 先例新增 `task-written` 通道；`GeneratingView` 订阅后重拉 task + `loadTodos` + 同步状态，消除"AI 说改了、页面还是旧的"。

### 变更
- 完成护栏事实从 `rewritten: bool` 扩展为带明细（`rewritten_tools`）：呈现与恢复共用一份数据源，不把"看见改了什么"和"回退"割裂（§5.4）。
- `runner.on_write_success` 触发集由 catalog 派生，新写工具自动纳入；`inject_items` 描述改为"仅用于新增"，与 `update_decision_node` 职责分界写进工具描述与权限段。
- 可写档权限段新增「决策推进」操作规程（先读 id 与状态字典 → 逐条 update → 不用 inject 重复追加），并要求 `restorable=false` 时如实告知不可一键回退。

### 遗留（本次不做）
- 随记 `revise_notes`（建议模式）仍待做；洞察板 HTML 未进快照体系（整份 HTML 体积大，需 gzip 与单独存储设计）。

### 涉及文件
- `core/rewrite_snapshots.py`（新增）、`app/routers/agent_tools.py`、`app/routers/notes.py`、`app/routers/chat.py`、`core/agent_tools/{catalog,impl,tokens}.py`、`core/cli_engine/{context_export,mcp_bridge}.py`、`app/server.py`、`frontend/src/composables/useTaskWrites.ts`（新增）、`useAiChat.ts`、`components/layout/ai/AiChatPanel.vue`、`views/GeneratingView.vue`、`api/{chat,notes}.ts`、i18n（ai-panel 中英）、`tests/conftest.py`、`tests/test_rewrite_snapshots.py`（新增）、`docs/PROPOSAL-AGENT-REWRITE-CHANNEL.md`

### 验证
- pytest 686 passed（唯一失败仍为存量的 `.spike_local_engine` venv 路径干扰）；新增 `tests/test_rewrite_snapshots.py` 25 例：快照追写/保留上限/过期清理/按轮逆序回滚/撤销创建/被拒写不留快照/只读档 403/端点端到端。
- 前端 `vue-tsc --noEmit` 无错；`python3 cli.py build` 已部署，`task-written` / `rewrites/restore` / 中文文案均已进产物。

## [未发布] - 2026-09-30 — 随记对 AI 从「不可见」到「可读」

### 修复
- **随记（`user_notes`）是四域中唯一对 AI 不可见的域（实测复盘：用户把共识结论写进随记要求同步决策面板，智能体回「随记内容我读不到」）**：三条读路径同时缺失——① CLI 工作区只导出 transcript/summary/todos/insights，无 notes；② 工具面无随记读入口，`get_meeting_info` 也不报随记存在性（不告知就等于不存在）；③ 内置问答路径的上下文块不含随记（仅纪要生成链路读过它）。现全部打通。
- **AI 读到的纪要基线不取定稿口径**：工作区 `summary.md`、`get_meeting_info.summary_preview`、问答注入块均只读 `summary`（AI 初稿），用户手改存于 `user_summary` → `propose_summary` 的行级 diff 会把用户修改静默回退。现统一走新增的 `core.chat_context.task_final_summary()`（`user_summary` 存在即优先，含空串），与前端纪要 Tab 逐字节同口径。

### 新增
- **只读工具 `get_meeting_notes`**（`catalog.py` + `impl.py`，kind=read）：返随记原文（6000 字上限，超限标 `truncated`），描述里明确「用户说『写在随记里了』时先读本工具」与「只读、不得声称已改写随记」两条约束；只读档可用，MCP 预授权清单自动涵盖。
- **`context/notes.md` 导出**（`export_context`，8000 字上限）：带「用户手写原文、可信度高于转写推断、未经确认不得改写」的头部声明，使弱模型能正确将其作为事实源。
- **决策节点稳定 id 上工具面**：`get_meeting_todos` 输出补 `id/title/status`，清除 PROPOSAL-AGENT-REWRITE-CHANNEL §9 标记的 P3 前置缺口（此前只能按文本匹配，无法按节点寻址）。
- **防幻觉护栏**：可写档权限段（`_build_permission_section`）新增一条：随记当前无写回工具，只能引用其内容更新纪要/决策或给出建议文本，严禁声称已写入/修改随记。

### 遗留（本次不做）
- 随记写回（`revise_notes` 建议模式）与决策节点改写/删除仍是 PROPOSAL §6 的 P3 待做：因此图中「按随记把那 4 条【待确认】决策改掉」的写侧闭环未开，AI 现只能读准随记、新增条目（`inject_items`）或给出建议文本。
- 前端 AI 面板「上下文」资源清单未列随记（`useAiContext.ts` 的 `contextStats` 只有转写/纪要/待办/项目），展示层与读能力暂不一致。

### 涉及文件
- `core/chat_context.py`（新增 `task_final_summary`/`task_notes`）、`core/cli_engine/context_export.py`、`core/agent_tools/catalog.py`、`core/agent_tools/impl.py`、`app/routers/chat.py`、`docs/PROPOSAL-AGENT-REWRITE-CHANNEL.md`（v0.4.1）、`tests/test_cli_engine.py`、`tests/test_agent_tools.py`

### 验证
- pytest 661 passed（唯一失败 `test_model_downloader::test_worker_command_dev_mode` 为存量的 .spike_local_engine venv 路径干扰，与本次无关）；新增 8 个用例覆盖 notes 导出/读工具/存在性/节点 id/只读档放行。
- 真实会议数据离线复核（差旅报销与预算控制机制讨论）：brief 列出 `context/notes.md`，随记三段全文入盘，`get_meeting_info` 返 `has_notes=true`，决策节点带 uuid 与 `to_decide` 状态。

## [未发布] - 2026-09-29 — 工程化能力收敛：退役自建 Agent 循环，CLI 为唯一智能体引擎

### 决策
- **自建 ReAct 循环退役（ADR-0020，supersede 双轨工具调用 ADR）**：删除 `core/agent_loop.py`（多轮工具循环、function calling/文本回退双轨、工具 JSON Schema）。内置 AI 对话回归「上下文注入 + 单轮流式问答」：`/api/chat/stream` 内置分支直接流式补全，`done` 后处理（待办注入卡 `extracted_items`、`model_usage` 回显、Mermaid 画图意图）全部保留；CLI 失败 `__fallback__` 同样落入单流路径。
- **会议域工具实现迁移而非删除**：`execute_tool` 与 `_tool_*` 逐字节迁入新建 `core/agent_tools/impl.py`（单一来源），MCP 反向桥读工具执行链路不变；`catalog.py` 成为唯一工具定义来源，双轨定义维护成本消除。
- **行为变化**：未启用 CLI 的用户无多轮工具调用（常规问答不受影响，上下文已预注入）；洞察板共创落盘、`update_summary`、`inject_items` 等写入型工具仅智能体（CLI）模式具备，问答模式共创起跳时 toast 明确提示；洞察板空态文案同步注明「智能体」模式。
- **配套死代码清理**：`core/cloud_client.py` 删除 `cloud_llm_chat_with_tools()`；`cloud_api.py` 的 `CloudLLMRequest` 移除 `tools`/`tool_choice` 透传字段（Pydantic 忽略未知字段，旧客户端多发无害）。

### 修复
- **AI 对话流式渲染冻结（Vue 响应式绕过，浏览器 MutationObserver 实测定位）**：`useAiChat.ts` 的 `onToken/onDone` 写的是 push 前的 raw 对象引用，绕过 reactive 代理的依赖收集 → token 早已逐块到达 JS 层但 DOM 长时间不动、直到 done 才一次性出现全文。现改为经数组下标读回响应式代理（`liveMsg()`）写回，问答/智能体两引擎同一渲染路径同时受益；实测文字量逐 80ms 级增长（242 次 DOM 增量事件）。

### 涉及文件
- `core/agent_loop.py`（删除）、`core/agent_tools/impl.py`（新增）、`app/routers/chat.py`、`app/routers/agent_tools.py`、`core/agent_tools/catalog.py`、`core/cloud_client.py`、`app/routers/cloud_api.py`、`frontend/src/components/layout/AIPanel.vue`、i18n（ai-panel/generating 中英）、`frontend/src/composables/useAiChat.ts`（流式渲染修复）、`tests/test_agent_tools.py`

### 验证
- pytest 620 passed（1 失败为环境依赖存量问题）；ruff 改动文件零告警；vue-tsc/build 零错误。
- 临时实例实测：内置问答 stage→token→done（含 model_usage/extracted_items）；CLI 智能体 engine_route→MCP `oms-tools connected`→token/done 闭环；`/api/agent-tools/invoke` 令牌校验在线。

## [未发布] - 2026-09-29 — 划词工具栏：修正从「假成功」变为全量回溯，并适配主题色

### 新增
- **文本回溯修正链路 `core/text_correction.py` + `POST /api/tasks/{task_id}/correct-text`**：把一条「误识别→正确文本」映射全量落到本场会议的四份产物（任务对象 / insights.json / board.html / 导出纪要 md）。匹配口径与转写链路同源（新增 `core.hotwords.sub_term`：ASCII 词按邻接边界、中文按子串，详见下方词边界修复条目），改写范围按**键名白名单** `REWRITE_KEYS` 递归判定，标识与路径字段永不触碰；响应逐产物回传真实命中数，并用 `residual` 全量残扫作为「白名单漏项」的显式告警。
- 新端点契约见 `docs/API_CONTRACTS.md` §15；行为契约用例 `tests/test_text_correction.py`（7 项，含词边界、路径保护、旁路落盘、revision 升位、幂等）。

### 修复
- **划词「创建映射 / 应用修正」的假成功反馈**：旧 `GeneratingView.replaceInTranscriptDom()` 只在「原文」Tab 的 `.ts-line-body .txt` DOM 里改**第一处**命中就 `return`，不回写数据也不落盘（纪要 Tab 完全无效、一次重渲染即复原），但 toast 仍无条件报「已修正为…」。现改为：后端改写 + 前端从数据源重拉（任务快照 / 决策 / 随记 / 洞察卡片 / 洞察板），命中 0 处时改报「本场会议未出现该词」。随记 Tab 正在编辑时不覆盖用户输入。
- **洞察消息内存缓存不同步**：`useAiInsights.reloadTaskMessages()` 新增。回溯修正改了 `insights.json`，但模块级 `messagesByTask` 不重拉既会呈现旧词，更会在切会议时被 `persistMessages` 整体写回、覆盖刚落盘的修正。
- **多行划词会写坏 `data/hotword_mappings.txt`（静默污染后续转写）**：一条多行选区被原样序列化成 `选区→目标` 落盘，一行变 N 行，其中恰好含分隔符的那行又被解析成一条**真实生效**的映射（实测例：`对。比如说→ZZZ不存在的词ZZZ`），下一次转写会静默改坏语料。现两层收口：前端 `SelectionToolbar.isUsableTerm()` 拒收多行 / 超 30 字的选区（「加入热词」与「创建映射」共用）；后端 `POST /api/hotword-mappings` 对不含分隔符的行直接 400（校验先于写盘），仅右值空的退化映射依旧静默丢弃（保持旧行为、不阻断整页保存）。
- **ASCII 词条的词边界判定在中文语境下全面失效（自 v0.20 热词映射上线即存在）**：`apply_hotword_mappings` 用 `\\b` 判定英文词边界，但 Python 的 Unicode 语义把汉字也算作 `\\w`，「与ES（」「讨论ES。」这类**英文编码紧贴汉字**的形态（中文会议里最常见）左右都不存在 `\\b` → `ES→EAS` 写了永不生效。回溯修正复用同一规则，而 `count_term` 残扫也用同一规则，连 residual 告警都是盲的（报 0，而屏幕上 ES 满屏）。现新增 `core.hotwords.ascii_term_pattern()` 作为边界判定的**单一真源**（`(?<![A-Za-z0-9])词(?![A-Za-z0-9])`，大小写不敏感），四处调用点（映射预编译缓存 / `apply_hotword_mappings` 显式入参分支 / `sub_term` / `count_term`）全部改走它：既命中「与ES」，又不误伤 `FILES` / `ESB` / `CH2O`。契约用例 `tests/test_hotword_term_boundary.py`（含「转写侧与回溯侧同口径」与「计数侧与替换侧不分叉」两条锁定）。
- **划词工具栏不跟随主题色（5 套暗色主题下几乎不可读）**：`notes-editor.css` 的反色墨条（`background: var(--fg)`）内部颜色全部硬编码为「深底浅字」常量，暗色主题下墨条翻为近白而文字仍为浅灰 → 白底白字。现下沉为一组局部 token（`--sel-ink*` 基于 `var(--bg)` 用 `oklch(from …)` 派生；语义标改跟 `--ok`/`--warn`/`--error` 走），主按钮 hover 改用 `oklch(from var(--accent) calc(l - 0.06) c h)` 而非固定蓝。实测文字对比度：标准深色 14.67:1 / 标准浅色 16.9:1。

### 涉及文件
- `core/text_correction.py`（新增）、`core/hotwords.py`（+`sub_term`、+`ascii_term_pattern`）、`app/routers/tasks.py`、`app/routers/hotwords.py`（映射行门禁）、`tests/test_text_correction.py`（新增）、`tests/test_hotword_mapping_lines.py`（新增）、`tests/test_hotword_term_boundary.py`（新增）
- `frontend/src/api/tasks.ts`、`views/GeneratingView.vue`、`components/SelectionToolbar.vue`、`composables/useAiInsights.ts`、`styles/notes-editor.css`、`i18n/locales/{zh-CN,en}/{generating,common}.json`（移除会报假成功的 `correction_applied` 文案）

## [未发布] - 2026-09-27 — 决策对象统一：决策流为唯一「决策」（DC-UNIFY-01）

### 变更
- **单一决策对象**（项目方裁决）：「决策」收敛为会议内的决策流节点（`task["todos"]`）这一个对象；原 `task["decisions"]` 记录对象及其 CRUD API（`/api/tasks/{id}/decisions*`）、独立卡片组件（`DecisionCard.vue`）、执行人快照下拉（`OwnerSelectCombobox.vue`）一并下线，存量数据不迁移、无读路径。
- **共享读写口径** `core/decision_flow.py`：执行人以说话人档案为权威（改名全局生效、档案缺失宽容回退快照名）、节点状态字典驱动（历史无 status 由 `done` 布尔兼容推导）、新建节点形状统一（纪要页手动添加 / AI 注入 / 决策中心补录共用）、读侧随行下发状态字典与元信息，前端不再写死枚举。
- **决策中心重做为就地可交互的决策流卡片**：筛选 chips / 色点 / 徽标 / 闭档沉底全部由状态字典驱动（`useDecisionStatuses` 一处加载多处复用）；补录与编辑直接落到来源会议的决策流。纪要页 Tab 界面统一称「决策」，「行动项」降为数据语义描述。
- **CLI 引擎多适配**：`engine_id` 白名单动态取自 `core/cli_engine/manifests/` 目录（新增 claude-code、qoder-cli-cn 清单），设置页引擎下拉数据驱动并带预览探针，新增引擎无需改代码。

### 涉及文件
- `core/decision_flow.py`（新增）、`app/routers/decisions.py`（大幅删减）、`app/routers/notes.py`、`app/routers/decision_statuses.py`、`app/routers/settings.py`、`app/routers/import_tasks.py`
- `frontend/src/views/DecisionCenterView.vue`、`generating/DecisionFlowPanel.vue`、`DecisionNode.vue`、`composables/useDecisionStatuses.ts`（新增）、`components/settings/*`（新增详情面板拆分）
- `tests/test_decision_flow.py`（新增）、删除 `test_dc_r2_*.py` / `test_decision_center.py`；`docs/API_CONTRACTS.md` §12、`docs/GLOSSARY.md` 同步

## [未发布] - 2026-09-27 — 会议库检索体验优化（匹配计数 + 来源标识）

### 变更
- **计数改匹配口径**（LibraryView）：搜索/筛选时，顶部「N 个会议」显示「匹配 N / 共 M」，「全部 / 已归档」Tab 计数显示各 Tab 的匹配数（此前恒为全量 450/194/256，与已筛短的列表不一致，易被误认为搜索失效）。抽出共用过滤函数 `applyLibFilters`，列表分组与计数同口径。
- **来源标识徽章**：靠纪要/转写原文等非标题维度命中的行，标题后加「原文中匹配」徽章（含 tooltip 说明），标题命中的行不加——多维度搜索逻辑（`matchTask`）保持不变，仅将「为什么匹配」可视化。

### 涉及文件
- `frontend/src/views/LibraryView.vue`（过滤函数抽取、匹配计数 computed、来源徽章与样式）
- `frontend/src/utils/search.ts`（新增 `matchesTitle`）
- `frontend/src/i18n/locales/{zh-CN,en}/library.json`（`count_matched` / `source_content` / `source_content_hint`）

## [未发布] - 2026-09-26 — 设置信息架构重构（REQ-SETTINGS-IA）+ 专家详情注释层（REQ-EXPERT-MODE）

### 新增
- **决策层两卡 + 从属详情层**（REQ-SETTINGS-IA）：接入方式收敛为「离线 / 联网」（Q1 定名），配套六张详情卡（账户·套餐 / LLM 算力来源 / ASR 算力来源 / 引擎本地组件 / CLI 引擎 / 使用面回显），缩进+引用轨两层分离；离线态 LLM/ASR 卡整卡「🔒 本机接管」。
- **切换事务端点** `POST /api/settings/access-mode`：切换必经后果预览（字段级 diff + 进程动作 + 计费与出网三段；联网→离线红色风险条目+显式勾选知晓，裁决-2）；任一环节失败全量回滚，settings.json 零写入（裁决-1）。
- **逐能力算力来源**：`capability_source{,_override}` 新字段，体验配额/自带 Key/本机端点逐能力选择；账户「优先使用体验配额」勾选降为详情默认值来源，三态徽章（默认生效/已覆盖/未设置，离线上第四形态本机接管），覆盖状态持久化不被登录/勾选改回；route_override 静默计费改写语义消灭。
- **自动改用三级提示 + 事件记录**（Q3）：L1 能力行内常驻（含 CTA）/ L2 页面 amber 横幅可折叠历史 / L3 联网卡角标；10 分钟预警阈值；每次自动改用落 `data/settings_events.json`（core/settings_events.py，账单争议可查）；界面禁用「降级/兜底/fallback」词。
- **专家详情 = 同模型叠注释层**（REQ-EXPERT-MODE）：页面级 role=switch 开关（移出 radiogroup），开启后卡片/详情卡/矩阵显示等宽工程值行（`engine.mode ▸ local` 式，≥12px）；不再恢复平行旧版分类视图。
- **设置导航 L0→L5 重排 + CLI 引擎分类页**：账户→接入方式→服务→计算引擎→CLI 引擎；探针三段（路径解析→版本校验→登录态）失败段定位（probe_engine 新增 `failed_stage`）常驻回显；对话面板智能体未就绪置灰+指引。
- **会话级对话模型选择器**（第 6 刀使用面闭环）：默认跟随详情，候选=预设模型/探测本机模型并标注来源；每轮回复尾部回显实际消费方与计费口径（done 事件 `model_usage`，与 core/routing 判定同源）；model 缺省改读 llm.model 设置值。
- 词汇五词表入 GLOSSARY v1.4.0（离线/联网/体验配额/自带 Key/本机端点，「托管」等留历史映射注记）。

### 变更
- **单向数据流**：接入方式唯一写入口=决策卡事务端点；逐能力来源写入口=详情卡；「服务」页降为参数唯一编辑面（显式保存）；引擎页 mode dropdown 改只读徽章；卡片内联自动保存面板废除；routers/settings 反向同步降级为旧客户端兼容窗口（仅投影字段真实变化时重对齐，带日落日志）。
- **声纹云端下架**（2026-09-26 裁决①）：`voiceprint.provider/cloud_base_url/cloud_api_key` 字段在 schema/UI/后端三处不存在，CloudEmbeddingProvider 删除；「零出网」结构性为真。存量注册特征无需迁移（cam++-v1-cloud 与 cam++-v1 经 COMPATIBLE_VERSIONS 互兼容，ADR-0009）；存量 settings 键启动时丢弃。
- 流向矩阵搬入接入方式页：四列（离线/体验配额/自带 Key/本机端点）、逐能力行高亮、单元格「出网 ↑ / 零出网」徽章；幽灵枚举 `engine_mode_cloud` 随删。
- `GET /api/settings`：移除 voiceprint 块，新增 `capability` 快照；`GET /api/settings/routing` 新增 `capability`/`auto_switch`/`quota_warning`/`recent_events`；旧客户端 access_mode=hosted/byok 提交归一化为 cloud+对应来源。
- 状态栏/顶栏徽章文案切五词表（离线/体验配额/自带 Key）；App.vue 事后 toast 降为兜底（主路径 L1-L3 常驻）。
- tierName 去写死：读账户真实档位，未知档降级显原值。

### 存量迁移
| 存量 access_mode | 迁移为 | 投影不变量 |
|---|---|---|
| local | 离线模式 | engine.mode=local |
| hosted | 联网 + LLM/ASR=体验配额 + 勾选开 | engine.mode=proxy |
| byok | 联网 + 来源=自带 Key（llm localhost 识别为本机端点） | engine.mode=direct |

混配存量逐能力读实际值并标覆盖（冲突明示）；A1 裁决（direct+订阅开=托管）废止；新增标记 `_settings_ia_migrated`。

### 涉及文件
- 后端：`app/settings_store.py`、`app/routers/settings.py`、`app/routers/chat.py`、`core/routing.py` v2.0、`core/settings_events.py`（新）、`core/embedding_provider.py`、`core/voiceprint_registry.py`、`core/cli_engine/probe.py`
- 前端：`api/access.ts` 重写、`api/settings.ts`、`api/chat.ts`、`stores/engine.ts`、`components/settings/AccessModeCards.vue` 重写、`components/settings/CliEnginePanel.vue`（新）、`views/SettingsView.vue`、`AiChatPanel.vue`、`AIPanel.vue`、`useAiChat.ts`、`App.vue`、i18n（settings/common/topbar/ai-panel × 双语）
- 测试：`test_access_mode_migration.py` 重写（迁移全组合+事务回滚）、`test_routing_decision.py` 重写（逐能力来源）、`test_settings_i18n_vocab.py`（新，五词 lint）、`test_expert_mode.py`（新，探针/注释层门禁）；全量 580 绿；文档：`docs/BACKLOG.md`、`docs/DISPATCH-TRACKER.md`、`docs/GLOSSARY.md` v1.4.0
- 浏览器点验项（两单 AC 清单列明）交 QA 通道，产品侧出验收单

## [未发布] - 2026-09-25 — 洞察台会后化（REQ-INSIGHT-DECK-POSTMEETING）

### 新增
- **纪要页「洞察」第 5 个 Tab**（只读回看）：`RecInsightsPanel` 新增 `mode: 'live' | 'readonly'`（live 默认行为不变），只读态隐藏开关/频率/扩展控件、消息无视能开关始终可见；空态与图工具栏提供「分析本场会议」入口；进入 Tab 即已读，跳转时间戳联动原文与音频。
- **会后补分析端点** `POST /api/insights/analyze/task/{task_id}`（契约见 API_CONTRACTS §14）：服务端从任务读完整 dialogue + 章节，取最近 40 句（可配置）跑一轮角色感知洞察分析；同任务进行中 409、超时 60s（可配置）→504 不写盘；有发现时后端追加快照落盘（`phase="post_meeting"`，卡片带「会后」徽标），前端重拉刷新。
- **洞察注入 AI 会话上下文**：chat qa/stream 两路径新增「会议洞察台」块（≤ 5 条 / 1200 字符，diagram 不整段注入）；`generating` 页面上下文上线；CLI 智能体引擎工作区导出 `context/insights.md`（全量）。会后用户可直接和洞察台的内容对话。
- 侧栏洞察指示器放宽：会后态也可达（静态展示不脉动）；洞察消息新增可选 `phase` 字段，存量文件缺字段按 `meeting` 读取，零迁移。

### 修复
- 启动孤儿清理遗漏 `.insights.json` 伴生文件（`app/task_store.py` 两处），删除级联现已覆盖三件套。

### 涉及文件
- 后端：`app/routers/insights.py`、`app/routers/chat.py`、`core/chat_context.py`、`core/cli_engine/context_export.py`、`app/task_store.py`
- 前端：`useAiInsights.ts`、`useGeneratingData.ts`、`GeneratingView.vue`、`RecInsightsPanel.vue`、`ActivityRail.vue`、`api/insights.ts`、i18n、`meeting-view.css`、`activity-rail.css`
- 测试：`test_smoke.py`（+4）、`test_chat.py`（+4，1 改写）、`test_cli_engine.py`（+2）；文档：`docs/REQUIREMENT-INSIGHT-DECK-POSTMEETING.md`、`API_CONTRACTS.md` §14、`VUE_COMPONENT_MAP.md`


## [未发布] - 2026-09-23 — Insight Deck 画布改造（workflow 阶段卡样式）

### 变更
- **输入契约改为大模型原生的受约束 Mermaid**：洞察台提示词（`core/insights.py` + 两个角色 `insights.md`）删除「结构化知识图谱 graph 字段」节，新增「洞察台画布书写规范」（`flowchart LR` + subgraph 阶段 + `@@<毫秒>` 转写定位标记 + `---` 无箭头连线）；返回 JSON 不再含 graph。转写行携带 `mm:ss` 时间戳供模型提取 `@@` 标记。历史数据兼容：后端仍透传旧 graph 字段，仅旧会话重载时生效。
- **画布渲染器替换 G6 圆点关系图**：新增 `frontend/src/utils/parseInsightFlow.ts`（受约束 Mermaid → 阶段卡结构，非法输入返回 null 触发降级；20 项 Node 单测覆盖验收项，`npm run test:parser`）与 `InsightFlow.vue`（点阵背景、阶段卡错行排布、SVG 直角无箭头连线、适应画布/缩放/全屏控件、芯片点击跳转转写与 hover tooltip、明暗主题）。
- **降级路径**：解析失败 → 现有 `MermaidDiagram.vue` 直接渲染原始 Mermaid，用户永远有图看。
- **@antv/g6 依赖移除**：`InsightGraph.vue` 重写为零依赖静态 SVG（历史消息降级展示，保留节点点击跳转）；锁文件 g6 相关条目清零。包体积说明：构建产物中 cytoscape/elk 等大 chunk 仍存留，系 mermaid 自身传递依赖，与 g6 无关。
- **CSS 修复经验**：Mermaid 铺满规则 `.rec-insight-diagram svg` 会波及画布内部图标（11px 被拉伸至 176px），已收窄为 `.mermaid-diagram-svg > svg` 精确命中渲染体并加画布内尺寸防御。

### 涉及文件
- `core/insights.py`（prompt 重写、graph 透传兼容、用户消息时间戳）
- `data/agent/_roles/_builtin/{meeting-minutes,learning-tutor}/insights.md`（同步规范，v2.0.0）
- `frontend/src/utils/parseInsightFlow.ts`、`frontend/src/components/common/InsightFlow.vue`（新建）
- `frontend/src/components/common/InsightGraph.vue`（重写为静态 SVG）
- `frontend/src/views/recording/RecInsightsPanel.vue`、`composables/useAiInsights.ts`、`api/insights.ts`、`styles/recording-view.css`、i18n `{zh-CN,en}/recording.json`
- `frontend/package.json`（移除 @antv/g6，新增 test:parser）

## [v7.4.5] - 2026-09-17

### 修复
- **云端离线转写 `SUCCESS_WITH_NO_VALID_FRAGMENT`（Windows 用户反馈）**：低音量录音（如 mean=-81.9 dB）实时流式转写正常，但离线 `paraformer-v2` 服务端 VAD 判整段为静音导致任务失败。三处联合修复：
  - **响度归一化（治本）**：`core/audio.py` 新增 `_measure_max_volume_db()`（ffmpeg volumedetect 探测峰值），`normalize_audio()` 增加条件式增益——仅当峰值低于 `quiet_threshold_db`（默认 -20 dB）时应用 `volume` 增益（目标峰值 -3 dB，上限 40 dB）+ `alimiter` 限幅防削波；正常音量音频命令不变，避免回归与底噪放大。
  - **真实错误透传**：`core/cloud_client.py` 的 `_cloud_upload_file()` 对服务端业务错误（HTTPError）改为 `raise RuntimeError(detail)`，使 `转写任务失败: SUCCESS_WITH_NO_VALID_FRAGMENT` 冒泡到 `classify_error()`，命中 `errors.py` 已有的可读建议「音频中未检测到有效语音」（此前被通用文案覆盖，落到 unknown 分类）。连接级失败仍返回 None。
  - **实时转写降级兜底**：`core/pipeline_runner.py` 新增 `_build_dialogue_from_realtime()` / `_try_realtime_fallback()`，当批转写抛非瞬时错误或返回空 dialogue 且存在 `realtime_full_transcript` 时，用实时结果构建对话稿并继续生成纪要（复用实时说话人绑定姓名），任务标记 `transcript_source=realtime_fallback` 而非整单失败。
- **纪要页失败态 404 原始 JSON**：任务失败后 `output_path`/`audio_path` 为空，此前 `GeneratingView` 仍渲染工具栏与 `<audio>`，点击导出会在浏览器新标签页展示 `{"detail":"Not Found"}` 原始 JSON；音频元素后台也会打 `/api/audio/{id}` 404。改造：`useGeneratingData.ts` 增加 `isFailed` 守卫（audioUrl 空串、onCopy/onExport 拦截）与 `failureInfo` 分类（transient/api_config/audio/no_speech/unknown，复用 `error_category` + `error_suggestion`）；`GeneratingView.vue` 在 `isFailed` 时用居中大卡片整页替换，含彩色图标、可读文案、原始错误折叠展开、「重试转写 + 返回会议库」两个操作（重试复用 `retranscribe` API 并乐观更新状态）；色相与侧边栏 `TaskCard.vue` 保持一致。新增 i18n `generating.failure.{title,show_raw,back_to_library}` zh-CN/en。
- **旧版单文件模式 SPA 刷新 404**：`app/server.py` 在 `frontend/dist` 缺失回退到 `app/static/index.html` 的旧版分支下，未挂载 SPA catch-all，导致 Vue Router history 模式在 `/settings`、`/library` 等子页面 F5 刷新命中 FastAPI 默认 404 JSON。新增 `legacy_frontend_catch_all` 路由：非 `api/`、`ws/`、`auth/` 前缀的路径统一返回 `app/static/index.html`，交由前端 router 接管。

### 涉及文件
- `core/audio.py`：响度归一化 + 音量测量
- `core/cloud_client.py`：HTTPError 透传真实 detail
- `core/pipeline_runner.py`：实时转写降级兜底
- `app/server.py`：旧版分支 SPA catch-all 路由
- `frontend/src/composables/useGeneratingData.ts`：isFailed 守卫 + failureInfo 分类
- `frontend/src/views/GeneratingView.vue`：失败态整页卡片 UI + 重试逻辑
- `frontend/src/styles/meeting-view.css`：`.gen-failure-*` 样式（含四色图标底）
- `frontend/src/i18n/locales/{zh-CN,en}/generating.json`：失败态文案
- `VERSION`：7.4.4 → 7.4.5
- `CHANGELOG.md`：本条目

## [v7.3.0] - 2026-09-16

### 新增
- **Agent 角色系统**：
  - 新增 `core/agent_workspace.py` 实现角色目录扫描、YAML front matter 解析、角色加载与 fork 管理
  - 新增 `app/routers/agent.py` 暴露 REST API（`/api/agent/roles`、`/api/agent/active`、fork/save/delete）
  - 新增前端 `AgentsView.vue` 角色管理视图、`stores/agent.ts` Pinia store、`api/agent.ts` API 客户端
  - 预定义 5 个内置角色：meeting-minutes（会议纪要师）、meeting-analyst（会议分析师）、meeting-coach（会议教练）、deep-reader（深度阅读者）、learning-tutor（学习导师）
  - 支持用户 fork 自定义角色、编辑 `.md` 文件、删除自定义角色
  - 全局激活模式：`settings.json` 持久化 `active_agent`，所有会话共享同一角色
- **Agent 渐进式循环架构**：
  - `core/agent_loop.py` 实现工具调用循环（get_meeting_info/transcript/todos/search_project_files/get_hotwords/get_system_settings）
  - SSE 协议扩展：新增 `stage`/`tool_call`/`tool_result` 事件类型
  - 云端代理兼容：`cloud_api.py` 新增 `tools`/`tool_choice` 字段支持 function calling
  - 双模式支持：原生 function calling（本地 Key）+ 文本回退（云端代理）
- **设计文档**：新增 `docs/design/AGENT_ROLE_SYSTEM.md`（525 行）、ADR-0017 Agent 角色系统

### 变更
- **前端 UI 优化**：
  - `GeneratingView.vue`、`SettingsView.vue`、`SpeakersView.vue` 等核心视图组件改进
  - `DecisionFlowPanel.vue`、`DecisionNode.vue` 简化重构
  - `NotesPanel.vue`、`SummaryPanel.vue` 增强
  - `SelectionToolbar.vue`、`AIPanel.vue`、`ActivityRail.vue` 交互优化
  - `InlineEditInput.vue` 组件增强、`useInlineEdit.ts` composable 扩展
- **样式系统**：`notes-editor.css` 重构（162 行变更）、`ai-panel.css`/`layout.css`/`topbar.css` 微调
- **i18n**：新增 `agents.json`（zh-CN/en）、更新 `generating.json`/`settings.json`/`login.json`/`sidebar.json`/`start.json`/`common.json`
- **后端改进**：`core/llm.py`、`core/metering.py`、`core/pipeline.py`、`core/realtime_asr.py`、`core/summarize.py`、`core/transcribe.py` 多项优化
- **Windows 安装器**：`installer.iss`、`launcher.bat` 更新

### 修复
- `app/routers/record.py` 补充 `from core import realtime_asr` 导入（F821 错误）
- `AgentsView.vue`、`DecisionNode.vue` 移除未使用变量（TS6133 错误）
- CI 工作流：ffmpeg 安装从第三方 Action 改为 `apt-get install ffmpeg`（Node.js 20→24 兼容性问题）

## [v7.2.2] - 2026-09-15

### 修复
- **BUG-001 (P0)**：录音启动后立即崩溃（僵尸状态）
  - 根因：ffmpeg 命令硬编码 `-f avfoundation`（仅 macOS），Windows 不支持
  - 修复：跨平台适配 — Windows 使用 `-f dshow` + 自动检测音频设备；新增僵尸录音清理机制
- **BUG-002 (P0)**：LLM 占位符 Key 被当作有效 Key，未触发云端降级
  - 根因：`_should_use_cloud()` 将 `sk-xxxx...` 占位符视为有效 Key
  - 修复：新增 `_is_placeholder_key()` 检测 `xxxx`/`your-`/长度不足等模式
- **BUG-003 (P1)**：400/500 错误响应体为空 → 添加自定义 Exception 处理器，始终返回 `{"detail": ...}` JSON
- **BUG-005 (P2)**：`/api/health` 端点缺失 → 添加 `GET /api/health` 返回 `{"status": "ok"}`
- **BUG-006 (P2)**：`server.log` 始终为空（frozen 模式）→ `logging.basicConfig()` 使用 `force=True` 强制重新配置
- **BUG-008 (P3)**：设置页 ServiceProvider 下拉框空白 → 前端加载设置时将短名映射匹配到预设全名
- 涉及文件：`app/routers/record.py`、`app/server.py`、`core/audio_recording.py`、`core/llm.py`、`frontend/src/views/SettingsView.vue`

## [v7.2.1] - 2026-09-15

### 修复
- **桌面端占位符检测**：`.env.example` 模板值（如 `http://your-server:8000`）不再阻止真实默认值注入
  - 根因：占位符是非空字符串，`if not os.getenv()` 检查时认为值已存在，真实云端地址永远不会被注入
  - 修复：新增 `_is_placeholder()` 检测函数，识别包含 `your-`/`xxxx`/`sk-xxx` 的占位符值，自动替换为真实默认地址
- 涉及文件：`desktop.py`

## [v7.2.0] - 2026-09-15

### 决策
- **云端代理 ASR/LLM 混合架构**：桌面客户端默认通过云端服务器中转 ASR/LLM 请求，用户只需手机号登录即可零配置使用全部功能（录音/转写/AI 问答），无需手动配置任何 API Key；同时保留本地直连模式供高级用户切换

### 新增
- **服务端代理端点**（`app/routers/cloud_api.py`）：
  - `POST /api/cloud/llm/chat/completions` — LLM 代理转发到 DashScope，带 HMAC 认证 + 配额检查 + 用量自动上报
  - `POST /api/cloud/asr/transcribe` — ASR 代理转发到同机 ASR 代理，支持 multipart 文件上传
- **客户端云端调用**（`core/cloud_client.py`）：
  - `cloud_llm_chat()` — 通过云端调用 LLM，自动携带用户 token
  - `cloud_transcribe()` — 上传音频到云端进行转写
  - `_cloud_upload_file()` — multipart 文件上传辅助函数

### 变更
- **核心模块集成**：
  - `core/llm.py`：新增 `_should_use_cloud()` 检测，无本地 Key 时自动走云端代理
  - `core/transcribe.py`：新增 `mode=cloud` 分支 + 自动降级逻辑
  - `app/settings_store.py`：ASR 支持 `proxy`/`direct`/`cloud` 三种模式
  - `desktop.py`：默认设置 `CLOUD_API_URL` + `ASR_MODE=cloud`；移除 API Key 未配置弹窗
- **前端**：`SettingsView.vue` ASR 模式下拉增加「云端代理」选项；i18n 新增 `asr_mode_cloud`
- **配置**：`.env.example` 增加 `ASR_MODE` 说明文档

### 影响
- 桌面端默认注入 `CLOUD_API_URL=http://47.116.10.194:8000` 与 `CLOUD_API_TOKEN`，用户安装后手机号登录即可直接使用
- 服务端承担 HMAC 鉴权与配额扣减职责；ASR 代理通过同机 `localhost:8000` 调用，避免跨网络延迟
- 涉及文件：`app/routers/cloud_api.py`、`core/cloud_client.py`、`core/llm.py`、`core/transcribe.py`、`app/settings_store.py`、`desktop.py`、`frontend/src/views/SettingsView.vue`

## [v7.1.8] - 2026-09-15

### 修复
- **Windows 桌面客户端 ASR/LLM 不可用** — 配置自动初始化
  - 根因：桌面客户端（exe）被当作 Web 服务器配置，无 `.env` 文件 → `DASHSCOPE_API_KEY` 为空 → LLM 500 错误；ASR 默认 proxy 模式需 `ASR_PROXY_URL` → 转写失败
  - 修复（三层防御）：
    1. `desktop.py` `_setup_desktop_env()`：frozen 模式首次启动自动从 `.env.example` 创建 `.env`，注入 `ASR_MODE=direct` + SMS 代理默认地址
    2. `settings_store.py` `get_asr_config()`：环境变量 `ASR_MODE` 优先于 `settings.json`；proxy 模式无 URL 时自动降级为 direct 模式
    3. `desktop.py` `_check_api_key_config()`：frozen 模式启动时检测 API Key 是否为占位符，未配置时弹窗提醒
- 涉及文件：`.env.example`、`app/settings_store.py`、`desktop.py`

## [v7.1.4] - 2026-09-15

### 修复
- **Windows PyInstaller 打包遗漏 app/core 模块**
  - 根因：Windows spec 缺少 `sys.path.insert(0, ROOT)`，导致 `collect_submodules` 在 CI 环境中无法找到 `app/core` 包
  - 修复：添加 `sys.path` 修复（与 macOS spec 对齐）；显式列举全部 72 个 `app/core` 子模块（双重保险）；补充 `VERSION` 和 `core/i18n/locales` 到 `datas`
- **诊断打印改为英文**：避免 Windows CI `cp1252` 编码错误
- **Windows 桌面客户端三个用户反馈问题**：
  1. ffmpeg 不可用：添加 PyInstaller frozen 环境下 ffmpeg 路径自动解析（优先系统 PATH → exe 同级 `ffmpeg/` → 项目根目录）
  2. 手机号登录失败：内置 SMS 代理默认配置（`SMS_PROXY_URL` 默认指向官方云服务）
  3. 状态栏硬编码模型名：改为从后端设置动态读取，默认值 `paraformer-v2` + `qwen-plus`
- **`/auth/me` 返回增加 `subscription` 字段**：修复手机用户看不到配额的问题
- 涉及文件：`build/pyinstaller.spec`、`core/audio.py`、`core/sms.py`、`frontend/src/App.vue`、`app/routers/auth.py`、`frontend/src/api/types.ts`

## [v7.1.1] - 2026-09-15

### 修复
- **Windows 安装器编译失败** — `ChineseSimplified.isl` 不存在
  - Inno Setup 6 通过 Chocolatey 安装时不包含第三方中文语言包
  - 修复：`installer.iss` 使用 `#if FileExists()` 条件引用中文语言包；`build-windows.yml` 新增下载 `.isl` 步骤，失败时优雅降级为英文
- **installer.iss 无效的 Flags 参数**：移除 `.env.example` 的 `skipifexists` flag（Inno Setup 不支持），仅保留 `uninsneveruninstall`
- **data 目录 flag 修复**：移除 `skipifexists` 无效 flag，添加 `recursesubdirs` 配合 `createallsubdirs`
- **CI 失败修复**：`desktop.py` uvicorn F821 未定义名称 + `App.vue` TS6133 未使用变量
- 涉及文件：`build/installer.iss`、`.github/workflows/build-windows.yml`、`desktop.py`、`frontend/src/App.vue`

## [v7.1.0] - 2026-09-15

### 变更
- **会议纪要待办改决策**：
  - 新增 `DecisionFlowPanel.vue`、`DecisionNode.vue` 决策流面板组件
  - 删除 `TodosPanel.vue`，待办功能合并到 `NotesPanel.vue`
  - `NotesPanel.vue`、`SummaryPanel.vue` 简化重构
  - 新增 `usePhilosophy.ts` composable、`InlineEditInput.vue` 组件
- **主题系统更新**：
  - 删除 `lavender.css`、`ocean.css`、`rose.css` 三个主题
  - 新增 `mist.css`、`wheat.css`、`standard-light.css`、`standard-dark.css` 四个主题
  - 现有主题（`default.css`、`dark.css`、`forest.css`、`warm.css`）变量更新
- **前端 i18n**：更新 `common.json`、`generating.json`、`hotwords.json`、`projects.json`、`speakers.json`、`ai-panel.json`（zh-CN/en）
- **视图组件优化**：`GeneratingView.vue`、`HotwordsView.vue`、`LibraryView.vue`、`ProjectsView.vue`、`RecordingView.vue`、`SpeakersView.vue` 交互改进
- **样式重构**：`notes-editor.css`（285 行变更）、`ai-canvas.css`、`hotwords.css`、`layout.css`、`meeting-view.css`、`speakers.css` 调整
- **后端改进**：`app/routers/chat.py`、`app/routers/notes.py`、`app/routers/philosophy.py`、`app/routers/usage.py` 优化
- **新增云端代理基础**：`app/routers/cloud_api.py`、`core/cloud_client.py`（为 v7.2.0 铺垫）
- **文档**：新增 `docs/GIT_COLLABORATION_GUIDE.md`、更新 `docs/VUE_COMPONENT_MAP.md`
- **测试**：新增 `tests/test_chat.py`、`tests/test_misc.py`
- **CI/CD**：新增 `.github/ISSUE_TEMPLATE/`、`.github/PULL_REQUEST_TEMPLATE.md`、`.github/workflows/build-macos.yml`、`build-windows.yml`、`ci.yml`、`dco.yml`

## [v2.x-overlay-standardization] - 2026-09-13

### 变更
- **蒙版体系统一**（6 Phase 实施，详见 `docs/design/OVERLAY_PLAN.md`）：
  - **Token 化**：`base.css` 新增 `--overlay-bg` / `--overlay-bg-soft` / `--overlay-bg-heavy` / `--overlay-enter` / `--card-enter` / `--modal-width-*` 蒙版 token；新增全局基础类 `.oms-overlay` + `.oms-overlay-card` + `.oms-card-guided`
  - **背景收敛**：12 处蒙版背景色统一为 `var(--overlay-bg)`，2 处硬编码 `z-index: 1000` 改为 `var(--z-modal)`
  - **ESC 关闭**：新增 `useEscClose` composable（window 级 keydown 监听），5 个弹窗补全 ESC 关闭支持；所有可关闭弹窗的取消按钮添加 `<kbd>ESC</kbd>` 键帽标识
  - **动效统一**：10 个弹窗统一为 2 种标准入场动效（标准 Modal: overlay fade 0.2s + card translateY(8px) 0.25s；引导型 Modal: overlay fade 0.2s + card translateY(16px) scale(0.97) 0.4s）
  - **全局类迁移**：DeleteDialog / ArchiveDialog 从 `v-if` + scoped 样式迁移到 `v-show` + 全局 `.oms-overlay` + `.oms-overlay-card`
  - **死代码清理**：删除 `meeting-view.css` 和 `speakers.css` 中各 40 行无引用的向导 CSS（`.wizard-overlay` / `.wizard` / `.wiz-*`）
- 涉及文件：`base.css` / `meeting-view.css` / `speakers.css` / `recording-view.css` / `update-panel.css` / `start-page.css` / `DeleteDialog.vue` / `ArchiveDialog.vue` / `SpeakersView.vue` / `StartView.vue` / 新增 `useEscClose.ts`

## [v2.x-rename-project-to-knowledge-base] - 2026-09-13

### 变更
- **术语重命名**：「项目 / Project」→「文档知识库 / Document Knowledge Base」，解决 GitHub 开发者对「Project」一词的心智模型冲突（易与代码仓库混淆）。新名称自带「需要文档」暗示，降低用户理解成本
- **前端 i18n**：zh-CN 全部「项目」→「知识库」，en 全部「Project」→「Knowledge Base」；涉及 projects.json、generating.json、sidebar.json、ai-panel.json 四个语言包
- **前端 UX 引导**：空状态文案增加文件类型提示（.md / .txt / .docx / .pdf）与行动指引；副标题明确说明文档类型要求
- **后端 gettext**：所有用户可见错误消息的 msgid/msgstr 同步更新（「知识库不存在」「任务未关联知识库」等）；涉及 `app/routers/projects.py`、`app/routers/tasks.py`、`scripts/gen_i18n_po.py`、两个 `.po` 文件
- **内部代码不变**：`project_id`、`projects.json`、API 路由路径、TypeScript `Project` 接口等内部标识符保持不变，避免破坏性变更
- **知识库关联 chip 交互升级**：
  - 图标从「文件夹」→「书本打开」（book-open），与「知识库」语义匹配
  - 新增尾部状态图标：未关联态显示 `+`（暗示可添加），已关联态 hover 显示 `✕`（暗示可移除）
  - 新增 tooltip 引导：未关联时提示「关联知识库，让 AI 基于你的资料理解会议」，已关联时提示「已关联知识库，点击可切换」
  - 空知识库列表时下拉菜单显示「新建知识库」引导按钮，点击跳转至知识库管理页
  - 涉及 `GeneratingView.vue`、`RecControlBar.vue`、`meeting-view.css`、`speakers.css`

## [v2.x-trial-region-restriction] - 2026-09-13

### 决策
- **体验期共享 proxy 仅限中国大陆地区用户**：开发者 API Key 部署在国内云端服务器，云端 AI 服务区域限制与数据跨境合规问题要求限制体验期用户范围。国内手机号（SMS）验证作为天然地理屏障，GitHub OAuth / 本地账户用户需自行配置 API Key。

### 变更
- **后端代码**：`core/metering.py` 的 `is_metered()` 增加 `provider == "sms"` 检查，非 SMS 用户返回 `False`（不计量，需自持 Key）
- **文档**：`SECURITY.md` 新增「体验期服务区域限制」章节（含注册方式对照表）；`AUTH_DESIGN.md` 补充区域限制策略与代码实现说明
- **前端**：`StartView.vue` 隐私弹窗新增区域限制提示；i18n 新增 `disclaimer_region` 条目（zh-CN/en）；`start-page.css` 新增 `.privacy-dialog-region` 样式
- **前端 UI 抽象化**：用户可见文案中的具体云端 AI 服务商名称统一替换为「云端 AI 服务」，包括：隐私弹窗 `disclaimer_cloud`、底部状态栏 `cloud_connected`（i18n key 从 `dashscope_connected` 重命名）、`SettingsView.vue` ASR provider 回退值；代码内部与开发者文档中的技术依赖名称保留不变
- **文档抽象化**：`SECURITY.md` 全文云端 AI 服务商品牌引用替换为「云端 AI 服务提供商」通用描述（数据流向表、架构图、免责条款、第三方依赖表、UI 文案模板）；`AUTH_DESIGN.md` 加注「默认厂商为 DashScope（可替换为任意兼容 API）」并抽象化区域限制说明

## [v2.x-i18n-speaker-fallback] - 2026-09-12

### 修复
- 后端发言人名称 fallback 从硬编码中文（"发言人N"/"说话人N"）改为空字符串或英文（"Speaker N"），由前端 i18n 系统统一渲染，解决英文模式下仍显示中文发言人名称的问题
- 自动创建默认用户的名称从 "本地用户" 改为 "Local User"
- 涉及文件：`app/realtime_store.py`、`app/routers/record.py`、`app/routers/chat.py`、`app/routers/speakers.py`、`app/routers/voiceprint.py`、`core/text_bridge.py`、`core/chapters.py`、`core/summarize.py`、`core/pipeline.py`、`core/speakers.py`、`core/chat_actions.py`

## [v2.x-decommercialize-subscription] - 2026-09-12

### 决策
- **去除商业订阅概念，重新定位为「个人开发者 + 体验授权」**：项目代码和文档中存在系统性的 SaaS 商业化假设（四档订阅套餐、月费定价、自动续费、转化漏斗等），与实际定位「个人开发者维护的开源软件，不提供商业订阅服务」严重不符。本次清理覆盖 8 个代码文件 + 7 个文档文件，共 30+ 处修改。

### 变更
- **后端代码**：`core/metering.py` 简化 `TIER_QUOTAS` 为单一体验期档位（删除 personal/pro/team）、注释重命名（订阅→授权）；`core/users.py` 去除 `auto_renew` 字段并重命名注释；`core/diarization_cluster.py` 更新功能门控注释；`app/routers/usage.py` 简化 TIER_NAMES；`app/routers/admin.py` 简化统计与授权端点
- **管理后台**：`admin.html` 去除多档位选择器，仅保留「体验期」；删除「付费用户」统计卡片；简化 `tierLabel()` 函数
- **前端 i18n**：`settings.json`（zh-CN/en）简化 `tier_names` 为单一 `free` 键；修正 `cloud_mode_hint`、`diarization_requires_subscription`、`diarization_local_toggle_desc` 文案；`login.json`（zh-CN/en）修正自相矛盾的「个人版完全免费，无需订阅」→「登录即可体验全部功能」
- **前端组件**：`SettingsView.vue` 简化 `tierName()` 函数，注释「用量与订阅」→「用量与配额」
- **文档 AUTH_DESIGN.md**：标题「认证与订阅」→「认证与授权」；「订阅用户 vs 未订阅用户」→「共享 proxy 用户 vs 自持 Key 用户」；去除「平台提供」「按流量付费」等 SaaS 术语；支付方案标记为已取消
- **文档 USAGE_METERING_DESIGN.md**：删除资费梯度表（¥29/¥79/¥59）；删除「查看资费方案」「引导升级」等 UI 设计；删除 `auto_renew` 字段；术语全部从「订阅」改为「授权」
- **ADR-0006**：状态从 `Proposed` 改为 `Superseded`；添加定位说明；支付方案标记为已取消
- **ADR-0015**：「商业模式演进」→「体验授权机制」；「引流授权服务」→「体验授权服务」；去除「转化追踪」「转化路径」等商业术语；「团队订阅付费」→「协作授权」
- **ADR-0009**：「订阅增值服务」→「授权用户的可选云端能力」；功能门控描述从「订阅用户」改为「扩展授权用户」

### 话语体系对照表

| 旧表述 | 新表述 |
|------|------|
| 订阅 | 授权 |
| 平台提供 | 开发者共享代理 |
| 按流量付费 | 体验期内免费 |
| 体验版 / 个人版 / 专业版 / 团队版 | 体验期（唯一档位） |
| 引流 / 转化 | 体验 / 试用 |
| 自带 Key | 自持 Key |

## [v2.x-terminology] - 2026-09-12

### 变更
- **全局术语替换：「本地优先」→「本地数据·云端智能」**：项目文档中长期使用「本地优先」来描述架构理念，但该表述容易让用户误读为「纯离线运行」或「拒绝云端 API」，与软件实际架构（用户数据本地生成与存储，计算智能由云端模型 API 提供）不符。本次全局替换覆盖 MISSION.md、AGENTS.md、MVP_PLAN.md、ROADMAP.md、CHANGELOG.md、docs/README.md、docs/design/MOBILE_DESIGN.md 以及 ADR-0001/0006/0009/0014/0015/0016 等文档，统一采用「本地数据·云端智能」作为核心架构理念的标准表述。ADR-0015 文件名与标题保留原文作为历史决策记录。

| 文件 | 操作 | 说明 |
|------|------|------|
| `MISSION.md` | 修改 | 4 处替换（front matter、一句话定位、设计原则、注释） |
| `AGENTS.md` | 修改 | 禁区条款替换 |
| `MVP_PLAN.md` | 修改 | 与 MISSION 关系说明替换 |
| `docs/ROADMAP.md` | 修改 | 2 处替换（front matter、正文） |
| `docs/README.md` | 修改 | 文档索引表 MISSION 定位描述替换 |
| `docs/design/MOBILE_DESIGN.md` | 修改 | 3 处替换（变更摘要、问题描述、核心约束） |
| `docs/adr/README.md` | 修改 | ADR-0015 索引描述替换 |
| `docs/adr/0001-mvp走云方案.md` | 修改 | 后果条款替换 |
| `docs/adr/0006-认证与订阅架构.md` | 修改 | 2 处替换（约束条件、后果） |
| `docs/adr/0009-声纹识别服务云端拆分.md` | 修改 | 默认模式描述替换 |
| `docs/adr/0014-移动端走Webhook消息流.md` | 修改 | 项目定位描述替换 |
| `docs/adr/0015-本地优先原则重定义与引流授权服务.md` | 修改 | 正文术语替换 + 添加编者注（标题保留原文） |
| `docs/adr/0016-开源许可证变更为AGPLv3.md` | 修改 | 背景条款替换 |
| `CHANGELOG.md` | 修改 | 历史条目术语同步更新 |

## [v2.x-i18n-default-en] - 2026-09-12

### 变更
- **默认语言由中文改为英文（开源国际化对齐）**
  - 后端 `DEFAULT_LOCALE` 从 `"zh_CN"` 改为 `"en"`（`core/i18n/middleware.py`）
  - 前端静态导入从 `zh-CN` 切换为 `en`，`fallbackLocale` 改为 `'en'`，`detectLocale()` 回退值改为 `'en'`（`frontend/src/i18n/index.ts`）
  - 编译 `en/LC_MESSAGES/messages.mo`（此前仅有 .po 无 .mo）
  - README.md 重写为英文主版本，原中文版保存为 `README_zh-CN.md`
  - pyproject.toml `description` 改为英文
  - 中文（zh-CN）作为一等翻译语言保留，浏览器语言检测仍优先识别中文

## [v2.x-security-disclaimer] - 2026-09-12

### 新增
- **数据安全与隐私保护免责声明**
  - SECURITY.md 新增「数据安全与隐私保护声明」章节，涵盖：架构数据流向说明（本地 vs 云端）、敏感数据使用警告、标准免责条款、第三方服务依赖声明
  - 提供 5 套 UI 提示文案：首次启动弹窗、录音页顶部警告横幅、录音前二次确认弹窗、设置页提示条、文件上传确认
- **隐私警告 UI 实现**
  - 新建 `usePrivacyDisclaimer` composable，管理免责声明确认状态（localStorage 持久化）
  - StartView：首次访问弹出数据安全须知弹窗（不可跳过）；录音前弹出确认弹窗（含涉密/商业机密/隐私三项检查）；上传前弹出确认弹窗
  - RecordingView：录音页顶部显示隐私警告横幅（可关闭）
  - SettingsView：设置页顶部显示隐私提示条（含“了解详情”链接，可关闭）
  - i18n 中英文翻译同步更新（start.json / recording.json / settings.json）

## [v2.x-sidebar-perf] - 2026-09-12

### 变更
- **侧边栏 TaskList 性能优化：虚拟滚动 + 搜索防抖 + 增量更新**
  - TaskList.vue 从 plain `v-for` 改造为 DynamicScroller 虚拟滚动，仅渲染可视区域内的 TaskCard，解决会议列表增大时的 DOM 爆炸与渲染卡顿
  - task store 搜索过滤新增 300ms 防抖（`debouncedQuery`），避免每次按键触发全量过滤重算
  - rename / retry 操作改为 `patchTaskLocal` 增量更新，不再调用 `loadTasks()` 全量重新拉取
  - CSS 适配：虚拟滚动容器内禁用 transition 动画，避免高度测量不同步导致内容重叠
  - 播放定位从 `scrollIntoView` 改为 `scrollToItem` + flatItems 索引查找
  - 时间轴视觉修复：圆形节点/小圆环/连接线统一以 24px 留白槽内轴线（中心 x=12，border-box 外径语义）定位且偏移均 ≥0，修复虚拟滚动容器 overflow 剪切圆环、圆环与标题未垂直居中、连线与圆环未水平对齐问题；组头线段改为贯穿全高（节点盖线）消除与上一段的衔接空档（仅列表首项节点上方留空）；移除小圆环后的水平短杠

## [v2.x-auto-scroll-and-alignment] - 2026-09-12

### 修复
- **录音页自动滚动逻辑内聚化 + 回到底部按钮归属修正 + 转写行与 partial 文本对齐**
  - 自动滚动逻辑从 RecordingView 迁移到 RecTranscriptPanel 内部，新行到达时自动 `scrollToItem(len-1)`
  - 用户手动滚动时暂停自动跟随（`autoFollow = false`），显示「回到底部」按钮；滚回底部或点击按钮时恢复
  - 「回到底部」按钮从 `.rec-transcript` 根级移到 `.rec-scroll-wrap` 内，作为 DynamicScroller 的 absolute 定位子元素
  - item-wrapper 水平 padding 改为由 `.rec-transcript-item` 统一处理（`padding-left/right: var(--s-7)`），解决 DynamicScroller 绝对定位 items 不受 wrapper padding 影响导致的左对齐错位

### 涉及文件

| 文件 | 变更 |
|------|------|
| `frontend/src/views/recording/RecTranscriptPanel.vue` | 自动滚动逻辑内聚；jump 按钮移入 `.rec-scroll-wrap`；items 包裹 `.rec-transcript-item`；移除 `showJumpBtn` prop 和 `jumpLatest` emit |
| `frontend/src/views/RecordingView.vue` | 移除自动滚动相关代码（`showJumpBtn`/`scrollIfAtBottom`/`onTranscriptScroll`/`scheduleScrollCheck`） |
| `frontend/src/styles/recording-view.css` | 新增 `.rec-scroll-wrap`/`.rec-transcript-item` 规则；item-wrapper padding 改为垂直-only |

## [v2.x-virtual-scroll-size-estimate] - 2026-09-12

### 修复
- **DynamicScroller 转写行预估值改为动态计算**：原固定 80px 预估值在长文本（多行换行）场景下导致 `scrollToEnd()` 定位不准，最后一行内容被裁剪无法完整查看
  - 新增 `estimateLineHeight(idx)` 函数：根据文本长度、翻译显示模式、内联笔记等动态估算渲染高度
  - 文本换行估算基于气泡内宽 ≈ 360px、中文字宽 ≈ 13px（每行约 38 字符）
  - 双语/译文模式自动追加翻译行高度，笔记卡片自动追加卡片高度
  - ResizeObserver 实测后仍以实测值为准，预估值仅影响首帧布局与滚动定位

### 涉及文件

| 文件 | 变更 |
|------|------|
| `frontend/src/views/recording/RecTranscriptPanel.vue` | 新增 `estTextLines` / `estimateLineHeight`；`mixedItems` 改用动态预估 |

## [v2.x-insights-per-task-isolation] - 2026-09-12

### 新增
- **录音页转写原文虚拟滚动 + 时间轴导航**：解决长会议（2-3 小时）场景下转写原文 DOM 节点过多导致的渲染卡顿
  - 引入 `vue-virtual-scroller` 的 `DynamicScroller` 替代原有 `v-for` 全量渲染，仅渲染可视区域内的转写行
  - 新增 `RecTimeline.vue` 时间轴组件：Canvas 绘制说话人色带（按 10 秒分桶统计各说话人发言量，以颜色+高度可视化）、可拖拽滑块、章节刻度线、时间跳转输入框
  - 二分查找实现 O(log N) 时间→行索引定位，支持点击时间轴/输入时间快速跳转到指定位置
  - `RecordingView.vue` 预计算 `chapterStartMap`（章节起始映射），替代原有每行重复调用的 `getChapterStartInfo` 函数
  - 相关文档：[ADR-0018](docs/adr/0018-录音页虚拟滚动与时间轴导航.md)
- **AI 洞察消息按会议隔离 + 持久化**：洞察消息从属于各个独立的会议纪要，不同会议的洞察数据互不干扰
  - 后端新增 `GET/POST /api/insights/messages/{task_id}` 端点，消息持久化到 `data/tasks/{task_id}.insights.json`
  - 前端 `useAiInsights.ts` 消息存储从单一数组改为 `Record<taskId, InsightMessage[]>` 按会议分桶
  - 新增 `setCurrentTask(taskId)` 函数：切换会议时自动加载已有消息、重置引擎状态
  - 引擎停止时自动持久化当前会议的消息

### 涉及文件

| 文件 | 变更 |
|------|------|
| `app/routers/insights.py` | 新增消息持久化端点（GET/POST） |
| `frontend/src/api/insights.ts` | 新增 `loadInsightMessages` / `saveInsightMessages` |
| `frontend/src/composables/useAiInsights.ts` | 消息按 taskId 分桶；新增 `setCurrentTask` / `persistMessages`；引擎状态按会议重置 |
| `frontend/src/views/RecordingView.vue` | onMounted 中先 `setCurrentTask` 再 `startEngine` |
| `tests/test_smoke.py` | 新增 `TestInsightMessagesPersistence` 冒烟测试 |

## [v2.x-per-category-scan-interval] - 2026-09-12

### 新增
- **AI 洞察按类别自定义扫描频率**：三类洞察（上下文关联/盲点揭示/共识提炼）各自拥有独立的扫描频率配置，用户可在设置面板中为每个类别单独选择扫描间隔（1/2/3/5/10/15/30 分钟）
- 引擎改造：原全局 60 秒定时器对三类分析统一执行，改为每 60 秒基础轮询 + 各类别独立频率守卫（`scanIntervals` 配置项）
- 默认值：上下文关联 2 分钟、盲点揭示 5 分钟、共识提炼 10 分钟
- 设置 UI：每个开启的类别下方显示频率选择器（select 下拉）

### 涉及文件

| 文件 | 变更 |
|------|------|
| `frontend/src/composables/useAiInsights.ts` | 配置新增 `scanIntervals` 字段；引擎增加 `lastScanTimeByCategory` 追踪；`runAutoInsightCheck` 增加频率守卫 |
| `frontend/src/components/layout/ai/AiInsightsSettings.vue` | 类别行新增频率选择器 UI；新增 `scanIntervalChange` 事件 |
| `frontend/src/views/recording/RecInsightsPanel.vue` | 透传 `scanIntervalChange` 事件 |
| `frontend/src/views/RecordingView.vue` | 新增 `onInsightScanIntervalChange` 处理函数 |
| `frontend/src/styles/ai-panel.css` | 新增 `.ai-ps-scan-freq` / `.ai-ps-scan-freq-label` / `.ai-ps-scan-freq-select` 样式 |
| `frontend/src/i18n/locales/zh-CN/ai-panel.json` | 新增 `scan_interval` / `scan_interval_unit` |
| `frontend/src/i18n/locales/en/ai-panel.json` | 新增 `scan_interval` / `scan_interval_unit` |

## [v2.x-insight-categories-redesign] - 2026-09-12

### 变更
- **AI 洞察类别重构：从「错误检测」到「上下文赋能」**：洞察引擎从偏离检测单一视角重构为三类深度分析：
  - **上下文关联 (context)**：引入讨论之外的相关背景、历史决策、跨项目关联，帮助参会者看到更大图景
  - **盲点揭示 (blindspot)**：指出被忽视的利益相关者、未验证的假设、长期影响等局部认知之外的因素
  - **共识提炼 (consensus)**：从散乱讨论中萃取真正的共识点，定位分歧根源，推进有意义的共识
- 后端统一端点 `/api/insights/analyze` 替代原 `/api/insights/check-deviation`，支持 `analysis_type` 参数
- 前端类别从 6 个（偏离/矛盾/遗漏/待办/总结/卡壳）精简为 3 个（上下文/盲点/共识）
- 配置迁移：`deviationThreshold` → `insightThreshold`，旧配置自动迁移

### 涉及文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `core/insights.py` | 重写 | 三类分析 LLM 提示词 + 统一 `run_analysis()` 入口 |
| `app/routers/insights.py` | 重写 | `/api/insights/analyze` 统一端点 |
| `frontend/src/api/insights.ts` | 重写 | `runInsightAnalysis()` API 客户端 |
| `frontend/src/composables/useAiInsights.ts` | 重写 | 类别、引擎、手动分析、demo 数据全面更新 |
| `frontend/src/views/recording/RecInsightsPanel.vue` | 修改 | 下拉菜单更新为三类分析 |
| `frontend/src/components/layout/ai/AiInsightsSettings.vue` | 修改 | 类别标签 + 灵敏度滑块更新 |
| `frontend/src/views/RecordingView.vue` | 修改 | 引擎 API 名称更新 |
| `frontend/src/i18n/locales/zh-CN/ai-panel.json` | 修改 | 新类别文案 + demo 场景 |
| `frontend/src/i18n/locales/en/ai-panel.json` | 修改 | 新类别英文文案 |
| `tests/test_smoke.py` | 修改 | 端点测试更新为 `/api/insights/analyze` |

## [v2.x-license-change] - 2026-09-12

### 决策
- **开源许可证变更：MIT License → GNU AGPLv3**：项目开源许可证从 MIT License 变更为 GNU Affero General Public License v3（AGPLv3）。AGPLv3 的 copyleft 特性确保衍生作品同样开源，第 13 条（Remote Network Interaction）覆盖网络服务场景，与项目「开源、本地数据·云端智能、摆脱商业平台锁定」的使命高度一致。详见 [ADR-0016](docs/adr/0016-开源许可证变更为AGPLv3.md)。

## [v2.x-insights-engine] - 2026-09-12

### 新增
- **AI 洞察引擎实现**：为 `useAiInsights.ts` 接入真正的洞察引擎，消费原已定义但未使用的配置项：
  - **idle 计时器**：读取 `idleMinutes` 配置，新转写行到达时重置，超时后触发总结建议
  - **LLM 偏离检测**：新增后端端点 `/api/insights/check-deviation`，每 60 秒调用 LLM 判断最近讨论是否偏离章节主题，读取 `deviationThreshold` 配置
  - **冷却限流 + 会话上限**：`cooldownMinutes` 控制同类消息最小间隔，`sessionMax` 限制单次会议消息总数
  - **通知方式接入 UI**：`sidebarIndicator` 控制侧边栏指示器可见性，`breathing` 控制 AIPanel 折叠态呼吸灯，`banner` 控制录音页悬浮横幅，`autoExpand` 控制新消息自动切换到洞察面板
  - **录音结束待办提取**：`triggerMeetingEndTodos()` 已接入录音结束事件
  - **action 差异化处理**：洞察消息操作按钮根据 key 执行不同行为（调整→切回转写、生成/查看→切换到洞察）

### 涉及文件
- 新建：`core/insights.py`（偏离检测 LLM 调用逻辑）
- 新建：`app/routers/insights.py`（`/api/insights/check-deviation` 端点）
- 新建：`frontend/src/api/insights.ts`（前端 API 客户端）
- 修改：`frontend/src/composables/useAiInsights.ts`（核心引擎：idle/冷却/偏离/通知/生命周期）
- 修改：`frontend/src/views/RecordingView.vue`（引擎接入 + 横幅 UI + action 差异化）
- 修改：`frontend/src/components/layout/Sidebar.vue`（sidebarIndicator 配置门控）
- 修改：`frontend/src/components/layout/AIPanel.vue`（breathing 配置门控）
- 修改：`app/server.py`（注册 insights router）
- 修改：`zh-CN/ai-panel.json`、`en/ai-panel.json`（新增偏离检测文案）
- 修改：`tests/test_smoke.py`（新增偏离检测端点冒烟测试）

## [v2.x-admin-split] - 2026-09-12

### 变更
- **录音页「实时总结」Tab 重新定位为「AI 洞察」**：将原定时总结面板（倒计时环 + 频率设置 + 滚动摘要）完全移除，替换为 AI 洞察面板，承载原 AIPanel 中的主动 AI 消息流与配置能力。同时将全局术语从「主动 AI / proactive」统一更名为「AI 洞察 / insights」。章节总结功能已在转写原文中提供，定时总结不再需要。

### 涉及文件
- 重命名：`useAiProactive.ts` → `useAiInsights.ts`，`AiProactiveSettings.vue` → `AiInsightsSettings.vue`，`RecSummaryPanel.vue` → `RecInsightsPanel.vue`
- 修改：`RecordingView.vue`、`AIPanel.vue`、`AiChatPanel.vue`、`Sidebar.vue`、`SettingsView.vue`
- 修改：`ai-panel.css`、`recording-view.css`、`sidebar.css`、`speakers.css`、`meeting-view.css`
- 修改：`zh-CN/ai-panel.json`、`en/ai-panel.json`、`zh-CN/recording.json`、`en/recording.json`
- 清理：`api/record.ts` 移除 `pauseSummary` / `resumeSummary` / `stopSummary` / `setSummaryInterval`
- `app/routers/admin_config.py`：新增（远程配置路由域）
- `app/admin_server.py`：新增 admin_config router 注册
- `CHANGELOG.md`：本条目

## [v2.x-asr-proxy-split] - 2026-09-12

### 变更
- **asr-proxy/server.py 拆分重构（P2）**：原 641 行的 ASR 代理服务将 WebSocket 实时流式中继域独立为 `asr-proxy/ws_relay.py`（241行，云端 ASR SDK 回调 + PCM 帧中继 + 签名校验）。原文件保留为 448 行的批处理转写 + 配置 + 签名 + 健康检查 + router 注册。

### 涉及文件
- `asr-proxy/server.py`：641行 → 448行（批处理转写+配置+健康检查）
- `asr-proxy/ws_relay.py`：新增（WebSocket 流式中继域）
- `CHANGELOG.md`：本条目

## [v2.x-pipeline-runner-split] - 2026-09-12

### 变更
- **core/pipeline_runner.py 拆分重构（P2）**：原 655 行的管线编排模块将说话人数量估算域独立为 `core/speaker_count.py`（257行，采样+谱聚类 eigengap 启发式）。原文件保留为 418 行的管线编排层（stage1/stage2 后台执行 + 分层匹配 + 自动重试）+ re-export 兼容层。

### 涉及文件
- `core/pipeline_runner.py`：655行 → 418行（管线编排+兼容层）
- `core/speaker_count.py`：新增（说话人数量估算域）
- `CHANGELOG.md`：本条目

## [v2.x-audio-split] - 2026-09-12

### 变更
- **core/audio.py 拆分重构（P2）**：原 679 行的音频模块按职责拆分为音频处理与录制控制两层。音频归一化 + 时长查询保留在 `core/audio.py`（132行），录制控制独立为 `core/audio_recording.py`（567行，系统内录 + 流式录音 + 暂停/恢复 + 设备列表）。原文件保留为 re-export 兼容层。

### 涉及文件
- `core/audio.py`：679行 → 132行（归一化+时长+兼容层）
- `core/audio_recording.py`：新增（录制控制域）
- `CHANGELOG.md`：本条目

## [v2.x-diarization-split] - 2026-09-12

### 变更
- **core/diarization.py 拆分重构（P2）**：原 712 行的说话人分离模块按职责拆分为特征提取层与聚类引擎层。VAD + MFCC 特征提取保留在 `core/diarization.py`（225行），聚类引擎独立为 `core/diarization_cluster.py`（493行，SpeakerDiarizer 类 + 数据模型 + 工厂函数）。原文件保留为 re-export 兼容层。

### 涉及文件
- `core/diarization.py`：712行 → 225行（VAD+MFCC+兼容层）
- `core/diarization_cluster.py`：新增（聚类引擎）
- `CHANGELOG.md`：本条目

## [v2.x-cli-split] - 2026-09-12

### 变更
- **cli.py 拆分重构（P2）**：原 735 行的 CLI 入口按本地/远程职责拆分。本地命令（transcribe/normalize/upload/server/build/admin）保留在 `cli.py`（320行），远程 API 命令（record/tasks/speakers/hotwords/settings/chat）及 `_api_request` 工具函数独立为 `cli_remote.py`（440行），通过 `register_remote_commands(subparsers)` 注册 argparse 子命令。

### 涉及文件
- `cli.py`：735行 → 320行（本地命令 + main 入口）
- `cli_remote.py`：新增（远程 API 命令 + argparse 注册）
- `CHANGELOG.md`：本条目

## [v2.x-projects-split] - 2026-09-12

### 变更
- **core/projects.py 拆分重构（P2）**：原 794 行的项目管理模块按职责拆分为 CRUD+同步 与 索引+检索 两层。索引与检索域独立为 `core/project_index.py`（456行，文本提取+关键词+文件扫描+搜索+上下文构建）。原文件保留为 371 行的项目 CRUD + 文件夹同步 + re-export 兼容层。

### 涉及文件
- `core/projects.py`：794行 → 371行（CRUD+同步+兼容层）
- `core/project_index.py`：新增（索引+检索域）
- `CHANGELOG.md`：本条目

## [v2.x-voiceprint-split] - 2026-09-12

### 变更
- **core/voiceprint.py 拆分重构（P2）**：原 867 行的声纹模块按职责拆分为数据层与管线层。数据层独立为 `core/voiceprint_registry.py`（409行，常量+注册表+匹配算法），管线层独立为 `core/voiceprint_identify.py`（480行，自动识别+绑定注册+跨会议重建）。原文件保留为 52 行的 re-export 兼容层。

### 涉及文件
- `core/voiceprint.py`：867行 → 52行（兼容层）
- `core/voiceprint_registry.py`：新增
- `core/voiceprint_identify.py`：新增
- `tests/test_voiceprint.py`：monkeypatch 指向源模块 voiceprint_registry
- `CHANGELOG.md`：本条目

## [v2.x-test-split] - 2026-09-12

### 变更
- **tests/test_smoke.py 拆分重构（P2）**：原 1544 行的测试文件按功能域拆分为 5 个测试文件。test_smoke.py 保留基础可用性+任务+说话人+设置+热词+用户+录制+项目+笔记等核心域（319行）。新增：`tests/test_voiceprint.py`（声纹域，268行）、`tests/test_chat.py`（AI 对话域，395行）、`tests/test_text_bridge.py`（文本桥接匹配域，213行）、`tests/test_misc.py`（杂项域：SMS/认证/版本/用量/管理/配置/理念/错误分类/静默检测，440行）

### 涉及文件
- `tests/test_smoke.py`：1544行 → 319行
- `tests/test_voiceprint.py`：新增
- `tests/test_chat.py`：新增
- `tests/test_text_bridge.py`：新增
- `tests/test_misc.py`：新增
- `CHANGELOG.md`：本条目

## [v2.x-record-split] - 2026-09-12

### 变更
- **app/routers/record.py 拆分重构（P1）**：原 1128 行的录制路由按职责拆分。WebSocket 实时转写端点独立为 `app/routers/ws_transcript.py`（152行），静默检测协程与自动关停逻辑提取至 `core/silence_detection.py`（192行）。路由层保留为 ~757 行的端点编排层。

### 涉及文件
- `app/routers/record.py`：1128行 → 757行
- `app/routers/ws_transcript.py`：新增
- `core/silence_detection.py`：新增
- `app/server.py`：注册 ws_transcript router
- `CHANGELOG.md`：本条目

## [v2.x-chat-split] - 2026-09-12

### 变更
- **app/routers/chat.py 拆分重构（P1）**：原 1231 行的 AI 对话路由按职责拆分为 3 个 core 层子模块。路由层保留为 443 行的端点编排层。新增：`core/chat_actions.py`（动作检测与执行引擎，430行）、`core/chat_edits.py`（编辑意图 LLM 解析+执行+磁盘回读校验，205行）、`core/chat_context.py`（页面上下文构建+注入内容提取，175行）

### 涉及文件
- `app/routers/chat.py`：1231行 → 443行
- `core/chat_actions.py`：新增
- `core/chat_edits.py`：新增
- `core/chat_context.py`：新增
- `tests/test_smoke.py`：monkeypatch 同步 patch chat_edits 模块
- `CHANGELOG.md`：本条目

## [v2.x-recording-view-split] - 2026-09-12

### 变更
- **RecordingView.vue 拆分重构（P1）**：原 1337 行的录音页面拆分为 5 个子组件 + 2 个 composable。父组件保留为 456 行的布局编排层。新增子组件：`RecTranscriptPanel.vue`（转写原文+章节）、`RecSummaryPanel.vue`（实时总结+倒计时）、`RecNotesBar.vue`（随记输入栏）、`RecSpeakerBind.vue`（说话人绑定弹窗）、`RecControlBar.vue`（顶栏+项目关联）。新增 composable：`usePresenceDetection.ts`（存在性检测）、`useRecordingNotes.ts`（笔记持久化+自动关联）

### 涉及文件
- `frontend/src/views/RecordingView.vue`：1337行 → 456行
- `frontend/src/views/recording/RecTranscriptPanel.vue`：新增
- `frontend/src/views/recording/RecSummaryPanel.vue`：新增
- `frontend/src/views/recording/RecNotesBar.vue`：新增
- `frontend/src/views/recording/RecSpeakerBind.vue`：新增
- `frontend/src/views/recording/RecControlBar.vue`：新增
- `frontend/src/composables/usePresenceDetection.ts`：新增
- `frontend/src/composables/useRecordingNotes.ts`：新增
- `CHANGELOG.md`：本条目

## [v2.x-ai-panel-split] - 2026-09-12

### 变更
- **AIPanel.vue 拆分重构（P0）**：原 1445 行的前端最大组件按职责拆分为 5 个子组件 + 2 个 composable。父组件 `AIPanel.vue` 保留为 398 行的布局编排层。新增子组件：`AiChatPanel.vue`（对话 Tab + 输入区）、`AiAnalysisPanel.vue`（分析 Tab）、`AiContextPanel.vue`（上下文 Tab）、`AiSessionTabs.vue`（会话标签栏）、`AiProactiveSettings.vue`（主动 AI 设置面板）。新增 composable：`useAiContext.ts`（上下文数据）、`useAiCommandActions.ts`（指令操作回调）

### 涉及文件
- `frontend/src/components/layout/AIPanel.vue`：1445行 → 398行
- `frontend/src/components/layout/ai/AiChatPanel.vue`：新增
- `frontend/src/components/layout/ai/AiAnalysisPanel.vue`：新增
- `frontend/src/components/layout/ai/AiContextPanel.vue`：新增
- `frontend/src/components/layout/ai/AiSessionTabs.vue`：新增
- `frontend/src/components/layout/ai/AiProactiveSettings.vue`：新增
- `frontend/src/composables/useAiContext.ts`：新增
- `frontend/src/composables/useAiCommandActions.ts`：新增
- `CHANGELOG.md`：本条目

## [v2.x-store-split] - 2026-09-12

### 变更
- **app/store.py 拆分重构（P0）**：原 1272 行的“上帝模块”按职责拆分为 4 个子模块：`app/task_store.py`（任务持久化与恢复，335行）、`app/settings_store.py`（设置管理，262行）、`app/realtime_store.py`（实时消息推送状态，110行）、`core/pipeline_runner.py`（管线编排，654行）。原 `app/store.py` 保留为 111 行兼容入口，统一 re-export 所有符号，既有 `from app.store import X` 零修改。同步更新 `server.py`（event_loop 赋值指向 realtime_store）、`record.py`（event_loop 读取指向 realtime_store）、`test_smoke.py`（monkeypatch 指向源模块）

### 涉及文件
- `app/store.py`：1272行 → 111行（兼容 re-export 层）
- `app/task_store.py`：新增，任务持久化与恢复
- `app/settings_store.py`：新增，设置管理
- `app/realtime_store.py`：新增，实时状态与消息推送
- `core/pipeline_runner.py`：新增，管线编排与说话人估算
- `app/server.py`：startup 中 event_loop 赋值指向 realtime_store
- `app/routers/record.py`：event_loop 读取指向 realtime_store
- `tests/test_smoke.py`：monkeypatch 指向 task_store 源模块
- `CHANGELOG.md`：本条目

## [v2.x-mobile-webhook-design] - 2026-09-12

### 新增
- **移动端消息流设计方案**：基于 Webhook 的消息流移动端交互设计，用户通过自选消息应用（Telegram / Bark / ntfy 等）与本地服务双向通信。引入会话锚点模型解决多会议上下文问题，支持会议状态监控、随记、超时告警推送。详见 `docs/design/MOBILE_DESIGN.md`
- **ADR-0014**：移动端走 Webhook 消息流架构决策记录
- **ROADMAP v8**：移动端消息流版本条目

### 涉及文件
- `docs/design/MOBILE_DESIGN.md`：移动端消息流完整设计方案
- `docs/adr/0014-移动端走Webhook消息流.md`：架构决策记录
- `docs/adr/README.md`：ADR 索引更新
- `docs/ROADMAP.md`：新增 v8 条目
- `CHANGELOG.md`：本条目

## [v2.x-rec-auto-scroll] - 2026-09-11

### 修复
- **录音页原文区未随实时转写自动滚动**：`RecordingView.vue` 的自动滚动仅监听 `wsLines.length` 和 `wsPartial` 变化，未监听 `wsChapters.length` 变化。新章节出现时章节卡片与关键要点插入 DOM 改变内容高度，但滚动未被触发。同时 `nextTick()` 不足以等待浏览器完成布局计算，导致滚动位置计算不准确。另外，随记输入框自动增高时挤压上方 transcript body 的 `clientHeight`，但滚动检查未触发，导致内容满屏后底部出现空白。修复：抽取 `scheduleScrollCheck()` 统一使用 `nextTick() + requestAnimationFrame()` 双层延迟确保 DOM 渲染与布局均完成后再滚动；新增 `wsChapters.length` watcher 触发滚动检查；textarea 自动调整高度后也触发滚动检查。

### 涉及文件
- `frontend/src/views/RecordingView.vue`：自动滚动逻辑重构

## [v2.x-llm-progressive-loading] - 2026-09-11

### 新增
- **CODEX.md 功能流图**：新增「功能流图」节，以表格列出 11 个核心功能的前端调用链、后端端点和状态同步关键点（`loadTasks()` 调用标记 ✅/⚠️），LLM 遇到状态同步类 bug 时查表即可定位，预计节省 50-70% 搜索 token
- **CODEX.md 按任务类型加载细化**：从 8 项粗粒度目录级细化为 20 项精确到文件级，覆盖录音/首页/侧边栏/AI面板/纪要页/TopBar/设置/说话人/热词/项目/任务库/转写管线/实时ASR/Store/主题/登录等场景
- **`[状态同步]` 代码注释标签**：在 7 个前端文件的 17 处 `loadTasks()` 调用处添加 `[状态同步]` 注释，LLM 通过 `grep "[状态同步]"` 即可找到所有跨组件状态刷新点，对比一致性

### 涉及文件
- `CODEX.md`：功能流图表 + 按任务类型加载表细化
- `StartView.vue` / `AIPanel.vue` / `TopBar.vue` / `useAiChat.ts` / `GeneratingView.vue` / `RecordingView.vue` / `App.vue`：`[状态同步]` 注释

## [v2.x-page-context-awareness] - 2026-09-11

### 新增
- **AI 助手页面上下文感知**：AI 对话现在能感知用户当前所在页面（首页/录音/纪要/说话人/热词/设置/项目/会议库），根据页面注入差异化上下文数据，使回复更贴合用户当前操作场景。
  - 前端：`chat.ts` 新增 `current_page` 字段，`useAiChat.ts` 自动传入当前路由名
  - 前端：`AIPanel.vue` 上下文指示器显示当前页面名称（非会议页显示页面名，会议页显示会议标题）
  - 后端：`chat.py` 新增 `_build_page_context()` 函数，按页面注入差异化上下文（说话人列表、热词列表、设置摘要、项目列表、会议统计等）
  - 后端：系统提示词增加页面感知指引
  - i18n：新增 8 个页面名称翻译键（zh-CN + en）
  - 测试：新增 9 个冒烟测试覆盖页面上下文构建与端点兼容性

## [v2.x-chat-summary-fix] - 2026-09-11

### 修复
- **AI 对话回复错误：多人会议被误判为"内容过短"**：`generate_summary()` 用 `len(dialogue)` 判断对话是否过短，但 `dialogue` 是按说话人分组的列表（2 人 = 2 条目），不是按句子计数。导致 2 人会议无论内容多丰富都被误判为"仅 2 句，内容过短"，summary 字段存入错误信息，AI 对话时 LLM 看到错误信息后回复"无法生成有效结论"。
  - `core/summarize.py`：改为展开 `sentences` 字段统计真实句子数（`total_sentences`），仅当实际句子数 < 3 时才判定过短
  - `app/routers/chat.py`：增加兜底——若 summary 包含"内容过短"/"无法生成有效纪要"等错误信息，视为无纪要，回退到注入 dialogue 片段
- **AI 对话上下文缺失：待办事项未注入 + 对话片段过少**：chat 端点上下文注入逻辑缺少 `todos` 字段，且 summary 错误时回退的对话片段仅取前 5 条（约 1500 字符），LLM 因上下文不足无法正确回答结论/待办相关问题。
  - `app/routers/chat.py`：新增待办事项上下文注入（始终注入，含状态与责任人）；对话回退改为展开 `sentences` 字段注入全部对话（上限 3000 字符）
- **AI 回复中已有待办被误提为“新待办”建议注入**：待办注入上下文后，AI 回复中自然会引用已有待办内容，`_extract_injectable_items` 未做去重，导致前端显示“检测到 1 条待办 → 全部注入”的冗余提示。
  - `app/routers/chat.py`：新增 `_is_duplicate_todo()` 模糊去重（互相包含 + Jaccard 相似度 > 60%），调用时传入已有待办列表过滤

## [v2.x-silence-detection] - 2026-09-11

### 新增
- **录音静默检测与用户存在性感知**：解决用户离开后录音持续录制并生成原文造成资源浪费的问题。三层检测机制：
  - **第一层**：RMS 音量阈值判定静默（嘈杂环境下可能失效）
  - **第二层**：ASR 无定稿句子超时（5 分钟无语音活动）
  - **第三层**：基于软件状态的用户存在性评分模型（前端采集 visibilitychange/blur/focus/interaction 信号，衰减计分制，每 30 秒心跳上报）
  - **三阶段提醒**：温和横幅（120 秒倒计时）→ 紧急模态框（60 秒倒计时）→ 自动关停并保存
  - **心跳超时硬条件**：前端不可达（90 秒无心跳）直接自动关停
  - 详见设计文档 `docs/design/SILENCE_DETECTION.md`
  - 涉及文件：`app/store.py`（新增状态字典 + 配置函数）、`app/routers/record.py`（WebSocket 双向通信 + 静默监测协程 + 自动关停）、`frontend/src/composables/useWebSocket.ts`（心跳发送 + 消息处理）、`frontend/src/views/RecordingView.vue`（存在性信号采集 + 提醒 UI）、`data/settings.json`（配置项）

## [v2.x-recording-summary-linkage] - 2026-09-11

### 新增
- **录音暂停/恢复联动实时总结**：暂停录音时自动暂停实时总结（若总结正在运行），恢复录音时自动恢复因录音暂停而被暂停的总结。通过 `_paused_by_recording` 标记区分「用户手动暂停」和「录音联动暂停」，避免用户手动暂停总结后恢复录音时被意外恢复。前端 `summaryPaused` 状态改为由 WebSocket `summary_status` 消息驱动，确保后端自动暂停/恢复时 UI 同步更新
  - `core/realtime_summary.py`：`pause()` 增加 `source` 参数，新增 `auto_resume_for_recording()` 方法和 `is_paused_by_recording` 属性
  - `app/routers/record.py`：`pause_record()` 和 `resume_record()` 增加总结联动逻辑，返回 `summary_paused`/`summary_resumed` 状态供前端同步
  - `frontend/src/composables/useWebSocket.ts`：新增 `summaryPaused` ref，处理 `summary_status` WebSocket 消息
  - `frontend/src/composables/useRecorder.ts`：`pauseRecording()` 和 `resumeRecording()` 返回 API 响应数据
  - `frontend/src/views/RecordingView.vue`：`summaryPaused` 改为 computed，由 WebSocket 消息驱动；`onTogglePause()` 根据 API 返回值同步总结状态（解决 WebSocket 断开期间无法收到推送的问题）

## [v2.x-library-responsive-table] - 2026-09-11

### 修复
- **热词管理页布局坍缩导致内容不可见**：`HotwordsView` 根 `<div>` 缺少显式高度，导致内部 `.hw-layout` 的 `height: 100%` 解析为 0，页面内容无法渲染。修复：根元素添加 `height:100%; display:flex; flex-direction:column`，`.hw-layout` 改用 `flex:1; min-height:0` 填充剩余空间
- **会议库表格窄屏标题列过度压缩**：当浏览器窗口缩小时，`1fr` 标题列被固定宽度列挤压导致文本截断/换行。修复方案：
  - **最小宽度保障**：标题列从 `1fr` 改为 `minmax(180px, 1fr)`，确保核心信息基本可读
  - **渐进隐藏次要列**：增加 1000px 断点隐藏说话人列，768px 隐藏时长列，600px 隐藏时间列，每档同步收紧标题 min-width
  - **ResizeObserver 宽度档位**：新增 `is-compact`/`is-narrow`/`is-xnarrow` 组件级类，与项目现有模式一致，实现状态文字隐藏、行高收紧等精细适配

## [v2.x-smoke-test-expansion] - 2026-09-11

### 新增
- **冒烟测试覆盖扩展**：为 7 个未覆盖的 router 补充基础端点测试，测试类从 34 个增至 52 个（新增 27 个测试方法）。覆盖范围：
  - **auth 路由**（4 个）：GitHub OAuth 重定向、/auth/me 未登录 401、logout 正常返回、callback 缺 code 400
  - **chat 路由**（4 个）：空消息 400、缺 message 字段 422、GET /api/models 模型列表、POST /api/optimize 空文本 400
  - **update 路由**（2 个）：版本号查询、更新检查（含网络不可达静默降级）
  - **usage 路由**（3 个）：用量汇总、逐日明细、配额预检
  - **admin 路由**（5 个）：独立 admin_app 测试客户端 fixture、未配置密码 500、密码错误 401、未认证 401（me/overview）、logout 正常返回
  - **config 路由**（2 个）：公告列表、配置版本号
  - **philosophy 路由**（1 个）：随机理念返回
- **core/text_bridge.py 单元测试**（14 个测试方法）：覆盖 `_normalize_text`（空白去除）、`_text_similarity`（精确/模糊/空输入/长度比过滤）、`text_bridge_match`（空输入/无绑定/精确匹配/多人投票/无匹配/短文本过滤/to_dict 输出格式）
- **已知问题标注**：`TestVoiceprintRegisterFromBinding` 和 `TestVoiceprintMatchMargin` 两个已有测试因 v4 CAM++ 升级（256→192 维）后测试 mock 未同步而失败，非本次引入

### 修复
- **AI 动作检测关键词误命中**：`summarize_conclusions` 的关键词「结论」仅 2 字，导致用户说「生成会议纪要包含结论」时被误命中，只回显已有摘要而不触发真正的纪要生成。修复：移除「结论」短词，新增「总结关键决策」替代，保留「关键结论」「总结结论」「总结关键」等 4+ 字关键词；新增 4 个回归测试验证误命中已消除且正常触发不受影响

## [v2.x-eslint-compliance] - 2026-09-11

### 修复
- **前端 ESLint 合规性审计与修复**：运行 `npm run lint` 发现 11 个 `require-button-label` error + 63 个格式化 warning。修复所有 11 个图标按钮缺少文本定义的问题：
  - `ResponsiveButtonGroup.vue`：下拉菜单项按钮添加 `:title="btn.label"`
  - `AIPanel.vue`：会话标签按钮、上下文空状态 3 个操作按钮、发送按钮各添加 `:title`
  - `TopBar.vue`：主题选项按钮添加 `:title`，同时将循环变量从 `t` 重命名为 `theme` 消除 `vue/no-template-shadow` 警告
  - `GeneratingView.vue`：Tab 按钮、章节回顾卡片头部、待办链接按钮添加 `:title`
  - `StartView.vue`：最近会议项按钮添加 `:title`
- **i18n 补充**：zh-CN/en 的 `ai-panel.json` 新增 `send`、`session_default` 2 个 key
- **格式化自动修复**：`eslint --fix` 自动修复 63 个 `vue/html-indent`、`vue/first-attribute-linebreak`、`vue/html-closing-bracket-newline` warning
- **验证**：`npm run lint` 零 error 零 warning；`python cli.py build` 构建部署成功

## [v2.x-i18n-template-audit] - 2026-09-11

### 修复
- **前端模板硬编码中文审计与修复**：扫描全部 Vue 文件 `<template>` 区域，发现并修复 3 处未通过 `t()` 包裹的硬编码中文：
  - `DurationDial.vue`：aria-label 和时长文本（「0分钟」「X分钟」「X小时」）改绑 `t('common.duration.*')`
  - `PlayingEq.vue`：aria-label「播放中/播放暂停」改绑 `t('common.playing')` / `t('common.paused')`
  - `AIPanel.vue`：「AI 建议」标签改绑 `t('ai-panel.ai_suggestion')`
- **i18n 补充**：zh-CN/en 的 `common.json` 新增 5 个 key（`duration.zero/hours/aria_label`、`playing`、`paused`）；`ai-panel.json` 新增 1 个 key（`ai_suggestion`）
- **验证**：模板扫描硬编码中文 0 处；`npm run lint` 通过；`python cli.py build` 构建成功

## [v2.x-input-validation] - 2026-09-11

### 变更
- **后端 Router 输入校验加固**：为 3 个 router 的 Pydantic 模型添加 Field 约束，防止超大输入攻击：
  - `speakers.py`：`SpeakerCreate.name` 限制 1-100 字、`role` 100 字、`note` 500 字；`SpeakerUpdate` 同步限制
  - `hotwords.py`：新建 `HotwordsSaveRequest`/`HotwordMappingsSaveRequest` Pydantic 模型替代原始 `dict`，限制 50000 字符
  - `notes.py`：`NotesUpdate.notes` 限制 100000 字；`InjectRequest` 各字段限制（type 50/content 10000/source 10000）；`TodoCreateRequest`/`TodoUpdateRequest` 限制（text 500/assignee 100）
- **新增边界测试**（4 个）：说话人名称超长 422、空名称 400/422、热词正常保存、超大热词 422

## [v2.x-type-hints] - 2026-09-11

### 变更
- **core/ 类型标注补全**：审计全部 core/ 模块公开函数类型标注，补全关铯缺失：
  - `core/auth.py`：`cleanup_expired_states()` 添加 `-> None` 返回类型
  - `core/llm.py`：`chat_completion_stream()` 添加 `-> Generator[str, None, None]` 返回类型，`model` 参数从 `str = None` 修正为 `str | None = None`

## [v2.x-voiceprint-test-fix] - 2026-09-11

### 修复
- **声纹冒烟测试维度对齐**：v4 CAM++ 升级将声纹嵌入从 256 维改为 192 维，但测试 mock 数据未同步更新，导致 `TestVoiceprintRegisterFromBinding`、`TestVoiceprintMatchMargin`、`TestVoiceprintRebuildAcrossMeetings` 3 个测试类失败（mock 向量被 `match_voiceprint()` 的维度过滤丢弃）。修复：
  - `TestVoiceprintRegisterFromBinding`：mock 向量从 `np.zeros(256)` 改为 `np.zeros(192)`
  - `TestVoiceprintRebuildAcrossMeetings`：同上
  - `TestVoiceprintMatchMargin`：`_vec()` 从返回 2 维 `[cos, sin]` 改为 192 维（前 2 维旋转，其余为 0）
- **测试状态**：103 通过 / 0 失败（此前 2 个遗留失败已消除）

## [v2.x-error-audit] - 2026-09-11

### 审计
- **错误处理一致性审查**：审查全部 16 个 router 的 `HTTPException` 使用模式。发现 6 处轻微不一致（`str(e)` 直接传递而非 `_()` 包裹），均位于内部技术错误场景（`record.py` 的 RuntimeError、`admin.py` 的 ValueError），对用户不可见，无需立即修复。整体错误处理体系（`core/errors.py` 分类 + `_()` i18n + Pydantic 422）运作正常，无架构性问题

## [v2.x-speaker-zone-fix] - 2026-09-11

### 修复
- **已完成会议说话人视图不一致显示**：部分已完成会议的顶部说话人占比横条不显示。根因：`core/pipeline.py` 的 `run_pipeline_stage2` 在 `speaker_mapping` 为空时（如服务重启恢复 `awaiting_mapping` 任务、自动匹配无结果等场景），将 `speaker_mapping` 字段设为 `{}`，导致前端 `speakerStats` 计算属性返回空数组。修复：`run_pipeline_stage2` 的 `else` 分支改为从 dialogue 数据构建默认姓名映射（`说话人1`、`说话人2`...），确保所有已完成任务都有非空的 `speaker_mapping`；同时运行数据迁移脚本修复了 17 个历史任务

## [v2.x-ai-proactive-messaging] - 2026-09-11

**新增**：AI 主动发起会话功能原型与实现。

- **功能开关**：AI 面板头部右侧新增闪电图标 Toggle，控制「AI 主动提示」启用/停用，状态持久化到 localStorage，关闭时清除所有主动消息
- **折叠态诱导**：AI 面板折叠时，折叠条图标变为 proactive 紫色，右上角显示呼吸灯动画 + 未读计数角标，吸引用户点击展开
- **展开态横幅**：输入框上方滑入悬浮通知横幅（`bannerSlideUp` 0.35s 动画），展示最新 AI 洞察摘要，点击横幅滚动到对应消息，支持关闭
- **主动消息气泡**：专属视觉样式——紫色左边框 3px + 淡紫背景 + 「AI 主动提示」徽章（闪电图标）+ 操作按钮区（圆角药丸），与常规气泡形成三级视觉区分
- **预设场景**：场景 A = 会议结束自动提取待办（含查看详情/同步/稍后处理按钮）；场景 B = 长时间无操作建议生成总结
- **Design Tokens**：全部 7 个主题文件新增 `--proactive` / `--proactive-soft` / `--proactive-mid` 紫色系变量（夜色主题调整亮度）
- **i18n 全量支持**：所有 UI 文案（Toggle 标签、徽章、横幅、操作按钮、Toast、场景标题/正文）均通过 `t()` / `tt()` 绑定 i18n 键值，zh-CN 与 en 双语包同步新增 `proactive.*` 命名空间（含 22 个 key）；含 HTML 的翻译值拆为纯文本片段在 composable 中拼接，规避 intlify HTML 拒绝构建失败
- **新增文件**：`frontend/src/composables/useAiProactive.ts`（状态管理）、`docs/prototypes/ai-proactive-messaging.html`（交互原型）
- **侧边栏指示器**：底栏新增麦克风图标指示器（`.sb-proactive-indicator`），位于齿轮按钮左侧，显示未读计数角标 + 呼吸灯动画；后迁移入 `.sbp-bar` 单行布局内，消除独立元素的纵向空间占用；修复 `onProactiveClick()` 单向开关问题，改为双向 toggle（展开↔折叠），仅在展开时触发 `ai-scroll-to-unread` 事件；折叠态（52px）下分割线从 `.sb-bottom-panel` 下移至 `.sbp-bar`，指示器通过绝对定位浮于分割线上方居中显示，齿轮留在分割线下方

## [v2.x-sidebar-bottom-panel] - 2026-09-10

**重构**：侧边栏底部交互重新设计为向上展开式面板。

- **背景**：原用户下拉菜单中的设置入口依赖登录状态，违反「无需登录即可配置 API 密钥」的开源策略基准原则；且折叠态设置入口缺失
- **新设计**：移除 `.sb-user-wrap` + `.sb-mgmt-dropdown` 旧结构，替换为 `.sb-bottom-panel` 向上展开面板
- **触发按钮**：底部常驻齿轮图标按钮（Lucide `Settings`，`IconButton` 组件，`label="菜单"`），展开/折叠态均可见
- **面板内容**：账户区（登录/用户信息+登出）、管理区（项目/说话人/热词）、系统区（设置）——设置入口不再依赖登录状态
- **动画**：`scaleY` + `opacity` 过渡，`transform-origin: bottom center` 实现向上弹出效果
- **点击外部收起**：`document.click` 监听 `.sb-bottom-panel` 外部点击自动关闭
- **清理**：移除 `.sb-collapsed-icons` 中单独的设置齿轮图标；移除旧 `.sb-user-wrap`/`.sb-mgmt-dropdown` CSS 规则；新增 i18n 键 `menu_login`/`menu`
- **底栏合并**：版本号行（`.sb-version-bar`）与菜单触发按钮合并为单行 `.sbp-bar`（左版本号 + 右菜单图标），消除两行堆叠的冗余感；折叠态隐藏版本号，仅居中显示菜单图标
- **折叠态交互优化**：齿轮按钮点击时若侧边栏处于折叠态，先自动展开侧边栏（`nextTick` 确保 DOM 更新完成），再打开菜单面板，避免 52px 宽度下面板内容被压缩

## [v2.x-processing-status-fix] - 2026-09-10

### 修复
- **ProcessingView 管线步骤全显示"等待中"**：后端使用 `processing` 状态表示转写/纪要生成中，但 Vue 前端 `TaskStatus` 类型不包含该值，导致：①`ProcessingView` 的 `stepClass()`/`isStageDone()` 不认识 `processing`，所有管线步骤显示为"等待中"；②`statusText` 回退显示原始 message；③侧边栏/任务卡片状态标签缺失。修复：在 `TaskStatus` 类型和 `STATUS_CONFIG` 中添加 `processing`；`ProcessingView` 使用 `progress` 字段（≥70 转写完成，<70 转写中）正确渲染管线步骤；同步更新 `TaskList`/`TaskCard`/`TopBar`/`LibraryView`/`taskStore` 中的状态映射

## [v2.x-sidebar-remove-bottom-settings] - 2026-09-10

**清理**：移除侧边栏底部冗余的设置按钮（`.sb-bottom-section`）。

- **原因**：设置入口已存在于用户下拉菜单中（展开态），`.sb-bottom-section` 在折叠态独占一行仅放一个设置图标，冗余且浪费空间
- **改动**：移除 `Sidebar.vue` 中 `.sb-bottom-section` 模板块；清理 `sidebar.css` 和 `legacy-views.css` 中对应的 CSS 规则；将设置齿轮图标迁移至 `.sb-collapsed-icons`（折叠态图标条），确保折叠态下设置入口直达

## [v2.x-settings-api-form-restructure] - 2026-09-10

**修复**：设置页 API 配置区表单重构，修复前后端数据结构不匹配导致保存失效的问题。

- **根因**：前端 `Settings` 接口为扁平结构（`api_key`/`asr_model`/`llm_model`），后端期望嵌套结构（`llm.api_key`/`asr.model`），导致 3 个表单字段全部无法正确保存
- **前端接口重构**：`Settings` 改为嵌套结构 `{ asr: { model }, llm: { provider, base_url, api_key, model } }`
- **表单重构**：API 配置区拆分为「纪要生成服务」和「语音转写服务」两个子区块；LLM 新增 Provider 下拉（DashScope/OpenAI/DeepSeek/Moonshot/自定义）+ Base URL 字段；ASR 保留只读 Provider 展示 + Model 输入
- **Provider 联动**：选择 Provider 后自动填充对应 Base URL，海外用户可选「自定义」填入国际版地址
- **保存逻辑修复**：`onSave()` 改为发送嵌套结构 `{ asr: {...}, llm: {...} }`，与后端 `save_settings()` 期望格式对齐
- **i18n**：中英文语言包新增 8 个 key（`llm_service`/`llm_provider`/`llm_base_url`/`asr_service`/`asr_provider`/`asr_proxy_managed` 等）

## [v2.x-sidebar-narrow-btn-dash] - 2026-09-10

**优化**：侧边栏窄幅态头部按钮降级符号从省略号“…”改为短横线“一”。

- **改动**：`.sidebar.is-narrow .sb-text-btn::after` 的 `content` 从 `'\2026'`（…）改为 `'\4E00'`（一），图标始终保留，文字隐藏后以短横线表示截断
- **同步修改**：`legacy-views.css` 中同名规则同步更新，避免优先级冲突

## [v2.x-voiceprint-toggle] - 2026-09-10

**决策**：声纹自动识别（P1 CAM++ 匹配）默认关闭，改为实验性功能开关控制。

- **背景**：CAM++ 192 维声纹模型在真实会议场景下误匹配/漏匹配严重，自动匹配结果反而增加用户纠正成本
- **改动**：新增 `feature_flags.voiceprint_auto_match`（默认 `false`），控制 `app/store.py` 中 P1 声纹匹配阶段的执行
- **后端**：`get_feature_flags()` 新增字段；`run_pipeline_task()` 中 P1 声纹匹配前检查开关
- **前端**：设置页「功能开关」区新增「声纹自动识别」开关，标注「实验性」标签；`FeatureFlags` 接口同步更新
- **i18n**：中英文语言包新增 `voiceprint_auto_match` / `voiceprint_auto_match_desc` / `experimental` 文案
- **影响范围**：P0 文本桥接匹配、手动绑定流程、云端 ASR 说话人分离（L2）均不受影响；仅 P1 声纹身份识别（L3）被关闭

## [v2.x-sidebar-single-line-truncation] - 2026-09-10

**优化**：侧边栏会议条目统一单行省略号截断策略。

- **标题** `.sb-tl-title`：从 `-webkit-line-clamp: 2` 多行截断改为 `white-space: nowrap; text-overflow: ellipsis` 单行截断，所有宽度下统一生效
- **时间行** `.sb-tl-time`：添加 `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`，防止窄宽下换行
- **元信息行** `.sb-tl-meta`：flex 容器添加 `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`；子元素统一 `flex-shrink: 0; min-width: 0`；`.sb-tl-status` 添加独立截断规则

## [v2.x-sidebar-narrow-responsive] - 2026-09-10

**优化**：侧边栏拖拽缩窄（200px → 140px）时的会议列表窄幅自适应。

- **问题**：侧边栏拖拽至最小宽度 140px 时，会议标题区仅 60px 宽，13px 标题每行仅 4 个汉字，日期组计数与 chevron 争夺空间，元信息行换行混乱
- **修复**：新增 7 条 `.sidebar.is-narrow` 规则（由 ResizeObserver 在宽度 < 200px 时自动激活）：隐藏日期组计数、缩小标题/时间/元信息字号、减少右内边距、调整“更多”按钮位置
- **时间轴稳定性**：所有时间轴元素（竖线、节点、连接线）均为绝对定位，拖拽过程中位置固定无偏移

## [v2.x-sidebar-padding-fix] - 2026-09-10

**修复**：左侧边栏会议列表与浏览器窗口左边缘之间存在异常空白间距。

- **根因**：`.sb-history`（展开态 `padding-left: 44px`，为折叠态 logo 区留空）与 `.sb-timeline`（`padding-left: 56px`，时间轴布局）的左侧内边距**叠加**，导致会议列表内容距侧边栏左边缘合计 100px，在 200px 宽的侧边栏中内容区仅剩 ~92px
- **修复**：将 `.sb-timeline` 的 `padding-left` 从 `56px` 减至 `20px`（足以容纳时间轴节点溢出），同时将 `::before` 竖线 `left` 从 `38px` 修正为 `4px`——竖线为绝对定位不随 padding 自动偏移，需手动对齐节点中心（日期节点 `left: -22px` + 宽 12px → 中心 4px；会议节点 `left: -21px` + 宽 7px → 中心 2.5px）。修复后总左侧偏移 = 44 + 20 = 64px，内容区宽度 ~128px

## [v2.x-sidebar-click-outside-collapse] - 2026-09-10

**新增**：左侧边栏点击外部区域自动折叠。

- **交互逻辑**：侧边栏展开状态下，点击侧边栏 DOM 外部任意区域（主内容区、右侧 AI 面板、顶部导航栏等），侧边栏自动执行折叠收起
- **边界条件**：① 已折叠时忽略外部点击；② 分隔条拖拽中（`is-divider-dragging`）忽略；③ 点击侧边栏内部元素（列表项、筛选按钮、搜索框、折叠/展开按钮等）不触发；④ 拖拽分隔条拉手不触发
- **实现方式**：在 `Sidebar.vue` 的 `onMounted` 中注册 `document` 级 `click` 监听，通过 `sidebarRef.contains(target)` 判断点击是否在侧边栏外部，通过 `layout.sidebarCollapsed = true` 执行折叠

## [v2.x-llm-async-guard] - 2026-09-10

**修复**：同步 LLM 调用阻塞 asyncio 事件循环导致服务死机。

- **根因**：录音期间 `realtime_summary` / `realtime_chapters` 的定时器线程通过 `requests.post()` 同步调用 LLM，虽然不在事件循环线程，但 `requests` 持 GIL 做 SSL/JSON 运算与事件循环争抢；若任何代码路径从事件循环线程直接调用 `chat_completion()`，将完全阻塞事件循环导致服务无响应
- **修复①（事件循环守卫）**：`core/llm.py` 的 `chat_completion()` 新增安全守卫——检测若从事件循环线程调用，自动委托到线程池执行，防止阻塞。同时抽取 `_chat_completion_raw()` 作为无守卫的实际执行体，避免递归守卫
- **修复②（异步安全包装）**：新增 `async_chat_completion_safe()` 异步函数，内部用 `asyncio.to_thread` 将同步 LLM 调用委托到事件循环线程池；`realtime_summary` / `realtime_chapters` 的定时器回调改为通过 `asyncio.run_coroutine_threadsafe` 调度此包装，LLM 调用在事件循环线程池中执行（`requests` 持 GIL 但不阻塞事件循环本身）
- **修复③（兜底路径）**：定时器回调保留无事件循环时的兑底同步调用（不应发生，但确保健壮性）
- **影响范围**：`core/llm.py`、`core/realtime_summary.py`、`core/realtime_chapters.py`；管线后台线程（`summarize.py`/`chapters.py`）不受影响（仍在后台线程同步执行）

## [v2.x-i18n-render-fix] - 2026-09-10

**修复**：前端 i18n 全站渲染原始 key 的灾难性 Bug（语言包命名空间层级错误）——此前 `[v2.x-i18n-foundation]` 声称「前端 UI 文案已全量国际化」，但实际从未在浏览器验证渲染，界面上直接显示 `settings.title`、`common.skip_to_content` 这类原始 key 而非译文。

- **根因**：`frontend/src/i18n/index.ts` 合并各语言模块时用扁平展开 `{...zhCommon, ...zhSettings}`，但 15 个 JSON 文件内部不含模块名前缀（common.json 顶层是 `action`/`status`/`skip_to_content`），而组件全部调用带命名空间的 key（`t('common.skip_to_content')`、`t('settings.title')`）→ 所有 key 解析失败。合并后还产生跨模块 key 冲突（如多个模块都有 `title`）
- **修复**：合并时按模块名包裹命名空间——静态 `defaultMessages` 与动态 `loadLocaleMessages` 均改为 `{ common: zhCommon, settings: zhSettings, 'ai-panel': zhAiPanel, ... }`（`imports[i]` 对应 `LOCALE_MODULES[i]`）；`MessageSchema` 类型同步改为包裹结构
- **附带修复①（启动加载）**：`main.ts` 挂载前从未加载初始 locale 语言包，当 `detectLocale()` 返回 en（浏览器英文或 localStorage 持久化）时 en 语言包未加载 → 首屏回退到 zh-CN，造成「语言选择器高亮 English、界面却是中文」的不一致（刷新必现）。改为 `bootstrap()` 中先 `await loadLocaleMessages(getLocale())` 再挂载（含 try/catch 静默回退）
- **附带修复②（主题名）**：外观主题按钮（默认/夜色/暖阳…）用硬编码 `theme.label`，英文态不翻译；改为 `t('common.theme.' + theme.id)`（common.json 早有 `theme.*` 译文，id 与键名一一对应）
- **附带修复③（残留硬编码 tooltip）**：ResponsiveButtonGroup「更多」按钮、RecordingView 跳转/总结更多按钮的 `title`/`aria-label` 硬编码中文，改绑 `t('common.action.more')` / `t('recording.jump_latest')`
- **验证**：脚本全量比对——zh-CN/en 各 597 key、parity 完全一致，组件用到的 567 个静态 key 全部解析（缺失 0）；浏览器实测 en 刷新全英文、zh-CN 刷新全中文、语言 chip 高亮与界面语言一致、无原始 key 残留

## [v2.x-i18n-foundation] - 2026-09-10

**新增**：国际化（i18n）基础设施搭建，前后端均具备多语言适配能力。

- 前端：引入 `vue-i18n@^11.4.0` + `@intlify/unplugin-vue-i18n`；创建 `frontend/src/i18n/` 模块（实例创建、异步加载、语言切换）；按模块拆分 15 个语言文件（common/recording/start/processing/library/speakers/hotwords/settings/projects/sidebar/topbar/generating/task/login/ai-panel）；完成全部 9 个视图（Recording/Start/Processing/Library/Projects/Settings/Speakers/Hotwords/Generating）+ 全部布局与业务组件（Sidebar/TopBar/App/SelectionToolbar/TaskCard/TaskList/LoginModal/AIPanel）的中文文案提取与 `t()` 替换，前端 UI 文案已全量国际化（仅剩演示 mock 数据、代码注释与内部逻辑判别符未翻译）
- 已知修复：`@intlify/unplugin-vue-i18n` 消息编译器拒绝翻译串中的 HTML，故 LoginModal 页脚 `<br>` 拆为 `footer_line1`/`footer_line2` 两键、模板用 `<br>` 元素拼接（替代 v-html）；AIPanel `formatCount` 的「万」单位改为 locale 感知（仅中文用万，其他语言走 k）；`todos.filter` 箭头参数重命名为 `x` 避免遮蔽 i18n `t`
- 非组件 TS 文件国际化：`i18n/index.ts` 新增 `tt()`（走全局 composer，供 composables/stores 使用）；`useAiChat.ts`（7 处）与 `useHotwordGroups.ts`（7 处）的 toast/prompt/confirm 用户可见串改为 `tt()`；AI 自动分组产生的内部组名判别符（未分组/其他等）作为数据与去重键保留不译
- 后端：引入 `Babel>=2.14.0`；创建 `core/i18n/` 模块（`I18nMiddleware` 中间件 + `get_translator()` + `_()` 翻译函数）；`_()` 改为 ContextVar 驱动（参照 `core/users.py` 的 `set_request_user_id` 模式），中间件按请求写入 locale、深层调用栈（router `raise HTTPException`、`core/errors.py`）无需传 request 即可获得请求级语言；`app/server.py` 注册 i18n 中间件；创建 `babel.cfg` 翻译提取配置
- 后端 router 国际化：将 12 个 router（tasks/record/speakers/notes/projects/auth/user/voiceprint/settings/usage/admin/chat）的 105 条面向用户串改为英文 msgid + `_()`，覆盖 `HTTPException` detail、响应 `message`/`error` 字段（f-string 改 `_("...{x}").format(...)`）；WebSocket 处理器用 `set_current_locale(locale)` 使 WS 流程内 `_()` 生效
- 架构决策：**持久化的 `tasks[task_id]["message"]` 状态不做后端翻译**（避免把某请求者语言烤进磁盘数据，前端已有 `common.status.*` 通过 `getStatusLabel()` 渲染）；后台线程内推送的 WS 消息不翻译（ContextVar 不跨 `threading.Thread` 传播）；chat.py 的 AI 动作结果 message 与 prompt 字符串保留中文（属模型输入/工具输出而非纯 UI）；日志串保留中文
- 翻译工作流：新增 `scripts/gen_i18n_po.py`——`pybabel extract` 自动扫描 `_()` 生成 `messages.pot`（105 msgid），脚本按「英文→中文」映射表生成 `zh_CN.po`、en 用 identity 生成 `en.po`，再 `pybabel compile` 编译 `.mo`
- 翻译文件：`core/i18n/locales/zh_CN/`、`core/i18n/locales/en/`（.po + .mo，各 105 条）
- API 联动：`frontend/src/api/client.ts` 请求拦截器自动携带 `Accept-Language` 头；WebSocket 连接通过 `?locale=` 参数传递语言偏好；后端 WS 端点接受 locale 并使用翻译函数
- 语言切换 UI：设置页新增「语言」分区，支持简体中文/English 一键切换，持久化到 localStorage
- 文档：新增 [ADR-0013 国际化架构](docs/adr/0013-国际化i18n架构.md)（选型/msgid 策略/ContextVar 传递/翻译边界）；`docs/ARCHITECTURE.md` 补国际化模块；ADR 索引补 0012/0013

**修复**：随记时间戳显示为 `00:00` 的 Bug。录音阶段添加的笔记在纪要页全部显示为 `00:00`，根因是多层缺陷叠加：**核心**——`useWebSocket.ts` 的 `sentence` 处理器将后端 WS 正确发送的 `begin_time`/`end_time` 丢失（`rtStore` 有存但 `lines` 数组未存），导致所有实时到达的转写行无时间戳，`formatNoteTime` 始终回退到备用值；叠加——`onSendNote` 无 WS 行时回退到 `Date.now()`（Unix 纪元毫秒数而非录音经过时间）；`restoreNotesFromStorage` 从 localStorage 恢复笔记时硬编码 `lineIndex = -1`；`formatNoteTime` 访问 `wsLines[-1]` 返回 undefined 后直接返回 `'00:00'`。修复：`useWebSocket.ts` `sentence` 处理器补上 `begin_time`/`end_time`；`onSendNote` 改用 `recorder.elapsed.value * 1000`（录音经过毫秒数）；`formatNoteTime` 增加 `fallbackTimeMs` 参数 + `??` 替代 `||` 避免 `begin_time=0` 误判；`restoreNotesFromStorage` 增加旧数据清洗（`Date.now()` 值重置为 0）；`onStop` 调用时传递 `n.time` 作为备用值。

## [v2.x-duration-dial] - 2026-09-10

**修复**：录音页原文栏目内章节分隔卡片由纯文本标签升级为可展开卡片（与纪要生成页一致），新章节出现时自动展开，点击可手动展开/收起。

- `frontend/src/views/RecordingView.vue` — 新增 `recExpandedChapters` 响应式集合 + `watch(wsChapters.length)` 自动展开；`getChapterStart` 重命名为 `getChapterStartInfo` 返回章节索引；`toggleChapterExpand` 由空函数实现为实际切换逻辑；模板章节分隔由 `<span class="chapter-divider-label">` 升级为完整 `.chapter-divider` 卡片（含序号圆徽、标题、时间、箭头）
- `frontend/src/styles/legacy-views.css` — 移除废弃的 `.chapter-divider-label` 规则

**变更**：侧边栏会议列表的时长由纯文字改为「表盘 + 数字」双重编码（方案 A 落地）。实心圆 = 1 小时（多小时并排，上限 3 个），空心圆 + 扇形 = 不足 1 小时的余数分钟（按实际分钟连续绘制，从 12 点顺时针），所有圆盘右侧附等宽数字标注（`32分钟` / `2小时` / `1h20m`）。表盘服务扫视、数字服务精读，替代原「14:30 · 已完成 · 45分钟」中的纯文字时长段。

- `frontend/src/components/common/DurationDial.vue`（新增）— 表盘组件：props `seconds`，内部换算分钟；配色走 `--fg` / `--border` / `--subtle` token，适配全部主题；带 `aria-label`
- `frontend/src/components/task/TaskCard.vue` — `.sb-tl-meta` 行的时长 `<span>` 替换为 `DurationDial`（`sb-tl-dur` 类名保留在组件根上，`:has()` 分隔符联动不变）；悬停知识卡片仍用文字格式
- `frontend/src/styles/sidebar.css` — 移除被组件 scoped 样式取代的 `.sb-tl-dur` font-family 规则
- `docs/design/DESIGN_DECISIONS.md` §16 — 新增「会议时长 · 表盘化显示」编码规则、应用范围与禁止事项

## [v2.x-minutes-play-btn-spec] - 2026-09-10

**变更**：会议纪要页音频条播放按钮对齐录音页 `.btn-pause` 的「图标 + 动作文字」药丸范式。原为 28px 中性描边圆形纯图标按钮，改为 accent 填充药丸（`border-radius: 999px`，16px 图标 + `var(--fs-13)`/500 文字）；文字写**即将执行的动作**而非当前状态——播放中显示暂停图标 +「暂停」，已暂停显示播放图标 +「播放」，图标几何与录音页完全一致。`title` / `aria-label` 补为完整语义（「暂停播放」/「播放录音」）。控制条总高仅 44px（录音页约 64px），故高度按密度取 32px，形态与配色不变。

- `frontend/src/views/GeneratingView.vue` — `.gen-audio-play` 按钮内新增 `.gen-audio-play-text` 状态文字，`v-if/v-else` 图标沿用录音页 16px 几何，补 `title`；移除只服务旧圆形底座的 `gen-audio-ctrl` 类
- `frontend/src/styles/legacy-views.css` — `.gen-audio-play` 由圆形描边改为 accent 药丸并新增 `.gen-audio-play-text`；删除已无引用的 `.gen-audio-ctrl` 三条规则
- `docs/design/DESIGN_DECISIONS.md` §10.9 — 新增「状态切换按钮 · 文字写『即将执行的动作』」，把 `.btn-pause` 固化为跨页共享规范（含高度按控制条密度取值规则）

**已知边界**：药丸变宽 50px（28→78px）使 `.gen-control-zone` 自然内容宽度升到约 696px（进度条压到 `min-width` 后约 652px）。`.main` 的宽度档位类 `is-narrow` / `is-xnarrow`（会把音频条拆成独立整行并隐藏时间显示）在 Vue 版中**无任何 JS 驱动**，属休眠规则，因此主区宽度落在约 602–652px 区间时控制条会比改动前更早溢出。修复该档位机制是独立议题，本次未扩大范围。

## [v2.x-global-player-state] - 2026-09-10

**新增**：全局播放态。音频播放从纪要页组件内提升为 Pinia 全局单例（`stores/player.ts` 持有唯一 `HTMLAudioElement`），离开纪要页后播放继续不中断。播放中的会议在三处统一标识：会议库列表行、侧边栏时间线条目（`PlayingEq` 声纹 + 标题转 `--accent`），以及**非纪要页**顶栏的播放胶囊 `.player-pill`（借鉴录音中 `.rec-pill` 形态：声纹 + 标题 + 时间 + 可点击进度条 + 播放/暂停、倍速、打开纪要、停止）。播放任务变化时侧边栏自动展开所属分组并滚动定位到该条目（`scrollIntoView({ block: 'nearest' })`）。

**变更**：`GeneratingView.vue` 移除组件内 audio 元素与本地播放状态（`audioPlaying` / `audioSpeed` / `audioProgress` / `onTimeUpdate` / `stopAudio`），改由 player store 驱动；播放排他性改由 `load()` 内先 `release()` 旧元素结构性保证，取代「组件卸载即停止」方案。播放跟随（当前行高亮与滚动）改由 `watch(player.currentTime)` 驱动，行为不变。

- `frontend/src/stores/player.ts`（新增）— 全局播放器 store：`taskId` / `playing` / `currentTime` / `duration` / `speed` + 派生 `progress` / `timeStr`，方法 `load` / `toggle` / `seekToMs` / `seekPercent` / `cycleSpeed` / `stop` / `stopForTask`；播放中的任务被删除时自动释放
- `frontend/src/components/common/PlayingEq.vue`（新增）— 三竖条声纹指示器，暂停态动画冻结并降透明度（不消失，保留「可接着播」提示）
- `frontend/src/views/GeneratingView.vue` — 音频条改绑 player store（`player.timeStr` / `player.progress` / `cycleSpeed`）；删除本地 audio 元素与 `stopAudio`；`seekToTime(ms)` → `player.seekToMs(ms)`
- `frontend/src/views/LibraryView.vue` — 行 `:class="{ 'is-playing': player.taskId === task.task_id }"`，标题前插入 `PlayingEq`
- `frontend/src/components/task/TaskCard.vue` — 条目 `.is-playing` + 标题前 `PlayingEq`；向根元素透传 `data-task-id` 供定位查询
- `frontend/src/components/task/TaskList.vue` — `watch(() => player.taskId)`（含 `immediate`）自动展开折叠分组并定位滚动
- `frontend/src/components/layout/TopBar.vue` — 新增 `.player-pill`，显示条件 `player.taskId && route.name !== 'generating'`
- `frontend/src/styles/topbar.css` `sidebar.css` `legacy-views.css` — 胶囊样式、播放中标题色、顶栏溢出保护与 ≤640px（隐藏标题）/ ≤480px（隐藏进度与时间）降级
- `docs/design/DESIGN_DECISIONS.md` §15 — 记录播放态全局标识、顶栏胶囊作用域与侧边栏定位决策

## [v2.x-transcript-click-to-seek] - 2026-09-10

**新增**：会议纪要页原文行整行可点击跳转播放。点击转写行任意位置（文本气泡 / 行内空白 / 时间戳）即从该句 `begin_time` 开始播放，暂停态下点击同时启动播放；说话人区（说话人标签 / 定位按钮 / 绑定箭头）保持原有身份绑定与定位语义，点击不触发跳转。拖选原文时跳过跳转，避免划词工具栏刚弹出播放位置就被拽走。

- `frontend/src/views/GeneratingView.vue` — `.ts-line` 新增 `@click`，`.spk-wrapper` 与时间戳 `.ts` 加 `@click.stop` 阻断冒泡；原 `seekToTime` 改名 `seekFromTranscriptClick` 并加入选区保护（`window.getSelection()` 非空时不跳转），时间戳与整行共用同一入口
- `docs/design/DESIGN_DECISIONS.md` §13 — 记录原文行点击跳转播放与「划词优先」决策

## [v2.x-summary-without-binding] - 2026-09-10

**变更**：纪要生成不再等待说话人绑定确认。Stage 1 转写完成后若声纹/文本桥接未自动匹配，不再停留 `awaiting_mapping`，直接以空映射跑 Stage 2（纪要先以通用说话人标签生成）；服务重启时存量 `awaiting_mapping` 任务一并从 Stage 2 补跑。说话人绑定栏改为事后补充能力：存在未关联说话人时保留在纪要栏目上方（含原文可绑定标签），点击「确认关联」按真实身份重新生成纪要、全部关联后提示自然结束；「暂不关联」按任务级持久隐藏绑定栏。

- `app/store.py` — `run_pipeline_task` 移除无自动匹配时的 `awaiting_mapping` 停留分支，改为始终运行 `_run_stage2_for_task`；`recover_interrupted_tasks` 将 `awaiting_mapping` 纳入 Stage 2 恢复范围
- `frontend/src/views/GeneratingView.vue` — 绑定栏显示条件改为 `showBindingBar`（未关联数 > 0 且状态为 completed/awaiting_mapping 且未关闭）；原文标签可绑定态 / 定位按钮 / 箭头改由 `canBind` 控制；纪要面板移除「请先在上方绑定栏关联说话人身份」引导卡，统一为「纪要生成中」骨架屏；增量保存状态门槛放开到 completed；「暂不关联」改为持久隐藏且不再提交空映射；新增 watch 修复刷新时绑定映射初始化晚于 store 装载的竞态
- `docs/design/DESIGN_DECISIONS.md` §7 — 补充绑定栏显示时机决策

## [v2.x-minutes-breadcrumb] - 2026-09-10

**变更**：会议纪要顶部标题恢复为面包屑形式（1.0 形态回归）。已关联项目显示 `项目 / {项目名} / {会议标题}`，未关联显示 `会议库 / {会议标题}`；祖先层级可点击跳转（`/projects`、`/library`），末级会议标题不可点击、悬停显示全文；中间层级限宽截断，不再挤掉会议标题。层级由 `task.project_id` 派生，刷新与直达链接下保持一致。

- `frontend/src/views/GeneratingView.vue` — `.gen-breadcrumb` 由单一标题改为 `nav` 面包屑：新增 `breadcrumbTitle` / `breadcrumbs` computed，祖先层级渲染为 `button.gen-breadcrumb-item`（图标 + 标签），层级间 `/` 分隔
- `frontend/src/styles/legacy-views.css` — `.gen-breadcrumb-item` 增加 `max-width: 14em; overflow: hidden`，新增 `.gen-breadcrumb-label` 省略号截断
- `docs/design/DESIGN_DECISIONS.md` §14 — 记录顶部标题面包屑化决策

## [v2.x-login-back-affordance] - 2026-09-10

**新增**：登录页左上角可见返回按钮（`IconButton` + 「返回」文本 + `ESC` 键帽标识），点击关闭登录遮罩；键帽标识向用户明示 ESC 快捷键可完成同一返回操作，补齐全屏登录遮罩缺失的退出 affordance。

**修复**：ESC 关闭登录遮罩原实现直接改 DOM class（`useKeyboardShortcuts.ts`），与 `LoginModal` 的 `visible` 状态脱钩——组件重渲染（如短信验证码冷却倒计时 tick）会把 `is-hidden` 抹掉导致遮罩「复活」。改为派发 `oms:hide-login` 事件由 `LoginModal` 统一更新状态，DOM 与 Vue 状态保持单一事实源。

- `frontend/src/components/modals/LoginModal.vue` — 遮罩内新增 `.login-back-btn`（IconButton，label「返回（或按 ESC）」，label 插槽渲染「返回 + kbd ESC」）
- `frontend/src/styles/legacy-views.css` — 新增 `.login-overlay .login-back-btn` 定位与键帽样式（绝对定位左上角，配色跟随主题变量）；登录卡片宽度 360px → 420px，改善表单呼吸空间
- `frontend/src/composables/useKeyboardShortcuts.ts` — ESC 分支改派 `oms:hide-login` 事件
- `docs/design/DESIGN_DECISIONS.md` §12 — 记录登录页退出 affordance 决策

## [v2.x-library-header-and-btn-degradation] - 2026-09-09

**新增**：通用响应式按钮组组件 `ResponsiveButtonGroup`（`frontend/src/components/common/ResponsiveButtonGroup.vue`），实现三级降级策略：容器宽度足够时图标+文字同显；不足时降级为仅图标；再不足时仅保留首个图标按钮，其余收进「更多」弹出菜单（复用 `usePopMenu` 定位规范，菜单 `Teleport` 到 body 以规避祖先 transform/overflow 对 fixed 定位与层叠上下文的劫持）。首页「麦克风录音 / 上传音频文件」已切换为该组件。

**变更**：
- `LibraryView.vue` — 「全部会议」标题、会议计数与搜索框整合到同一行（`.lib-header-bar`），提升信息密度；≤768px 时降级为上下堆叠
- `Sidebar.vue` — `/library` 路由下隐藏侧边栏顶部「全部折叠 / 筛选」按钮与搜索行，搜索功能由 LibraryView 页面自身承载，避免双入口与窄幅侧边栏下的布局挤压

## [v2.x-topbar-rec-pill-scope] - 2026-09-09

**修复**：会议相关路由（`recording` / `processing` / `generating`）不再在顶栏叠加右上角录音中胶囊（`.rec-pill`），避免与页面自身头部/控制栏状态重复显示；左侧状态胶囊也不再以「转写中…」「已暂停」等录音态文字出现（录音页由视图头部与控制栏承载，非会议页由右上角 rec-pill 承载）。新建会议按钮的「返回录音」行为改为依赖 `hasRecordingTask`（是否存在录音中任务），与 rec-pill 是否在会议页面隐藏解耦。

- `frontend/src/components/layout/TopBar.vue` — 新增 `MEETING_ROUTES` 常量与 `showRecPill` / `showStatePill` 计算属性；`showTaskInfo` 复用常量；新建按钮 class/title/click/icon/text 全部切换为 `hasRecordingTask` 驱动；顶栏左侧 state-pill 加 `v-if="showStatePill"` 条件
- `docs/design/DESIGN_DECISIONS.md` §1 — 「顶栏遵循『标题、状态与视图』原则」补充：顶栏不放置功能入口，也不叠加录音中胶囊（录音态由页面自身或右上角 pill 承载）

**已知边界情况**：若后端存在孤儿录音会话（音频流仍在运行但对应 task 未落盘，常见于服务重启后实时资源丢失而音频 pipe 未完全释放），`is_stream_recording()` 返回 true 但 `tasks[]` 中无 recording/paused 条目，此时前端 `hasRecordingTask = false`，新建按钮不会显示「返回录音」。此属后端状态不一致问题，需另行修复（见下文根因分析）。

## [v2.x-sidebar-narrow-truncation] - 2026-09-09

**变更**：侧边栏拖拽至宽度 < 200px 时自动进入窄幅态（`.is-narrow`），任务列表标题从两行截断切换为单行省略号截断（`text-overflow: ellipsis`），时长信息自动隐藏，保持列表项高度一致、视觉节奏稳定。悬停卡片仍可查看完整标题。

- `frontend/src/components/layout/Sidebar.vue` — 新增 `sidebarRef` + `isNarrow` 响应式变量；`onMounted` 中通过 `ResizeObserver` 监听侧边栏宽度变化并动态切换 `is-narrow` 类；`onBeforeUnmount` 中清理 observer
- `frontend/src/styles/legacy-views.css` §2937–2939 — 已有 `.sidebar.is-narrow .sb-tl-title` 单行截断规则与 `.sb-tl-dur` 隐藏规则，本次接入 JS 驱动使其生效

## [v2.x-start-page-recent-all-statuses] - 2026-09-09

### 修复
- 修复 AI 对话启动录音后页面不自动跳转到录音页的问题：后端返回 `action`（单数）而前端读取 `actions`（复数）字段名不匹配，导致前端无法接收导航指令

### 变更
- 开始页底部「最近会议」移除 `status === 'completed'` 过滤，显示所有状态的会议，与侧边栏排序一致
- 非已完成会议显示状态标签（录音中/转写中/总结中等）替代时长
- 点击最近会议根据状态跳转至对应视图（录音/处理中/纪要）
- 修复 `watch` 未导入的 TS 编译错误

## [v2.x-onboarding-vue-port] - 2026-09-09

### 新增
- 说话人绑定引导弹窗移植到 Vue 组件（GeneratingView.vue），从原型 `speaker-binding-onboarding-v3.html` 移植：
  - **数据变化感知演示**：3 行迷你转写（2 条他人 + 1 条"我的"），骨架屏表示会话文本，说话人标签从灰色通用（虚线边框）循环动画切换为彩色实名
  - **循环动画**：1.5s 后触发 bound 状态，4s 后重置，1.5s 间隔，持续循环
  - **无障碍**：`role="dialog"` `aria-modal="true"` `aria-labelledby`，Escape 键关闭，`:focus-visible` 焦点环
  - **减少动效降级**：`prefers-reduced-motion: reduce` 时直接显示终态
  - **响应式**：`@media (max-width: 520px)` 自适应窄屏
  - **新增 CSS 变量**：`--radius-xl: 16px`（大型容器圆角）
  - **组件卸载清理**：`onUnmounted` 停止动画定时器，防止内存泄漏

## [v2.x-onboarding-polish] - 2026-09-09

### 修复
- 说话人绑定引导弹窗设计打磨（impeccable-design-polish），修复 12 项问题：
  - **P0-1** 底部按钮 2.6s 延迟入场 → 移除 `animation-delay`，按钮立即可见可点击
  - **P0-2** 无 `prefers-reduced-motion` 降级 → CSS 媒体查询禁用所有动画 + JS 端检测后直接显示终态
  - **P0-3** 弹窗缺少 ARIA → 添加 `role="dialog"` `aria-modal="true"` `aria-labelledby="dialogTitle"`
  - **P0-4** 骨架条对比度不足 → `background` 从 `--surface-3`（93%）升级为 `--border-strong`（82%）+ `opacity: 0.5`
  - **P0-5** 硬编码颜色 → 3 处 `rgba()` / 硬编码 `oklch()` 替换为 `oklch(0% 0 0 / alpha)` 或主题变量（`--ok`）
  - **P0-6** 无 `:focus-visible` → 按钮、复选框、演示按钮均添加 2px accent 焦点环
  - **P1-7** `text-transform: uppercase` 对中文无效 → 移除，`letter-spacing` 改为相对单位 `0.04em`
  - **P1-8** 按钮缺少 `type="button"` → 两处按钮补全
  - **P1-9** `scale(1.08)` 永久放大 → 改为 `transform: none`，仅用阴影 + 字重增强
  - **P1-10** 卡片固定 480px 无响应式 → 添加 `@media (max-width: 520px)` 自适应
  - **P1-11** 按钮 hover 装饰性 `translateY(-1px)` → 移除，仅保留背景色变化
  - **P1-12** 无 Escape 键关闭 → 添加 `keydown` 监听，Escape 移除弹窗
- **排版优化**：移除标题与演示区之间的"关联前/关联后"状态标签——动画本身（灰色虚线→彩色实名）已清晰传达状态变化，无需文字重复说明；演示区内边距从 `0 var(--s-6) var(--s-4)` 调整为 `var(--s-4) var(--s-6) var(--s-5)`，增加呼吸空间

## [v2.x-divider-visual-only] - 2026-09-09

### 变更
- 分隔条拖拽调宽功能移除：`.layout-divider` 改为纯视觉分隔缝（`pointer-events: none`，仅保留 `.divider-line` 子元素），删除 hover 高亮、grip 圆点与 tracking-dot / mode-badge / scroll-indicator / width-tooltip 等失效反馈元素；调宽与折叠统一由缝隙拉手双手势承担，`useDivider` 不再绑定分隔条 mousedown
- 修复左侧缝隙拉手被缝线「贯穿」的层叠问题：`.sidebar` 的 `contain: layout style` 会建立独立层叠上下文、困住拉手的 z-index，为 `.sidebar` 显式 `z-index: 11` 使拉手绘制在分隔缝之上
- `DESIGN_DECISIONS.md`（v2.6.0）：§9.5 改写为「缝隙拉手双手势标准（分隔缝纯视觉）」并新增层叠规则，§1、§3 同步更新

### 修复
- 清理阻塞构建的未使用绑定：`RecordingView.vue` 的 `wsConnected`（TS6133，noUnusedLocals）

## [v2.x-onboarding-skeleton-principle] - 2026-09-09

**变更**：说话人绑定引导弹窗原型（v3）的演示动效——非核心内容（会话文本）从动画第一帧即以骨架屏表示，全程不呈现真实文本。

- `docs/prototypes/speaker-binding-onboarding-v3.html` — 移除三处真实文本（`txt-content`），骨架条成为内容的固有表示；唯一动态变化为说话人标签「灰色通用 → 彩色实名」及「我的」行气泡显隐；修正 is-me 气泡边框（原 `border-color` 无边框宽度不生效）

**决策**：引导演示动效两条原则的补充澄清——
1. 骨架屏是内容在演示中的**表示方式**，从动画一开始就存在，而非先呈现内容再用工具事后虚化；
2. 配合既定原则（非核心内容用骨架屏退居背景 + 演示动效循环播放），适用于未来所有引导类演示动效。

## [v2.x-sidebar-latest-indicator] - 2026-09-09

**变更**：侧边栏会议列表第一条（最新会议）添加左侧 3px 强调色条，与开始页底部最近会议的标识方式统一。

- `TaskCard.vue` — 新增 `isLatest` prop，根元素添加 `is-latest` class
- `TaskList.vue` — 传递 `is-latest` 给 `groupedTasks[0].tasks[0]`
- `legacy-views.css` — 新增 `.sb-tl-item.is-latest` 样式（`border-left: 3px solid var(--accent)` + padding 补偿）
- `DESIGN_DECISIONS.md` — 第 11 节扩展为「最近会议标识 · 统一标准」，覆盖开始页和侧边栏两个位置

## [v2.x-button-label-enforcement-l2-l3] - 2026-09-09

### 新增
- **L2 全局 tooltip 兜底**：`base.css` 新增 `[data-tip]::after` 全局规则，为所有带 `data-tip` 的元素提供统一 CSS tooltip 样式，覆盖未迁移到 IconButton 的存量裸按钮
- **L3 ESLint 自定义规则**：`eslint-rules/require-button-label.js` 遍历 Vue 模板 AST，拦截无文本定义的图标按钮（无 `title`/`aria-label`/`data-tip` 且无可见文本的 `<button>`）；`eslint.config.js`（flat config）+ `typescript-eslint` 解析 Vue SFC
- `package.json` 新增 `lint` / `lint:fix` 脚本

### 决策
- 按钮文本定义不可变更原则从"文档约束"升级为"代码级强制执行"——三层防护：L1 组件编译报错 → L2 全局 CSS 兜底 → L3 ESLint CI 拦截
- 规则首次启用发现 12 处存量违规（AIPanel 5、Sidebar 1、TopBar 2、GeneratingView 3、StartView 1），后续迁移至 IconButton 组件

### 参考
- DESIGN_DECISIONS.md 第 10.8 节「三层防护机制」
- AGENTS.md 硬约束条款已同步更新

## [v2.x-seam-handle-dual-gesture] - 2026-09-09

### 新增
- 缝隙拉手**双手势**：点击（水平位移 ≤4px）= 折叠/展开，按住水平拖动 = 调整面板宽度；复用 `useDivider` 的 clamp（侧边栏 140–400 / 助手栏 240–600）与 `oms_sb_width` / `oms_ai_width` 持久化
- 左侧边栏新增缝隙拉手 `.sb-toggle`（骑右缝、垂直居中），与右侧 `.ai-toggle` 造型、手势、tooltip 规则完全一致

### 变更
- `useDivider.ts` 重构为模块级：导出 `beginResize(e, side, { onClick, resizable })` / `setSidebarWidth` / `setAiWidth`，分隔条与两侧拉手共用同一拖拽会话与 4px 点/拖阈值
- 移除侧边栏头部折叠 IconButton 与 `App.vue` 的 `.sb-float-expand` 浮动展开按钮（后者在 Vue 版因缺 `is-visible` 类始终不可见）；折叠态隐藏空头部 `.sb-header`，拉手成为唯一折叠/展开入口
- 清理 `legacy-views.css` 对应死规则（`.sb-sidebar-toggle`、`.sb-float-expand`、折叠态头部居中）

### 决策
- 缝隙拉手双手势统一标准：缝隙全高可拖无死区、折叠态只响应点击展开、拉手与分隔条共享宽度状态；方案经交互原型 `docs/design/ai-handle-resize-prototype.html` 三案对比后选定，见 DESIGN_DECISIONS 9.5

## [v2.x-binding-onboarding-v3-minimal] - 2026-09-09

### 变更
- 说话人绑定引导弹窗原型 v3 精简：移除标题下解释文本和底部变化摘要注释（"3 条转写已更新姓名""纪要将同步显示"），让视觉变化本身完成用户感知教育，符合软件「极少内容」规范

## [v2.x-binding-onboarding-skeleton-loop] - 2026-09-09

### 变更
- 说话人绑定引导弹窗原型 v3 虚化方式升级：关联后状态的会话文本从 CSS blur 改为骨架屏（灰色圆角条），与截图中的设计语言一致，更干净、更有设计意图
- 演示动效改为循环播放（4s 一轮 + 1.5s 间隔），不再是一次性播放
- **确立设计原则**：未来所有引导/演示动效遵循两条规范——① 非核心内容用骨架屏退居背景（灰色圆角条，非 blur）；② 演示动效循环播放

## [v2.x-binding-onboarding-v3-refine] - 2026-09-09

### 变更
- 说话人绑定引导弹窗原型 v3 优化：标题区添加 `--surface-2` 背景色 + 底部分隔线，与内容区形成明确视觉分区；关联后状态的会话文本添加 `blur(2.5px)` + `opacity: 0.45` 虚化处理，说话人名称标签增强（`scale(1.08)` + 阴影 + 加粗），让数据变化的核心信息（姓名映射）成为唯一视觉焦点

## [v2.x-ai-panel-handle] - 2026-09-09

### 修复
- AI 助手栏折叠/展开按钮箭头方向与用户操作预期相反：展开态显示 `‹`、折叠态显示 `›`（箭头表示的是「当前状态」而非「动作方向」）

### 变更
- 折叠/展开控件由「面板左缘顶部 26px 圆形按钮」改为**缝隙居中胶囊拉手**：18×56px、圆角 9px、半嵌在面板与主内容缝隙（`left: -9px`）、面板区域垂直居中；折叠态停在 44px 折叠条左缝，不再被误读为「返回」按钮
- 箭头语义统一为**动作方向**：展开态显示 `›`（点击向右收起面板）、折叠态显示 `‹`（点击向左展开面板）；基础字形改为右箭头，折叠态沿用既有 CSS rotate(180°) 翻转
- 拉手补充随状态切换的 `title` / `aria-label`（收起助手 ↔ 展开助手）与 `aria-expanded`
- `ai-panel.css` 与 `legacy-views.css` 两处重复的 `.ai-toggle` 规则同步更新

### 决策
- 面板局部控件留在该面板边缘（缝隙拉手），不上顶栏；折叠/展开控件箭头恒指动作方向，见 DESIGN_DECISIONS 第 9 节

## [v2.x-start-page-recent-meetings] - 2026-09-09

### 变更
- 开始页最近会议列表从 5 条缩减为 **3 条**，降低信息密度，让"新建会议"按钮回归视觉主导
- 最新会议（第一条）增加左侧 **3px 强调色条**（`--accent`），作为唯一区分手段
- 会议卡片图标从**音符**（♪）替换为**文档图标**（折角 + 文字行），语义更贴近"会议纪要"
- "查看全部"按钮阈值从 `> 5` 调整为 `> 3`

### 决策
- 不使用麦克风图标——已用于「麦克风录音」按钮，避免语义冲突
- 不使用放大/加粗/标签区分最新会议——仅用左侧色条，保持等权排列的克制感

## [v2.x-onboarding-data-perception] - 2026-09-09

### 变更
- 说话人绑定引导弹窗 v3 原型（`docs/prototypes/speaker-binding-onboarding-v3.html`）
- 设计方向调整：从「操作流程说明」改为「数据变化感知」——让用户直观看到绑定操作对页面数据的实际影响
- **纵向空间优化**：将"关联前"和"关联后"两个独立转写块合并为单一容器，用 JS 动画在 1.5 秒后自动切换状态，弹窗高度减半
- 移除 v2 的三步骤卡片（点击/选择/确认），改为**关联前/关联后**的转写数据对比
- 关联前：灰色虚线边框的通用标签（说话人 1/说话人 2）+ 无气泡的裸文本
- 关联后：彩色实底实名标签（说话人 A/说话人 B）+ 气泡化文本 + "我的"行右对齐绿色气泡
- 转换箭头动画（1.2s 延迟淡入）分隔前后两态
- 底部变化摘要条（2.4s 延迟入场）：「3 条转写已更新姓名」「纪要将同步显示」
- 按钮文案从「我知道了」改为「开始关联」——引导用户立即操作

## [v2.x-onboarding-graphical] - 2026-09-09

### 新增
- 说话人绑定引导弹窗 v2 原型（`docs/prototypes/speaker-binding-onboarding-v2.html`）
- 设计方向：图形化 + 动效替代纯文字说明，保留上/中/下三区布局
- 顶部视觉区：「说话人 1 → 张三」流程图增加入场动画（标签滑入、箭头绘制、人物标签弹出）+ 背景光晕脉冲
- 中部演示区：3 个文字步骤改为图形化迷你卡片，每张带专属图标动画（点击涟漪、列表弹跳、勾选绘制）
- 底部操作区：保持不变（不再显示复选框 + 我知道了按钮）
- 弹窗整体入场：上移 + 缩放弹性动画
- 步骤卡片依次延迟入场（0.7s / 1.0s / 1.3s），引导视线从上到下

## [v2.x-frame-grid-fix] - 2026-09-09

### 修复
- 底部状态栏异常膨胀（占据近半视口、文字悬在页面中部），主体区被压缩成内容高度
- 根因：`.frame` 网格 `grid-template-rows: auto auto 1fr 28px` 硬编码 4 行，但首个子元素（系统公告横幅）是 `v-if` 条件渲染；公告被永久关闭后 DOM 只剩 3 个子元素，错位落轨——主体落入 auto 行（内容高度 370px），底部栏落入 1fr 行（约 872px）。截图中可见的横幅实为 TopBar 内置注册引导横幅（sessionStorage 独立记录关闭状态），两横幅关闭状态不同步暴露了此缺陷
- 修复：App.vue 公告横幅改为常驻渲染（复用 `is-hidden` 折叠机制，与 TopBar 横幅同模式），内层内容区保持 `v-if="annMessage"` 防空引用；`.frame` 子元素数量恒为 4，网格落轨稳定
- 清理 `legacy-views.css` 中过时的 3 行 `.frame` 重复规则（与 layout.css 形成双事实源），`layout.css` 成为唯一定义来源
- `.reg-guidance-banner.is-hidden` 补 `border-bottom: none`，折叠态不再残留 1px 边线

## [v2.x-transcript-toggle-scope] - 2026-09-09

### 修复
- 纪要页「转写原文」开关隐藏范围过大：关闭时连 AI 生成的章节卡片（标题/摘要/要点）一并隐藏，转写区只剩章节导航条
- 根因：`v-show="showTranscriptLines"` 加在整个 `.gen-transcript-list` 容器上，章节分隔卡片与原文行同属该容器
- 修复：`v-show` 下移到 `.ts-line` 转写行元素，开关只作用于原文会话；章节卡片恒可见（与录音页 RecordingView 的既有行为对齐）
- 开关图标语义此前与状态相反（显示中却渲染带斜杠的 eye-off），已按状态修正
- 涉及文件：`GeneratingView.vue`、`legacy-views.css`

### 变更
- 「转写原文」开关归属「转写」Tab：加 `v-if="activeTab === 'transcript'"`，纪要/笔记/待办 Tab 不再出现该按钮（音频播放条属跨 Tab 控件，保持常驻）
- 开关文案由静态名词「转写原文」改为随状态切换的动词「隐藏原文」/「显示原文」，图标改为 Lucide `eye` / `eye-off`，`title` 说明隐藏后仍保留章节与要点
- 隐藏原文后在转写区就地显示提示条 `.gen-hidden-indicator`：「已隐藏 N 条转写原文，当前仅显示章节与要点」+「显示原文」快捷按钮，视觉与录音页 `.rec-hidden-indicator` 统一（CSS 选择器共用）

### 决策
- 控件作用域必须等于其影响范围；隐藏类开关必须自解释（动词文案 + 状态图标 + 就地恢复提示条）——见 `docs/design/DESIGN_DECISIONS.md` 第 9 节

## [v2.x-popmenu-standard] - 2026-09-09

### 新增
- `frontend/src/composables/usePopMenu.ts` — 弹出菜单统一封装：智能定位（底部不足向上翻转、左右溢出回缩、8px 视口边距）、点击空白关闭、Esc 关闭、滚动/缩放自动重定位
- z-index 分层 token（`legacy-views.css :root`）：`--z-topbar: 100` / `--z-popover: 500` / `--z-modal: 1000` / `--z-toast: 1100`

### 变更
- `RecordingView.vue` 两个更多菜单、`GeneratingView.vue` 更多菜单全部迁移到 `usePopMenu`，删除三份重复的手写定位代码
- 修复两个视图更多菜单此前均缺少「点击空白处关闭」的缺陷（全局点击监听只覆盖了绑定气泡）
- 全部弹出层 `z-index` 迁移到分层 token：更多菜单/下拉/悬浮卡片/绑定气泡/选择操作条等 30+ 处（原 9999/200/100/60 等任意值），模态/遮罩统一 `--z-modal`，toast 统一 `--z-toast`
- 更多触发按钮补充 `aria-haspopup="menu"` 与明确 `aria-label`
- `DESIGN_DECISIONS.md` 第 8 节重写为「弹出菜单（PopMenu）统一标准」：行为四原则、图层阶梯、代码用法、禁止事项

### 决策
- 今后任何"点按钮弹小面板"一律复用 `usePopMenu`，禁止手写 `position: fixed` 定位与关闭逻辑，禁止自造 z-index 数值（见 DESIGN_DECISIONS 8.4）

## [v2.x-ann-banner-theme-adapt] - 2026-09-09
- **修复**：顶部公告栏（`reg-guidance-banner`）在暗色主题下使用硬编码浅绿色 OKLch 值，与深色背景严重冲突
- **变更**：将公告栏全部 7 处硬编码颜色替换为 CSS 变量（`--ann-bg`/`--ann-border`/`--ann-icon`/`--ann-cta-bg`/`--ann-cta-fg`/`--ann-text-strong`/`--ann-dismiss-hover`），fallback 到主题通用变量（`--surface-2`/`--border`/`--accent`/`--accent-fg`/`--fg`/`--surface-3`）
- **设计规范**：公告栏不定义独立色相，完全从主题变量派生，自动适配所有 7 个主题（default/dark/forest/rose/ocean/lavender/warm）
- **文件**：`frontend/src/styles/topbar.css`、`frontend/src/styles/legacy-views.css`

## [v2.x-rec-pause-toggle-fix] - 2026-09-09

### 修复
- 录音页底部播放/暂停按钮点击无切换效果，界面恒显示「已暂停 + 播放图标」，波形动画也恒为暂停态
- 根因：模板中 `recorder.isPaused` 拿到的是 ref 对象本身（普通对象内嵌套的 ref 在模板中不会解包），恒为真；脚本侧读 `.value` 正常，故状态机正确但渲染不跟随
- 修复：`isPaused` 提升为顶层绑定 `recPaused` 供模板使用；顺带修复永不触发的 `watch(() => recorder.isPaused)`（getter 每次返回同一 ref 对象）改为 `watch(recPaused)`
- 涉及文件：`RecordingView.vue`

## [v2.x-recording-menu-cleanup] - 2026-09-09

**变更**
- 录音页底部更多菜单：移除与实时总结面板重复的「总结刷新频率」和「暂停/恢复总结」，仅保留「放弃录音」——就近原则，总结相关操作统一收归实时总结面板右侧更多菜单

## [v2.x-dropdown-smart-position] - 2026-09-09

### 修复
- 底部更多按钮弹出菜单溢出屏幕底部（如"总结刷新频率"菜单被截断）
- 根因：下拉菜单使用 `position: fixed` 但无智能定位逻辑，始终向下弹出
- 修复：新增 `positionDropdown` / `toggleGenMoreMenu` 函数，检测底部空间不足时向上翻转弹出，右侧溢出时左对齐
- 二次修复：`nextTick` 在 dropdown 从 `display:none` → `display:block` 时无法保证浏览器完成布局，`offsetHeight` 返回 0 导致定位失效；改用 `requestAnimationFrame` 确保布局完成后再测量尺寸
- 涉及文件：`RecordingView.vue`、`GeneratingView.vue`

## [v2.x-banner-layout-overflow] - 2026-09-09

### 修复
- 顶部系统消息横幅导致画面向底部溢出，录音纪要页面底部更多按钮弹出菜单显示不完整
- 根因：`reg-guidance-banner` 在 `.frame`（100vh grid）外部，不参与高度计算；`.gen-view` / `.rec-main` 使用硬编码 `calc(100vh - ...)` 无法适应动态横幅
- 修复：将横幅移入 `.frame` grid（新增 auto 行），子视图改用 `height: 100%` 继承可用空间
- 涉及文件：`App.vue`、`layout.css`、`legacy-views.css`

## [v2.x-speaker-display-unify] - 2026-09-09

### 变更
- 说话人显示统一标准：**字体颜色区分** + **横条占比图形**替代数字百分比，移除所有彩色圆点
- 涉及文件：`GeneratingView.vue`、`RecordingView.vue`、`SpeakersView.vue`、`legacy-views.css`
- 设计规范：`docs/design/DESIGN_DECISIONS.md` 新增第 7 节「说话人显示统一标准」

## [v2.x-design-docs-refactor] - 2026-09-09

### 变更
- `docs/design/ui-spec.md` 废弃，拆分为 `docs/design/DESIGN_DECISIONS.md`（设计决策与原则）；组件实现以 Vue 源码为准，不再维护平行的 Markdown 清单
- 同步更新 `AGENTS.md`、`CODEX.md`、`docs/README.md`、`README.md` 中的引用

## [v2.x-pause-transcript-fix] - 2026-09-09

**修复**：录音页暂停功能失效——暂停后实时转写仍在继续

- 根因：`onTogglePause` 先调 API 再断 WebSocket，API 慢时 WebSocket 仍接收数据
- 修复：暂停时先断 WebSocket 再调 API；新增 `watch(isPaused)` 确保状态同步
- 文件：`RecordingView.vue`

## [v2.x-neutral-hub-strategy] - 2026-09-09

### 决策
- **确立「跨平台中立枢纽闭环」产品战略**：厘清会议软件生态与转录生态的三处接缝（会前上下文 / 会中采集 / 会后回流），明确闭环方向不是接入平台开放 API 做深度集成（违背「反生态锁定」使命、自降为附庸），而是做中立枢纽——上游靠「项目」机制补上下文、会中靠主动型 AI 基于音频流越界、下游多路回流协作生态。

### 变更
- **文档同步**：`docs/PRD.md` 新增「生态闭环：做跨平台的中立枢纽」章节；`docs/ROADMAP.md` 想法池新增战略条目并关联下游回流；`MISSION.md` 强化「生态锁定」痛点目标与「开放自由」设计原则表述。

## [v2.x-font-size-unify] - 2026-09-09

### 修复
- **录音页转写文本字体大小与纪要页不一致**：录音页 `.rec-line-text` 使用 `var(--fs-14)` (14px)，而纪要页 `.ts-line` 使用 `var(--fs-13)` (13px)。统一为 `var(--fs-13)` (13px)，与侧边栏标题、说话人标签等保持一致。同步更新原型。

## [v2.x-recording-jump-btn] - 2026-09-09

### 修复
- **录音页"回到底部"按钮不显示**（两处叠加）：
  1. `showJumpBtn` 只在新内容到达时（`wsLines.length` / `wsPartial` 变化）才更新，用户手动上滑时没有滚动监听器。新增 `transcriptBody` 的 `scroll` 事件监听，实时根据滚动位置切换按钮显隐；`onUnmounted` 时移除监听器。
  2. 模板用 `v-show` 控制显隐，但 CSS 里按钮默认 `opacity: 0; pointer-events: none`，需 `.is-visible` 类才可见——而模板从未绑定该类，按钮即使移出 `display:none` 仍然透明不可点。改为 `:class="{ 'is-visible': showJumpBtn }"` 驱动，保留淡入过渡动画。

## [v2.x-recording-autoscroll] - 2026-09-09

### 修复
- **录音页实时转写不自动滚动**：自动滚动 watcher 只监听 `wsLines.length`（新行定稿时触发），但 partial 文本更新（正在说的句子）不改变数组长度，页面不跟随滚动。新增 `wsPartial` watcher + 抽取 `scrollIfAtBottom()` 公共函数，partial 更新时也触发滚动。

## [v2.x-prototype-purification] - 2026-09-09

### 变更
- **转写页面原型净化**（Creative Director 诊断后执行）：
  - 删除原型标注条（`.proto-banner`）——开发脚手架不进入设计评审
  - 移除说话人标签的 `translate()` 偏移调试残留——标签自然排列
  - 移除章节导航条（`.chapter-overview`）——与章节分隔卡片功能重叠
  - 删除 3 处演示分隔线和 `demo-label` 标注
  - 移除筛选模式演示区（聚焦横幅 + 淡化行 + 定位行）——聚焦到单一连贯状态
  - 绑定下拉框从固定坐标改为 JS 锚定到「说话人4」转写行下方
  - 转写行间距增加：gap 2px → 8px，padding 8px 12px → 12px 12px
  - 气泡内边距增加：8px 12px → 10px 14px
  - 清理对应 CSS：`.proto-banner`、`.demo-label`、`.chapter-overview` 等约 40 行无用样式
- **同步**：净化后原型同步至代码仓库 `docs/prototypes/transcript-page-v2.html`

## [v2.x-ai-panel-recording-fix] - 2026-09-09

### 修复
- **录音页 AI 面板"插入笔记/纪要"报错**：`RecordingView` 未注册 `useQuoteRef` 的回调函数，导致点击 AI 面板的"插入笔记"或"插入纪要"按钮时 toast 报错"请先打开一个会议的笔记页面"。新增 `registerNotesAppender` 和 `registerSummaryAppender` 注册，将 AI 内容追加到笔记输入框

## [v2.x-prototype-border-sync] - 2026-09-09

### 修复
- **原型气泡边框不可见**（Vue 部署版修复后原型未同步）：`transcript-page-v2-prototype.html` 他人行气泡边框从 `--border`（92% 亮度）升级为 `--border-strong`（86% 亮度）；「我的」行气泡从 `--mine-bg` / `--mine-border`（91% 浅绿边框，近乎隐形）改为 `--mine-soft` / `--mine`，与 Vue 部署版完全一致
- **清理**：移除原型中不再使用的 `--mine-bg` / `--mine-border` token 定义
- **同步**：原型修复同步至代码仓库 `docs/prototypes/transcript-page-v2.html`

## [v2.x-bubble-border-fix] - 2026-09-09

### 修复
- **气泡边框不可见**：`--mine-bg` / `--mine-border` 为未定义 CSS 变量，浏览器忽略整个 border 声明。替换为已定义的 `--mine-soft`（背景）和 `--mine`（边框），覆盖 `GeneratingView.vue` 和 `RecordingView.vue`
- **他人行边框对比度不足**：`.txt` 边框从 `--border`（92% 亮度，与背景近乎无色）升级为 `--border-strong`（86% 亮度），确保气泡轮廓清晰可见

## [v2.x-vue-bubble-transcript] - 2026-09-09

### 变更
- **转写行气泡化移植到 Vue**：将原型确认的气泡样式移植到 `legacy-views.css`——所有转写行 `.txt` 统一包进气泡（白底 + 1px 边框 + `--radius-lg` 12px 圆角），「我的」行保持绿色调气泡右对齐（scoped 样式已有）
- **CSS 细节**：`.ts-line` 添加 hover 背景 `var(--surface-2)`；`.ts-line-body` 改为 `inline-block` + `max-width: 85%`；`.spk` 圆角改用 `--radius-sm` token；`.spk-unbound` 添加 `font-style: italic`

## [v2.x-prototype-bubble-unify] - 2026-09-09

### 变更
- **转写行统一气泡化（原型）**：`transcript-page-v2-prototype.html` 所有会话内容统一包进气泡——他人行为白底 + 1px 边框气泡（品牌「1px 细线分区」语言），「我的」行保持绿色调气泡，两者均以 `align-self` 收缩至内容宽度
- **圆角标准确立**：三档 token——`--radius-sm` 6px（按钮/标签/chip）、`--radius` 8px（输入框/下拉框）、`--radius-lg` 12px（弹窗/章节卡/对话气泡）；气泡统一 12px 并带 4px 锚点角（靠近说话人一侧收窄：他人行左上、「我的」行右上）
- **「我的」行头部修正**：移除 `.ts-line-head` 的 `row-reverse`，改为整组右对齐，内部保持「时间戳 → 说话人」阅读顺序，说话人标签落在最右与锚点角对齐
- **对齐方式调整**：`.ts-line-body` 对齐偏移从 `padding-left` 改为 `margin-left`，气泡内边距保持四边一致
- **清理**：移除「我的」行遗留的内联 `border-radius: 9px` 覆盖与 `text-align: right` 冗余声明

## [v2.x-prototype-ts-order] - 2026-09-09

### 变更
- **转写行头部元素顺序调整**：时间戳移到说话人左侧，左对齐。`.ts-line-head` 内 HTML 顺序从「说话人 → 时间戳」改为「时间戳 → 说话人」
- **文本对齐调整**：`.ts-line-body` 添加 `padding-left: calc(40px + var(--s-2))`，让文本内容与第一行的说话人标签左对齐（跳过时间戳宽度）

## [v2.x-prototype-2row-update] - 2026-09-09

### 变更
- **转写页面原型更新为两行布局**：`transcript-page-v2-prototype.html` 所有转写行从 CSS Grid 三列单行改为 Flexbox 两行（`.ts-line-head` 说话人+时间戳 / `.ts-line-body` 文本内容），与 Vue 组件实现保持一致
- **流程约定**：今后所有前端修改先调整原型图并确认，再移植到 Vue 组件

## [v2.x-transcript-2row-layout] - 2026-09-09

### 变更
- **转写行布局改为两行**：说话人与时间戳一行、内容一行。从 CSS Grid 三列单行改为 Flexbox 两行（`.ts-line-head` + `.ts-line-body`），同步应用于纪要页（`.ts-line`）和录音页（`.rec-line`）
- **"我的"气泡样式适配**：`.ts-line.is-me` / `.rec-line.is-me` 改为 `align-items: flex-end` + `.ts-line-head` 反转 + `.ts-line-body` 右对齐，气泡最大宽度 70%

### 修复
- `frontend/src/views/GeneratingView.vue`：转写行 HTML 重构为 `.ts-line-head`（说话人+时间戳）+ `.ts-line-body`（文本）
- `frontend/src/views/RecordingView.vue`：录音行 HTML 同步重构为 `.rec-line-head` + `.rec-line-body`，含 partial 行
- `frontend/src/styles/legacy-views.css`：`.ts-line` 从 `grid-template-columns: 60px minmax(56px,80px) 1fr` 改为 `flex-direction: column`；`.rec-line` 同步改为 `flex-direction: column`；新增 `.ts-line-head` / `.ts-line-body` / `.rec-line-head` / `.rec-line-body` 样式

## [v2.x-chapters-backfill] - 2026-09-09

### 修复
- **旧任务章节缺失**：已完成任务在章节生成功能添加前完成，`chapters` 字段为 `None`。新增后台自动补生成逻辑——`get_task` API 检测到 `completed` 但无章节时，启动后台线程调用 `generate_chapters()` 并持久化
- **前端章节加载态**：`GeneratingView.vue` 新增章节补生成轮询（3 秒间隔），章节生成期间显示"章节划分中..."加载指示器

### 变更
- `app/routers/tasks.py`：`get_task` 增加章节补生成逻辑
- `frontend/src/views/GeneratingView.vue`：新增 `startChapterPolling` / `stopChapterPolling` + `.chapter-loading` 模板
- `frontend/src/styles/legacy-views.css`：新增 `.chapter-loading` / `.chapter-loading-spinner` 样式

## [v2.x-minutes-tabs-migration] - 2026-09-09

### 新增
- **纪要面板增强**：`GeneratingView.vue` 纪要 Tab 新增章节回顾卡片（可展开要点列表，使用已有 chapters 数据）+ 行动项入口（虚线按钮跳转待办 Tab，实时显示待办计数）
- **笔记工具栏引用按钮**：Markdown 工具栏新增引用（`>`）按钮，与原型一致
- **待办定位原文按钮**：每个待办条目新增 hover 显示的定位按钮，点击跳转到转写 Tab

### 变更
- `legacy-views.css`：新增 `.sum-section` / `.sum-chapter-card` / `.sum-todos-link` / `.todo-locate-btn` 样式

## [v2.x-minutes-tabs-prototype] - 2026-09-09

### 新增
- **纪要页功能原型**（`docs/prototypes/minutes-tabs-v2.html`，同步 Design Files `minutes-tabs-v2-prototype.html`）：基于 1.0 版本还原纪要页其余功能区，与已定稿的 transcript-page-v2 原型共享同一套 tokens 与页面框架——
  - **纪要 Tab**：概述 / 章节回顾（可展开要点卡片）/ 关键决策（含决策人）/ 风险与待确认（warn 语义色）/ 行动项入口（跳转待办 Tab）；底部附三态演示（awaiting_mapping 引导 + Stage 2 生成中骨架屏）
  - **笔记 Tab**：1.0 Markdown 工具栏（B/I/code/H/列表/引用）+ 时间戳笔记块（点击时间戳跳转音频，hover 编辑，含编辑态示例与"已保存"指示）
  - **待办 Tab**：统计行实时联动 + 待办条目（勾选 / 执行人 / 来源徽标 AI·手动 / 定位原文跳转转写 Tab）+ 虚线按钮展开添加表单
  - **AI 会议助手右侧轨道**：上下文标签 / 对话·分析·指令三个子 Tab / 消息气泡（含"已同步至待办 Tab"动作芯片）/ 发言占比与高频关键词 / `/` 指令表 / 快捷指令芯片 / 可折叠为竖条

## [v2.x-transcript-v2] - 2026-09-09

### 变更
- **转写页面原型设计 → 代码移植**（`GeneratingView.vue` + `legacy-views.css`）：基于 1.0 版本设计还原完整转写页面——
  - **"我的"转写行布局修复**：从 CSS Grid（`order` 属性导致 `.txt` 被挤进 56-80px 窄列）改为 Flexbox `row-reverse`，文本气泡自然获得剩余空间，不再大量换行
  - **右侧说话人面板**：搜索框 + 勾选筛选列表（含角色/时长/次数统计）+ 底部合计；支持面板收起/展开；勾选单个说话人进入聚焦模式
  - **聚焦模式横幅**：显示当前聚焦说话人 + 上下条导航 + 退出按钮；非目标行淡化（opacity 0.25），目标行高亮（accent-soft 背景 + 左侧 accent 色条）
  - **转写面板布局**：添加 `spk-layout-active` class 解除 `max-width: 760px` 约束，允许转写区 + 说话人面板并排显示

## [v2.x-ui-polish] - 2026-09-09

### 变更
- **首页与会议库路由拆分**（`StartView.vue` + `legacy-views.css`）：StartView 精简为纯首页（动画背景 + 操作按钮 + 最近会议），移除 `.main-inner` 空闲态双层结构和 `showStartPage` 显隐切换；CSS 中 `.start-page` 改为始终 `display: flex`，所有 `.start-page.is-active` 选择器简化为 `.start-page`；首页操作直接路由跳转，不再有中间页面闪烁
- **纪要页元信息区重构**（`GeneratingView.vue` + `legacy-views.css`）：对齐原型设计——图标化元信息行（时长/人数/日期 + 项目标签）+ 新增说话人色条与彩色圆点名单；新增 `metaDuration`、`metaDateShort`、`speakerStats` computed
- **TopBar 响应式折叠**（`topbar.css`）：≤1280px 隐藏语言按钮与视图切换器，≤1100px 新建按钮仅显示图标
- **录音页波形动画增强**（`legacy-views.css`）：wbar 从纯 opacity 脉冲改为 scaleY 高度联动，5 根条错峰动画
- **跳过处理中页**（`RecordingView.vue`）：录音结束直接跳转纪要页，由其内部轮询展示"转写内容整理中"，ProcessingView 保留为手动入口
- **说话人绑定流程还原**（对齐 1.0 版本）：`GeneratingView.vue` 还原绑定栏（legend chips / 未关联计数 / 暂不关联 / 确认关联）+ 转写内联绑定下拉框（搜索 / 不关联 / 新建 / 键盘导航）+ 增量 PUT 保存；`api/speakers.ts` 新增 `submitSpeakerMapping`、`saveSpeakerMapping`
- **样式规范落地**：6 个组件（Library/Processing/Settings/Speakers/Generating/Recording）硬编码间距替换为 `--s-*` token；13 处 opacity 衰减型 hover 改为背景加深/前景增强（`legacy-views.css`、`topbar.css`、`GeneratingView.vue`）；StartView 说话人选择器内联样式抽取为 class
- **说话人页面 UI 重新设计**（`SpeakersView.vue` + `legacy-views.css`）：移除彩色方块头像，改用彩色圆点 + 文字信息的简洁列表风格，与会议列表视觉一致；列表项改为统一边框容器 + 分隔线布局；操作按钮改为轻量 ghost 样式；详情视图头部同步简化；清理 legacy-views.css 中约 50 行未使用的 `.spk-table`、`.spk-detail-avatar`、`.spk-detail` 旧样式

### 修复
- **"设为我"按钮操作后无反馈**：前端 `mapSpeaker` 读取 `raw.is_me` 但后端只返回 `linked_user_id`，导致 `is_me` 永远为 `false`；改为引入 `useUserStore`，通过比较 `linked_user_id` 与当前用户 `id` 判断；`onSetMe` 增加 try/catch + toast 成功/失败反馈
- **录音完成后页面卡住**：`RecordingView` 原直接跳纪要页但后端管线未完成；`GeneratingView` 新增轮询兜底（任务未完成时每 3 秒拉取最新数据），`onMounted` 始终 fetch 最新任务而非复用 store 旧数据；`ProcessingView` 轮询补充 `awaiting_mapping`、`failed` 状态处理
- **`awaiting_mapping` 提示误导**：纪要面板不再显示"等待原文校正"，改为明确的"请先绑定说话人身份"引导卡片
- **会议列表切换不响应**：`App.vue` 的 `<router-view>` 增加 `:key="$route.fullPath"`，路由参数变化时强制重建组件
- **任务卡片删除/重命名/重试无响应**：`TaskList.vue` 补监听 `@menu` 事件，`TaskCard.vue` 的 menu 事件透传 `newName` 避免重命名弹两次输入框
- **暗色主题穿帮（P0）**：归档对话框 9 处硬编码 fallback 颜色改走主题变量；`SpeakersView` 声纹 badge 硬编码绿色/红色改用 `--ok-soft`/`--rec-soft` 语义色
- **全局键盘可达性（P0）**：`base.css` 新增 `:focus-visible` 焦点环（`--accent` 色，覆盖 button/input/a/[role="button"]）
- **"设为我"后转写行未居右**（还原 1.0 版本群聊风格）：`GeneratingView.vue` 和 `RecordingView.vue` 的 `isMeSpeakerId`/`isMeSpeaker` 函数从读取后端不返回的 `is_me` 改为通过 `linked_user_id` 与当前用户 `id` 比较；CSS 从简单背景高亮增强为右对齐气泡对话框——`flex-direction: row-reverse` + `--mine-soft` 气泡背景 + 圆角 12px + 最大宽度 70%/85%
- **首页操作闪烁**：`StartView.vue` 移除 `onStartRecord`、`onUploadClick`、`onFileSelected`、`openTask` 中提前设置 `showStartPage = false` 的逻辑，API 等待期间保持首页覆盖层显示，路由跳转后自然切换
- **录音计时器小数位**：`useRecorder.ts` 的 `formatElapsed` 对 `elapsed` 先 `Math.floor` 取整，避免浮点精度导致秒数显示为 `00:9.01394…`
- **空状态响应式**：LibraryView / SpeakersView 空状态 padding 改用 token 并新增 920px 断点，搜索框窄屏撑满
- **"我的会话"气泡大量换行**：`GeneratingView.vue` 的 `.ts-line.is-me` 使用 CSS Grid `order` 属性试图反转布局，但 grid 自动放置仍按 order 排序后依次填入列，导致 `.txt` 被放入 `minmax(56px, 80px)` 的说话人列，文本被挤进窄列；改为 `grid-column` 显式指定 `.txt` → 第 1 列（1fr）、`.spk-wrapper` → 第 2 列、`.ts` → 第 3 列，`.txt` 加 `justify-self: end` 右对齐气泡

## [v1.x-backlog-restructure] - 2026-09-09

### 决策
- **产品迭代规划结构化重构**：将 8 个零散产品想法按模块分类整理为结构化需求卡片，写入 BACKLOG.md「产品迭代规划」章节

### 新增
- **BACKLOG 新增 9 条结构化需求**（4 大模块）：
  - UI/UX：全局面包屑导航、工具栏响应式降级规范
  - 核心业务：项目文件转写状态可视化、说话人手动标记准确性修复
  - AI 能力：AI 操作交互确认机制、纪要编辑与上下文反馈增强、实时章节折叠交互、实时新词发现与确认机制
  - 外部集成：本地系统日历集成

## [v1.x-product-ideas] - 2026-09-08

### 决策
- **产品战略方向**：从会议助理向主动型 AI 转变，AI 主动识别卡壳/偏题并提供解决方案（写入 PRD.md、ROADMAP.md）
- **企业化核心洞察**：更大上下文 → 更有效决策，用户参与编辑提升置信度（写入 PRD.md、ROADMAP.md）

### 新增
- **BACKLOG 新增 7 条**：说话人绑定无法解绑（缺陷）、说话人分离精度不足（缺陷）、录音界面显示系统时钟、AI 主动识别卡壳/偏题、实时总结重新定位、笔记支持选中文本批注、转写摘要允许用户编辑

## [v2.0-frontend] - 2026-09-08

### 新增
- **前端 Vue 3 重构**：将 19,509 行单文件 `index.html` 拆分为 48+ 个模块化源文件
  - 技术栈：Vue 3 + TypeScript + Vite + Pinia + Vue Router
  - 目录结构：`frontend/src/`（api/ stores/ composables/ views/ components/ styles/）
  - 7 个主题 CSS 变量拆分为独立文件，保留 oklch() 色彩系统
  - 9 个视图全部实现：StartView、RecordingView、ProcessingView、GeneratingView、LibraryView、ProjectsView、SpeakersView、HotwordsView、SettingsView
  - 3 个 composable：usePolling、useRecorder、useWebSocket
  - 11 个 API 封装模块，与后端 15 个 router 完全对齐
  - 登录弹窗：GitHub OAuth + 短信验证码双 Tab
  - AI 对话面板：实时对话 + 上下文感知 + 折叠/展开
  - 侧边栏：任务列表时间分组、搜索过滤、用户菜单
- **生产集成**：`server.py` 自动检测 `frontend/dist/` 并托管 Vue 构建产物，支持 history 模式
- **CLI 命令**：`python cli.py build` 一键构建前端
- **部署脚本**：`deploy.sh` 新增 Node.js 依赖安装和前端构建步骤

### 变更
- **server.py**：前端托管改为双模式（新版 Vue SPA / 旧版 index.html 兼容），自动检测
- **cli.py**：新增 `build` 子命令，自动安装依赖并构建前端
- **.gitignore**：新增 `frontend/node_modules/` 和 `frontend/dist/`

## [v1.x-icon-spec] - 2026-09-08

### 新增
- **图标规范文档**：新增 `docs/ICON_SPEC.md`，统一图标体系：
  - 选型 Lucide（Feather Icons 活跃分支），与现有内联 SVG 风格 100% 兼容
  - 定义 4 级尺寸体系（sm 14px / md 16px / lg 20px / xl 24px）
  - 设计 JS 图标映射表 `ICONS`（30+ 图标） + `icon()` 辅助函数
  - 完整 Emoji → Lucide SVG 替换映射表
  - 明确 SVG 属性规范、禁止事项、新增图标流程

### 变更
- **图标系统实施**：按 `ICON_SPEC.md` 完成全应用图标替换：
  - `index.html`：添加 `.ic` / `.ic-sm` / `.ic-md` / `.ic-lg` / `.ic-xl` CSS 类 + `ICONS` 映射表 + `icon()` 函数
  - 重构 `AI_GUIDANCE_ICONS`、`iconSvgs` 动态 SVG 映射表改用 `icon()` 函数
  - 替换 14 处 emoji 为 SVG 图标（⚠→alert-triangle、🔄→refresh-cw、🎵→music、🔑→key、📎→paperclip、📁→folder、📂→folder-open、✕→x、✓→check、☐→square、☑→check-square、↓→chevron-down）
  - 替换密码可见性切换硬编码 SVG path 改用 `ICONS['eye']` / `ICONS['eye-off']`
  - 替换版本更新日志分类图标（+→plus、✓→check、↑→chevron-up）
  - `admin.html`：添加图标 CSS 类，替换 3 处 emoji 空状态图标（📭→inbox、📢→megaphone、🎛️→sliders）
- `ui-spec.md` 添加图标规范引用，「待补」项标记视觉规范已部分完成
- `CODEX.md` 模块速查表新增 `ICON_SPEC.md` 入口

## [v1.x-hotwords-cache] - 2026-09-08

### 修复
- **热词映射重复读文件**：`load_hotword_mappings()` 在实时转写期间每 ~200ms 被调用一次，每次都从磁盘读取文件并重新编译正则。改为基于文件 mtime 的模块级缓存 + 预编译正则，缓存命中时性能提升约 80 倍。保存端点调用 `invalidate_hotword_mappings_cache()` 确保写入后立即生效。

## [v1.x-perf-monitoring] - 2026-09-08

### 新增
- **运行时性能监控埋点**：新增 `core/perf.py` 轻量性能工具（`perf_timer` 上下文管理器 + `PerfCollector` 任务级收集器 + 慢操作告警阈值），在关键路径加耗时日志：
  - `core/pipeline.py`：管线两阶段总计 + 各子步骤（归一化、热词、转写、纪要、标题、章节）
  - `core/audio.py`：ffmpeg 归一化耗时
  - `core/transcribe.py`：ASR 代理调用耗时
  - `core/llm.py`：同步/异步 LLM 调用耗时（含超时/失败时的耗时记录）
  - `app/store.py`：管线任务总计 + P0 文本桥接匹配 + P1 声纹匹配
  - `app/server.py`：慢请求告警（>3s 的 HTTP 请求输出 WARNING 到主日志）
- 所有性能日志统一 `[PERF]` 前缀，便于 grep 过滤

## [v1.x-ai-followup-and-cmd-toggle] - 2026-09-08

### 新增
- **AI 消息跟进建议**：每条 AI 回复底部自动展示 1-3 个上下文相关的对话引导 chips（如回复涉及待办→建议"按责任人分类"，涉及结论→建议"展开讨论细节"），点击即发送
- **快捷指令管理（设置面板）**：设置 → 快捷指令管理，可按指令逐个启用/禁用，关闭的指令不再出现在 / 指令面板中。支持按状态分组（通用/录制中/已完成），配置持久化到 settings.json

## [v1.x-transcript-loading-fix] - 2026-09-08

### 修复
- **已完成会议转写内容栏残留"整理中"**：两层问题——①`getContextStats` 引用了未定义的 `projects` 变量（应为 `projectsCache`），导致 `showCompleted` 在调用 `updateAiSessionBar` 时抛出 `ReferenceError` 崩溃，后续 UI 更新全部跳过；②即使无异常，`showCompleted` 也未显式隐藏转写区加载态。修复：将加载态隐藏移至 `showCompleted` 最开头（在任何可能异常的调用之前），并修正 `projects` → `projectsCache.find()`

## [v1.x-summary-countdown] - 2026-09-08

### 新增
- **实时总结倒计时**：总结面板 header 新增环形进度倒计时（28px SVG ring）+ 底部线性进度条，10 秒内橙色预警；后端每秒通过 WebSocket 推送 `summary_countdown` 消息，前端实时渲染剩余秒数
- **用户自定义刷新频率**：设置页「实时总结生成」开关下方新增频率选择器（30s / 60s / 120s / 300s），持久化到 `settings.json` 的 `feature_flags.realtime_summary_interval`；录音中通过总结面板 "..." 更多菜单切换频率，热更新立即生效
- **停止/启动控制**：通过 "..." 更多菜单内的停止/开始项，支持三态模型——运行中 → 已停止（彻底关闭自动更新，ring 显示 "—"）→ 菜单项切换为"开始总结"恢复；暂停按钮独立可用
- **页面刷新同步**：WebSocket 回放时携带 `remaining`（剩余秒数）和 `interval`（当前间隔），重连后倒计时状态无缝恢复

### 变更
- **总结面板布局精简**：移除底部状态栏（倒计时文字 + 间隔快选 + 元信息），与 header 环形倒计时消除冗余；停止/暂停两个独立按钮合并为一个暂停按钮 + "..." 更多菜单（内含停止/启动、刷新频率选择）；聚焦模式按钮移至顶部工具栏与翻译同级
- `RealtimeSummarizer.__init__` 新增 `interval` 和 `on_countdown` 参数，`_schedule_next()` 使用实例属性替代模块常量
- `get_feature_flags()` 返回增加 `realtime_summary_interval` 字段（默认 60）
- 新增 API 端点：`POST /api/record/summary/stop`、`/restart`、`/interval`

### 修复
- **音频双重归一化**：`estimate_speaker_count` 先归一化生成 `_normalized.wav`，`run_pipeline_stage1` 又对其再次归一化产生 `_normalized_normalized.wav`；`normalize_audio` 新增幂等性检查，输入已为 `_normalized.wav` 时直接返回跳过 ffmpeg
- **声纹注册表维度混合崩溃**：注册表中同时存在 CAM++ 192 维和 MFCC 降级 14 维嵌入，`np.stack` 因维度不一致抛出 `ValueError`；`auto_identify_speakers` 和 `match_speaker` 新增维度过滤，剔除与当前 encoder 输出维度不一致的记录

## [v1.x-notes-inline-flow] - 2026-09-08

### 新增
- **孤儿录音自动恢复**：服务异常退出后重启时，若检测到正在录制的任务且 raw PCM 文件仍在，自动将 raw 转为 WAV 并保留任务（状态置为 `pending`），用户可直接触发后续转写与分析，不再丢失音频数据

### 变更
- **笔记融入转写流**：笔记从独立浮动面板改为直接插入转写时间线，与对话共享同一滚动区域
  - 靠右轻量气泡（max-width 78%、冷色 `--note-bg`、✏️「笔记」标签 + 时间戳），视觉重量低于转写段落
  - 点击发送后笔记自动出现在时间上最近的对话条目之后，无需跳转操作
- **全宽输入栏**：笔记输入栏横跨转写 + 总结下方（`.rec-notes-bar`），移除摘要栏 / 浮动面板 / 独立笔记列表
  - 计数徽章（`role="status"`）与「显示标记」开关移入输入栏
- **「我说的」暖色区分**：绑定为「我」的说话人段落改用暖绿底色（`--mine-bg` / `--mine-border`），与冷色笔记气泡形成「形态 + 色相」双重区分（7 套主题均定义 token）
- **可访问性落地**（原型打磨同步）：textarea 关联 sr-only label、删除按钮 24×24 触控目标、`aria-pressed`/`aria-label` 同步、删除动画改用 `.note-removing` CSS class、新增 `prefers-reduced-motion` 适配

### 修复
- 「显示标记」压缩逻辑适配内嵌气泡：仅当转写区溢出时折叠无笔记对话组，空间足够时不压缩

### 移除
- 旧浮动面板体系：`.rec-notes-section` / `.notes-summary-bar` / `.rec-notes-floating-panel` / `.note-card` / `.transcript-note-marker` 及相关 JS（`toggleNotesPanel`、`highlightNoteCard`、`createNoteCard` 等）

### 涉及文件
- `app/static/index.html`：CSS token + 笔记样式 + HTML 结构 + JS 逻辑
- `docs/design/ui-spec.md`：「录音视图 · 时间戳打点笔记」段落重写

## [v1.x-timestamped-notes] - 2026-09-08

### 新增
- **时间戳打点笔记**：录音期间的笔记功能从整体 textarea 升级为带时间戳的打点系统
  - **笔记输入**：底部笔记栏从折叠式 textarea 改为始终可见的输入行（支持多行），Enter 发送、Shift+Enter 换行
  - **时间戳标记**：每条笔记自动打上录音时间戳（如 `记录于 1:42`），明确标注记录时刻
  - **笔记卡片**：已发送的笔记以卡片形式展示，左侧时间标签 + 右侧内容，支持点击跳转到转写区对应位置
  - **转写区标记行**：开启「显示标记」后，转写列表中在对应位置插入蓝色标记行，显示时间 + 笔记图标 + 内容预览
  - **对话压缩**：开启标记后，无标记的对话段落自动折叠为「已折叠 N 段对话」，点击可展开/收回，便于快速扫描打点位置
  - **可折叠面板**：笔记区默认折叠为摘要栏（显示笔记数量 + 最新预览），点击展开笔记列表，最大高度 220px 内部滚动
  - **删除确认**：删除笔记需点击叉号后二次确认（「确认删除？删除 取消」），防止误操作
  - **双向跳转**：点击笔记卡片 → 转写区滚动到标记行并高亮闪烁；点击转写区标记 → 展开笔记面板并高亮对应卡片
  - **localStorage 持久化**：笔记数据实时保存，刷新页面不丢失
  - **停止录音提交**：笔记格式化为 `[0:42] 内容` 提交给后端，作为结构化上下文传给纪要生成

### 变更
- **笔记栏 HTML 结构**：`.rec-notes-bar` 替换为 `.rec-notes-section`，包含摘要栏、可展开区域、笔记列表、输入行
- **笔记 CSS 样式**：新增完整的笔记系统样式（摘要栏、笔记卡片、标记行、压缩指示器、删除确认、焦点环、reduced-motion 适配）
- **笔记 JavaScript 逻辑**：新增 `recNotes` 状态管理、`addNote()`、`deleteNote()`、`toggleNotesPanel()`、`toggleMarkerMode()`、`rebuildCompression()`、`scrollToNoteMarker()`、`highlightNoteCard()` 等函数
- **可访问性增强**：所有交互元素添加 `:focus-visible` 焦点环，摘要栏/压缩指示器/笔记可点击区域添加 `tabindex` + `role="button"` + 键盘事件支持

### 涉及文件
- `app/static/index.html`：CSS 样式、HTML 结构、JavaScript 逻辑全面改造

## [v1.x-todo-crud] - 2026-09-07

### 新增
- **待办手工增删改**：`app/routers/notes.py` 新增 `POST /api/tasks/{task_id}/todos`（手工添加待办）和 `PUT /api/tasks/{task_id}/todos/{todo_id}`（编辑待办内容/执行人）两个端点，支持用户在 AI 提取待办之外手工补充和管理待办事项

### 涉及文件
- `app/routers/notes.py`：新增 `TodoCreateRequest`、`TodoUpdateRequest` 模型及对应端点

## [v1.x-tab-order] - 2026-09-07

### 变更
- **会议纪要 Tab 顺序调整**：详情页 Tab 顺序从「转写 → 纪要 → 章节 → 笔记 → 待办」调整为「转写 → 笔记 → 纪要 → 待办」。章节（chapters）已合并到转写面板，不再作为独立 Tab
- **重新生成纪要**：纪要 Tab 保留「重新生成纪要」按钮，笔记修改后可一键重新调用 LLM 生成纪要

### 涉及文件
- `app/static/index.html`：Tab 顺序调整，chapters 合并到 transcript 面板

## [v2.0-asr-proxy] - 2026-09-07

### 新增
- **ASR 代理服务**：新增 `asr-proxy/` 目录，FastAPI 服务运行在 <server-ip>:8200，持有云端 ASR API Key，为客户端提供批处理转写（`/asr/transcribe`）和实时流式转写（`/asr/ws`）中转。通信协议：HTTP POST + HMAC-SHA256 签名（`X-ASR-Timestamp` / `X-ASR-Sign`），WebSocket 通过查询参数传递签名。详见 ADR-0012。服务端已部署（`/opt/asr-proxy`，systemd 管理，开机自启）。

### 变更
- **客户端转写管线改造**：`core/transcribe.py` 从直连云端 ASR 改为调用 ASR 代理 `/asr/transcribe`，一站式提交音频文件并获取完整转写结果（代理内部处理上传 + 提交 + 轮询 + 下载）。`core/pipeline.py` 移除独立的上传步骤（不再调用 `core/upload.py`）。
- **实时转写改造**：`core/realtime_asr.py` 从云端 ASR SDK 直连改为通过代理 WebSocket 中继，使用 `websockets` 库连接 `ws://proxy:8200/asr/ws`。
- **计量逻辑简化**：`core/metering.py` 的 `is_metered()` 不再判断"自带 Key"分支，代理模式下所有已登录用户均走计量。
- **设置页精简**：移除 ASR API Key、Base URL、Provider 配置入口，仅保留模型选择。新增代理模式说明。
- **`app/store.py`**：`get_asr_config()` 返回代理地址而非云端 ASR 直连配置。
- **`app/routers/settings.py`**：`save_settings()` 不再保存 ASR API Key；`_test_asr_connection()` 改为调用代理健康检查端点。

### 环境变量
- 新增：`ASR_PROXY_URL`（默认 `http://<server-ip>:8200`）、`ASR_PROXY_TOKEN`（共享密钥）
- `DASHSCOPE_API_KEY` 仅用于 LLM 纪要生成，ASR 不再直连

### 决策
- ASR 转写走云端代理，云端 AI Key 不落地客户端。详见 ADR-0012。

## [v3++-speaker-binding-loop] - 2026-09-07

### 新增
- **文本桥接匹配（P0）**：新增 `core/text_bridge.py`，利用实时绑定阶段的文本内容（确定性证据）在批处理结果中搜索相似文本，继承说话人绑定关系。基于 `difflib.SequenceMatcher` 字符级模糊匹配，按命中次数投票确定新 speaker_id
- **分层匹配策略**：批处理完成后按 P0 文本桥接 → P1 声纹匹配 → P2 手动绑定的优先级依次执行（`app/store.py:run_pipeline_task`）。文本桥接未覆盖的 speaker_id 由声纹匹配补充
- **全量实时转写持久化**：新增 `realtime_full_transcripts` 字典（`app/store.py`），录音期间无上限累积所有定稿句子，突破 `REALTIME_BUFFER_MAX=10` 的限制，供文本桥接匹配使用
- **声纹时长加权累积**：`VoiceprintRecord` 新增 `total_sample_duration` 字段，`register_voiceprint()` 按音频时长加权累积平均（替代旧的样本数加权），更准确反映信息量
- **声纹自动更新闭环**：自动匹配成功后立即调用 `register_from_binding` 更新声纹注册表（含时长加权），无需用户手动触发
- **声纹采集用户感知**：实时绑定完成后 toast 提示「已记录声音特征，后续会议将自动识别」；设置页说话人列表显示「声纹样本：X 分钟」（替代旧的手动更新按钮）；绑定横幅暗示「系统正在学习识别说话人」

### 变更
- **声纹注册 API 扩展**：`register_voiceprint()` 新增 `duration_sec` 参数；`VoiceprintStatusResponse` 和 `/api/voiceprint/registry` 返回 `total_sample_duration` 字段
- **前端声纹按钮**：说话人详情页的「注册/更新声纹」按钮改为只读的声纹样本时长显示（`<span>` 替代 `<button>`），声纹更新由系统自动完成

## [v1.x-jwt-user-identity] - 2026-09-07

### 修复
- **多用户身份隔离**：`get_current_user()` 从全局 `current_user_id` 改为优先读取请求级 ContextVar（由 JWT cookie 解析），回退到 `current_user_id` 兼容后台任务场景。新增 `user_identity_middleware`（`app/server.py`）从 `oms_session` cookie 解析用户 ID 并写入 ContextVar。修复了多用户同时登录时订阅信息、用量数据、偏好设置互相覆盖的 bug

### 涉及文件
- `core/users.py`：新增 `set_request_user_id()`、`get_request_user_id()`，重构 `get_current_user()`
- `app/server.py`：新增 `user_identity_middleware`

## [v1.x-diarization-user-pref] - 2026-09-07

### 新增
- **声纹方案用户偏好 + 订阅状态驱动**：实时说话人分离的 provider 选择（云端 CAM++ vs 本地 MFCC）改为用户可控。非订阅用户（free）强制本地 MFCC；订阅用户（personal/pro/team）默认云端 CAM++，可通过偏好设置切换回本地 MFCC。新增 `core/users.py` 的 `should_use_local_diarization()`、`core/diarization.py` 的 `create_realtime_diarizer()` 工厂函数、`GET/POST /api/user/prefs` 端点、`GET /api/settings` 返回 `diarization` 节

### 涉及文件
- `core/users.py`：新增 `should_use_local_diarization()`
- `core/diarization.py`：新增 `create_realtime_diarizer()` 工厂函数
- `app/routers/record.py`、`app/routers/chat.py`：改用 `create_realtime_diarizer()`
- `app/routers/user.py`：新增 `GET/POST /api/user/prefs` 端点
- `app/routers/settings.py`：`GET /api/settings` 新增 `diarization` 字段

## [v1.x-realtime-cloud-cam++] - 2026-09-07

### 变更
- **实时声纹聚类切换到云端 CAM++ 192 维**：`core/diarization.py` 的 `SpeakerDiarizer` 和 `extract_speaker_feature()` 改为通过 `core.embedding_provider` 抽象层提取嵌入（云端 CAM++ 192 维优先，MFCC 14 维降级兜底）。匹配阈值从 0.65（MFCC）调整为 0.55（CAM++），合并阈值从 0.52 调整为 0.65。阈值根据 provider 维度自动选择，云端不可用时回退 MFCC 阈值。调用方（`record.py`、`chat.py`、`store.py`）无需修改

### 涉及文件
- `core/diarization.py`：`SpeakerDiarizer` 新增 `provider` 参数，`extract_speaker_feature` 走 provider，新增 `CLOUD_SIMILARITY_THRESHOLD` / `CLOUD_MERGE_THRESHOLD` 常量

## [v1.x-speaker-count-and-archive] - 2026-09-07

### 修复
- **说话人计数不准确**：`core/diarization.py` 后处理合并阈值从 0.40 提高到 0.52，避免 MFCC 14 维特征区分度不足时把不同说话人误合并；录音停止时改用有效说话人计数（过滤语音时长 <2s 的伪说话人）

### 新增
- **实时说话人参与统计**：录音过程中实时显示当前识别到的说话人数量，顶栏展示「N 位说话人」徽章，悬停显示说话人姓名列表；后端每 2 秒检测数量变化并通过 WebSocket `speaker_count_update` 消息推送
- **项目归档用户确认**：会议纪要完成后不再自动写入项目文件夹，改为弹出确认提示，由用户选择是否将纪要和待办写入关联项目的文件夹；新增 `GET /api/tasks/{id}/sync-status` 和 `POST /api/tasks/{id}/sync-to-project` 两个端点

### 涉及文件
- `core/diarization.py`：合并阈值调整，新增 `get_active_speaker_count()` / `get_active_speaker_ids()`
- `app/routers/record.py`：实时说话人统计推送，停止录音时使用有效计数
- `app/routers/tasks.py`：新增同步状态查询与手动同步端点，移除自动同步逻辑
- `app/store.py`：移除 `_run_stage2_for_task` 中的自动同步调用
- `app/static/index.html`：录音顶栏说话人徽章、`handleSpeakerCountUpdate`、`checkAndPromptProjectSync`

## [v1.x-sticky-scroll-transcript] - 2026-09-07

### 修复
- **实时录写时无法上翻查看历史**：转写列表原本每收到 partial/sentence 消息就无条件滚到底部，导致用户上翻查看之前的对话时被强行拽回。改为「粘底检测」模式：监听滚动位置，距底部 60px 以内视为粘底（跟随模式），只有粘底时新消息才自动滚动；用户上翻后停止自动滚动，并在转写面板右下角显示「回到底部」浮动按钮，点击跳回最新位置并恢复跟随。新建/恢复录音时重置为粘底状态。

### 涉及文件
- `app/static/index.html`：新增 `recStickBottom` 粘底状态与 `recScrollIfStuck()` 等辅助函数；`handleTranscriptMessage` 中 5 处（partial / sentence / history / error / 章节分隔）无条件滚动改为粘底条件滚动；新增「回到底部」按钮及样式；3 处清空转写列表处重置粘底状态


## [v1.x-update-flow] - 2026-09-07

### 新增
- **软件更新流程（L3 骨架）**：启动后自动检查新版本并提示，应用内展示更新面板（版本对比 / 分类 changelog / 下载进度）与重启确认模态框。当前为骨架版本：版本检查与 UI 已可用，下载与重启为模拟逻辑，真实发布渠道接入计划见 [BACKLOG](docs/BACKLOG.md)「软件更新流程落地（L3）」。
- `core/version_check.py`（新增）：读取根目录 VERSION，调用 GitHub Releases API 获取最新版本，语义化版本比对，结果缓存 30 分钟，网络失败静默降级；远端地址可用 `settings.json` 的 `update.releases_url` 覆盖
- `app/routers/update.py`（新增）：`GET /api/update/version`（当前版本）、`GET /api/update/check`（检查更新，支持 `force` 跳过缓存）
- 前端：侧边栏底部固定版本号（点击打开更新面板，侧栏收起时自适应）、顶部导航栏更新徽标、右滑更新面板（changelog 自动分类为新功能/修复/优化）、下载进度模拟、重启确认模态框
- 启动 2 秒后自动检查版本，受 `feature_flags.update_check` 功能开关控制

### 涉及文件
- `core/version_check.py`：新增
- `app/routers/update.py`：新增
- `app/server.py`：注册 `update` 路由
- `app/static/index.html`：新增侧边栏版本号、更新徽标、更新面板、重启模态框及对应 JS
- `VERSION`：新增版本文件


## [v1.x-fix-bind-speaker] - 2026-09-07

### 修复
- **录音中绑定说话人无效**：修复录音过程中绑定说话人后未生效的 bug。`handle_bind_speaker` 事件处理现在立即更新内存中活跃会话的说话人映射，确保后续 WebSocket 推送使用最新映射；`update_speaker_mapping` 同时更新内存映射和持久化到 `data/meeting_mappings.json`。

### 涉及文件
- `app/routers/record.py`：`handle_bind_speaker` 立即更新 `session.speaker_mapping`
- `core/diarization.py`：`update_speaker_mapping` 同步更新内存与持久化存储


## [v1.x-feature-flags] - 2026-09-07

### 新增
- **功能开关**：设置页新增「功能开关」卡片，支持用户停用/启用实时章节生成、实时总结生成、软件更新提示三项功能，默认全部开启。配置持久化到 `data/settings.json` 的 `feature_flags` 配置节，关闭后对应功能在录音/启动流程中跳过，不产生额外 API 调用。

### 涉及文件
- `data/settings.json`：新增 `feature_flags` 配置节
- `app/store.py`：新增 `get_feature_flags()` 辅助函数
- `app/routers/settings.py`：GET/POST 端点支持读写 `feature_flags`
- `app/routers/record.py`：根据开关控制实时总结器与章节生成器的创建与句子馁入
- `app/routers/chat.py`：AI 面板发起录音时同样受开关控制
- `app/static/index.html`：设置页新增功能开关卡片及对应 JS 逻辑


## [v1.x-sms-proxy] - 2026-09-07

### 新增
- **SMS 代理服务**（`sms-proxy/`）：独立 FastAPI 服务，部署于 <server-ip>:8080，持有云端服务密钥并调用短信 SDK，为客户端提供短信发送/核验中转。含签名校验（HMAC-SHA256 + 时间戳防重放）、systemd 部署脚本、完整 README。

### 变更
- **短信代理改造**：`core/sms.py` 从直调云端短信 SDK 改为 HTTP 调用云端代理（<server-ip>:8080），云端服务密钥从 `.env` 完全移除，密钥不落地。客户端通过 HMAC-SHA256 签名 + 共享密钥与代理通信，防未授权调用。
- **`.env` / `.env.example`**：移除云端短信服务相关配置，新增 `SMS_PROXY_URL` 和 `SMS_PROXY_TOKEN`。
- **依赖简化**：不再需要 `alibabacloud_dypnsapi20170525` SDK（代理端持有，客户端仅用标准库 `urllib` 发 HTTP 请求）。

### 决策
- 短信代理通信协议：POST JSON + `X-SMS-Timestamp` / `X-SMS-Sign` 请求头，签名有效期 5 分钟防重放。详见 ADR-0010。


## [v1.x-remote-config] - 2026-09-06

### 新增
- **远程配置系统**：管理后台可动态管理客户端横幅/公告消息，文案、展示条件、关闭策略均通过后台实时下发，无需发版。
  - `core/remote_config.py` — 消息 CRUD + 过滤逻辑，存储在 `data/remote_config.json`
  - `GET /api/config/announcements` — 客户端拉取当前有效消息（按 target 过滤、priority 排序）
  - `GET /api/config/version` — 配置版本号（增量刷新判断）
  - 管理后台 5 个 API：列表、创建、更新、删除、启用/禁用切换
- **消息管理后台 Tab**：管理后台前端新增「消息管理」标签页，支持消息列表、创建/编辑表单、启用/禁用开关、删除操作。
- **三种关闭策略**：`session`（会话级）、`delayed`（延迟 N 天重现）、`permanent`（永久关闭），替代原有的"关闭即永久消失"逻辑。

### 变更
- **`index.html` 横幅**：从硬编码文案改为远程拉取渲染，横幅内容（文案、按钮、链接）由管理后台动态配置。
- **`app/server.py`**：注册 config 路由模块。
- **`app/routers/admin.py`**：新增消息管理 CRUD 端点。

## [v1.x-cloud-deploy] - 2026-09-06

### 新增
- **云服务器部署**：云端轻量应用服务器（2核4G，Ubuntu 24.04，IP: <server-ip>），systemd 托管 Web 服务（8000）+ 管理后台（8001），开机自启 + 崩溃自动重启。
- **部署文档**：`docs/DEPLOYMENT.md` 记录服务器信息、端口、SSH、服务管理、代码更新流程、API 调用路径、systemd 配置。
- **部署脚本**：`scripts/deploy.sh` 一键部署脚本（系统依赖 + venv + pip install + systemd + 防火墙）。

### 架构
- 本地开发与云服务器各自独立调用云端 API，互不影响
- 代码在哪台机器运行，API 就从哪台机器发出

## [v1.x-voiceprint-cloud-split] - 2026-09-06

### 新增
- **声纹嵌入提取抽象层**（`core/embedding_provider.py`）：定义 `EmbeddingProvider` 接口，三个实现——`LocalCamPlusProvider`（本地 torch）、`CloudEmbeddingProvider`（HTTP 云端，暂不部署）、`MfccFallbackProvider`（14 维 MFCC 零依赖降级）。`get_embedding_provider()` 按 settings.json 配置自动选择，支持环境变量覆盖。
- **声纹配置管理**：`settings.json` 新增 `voiceprint` 配置节（`provider`/`cloud.base_url`/`cloud.api_key`），`GET/POST /api/settings` 已支持读写，API Key 脱敏处理。
- **兼容版本集合**：`COMPATIBLE_VERSIONS` 使本地 `cam++-v1` 与云端 `cam++-v1-cloud` 提取的 embedding 可互相匹配，注册表无需区分来源。

### 变更
- **`core/voiceprint.py`**：`extract_embedding()` 和 `extract_embedding_from_pcm()` 改为通过 provider 抽象层调用；新增 `extract_embedding_local()` 和 `extract_embedding_from_pcm_local()` 封装原始 CAM++ 推理代码，供实时链路直接调用。匹配侧（`match_voiceprint_detail`、`auto_identify_speakers`、`register_voiceprint`、`get_voiceprint_status`）统一改用 `_is_compatible_version()` 做版本兼容检查。
- **`core/diarization.py`**：`_extract_camplus_embedding()` 改为调用 `extract_embedding_from_pcm_local()`，实时链路始终走本地 CAM++，不受 provider 切换影响。
- **`app/routers/settings.py`**：GET/POST 端点新增 voiceprint 配置字段，保存后自动重置 provider 缓存。
- **ADR-0009** 状态从 Proposed → Accepted。

### 架构
- 批处理链路（voiceprint.py）→ provider 抽象层 → 本地/云端/MFCC 三选一
- 实时链路（diarization.py）→ 始终本地 CAM++（延迟敏感，不走 provider）
- 云端服务暂不部署，接口契约已在 ADR-0009 中定义

## [v1.x-admin-panel] - 2026-09-06

### 新增
- **独立管理后台（方案 B）**：同代码库、独立运行入口，与用户端服务完全隔离。管理后台默认监听 `127.0.0.1:8001`，不暴露到公网。
- **启动命令**：`python cli.py admin [--host 127.0.0.1] [--port 8001] [--reload]`，打包后为 `open-meeting-scribe.exe admin`。
- **管理员认证**：独立密码认证（`ADMIN_PASSWORD` 环境变量），独立 JWT cookie（`oms_admin_session`），与用户端 `oms_session` 完全隔离，互不干扰。
- **管理后台 API**（`app/routers/admin.py`）：
  - `POST /api/admin/login` — 管理员登录
  - `GET /api/admin/overview` — 系统概览（用户总数、档位分布、本月用量、最近注册）
  - `GET /api/admin/users` — 用户列表（支持搜索、档位筛选）
  - `GET /api/admin/users/{id}` — 用户详情（含 7 天用量历史）
  - `PUT /api/admin/users/{id}/subscription` — 修改订阅档位
  - `PUT /api/admin/users/{id}/status` — 禁用/启用账号
- **管理后台前端**（`app/admin_static/admin.html`）：单页应用，包含概览仪表盘、用户管理列表、用户详情面板、订阅修改、账号状态控制。
- **新增环境变量** `ADMIN_PASSWORD`（`.env.example` 已同步更新）。

### 架构
- `app/admin_server.py` — 独立 FastAPI 实例，与 `app/server.py` 共享 `core/` 层数据访问，但运行时完全独立。
- `cli.py` 新增 `admin` 子命令，与 `server` 子命令平级。

## [v1.x-sms-send-fix] - 2026-09-06

### 修复
- **短信验证码发送 500 崩溃**：`core/sms.py` 给 `SendSmsVerifyCodeRequest` 传了不存在的参数 `expire_time`（PNVS SDK 正确字段为 `valid_time`，映射到 API 的 `ValidTime`），导致 `TypeError` 在 try 块外抛出、端点返回 HTTP 500 纯文本，前端 `resp.json()` 解析失败误报「网络异常，请检查连接」。修正参数名，并将请求构造移入 try 块，使任何 SDK 异常统一转为 400 JSON。
- **前端错误提示区分**：`app/static/index.html` 新增 `_readSmsJson` 稳健解析响应，服务端返回非 JSON（如 500 纯文本）时降级为带 HTTP 状态码的提示，不再一律误报「网络异常」；发送与核验两处调用点均已切换。
- **回归测试**：`tests/test_smoke.py` 新增 `TestSmsSendHappyPath`，覆盖此前缺失的「有效号码 → 构造请求」关键路径，断言请求携带 `TemplateParam`/`CodeType`/`ValidTime`（秒）且 PNVS 错误返回 400 而非 500。
- **PNVS 发送缺失 TemplateParam 报 400（MissingTemplateParam）**：`SendSmsVerifyCode` 的 `TemplateParam` 为必填，验证码位须用占位符 `##code##`（由 PNVS 动态生成并托管，`CheckSmsVerifyCode` 方可核验），且传占位符时 `CodeType` 必填。新增 `SMS_TEMPLATE_PARAM`/`SMS_CODE_TYPE`/`SMS_CODE_LENGTH` 三个可配置项（同步 `.env.example`）。
- **ValidTime 单位修正**：PNVS 的 `ValidTime` 单位是「秒」（默认 300）而非分钟，上一轮误传 `5`（=5 秒），改为 `SMS_EXPIRE_MINUTES * 60`。
- **模板参数变量不匹配（请检查模板内容与模板参数是否匹配）**：赠送模板 `100001` 含 `${code}` 与 `${min}` 两个变量，上一轮默认只传 `{"code":"##code##"}` 漏了 `min`。默认 `SMS_TEMPLATE_PARAM` 改为 `{"code":"##code##","min":"<有效期分钟>"}`（min 动态同步 `SMS_EXPIRE_MINUTES`）；并在模板类错误时于返回信息附上当前 TemplateParam 与核对指引，便于自助排查。
- **核验恒判失败（验证码错误或已过期）**：`CheckSmsVerifyCode` 的核验结果只在 `Model.VerifyResult`（`PASS`=通过 / `UNKNOWN`=失败），且官方明确 `Code=OK`/`Success=true` 仅代表请求成功。旧代码误读不存在的 `body.pass_`/`body.Pass`，导致发送成功、验证码正确也恒判失败。改为读取 `body.model.verify_result == "PASS"`；新增 `TestSmsCheckVerifyCode` 三个用例覆盖 PASS/UNKNOWN/接口错误。

## [v1.x-sms-login] - 2026-09-06

### 新增
- **手机号短信验证码登录**：接入云端短信认证服务，支持个人账号无需企业资质。新增 `core/sms.py` 封装 `SendSmsVerifyCode` / `CheckSmsVerifyCode` 两个 API，内置 60 秒冷却 + 每天 10 次频率限制。
- **新增端点** `POST /auth/sms/send`（发送验证码）和 `POST /auth/sms/verify`（核验并登录），核验通过后签发 JWT 并设置 httpOnly cookie，与 GitHub OAuth 登录机制完全一致。
- **登录卡片 Tab 化**：前端登录页新增「GitHub / 手机号」双 Tab 切换，手机号 Tab 包含号码输入框、验证码输入框、60 秒倒计时发送按钮、错误提示区域。
- **SMS 用户模型**：`core/users.py` 新增 `find_or_create_sms_user`，用户 `provider="sms"`，`provider_id` 为手机号，默认名称为掩码手机号（如 `133****3103`）。
- **冒烟测试**：`tests/test_smoke.py` 新增 `TestSmsSendValidation` / `TestSmsVerifyValidation` 覆盖手机号格式校验和必填字段验证。

### 变更
- **requirements.txt**：新增 `alibabacloud-dypnsapi20170525` 和 `alibabacloud-tea-openapi` 两个 SDK 包。
- **.env.example**：新增 `ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`、`SMS_SIGN_NAME`、`SMS_TEMPLATE_CODE` 四个环境变量说明，同时补全 GitHub OAuth 和 JWT 配置模板。

## [v1.x-metering-ui] - 2026-09-06

### 新增
- **底部状态栏用量指示器**：进度条 + 剩余时长文本，颜色三级编码（绿 >50%、黄 20-50%、红 <20%）。非计量用户自动隐藏。
- **设置页「用量与订阅」面板**：档位徽章、月额度/已用/剩余三栏统计、进度条、最近 30 天用量柱状图（hover 显示详情）。三种状态：计量模式 / 自带 Key 模式 / 未登录。
- **自动刷新**：页面加载（checkAuth 后）、转写完成、录制结束、保存设置后均自动刷新状态栏额度。

### 变更
- **app/static/index.html**：状态栏新增 `#usageIndicator` 区域；设置页账户卡片下方新增用量卡片；JS 新增 `loadUsageSummary` / `loadUsagePanel` / `_renderUsageChart` / `_formatMinutes` 四个函数。

## [v1.x-metering-impl] - 2026-09-06

### 新增
- **用量计量引擎** `core/metering.py`：record_usage（JSONL 追加写入）、get_monthly_usage（按月汇总）、get_daily_history（逐日明细）、check_quota（配额预检）、is_metered（双轨判定）。数据存储在 `data/usage/usage-YYYY-MM.jsonl`。
- **用量查询 API** `app/routers/usage.py`：GET `/api/usage/summary`（状态栏）、GET `/api/usage/history`（图表）、GET `/api/usage/check`（预检）。
- **批量转写计量钩子** `app/store.py`：run_pipeline_task 转写完成后自动记录 audio_duration。
- **实时录制计量钩子** `app/routers/record.py`：stop_record 按录制时长记录用量。
- **配额预检**：录制开始（`/api/record/start`）和文件上传（`/api/transcribe`）前检查配额，额度用尽返回 402。
- **Key 来源标记** `app/store.py`：get_asr_config() 返回 `source` 字段（"platform" | "user"），用于计量判定。
- **订阅管理** `core/users.py`：get_user_subscription / set_user_subscription，新用户默认 tier="free"。

### 变更
- **app/server.py**：注册 usage router（第 13 个路由模块）。
- **app/routers/settings.py**：GET /api/settings 返回 asr.source 字段。

## [v1.x-metering-decision] - 2026-09-06

### 决策
- **USAGE_METERING_DESIGN.md 开放问题已决策**：①实时转写先按录制时长计量；②体验版额度用尽后允许配置自有 Key；③团队版**先扣团队共享池，超出后扣个人额度**（与原建议相反）；④按月度额度处理、跨月清零；⑤v1 不做风控，先观察数据分布。

## [v1.x-doc-sync] - 2026-09-06

### 文档
- **全面复盘代码与文档一致性**：遍历 `core/`、`app/routers/`、`app/server.py`、`app/store.py` 等核心代码，对比所有说明性文档，修正 28 处不同步问题。
- **CODEX.md**：版本号 v0.25 → v1.x；技术栈 resemblyzer → torch/torchaudio(CAM++)；前端行数 6500 → ~14700；diarization.py 描述更新（CAM++ 192维 + VAD）；RealtimeASRClient → RealtimeTranscriber；voiceprint.py/projects.py/users.py 关键函数更新；server.py 行数 <100 → ~210；路由表补充 philosophy.py/auth.py；数据目录补充 uploads/hotword_mappings/voiceprint_registry/users/settings；新增 errors.py/joblog.py/auth.py 模块条目。
- **docs/ARCHITECTURE.md**：分层表新增 10 个模块（实时转写/实时分离/实时总结/说话人/项目/用户/认证/错误处理/路由/共享状态）；依赖列表补充 httpx/python-docx/PyPDF2/PyJWT；明确标注 resemblyzer 已移除。
- **docs/PRD.md**：功能清单从未实现改为已完成（[x]）；声纹姓名化从非目标移除并标记 ✅。
- **MISSION.md**：技术路线从 FunASR/pyannote/WeSpeaker 更新为 DashScope paraformer-v2/CAM++；核心组件选型表全面更新；MVP 清单标记已完成项；当前状态从「原型设计」更新为「v1.x 迭代开发」。
- **MVP_PLAN.md**：目录结构全面更新（新增 15+ 文件/目录）；P3 声纹姓名化从「开发中」改为 ✅ 已完成；WeSpeaker → CAM++。
- **docs/ROADMAP.md**：M1 实时聚类升级标记 ✅；多个迭代计划项去掉「规划中」标签。
- **docs/GLOSSARY.md**：声纹条目从 v3 更新为 v4（CAM++ 192维嵌入）。
- **app/server.py**：头部注释补充安全审计中间件职责；voiceprint 版本 V3 → V4 CAM++。

## [v1.x-sel-toolbar-position-fix] - 2026-09-06

### 修复
- **选中操作条定位异常**：浮动选中操作条（引用到 AI / 改写 / 总结 / 提取待办）在某些场景下 `range.getBoundingClientRect()` 返回零值 rect，导致工具栏被定位到页面左上角 `(8, 8)`。新增 `rangeCount` 安全检查，并在 rect 无效时回退使用 anchor 元素的位置进行定位。

## [v1.x-auth-phase1] - 2026-09-06

### 新增
- **GitHub OAuth 登录**：新增 `core/auth.py`（OAuth 流程 + JWT 管理）和 `app/routers/auth.py`（`/auth/github`、`/auth/callback`、`/auth/me`、`/auth/logout`），支持通过 GitHub 账号登录。
- **JWT 会话管理**：登录后签发 httpOnly cookie（`oms_session`），7 天有效期，前端不直接操作 token。
- **登录界面**：未登录时显示登录遮罩层，登录后在 topbar 显示用户头像和下拉菜单（含退出登录）。
- **用户数据模型升级**：`users.json` 从单用户结构迁移为多用户数组结构（`users[]` + `current_user_id`），支持 OAuth 用户（provider、provider_id、avatar_url 等），旧数据自动迁移。
- **新增依赖**：`PyJWT>=2.8.0`。

### 决策
- 认证架构详见 `docs/adr/0006-认证与订阅架构.md` 和 `docs/AUTH_DESIGN.md`。
- 第一期仅实现 GitHub OAuth，后续扩展 Google 和微信。
- 当前不强制登录（前端检查但后端 API 未加认证中间件），后续逐步添加。

## [v1.x-ai-panel-collapse-fix] - 2026-09-05

### 修复
- **AI 面板折叠/展开布局问题**：折叠时 `conv-canvas-center`（聊天画布）未隐藏，导致内容被挤压到 44px 宽度内造成布局错乱；已将其加入折叠隐藏列表。
- **折叠宽度不稳固**：`.ai.is-collapsed` 缺少 `max-width` 约束，内容可能撑开面板；新增 `max-width: 44px !important` 确保折叠宽度稳定。
- **折叠动画不完整**：过渡效果仅覆盖 `flex-basis`，`min-width` 变化无动画；现已同步添加 `min-width` 过渡。
- **折叠按钮层级不足**：`.ai-toggle` 的 `z-index` 从 10 提升至 20，确保按钮始终可点击。

## [v1.x-speaker-count-fix] - 2026-09-05

### 修复
- **说话人计数修正**：`speaker_count` 原本误用 `len(dialogue)`（对话条目总数），改为从 dialogue 中提取 `speaker_id` 去重集合长度，正确反映实际说话人数。
- **历史数据自动迁移**：`load_tasks_from_disk()` 启动时扫描所有已有任务文件，若 `speaker_count` 与去重说话人数不一致则自动修正并回写磁盘，日志输出修正数量。

## [v1.x-divider-visual-removed] - 2026-09-05

### 变更
- **分隔条移除悬停视觉反馈**：去掉鼠标悬停时分隔线的 accent 色加粗发光、握柄圆点（.divider-grip）、追踪涟漪点（.tracking-dot）、模式标签（.mode-badge）、滚动指示条（.scroll-indicator）、宽度提示（.width-tooltip）等全部装饰效果；分隔条仅保留 1px 静态边框线作为面板分隔，拖拽调整宽度功能不受影响。

## [v1.x-sidebar-filter-collapse] - 2026-09-05

### 新增
- **侧边栏头部增加筛选与折叠按钮**：头部最左侧新增面板折叠按钮（点击收起整个侧边栏，左边缘出现浮动展开按钮可恢复）；「全部折叠」右侧新增「筛选」按钮，点击展开搜索行，支持输入关键词实时过滤时间轴会议列表，并提供「重置」一键清空筛选并关闭搜索行。

## [v1.x-divider-no-collapse] - 2026-09-05

### 变更
- **分隔条取消单击折叠/展开**：左右分隔条从「拖动调宽 / 单击折叠 / 拖动或滚轮滚动」三合一收敛为两合一，单击不再触发任何面板折叠，避免误触。面板显隐统一由顶栏视图切换（全视图 / 资源视图 / 对话视图）承担。
- **移除右侧 AI 面板折叠态**：删除 `ai-collapsed` 窄轨模式（48px 竖排「AI 助手」标签）及配套 CSS、`toggleAiPanel()`、视图切换中的 `expandAiPanel()` 强制展开逻辑；`setView` 去掉已无意义的 `opts.enforce` 参数。≤1200px 断点改为直接隐藏 AI 面板与其分隔条。
- **清理分隔条死代码**：删除 `mode-click` 徽标样式与 `collapse-flash` 闪烁动画、`_toggleCollapse` / `_isCollapsed` / `isAiCollapsed` 及点击判定常量（`CLICK_MAX_MOVEMENT` / `CLICK_MAX_DURATION`）与 `startTime` / `currentX` / `currentY` 状态；`initTripleDivider` 更名为 `initLayoutDividers`。

### 文档
- `docs/design/ui-spec.md`：顶栏「面板切换」改为「视图切换」；§6.1 新增分隔条交互说明并修正 ≤1200px 断点描述。

### 验证
- `node --check` 校验内联脚本语法通过；全文已无 `toggleAiPanel` / `ai-collapsed` / `ai-rail` / `collapse-flash` 残留引用；拖动调宽与滚动联动逻辑保持不变。

## [v1.x-sidebar-header-textbtns] - 2026-09-05

### 变更
- **侧边栏头部改文字式操作按钮**：去掉「全部会议」标题；两个纯图标按钮改为「图标 + 文字」文字式按钮并右对齐。「全部折叠/全部展开」按钮文字与图标随全局折叠态联动切换（展开态显示「全部折叠」+ 内向箭头，全折叠态显示「全部展开」+ 外向箭头）；筛选按钮图标改为三横线式。头部底部加分割线与列表区隔开；筛选浮层下移至分割线下方，不被遮挡。
- **折叠态联动与保持**：手动折叠/展开单个日期组后自动同步全局状态（全组折叠才记为全折叠态并刷新按钮）；历史列表刷新重建日期组后继承全折叠态，折叠状态不再丢失。

### 验证
- 浏览器实测：按钮触发全部折叠/全部展开、手动逐组折叠后按钮自动切换，均正常；console 零报错。

## [v1.x-notes-tab-reload] - 2026-09-05

### 修复
- **录音笔记在会议完成后「笔记」Tab 看不到**：实时录音期间录入的笔记，停止后后端已正确写入 `tasks[].user_notes` 并落盘（`GET /api/tasks/{id}/notes` 实测正常返回），但完成页「笔记」Tab 空白。根因是笔记加载为一次性、无兜底——`loadTaskNotes()` 仅在 `showCompleted()` 中以 fire-and-forget（`async` 未 `await`）方式调用一次，而 `switchGenTab('notes')` 不像待办 Tab 那样重载；该次异步回填一旦遇到 `currentTaskId` 竞态或多会议来回切换未落到输入框，笔记便永久空白。修复：`switchGenTab` 增加 `if (tab === 'notes') loadTaskNotes();`，与待办 Tab（`loadTaskTodos`）对称，每次切入笔记 Tab 都从后端拉取最新 `user_notes`，同时因切换时 `currentTaskId` 已稳定而消除竞态（`app/static/index.html`）。

## [v1.x-breadcrumb-nav] - 2026-09-05

### 新增
- **会议纪要面包屑导航**：工具栏左侧新增进入链路展示，显示用户从何处进入当前会议（全部会议 / 项目 / 说话人），点击上游节点可返回对应视图。支持三种进入方式：侧边栏/库视图（默认"全部会议"）、说话人详情页（显示"说话人 / 姓名"）、项目详情页（显示"项目 / 项目名"）。
- **工具栏按钮布局调整**：复制按钮移至右侧，与导出、全屏并列；左侧仅保留面包屑导航。

### 变更
- 新增 `navCrumbs` 状态变量和 `setNavContext` / `renderBreadcrumb` 函数，在各入口点（`loadTask`、`openTaskFromSpeaker`、侧边栏点击、库视图点击、悬停卡片打开）设置导航上下文。
- 在 `showCompleted`、`showMeetingProcessing`、`showGenError`、`showSpeakerBinding` 中调用 `renderBreadcrumb()` 渲染面包屑。

## [v1.x-toolbar-more-menu] - 2026-09-05

### 变更
- **纪要工具栏按钮精简**：外部可见操作只保留"看"类与"分享"类（复制、导出、全屏），"编辑"类操作（编辑、重新识别）收入"更多"下拉菜单。删除冗余的 `genBtnRetranscribe2` 按钮及其全部 JS 引用。

## [v1.x-tab-memory-fix] - 2026-09-05

### 修复
- **会议 Tab 记忆覆盖生成完成落点（回归）**：按会议记忆 Tab（`meetingTabState`）上线后，任务从「处理中」轮询到 `completed` 时也走记忆恢复，用户在等待期间点过「转写」，纪要生成完毕便停在转写页看不到结果（改造前总是跳「纪要」）。修复：`pollTask` 的 completed 分支先 `delete meetingTabState[currentTaskId]` 再 `showCompleted`，即 Tab 记忆只服务「侧边栏来回切换会议」，不覆盖状态跃迁的自然落点（`app/static/index.html`）。
- **`updateSpkBatchBar` 抛 `TypeError: visibleRows.every is not a function`**：`$$` 是 `document.querySelectorAll` 别名，返回 NodeList，只有 `forEach` 没有 `every`。异常沿 `renderSpeakersManageList` 冒泡到 `loadSpeakers` 的 catch，导致初始化在 `backToSpeakerList()` 前中断（控制台报「加载说话人失败」），且全选框与行勾选状态永不同步、`toggleSpkSelectAll` / `toggleSpkRowSelect` / `clearSpkSelection` 全部抛错。修复：`Array.from($$(...))` 后再 `every`，与文件内既有 `Array.from(palette.querySelectorAll(...))` 写法统一。

### 变更
- `deleteTask` 删除会议时清理 `meetingTabState[taskId]`，避免已删任务的 Tab 记忆残留。

### 验证
- 浏览器实测 13 项全通过：页面加载 console 零报错；说话人页全选→行取消勾选后全选框自动回退 false；会议 A 切「转写」→ 会议 B → 切回 A 仍停在「转写」；模拟轮询 completed 分支后 Tab 由 `transcript` 强制回落 `summary`。
- `node --check` 校验整段内联脚本无语法错误；全文件复查无其他 NodeList 误用数组方法。

## [v1.x-chat-verified-actions] - 2026-09-05

### 修复
- **AI 回复幻觉操作声称**：此前数据修改类请求（如「待办中参会人A应该是参会人B」）没有执行通道，LLM 凭空声称「已修正、纪要已同步更新」，后端从未写入、界面也不刷新。现按 ADR-0008 重构：执行权与叙述权分离，操作结果以系统校验为唯一事实源。

### 新增
- **待办编辑意图解析与执行校验**（`app/routers/chat.py`）：编辑类消息经门槛关键词预过滤后，由低温度 LLM 解析为结构化操作（白名单：待办责任人/内容/完成状态/删除），`_sanitize_edit_ops` 过滤越权操作；`_execute_and_verify_edits` 执行后**回读磁盘逐条校验**，产出带 `verified` 标记的变更清单并写入 joblog。
- **回复事后审计** `_audit_reply_claims`：扫描回复中的操作声称词。有变更 → 回复尾部追加「✅ 系统校验（本轮执行结果，磁盘回读确认）」清单；无变更却含声称 → 追加「⚠️ 系统校验：本轮未执行任何写操作」提示。审计结论由系统生成，不依赖 LLM 自觉。
- **系统提示词「操作权限边界」**：最高优先级规范——AI 无执行权，操作结果只能引用「系统动作执行结果」块，禁止复述待办/纪要全文。
- **界面同步**：`/api/chat` 响应新增 `verified_changes` 字段；前端收到非空变更清单后自动刷新待办 Tab 与本地任务缓存，界面与真实状态一致。

### 变更
- 编辑轮跳过关键词动作检测（避免「待办」关键词误触发 extract_todos 叠加动作）；编辑轮回复不再产出注入候选（避免改写后的待办被当作新待办注入）。

### 验证
- 49 个冒烟测试全部通过（新增 6 个：执行校验、删除校验、无变更、操作白名单、回复审计、端点端到端）

## [v1.x-speaker-locate] - 2026-09-05

### 新增
- **说话人绑定栏「定位」功能**：在"识别说话人"界面（等待绑定态），绑定栏每个已识别说话人新增定位图标（`app/static/index.html`）。点击后自动切到「转写」Tab、滚动到该说话人的第一条发言，并进入聚焦模式——高亮本人全部发言、淡化其他人，便于在多人会议中快速定位指定说话人；再次点击同一说话人取消定位。原有"点击说话人绑定姓名"的交互完全保留（定位图标 `stopPropagation`，不触发绑定下拉）。
- 转写行 `.bt-line` 增加 `data-speaker-id` 属性作为定位检索依据；`renderBindingTranscript` 重渲染时重置定位状态，避免残留高亮。

## [v1.x-diarization-merge] - 2026-09-05

### 修复
- **`SpeakerProfile.avg_feature` 缺失 L2 归一化（过度分裂根因）**：单个 CAM++ 嵌入是 L2 归一化的单位向量，但 `avg_feature` 取均值后不再是。`_match_speaker` 用 `np.dot(feature, avg)` 当余弦相似度，要求双方都是单位向量。未归一化导致点积系统性偏低 → 有效阈值被抬高 → 同一说话人被拆成多个簇。修复：均值后重新 L2 归一化，与 `voiceprint.py::merge_embeddings` 做法统一。
- **方案 C 将 `speaker_count=None` 误判为 <2**：`pipeline.py` 的兜底条件 `speaker_count is None or speaker_count < 2` 将"未知，交给 API 自动估计"的 None 等同于"< 2"并强制替换为 2，对多人会议造成回归（4 人被钉死成 2 人）。修复：仅在 `speaker_count` 明确给出且 < 2 时干预，None 保持透传。
- **CAM++ 嵌入时间漂移导致过度分裂**：实测同说话人相邻窗口余弦 0.79，但跨时段（前 14s vs 后 28s）仅 0.174。贪心聚类用初始帧建立档案后，同说话人后来的嵌入 drifted away 被当成新说话人。新增 `SpeakerDiarizer.finalize()` 后处理合并：录音结束后比较所有簇质心，将余弦相似度 > 0.40 的簇迭代合并。实测 853fa856（46s，真值 2 人）从贪心 6 人降到合并后 2 人，命中真值。

### 新增
- **`SpeakerDiarizer.finalize()` 方法**：执行后处理合并并返回最终说话人数量。录音停止时（`record.py`）和离线估算时（`store.py::estimate_speaker_count`）显式调用，录音期间不触发（避免过早合并正在形成的簇）。
- **谱聚类辅助离线估算**：`estimate_speaker_count()` 新增谱聚类（eigengap 启发式）路径：提取采样片段特征 → 构建余弦相似度矩阵 → 归一化图拉普拉斯 → 特征值 eigengap 自动确定最优 k。与贪心聚类交叉验证，谱聚类信号强时优先采信。轻量实现仅依赖 scipy（不引入 sklearn）。

### 验证
- 43 个冒烟测试全部通过
- 853fa856（46s，真值 2 人）：贪心 6 → 合并 2 ✅
- 03c74e81（700s，多人会议）：贪心 4 → 合并 2

## [v1.x-diarization-upgrade] - 2026-09-05

### 变更
- **实时声纹聚类升级：MFCC 14维 → CAM++ 192维神经声纹**（方案 A）。`core/diarization.py` 的 `extract_speaker_feature()` 优先调用 `voiceprint.extract_embedding_from_pcm()` 提取 CAM++ 嵌入，区分度提升一个量级。CAM++ 不可用时自动降级为 MFCC（向后兼容）。相似度阈值从 0.65 调整为 0.55（适配 192 维空间），特征窗口从 1.5s 增至 2.5s（CAM++ 需要更长的音频段）。
- **VAD 前置过滤**（方案 B）。新增 `_is_speech()` 能量阈值 VAD，RMS < 0.01 或时长 < 0.8s 的音频段跳过特征提取，避免静音段产生噪声聚类。新增 `get_vad_stats()` 调试接口。
- **批处理说话人分离兜底**（方案 C）。`core/pipeline.py` 的 `run_pipeline_stage1()` 中，当音频时长 > 30 秒但估算说话人数量 < 2 时，强制传 `speaker_count=2` 给云端 ASR，确保长音频至少尝试 2 人分离。

### 修复
- **说话人未被识别**：根因为 MFCC 14维特征区分度不足 + speaker_count=1 时 DashScope 不做分离。三方案联合修复：CAM++ 提升实时聚类精度 → VAD 减少噪声 → 兜底确保批处理不遗漏。

## [v1.x-camplus-encoder] - 2026-09-04

### 变更
- **声纹编码器升级：resemblyzer GE2E → CAM++**（v3 → v4）。CAM++ 基于 FunASR CAMPPlus 实现（MIT License），权重来自 ModelScope `iic/speech_campplus_sv_zh-cn_16k-common`（28MB，中文语料训练）。嵌入维度 256 → 192（L2 归一化），对中文说话人判别力显著优于英文训练的 GE2E。实现放在 `core/models/cam_plus.py`，自包含、仅依赖 torch + torchaudio，剥离 funasr 重依赖链。
- **注册表加 `model_version` 字段**（当前 `cam++-v1`）。匹配侧自动忽略版本不一致的记录，避免跨 encoder 的不可比向量污染结果；注册侧遇到旧版本记录时强制覆盖（不累积），保证语义一致。
- **匹配算法升级：逐人独立匹配 → per-meeting 统筹分配**。同一会议所有说话人共享录音信道（同一麦克风/线路），embedding 含公共信道分量导致人间相似度偏高。新算法：① 提取所有说话人嵌入后减均值（per-meeting 中心化），消除信道公共分量；② 用匈牙利算法（`scipy.optimize.linear_sum_assignment`）做最优一对一分配，保证不会把两个 ASR 说话人分给同一个注册人。中心化空间中绝对相似度不可比，接受准则改为仅看 margin（最佳与次优的差距）。
- **移除 GE2E 时代的补丁代码**：旧版 cohort centering（减注册表均值）、`RAW_*` / 中心化双阈值、`CENTERING_MIN_SPEAKERS` 等。
- **依赖调整**：`requirements.txt` 移除 `resemblyzer`，新增 `torch` + `torchaudio`；卸载 `funasr`（仅用于参考架构，未实际使用）。

### 修复
- **`register_from_binding` 空路径保护**：`audio_path` 为 None 时返回 `audio_unavailable` 而非崩溃。
- **`extract_embedding` 防御性类型转换**：int16 输入自动转 float32，避免 torchaudio fbank 报错。

### 迁移
- 用 `scripts/backfill_voiceprints.py` 全量重建注册表：10/11 条记录升级到 `cam++-v1`（1 条因源会议音频缺失保留 legacy，下次参与会议时自动覆盖）。

### 文档
- `docs/ARCHITECTURE.md`：声纹层描述更新为 CAM++，依赖列表更新。
- `docs/ROADMAP.md`：新增 v4 · CAM++ 声纹编码器升级 ✅；M1 实时聚类升级改用 CAM++。

## [v1.x-auto-todo-extract] - 2026-09-04

### 修复
- **待办自动提取**：纪要生成后自动从 Markdown 中解析 `- [ ] **负责人**：任务描述（截止日期）` 格式的待办事项，写入 `task["todos"]`。此前纪要虽包含待办章节，但无代码将其解析为结构化数据，导致前端待办 Tab 始终为空。新增 `core/summarize.py::parse_todos_from_summary()`，在 `app/store.py::_run_stage2_for_task()` 纪要完成后调用。支持负责人提取、截止日期提取、去重、跳过已完成项。
- **历史数据回填**：新增 `scripts/backfill_todos.py` 一次性脚本，为修复前已完成的会议纪要回填待办。已为 2 个会议回填 9 条待办（税务研讨会 5 条、预付款讨论 4 条）；1 个会议纪要内容过短无待办可提取。

### 测试
- 新增 `TestParseTodosFromSummary` 6 个冒烟测试（含负责人/截止日期/无负责人/去重/空输入/跳过已完成）。

## [v1.x-joblog-context] - 2026-09-04

### 新增
- **per-task 作业日志层 `core/joblog.py`**：以 task_id 为键的 append-only JSONL（`data/tasks/{id}.joblog.jsonl`），记录录音/转写/声纹匹配/绑定/纪要生成/助手动作的关键操作与运行事件（`ts/stage/level/message/detail`）。作业日志从属于会议纪要，使会议助手能对应到该会议此前发生过的操作与运行痕迹。写入失败静默降级，不打断主链路。
- **会议助手作业日志渐进式上下文（chat 维度 2.5）**：仅当问题涉及操作/运行/流程/故障（`JOBLOG_INTENT_KEYWORDS` 门控，即"某些情况"）才注入；注入分两层——先轻量概要（阶段计数 + 最近事件），再按问题检索相关明细（stage 触发词 + 子串命中，限条数），避免全量日志塞入提示词。

### 变更
- **关键节点埋点**：`app/store.py` 管线 stage1/stage2（开始/完成/重试/失败）、声纹匹配（命中/0 命中降级/异常）、等待手动绑定；`app/routers/speakers.py` 确认绑定（含姓名）；`app/routers/chat.py` 助手动作执行结果（成功/失败）。不记 HTTP 与逐句转写噪声。
- **文档**：`docs/ARCHITECTURE.md` 分层表新增作业日志层并补充从属/渐进式说明；新增 `docs/adr/0007` 记录 per-task 作业日志与渐进式上下文决策。

### 测试
- 新增作业日志写入/读取、概要/检索、渐进式上下文、意图门控 4 个冒烟测试（合计 39 个）。

## [v1.x-voiceprint-cross-meeting-rebuild] - 2026-09-04

### 新增
- **跨会议声纹重建端点 `POST /api/voiceprint/rebuild/{speaker_uuid}`**：人员独立于会议记录——扫描该说话人参与的所有已完成会议（按 `speaker_uuid_mapping` 反查），从每场会议的归一化音频中按其发言时间段提取声纹嵌入，均值融合后整体覆盖注册表（`sample_count` = 参与会议数）。此前说话人详情页「注册/更新声纹」只取发言最长的**单场**会议音频，声纹被绑死在一个录音文件上；现改为聚合全部已绑定会议，抑制单场录音的信道偏置。实测基于 2 场会议、共 222.6s 发言重建。

### 变更
- **前端「注册/更新声纹」改调重建端点**：删除前端单会议挑选与时间段计算逻辑（约 80 行），聚合逻辑收敛到后端；按钮反馈显示「已基于 N 场会议更新 ✓」。
- **`core/voiceprint.py` 提取复用函数**：新增 `extract_speaker_embedding`（单会议单人嵌入提取）与 `merge_embeddings`（多嵌入均值融合）；`register_from_binding` 改为复用前者，消除重复的截断/拼接逻辑；`register_voiceprint` 新增 `sample_count` 显式入参（重建时一次写入多场样本数）。
- **归一化音频路径推导收敛**：`app/routers/voiceprint.py` 新增 `_resolve_normalized_path`，重建端点与任务级匹配端点共用。
- **测试**：新增跨会议重建聚合、无足够音频 400、说话人不存在 404 三个冒烟测试（合计 35 个）。

## [v1.x-mapping-count-guard] - 2026-09-04

### 修复
- **彻底移除历史会议映射自动绑定说话人**：此前声纹匹配失败后，`loadLatestMappingSuggestion` 会从 `meeting_mappings.json` 取最近一次会议的 speaker_id→姓名映射，按 speaker_id 数值自动补填到当前会议。但 DashScope paraformer-v2 的 speaker_id 按发言顺序/音量分配，跨会议完全不稳定（speaker_id=0 在不同会议中可能是完全不同的人），导致错误绑定（如将"苗文娟"误绑到当前说话人）。现已完全移除 `loadLatestMappingSuggestion` 函数及其调用，说话人绑定仅依赖声纹自动匹配——匹配成功则自动填入，匹配失败则由用户手动绑定，不再使用任何历史数据。

## [v1.x-chat-reparse-actions] - 2026-09-04

### 新增
- **AI 对话支持「重新解析音频」与「重新生成纪要」动作**：在 `ACTION_REGISTRY` 新增 `retranscribe`（关键词：重新解析/重新识别/重新转写/重新处理音频）和 `retry_summary`（关键词：重新生成纪要/重新总结/重新写纪要）两个动作。用户通过右侧 AI 对话框说"那就重新解析音频"即可触发后台重新跑管线，无需手动操作。执行逻辑复用 `run_pipeline_task` / `run_stage2_task`，以 daemon 线程后台运行。

## [v1.x-voiceprint-centering] - 2026-09-04

### 修复
- **声纹通道空转（自动绑定退化为历史映射）**：注册表已有 8 人、resemblyzer 正常工作，但每场会议均 0 命中——被上一版引入的次优优势门槛全部拦下（实测 best=0.915/margin=0.002、best=0.923/margin=0.018 < 0.02）。根因是原始 d-vector 在同一路内录音频上判别力极差：不同人余弦高达 0.970，与同人得分完全重叠，绝对阈值 0.75 形同虚设，放宽门槛即误判、收紧即空转。
- **注册与匹配样本长度不一致**：注册侧截断单人前 180s，匹配侧却拼接全量发言（长会议十余分钟）。d-vector 是全段平均，长度差异让嵌入不可比，同人相似度被显著压低。现两侧共用 `_cap_segments` 与 `MAX_SEC_PER_SPEAKER`，回测 margin 从 0.405~0.836 提升至 0.468~0.819 且自匹配全为 1.000。
- **未命中时相似度被归零**：`voiceprint_match` 中 unmatched 一律记 `similarity: 0.0`，掩盖真实分数，无法判断是"分数不够"还是"提取失败"。现保留真实 best 分数、`margin` 与 `best_candidate`（低置信候选，仅供人工参考）。
- **旧任务声纹匹配接口 400**：`POST /api/voiceprint/tasks/{id}/match` 对重启前创建的任务因缺 `normalized_path` 直接 400。现按命名约定推导归一化音频并回填任务。

### 变更
- **中心化比对（cohort centering）**：匹配前减去注册表均值向量再 L2 归一化。注册表人间最大相似度由 0.970 降至 0.595，本人自匹配 1.000。阈值随空间重标为 `MATCH_THRESHOLD=0.55` / `MIN_MATCH_MARGIN=0.08`；注册人数 < `CENTERING_MIN_SPEAKERS=3` 时均值不可靠，退化为原始余弦并沿用旧阈值（`RAW_MATCH_THRESHOLD=0.75` / `RAW_MIN_MATCH_MARGIN=0.02`）。
- **多样本累积注册**：`register_voiceprint(accumulate=True)` 按样本数加权平均而非整体覆盖，多场会议样本可逐步抵消单场录音的信道偏置，提升跨会议判别力。
- **测试**：新增中心化命中/模糊拒绝、人数不足退化、多样本累积 3 个冒烟测试（合计 32 个）。

### 回测结论
9 人注册表下，三场会议全部已确认绑定的说话人 **100% 命中本人**（e6cda37b 6/6、703ff5db 2/2、ef3f6b76 1/1）；未注册的说话人被正确拒绝（0.316~0.410），无跨人误判。

## [v1.x-ffmpeg-stdin-guard] - 2026-09-04

### 修复
- **SIGTTIN 进程组挂起**：`core/audio.py` 中 5 处 ffmpeg/ffprobe subprocess 调用未重定向 stdin。服务以后台进程组运行时，音频归一化阶段 ffmpeg 读取控制终端触发 SIGTTIN，整个进程组被挂起，表现为页面卡在"正在上传"、API 无响应、进程 STAT=T。现全部显式 `stdin=subprocess.DEVNULL`。
- **watchdog 崩溃循环**：watchdog 启动终端被回收后其 fd 0 失效（revoked），此后每次拉起服务均在解释器 `init_sys_streams` 阶段 EBADF 即死，自愈能力失效且 2 秒一轮空转。启动命令改为 `nohup bash scripts/watchdog.sh >> logs/watchdog.log 2>&1 < /dev/null &`，服务 fd 0 落 `/dev/null`。

### 变更
- **watchdog 自愈增强**（`scripts/watchdog.sh`）：脚本内 `exec </dev/null` 自保险，不再依赖启动命令写法；新增健康检查循环，curl `/` 连续 3 次失败（约 15s）即判定服务"活着但不响应"（挂起等），强杀重启——补齐旧 watchdog 只在进程退出时自愈、无法感知挂起的缺口。

## [v1.x-voiceprint-auto-register] - 2026-09-04

### 修复
- **声纹自动注册闭环**：此前声纹注册表（`data/voiceprint_registry.json`）无自动写入路径（仅说话人详情页手动注册），导致自动匹配永远空命中，绑定页的"自动绑定"实际按 speaker_id 位置复用上次会议映射（跨会议不稳定），产生跨会议身份混淆。现用户点击「确认并生成纪要」后，后台按确认绑定逐人提取声纹注册/更新（`core/voiceprint.py::register_from_binding`），后续会议可真正按声纹特征自动匹配并写入任务上下文（`voiceprint_match` / `voiceprint_auto_mapping`）。

### 变更
- **绑定页建议机制**：改为先声纹自动匹配、上次会议映射仅为未命中且未绑定的说话人补填建议，并明确提示"非声纹确认、需人工核对"；`auto_identify_speakers` 在注册表为空时直接返回，避免对长音频做无意义的嵌入提取。
- **测试**：新增声纹自动注册闭环、空注册表跳过 2 个冒烟测试（注册表临时目录隔离 + mock 嵌入提取，不加载重模型）。

## [v1.x-voiceprint-backfill] - 2026-09-04

### 新增
- **声纹回溯采集脚本**（`scripts/backfill_voiceprints.py`）：扫描已完成且带确认绑定的任务，按绑定从归一化音频补录声纹。首次回溯两场会议共 8 人（说话人 S1、说话人 S2、说话人 S3、说话人 S4、说话人 S5、说话人 S6、说话人 S7、说话人 S8），注册表自此可用，回测绑定命中 8/8。
- **匹配次优优势门槛**（`MIN_MATCH_MARGIN = 0.02`）：同通道内录音频下不同人余弦相似度实测可达 0.97，仅靠绝对阈值 0.75 会误判；现要求最佳匹配显著优于次优候选才接受，回测中 3 条 0.94~0.96 的跨人误判被拦截。

### 修复
- **normalized_path 持久化**：stage1 完成后写入任务字典（此前仅局部变量），绑定后声纹补录闭环与回溯脚本依赖该字段；旧任务缺失时按命名约定（原文件名 + `_normalized.wav`）推导兜底。
- **注册音频截断**（`max_sec_per_speaker` 默认 180s）：d-vector 在数分钟音频上已稳定，截断避免长会议注册/提取的分钟级 CPU 消耗。

### 测试
- 新增次优优势门槛冒烟测试（两人注册表余弦 ≈0.96，中间查询被拒绝）。

---

## [v1.x-security-audit] - 2026-09-04

### 新增
- **开发阶段安全审计体系**：双层监控，实时中间件 + 离线扫描脚本。
  - **审计中间件**（`app/server.py`）：所有 HTTP 请求记录到 `logs/audit.log`（IP、方法、路径、状态码、耗时）；自动检测可疑行为（路径遍历 `../`、敏感文件探测 `.env/.git/.ssh/.aws`、URL 中泄露的 API Key）并标记告警；4xx/5xx 错误单独记录 WARNING 级别。
  - **离线扫描器**（`scripts/security_audit.py`）：支持扫描 `server.log` 或 `audit.log`，检测 API Key 明文泄露、堆栈暴露、路径遍历、异常访问频率、错误激增等 6 类安全隐患。支持 `--watch` 持续监控模式、`--since 1h` 时间范围过滤、`--file` 指定日志文件。

---

## [v1.x-gen-toolbar-simplify] - 2026-09-04

### 变更
- **会议纪要顶部菜单精简**：移除 gen-toolbar 左侧重复标题（"录音纪要"），工具栏去掉背景色和底边框，视觉降级退至内容之后。操作按钮从 7 个平铺精简为 2 个常驻（编辑、导出与分享）+ 1 个"更多"下拉菜单（复制、全屏、重新生成纪要、重新识别）。下拉菜单支持点击外部关闭。移除冗余的 `genToolbarTitle` 元素，所有标题显示统一由顶部导航栏 `currentTaskTitle` 承担

---

## [v1.x-meeting-date-editable] - 2026-09-04

### 新增
- **支持修改会议纪要日期**：录音文件上传场景下，会议日期默认为上传日期，用户可在详情页点击日期弹出日期选择器修改为实际开会日期。新增 `meeting_date` 字段（`YYYY-MM-DD`），后端 PATCH `/api/tasks/{task_id}` 支持更新；前端所有日期显示位置（左侧列表、悬停卡片、分组逻辑、会议库表格、详情元信息行）统一从 `meeting_date` 读取，兜底 `created_at`。已有任务自动迁移（启动时从 `created_at` 提取日期填充 `meeting_date`）。纪要生成也优先使用 `meeting_date` 作为会议时间

---

## [v1.x-table-squeeze-guard] - 2026-09-04

### 新增
- **全局表格防挤压机制**：表头与数值/时间/状态/操作类单元格永不换行，空间不足时优先压缩弹性文本列（姓名、标题、最近参与，带省略号），极限宽度下容器横向滚动兜底。解决「总发言时长」等长表头在窄窗口下换行、以及 lib-table `overflow: hidden` 裁切内容的问题。统一覆盖说话人、项目、热词、会议库四个数据表格；后续新增表格将其类名加入机制选择器组、并用 `.table-scroll` 包裹即可

---

## [v1.x-fix-event-loop-blocking] - 2026-09-04

### 修复
- **服务卡死根因修复：async def 端点阻塞事件循环**：大量 `async def` 端点内执行同步阻塞 I/O（文件读写、目录遍历、subprocess 状态检查），冻结 asyncio 事件循环导致 WebSocket 断连、HTTP 请求排队、服务表现为「卡死」。按 AGENTS.md 规范将所有含阻塞操作的端点改为 `def`（FastAPI 自动线程池化）：
  - `tasks.py`: `serve_audio`、`download_summary`、`get_task`、`delete_task`、`retranscribe_task`、`retry_summary`、`update_task`
  - `speakers.py`: 全部 9 个端点（CRUD + 映射）
  - `settings.py`: `get_settings`、`save_settings`
  - `hotwords.py`: 全部 4 个端点
  - `notes.py`: 全部 9 个端点（笔记/注入/待办）
  - `user.py`: 全部 3 个端点
  - `projects.py`: 全部 11 个端点（含最严重的 `browse_filesystem` 目录遍历）
  - `chat.py`: `_execute_action` 函数（含录音启动等阻塞操作）

### 预防
- 新增端点时必须遵循 async/sync 边界：含阻塞操作（文件 I/O、subprocess、同步 HTTP）用 `def`；纯异步 I/O 用 `async def`

---

## [v1.x-meeting-menu-restraint] - 2026-09-04

### 决策
- **会议纪要顶部菜单精简**：顶部菜单要克制，更多信息留给内容而不是功能。菜单栏只保留高频、不可缺少的操作，低频功能下沉到右键菜单或设置页。内容区域优先于功能区域——用户打开会议纪要是为了阅读，不是为了点按钮。这是软件的设计范式

### 文档
- `docs/ROADMAP.md` 新增「v1.x 会议纪要顶部菜单精简」迭代计划
- `docs/design/ui-spec.md` 补充「菜单克制、内容优先」设计规范

---

## [v0.41-cleanup-ai-task-control] - 2026-09-04

### 变更
- **清理 AI 任务控制条冗余状态**：移除 `updateAiInputState()` 中"纪要生成中…"的显示逻辑——该状态在 `pending`/`processing`/`awaiting_mapping` 下不一致展示，已失去实际意义；状态统一由 `aiSessionBar` 准确呈现。控制条现仅服务于录音态（录音中/录音已暂停）
- **清理关联死代码**：移除 `stopCurrentTask()` 中处理中分支（实际只输出提示消息，无中断能力）、`.ai-task-control.is-proc` / `.ai-task-stop.is-proc` CSS 规则

## [v0.40-task-failure-handling] - 2026-09-04

### 新增
- **识别任务失败处理机制**：构建三层失败处理体系——① 后端自动重试瞬时错误（网络超时、API 限流等，最多 2 次，用户无感）；② 阶段感知重试：转写成功但纪要失败时，可仅重跑纪要阶段（`POST /api/tasks/{task_id}/retry-summary`），无需重跑耗时的 ASR；③ 前端错误分类展示：按错误类型（瞬时/音频/API配置/未知）给出不同提示和操作按钮，失败态内容区直接嵌入「重新生成纪要」+「重新识别」按钮
- **错误分类模块**（`core/errors.py`）：提供 `is_transient_error()` 判断是否可重试、`classify_error()` 返回错误分类与用户建议
- **任务数据模型扩展**：新增 `failed_stage`（失败阶段）、`error_category`（错误分类）、`error_suggestion`（建议）、`retry_count`（重试次数）字段

### 变更
- **管线自动重试**：`run_pipeline_task` 和 `_run_stage2_for_task` 均加入重试循环，瞬时错误等待 2s/5s 后自动重试，永久错误立即失败
- **前端失败态改造**：`showGenError()` 从接收错误字符串改为接收 task 对象，按 `error_category` 渲染不同图标和文案，按 `failed_stage` 决定显示哪些操作按钮
- **工具栏新增「重新生成纪要」按钮**：仅当纪要阶段失败且转写结果存在时可见

## [v0.39-retranscribe-button] - 2026-09-04

### 新增
- **重新识别按钮**：会议完成页工具栏新增「重新识别」按钮，可对当前录音文件重新执行 ASR 转写管线（归一化 → 上传 → 说话人分离 → 纪要生成），清除旧结果并重新处理。适用于转写质量不佳或热词配置更新后需要重新识别的场景。后端 `POST /api/tasks/{task_id}/retranscribe`，前端按钮在完成态和失败态可见，处理中自动隐藏

## [v0.38-sidebar-user-menu-polish] - 2026-09-04

### 修复
- **管理菜单定位错误（P0）**：`.sb-mgmt-dropdown` 此前以整条侧边栏为定位容器（`bottom: 100%`），展开后菜单底边贴在侧边栏顶部、大部分伸出视口被裁剪。现以 `.sb-user-wrap` 包裹触发器与菜单，菜单锚定在用户行上方 6px 处，展开位置正确

### 变更
- **用户信息入口显性化**：设置用户名的模态框原先只能通过点击小头像进入（隐形功能），现作为「用户信息」菜单项置于管理菜单顶部，头像不再承载点击
- **菜单项语义化**：`mgd-item` 由 `div onclick` 改为 `<button role="menuitem">`，触发器由 `div role=button` 改为真实 `<button>` 并补 `aria-haspopup` / `aria-controls` / `aria-expanded`
- **键盘支持**：Escape 关闭菜单并归还焦点；ArrowDown 从触发器进入菜单，菜单内 ArrowUp/ArrowDown 循环移动焦点（原生 Enter/Space 触发按钮）
- **视觉**：菜单项改为圆角 pill hover（对齐千问参考风格）；当前页菜单项加 2px 品牌色 inset 左条与 hover 区分；chevron 默认向上（提示向上展开）、展开后旋转向下；菜单加 0.12s 上滑入场动效（`prefers-reduced-motion` 全局兜底）
- **清理死代码**：删除顶栏用户区遗留的 `.user-area` / `.user-avatar` / `.user-name` 样式（HTML 已无引用）

## [v0.37-sidebar-event-decoupling] - 2026-09-04

### 变更
- **侧边栏刷新改为事件驱动，解耦任务变更与 UI 刷新**：引入轻量事件总线（`EventTarget` + `CustomEvent`），任务创建/删除/完成/加载处只发 `task-changed` 事件，侧边栏监听事件自动刷新。消除 6 处直接调用 `refreshHistory()` 的耦合点，后续新增任务操作无需关心侧边栏刷新逻辑

### 修复
- **新建会议时左侧列表未及时更新**：录音启动和文件上传成功后未刷新左侧历史列表。通过事件机制自动触发刷新，用户可立即看到新会议条目

---

## [v0.36-fix-stop-record-blocking] - 2026-09-04

### 修复
- **停止录音端点阻塞事件循环导致服务卡死**：`/api/record/stop` 原为 `async def`，内部调用 `stop_recording_with_stream()` 包含 `subprocess.wait(timeout=10)` + `thread.join(timeout=5)` 等阻塞操作，直接卡死 asyncio 事件循环导致整个服务无法响应。改为 `def`（同步端点），FastAPI 自动在线程池中运行，不阻塞事件循环

---

## [v0.35-speaker-count-estimation] - 2026-09-04

### 新增
- **文件上传路径说话人数量自动估算（采样法）**：`estimate_speaker_count()` 重构为均匀采样策略——读取 WAV 文件头计算时长，在 10-30 个均匀分布的时间点各提取 3 秒片段，馈入声纹聚类器估算说话人数。101 分钟音频从数分钟降至 1-3 秒
- **前端上传说话人数手动指定**：拖拽上传区下方新增说话人数下拉选择器（2-10 人或自动估算），用户已知人数时指定可显著提升分离精度

### 变更
- `run_pipeline_task()` 复用估算阶段生成的归一化文件，避免重复 ffmpeg 归一化

---

## [v0.34-sidebar-sync-on-create] - 2026-09-04

### 修复
- **新建会议时左侧列表未及时更新**：录音启动和文件上传成功后未调用 `refreshHistory()`，导致左侧历史列表不显示新创建的会议条目，用户感觉不同步。修复：在 `switchToRecordingView()` 末尾和 `uploadFile()` 上传成功后立即刷新历史列表

---

## [v0.33-fix-history-switch] - 2026-09-04

### 修复
- **切换历史记录时误报「录音文件加载失败」**：`initAudioPlayer` 销毁旧 Audio 实例时设置 `src=''` 会触发 error 事件，导致误弹 Toast。修复方案：移除旧实例的 error 监听器，并在新监听器中校验 src 是否为目标 URL
- **已完成会议显示「纪要生成中…」状态不一致**：`updateAiInputState()` 仅检查 `viewGenerating` 是否可见，未校验任务实际状态。已完成任务也使用 `viewGenerating` 视图，导致误显示生成中状态。修复方案：增加任务状态校验，仅 `pending/processing/awaiting_mapping` 状态才显示生成中

---

## [v0.32-sidebar-asset-p2] - 2026-09-04

### 新增
- **左侧栏资产化 P2**：搜索 + 悬停知识卡片，快速定位与预览会议内容
  - **搜索框**：历史列表顶部新增搜索输入，按标题 / 摘要 / 音频名实时过滤，150ms 防抖；支持一键清除
  - **悬停知识卡片**：鼠标悬停 400ms 弹出浮动卡片，显示完整标题、日期、时长、说话人标签、纪要摘要（最多 4 行）；底部快捷操作支持下载纪要 / 直接打开
  - 卡片智能定位：优先显示在历史项右侧，空间不足时自动切换到左侧或向上偏移

### 变更
- `refreshHistory()` 拆分为数据获取 + `_renderHistoryList()` 渲染两个函数，支持搜索过滤复用
- 缓存 `_allTasks` 全量任务数据，供搜索过滤和悬停卡片共享
- 移除旧的 `.sb-title-tooltip` 简单文本提示，替换为 `.sb-hover-card` 富信息卡片
- **恢复 P0/P1 功能**：时间分组（今天/昨天/本周/更早）、状态视觉权重（左边框色彩）、双行卡片（标题+摘要首句）、元数据条（时长·说话人数·状态·日期）

### 文档
- `docs/ROADMAP.md` 标记 P2 已完成
- `docs/design/ui-spec.md` 补充搜索框与悬停知识卡片规范

---

## [v0.31-sidebar-asset-p1] - 2026-09-04

### 新增
- **左侧栏资产化 P1**：历史卡片从单行升级为双行信息架构
  - **双行卡片**：标题下方显示纪要摘要首句（去除 Markdown 标题前缀），不打开即可获取核心信息；未完成态显示对应状态提示（处理中 / 录音中 / 待绑定 / 失败）
  - **元数据条**：卡片底部展示 `时长 · 说话人数 · 状态 · 日期`，以 `·` 分隔，辅助快速判断

### 变更
- `.sb-history-item` 布局从 `flex row` 改为 `flex column`，新增 `.sb-card-top` / `.sb-card-summary` / `.sb-card-meta` 三个子结构
- `refreshHistory()` 渲染逻辑重构：从 `task.summary` 提取首句、从 `task.audio_duration` / `task.speaker_count` 组装元数据

---

## [v0.30-sidebar-asset] - 2026-09-04

### 新增
- **左侧栏资产化 P0**：历史会议列表从「待办清单」升级为「知识资产」
  - **时间分组**：列表按「今天 / 昨天 / 本周 / 更早」分组，空分组自动隐藏，消灭无尽滚动
  - **状态视觉权重**：非完成态任务通过左边框色彩引导注意力——失败红色、待绑定琥珀色、进行中蓝色脉冲；完成态无边框
  - 纯前端改造，无需后端变更；`refreshHistory()` 按 `created_at` 分组渲染

### 文档
- `docs/ROADMAP.md` 新增「v1.x 左侧栏资产化」迭代计划（P0/P1/P2 分级）
- `docs/design/ui-spec.md` 补充历史列表时间分组与状态视觉权重规范

---

## [v0.29-diarization-accuracy] - 2026-09-04

### 修复
- **说话人分离精度增强（短期四项）**：
  - **S1** `speaker_count` 全链路传递：文件上传端点新增可选 `speaker_count` 表单参数；未传时自动归一化→快速声纹扫描估算（钳制到 1-10），解决上传路径不传 speaker_count 导致 paraformer-v2 盲猜说话人数的问题
  - **S2** 录音路径 speaker_count 钳制保护：实时聚类估算值钳制到 [1, 10]，避免噪声产生过多伪说话人
  - **S3** 放松后处理修正条件：夹心修正间隔 2000ms→800ms，碎片跟前句间隔 2000ms→500ms（新增 `FRAGMENT_SPEAKER_FIX_GAP_MS`），减少真正的说话人切换被误合并
  - **S4** 聚类参数调优：相似度阈值 0.70→0.65（更严格区分音色相近者），特征窗口 2s→1.5s / 步长 1s→0.75s（提升时间分辨率）

### 变更
- `docs/ROADMAP.md` 新增「v3+ 说话人分离精度增强」迭代计划（短期 S1-S4 / 中期 M1-M3 / 长期 L1-L3）

## [v0.28-self-highlight] - 2026-09-04

### 新增
- **转写栏「自己」右对齐对话框样式**：当说话人姓名与当前用户姓名一致时，转写条目以右对齐气泡样式显示
  - 实时转写（`rec-entry`）：`flex-direction: row-reverse` + 淡蓝气泡背景
  - 对话稿（`bt-line`）：`flex-direction: row-reverse` + 淡蓝气泡背景 + 70% 最大宽度
  - 判断逻辑：`_currentUser && label === _currentUser.name`
  - 自动刷新：保存用户姓名、绑定说话人、实时说话人绑定更新时自动刷新高亮

## [v0.27-cli-in-settings] - 2026-09-04

### 新增
- **设置页 CLI 命令参考**：设置页新增「CLI 命令行工具」卡片，展示所有可用 CLI 命令
  - 前端动态加载：`loadCliReference()` 从 `/api/cli-reference` 获取命令列表并渲染
  - 后端新增 `GET /api/cli-reference` 端点，返回结构化 CLI 命令参考（JSON 格式）
  - 便于用户理解 CLI 功能，也便于其他 AI Agent 工具程序化调用

---
## [v0.26-codex-workspace-health] - 2026-09-04

### 新增
- **CODEX.md 渐进式上下文索引**：AI 代理第一入口（124 行），模块速查 + 按任务类型加载路径
  - 替代原「全量加载 README→MISSION→ARCHITECTURE」模式
  - 包含：模块速查表、API 端点概览、硬约束速记、数据目录说明
- **截图归档**：根目录 50 张调试截图移入 `docs/screenshots/{verify,test,debug}/`

### 变更
- `AGENTS.md`：开工先读改为渐进式加载（CODEX.md 优先）
- `README.md`：文档地图新增 AI 入口层
- `.gitignore`：补充运行时数据文件排除（speakers.json、users.json、voiceprint_registry.json 等）

---

## [v0.25-fix-audio-player-binding] - 2026-09-04

### 修复
- **说话人绑定页音频无法播放**：`awaiting_mapping` 状态下点击播放按钮无反应
  - 根因：`showSpeakerBinding()` 未调用 `initAudioPlayer()`，音频元素未初始化
  - 修复：在 `showSpeakerBinding()` 中添加 `initAudioPlayer(currentTaskId)` 调用

---

## [v0.25-voiceprint] - 2026-09-04

### 新增
- **V3 声纹姓名化**：把「说话人1」自动变「张三」
  - `core/voiceprint.py`：声纹提取与匹配引擎
    - 基于 resemblyzer（GE2E 编码器）提取 256 维声纹嵌入向量
    - 声纹注册表持久化（`data/voiceprint_registry.json`），与 `speakers.json` 解耦
    - 余弦相似度匹配（阈值 0.75），支持注册/更新/删除/查询
    - `auto_identify_speakers()`：从归一化音频中按 speaker_id 提取各段声纹，批量匹配注册表
    - 延迟加载编码器，保持服务启动轻量
  - `app/routers/voiceprint.py`：声纹管理 API
    - `GET /api/voiceprint/registry` — 获取声纹注册表（含说话人姓名）
    - `GET /api/voiceprint/status/{uuid}` — 查询指定说话人声纹状态
    - `POST /api/voiceprint/register` — 从音频片段注册声纹
    - `DELETE /api/voiceprint/{uuid}` — 删除声纹
    - `POST /api/voiceprint/tasks/{task_id}/match` — 对任务执行自动声纹匹配
  - **管线集成**（`app/store.py`）：转写完成后自动执行声纹匹配
    - 有匹配结果 → 自动绑定说话人 → 直接进入纪要生成
    - 无匹配 → 降级为手动绑定（向后兼容）
    - 匹配失败不阻塞管线
  - **前端集成**（`app/static/index.html`）：
    - 说话人绑定视图：声纹自动识别状态栏，显示匹配结果与置信度
    - 说话人管理页：列表显示声纹注册状态图标（麦克风）
    - 说话人详情页：新增「注册声纹」/「更新声纹」按钮
    - 自动加载声纹注册表，实时反映注册状态
  - **依赖**：`resemblyzer>=0.1.3`（含 torch、librosa、webrtcvad）

### 决策
- 声纹引擎选 resemblyzer 而非 WeSpeaker：resemblyzer 更轻量，模型加载快（<1s），256 维嵌入足够区分 4-8 人会议
- 声纹注册表独立于 speakers.json：解耦声纹数据与人员档案，支持声纹单独更新不影响人员信息
- 匹配阈值 0.75：平衡误识别与漏识别，可通过 API 参数调整

---

## [v0.25-unified-meeting-page] - 2026-09-04

### 变更
- **说话人绑定页 / 纪要生成页 / 结果页融合为统一会议页**：录音结束 → 上传/转写 → 说话人绑定 → 纪要生成 → 结果查看，全程不再切换页面
  - `viewSpeakerBinding` 独立绑定页删除：绑定交互内联到统一会议页「转写」Tab（点击说话人 chip 下拉绑定 / 新建说话人）
  - `viewCompleted` 独立结果页删除：纪要 / 待办 / 笔记全部并入统一页
  - 顶部新增「说话人绑定条」：识别到 N 位说话人（M 位未绑定）+ 说话人概览 chips + 跳过 / 新建说话人 / 确认并生成纪要
  - Tab 统一为：转写 / 纪要 / 章节 / 笔记 / 待办；纪要面板三态（待绑定提示 → 骨架屏 → 内容）
- **上传流程并入统一会议页**：`uploadFile` 不再切 processing 视图，上传/转写进度实时显示在纪要 Tab 骨架屏提示语
- **声纹自动匹配自动触发**：`triggerVoiceprintMatch` 重构为无 UI 依赖的 `autoMatchVoiceprint`，进入绑定阶段且无已有绑定时自动执行并应用结果
- **活跃任务互斥判断统一**：`isTaskActive` / `getActiveTaskView` / 上传与录音互斥 / AI 面板任务控制条全部收敛到 `viewGenerating`

### 修复
- 清理死代码：旧完成页 Tab 处理器（TAB_IDS）、AI 注入 Tab 函数群、`renderTranscriptTab`、`showSpeakerBindingForEdit`、声纹绑定页死 UI

---

## [v0.24-server-refactor] - 2026-09-04

### 变更
- **server.py 轻量化重构**：2152 行 → 95 行，按功能域拆分为 9 个 router 模块
  - 新增 `app/store.py`：共享状态层（任务字典、实时状态、持久化辅助、配置常量）
  - 新增 `app/routers/`：tasks / record / speakers / projects / chat / user / hotwords / settings / notes
  - server.py 仅保留 app 创建、路由注册、生命周期管理、前端页面托管
- **新增冒烟测试**：`tests/test_smoke.py` 覆盖 15 个关键路径，含录音启动防阻塞回归测试

### 规范
- **server.py 轻量化原则**：server.py 仅做 app 创建与 router 注册，不含业务逻辑
- **async/sync 边界规则**：含阻塞操作的端点用 `def`；纯异步 I/O 端点用 `async def`
- **冒烟测试兜底原则**：每个功能域至少一个冒烟测试覆盖关键路径

---
## [v0.23-fix-record-start-blocking] - 2026-09-04

### 修复
- **麦克风录音无响应**：点击"麦克风录音"按钮无任何反应
  - 根因：`/api/record/start` 端点定义为 `async def`，但内部执行阻塞操作（`subprocess.Popen` 启动 ffmpeg + `time.sleep(0.5)`），卡死 asyncio 事件循环，整个服务无法响应任何请求
  - 修复：将端点改为同步 `def`，FastAPI 自动在线程池执行，不再阻塞事件循环

---
## [v0.22-fix-binding-confirm] - 2026-09-04

### 修复
- **说话人绑定确认失败**：点击"确认并生成纪要"后页面无响应，任务永远停留在处理中
  - 根因：代码引用了不存在的 DOM 元素 `progressFill`、`processLog`、`pipelineSteps`，导致 `TypeError: Cannot read properties of null` 中断函数执行，API 请求从未发送
  - 修复：为所有引用添加空值检查（`if ($('#progressFill')) ...`），确保元素不存在时不抛错
  - 影响函数：`confirmSpeakerMapping()`、`generateSummaryWithoutMapping()`、`pollTask()`、`updatePipelineSteps()`、`addLog()`、`resetToIdle()`、`loadTask()`

---
## [v0.21-audio-playback] - 2026-09-04

### 新增
- **会议录音回放功能**：已完成会议支持原始录音回放
  - 后端新增 `GET /api/audio/{task_id}` 端点，按 MIME 类型流式返回音频文件
  - 前端用真实 HTML5 `<audio>` 替换原模拟播放器，支持播放/暂停/拖动进度/快进快退/倍速
  - 完成态视图（`viewCompleted`）新增音频播放器栏，与生成态视图共用同一播放器逻辑
  - 音频播放器自动适配当前可见视图（通过 `_audioIds()` 路由到正确 DOM 元素）
  - 原始录音文件保留在 `data/recordings/` 或 `data/uploads/`，删除任务时一并清理

---
## [v0.20-hotword-mappings] - 2026-09-04

### 新增
- **热词映射（后处理纠正）**：ASR 识别结果自动纠正，如 `ES` → `EAS系统`
  - 映射文件 `data/hotword_mappings.txt`，格式 `错误识别→正确文本`
  - 英文词使用 `\b` 词边界匹配（大小写不敏感），避免误替换子串
  - 中文/中英混合直接子串替换
  - 长匹配优先（按左串长度降序排列）
  - 批处理管线（`assemble_dialogue()`）和实时转写（`on_event()`）均已集成
  - REST API：`GET/POST /api/hotword-mappings` 管理映射
  - AI 动作：支持「热词映射」「映射列表」查询

---
## [v0.19-rec-tab-mode] - 2026-09-04

### 新增
- **录音视图响应式 Tab 切换**：视口宽度 < 800px 时，实时转写与实时总结自动切换为 Tab 模式
  - 顶部 Tab 栏含图标 + 文字，激活项有下划线高亮
  - 默认展示「实时转写」，点击切换到「实时总结」
  - 切换时保留数据和滚动位置（仅 CSS 显隐控制）
  - Tab 区域最小高度 44px，触摸友好
  - 从窄屏恢复宽屏时自动清除 Tab 状态，恢复并行布局
  - Tab 模式下总结面板折叠按钮隐藏（Tab 切换替代折叠功能）

---
## [v0.18-ai-panel-enhanced] - 2026-09-03

### 新增
- **AI 面板任务控制条**：录音或处理中时，AI 输入区上方显示任务状态条，含停止按钮可快速终止录音
- **AI 面板「更多」菜单**：输入框左侧新增更多按钮（⋮），点击展开向上弹出的快捷操作菜单
  - 配置化架构（`AI_QUICK_ACTIONS` 数组），新增功能只需追加一项即可
  - 预置 4 项：麦克风录音（录音中自动切换为「停止录音」并高亮）、上传音频文件、查看历史会议、热词管理
  - 点击外部自动关闭菜单
- **状态联动**：任务控制条与更多菜单文案随录音/暂停/处理状态实时更新

---
## [v0.17-ai-action-cli] - 2026-09-03

### 新增
- **AI 对话框动作执行**：右侧 AI 对话框的操作按钮现在真正执行系统功能
  - 后端 `/api/chat` 新增动作检测层，识别用户意图并执行对应操作
  - 支持 11 种动作：录音控制（开始/停止/暂停/恢复）、内容分析（提取待办/关键结论/发言分析）、任务查询、热词/设置查看
  - 动作结果注入 LLM 上下文，生成自然回复
  - 前端根据动作结果自动更新 UI（如录音启动后切换到录音视图）
- **完整 CLI 会议助手**：`cli.py` 扩展为完整的命令行工具
  - `record start/stop/pause/resume/status` — 录音控制
  - `tasks list/show/delete` — 任务管理
  - `speakers list/add` — 说话人管理
  - `hotwords list/add` — 热词管理
  - `settings show/set` — 设置管理
  - `chat <消息>` — AI 对话

---
## [v0.16-sidebar-nav-refactor] - 2026-09-03

### 变更
- **顶栏清理**：移除说话人按钮和用户设置入口，顶栏仅保留应用标题、任务标题、状态指示器和面板切换按钮
- **左栏底部导航**：新增说话人管理、热词管理、设置三个导航入口，位于项目列表下方
- **中栏视图扩展**：新增说话人管理页、热词管理页、设置页三个中栏视图，点击左栏底部入口切换
- **侧栏宽度**：从 232px 调整为 200px，符合 UI 规范
- **API 新增**：
  - `GET/POST /api/hotwords` — 热词读取与保存
  - `GET/POST /api/settings` — 设置读取与保存

### 文档
- 更新 `docs/design/ui-spec.md` 顶栏与左栏说明

---
## [v0.15-realtime-summary-restore] - 2026-09-03

### 修复
- **实时总结页面刷新丢失**：录音中刷新页面后，实时总结面板内容完全消失
  - 后端 WebSocket 连接建立时，回放当前实时总结内容和状态（`summary_update` + `summary_status`）
  - 前端 `checkRecording()` 恢复录音时初始化总结面板 UI 状态
  - 暂停状态也能正确恢复

---

## [v0.14-realtime-speaker-binding] - 2026-09-03

### 新增
- **实时说话人绑定**：录音期间可直接在实时转写区域绑定发言人身份
  - 点击转写条目中的发言人姓名，弹出说话人选择下拉框
  - 选择已有说话人或新建说话人后立即绑定
  - 绑定后所有该说话人的转写条目自动刷新姓名显示
  - 已绑定的说话人名称加粗高亮，便于区分
- **实时总结发言人标注**：实时总结内容自动包含发言人姓名
  - 后端 `_resolve_realtime_speaker_name()` 从绑定映射解析姓名
  - 总结器 `_do_summary()` 构造对话文本时标注「发言人：内容」格式
  - 系统提示词新增发言人标注原则
- **实时绑定 API**：
  - `POST /api/record/bind-speaker` — 录音期间绑定说话人
  - `GET /api/record/speaker-bindings` — 查询当前绑定状态
  - WebSocket 下行新增 `speaker_bound` 消息类型，广播绑定更新
- **页面刷新恢复**：恢复录音时自动拉取已有说话人绑定

### 变更
- **实时转写消息增强**：`partial`/`sentence`/`history` 消息均携带 `speaker_name` 字段
- **实时总结输入增强**：`feed_sentence()` 支持 `speaker_name` 字段，总结 prompt 包含发言人归属信息
- **录音停止时保存绑定**：实时说话人绑定映射写入任务数据，供批管线复用

---

## [v0.13-tab-refactor] - 2026-09-03

### 新增
- **笔记 Tab**：完成态新增可编辑笔记 tab，支持自动保存（防抖 1 秒），录音时的临时笔记自动迁移到持久化笔记
- **AI 注入 Tab**：AI 对话回复中自动识别待办/结论/决策，弹出注入提示条，用户可一键注入到会议记录
  - 后端 `_extract_injectable_items()` 规则引擎，从 AI 回复中匹配 Markdown checkbox、关键词列表项和结论段落
  - `/api/chat` 返回新增 `extracted_items` 字段
  - 注入内容支持「写入纪要」标记和删除操作
- **待办 Tab**：汇总展示会议相关待办事项，支持勾选完成/删除，来源标注（AI 注入 / 纪要提取）
- **用户信息登记**：顶栏右侧新增用户区域，点击弹出模态框输入姓名，支持一键绑定当前会议的说话人身份
  - `core/users.py` 用户数据管理模块，持久化到 `data/users.json`
  - `GET/POST /api/user`、`POST /api/user/bind-speaker` 端点
- **笔记/注入/待办 API**：
  - `GET/PUT /api/tasks/{id}/notes` — 笔记读写
  - `GET/POST /api/tasks/{id}/injections` — 注入内容列表/新增
  - `POST /api/tasks/{id}/injections/{id}/apply` — 标记已写入纪要
  - `DELETE /api/tasks/{id}/injections/{id}` — 删除注入
  - `GET /api/tasks/{id}/todos` — 待办列表
  - `POST /api/tasks/{id}/todos/{id}/toggle` — 切换待办完成状态
  - `DELETE /api/tasks/{id}/todos/{id}` — 删除待办

### 变更
- **移除「原始转写」Tab**：完成态不再展示云端 ASR 原始返回 JSON，减少无意义数据暴露
- **任务 JSON 瘦身**：`_save_task_to_disk()` 持久化时排除 `transcription` 字段，单任务文件从 ~124KB 降至 ~10KB
- **启动迁移**：`_load_tasks_from_disk()` 自动检测并剔除旧文件中的 `transcription` 字段

---

## [v0.12-delete-task] - 2026-09-03

### 新增
- **录音列表删除功能**：左侧历史记录支持删除会议录音
  - 鼠标悬停在历史项时显示删除按钮（垃圾桶图标）
  - 删除前弹出确认对话框，防止误操作
  - 删除后自动刷新列表，若删除的是当前查看的任务则切回空闲态
  - 后端复用已有 `DELETE /api/tasks/{task_id}` 接口，清理任务文件与持久化数据

## [v0.11-folder-picker] - 2026-09-03

### 新增
- **文件夹选择器**：项目关联文件夹时支持可视化浏览本地文件系统，不再需要手动输入路径
  - 后端 `GET /api/filesystem/browse?path=...` 端点，返回目录列表（默认返回用户主目录）
  - 前端弹窗式文件夹浏览器：面包屑导航、主目录/上级快捷按钮、子目录列表（点击进入）
  - 选择后路径自动回填到输入框，用户仍可手动编辑

## [v0.10-realtime-summary] - 2026-09-03

### 新增
- **实时总结功能**：录音期间每分钟自动生成增量会议纪要摘要
  - **后端增量引擎**（`core/realtime_summary.py`）：收集定稿句子，每 60 秒触发 LLM 增量总结，使用 qwen-turbo 低延迟模型
  - **增量策略**：首次总结仅用当前缓冲句子；后续传入「上次摘要 + 新增句子」，模型输出更新后的完整摘要
  - **前端左右分栏布局**：录音界面笔记栏上方分为左栏（实时转写）和右栏（实时总结），55%/45% 比例
  - **控制面板**：右栏支持暂停/恢复总结、折叠/展开面板
  - **WebSocket 消息扩展**：复用现有 `/ws/transcript/{task_id}`，新增 `summary_update` 和 `summary_status` 消息类型
- **新增 API 端点**：
  - `POST /api/record/summary/pause` — 暂停实时总结
  - `POST /api/record/summary/resume` — 恢复实时总结

### 变更
- 录音界面布局从单栏转写升级为双栏（转写 + 总结），转写区域宽度从 `flex:1` 调整为 `flex:55`
- 定稿句子回调同时送入实时转写 WebSocket 和实时总结引擎

---

## [v0.9-ai-context] - 2026-09-03

### 新增
- **AI 面板深度上下文集成**：右侧会议助手对话框基于四维上下文生成回复
  - **维度 1 — 实时转写流**：录音期间将最近 10 条定稿句子作为动态上下文注入，AI 可基于最新对话内容回答
  - **维度 2 — 已完成会议纪要**：已生成纪要的摘要、结论、待办事项作为上下文
  - **维度 3 — 关联项目资料**：通过项目关键词检索注入相关文档片段
  - **维度 4 — 对话历史**：维护最近 5 轮（10 条）对话历史，确保多轮连贯性
- **后端实时转写缓冲区**：`_realtime_transcript_buffers` 自动收集 WebSocket 流中的定稿句子（`app/server.py`）
- **`POST /api/chat` 增强**：
  - 新增 `realtime_transcripts` 请求字段，接收前端传来的实时转写条目
  - 上下文按优先级注入：实时转写 > 完成纪要 > 项目资料 > 对话历史
  - 新增 `_build_speaker_name_map()` 辅助函数，解析说话人姓名
- **前端实时转写追踪**：
  - 新增 `realtimeTranscriptEntries` 数组，在 `handleTranscriptMessage` 的 `sentence` 分支自动收集
  - `sendAiMessage()` 请求体携带最近 10 条实时转写条目
  - 录音启动/恢复时自动清空缓冲区

### 变更
- AI 对话上下文注入从单一维度升级为四维分层，优先级清晰
- 系统提示词结构保持不变，动态上下文块以 `---` 分隔追加在末尾

---

## [v0.8.1-ui-fix] - 2026-09-03

### 修复
- **会议时间显示"未提供"**：LLM 有时忽略提示词中的会议时间，增加后处理兜底替换；同时增加从音频文件名提取时间的兜底逻辑（`app/server.py`、`core/summarize.py`）
- **"关联项目"按钮点击无响应**：按钮 onclick 与 document click 监听器存在事件冒泡冲突，添加 `event.stopPropagation()` 修复（`index.html`）
- **记录要点输入框高度过小**：CSS `min-height` 从 4em 增至 6em，JS 自动扩展上限从 80px 增至 150px，`rows` 从 1 改为 3（`index.html`）
- **"添加文件夹"按钮点击无效**：将 `prompt()` 弹窗改为页面内联输入框，避免浏览器阻止原生对话框（`index.html`）

## [v0.8-notes] - 2026-09-03

### 新增
- **录音笔记栏**：录音界面底部控制栏上方新增笔记输入区域
  - 用户可在录音期间随时记录要点、待办或关键信息
  - 笔记自动扩展高度（最大 80px），支持多行输入
  - 笔记内容作为上下文传递给纪要生成 LLM，辅助理解会议背景
- **后端支持**：
  - `POST /api/record/stop` 新增 `notes` 参数，接收用户笔记
  - 笔记存储在任务记录中（`user_notes` 字段）
  - 管线第二阶段将笔记注入 `generate_summary` 提示词
- **纪要提示词增强**：系统提示词新增「用户笔记为辅助参考」原则，明确笔记仅作背景参考，纪要仍以对话原文为依据

## [v0.7-projects] - 2026-09-03

### 新增
- **项目关联功能**：会议纪要与本地项目资料深度联动
- **`core/projects.py`**：项目管理与文件索引模块
  - 项目 CRUD：创建/删除项目，关联多个本地文件夹
  - 文件扫描：自动扫描 md/txt/docx/pdf 文件，提取文本内容
  - 轻量索引：文件名 + 摘要 + 关键词（Markdown 标题/英文术语/中文书名号）
  - 关键词检索：基于文件名/标题/关键词/摘要的匹配搜索
  - 上下文注入：`get_project_context_for_chat()` 为 AI 对话提供项目资料片段
- **项目 API 端点**：
  - `GET/POST/PUT/DELETE /api/projects`：项目 CRUD
  - `POST/DELETE /api/projects/{id}/folders`：文件夹管理
  - `POST /api/projects/{id}/scan`：异步触发索引构建
  - `GET /api/projects/{id}/files`：获取索引文件列表
  - `POST /api/projects/{id}/search`：项目文件搜索
- **`POST /api/chat`**：AI 对话端点（接入通义千问，替代原有模拟回复）
  - 自动注入当前会议纪要上下文 + 项目资料检索增强
  - 返回回复文本 + 引用来源文件列表
- **前端 UI**：
  - 左侧导航新增「项目」区域
  - 中栏新增项目管理视图（创建/添加文件夹/重建索引/查看文件）
  - AI 对话框新增「📎 关联项目」按钮
  - AI 回复引用项目资料时标注来源
  - AI 对话接入真实 LLM（qwen-plus），支持多轮上下文
- **依赖**：`python-docx>=1.1.0`、`PyPDF2>=3.0.0`

### 变更
- AI 对话从模拟回复升级为接入通义千问 LLM
- `requirements.txt`：新增 python-docx、PyPDF2

### 决策
- 项目配置独立存储于 `data/projects.json`
- 索引采用轻量关键词匹配，适合 MVP 规模
- AI 对话注入上下文上限 3000 字符

---

## [v0.6.4-realtime-diarization] - 2026-09-03

### 新增
- **实时说话人分离**：录音过程中实时区分不同说话人，前端显示「发言人1」「发言人2」等标签
  - 原理：本地声纹聚类（MFCC 特征提取 + 余弦相似度），无需云端 API
  - `core/diarization.py`：新增声纹聚类模块，每 2 秒提取一次特征，基于相似度阈值自动创建/匹配说话人
  - `app/server.py`：PCM 回调同时送 ASR 和声纹聚类器，ASR 句子标注 speaker_id 后推送前端
  - `requirements.txt`：新增 numpy、scipy 依赖
  - 前端已支持 speaker_id 显示（`msg.speaker_id ?? 1`），无需改动

### 限制
- 基于声学特征的启发式方法，准确率低于神经声纹模型（如 WeSpeaker）
- 适合 2-4 人会议场景；人数过多或音色相近时可能误判
- 需要每人至少说 2 秒才能建立可靠档案

---

## [v0.6.3-fix-pause-recording] - 2026-09-03

### 修复
- **录音暂停无效**：点击暂停按钮后录音仍在继续，实时转写也未停止
  - 根因：前端 `togglePause()` 仅暂停了计时器 UI，未通知后端
  - `core/audio.py`：新增 `_stream_paused` 标志，reader loop 暂停时仍读取 pipe（防 ffmpeg 阻塞）但丢弃数据，不写文件、不送 ASR
  - `core/audio.py`：新增 `pause_recording_with_stream()` / `resume_recording_with_stream()` 函数，累计暂停时长从最终 duration 中扣除
  - `app/server.py`：新增 `POST /api/record/pause` 和 `POST /api/record/resume` 端点
  - `app/static/index.html`：`togglePause()` 改为 async，暂停/恢复时调用后端 API

---

## [v0.6.2-task-persist] - 2026-09-03

### 修复
- **任务数据持久化**：任务数据（对话稿、说话人绑定、纪要等）从纯内存存储改为 JSON 文件持久化（`data/tasks/`），页面刷新或服务重启后数据不丢失
- **说话人绑定刷新丢失**：绑定说话人后页面刷新，已关联的人员绑定不再丢失
  - 后端：`set_speaker_mapping` 端点在触发纪要生成前，即将 `speaker_uuid_mapping` 写入任务并持久化
  - 前端：`showSpeakerBinding` 加载任务时从 `speaker_uuid_mapping` 恢复已有绑定状态
  - 前端：`confirmSpeakerMapping` 提交成功后立即同步映射到本地 task 对象
- **loadTask 缺少 failed 状态处理**：加载失败状态任务时页面不再空白，正确显示错误信息

### 变更
- `app/server.py`：新增 `_save_task_to_disk()` / `_load_tasks_from_disk()` 函数，启动时自动恢复任务
- `app/static/index.html`：`selectBtOption` 同步更新本地 task 缓存；`showSpeakerBinding` 支持恢复已有绑定
- `.gitignore`：新增 `data/tasks/` 排除规则

---

## [v0.6.1-retry] - 2026-09-03

### 修复
- **实时转写限流重试**：DashScope ASR 返回 `Too many requests` 时自动指数退避重试（2s/5s/10s，最多 3 次）
- `core/realtime_asr.py`：
  - `_TranscriptCallback` 新增 `wait_for_connect()` 同步等待连接结果（`on_open`/`on_error` 信号）
  - `RealtimeTranscriber.start()` 增加重试循环，重试期间显示用户友好提示（"服务繁忙，自动重试中"）
  - 仅最后一次重试才转发原始 SDK 错误，避免中间错误刷屏
- `app/server.py`：转写器启动移至后台线程，避免阻塞 FastAPI 事件循环（重试等待可能持续数秒）
- **管线热词参数名修复**：`pipeline.py` 调用 `get_or_create_vocabulary()` 的参数从 `model=` 修正为 `target_model=`（v0.4 升级 API 时遗留）

### 变更
- **说话人绑定界面重构**：从抽象卡片列表（"说话人0 · 5句"）改为对话稿内联绑定模式
  - 对话稿按时间线排列，每行显示时间戳 + 说话人标签（彩色 chip）+ 文本内容
  - 点击说话人标签弹出下拉菜单，可选择绑定身份或新建说话人
  - 顶部增加说话人概览条，显示各说话人绑定状态
  - 用户可看着实际发言内容来判断说话人身份，不再依赖抽象序号

---

## [v0.6-speakers] - 2026-09-03

### 新增
- **说话人姓名化**（P3）：将 `speaker_id` 映射为真实姓名，纪要中使用真实姓名
- **`core/speakers.py`**：说话人档案管理模块
  - `Speaker` 类：说话人档案（姓名、角色、备注）
  - `MeetingMapping` 类：会议级 speaker_id → 说话人 映射
  - 全局说话人 CRUD：`load_speakers()` / `add_speaker()` / `update_speaker()` / `delete_speaker()`
  - 会议映射管理：`save_meeting_mapping()` / `get_latest_mapping()`
  - 姓名应用：`apply_speaker_names()` 将 speaker_id 映射为真实姓名
- **数据文件**：
  - `data/speakers.json`：全局说话人档案
  - `data/meeting_mappings.json`：会议映射历史（用于复用建议）
- **API 端点**：
  - `GET /api/speakers`：获取说话人列表
  - `POST /api/speakers`：添加说话人
  - `PUT /api/speakers/{id}`：更新说话人
  - `DELETE /api/speakers/{id}`：删除说话人
  - `GET /api/speakers/mapping/latest`：获取最近一次会议映射（用于复用）
  - `POST /api/speakers/mapping`：保存会议映射
- **管线集成**：`run_pipeline()` 新增 `speaker_mapping` 参数，转写后自动应用姓名映射
- **纪要提示词**：`generate_summary()` 使用真实姓名，对话稿显示 `**张三**：...` 而非 `**说话人0**：...`

### 决策
- 采用「人工映射 + 历史复用」方案（详见 ADR-0005），不引入声纹识别（WeSpeaker），保持 v1 纯云方案定位
- 说话人档案全局共享，会议映射独立存储，支持历史复用

---

## [v0.5-postprocess] - 2026-09-03

### 新增
- **批转写后处理管线**（`core/transcribe.py`）：
  - `merge_fragments()`：碎片句子合并——基于时间间隔（<2s）、短句检测（<12字）、跨句拆词检测（如"智"+"能"="智能"）
  - `correct_speaker_ids()`：说话人修正——夹心修正（A-B-A→全A）+ 碎片短句跟随前句说话人
  - `assemble_dialogue()` 接入后处理管线：原始句子 → 碎片合并 → 说话人修正 → 按 speaker 归并

---

## [v0.4-asr-upgrade] - 2026-09-03

### 变更
- **实时转写模型升级**：`paraformer-realtime-v2` → `qwen-audio-3.0-asr-flash-streaming`（官方首推实时模型，详见 ADR-0004）
- `core/realtime_asr.py`：新增 `vocabulary`（即时热词）和 `context`（上下文增强）参数支持
- `core/hotwords.py`：热词 API 适配新版——`model` → `target_model`，热词格式 `{"word": ..., "weight": 2}` → `{"text": ..., "weight": 4}`，上限 500 → 2000

### 决策
- 实时转写升级为 `qwen-audio-3.0-asr-flash-streaming`：支持上下文增强（传入领域术语提升识别率）和即时热词（随请求内联传入，免创建热词表）
- 批处理转写（paraformer-v2）保持不变，因其支持说话人分离且异步处理长音频稳定
- WebSocket 连接逻辑无需改动（新模型使用相同 SDK 和回调机制）

---

## [v0.3-realtime] - 2026-09-03

### 新增
- **实时转写**：录音期间通过 DashScope `paraformer-realtime-v2` 流式识别，前端实时显示转写文字（延迟约 1-2 秒）
- **`core/realtime_asr.py`**：封装实时转写引擎（WebSocket + SDK 回调 → asyncio Queue → 前端推送）
- **流式录音**：`core/audio.py` 新增 `start_recording_with_stream()`，ffmpeg 输出 raw PCM 到 stdout pipe，后台线程同时写文件 + 回调送入 ASR
- **WebSocket 端点**：`app/server.py` 新增 `WS /ws/transcript/{task_id}`，实时推送 partial/sentence/error/ended 消息
- **前端实时视图**：录音中页面下方新增「实时转写预览」区域，临时结果斜体显示，定稿句子正常追加
- 实时转写失败时优雅降级：仅录音，不影响后续批管线

### 变更
- 录音端点改用流式录音（`start_recording_with_stream` / `stop_recording_with_stream`）替代原有文件直写方式
- `requirements.txt` 新增 `dashscope>=1.23.0`、`websockets>=12.0`

### 决策
- 实时转写（paraformer-realtime-v2）**不支持说话人分离**，定位为「预览」；最终纪要仍走批管线（paraformer-v2 + diarization）
- 使用语义断句（`semantic_punctuation_enabled=True`）更适合会议场景
- 单 ffmpeg 进程输出 PCM pipe，Python 线程分叉写文件 + 送 ASR（避免 avfoundation 并发采集冲突）

---

## [v0.2-recording] - 2026-09-03

### 新增
- **实时录音**：`core/audio.py` 增加麦克风/BlackHole 采集（ffmpeg avfoundation），支持开始/停止录音、设备列表查询
- **录音 API**：`app/server.py` 新增 `POST /api/record/start`、`POST /api/record/stop`、`GET /api/record/status` 三个端点
- **录音 UI**：前端增加录音按钮、录音中视图（红点脉冲 + 计时器 + 停止按钮）、页面刷新恢复录音状态
- 录音文件存放 `data/recordings/`，停止录音后自动进入管线处理（归一化 → 转写 → 纪要）
- 录音设备名可通过环境变量 `RECORD_DEVICE` 覆盖（默认 `MacBook Pro麦克风`；线上会议戴耳机场景可改为 `BlackHole 2ch`）

---

## [v0.1-mvp] - 2026-09-03

### 新增
- **core/ 管线模块**：`audio.py`（ffmpeg 归一化）、`upload.py`（DashScope 临时存储上传）、`transcribe.py`（paraformer-v2 转写+轮询+说话人分离）、`hotwords.py`（热词表）、`llm.py`（通义千问 provider）、`summarize.py`（纪要提示词与解析）、`pipeline.py`（全流程编排）
- **cli.py**：命令行入口，支持 `transcribe` / `normalize` / `upload` / `server` 四个子命令
- **app/server.py**：FastAPI 本地服务，RESTful API（上传/查询/下载）+ 后台管线执行
- **app/static/index.html**：前端页面，左中右三栏布局，支持拖拽上传、实时进度、纪要展示、AI 对话框
- **requirements.txt**：运行依赖清单
- **端到端验证通过**：samples/ 下 ~2h 真实会议音频（4 说话人 / 983 句）全流程跑通，纪要质量合格

### 决策
- 转写调用使用 `requests` 直调 RESTful API（SDK 不支持 `oss://` 前缀），详见 API_CONTRACTS.md

---

## [v0-prototype] - 2026-09-03

### 新增
- MVP 原型图（HTML 可视化线框）：`docs/design/wireframes/mvp-prototype.html`
- 细化 `docs/design/ui-spec.md`：完整页面结构、交互流程、热词管理页、设置页、快捷键

### 变更
- `MISSION.md` MVP 清单同步为 v1 云方案（DashScope），当前状态更新为「原型设计」
- `docs/PRD.md` 加入 AI 对话功能到核心场景与功能清单，明确「AI 对话是标配」产品定位

### 重构
- 界面布局从「上下结构」改为「左中右三栏布局」
- 右栏 AI 对话框作为产品标配功能，支持对话驱动操作（录音、转写、查询、设置、热词管理）

---

## [v0-skeleton] - 2026-09-03

### 新增
- 工作区骨架：`README` 入口、`AGENTS` 约定、`CHANGELOG`、`.env.example`、`.gitignore`
- `docs/` 分层：`ARCHITECTURE`、`API_CONTRACTS`、`GLOSSARY`、`adr/`、产品层占位（PRD/ROADMAP/design）
- 代码目录占位：`core/` `app/` `tests/` `scripts/` `data/`
- 初始化 git 仓库（main 分支）

### 决策
- **ADR-0001** MVP v1 走云方案（DashScope），不做本地语音解析
- **ADR-0002** ASR + 说话人分离 选 `paraformer-v2`
- **ADR-0003** 纪要生成 选 通义千问 `qwen-plus`

### 说明
- 云方案 v1 设计定稿，见 `MVP_PLAN.md`。
- 待办：P0 环境与冒烟测试尚未开始。
