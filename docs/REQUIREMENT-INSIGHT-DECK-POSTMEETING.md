---
title: 需求记录 — 洞察台会后化（纪要页展示 · 会后补分析 · AI 上下文注入）
description: 将洞察台从实时转写专属能力升级为会议全生命周期资产：纪要页新增洞察 Tab、支持按任务会后补分析、洞察结果注入 AI 会话上下文（含 CLI 引擎工作区），使用户会后可查看、可追问、可与洞察对话。
id: REQ-INSIGHT-DECK-POSTMEETING
version: 0.3.0
status: implemented（2026-09-25 全量实施 R1–R4，含 v0.2.0 评审契约：409/504/mode；待产品验收后升 1.0.0）
created_at: 2026-09-25
updated_at: 2026-09-25
date: 2026-09-25
category: 功能演进 / 洞察台
tags: ["insight-deck", "post-meeting", "chat-context", "requirement"]
author: wangyongliang
related:
  - docs/REQUIREMENT-DECISION-CENTER.md（决策对象化——本需求聚焦洞察消息，不重叠）
  - docs/API_CONTRACTS.md（新端点契约需在此登记）
  - docs/VUE_COMPONENT_MAP.md（纪要页新 Tab 需在此登记）
  - docs/design/AGENT_ROLE_SYSTEM.md（会后补分析沿用角色洞察 prompt 链路）
owner: 产品经理（定义）/ 待指派（工程实施）
---

# 需求记录：洞察台会后化（REQ-INSIGHT-DECK-POSTMEETING）

## 1. Problem（要解决什么）

洞察台（Insight Deck）当前是**实时转写场景的专属功能**：只出现在录音页，只分析会中最近转写行。会议一结束，洞察台对用户就"消失"了——尽管它的数据其实一直都在。

代码调研（2026-09-25，行号均已核实）确认的四层现状：

1. **持久化已就绪（数据层已经是"会议本位"）**：洞察消息按会议落盘 `data/tasks/<task_id>.insights.json`，读写端点 `GET/POST /api/insights/messages/{task_id}` 已存在（`app/routers/insights.py:78-111`）；前端 `useAiInsights.ts` 为模块级单例，`ensureTaskLoaded(taskId)`（L120）已支持按会议从后端兜底拉取。**缺的不是存储，是使用场景**。
2. **展示仅存在于录音页**：洞察面板只在 `RecordingView.vue:125-139` 渲染；纪要页 Tab 集合 `TAB_IDS = ['transcript', 'notes', 'summary', 'todos']`（`useGeneratingData.ts:202`）没有洞察入口；侧边栏洞察指示器以 `activeRecordingTaskId` 为显示门槛（`ActivityRail.vue:81-85`），会后不可见。
3. **AI 会话上下文完全不含洞察**：`_build_chat_context_blocks`（`app/routers/chat.py:389` 起）注入实时转写 / 会议元信息 / 纪要 / 原文 / 待办 / 项目资料 / 页面上下文六类块，**不读洞察文件**；stream 路径的上下文构建（同文件 L740 起）同样缺失；`build_page_context('generating')` 直接返回 None（`core/chat_context.py:67-68`）；CLI 引擎工作区只导出 `transcript.md / summary.md / todos.json`（`core/cli_engine/context_export.py:90-107`）。**后果：会后用户问 AI"洞察台提到的风险怎么应对"，AI 一无所知**。
4. **无会后分析能力**：`POST /api/insights/analyze`（`app/routers/insights.py:44-65`）是纯无状态端点，要求前端传入会中的 `recent_lines + chapter_titles`，只有 RecordingView 手动/自动两个触发点。会后想基于完整会议内容补一轮洞察，没有任何入口。

**期望结果**：洞察台成为会议纪要的组成部分和 AI 会话上下文的一等来源——会中产生的洞察会后可看、可追问；会后还能基于全文补分析；AI（含 CLI 智能体引擎）回答问题时知晓洞察台的观察结论。

**证据来源**：同日代码调研 + 项目方直接反馈（本需求由用户提出："洞察台不应该只是实时转写中的内容，应该在完成的会议纪要中也有，且持久化存储，成为 AI 会话上下文的一部分，这样即使会后，用户也能与之交流"）。

