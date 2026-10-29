# 实施工单台账（DISPATCH-TRACKER）

> 项目管理员登记。最新登记批次：**EP0-IMP｜企业版 P0 实施工单（2026-10-29 晚）**，依据项目方指令（cmsg_01m63fmzcrbefvenb1an258a4t：不等 v10 关账，今晚以最终实现为目标持续运行直至实现）与产品经理裁决（cmsg_01m63fn448vz5fta7ahrggq9rk、cmsg_01m63fnrtgp4pr4zs1h8fzt2eg、cmsg_01m63frf0zk4ap0966st6t9hft）。
> 协调人：产品经理（群内持续盯到实现验收）。各角色开工与进度直接回群播报。
>
> **EP0-IMP 共同实施基线（2026-10-29 补登，产品经理指定 cmsg_01m63fy7bzc9gj7n02wb5egxk2）**：
> - 《企业版 P0 产品方案（PRD）· 精简实施基线 v1.0》：shared/PRD-ENTERPRISE-P0-20261029.md（镜像 docs/EP0-DESIGNS/）
> - 后端 API 契约 **v1.0 冻结时点：2026-10-29 09:30 UTC**（cmsg_01m63fwhr5m6etwnxwwp96w4rr，shared/P0-BACKEND-DESIGN-MULTIUSER-20261029.md）
> - 冲突裁决规则：技术细节以契约为准，承诺口径以 PRD 为准（承诺措辞 = QA B5 判据，实现期不得偏离）
> - 产品裁决补充：① 用户删除回收站=软删 30 天为 P0 正式口径，物理删除端点保留为管理员手动操作、管理台入口随 P1；② 决策状态字典管理台页面排 P1，P0 后端提供数据即可；③ 数据层隔离修正为"无 users/<id> 目录树、隔离在 DB 行级"（PRD §8 为准，本台账早期表述作废）
> - 排期口径（PRD §9，对项目方如实说明）：全员并行可压缩联调窗口，但出场门禁五条一条不让步——宁可晚上线，不可坏承诺

## EP0-IMP｜企业版 P0 实施工单（2026-10-29）

设计文档位于群共享目录 `shared/`（同一份镜像见项目 docs/EP0-DESIGNS/）。

