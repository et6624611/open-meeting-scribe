---
title: 需求记录 — 说话人实名化展示（去除 Speaker 编号占位名）
id: REQ-SPK-RN
version: 0.2.0
status: approved（口径裁决 D5/D6 已由项目方批复，作为派工依据；T1 设计稿仍待工程师收敛回报）
date: 2026-09-25
decided_by: 项目方（2026-09-25 指令：未关联或无实际意义的用户名对用户没有现实意义，且产生信息冗余，应去掉 Speaker One/Speaker Two 这类编号占位内容，在对应位置显示真实的用户信息；并指派 UI/前端工程师先设计、后排单修复。09-25 追加裁决：**D5** 除可进行用户绑定操作的位置外，其他位置一律以「未识别 N 人」聚合方式呈现未绑定说话人；**D6** 后端根因修复立项，派生单 REQ-SPK-RN-BE 交后端工程师）
category: 信息架构 / 说话人身份展示
related:
  - docs/VUE_COMPONENT_MAP.md（Sidebar / TaskCard / LibraryView 组件映射）
  - docs/GLOSSARY.md（「说话人」「speaker_mapping」词条可能需随本需求修订）
  - docs/REQUIREMENT-TRANSCRIBE-PROGRESS-DISPLAY.md（同 Owner 在途单，注意排期互斥）
  - docs/REQUIREMENT-ACCESS-MODE-CARDS.md（AM-F1 待派工，排期需一并权衡）
owner: 项目管理员（定义与跟踪）/ 前端开发工程师 d1b77737cde5（设计与实施）
---

# 需求记录：说话人实名化展示（REQ-SPK-RN）

## 1. Problem（要解决什么）

系统各处大量出现 **Speaker One / Speaker Two（及 Speaker N / 说话人N / 发言人N 变体）** 的编号占位名。这些名字是 ASR 分离出说话人但**未完成真实身份绑定时**写入的默认值，对用户没有任何信息量，且造成列表/筛选器信息冗余。项目方明确要求：用户可见界面不显示这类占位编号，对应位置显示真实的用户信息。

用户已发现的两个位置：

1. **左侧边栏会议列表**（TaskCard 从 `task.speaker_mapping` 取 Top3 说话人渲染）；
2. **会议库说话人下拉筛选**（选项值来自各任务 `speaker_mapping` 去重，默认名直接混入）。

全站点位普查（本会话代码核查结果，实施前由设计师复核补全）：

| 点位 | 文件 / 行号 | 占位名来源 |
| --- | --- | --- |
| 侧边栏会议卡片 Top3 | `frontend/src/components/task/TaskCard.vue:24-38、187-220` | 后端落盘 `task.speaker_mapping` 默认名 |
| 库页说话人下拉筛选 | `frontend/src/views/LibraryView.vue:49-51、277-288` | 同上（遍历所有任务去重） |
| 库页说话人列 | `LibraryView.vue:142-153、631-675` | 同上 |
| 转写面板 | `frontend/src/components/TranscriptPanel.vue:147` | i18n 兜底 `speaker_default` |
| 实时录制页 | `RecordingView.vue:385`、`useSpeakerPanel.ts:56`、`useSpeakerBinding.ts:61、127` | i18n 兜底（en「Speaker {id}」/ zh「说话人{id}」） |
| 默认名生成根因 | `core/pipeline.py:241、252-253`、`core/speakers.py:344`、`core/import_parser.py:277` | 无绑定时持久化 `f"Speaker {n}"` |
| 下游污染 | `core/summarize.py`、`core/chapters.py`、`core/projects.py:235-247`（参与者列表）、`app/routers/chat.py` | 读取默认名 |

真实用户信息可用数据源：全局说话人库 `data/speakers.json`（`Speaker.name / linked_user_id`，`core/speakers.py:40-77`）、系统用户 `data/users.json`、会中绑定接口 `app/routers/speakers.py:284-358`、声纹自动匹配 `core/voiceprint_identify.py`。

## 2. 指令口径（硬约束，不可协商）

- **H1**：用户可见界面（含本表未列出的全部页面/导出/弹窗）不得出现 "Speaker N / 说话人N / 发言人N" 编号占位串。
- **H2**：已绑定真实身份的说话人，在对应位置显示真实姓名（来自说话人库/会中绑定/声纹匹配回填）。
- **H3**：未绑定身份的说话人**不得**以编号占位名露出。呈现口径已裁决（D5，2026-09-25 项目方批复）：**除可进行用户绑定操作的位置外，其他一切位置统一以「未识别 N 人」聚合方式呈现**（N 为该展示范围内未绑定说话人去重计数）。绑定操作位（如会中绑定面板、说话人库管理）保留逐个占位以待绑定，但展示文案不出现编号占位串（具体文案由 T1 设计稿定）。
- **H4**：本单（REQ-SPK-RN）实施范围为实现层**展示侧过滤/回填**，不改写存量数据（历史 `task.speaker_mapping` 保持原样，绑定动作仍走既有接口覆盖）。后端根因修复已裁决立项（D6）：**派生单 REQ-SPK-RN-BE**，规格见 §7，Owner 后端工程师。

## 3. 交付物与阶段（设计 → 排单 → 修复）

| 阶段 | 交付物 | 验收门 |
| --- | --- | --- |
| T1 设计 | 展示策略设计稿（含全站点位清单复核结果、H3 未绑定态呈现方案及理由、下拉筛选与列表的取数规则、i18n 兜底文案处理、H4 后端派生决策项） | 管理员初审 → 项目方确认后才进入 T2 |
| T2 实施 | 按设计稿提交 PR（分支 `feat/req-spk-rn`，worktree 隔离，基于合入时 main） | pytest 全绿 + 构建全绿门禁 |
| T3 验收 | **浏览器验收包**（硬性交付物）：涉及页面/入口路径、非技术语言分步验证脚本（≤5 步）、「什么样算通过」、自测截图 | 管理员 AC 初审 → 置 `browser-acceptance-ready` → 项目方浏览器核验通过才关单 |

