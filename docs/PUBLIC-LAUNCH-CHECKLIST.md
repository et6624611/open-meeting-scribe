---
title: 开源发布执行清单 v1.0.0 — Open Meeting Scribe
description: 2026-10-05 首发执行的实际清单与状态；配套 PUBLIC-LAUNCH-REMEDIATION-PLAN.md（方案 A）
author: et6624611
created_at: 2026-10-05
updated_at: 2026-10-05
version: "1.0.0"
status: active
---

# 开源发布执行清单 v1.0.0

> 方案依据：[PUBLIC-LAUNCH-REMEDIATION-PLAN.md](PUBLIC-LAUNCH-REMEDIATION-PLAN.md) 方案 A（干净首提交 + 新建 GitHub 仓库）。
> 执行日期：2026-10-05。备份：`~/oms-full-backup-20261005.bundle`（159 MB）+ `open-meeting-scribe-mirror-backup-20261004.git`。

## 已完成

### A 组：工作树脱敏

- [x] 删除 `tests/eval_local_engine/` 真实语料与结果 42 个文件（refs/ 20、results/ 22、eval_manifest.json）
- [x] 4 份评测报告脱敏：真名→S1~S7 代号，样本文件改化名，云端账号/手机号泛化，头部加私有归档声明
- [x] `tests/test_chat.py` 真名 fixture → 虚构测试名
- [x] `tests/test_llm_selfhost.py` 内网地址 → RFC 5737 保留段 `192.0.2.10`（含反向断言对齐）
- [x] `pyproject.toml` 作者 → et6624611 + GitHub noreply 邮箱
- [x] CHANGELOG / adr/0008 真名例句 → 「参会人 A/B」
- [x] 补漏：真实公司名「智达方通」5 文件 → 「云端科技」（gitleaks 扫描时发现，A 组首轮漏网）
- [x] 测试占位 api_key 改显式 FAKE 串，AUTH_DESIGN 示例 license 改 `OMSK-XXXX-...`
- [x] 后端测试通过（test_chat / test_llm_selfhost / test_local_engine_* 等）

### B 组：版本号治理

- [x] VERSION：7.4.5 → 1.0.0
- [x] README.md / README_zh-CN.md front-matter → 1.0.0
- [x] CHANGELOG 顶部加 [1.0.0] 首发段，旧版本叙事保留
- [x] 首提交作者身份使用 noreply 邮箱

### C 组：合规门禁

- [x] THIRD_PARTY_NOTICES 重写：移除退役 G6，补 NumPy/python-docx/PyPDF2/Babel/pywebview/ffmpeg，新增 FunASR/PyTorch 与 ModelScope 四模型「引导下载不随包分发」声明
- [x] gitleaks 扫描：HEAD 零命中（历史 8 处命中均属旧 commit，孤儿首提交不带入）
- [x] `data/settings.json` 真实 key 未跟踪，不入仓
- [x] Docker 镜像实测：`docker build` 通过（node:20-slim + python:3.12-slim，内置 ffmpeg 7.1.5）；冒烟全绿——`GET /` 200、静态 asset 200、`GET /api/tasks?view=lite` 200。修复：package-lock.json 与 package.json 失步（缺 vitest/playwright-core/jsdom 等 devDeps），已用 node:20 容器 `npm install --package-lock-only` 重建

### D 组：干净历史与远端

- [x] 全量 bundle 备份（仓库与同步盘外）
- [x] orphan 干净首提交：`f35a336`（598 文件，单提交）
- [x] tag：只打 v1.0.0
- [x] 旧仓 rename：`open-meeting-scribe` → `open-meeting-scribe-private-archive`，保持 private
- [x] 删除旧仓 18 个远端分支（保留 main）
- [x] 新建公开仓：https://github.com/et6624611/open-meeting-scribe
- [x] 推送干净 main + v1.0.0
- [x] 误推的 17 个旧 tag 已从新仓删除（事故记录：`git push --tags` 无差别推送，已立即纠正，GitHub 侧悬空对象等待服务端 gc）
- [x] 本地 main 重置到 f35a336，跟踪新 origin；旧仓 remote 改名 old-archive

### E 组：门面

- [x] README 双语首屏：badges、Releases/Security 导航、非技术用户 AI 协助声明
- [x] ~~Demo 段占位~~ 用户决定暂不放演示素材，占位段已移除（2026-10-05）
- [x] Docker 路径写入双语 README Quick Start（Option A / 路径 A），含「不含 FunASR 权重」说明
- [x] 分发声明：仅源码 + Docker，无预编译二进制
- [x] 署名统一 et6624611
- [x] Issue 模板双语引导（bug_report / feature_request）
- [x] ~~Demo GIF/视频~~ 用户决定暂不提供（2026-10-05）
- [x] GitHub Release v1.0.0 发布说明：https://github.com/et6624611/open-meeting-scribe/releases/tag/v1.0.0
- [x] topics 标签已加：meeting / transcription / asr / speaker-diarization / voiceprint / minutes / funasr / open-source

## 遗留与后续

| 事项 | 状态 | 说明 |
|---|---|---|
| Docker 冒烟 | 已完成 | 2026-10-05 build + 三项冒烟全绿（见 C 组） |
| 旧仓观察期 | 待办 | private-archive 保留观察，确认无引用后删除 |
| feature/performance-monitoring | 可选 | 本地仍有该分支（16 个独有提交、无隐私），需要时 rebase 到干净仓 |
| 本地旧分支清理 | 待办 | 18 个本地旧分支 + snapshot/pre-slim-20261004 仅本地救援用，观察期后清理 |
| B1 真机验收 | 持续 | WKWebView 桌面壳真机回归（录音/权限/原生桥/文件路径） |
| 评测复现 | 不做 | 如需可复现性，另立合成数据工程（虚构剧本 + TTS），不复用真实片段 |

## 回滚点

- 新仓推送内容 = 本地 f35a336（单提交），任何阶段可用 `~/oms-full-backup-20261005.bundle` 恢复全部旧历史
- 旧仓未删除，仅 rename 为 private：`git@github.com:et6624611/open-meeting-scribe-private-archive.git`
