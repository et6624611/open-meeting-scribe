---
title: 派工台账（Dispatch Tracker）
description: 所有在途/关闭派工的单一事实源，原由产品经理维护，2026-09-25 起由 Qoder IDE 承接方接管
version: "1.1.0"
status: active
---

# 派工台账

> 规则：一行一单；状态取值 `dispatched`（已派出）/ `in-progress`（有 commit 进展）/ `awaiting-acceptance`（完成待验收）/ `blocked`（卡住/需决策）/ `closed`（验收合入）。巡检任务仅在**状态或进展变化**时改写本表并留痕；异常在「待关注」列以 ⚠️ 标记，IM channel 接入后同时发消息提醒。

## 在途派工

| 单号 | 派工依据 | Owner | 会话 / 分支 | 状态 | 最近进展（巡检时间） | 下一步 | 待关注 |
|---|---|---|---|---|---|---|---|
| REQ-SPK-RN | docs/REQUIREMENT-SPEAKER-REALNAME-DISPLAY.md v0.2.0 | 前端开发工程师（d1b77737cde5） | 分支 docs/req-spk-rn-t1-design@b159b41（设计稿）；T2 实施届时基于 main 开 feat/req-spk-rn | **initial-review-passed（T2 待派）** | 2026-09-25 IDE 承接轮：管理员初审**通过**（意见书 docs/REVIEW-SPK-RN-T1-BE.md）——T1 设计稿 v0.2.0 点位普查/聚合粒度/Q2 取舍/BE-R3 联调基准全闭环；O1 取数口径钉死（值空+超集正则）；Q2 取舍随 T2 验收自然确认不再单独等待 | 项目方对 IDE 下令派 T2 实施（worktree 基于 main；联调基准=超集正则；AC-8 双侧同正则断言为共同关单条件）→ T3 浏览器验收包三段式验收 | ⚠️ 主工作区 `core/pipeline.py` WIP 已还原现场（归档 patch 在 `qa-evidence/wip-archive/`，需要时 `git apply` 恢复）；T2 涉 pipeline 输出面时须先与该 patch 归属核对避免撞车 |
| REQ-SPK-RN-BE | docs/REQUIREMENT-SPEAKER-REALNAME-DISPLAY.md §7（v0.2.0，D6 裁决立项） | 后端工程师（a4cdbd0ca795） | 实施分支届时基于 main 开 worktree feat/req-spk-rn-be | **proposal-initial-review-passed（实施待派）** | 2026-09-25 IDE 承接轮：技术提案初审**通过**（意见书 docs/REVIEW-SPK-RN-T1-BE.md，提案全文已随 AM-B1 合入 main@qa-evidence/RT-P0-FIX/）——「空字符串=未命名」形态、归一化公共入口、消费方 8 处清单、三类新用例+存量零改写 Prove-It 全认可；**D6 批准**（BE-R3 正则收编超集含单词形态）；**O2 取证完成**（data/tasks 400 文件扫描：数字形态 80/单词形态 0 存量，超集仍采纳作防御）；O3 归 T1 措辞、BE 按保守口径先行 | 项目方对 IDE 下令派实施（按提案 §6 四步：入口+单测→三写入点→消费方切换→回归门禁）；pytest 全绿门禁；不动 frontend/、不动存量数据 | ⚠️ 实施必须 worktree（主工作区禁改 core/pipeline.py 现场约定已解除但保持隔离惯例）；BE-R3 归一化口径与 T2 前端过滤同款超集正则（AC-8） |

## 待派工队列

