---
title: 派工台账（Dispatch Tracker）
description: 所有在途/关闭派工的单一事实源，原由产品经理维护，2026-09-25 起由 Qoder IDE 承接方接管
version: "1.2.0"
status: active
---

# 派工台账

> 规则：一行一单；状态取值 `dispatched`（已派出）/ `in-progress`（有 commit 进展）/ `awaiting-acceptance`（完成待验收）/ `blocked`（卡住/需决策）/ `closed`（验收合入）。巡检任务仅在**状态或进展变化**时改写本表并留痕；异常在「待关注」列以 ⚠️ 标记，IM channel 接入后同时发消息提醒。

## 在途派工

（2026-09-26 起仅恢复**产品评审通道**个案派工；开发派工维持 IDE 承接，见「派工体系收口留痕」节）

| 单号 | 派工依据 | Owner | 会话 / 分支 | 状态 | 最近进展（巡检时间） | 下一步 | 待关注 |
|---|---|---|---|---|---|---|---|

## 待派工队列

| 单号 | 派工依据 | 拟 Owner | 触发条件 |
|---|---|---|---|
| DEF-PROXY-03 终判（观察项，代码已交） | qa-evidence/def-proxy-0203/proxy03-qualification.md（代码层排除+偏差自检已上线） | 项目方（样音复测）/ 后端（若留痕再现） | 项目方有声样音录制后看任务 JSON 是否出现 wav_wallclock_gap_sec：无→按观察项关闭；有→携留痕开代码修复单 |

（REQ-DECISION-CENTER-R2 六条反馈已随 DC-R2-a / -BE / -b / -c 四单全部闭环，队列内无决策中心剩单）

## 已关闭派工

