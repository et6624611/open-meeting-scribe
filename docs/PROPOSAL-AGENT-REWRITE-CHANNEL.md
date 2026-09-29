---
title: "方案：AI 会话改写通道统一 —— 模式即权限"
description: "把随记/纪要/决策/洞察板的会话面板改写收敛为一条声明式统一通道，以'会话模式'作为写权单一真相源，并补齐完成护栏与缺失工具。"
tags: ["architecture", "ai-chat", "agent", "rewrite", "permissions"]
created_at: "2026-09-29"
updated_at: "2026-09-30"
version: "0.4.0"
author: "wangyongliang"
status: "draft"
category: "technical"
related_docs: ["PROPOSAL-QODER-CLI-ENGINE.md", "INSIGHT_BOARD_SPEC_v0.md"]
---

# 方案：AI 会话改写通道统一 —— 模式即权限

## 1. 背景与触发

一次「重新生成洞察板」失败暴露了系统性问题：用户在智能体模式点共创、明确说"重新生成"，AI 只读了基线就停在"我先读转写与纪要"，`board.html` 停留在 rev 1 从未被重写。排查（`logs/audit.log`、`agent-workspace/…/AGENTS.md`、`context/history.md`）确认这不是洞察板独有 bug，而是**四域共用的一套碎化改写机制**在三层断点上叠加的必然结果。

随记、纪要、决策、洞察板都面临"通过 AI 会话面板改写"的诉求，当前各写各的，缺一个统一的权限与执行模型。

## 2. 核心主张：写是智能体模式的一种权利

系统已经区分了**会话模式**（问答 / 智能体）。据此确立单一真相源：

> **写回能力是"智能体模式"固有的权利，不是"按某个按钮临时借来的特权"。**

- **问答模式 = 只读**：读上下文 + 回答，天然不该偷偷改数据。
- **智能体模式 = 有协助写回权**：用户选「智能体」即选"帮我动手"，符合既有裁决"用户选择即意图"（`chat.py`）。

这与现状记忆一致：写工具（`update_summary`/`inject_items`/`revise_insight_board`）本就只在智能体模式具备，问答模式共创起跳只 toast 提示切换。本方案是把这一**事实显式化为权限模型**，删掉"仅 boardCoCreate 才升档"的特例，让四域一视同仁。

## 3. 范围边界（明确不做什么）

只治理**对话类改写**——在会话面板里让 AI 读基线、多轮规划、改随记/纪要/决策/洞察板。

**不纳入**函数类操作（划词改写、一键洞察分析、一键总结）：它们输入已知、单轮变换、亚秒级、结果即 Diff，**恒走内置 LLM 通道**，与模式无关。不得把函数类操作升级成智能体（CLI 固定开销会摧毁其可用性）。若智能体想用这些能力，应由 CLI 经 MCP 反向调用内置原语，而非改道。

## 4. 现状盘点

### 4.1 四域四机制

| 域 | 数据字段 | 现状写回工具 | 语义 | 缺口 |
|---|---|---|---|---|
| 随记 | `user_notes` | **无** | —— | 会话面板完全无法写回 |
| 纪要 | `user_summary` | `update_summary` | 整篇 Markdown 覆盖 | 无读基线、无增量，改一句也要重写全文 |
| 决策 | 决策节点 | `inject_items` | 仅追加注入 todo/conclusion/decision | 不能改写/删除已有节点 |
| 洞察板 | `.board.html` | `revise_insight_board(_section)` | 读+写双语义 + 单节 | 已是目标形状（本方案参照物） |

洞察板已验证了"正确改写通道"的形状：读基线 → 整份/单节写回 → revision 递增 → audit → CSS/HTML 契约。其余三域未收敛到此形状。

### 4.2 三层断点（叠加导致"只说不做"）

