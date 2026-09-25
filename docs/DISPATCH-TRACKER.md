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
| REQ-PROGRESS-P0 | docs/REQUIREMENT-TRANSCRIBE-PROGRESS-DISPLAY.md v0.3.0（main@7f13a8d） | 前端开发工程师（d1b77737cde5） | session 7ff67e75-b66d-41dc-bcc9-7fcd7375148f / 分支 feat/req-progress-p0（worktree 隔离，origin 顶=本地顶=51d8e85） | **awaiting-acceptance** | 2026-09-25 09:3x：09:13 卡点询问后工程师即回报**选项①完工待验收**（称停摆系回报通道未达、完工回报已于 04:0x 会话内提交过——本巡检仅能证实 04:04 push 动作，会话内回报无法外部核验，不影响本次以新证据为准）。管理员逐条 AC 初审：AC-1/2/4/8/9 **通过**（66min 全程截图+ETA+失败重试链+完成 toast/角标持久化+四步条 tick 序列，33 件证据已随 61871ff 入库）；AC-5（离开恢复/刷新重建）+AC-3 en-US 两项缺证 → 发 RF-P0-1 追证令；AC-6 替代口径获项目方裁决接受（见下行）。**09:50 应询巡检增量：RF-P0-1 补证进行中**——主库 `qa-evidence/req-progress-p0/` 新落 5 件（AC5a 切换前后 3 图+AC5b 刷新重建图+AC3b en-US 面板图，09:21-09:23 写入，未跟踪待工程师自行提交），`AC5_ticks.log` 当前 0 字节（疑仍在产出）；会话 runtimeState=running 活跃。**10:00 巡检：RF-P0-1 六件补证全部齐备可读**——`AC5_ticks.log` 已落 5189 字节（CHECK-1 离开恢复 / CHECK-2 刷新重建 / CHECK-3 en 面板三项 PASS，含 66min 本地任务全程对采序列）；`AC3b_en_text_sample.txt` 附 en locale 全文案采样+无 i18n 泄漏说明（顶栏「处理中」chip 归因主干 f5497f5，非本单范围，建议列 BACKLOG——与 AC-6 侧主干错误文案留痕同口径）；AC5a 三图+AC5b 图完好（09:26-09:29 写入）。分支顶仍=51d8e85，证据 6 件均未跟踪未推送；会话 running 活跃（10:00:46）。缺项仅剩：工程师自行 commit+push 证据并按回报条款提交完工回报。 | 等工程师推送补证 commit + 完工回报 → 管理员终验（AC-3/AC-5 复核证据块）→ 置 browser-acceptance-ready 并发项目方一行验证指引，项目方浏览器点验后关单（解锁 AM-F1 验收前置） | ~~⚠️ RF-P0-1 补证进行中~~ **10:00 已解除**（六件齐备，转等推送+回报；证据仍在工作区未入库，若下轮仍未推送且会话转闲置则按回报条款催办一次）。**AC-6 已裁决（项目方 09-25 批复「接受」）**：本地短音频等效替代通过，裁决落需求文档 §11-Q6，free tier 不可切云留痕。原 05:00 阻塞性异常（停摆+催办无效）**已由工程师响应解除**。已披露偏差留痕：原文整理瞬态<3s 未定格（可接受）；失败卡片英文 suggestion/侧栏错误串为主干既有行为建议另列 BACKLOG（不属本单） |
| REQ-SPK-RN | docs/REQUIREMENT-SPEAKER-REALNAME-DISPLAY.md v0.2.0 | 前端开发工程师（d1b77737cde5） | 待设计稿定稿后开分支 feat/req-spk-rn（worktree 隔离，基于届时 main） | **dispatched（T1 设计阶段）** | 2026-09-25 项目方直接指令：去除全站点位的 Speaker One/Two 编号占位名、显示真实用户信息；管理员完成点位普查并落需求单 v0.1.0（main@9dc02a3），设计派工令已注入工程师会话。**同日项目方追加裁决（需求单升 v0.2.0）**：D5——除可执行用户绑定的位置外，其他位置一律「未识别 N 人」聚合呈现；D6——后端根因修复立项（派生单 REQ-SPK-RN-BE，见下行）。裁决已回注工程师会话收敛设计 | T1 设计稿收敛回报（剩余设计点：Q2 下拉筛选取舍、Q3 派生点位复核、各点位聚合粒度；H3/Q1/Q4 已裁决关闭）→ 管理员初审 → T2 实施排队（与 REQ-PROGRESS-P0 收尾、AM-F1 联排；联调基准=BE-R3 归一化口径）→ T3 浏览器验收包三段式验收 | ⚠️ 同 Owner 三单并行（P0 补证收尾 / AM-F1 队列 / 本单设计），T2 实施顺序待设计稿建议后管理员排期 |
| REQ-SPK-RN-BE | docs/REQUIREMENT-SPEAKER-REALNAME-DISPLAY.md §7（v0.2.0，D6 裁决立项） | 后端工程师（a4cdbd0ca795） | 派工令已注入原会话 c95528c3-7941-4527-8648-ee0275c885d6（同 RT-P0-FIX 模式，不另开会话）/ 实施分支届时基于 main 开 worktree | **dispatched（排队：RT-P0-FIX 在前）** | 2026-09-25 项目方批复 D6「修复后端的根因」即派：三处默认名生成点（`core/pipeline.py:241、252-253` / `core/speakers.py:344` / `core/import_parser.py:277`）停止持久化 Speaker 编号（BE-R1）+ 读取侧归一化公共入口（BE-R3）+ 绑定/声纹回填链路保持（BE-R2）+ 存量数据零改写（BE-R4）；要求先出技术提案再实施 | Owner 应答确认排期 → RT-P0-FIX 转绿后出技术提案 → 管理员初审 → 实施（pytest 全绿门禁 + 三类新用例）→ 浏览器验收包（与 REQ-SPK-RN T2 联调） | ⚠️ 主工作区 `core/pipeline.py` 有已存档未归属 WIP（`qa-evidence/wip-archive/`），禁动现场、必须 worktree 实施；禁改 frontend/（前端点位归 REQ-SPK-RN T2）；BE-R3 归一化模式须与前端过滤口径对齐，单号耦合由管理员联排时标注 |
| AM-B1 | docs/REQUIREMENT-ACCESS-MODE-CARDS.md v0.1.0（main@f2445a1） | 后端工程师（a4cdbd0ca795） | session c95528c3-7941-4527-8648-ee0275c885d6 / 分支 feat/req-access-mode-b1（worktree 隔离，origin 顶=本地顶=9b829b5） | **blocked** | 2026-09-25 09:00 巡检：无新 commit、无完工回报（分支/worktree 进展连续第 3 轮无变化，reflog 无 00:46 后动作）；但**会话状态变化**——runtimeState 由 waiting_input 转 running（resume 进程 pid 80829 于 08:59:37 启动，lastActive 持续跟进，为真实运行非巡检查询抖动；07:00 转 blocked 后约 2h 被重新唤醒），与 RT-P0-FIX 修复令注入时点吻合，运行约 3min 尚未产出可观测进展。**09:50 应询巡检增量：RT-P0-FIX 首 commit 已落**——`286eee9`（09:06，test(llm-selfhost) DEF-RETEST-03/04 用例与本机 settings.json 解耦），分支自 00:46 后首次推进、origin=本地；但为 test-only 增量，DEF-03/04 主体（守卫代码或测试预期定性）未落、清单结果列未回填、pytest 全绿未复核，会话 09:10 后回 waiting_input，无完工回报。**10:00 巡检：会话由 waiting_input 转 running**（lastActive 10:00:56 持续跟进，疑 RT-P0-FIX 主体修复进行中）；分支顶仍=286eee9 无新 commit、无完工回报、pytest 全绿证据未见 | 观察 11:00 轮：等 DEF-03/04 主体 commit/完工回报/pytest 全绿门禁证据；仍无产出→评估是否超 4h 无进展窗口转催办（现距首 commit 09:06 未超阈，巡检侧不催）；仍无动静→维持等项目方拍板（A 人工询问卡点 / B 重新派工，分支基于 39d8b47、未含 main@d92e598）。**09:50 应询巡检更新：进展维度已解锁**（分支自 00:46 后首见新 commit），转等 RT-P0-FIX 完工回报与 pytest 全绿门禁证据 | ⚠️⚠️ 阻塞性异常①（07:00 确认）：催办 1 次（05:00，05:08 触达）后连续两轮无进展且催办无效，需项目方决策。**叫醒受限留痕**：QoderWake 已接 IM channel 仅「企业微信机器人」（global-tdceqy-wecom-bot），非钉钉/飞书/Lark 通道，无法按预授权规则自动发消息叫醒，故仅本台账留痕。已催办 1 次；同工程师两单并行；AM-B1 禁改 frontend/，与 decisions 相关文件冲突需回报协调（DC-DEC-B1 已合入 main@586d141）。巡检注：分支实现基于 39d8b47，未含 main@d92e598（反引号剥除 P2），合入前需 rebase 核验。**09-25 上午 P0-RETEST 增量实证：性质升级**——基线 main 全量 pytest 4 红，其中 DEF-RETEST-03/04 为 `/api/settings/test-llm` localhost 守卫分支的确定性回归（空 Key 误发 `Bearer ollama` 头 / 非 localhost 空 Key 返 `auth_failed` 而非 `missing_key`），自包含用例、与执行机环境无关，直指 bc261e6/9b829b5 守卫实现（PRD R4 约定被破坏）。本单由「完工回报缺失」升级为「实现带确定性回归」，解阻前提改为 RT-P0-FIX 修复单验收，非单纯催办。**归属勘误（09-25 管理员 git 复核，已同步至会话）**：bc261e6/9b829b5 仅在 feat 分支、不在 main，4 红灯复现于 main@fa42d2d 基线；`/api/settings/test-llm` 守卫与 test_llm_selfhost.py 由更早 WP-A 提交（c2a1272/24eb45f）引入 main——DEF-03/04 非 AM-B1 分支回归，排查方向为 main 既有逻辑 vs PRD R4 口径，勿在分支 diff 找因果；修复 commit 可继续落 feat/req-access-mode-b1（合入前本须带绿门禁）。**RT-P0-FIX 派工留痕（09-25 上午）**：项目方确认「可以反馈」，管理员已向原会话 c95528c3 注入修复令+归属勘误（runtimeInputMode=next_turn） |

