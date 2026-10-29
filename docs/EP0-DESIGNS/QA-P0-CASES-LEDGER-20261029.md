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

**移交后端增量2 的两条端点层映射要求（防 5xx 违规，非当前 FAIL）**：
1. `client_mutation_id` 跨 task 复用现抛裸 ValueError → 端点层必须映射 4xx（建议 409/422），直落 500 将违反 A2"禁止 5xx"判定；
2. 密码校验类 ValueError（如长度不足）→ 422 语义，勿 500。

结论：**P-001 增量1 数据层结构断言全绿，QA 侧无阻塞**；下一执行点=端点层交付后 W/A/P 系 HTTP 全量 + UI W1 走查闭环（与项目管理员检查点一致）。