1. **授权层**：写工具全标 `kind=write`，默认档 `readonly`（`settings_store`），CLI harness 在 `dont_ask` 下直接拒未预授权工具。目前**只有洞察板共创**在前端把本轮升 `workspace_write`（`useAiChat.ts` L308 `boardCoCreate`）。纪要/决策/随记走 AI 改写无任何升档 → 模型物理上写不了。
2. **提示词层**：当前角色 `learning-tutor` 的 `AGENT.md` 写死"你没有执行权：不能修改、删除、写入任何数据"（绝对禁令），且 brief（`context_export.py` L264-281）只透传问题、无"必须落盘"约束。模型读完基线即收尾。
3. **完成护栏层**：无机制检测"用户明确要求改写、但本轮零写回"。前端照常显示旧版本，用户只能对着 rev 1 干猜。

## 5. 目标架构

### 5.1 模式即权限（收敛断点 1）

- **落点**：`app/routers/chat.py::_agent_engine_events`（L992）`auth_tier = data.auth_tier or cfg["auth_tier"]` 改为：**engine=agent 且未被显式降级时，默认抬到 `workspace_write`**（禁 Bash/WebFetch/WebSearch，放开工作区编辑 + 板/纪要/决策/随记写）。
- **优先级链（v0.2.0 补，必须定义清楚）**：`请求级显式 auth_tier > 用户在设置页显式降级 > 模式派生默认（agent→workspace_write）`。⚠️ `settings_store` 现行默认 `readonly`（L249/L257）：若仍让 `cfg["auth_tier"]` 直接生效，抬档永不落地；若模式派生无条件压过配置，设置页「授权档」字段语义就从"选择"变成"降级/覆盖"。落档时必须同步修订设置页该字段的文案与交互（REQ-SETTINGS-IA 刚收敛的信息架构不得被本需求打散）。
- **退役特例**：`frontend/src/composables/useAiChat.ts` 的 `boardCoCreate` 升档逻辑（L308）删除——不再按按钮才给权，进入智能体模式即天然可写。⚠️ `boardCoCreate` 现同时承担「升档」与「共创意图打标」双职责（L91-96），退役时**意图 flag 必须独立保留**并作为 §5.4 护栏的输入（同属 P1，需一并设计）。
- **直写边界（v0.3.0 重写，审查采纳项 1）**：事实修正——任务数据在 `data/`，与 `agent-workspace/` 无父子关系（`context_export.py` L28-30），且 CLI 进程 `-w` 锁定工作区，**直写任务文件今天就已物理不可达**，无需新机制；真正的未治理面是 `--add-dir` 挂载的项目知识库目录（`context_export.py` L283-287）——若 accept_edits 作用域含 add_dirs，AI 可直写用户项目文件夹。**拆为两个子项**：(a) 提示词约束已随 §5.2 权限段落地（"文件编辑工具只允许写 output/，任务数据必须经集成工具"）；(b) **SPIKE 核实项（P1 验收前）**：实测各 CLI `accept_edits` 是否放开 add_dirs 写入；若放开，智能体轮的 add_dirs 改为只读挂载或仅产物输出时临时挂载。`RewriteTarget` 适配器仍是任务数据唯一落盘通道（`save_task_to_disk` 单点）。
- **意图 flag 轮级语义（v0.3.0 新增，审查采纳项 3）**：现 `boardCoCreate` 是会话级常驻 flag（置真后持续到任务切换），直接推广会让点过一次共创后的后续闲聊轮全被误标"改写意图"、横幅大量误报，与 §9 "宁可漏报不可误报"相悖。新 flag 定义为**轮级**：入口按钮点击→标记下一轮→发出即清除。入口清单：P1 仅洞察板共创入口（既有）；纪要/决策/随记的共创入口本身是 P3 新工作，届时逐个接入同一 flag。
- **可选降级**：智能体档下保留一个默认关闭的「仅深度问答·本轮不落盘」开关，供谨慎用户；它是例外不是默认。实现口径：前端显式传请求级 `auth_tier=readonly`（走请求级优先链）。

### 5.2 提示词按落档分段（收敛断点 2，v0.3.0 重写，审查采纳项 2）

