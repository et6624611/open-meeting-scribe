---
title: 需求记录 — 跨会议决策中心（Decision 结构化与全量查看）
id: REQ-DECISION-CENTER
version: 0.2.0
status: approved（全部裁决完成，作为派工依据）
date: 2026-09-24
decided_by: 项目方（2026-09-24 裁决：① 跳过 P0 直接做 P1；② `[待确认]` 决策在决策中心默认可见（带徽标）；③ 纪要编辑后不做决策重同步交互，漂移由手动修正；④ 议题维度 v1 不做，v1.1 视使用反馈以可选增量字段补充。见 §11）
category: 功能补全 / 纪要结构化输出
related:
  - docs/REQUIREMENT-AI-NATIVE-OUTPUT-STRUCTURE.md（§Q1「决策项无结构化源」痛点即本需求要裁决的问题）
  - docs/GLOSSARY.md:24-26（现定义「决策 = 行动项」，需随本需求消歧）
  - docs/PRD.md:31-32
  - docs/VUE_COMPONENT_MAP.md
owner: 产品经理（定义）/ 待指派（工程实施）
---

# 需求记录：跨会议决策中心（REQ-DECISION-CENTER）

## 1. Problem（要解决什么）

会议最终形成的"决策/主要结论"目前**不是数据对象，只是纪要 markdown 里的一段文字**，导致：

1. **没有全量视角**：用户无法跨会议查看"到底定下来了哪些事"。所有 API、存储、UI 均为单会议作用域（`app/routers/notes.py:168/225/251`、`data/tasks/<task_id>.json` 平铺）。
2. **决策没有结构化源**：`core/summarize.py` 的「二、主要结论」章节（prompt 第 121-126 行）产出的决策条目只存在于 markdown；`parse_todos_from_summary()`（`core/summarize.py:329-400`）只解析 `- [ ]` 待办。产出结构工程化方案 §8-Q1 已确认该缺口。
3. **决策状态无法管理**：决策被后续会议推翻/调整后，历史记录无从标注，全量视图失去意义的前提就是每条决策可信、可追踪生效状态。
4. **术语错位**：`docs/GLOSSARY.md:24` 把「决策」定义为行动项（todos），与用户心智中"决策 = 已定结论"不一致；现有「决策」Tab（`DecisionFlowPanel.vue`）实际展示的是行动项。

**期望结果**：决策成为一等数据对象，自动从纪要抽取、可跨会议检索查看、带生效状态；本需求同时裁决并落定 OUTPUT-STRUCT 计划 §Q1。

**证据来源**：代码调研（2026-09-24，行号均已核实）+ 项目方直接反馈（本需求由用户提出）。

## 2. Target Users and Scenarios

| 用户 | 场景 | 现在 | 交付后 |
|---|---|---|---|
| 会议主持人/负责人 | 阶段复盘："这个项目到现在定了哪些事？" | 逐个打开会议翻纪要 | 决策中心一页看完，可按时间/知识库筛选 |
| 项目参与者 | 新决策与旧决策冲突："上次说的方案被改了吗？" | 无从知晓 | 被推翻的决策可标记并关联取代它的新决策 |
| 任意用户 | 会后发现纪要中决策漏抽/误抽 | 只能改 markdown 原文 | 在会议内或决策中心手动补录/修正 |
| AI Agent（洞察台） | 「某知识库近 7 天会议的决策汇总」 | 无结构化数据，只能读全文 | 读 `task["decisions"]` / index 即可（对齐 OUTPUT-STRUCT 验收场景） |

## 3. 产品目标与成功标准

**目标**：用户在一个独立页面即可回答——「定了哪些事、在哪个会议定的、现在还作不作数」。

**成功标准（无 analytics 体系，采用可测代理指标）**：

- 新生成的会议纪要有明确结论条目时，决策抽取召回率：dogfooding 5 场真实会议中，「主要结论」编号条目 → 结构化决策的转换准确数 ≥ 95%（无漏条、无编造条）。
- 存量会议（≥ 10 场）经回填后，决策中心首屏可见全部历史决策，未解析成功的会议有明确标记而非静默丢失。
- 对任一决策，用户可在 2 次点击内跳转到来源会议的纪要上下文。

## 4. Scope

本需求为整体 P1 交付（项目方裁决跳过 P0）。包含四部分：

### R1 — 决策数据模型与抽取（模型层，核心）