| 工单 | 负责人 | 实施内容 | 设计依据 | 开工条件 | 出场 gate | 状态 |
|------|--------|----------|----------|----------|-----------|------|
| EP0-BE | 后端工程师 | 数据层迁移（DATA_ROOT + users/<user_id> 命名空间、单租户 JSON→SQLite、存量数据归 13373013103、settings 按用户加密拆分、schema 预留 owner/scope）+ API 契约实现 + 账号体系（邀请码自助设密/管理员建号/停用即吊销会话）；契约必须含：默认零出网引擎/AI 配置开关、设备配对 token、sync_status 与 visibility 字段、邀请码自助设密端点、账号停用后定稿文字保留在企业服务器且管理台可整包删除语义 | shared/P0-BACKEND-DESIGN-MULTIUSER-20261029.md（v0.2） | 已就绪：契约已于 2026-10-29 09:30 UTC 冻结 v1.0，本单进入存储迁移开发（第一个增量：DATA_ROOT + schema + actor 强制 DAO 层） | 契约冻结（端点清单/错误码/WS schema/幂等键/JWT 策略齐备并发群）→ SQLite 迁移脚本 + 存量迁移可复现 → 账号体系端点自测通过 | 进行中（HTTP 16/19 PASS+M 6/6 PASS P-014；即修 D001–D003（见缺陷登记）后 QA 复跑销项；增量4 本地控制面/outbox 扩围中） |
| EP0-FE | 前端开发工程师 | 七档去单例化改造：①守卫+登录页+清态（S）②双 client 工厂+origin 归属打标（M）③task store 按 user 过滤（M）④录音 per-task 化（M，硬依赖 EP0-BE 契约）⑤engine 状态归位设备属性（S+M）⑥管理台页面组（M）⑦数据目录设置+上传知情同意交互（M，按 UI 规格） | shared/DESIGN-P0-FRONTEND-ARCH-20261029.md | ①⑥⑦不依赖后端，即刻开工；②③⑤随契约冻结推进；④待 EP0-BE 录音控制面契约 | ①登录守卫+退出清 localStorage（零残留）→ 全部七档完成且企业 build flag 下个人版零变化 → 同意卡/数据位置/登录页三处文案与 QA B5 逐字一致 | 进行中（档①含 W1 销项完成且走查关闭 P-007/P-008；档②⑤推进中） |
| EP0-OPS | DevOps 工程师 | deploy/private Docker Compose 骨架（oms-app/oms-proxy/oms-backup 三服务）、离线 tar 交付包（oms-private_<版本>_linux_amd64.tar.gz）、管理员初始化向导 4 步（默认绑定 13373013103）、TLS_MODE 三态开关（出厂 off + 管理台/向导常驻一键开内置 CA + 企业自有证书文档位）、数据卷备份（每日快照 14 天轮转）与升级回滚流程（强制前置备份→事务化 migrate→/healthz 探活） | shared/DEVOPS-P0-DESIGN-20261029.md | 即刻开工（可与 EP0-BE 并行；联调点仅 db migrate 命令与 /healthz）；CA 已降级，不再是出场 gate | compose 一键包在内网 Linux 裸机跑通「管理员启用服务→Web 访问」→ 升级回滚演练一次成功 → 离线包无外网依赖验证 | 进行中（骨架+回填+CLI 冒烟全绿 P-002/P-003/P-009；剩容器全链路 smoke+CI job；新发现 /healthz 缺口见 EP0-C7） |
| EP0-QA | QA 工程师 | 越权矩阵（资源×操作×令牌形态全矩阵，含禁止 5xx 区分存在性、WS 订阅越权、管理员默认不可读单分支、注销用户定稿保留/管理台整包删除预期、13373013103 存量专项 diff=∅ 可回滚）展开为逐条用例 + 数据出境白名单（默认零出网；非白名单对端全关；同意卡三行=抓包事实 B5 断言；域 B 按 CA 降级拆两条口径）+ 个人版升级回归门禁四条 + §3A U1–U7 | shared/QA-ENTERPRISE-P0-ACCEPTANCE-DRAFT-20261029.md（v0.2） | 框架与不依赖契约的用例即刻开写；逐条展开+升 v1.0 待 EP0-BE 契约冻结 | v1.0 定稿 → P0 六场景端到端验收（开通服务/邀请码建号/Web 查看编辑定稿文字/助手连接同步/用户隔离/备份回滚）+ 越权矩阵 100% 执行 + 白名单抓包通过 | 进行中（增量1 结构断言执行全绿 P-006；HTTP 全量待端点层，M 系待 oms-migrate） |
| EP0-UX | UI 设计师 | 转入实现走查：对照已交付规格逐屏核对前端/管理台实现（登录/用户空间、本机录音助手+数据位置分区、同意卡与徽标、/admin 三页+向导、服务停用双端表现、文案词表禁"云端"） | shared/P0-UIUX-SPEC-20261029.md | 本侧设计已交付，无前置；随 EP0-FE 各档产出滚动走查 | 每轮走查问题清单发群并跟踪闭环；P0 出场前走查项零未关闭 P0 级缺陷 | 进行中（W1 批次已关闭 P-008；W2 随档⑥、W3 随档⑦、W4 随档②⑤播报触发） |

## EP0-IMP 实施进展登记（滚动）

| 编号 | 时间(UTC) | 工单 | 交付物 | 证据位置 | 验证状态 | 下一步 |
|------|-----------|------|--------|----------|----------|--------|
| P-001 | 10-29 ~09:40 | EP0-BE | 增量1：存储迁移基础（DATA_ROOT、schema 0001 全表、迁移 runner、actor 强制 DAO、账号域、快照域、防枚举 404 修正） | 分支 feat/ep0-datalayer-20261029-093500 @ 8b09a3f（worktree，本地未推送）；tests/test_ep0_datalayer.py 13 passed | 已核实（worktree list 实查）；QA 冒烟未执行 | /api/v1 端点层 + oms-migrate 存量迁移工具 |
| P-002 | 10-29 ~09:36 | EP0-OPS | deploy/private 一键包骨架 13 文件（compose/离线安装/升级回滚/备份/Caddy TLS 三态/CA 导入脚本/管理员手册） | main @ 8417811（本地未推送）；compose config+语法校验通过 | 已核实（git log 实查）；Linux 实机全链路未验证 | 镜像产物后实机 install→登录→upgrade→rollback smoke |
| P-003 | 10-29 ~09:38 | EP0-OPS | 契约回填：reset-password 本机命令定稿、backup-snapshot 封装优先+sqlite3 API 回退、备份 sidecar 改企业镜像 | main @ 6958e88（本地未推送） | 已核实 | 企业包 CI job workflow |
| P-004 | 10-29 ~09:39 | EP0-FE | 档①完成：双形态开关、/login、/activate 邀请码设密、路由守卫、登出清态、会话过期、锁定三行组件（B5 三处同源） | 分支 feat/req-ep0-fe-auth @ 1057fd6（已 push origin，未合 main）；vue-tsc 0 错、build 通过、vitest 54/54 | 已核实（分支+origin ref 实查）；真实例联调待后端端点层；UI W1 走查进行中 | 档②OriginRegistry 双 client+WS handshake、档⑤engine 状态归位 |
| P-005 | 10-29 ~09:37 | EP0-QA | 验收标准升 v1.0 定稿 + 47 项用例台账（六组 QA-EP0-A/P/M/W/C/U） | shared/QA-ENTERPRISE-P0-ACCEPTANCE-DRAFT-20261029.md、shared/QA-P0-CASES-LEDGER-20261029.md（镜像 docs/EP0-DESIGNS/） | 已核实（文档版本行实查） | 按增量顺序滚动冒烟：schema/DAO→结构项先行（P-001 已可开测） |

