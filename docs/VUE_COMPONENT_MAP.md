---
title: "Vue 组件页面映射清单"
description: "列出所有 Vue 组件与页面/区域的对应关系，方便快速定位需要修改的文件。"
tags: ["vue", "frontend", "component_map", "ui"]
created_at: "2026-09-12"
updated_at: 2026-09-25
version: "1.7.0"
author: "wangyongliang"
status: "published"
category: "technical"
---

# Vue 组件页面映射清单

> 调整页面时，根据本文快速定位需要修改的 `.vue` 文件。
> 所有路径相对于 `frontend/src/`。

## 整体布局结构

```
┌───────────────────────────────────────────────────────┐
│  TopBar.vue              顶栏（所有页面共享）            │
├──────┬────────┬───────────────────────────┬───────────┤
│Activity│Sidebar │     主内容区               │ AIPanel.vue│
│Rail  │ .vue   │  (router-view 按路由切换)  │ AI 面板    │
│导航轨 │ 侧边栏  │                           │（所有页面共享│
├──────┴────────┴───────────────────────────┴───────────┤
│  底部状态栏 (App.vue 内联)                              │
└───────────────────────────────────────────────────────┘
```

## 一、路由页面（views/）

| 路由 | 文件 | 页面名称 | 说明 |
|------|------|----------|------|
| `/` | `views/StartView.vue` | 快速启动 | 首页，录音按钮 + 上传入口 |
| `/recording/:taskId?` | `views/RecordingView.vue` | 录音中 | 实时录音页：波形、实时转写、洞察台、底部控制栏 |
| `/meeting/:taskId` | `views/GeneratingView.vue` | 会议纪要 | 会议详情：原文/随记/纪要/行动项/洞察五 Tab（原「决策」Tab 更名）+ 说话人绑定 + 会后只读洞察台 |
| `/library` | `views/LibraryView.vue` | 会议库 | 全部会议列表，表格 + 搜索 + 筛选 + 分页 |
| `/projects` | `views/ProjectsView.vue` | 项目管理 | 项目列表与详情 |
| `/speakers` | `views/SpeakersView.vue` | 说话人管理 | 说话人列表 → 详情两态切换 |
| `/hotwords` | `views/HotwordsView.vue` | 热词管理 | 热词组 CRUD + 词条编辑 |
| `/settings` | `views/SettingsView.vue` | 设置 | API Key、模型选择、语言等配置项 |
| `/decisions` | `views/DecisionCenterView.vue` | 决策中心 | 跨会议全量决策：筛选（日期/知识库/状态/关键词）+ 补录 + 取代/撤销（REQ-DECISION-CENTER R3） |

## 二、全局布局组件（始终可见）

| 文件 | 位置 | 说明 |
|------|------|------|
| `components/layout/ActivityRail.vue` | 最左侧（52px） | 常驻全局导航轨：Sidebar 折叠按钮、4 个导航图标（会议库/项目/说话人/热词）、洞察台呼吸指示器、设置按钮（含版本号） |
| `components/layout/TopBar.vue` | 顶部 | 面包屑、全局搜索、主题切换、全屏、用户头像 |
| `components/layout/Sidebar.vue` | 左侧 | 导航菜单、最近任务列表、项目快捷入口 |
| `components/layout/AIPanel.vue` | 右侧 | AI 对话/上下文双 Tab + 多会话切换 + 洞察台呼吸灯指示 |
| `App.vue` | 根 | 布局框架、路由出口、全局 Toast、划词工具栏、底部状态栏 |

## 三、录音页子组件（views/recording/）

RecordingView 内部按职责拆分为以下子组件：

