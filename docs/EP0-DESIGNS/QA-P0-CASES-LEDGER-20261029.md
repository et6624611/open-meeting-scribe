# 企业版 P0 验收用例台账（QA-EP0，执行记录载体）

- 维护：QA工程师 ｜ 基线：shared/QA-ENTERPRISE-P0-ACCEPTANCE-DRAFT-20261029.md v1.0（判定规则详情见该稿对应条款，本台账只列用例 ID/内容/结果）
- 结果标记：`—` 未执行 / `PASS` / `FAIL(缺陷号)` / `BLOCK(原因)`
- 证据引用：执行时在"证据"列填 qa-outputs 相对路径或抓包/审计行编号；口头结论不入库。

## 域 A：跨用户越权（契约 §1.2–§1.8）

| ID | 用例 | 预期 | 结果 | 证据 |
|---|---|---|---|---|
| QA-EP0-A01 | member B JWT 读 A 的 task 列表/详情（GET context/tasks, /tasks/{id}） | 列表不含 A 条目；详情 403/404，禁 5xx | — | |
| QA-EP0-A02 | member B JWT 对 A 的 task PUT snapshot / DELETE | 403/404 | — | |
| QA-EP0-A03 | member B JWT 读/写 A 的 assets（hotwords、speaker-aliases） | 403/404 | — | |
| QA-EP0-A04 | 无令牌访问全部 `/api/v1/*`（instance/info 除外） | 401 | — | |
| QA-EP0-A05 | 篡改 JWT user_id / 过期 JWT / pending 未激活账号 | 401/403；pending 仅可走 activate | — | |
| QA-EP0-A06 | admin JWT 访问任何员工业务内容端点（task 详情/snapshot/blobs/assets 读取） | 403/404（Q2 单分支：P0 无管理可读通道）；用户列表仅元数据计数 | — | |
| QA-EP0-A07 | 管理台"整包删除该账号数据"：二次确认、审计留痕、幂等（重复执行不报错不复活）；member 令牌调用被拒 | 按契约 §1.8 | — | |
| QA-EP0-A08 | 停用账号：旧会话即刻失效、登录 403 account_disabled、device token 重传 403；恢复启用后凭证需重登 | 错误码不与服务停用混用 | — | |
| QA-EP0-A09 | 服务停用（close）：已登录会话不踢出、读放行、全部写 503 service_closed、新登录 403 service_closed、instance/info.service_open=false；open 后复原 | 契约 §1.3 | — | |
| QA-EP0-A10 | 探测订阅/反向推送类路径（/api/v1/ws、/subscribe、/push 等） | 404（P0 不提供） | — | |
| QA-EP0-A11 | 企业实例攻击面清单：本地路由（/api/record、/ws/transcript、/api/engine、/api/models、/api/voiceprint、/api/audio、/api/download 媒体、/api/projects）逐一探测 | 全部 404，两平面零交集（契约 §4） | — | |
| QA-EP0-A12 | GitHub OAuth / SMS 登录端点在企业实例挂载探测 | 不存在/404（裁决⑤+契约 §1.1） | — | |
| QA-EP0-A13 | 越权请求全量重放时服务端日志/报错体不泄漏他方数据内容与存在性（403 vs 500 区分、报错回显扫描） | 无内容泄漏 | — | |
| QA-EP0-A14 | DAO actor 强制抽查：静态确认无 actor 参数查询 lint 失败项进主干=0；抽 10% 端点绕过 UI 直请求复核 | 结构性保证未被绕过 | — | |

## 域 A-3：设备配对/本地控制面（契约 §1.8）

| ID | 用例 | 预期 | 结果 | 证据 |
|---|---|---|---|---|
| QA-EP0-P01 | pairings 需 Web 登录态；配对码 10min 过期、兑换即失效（重放拒绝） | 401/409 | — | |
| QA-EP0-P02 | device token 权限面：仅 §1.4/§1.5 写端点 + me?as=user；访问管理面/列表/其他=拒绝 | 越界即 FAIL | — | |
| QA-EP0-P03 | DELETE /devices/{id} 即刻吊销：后续重传 403 device_revoked；其他设备不受影响 | — | — | |
| QA-EP0-P04 | 同机双用户：handshake paired_user_id 唯一性；/api/record/status?task_id= 不返回他人任务状态（串音） | 需重新配对 | — | |
| QA-EP0-P05 | X-OMS-Local-Token / local handshake 产物发往企业实例 | 拒绝 | — | |

## 域 A-4：存量迁移（契约 §5）