- **事实勘误："问答段"是死代码**——`context_export.py` 只在智能体模式（CLI 路径）执行，问答模式是内置单流（`core/agent_loop.py` 已按 ADR-0020 物理删除），根本不会读 AGENTS.md。因此本方案的权限段只有两个落档：**可写档（workspace_write/full_task）与降级只读档（显式传 readonly 的智能体轮）**；问答模式的只读由内置 prompt（`chat.py` L261-266，**保持原样不动**，它就是问答模式的只读保障）与无工具通道天然保障，不在本方案改动范围。
- **落点**：`core/cli_engine/context_export.py::_build_permission_section(auth_tier)` 按本轮实际落档生成"本轮权限段"，置于角色段之后并声明"以本段为准"（后声明者胜）：
  - 可写档：你拥有协助写回权；用户要求改写某域时必须调用对应 `revise_*`/写工具完成落盘，仅在对话里描述计划不算完成；附直写边界约束（只写 output/，任务数据走 MCP）。
  - 降级只读档：无执行权，禁止"已修正/已更新"表述，提示用户切换。
- **角色档案解耦**：`data/agent/_roles/_builtin/*/AGENT.md`（learning-tutor、meeting-minutes）的"没有执行权"从**绝对禁令**改为**按档位声明**（"默认档位下没有执行权；写回权是智能体可写模式固有的权利，以运行时权限段为准"）。注意：角色 `agent_md` 同时被内置非 QA 路径当 system_prompt 使用（`chat.py` L614/L761/L1066），而内置路径无工具通道——故禁令措辞保留"默认档位下无执行权"安全底线，不引入"你可以写"的误导。
- **用户资产不侵权**：`data/agent/_roles/my/AGENT.md`（用户自建/自定义角色目录）**不改其资产文件**——存量禁令由 `_build_permission_section` 运行时注入段覆写（注入段置于角色段之后，声明"以本轮模式权限段为准"，builtin 与 my 两区同一机制）。

### 5.3 统一改写通道 RewriteTarget（结构性收敛）

- 在 `core/agent_tools/catalog.py` 引入 `RewriteTarget` 注册表，每域声明：
  ```
  { target_id, read_baseline(task_id), write_back(task_id, payload), validate(payload), version_field }
  ```
- 四域适配器（读基线 + 写回 + 校验 + 版本），全部复用 `save_task_to_disk` + 脏标记 + `audit_logger`：
  - **随记**：新增 `revise_notes`（读/写 `user_notes`，整篇或按选区）。
  - **纪要**：v0.4.0 改为**提案式 diff**（Copilot-in-Word 式）：新增 `propose_summary` 信号工具（kind=write 但后端不落盘），AI 产出建议→前端行级 diff 预览→用户接受才经 `PUT /summary` 落盘。原 `update_summary` 保留但标为已弃用。此举同时解决"改完不即时刷新"（接受时前端 saveSummary+patchTaskLocal，summaryMd 由 task watcher 派生自动刷新）与"不是 diff 模式"两条实测反馈。
  - **决策**：`inject_items` 扩出"改写/删除指定节点 id"，不再只能追加。
  - **洞察板**：已是目标形状，纳入统一注册表。
- **收益**：新增任何可改写域只需注册一个适配器，授权/护栏/审计/脏标记全部白拿。
- **快照强制契约（v0.2.0 新增，依据 §7 事实修正）**：`write_back` 内部**强制先做字段级快照再落盘**（适配器作者无法跳过）——写回前把被写字段旧值 append 到 per-task sidecar（JSONL：task_id / target / 旧值 / turn_id / revision / ts），每字段保留上限 N 版（建议 N=20）并入现有 `retention_days` 清理。**只快照 AI 写回，用户手改不快照**（否则快照点要铺到全部 task 写入路径，成本失控）。
- **决策域口径（v0.2.0 补）**：决策改写/删除必须挂在 DC-UNIFY-01 收口后的 `core/decision_flow.py` 共享读写口径上（决策=唯一对象「决策流节点」`task[todos]`），按**节点 id** 寻址、按节点粒度快照/撤销；不得在 `inject_items` 旁另开第二套写路径，防止刚收口的"唯一对象"再分裂。前置核实项：决策流节点稳定 id 是否已暴露给工具面（P2 开工前确认）。
- **随记特殊口径（v0.2.0 补，市场模式 D）**：`user_notes` 是**用户原创区**，与纪要（AI 产物）性质不同。`revise_notes` 不做与其他域同构的直接写回，而做成**建议模式**：工具产出 Diff/预览，用户确认后才落盘（市面纪要类产品均不让 AI 直写用户原创区）。§5.3 的"四域同一 write_back 语义"因此在随记域有一处有意的例外。

