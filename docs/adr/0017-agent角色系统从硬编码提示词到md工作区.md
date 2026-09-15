---
title: "ADR-0017 Agent 角色系统：从硬编码提示词到 .md 工作区"
description: "将 AI 行为定义从 Python 字符串常量迁移到 .md 文件工作区，支持预定义角色开箱即用、用户 fork 自定义、场景间自由切换。"
tags: ["adr", "agent", "role", "prompt", "workspace"]
created_at: "2026-09-15"
updated_at: "2026-09-15"
version: "1.0.0"
author: "wangyongliang"
status: "proposed"
category: "architecture"
---

# ADR-0017 Agent 角色系统：从硬编码提示词到 .md 工作区

- 状态：Proposed
- 日期：2026-09-15
- 相关：`core/agent_workspace.py`（待建）、`app/routers/chat.py`、`core/summarize.py`、`docs/design/AGENT_ROLE_SYSTEM.md`

## 背景

当前系统的 AI 行为由 4 个 Python 字符串常量硬编码定义（`CHAT_SYSTEM_PROMPT`、`SYSTEM_PROMPT`、`TITLE_SYSTEM_PROMPT`、`SUMMARY_SYSTEM_PROMPT`），分散在 `app/routers/chat.py` 和 `core/summarize.py` 中。设置界面仅做只读展示，用户无法修改。

这带来三个问题：
1. **单一角色无法适应多场景**：会议纪要、深度分析、学习辅导等场景需要不同的 AI 人格和输出风格
2. **用户无法定制**：高级用户希望调整 AI 回复风格、输出模板，但提示词锁死在代码中
3. **开发者迭代成本高**：每次调整提示词需修改 Python 代码并重启服务

现代 Agent 工程化软件（Cursor、Qoder 等）已验证了「.md 文件定义 Agent 行为 + 渐进式加载」的模式。本项目已有 `project_index.py` 的关键词检索 + front matter 解析基础设施，具备复用条件。

## 选项

### 方案 A — 设置 UI 可编辑（保留硬编码架构）

在现有设置页面增加提示词编辑器，用户修改后写入 `settings.json`，Python 代码启动时读取。

- 优点：改动最小，不引入新概念
- 缺点：
  - 仍然是「一个提示词走天下」，无法按场景切换角色
  - `settings.json` 中嵌入大段 Markdown 可读性差
  - 无法按文件拆分（模板、规则、人格混在一起）
  - 不支持 fork/版本管理

### 方案 B — .md 工作区 + 角色系统（选定）

将 AI 行为定义外化为 `data/agent/_roles/` 目录下的 `.md` 文件集合。预定义角色内置于 `_builtin/`，用户通过 fork 创建自定义角色。会话/任务可绑定不同角色，系统按角色目录渐进式加载。

- 优点：
  - 预定义角色保底，零配置即可用
  - 用户可 fork + 编辑，定制无上限
  - 文件即配置，人类和 AI 均可阅读
  - 目录结构天然支持按场景分类
  - 复用现有 `project_index.py` 的检索基础设施
  - 硬编码常量保留为 fallback，向后兼容
- 缺点：
  - 新增 `core/agent_workspace.py` 模块（约 150 行）
  - 前端需新增角色选择器和角色管理界面
  - 需要处理 `.md` 文件编辑的安全性（路径遍历防护）

### 方案 C — 数据库存储 + 管理界面

角色定义存入数据库（SQLite），通过管理后台 CRUD 界面编辑。

- 优点：结构化查询、事务安全
- 缺点：
  - 过度工程化，角色定义本质是文本，不需要数据库
  - 无法被文件系统工具/编辑器直接编辑
  - 丧失了「.md 文件可被 AI 直接读取和索引」的核心优势
  - 增加部署复杂度

## 决定

选择 **方案 B**：.md 工作区 + 角色系统。

核心理由：
1. `.md` 文件同时承担「人类可读文档」和「Agent 配置」双重角色，与项目已有的文档驱动理念一致
2. 预定义角色 + fork 机制兼顾了零配置体验和定制自由度
3. 已有 `project_index.py` 基础设施可直接复用，实施成本低
4. 硬编码常量作为 fallback 保证了向后兼容，可渐进迁移

## 后果

### 正面

- 用户可在不同场景间切换角色（会议纪要 vs 深度分析 vs 学习辅导），AI 行为差异化可感知
- 高级用户可通过编辑 `.md` 文件完全定制 AI 行为，无需改代码
- 开发者调整提示词只需编辑 `.md` 文件，无需重启服务
- 为后续「角色市场」（用户间分享角色文件包）奠定基础

### 负面 / 代价

- 新增 `core/agent_workspace.py` 模块，增加代码维护量（约 150 行）
- 前端需新增角色选择器（AIPanel）和角色管理界面（SettingsView），约 2-3 天工作量
- 用户编辑 `.md` 可能导致 AI 行为异常，需提供「恢复默认」机制
- 需要处理 `.md` 文件编辑的安全性（防止路径遍历攻击）

### 后续需注意

- 预定义角色的 `.md` 内容需要经过充分调优，确保开箱即用的体验不低于当前硬编码版本
- fork 后原预定义角色更新时，需要版本对比机制提示用户
- 角色文件的 token 总量需要控制，避免 context window 溢出
- 实施分三阶段（文件化 → 角色切换 → 角色管理），每阶段可独立交付价值
- 详细设计见 [`docs/design/AGENT_ROLE_SYSTEM.md`](../design/AGENT_ROLE_SYSTEM.md)
