---
title: T1 设计稿 — 说话人实名化展示策略（REQ-SPK-RN）
id: REQ-SPK-RN/T1
version: 0.2.0（按项目方裁决 D5/D6 收敛：Q1/Q4 关闭；细化聚合粒度、绑定位文案、Q2 取舍报告、Q3 纳入确认、BE-R3 联调基准）
status: draft（管理员初审 → 项目方确认 Q2 取舍后作为 T2 实施依据）
date: 2026-09-25
author: 前端开发工程师 d1b77737cde5
related:
  - docs/REQUIREMENT-SPEAKER-REALNAME-DISPLAY.md v0.2.0（需求单，H1-H4 硬约束 + §7 REQ-SPK-RN-BE）
---

# 1. 设计总纲

一句话口径：**「编号占位名」从展示层彻底消失；有真名显真名，没真名显中性聚合态，数据本体不动（H4）。**

说话人展示数据源优先级（全站点统一，收敛为单一解析函数，禁止各组件自判）：

```
1. linked_user_id → users.json 真实用户名
2. speakers.json 档案 name（排除占位名，见下判定器）
3. 声纹/会中绑定回填名（既有接口产物，归入 2）
4. 以上皆无 → 未绑定态（§3 D5 两形态规则）
```

**占位名判定器**（前端 util + 验收正则同源，口径差收编请求见 §6/决策 D6）：`/^Speaker\s+\d+$/i`、`/^Speaker\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)$/i`、`/^说话人\s*\d+$/`、`/^发言人\s*\d+$/`。命中即视为「无真实信息」，进入未绑定态分支。存量 `task.speaker_mapping` 不改写（H4），过滤只发生在读取渲染时。

# 2. 点位清单复核结果

## 2.1 需求单位点：全部确认存在，行号勘误

| 需求单位点 | 实际位置（main@5476fe1） | 备注 |
| --- | --- | --- |
| TaskCard Top3 | `components/task/TaskCard.vue:191-222` | 基本准确 |
| LibraryView 下拉/列 | `views/LibraryView.vue:277-289`（下拉）、`342-348`（匹配）、`143-160 + 631-680`（列，已有 SPK_MAX_SHOWN=4 折叠） | 行号漂移已更正 |
| TranscriptPanel | **`views/generating/TranscriptPanel.vue`**（需求单误写 components/）：`:147` 兜底 + `:134` 头像数字首字 + `:231-241` 说话人面板 | 路径需回写需求单 |
| RecordingView 兜底 | `RecordingView.vue:381-386`、`useSpeakerPanel.ts:56`、`useSpeakerBinding.ts:61` | 准确 |
| 根因/下游 | `core/pipeline.py:241,252`、`core/speakers.py:344,405`、`core/import_parser.py:277,368`；`summarize.py`、`chapters.py:100`、`projects.py:235-264`、`chat.py` 多处 | 准确 |

## 2.2 新确认遗漏点位（必须入 H1 清单，共 9 处）

| # | 点位 | 文件:行号 | 露出形态 |
| --- | --- | --- | --- |
| L1 | 会议详情说话人区（最大遗漏） | `views/generating/GeneratingSpeakerZone.vue:17,22,37,39,120` | displayName 兜底「说话人N」必现；chip 名 + 窄屏圆点首字 |
| L2 | **占位名写库前端源头** | `composables/useSpeakerBinding.ts:126-127` | 「新建说话人」空名时用 `t('generating.speaker_default')` **持久化进 speakers.json**，此后全站档案名位长期污染——T2 必须一并修（前端侧） |
| L3 | roster 自动同步扩散 | `views/GeneratingView.vue:580-600` | 绑定占位名档案 → 名字写入参会名单并持久化 |
| L4 | 参会名单芯片 | `views/generating/MeetingRosterZone.vue:18-19` | 渲染 roster 字符串（含 L3 扩散名） |
| L5 | 说话人管理页 | `views/SpeakersView.vue:44,83,180,203` | 占位档案名 + 发言摘要/待办原文内嵌名 |
| L6 | 录制页参会人下拉 | `views/recording/RecControlBar.vue:33-48` | 档案名污染 |
| L7 | 录音中绑定弹窗 | `views/recording/RecSpeakerBind.vue:15` | 档案名污染（`onCreateAndBind` 本身要求非空，安全） |
| L8 | 录音页实时转写 | `views/recording/RecTranscriptPanel.vue:115,118` | WS `speaker_name` ← `app/realtime_store.py:95-112` 命中占位档案名 |
| L9 | 搜索匹配 | `utils/search.ts:29-34` | 搜占位串可命中任务（行为面，随 §4 Q2 口径一并处理） |

