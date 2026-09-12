---
title: 贡献指南
description: 如何为 Open Meeting Scribe 贡献代码、报告问题或提出建议
tags: ["contributing", "open-source", "guidelines"]
created_at: "2026-09-10"
updated_at: "2026-09-12"
version: "1.0.0"
---

# 贡献指南

感谢你考虑为 Open Meeting Scribe 做出贡献！每一份帮助都让这个工具变得更好。

## 报告 Bug

如果你发现了 Bug，请提交 Issue：

1. 先到 [Issues 页面](https://github.com/et6624611/open-meeting-scribe/issues) 搜索是否已有相同报告
2. 如果没有，点击 **New Issue** → **Bug Report**
3. 填写模板中的信息，尤其是：
   - 复现步骤
   - 期望行为 vs 实际行为
   - 环境信息（macOS 版本、Python 版本、浏览器版本）

## 提出功能建议

欢迎提出新功能想法：

1. 到 Issues 页面点击 **New Issue** → **Feature Request**
2. 描述你的使用场景和期望的功能
3. 如果有实现思路，也欢迎一并分享

## 提交代码

### 开发流程

1. Fork 本仓库并 clone 到本地
2. 创建功能分支：`git checkout -b feature/your-feature-name`
3. 进行开发（遵循下方代码规范）
4. 提交前运行测试：`pytest tests/`
5. 提交代码：`git commit -m "描述你的改动"`
6. 推送到你的 Fork：`git push origin feature/your-feature-name`
7. 创建 Pull Request

### 代码规范

**后端（Python）**：
- Python 3.11+
- 遵循现有代码风格（函数命名用 snake_case，类名用 PascalCase）
- 注释和文档字符串使用中文
- 含阻塞操作的函数用同步定义，纯异步 I/O 用 `async def`

**前端（Vue 3 + TypeScript）**：
- 使用 Composition API + `<script setup>` 语法
- 组件命名用 PascalCase
- 遵循现有目录结构

### 提交信息格式

```
<类型>: <简短描述>

<可选的详细说明>
```

类型：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `refactor`: 重构（不改变功能）
- `test`: 测试相关
- `chore`: 构建/工具链

## 开发环境搭建

详见 [README.md](README.md) 的「快速开始」部分。

## 许可证

提交代码即表示你同意你的贡献以 [GNU AGPLv3](LICENSE) 授权。