| AM-F1 | docs/REQUIREMENT-ACCESS-MODE-CARDS.md v0.1.0（main@2599d71） | 前端开发工程师（d1b77737cde5） | session 1659366c-c72b-4871-ac00-19eefe33fbed / 分支 feat/req-access-mode-f1（worktree 隔离，基于开单时 main） | dispatched | 2026-09-25 09:51 派出（T3 三卡片/T4 引导+专家模式/T5 状态栏统一；AM-B1 后端契约 mock 先行，参照 DC-DEC-F1 惯例）。**项目方裁决 B：触发条件放宽**——不等 REQ-PROGRESS-P0 合入，即刻派工 | 契约 mock 定稿/完工群回报 → 管理员验收 AC-T3/T4/T5 + rebase 全绿证据 → 与 AM-B1 联调（D2 toast 接真接口）→ 合入 | ⚠️ 裁决 B 代价条款：与 REQ-PROGRESS-P0 同动导航/状态区，P0 合入后本单须 rebase 且构建全绿方可进验收，合并顺序 P0 优先；同 Owner 多单并行（P0 补证收尾 / 本单 / REQ-SPK-RN 设计），排期冲突由管理员联排 |
| DC-R2-a | docs/REQUIREMENT-DECISION-CENTER-R2.md v0.2.0 §3 F1/F2/F3/F5 + §6 子单（项目方 09-25 裁决 D1「编辑+删除」，一句「派」批准） | 前端开发工程师（d1b77737cde5） | session 1659366c-c72b-4871-ac00-19eefe33fbed / 分支 feat/req-decision-r2a（worktree 隔离，基于 main@04847bb） | **dispatched** | 2026-09-25 12:2x 派工令注入成功（event 417dc574，runtimeInputMode=next_turn，会话 running，与 AM-F1 同会话串行）。四交付项：F1 组内卡片去会议名冗余 / F2 删平铺切换固定分组 / F3 卡片菜单编辑+删除（既有 PUT/DELETE API，无后端改动）/ F5 知识库 combobox | 完工回报 → 管理员 AC 初审（需求单 §5 AC1-4 + 构建全绿 + 边界不破）→ 置 browser-acceptance-ready 发项目方一行验证指引 → 项目方浏览器点验关单 | ⚠️ 边界条款：禁改 AddDecisionDialog 字段结构（F4 三要素=DC-R2-b）、禁动状态枚举与呈现配置（F6=DC-R2-c）、禁改后端与 API 契约；同 Owner 三单并行（AM-F1 / REQ-SPK-RN 设计 / 本单），排期由工程师会话内串行自然消化，管理员按 next_turn 落点巡检 |

