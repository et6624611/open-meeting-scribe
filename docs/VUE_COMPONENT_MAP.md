---
title: "Vue 组件页面映射清单"
description: "列出所有 Vue 组件与页面/区域的对应关系，方便快速定位需要修改的文件。"
tags: ["vue", "frontend", "component_map", "ui"]
created_at: "2026-09-12"
updated_at: "2026-09-12"
version: "1.0.0"
author: "wangyongliang"
status: "published"
category: "technical"
---

# Vue 组件页面映射清单

> 调整页面时，根据本文快速定位需要修改的 `.vue` 文件。
> 所有路径相对于 `frontend/src/`。

## 整体布局结构

```
┌──────────────────────────────────────────────────┐
│  TopBar.vue              顶栏（所有页面共享）       │
├────────┬───────────────────────────┬──────────────┤
│Sidebar │     主内容区               │  AIPanel.vue │
│ .vue   │  (router-view 按路由切换)  │  AI 面板     │
│ 侧边栏  │                           │ （所有页面共享）│
├────────┴───────────────────────────┴──────────────┤
│  底部状态栏 (App.vue 内联)                          │
└──────────────────────────────────────────────────┘
```

## 一、路由页面（views/）

| 路由 | 文件 | 页面名称 | 说明 |
|------|------|----------|------|
| `/` | `views/StartView.vue` | 快速启动 | 首页，录音按钮 + 上传入口 |
| `/recording/:taskId?` | `views/RecordingView.vue` | 录音中 | 实时录音页：波形、实时转写、实时总结、底部控制栏 |
| `/meeting/:taskId` | `views/GeneratingView.vue` | 会议纪要 | 会议详情：原文/纪要/随记/待办四 Tab + 说话人绑定 |
| `/library` | `views/LibraryView.vue` | 会议库 | 全部会议列表，表格 + 搜索 + 筛选 + 分页 |
| `/projects` | `views/ProjectsView.vue` | 项目管理 | 项目列表与详情 |
| `/speakers` | `views/SpeakersView.vue` | 说话人管理 | 说话人列表 → 详情两态切换 |
| `/hotwords` | `views/HotwordsView.vue` | 热词管理 | 热词组 CRUD + 词条编辑 |
| `/settings` | `views/SettingsView.vue` | 设置 | API Key、模型选择、语言等配置项 |

## 二、全局布局组件（始终可见）

| 文件 | 位置 | 说明 |
|------|------|------|
| `components/layout/TopBar.vue` | 顶部 | 面包屑、全局搜索、主题切换、全屏、用户头像 |
| `components/layout/Sidebar.vue` | 左侧 | 导航菜单、最近任务列表、项目快捷入口 |
| `components/layout/AIPanel.vue` | 右侧 | AI 对话/分析/上下文三 Tab + 主动 AI 设置 |
| `App.vue` | 根 | 布局框架、路由出口、全局 Toast、划词工具栏、底部状态栏 |

## 三、会议纪要页子组件（views/generating/）

GeneratingView 内部按职责拆分为以下子组件：

| 文件 | 对应区域 | 说明 |
|------|----------|------|
| `generating/TranscriptPanel.vue` | 原文 Tab | 转写全文 + 章节分隔卡片 + 说话人侧面板 + 聚焦模式 |
| `generating/SummaryPanel.vue` | 纪要 Tab | Markdown 纪要 + 章节回顾卡片 + 行动项入口 |
| `generating/NotesPanel.vue` | 随记 Tab | Markdown 编辑器 + 工具栏（加粗/斜体/代码/标题/列表/引用） |
| `generating/TodosPanel.vue` | 待办 Tab | 待办列表 + 勾选/删除/新增表单 |
| `generating/GeneratingSpeakerBar.vue` | 说话人绑定条 | 身份关联横幅 + Teleport 下拉框（搜索/新建/键盘导航） |
| `generating/OnboardingDialog.vue` | 引导弹窗 | 首次进入时的说话人绑定功能演示动画 |
| `generating/ArchiveDialog.vue` | 归档弹窗 | 归档确认对话框 |

