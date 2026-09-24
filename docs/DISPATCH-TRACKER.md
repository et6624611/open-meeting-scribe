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
| DC-DEC-B1 | docs/REQUIREMENT-DECISION-CENTER.md v0.2.0（main@bf875ff） | 后端工程师（a4cdbd0ca795） | session c7ddd206-a797-4291-9a23-99b1bf491b00 / 分支 feat/req-decision-center-b1 @ 7e1a328+b2fb8da / PR #7 | in-progress | 2026-09-25 00:10 产品首轮验收：29 用例独立复跑过，R2 API/注入级联/回填幂等/契约 §12 全过；唯 RF-1 阻塞——模板运行时覆盖 SYSTEM_PROMPT，但抽取只读「二、主要结论」，模板真正的决策来源「三、决策」节不被解析（§Q1 缺口未堵上），修复单已下达 | 工程师修 RF-1（双章节抽取+去重+新增用例）→ 复验 → 合入 PR #7 → 产品侧 dogfooding 验 AC-1 + 执行 R4 真实回填 | ⚠️ RF-1 修复中；群回报无发送身份，暂走 session send 兜底 |
| DC-DEC-F1 | docs/REQUIREMENT-DECISION-CENTER.md v0.2.0（main@bf875ff） | 前端开发工程师（d1b77737cde5） | session 1af94412-472c-4c9d-be9a-19ddb330502d / 分支 feat/req-decision-center-f1（worktree 隔离） | dispatched | 2026-09-24 23:26 派出（R3 决策中心页 + 决策Tab更名行动项）；23:40 追发同款回报条款 | mock 先行开发；主动群回报后产品验收 AC-8/9 → 与 B1 联调 → 合入 | ⚠️ 同工程师已有 REQ-PROGRESS-P0 在途，两分支都动 router/导航，合并顺序 P0 优先、本单后 rebase |

## 已关闭派工

| 单号 | 关闭时间 | 结果 |
|---|---|---|
| （暂无） | | |

## 巡检说明

- 回报通道（2026-09-24 23:40 起，项目方批准）：**推模式为主**——工程师在开发群 `messages send --mention 产品经理 --intent request_action` 主动回报（契约交付/完工/卡点三个必报时点），兜底 `session send` 直投产品经理会话；定时巡检降级为**工程师忘回报时的拉模式保险**（REQ-DECISION-CENTER 两单已追发条款；REQ-PROGRESS-P0 暂未追加，仍走纯巡检）。
- 巡检自动任务：QoderWake 平台 automation「派工进度巡检」（tr_08b821764f093472194a49de），2026-09-24 23:42 由项目管理员重建（原产品经理名下任务已失联），每小时整点运行，权限=read-write+network+runCommands（限 git/qoderwake/pytest/python3）。
- 无人值守自治边界（2026-09-24 23:41 项目方拍板）：① **预授权按 AC 验收**——证据齐备且 AC 可机器核验时巡检可直接关单，缺证或口径争议不关单、标 ⚠️ 留痕；② 超 4 小时无进展自动催办 Owner 会话；③ 仅阻塞性异常叫醒项目方（连续两轮无进展、会话卡死、验收争议、范围/排期/跨单冲突需决策）；④ 每天 09:00 出日报追加至本台账。
- 巡检动作：读本表在途行 → `qoderwake session list/detail` 查会话态 → `git fetch` 比对分支 commit → 有变化才更新本行并 commit+push（前缀 `docs(tracker):`）→ 异常（完成未回报 / 运行报错 / 无进展超 4 小时）标 ⚠️ 并在 IM channel 可用时提醒项目方。
- 无变化时静默退出，不产生 commit、不打扰。