| 文件 | 对应区域 | 说明 |
|------|----------|------|
| `recording/RecControlBar.vue` | 底部控制栏 | 录音控制按钮（暂停/继续/停止、标记） |
| `recording/RecTranscriptPanel.vue` | 实时转写区 | 实时转写文本流 + 说话人标签 |
| `recording/RecInsightsPanel.vue` | 洞察台区 | 洞察台绘图面板（Mermaid 图 + G6 知识图谱双轨渲染，支持复制/重新生成/在对话中编辑） |
| `recording/RecNotesBar.vue` | 随记栏 | 录音中的快捷随记输入 |
| `recording/RecSpeakerBind.vue` | 说话人绑定 | 录音中说话人身份关联 |
| `recording/RecTimeline.vue` | 时间轴导航 | Canvas 说话人色带可视化 + 滑块拖拽定位 + 章节刻度线 + hover 时间标签 |
| `ai/AiInsightsSettings.vue` | ~~洞察台设置~~ | **已删除**（重构中移除，纯手动触发无需设置面板） |

## 四、会议纪要页（GeneratingView.vue）

GeneratingView 是会议纪要的顶层编排组件，自身包含以下内联区域，并将各 Tab 内容委托给子组件：

### 4.1 GeneratingView 自身内联区域

| 区域 | 说明 |
|------|------|
| 顶部工具栏（gen-toolbar） | 面包屑导航 + 复制/导出/全屏按钮 + 「更多」下拉菜单（编辑纪要/重新生成/重新转写/归档/删除） |
| 元信息行（gen-meta） | 时长、说话人数、日期（可点击改日期）、项目绑定芯片（下拉切换项目） |
| 说话人名单区（speaker-zone） | 各说话人名称 + 发言占比横条，按颜色区分 |
| Tab 切换栏（gen-tabs） | 原文/随记/纪要/行动项/洞察五 Tab + 音频播放控制条（播放/暂停/进度/倍速） |
| 章节导航条（chapter-overview） | 仅原文 Tab 可见：章节圆点导航 + 当前章节索引 + 原文显隐切换按钮 |
| 划词工具栏（SelectionToolbar） | 浮动选中条：引用到 AI / 改写 / 总结 / 提取待办 |
| 行间改写输入（InlineEditInput） | 划词改写后弹出的指令输入框（快捷指令 chips + 自定义指令） |

### 4.2 子组件（views/generating/）

| 文件 | 对应区域 | 说明 |
|------|----------|------|
| `generating/TranscriptPanel.vue` | 原文 Tab | 转写全文 + 章节分隔卡片 + 说话人侧面板 + 聚焦模式 + 播放跟随高亮 |
| `generating/SummaryPanel.vue` | 纪要 Tab | Markdown 纪要 + 章节回顾卡片 + 行动项入口 + 生成中状态展示 |
| `generating/NotesPanel.vue` | 随记 Tab | Markdown 编辑器 + 工具栏（加粗/斜体/代码/标题/列表/引用） |
| `generating/DecisionFlowPanel.vue` | 行动项 Tab（原「决策」Tab，2026-09-25 更名） | 行动项面板：点阵图进度可视化 + 文字摘要 + 添加按钮 + 已完成沉底分组；含结构化决策只读区（展示层剥除成对强调符号，RF-F1） |
| `recording/RecInsightsPanel.vue`（复用） | 洞察 Tab（会后只读态） | 纪要页以 `:readonly="true"` 复用洞察台面板：隐藏开关/频率/扩展控件、消息始终可见 + 「分析本场会议」补分析入口 + 会后徽标（REQ-INSIGHT-DECK-POSTMEETING R1） |
| `generating/DecisionNode.vue` | 行动项节点 | 单个行动项卡片：两行布局（标题 + 元信息）+ 左侧 40px rail 状态圆点 + 展开详情（why/how/outcome）+ 状态菜单 + 负责人轮转 |
| `decisions/DecisionCard.vue` | 决策中心卡片 | 单条决策：剥除符号后的纯文本展示（stripDecisionEmphasis）+ 来源会议跳转（dq 携带原始文本）+ pending/superseded/revoked 态 |
| `decisions/AddDecisionDialog.vue` | 决策中心·补录 | 手动补录决策（text 1..2000 前端前置校验 + 待确认开关） |
| `decisions/SupersedeDialog.vue` | 决策中心·取代 | 跨会议 supersede 选择：检索双命中原始/剥除文本，结果行剥除后展示 |
| `generating/GeneratingSpeakerZone.vue` | 说话人区（三态合并） | 只读名单 / 绑定提示 / 绑定完成三态一体，名字+占比条+身份关联横幅 + Teleport 下拉框（搜索/新建/键盘导航） |
| `generating/OnboardingDialog.vue` | 引导弹窗 | 首次进入时的说话人绑定功能演示动画 |
| `generating/ArchiveDialog.vue` | 归档弹窗 | 归档确认对话框 |
| `generating/DeleteDialog.vue` | 删除弹窗 | 删除会议确认对话框（含 ESC 快捷键标识） |
| `generating/ProjectOnboardingDialog.vue` | 知识库引导弹窗 | 知识库关联功能引导动画弹窗（空知识库 → 文档 + 纪要回写演示） |