## 待派工队列

| 单号 | 派工依据 | 拟 Owner | 触发条件 |
|---|---|---|---|
| DEF-PROXY-02/03 | docs/DEFECT-PROXY-TEST-20260925.md v0.1.0（09-25 项目方实测 464af449：主因=采集静音-91dB 属环境项，先由项目方自查麦克风权限+样音复测；代码项=实时兜底字段未落盘致整单失败 + WAV 落盘时长仅墙钟 1/3） | 后端工程师（a4cdbd0ca795） | 待项目方样音复测结论：仍静音→02/03 即刻派；恢复有声→DEF-PROXY-03 降级为观察项、仅派 02。与 RT-P0-FIX 同域同人，排 RT-P0-FIX 之后同会话串行 |
| DEF-DEVICE-01 | docs/DEFECT-PROXY-TEST-20260925.md §2（09-25 项目方实测：设备选择保存死循环，审计日志实证 10+ 次进设置页零保存 POST；根因 A=前端 watch 初始化守卫吞首次真实变更，确定性；根因 B=后端设计明示不持久化，重启丢） | 前端开发工程师（d1b77737cde5，根因 A） | 根因 A 可即刻派（守卫改显式标志位，与 DC-R2-a 同会话串行）。根因 B（设备选择是否持久化进 settings.json）**待项目方裁决**；裁决「持久化」则拆前后端子单联排 |
| REQ-DECISION-CENTER-R2-b/c（剩余子单） | docs/REQUIREMENT-DECISION-CENTER-R2.md v0.2.0（DC-R2-a 已派，见在途表；剩 F4/F6） | 前端/后端按子单（见需求单 §6） | **DC-R2-b**（F4 三要素，动模型+prompt+API）等 O4（执行人可否留空、纪要主要结论是否改三要素模板）关闭；**DC-R2-c**（F6 状态字典全量自定义）等 O5（新增状态与沉底/取代/默认筛选绑定规则，管理员可先出设计稿圈选）关闭。两单均涉模型层，须与 DC-R2-a / RT-P0-FIX 合入顺序联排，分支 rebase 届时 main |
| AM-Q1 | 同上（T6 回归验证，含存量组合迁移用例=发版门禁） | QA | AM-B1 与 AM-F1 均转 awaiting-acceptance 后触发 |
| RT-P0-FIX | docs/P0-RETEST-20260925.md「缺陷发现」（基线 HEAD=fa42d2d，pytest 4 failed / 338 passed） | 后端工程师（a4cdbd0ca795，与 AM-B1 同人） | **已派（09-25 并入 AM-B1 原会话 c95528c3 注入，不另开会话）**：① 修复 DEF-RETEST-03/04（`/api/settings/test-llm` 空 Key 带头 + `missing_key` 错误码回归，确认改代码还是改测试预期）；② 定性 DEF-RETEST-01/02（在自身 worktree 切 cloud provider 单跑 tests/test_chat.py，区分环境噪声 vs mock/代码回归；主工作区 data/settings.json 禁动）；③ 门禁全绿后重跑 P0-RETEST T1~T5 手工实测。归属以 AM-B1 行勘误为准（守卫为 WP-A 早期既有实现，非 AM-B1 分支回归）。验收标准=pytest 全绿 + 清单结果列回填完毕 |