| 单号 | 关闭时间 | 结果 |
|---|---|---|
| REQ-SETTINGS-IA | 2026-09-26 | **IDE 承接轮交付（待点验）**。五刀全部落地：① 决策两卡+六详情卡+后果预览（联网→离线需勾选知晓，裁决-2）+切换事务端点 POST /api/settings/access-mode 失败全量回滚（裁决-1，零写入用例钉死）；② 卡片内联自动保存面板/声纹 provider 选择器/引擎页可写 dropdown 全废，服务页为参数唯一编辑面，反向同步降级为「仅投影字段真实变化时重对齐」带日落日志；③ 五词表收敛（托管/体验代理/自持 Key/自接端点/平台代理/降级全量清退，幽灵枚举 engine_mode_cloud 随删，流向矩阵搬入接入方式页四列逐能力高亮+出网双通道徽章，GLOSSARY v1.4.0 历史映射注记）；④ 声纹云端下架（CloudEmbeddingProvider/schema 字段/UI 区块/后端读写全删，结构性零出网）；**前置闸结论（Dev 评估代录）**：注册表存本机 data/voiceprint_registry.json，存量 cam++-v1-cloud 标记经 COMPATIBLE_VERSIONS 与本机 cam++-v1 同空间互兼容（ADR-0009，同片段 cos=1.0 实证）——**无用户数据迁移**，启动迁移仅丢弃设置键；⑤ prefer_subscription 降为账户默认勾选（三态徽章+覆盖持久化+route_override 静默语义消灭，自动改用三级提示 L1/L2/L3+10分钟预警+core/settings_events.py 本地事件记录；Q4 未裁——能力卡标「共用同一额度池」）。存量迁移 local/hosted/byok/null/混配全组合单测+实机验证通过；pytest 580 全绿；前端构建部署+服务重启完成。AC-5/6/7 浏览器点验交 QA 通道，产品侧出验收单 |
| REQ-EXPERT-MODE | 2026-09-26 | **IDE 承接轮交付（待点验，与 SETTINGS-IA 同轮串行落地）**。专家开关移出 radiogroup 成页面级 role=switch（aria-checked+Space/Enter），radiogroup 仅两卡 ←/→ roving；开启=同 DOM 叠注释层（决策卡/六详情卡工程值行 `engine.mode ▸ local` 式、矩阵工程值副行、无平行视图）；导航 L0→L5 重排（账户→接入→服务→引擎→**CLI 引擎新分类页**），本地资产就绪度前置离线卡+直达清单，CLI 探针三段（probe.py 新增 failed_stage 定位）在详情卡与对话面板双前置回显，智能体未就绪置灰+指引；tierName 去写死改读真实档位（未知档降级显原值）；会话级模型选择器（默认跟随详情，候选标来源，engine store 共享态与使用面回显卡联动）+后端 model 缺省改读 llm.model+done 事件携 model_usage 消费方/计费回显（与 routing 同源）；字号门禁（≥12px 静态检查等）入 tests/test_expert_mode.py，全量 580 绿。AC-1/2/3/4 键盘走查/axe 对比度/选模型实发点验交 QA 通道 |
| UI-REVIEW-SETTINGS-IA-01 | 2026-09-26 | **评审通道个案关单（产品验收）**。UI 设计师交付 docs/REVIEW-UI-SETTINGS-IA-REPORT.md（R1-R6 三态结论 + 1 阻塞项 + 附录 B 勘误表）。阻塞项（① 问题 2 演示与 embedding_provider.py:518-530 离线短路相反）派工人独立复核确认成立。逐项处置：21 条修改建议采纳 20、部分采纳 1（R6-4 矩阵改四列含「本机端点」单列，保留窄屏可读性意见）；原型升 **v4**（勘误版问题 2 重写、附录 B 行号全修、对比度令牌 --warn #8a5800/--subtle #6b7382、三态徽章、离线态 setPsub 守卫、role/aria + roving tabindex、弹窗字段 diff/失败态/动态确认文案、②页现状-建议-未来风险 chip、上下步导航、双写模拟器字段集并排 + 清空 Key 演示、词汇五词收敛）。验收回应 docs/REVIEW-UI-SETTINGS-IA-ACCEPTANCE.md。node --check + id/function 交叉校验全过。**遗留转产品侧**：项目方已于 09-26 会话内终裁 7 项（Q1=联网模式、裁决-1=全量回滚、裁决-2=联网→离线更强确认、裁决-3=允许例外+判据措辞、裁决-4=五词表、裁决-5=无障碍产品级规则、Q3=三级 amber 提示），Q2/Q4-Q7 共 5 项随需求单登记继续追踪；声纹注册表迁移需 Dev 确认后需求单方可写「无用户数据迁移」。**后续（同日）**：项目方「批准实施」，REQ-SETTINGS-IA v0.2.0 + REQ-EXPERT-MODE v0.2.0 已登记入待派工队列，本轮全部产出（原型 v4/评审三文档/两需求单/台账）随登记 commit 入库 |
| DC-DEC-B1 | 2026-09-25 00:40 | 两轮验收：首轮 RF-1 打回（模板「三、决策」节漏采），23dc21d 修复复验通过（33/33 新用例+84/84 相邻回归本侧独立复跑）。PR #7 squash 合入 main@586d141。R4 已执行（项目方批准 00:24）：382 扫描/56 回填/359 条决策/9 空标记；47 失败经抽查 46 场为旧版格式纪要（无结论/决策章节）、1 场混合节，属真实历史边界非解析缺陷，留决策中心手动补录兜底；报告 data/_backfill_report.json。遗留：AC-1 真实 LLM dogfooding 随后续 5 场真实会议自然验证 |
| DC-DEC-F1 | 2026-09-25 02:20 | 三轮验收：首轮（86c33fd）构建/代码过，RF-F1（** 剥除）+rebase 修复单下达；增量 d181ed2 §12 契约对齐五项通过；修复轮 07aea76 复验通过——stripDecisionEmphasis 仅剥成对 **/__（dq 保留原文、后端不回改、检索双命中），DecisionCard/SupersedeDialog/DecisionFlowPanel 三面接入，本侧独立 worktree 构建全绿，真实后端冒烟证据 dc-f1-20~27（359 条零符号泄漏、补录/取代/撤销/检索/锚点跳转全链路、临时数据清理）。squash 合入 main@714f6cf。备注：分支 merge 实际锚点为 e2c8142（回报写 07d83f7，勘误不影响代码）。交错增量收编：工程师修复轮后续 commit 17f9857 补齐成对反引号剥除（RF-F1 原口径清零，构建复跑全绿，证据 dc-f1-28~30），已 squash 合入 main@d92e598；merge 代 rebase 获产品认可（squash 保 main 线性，分支内部无需重写远端历史）。R5 文档收尾已同步落：GLOSSARY 术语拆分 / VUE_COMPONENT_MAP 路由+组件+api 行 / PRD v1.3.0 / OUTPUT-STRUCT §Q1 裁决注记 / BACKLOG 全量拉取 5s 性能跟进项。解锁：AM-F1 派工前置仅剩 REQ-PROGRESS-P0 合入。**09-25 项目方浏览器补验通过**（决策中心页面，按新验收流对已关单的 DC-DEC-B1/F1 补记最终验收人结论） |
| REQ-PROGRESS-P0 | 2026-09-25 13:10 | **IDE 承接轮关单**。项目方授权承接方代跑浏览器点验：Playwright 无头 1440×900 六项全 PASS（四步面板+单调前进+离开恢复无假100%+刷新重建+英文面板零残留零key泄漏+完成态正常退出），证据 qa-evidence/req-progress-p0-ide/（6 截图+metrics.json+selftest 日志）随 52ba415 入库；merge --no-ff 合入 main@a62cd2b，合并后构建全绿。前轮 720px 窄视口「逐字竖排」定性=主干三栏固定宽度总和溢出（layout.css:19 min-width:300 + useContainerSize 档位均主干既有，P0 未触壳布局），非本单回归；主干 i18n 中文残留（顶栏状态 pill「处理中/处理失败」、库页状态列、日期/量词硬编码）维持 BACKLOG 建议（DC-DEC-F1 行同口径留痕） |
| AM-F1 | 2026-09-25 13:20 | **IDE 承接轮关单**。P0 合入后 rebase 至 main@a62cd2b **零冲突**（台账预警的导航/状态区交集未成真），构建全绿；有状态 mock 全链路 selftest（selftest_amf1.py）重跑 **ALL ASSERTIONS PASSED**（AC-T3 三卡片/AC-T4 引导+专家模式/AC-T5 状态收敛五步全覆盖），1440 截图目视三卡片渲染正常；rebase 终验 commit a9d70ed 推送后 merge --no-ff 合入 main@588db7b。观察项裁决留痕：离线模式隐私横幅张力属文案语境项随点验接受。与 AM-B1 联调：AM-B1 合入后 api/access.ts 真接口优先自动切换（零代码），契约级冒烟已过（/api/settings/routing 形状=§13.5、GET 扩展=§13.3、写路径旧字段双写=§13.4），UI 级三模式全链路回归交 AM-Q1 |
| DC-R2-a | 2026-09-25 13:30 | **IDE 承接轮关单**。rebase 至 main 零冲突+构建全绿；selftest_dcr2a.py 21 断言重跑 **ALL PASSED**（纯 mock 通道 VITE_DECISIONS_MOCK=1）。留痕教训：首轮重跑漏设 mock 开关致 /api/decisions 穿透真实后端（误编辑 1 条+误删 1 条决策，已按纪要原文 PUT 还原+POST 重建修复，新 id 3a27b629、source=manual 为已披露偏差）。AC3 后半句（auto 决策重生成复活）按豁免口径关闭，交派生单 DC-R2-BE 闭环。merge --no-ff 合入 main@14fdfa0 |
| DEF-DEVICE-01-A | 2026-09-25 13:40 | **IDE 承接轮关单**。rebase 至 main@14fdfa0（含 AM-F1 设置页改动）后构建全绿；selftest_def01a.py 7 断言 **ALL PASSED**（空值态零 POST→首选择即 POST→回显不冗余→连切连发→刷新回显），与 AM-F1 设置页改造无语义冲突。merge --no-ff 合入 main@cf72154。持久化半边（根因 B）交 DEF-DEVICE-01-BE |
| RT-P0-FIX | 2026-09-25 13:45 | **IDE 承接轮关单**（与 AM-B1 同分支合入）。修复主体 8a0c402 + 回填/详证补交（docs/P0-RETEST-20260925.md 处置回填段 + qa-evidence/RT-P0-FIX/selftest-20260925.md + REQ-SPK-RN-BE-proposal.md）经 rebase 后随 AM-B1 合入 main@b34d663；**main 基线转绿实证**：rebase 后全量 pytest **399 passed / 0 failed**（原 4 红全消，含 RT-P0-FIX 泄漏/干净双条件用例）。DEF-RETEST-01/02 定性（测试非自包含）已随修复收口；P0-RETEST 清单 T1~T5 手工重测由本单转 REQ-PROGRESS-P0/AM-F1/DC-R2-a/DEF-01-A 各单点验实际覆盖，T4 已于 09-25 项目方补验销账，余者以各单浏览器点验证据为终验，清单不再整单重跑（留痕于此） |
| AM-B1 | 2026-09-25 13:45 | **IDE 承接轮关单**。工程师会话已随 QoderWake 收口停用，完工审查由承接方按需求单 AC 初审代偿：AC-T1（access_mode/expert_mode 读写接口+§4 迁移映射 20 用例+旧字段兼容双写）、AC-T2①（grep 级核验 _should_use_cloud/_get_asr_mode 均为薄适配仅委托 core/routing）、AC-T2③（/api/settings/routing 端点 settings.py:424+21 用例）全过；rebase 至 main@cf72154 撞两处冲突均文档级（API_CONTRACTS.md §12/§13 双节保留、P0-RETEST 回填段保留分支侧），解决后全量 pytest **399 passed**；契约冒烟（routing 形状/GET 扩展/写路径双写）实机通过。merge --no-ff 合入 main@b34d663。历史阻塞性异常①（07:00 确认的停摆）随会话收口自然关闭；叫醒通道受限留痕维持原文不再追述 |
| REQ-SPK-RN-BE | 2026-09-25 17:40 | **IDE 承接第二轮（项目方「全做」）关单**。按提案 §6 四步实施：BE-R1 三写入点收口（pipeline 键保留值留空/apply_speaker_names 查不到→空串/import_parser 模式3 编号仅归组不落名）；BE-R3 归一化唯一入口 is_unnamed_speaker/normalize_speaker_mapping（D6 超集正则：数字+One..Ten 词形+中文两式，整串锚定不误伤含号真名），消费方 8 处切换（summarize×4/chapters/projects/chat×4/text_bridge 防御位）；BE-R2 绑定回填不变量保持；BE-R4 存量零改写 Prove-It 守护。36 新用例，全量 434 绿。merge --no-ff 合入 main@ee355be |
| REQ-SPK-RN | 2026-09-25 17:50 | **IDE 承接第二轮关单（T2+T3 一并落地）**。判定器 utils/speakerDisplay.ts 与 BE 同源超集；α 聚合位（TaskCard 未识别 N chip/库页下拉真名⊕「未识别」特殊项 Q2 保留口径/列尾聚合项/转写行首中性化/roster L3-L4 收敛/搜索 L9 占位不可搜）+β 绑定位（说话人区/绑定下拉/管理页灰标）+L2 写库源头必填守卫（AC-7）；i18n 去编号插值+onboarding 演示名小李/小王。selftest_spkrn.py **18 断言 ALL PASSED**（全量 mock 零真实后端接触）+4 页截图；AC-8 双侧同正则矩阵两侧钉死一致。构建全绿，merge 合入 main@2d2c54a。已披露偏差：useAiChat/useAiGuidance 硬编码「发言人」建议文案 i18n 化（§7 顺路小项不违 H1）挂 BACKLOG；录制页 WS 实时行为需真麦环境未跑（静态点位同 util 已覆盖） |
| DEF-DEVICE-01-BE | 2026-09-25 18:00 | **IDE 承接第二轮关单**。POST /api/record/device 成功即写 settings.json（复用 settings_store 原子写）；启动按「settings>env>平台默认」恢复（**需求矛盾处置**：验收④原文「env 优先」与裁决正文「settings>env」冲突，按项目方裁决正文为准，验收④修订为优先级判定留痕——启动日志落来源标记）；空串「自动」合法持久值；持久化失败降级不阻断。6 新用例全量 440 绿。附带项 __pycache__ 解除跟踪核查 0 存量（61871ff 轮已完成）。merge 合入 main@dcbaa89。验收③真机重启回显交项目方日常使用中自然确认 |
| DC-R2-BE | 2026-09-25 18:05 | **IDE 承接第二轮关单**（项目方「全做」即批准）。task 级 decision_deletions 墓碑：DELETE auto 决策落碑（归一化文本为身份键——auto id 每次重解析会变；幂等去重），merge_decisions_after_regen 加可选 deletions 参按碑过滤 parsed（缺省两参调用向后兼容），管线重生成/导入重解析两处接入；用户改表述新文本不被误杀；非 auto 不建碑。5 新用例全量 445 绿。merge 合入 main@6ff05c7，DC-R2-a 豁免的 AC3 后半句就此闭环 |
| DEF-PROXY-02 | 2026-09-25 18:15 | **IDE 承接第二轮关单**。根因=stop 竞态：pop 全量转写后 SDK 线程迟到定稿经 setdefault 落孤儿列表丢失→兑底静默跳过整单失败。修复=stop 时空列表也绑定引用+登记 realtime_full_sealed，迟到句 append 进 task 持有的同一列表；僵尸/放弃路径同步清封存。验收命中：静音+有实时句→transcript_source=realtime_fallback 降级出纪要（用例钉死）+stop 竞态用例。merge 合入 main@59bcba1 |
| DEF-PROXY-03 | 2026-09-25 18:15 | **代码部分交付，终判转观察项**（与 02 同单合入 59bcba1）。定性实验（qa-evidence/def-proxy-0203/proxy03-qualification.md）：lavfi 已知输入证明 aresample+asplit 链时长忠实；真机复采未见 3.17x 结构性欠采（差值≈启停固定开销）；avfoundation 不接受 rate 声明参数——排除代码层，原缺陷与权限静音时钟异常同根可能性高。交付观测：WAV 时长 vs 墙钟偏差>15% 自动留痕 wav_wallclock_gap_sec+WARNING，待项目方样音复测终判 |
| AM-Q1 | 2026-09-25 18:25 | **IDE 承接第二轮执行完毕**。报告 qa-evidence/AM-Q1/REPORT.md：②迁移 41 用例全绿；① hosted 实测 completed、byok 实测 byok_key_missing→cloud 契约回退路径端到端（direct 分支无用户 Key 由用例矩阵覆盖）、local 本机模型未部署 NOT RUN 披露（替代：DEF-FE-05 已验收 UI+WP-C 评测管线）；③④沿用已验收项。**门禁判定：可发版**（无阻塞性缺陷，两项环境限制已披露） |
| DC-R2-b | 2026-09-25 19:12 | **IDE 承接第三轮关单**（项目方二轮裁决 D4/D5 后直派）。三要素落库：`decisions[]` 新增 title / owner_id / owner_name，text 语义收窄为内容；**执行人选人不选文本**（OwnerSelectCombobox：可搜档案 + 无同名手打即时建档 + 不指派出口），owner_id 为权威、改名全局跟随且不批量重写存量 JSON；占位档案名 Speaker N 不入候选。纪要「主要结论」prompt 改「**短标题**：正文」条目式（D5：AI 只要标题+正文，owner 合法留空）；split_decision_title 宽容拆分不丢条目。聚合契约修正：行内 title=决策标题、会议标题改发 meeting_title（分组 label/组头同步）；q 命中标题；PUT 下 owner 空串=清空指派。30 新用例 + Playwright 24 断言 ALL PASSED（qa-evidence/req-decision-r2b/）。merge 合入 main@0b5eb18 |
| DC-R2-c | 2026-09-25 19:54 | **IDE 承接第三轮关单**（D6/D7 裁决后直派）。新增 `core/decision_status.py` + `/api/decision-statuses` CRUD/reorder（`data/decision_statuses.json` 已 gitignore，首次读取即迁移）；**系统锚点收敛为生效中+完成**（不可改名不可删，后端强校验 + 前端输入只读/删除禁用）；取代/撤销下线（菜单两项入口移除、SupersedeDialog 删除、PATCH supersede 端点摘除，superseded_by 停写、存量只读降级）。**存量零改写**：历史 superseded/revoked 迁移为两个可编辑普通状态（默认闭档）。D7：`closing` 逐状态勾选，默认视图=非闭档全集（前端本地筛选）+「查看全部」一键放宽；`pending_confirmation` 维持标志位。删状态时引用决策当场回落 active 并逐任务落盘。聚合行随行下发 status_name/name_en/color/closing，徽标·色点·沉底全配置驱动。12 新用例 + Playwright 30 断言 ALL PASSED（qa-evidence/req-decision-r2c/）。merge 合入 main@333cbf9 |

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
- **合并后门禁复验与测试自包含修复**：main 合入链末端本地全量 pytest 首跑 1 failed（`TestLocalRouting::test_get_asr_mode_returns_local_when_engine_local`）——定性=非自包含用例（AM-B1 后 `_get_asr_mode` 经 `core/routing` 先读 access_mode，本机 `data/settings.json` 已被启动迁移钩子合法写入 `access_mode=hosted`，短路进 hosted 分支绕过用例要验的 legacy engine.mode 判定；CI 干净环境无 settings 文件故不现）。已按 `test_llm_selfhost` 隔离夹具口径补 `SETTINGS_FILE` monkeypatch（e573647），本地全量 **399 passed / 0 failed** 复验；Ruff CI 口径（F821,F811,F402）本地全过。main 终态链：a62cd2b→588db7b→14fdfa0→cf72154→b34d663→fbbc106→e573647。
- **待项目方动作**：① 是否派 REQ-SPK-RN T2 + REQ-SPK-RN-BE（初审已过）；② 是否派 DEF-DEVICE-01-BE（可即刻）；③ DC-R2-BE 墓碑单批准；④ AM-Q1 回归启动指令；⑤ DEF-PROXY-02/03 样音复测结论回填。
- 叫醒通道现状（09-25 07:00 巡检核实）：QoderWake 已接 IM channel 仅「企业微信机器人」`global-tdceqy-wecom-bot`（connected），非钉钉/飞书/Lark 通道，巡检工具链无法向其发消息；钉钉侧 `chat search` 未命中开发群（派工/OpenMeetingScribe 均 0 结果）。故阻塞性异常实际仍只能靠台账留痕，需项目方手工查看或补接可用叫醒通道。
- 项目方授权收口（09-25 09:10，会话内批复「1.同意归档 2.自行推进」）：① **归档已完成**（commit 61871ff）——QA 证据全量入库（12MB）、`data/_backfill_report.json` 入库、`.worktrees/` 加入 gitignore；主工作区 `core/pipeline.py` 一份未归属的工程师 WIP 改动**未合入未切分支**，以 patch + README 存档于 `qa-evidence/wip-archive/`，现场改动保持原样待工程师自处。② **REQ-PROGRESS-P0 卡点询问已发**（09:13 `session send` 至 7ff67e75，项目方预授权由管理员跟进）：限 1 小时内三选一应答（完工待验收/报卡点/无法继续），超时未响应按「重新派工」建议上报项目方。③ RT-P0-FIX 观察窗维持 10:00 巡检轮，无需项目方动作。