- `data/tasks/<task_id>.json` 新增 `decisions` 数组（与 `todos` 平级），字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | uuid str | 主键 |
| `text` | str | 决策内容（转述文本） |
| `status` | `active` \| `superseded` \| `revoked` | 生效状态；默认 `active` |
| `pending_confirmation` | bool | 对应 prompt 规则 4 的 `[待确认]` 前缀 |
| `source` | `auto` \| `backfill` \| `manual` \| `injection` | 来源标记；重新生成纪要只覆盖 `auto`，其余保留 |
| `created_at` / `updated_at` | ISO 8601 | — |
| `superseded_by` | `{task_id, decision_id}` \| null | 跨会议取代关系，来源会议删除时降级显示 |
| `related_todo_ids` | str[] | 同会议行动项软链接 |

- **抽取方式（扩展纪要 prompt 输出契约 + 确定性解析，不引入第二次 LLM 调用）**：
  - `core/summarize.py` prompt「输出结构」对「二、主要结论」增加硬约束：每条决策必须为有序列表项（`1. ` 起），未敲定条目以 `[待确认]` 前缀开头，禁止该章节出现非决策文本。
  - 新增 `parse_decisions_from_summary()`（与 `parse_todos_from_summary()` 并列，`core/summarize.py`），解析上述章节写入 `task["decisions"]`；写回时机与 todos 相同（`core/pipeline_runner.py:595-597` 及 `app/routers/import_tasks.py` 导入路径）。
  - 解析失败（章节缺失/格式异常）时决策置空并写 `.joblog.jsonl` 一条 warning，不阻断流水线。
- **聊天注入**：`app/routers/notes.py:111-127` 现只对 `todo` 类型生成结构化节点；扩展 `decision` 类型注入 → 同步生成 `source=injection` 的决策项。

### R2 — 决策 CRUD 与跨会议聚合 API（服务层）

- 任务级：`GET/POST/PUT/DELETE /api/tasks/{task_id}/decisions[/{id}]`（pydantic 校验，复用 `_mark_modified` + `save_task_to_disk` 脏检测链路，`app/routers/notes.py:19-21`）。
- 标记取代：`PATCH .../decisions/{id}/supersede`，body 携带取代方 `{task_id, decision_id}`；被取代项 `status=superseded`。
- 跨任务聚合（新）：`GET /api/decisions?since=&until=&kb_id=&status=&q=&group_by=meeting|date`。遍历 task_store 内存态聚合（桌面单机数据量可承受，不引入数据库）；返回项附带 `task_id`、会议标题、`meeting_date`、所属知识库。`q` 为 text 子串匹配。
- 契约文档同步：`docs/API_CONTRACTS.md`。

### R3 — 决策中心页面（表现层）

- 新路由 `/decisions`（`frontend/src/router/index.ts` 现 9 条路由后追加）+ 主导航入口「决策中心」，与会议列表平级。
- 视图 `frontend/src/views/DecisionCenterView.vue`：
  - 列表按会议日期倒序，可切换「按会议分组折叠 / 平铺」；筛选器：时间范围（近 7 天/30 天/全部）、知识库、状态（含"仅看生效中"默认勾选）、关键词。
  - 决策卡片：文本 + 来源会议（点击跳转 `GeneratingView` 纪要页并锚点定位）+ 日期 + 状态徽标；`pending_confirmation` 显示「待确认」徽标；`superseded` 沉底折叠并显示"已被〈新决策〉取代"链接。
  - 卡片支持行内标记"已被取代/已撤销"（选择取代方需弹层内检索其他决策）。
  - 空态（无决策/筛选无结果）、加载态、错误态按项目既有视图惯例。
- 组件复用：卡片视觉复用 `DecisionNode.vue` 的样式基元（不复用其决策流状态机逻辑——那是行动项语义）。
- 单会议内：「决策」Tab 更名为「行动项」（见 R5 术语消歧；**2026-09-27 项目方裁决改回「决策」**，见版本记录 0.2.1），并在面板顶部只读展示本会议决策条目 + "去决策中心"链接。
- i18n：全部文案走 `vue-i18n` 双语键。

### R4 — 存量回填

- `scripts/backfill_decisions.py`：解析存量任务 `user_summary`（优先）或 `summary` 的「主要结论」章节 → 写入 `decisions`（`source=backfill`，按当前 markdown 结构宽容解析：支持有序列表与裸行条目）。
- 幂等：任务 JSON 已有 `decisions` 或存在 `decisions_backfilled_at` 标记则跳过；输出 `_backfill_report.json`（成功/跳过/失败计数与原因）。
- 触发方式：随包提供，由用户/派工在升级后手动执行一次（不做启动时静默执行，风险见 §11）。

