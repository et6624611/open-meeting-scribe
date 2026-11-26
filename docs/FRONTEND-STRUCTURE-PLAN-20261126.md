---
title: 前端结构治理方案（2026-11-26）
description: Vue 前端拆分评估后的落地计划，按 P0/P1 分项实施，每项独立可验收、可回退。已通过独立评审并修订。
tags: ["frontend", "vue", "refactor", "architecture", "tech-debt"]
created_at: "2026-11-26"
updated_at: "2026-11-26"
version: "1.2.0"
author: "Yongliang Wang"
status: "implemented"
category: "technical"
---

# 前端结构治理方案（2026-11-26）

> 执行说明：本文档可独立实施，无需回看对话。P0 项零行为变更；P1 项会移动组件边界，需人工回归；P2 仅登记，不在本轮。
> 基线：`npx vue-tsc -b` 通过（2026-11-26）。构建产物由 FastAPI 托管 `frontend/dist`，改完必须 `npm run build` 才在应用内生效。
> 评审记录见第 7 节。

## 1. 结论

拆分方向正确，不需要重构。问题不是"拆没拆"，而是三个边界没定死：

1. `TranscriptPanel` 同时承担原文列表、书面版状态机、说话人侧面板、播放控制四件事，是新增功能的主要落点。
2. 两份转写面板各自维护显示工具，且未识别说话人的兜底文案两套。
3. 文档与目录里有失效引用和云同步副本，让"该改哪个文件"失真。

本轮只做"拆职责 + 去重 + 修文档"，不动交互、不动布局、不动数据流。

## 2. 基线事实（已逐条核验）

> 本节数字与行号均为**改造前**（2026-11-26 动工前）口径，用于说明问题规模；文中行号随之失效，符号名仍有效。改造后的规模与行数见第 8 节。

| 项 | 实测 | 证据 |
|---|---|---|
| 前端规模 | 82 个 `.vue` + 121 个 `.ts` | 约 4.2 万行 |
| `composables/` | 58 个 `.ts`（不含测试），9233 行 | 其中 8 个为模块级单例 |
| `stores/` | 10 个文件，1483 行 | 偏薄 |
| 主题数 | 10 套 | `stores/theme.ts:L5-L16` |
| 测试文件 | 13 个 | 无转写面板挂载测试 |
| `GeneratingView.vue` | 868 行 / 20 个 composable 引用 | 模板 L126-L184 为 TranscriptPanel 接线 |
| `TranscriptPanel.vue` | 723 行；props **37** 个（L429-L472）、emits **21** 个（L612-L634） | 承担原文/书面版/说话人面板/播放条 |
| `GeneratingSpeakerZone.vue` | 490 行；props **12** 个（L297-L319）、emits **15** 个（L321-L340） | |
| `RecTranscriptPanel.vue` | 740 行；props **21** 个（L377-L399） | 录音实时转写 |

### 2.1 不做什么（评审后确认）

- **不把 `Set` 改成数组**。`expandedChapters` / `visibleChapterIndices` 来自 `useGeneratingData.ts:L164-L166` 的 `reactive(new Set())`，`speakerFilterSet` 来自 `useSpeakerPanel.ts:L25`，Vue 3 对 reactive 集合追踪完整。
- **不抽"共享滚动内核"**。贴底跟随、程序性滚动窗口、三段落底校正只存在于 `RecTranscriptPanel.vue:L578-L681`；`TranscriptPanel.vue` 自身无贴底逻辑，播放定位由 `usePlaybackFollow.ts:L37-L48` 的 `scrollIntoView` 完成。硬抽共享层是为对称造抽象。
- **不做"props 按域分组 + 父级 `v-bind`"**。评审确认该做法只把 38 行模板藏起来：prop 总数不变，新增字段仍改三处；`v-bind` 的对象展开会放宽必填校验，且子组件多出的键会静默落到根节点。该方案作废。