## 已关闭派工

| 单号 | 关闭时间 | 结果 |
|---|---|---|
| DC-DEC-B1 | 2026-09-25 00:40 | 两轮验收：首轮 RF-1 打回（模板「三、决策」节漏采），23dc21d 修复复验通过（33/33 新用例+84/84 相邻回归本侧独立复跑）。PR #7 squash 合入 main@586d141。R4 已执行（项目方批准 00:24）：382 扫描/56 回填/359 条决策/9 空标记；47 失败经抽查 46 场为旧版格式纪要（无结论/决策章节）、1 场混合节，属真实历史边界非解析缺陷，留决策中心手动补录兜底；报告 data/_backfill_report.json。遗留：AC-1 真实 LLM dogfooding 随后续 5 场真实会议自然验证 |
| DC-DEC-F1 | 2026-09-25 02:20 | 三轮验收：首轮（86c33fd）构建/代码过，RF-F1（** 剥除）+rebase 修复单下达；增量 d181ed2 §12 契约对齐五项通过；修复轮 07aea76 复验通过——stripDecisionEmphasis 仅剥成对 **/__（dq 保留原文、后端不回改、检索双命中），DecisionCard/SupersedeDialog/DecisionFlowPanel 三面接入，本侧独立 worktree 构建全绿，真实后端冒烟证据 dc-f1-20~27（359 条零符号泄漏、补录/取代/撤销/检索/锚点跳转全链路、临时数据清理）。squash 合入 main@714f6cf。备注：分支 merge 实际锚点为 e2c8142（回报写 07d83f7，勘误不影响代码）。交错增量收编：工程师修复轮后续 commit 17f9857 补齐成对反引号剥除（RF-F1 原口径清零，构建复跑全绿，证据 dc-f1-28~30），已 squash 合入 main@d92e598；merge 代 rebase 获产品认可（squash 保 main 线性，分支内部无需重写远端历史）。R5 文档收尾已同步落：GLOSSARY 术语拆分 / VUE_COMPONENT_MAP 路由+组件+api 行 / PRD v1.3.0 / OUTPUT-STRUCT §Q1 裁决注记 / BACKLOG 全量拉取 5s 性能跟进项。解锁：AM-F1 派工前置仅剩 REQ-PROGRESS-P0 合入。**09-25 项目方浏览器补验通过**（决策中心页面，按新验收流对已关单的 DC-DEC-B1/F1 补记最终验收人结论） |

