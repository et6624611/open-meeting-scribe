# 企业版 P0 验收标准（v1.0 定稿）

- 产出：QA工程师 ｜ 日期：2026-10-29 ｜ v0.2：并入产品拍板（cmsg_01m63fn448vz5fta7ahrggq9rk）｜ v0.3：并入 QA 五问裁决与新时序（cmsg_01m63frf0zk4ap0966st6t9hft、cmsg_01m63fs38az5jy46tmtyjj979w）｜ **v1.0：后端契约冻结（2026-10-29 09:30 UTC，shared/P0-BACKEND-DESIGN-MULTIUSER-20261029.md v1.0）后按实际端点展开定稿**
- 对应派工单：cmsg_01m63fh4xpe75d04t20w12sge2（P0 设计派工）；工单 EP0-QA（docs/DISPATCH-TRACKER.md）
- 状态：**v1.0 定稿，可执行**。用例展开依据 = 契约 §1.2–§1.8 端点表、§2.2 schema、§2.4 出境清单、§5 迁移专节。
- 契约再变更纪律：后端契约任何变更须在契约文档"变更记录"登记并通知 QA，关联用例同步修订；执行以冻结版为准。
- 判定依据（项目方裁决，2026-10-29，cmsg_01m63fehgb3ewqjd24rgkb14fx）：
  1. 双产品线（一套代码、两种打包/承诺口径），个人版"数据不出设备"不反转；
  2. 企业版 P0 = 内网私有化单实例多用户；
  3. 上云边界 = 仅定稿文本（转写文本、纪要、决策流、笔记、术语/热词资产）；**音频、API Key、声纹 embedding 不出本地**；
  4. 存量单机数据归入手机账号 13373013103（默认初始账号）；
  5. 账号体系 = 管理员建号/邀请码，不依赖 SMS / GitHub OAuth。

---

## 0. 术语与判定口径

- **出境**：数据离开员工本机、发往企业服务器或其他网络对端。企业版内"服务器"是授权对端，"其他对端"默认未授权。
- **定稿文本**：任务状态进入定稿后的转写/纪要/决策流/笔记/术语内容。中间态（实时转写候选段、未保存草稿）**已裁决一律不出本机**（产品裁决 Q4，cmsg_01m63frf0zk4ap0966st6t9hft）；后端 WS schema 若承载非定稿文本即判 B 域 FAIL。
- **证据形态**：每条用例必须产出 ①请求/响应记录（代理抓包导出）②服务端落库抽查 ③审计日志行。口头"应该没问题"不作为通过信号。

---

## 1. 验收域 A：跨用户越权测试框架

### A1 测试矩阵（按契约 v1.0 端点展开）

服务端攻击面 = `/api/v1/*` 全集（契约 §1.2–§1.8），本地控制面路由（`/api/record/*`、`/ws/transcript/*`、`/api/engine/*`、`/api/models/*`、`/api/voiceprint/*`、`/api/audio`、`/api/download` 媒体、`/api/projects/*`）**不得出现在企业实例**（出现即 FAIL，§4 零交集规则）。

| 维度 | 枚举（契约锚点） |
|---|---|
| 资源 R | `context/tasks`（GET 列表/详情）、`snapshot`（PUT）、`tasks/{id}`（DELETE 回收站）、`assets/hotwords`（GET/PUT）、`assets/speaker-aliases`（GET/PUT）、`auth/*`（login/activate/change-password/me/logout）、`admin/users|invites|instance/close|open|instance/ai`、`ai/summary/generate`、`pairings`、`device-activate`、`devices`、`instance/info`（免登录面） |
| 操作 O | 读单条 / 列表 / 写（PUT/POST/DELETE）/ 状态变更 / 订阅（P0 应 404） |
| 令牌 X | 无令牌、member A JWT、member B JWT、admin JWT、未激活(pending) JWT、停用账号 JWT、过期 JWT、篡改 user_id JWT、**device token**（越界使用，见 T7）、local_token（发往服务端应拒） |

### A2 判定规则（含契约错误码全集）

