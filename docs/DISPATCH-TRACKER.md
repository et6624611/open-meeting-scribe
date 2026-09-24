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
| AM-B1 | docs/REQUIREMENT-ACCESS-MODE-CARDS.md v0.1.0（main@f2445a1） | 后端工程师（a4cdbd0ca795） | session c95528c3-7941-4527-8648-ee0275c885d6 / 分支 feat/req-access-mode-b1（worktree 隔离） | dispatched | 2026-09-25 派工（T1 数据层 access_mode/expert_mode+迁移、T2 后端行为收口+路由变化可感知契约）；含推模式回报条款 | 工程师交付契约/完工回报 → awaiting-acceptance → 产品验收 AC-T1/AC-T2 → 合入 | ⚠️ 同工程师两单并行；AM-B1 禁改 frontend/，与 decisions 相关文件冲突需回报协调（DC-DEC-B1 已合入 main@586d141） |

## 待派工队列

| 单号 | 派工依据 | 拟 Owner | 触发条件 |
|---|---|---|---|
| AM-F1 | docs/REQUIREMENT-ACCESS-MODE-CARDS.md v0.1.0（T3 三卡片组件 / T4 引导与专家模式 / T5 状态栏统一） | 前端开发工程师（d1b77737cde5） | 项目方裁决 2026-09-25：等 REQ-PROGRESS-P0 与 DC-DEC-F1 两单合入后再派（冲突面最小），届时基于新 main 开 worktree |
| AM-Q1 | 同上（T6 回归验证，含存量组合迁移用例=发版门禁） | QA | AM-B1 与 AM-F1 均转 awaiting-acceptance 后触发 |

## 已关闭派工

| 单号 | 关闭时间 | 结果 |
|---|---|---|
| DC-DEC-B1 | 2026-09-25 00:40 | 两轮验收：首轮 RF-1 打回（模板「三、决策」节漏采），23dc21d 修复复验通过（33/33 新用例+84/84 相邻回归本侧独立复跑）。PR #7 squash 合入 main@586d141。R4 已执行（项目方批准 00:24）：382 扫描/56 回填/359 条决策/9 空标记；47 失败经抽查 46 场为旧版格式纪要（无结论/决策章节）、1 场混合节，属真实历史边界非解析缺陷，留决策中心手动补录兜底；报告 data/_backfill_report.json。遗留：AC-1 真实 LLM dogfooding 随后续 5 场真实会议自然验证 |
| DC-DEC-F1 | 2026-09-25 02:20 | 三轮验收：首轮（86c33fd）构建/代码过，RF-F1（** 剥除）+rebase 修复单下达；增量 d181ed2 §12 契约对齐五项通过；修复轮 07aea76 复验通过——stripDecisionEmphasis 仅剥成对 **/__（dq 保留原文、后端不回改、检索双命中），DecisionCard/SupersedeDialog/DecisionFlowPanel 三面接入，本侧独立 worktree 构建全绿，真实后端冒烟证据 dc-f1-20~27（359 条零符号泄漏、补录/取代/撤销/检索/锚点跳转全链路、临时数据清理）。squash 合入 main@714f6cf。备注：分支 merge 实际锚点为 e2c8142（回报写 07d83f7，勘误不影响代码）。交错增量收编：工程师修复轮后续 commit 17f9857 补齐成对反引号剥除（RF-F1 原口径清零，构建复跑全绿，证据 dc-f1-28~30），已 squash 合入 main@d92e598；merge 代 rebase 获产品认可（squash 保 main 线性，分支内部无需重写远端历史）。R5 文档收尾已同步落：GLOSSARY 术语拆分 / VUE_COMPONENT_MAP 路由+组件+api 行 / PRD v1.3.0 / OUTPUT-STRUCT §Q1 裁决注记 / BACKLOG 全量拉取 5s 性能跟进项。解锁：AM-F1 派工前置仅剩 REQ-PROGRESS-P0 合入 |

## 巡检说明

- 回报通道（2026-09-24 23:40 起，项目方批准）：**推模式为主**——工程师在开发群 `messages send --mention 产品经理 --intent request_action` 主动回报（契约交付/完工/卡点三个必报时点），兜底 `session send` 直投产品经理会话；定时巡检降级为**工程师忘回报时的拉模式保险**（REQ-DECISION-CENTER 两单已追发条款；REQ-PROGRESS-P0 暂未追加，仍走纯巡检）。
- 巡检自动任务：QoderWake 平台 automation「派工进度巡检」（tr_08b821764f093472194a49de），2026-09-24 23:42 由项目管理员重建（原产品经理名下任务已失联），每小时整点运行，权限=read-write+network+runCommands（限 git/qoderwake/pytest/python3）。
- 无人值守自治边界（2026-09-24 23:41 项目方拍板）：① **预授权按 AC 验收**——证据齐备且 AC 可机器核验时巡检可直接关单，缺证或口径争议不关单、标 ⚠️ 留痕；② 超 4 小时无进展自动催办 Owner 会话；③ 仅阻塞性异常叫醒项目方（连续两轮无进展、会话卡死、验收争议、范围/排期/跨单冲突需决策）；④ 每天 09:00 出日报追加至本台账。
- 巡检动作：读本表在途行 → `qoderwake session list/detail` 查会话态 → `git fetch` 比对分支 commit → 有变化才更新本行并 commit+push（前缀 `docs(tracker):`）→ 异常（完成未回报 / 运行报错 / 无进展超 4 小时）标 ⚠️ 并在 IM channel 可用时提醒项目方。
- 无变化时静默退出，不产生 commit、不打扰。