## 2. Target Users and Scenarios

| 用户 | 场景 | 现在 | 交付后 |
|---|---|---|---|
| 会议参与者 | 会后复盘："会中 AI 提示过什么风险？" | 洞察随录音页关闭而不可达 | 纪要页「洞察」Tab 完整回看，含 Mermaid 决策流图 |
| 会议主持人 | 拿到完整纪要后想要更全局的洞察 | 无入口 | 点「分析本场会议」基于全文 + 章节补一轮综合洞察 |
| 任意用户 | 会后与 AI 讨论："洞察台说方案 B 有资源冲突，怎么缓解？" | AI 不知道洞察台说过什么 | 洞察块注入系统提示词，AI 可引用、可展开 |
| AI Agent（CLI 引擎） | 智能体模式生成分析报告需要会中观察 | 工作区无洞察文件 | `context/insights.md` 随其他上下文一并导出 |
| 图表使用者 | 会后想让 AI 修改某张洞察图 | `lastViewedDiagram` 只在录音页生效（`useAiChat.ts:139`） | 纪要页展开洞察卡片同样进入图修改链路 |

## 3. 产品目标与成功标准

**目标**：一场会议结束后，洞察台的全部产出（消息卡片 + 图）对人和对 AI 都持续可用，且可增量丰富。

**成功标准（无 analytics 体系，采用可测代理指标）**：

- 任意含洞察消息的已完成会议，在纪要页 2 次点击内可回看全部洞察卡片并渲染 Mermaid 图。
- 对含洞察消息的任务发起 AI 对话，系统提示词中稳定出现「会议洞察台」注入块（dogfooding 10 轮对话日志核验）。
- 会后补分析在转写 ≥ 5 句且有章节的任意任务上可成功产出卡片（或明确提示无发现），消息落盘后刷新不丢失。

## 4. Scope

### R1 — 纪要页「洞察」Tab（表现层，P0）

- `frontend/src/composables/useGeneratingData.ts`：`TAB_IDS` 追加第 5 项 `insights`，Tab 文案走 `generating.tabs.insights` 双语 i18n 键；Tab 图标新增一枚线性 SVG（与现有 4 个 Tab 同风格），命名与录音页「洞察台」及 `GLOSSARY.md` 术语口径对齐。
- **面板复用口径（v0.2.0 修正）**：`RecInsightsPanel.vue`（`frontend/src/components/recording/`）**本身已是独立组件**，不做"抽通用渲染层"式拆分重构；改造方式为新增 `mode: 'live' | 'readonly'` prop，默认 `live` 保持录音页行为不变，纪要页传 `readonly`。
- **只读态控件清单（v0.2.0 补全）**，`readonly` 模式下：
  - 隐藏：自动频率选择（`rec-insights-freq`）、**洞察启用开关（toggle-switch，会后无意义）**、会中实时横幅等仅会中有效控件；
  - 变身：手动分析按钮改为「分析本场会议」，接 R2 端点，复用现有 `is-loading` / `rec-insights-spin` 转圈态，响应（含 409 冲突提示）到达前保持禁用防重复点击；
  - 降级：录音页的「占满内容区」expand 逻辑依赖 `.rec-content-area` 布局，纪要页无对应物——`readonly` 模式隐藏面板级 expand，仅保留卡片内展开/折叠；`lastViewedDiagram` 链路挂在卡片展开上（见 R3），不受影响；
  - 保留：展开/折叠、确认折叠、Mermaid 渲染、跳转原文时间点；含图卡片在 Tab 面板窄容器下的渲染（留白/横向滚动）需 UI 设计师出 1 张示意后再进派工验收。