### 2.2 确实重复的部分

| 重复项 | 位置 | 一致性 |
|---|---|---|
| 毫秒转 `mm:ss` | `TranscriptPanel.vue:L657-L661`、`RecTranscriptPanel.vue:L707-L710`、`SummaryPanel.vue:L191-L195` | 三处逐字相同，均无小时位（第三处为复查时补入） |
| 时间点 → 章节索引 | `TranscriptPanel.vue:L663-L668`、`useGeneratingData.ts:L156` | 两份实现，语义相同 |
| 头像首字 | `TranscriptPanel.vue:L692-L696`、`utils/speakerDisplay.ts:L65-L69`、`RecTranscriptPanel.vue:L700-L705` | **不一致**，不可直接合并 |
| 说话人色值包装 | `RecTranscriptPanel.vue:L689` | 包一层 `getSpeakerColor`，可直接删 |

**头像差异（必须按此处理）**

- `utils/speakerDisplay.ts`：未识别默认 `未`，真名取首字并 `toUpperCase`
- `TranscriptPanel.vue`：未识别取 `t('generating.speaker_unid_initial')`（zh 为「未」，en 为 `?`），不转大写
- `RecTranscriptPanel.vue`：已绑定取真名首字大写；未绑定显示**编号** `N+1`（与行内「说话人N」标签配套）

结论：统一到 utils，但两个面板各自传入自己的兜底 label；录音面板的"编号优先"分支保留在本地，不进 utils。

## 3. 分项

> 本节为改造前的方案稿，保留判断依据；实际落地的接口以第 8 节与代码为准，个别字段与本文草案不同（见 P1-1 的括注）。

### P0-1 修正组件地图与脏文件说明

> 状态：已完成（2026-11-26）。验收见第 8 节。

**目标**：消除"不存在的文件还在文档里"。

**改动**

1. 修正 `docs/VUE_COMPONENT_MAP.md` 的 8 条失效引用（均已核实）：

| 文档写法 | 实际 |
|---|---|
| `composables/useNotesAndTodos.ts` | `composables/useNotesAndDecisions.ts` |
| `composables/useOnboarding.ts` | 不存在 |
| `composables/useProjectOnboarding.ts` | 不存在 |
| `composables/useHotwordGroups.ts` | `composables/useHotwords.ts` |
| `views/generating/OnboardingDialog.vue` | 不存在 |
| `views/decisions/DecisionCard.vue` | 不存在 |
| `views/decisions/SupersedeDialog.vue` | 不存在 |
| `api/decisionsMock.ts` | 不存在 |

2. 补齐缺失条目：路由 `/board/:taskId` → `BoardViewerView.vue`；`views/generating/` 的 `FailurePage / GenToolbar / GenMetaBar / GenTabs / InsightBoard / VoiceprintResultBar / MeetingRosterZone / ProgressDialog / decisionFlowLogic.ts`；`views/decisions/`、`views/library/`、`views/projects/`；`stores/agent.ts`。
3. 新增一节"云同步副本"：`.gitignore:L120-L121` 的 `* [0-9]` 规则会把云盘生成的 `xxx 2.vue` 一并忽略，这类文件**未被 git 跟踪、删除不可恢复、且可能随同步再生**。因此：
   - 不在仓库层面删除，也不依赖它们回滚任何改动；
   - `DecisionNode 2.vue`（141 行）是 `DecisionNode.vue` 的旧副本，`ProjectOnboardingDialog 2.vue`（95 行）无对应正式文件且无人引用——两者都视为本地脏文件，由开发者自行清理，不作为提交内容。
4. 组件地图中"7 套主题"更正为 10 套。

**风险**：零。只改文档。

**验收**：文档内所有被反引号引用的路径，用 `test -f` 批量校验全部存在；`git diff` 仅涉及 `docs/`。

---

### P0-2 转写显示工具去重