| ID | 用例 | 预期 | 结果 | 证据 |
|---|---|---|---|---|
| QA-EP0-M01 | 13373013103 登录：存量任务/笔记/热词全可见可用可导出；owner=该账号、scope=personal | — | — | |
| QA-EP0-M02 | 其他账号对存量内容全接口/全 UI 路径零可见（含搜索、since 增量、分页越界） | Q5 | — | |
| QA-EP0-M03 | 不搬运清单核查：服务端存储零音频/声纹/凭据/projects/agent-workspace | §2.3 | — | |
| QA-EP0-M04 | 归属"告知即过"：不存在任何确认回执端点（探测即 404）；归属卡仅出现于 bootstrap 账号 | 裁决#3 | — | |
| QA-EP0-M05 | 迁移幂等与对账：重复执行安全；对账单（源数/入库数/跳过原因/content_hash 抽检）齐备且与 DB/blobs 一致 | §5.5 | — | |
| QA-EP0-M06 | 迁移回滚：源目录全程未动；按台账批量 DELETE 后服务端完全撤销，旧版应用仍可读写原目录 | §5.6 | — | |

## 域 B：出境白名单（契约 §2.4/§1.7，B-hard 出场 gate）

| ID | 用例 | 预期 | 结果 | 证据 |
|---|---|---|---|---|
| QA-EP0-W01 | 默认出厂态（AI 关闭）服务端+客户端全链路抓包：外网对端枚举 = ∅（仅服务器 origin + localhost） | 零出网 | — | |
| QA-EP0-W02 | AI 开启态：仅 base_url 白名单域可出网；应用层绕过尝试（伪造目标、直连 IP）被网络层拦截 | §1.7 网络层强制 | — | |
| QA-EP0-W03 | egress_audit ↔ 抓包双向比对：每外呼有行、每行有呼，多/少任一方向 FAIL | §2.2 | — | |
| QA-EP0-W04 | 恶意快照 PUT：音频字节/embedding 数组/sk- 型 Key/本地绝对路径/base64 大块/第六类字段 → 422 拒收；客户端出境拦截器同判 | §2.4 双门禁 | — | |
| QA-EP0-W05 | 白名单字段五名词正向映射：formal/summary/decisions/notes/hotwords+aliases 逐项可上传、落库可查 | 同意卡第 2 行 | — | |
| QA-EP0-W06 | 中间态内容红线：录音中/未定稿草稿在任何通道（含轮询参数、错误回显）不出本机；WS 仅 local | Q4 | — | |
| QA-EP0-W07 | 凭据面：用户 API Key 仅存客户端 enc.json；服务端 DB/blobs/日志零用户 Key；仅企业自管实例级加密 Key（AES-GCM/instance.key） | 契约 §3 | — | |
| QA-EP0-W08 | 服务端存储离线扫描：blobs/*.json.gz 解压抽样 + instance.db 全库敏感模式扫描零命中（音频/生物特征/凭据） | L1/L2/L3 | — | |
| QA-EP0-W09 | 幂等重传：断网编辑合并（last-merge-wins）、重启 outbox 重放、同 Idempotency-Key 重放 200 idempotent_replay、409 current_rev 冲突路径无脏数据 | §1.4 | — | |
| QA-EP0-W10 | 三处文案逐字比对：同意卡/「数据位置」三行表/登录页隐私说明 vs B5 定稿三行；再与 W01–W08 实测结果双向一致性评审 | B5，UI 声明=抓包事实 | — | |

## 域 C：个人版升级回归门禁（发版硬门禁）

| ID | 用例 | 预期 | 结果 | 证据 |
|---|---|---|---|---|
| QA-EP0-C01 | 个人版升级安装后抓包画像 vs 基线：除 localhost+模型首下载外零出网，diff=∅ | C1 | — | |
| QA-EP0-C02 | 本地 data/ 树升级前后清单 diff 仅新增；旧版回滚可读写；迁移对账单为物证 | C2 | — | |
| QA-EP0-C03 | 个人版 UI/文档无"上传/同步到服务器"默认开启项；企业能力仅企业包形态（打包差异清单） | C3 | — | |
| QA-EP0-C04 | 个人版设置页无企业字段（owner/scope/服务器地址/管理台入口）可见残留 | C4 | — | |

## 域 U：产品拍板衍生（§3A）

| ID | 用例 | 结果 | 证据 |
|---|---|---|---|
| QA-EP0-U1 | visibility 恒 "personal"（全实体响应必备） | — | |
| QA-EP0-U2 | sync_status 队列权威态四态真实 + 服务端 DTO{synced,stale} 仅"最后同步于"，冲突以队列为准 | — | |
| QA-EP0-U3 | 无助手设备：文字读/编辑可用、无录音入口、无可点即败控件 | — | |
| QA-EP0-U4 | 归属卡告知即过、无确认按钮、仅一次 | — | |
| QA-EP0-U5 | 服务停用横幅/登录拦截文案 + A09 API 侧同步复核 | — | |
| QA-EP0-U6 | 邀请码全链路无初始密码；管理员不可见/不经手密码 | — | |
| QA-EP0-U7 | 企业版文案禁"云端"字样、禁复用五词表（i18n 门禁延伸） | — | |
| QA-EP0-U8 | 实例重启会话保持（instance.key 持久化） | — | |

---

- 执行顺序：后端增量一到即跑对应冒烟（schema/DAO→A14/M 系；数据面端点→A01–A05、W 系；账号面→A08–A09、P 系、U6；迁移工具→M 系、C02），全量矩阵在可联调后收口。
- 已知非阻塞默认（按契约 §6）：删除=软删 30 天回收站；决策状态字典管理台页面缺席不判 FAIL。

---

## 执行记录｜EP0-BE 增量1 数据层结构断言（2026-10-29，feat/ep0-datalayer-20261029-093500 @ 8b09a3f）

环境：macOS arm64，仓库 venv（Python 3.14），worktree 实查与播报 commit 一致。
证据：①开发测试独立复跑 `tests/test_ep0_datalayer.py` **13 passed**；②QA 独立对抗探针（非复用开发断言，29 项）**29 passed** — qa-outputs/open-meeting-scribe/20261029-094200/evidence/test_qa_ep0_probe_increment1.py。

**数据层通过（结构支撑成立，HTTP 语义待端点层复验）**：
- QA-EP0-A14 **PASS**：15 个业务 DAO 方法 actor_user_id 均为 keyword-only 强制，空/缺 actor 一律 ActorRequiredError；无绕过面。
- QA-EP0-A01/A02/A03/A04/A05/A06（数据层部分）**PASS**：跨用户读/写/删同名他人 task 与不存在 task 异常类型一致（统一 NotFoundError，无存在性 oracle）；开发播报的"409→404 防枚举修正"经探针实测确认；member 执行管理操作（建号/停用/实例配置）同走 NotFound 语义。
- QA-EP0-W09（数据层部分）**PASS**：同 mutation 重放返回首次结果不重复入库（rev 计数=1）；base_rev 过期抛 StaleRevisionError 携带 current_rev；顺序推进 rev 正常。
- QA-EP0-W04（数据层部分）**PASS**：audio_base64/voiceprint_embedding/api_key/local_path/audio_file_ref 及 meta 夹带 audio_url 全部 PayloadNotAllowedError 拒收；五类合法字段通过。
- QA-EP0-P01/P02/P03 **PASS**：配对码兑换即失效、ttl 过期拒绝、revoke 即刻 verify_device_token=None。
- QA-EP0-A08（数据层部分）**PASS**：停用级联=登录失效+全部 session/device 吊销+数据保留（ctx_tasks 计数不变）；整包删除=行+blob 目录全清。
- QA-EP0-U1/U6 **PASS**：get_task/list_tasks 恒返 visibility='personal' + sync_status 字段；建号 pending 且 password_hash=NULL（无初始密码）、服务端邀请码仅存 hash、一次性使用、弱密码拒绝、激活后可登录。
- 回收站 30 天到期物理删+幂等 **PASS**；migrate runner 重复执行 no-op、applied_versions={1} **PASS**。

**保持 BLOCK（按台账待后端增量2 端点层/迁移工具）**：A09/A10/A11/A12/A13、W01/W02/W03/W05–W10、M01–M06（oms-migrate 未交付）、C 系、U2（GET /api/sync/queue 端点）、U5/U8。

**增量2 交付验收点（EP0-C7，随端点层执行）**：
- QA-EP0-X01 `GET /healthz` 挂载可用（三条运维门禁共同判定点）；
- QA-EP0-X02 `client_mutation_id` 跨 task 复用 → HTTP 409/422（非 500，A2 判定）；
- QA-EP0-X03 密码校验类 ValueError → HTTP 422（非 500）。

**移交后端增量2 的两条端点层映射要求（防 5xx 违规，非当前 FAIL）**：
1. `client_mutation_id` 跨 task 复用现抛裸 ValueError → 端点层必须映射 4xx（建议 409/422），直落 500 将违反 A2"禁止 5xx"判定；
2. 密码校验类 ValueError（如长度不足）→ 422 语义，勿 500。

结论：**P-001 增量1 数据层结构断言全绿，QA 侧无阻塞**；下一执行点=端点层交付后 W/A/P 系 HTTP 全量 + UI W1 走查闭环（与项目管理员检查点一致）。

---

## 执行记录｜EP0-BE 增量2 HTTP 全量（2026-10-29，@ aba84fb）

套件：qa-outputs/open-meeting-scribe/20261029-094200/evidence/test_qa_ep0_http_increment2.py（19 项独立对抗用例，TestClient 无副作用实例）。
结果：**16 PASS / 3 FAIL（均为错误码/5xx 契约失配；访问拒绝语义全部正确，无越权穿透）**。

PASS 要点：X01 /healthz；X02 422 client_mutation_conflict；X03 422 activation_failed；匿名 401 全覆盖；跨用户统一 404 not_found（与不存在资源不可区分，无枚举 oracle）；admin 不可读员工内容（404+列表零泄漏）；member 管理面 403；幂等重放 200+rev 不增、409 rev_conflict 携带 current_rev；W04 快照/资产内容门禁（audio_base64/嵌套 float embedding 均 422 + snapshot_rejected 审计行）；**service_closed 五断言全过**（含 PM 补令⑤：停用期 activate 放行但该账号 login 仍 403）；device token 写通道可用且无读权限；ai_disabled 409；推送/订阅类路径 404；U1 visibility 恒 personal。

缺陷清单（移交后端即修，出场 gate 阻断项）：
- **QA-EP0-D001｜中**｜停用账号登录返回 `401 bad_credentials`，契约 §1.8/裁决要求 `403 account_disabled`。复现：admin PUT /admin/users/{id}/status=disabled → 该账号 POST /auth/login 正确密码。影响：前端档①已按 account_disabled 分流"请联系管理员"，实际用户将看到"账号或密码错误"——误导+求助路径断裂。grep 证实 account_disabled 码全链路未实现。
- **QA-EP0-D002｜低-中**｜设备吊销后重传返回 `401 unauthenticated`，契约要求 `403 device_revoked`。复现：pairings→device-activate→DELETE /devices/{id}→Bearer 重传快照。影响：助手端无法区分"凭据错"与"设备被撤"，静默重试不收敛。
- **QA-EP0-D003｜低**｜畸形 `If-Match-Rev` 头（如 "abc"）→ **500**（int() 未捕获）。违反 A2"禁止 5xx"判定。复现：PUT snapshot 带非法头。同类模式在资产 PUT 同源。修复建议：头解析失败→400/422 invalid_header。

契约偏差登记核对：①通用邀请码 501 占位=PM 已批准，枚举清单记录在案（/admin/invites 返回 501 而非路由缺失，可接受）；②activate 停用期放行=PM 批准并扩第五断言，**已执行通过**。

## 执行记录｜EP0-BE 增量3 迁移探针（2026-10-29，@ 3dc5e35）

套件：test_qa_ep0_migrate_increment3.py；源=主 checkout **真实存量**（tasks/ 全量 169 文件副本 + 资产文件，非合成）。结果：**6/6 PASS**。
- M05/M01：真实量级迁入、对账单计数守恒（scanned=migrated+skipped 分布全解释）、spot_check 全 ok、owner=13373013103 对应 user_id 且 scope=personal 单一归属、legacy_import_ledger=报表=DB 三方一致；
- W 禁运零命中：全部 blob（json.gz 解压）+ ctx_entities 全库扫描 audio_path/embedding/voiceprint/sk-/recordings/.wav 等 12 项禁运 token=0 命中；
- 幂等重跑：二次 migrated=0、already_migrated≥首次、revision 总数不增；
- 源变更重推：改动笔记字段→该 task current_rev=2（新 mutation 安全重放）；
- 账号缺失拒绝：SystemExit 含 13373013103 提示、ctx_tasks 零写入（向导未完成形态防护成立）；
- 源只读：迁移前后源目录内容指纹一致；
- 资产形态：speaker_aliases 纯字符串值、embedding 零出现。

M 系剩余：M04 归属卡无回执端点（探测 404）与 M06 服务端整包撤销回滚的 HTTP 级复验随联调环境执行；C2 个人版升级回归需安装包形态，维持 BLOCK。

---

## 执行记录｜D001–D003 修复复跑销项（2026-10-29，@ c23b247 增量4）

复跑范围：QA 三套件全量（增量1 探针 29 + 增量2 HTTP 20【含新增两状态线组合断言】+ 增量3 M 系 6）+ 开发 EP0 全套独立复跑。
结果：**QA 55/55 PASS；开发 32 passed**。

- D001 **销项**：停用账号+正确密码 → 403 account_disabled（前端"请联系管理员"分流接通）；错凭据仍 401 bad_credentials，三分正确。
- D002 **销项**：出示 Bearer 但凭据吊销/失效 → 403 device_revoked，与 401 unauthenticated 区分成立。
- D003 **销项**：If-Match-Rev 畸形/负数 → 400 invalid_header，快照+资产双端同规则，全链无裸 5xx（复跑 20 项 HTTP 未见任何 5xx）。
- 组合断言（后端建议采纳入册）：账号线/实例线错误码不混用 PASS——停用+关闭叠加态下 active 用户登录=403 service_closed、停用用户=403（两线之一），401 混码零出现。
- 探针漂移说明（非产品缺陷）：增量4 `redeem_pairing` DAO 返回值扩为 3 元组（附 user_id 供助手展示），QA 增量1 探针已同步适配；HTTP 契约面（device-activate 响应体）不受影响。

**A 域状态：全绿收口**。维持 BLOCK 不变：W01–W03/W05–W08 抓包系、C 系（安装包形态）、W10（随 FE 档⑦）、U8（随 compose 实机）、M04/M06 HTTP 级复验（随联调）。

---

## 口径更新与新增用例｜契约 v1.1 §7.1 第8条 + 助手面存储端点（2026-10-29，@ 77765aa）

**U2 基准定稿**：`GET /api/sync/queue`（本地面）未配对形态 = **200 空队列**（契约 v1.1 §7.1 第8条，FE 7a6f23c 实测背书；本地面不设 409）。U2 用例预期同步修订：未配对设备队列可读且为空、不出现错误态红标。

**W10 词表门禁扩展两条**（产品 cmsg_01m63j8pc9ymzx6skqg9v3jj41 四处表面基础上）：
- 管理台 AI 出网区不得再出现"API 密钥"独立指代（定稿措辞"云端 AI 服务凭据"+ 说明行逐字）；全站任何"上传/保存密钥"类 UI 表述不得与承诺第三行构成同词反向断言；
- 数据目录迁移完成态文案必须为"迁移完成，重启助手后生效"语义，**禁止即时切换表述**（activation 边界，后端如实披露口径）。

**新增 L 系用例（助手面本地数据目录端点，QA-EP0-L01–L05）**：
- L01 `GET /api/local/storage` local_token 守卫：无/失效 token 拒绝；返回字段齐（data_dir/total_bytes/recordings_bytes/tasks_files/writable/disk_free_bytes）。
- L02 `POST /api/local/storage/migrate`：嵌套目标目录/同目录 → 422 migrate_rejected；合法目标=复制-校验-保留源三段式、重跑 skip_identical 幂等、源目录指纹前后一致（复用 M 系指纹法）。
- L03 activation 语义断言：响应 activation 字段与 UI 文案一致（重启生效，非即时切换）；迁移后未重启态读写仍指向旧目录=如实行为。
- L04 两平面零交集扩展：企业实例 origin 探测 `/api/local/*`、`/api/sync/queue` 全部 404（并入 A11 攻击面清单，assistant 形态端点不入企业面）。
- L05 助手→实例通道信任边界：注入 HTTP(S)_PROXY 环境代理变量后助手推送仍直连实例（不采纳环境代理），W02 抓包阶段执行。

L 系执行条件：L01–L03 随联调环境（assistant 进程可起即可跑，与 U2 同批）；L04 即时可加（下轮 HTTP 套件补挂）；L05 随实机抓包批。

---

## 口径更新｜content_hash 服务端权威（契约 v1.1 第10条）+ W10 扫描面扩展（2026-10-29，@ 77765aa 复跑 21/21 PASS）

- **基准改定**：QA 全部 content_hash 断言（W 系对账、M 系 spot_check、3b 助手对账承接项）统一为"响应/详情/DB 三处=服务端对规范化正文的 sha256；客户端提交值一律不可信、被覆盖"。
- **独立防篡改探针已入 HTTP 套件并复跑通过**（哨兵 DEADBEEF_SENTINEL 提交→响应 64 位规范化哈希、DB/详情同尺；套件现 21 项全绿，77765aa 实测）。M 系对账尺子与本条同源，历史结果无需改判。
- **W10 扫描面追加**（UI 规格 v1.3/v1.4 入册）：数据目录迁移语境全站禁用三词"已切换 / 即时生效 / 暗示已启用"；activation 原文不得进员工界面；422 拒收态文案按规格五条基准核对。四处锁定表面+管理台承诺卡=W10 运行时目检五表面（UI 已确认代码级单源 LockedPrivacyBlock，QA 保留运行时目检收口）。
- **表面口径终版对齐（规格 v1.4 §7，2026-10-29 与 UI 确认）**：B5 逐字锁定块断言面=**四处**（登录页/激活页/同意卡/数据位置表，均 LockedPrivacyBlock 单源，任一字符差异 FAIL）；W10 运行时目检=四处锁定表面 + 管理台"数据与备份"承诺卡（产品 W2 扩围的另一组锁定文本，逐字=DevOps §6 口径）共**五表面**；词表门禁三件套（"云端 AI 服务凭据"定稿措辞、同词反向断言禁令、禁用三词）为全站扫描项，不计表面数。

---

## 执行记录｜合入批准批次·本机可跑六组收口（2026-10-29，@ 77765aa，等待 OPS 期间完成）

套件：test_qa_ep0_closeout_local.py **7/7 PASS**（U8 用真 uvicorn 子进程重启验证，非模拟）。
- M04 **PASS**：attribution/migration confirm·ack·receipt 类端点全 404=告知即过、无回执握手；**事实修正**：`POST /admin/invites` 实况=404 路由缺失（后端播报"501 占位"表述不准，仅 /ai/summary/generate 为 501）——用户可见语义不变（P0 不提供通用邀请码，偏差①批准口径不受影响），请后端按实况修口径、台账同步。
- M06 **PASS**（HTTP 级）：建号→激活→写入快照+资产→停用→admin DELETE data：ctx_tasks/ctx_assets 清零、blobs/<uid> 全除、停用账号数据通道 401。
- L01 **PASS**：/api/local/storage 无 token/伪造 token 401；字段齐；查询参数承载（oms_local_token）与 v1.1 一致。
- L02 **PASS**：同目录/嵌套 422 migrate_rejected；合法迁移 copied>0/failed=[]/source_retained=true；重跑 copied=0 skip_identical>0；源指纹不变。
- L03 **PASS**：activation 字段逐字含"重启助手进程…生效"；迁移后快照 data_dir 仍指旧目录=非即时切换为真，FE 文案有实现依据。
- U2 **PASS**：未配对 queue=200 {"queue":[]}；enqueue→pending 可见；flush 未配对=skipped_unpaired 非报错。
- U8 **PASS**：真进程重启（kill+新 uvicorn、同 DATA_ROOT、复用 httpOnly cookie）→ /auth/me 200 会话保持；instance.key 持久化实测在位。附注：本机畸形代理环境变量需 trust_env=False 隔离，实机抓包工位同法处理防噪音误判。

**收口进度**：环境依赖六组中 U2/U8/M04/M06/L01–L04 本机全绿销项；剩 W 抓包系（W01–W03/W05–W08+L05）、C 系、W10 五表面运行时目检随 OPS 企业包镜像/Linux smoke 环境就绪执行——出场 gate 终局判定待最后一批。

---

## 基线钉桩｜main @ b6c3037 复验（2026-10-29 22:4x，合入第一棒后）

- 合入实况独立核实：de8fbaa 六提交合入 diff=**3297 insertions(+)/0 deletions**（18 文件，纯新增声明属实）；origin/main=b6c3037 已同步（ls-remote 实测）；b6c3037 契约第12条 404 口径修正实查在位、shared 镜像一致。
- **QA 四套件对 main 基线全量复跑 = 63/63 PASS**（增量1 结构 29 + HTTP 21 + M 系 6 + 本机收口 7）。终局判定基准自此钉在 main，此前分支态结果仅作过程记录。
- 剩余仍按令：W 抓包系/C 系/W10 五表面运行时目检，待 FE 第二棒+OPS 点火后环境收口。

---

## 执行记录｜第二棒后基线重钉 + W10 产物级验证（2026-10-29，main=f798704→59af334）

- QA 四套件对合入 FE 后的 main 全量复跑 **63/63 PASS**（终局基准改钉 f798704 树；origin 实测同步，含后续台账 docs 提交 59af334）。
- W10 产物级验证（VITE_EDITION=enterprise 构建，dist 快照存 qa-outputs/…/evidence/enterprise-dist）：
  - 锁定三行逐字各 **1 次**（单源组件形态与 UI 走查结论一致）；banner"企业服务已暂停，仅可查看已同步内容"、hotwords 指引、AI 说明行、paused_hint 定稿、管理台承诺卡口径全部逐字命中 ✓；
  - 词表扫描判定："云端"42 处均系个人版字串集与已批准的"云端 AI 服务凭据"定稿措辞（W2-02 产品原文），企业命名空间内无未批准指代；独立"API 密钥"第 3 处定位于个人版 settings.api_key 标签（企业形态不复用个人设置视图，W3 裁决代码级背书），非违例；"已切换"2 处均在个人版云降级/设置语境，非数据目录迁移语境，按 v1.3 口径非违例；
  - 运行时目检残留两项（随实机浏览器执行，UI 已认领接应）：企业表面不渲染上述个人版字串的路径确认 + 五表面视觉呈现核对。
- W10 状态：产物级 PASS + 运行时目检待实机；C 系与 W 抓包系维持待 OPS 产物。

---

## 出场 gate 终局判定（2026-10-29 23:2x，基线 main=f798704+0d26fd4，OPS run 40897084410 环境）

**W 抓包系（本机实进程形态，test_qa_ep0_wpack_live.py PASS）**：
- W01 默认零出网：企业实例+助手双进程 lsof 秒级采样（操作态+空闲态≥5 样本），非 127.0.0.1 对端 = **0**；
- W02 默认关：ai_enabled=false、allowlist 空、无 base_url 开启 422；开启态落配置+逐域回显；**开启态服务端 AI 代理=501 ai_proxy_pending（已声明边界，无任何外呼发生）**——"仅白名单域可达"的网络层强制待代理实现后补验，今晚零出网主张不受影响；
- W03 egress_audit 与操作精确一致（applied=1 直连推送、rejected=1 哨兵拒收，无孤儿行）；
- W06 中间态/夹带字段（draft_text/audio_ref）422 拒收，非定稿内容进不了服务端；
- W07 服务端凭据零明文：instance.db+blobs 解压全扫 sk-/口令/音频引用零命中；ai_provider api_key 密文存储；
- L05 助手在 HTTP(S)_PROXY=死代理环境下 register→enqueue→flush→Web 读取全链成功=**直连不采纳环境代理实证**。

**W10 运行时目检（headless Chrome 对真实企业构建+真实实例）**：
- 登录页常态：锁定三行逐字渲染 ✓、仅账号+密码+Accept Invitation、**无 GitHub/SMS 可见入口** ✓（截图 w10_login_normal.png）；
- 登录页停用态："Company service is paused. Please contact your admin." 横幅渲染 ✓（浏览器英文 locale；中文逐字面已在产物级+vitest 锁）（截图 w10_login_service_closed.png）；
- 激活页：锁定三行逐字渲染 ✓；
- 残留目检三项（blocked-on-capability：本机无 CDP 登录态自动化）：数据位置表/同意卡/管理台承诺卡登录态视觉——已有产物级逐字+单源组件+API 数据源三重证据，建议并入项目方四项体验确认点实机覆盖；
- 低优先观察（转 UI/前端，不阻塞）：登录页右侧 ai-panel 头渲染出 i18n 键字面 "ai-panel.page.login"（缺键）；顶栏 "Update Available" 徽标在企业内网形态是否应隐藏待产品定口径。

**C 系**：blocked-on-environment 维持——个人版安装包形态需 Win/mac 实机窗口（v10 遗留同窗）；过程证据=合入纯新增 0 删除、CI 仅构建企业形态、FE 默认构建红线自查、后端全量 1090 passed。

**终局**：实现缺口 **0**；A/B/M/L/U 域 + W 抓包系核心 + OPS 实机六步 smoke 全绿；披露三项=①C 系安装包（环境，随 v10 实机窗）②W10 登录态三表面（能力，随项目方体验确认点）③W02 开启态代理 501（已声明边界）。**QA 判定：企业版 P0 具备向项目方交付条件（附上述三项如实披露）。**


---

## 终局判定补录｜D004：REQUIRE_AUTH=true 强制形态登录面断（2026-10-30，DevOps 发现、QA 实进程复现坐实）

- **严重级 P0（仅对正式 Docker 交付形态）**：deploy/private/docker-compose.yml:12 硬置 REQUIRE_AUTH=true，而 server.py 外层网关 `_AUTH_EXEMPT_PREFIXES` 不含 `/api/v1/auth/*` 与 `/api/v1/instance/info` → 正式包形态下登录/激活/免登录预取在网关层 401，**企业实例无法登录**。项目方当前体验路径（开发形态 REQUIRE_AUTH=false）不受影响。
- **QA 复现证据（本机真进程 app.server:app）**：true 形态 GET /api/v1/instance/info → 401 `{"detail":"Authentication required"}`（网关信封）、POST login → 401 同体未达企业路由；false+已迁移对照 → info 200 正常 DTO、login 401 `{"error":{"code":"bad_credentials"}}` 企业信封可达。
- **验收盲区根因（QA 自认计入）**：QA 63 项以 register_enterprise_routes 最小应用测（无外层网关），CI smoke 六步不含登录流——两层都绕开"完整 server×强制鉴权"组合。教训入册：**交付形态的组合面（网关×路由×env）必须至少一条端到端用例**。
- **新增用例 QA-EP0-X04（C 类回归，永久）**：REQUIRE_AUTH=true + enterprise 真进程 → ①instance/info 免登录 200 ②login 达企业路由（200/企业信封）③登录后业务面正常 ④停用/错误码语义不变。修复合入后以 X04 复验销 D004；建议 CI smoke 插入登录断言（DevOps 裁量）。
- **终局判定修订**：**Docker 正式形态在 D004 修复+X04 复验前不可交付试用企业**；开发体验形态与已交付报告结论不受追溯影响，但报告读者须知该形态差异。


---

## 新增用例登记｜X05 首管理员 bootstrap 端到端（D005，产品裁决语义，待后端契约+前端落地后执行）

断言三件套（验收=后端 bootstrap 契约 + 前端 SetupView 合入后真进程执行）：
- X05-1 本机首建：needs_bootstrap=true 时，回环来源（127.0.0.1/::1）POST bootstrap 建号端点 → 成功创建首个 admin（绑定 13373013103 认领存量语义，与裁决④一致）+ 该账号可登录 + instance/info.needs_bootstrap 转 false；
- X05-2 非回环拒绝：needs_bootstrap=true 时，非回环来源调用同一端点 → 拒绝（403/401，不泄漏端点存在性差异）；
- X05-3 通道永久关闭：bootstrap 完成后（needs_bootstrap=false），任何来源（含回环）再调 bootstrap 端点 → 拒绝；重复首建不存在第二管理员通道。
- 附带目检（随 W10 补注）：needs_bootstrap=true 时登录页自动跳转 SetupView（前端落地后浏览器实测）；SetupView 不含命令行要求文案（"产品内完成"承诺）。
- 反向纪律断言：DevOps 本机 SQL bootstrap 不再作为部署路径——文档/向导文案若引导命令行建管理员判 FAIL（应急工具属性仅限"忘记管理员密码"级）。

执行状态：BLOCK（等后端契约+实现、前端 SetupView 跳转；播报到达即跑）。与 X04 同为交付形态（Docker）出场 gate 恢复无条件版本的必要条件。


---

## 销项记录｜X04+X05+D006 双销项完成（2026-10-30，main@34ed119，真完整 server 进程）

套件 test_qa_ep0_x04_x05_d006.py **2/2 PASS**（uvicorn app.server:app 完整服务，非最小应用）：
- X04 四断言全绿：REQUIRE_AUTH=true 下 ①instance/info 免登录 200 ②login 达企业路由建会话 ③业务面无会话 401 企业信封/有会话 200+快照可写 ④422 payload_not_allowed 语义不变——**D004 销项**；
- X05 三断言全绿：①回环首建 pending admin+一次性码（激活前 needs_bootstrap 保持 true，激活后转 false）②**真非回环（本机 LAN IP 经 0.0.0.0 绑定）403 bootstrap_loopback_only 实测**③完成后回环再调 409 bootstrap_done 通道永久关闭——**D005 API 面销项**（SetupView 前端一屏未落地前，Docker 首装的 UI 跳转仍差最后一屏，端到端目检项随 FE 落地补 W10 补注）；
- D006 双形态锁死：true 与 **false 误配对照实例**下个人遗留业务面（/api/tasks）均无条件 401 企业信封——**D006 销项**；
- 豁免面探针（网关三分后 _AUTH_EXEMPT_PREFIXES 透传面）：/api/models、/api/config/announcements、/api/health=200（设计公开面）；/api/download/、/api/admin/users=404（企业实例未挂载个人数据面）——无企业数据裸露。
- 全量回归：QA 五套件 64/64 PASS（增量1 结构+HTTP+M+本机收口+W 抓包）于修复后 main 复跑，零破坏。

**交付形态判定恢复**：后端侧三单（D004/D005/D006）QA 复验全绿；Docker 正式形态剩余唯一差项=FE SetupView（契约 v1.1 第13条已备），落地+X05 目检补注后"首个试用企业部署"叙事可恢复无条件版本。


---

## 缺陷登记 D007（=UI 走查 W-D005-B）+ 新用例 X06（2026-10-30，main@d598b2e 实测坐实）

**D007｜P0（Docker 首装场景必踩）｜首管中断死循环**：needs_bootstrap 判定=无 active admin，而 bootstrap 门槛=存在任何 admin 即 409——两步之间刷新/关页（邀请码仅存内存必然丢失）后：重进登录页 needs_bootstrap=true → 自动跳 /setup → 第一步重放 → 409 bootstrap_done（**错误码语义还是假的：根本没 done**）→ 前端"通道已永久关闭"误导 → 回登录页 → 再跳 setup → **产品内无恢复路径**，违背 D005"产品内完成"承诺本体。
- QA 复现（真进程全新库）：bootstrap 首建 200 → 立即重入 → 409 bootstrap_done 且 needs_bootstrap 仍 true——死循环成立，与 UI 源码推演互证一致。
- 影响面：8010 体验实例不受影响（admin 已激活）；正式客户首装中途关一次浏览器即踩中。

**X05-4 重入用例（产品裁决定稿编号，原登记 X06 并入；入 C 类回归永久）**：
- X05-4a 首建后未激活重入：bootstrap 成功→再次 bootstrap → **200 重发新邀请码**（旧码作废），needs_bootstrap 保持 true，新码可正常 activate；
- X05-4b 激活后永久关闭（X05-3 语义保留）：activate 完成后任何再调 → 409（此时 bootstrap_done 语义为真）；
- X05-4c 前端该态文案如实：重入引导"重新生成激活码并继续"，不得出现"已完成/永久关闭"误导；
- X05-4d 重入仍受回环限制（非回环重入 403，不因可重入而放宽）。

**双销项状态修订**：X04/D004、D006 销项维持；**D005 转"有条件"——SetupView 本体+契约面通过，D007(=W-D005-B) 修复+X05-4 复验前 Docker 首装叙事维持带雷状态**。

> 产品裁决（cmsg_01m659k6gamgww226acq8vdn8h）已采纳：重入语义=无 active admin 时撤旧码原子重发、bootstrap_done 置位后才永久 409；X05-4 四断言与裁决三点一一对应，随双销项批执行。