| 单号 | 派工依据 | 拟 Owner | 触发条件 |
|---|---|---|---|
| DEF-PROXY-02/03 | docs/DEFECT-PROXY-TEST-20260925.md v0.1.0（09-25 项目方实测 464af449：主因=采集静音-91dB 属环境项，先由项目方自查麦克风权限+样音复测；代码项=实时兜底字段未落盘致整单失败 + WAV 落盘时长仅墙钟 1/3） | 后端工程师（a4cdbd0ca795） | 待项目方样音复测结论：仍静音→02/03 即刻派；恢复有声→DEF-PROXY-03 降级为观察项、仅派 02。RT-P0-FIX 已关闭，同人排期约束解除，可同会话串行 |
| DEF-DEVICE-01-BE（持久化子单） | docs/DEFECT-PROXY-TEST-20260925.md v0.3.0 §2 根因 B（项目方 09-25 已裁决：做持久化——设备选择写 settings.json + 启动恢复，优先级 settings>env>平台默认，空串「自动」为合法持久值；根因 A 前端修复已合入 main@cf72154） | 后端工程师（a4cdbd0ca795） | **可即刻派**（RT-P0-FIX 已关闭不再压队）：验收=§2 四条（含重启回显与 env 优先留痕）+ pytest 全绿门禁 | 附带项：tests/app/core __pycache__ 存量已跟踪漂移（.gitignore:29 规则晚于入库），随单一次性 `git rm -r --cached` 解除追踪 |
| REQ-DECISION-CENTER-R2-b/c（剩余子单） | docs/REQUIREMENT-DECISION-CENTER-R2.md v0.2.0（DC-R2-a 已合入 main@14fdfa0；剩 F4/F6） | 前端/后端按子单（见需求单 §6） | **DC-R2-b**（F4 三要素，动模型+prompt+API）等 O4（执行人可否留空、纪要主要结论是否改三要素模板）关闭；**DC-R2-c**（F6 状态字典全量自定义）等 O5（新增状态与沉底/取代/默认筛选绑定规则）关闭。两单涉模型层，分支 rebase 届时 main |
| DC-R2-BE（auto 决策删除墓碑，派生自 DC-R2-a 卡点披露） | docs/REQUIREMENT-DECISION-CENTER-R2.md §5-3 后半句（产品已核实：main `merge_decisions_after_regen` 保留非 auto+全量追加新 auto，无墓碑，删除的 auto 决策重生成必复活） | 后端工程师（a4cdbd0ca795） | **待项目方一句批准**：删除 auto 决策时落 `decision_deletions` 墓碑（task 级），合并时按墓碑过滤 parsed。DC-R2-a 点验已按豁免口径通过（复活半句交本单闭环） |
| AM-Q1 | docs/REQUIREMENT-ACCESS-MODE-CARDS.md（T6 回归验证，含存量组合迁移用例=发版门禁） | QA | **触发条件已满足**（AM-B1 合入 main@b34d663、AM-F1 合入 main@588db7b）：三模式全链路 + §4 存量迁移用例 + 离线不泄露云模型名 + 配额扣减与文案一致；待项目方下令启动 |
| REQ-SPK-RN T2 / REQ-SPK-RN-BE 实施 | 见在途表两单初审通过 + docs/REVIEW-SPK-RN-T1-BE.md 裁决 | 前端/后端对应工程师 | 初审已过，待项目方对 IDE 一句「派」 |

## 已关闭派工

