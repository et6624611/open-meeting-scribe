---
title: "PROPOSAL: Qoder CLI 作为 AI 对话面板的工程化会话引擎（初步方案）"
description: "提议将本地 Qoder CLI 作为 OpenMeetingScribe AI 对话面板的可选外部 Agent 引擎：软件负责会议上下文的构建与供给，CLI 负责工程化多轮会话与工具执行，通过接入模式路由、stream-json 桥接与 MCP Bridge 实现两者集成。"
tags: ["proposal", "ai-chat", "agent", "qoder-cli", "architecture", "mcp", "ux"]
created_at: "2026-09-25"
updated_at: "2026-09-25"
version: "0.4.0"
author: "wangyongliang"
status: "draft"
category: "architecture"
related_docs: ["docs/PRD.md", "docs/ARCHITECTURE.md", "docs/adr/"]
---

# PROPOSAL-QODER-CLI-ENGINE：Qoder CLI 作为 AI 对话面板的工程化会话引擎

> 状态：**v0.4.0——实施中**：Phase 0（Spike 取证）、Phase 1（只读竖切片 + 前端最小改动）、Phase 2（MCP 双向桥）、Phase 3（意图自动分流 v1 / 三态模式 / 写操作审计 / 工作区保留清理）均已落地并实测；见 `docs/SPIKE-QODER-CLI-ENGINE.md` 与 `core/cli_engine/`、`core/agent_tools/`、`mcp-bridge/`。默认关闭（不破坏零配置即用）。
> 早期状态：v0.2 吸收产品/交互深度评审；v0.2.1 增补配置分层/多引擎适配层；v0.3.0 按 Phase 0 实测修订（M1/M2/M3，废弃 default 档与 allowed-tools 前置授权）。

---

## 1. 背景与动机

### 1.1 现状痛点
当前 AI 对话面板的工程化能力全部在软件内自建：

| 能力 | 现状实现 | 体量与局限 |
|---|---|---|
| Agent 循环 | `core/agent_loop.py`（ReAct，function calling 主 + 文本回退双轨，MAX_ITERATIONS=8，60s 超时） | 工具集有限，仅覆盖 task/项目数据的读写，无法做真正的文件级/代码级工作 |
| 上下文注入 | `app/routers/chat.py` `_build_chat_context_blocks()` 四维注入（页面/会议/项目/历史） | 手工维护注入块拼装逻辑，深度分析场景上下文供给不足 |
| 结构化输出 | 文本后处理提取（`extract_injectable_items`、Mermaid 关键词检测、`audit_reply_claims`） | 脆弱，依赖对模型自由文本的正则/意图猜测 |
| 会话记忆 | 前端手工截取最近 10 条 history 传回后端 | 无跨轮持久化，无法恢复会话 |

在单体应用内继续堆叠"工程化 Agent 能力"（沙箱执行、文件编辑、多步规划、上下文管理），本质是在重造一个 Coding Agent 的轮子，难度高、维护重、与主业（会议智能）偏离。

### 1.2 核心设想
**分工组合**：
- **软件（OpenMeetingScribe）** = 上下文环境提供方：会议转写、纪要、决策、说话人映射、项目知识库 —— 这些是软件独占的、Qoder CLI 自身拿不到的数据资产；
- **Qoder CLI** = 工程化会话引擎：成熟的 Agent 循环、工具集（读写文件/执行命令/检索）、原生会话持久化、模型与账号体系 —— 这些是软件自建代价最高的部分。

### 1.3 可行性前提（已验证，2026-09-25，本机 qodercli 1.1.53）
Qoder CLI 已具备被程序化无头调用的完整接口：

```
qoder -p --output-format stream-json        # 非交互 + 流式 JSON 输出
     --system-prompt / --append-system-prompt # 提示词注入（对应现有角色系统）
     --agent <name> / --agents <json>         # 自定义 Agent（对应 resolve_agent_role）
     -w <dir> / --add-dir <dir>               # 工作区与附加目录（对应上下文块供给）
     --attachment <file>                      # 文件附件注入
     -r <session-id> / --resume / --session-id # 原生会话持久化与恢复
     --tools / --allowed-tools / --disallowed-tools  # 工具集收敛
     --permission-mode <default|...>          # 权限模式
     --mcp-config <json>                      # 挂载自定义 MCP Server（双向集成抓手）
```

---

## 2. 总体架构