## 4. 验收标准（AC 草案，随 T1 设计稿细化并回写本文件）

- **AC-1** 全站点位清单内每个页面截图证明：侧边栏会议列表、会议库下拉筛选与说话人列、转写面板、实时录制页均无 H1 违例串（正则口径 `Speaker \d|说话人\d|发言人\d|Speaker (One|Two|…)`）。
- **AC-2** 对一场已绑定 ≥1 位真实姓名的会议：真实姓名在侧边栏卡片与库页正确显示，与设计稿取数规则一致。
- **AC-3** 会议库说话人筛选按定稿口径可用：真实姓名可筛选，未绑定说话人按 H3 定稿方案呈现且筛选行为无异常（可选/不可选口径与设计一致）。
- **AC-4** 存量数据零改动：跑单前后 `data/tasks/*.json` 的 `speaker_mapping` 内容不变（展示层过滤证明）；既有绑定接口回归通过。
- **AC-5** i18n：中英双语环境下均无编号占位串露出（含实时录制页兜底文案路径）。
- **AC-6** 浏览器验收包四件套齐备（见 T3）。

## 5. 排期与并行约束

- Owner（前端开发工程师 d1b77737cde5）现状：REQ-PROGRESS-P0 处 RF-P0-1 补证收尾（awaiting-acceptance）；AM-F1 项目方已裁决排队等两单合入。**T1 设计为纸面工作，可即刻并行启动，不动代码**；T2 实施排队顺序在设计稿回报时一并给出建议，由管理员结合台账排期，改序需项目方拍板。
- 冲突面：本单点位（TaskCard / LibraryView / TranscriptPanel / RecordingView 展示层）与 REQ-PROGRESS-P0（进度面板）、AM-F1（设置与状态栏）基本不相交；若 T1 设计牵出后端派生单（H4），归属后端工程师 a4cdbd0ca795，另立单号。

## 6. 开放问题裁决与遗留设计点

- **Q1（已裁决 D5）**：非绑定操作位一律「未识别 N 人」聚合呈现，不做单占位「去绑定」引导（绑定入口收敛在绑定操作位）。各点位聚合粒度与计数口径、绑定操作位的替代文案仍由 T1 设计稿细化。
- **Q2（待设计）**：库页下拉是否枚举「说话人库真实姓名」+ 可选「未识别」聚合项；若「未识别 N 人」不可筛选，历史会议未绑定片段将无法按人过滤——设计稿给出取舍与理由报项目方。
- **Q3（随 D5 口径推定）**：`core/projects.py` 参与者列表等派生展示位属「其他位置」，纳入 H1/「未识别 N 人」口径清单；T1 设计稿复核确认。
- **Q4（已裁决 D6）**：后端根因修复立项，见 §7。

## 7. 派生单 REQ-SPK-RN-BE — 后端根因：停止持久化 Speaker 编号默认名（D6 立项）

**问题**：`core/pipeline.py:241、252-253`（转写管道无绑定时写入 `f"Speaker {sid+1}"` 并持久化进 task JSON 的 `speaker_mapping`）、`core/speakers.py:344`（`apply_speaker_names` 回退同名）、`core/import_parser.py:277`（导入解析生成默认名）——默认名一旦落盘即污染所有下游消费方（摘要、章节、项目参与者、chat、库筛选），前端只能逐处过滤，属治标。

**修复口径（需求级，实现方案由 Owner 出技术提案后实施）**：

- **BE-R1** 三处生成点不再向持久化数据写入编号默认名；未绑定说话人在数据层以可枚举但无名分的形态存在（如保留 `speaker_id`/uuid 映射与人数信息，姓名字段留空），供展示层按 D5 口径聚合计数。
- **BE-R2** 既有绑定链路语义不变：`app/routers/speakers.py` 绑定后以真实姓名回填 `speaker_mapping` 并原地替换摘要/待办的既有行为保留；声纹匹配回填（`core/voiceprint_identify.py`）同理。
- **BE-R3** 存量数据兼容：历史 task JSON 中已落盘的 `Speaker N` 不强制迁移（避免批量改写用户数据）；读取侧归一化——`speaker_mapping` 值命中编号占位模式（`Speaker \d|说话人\d|发言人\d`）一律视为「未命名」，等效于空姓名参与 D5 聚合。归一化函数收敛为单一公共入口，供 summarize/chapters/projects/chat/text_bridge 等全部下游复用。
- **BE-R4** 门禁：pytest 全绿；新增用例覆盖「未绑定不落默认名 / 读取侧归一化 / 绑定回填链路回归」三类；存量 task 数据零改写回归用例。

**排期与约束**：Owner 后端工程师 a4cdbd0ca795（与 AM-B1/RT-P0-FIX 同人），RT-P0-FIX 修复单优先级保持在前；本单改动面在 `core/` 与 `app/`，禁改 `frontend/`（前端点位归 REQ-SPK-RN T2）；主工作区 `core/pipeline.py` 存在已存档未归属的 WIP 改动（`qa-evidence/wip-archive/`），本单必须在自身 worktree 基于 main 实施，勿动主工作区现场。与 REQ-SPK-RN T2（前端展示侧）可并行：T2 的过滤逻辑以 BE-R3 归一化口径为对齐基准，若先行合入则 T2 相应简化，联调点由管理员在排期时标注。