## IDE 承接第二轮留痕（2026-09-25 15:30-18:30，项目方对五个待决事项批复「全做」）

- **六单全部执行并合入 main**，链：ee355be（REQ-SPK-RN-BE）→ 2d2c54a（REQ-SPK-RN T2）→ dcbaa89（DEF-DEVICE-01-BE）→ 6ff05c7（DC-R2-BE）→ 59bcba1（DEF-PROXY-02/03）；AM-Q1 回归报告 qa-evidence/AM-Q1/REPORT.md 判定可发版。新用例累计 +52（36+6+5+7 另 T2 自测 18 断言），每单合入前全量 pytest 绿（434→440→445→447）+前端构建绿。
- **需求矛盾处置**：① DEF-DEVICE-01-BE 验收④与裁决正文优先级冲突→按裁决（settings>env）并留痕；② DC-R2-BE 碑键=归一化文本（派工单字面「按墓碑过滤 parsed」未定形态，auto id 不稳定故 id 方案不可行）；③ AM-Q1 local/byok-direct 两项环境限制如实披露不强行判绿。
- **现场安全**：本轮发现主工作区存在**另一活跃会话的未提交 WIP**（Qoder CLI 引擎方向：chat.py/settings.py/settings_store.py/store.py/.gitignore + core/cli_engine/ 等）——DEF-PROXY-0203 合入时仅 stash 让路 store.py 单文件并即时 pop 还原（auto-merge 成功），全程未提交/未丢弃他人现场；后续操作一律显式路径 add。
- **网络抖动手记**：GitHub SSH 22 端口两次超时，改用 ssh.github.com:443 通道完成推送（T2/DC-R2-BE 两笔）；known_hosts 已自动登记 443 指纹（与 github.com 官方 ED25519 一致）。
- **剩余待决**：仅 DC-R2-b/c（需项目方先关 O4/O5 设计问题）与 DEF-PROXY-03 样音终判（项目方日常录制即自动留痕，无需专门复测动作）。