| 单号 | 关闭时间 | 结果 |
|---|---|---|
| DC-DEC-B1 | 2026-09-25 00:40 | 两轮验收：首轮 RF-1 打回（模板「三、决策」节漏采），23dc21d 修复复验通过（33/33 新用例+84/84 相邻回归本侧独立复跑）。PR #7 squash 合入 main@586d141。R4 已执行（项目方批准 00:24）：382 扫描/56 回填/359 条决策/9 空标记；47 失败经抽查 46 场为旧版格式纪要（无结论/决策章节）、1 场混合节，属真实历史边界非解析缺陷，留决策中心手动补录兜底；报告 data/_backfill_report.json。遗留：AC-1 真实 LLM dogfooding 随后续 5 场真实会议自然验证 |
| DC-DEC-F1 | 2026-09-25 02:20 | 三轮验收：首轮（86c33fd）构建/代码过，RF-F1（** 剥除）+rebase 修复单下达；增量 d181ed2 §12 契约对齐五项通过；修复轮 07aea76 复验通过——stripDecisionEmphasis 仅剥成对 **/__（dq 保留原文、后端不回改、检索双命中），DecisionCard/SupersedeDialog/DecisionFlowPanel 三面接入，本侧独立 worktree 构建全绿，真实后端冒烟证据 dc-f1-20~27（359 条零符号泄漏、补录/取代/撤销/检索/锚点跳转全链路、临时数据清理）。squash 合入 main@714f6cf。备注：分支 merge 实际锚点为 e2c8142（回报写 07d83f7，勘误不影响代码）。交错增量收编：工程师修复轮后续 commit 17f9857 补齐成对反引号剥除（RF-F1 原口径清零，构建复跑全绿，证据 dc-f1-28~30），已 squash 合入 main@d92e598；merge 代 rebase 获产品认可（squash 保 main 线性，分支内部无需重写远端历史）。R5 文档收尾已同步落：GLOSSARY 术语拆分 / VUE_COMPONENT_MAP 路由+组件+api 行 / PRD v1.3.0 / OUTPUT-STRUCT §Q1 裁决注记 / BACKLOG 全量拉取 5s 性能跟进项。解锁：AM-F1 派工前置仅剩 REQ-PROGRESS-P0 合入。**09-25 项目方浏览器补验通过**（决策中心页面，按新验收流对已关单的 DC-DEC-B1/F1 补记最终验收人结论） |
| REQ-PROGRESS-P0 | 2026-09-25 13:10 | **IDE 承接轮关单**。项目方授权承接方代跑浏览器点验：Playwright 无头 1440×900 六项全 PASS（四步面板+单调前进+离开恢复无假100%+刷新重建+英文面板零残留零key泄漏+完成态正常退出），证据 qa-evidence/req-progress-p0-ide/（6 截图+metrics.json+selftest 日志）随 52ba415 入库；merge --no-ff 合入 main@a62cd2b，合并后构建全绿。前轮 720px 窄视口「逐字竖排」定性=主干三栏固定宽度总和溢出（layout.css:19 min-width:300 + useContainerSize 档位均主干既有，P0 未触壳布局），非本单回归；主干 i18n 中文残留（顶栏状态 pill「处理中/处理失败」、库页状态列、日期/量词硬编码）维持 BACKLOG 建议（DC-DEC-F1 行同口径留痕） |
| AM-F1 | 2026-09-25 13:20 | **IDE 承接轮关单**。P0 合入后 rebase 至 main@a62cd2b **零冲突**（台账预警的导航/状态区交集未成真），构建全绿；有状态 mock 全链路 selftest（selftest_amf1.py）重跑 **ALL ASSERTIONS PASSED**（AC-T3 三卡片/AC-T4 引导+专家模式/AC-T5 状态收敛五步全覆盖），1440 截图目视三卡片渲染正常；rebase 终验 commit a9d70ed 推送后 merge --no-ff 合入 main@588db7b。观察项裁决留痕：离线模式隐私横幅张力属文案语境项随点验接受。与 AM-B1 联调：AM-B1 合入后 api/access.ts 真接口优先自动切换（零代码），契约级冒烟已过（/api/settings/routing 形状=§13.5、GET 扩展=§13.3、写路径旧字段双写=§13.4），UI 级三模式全链路回归交 AM-Q1 |
| DC-R2-a | 2026-09-25 13:30 | **IDE 承接轮关单**。rebase 至 main 零冲突+构建全绿；selftest_dcr2a.py 21 断言重跑 **ALL PASSED**（纯 mock 通道 VITE_DECISIONS_MOCK=1）。留痕教训：首轮重跑漏设 mock 开关致 /api/decisions 穿透真实后端（误编辑 1 条+误删 1 条决策，已按纪要原文 PUT 还原+POST 重建修复，新 id 3a27b629、source=manual 为已披露偏差）。AC3 后半句（auto 决策重生成复活）按豁免口径关闭，交派生单 DC-R2-BE 闭环。merge --no-ff 合入 main@14fdfa0 |
| DEF-DEVICE-01-A | 2026-09-25 13:40 | **IDE 承接轮关单**。rebase 至 main@14fdfa0（含 AM-F1 设置页改动）后构建全绿；selftest_def01a.py 7 断言 **ALL PASSED**（空值态零 POST→首选择即 POST→回显不冗余→连切连发→刷新回显），与 AM-F1 设置页改造无语义冲突。merge --no-ff 合入 main@cf72154。持久化半边（根因 B）交 DEF-DEVICE-01-BE |
| RT-P0-FIX | 2026-09-25 13:45 | **IDE 承接轮关单**（与 AM-B1 同分支合入）。修复主体 8a0c402 + 回填/详证补交（docs/P0-RETEST-20260925.md 处置回填段 + qa-evidence/RT-P0-FIX/selftest-20260925.md + REQ-SPK-RN-BE-proposal.md）经 rebase 后随 AM-B1 合入 main@b34d663；**main 基线转绿实证**：rebase 后全量 pytest **399 passed / 0 failed**（原 4 红全消，含 RT-P0-FIX 泄漏/干净双条件用例）。DEF-RETEST-01/02 定性（测试非自包含）已随修复收口；P0-RETEST 清单 T1~T5 手工重测由本单转 REQ-PROGRESS-P0/AM-F1/DC-R2-a/DEF-01-A 各单点验实际覆盖，T4 已于 09-25 项目方补验销账，余者以各单浏览器点验证据为终验，清单不再整单重跑（留痕于此） |
| AM-B1 | 2026-09-25 13:45 | **IDE 承接轮关单**。工程师会话已随 QoderWake 收口停用，完工审查由承接方按需求单 AC 初审代偿：AC-T1（access_mode/expert_mode 读写接口+§4 迁移映射 20 用例+旧字段兼容双写）、AC-T2①（grep 级核验 _should_use_cloud/_get_asr_mode 均为薄适配仅委托 core/routing）、AC-T2③（/api/settings/routing 端点 settings.py:424+21 用例）全过；rebase 至 main@cf72154 撞两处冲突均文档级（API_CONTRACTS.md §12/§13 双节保留、P0-RETEST 回填段保留分支侧），解决后全量 pytest **399 passed**；契约冒烟（routing 形状/GET 扩展/写路径双写）实机通过。merge --no-ff 合入 main@b34d663。历史阻塞性异常①（07:00 确认的停摆）随会话收口自然关闭；叫醒通道受限留痕维持原文不再追述 |