### R5 — 文档与术语（必须随本需求变更，防止语义漂移）

- `docs/GLOSSARY.md`：「决策」重定义为"会议形成的已定结论/决议"（decision 对象）；原「决策 = 行动项」条目改为「行动项 = todos，由决策流面板展示」并更名面板标题。
- 产出结构工程化方案 §8-Q1：渲染源由"倾向方案 A（用 todos 渲染）"改判为 **方案 C：用 `task["decisions"]`（本需求产物）+ todos 共同渲染 `decisions.md`**；`core/output_repository.py` 落地时遵循。
- `docs/PRD.md`、`docs/VUE_COMPONENT_MAP.md`、`docs/BACKLOG.md` 同步登记。

**依赖**：R5 的 OUTPUT-STRUCT 联动仅约定渲染源，不依赖 `output_repository.py` 存在；R1–R4 无外部依赖。

## 5. Non-Goals（v1 明确不做）

- 决策审批流 / 权限分级。
- 跨设备同步、多人协作冲突合并。
- LLM 自动检测"新决策推翻旧决策"（v1 仅手动标记；待积累真实数据后再评估）。
- 决策与 OKR/项目目标关联、决策提醒推送。
- 引入数据库（继续 JSON 文件事实源）。
- P0 式"纯 markdown 解析的只读聚合视图"（已被项目方裁决跳过；R4 回填即其替代）。

## 6. User Flow

1. 用户录完会/导入音频 → 流水线生成纪要 → 「主要结论」条目同步落入 `task["decisions"]`（`source=auto`）→ 无感知。
2. 用户点击侧边导航「决策中心」→ 默认视图：全部生效中决策，按会议分组倒序。
3. 用户筛选"近 7 天 + 知识库 A" → 列表刷新 → 点击某条决策的来源会议 → 跳转该会议纪要页并高亮对应条目。
4. 用户发现某决策已被上次会议方案取代 → 卡片上点「已被取代」→ 弹层搜索并选中取代方决策 → 该卡片沉底折叠。
5. 升级安装后首次进入决策中心，若历史会议无决策数据 → 空态引导文案 + 一键"回填历史决策"入口（触发 R4，完成后刷新）。

**数据创建/更新**：`task["decisions"]` 数组、`_backfill_report.json`、task `last_modified_at`（触发既有知识库脏检测）。

## 7. Acceptance Criteria（QA 可执行）

1. **抽取正例**：构造含 3 条编号结论（1 条带 `[待确认]`）的对话跑完整流水线 → `task["decisions"]` 恰有 3 条，`pending_confirmation` 正确标记，无编造条目。
2. **抽取负例**：纪要为"本次会议未形成明确结论" → `decisions` 为空数组，不产生占位决策。
3. **解析失败降级**：注入格式破坏的 summary → 流水线任务状态不失败，`.joblog.jsonl` 有 warning，`decisions` 为空。
4. **重新生成保护**：对已有 `manual`/`injection` 决策的任务重新生成纪要 → `auto` 条目被替换，其余保留。
5. **跨会议 API**：`GET /api/decisions?since=<T-7d>` 返回且仅返回 7 天内会议的决策，含 `task_id`/标题/日期；对不存在 task 的 update/supersede 请求返回 404。
6. **取代链路**：标记 supersede 后，决策中心该条沉底且可跳转取代方；来源会议删除后卡片降级显示（不白屏、不报错）。
7. **回填幂等**：连续执行 `backfill_decisions.py` 两次，第二次全部 skip，report 计数一致。
8. **UI 路径**：筛选组合（时间×库×状态×关键词）任取两项叠加结果正确；空态/加载态/错误态三态可见；跳转锚点定位准确；中英文案完整。
9. **术语一致性**：`docs/GLOSSARY.md` 更新后，全局搜索无"决策=待办"残留语义；「行动项」Tab 更名不破坏 `VUE_COMPONENT_MAP.md` 对应关系。
10. **知识库脏检测兼容**：决策 CRUD 后 task `last_modified_at` 更新，KB 同步按既有链路感知变更。

## 8. Rollout