## IDE 承接第三轮留痕（2026-09-25 18:45-19:59，项目方给出 O4/O5 二轮裁决 D4-D7）

- **裁决内容**：D4 执行人改为选说话人档案（可手打即时建档）；D5 AI 生成决策只要标题+正文（纪要主要结论接受条目式模板）；D6 **只固定「完成」为系统保底，其余全由用户定义**，并明确选择「砍掉取代/撤销两项」（知情：属删除已点验上线的能力）；D7 默认视图只看非完成类、新状态逐项勾选「算完成类」、`[待确认]` 维持标志位。裁决已回写需求单 v0.3.0（§4 O4/O5 转 closed、§5 验收定稿、§11 二轮裁决）。
- **两单均已执行合入 main**，链：0b5eb18（DC-R2-b）→ 333cbf9（DC-R2-c）；新用例 +42（30+12），浏览器断言 +54（24+30），每单合入前全量 pytest 绿（475→487）+ vue-tsc 构建绿 + Ruff CI 口径（F821,F811,F402）绿。
- **实施方追加的兜底（未扩大功能面，已留痕）**：① 存量 superseded/revoked 迁移为可编辑普通状态而非直接抹除（数据诚实）；② `superseded_by` 保留只读展示；③ 排序以「上移/下移」按钮实现而非拖拽（需求原文写「拖拽排序」，F6 定稿已改为「排序」）。
- **契约变更两处（下游需知）**：聚合行 `title` 语义从会议标题改为决策标题，会议标题改走 `meeting_title`；`/api/decisions` 的 `status` 参数从枚举改为状态字典 id（非法值 422），且默认视图筛选下沉到前端本地完成。
- **现场安全（延续第二轮口径）**：主工作区仍有另一活跃会话的未提交 WIP（Qoder CLI 引擎 + 洞察台会后化：chat.py/server.py/settings.py/settings_store.py/.gitignore/API_CONTRACTS §14/CHANGELOG 等）。DC-R2-c 合入时 stash 让路 server.py + .gitignore + API_CONTRACTS.md 三个交集文件，merge 后即时 pop 还原（auto-merge 成功，双方改动共存已核对：§12.4 与 §14 均在位、两条 gitignore 条目均在位），全程未提交未丢弃他人现场。
- **已知环内噪声（非本轮引入）**：全量 pytest 唯一红 `test_misc.py::TestPhilosophyRandom` 为 worktree 缺 gitignored 数据文件的预存环境项；主工作区 `npm run build` 因他人 WIP 中 AIPanel/AiChatPanel 的 `hasAgentSession` 必填 prop 未传而 typecheck 失败，与本轮两单无关（两单各在自有干净 worktree 构建全绿）。
- **台账现状**：在途 0；待派工队列仅剩 DEF-PROXY-03 样音终判（观察项，无需专门动作）。REQ-DECISION-CENTER-R2 六条反馈全部闭环。
- **上线部署（19:59）**：确认 `/api/record.status=false`（无进行中录音）后重启本地服务（旧 PID 31128 → 新 PID 48373）；新构建产物以干净 worktree（feat/dc-r2-c，等于 main 已提交前端）拷入 `frontend/dist` 部署——**未使用主工作区构建**，因其 typecheck 被他人未提交 WIP 阻断，不得把他人半成品打进生产包。启动后核对：`/api/decision-statuses` 返回四态且锚点位正确（首次读取已生成 `data/decision_statuses.json`）、首页指纹已切到新 bundle `index-CzSjW1b4.js`。