**Onboarding 弹窗（清单外补充）**：`generating.onboarding.demo_label_1/2` 硬编码「说话人 1 / Speaker 1」演示样例名，属 H1 违例，T2 换真实感示例名。

## 2.3 已排查安全位（不露名，仅计数/颜色）

`GeneratingView.vue:816-819`（计数）、`AiContextPanel/AIPanel`（数量）、`ProjectsView:172`、`RecTimeline`（色桶）、`useSpeakerStats`、`DecisionCenterView/DecisionFlowPanel/NotesPanel/Hotwords/Settings/Start/Agents` 无编号占位代码（但决策/纪要**文本内嵌**见 §5 Q3 污染面）。

# 3. D5 落地 — 全点位「未识别」聚合粒度与计数口径

> Q1 已由项目方裁决 D5 关闭（需求单 v0.2.0 §2-H3）：**除可进行用户绑定操作的位置外，其余一律「未识别 N 人」聚合；绑定操作位保留逐个占位以待绑定，但展示文案不出现编号占位串。** 本章回答 T1 剩余问题：各点位聚合粒度、计数口径、绑定操作位替代文案。

## 3.1 计数口径（全点位统一）

- **N = 该展示范围内未命名说话人按 `speaker_id`（声纹 uuid）去重后的人数**，不是发言条数、不是段落数。
- 判定输入：任务 `speaker_mapping` 中值命中 §1 判定器（或为空）的 distinct `speaker_id`；若该 sid 已绑定 speakers.json 有效档案（非占位名/已关联 user），则**不**计入 N。
- **跨会议/库级不做人数加总**（不同任务的 sid 无跨任务身份，加总会造成「同一个人被数两次」的误导）。库级只用布尔聚合项「未识别」（= 该任务含 ≥1 未绑定说话人），呈现「未识别」字样而非数字 N；任务卡/会议内才用「未识别 N 人」。
- N=0 时不渲染任何计数元素（不留空 chip/占位）。
- 文案：zh「未识别 N 人」/ 单任务卡可缩写「未识别 N」；en "N unidentified" / "Unidentified"。**任何形态都不带编号、不带 sid 数字。**

## 3.2 分点位粒度表（D5 两形态逐位套用）

**形态 α — 聚合位（不可绑定处，一律「未识别 N 人」/「未识别」）：**

| 点位 | 规则 |
| --- | --- |
| 侧边栏 TaskCard Top3 | 仅列真实名（≤3）；存在未绑定时追加中性计数 chip「未识别 N」（title「N 位发言人尚未关联身份」）。全占位时只有这一枚 chip |
| 库页说话人列（含 SPK_MAX_SHOWN=4 折叠态） | 真实名列表 + 尾聚合项「未识别」；折叠计数把聚合项作为**一个**项计入，不展开 N 个 |
| 转写面板行首（`generating/TranscriptPanel.vue:147`）/ 录音页实时转写（L8） | **发言级单数形态**：行首标签「未识别」+ 色点（复用 `getSpeakerColor`），不输出编号；同会议内不同未绑定说话人靠颜色 + 相邻上下文区分。头像首字取「未」/「?」，禁用数字 |
| 参会名单芯片（L4）/ roster 同步（L3） | L3 改为**占位名不入 roster**（判定器命中即跳过同步）；L4 存量 roster 字符串渲染前过判定器，命中项显示「未识别」（同名单去重后只出现一枚） |
| Onboarding 演示弹窗 | 非真实数据，不适用聚合——换真实感示例名（§7），彻底移除编号字样 |

**形态 β — 绑定操作位（逐个保留待绑定实体，文案无编号）：**

| 点位 | 替代文案 |
| --- | --- |
| 会议详情说话人区 L1（`GeneratingSpeakerZone`） | 每个未绑定 sid 仍逐个成 chip/圆点（可点进既有关联流程），显示名「未识别」，圆点首字用色点符号不用数字；旁注时长「未识别 · 约 n 分钟」 |
| 绑定下拉（L6 RecControlBar / L7 RecSpeakerBind） | 未绑定项逐条显示「未识别 · 约 n 分钟」（n 取该 sid 累计发言时长，无时长数据时仅「未识别」）；真实名档案正常显示。选中即走既有绑定流程 |
| 说话人管理页 L5（SpeakersView = 档案编辑操作位） | 存量占位档案**仍列出**（档案是数据本体，H4 不改写），档案名位置显示「未识别」灰标 + 内部 sid 仅用于键不渲染；改名走既有编辑功能。发言摘要/待办原文内嵌名属 §5 文本内嵌面，不在本点位处理 |

**L2 写库源头（T2 前端必做）**：`useSpeakerBinding.ts:126-127` 空名建档不再落 `t('generating.speaker_default')` 占位串——改为非空校验引导（复用既有必填交互），确保**新**档案永不写入编号占位名。