- 访问他人资源：一律 403/404，**禁止 5xx**；DAO 层强制 actor 参数为结构性保证（§2.2），QA 抽 10% 端点做"绕过 UI 直请求"复核。
- 列表接口：仅返回本人 owner 可见集（§1.4 P0=personal 单分支，Q2 裁决：admin 列表/详情亦不可读员工内容，仅元数据计数——admin 可读内容判 FAIL）。
- 反向推送/WS 订阅：P0 服务端**不提供**（§1.4），探测 `/api/v1/ws*`、`/subscribe`、`/push` 类路径应 404；`X-OMS-Local-Token` 与 `/ws/transcript` 仅存在于 local origin，服务端收到即 401/404。
- 状态线错误码不混用（§1.8，混用判 FAIL）：停用账号→403 `account_disabled`；设备吊销→403 `device_revoked`；服务关闭写→503 `service_closed`、新登录→403 `service_closed`；AI 关闭→409 `ai_disabled`；rev 冲突→409 `current_rev`；白名单外字段→422。
- 服务停用（=U5 契约化）：close 后已登录会话不踢出、读放行、全部写端点 503；`instance/info.service_open=false` 正确回显；open 后复原。
- 已停用账号：会话与 device token 即刻吊销（重传 403）；其定稿保留、管理台"整包删除"为唯一删除路径（二次确认+审计留痕，物理删除幂等——重复点击不报错不重复删）。

### A3 设备配对与本地控制面边界（契约 §1.8 落地）

- 配对码：一次性、10 分钟时效、兑换即失效（重放 `pairing_code` 应 401/409）；未登录 Web 不得调用 `POST /api/v1/pairings`。
- device token 权限面：仅允许 §1.4/§1.5 上下文写端点与 `GET /api/v1/auth/me?as=user`；用它访问用户列表、管理面、资产以外的端点一律拒绝（403/404）——"device token 越界=登录态等价"判 FAIL。
- DELETE devices 即刻吊销：该 token 后续 outbox 重传 403 `device_revoked`；不影响同用户其他设备。
- 一机一 paired user：`/api/local/handshake` 返回的 `paired_user_id` 切换须重新配对；同机双用户并发录音场景出串音用例（录音状态接口按 `task_id` 参数化，`/api/record/status?task_id=` 不得返回他人任务状态）。
- local_token 发往企业实例任何端点 → 拒绝（两平面零交集，§4）。

### A4 存量迁移专项（裁决④ + 契约 §5）

- 以 13373013103 账号登录：全部存量任务/笔记/热词可见、可用、可导出；迁移对象 `owner=该账号、scope='personal'`，可见性不因迁移隐式扩大。
- 以其他新建账号登录：上述内容在任何接口、任何 UI 检索路径**零可见**（Q5 裁决：存量热词/术语仅 13373013103 可见）。
- 迁移只搬"tasks 定稿文本+本人热词+发言人别名"；音频/声纹/凭据/projects/agent-workspace 出现在服务端存储即 FAIL（§2.3 不搬运清单）。
- 告知即过：服务端**不存在**任何"用户确认归属"回执端点（存在即违背裁决 #3）；归属卡纯告知。
- 对账物证：`migrations` 台账（legacy_id+source_hash 去重）+ 迁移对账单（源数/入库数/跳过原因/content_hash 抽检）落 logs/，为 C2 门禁物证；重复执行迁移安全（重放返回既有目标）。
- 回滚：复制-校验-保留源三段式，源目录全程不动；服务端按台账批量 DELETE 可完全撤销。

### A5 出场 gate

矩阵 100% 执行、FAIL 清零或降级为已裁决接受的书面例外，否则 P0 不得出验收。

---

## 2. 验收域 B：数据出境白名单（可抓包验证）

### B1 企业版 P0 默认白名单（授权对端枚举）

| # | 对端 | 允许内容 | 验证方式 |
|---|---|---|---|
| W1 | 企业服务器 origin（内网部署地址） | 仅 §1.4/§1.5 白名单字段：`meta`（title/meeting_time/participants_text/source/legacy_id）+ formal/summary/decisions/notes/insights_html + 热词/别名资产 + 账号面（登录/激活/改密的凭据传输走 TLS）+ 队列/对账状态字段 | 正向抓包 + 落库抽查 + `egress_audit` 表比对（每个 LLM 代理调用有审计行，缺行/多行判 FAIL） |
| W2 | localhost / 本机控制面 | 音频流、实时转写、声纹注册与匹配、未定稿草稿、`GET /api/sync/queue`、`/api/local/handshake`、本机 Key 与加密 settings | 本机侧断言"无发往 W1 的同内容副本"；`/api/voiceprint/*` 等本地路由在企业实例上 404（攻击面清单双形态各一份，§4 零交集） |
| W3 | （默认关闭）AI 云对端 | 出厂零出网；仅管理员经 `/api/v1/admin/instance/ai` 显式开启后，base_url 域名逐域放行（**网络层强制**，非仅应用层判断——应用层判断可绕，网络层不可绕，QA 按绕过尝试断言） | 默认态抓包零命中外部域 + 开启态仅白名单域 + `egress_allowlist` 配置快照 |

