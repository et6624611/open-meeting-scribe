---
title: "Vue 组件页面映射清单"
description: "列出所有 Vue 组件与页面/区域的对应关系，方便快速定位需要修改的文件。"
tags: ["vue", "frontend", "component_map", "ui"]
created_at: "2026-09-12"
updated_at: "2026-09-13"
version: "1.4.1"
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
| `/recording/:taskId?` | `views/RecordingView.vue` | 录音中 | 实时录音页：波形、实时转写、AI 洞察、底部控制栏 |
| `/meeting/:taskId` | `views/GeneratingView.vue` | 会议纪要 | 会议详情：原文/纪要/随记/待办四 Tab + 说话人绑定 |
| `/library` | `views/LibraryView.vue` | 会议库 | 全部会议列表，表格 + 搜索 + 筛选 + 分页 |
| `/projects` | `views/ProjectsView.vue` | 项目管理 | 项目列表与详情 |
| `/speakers` | `views/SpeakersView.vue` | 说话人管理 | 说话人列表 → 详情两态切换 |
| `/hotwords` | `views/HotwordsView.vue` | 热词管理 | 热词组 CRUD + 词条编辑 |
| `/settings` | `views/SettingsView.vue` | 设置 | API Key、模型选择、语言等配置项 |

## 二、全局布局组件（始终可见）

| 文件 | 位置 | 说明 |
|------|------|------|
| `components/layout/ActivityRail.vue` | 最左侧（52px） | 常驻全局导航轨：Sidebar 折叠按钮、4 个导航图标（会议库/项目/说话人/热词）、AI 洞察呼吸指示器、设置按钮（含版本号） |
| `components/layout/TopBar.vue` | 顶部 | 面包屑、全局搜索、主题切换、全屏、用户头像 |
| `components/layout/Sidebar.vue` | 左侧 | 导航菜单、最近任务列表、项目快捷入口 |
| `components/layout/AIPanel.vue` | 右侧 | AI 对话/分析/上下文三 Tab + 洞察呼吸灯指示 |
| `App.vue` | 根 | 布局框架、路由出口、全局 Toast、划词工具栏、底部状态栏 |

## 三、录音页子组件（views/recording/）

RecordingView 内部按职责拆分为以下子组件：

| 文件 | 对应区域 | 说明 |
|------|----------|------|
| `recording/RecControlBar.vue` | 底部控制栏 | 录音控制按钮（暂停/继续/停止、标记） |
| `recording/RecTranscriptPanel.vue` | 实时转写区 | 实时转写文本流 + 说话人标签 |
| `recording/RecInsightsPanel.vue` | AI 洞察区 | AI 实时洞察面板（上下文关联/盲点揭示/共识提炼） |
| `recording/RecNotesBar.vue` | 随记栏 | 录音中的快捷随记输入 |
| `recording/RecSpeakerBind.vue` | 说话人绑定 | 录音中说话人身份关联 |
| `recording/RecTimeline.vue` | 时间轴导航 | Canvas 说话人色带可视化 + 滑块拖拽定位 + 章节刻度线 + hover 时间标签 |
| `ai/AiInsightsSettings.vue` | AI 洞察设置 | AI 洞察功能开关与配置（文件位于 `components/layout/ai/`，由 RecInsightsPanel 引用） |

## 四、会议纪要页（GeneratingView.vue）

GeneratingView 是会议纪要的顶层编排组件，自身包含以下内联区域，并将各 Tab 内容委托给子组件：

### 4.1 GeneratingView 自身内联区域

| 区域 | 说明 |
|------|------|
| 顶部工具栏（gen-toolbar） | 面包屑导航 + 复制/导出/全屏按钮 + 「更多」下拉菜单（编辑纪要/重新生成/重新转写/归档/删除） |
| 元信息行（gen-meta） | 时长、说话人数、日期（可点击改日期）、项目绑定芯片（下拉切换项目） |
| 说话人名单区（speaker-zone） | 各说话人名称 + 发言占比横条，按颜色区分 |
| Tab 切换栏（gen-tabs） | 原文/纪要/随记/待办四 Tab + 音频播放控制条（播放/暂停/进度/倍速） |
| 章节导航条（chapter-overview） | 仅原文 Tab 可见：章节圆点导航 + 当前章节索引 + 原文显隐切换按钮 |
| 划词工具栏（SelectionToolbar） | 浮动选中条：引用到 AI / 改写 / 总结 / 提取待办 |