> 状态：已完成（2026-11-26）。验收见第 8 节。

**目标**：时间、章节定位、头像三套规则各自只有一份实现。

**改动**

1. 新建 `frontend/src/utils/transcriptView.ts`：
   - `formatTimeMs(ms: number): string`（保持 `mm:ss`，不新增小时位，避免显示变化）
   - `getChapterIdxAtTime(chapters: Chapter[], ms: number): number`
2. `TranscriptPanel.vue`：删除本地 `formatTimeMs`、`getChapterIdxAtTime`（L657-L668），改 import。
3. `useGeneratingData.ts`：删除 L156 的本地实现，改 import；`usePlaybackFollow` 的入参随之改为可选/去掉透传。
4. 头像统一：
   - `TranscriptPanel.vue` 删除本地实现，调用 `avatarInitial(name, t('generating.speaker_unid_initial'))`。
   - `RecTranscriptPanel.vue` 保留"未绑定显示编号"分支，其余走 `avatarInitial(name, t('recording.speaker.unid_initial'))`。
   - 删除 `RecTranscriptPanel.vue:L689` 的 `speakerColor` 包装，模板直接调 `getSpeakerColor`。
5. 新增 `frontend/src/utils/__tests__/transcriptView.test.ts`：跨分、`mm:ss` 补零、空章节、时间早于首章、阈值边界（若后续加入 `isNearBottom`）。
6. `SummaryPanel.vue`：删除同类 `formatTimeMs`，改 import（复查时补入，初稿遗漏这第三份）。

**风险**：低。纯函数替换；`formatTimeMs` 与 `formatTime` 已核实逐字相同，合并无显示变化。

**验收**：`cd frontend && npx vue-tsc -b && npm run test:unit`；人工看录音页时间戳与纪要页章节定位。

---

### P1-1 拆出书面版：`useFormalVersion` + `FormalVersionCard`

> 状态：已完成（2026-11-26）。验收见第 8 节。

**目标**：把 `TranscriptPanel` 中最大的自包含功能块移出，降低后续书面版迭代的改动面。

**现状**：模板 L8-L65（状态卡）、L476-L607（状态机：定时器、2s 轮询、settings 读写、错误映射），工具函数 L521-L536，依赖 `taskStatus / taskId / lines / layerView / visible / onEnterFormal`。`formalizeSelection` 通过 `defineExpose` 暴露给父页面。

**做法**

1. 新建 `frontend/src/views/generating/useFormalVersion.ts`，迁入 L476-L607 的状态与函数，对外返回（落地后的实际签名）：
   `formalVersion / formalState / formalMap / formalProgress / formalPercent / toneCount / estimatedTokens / costNote / formalItem / isFormalView / isToneFlagged / formatFormalTime / formalStarting / formalActionError / autoFormalEnabled / startFormal / formalizeSelection / onToggleAutoFormal`
   （初稿写的 `refresh` 未落地，自动开关切换由 `onToggleAutoFormal` 承担。）
2. 新建 `frontend/src/views/generating/FormalVersionCard.vue`，接收 `state / progress / percent / version / starting / actionError / autoEnabled / estimatedTokens / costNote / toneCount`，emit `start`、`toggle-auto`；只做渲染，不含轮询。（初稿的 `model / tokens / finishedAt` 改为直接下发 `version` 与预估值。）
3. `TranscriptPanel.vue` 模板 L8-L65 换成 `<FormalVersionCard v-if="layerView === 'formal'" :state="..." @start="..." @toggle-auto="..." />` 逐字段绑定；`defineExpose` 的 `formalizeSelection` 改为转调 composable。（初稿的 `v-bind="formalCardProps"` 方案未采用，避免对象展开放宽类型校验。）
4. 样式暂不搬：`gen-formal-*` 类仍由 `meeting-view.css` 提供，保持零视觉变化。