## 巡检说明

- **浏览器验收流（2026-09-25 项目方拍板，即日生效）**：项目方为非技术背景，关注结果交付与页面可验证性。规则三条：① 每单派工依据追加硬性交付物「**浏览器验收包**」——涉及页面/入口路径、非技术语言的分步验证脚本（≤5 步）、「什么样算通过」、工程师自测截图；② 验收三段式：工程师完工回报 → 管理员 AC 初审（含 pytest 门禁转绿等技术底线，项目方不感知）→ 置 `browser-acceptance-ready` 并向项目方发一行验证指引（启动命令 + 打开哪个页面 + 看什么）；**项目方浏览器核验通过才关单，管理员不代关**；③ 每日 09:00 日报附「今日可在浏览器验证」清单，项目方按清单点验即可，无需读技术细节。IDE 承接轮补充（09-25 13:00 项目方授权）：承接方可代跑点验（Playwright 无头 1440×900 截图+量化断言），通过后直接合入。

- P0 实测轮次留痕（2026-09-25 上午，项目方手工派工 Qoder IDE，非巡检产出）：承接昨晚合入 main 的 4 项功能（进度面板 P0 / 决策中心 B1+F1 / DEF-FE-05 / AM-B1 路由），清单 `docs/P0-RETEST-20260925.md`。本轮 **BLOCKED**——pytest 门禁 4 failed / 338 passed 触发「未全绿即停」协议，T1~T5 未执行。缺陷 DEF-RETEST-01~04 已登记（03/04 确定性回归归因 AM-B1 守卫；01/02 待定性，基线保持原样未清理）。反馈包三产物（清单 + `qa-evidence/P0-RETEST-20260925/env/pytest_full_failures.txt` + `feedback_plaintext.txt`）已交项目方。下一步以 RT-P0-FIX 修复单转绿门禁后重跑全量实测。管理员复核补充：① 反馈口径裁决为「直接发、基线原样」，DEF-01/02 定性动作移交工程师在自身 worktree 执行（QA 禁改 data/settings.json）；② 归属勘误——DEF-03/04 红灯自 main 基线 WP-A 提交（c2a1272/24eb45f）即存在，非 bc261e6/9b829b5（不在 main）引入；修复令 + 勘误已于上午注入 AM-B1 会话 c95528c3（= 原 C 选项执行）。**项目方浏览器点验进度（新验收流）**：① 决策中心页面 09-25 通过（见已关闭表 DC-DEC-F1 补验记录）；② T4 本地模式状态栏（DEF-FE-05，main@1926311 早已关闭）09-25 项目方点验通过——页面表现即最终验收，清单 T4.1 的形式化全量重跑随门禁转绿后的重测一并补录销账。

