---
title: "Git 多电脑协作实战指南"
description: "从一次 force push 事故出发，系统梳理 Git 多电脑协作的正确流程、VS Code Git 菜单功能、常见命令与避坑要点。"
tags: ["git", "协作", "多电脑", "版本控制", "实战指南"]
created_at: "2026-09-14"
updated_at: "2026-09-14"
version: "1.0.0"
author: "wangyongliang"
status: "published"
category: "tutorial"
---

# Git 多电脑协作实战指南

> 本文从一次真实的 force push 事故出发，系统梳理 Git 多电脑协作的正确流程、VS Code Git 菜单功能、常用命令与避坑要点。

---

## 一、一次真实的事故：发生了什么

### 背景

在 Mac 和 Windows 两台电脑上维护同一个 GitHub 仓库 `open-meeting-scribe`。

### Mac 上的正常开发历史

```
dfdb8d8  更新                          ← Mac 最后一次提交
90b4053  修复win打包问题 (v7.0.1)
6f037e6  显式列举全部子模块 (v7.0.0)
6ab1479  工作流增加 dist 诊断步骤
fb16ee4  添加 Windows 应用图标
58d79a9  修复 uvicorn 导入
cacf706  修复 PyInstaller stderr 崩溃
f7478b8  修复 spec 动态收集数据文件
abc8450  同步 VERSION 为 v7.0.0
  ...（完整的渐进式开发历史，每次改动一个提交）
```

### Windows 推送后，远程变成了

```
f5497f5  解决了当前版本下win程序打包的问题  ← 唯一的提交，包含全部 414 个文件
```

**没有任何父提交**，是一个全新的「根提交」，包含了整个项目的所有代码（288,246 行）。

### 事故原因

Windows 那边大概率做了以下操作之一：

1. **重新 `git init` 了一个全新仓库**，把所有代码复制进去，一次性 `git add . && git commit`，再 `git push --force` 强推上去
2. 或者做了**浅克隆**（`--depth=1`），历史被截断，修改后又 force push

### 后果

| 问题 | 影响 |
|---|---|
| 提交历史丢失 | Mac 上十几个有意义的提交全部消失，无法追溯「什么时候改了什么」 |
| 强制推送覆盖远程 | 另一台电脑拉取时会遇到历史断裂 |
| 构建产物入库 | 10 万行 PyInstaller 产物也被一起提交 |

---

## 二、双电脑协作的正确模型

```
Mac 提交 → push → GitHub ← push ← Windows 提交
         ↑                          ↑
       pull                       pull
```

### 铁律

> **每次推送前先拉取，永远不要用强制推送覆盖远程。**

### Windows 电脑日常开发流程

```
┌─────────────────────────────────────────────────┐
│  1. 开工前：git pull                              │
│     → 把 Mac 的改动拉下来合并到本地               │
│                                                  │
│  2. 开发修改代码                                  │
│                                                  │
│  3. git commit                                    │
│     → 保存到本地，写清楚提交信息                   │
│                                                  │
│  4. git push                                      │
│     → 上传到远程                                  │
│     → 如果失败，说明 Mac 又推了新代码，回到步骤 1  │
└─────────────────────────────────────────────────┘
```

### 如果推送失败（远程有新提交）

```
推送失败
    ↓
git pull → 自动合并对方的改动
    ↓
如果有冲突 → 手动解决冲突 → git commit
    ↓
再 git push → 成功
```

---

## 三、VS Code Git 菜单功能详解

VS Code 源代码管理面板中的 Git 菜单各项功能：

| 菜单项 | 对应 Git 命令 | 使用场景 |
|---|---|---|
| **拉取** | `git pull` | 把远程最新代码**下载并合并**到本地。开工前必做 |
| **推送** | `git push` | 把本地已提交的改动**上传**到远程。远程有新提交时会拒绝，提示先 pull |
| **克隆** | `git clone` | 从远程**完整复制**一个仓库到本地（首次获取项目时使用） |
| **签出到...** | `git checkout` | 切换分支、恢复文件、或回到某个历史提交 |
| **抓取** | `git fetch` | 只下载远程信息**不合并**，安全预览远程有什么新改动 |
| **提交** | `git commit` | 把暂存区的改动保存为一次本地提交（还没上传到远程） |
| **更改** | — | 查看当前工作区所有未暂存的修改文件列表 |
| **拉取，推送** | `git pull && git push` | 一键完成「先拉取再推送」，适合快速同步 |
| **分支** | `git branch` | 创建、切换、删除本地分支 |
| **远程** | `git remote` | 管理远程仓库（添加/删除/重命名远程地址） |
| **存储** | `git stash` | 临时保存当前未提交的改动，清空工作区以便切换分支，之后可恢复 |
| **标记** | `git tag` | 给某个提交打标签（如 `v7.0.0`），用于版本发布标记 |
| **显示 GIT 输出** | — | 打开 Git 命令的详细日志面板，用于排查问题 |

---

## 四、常用 Git 命令速查

### 查看与诊断

```bash
# 查看远程仓库地址
git remote -v

# 查看当前状态（哪些文件改了、哪些没跟踪）
git status

# 查看所有分支（本地 + 远程）
git branch -a

# 查看提交历史（最近 10 条）
git log --oneline -10

# 查看操作历史（即使 reset 也能找回）
git reflog

# 查看远程比本地多了哪些提交
git log HEAD..origin/main --oneline

# 查看文件变更统计
git diff HEAD..origin/main --stat
```

