---
title: 需求记录 — 说话人实名化展示（去除 Speaker 编号占位名）
id: REQ-SPK-RN
version: 0.1.0
status: draft（项目方指令明确；展示策略方案设计交前端开发工程师，设计稿经管理员初审后报项目方确认，作为实施派工依据）
date: 2026-09-25
decided_by: 项目方（2026-09-25 指令：未关联或无实际意义的用户名对用户没有现实意义，且产生信息冗余，应去掉 Speaker One/Speaker Two 这类编号占位内容，在对应位置显示真实的用户信息；并指派 UI/前端工程师先设计、后排单修复）
category: 信息架构 / 说话人身份展示
related:
  - docs/DISPATCH-TRACKER.md（派工台账）
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
- **H3**：未绑定身份的说话人**不得**以编号占位名露出；其呈现方式（隐藏、聚合计数如「未识别 n 人」、中性词或其他）由 UI 工程师设计方案并经项目方确认后定稿，本单不预设。
- **H4**：本单最小口径为实现层**展示侧过滤/回填**，不改写存量数据（历史 `task.speaker_mapping` 保持原样，绑定动作仍走既有接口覆盖）。是否向 `core/pipeline.py` 等上游派生「不再写入默认名」的后端修复单，由设计稿列为决策项交项目方拍板，不纳入本单实施范围。

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

## 6. 开放问题（T1 需回答）

- Q1 未绑定说话人的侧边栏卡片呈现：完全隐藏 vs 聚合「未识别 n 人」vs 保留占位但改为可点「去绑定」引导？（涉及是否顺带做绑定入口露出，超范围须报项目方）
- Q2 库页下拉是否只枚举「说话人库真实姓名」，未绑定聚合项是否单独作为一个可筛选项（否则历史会议将无法按人过滤未绑定片段）？
- Q3 存量已派生污染数据（`core/projects.py` 参与者列表等）展示位是否纳入 H1 清单？
- Q4 H4 后端根因派生单是否立项、优先级？