| P-006 | 10-29 ~09:45 | EP0-QA | 增量1 结构断言执行：A14/防枚举/W09/W04/P系/A08/U1/U6/回收站/migrate no-op 全 PASS；双轨证据=独立复跑 13 passed + 对抗探针 29 passed | shared/QA-P0-CASES-LEDGER-20261029.md「执行记录｜增量1」+ qa-outputs/open-meeting-scribe/20261029-094200/evidence/（仓库外） | 已核实（台账执行记录节+目录实查）；worktree 8b09a3f 实查与播报一致 | BLOCK 项等增量2：A09–A13、W01–W03/W05–W10、M 系、C 系、U2/U5/U8 |
| P-007 | 10-29 ~09:44 | EP0-FE | 档①增量2：W1-01 redirect 回跳修复、W1-03 激活页接入锁定文案块、W1-04 scopedKey 纪律确认 | feat/req-ep0-fe-auth @ 2be0327（已 push origin）；vue-tsc 0 错、build 通过、vitest 54/54 | 已核实（分支 commit 实查） | 档②OriginRegistry+WS handshake、档⑤engine 归位 |
| P-008 | 10-29 ~09:45 | EP0-UX | W1 批次正式关闭（4/4 销项，UI 读码验证 2be0327）；W1-02 产品经理拍板方案①（承诺块仅中文、P0 不参与 i18n），规格升 v1.1 §7 落口径 | shared/P0-UIUX-SPEC-20261029.md v1.1；cmsg_01m63gms3vcn2habq9phfwbvjv、cmsg_01m63gr212x8pj80qf314r9t3y | 已核实（拍板+销项链路完整） | W2/W3/W4 按档位产出触发 |
| P-009 | 10-29 ~09:43 | EP0-OPS | 增量1 CLI 接线冒烟全绿（migrate 幂等/backup-snapshot 布局一致/reset-password 参数面一致）；发现端点缺口：契约 §7 承诺的 GET /healthz 在 8b09a3f 全仓不存在 | main @ 844e52d + edec3dd（OMS_HEALTH_PATH 过渡措施，本地未推送） | 已核实（commit 实查）；容器全链路 smoke 仍待镜像 | 缺口移交后端增量2（EP0-C7）；镜像 build 上下文含 deploy/private 需 smoke 确认体积口径 |

| P-010 | 10-29 ~09:50 | EP0-BE | 增量2：/api/v1 端点层全量（认证/管理/上下文/配对四域）+ GET /healthz（DB 可读复合探针）+ QA 映射①②落实（422 无裸 5xx）+ 资产内容级门禁；仅企业形态条件挂载、个人版路由数不变；P0 实例级串行锁（P1 优化项已注记） | feat/ep0-datalayer-20261029-093500 @ aba84fb（本地未推送）；tests/test_ep0_api.py 11 + datalayer 13 = 24 passed，既有回归 61 passed | 已核实（commit+stat 实查）；HTTP 全量待 QA 执行 | 下一增量：oms-migrate（M 系入口）+ 管理台 Web 静态页挂载 |