- 数据加载：进入纪要页（选定 task）时调用 `insights.setCurrentTask(taskId)` / `ensureTaskLoaded(taskId)`；卡片上的 `acknowledged/read` 等状态变更仍走既有 `persistMessages` 全量保存（已知覆盖写竞态见 §9 风险表）。
- 空态：无洞察消息时 Tab 常驻（§11-① 已裁决），显示引导文案 +「分析本场会议」按钮（接 R2）；引导文案需明示「洞察是 AI 的过程观察，非纪要内容」，与 R3 注入块「供参考非事实源」同一心智。
- 侧边指示器：`ActivityRail.vue` 的显示条件由 `activeRecordingTaskId` 放宽为「当前任务（会中或会后）存在洞察消息且有未读」，未读口径即既有 `unreadCount`（`acknowledged` 字段）；会后不再显示"实时"语义的呼吸动效；纪要页 Tab 名上不叠加第二层未读徽标，避免双重提醒噪音。

### R2 — 会后补分析端点（服务层，P0）

- 新增 `POST /api/insights/analyze/task/{task_id}`（`app/routers/insights.py`）：
  - 后端从任务 JSON 读取 `dialogue` 与 `chapters`，自行构造 `recent_lines`（取全文时间序**最近 K 句，K 为后端配置项、默认 40**，含 `text/speaker_id/begin_time`，说话人实名化走 `core.speakers.normalize_speaker_name`）与 `chapter_titles`；
  - 复用 `core.insights.run_analysis`，角色 prompt 注入与 `model_tier` 防幻觉守卫链路不变（与现有 `/analyze` 端点对等）；
  - 任务状态非 `completed` 或无转写内容时返回 400（`detail` 说明原因）。
- **时长与幂等契约（v0.2.0 新增，派工前置）**：
  - 同步执行，端点整体超时守护默认 60 秒（配置项），超时返回 504 且**不写盘**，前端 toast「分析超时，请稍后重试」；
  - **并发守卫**：同一 `task_id` 已有分析在跑时再次调用直接返回 **409**（`detail` 说明"该会议正在分析中"），不排队、不并行重复跑；前端按钮在响应到达前保持 loading 禁用，409 按提示文案处理不算失败；
  - **追加语义明示**：守卫只防"同时"，不防"先后"——同一会议多次成功分析会追加多批消息（各自带 `phase=post_meeting`），属预期行为；空态引导文案与「分析本场会议」按钮 tooltip 需说明"每次分析可能产生新的观察"。
- **写盘归属后端**：`has_finding=true` 时由后端将新消息**追加**写入 `<task_id>.insights.json`（走 `core/fs_atomic.atomic_write_json`，防半截文件），消息对象标记 `phase: "post_meeting"`、`source: "system"`；响应体返回 `{result, messages}`（完整消息列表），前端以重拉方式刷新面板，**不经前端 persistMessages 覆盖写**——规避会中/会后新旧客户端交叉全量覆盖的竞态。
- 无发现 / LLM 失败：沿用安全默认值语义（`has_finding=false`），不写盘，前端 toast 正面反馈（对齐手动分析路径的现有约定）。
- **向后兼容**：消息对象新增可选字段 `phase`（`"meeting" | "post_meeting"`），存量文件缺字段一律按 `"meeting"` 读取；卡片对 `post_meeting` 显示「会后」徽标。
- 现有无状态 `/api/insights/analyze` 端点保留不动，继续服务会中路径。

### R3 — 洞察注入 AI 会话上下文（上下文层，P0）

- `app/routers/chat.py`：**qa 与 stream 两条路径**的上下文构建中，当 `data.task_id` 有效时新增注入块：
  ```
  ## 会议洞察台（AI 会中/会后观察，供参考非事实源）
  - [会中] {title}：{body 摘要 ≤200 字}（建议：{solution ≤100 字}）
  ...
  ```
  读取 `<task_id>.insights.json`，仅收 `has_finding` 有效消息，取**最近 N=5 条**、整块**截断 1200 字符**；`diagram` 源码不整段注入（token 不友好），仅在消息含图时附一行「（该洞察附决策流图）」。文件不存在 / 无有效消息时不产生块（三态：有洞察 / 无洞察 / 无文件）。