## 日报 2026-09-25（09:00 巡检轮）

- 在途单 2：REQ-PROGRESS-P0（in-progress，仍停摆待拍板）、AM-B1（blocked，RT-P0-FIX 修复令已派回原会话，会话 08:59 转 running，待产出证据）。
- 各单一句话状态：
  - REQ-PROGRESS-P0——无新 commit/无回报（进展连续第 3 轮无变化），维持等待项目方拍板「人工询问卡点 vs 重新派工」，巡检不再重复催办。
  - AM-B1——本身无进展，但会话因 RT-P0-FIX 注入被唤醒转 running；本单解阻前提已改为 RT-P0-FIX 转绿验收。
- 当日验收/关单：无（无单达到可验收条件）。
- 待项目方拍板项：① REQ-PROGRESS-P0 处置方向（人工询问卡点 or 重新派工）；② RT-P0-FIX 已按 C 选项派工，若 10:00 轮仍无工程师应答则评估转 B 重新派工。
- 叫醒通道仍受限（仅企业微信机器人，非钉钉/飞书/Lark），异常全部台账留痕。

## 巡检说明

- **浏览器验收流（2026-09-25 项目方拍板，即日生效）**：项目方为非技术背景，关注结果交付与页面可验证性。规则三条：① 每单派工依据追加硬性交付物「**浏览器验收包**」——涉及页面/入口路径、非技术语言的分步验证脚本（≤5 步）、「什么样算通过」、工程师自测截图；② 验收三段式：工程师完工回报 → 管理员 AC 初审（含 pytest 门禁转绿等技术底线，项目方不感知）→ 置 `browser-acceptance-ready` 并向项目方发一行验证指引（启动命令 + 打开哪个页面 + 看什么）；**项目方浏览器核验通过才关单，管理员不代关**；③ 每日 09:00 日报附「今日可在浏览器验证」清单，项目方按清单点验即可，无需读技术细节。

