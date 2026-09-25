---
title: T1 设计稿 — 说话人实名化展示策略（REQ-SPK-RN）
id: REQ-SPK-RN/T1
version: 0.1.0
status: draft（管理员初审 → 项目方确认后作为 T2 实施依据）
date: 2026-09-25
author: 前端开发工程师 d1b77737cde5
related:
  - docs/REQUIREMENT-SPEAKER-REALNAME-DISPLAY.md v0.1.0（需求单，H1-H4 硬约束）
---

# 1. 设计总纲

一句话口径：**「编号占位名」从展示层彻底消失；有真名显真名，没真名显中性聚合态，数据本体不动（H4）。**

说话人展示数据源优先级（全站点统一，收敛为单一解析函数，禁止各组件自判）：

```
1. linked_user_id → users.json 真实用户名
2. speakers.json 档案 name（排除占位名，见 §2 判定器）
3. 声纹/会中绑定回填名（既有接口产物，归入 2）
4. 以上皆无 → 未绑定态（§3 Q1 方案）
```

**占位名判定器**（前端 util + 验收正则同源）：`/^Speaker\s+\d+$/i`、`/^Speaker\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)$/i`、`/^说话人\s*\d+$/`、`/^发言人\s*\d+$/`。命中即视为「无真实信息」，进入未绑定态分支。存量 `task.speaker_mapping` 不改写（H4），过滤只发生在读取渲染时。

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

# 3. Q1 回答 — 未绑定说话人的呈现策略

**推荐：聚合计数「未识别 n 人」+ 中性点位列。** 三选一对比：

| 方案 | 信息量 | 侵入度 | 风险 |
| --- | --- | --- | --- |
| A 完全隐藏 | 差——用户不知该会议还有未识别发言人，误以为数据丢失 | 最低 | 「怎么少了几个人」类反馈 |
| B 聚合「未识别 n 人」（推荐） | 保留人数事实，不泄露编号 | 低 | n=0 时不渲染；文案中性，不违 H1（无编号） |
| C 占位改「去绑定」引导 | 好 | **超出本单范围**（新增交互入口/跳转逻辑） | 需项目方另行拍板，本单不预设 |

各点位套用 B 的具体规则：

- **侧边栏 TaskCard Top3**：仅列真实名（≤3）；存在未绑定时追加一枚中性计数 chip「未识别 n」（i18n `speakers_unidentified`，zh「未识别」/en「Unidentified」，带 title「n 位发言人尚未关联身份」）。全为占位时只显示「未识别 n」。
- **库页说话人列**：同 Top3 规则（真实名列表 + 尾计数）。
- **转写面板 / 录音页实时转写**：行首标签用「未识别」+ 色点区分不同说话人（颜色本就有 `getSpeakerColor` 体系），**不再输出编号**；同一会议内不同未绑定说话人靠颜色与相邻上下文区分。头像首字取「未」/「?」，不用数字。
- **会议详情说话人区（L1）/ 绑定下拉（L2/L6/L7）**：未绑定项在绑定选择器中显示「未识别 · 约 n 分钟」，点击进既有关联流程（复用现有入口，不新增交互）。
- **roster / SpeakersView**：roster 同步（L3）改为**占位名不入 roster**（filter 判定器命中即跳过）；SpeakersView 存量占位档案仍列出（档案是数据本体，H4 不改写），但列表名旁加「未识别」灰标，档案改名走既有编辑功能。

# 4. Q2 回答 — 库页下拉取数口径

- 下拉**只枚举真实姓名**：并集 =（speakers.json 有效档案名 ∪ 各任务 speaker_mapping 中非占位名），去重、localeCompare 排序。占位名一律不枚举。
- **增设一个特殊筛选项「未识别」**（i18n `filter_speaker_unidentified`）：命中条件 = 该任务 speaker_mapping 含任一占位名。解决「历史会议无法按未绑定片段过滤」的顾虑——可筛、但按聚合口径而非逐个编号。
- 匹配语义：选真实名 → 任务 mapping 值或绑定档案名等于该真实名；选「未识别」→ 含任意占位名。搜索匹配（L9 `utils/search.ts`）同步此口径：搜「Speaker」不再命中占位任务（占位串不作为可搜索文本），搜「未识别」命中含占位任务。
- 说话人列折叠态（SPK_MAX_SHOWN=4）内计数同样把「未识别 n」作为一个聚合项计入。

# 5. Q3 回答 — 派生污染位是否纳入 H1

分两类，**结论不同**：