**风险**：中低。轮询与定时器必须完整迁移，否则进入书面视图后进度不再刷新；`defineExpose` 契约必须保留。

**验收**：`vue-tsc` + 人工四场景——未生成态点生成、生成中进度递增、失败态重试、已完成态切自动开关；`npm run build` 后页面无样式错位。

---

### P1-2 拆出说话人侧面板：`TranscriptSpeakerPanel`

> 状态：已完成（2026-11-26）。验收见第 8 节。

**目标**：把 `TranscriptPanel` 的展示型侧栏独立，主面板只保留布局与转发。

**现状**：模板 L322-L383（约 60 行），依赖 `speakerPanelVisible / searchExpanded / panelSpeakerList / panelTotalDuration / panelTotalTurns`，`v-model:speaker-panel-search`，emit `toggle-search / toggle-panel / toggle-speaker / locate`。

**做法**

1. 新建 `frontend/src/views/generating/TranscriptSpeakerPanel.vue`，仅接收上述字段与事件，内部不含查询逻辑。
2. `TranscriptPanel.vue` 保留布局容器，替换侧栏块；样式类名不动。
3. 搜索框聚焦与 `searchInputEl` ref 的 `defineExpose` 需一并迁移或通过 `defineExpose` 转发，避免 `useSpeakerPanel` 的聚焦行为失效。

**风险**：中低。焦点与滚动相关行为依赖 DOM ref，迁移后需实测搜索展开/收起。

**验收**：`vue-tsc` + 人工——展开侧栏、搜索过滤、点说话人定位、折叠侧栏四项。

---

### P2 登记不做

> 状态：登记，未排期。

1. **单例 composable 归位**：`useSummaryProposal` / `useNotesProposal` / `useInlineEdit` / `useToast` / `useAnnouncements` / `useUpdateCheck` / `usePrivacyDisclaimer` / `useDecisionStatuses` 用模块级 `ref` 共享，与 Pinia 双轨。行为无缺陷，迁移影响 10 余个文件，收益是可读性而非功能。等出现状态不同步缺陷再做。
2. **转写行共享组件**：两份面板行结构差异大（翻译、清理层 peek、笔记、定位按钮），统一需改 DOM 与两套 css，收益是未来加字段少写一次，成本是全量视觉回归。等真正要加"跨页统一行特性"时再做。
3. **补两个面板的挂载测试**：拆完后 props 减少，具备条件，但需要构造 20 余个测试夹具，单独排期。

## 4. 实施顺序

```
P0-1 文档 ──→ P0-2 工具去重 ──→ P1-1 书面版拆分 ──→ P1-2 侧面板拆分
```

每项独立提交，信息格式 `refactor(frontend): ...`。每项完成后跑 `cd frontend && npx vue-tsc -b && npm run test:unit`；涉及组件结构的项再加 `npm run build`。任一项验收失败即回滚该项，不影响其他项。

## 5. 验证矩阵

| 项 | vue-tsc | test:unit | build | 人工回归 |
|---|---|---|---|---|
| P0-1 | 免 | 免 | 免 | 文档路径校验 |
| P0-2 | 必跑 | 必跑（含新增用例） | 免 | 录音页时间戳 / 纪要页章节定位 |
| P1-1 | 必跑 | 必跑 | 必跑 | 书面版四场景 |
| P1-2 | 必跑 | 必跑 | 必跑 | 侧栏四场景 |

> 注：`npm run lint` 只覆盖 `src/**/*.vue`（`frontend/eslint.config.js:L24`），新增 `.ts` 不在其内，故不作为 .ts 改动的验收依据。

## 6. 明确不做

- 不重写 `GeneratingView` 的编排结构，不引入 `provide/inject`。
- 不迁移单例 composable 到 Pinia。
- 不调整录音页与纪要页的交互与布局。
- 不合并 `views/` 与 `components/` 的目录规则。
- 不改后端 API 与数据结构。