- `core/chat_context.py`：`build_page_context('generating')` 由 None 改为：「用户正在查看会议纪要，可查看/引用洞察台结论回答问题」。
- CLI 引擎：`core/cli_engine/context_export.py` 在 task 存在且洞察文件非空时导出 `context/insights.md`（标题 + 正文 + solution + diagram 源码，全量不截断——工作区文件模式对 token 预算宽松），并在 AGENTS.md 说明区提及该文件。
- 图对话链路：纪要页展开含图洞察卡片时同步更新 `insights.lastViewedDiagram`（复用 `toggleExpanded` 既有逻辑，仅解耦"录音页专属"的隐含假设），使会后「把这张图的 XX 改掉」可用。

### R4 — 生命周期与文档配套（P1）

- **删除级联已存在**：任务删除端点已按 `.json / .joblog.jsonl / .insights.json` 三件套清理（`app/routers/tasks.py:326-330`），无需改动。
- **孤儿清理缺口**：`app/task_store.py` 启动恢复的两处孤儿录音清理（L248-252、L260-262）只删任务 JSON 与 joblog，**遗漏 `.insights.json`**——补齐（同一遍历内顺带处理，无迁移成本）。
- `docs/API_CONTRACTS.md` 登记 R2 新端点与 `phase` 字段；`docs/VUE_COMPONENT_MAP.md` 登记纪要页第 5 个 Tab。
- i18n 双语文案清单：Tab 名、空态引导、补分析按钮、「会后」徽标、失败 toast。

**依赖**：R1 展示层可先行（不依赖 R2，只读回看 + 对话）；R1 的空态「分析本场会议」按钮依赖 R2；R3 独立于 R1/R2，可并行；R4 收口项。

## 5. Non-Goals（v1 明确不做）

- **纪要 pipeline 完成时自动追加最终洞察分析**——已裁决不做（项目方 2026-09-25 选择"支持会后补分析"而非"自动分析一次"），列为使用反馈观察项：若用户很少手动补分析，v1.1 重提。
- 跨会议洞察聚合视图（洞察是"过程观察"语义，不适配决策中心式的全量管理）。
- 洞察内容写入纪要 markdown / 导出文档正文（洞察与纪要保持平行档案）。
- 会后洞察卡片的编辑 / 单条删除交互（v1 只增不删，清空走既有 `clearInsightMessages`）。
- 洞察消息数据库化（继续 JSON 文件事实源）。
- 会中分析节流策略调整（`maybeAutoAnalyze` 的频控/门槛不动）。

## 6. User Flow

1. 用户录完会，流水线生成纪要 → 进入纪要页 → 点「洞察」Tab → 看到会中产生的全部洞察卡片（Mermaid 图正常渲染）→ 点卡片时间戳跳回原文定位。
2. 用户觉得会中洞察太少 → 点「分析本场会议」→ 后端基于全文 + 章节补分析 → 新卡片带「会后」徽标出现 → 刷新页面仍在（后端已落盘）。
3. 用户打开 AI 面板问："洞察台提到的资源冲突，如果延期一周能解决吗？" → 后端注入块含洞察标题与摘要 → AI 引用具体洞察内容作答。
4. 用户展开某张洞察图，说"把这个图里的'测试阶段'改成'验收阶段'" → `current_diagram` 随展开态携带 → 走既有图修改链路返回新图。
5. 智能体模式（CLI 引擎）下请求"结合会中观察写一份跟进邮件" → 工作区 `context/insights.md` 可被 CLI 读取。
6. 用户删除该会议 → 任务 JSON / joblog / insights 三件套一并清理（含孤儿启动清理路径）。

**数据创建/更新**：`<task_id>.insights.json`（后端追加快照 + 前端状态覆盖保存）、`context/insights.md`（派生产物，随工作区重建）。

## 7. Acceptance Criteria（QA 可执行）