### 4.2 子组件（views/generating/）

| 文件 | 对应区域 | 说明 |
|------|----------|------|
| `generating/TranscriptPanel.vue` | 原文 Tab | 转写全文 + 章节分隔卡片 + 说话人侧面板 + 聚焦模式 + 播放跟随高亮 |
| `generating/SummaryPanel.vue` | 纪要 Tab | Markdown 纪要 + 章节回顾卡片 + 行动项入口 + 生成中状态展示 |
| `generating/NotesPanel.vue` | 随记 Tab | Markdown 编辑器 + 工具栏（加粗/斜体/代码/标题/列表/引用） |
| `generating/TodosPanel.vue` | 待办 Tab | 待办列表 + 勾选/删除/新增表单 + 定位原文来源 |
| `generating/GeneratingSpeakerZone.vue` | 说话人区（三态合并） | 只读名单 / 绑定提示 / 绑定完成三态一体，名字+占比条+身份关联横幅 + Teleport 下拉框（搜索/新建/键盘导航） |
| `generating/OnboardingDialog.vue` | 引导弹窗 | 首次进入时的说话人绑定功能演示动画 |
| `generating/ArchiveDialog.vue` | 归档弹窗 | 归档确认对话框 |
| `generating/DeleteDialog.vue` | 删除弹窗 | 删除会议确认对话框（含 ESC 快捷键标识） |
| `generating/ProjectOnboardingDialog.vue` | 知识库引导弹窗 | 知识库关联功能引导动画弹窗（空知识库 → 文档 + 纪要回写演示） |

## 五、会议纪要页 Composable（composables/）

GeneratingView 的业务逻辑拆分为以下 composable：

| 文件 | 职责 |
|------|------|
| `composables/useGeneratingData.ts` | 核心数据层：任务状态、章节、转写、元信息、Tab 切换、轮询、工具栏 |
| `composables/useSpeakerBinding.ts` | 说话人身份绑定：映射、下拉框、增量保存、确认/跳过 |
| `composables/useSpeakerPanel.ts` | 右侧面板：搜索、筛选、聚焦模式、上下条导航 |
| `composables/usePlaybackFollow.ts` | 播放跟随：播放进度 → 原文自动滚动定位 |
| `composables/useNotesAndTodos.ts` | 随记/待办 CRUD：自动保存、新增/删除/勾选 |
| `composables/useOnboarding.ts` | 引导弹窗：动画循环、localStorage 持久化 |

## 六、AI 面板子组件（components/layout/ai/）

AIPanel 内部按职责拆分为以下子组件：

| 文件 | 对应区域 | 说明 |
|------|----------|------|
| `ai/AiSessionTabs.vue` | Tab 栏 | AI 对话/分析/上下文三 Tab 切换 |
| `ai/AiChatPanel.vue` | 对话 Tab | AI 对话交互面板 |
| `ai/AiContextPanel.vue` | 上下文 Tab | 上下文信息展示与注入 |

## 七、通用/共享组件（components/）