## 派工体系收口留痕（2026-09-25 12:07，项目方指令）

项目方决定：**未来开发交由 Qoder IDE 承接，QoderWake 侧派工任务全部收口**。平台自动任务「派工进度巡检」（tr_08b821764f093472194a49de）已停用（回读确认 enabled=false、无后续排程；如需彻底删除由项目方另行指令）。本台账停止自动巡检改写，转为**交接事实源**保留，IDE 侧后续工作按下表接管：

| 遗留项 | 交接状态 | IDE 侧动作 |
|---|---|---|
| REQ-PROGRESS-P0 | browser-acceptance-ready，AC 终验全过，分支顶 b2c2f4a | 项目方浏览器点验（五步指引见在途表）→ 合入 main（P0 优先，解锁 AM-F1） |
| AM-F1 | awaiting-acceptance，首轮验收过（1e5049d） | 点验待 P0 合入后 rebase+全绿构建 → 终验 → 与 AM-B1 联调 |
| DC-R2-a | browser-acceptance-ready，证据已入库（5dd778a） | 点验；AC3 后半句豁免+派生单 DC-R2-BE 待项目方裁决 |
| DEF-DEVICE-01-A | browser-acceptance-ready，证据入库争议已关闭（f43051c） | 项目方五步点验后合入 |
| RT-P0-FIX / AM-B1 | 修复主体已推（8a0c402，pytest 366 passed 入库）；`docs/P0-RETEST-20260925.md` 回填+`qa-evidence/RT-P0-FIX/` 详证**仍在主工作区未入库**，AM-B1 本体无完工回报 | 待归属澄清后补交证据；DEF-RETEST-01/02 定性与 T1~T5 手工重测随 IDE 复测 |
| REQ-SPK-RN / -BE | T1 设计稿（b159b41）与 BE 提案（主工作区未入库）已交付，**管理员初审/O1-O3 联裁未做** | 项目方与 IDE 直接推进，Q2 取舍确认仍在需求单 |
| 待派工队列（DEF-PROXY-02/03、DEF-DEVICE-01-BE、DC-R2-b/c、DC-R2-BE、AM-Q1） | 触发条件与验收口径见各自行 | 是否派工由项目方对 IDE 直接下令 |
| 现场注意 | 主工作区 `core/pipeline.py` 有未归属 WIP（存档 `qa-evidence/wip-archive/`）+ RT-P0-FIX 未入库证据件，**IDE 开工前先处置，勿误提交/误丢弃** | 归属工程师自处或项目方裁决 |

## IDE 承接轮留痕（2026-09-25 13:00-14:00，项目方授权「后续工作你来承接」）