1. **回看正例**：含 3 条洞察（1 条带 diagram）的已完成会议 → 纪要页洞察 Tab 显示 3 张卡片，Mermaid 渲染成功，展开/折叠与已读状态保存后刷新不丢。
2. **回看负例**：无洞察文件的会议 → Tab 显示空态引导（不白屏、不报错），`/api/insights/messages` 返回空列表。
3. **补分析落盘**：转写 ≥ 5 句、有章节的 completed 任务调用 `POST /api/insights/analyze/task/{id}` → 有发现时消息追加落盘且带 `phase=post_meeting`，响应 messages 与磁盘文件一致；无发现时文件不变；分析进行中重复调用返回 409 不并行跑；超时返回 504 且不写盘。
4. **补分析门槛**：failed / processing 状态任务或无转写任务调用 → 400 且 detail 可读；旧版洞察文件（无 `phase` 字段）读取不报错、按 `meeting` 处理。
5. **上下文注入对等**：同一有洞察的 task，qa 路径（/api/chat）与 stream 路径（/api/chat/stream）的 DEBUG 日志均可见「会议洞察台」块，块内 ≤5 条、≤1200 字符；无洞察 task 两块均不出现。
6. **CLI 工作区导出**：agent 模式对有洞察任务发起对话 → 工作区存在 `context/insights.md` 且内容含全部有效消息；无洞察任务不生成该文件。
7. **会后图对话**：纪要页展开含图卡片后发起"修改这张图" → 请求携带 `current_diagram`，返回新 diagram 可渲染。
8. **孤儿清理**：构造无音频无对话的残留任务文件 + 伴生 `.insights.json` → 重启服务后三件套均被清理。
9. **删除级联回归**：删除带洞察的会议 → `.insights.json` 不再存在（既有逻辑不回归）。
10. **三态与 i18n**：空态/加载态/错误态齐备；中英双语文案完整；`docs/API_CONTRACTS.md`、`VUE_COMPONENT_MAP.md` 已登记。
11. **只读态控件与无障碍**：纪要页洞察面板（`mode=readonly`）不出现启用开关、自动频率、面板级 expand、实时样式；「分析本场会议」按钮在响应前保持 loading 禁用；复用后的交互元素保留既有 aria 规格（role/aria-label/aria-checked）；录音页（`mode=live` 默认）行为与改造前完全一致（回归项）。

## 8. Rollout

- 随下一常规版本发布；数据层零迁移（`phase` 为可选增量字段，旧文件天然兼容）。
- 存量会议（会中有洞察的）升级后直接可在纪要页回看，无需回填；会中未产生洞察的会议仅可用 R2 补分析。
- 回退策略：旧版前端忽略洞察 Tab 与 `phase` 字段、旧版后端忽略新端点调用，洞察文件格式跨版本一致，回退无数据损坏。
- Changelog（用户语言）：「洞察台会后可用：纪要页新增洞察 Tab 回看会中洞察，支持基于完整纪要补充分析，AI 对话现已理解洞察台的观察结论」。

## 9. Risks

| 风险 | 等级 | 缓解 |
|---|---|---|
| 后端追加快照与前端 `persistMessages` 全量覆盖写交叉竞态（会中客户端旧数据覆盖会后新洞察） | 中 | R2 写盘归属后端 + 前端重拉（§4-R2）；同一会议同一时刻仅一个写入方的实际使用形态将竞态窗口压至近似零；写盘走 `atomic_write_json` 防半截文件 |
| 全文构造 recent_lines 超小模型上下文 / 诱发幻觉 | 中 | K 句窗口上限（配置项，默认 40）+ 既有 `model_tier` 防幻觉守卫；prompt 不随本需求放宽 |
| 洞察注入块挤占既有上下文预算（纪要 2000 字 + 原文块已在） | 低 | N=5 条 / 1200 字符双限；diagram 不整段注入 |
| 「洞察是 AI 观察非事实」语义被 LLM 当事实复读，污染回答 | 中 | 注入块标题显式标注「供参考非事实源」；验收 5 覆盖块存在性、后续按 dogfooding 调整措辞 |
| 侧边指示器放宽到会后态引起误读（以为还在录音） | 低 | 会后态不显示呼吸动效与"实时"样式；仅未读计数 |
| 洞察 Tab 常驻但多数会议无洞察，形成噪音 | 低 | §11-① 已裁决常驻 + 空态引导（稳定入口承接 R2），观察后定 |
| **只读态 read/acknowledged 状态变更仍走前端 `persistMessages` 全量覆盖写**：两个会后客户端（多标签页/多设备）并存时可互相覆盖洞察与已读状态，与"同一时刻仅一个写入方"假设不符 | 低（v1 实际使用形态下窗口极小） | v1 接受为已知限制并在本文档留痕；v1.1 候选：状态变更（已读/确认）改走服务端增量端点（如 `PATCH /api/insights/messages/{task_id}` 按 id 更新），彻底消除客户端全量覆盖路径 |

