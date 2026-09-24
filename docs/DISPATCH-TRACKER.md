---
title: 派工台账（Dispatch Tracker）
description: 所有在途/关闭派工的单一事实源，由产品经理维护，平台自动任务「派工进度巡检」周期性更新
version: "1.0.0"
status: active
---

# 派工台账

> 规则：一行一单；状态取值 `dispatched`（已派出）/ `in-progress`（有 commit 进展）/ `awaiting-acceptance`（完成待验收）/ `blocked`（卡住/需决策）/ `closed`（验收合入）。巡检任务仅在**状态或进展变化**时改写本表并留痕；异常在「待关注」列以 ⚠️ 标记，IM channel 接入后同时发消息提醒。

## 在途派工

| 单号 | 派工依据 | Owner | 会话 / 分支 | 状态 | 最近进展（巡检时间） | 下一步 | 待关注 |
|---|---|---|---|---|---|---|---|
| REQ-PROGRESS-P0 | docs/REQUIREMENT-TRANSCRIBE-PROGRESS-DISPLAY.md v0.2.0（main@7f13a8d） | 前端开发工程师（d1b77737cde5） | session 7ff67e75-b66d-41dc-bcc9-7fcd7375148f / 分支 feat/req-progress-p0 | dispatched | 2026-09-24 18:55 派出，会话 running | 等工程师回报分支+commit+自测证据 → 产品验收（AC-1~6/8/9）→ 合入 main | — |

## 已关闭派工

| 单号 | 关闭时间 | 结果 |
|---|---|---|
| （暂无） | | |

## 巡检说明

- 巡检自动任务：QoderWake 平台 automation「派工进度巡检」，每 10 分钟唤醒产品经理会话。
- 巡检动作：读本表在途行 → `qoderwake session list/detail` 查会话态 → `git fetch` 比对分支 commit → 有变化才更新本行并 commit+push（前缀 `docs(tracker):`）→ 异常（完成未回报 / 运行报错 / 无进展超 4 小时）标 ⚠️ 并在 IM channel 可用时提醒项目方。
- 无变化时静默退出，不产生 commit、不打扰。