### 拉取与合并

```bash
# 只下载不合并（安全预览）
git fetch origin

# 拉取并合并（推荐日常使用）
git pull origin main

# 拉取并 rebase（保持线性历史，更干净）
git pull --rebase origin main

# 浅拉取（仅预览，不用于后续合并）
git fetch origin main --depth=1
```

### 提交与推送

```bash
# 暂存所有改动
git add -A

# 提交到本地
git commit -m "描述你的改动"

# 推送到远程
git push origin main
```

### 暂存与恢复（切换分支/合并前保护本地修改）

```bash
# 暂存本地修改
git stash push -m "暂存本地修改"

# 查看暂存列表
git stash list

# 恢复暂存的修改
git stash pop

# 丢弃暂存（不恢复）
git stash drop
```

### 强制同步远程（历史已被重写时）

```bash
# 1. 暂存本地修改
git stash push -m "暂存本地修改"

# 2. 将本地重置为远程最新
git reset --hard origin/main

# 3. 恢复本地修改
git stash pop
```

### 从跟踪中移除文件（但不删除本地文件）

```bash
# 从 Git 跟踪中移除，但保留本地文件
git rm --cached <文件路径>

# 递归移除整个目录
git rm --cached -r <目录路径>
```

---

## 五、.gitignore 最佳实践

### 为什么需要 .gitignore

不是所有文件都应该进入版本控制：

| 应该忽略 | 原因 |
|---|---|
| `build/` 下的产物目录 | PyInstaller 等构建工具生成的二进制文件，可随时重建 |
| `dist/` | 打包输出目录 |
| `node_modules/` | 依赖安装目录 |
| `__pycache__/` | Python 字节码缓存 |
| `.env` | 包含敏感密钥和配置 |
| `*.pyc`, `*.pyo` | Python 编译产物 |
| `.DS_Store` | macOS 系统文件 |
| `logs/` | 运行时日志 |
| `data/output/`, `data/uploads/` | 运行时产生的数据 |

### 应该保留跟踪的

| 应该跟踪 | 原因 |
|---|---|
| `build/*.py` | 构建脚本源代码 |
| `build/*.spec` | PyInstaller 配置模板 |
| `build/icon.*` | 应用图标源文件 |
| `build/launcher.*` | 启动脚本 |
| `.env.example` | 配置模板（不含真实密钥） |

### 示例：精确忽略产物而非整个目录

```gitignore
# ❌ 错误：忽略整个 build/，会丢掉有用的源文件
build/

# ✅ 正确：只忽略产物子目录，保留源文件
build/OpenMeetingScribe/
build/pyinstaller_macos/
```

---

## 六、绝对不要做的操作

| 危险操作 | 后果 | 正确替代 |
|---|---|---|
| `git push --force` | 覆盖远程历史，丢失别人的提交 | `git pull` 后再 `git push` |
| 删除远程仓库后重新 push | 同上，历史全部丢失 | 正常 push，有冲突先解决 |
| 不拉取就强制推送 | 两台电脑的代码互相覆盖 | 先 pull 再 push |
| `git init` 后 force push 到已有远程 | 重写整个历史 | 用 `git clone` 获取已有仓库 |
| 提交构建产物/大文件 | 仓库膨胀，拖慢所有人 | 加入 `.gitignore` |

---

## 七、Git 核心概念图解

```
工作区 (Working Directory)
    │  git add
    ▼
暂存区 (Staging Area / Index)
    │  git commit
    ▼
本地仓库 (Local Repository)
    │  git push
    ▼
远程仓库 (Remote Repository / GitHub)
    │  git pull / git fetch
    ▼
本地仓库 ← 合并/变基 ← 远程更新
```

### 三个区域的关系

- **工作区**：你正在编辑的文件
- **暂存区**：`git add` 后准备提交的文件快照
- **本地仓库**：`git commit` 后保存的完整历史记录
- **远程仓库**：GitHub 上的共享版本

### 分支是什么

```
main:  A --- B --- C --- D  ← 主分支，稳定版本
              \
feature:       E --- F      ← 功能分支，开发新功能
```

- 分支是**指向某个提交的指针**，不是文件的副本
- 切换分支时，Git 会自动替换工作区的文件为对应版本
- `main` 是默认主分支，通常保持可发布状态

---

## 八、排查问题工具箱

```bash
# 查看最近的操作历史（包括 reset、merge 等）
git reflog

# 查看某个文件的历史修改
git log --oneline -- <文件路径>

# 查看某次提交的详细内容
git show <commit-hash>

# 查看两个提交之间的差异
git diff <commit1> <commit2>

# 查看谁在什么时候改了什么
git blame <文件路径>

# 恢复某个文件到指定提交的状态
git checkout <commit-hash> -- <文件路径>

# 撤销工作区的修改（未 add 的）
git restore <文件路径>

# 撤销暂存区的修改（已 add 未 commit 的）
git restore --staged <文件路径>
```

---

## 九、总结：多电脑协作口诀

```
开工之前先拉取 (git pull)
改完代码要提交 (git commit)
提交之后推远程 (git push)
推送失败再拉取 (git pull → 解决冲突 → git push)
永远不要强推送 (禁止 git push --force)
构建产物要忽略 (.gitignore)
```