- 随下一常规版本发布（非独立发版；数据模型为增量字段，旧 task JSON 缺 `decisions` 字段一律按空数组读取，天然向后兼容）。
- 升级说明告知用户可执行回填；读路径对未回填存量任务正常降级（决策中心显示"该会议决策未回填"提示行）。
- 回退策略：新版后端不依赖旧版未有的存储结构，回退仅导致 `decisions` 字段被旧版忽略，无数据损坏。
- Changelog（用户语言）：「新增决策中心：跨会议查看、筛选和管理所有已定结论；历史会议支持一键回填」。

## 9. Risks

| 风险 | 等级 | 缓解 |
|---|---|---|
| LLM 不遵守「主要结论」编号格式硬约束 → 抽取漏条 | 中 | 确定性解析 + 宽容降级（裸行也收）；joblog 可观测；验收标准 1/3 强制覆盖 |
| 用户在纪要页编辑 markdown 后，`decisions` 与正文漂移 | 中 | 已裁决不做自动/引导重同步（项目方 2026-09-24）；漂移由用户在决策条目上手动增删改修正。`source` + `updated_at` 字段保证可辨识与可追责；纪要编辑页仅展示静态提示「决策条目需单独维护」 |
| 存量纪要「主要结论」写法多样，回填质量参差 | 中 | 回填标记 `source=backfill` 可辨识；report 暴露失败清单；决策中心支持删改 |
| 跨会议 `superseded_by` 引用悬空（task 删除） | 低 | 降级显示已失效引用（验收 6） |
| 「决策」Tab 更名「行动项」造成老用户困惑 | 低 | 变更随版本一次性发生 + changelog 说明；术语本就有纠错必要性 |
| 启动时自动回填造成首启卡顿/写盘意外 | — | 已裁决为手动/引导式触发（R4、用户故事 5） |

## 10. 实施拆单建议（派工口径）

1. R1 模型+抽取+解析（含 prompt 契约、单测）——后端，P0 优先级，其余全部依赖它。
2. R2 API（任务级 + 聚合 + supersede）——后端，依赖 1。
3. R3 决策中心前端 + Tab 更名——前端，依赖 2 的接口契约（可按 API_CONTRACTS 先行并行）。
4. R4 回填脚本——后端/工具，依赖 1。
5. R5 文档修订——随 1–4 收口，PR 门禁项。

## 11. 裁决记录（项目方，2026-09-24，全部完成）

1. 范围：跳过 P0，直接做 P1 根治方案。
2. `[待确认]` 决策在决策中心**默认可见**（带徽标），维持本稿设计。
3. 纪要编辑后**不做**决策重同步交互（无自动重解析、无引导弹窗），漂移由用户手动修正决策条目。
4. **议题维度 v1 不做**：不为 decision 增加 `chapter_id` 软链接。理由：价值仅在长会多议题场景显现（现有"跳转来源会议"兜底），决策→议题自动归属是新失败模式。`chapter_id` 预留为 v1.1 可选增量字段（向后兼容，无迁移成本），待决策中心真实使用反馈后再裁决。

---

**版本记录**
- 0.3.0（2026-09-27）：**DC-UNIFY-01 收敛为单一决策流**——项目方裁决「决策只有一个对象」（决策流 `todos`），
  原 R1 的 `task["decisions"]` 数据对象、R2 的任务级 decision CRUD、R3 的纪要页「本会议决策」只读区全部下线；
  存量 decision 数据不迁移（磁盘保留、无读路径）。决策中心改为决策流的跨会议聚合视图 + 就地可交互卡片，
  写入统一走 `/api/tasks/{id}/todos*`；状态字典默认集换为决策流五（锚点仅 `done`）；
  AI 自动解析的「主要结论」以「待确认」态自动入流。契约同步 API_CONTRACTS §12，术语同步 GLOSSARY。
- 0.2.1（2026-09-27）：R5 部分回退——项目方裁决纪要页 Tab 名由「行动项」改回「决策」（决策中心作为「决策」对象的专属管理页不受影响）；同步更新 GLOSSARY 两条目及前端 i18n/注释，「行动项」降级为仅描述 todos 数据语义的术语。
- 0.2.0（2026-09-24）：议题维度裁决完成（v1 不做），全量裁决放行，**approved，作为派工依据**。
- 0.1.1（2026-09-24）：记录项目方裁决（范围 P1、待确认默认可见、不做重同步）；§11 改为裁决记录 + 待裁决清单；风险表同步更新。
- 0.1.0（2026-09-24）：首稿。范围依据：项目方裁决跳过 P0、直接 P1（本对话）；数据/链路行号来自同日代码调研。