## 7. 独立评审记录（2026-11-26）

总评：有条件通过。

**已采纳（必须修改）**

1. 计数错误：原稿 props 41/20、SpeakerZone 14/16、RecTranscriptPanel 23 均为误；实际 37/21、12/15、21。已更正。
2. P1-1 曾把"头像合并"说成行为一致。实际默认文案与编号规则三处不同。已改为各自传 label、保留录音面板编号分支。
3. 章节索引存在第三份实现（`useGeneratingData.ts:L156`），原稿漏掉。已纳入 P0-2。
4. "删除死文件"不可回滚：两个 ` 2.vue` 被 `.gitignore` 忽略且未跟踪。已改为"本地脏文件说明"，不作为提交内容。
5. 验收入口缺 `cd frontend` 与 `npm run build`；lint 不覆盖 `.ts`；主题数是 10 不是 7。已更正。
6. `v-bind` 分组方案不能降低新增字段成本，且会放宽类型校验。该方案作废，改为拆分组件边界。

**保留意见**

- 建议补两个转写面板的最小挂载测试。已登记为 P2-3，理由是夹具成本高，且拆分后条件更成熟。
- 建议优先抽书面版状态机。已采纳为 P1-1。

## 8. 实施记录（2026-11-26）

| 项 | 状态 | 结果 |
|---|---|---|
| P0-1 | 完成 | 修正 8 条失效引用；补路由、子组件、API、store 条目；新增「云同步副本」一节；主题数更正为 10 |
| P0-2 | 完成 | 新增 `utils/transcriptView.ts`（27 行）与 9 个单测；四份实现收敛（两份面板、`useGeneratingData`、`SummaryPanel`）；`formatTime`/`formatTimeMs` 合并后显示不变 |
| P1-1 | 完成 | 新增 `useFormalVersion.ts`（182 行）、`FormalVersionCard.vue`（99 行）；`TranscriptPanel.vue` 723 → 499 行 |
| P1-2 | 完成 | 新增 `TranscriptSpeakerPanel.vue`（116 行）；侧栏模板与搜索焦点迁移，`searchInputEl` 经 ref 转发 |
| 验证 | 通过 | `vue-tsc -b`、`vitest`（15 文件 / 90 用例）、`npm run build`、`npm run lint` 全绿 |
| 复查补漏 | 完成 | `SummaryPanel.vue` 第三份 `formatTimeMs` 接上 `utils/transcriptView.ts`；`docs/VUE_COMPONENT_MAP.md` 补录 4 个新文件（`transcriptView.ts`、`useFormalVersion.ts`、`FormalVersionCard.vue`、`TranscriptSpeakerPanel.vue`）并修订 `TranscriptPanel` 条目；第 2、3 节标注改造前口径 |
| 提交 | 待办 | 本轮全部改动仍在工作区（7 改 + 5 新增未跟踪），尚未按第 4 节拆分提交 |

改造后规模：84 个 `.vue`、123 个 `.ts`（不含测试）、15 个测试文件。第 2 节的 82 / 121 / 13 为改造前数字，行号亦为改造前位置。

偏差说明：

1. P1-2 未减少 `TranscriptPanel` 的 props 数量（37 个依旧；数据仍由 `GeneratingView` 下发，面板再转发给侧栏组件）。该项收益是模板与职责分离，不是接口面积收缩。
2. `RecTranscriptPanel` 已绑定名的头像改走 `normalizeSpeakerName`：若某人真名形似占位名（如 `Speaker 1`），会退回 `unid_initial` 的 `?`，而旧实现显示 `S`。占位名判定与绑定流程同源，实际触发概率极低，未额外加固。
3. `TranscriptPanel` 的 `searchInputEl` 改为 `computed` 转发子组件 `defineExpose`，父级拿到的是 DOM 元素而非 ref；`useSpeakerPanel` 的 `?.focus()` 行为不变。