契约偏差两项（产品经理已裁决，PRD §8 补记 2026-10-29 09:49，cmsg_01m63h2jvwcvtrpty7rwybn3cg）：① POST /admin/invites 通用邀请码 P0 不挂载（501 占位）→ **批准**，账号绑定码即 P0 唯一需求，通用码列 P1，QA 枚举清单按此记录；② /auth/activate 在 service_closed 期间放行 → **批准，附新增验收断言**：停用期间 activate 成功→该账号 login 仍 403（service_closed 断言四扩五，入 W/A 系台账，列为 QA 出场检查项）。

| P-011 | 10-29 ~09:54 | EP0-BE | 增量3：oms-migrate 存量迁移（命令面冻结 `python -m app.db migrate-legacy --source <data目录> --account 13373013103`；账号不存在拒执；三段式复制-校验-保留源、源零改动有断言；幂等台账 (legacy_id, source_hash)；文本白名单搬运，音频/声纹/凭据物理不读取）；资产内容门禁加强为递归文本态校验；service_closed 第五断言语义已实现（activate 放行、login 独立拦） | feat/ep0-datalayer-20261029-093500 @ 3dc5e35（本地未推送）；合成 5 测试+真实存量双跑（scanned 131/migrated 112/skip 19/spot_check 112/112/重跑全 already_migrated）；对账单 DATA_ROOT/logs/migration_report_<ts>.json=QA M 系门禁物证格式 | 已核实（commit+stat 实查）；M 系执行待 QA | README-admin 迁移入口由 OPS 回填；向导"老数据一键导入"可直接调该命令 |

| P-012 | 10-29 ~09:56 | EP0-OPS | README-admin 新增 §3 存量迁移用户向四步（容器内 migrate-legacy 冻结命令面唯一入口、裁决口径逐字对齐"录音仍留原机"）；撤除 OMS_HEALTH_PATH 过渡配置（/healthz 已落地后清理） | main @ 66e8ca2 + 0e837f5（本地未推送；0e837f5 为原 99bb47a 重提交——该提交在我第六次更新 amend 恢复历史时被丢出分支，改动无损留存工作区后由 OPS 重提交，哈希以 0e837f5 为准，台账无 99bb47a 引用） | 已核实（commit+文件实查，工作区干净） | 企业包 CI job 等合 main；Linux 全链路 smoke 等镜像产物 |
| P-013 | 10-29 ~09:55 | EP0-BE（联调中事实） | 前后端联调两处 DTO 校准认可（非契约变更）；WS 承载裁决：local token 改查询参数 `?oms_local_token=`（浏览器 WS 无法自定义头的硬约束，契约 v1.1 登记此偏差，HTTP 面维持头）；本地控制面端点（/api/local/handshake、GET /api/sync/queue、outbox 推送器、per-task 校验）确属增量2 缺口，归入 EP0-BE 增量4，真双进程 e2e 后再点名前端接线 | 后端播报 cmsg_01m63hcp6xp3rg4bfbge5f8bk7 | 待增量4 交付核实 | "助手连接同步"场景（目标态五之一）实现收口依赖增量4，列为跟踪项 |

| P-014 | 10-29 ~09:57 | EP0-QA | 增量2 HTTP 全量回收：16 PASS / 3 FAIL（D001–D003，见缺陷登记）；增量3 M 系 6/6 PASS（真实存量 169 文件实战，计数守恒+禁运零命中+幂等/源零改动全过）；service_closed 五断言全过（含产品补令第⑤条，无绕入口）；契约偏差①②入枚举清单核对闭环；开发自测独立复跑 29 passed | shared/QA-P0-CASES-LEDGER-20261029.md 三节执行记录（增量1/2/3） | 已核实（台账节实查）；M04/M06 HTTP 级复验随联调收口 | 维持 BLOCK：W 抓包系+C 系（待 OPS 实机）、W10 文案（待档⑦）、U8（待 compose 实机）。出场 gate：D001–D003 修复复验前 A 域不出全绿 |

推送纪律：BE/OPS 分支与 main 提交均未推送，推送需项目方确认；FE 分支已按群纪律 push origin 不自行合 main。

### EP0 缺陷登记（QA 增量2 执行发现，均为错误码/5xx 契约失配，无越权穿透）

| 缺陷 | 严重级 | 现象 | 契约要求 | 影响 | 负责人 | 状态 |
|-------|--------|------|----------|------|--------|------|
| D001 | 中 | 停用账号登录返回 401 bad_credentials，account_disabled 码全链路未实现 | 403 account_disabled | 前端档①"请联系管理员"分流断裂，用户可见误导（求助路径） | 后端工程师 | 已移交即修（QA 消息直达），修复推送后 QA 复跑两套件销项 |
| D002 | 低-中 | 设备吊销后重传返回 401 unauthenticated | 403 device_revoked | 助手端无法区分凭据错/被撤，重试不收敛 | 后端工程师 | 同上 |
| D003 | 低 | 畸形 If-Match-Rev 头 →500（int() 未捕获），资产 PUT 同源模式 | 建议 400 invalid_header（A2 禁 5xx） | 违反 A2 判定 | 后端工程师 | 同上 |