## 五、Composable（composables/）

### 5.1 会议纪要页 Composable

GeneratingView 的业务逻辑拆分为以下 composable：

| 文件 | 职责 |
|------|------|
| `composables/useGeneratingData.ts` | 核心数据层：任务状态、章节、转写、元信息、Tab 切换、轮询、工具栏 |
| `composables/useSpeakerBinding.ts` | 说话人身份绑定：映射、下拉框、增量保存、确认/跳过 |
| `composables/useSpeakerPanel.ts` | 右侧面板：搜索、筛选、聚焦模式、上下条导航 |
| `composables/usePlaybackFollow.ts` | 播放跟随：播放进度 → 原文自动滚动定位 |
| `composables/useNotesAndTodos.ts` | 随记/决策 CRUD：自动保存、新增/删除/勾选、决策流状态同步 |
| `composables/useOnboarding.ts` | 引导弹窗：动画循环、localStorage 持久化 |

### 5.2 全局/跨页 Composable

| 文件 | 职责 |
|------|------|
| `composables/useAiChat.ts` | AI 对话逻辑：消息发送、流式响应、历史管理 |
| `composables/useAiCommandActions.ts` | AI 指令动作执行（引用/改写/总结等） |
| `composables/useAiCommands.ts` | AI 指令系统：指令定义、按状态过滤、面板状态 |
| `composables/useAiContext.ts` | AI 上下文数据源（对话/转写/纪要聚合，含原 useAiAnalysis 逻辑） |
| `composables/useAiGuidance.ts` | AI 引导面板：根据会议状态动态生成上下文引导建议 |
| `composables/useAiInsights.ts` | 洞察台引擎：消息管理、未读计数、手动分析、图交互状态 |
| `composables/useAnnouncements.ts` | 公告横幅：拉取/显示/关闭策略、登录状态联动 |
| `composables/useBlockEditor.ts` | Markdown 块级编辑逻辑（解析/AI 标记/diff） |
| `composables/useContainerSize.ts` | 容器宽度档位检测（ResizeObserver → 标准化 tier） |
| `composables/useDivider.ts` | 缝隙拉手拖拽：侧边栏/AI 面板宽度调整 |
| `composables/useEscClose.ts` | ESC 键关闭弹窗（比模板 @keydown.esc 更可靠） |
| `composables/useHotwordGroups.ts` | 热词分组管理：分组/词条 CRUD、AI 自动分组、搜索筛选 |
| `composables/useInlineEdit.ts` | 行间编辑：划词改写 → AI 改写 → diff 展示 → 采纳/拒绝 |
| `composables/useKeyboardShortcuts.ts` | 全局键盘快捷键（ESC/Cmd+B/Cmd+J/Cmd+K 等） |
| `composables/usePageBack.ts` | 页面返回：router.back() + ESC 键触发 + 兑底首页 |
| `composables/usePhilosophy.ts` | 价值主张管理：按页面/Tab 获取理念语录、状态栏文字 |
| `composables/usePolling.ts` | 轮询封装：定时拉取任务状态 |
| `composables/usePopMenu.ts` | 弹出菜单统一封装：智能定位/点击外部关闭/滚动跟随 |
| `composables/usePresenceDetection.ts` | 存在性检测：交互事件 + 页面可见性 → 存在性评分 → 心跳 |
| `composables/usePrivacyDisclaimer.ts` | 隐私免责声明确认状态（双层留痕：localStorage + 服务端） |
| `composables/useProjectOnboarding.ts` | 知识库关联引导弹窗：动画与展示控制 |
| `composables/useQuoteRef.ts` | 划词引用/改写状态管理 |
| `composables/useRecorder.ts` | 录音控制：API 调用封装（开始/暂停/停止） |
| `composables/useRecordingNotes.ts` | 录音随记持久化：localStorage + 笔记-转写行自动关联 |
| `composables/useSpeakerStats.ts` | 说话人统计：从任务列表聚合会议/发言/决策数据 |
| `composables/useToast.ts` | Toast 通知：全局轻量反馈（warn/success/error/info） |
| `composables/useTranslation.ts` | 实时翻译：启用/关闭、语言选择、译文映射、WebSocket 通信 |
| `composables/useWebSocket.ts` | 实时转写 WebSocket：连接/消息接收/说话人信息 |

