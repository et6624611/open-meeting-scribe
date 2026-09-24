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
| REQ-PROGRESS-P0 | docs/REQUIREMENT-TRANSCRIBE-PROGRESS-DISPLAY.md v0.3.0（main@7f13a8d） | 前端开发工程师（d1b77737cde5） | session 7ff67e75-b66d-41dc-bcc9-7fcd7375148f / 分支 feat/req-progress-p0（worktree 隔离） | in-progress | 2026-09-24 21:40 产品已向会话追发补证要求（4 项自测证据）；PRD 升 v0.3.0：Q5 裁决关闭，AC-8 降级为角标+toast，系统通知转 P1 | 工程师补自测证据 → 转 awaiting-acceptance → 产品验收 AC-1~6/8/9 → 合入 | ⚠️ 等待工程师补证回报 |
| DC-DEC-B1 | docs/REQUIREMENT-DECISION-CENTER.md v0.2.0（main@bf875ff） | 后端工程师（a4cdbd0ca795） | session c7ddd206-a797-4291-9a23-99b1bf491b00 / 分支 feat/req-decision-center-b1（worktree 隔离） | dispatched | 2026-09-24 23:26 派出（R1 模型抽取 / R2 API / R4 回填）；23:40 追发回报条款（群 @产品经理 主动回报为主，session send 兜底） | 契约交付/完工/卡点应主动群回报；等回报后产品验收 AC-1~7/10 → 合入 | 与 F1 同仓并行，公共文档冲突由产品协调 |
| DC-DEC-F1 | docs/REQUIREMENT-DECISION-CENTER.md v0.2.0（main@bf875ff） | 前端开发工程师（d1b77737cde5） | session 1af94412-472c-4c9d-be9a-19ddb330502d / 分支 feat/req-decision-center-f1（worktree 隔离） | dispatched | 2026-09-24 23:26 派出（R3 决策中心页 + 决策Tab更名行动项）；23:40 追发同款回报条款 | mock 先行开发；主动群回报后产品验收 AC-8/9 → 与 B1 联调 → 合入 | ⚠️ 同工程师已有 REQ-PROGRESS-P0 在途，两分支都动 router/导航，合并顺序 P0 优先、本单后 rebase |

## 已关闭派工

| 单号 | 关闭时间 | 结果 |
|---|---|---|
| （暂无） | | |

## 巡检说明

- 回报通道（2026-09-24 23:40 起，项目方批准）：**推模式为主**——工程师在开发群 `messages send --mention 产品经理 --intent request_action` 主动回报（契约交付/完工/卡点三个必报时点），兜底 `session send` 直投产品经理会话；定时巡检降级为**工程师忘回报时的拉模式保险**（REQ-DECISION-CENTER 两单已追发条款；REQ-PROGRESS-P0 暂未追加，仍走纯巡检）。
- 巡检自动任务：QoderWake 平台 automation「派工进度巡检」，每 10 分钟唤醒产品经理会话。
- 巡检动作：读本表在途行 → `qoderwake session list/detail` 查会话态 → `git fetch` 比对分支 commit → 有变化才更新本行并 commit+push（前缀 `docs(tracker):`）→ 异常（完成未回报 / 运行报错 / 无进展超 4 小时）标 ⚠️ 并在 IM channel 可用时提醒项目方。
- 无变化时静默退出，不产生 commit、不打扰。