# 4. Q2 回答 — 库页下拉筛选取舍（含理由，待项目方确认 = 决策 D2）

**取舍结论（本稿建议）：真实名正常枚举 + 增设一个特殊筛选项「未识别」；占位名一律不枚举。**

- 枚举口径：并集 =（speakers.json 有效档案名 ∪ 各任务 speaker_mapping 中非占位名），去重、`localeCompare` 排序。
- 「未识别」特殊项命中条件 = 该任务 `speaker_mapping` 含任一占位名/空值（§3.1 布尔口径，不做跨任务计数）。
- 匹配语义：选真实名 → 任务 mapping 值或绑定档案名等于该真实名；选「未识别」→ 含任意占位名。
- 搜索匹配（L9 `utils/search.ts`）同步此口径：占位串不作为可搜索文本（搜「Speaker」不再命中占位任务），搜「未识别」命中含占位任务。

**保留「未识别」筛选项的理由（3 条）**：① 可发现性——用户能定位「哪些历史会议还有未绑定片段」进而去绑定，是本需求实名化闭环的入口；若删除，未绑定数据变成不可过滤的暗数据。② 信息量——聚合布尔项不泄露任何编号，符合 H1/D5，删它对合规零增益。③ 成本——一个特殊枚举值 + 一个谓词，无新增交互。

**若项目方选择删除（披露代价）**：库页将无法过滤含未绑定说话人的任务；Onboarding 之外用户感知不到「哪些会议待处理」，实名化推进缺乏抓手。管理员初审时请一并裁定。

# 5. Q3 复核 — 派生污染点位纳入清单结论

> 需求单 v0.2.0 已立 REQ-SPK-RN-BE（D6）；本章回答「projects 参与者等派生位是否纳入 T2（前端）验收」。

1. **projects 参与者（结构化展示位）→ 纳入 T2**。复核前端消费面：`participants` 数据在用户界面仅 **ProjectsView 一处**渲染（`:172` 为计数，安全位；列表名渲染走项目详情参与人区）。属用户可见界面，按 §1 优先级 + §3 聚合规则过滤——纳入 H1/T2 清单。注：`core/projects.py:235-264` 生成的 `participants:` frontmatter 是**落盘文件内容**，与导出同性质，归 BE（下条）。
2. **文本内嵌位 → 不纳入 T2，归 REQ-SPK-RN-BE**：纪要正文（summarize.py 提示词输出「说话人X认为…」）、聊天回复（chat.py 注入 `f"Speaker {sid+1}"`）、洞察卡片（insights.py `[说话人N]` 前缀回显）、待办 assignee、章节标题、决策条目、**md/docx 导出**（`tasks.py:206` 直读落盘文件、`docx_export.py:11` 原样转换）、项目知识库 .md。这些是**生成内容而非展示数据**，前端过滤不可达或需脆弱洗文；强行纳入则导出/聊天场景必然失守。**AC 口径建议（延续 §8-AC1）：H1「导出」口径 = 说话人前缀来自 BE-R3 读取侧归一化同源解析（依赖后端单），T2 验收范围 = 前端渲染点位。** 此口径需项目方在初审时确认。

# 6. Q4/BE-R3 联调基准 — T2 与 REQ-SPK-RN-BE 的接口口径

> Q4 已由裁决 D6 关闭：后端根因立项 **REQ-SPK-RN-BE**（需求单 §7），**T2 展示逻辑以 BE-R3 读取侧归一化口径为联调基准**。本章为联调约定。

## 6.1 ⚠ 口径差提醒（决策 D6，需后端/管理员确认收编）

需求单 §7 BE-R3 归一化正则 `Speaker \d|说话人\d|发言人\d` **未覆盖英文单词形态 `Speaker One/Two/…/Ten`**——而项目方指令原文点名的正是「Speaker One/Speaker Two」，且实测存在于历史 `tasks/*.json` 数据。若两侧正则不一致：

- BE-R3 归一化后单词形态仍作「有效名」返回 → 前端聚合层若同款漏判，H1 在指令点名场景直接失守；
- 前端若单独按超集实现而 BE 不收编，`apply_names` 洗名、导出前缀替换均会漏掉这批记录，两侧「未识别」计数与筛选口径漂移。

**本稿立场：前端判定器按超集实现（§1，含单词形态），并请求 BE-R3 正则收编同一超集。** 联调验收以两侧同一正则为准（AC-8 钉死，见 §8）。

## 6.2 合入顺序自适应