## 六、AI 面板子组件（components/layout/ai/）

AIPanel 内部按职责拆分为以下子组件：

| 文件 | 对应区域 | 说明 |
|------|----------|------|
| `ai/AiSessionPopover.vue` | 会话切换 | 多 AI 对话会话切换（popover + 重命名/删除） |
| `ai/AiChatPanel.vue` | 对话 Tab | AI 对话交互面板 |
| `ai/AiContextPanel.vue` | 上下文 Tab | 上下文信息展示与注入 |

## 七、通用/共享组件（components/）

| 文件 | 使用场景 | 说明 |
|------|----------|------|
| `components/task/TaskCard.vue` | 侧边栏、会议库 | 单个任务卡片（状态、标题、时间、操作） |
| `components/task/TaskContextMenu.vue` | 侧边栏 | 任务右键上下文菜单（复制标题/归档/删除） |
| `components/task/TaskList.vue` | 侧边栏 | 任务列表（按时间分组） |
| `components/SelectionToolbar.vue` | 全局浮动 | 划词选中后弹出的操作条（引用到 AI / 改写 / 总结 / 提取待办） |
| `components/InlineEditInput.vue` | 纪要/随记 Tab | 行间改写指令输入框（快捷指令 chips + 自定义指令输入 + ESC 取消） |
| `components/MdBlockEditor.vue` | 纪要 Tab、随记 Tab | Markdown 块级编辑器（双击编辑、实时预览） |
| `components/modals/LoginModal.vue` | 全局弹窗 | 登录/注册弹窗 |
| `components/common/IconButton.vue` | 全局 | 带 label 的图标按钮（自动处理 title/aria-label/tooltip） |
| `components/common/ResponsiveButtonGroup.vue` | 工具栏 | 响应式按钮组（宽屏展开 / 窄屏折叠到更多菜单） |
| `components/common/DurationDial.vue` | 录音页 | 时长选择旋钮 |
| `components/common/PlayingEq.vue` | 顶栏、录音页 | 播放状态均衡器动画（3 条竖线跳动） |

## 八、前端状态管理（stores/）

基于 Vue 3 `defineStore` 的 Pinia 状态管理：

| 文件 | 职责 |
|------|------|
| `stores/task.ts` | 当前选中任务、任务列表状态 |
| `stores/realtime.ts` | 实时转写消息流、WebSocket 状态 |
| `stores/player.ts` | 音频播放进度、播放状态 |
| `stores/layout.ts` | 侧边栏/AI 面板展开收起、布局状态 |
| `stores/theme.ts` | 主题切换（亮/暗/跟随系统） |
| `stores/user.ts` | 当前登录用户信息 |
| `stores/aiSessions.ts` | AI 对话会话列表与活跃会话 |
| `stores/watermark.ts` | 水印氛围层开关与透明度偏好 |

## 九、API 层（api/）

前端与后端通信的封装层：

