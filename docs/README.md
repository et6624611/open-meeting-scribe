---
title: docs 目录导航
description: Open Meeting Scribe 文档中心索引，说明 docs/ 下各文件的定位、存储内容与「单一事实源」归属，帮助新人与 AI 快速定位该改哪份文档。
tags: ["docs", "index", "navigation", "single-source-of-truth"]
created_at: "2026-09-09"
updated_at: "2026-09-15"
version: "1.1.0"
author: "wangyongliang"
status: "published"
category: "documentation"
---

# docs — 文档目录导航

> 本目录是项目的**文档中心**。核心原则是「单一事实源」：每类内容只有一份权威文档，改哪、不改哪有明确归属。

## 一、按内容类型速查（改哪份文档）

| 你要改 / 查的内容 | 唯一文档 | 定位 |
|------|----------|------|
| 产品稳态需求、目标用户、核心场景、产品定位 | [`PRD.md`](PRD.md) | 版本无关的**稳态需求**，随产品演进原地更新 |
| 版本主线 / 里程碑（各版本交付什么） | [`ROADMAP.md`](ROADMAP.md) | 版本路线，不含细碎条目 |
| 零散缺陷、体验优化 | [`BACKLOG.md`](BACKLOG.md) | 从版本主线剥离的独立追踪，完成标 ✅ |
| 系统架构 / 模块 / 数据流 | [`ARCHITECTURE.md`](ARCHITECTURE.md) | 架构**唯一事实源**，改架构先改这里再改代码 |
| 外部 API 技术细节（DashScope / 通义千问） | [`API_CONTRACTS.md`](API_CONTRACTS.md) | API 契约**唯一事实源**，代码注释只引用不复述 |
| 云服务器部署 / 运维 | [`DEPLOYMENT.md`](DEPLOYMENT.md) | 服务器信息、端口、更新流程的**唯一事实源** |
| 认证与订阅系统实现方案 | [`AUTH_DESIGN.md`](AUTH_DESIGN.md) | 配套 [ADR-0006](adr/0006-认证与订阅架构.md) 的技术设计 |
| 用量计量 / 计费技术方案 | [`USAGE_METERING_DESIGN.md`](USAGE_METERING_DESIGN.md) | 计量计费设计草案，依赖 AUTH_DESIGN + API_CONTRACTS |
| 界面设计决策与原则 | [`design/DESIGN_DECISIONS.md`](design/DESIGN_DECISIONS.md) | 布局原则、状态机、交互策略、产品蓝图（组件实现以 Vue 源码为准） |
| Agent 角色系统设计与实施计划 | [`design/AGENT_ROLE_SYSTEM.md`](design/AGENT_ROLE_SYSTEM.md) | 从硬编码提示词迁移到 .md 工作区，预定义角色 + fork 自定义 + 场景切换 |
| 图标库选型与使用规范 | [`ICON_SPEC.md`](ICON_SPEC.md) | Lucide（Feather 风格）+ 尺寸体系 + Emoji 替换映射 |
| 重大决策的背景 / 选项 / 后果 | [`adr/`](adr/) | 一个决策一篇，旧的标 Superseded 不删不改 |
| 术语口径统一 | [`GLOSSARY.md`](GLOSSARY.md) | 避免文档 / 代码 / AI 对话各说各话 |

## 二、目录结构

```
docs/
├── README.md                    # 本文，目录导航
├── PRD.md                       # 产品稳态需求
├── ROADMAP.md                   # 版本主线（里程碑）
├── BACKLOG.md                   # 零散缺陷与体验优化
├── ARCHITECTURE.md              # 系统架构（唯一事实源）
├── API_CONTRACTS.md             # 外部 API 契约（唯一事实源）
├── DEPLOYMENT.md                # 云部署与运维（唯一事实源）
├── AUTH_DESIGN.md               # 认证与订阅技术设计
├── USAGE_METERING_DESIGN.md     # 用量计量技术方案
├── ICON_SPEC.md                 # 图标规范
├── GLOSSARY.md                  # 术语表
├── adr/                         # 架构决策记录（含独立 README 索引）
│   ├── README.md                # ADR 索引 + 新建模板
│   └── 000X-*.md                # 各篇决策
├── design/                      # 界面设计
│   ├── DESIGN_DECISIONS.md      # 界面设计决策与原则
│   ├── AGENT_ROLE_SYSTEM.md     # Agent 角色系统设计
│   ├── MOBILE_DESIGN.md         # 移动端设计
│   ├── START_PAGE_DESIGN.md     # 起始页设计
│   ├── SPK-RN-DISPLAY-STRATEGY.md # 说话人展示策略
│   └── SILENCE_DETECTION.md     # 静音检测设计
```

## 三、子目录说明

- **`adr/`** — 架构决策记录。编号递增，不删不改旧记录，作废改状态为 `Superseded by ADR-xxxx`。索引与模板见 [`adr/README.md`](adr/README.md)。
- **`design/`** — 界面设计。`DESIGN_DECISIONS.md` 记录设计原则与决策（布局、状态机、交互策略）；具体组件实现以 `frontend/src/` Vue 源码为准。

## 四、与根目录文档的关系

`docs/` 之外还有几份根目录文档承担不同职责，冲突时以 `docs/` 为准：

| 文档 | 定位 |
|------|------|
| [`../CHANGELOG.md`](../CHANGELOG.md) | 迭代痕迹，每次功能迭代追加一条 |
| [`../MISSION.md`](../MISSION.md) | 产品长期使命（「本地数据·云端智能」定位） |

## 五、维护约定

1. 每份 `.md` 均以 YAML front matter 开头（`title` / `description` / `tags` / `created_at` / `updated_at` / `version` 等）。
2. 修改文档内容时同步更新 `updated_at`，必要时升级 `version`。
3. 新增文档后，回来在本文的速查表与目录结构中登记，保持索引不失效。