## 10. 实施拆单建议（派工口径）

1. **R2 后端补分析端点**（含 `phase` 字段、追加快照写盘、单测）——后端，其余前端项依赖其契约。
2. **R3 上下文注入**（chat 两路径 + page_context + CLI 导出 + 单测/冒烟）——后端，与 1 并行。
3. **R1 纪要页洞察 Tab + `mode=readonly` 复用改造 + 指示器放宽**——前端，依赖 1、2 的契约（含 409/504 语义与空态按钮，可按本文先行并行开发）。
4. **R4 孤儿清理缺口 + 文档登记**——后端/文档，收口 PR 门禁项。

## 11. 待裁决清单

1. ~~**无洞察时 Tab 是否常驻**~~ **已裁决（项目方默认采纳产品建议，v0.2.0 落定）：Tab 常驻 + 空态引导**——常驻为 R2 补分析提供稳定入口，空态即转化位；观察噪音反馈后不再回退。
2. **R2 的 K 值（会后补分析取句数）**：已确认为**后端配置项、默认 40**（v0.2.0 随契约落定），派工后可按真实长会调参；超出部分是否按章节抽样而非时间截断，v1 不做。
3. **R3 注入上限（N=5 / 1200 字符）**：随首轮 dogfooding 的 token 消耗与回答质量复核一次。

---

**版本记录**
- 0.3.0（2026-09-25）：**全量实施**。R1：纪要页第 5 个「洞察」Tab，`RecInsightsPanel` 按契约新增 `mode: 'live' | 'readonly'`（live 默认行为不变），只读态隐藏开关/频率/面板级 expand，手动分析按钮变身「分析本场会议」（loading 禁用至响应），空态文案明示「过程观察非纪要」，指示器会后态可达且静态不脉动，进 Tab 即已读；R2：`POST /api/insights/analyze/task/{task_id}` 含幂等契约（同任务进行中 409、超时默认 60s→504 不写盘，K/超时均为环境变量可配置项），有发现时后端追加快照原子写盘（`phase=post_meeting`），前端重拉刷新；R3：chat qa/stream 两路径注入「会议洞察台」块（≤5 条/1200 字，diagram 不整段注入）+ `generating` 页面上下文 + CLI 工作区 `context/insights.md`；R4：孤儿清理补 `.insights.json`、API_CONTRACTS §14 / VUE_COMPONENT_MAP 登记。验证：后端 110 passed（含 409/504/注入块/导出用例）、ruff 门禁通过、vue-tsc + vite build + 部署、真实会议端到端补分析 11s 产出含图洞察且落盘/重载一致。待验收项：含图卡片窄容器 UI 示意（R1 遗留）、dogfooding 后复核注入上限。
- 0.2.0（2026-09-25）：产品评审收口版。四处批注落稿：① R2 新增时长与幂等契约（超时 60s→504 不写盘、同任务并发 409、追加语义明示）；② R1 复用口径修正为 `RecInsightsPanel` 增 `mode: 'live' | 'readonly'`（组件本已独立，不做拆分重构）；③ 只读态控件清单补全（隐藏启用开关/面板级 expand、手动分析按钮变身接 R2、含图窄容器待 UI 示意）；④ §9 风险表补录"只读态 read/acknowledged 走 persistMessages 全量覆盖写"竞态及 v1.1 增量端点候选。§11-① 裁决 Tab 常驻、② 确认 K 为配置项默认 40；AC 3/10/11 相应扩充。
- 0.1.0（2026-09-25）：首稿。范围依据：项目方当日两项裁决（支持会后补分析；纪要页采用第 5 个 Tab 形态）；数据/链路行号来自同日代码调研（`app/routers/insights.py`、`useAiInsights.ts`、`chat.py`、`context_export.py`、`tasks.py`、`task_store.py` 均已核实）。