| 文件 | 职责 |
|------|------|
| `api/client.ts` | HTTP 客户端基础配置（拦截器、鉴权头） |
| `api/auth.ts` | 登录/注册/验证码 |
| `api/record.ts` | 录音控制（开始/暂停/停止） |
| `api/tasks.ts` | 转录任务 CRUD |
| `api/projects.ts` | 项目管理 |
| `api/speakers.ts` | 说话人管理 |
| `api/hotwords.ts` | 热词管理 |
| `api/notes.ts` | 随记/决策注入 |
| `api/storage.ts` | 存储管理（用量查询/磁盘清理） |
| `api/settings.ts` | 设置读写 |
| `api/chat.ts` | AI 对话 |
| `api/announcements.ts` | 公告/通知 |
| `api/usage.ts` | 用量查询 |
| `api/insights.ts` | 洞察台分析与消息持久化 |
| `api/voiceprint.ts` | 声纹相关 |
| `api/decisions.ts` | 决策中心 CRUD + 跨会议聚合（契约 API_CONTRACTS §12；status 单值过滤，多状态 fetchDecisionsMulti 拆分合并） |
| `api/decisionsMock.ts` | 决策 mock 通道（仅 VITE_DECISIONS_MOCK=1 启用，默认走真实接口） |
| `api/types.ts` | 共享 TypeScript 类型定义 |

## 十、样式文件（styles/ + 组件 scoped）

样式按「主题变量 → 基础/布局 → 功能域」分层组织，在 `main.ts` 中按固定顺序导入。所有颜色、字号、间距、圆角、阴影均通过 CSS 变量引用，禁止硬编码。

### 10.1 主题变量（themes/）

7 套主题共享同一组变量名（`--bg`、`--surface`、`--accent` 等），通过 `html[data-theme]` 选择器生效，默认主题由 `:root` 提供。

| 文件 | 主题名称 | 说明 |
|------|----------|------|
| `themes/default.css` | 默认 | 蓝色主色调，亮色基础 |
| `themes/dark.css` | 夜色 | 深色模式 |
| `themes/warm.css` | 暖阳 | 珊瑚/橙色暖调 |
| `themes/forest.css` | 森林 | 深绿色调 |
| `themes/ocean.css` | 海洋 | 深青/蓝色调 |
| `themes/lavender.css` | 薰衣草 | 柔和紫色调 |
| `themes/rose.css` | 玫瑰 | 粉红色调 |

### 10.2 基础与布局

| 文件 | 说明 |
|------|------|
| `base.css` | 全局 reset、字体、滚动条、`prefers-reduced-motion` 减弱动效、全局 tooltip DOM、Z-index 阶梯 |
| `layout.css` | 三栏 Grid 框架（`.frame` → `.body` → `.sidebar/.main/.ai`）、分隔缝拖拽态、水印光晕层 |
| `components.css` | 通用原子类：`.btn`、`.panel`、`.tabs`、`.progress-bar`、`.pipe`、`.summary-content`、`.inline-confirm` |

### 10.3 功能域样式

| 文件 | 对应页面/区域 | 说明 |
|------|--------------|------|
| `topbar.css` | 顶栏 | 面包屑、全局搜索、主题切换、全屏、用户头像 |
| `sidebar.css` | 侧边栏 | 导航菜单、时间轴、折叠态、窄屏适配、主动 AI 指示器 |
| `ai-panel.css` | AI 面板 | AI 对话/上下文双 Tab + 多会话切换整体样式 |
| `ai-canvas.css` | AI 对话画布 | 消息气泡、Markdown 渲染、代码块、内联确认 |
| `recording-view.css` | 录音视图 | 转写流、实时总结面板、波形动画、确认弹窗、内嵌笔记 |
| `activity-rail.css` | 导航轨 | 常驻全局导航轨布局、Slack 风格按钮高亮、洞察台呼吸光晕与心跳脉冲动画 |
| `recording.css` | 录音页随记栏 | 全宽随记输入栏 |
| `speakers.css` | 说话人管理 | 右侧面板、聚焦模式、说话人列表 |
| `meeting-view.css` | 会议纪要页 | 面包屑、章节导航、说话人名单、Tab 切换、音频播放控制条 |
| `notes-editor.css` | 随记/纪要编辑 + 决策流 | 逐块 Markdown 编辑、浮动操作条、AI 引用/Diff；决策流方案 B 样式（`.db-*`：rail 轨道、点阵图、两行卡片、焦点光晕） |
| `summary-panel.css` | 纪要面板增强 | 章节回顾卡片、行动项入口 |
| `hotwords.css` | 热词管理 | 热词组 CRUD、词条编辑、窄屏适配 |
| `start-page.css` | 首页 | 录音按钮、上传入口、快速启动布局 |
| `auth.css` | 登录/注册 | 登录弹窗、注册表单、水印层 |
| `update-panel.css` | 版本更新 | 更新日志、版本对比面板 |