## 全局协调事项

| 编号 | 类型 | 内容 | 当前判断 | 跟进人 | 状态 |
|------|------|------|----------|--------|------|
| EP0-C1 | 关键路径 | EP0-BE API 契约冻结 = 全员开工令：前端②③④⑤、QA 升 v1.0、DevOps compose 微调的共同前置 | 已解除：契约 v1.0 于 2026-10-29 09:30 UTC 冻结（cmsg_01m63fwhr5m6etwnxwwp96w4rr），前端②③④⑤/QA v1.0/DevOps compose 微调的共同前置全部解除 | 后端工程师 | 已解除 |
| EP0-C2 | 依赖 | EP0-FE 档④（录音 per-task 化）硬依赖后端多用户录音控制面契约（per-task start/stop/status + WS 鉴权） | 已随契约 §1.8 冻结解除（pairing token + X-OMS-Local-Token + 一机一 paired user） | 前端开发工程师 | 依赖已解除 |
| EP0-C3 | 一致性 | 对外口径三处逐字一致：同意卡三行（cmsg_01m63fn448vz5fta7ahrggq9rk 第 5 条）、Settings「数据位置」三行表、登录页隐私说明 = QA B5 抓包断言基准；备份承诺（本机保留 14 天、永不上传外部云）并入企业版数据治理承诺 | 产品经理已定稿，UE 规格与 QA 稿均锁定；代码合并时不得偏离 | 产品经理 | 已定稿，实现期核对 |
| EP0-C4 | 风险 | v10 个人版验收债务（QA-R1 FAIL 项）与 EP0 并行：两轮结论不得混写；个人版升级回归门禁四条独立执行 | 项目方已裁决 EP0 不等待 v10 关账；两线互不阻塞 | QA 工程师 | 跟踪中 |
| EP0-C5 | 待项目方明示（PRD 评审项，非今晚阻塞） | ① AI 算力默认零出网（"你们公司的会议文字要不要发给外部 AI 公司？默认不要"）② 离线 tar 是否对应完全无外网客户 ③ Windows Server P0 不承诺验收仅出文档 ④ 移动浏览器不入 P0 | PRD v1.0 已交付（shared/PRD-ENTERPRISE-P0-20261029.md，镜像 docs/EP0-DESIGNS/）；随今晚状态播报向项目方明示 | 产品经理 | 待明示 |
| EP0-C7 | 端点缺口 | 契约 §7 承诺 GET /healthz 沿用，但增量1（8b09a3f）未实现；compose healthcheck/安装探活/升级回滚三条门禁共同判定点。QA 移交端点层错误码映射两项一并落实（client_mutation_id 跨 task 复用裸 ValueError→409/422；密码校验类→422，直落 500 违反 A2 禁止 5xx 判定） | 后端增量2 必须含 /healthz + 两项映射；OPS 过渡：OMS_HEALTH_PATH 可配（默认 /healthz） | 后端工程师 | 已交付（P-010），待 QA HTTP 复验收口 |
| EP0-C9 | 出场检查项 | service_closed 五断言（含偏差②裁决新增：activate 放行但登录仍拦，防停用绕入口）+ 偏差①通用邀请码 501 按 P0 口径记录不判缺陷 | 产品经理裁决 cmsg_01m63h2jvwcvtrpty7rwybn3cg；QA 已被告知扩断言 | QA 工程师 | 入场，随 HTTP 全量执行 |
| EP0-C8 | 出场检查项 | EP0-FE 后续所有档位播报必含"新增键均走 scopedKey"注明项（产品经理拍板 cmsg_01m63gms3vcn2habq9phfwbvjv，UI W2/W4 走查受理前提）；sessionStorage/IndexedDB 若启用纳入清态范围 | 前端已确认执行（2be0327 播报注明）；台账按此受理各档播报 | 项目管理员/前端 | 生效中 |
| EP0-C6 | 凭证缺口 | mac 桌面签名公证 G-7 仍缺 Apple 凭据，桌面端交付受影响（不影响今晚企业版服务端 Linux 路径） | 不阻塞 EP0；持续跟踪 | 项目方 | 未解决 |