### B2 禁止出境清单（红线，命中任一即 P0 FAIL）

- L1 音频：任何格式音频字节（含分片、临时文件上传、WS binary 帧）。
- L2 声纹：embedding 向量、注册表音频特征（服务端只允许 speaker 别名映射文本）。
- L3 凭据：API Key/token 明文（含请求头之外的日志、报错回显、任务 payload）。
- L4 非白名单对端：DashScope（dashscope.aliyuncs.com）、GitHub OAuth/api.github.com、ModelScope、Brave Search、版本检查/引擎下载 release 域名、SMS 代理——以上均为现仓库实测存在的出网面（asr-proxy/server.py:52、core/auth.py:48-51、core/model_downloader.py:41、core/agent_tools/impl.py:345、core/version_check.py、core/engine_installer.py:36、core/sms.py）。企业版 P0 下这些**默认关闭或不可达**（Q1 裁决：默认零出网）；管理员显式开启云端 AI 后，仅已加白域名可达，加白配置快照进验收证据。

### B3 内容级断言（不止看域名，要看字节）

- 允许字段=契约 §2.4 五名词逐项映射同意卡第二行（转写=formal、纪要=summary、决策流=decisions、笔记=notes、术语=hotwords/speaker-aliases），**无第六类**；构造第六类字段/音频引用/本地绝对路径/embedding 数组的恶意快照 PUT → 422 拒收（服务端防御 + 客户端出境拦截器双门禁，任一缺失记风险）。
- 对 W1 全部请求体做敏感模式扫描：音频 magic bytes、embedding 浮点数组特征、`sk-` 型 key 模式、base64 大块二进制 → 零命中。服务端存储抽查：blobs/ 与 instance.db 内 audio 字节、embedding 列值、明文凭据零命中（用户 API Key 只应存在于客户端 `settings/<user_id>.enc.json`，服务端仅企业自管实例级加密 Key——用户 Key 出现在服务端即 FAIL，契约 §3）。
- 离线队列重传幂等（契约 §1.4）：同 `Idempotency-Key` 重放 → 200 `idempotent_replay:true` 不重复入库；`base_rev != current_rev` → 409 携带 `current_rev`；断网期间同 task 多次编辑合并为单条最终快照（last-merge-wins）；重启后扫描 outbox 安全重放、无重复记录；跨 task 并行、同 task 顺序消费。
- `egress_audit` 表与代理抓包双向比对：每一外呼有审计行、每一审计行有抓包记录，多/少任一方向判 FAIL（可证伪来源，契约 §2.2）。

### B4 数据流向声明一致性（企业版 AC-5 姊妹项）

企业版发布材料 / SECURITY.md 企业版章节 / UI"数据位置"指示三处声明，与 B1 实测抓包结果逐条一致。不一致判 FAIL（个人版此条已有先例纪律）。

### B5 同意卡三行定稿文案 = 对外承诺 = 抓包事实（产品经理定稿，cmsg_01m63fn448vz5fta7ahrggq9rk）

定稿文案（措辞即承诺，验收按逐字比对，任一字符差异判 FAIL）：

> 你的会议录音和音频只保存在这台电脑上，不会离开本机。
> 会议定稿后的文字内容（转写文本、纪要、决策流、笔记、术语）会保存到公司服务器，方便你在任何设备上查看。
> 你的声纹信息和 API 密钥永远不上传。

**逐字一致的三处 UI 表面**：①上传知情同意卡 ②Settings「数据位置」三行表 ③登录页隐私说明。

**行 → 抓包/落库断言映射**：