## 四、会议纪要页 Composable（composables/）

GeneratingView 的业务逻辑拆分为以下 composable：

| 文件 | 职责 |
|------|------|
| `composables/useGeneratingData.ts` | 核心数据层：任务状态、章节、转写、元信息、Tab 切换、轮询、工具栏 |
| `composables/useSpeakerBinding.ts` | 说话人身份绑定：映射、下拉框、增量保存、确认/跳过 |
| `composables/useSpeakerPanel.ts` | 右侧面板：搜索、筛选、聚焦模式、上下条导航 |
| `composables/usePlaybackFollow.ts` | 播放跟随：播放进度 → 原文自动滚动定位 |
| `composables/useNotesAndTodos.ts` | 随记/待办 CRUD：自动保存、新增/删除/勾选 |
| `composables/useOnboarding.ts` | 引导弹窗：动画循环、localStorage 持久化 |

## 五、通用/共享组件（components/）

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

## 六、快速定位指南

按你想修改的内容，直接打开对应文件：

| 想改什么 | 打开哪个文件 |
|----------|-------------|
| 首页布局/录音入口 | [StartView.vue](../frontend/src/views/StartView.vue) |
| 录音页波形/控制栏 | [RecordingView.vue](../frontend/src/views/RecordingView.vue) |
| 会议纪要 — 原文区域 | [TranscriptPanel.vue](../frontend/src/views/generating/TranscriptPanel.vue) |
| 会议纪要 — 纪要区域 | [SummaryPanel.vue](../frontend/src/views/generating/SummaryPanel.vue) |
| 会议纪要 — 随记区域 | [NotesPanel.vue](../frontend/src/views/generating/NotesPanel.vue) |
| 会议纪要 — 待办区域 | [TodosPanel.vue](../frontend/src/views/generating/TodosPanel.vue) |
| 会议纪要 — 说话人绑定条 | [GeneratingSpeakerBar.vue](../frontend/src/views/generating/GeneratingSpeakerBar.vue) |
| 会议纪要 — 工具栏/面包屑/Tab 切换 | [GeneratingView.vue](../frontend/src/views/GeneratingView.vue) |
| 会议纪要 — 业务逻辑（数据/轮询） | [useGeneratingData.ts](../frontend/src/composables/useGeneratingData.ts) |
| 会议纪要 — 说话人绑定逻辑 | [useSpeakerBinding.ts](../frontend/src/composables/useSpeakerBinding.ts) |
| 会议纪要 — 播放跟随逻辑 | [usePlaybackFollow.ts](../frontend/src/composables/usePlaybackFollow.ts) |
| 会议列表页 | [LibraryView.vue](../frontend/src/views/LibraryView.vue) |
| 项目管理页 | [ProjectsView.vue](../frontend/src/views/ProjectsView.vue) |
| 说话人管理页 | [SpeakersView.vue](../frontend/src/views/SpeakersView.vue) |
| 热词管理页 | [HotwordsView.vue](../frontend/src/views/HotwordsView.vue) |
| 设置页 | [SettingsView.vue](../frontend/src/views/SettingsView.vue) |
| 顶栏 | [TopBar.vue](../frontend/src/components/layout/TopBar.vue) |
| 侧边栏 | [Sidebar.vue](../frontend/src/components/layout/Sidebar.vue) |
| AI 面板 | [AIPanel.vue](../frontend/src/components/layout/AIPanel.vue) |
| 登录弹窗 | [LoginModal.vue](../frontend/src/components/modals/LoginModal.vue) |
| 划词工具栏 | [SelectionToolbar.vue](../frontend/src/components/SelectionToolbar.vue) |
| 路由配置 | [router/index.ts](../frontend/src/router/index.ts) |
