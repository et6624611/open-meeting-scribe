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
| REQ-PROGRESS-P0 | docs/REQUIREMENT-TRANSCRIBE-PROGRESS-DISPLAY.md v0.3.0（main@7f13a8d） | 前端开发工程师（d1b77737cde5） | session 7ff67e75-b66d-41dc-bcc9-7fcd7375148f / 分支 feat/req-progress-p0（worktree 隔离，origin 顶=本地顶=51d8e85） | in-progress | 2026-09-25 06:00 巡检：仍无新 commit/无回报，但发现增量证据——reflog 显示 origin/feat/req-progress-p0 于 09-25 04:04:18 由 push 创建（恰为 04:00 催办触达时刻），原「仅本地未推 origin」记录勘误；即会话在催办时点有响应动作（推送分支后回到 waiting_input），并非完全失联。**07:00 巡检增量核验：状态与进展均无变化**（无新 commit、origin=本地仍 51d8e85、会话 lastActive 仍 04:04、无回报），维持上轮结论与待拍板项，不重复催办 | ⛔ 维持等待项目方拍板（建议携带新证据裁决：工程师可达但停摆，倾向「人工询问卡点原因」而非直接重新派工） | ⚠️⚠️ 阻塞性异常（05:00 确认）维持：催办无效需项目方决策；06:00 补充事实=04:04 催办触达当刻分支已推 origin（有响应、无后续）。IM channel 未配置→仅台账留痕。巡检不再重复催办 |
| AM-B1 | docs/REQUIREMENT-ACCESS-MODE-CARDS.md v0.1.0（main@f2445a1） | 后端工程师（a4cdbd0ca795） | session c95528c3-7941-4527-8648-ee0275c885d6 / 分支 feat/req-access-mode-b1（worktree 隔离，origin 顶=本地顶=9b829b5） | **blocked** | 2026-09-25 07:00 巡检：催办后**连续第 2 轮无进展**（06:00、07:00 两轮均无新 commit、无完工回报；origin=本地仍 9b829b5、worktree 干净、会话 lastActive 仍停在 05:08 催办触达时刻，runtimeState=waiting_input）；拉群检索亦未命中回报（chat search 派工/OpenMeetingScribe 均 0 结果）→ 按预授权规则触发**阻塞性异常①**，状态由 in-progress 转 blocked | RT-P0-FIX 已按 C 选项执行：09-25 上午项目方确认「可以反馈」，管理员随即向原会话 c95528c3 注入修复令 + 归属勘误（runtimeInputMode=next_turn）| 等工程师应答与 DEF-03/04 转绿证据；下一巡检轮仍无动静则评估 B 重新派工（分支基于 39d8b47、未含 main@d92e598，合入前需 rebase 核验）| ⚠️⚠️ 阻塞性异常①（07:00 确认）：催办 1 次（05:00，05:08 触达）后连续两轮无进展且催办无效，需项目方决策。**叫醒受限留痕**：QoderWake 已接 IM channel 仅「企业微信机器人」（global-tdceqy-wecom-bot），非钉钉/飞书/Lark 通道，无法按预授权规则自动发消息叫醒，故仅本台账留痕。已催办 1 次；同工程师两单并行；AM-B1 禁改 frontend/，与 decisions 相关文件冲突需回报协调（DC-DEC-B1 已合入 main@586d141）。巡检注：分支实现基于 39d8b47，未含 main@d92e598（反引号剥除 P2），合入前需 rebase 核验。**09-25 上午 P0-RETEST 增量实证：性质升级**——基线 main 全量 pytest 4 红，其中 DEF-RETEST-03/04 为 `/api/settings/test-llm` localhost 守卫分支的确定性回归（空 Key 误发 `Bearer ollama` 头 / 非 localhost 空 Key 返 `auth_failed` 而非 `missing_key`），自包含用例、与执行机环境无关，直指 bc261e6/9b829b5 守卫实现（PRD R4 约定被破坏）。本单由「完工回报缺失」升级为「实现带确定性回归」，解阻前提改为 RT-P0-FIX 修复单验收，非单纯催办。**归属勘误（09-25 管理员 git 复核，已同步至会话）**：bc261e6/9b829b5 仅在 feat 分支、不在 main，4 红灯复现于 main@fa42d2d 基线；`/api/settings/test-llm` 守卫与 test_llm_selfhost.py 由更早 WP-A 提交（c2a1272/24eb45f）引入 main——DEF-03/04 非 AM-B1 分支回归，排查方向为 main 既有逻辑 vs PRD R4 口径，勿在分支 diff 找因果；修复 commit 可继续落 feat/req-access-mode-b1（合入前本须带绿门禁）|