- **点验方式授权**：项目方拍板「承接方代跑浏览器点验，通过后直接合入 main，全程不再打扰」（替代原「项目方浏览器核验通过才关单，管理员不代关」条款，仅对本轮在途单生效）。
- **关单合入 5 单**：REQ-PROGRESS-P0（a62cd2b）→ AM-F1（588db7b）→ DC-R2-a（14fdfa0）→ DEF-DEVICE-01-A（cf72154）→ AM-B1+RT-P0-FIX（b34d663）。合并顺序遵守「P0 优先解锁 AM-F1 rebase」条款；全部 merge --no-ff 保 main 线性可追溯，每单合并后 main 前端构建全绿。
- **main 门禁转绿**：RT-P0-FIX 修复随 AM-B1 入库后全量 pytest **399 passed / 0 failed**（此前 main 基线 4 红）。
- **现场清理**：core/pipeline.py 未归属 WIP 经与归档 patch 逐字节核对一致后还原现场（patch 保留 qa-evidence/wip-archive/ 可随时恢复）；主工作区 6 件 P0 冗余证据副本删除（与 b2c2f4a 入库版 hash 逐一比对一致；微云同步对 PNG 有回填现象，已改 mv 移置 /tmp）；AM-F1 14 件证据补交入库（a4d69c5）；RT-P0-FIX 回填+详证+BE 提案补交入库（a51182c→随 rebase 进 main）。
- **数据误写事故与恢复（诚实留痕）**：DC-R2-a selftest 重跑首轮漏设 `VITE_DECISIONS_MOCK=1`，/api/decisions 穿透 vite 代理写脏真实数据（1 条决策被加测试后缀、1 条被删）——已按纪要原文 PUT 还原+POST 重建，逐键核验恢复；AM-B1 契约冒烟时因 `SETTINGS_FILE=Path("data/settings.json")` 为硬编码相对路径（环境变量仅测试 monkeypatch 有效），联调服务把主工作区 settings 写成 byok/direct——已按 12:20 worktree 快照逐键还原（engine.mode/asr.mode=proxy，迁移新增键移除，llm 段原值未动）。两事故均登记教训，无残留影响。
- **SPK 两单初审**：T1 设计稿与 BE 提案初审通过，D6/O1/O2/O3 裁决落 docs/REVIEW-SPK-RN-T1-BE.md；O2 取证=data/tasks 400 文件扫描（数字形态 80/单词形态 0）。两单实施待项目方一句「派」。
- **待项目方动作**：① 是否派 REQ-SPK-RN T2 + REQ-SPK-RN-BE（初审已过）；② 是否派 DEF-DEVICE-01-BE（可即刻）；③ DC-R2-BE 墓碑单批准；④ AM-Q1 回归启动指令；⑤ DEF-PROXY-02/03 样音复测结论回填。
- 叫醒通道现状（09-25 07:00 巡检核实）：QoderWake 已接 IM channel 仅「企业微信机器人」`global-tdceqy-wecom-bot`（connected），非钉钉/飞书/Lark 通道，巡检工具链无法向其发消息；钉钉侧 `chat search` 未命中开发群（派工/OpenMeetingScribe 均 0 结果）。故阻塞性异常实际仍只能靠台账留痕，需项目方手工查看或补接可用叫醒通道。
- 项目方授权收口（09-25 09:10，会话内批复「1.同意归档 2.自行推进」）：① **归档已完成**（commit 61871ff）——QA 证据全量入库（12MB）、`data/_backfill_report.json` 入库、`.worktrees/` 加入 gitignore；主工作区 `core/pipeline.py` 一份未归属的工程师 WIP 改动**未合入未切分支**，以 patch + README 存档于 `qa-evidence/wip-archive/`，现场改动保持原样待工程师自处。② **REQ-PROGRESS-P0 卡点询问已发**（09:13 `session send` 至 7ff67e75，项目方预授权由管理员跟进）：限 1 小时内三选一应答（完工待验收/报卡点/无法继续），超时未响应按「重新派工」建议上报项目方。③ RT-P0-FIX 观察窗维持 10:00 巡检轮，无需项目方动作。

## 巡检说明

