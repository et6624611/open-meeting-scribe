---
title: 贡献指南
description: 如何为 Open Meeting Scribe 贡献代码、报告问题或提出建议
tags: ["contributing", "open-source", "guidelines"]
created_at: "2026-09-10"
updated_at: "2026-09-13"
version: "1.1.0"
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
5. 提交代码并签署 DCO（见下节）：`git commit -s -m "描述你的改动"`
6. 推送到你的 Fork：`git push origin feature/your-feature-name`
7. 创建 Pull Request

### 签署 DCO（必需）

本项目采用 [Developer Certificate of Origin（DCO）](https://developercertificate.org/) 来确认你有权提交相应代码。每个 commit 都必须包含 `Signed-off-by` 行：

```
Signed-off-by: 你的名字 <你的邮箱>
```

- 使用 `git commit -s` 可自动添加该行（需先在 git 中配置好 `user.name` 与 `user.email`）。
- 若已提交但忘记签署，可用 `git commit --amend -s` 补签，再 `git push -f` 更新分支。
- 姓名与邮箱需与你的 GitHub 账号一致；未签署 DCO 的 PR 会被 CI 拦截，无法合并。

DCO 是一份轻量声明，代表你确认：该贡献由你本人创建且有权以本项目许可证提交，或基于兼容许可证的既有作品，或已在有权者同意下提交。它不转让版权，你依然是自己代码的版权持有人。

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

## 隐私与合规要求

提交前请务必检查，以下问题会导致 PR 被拒绝：

### 敏感信息

- **禁止提交任何密钥**：API Key、Token、密码等敏感配置一律通过 `.env` / 环境变量注入，不得硬编码到源码或提交进仓库。
- **禁止提交个人与基础设施信息**：公网 IP、真实人名、内部服务器地址等不得出现在代码、配置或文档中。测试/演示数据请使用匿名占位（如「说话人 S1」）。

### 品牌抽象化

本项目对用户可见文案采用品牌抽象化规范：

- **面向用户的 UI 文案与公开文档**（README、SECURITY、CHANGELOG 等）：不得暴露第三方厂商品牌名，统一使用「云端 AI 服务」等通用描述。
- **代码内部标识符**（provider 字段、环境变量名）与**技术 API 名称**（如模型 ID、Provider 下拉选项）：可保留具体名称，作为开发者实现参考。

### 许可证兼容性

本项目采用 **AGPLv3**（copyleft），对引入的第三方代码有兼容性要求：

- **不要粘贴来源不明或许可证不兼容的代码片段**（例如仅署名/专有许可，或与 AGPLv3 不兼容的 GPLv2-only 代码）。
- 引入新的第三方依赖前，请先评估其许可证是否与 AGPLv3 兼容，并在 PR 中说明。

## 许可证

提交代码即表示你同意你的贡献以 [GNU AGPLv3](LICENSE) 授权（入站授权与出站授权一致，inbound = outbound）。你依然是自己贡献代码的版权持有人，同时授予项目与下游使用者在 AGPLv3 条款下使用、修改与再分发的权利。