### 5.4 完成护栏（收敛断点 3，正交不可省）

有权力 ≠ 会行使：轻量模型（Qwen3.8-Flash）即便被授权、被放行，仍可能只报计划不落盘。

- **后端**：`done` 事件回 `rewritten: {target, revision}`（本轮若发生写回）。写回审计 `[agent-engine] revise_* task=… rev=…` 已有，统一即可。**v0.2.0 补**：`rewritten` 同时携带 **diff 摘要**（改了哪几节/哪几个节点/字段变更规模），呈现与恢复共用一份数据——不把"看见改了什么"和"回退"割裂成两套机制。
- **前端**：识别"改写意图（来自共创/重新生成入口）但 `done.rewritten` 为空" → 显式横幅「本轮 AI 未落盘」，给「切可写档重试 / 换强模型」入口，而不是让用户对着旧版本猜。意图标记来源为 §5.1 独立保留的意图 flag（非 boardCoCreate 本体）。
- **恢复入口（v0.2.0 新增）**：改写成功轮的会话气泡挂「撤销本轮改写」（借 Cursor/Claude Code 的"按轮恢复"交互语义；实现用 §5.3 字段级快照，不引入影子 git）；数据展示区给旧/新预览或行级 diff（纪要/随记字段级、决策节点卡片级、板旧新切换）。

## 6. 分阶段落地

| 阶段 | 内容 | 效果 | 影响文件 |
|---|---|---|---|
| **P1 止血** | 5.1 模式即权限 + 5.2 提示词分段 + 5.4 完成护栏 | 纪要/洞察板在智能体模式下正常落盘；未落盘可感知 | `chat.py`、`context_export.py`、`useAiChat.ts`、`AIPanel.vue`/`GeneratingView.vue`、角色 `AGENT.md` |
| **P2 收敛** | 5.3 `RewriteTarget` 注册表，四域适配器化；**含 §5.3 快照强制契约（字段级写前快照 + 保留上限）与 §5.4 恢复入口/按轮撤销 UI**（v0.2.0 调整） | 单一改写抽象，消除四套机制；AI 误写可回退 | `catalog.py`、`app/routers/agent_tools.py`、`core/insight_board.py`、`core/rewrite_snapshots.py`（新增）、`notes.py`、前端恢复/diff 呈现 |
| **P3 补齐** | 随记 `revise_notes`（**建议模式**，见 §5.3）、决策改写/删除节点（**按节点 id、走 `core/decision_flow.py` 口径**，见 §5.3） | 四域全部可对话改写 | `catalog.py`、`agent_tools.py`、`notes.py`、决策落库路径、前端四 Tab 共创入口 |

先做 P1 即可解决"重新生成不生效"的直接问题并验证方向；P2/P3 是结构性收敛与能力补齐。

**P1 实施状态（v0.3.0，2026-09-29）**：已落地——后端 `chat.py` 授权档优先级链（请求级 > 显式降级 > 模式派生默认 workspace_write，显式降级由 `chat_engine._auth_tier_explicit` 标记承接）、`context_export._build_permission_section` 按档注入权限段、`runner.on_write_success` → `done.metadata.rewritten`；前端 `useAiChat` 轮级意图 flag（rewriteIntentPending）+ 未落盘横幅（AiChatPanel `.guard-notice`）+ 重新执行入口；设置页授权档文案改为覆盖/降级语义。P1 待办：§5.1(b) add_dirs 可写性 SPIKE。

**成本结论（2026-09-29 产品评审估算）**：快照+恢复整体 ≈ 6–8.5 人日，绝大部分可并入 P2/P3 既有派工单，**净增约 2–3 人日**；存储增量几十 MB 级（每字段 N=20 版封顶 + retention 清理，板 HTML 建议 gzip）；安装包增量≈0（后端纯 stdlib，前端 diff 库约 30–50KB gzip）。若项目方要求 P1 即具备回退，则单拆 P1.5（前后端各一张快单）。