- **BE 先合**：前端读取侧判定器对已归一化数据命中为空集 → 天然无占位露出，T2 无需改一行适配。
- **T2 先合**：前端独立按 §1 超集过滤 + §3 聚合呈现，先消灭界面露出；BE 合入后读取侧语义不变。
- 两种顺序均成立，故不设强制依赖；但 **AC-8 双侧同正则断言必须在两侧都合入后跑通**才可关单。

## 6.3 实施注意

- L2（`useSpeakerBinding.ts`）为前端写库源头，**T2 必做**（§3.2 末），与 BE-R1「默认名不落盘」口径一致（值留空 = 未绑定态）。
- 存量 `speakers.json` 占位档案清洗归 BE 范围（H4 只约束 `tasks/*.json`，档案库清洗不违反）；前端 T2 只做读取侧过滤 + 灰标呈现。
- 主工作区 `core/pipeline.py` 存在已存档未归属 WIP（`qa-evidence/wip-archive/`）：BE 单必须在自身 worktree 基于 main 实施，勿动主工作区现场（需求单 §7 排期约束原文）。

# 7. i18n 处理清单

| key | 处置 |
| --- | --- |
| `generating.speaker_default`、`recording.speaker.default_name` | 删除编号插值，改中性「未识别」/「Unidentified」（无 {id}） |
| `generating.onboarding.demo_label_1/2` | 换真实示例名（zh「小李 / 小王」，en「Alex / Jordan」），仅作演示 |
| 新增 `speakers_unidentified`（task/library）、`filter_speaker_unidentified`（library）、绑定操作位「未识别 · 约 n 分钟」（generating/recording） | zh-CN/en 双语同步，17→21 keys 量级 |
| 静态文案含「说话人/发言人」字样（菜单、计数、placeholder 约 60 keys） | **非编号占位，不违 H1，不动**（如「说话人」列名是功能名词） |
| `useAiChat.ts:375`、`useAiGuidance.ts:51,62` 硬编码中文「发言人」建议文案 | 顺路 i18n 化（T2 小项，不含编号，不违 H1） |

# 8. T2 实施排期建议 + AC 草案细化回写

- 排期：REQ-PROGRESS-P0 关单 → AM-F1（项目方已裁提前）→ **REQ-SPK-RN T2** → REQ-SPK-RN-BE 联调收口（两侧合入顺序自适应，§6.2）。T2 前端点位收敛为一次提交：判定器 util + 统一解析 composable + §3 全点位替换（9+2 处）+ i18n；预估单人 1-2 天。
- AC 回写建议（对需求单 §4）：
  - **AC-1** 正则口径追加：「未识别 N / 未识别」不违例（聚合计数非编号名）；违例正则覆盖单词形态 `Speaker\s+(One|…|Ten)`；范围限定「前端渲染点位」，导出面挂 BE。
  - **AC-2** 增补：绑定下拉 / roster / SpeakersView 三处真实名一致性。
  - **AC-3** 按 §4 口径：真实名可筛 + 「未识别」特殊项可筛（若 D2 裁删则同步删除此 clause）。
  - **AC-4** 增补：T2 前后 `data/speakers.json` 与 `data/tasks/*.json` 均不变（L2 修复只影响**新**建档行为）。
  - **AC-5** 增补：Onboarding 弹窗双语截图纳入。
  - **AC-7**（新增）：L2 回归——新建说话人空名不再产生占位档案（必填引导生效）。
  - **AC-8**（新增，联调基准）：前端判定器与 BE-R3 归一化正则**同一超集**断言——两侧对同一批样本（含数字形态、单词形态、中文两式）判定结果逐条一致；两侧均合入后执行。

# 9. 决策表（状态更新）

| # | 事项 | 状态 |
| --- | --- | --- |
| D1 | H3 未绑定态呈现 | **已由项目方裁决 D5 关闭**（聚合「未识别 N 人」+ 绑定位无编号逐个），本稿 §3 为落地细则 |
| D2 | 库下拉「未识别」特殊筛选项取舍 | **待项目方确认**（本稿建议保留，理由与删除代价见 §4） |
| D3 | 导出/LLM 文本内嵌面 AC 归属 | **基本关闭**（随 D6 立 BE 单归口 §5-2），T2 验收范围=前端渲染点位的口径请初审顺带确认 |
| D4 | 后端根因单 | **已由裁决 D6 关闭**（立项 REQ-SPK-RN-BE，§7） |
| D5 | 转写行首「未识别」+ 颜色区分（无编号） | **已由项目方裁决关闭**，本稿 §3.2 形态 α 落地 |
| D6 | **BE-R3 正则超集收编**（补 `Speaker One…Ten` 单词形态） | **新增待确认**——需后端工程师 a4cdbd0ca795 / 管理员在 BE 单开工前裁定；前端按超集实现不依赖此裁定（§6.2），但 AC-8 关单依赖 |