## 待派工队列

| 单号 | 派工依据 | 拟 Owner | 触发条件 |
|---|---|---|---|
| AM-F1 | docs/REQUIREMENT-ACCESS-MODE-CARDS.md v0.1.0（T3 三卡片组件 / T4 引导与专家模式 / T5 状态栏统一） | 前端开发工程师（d1b77737cde5） | 项目方裁决 2026-09-25：等 REQ-PROGRESS-P0 与 DC-DEC-F1 两单合入后再派（冲突面最小），届时基于新 main 开 worktree |
| AM-Q1 | 同上（T6 回归验证，含存量组合迁移用例=发版门禁） | QA | AM-B1 与 AM-F1 均转 awaiting-acceptance 后触发 |
| RT-P0-FIX | docs/P0-RETEST-20260925.md「缺陷发现」（基线 HEAD=fa42d2d，pytest 4 failed / 338 passed） | 后端工程师（a4cdbd0ca795，与 AM-B1 同人） | **已派（09-25 并入 AM-B1 原会话 c95528c3 注入，不另开会话）**：① 修复 DEF-RETEST-03/04（`/api/settings/test-llm` 空 Key 带头 + `missing_key` 错误码回归，确认改代码还是改测试预期）；② 定性 DEF-RETEST-01/02（在自身 worktree 切 cloud provider 单跑 tests/test_chat.py，区分环境噪声 vs mock/代码回归；主工作区 data/settings.json 禁动）；③ 门禁全绿后重跑 P0-RETEST T1~T5 手工实测。归属以 AM-B1 行勘误为准（守卫为 WP-A 早期既有实现，非 AM-B1 分支回归）。验收标准=pytest 全绿 + 清单结果列回填完毕 |

## 已关闭派工

| 单号 | 关闭时间 | 结果 |
|---|---|---|
| DC-DEC-B1 | 2026-09-25 00:40 | 两轮验收：首轮 RF-1 打回（模板「三、决策」节漏采），23dc21d 修复复验通过（33/33 新用例+84/84 相邻回归本侧独立复跑）。PR #7 squash 合入 main@586d141。R4 已执行（项目方批准 00:24）：382 扫描/56 回填/359 条决策/9 空标记；47 失败经抽查 46 场为旧版格式纪要（无结论/决策章节）、1 场混合节，属真实历史边界非解析缺陷，留决策中心手动补录兜底；报告 data/_backfill_report.json。遗留：AC-1 真实 LLM dogfooding 随后续 5 场真实会议自然验证 |
| DC-DEC-F1 | 2026-09-25 02:20 | 三轮验收：首轮（86c33fd）构建/代码过，RF-F1（** 剥除）+rebase 修复单下达；增量 d181ed2 §12 契约对齐五项通过；修复轮 07aea76 复验通过——stripDecisionEmphasis 仅剥成对 **/__（dq 保留原文、后端不回改、检索双命中），DecisionCard/SupersedeDialog/DecisionFlowPanel 三面接入，本侧独立 worktree 构建全绿，真实后端冒烟证据 dc-f1-20~27（359 条零符号泄漏、补录/取代/撤销/检索/锚点跳转全链路、临时数据清理）。squash 合入 main@714f6cf。备注：分支 merge 实际锚点为 e2c8142（回报写 07d83f7，勘误不影响代码）。交错增量收编：工程师修复轮后续 commit 17f9857 补齐成对反引号剥除（RF-F1 原口径清零，构建复跑全绿，证据 dc-f1-28~30），已 squash 合入 main@d92e598；merge 代 rebase 获产品认可（squash 保 main 线性，分支内部无需重写远端历史）。R5 文档收尾已同步落：GLOSSARY 术语拆分 / VUE_COMPONENT_MAP 路由+组件+api 行 / PRD v1.3.0 / OUTPUT-STRUCT §Q1 裁决注记 / BACKLOG 全量拉取 5s 性能跟进项。解锁：AM-F1 派工前置仅剩 REQ-PROGRESS-P0 合入 |