## 变更记录

- 2026-10-29（晚）：登记 EP0-IMP 五张实施工单及全局协调事项 EP0-C1~C6（项目管理员，依据产品经理派工 cmsg_01m63frf0zk4ap0966st6t9hft；后端设计 v0.2 已在共享目录核收，工单拆分覆盖其全部契约点）。
- 2026-10-29（晚·第二次更新）：补登 EP0-IMP 共同实施基线（PRD v1.0 + 契约 v1.0，冻结时点 09:30 UTC，冲突裁决规则与产品裁决补充见台账头部）；EP0-C1/C2 关键路径标记解除；后端/前端/QA 状态按群内播报实况刷新；§9 排期口径（出场门禁五条不让步、宁可晚上线不可坏承诺）纳入播报基准；PRD 镜像至 docs/EP0-DESIGNS/（依据 cmsg_01m63fy7bzc9gj7n02wb5egxk2、cmsg_01m63fwhr5m6etwnxwwp96w4rr、cmsg_01m63fxgp38fhr5mnxpjfj7f58）。

- 2026-10-29（晚·第三次更新）：登记实施进展 P-001~P-005（后端增量1、DevOps 骨架+回填、前端档①、QA v1.0+用例台账），五单状态按 commit/文档实况刷新（项目管理员实查 git worktree/log/origin ref 与共享目录版本行核证）；QA v1.0 与用例台账镜像入 docs/EP0-DESIGNS/。下一检查点：EP0-BE 端点层交付后 QA W/A/P 系用例执行结果 + UI W1 走查清单。

- 2026-10-29（晚·第四次更新）：登记 P-006~P-009（QA 增量1 结构断言全绿、FE 档①增量2+W1 关闭、OPS CLI 冒烟+/healthz 缺口），新增协调项 EP0-C7（/healthz 端点缺口与 QA 错误码映射移交）、EP0-C8（scopedKey 播报必含项出场检查）；UI 规格 v1.1 口径（W1-02 方案①）入册。当前无阻塞项；下一检查点=后端增量2（端点层+/healthz+两项映射+oms-migrate）交付后 QA HTTP 全量执行、UI W4 触发。

- 2026-10-29（晚·第五次更新）：登记 P-010（EP0-BE 增量2 端点层+/healthz+QA 两项映射落实，24 passed+61 回归零破坏，commit 实查核实）；EP0-C7 转"已交付待 QA 复验"；两项契约偏差入册待 QA/产品经理核对。目标态五条服务端能力面自此可联调。

- 2026-10-29（晚·第六次更新）：两条契约偏差按产品经理裁决入册（PRD §8 补记核实，镜像同步），新增 EP0-C9 出场检查项（service_closed 五断言）；P-010 偏差核对状态转"裁决闭环"。

- 2026-10-29（晚·第七次更新）：登记 P-011（EP0-BE 增量3 oms-migrate，后端三增量齐、自测 29 passed、真实存量 112/112 对账通过；M 系用例入口就绪）。EP0-BE 工单出场 gate 前两项（契约冻结✓、迁移可复现✓）已达，待 QA 执行结论收口第三项。检查点更新：QA HTTP 全量+M 系+五断言执行结果、FE 档②⑤联调播报（须带 scopedKey 注明项，EP0-C8）。

- 2026-10-29（晚·第八次更新）：登记 P-012（OPS README §3 迁移入口+过渡配置撤除，含 99bb47a→0e837f5 重提交留痕：我第六次更新的 amend 恢复操作曾把 OPS 在途提交丢出分支、内容无损，流程教训=恢复历史前必须先 git status 复核他人在途改动，已在台账留痕）、P-013（联调事实：WS token 查询参数承载将入契约 v1.1 偏差登记；本地控制面端点与 outbox 推送器归入 EP0-BE 增量4，为"助手连接同步"场景收口依赖）。

- 2026-10-29（晚·第九次更新）：登记 P-014（QA 增量2 HTTP 全量 16/19、增量3 M 系 6/6、五断言全过、偏差①②核对闭环）+ 缺陷登记 D001–D003（错误码/5xx 契约失配，无越权穿透；出场 gate 注记：修复复验前 A 域不出全绿）。编号说明：QA 请求登记"P-011"，该号已被同时段后端增量3 占用，顺延为 P-014。当前关键路径收敛为两点：D001–D003 修复复验、增量4（本地控制面/outbox）交付。