### 2.1 架构原则
1. **不替换、只新增**：现有直连/代理/云端 LLM 链路（`core/llm.py` + `core/routing.py`）完整保留，Qoder CLI 作为**第四种引擎接入模式**挂在路由决策之后，默认关闭。
2. **上下文出口标准化**：软件侧新增"上下文序列化器"，把四维上下文块落成 CLI 工作区内的文件，而非塞进单个巨型 prompt。
3. **结构化回传走 MCP**：软件把自己的读写 API 封装为本地 MCP Server 供 CLI 调用，替代/增强现有文本后处理提取。`/api/chat/stream` 对前端的 SSE 协议**向下兼容、只扩不破**（新增 cancel/artifact 类事件），但"前端零改动"不成立——模式选择器、路由回显、真取消为最小必要改动，详见 §3.9。

### 2.2 目标架构图

```
┌────────────────────────────── OpenMeetingScribe ──────────────────────────────┐
│                                                                              │
│  AiChatPanel.vue ──► /api/chat/stream (SSE，协议不变：token/stage/done/…)     │
│                          │                                                   │
│                    chat.py 编排层                                            │
│                     │        │                                               │
│          ┌──────────┘        └───────────┐                                   │
│          ▼                               ▼                                   │
│   现有 agent_loop.py              Engine Router（core/routing.py 扩展）       │
│   （轻量 QA / 简单问答）           access_mode += "qoder_cli"                  │
│          │                               │                                   │
│          │                     ┌─────────▼──────────┐                        │
│          │                     │ core/qoder_engine/ （新增）                   │
│          │                     │  ├ context_export.py  上下文序列化器          │
│          │                     │  ├ cli_runner.py      Popen + stream-json 桥 │
│          │                     │  └ event_bridge.py    CLI事件 → SSE事件映射   │
│          │                     └─────────┬──────────┘                        │
│          │                               │ ①写入 workspace                   │
│          │                               ▼                                   │
│          │                     data/qoder-workspace/<task_id>/                │
│          │                       ├─ AGENTS.md          (角色+任务说明)         │
│          │                       ├─ context/           (转写/纪要/决策/热词)   │
│          │                       └─ output/            (CLI 允许 writes 区)   │
│          │                               │                                   │
│          │                     ② qoder -p --output-format stream-json ...     │
│          │                               ▼                                   │
│          │                     ┌─────────────────────┐                        │
│          │                     │  Qoder CLI 子进程     │                       │
│          │                     │  (用户本机已登录)      │                      │
│          │                     └───────┬─────────────┘                        │
│          │                             │ ③ MCP 工具调用（localhost, 带会话token）
│          │                             ▼                                     │
│          │              mcp-bridge/  本地 MCP Server（新增，FastMCP）           │
│          │                工具：get_task / update_summary / add_todos /        │
│          │                      query_project / read_transcript ...           │
│          │                （复用 core/chat_actions + chat_edits 的受控入口）    │
│          │                             │                                     │
│          └──────────────► SSE 事件流 ◄──┘（token/stage/done 由 event_bridge 翻译）│
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 与现有 routing.py 的关系
`core/routing.py::get_routing_decision` 当前输出 `access_mode ∈ {local, hosted, byok}`。本方案扩展为：

- 新增 `engine=qoder_cli` 的决策分支：仅当 **用户在设置中显式启用 + CLI 可用性探针通过** 时返回该路由；
- 可用性探针（启动时 + 每次调用前）：`which qoder`、`qoder --version` ≥ 最低支持版本、`qoder status` 确认已登录；任一失败自动回退现有链路并在 stage 事件中提示用户；
- 默认策略不变："云端代理默认、用户零配置即用"——qoder_cli 是**高级可选项**，不进入默认路径。

---

## 3. 关键设计

### 3.1 上下文序列化器（context_export.py）
把 `_build_chat_context_blocks()` 的产出从"拼进 system_prompt 的字符串块"升级为"工作区文件"：

| 注入维度 | 落盘文件 | 说明 |
|---|---|---|
| 页面上下文 | `AGENTS.md` §环境 | 复用 `build_page_context()` 产出 |
| 会议转写原文 | `context/transcript.md` | 说话人已实名化（复用 `build_speaker_name_map()`） |
| 纪要 / 决策 / 待办 | `context/summary.md` `context/todos.json` | 直接取 task JSON |
| 项目知识库 | `--add-dir <project_path>` | 不复制，直接把项目文件夹挂进工作区 |
| 热词 | `context/hotwords.md` | 术语对照，帮助 CLI 理解专有名词 |

原则：**大文件走工作区（CLI 自己按需检索），小关键信息进 prompt**。这与现状"全部塞进注入块"相反，恰是 Qoder CLI 的 RAG/工具检索能力带来的红利。

### 3.2 CLI 调用与生命周期（cli_runner.py）
- 调用形态（示意）：

```python
proc = await asyncio.create_subprocess_exec(
    qoder_path, "-p", "--output-format", "stream-json",
    "-w", workspace_dir,
    "--add-dir", project_path,
    "--session-id", oms_session_id,          # task_id 派生，支持跨轮恢复
    "--append-system-prompt", task_brief,    # 本轮用户问题 + 轻量指令
    "--permission-mode", "default",
    "--disallowed-tools", "...",             # 收敛网络/破坏性工具
    "--mcp-config", bridge_config_path,      # 注入 MCP Bridge（含会话 token）
    stdout=PIPE, stderr=DEVNULL, stdin=DEVNULL,
)
```

- **生命周期：每轮一进程**（v1 取舍）。Popen 常驻模式（参照 `core/engine_host.py` 经验）作为 v2 优化项，先验证 stream-json 的会话恢复是否已覆盖性能需求；
- 超时熔断：沿用现有 60s 首 token / 120s 总超时的分级保护思想，数值对 CLI 场景重新标定（冷启动预留）；
- 进程异常退出：映射为现有 `llm_unavailable` 类错误，返回用户可理解提示（含"已回退内置引擎"选项）。

### 3.3 事件桥（event_bridge.py）
stream-json 事件 → 现有 SSE 协议的映射（协议形状可复用，但前端非零改动——模式选择器/cancel/轨迹卡见 §3.9）：

| CLI stream-json 事件（待 Spike 确认字段名） | SSE 事件 |
|---|---|
| assistant text delta | `{"type":"token","content":...}` |
| tool_use（开始/完成） | `{"type":"stage","stage":"tool_call","label":...}` |
| thinking 阶段 | `{"type":"stage","stage":"thinking"}` |
| result / done | `{"type":"done","metadata":{model,usage,...}}` |

待办注入项（`extracted_items`）在 v2 中改由 MCP 工具调用直接产生（见 3.4），v1 仍走现有后处理提取兜底。

### 3.4 MCP Bridge（双向集成的核心抓手）
新建独立模块 `mcp-bridge/`（FastMCP，stdio 或本机 HTTP + bearer token）：

- **读工具**：`get_task`、`read_transcript(带时间戳)`、`query_project_docs`、`list_todos`；
- **写工具**：`update_summary`、`add_todos`、`add_hotword`、`replace_transcript_span` —— 全部走 `core/chat_actions.py` / `core/chat_edits.py` 的**既有受控入口**，自动继承现有的审计（`audit_reply_claims`）、脏标记与状态同步机制，不另开写路径；
- **鉴权**：`--mcp-config` 由软件在每次启动 CLI 时动态生成，携带仅对本轮/本会话有效的短时 token；Bridge 只监听 127.0.0.1；
- **收益**：AI 面板的"修改纪要/追加决策"等动作从「LLM 输出文本 → 正则解析 → 执行」升级为「结构化 tool call → 直接执行 → 结果回传」，可靠性质变。

### 3.5 意图分流（调用哪个引擎）
不是所有消息都该交给 CLI。在 chat.py 编排层增加轻量分流器：

| 请求类型 | 路由 | 示例 |
|---|---|---|
| 简单问答 / 摘要类 | 现有 agent_loop（直连 LLM） | "这个会议谁提到了预算？" |
| 工程化请求 | qoder_cli | "把这份纪要按公司模板重写成正式报告，保存到项目文件夹" / "对比这三次会议的行动项完成情况，生成跟踪表" |
| 用户显式切换 | 面板提供"深度模式"开关 | 手动强制走 CLI |

分流器 v1 只做关键词/规则判断（复用 `_detect_diagram_intent` 的成熟模式），v2 可升级为 LLM 前置分类。

### 3.6 会话与多轮
- `session-id` 由 `task_id + 会话序号` 派生，CLI 原生持久化替代现在"前端截 10 条 history"的方案；换轮/继续时 `-r` 恢复；
- 软件侧仍保留 messages 兜底：CLI 会话不可恢复（用户清理、版本升级）时回退现有链路重建上下文。

### 3.7 安全与数据边界
1. **工作区隔离**：CLI 只能访问 `data/qoder-workspace/<task_id>/` 与显式 `--add-dir` 的项目路径，其余目录不可见；
2. **写权限策略**（开放决策点 D3）：v1 建议 CLI 仅允许写 `workspace/output/`，落盘到会议纪要等正式位置必须经 MCP 写工具（受审计）；
3. **工具收敛**：`--disallowed-tools` 默认禁用网络访问、破坏性命令；**（v0.3 实测修订）`--permission-mode` 禁用 `default`**——无头模式下它静默拒绝且 `result.permission_denials` 为空、用户与软件都拿不到原因；授权档位在 `dont_ask`（只读+可解释拒绝）/ `accept_edits` / `auto` 三档中前置选定（§3.9-3）；
4. **不越过的红线**：CLI 进程不得接触 `settings.json` 中的 API Key、用户凭据；MCP token 单轮有效；
5. **审计**：CLI 侧的 MCP 写操作并入现有 `logs/audit.log` 体系。

### 3.8 计费与配额
- qoder_cli 模式下，模型消耗发生在 **用户自己的 Qoder 账号**内，不经过软件的 `core/metering.py` 与云端代理计费——对本软件是成本减负，但需：
  - 用量 JSONL 中仍记录"引擎=qoder_cli、轮次、token（取自 stream-json usage）"供用户自查，标记为不计费；
  - 设置页与 AI 面板明确显示当前引擎，避免用户误以为消耗订阅额度；
- 反向问题（开放决策点 D5）：未来若软件以 SaaS 形态分发，是否允许打包/引导安装 CLI、是否谈联合授权，超出本方案范围。

### 3.9 交互设计（v0.2 新增 · 产品/UX 评审结论）

> 核心判断：本集成不是"协议翻译问题"，而是**交互范式切换**——现有面板的一切 UI 假设是"秒级、无状态、单向流"的问答；智能体模式引入的是"分钟级、有状态、带副作用执行"的任务。以下 8 项是落地前置设计，缺任何一项都会把架构优势变成体验黑箱。

1. **模式选择器（会话级）**：输入区内左侧轻量 pill——`问答 ⚡ / 智能体 🤖 / 自动`，沿用斜杠指令面板培养的"输入区=控制区"心智；选择随 `AiSession` 持久化（正好激活 `stores/aiSessions.ts` 中预留未用的每会话 role 字段语义位）。"自动"接受 §3.5 分流器建议，但**实际路由必须以可见 chip 回显**（"本次由智能体执行"）——静默分流摧毁信任。**注意概念正交**：角色（人格/提示词，AgentsView 全局单激活）≠ 模式（执行引擎），需在 GLOSSARY 消歧，否则用户会把三者混为一谈。
2. **切换即预告成本归属**：切到智能体模式当场明示"将调用本机 Qoder CLI，消耗你个人的 Qoder 额度，不经本软件计费"（§3.8 的"设置页显示引擎"太弱，成本切换必须发生在决策点而非事后）；探针失败的引导文案就地展示，参照 `AccessModeCards.vue` 的卡内置上下文态范式（hosted→需登录、byok→缺 Key），不要把用户踢回设置页。
3. **授权前置卡（新增风险 R8 的对策）**：`-p` 无头模式下无人能应答 CLI 的运行时权限询问，`--permission-mode default`（§3.7-3）实际退化为**静默失败/超时**。授权必须前置为发起时刻的一张"本次任务授权范围"卡（只读工作区 ✅ / 写 output ✅ / MCP 写工具 ✅ / 联网 ❌），由 UI 选择映射到 `--allowed-tools / --disallowed-tools` 的具体生成——从"运行时弹窗"变为"发起前的合同"。
4. **执行轨迹卡（含产物区）**：现有实现把 stages 存入 `msg.stages` 却从不渲染，done 后 300ms 永久抹掉（`useAiChat.ts` 已知缺陷）——秒级问答无伤，分钟级任务的"回看它干了什么"是审计与信任基础设施。应做成可折叠轨迹卡（每步：图标+label+状态+耗时），与 PRD §演进方向"折叠未读卡片"定位吻合。配套两件事：① `TOOL_LABELS/TOOL_ICONS` 硬编码表抽为共享资源并加未知工具降级样式（CLI 的 Write/Bash 等不能裸显英文 name+🔧）；② 轨迹卡新增**产物区**，列出 `workspace/output/` 文件并提供"采纳到纪要"入口——没有产物区，D3 的"仅允许写 output/"就是黑洞。
5. **真取消协议**：前端 stop = `AbortController.abort()` 只断 fetch，**CLI 子进程会继续跑、继续写、继续花用户的钱**。协议需新增 cancel 端点/事件（后端 kill 进程树 + 标记会话中断），UI 语义区分"停止生成"（现语义）与"终止任务"（新语义）。
6. **分钟级等待体验与会话任务化**：spinner+秒表是为秒级设计的；轨迹卡需"已执行 N 步 / 正在 X"计数感，完成接系统通知（与 REQ-TRANSCRIBE-PROGRESS 的进度可视化统一交互语言）。用户切页/关面板会孤儿化长任务——Phase 2 排入"会话任务化"（服务端续跑 + 重连/轮询 + 消息栏未读卡提醒）。
7. **结构化回写显性化**：MCP 写工具产生的变更统一以既有 verified-changes 卡（"字段 旧值→新值"+通过徽标）回显，而非只体现在下轮文本里；注入提示条从"全部注入/忽略"全有全无升级为**逐条勾选**（CLI 一次产出 20 条待办时全有全无不可接受）。另：`useAiChat.ts` 的 tool_result 回填匹配在并行工具调用下可能错位，CLI 恰会并行调用——Spike 顺带验证。
8. **命名与入口排雷**：对外术语统一用**「智能体模式」**而非"第四引擎"——"引擎"一词已被 ASR 计算引擎（`/api/engine/status`）占用，EngineBadge/AccessStatusState 枚举均无 qoder_cli 位。对用户这是能力开关而非传输通道，故 access_mode 三卡保持不动，智能体作为独立设置区 + 面板 pill（反向支持 D1 选"正交"）。

### 3.10 配置分层归属（v0.2.1 新增 · 回答"Qoder CLI 的配置放在哪里"）

按**归属**拆三层，禁止混放：

| 层 | 内容 | 落位 | 原则 |
|---|---|---|---|
| ① 集成偏好（用户级、持久） | 智能体模式开关、引擎选择、授权档位、会话持久化开关（D5）、workspace 保留天数、CLI 路径覆盖 | `data/settings.json` 新增 `chat_engine` 命名空间（**正交于 `access_mode`**，与 D1 裁决一致） | 复用既有 settings store 的持久化/迁移/测试夹具（`SETTINGS_FILE` 隔离）模式；`/api/settings/routing` 扩字段下发前端 |
| ② 引擎自身配置（账号/登录/模型） | Qoder 账号态、CLI 内部模型偏好 | **CLI 自有用户目录（如 `~/.qoder`），软件零读写** | 软件只做探针（`--version`/`status`）与登录态**展示**；登录/登出引导用户在 CLI 本身完成。不代理登录态、不把任何 Token 复制进 settings.json |
| ③ 运行时上下文（每轮动态生成） | `AGENTS.md`、`context/` 文件、`--mcp-config`（含短时 token） | workspace 树；**mcp-config 落系统临时目录（0600、用后即删）** | 敏感物不进 CLI 可达面 |

**已识别的隔离坑（v0.2.1 补充）**：§2.2 原设计 workspace 位于 `data/qoder-workspace/`，使 CLI 可达面覆盖 `data/` 子树，而 `data/settings.json`（内含 API Key，见 §3.7-4 红线）就在隔壁。CLI 的读边界由 `-w/--add-dir` 约定，属**外部二进制行为，不可强制**。两个整改：① workspace 根目录迁出 `data/`（与 settings 树物理隔离），命名随 §3.11 泛化为 `agent-workspace/<engine_id>/<task_id>/`；② "CLI 是否能读取 `-w`/`--add-dir` 之外路径"加入 Phase 0 Spike 探针清单（第 7 项）——若 CLI 读边界不可信，§3.7-1 的"工作区隔离"从设计承诺降级为缓解措施，R7 需上调处置。

UI 入口：设置页新增「智能体模式」类目（与 `AccessModeCards` 三卡并列、不合并），面板 pill（§3.9-1）只做快捷态；路径覆盖、授权档位等高级项收在设置页，维持"默认零配置、高级可选"。

### 3.11 多 CLI 引擎适配层（v0.2.1 新增 · 回答"如何适配其他软件的 CLI"）

前提判断：Qoder CLI 的 flag 体系与 Claude Code 高度同形，Codex / Gemini 等 CLI 亦有非交互 JSON 流模式（各家具体 flag 与 schema 需逐一 Spike 调研，不预设存在）。"本地 CLI Agent"有稳定共性形态，抽象成立；但各家**能力不齐**（会话恢复、MCP 注入、预授权、附加目录语义均为变量），适配层核心不是"统一调用"，而是**能力声明 + 归一化降级**：

1. **归一化事件模型**：现有 SSE 词汇表（`token/stage/tool_call/tool_result/done/error`）已是事实标准，升格为内部 canonical 模型；`event_bridge` 从 qoder 专属改为共享层，各 adapter 只负责"原生流 → canonical"翻译。
2. **声明式 manifest**：`core/cli_engines/manifests/<engine_id>.json` 描述——探针命令与最低版本、argv 模板（各能力的真实 flag 名）、能力开关（`session_resume / mcp_injection / pre_authorization / add_dir`）、parser 模块标识、工具中文标签映射资源（对接 §3.9-4 共享标签表）。新增引擎 = 一份 manifest + 一个 parser，不动主链路。
3. **能力驱动 UI 降级**：无 `session_resume` → 隐藏"继续深度会话"；无 `mcp_injection` → 结构化回写退回文本后处理兜底；无 `pre_authorization` → 授权卡（§3.9-3）置灰并明示"该引擎权限控制较弱，建议只读档"。**最坏交集陷阱**在序列化器：无 `--add-dir` 类能力的引擎，§3.1 退化为"全部上下文复制进单一 workspace"。
4. **范围控制**：v1 仅交付 `qoder-cli` 一个 manifest/adapter 实现，适配层是**防腐设计而非开放平台**——不做插件市场、不开放用户自带 adapter（见 D8）。理由：R1 协议漂移在多引擎下乘法放大，每个引擎需独立契约测试样本库，维护成本按引擎数线性以上增长。
5. **命名泛化随此层落地**：`core/qoder_engine/` → `core/cli_engine/`（框架）+ `core/cli_engine/adapters/qoder_cli.py`（首个实现）；路由决策输出 `engine_id` 而非布尔位，为未来第二引擎留形不填实。

---



## 4. 风险清单

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | stream-json 属 CLI 内部协议，版本升级可能破坏字段兼容性 | 高 | 最低版本探针 + event_bridge 宽容解析（未知事件降级为 token/日志）+ 契约测试固定样本回放 |
| R2 | 用户未安装/未登录 CLI，体验断层 | 中 | 探针失败自动回退 + 设置页一键诊断；该模式永远非默认 |
| R3 | 冷启动/首 token 延迟高于直连 | 中 | 每轮一进程 + stage 事件填充等待；v2 评估常驻进程 |
| R4 | CLI 大上下文导致时延与不可控成本 | 中 | 上下文序列化器控制落盘体量；`--max-output-tokens`；分流器避免轻请求进 CLI |
| R5 | 写路径双轨（MCP 工具 vs 直接文件写）造成数据不一致 | 中 | 3.7-2 策略：正式数据只允许经 MCP 写工具；output/ 区仅作草稿 |
| R6 | 与开源策略冲突（上游依赖非开源二进制） | 低 | 作为可选适配器隔离在 `core/qoder_engine/`，核心不发版依赖 CLI；LICENSE/NOTICE 说明 |
| R7 | 会议敏感数据离开软件进程边界（进入 CLI 会话文件持久化） | 高 | 明示告知 + `--no-session-persistence` 可选项 + workspace 用后可清 |
| R8 | 无头模式（`-p`）下 CLI 运行时权限询问无人应答，需审批的工具静默失败/超时，用户只见"转圈后报错" | 高 | 授权前置卡（§3.9-3）：发起时刻将授权范围编译为 `--allowed-tools/--disallowed-tools`，消除运行时询问；Spike 实测权限行为（Phase 0 第 4 项） |
| R9 | 分钟级任务击穿现前端假设：fetch 断开后子进程失控、切页孤儿化、无产物出口 | 高 | 真取消协议 + 执行轨迹卡含产物区 + Phase 2 会话任务化（§3.9-4/5/6） |

---

## 5. 分阶段路线

### Phase 0：Spike（1~1.5 天，先于一切投入）
- 目标：证伪/证实七个关键假设：
  1. `qoder -p --output-format stream-json` 的事件结构能否无损映射到现有 token/stage/done SSE 协议；
  2. `--session-id/-r` 跨进程恢复是否可靠、延迟如何；
  3. `--mcp-config` 挂载自定义 stdio MCP Server 后，CLI 是否稳定调用其工具；
  4. **（v0.2 新增）无头模式权限行为实测**：触发需审批的工具调用时 CLI 如何失败（挂起/报错/跳过），`--allowed-tools` 预授权能否完全消除运行时询问（决定 R8 对策成立性，对应 §3.9-3）；
  5. **（v0.2 新增）任意 cwd 启动验证**：从非 repo 根目录拉起 CLI、workspace 用相对/绝对路径混合引用是否正常（呼应项目已登记的"子进程按 repo 根解析相对路径"已知隐患）；
  6. **（v0.2 新增）并行 tool_use/tool_result 归属**：stream-json 中并行工具调用的事件能否正确配对回填（现有 `useAiChat.ts` 匹配写法可疑，需真实样本取证）；
  7. **（v0.2.1 新增）CLI 读边界可信性**：受控尝试让 CLI 读取 `-w`/`--add-dir` 之外的路径（含 settings.json 同级目录），验证 §3.7-1"工作区隔离"是硬边界还是软约定（决定 R7 处置级别与 §3.10 workspace 迁移必要性）。
- 交付：`docs/SPIKE-QODER-CLI-ENGINE.md`（结论 + 原始 stream-json 样本），独立脚本 `scripts/spike_qoder_cli.py`，不并入主程序。
- **决策门槛：七项中任一证伪且无替代方案，则本方案对应阶段降级为备选**（第 1~3 项证伪动架构根基；第 4~7 项证伪动 §3.9/§3.10 交互与安全设计成立性）。

### Phase 1：只读 PoC（约 1 周 + 前端最小改动）
- `core/qoder_engine/` 三件套（context_export / cli_runner / event_bridge）+ 路由分支 + 设置页开关（本地开关，非默认）；
- 仅打通"深度问答"：上下文进、流式回答出，不含 MCP 写；
- **（v0.2 修订）前端最小改动验收**（撤销"零改动"假设）：模式 pill（问答/智能体/自动）+ 实际路由回显 chip + cancel 通道打通 + 探针失败就地引导——现有面板能流式显示 CLI 回答且用户永远知道谁在干活、能真正终止任务；
- **（v0.2 新增）两项 UI 前置项独立立项、先于 Phase 1 执行**（对现有 agent_loop 同样有价值，不依赖 CLI 落地）：① `msg.stages` 折叠执行轨迹卡渲染修复（当前存而不显、done 即抹）；② 工具中文标签/图标映射表抽为共享资源 + 未知工具降级样式。

### Phase 2：MCP Bridge（约 1~2 周）
- `mcp-bridge/` 读工具 + 写工具（走既有受控入口）+ 鉴权；
- `extracted_items`/编辑类意图在 qoder_cli 模式下改由 tool call 直出，保留文本后处理兜底；
- 意图分流器 v1（规则版）；
- **（v0.2 新增）会话任务化**：服务端任务句柄 + 断线重连/轮询 + 完成系统通知，解决切页/关面板孤儿化长任务（§3.9-6）；MCP 写变更统一经 verified-changes 卡回显、注入条升级逐条勾选（§3.9-7）。

### Phase 3：体验完善与决策点收口
- 会话恢复 UX（继续上次深度会话）、workspace 清理策略、审计接入、灰度与文档。

---

## 6. 开放决策点（供评审者重点评估）

| # | 问题 | 方案倾向 |
|---|---|---|
| D1 | qoder_cli 定位为"第四种 access_mode"还是"AI 面板的独立引擎维度"（与 access_mode 正交）？ | 倾向正交：access_mode 管 LLM/ASR 通道，引擎维度只管 chat 面板 |
| D2 | 每轮一进程 vs 常驻 CLI 进程（复用 engine_host 模式）？ | v1 每轮一进程，Spike 实测冷启动延迟后定 |
| D3 | CLI 是否允许直接写 project_path（经用户确认）？ | v1 禁止，仅 output/ + MCP 写；评审是否过严 |
| D4 | 意图分流的误判代价：轻请求误入 CLI（慢）vs 重请求误入直连（能力不足）？ | 面板提供显式"深度模式"开关兜底，分流器仅做默认建议 |
| D5 | 会话持久化（R7）默认开还是关？涉及"跨轮恢复能力"与"数据留痕"的取舍 | 默认开 + 设置页明示 + 一键清除；企业场景可能要求默认关 |
| D6 | 是否支持非会议场景（项目页/设置页）也能调 CLI 干工程化活？ | Phase 3 再评估，架构上 workspace 以 task_id 为主键需泛化（§3.11 已预留 `engine_id/task_id` 两级路径） |
| D7 | 模式选择器是否需要"消息级临时切换"（长按 pill 单次覆盖）？（v0.2 新增） | 倾向不做——会话级 + 路由回显已够；消息级会引发同会话双上下文（CLI session vs history）割裂且用户不可见 |
| D8 | 是否开放用户自带 CLI 引擎（第三方 adapter / 手写 manifest）？（v0.2.1 新增） | 倾向**不开放**（§3.11-4）：适配层是防腐设计非开放平台，协议漂移维护成本按引擎数乘法放大；v1 仅交付 qoder-cli 实现 |
| D9 | 集成偏好是否允许项目级覆盖（不同项目用不同引擎/授权档）？（v0.2.1 新增） | v1 仅全局 `chat_engine` 设置（§3.10-①），项目级覆盖待 D6 场景验证后再评估，避免配置优先级迷宫 |

### v0.2 产品/UX 评审倾向（2026-09-25，待项目方终审确认）

- **D1 → 裁定"正交"**：UI 侧依据——用户感知这是"能力开关"而非"传输通道"，塞进 AccessModeCards 第四张卡会制造"智能体与 local/hosted 互斥"的错误心智。术语定「智能体模式」，与「角色」「接入模式」三词进 GLOSSARY 消歧（§3.9-8）。
- **D3 → 维持 v1 禁止直写 project_path**，但**以执行轨迹卡的"产物区"为成立前提**（§3.9-4）：没有可见的 output/ 文件列表与"采纳"动作，该约束就是体验黑洞。
- **D4 → 自动分流仅作默认建议，路由结果必须可见回显**（§3.9-1）；轻/重误判代价不对称（慢可忍、答非所问不可忍），故误入 CLI 方向可宽容、误入直连方向规则应偏保守。
- **D5 → 默认开**，但"一键清除"不能是设置页装饰：**删除面板会话标签必须联动清理对应 workspace + 归档 CLI session**，否则数据留痕只进不出。
- **D7（新增，待评审）**：见决策表——v0.2 倾向不做消息级临时切换。

---

## 7. 不做什么（显式排除）

1. 不用 Qoder CLI 替换现有轻量问答链路——直连/代理 LLM 调用永远是一等公民；
2. 不依赖 Qoder CLI 的模型 API 转售或逆向——只把它当本机用户已授权的进程；
3. v1 不做 Windows/macOS 之外的平台适配验证；
4. 不在本方案内解决 CLI 的安装分发问题（仅探针 + 引导）。

---

## 8. 附录：Spike 验证脚本骨架（示意）

```python
# scripts/spike_qoder_cli.py —— 不进主程序，仅验证用
import asyncio, json, tempfile, pathlib

async def main():
    ws = pathlib.Path(tempfile.mkdtemp(prefix="oms-qoder-spike-"))
    (ws / "context").mkdir()
    (ws / "context" / "transcript.md").write_text("张三：我建议 Q3 上线…\n李四：预算不够…", encoding="utf-8")
    proc = await asyncio.create_subprocess_exec(
        "qoder", "-p", "--output-format", "stream-json",
        "-w", str(ws), "--no-session-persistence",
        "阅读 context/transcript.md，输出会议决策点的 JSON 列表",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    async for line in proc.stdout:
        evt = json.loads(line)
        print(evt.get("type"), str(evt)[:120])   # 收集真实事件结构 → SPIKE 报告

asyncio.run(main())
```

---

*文档版本 0.2.1（v0.2：产品/交互深度评审——§3.9、R8/R9、Spike 4~6、UI 前置项、D1/D3/D4/D5 倾向；v0.2.1：§3.10 配置分层归属、§3.11 多 CLI 引擎适配层、Spike 7、D7/D8/D9）。评审通过后应升级 1.0.0 并同步录入 `docs/adr/` 决策记录。*