## 7. 安全与兼容

- **绝不静默上云（PRD R7）** 不受影响：改写走本地任务数据写盘，与引擎无关。
- **写回可回退（v0.2.0 事实勘误）**：⚠️ **现状四域均不可回退**。洞察板的 `revision` 只是单调计数器（`core/insight_board.py` L664-668：读旧版本号+1、整份 HTML 直接覆盖，无任何历史正文留存），其用途是前端轮询比对"变没变"，**不是版本库**；纪要/决策/随记同样整篇覆盖。因此"误写可回到上一版"不是既有能力，而是 **P2 交付项**（§5.3 快照强制契约 + §5.4 恢复入口）；P2 前各域仅有 audit 追溯、无内容恢复。
- **向后兼容**：`auth_tier` 显式传入优先于模式派生默认，旧客户端不传时按模式安全回退；`AiSession.role` 等遗留字段不动。
- **单轮上限/防穿越**：写工具沿用现有 `items[:50]` 上限、`agent-tools` 短时令牌与路径 resolve 校验，不放宽。

## 8. 验收标准

1. 智能体模式（默认只读角色 learning-tutor 亦可）下，对随记/纪要/决策/洞察板说"重新生成/改写 X"，对应数据文件 revision/内容确实落盘。
2. 问答模式下同样的改写请求，被明确拒绝或提示切换，不产生任何写盘。
3. 构造"AI 只报计划未落盘"场景（弱模型），前端出现"本轮未落盘"横幅而非静默显示旧版本。
4. 划词改写/一键洞察分析等函数类操作行为不变（仍恒走内置、亚秒级、不升智能体档）。
5. 四域写回均产生 `[agent-engine]` 审计条目，前端脏标记与只读重拉正常。
6. **（P2 后生效，v0.2.0 新增）**对任一域 AI 写回后执行"撤销本轮改写"，被写字段回到本轮之前内容，且 audit 产生恢复条目；快照不越过保留上限（每字段 N 版 / retention_days）。
7. **（v0.2.0 新增）**随记改写仅产生"建议/Diff 预览"，未经用户确认不写盘。
8. **（v0.3.0 拆分原 AC8，拆为两条可测断言）**a) 智能体轮内用文件编辑工具写 `output/` 产物成功；b) 任务数据四域（task JSON/板文件）的任何变更在后端审计中必对应一次 `kind=write` 工具调用（无工具回执的内容变更即视为异常）。注：任务数据物理上在工作区外、直写本已不可达（§5.1 v0.3.0 事实修正），本条验收的是"变更必经工具通道"的审计可追溯性，而非新增拦截机制；add_dirs 项目目录可写性另由 §5.1(b) SPIKE 核实。
9. **（v0.3.0 新增）**轮级意图 flag：点共创后的下一轮未落盘→横幅；后续无意图的闲聊轮→不亮横幅。

## 9. 待决问题（2026-09-29 产品评审已给裁决建议，待方案作者/项目方确认）

- 决策域"改写/删除已有节点"的目标寻址方式：按节点 id 还是按文本匹配？——**评审建议：id**。且快照/撤销粒度必须与寻址单元一致（节点级），实现收口到 `core/decision_flow.py`（DC-UNIFY-01 唯一对象口径），见 §5.3。**v0.3.0 核实结果（已坐实为缺口）**：节点稳定 id 存在于 `make_todo_node`（uuid4），但工具面未暴露——`core/agent_tools/impl.py::_tool_get_meeting_todos`（L186-200）只回 `text/done/assignee` 不含 `id`。P3 开工前必须先扩该读工具输出（含对应契约测试同步）。
- 完成护栏的"改写意图"如何可靠识别：靠共创按钮入口显式打标（推荐），还是靠 NLU 检测用户消息？——**评审建议：显式打标**。NLU 误报与横幅"宁可漏报不可误报"的体验相悖；注意 §5.1 退役 boardCoCreate 时意图 flag 需独立承接。

## 10. 产品评审与修订记录（v0.1.0 → v0.2.0，2026-09-29，评审人：产品经理）