- **浏览器验收流（2026-09-25 项目方拍板，即日生效）**：项目方为非技术背景，关注结果交付与页面可验证性。规则三条：① 每单派工依据追加硬性交付物「**浏览器验收包**」——涉及页面/入口路径、非技术语言的分步验证脚本（≤5 步）、「什么样算通过」、工程师自测截图；② 验收三段式：工程师完工回报 → 管理员 AC 初审（含 pytest 门禁转绿等技术底线，项目方不感知）→ 置 `browser-acceptance-ready` 并向项目方发一行验证指引（启动命令 + 打开哪个页面 + 看什么）；**项目方浏览器核验通过才关单，管理员不代关**；③ 每日 09:00 日报附「今日可在浏览器验证」清单，项目方按清单点验即可，无需读技术细节。IDE 承接轮补充（09-25 13:00 项目方授权）：承接方可代跑点验（Playwright 无头 1440×900 截图+量化断言），通过后直接合入。

- P0 实测轮次留痕（2026-09-25 上午，项目方手工派工 Qoder IDE，非巡检产出）：承接昨晚合入 main 的 4 项功能（进度面板 P0 / 决策中心 B1+F1 / DEF-FE-05 / AM-B1 路由），清单 `docs/P0-RETEST-20260925.md`。本轮 **BLOCKED**——pytest 门禁 4 failed / 338 passed 触发「未全绿即停」协议，T1~T5 未执行。缺陷 DEF-RETEST-01~04 已登记（03/04 确定性回归归因 AM-B1 守卫；01/02 待定性，基线保持原样未清理）。反馈包三产物（清单 + `qa-evidence/P0-RETEST-20260925/env/pytest_full_failures.txt` + `feedback_plaintext.txt`）已交项目方。下一步以 RT-P0-FIX 修复单转绿门禁后重跑全量实测。管理员复核补充：① 反馈口径裁决为「直接发、基线原样」，DEF-01/02 定性动作移交工程师在自身 worktree 执行（QA 禁改 data/settings.json）；② 归属勘误——DEF-03/04 红灯自 main 基线 WP-A 提交（c2a1272/24eb45f）即存在，非 bc261e6/9b829b5（不在 main）引入；修复令 + 勘误已于上午注入 AM-B1 会话 c95528c3（= 原 C 选项执行）。**项目方浏览器点验进度（新验收流）**：① 决策中心页面 09-25 通过（见已关闭表 DC-DEC-F1 补验记录）；② T4 本地模式状态栏（DEF-FE-05，main@1926311 早已关闭）09-25 项目方点验通过——页面表现即最终验收，清单 T4.1 的形式化全量重跑随门禁转绿后的重测一并补录销账。

- 回报通道（2026-09-24 23:40 起，项目方批准）：**推模式为主**——工程师在开发群 `messages send --mention 产品经理 --intent request_action` 主动回报（契约交付/完工/卡点三个必报时点），兜底 `session send` 直投产品经理会话；定时巡检降级为**工程师忘回报时的拉模式保险**（REQ-DECISION-CENTER 两单已追发条款；REQ-PROGRESS-P0 暂未追加，仍走纯巡检）。
- 巡检自动任务：QoderWake 平台 automation「派工进度巡检」（tr_08b821764f093472194a49de），2026-09-24 23:42 由项目管理员重建（原产品经理名下任务已失联），每小时整点运行，权限=read-write+network+runCommands（限 git/qoderwake/pytest/python3）。
- 无人值守自治边界（2026-09-24 23:41 项目方拍板）：① **预授权按 AC 验收**——证据齐备且 AC 可机器核验时巡检可直接关单，缺证或口径争议不关单、标 ⚠️ 留痕；② 超 4 小时无进展自动催办 Owner 会话；③ 仅阻塞性异常叫醒项目方（连续两轮无进展、会话卡死、验收争议、范围/排期/跨单冲突需决策）；④ 每天 09:00 出日报追加至本台账。
- 巡检动作：读本表在途行 → `qoderwake session list/detail` 查会话态 → `git fetch` 比对分支 commit → 有变化才更新本行并 commit+push（前缀 `docs(tracker):`）→ 异常（完成未回报 / 运行报错 / 无进展超 4 小时）标 ⚠️ 并在 IM channel 可用时提醒项目方。
- 无变化时静默退出，不产生 commit、不打扰。