- P0 实测轮次留痕（2026-09-25 上午，项目方手工派工 Qoder IDE，非巡检产出）：承接昨晚合入 main 的 4 项功能（进度面板 P0 / 决策中心 B1+F1 / DEF-FE-05 / AM-B1 路由），清单 `docs/P0-RETEST-20260925.md`。本轮 **BLOCKED**——pytest 门禁 4 failed / 338 passed 触发「未全绿即停」协议，T1~T5 未执行。缺陷 DEF-RETEST-01~04 已登记（03/04 确定性回归归因 AM-B1 守卫；01/02 待定性，基线保持原样未清理）。反馈包三产物（清单 + `qa-evidence/P0-RETEST-20260925/env/pytest_full_failures.txt` + `feedback_plaintext.txt`）已交项目方。下一步以 RT-P0-FIX 修复单转绿门禁后重跑全量实测。管理员复核补充：① 反馈口径裁决为「直接发、基线原样」，DEF-01/02 定性动作移交工程师在自身 worktree 执行（QA 禁改 data/settings.json）；② 归属勘误——DEF-03/04 红灯自 main 基线 WP-A 提交（c2a1272/24eb45f）即存在，非 bc261e6/9b829b5（不在 main）引入；修复令 + 勘误已于上午注入 AM-B1 会话 c95528c3（= 原 C 选项执行）。**项目方浏览器点验进度（新验收流）**：① 决策中心页面 09-25 通过（见已关闭表 DC-DEC-F1 补验记录）；② T4 本地模式状态栏（DEF-FE-05，main@1926311 早已关闭）09-25 项目方点验通过——页面表现即最终验收，清单 T4.1 的形式化全量重跑随门禁转绿后的重测一并补录销账。

- 回报通道（2026-09-24 23:40 起，项目方批准）：**推模式为主**——工程师在开发群 `messages send --mention 产品经理 --intent request_action` 主动回报（契约交付/完工/卡点三个必报时点），兜底 `session send` 直投产品经理会话；定时巡检降级为**工程师忘回报时的拉模式保险**（REQ-DECISION-CENTER 两单已追发条款；REQ-PROGRESS-P0 暂未追加，仍走纯巡检）。
- 巡检自动任务：QoderWake 平台 automation「派工进度巡检」（tr_08b821764f093472194a49de），2026-09-24 23:42 由项目管理员重建（原产品经理名下任务已失联），每小时整点运行，权限=read-write+network+runCommands（限 git/qoderwake/pytest/python3）。
- 无人值守自治边界（2026-09-24 23:41 项目方拍板）：① **预授权按 AC 验收**——证据齐备且 AC 可机器核验时巡检可直接关单，缺证或口径争议不关单、标 ⚠️ 留痕；② 超 4 小时无进展自动催办 Owner 会话；③ 仅阻塞性异常叫醒项目方（连续两轮无进展、会话卡死、验收争议、范围/排期/跨单冲突需决策）；④ 每天 09:00 出日报追加至本台账。
- 巡检动作：读本表在途行 → `qoderwake session list/detail` 查会话态 → `git fetch` 比对分支 commit → 有变化才更新本行并 commit+push（前缀 `docs(tracker):`）→ 异常（完成未回报 / 运行报错 / 无进展超 4 小时）标 ⚠️ 并在 IM channel 可用时提醒项目方。
- 无变化时静默退出，不产生 commit、不打扰。
- 叫醒通道现状（09-25 07:00 巡检核实）：QoderWake 已接 IM channel 仅「企业微信机器人」`global-tdceqy-wecom-bot`（connected），非钉钉/飞书/Lark 通道，巡检工具链无法向其发消息；钉钉侧 `chat search` 未命中开发群（派工/OpenMeetingScribe 均 0 结果）。故阻塞性异常实际仍只能靠台账留痕，需项目方手工查看或补接可用叫醒通道。
- 项目方授权收口（09-25 09:10，会话内批复「1.同意归档 2.自行推进」）：① **归档已完成**（commit 61871ff）——QA 证据全量入库（12MB）、`data/_backfill_report.json` 入库、`.worktrees/` 加入 gitignore；主工作区 `core/pipeline.py` 一份未归属的工程师 WIP 改动**未合入未切分支**，以 patch + README 存档于 `qa-evidence/wip-archive/`，现场改动保持原样待工程师自处。② **REQ-PROGRESS-P0 卡点询问已发**（09:13 `session send` 至 7ff67e75，项目方预授权由管理员跟进）：限 1 小时内三选一应答（完工待验收/报卡点/无法继续），超时未响应按「重新派工」建议上报项目方。③ RT-P0-FIX 观察窗维持 10:00 巡检轮，无需项目方动作。