- 回报通道（2026-09-24 23:40 起，项目方批准）：**推模式为主**——工程师在开发群 `messages send --mention 产品经理 --intent request_action` 主动回报（契约交付/完工/卡点三个必报时点），兜底 `session send` 直投产品经理会话；定时巡检降级为**工程师忘回报时的拉模式保险**（REQ-DECISION-CENTER 两单已追发条款；REQ-PROGRESS-P0 暂未追加，仍走纯巡检）。
- 巡检自动任务：QoderWake 平台 automation「派工进度巡检」（tr_08b821764f093472194a49de），2026-09-24 23:42 由项目管理员重建（原产品经理名下任务已失联），每小时整点运行，权限=read-write+network+runCommands（限 git/qoderwake/pytest/python3）。
- 无人值守自治边界（2026-09-24 23:41 项目方拍板）：① **预授权按 AC 验收**——证据齐备且 AC 可机器核验时巡检可直接关单，缺证或口径争议不关单、标 ⚠️ 留痕；② 超 4 小时无进展自动催办 Owner 会话；③ 仅阻塞性异常叫醒项目方（连续两轮无进展、会话卡死、验收争议、范围/排期/跨单冲突需决策）；④ 每天 09:00 出日报追加至本台账。
- 巡检动作：读本表在途行 → `qoderwake session list/detail` 查会话态 → `git fetch` 比对分支 commit → 有变化才更新本行并 commit+push（前缀 `docs(tracker):`）→ 异常（完成未回报 / 运行报错 / 无进展超 4 小时）标 ⚠️ 并在 IM channel 可用时提醒项目方。
- 无变化时静默退出，不产生 commit、不打扰。