| 文件 | 使用场景 | 说明 |
|------|----------|------|
| `components/task/TaskCard.vue` | 侧边栏、会议库 | 单个任务卡片（状态、标题、时间、操作） |
| `components/task/TaskList.vue` | 侧边栏 | 任务列表（按时间分组） |
| `components/SelectionToolbar.vue` | 全局浮动 | 划词选中后弹出的操作条（引用到 AI / 改写 / 总结 / 提取待办） |
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
| `api/notes.ts` | 随记/待办 |
| `api/settings.ts` | 设置读写 |
| `api/chat.ts` | AI 对话 |
| `api/announcements.ts` | 公告/通知 |
| `api/usage.ts` | 用量查询 |
| `api/insights.ts` | AI 洞察分析与消息持久化 |
| `api/voiceprint.ts` | 声纹相关 |
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
| `ai-panel.css` | AI 面板 | AI 对话/分析/上下文三 Tab 整体样式 |
| `ai-canvas.css` | AI 对话画布 | 消息气泡、Markdown 渲染、代码块、内联确认 |
| `recording-view.css` | 录音视图 | 转写流、实时总结面板、波形动画、确认弹窗、内嵌笔记 |
| `activity-rail.css` | 导航轨 | 常驻全局导航轨布局、Slack 风格按钮高亮、AI 洞察呼吸光晕与心跳脉冲动画 |
| `recording.css` | 录音页随记栏 | 全宽随记输入栏 |
| `speakers.css` | 说话人管理 | 右侧面板、聚焦模式、说话人列表 |
| `meeting-view.css` | 会议纪要页 | 面包屑、章节导航、说话人名单、Tab 切换、音频播放控制条 |
| `notes-editor.css` | 随记/纪要编辑 | 逐块 Markdown 编辑、浮动操作条、AI 引用/Diff |
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
| 录音页 — AI 洞察区 | [RecInsightsPanel.vue](../frontend/src/views/recording/RecInsightsPanel.vue) |
| 录音页 — 随记栏 | [RecNotesBar.vue](../frontend/src/views/recording/RecNotesBar.vue) |
| 录音页 — 说话人绑定 | [RecSpeakerBind.vue](../frontend/src/views/recording/RecSpeakerBind.vue) |
| 录音页 — AI 洞察设置 | [AiInsightsSettings.vue](../frontend/src/components/layout/ai/AiInsightsSettings.vue) |
| 录音采集逻辑 | [useRecorder.ts](../frontend/src/composables/useRecorder.ts) |
| **会议纪要页** |
| 会议纪要 — 原文区域 | [TranscriptPanel.vue](../frontend/src/views/generating/TranscriptPanel.vue) |
| 会议纪要 — 纪要区域 | [SummaryPanel.vue](../frontend/src/views/generating/SummaryPanel.vue) |
| 会议纪要 — 随记区域 | [NotesPanel.vue](../frontend/src/views/generating/NotesPanel.vue) |
| 会议纪要 — 待办区域 | [TodosPanel.vue](../frontend/src/views/generating/TodosPanel.vue) |
| 会议纪要 — 说话人区（名单/绑定） | [GeneratingSpeakerZone.vue](../frontend/src/views/generating/GeneratingSpeakerZone.vue) |
| 会议纪要 — 工具栏/面包屑/Tab 切换 | [GeneratingView.vue](../frontend/src/views/GeneratingView.vue) |
| 会议纪要 — 业务逻辑（数据/轮询） | [useGeneratingData.ts](../frontend/src/composables/useGeneratingData.ts) |
| 会议纪要 — 说话人绑定逻辑 | [useSpeakerBinding.ts](../frontend/src/composables/useSpeakerBinding.ts) |
| 会议纪要 — 播放跟随逻辑 | [usePlaybackFollow.ts](../frontend/src/composables/usePlaybackFollow.ts) |
| **AI 面板** |
| AI 面板整体 | [AIPanel.vue](../frontend/src/components/layout/AIPanel.vue) |
| AI 面板 — 对话 Tab | [AiChatPanel.vue](../frontend/src/components/layout/ai/AiChatPanel.vue) |
| AI 面板 — 分析 Tab | [AiAnalysisPanel.vue](../frontend/src/components/layout/ai/AiAnalysisPanel.vue) |
| AI 面板 — 上下文 Tab | [AiContextPanel.vue](../frontend/src/components/layout/ai/AiContextPanel.vue) |
| AI 面板 — Tab 切换 | [AiSessionTabs.vue](../frontend/src/components/layout/ai/AiSessionTabs.vue) |
| AI 对话逻辑 | [useAiChat.ts](../frontend/src/composables/useAiChat.ts) |
| AI 分析逻辑 | [useAiAnalysis.ts](../frontend/src/composables/useAiAnalysis.ts) |
| AI 上下文逻辑 | [useAiContext.ts](../frontend/src/composables/useAiContext.ts) |
| AI 命令动作 | [useAiCommandActions.ts](../frontend/src/composables/useAiCommandActions.ts) |
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