### 10.4 组件内 scoped 样式

以下 Vue 组件在 `<style scoped>` 中包含组件级样式（未提取到外部 CSS 文件）：

| 文件 | 样式内容 |
|------|----------|
| `components/common/IconButton.vue` | `.icon-btn` 图标按钮定位与交互态 |
| `components/common/DurationDial.vue` | `.dur-dial` 时长选择旋钮 |
| `components/common/PlayingEq.vue` | `.playing-eq` 播放均衡器动画 |
| `components/common/ResponsiveButtonGroup.vue` | `.responsive-btn-group` 响应式折叠 |
| `components/layout/AIPanel.vue` | `.ai-welcome` 欢迎页与空状态提示 |
| `views/RecordingView.vue` | 仅注释（转写行气泡样式已迁移至 `recording-view.css`） |
| `views/LibraryView.vue` | `.lib-page` 会议库列表页 |
| `views/ProjectsView.vue` | `.proj-create` 项目创建表单 |
| `views/SpeakersView.vue` | `.spk-create` 说话人创建表单 |
| `views/SettingsView.vue` | `.settings-section` 设置分区 |
| `views/generating/ArchiveDialog.vue` | `.archive-dialog-overlay` 归档弹窗 |

## 十一、快速定位指南

按你想修改的内容，直接打开对应文件：