1. **结构化展示位（纳入）**：projects 参与者列表若在前端渲染（项目详情/知识库 UI），属用户可见界面，按 §1 优先级 + §3-B 规则过滤——纳入 H1 清单（本设计已并入 L3-L5 同类处理）。`core/projects.py:235-264` 生成的 `participants:` frontmatter 是**落盘文件内容**，与导出同性质，见下条。
2. **文本内嵌位（不纳入本单实施，列入 T2 风险与 Q4 后端单）**：纪要正文（summarize.py 提示词让 LLM 输出「说话人X认为…」）、聊天回复（chat.py 注入 `f"Speaker {sid+1}"`）、洞察卡片（insights.py `[说话人N]` 前缀回显）、待办 assignee、章节标题、决策条目、**md/docx 导出**（`tasks.py:206` 直读落盘文件、`docx_export.py:11` 原样转换）、项目知识库 .md。这些是**生成内容而非展示数据**，前端过滤不可达或需脆弱的正则洗文——若强行纳入，AC-1 会在导出与聊天场景必然失守。**建议 AC 草案明确：H1 的「导出」口径 = 导出内容中的说话人前缀来自展示侧同源解析（即依赖 Q4 后端单），本单 T2 验收范围 = 前端渲染点位。** 此口径需项目方确认。

# 6. Q4 回答 — H4 后端根因派生单

**建议立项，优先级 P1（T2 合入后紧随），单号建议 REQ-SPK-RN-B1，归属后端工程师 a4cdbd0ca795。** 理由：

1. 根因不封：`core/pipeline.py:241,252`、`speakers.py:344`、`import_parser.py:277` 持续写入 `f"Speaker {n}"`，展示侧过滤是治标；新数据每天在产生。
2. 不可达面：§5 第 2 类（导出/LLM 文本/知识库）只有后端能修——生成端不再注入占位名 + `apply_names` 洗名覆盖「跳过关联」路径（`useSpeakerBinding.ts:166` 之后永不洗名）。
3. 存量档案清洗：`speakers.json` 已被 L2 写入的占位档案需一次性迁移（改名或标记），属后端单范围（H4 只约束 `tasks/*.json`，档案库清洗不违反）。

范围建议：① 默认名改为不落盘（mapping 键保留、值留空即未绑定态，前端 §3 规则天然承接）；② 导出/摘要/聊天注入层统一走「真名或中性未识别标记」解析；③ apply_names 扩展 + 存量档案迁移脚本。**注意 `core/pipeline.py` 当前有他人未提交 WIP，后端单开工需等其落定，开工前 rebase。**

本单 T2 前端侧同步修 L2（`useSpeakerBinding.ts:127` 空名不落占位——改为要求输入非空或落「未识别」中性名，与后端单口径对齐）。

# 7. i18n 处理清单

| key | 处置 |
| --- | --- |
| `generating.speaker_default`、`recording.speaker.default_name` | 删除编号插值，改中性「未识别」/「Unidentified」（无 {id}） |
| `generating.onboarding.demo_label_1/2` | 换真实示例名（zh「小李 / 小王」，en「Alex / Jordan」），仅作演示 |
| 新增 `speakers_unidentified`（task/library 命名空间）、`filter_speaker_unidentified`（library）、说话人区「未识别 · 约 n 分钟」（generating） | zh-CN/en 双语同步，17→21 keys 量级 |
| 静态文案含「说话人/发言人」字样（菜单、计数、placeholder 约 60 keys） | **非编号占位，不违 H1，不动**（如「说话人」列名是功能名词） |
| `useAiChat.ts:375`、`useAiGuidance.ts:51,62` 硬编码中文「发言人」建议文案 | 顺路 i18n 化（T2 小项，不含编号，不违 H1） |

# 8. T2 实施排期建议 + AC 草案细化回写

- 排期：REQ-PROGRESS-P0 关单 → AM-F1（项目方已裁提前）→ **REQ-SPK-RN T2** → REQ-SPK-RN-B1（后端并行可提前，若 pipeline.py WIP 落定）。T2 前端点位收敛为一次提交：判定器 util + 统一解析 composable + 9+2 点位替换 + i18n；预估单人 1-2 天。
- AC 回写建议（对需求单 §4）：
  - AC-1 正则口径追加：`未识别\s*\d` 不违例（计数非编号名）；范围限定「前端渲染点位」，导出面挂 B1。
  - AC-2 增补：绑定下拉/roster/SpeakersView 三处真实名一致性。
  - AC-3 按 §4 口径：真实名可筛 + 「未识别」特殊项可筛。
  - AC-4 增补：T2 前后 `data/speakers.json` 也不变（L2 修复只影响**新**建档行为）。
  - AC-5 增补：Onboarding 弹窗双语截图纳入。
  - 新增 AC-7（建议）：L2 回归——新建说话人空名不再产生占位档案。

# 9. 决策请求汇总（交项目方拍板）

| # | 事项 | 本稿建议 |
| --- | --- | --- |
| D1 | H3 未绑定态呈现 | 方案 B 聚合「未识别 n」（§3） |
| D2 | 库下拉是否含「未识别」特殊筛选项 | 是（§4） |
| D3 | 导出/LLM 文本内嵌面是否挂本单 AC | 不挂，移交 B1（§5） |
| D4 | 后端根因单 | 立项 P1（§6） |
| D5 | 转写行首「未识别」+颜色区分（无编号） | 采纳（§3） |