| 承诺行 | 断言 | 挂钩条款 |
|---|---|---|
| 第 1 行（音频不出本机） | 全场景抓包无任何音频字节发往 W1 以外或对端；服务端存储无音频文件及可下载代理 | L1、B3 |
| 第 2 行（仅定稿五类文字上公司服务器 + 跨设备可查看） | W1 请求体内容类型白名单=转写/纪要/决策流/笔记/术语，与契约 §2.4 字段集合逐项一致（Q4 已裁决：中间态草稿不出本机，出现即 FAIL）；同账号异设备登录可读全部定稿 | W1、B3、§3A-U3 |
| 第 3 行（声纹与密钥永不上传） | 全流量零 embedding 向量、零凭据明文（含日志/报错回显）；服务端落库抽查同判 | L2、L3、B3 |

文案与 B1/B2 枚举存在任何一处"UI 说了、抓包没发生"或"抓包发生、UI 没说"的双向失配，均判 P0 FAIL。

### B6 域 B 拆两条口径（产品裁决：CA 不再为出场 gate，cmsg_01m63frf0zk4ap0966st6t9hft）

- **B-hard（出场 gate）**：B1 白名单 + B2 红线 + B3 内容级断言 + B5 承诺一致性——数据内容出境违规定为 FAIL，不可豁免。
- **B-recommend（部署加固项，不判 gate）**：HTTPS/内置 CA、传输加密强度等按 DevOps 降级结论执行；缺失记为风险披露进 PRD，不阻断 P0 出验收。HTTP 明文传输场景下 B3 断言仍照常执行（明文更容易验证，不构成豁免理由）。

---

## 3. 验收域 C：个人版升级回归门禁

前提裁决①：个人版承诺"业务数据不出设备"不反转。以下三条为**版本发布硬门禁**，任何迭代触碰个人版安装包均须重跑。

| # | 门禁 | 判定 |
|---|---|---|
| C1 | 零新增默认出网点 | 升级后安装包的抓包画像与基线版本一致：本地引擎模式下除 localhost（+模型权重首次下载白名单）外零出网。diff 非空即 FAIL |
| C2 | 本地数据目录不被污染 | 升级前后 `data/` 树：文件级清单 diff 仅允许新增（schema 迁移产物），禁止删除/改名/内容截断；升级后旧版本可回滚继续读写 |
| C3 | 承诺口径不蚕食 | 个人版 UI/README/SECURITY.md 不出现"上传/同步至服务器"类默认开启项；企业能力仅存在于企业打包形态（打包差异清单评审通过） |
| C4 | 设置事务完整 | 双产品线共码后，个人版设置界面不得因企业字段（owner/scope/服务器地址）出现可见残留或"界面说了不算"状态（BACKLOG 已录同类根因） |

---

## 3A. 产品拍板与契约插单衍生增量用例（v0.2 新增，来源 cmsg_01m63fn448vz5fta7ahrggq9rk）

| # | 用例 | 判定 |
|---|---|---|
| U1 | visibility 字段恒态 | 所有上下文实体接口响应固定含 `visibility`，P0 下恒为 `"personal"`；出现其他值或缺字段判 FAIL（UI 徽标组件依赖） |
| U2 | sync_status 三态真实性（契约 §1.4 双端口径） | **队列侧权威**：`GET /api/sync/queue`（local origin）枚举 pending/syncing/synced/error；断网中稳定 pending、恢复收敛 synced、异常注入 error——Web"待同步到公司服务器"提示逐档比对队列实际态。**服务端侧**：DTO `sync_status`∈{synced,stale} 仅驱动"最后同步于…"，与队列侧不一致时**以队列侧为准**（双端矛盾且 UI 显示服务端态判 FAIL，"界面说了不算"红线） |
| U3 | 无助手设备形态（拍板2） | 纯浏览器设备：读/编辑定稿文字正常，录音入口不可见或明确禁用说明；不得出现可点击但静默失败的录音控件 |
| U4 | 老数据归属卡（拍板3） | 首次登录 13373013103 展示"音频仍留原机"告知卡，**无需确认按钮、无后端回执**；卡片只出现一次不骚扰；其他账号不见此卡 |
| U5 | 服务停用双端表现（拍板4） | 管理员停用服务后：已登录会话不被踢出、顶部常驻"企业服务已暂停，仅可查看已同步内容"横幅、编辑/上传写操作禁用（API 侧同步拒绝，防绕过 UI 直发请求）；新登录在登录页拦截并提示"请联系管理员"；恢复服务后横幅消失、写操作复原 |
| U6 | 邀请码自助设密码（拍板1） | 账号流程无"初始密码"环节：管理员建号产出邀请码，员工凭码自设密码；管理员凭证无法查看/重置员工已设密码以外的密码字段（重置能力若存在须另行裁决进 Q2 域） |
| U7 | 词表隔离（全线规则） | 企业版 UI 文案不得复用个人版"联网/离线"五词表（tests/test_settings_i18n_vocab.py 既有门禁思路延伸）；企业版文案统一"公司服务器"表述，出现"云端"字样判 FAIL |
| U8 | 重启会话保持（后端工程债回归） | 服务实例重启后：已登录会话不因 JWT_SECRET 漂移全体失效（instance.key 持久化于 DATA_ROOT/secrets，契约 §2.1）；重启前后 cookie 有效性抽样断言 |