**锚点核验**：v0.1.0 全部代码断言逐条核对通过（`chat.py` L992 / `useAiChat.ts` L91-96、L308 / `context_export.py` L251-281 / `settings_store.py` L249、L257 / `catalog.py` 四写工具 `kind=write` / 随记域确无写工具 / 角色禁令原文），无虚构锚点。

**本次修订项**：
1. §7「写回可回退」事实勘误：洞察板 revision 经核为纯计数器（`core/insight_board.py` L664-668），四域现状均无内容回退——回退从"既有能力"改为 P2 交付项（原文 v0.1.0 与评审首轮表述此处均有误，已一并修正）。
2. §5.1 补授权档优先级链与设置页语义约束；补 workspace_write 直写边界（仅 output/，任务数据必须走 MCP 工具）。
3. §5.1/§5.4 明确 boardCoCreate 双职责拆分：升档退役、意图 flag 独立保留。
4. §5.2 补角色禁令全覆盖清单（含 `_roles/my/`、`chat.py` L261-266）与用户自建角色的运行时覆写策略。
5. §5.3 新增快照强制契约（字段级、写前、AI-only、N=20+retention）、决策域收口 `core/decision_flow.py` 按节点 id、随记改建议模式（市场模式 C/D）。
6. §5.4 `done.rewritten` 补 diff 摘要 + 按轮恢复入口（借 Cursor/Claude Code 交互语义，实现取字段快照而非影子 git）。
7. §6 P2/P3 内容与影响文件相应调整；§8 增验收 6/7/8 条；§9 两项待决给出评审裁决建议。

**市场机制调研依据（2026-09 检索）**：Claude Code 官方 checkpointing（每 prompt 前自动快照、/rewind 按轮恢复、100 个/约 30 天保留）；Cursor 官方 checkpoints 文档 + vibe-replay 影子仓库拆解（写前快照、整轮全量恢复、无固定保留上限——列为反面教训）；Microsoft 365 Copilot in Word（提案-保留式审批闸）；Granola/Otter 类纪要产品域隔离惯例（AI 不直写用户原创区）。

## 11. 工程审查与修订记录（v0.2.0 → v0.3.0，2026-09-29，审查：代码逐项锤定）

**锤定结果**：v0.2.0 全部锚点复核属实（含四处角色禁令、revision 纯计数器、随记零写工具、dont_ask 拒写链路、settings 默认档）；未发现虚构。

**本次修订项（三处 P1 级机制假设冲突，均已采纳并随 P1 实施落地）**：
1. §5.1 直写边界重写：任务数据物理直写本已不可达（data/ 不在工作区/add_dirs 内），真未治理面是 add_dirs 项目目录可写性（SPIKE 核实项）；原 AC8 拆为两条可测断言（§8-8a/8b）。
2. §5.2 删"问答段"死代码：context_export 仅智能体路径执行，问答模式无 AGENTS.md 消费方；chat.py L261-266 内置 prompt 从"直接改文件"改为"保持不动"；权限段改为按落档（可写/降级只读）两段。
3. §5.1/§5.4 意图 flag 定为轮级语义（发出即消费），新增 AC9；避免会话级常驻 flag 推广后的横幅误报。

**审查发现的事实补充（已写入对应章节）**：
- §9 决策节点 id：从"待核实"坐实为"确认缺口"（`_tool_get_meeting_todos` 不暴露 id），P3 前置动作明确。
- §5.4 审计"已有"的含义修正：四个写工具的 `audit_logger` 条目代码均已存（`agent_tools.py` L94/L112/L121/L132），但生产 audit.log 中 `revise_*` 尚无实写条目（仅 test 任务的 inject 条目）——"代码已有、实战待验"。
- 降级档 LLM 豁免延续：`agent_tools.py` L61-65 已允许 readonly 档调 `revise_insight_board` 读语义，"仅深度问答"降级轮仍可读基线，无需新增机制。
- 测试影响面：P1 改动波及 `tests/test_cli_engine.py`（权限段/授权档断言）与 `tests/test_agent_tools.py`（令牌/allowlist），已随实施同步更新。