## 巡检说明

- P0 实测轮次留痕（2026-09-25 上午，项目方手工派工 Qoder IDE，非巡检产出）：承接昨晚合入 main 的 4 项功能（进度面板 P0 / 决策中心 B1+F1 / DEF-FE-05 / AM-B1 路由），清单 `docs/P0-RETEST-20260925.md`。本轮 **BLOCKED**——pytest 门禁 4 failed / 338 passed 触发「未全绿即停」协议，T1~T5 未执行。缺陷 DEF-RETEST-01~04 已登记（03/04 确定性回归归因 AM-B1 守卫；01/02 待定性，基线保持原样未清理）。反馈包三产物（清单 + `qa-evidence/P0-RETEST-20260925/env/pytest_full_failures.txt` + `feedback_plaintext.txt`）已交项目方。下一步以 RT-P0-FIX 修复单转绿门禁后重跑全量实测。管理员复核补充：① 反馈口径裁决为「直接发、基线原样」，DEF-01/02 定性动作移交工程师在自身 worktree 执行（QA 禁改 data/settings.json）；② 归属勘误——DEF-03/04 红灯自 main 基线 WP-A 提交（c2a1272/24eb45f）即存在，非 bc261e6/9b829b5（不在 main）引入；修复令 + 勘误已于上午注入 AM-B1 会话 c95528c3（= 原 C 选项执行）。

- 回报通道（2026-09-24 23:40 起，项目方批准）：**推模式为主**——工程师在开发群 `messages send --mention 产品经理 --intent request_action` 主动回报（契约交付/完工/卡点三个必报时点），兜底 `session send` 直投产品经理会话；定时巡检降级为**工程师忘回报时的拉模式保险**（REQ-DECISION-CENTER 两单已追发条款；REQ-PROGRESS-P0 暂未追加，仍走纯巡检）。
- 巡检自动任务：QoderWake 平台 automation「派工进度巡检」（tr_08b821764f093472194a49de），2026-09-24 23:42 由项目管理员重建（原产品经理名下任务已失联），每小时整点运行，权限=read-write+network+runCommands（限 git/qoderwake/pytest/python3）。
- 无人值守自治边界（2026-09-24 23:41 项目方拍板）：① **预授权按 AC 验收**——证据齐备且 AC 可机器核验时巡检可直接关单，缺证或口径争议不关单、标 ⚠️ 留痕；② 超 4 小时无进展自动催办 Owner 会话；③ 仅阻塞性异常叫醒项目方（连续两轮无进展、会话卡死、验收争议、范围/排期/跨单冲突需决策）；④ 每天 09:00 出日报追加至本台账。
- 巡检动作：读本表在途行 → `qoderwake session list/detail` 查会话态 → `git fetch` 比对分支 commit → 有变化才更新本行并 commit+push（前缀 `docs(tracker):`）→ 异常（完成未回报 / 运行报错 / 无进展超 4 小时）标 ⚠️ 并在 IM channel 可用时提醒项目方。
- 无变化时静默退出，不产生 commit、不打扰。
- 叫醒通道现状（09-25 07:00 巡检核实）：QoderWake 已接 IM channel 仅「企业微信机器人」`global-tdceqy-wecom-bot`（connected），非钉钉/飞书/Lark 通道，巡检工具链无法向其发消息；钉钉侧 `chat search` 未命中开发群（派工/OpenMeetingScribe 均 0 结果）。故阻塞性异常实际仍只能靠台账留痕，需项目方手工查看或补接可用叫醒通道。