| 想改什么 | 打开哪个文件 |
|----------|-------------|
| **首页** |
| 首页布局/录音入口 | [StartView.vue](../frontend/src/views/StartView.vue) |
| **录音页** |
| 录音页整体布局 | [RecordingView.vue](../frontend/src/views/RecordingView.vue) |
| 录音页 — 底部控制栏 | [RecControlBar.vue](../frontend/src/views/recording/RecControlBar.vue) |
| 录音页 — 实时转写区 | [RecTranscriptPanel.vue](../frontend/src/views/recording/RecTranscriptPanel.vue) |
| 录音页 — 洞察台区 | [RecInsightsPanel.vue](../frontend/src/views/recording/RecInsightsPanel.vue) |
| 录音页 — 随记栏 | [RecNotesBar.vue](../frontend/src/views/recording/RecNotesBar.vue) |
| 录音页 — 说话人绑定 | [RecSpeakerBind.vue](../frontend/src/views/recording/RecSpeakerBind.vue) |
| 录音页 — 洞察台设置 | ~~AiInsightsSettings.vue~~ **已删除** |
| 录音采集逻辑 | [useRecorder.ts](../frontend/src/composables/useRecorder.ts) |
| **会议纪要页** |
| 会议纪要 — 原文区域 | [TranscriptPanel.vue](../frontend/src/views/generating/TranscriptPanel.vue) |
| 会议纪要 — 纪要区域 | [SummaryPanel.vue](../frontend/src/views/generating/SummaryPanel.vue) |
| 会议纪要 — 随记区域 | [NotesPanel.vue](../frontend/src/views/generating/NotesPanel.vue) |
| 会议纪要 — 行动项区域（原决策流） | [DecisionFlowPanel.vue](../frontend/src/views/generating/DecisionFlowPanel.vue) |
| 会议纪要 — 决策节点卡片 | [DecisionNode.vue](../frontend/src/views/generating/DecisionNode.vue) |
| 会议纪要 — 说话人区（名单/绑定） | [GeneratingSpeakerZone.vue](../frontend/src/views/generating/GeneratingSpeakerZone.vue) |
| 会议纪要 — 工具栏/面包屑/Tab 切换 | [GeneratingView.vue](../frontend/src/views/GeneratingView.vue) |
| 会议纪要 — 业务逻辑（数据/轮询） | [useGeneratingData.ts](../frontend/src/composables/useGeneratingData.ts) |
| 会议纪要 — 说话人绑定逻辑 | [useSpeakerBinding.ts](../frontend/src/composables/useSpeakerBinding.ts) |
| 会议纪要 — 播放跟随逻辑 | [usePlaybackFollow.ts](../frontend/src/composables/usePlaybackFollow.ts) |
| **AI 面板** |
| AI 面板整体 | [AIPanel.vue](../frontend/src/components/layout/AIPanel.vue) |
| AI 面板 — 对话 Tab | [AiChatPanel.vue](../frontend/src/components/layout/ai/AiChatPanel.vue) |
| AI 面板 — 上下文 Tab | [AiContextPanel.vue](../frontend/src/components/layout/ai/AiContextPanel.vue) |
| AI 面板 — 会话切换 | [AiSessionPopover.vue](../frontend/src/components/layout/ai/AiSessionPopover.vue) |
| AI 对话逻辑 | [useAiChat.ts](../frontend/src/composables/useAiChat.ts) |
| AI 上下文逻辑（含原分析逻辑） | [useAiContext.ts](../frontend/src/composables/useAiContext.ts) |
| AI 指令系统 | [useAiCommands.ts](../frontend/src/composables/useAiCommands.ts) |
| 洞察台引擎 | [useAiInsights.ts](../frontend/src/composables/useAiInsights.ts) |
| AI 引导建议 | [useAiGuidance.ts](../frontend/src/composables/useAiGuidance.ts) |
| **其他页面** |
| 会议列表页 | [LibraryView.vue](../frontend/src/views/LibraryView.vue) |
| 项目管理页 | [ProjectsView.vue](../frontend/src/views/ProjectsView.vue) |
| 说话人管理页 | [SpeakersView.vue](../frontend/src/views/SpeakersView.vue) |
| 热词管理页 | [HotwordsView.vue](../frontend/src/views/HotwordsView.vue) |
| 设置页 | [SettingsView.vue](../frontend/src/views/SettingsView.vue) |
| **全局组件** |
| 导航轨 | [ActivityRail.vue](../frontend/src/components/layout/ActivityRail.vue) |
| 顶栏 | [TopBar.vue](../frontend/src/components/layout/TopBar.vue) |
| 侧边栏 | [Sidebar.vue](../frontend/src/components/layout/Sidebar.vue) |
| 登录弹窗 | [LoginModal.vue](../frontend/src/components/modals/LoginModal.vue) |
| 划词工具栏 | [SelectionToolbar.vue](../frontend/src/components/SelectionToolbar.vue) |
| 行间改写输入 | [InlineEditInput.vue](../frontend/src/components/InlineEditInput.vue) |
| 任务右键菜单 | [TaskContextMenu.vue](../frontend/src/components/task/TaskContextMenu.vue) |
| **样式文件** |
| 样式入口与导入顺序 | [main.ts](../frontend/src/main.ts) |
| 主题变量文件 | [styles/themes/](../frontend/src/styles/themes/) |
| 基础与布局样式 | [styles/base.css](../frontend/src/styles/base.css)、[layout.css](../frontend/src/styles/layout.css) |
| 通用组件样式 | [styles/components.css](../frontend/src/styles/components.css) |
| 功能域样式文件 | [styles/](../frontend/src/styles/) |
| **基础设施** |
| 路由配置 | [router/index.ts](../frontend/src/router/index.ts) |
| 状态管理（Pinia stores） | [stores/](../frontend/src/stores/) |
| API 请求层 | [api/](../frontend/src/api/) |
| 国际化配置 | [i18n/index.ts](../frontend/src/i18n/index.ts) |
| 工具函数 | [utils/](../frontend/src/utils/)（platform / sanitize / search / speakerColors / decisionText 决策文本展示剥除） |