---

## 4. 阻塞项状态（v1.0：全部解除）

**产品裁决：五问全部关闭**（cmsg_01m63frf0zk4ap0966st6t9hft / cmsg_01m63fs38az5jy46tmtyjj979w）：
- Q1 ✅ 默认零出网，云端 AI 默认关闭、管理员逐域加白 → 落 W3/L4（契约 §1.7 实现：网络层强制 + egress_audit）；
- Q2 ✅ 管理员默认不可读，P0 不做可读通道 → 落 A2 单分支（契约 §1.8 元数据计数一致）；
- Q3 ✅ 停用即收权、定稿文字保留归企业、管理台整包删除、无自动到期 → 落 A2/契约 §1.8；
- Q4 ✅ 非定稿文字一律不出本机，"Web 会中回看他人会议"否决 → 落 §0 + B5 第 2 行；
- Q5 ✅ 存量热词/术语仅 13373013103 可见 → 落 A4。
- 另：CA 拆口径 → B6；邀请码自助设密/无助手形态/归属卡/服务停用/词表规则/重启会话保持 → §3A U1–U8。

**后端契约：已冻结（2026-10-29 09:30 UTC，v1.0）** — 端点清单（§1.2–§1.8）、错误码全集（account_disabled/device_revoked/service_closed/ai_disabled/409/422）、幂等协议（Idempotency-Key/If-Match-Rev）、配对 token 语义（§1.8）、零出网开关（§1.7）、迁移对账（§5.5）均已吸收进本稿。**QA 无剩余等待项；进入执行态，按后端增量交付滚动开测。**

**契约非阻塞开放项的验收默认值**（按后端 §6 默认先行）：用户删除=软删 30 天回收站、admin 不可读内容；决策状态字典管理台页面缺席不判 FAIL（产品排期项）。

---

## 5. 执行计划（v0.3 按项目方 2026-10-29 晚新指令更新）

- **时序改判**：项目方指令"不等 v10 关账、今晚以最终实现为目标持续运行"——企业版 P0 开测不再排在 v10 关账后，后端契约冻结即进入执行；v10 与 P0 的验收结论仍**分单记录、不得混写**（纪律保留，仅解耦排期）。
- 逐条用例台账（执行记录载体）：shared/QA-P0-CASES-LEDGER-20261029.md，按本稿各域展开 QA-EP0-* 用例 ID，开测时逐条登记结果与证据引用。
- 滚动开测节奏（今晚指令）：后端每交付一个增量（schema/DAO → 数据面端点 → 迁移工具 → 账号面），QA 对相应域先行冒烟，全量矩阵在功能可联调后执行；抓包工位与 B5 文案比对可即刻准备。
- 环境要求（P0）：内网隔离测试环境 × 至少 2 个真实终端用户账号 + 1 管理员 + 1 存量数据实例（13373013103 场景）；代理抓包工位（mitmproxy/Charles 同等物）；本地控制面与 Web 双 origin 抓包分流。
- 证据归档：qa-outputs/open-meeting-scribe/…/evidence/（开测时建），本稿及用例台账存群共享目录。

—— 本稿 v1.0 定稿（2026-10-29），无剩余阻塞；出场 gate = A5 矩阵 100% + B-hard 零违规 + C 门禁全过 + U1–U8 通过 + B6 风险披露入 PRD。
