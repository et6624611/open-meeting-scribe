# 企业版 P0 后端设计：单实例多用户数据层与 API 契约

- 版本：**v1.1（契约 v1.0 冻结 + 增量2–4 实现校准修订，见 §7.1）**——v1.0 冻结时点 2026-10-29 09:30 UTC；v1.1 变更需在本文档"变更记录"登记并通知依赖方
- v0.2 变更：纳入产品经理裁决（cmsg_01m63fn448vz5fta7ahrggq9rk）——契约插单①visibility ②sync_status ③邀请码自助设密码无初始密码下发、服务停用只读语义、老数据归属"告知即过"无回执、同意卡三行文案锁定为出境契约措辞；纳入 cmsg_01m63frf0zk4ap0966st6t9hft 裁决——AI 默认零出网开关（§1.7）、设备配对 token（§1.8）、账号停用数据保留语义（§1.8）、录音 per-task 契约（§1.8）
- 作者：后端工程师
- 日期：2026-10-29
- 依据裁决：项目方 2026-10-29（cmsg_01m63fehgb3ewqjd24rgkb14fx）——双产品线、内网私有化、仅定稿文本上服务端、存量数据归手机账号 13373013103、管理员建号
- 上位文档：shared/REVIEW-MULTIUSER-CONTEXT-ARCH-20261029.md
- 代码基线：main @ 75e05a5（本文所有"现状"引用均经实查）

---

## 0. 架构分层总纲（两平面模型）

P0 将系统明确拆为两个平面，**接口互不交叉**：

| 平面 | 进程位置 | 职责 | 数据 |
|------|---------|------|------|
| 本地控制面（Client Node） | 用户自己机器上的桌面客户端（现有 desktop.py 形态演进） | 录音、实时 ASR、本地引擎、声纹、凭据、音频文件 | 全部留本地数据目录（用户可设定路径） |
| 服务端数据面（Enterprise Server） | 企业内网 Docker Compose 实例 | 账号/权限、定稿文本上下文存储、（待裁决：LLM 摘要代理） | SQLite + 文本 blob，仅定稿内容 |

同步方向唯一：**客户端 → 服务端，单向推送定稿文本快照**（outbox 模式）。P0 不做双向实时同步（P1 命题）。

---

## 1. API 契约草案（前端/UI/QA 的前置依赖，优先交付）

### 1.1 通用约定

- 服务端命名空间统一 `/api/v1/*`；与现存本地端点（`/api/record/*`、`/api/engine/*` 等）**物理分离**——本地控制面端点不出现在服务端实例上。
- 鉴权：企业版实例强制 `REQUIRE_AUTH=true`（不再有默认放行形态）。会话为 httpOnly JWT cookie（复用现有中间件），私有化场景登录方式仅一种：**账号密码**；密码由用户凭**邀请码自助设置**（裁决③插单：管理员不经手任何密码，**无初始密码下发环节**）。GitHub OAuth / SMS 端点在企业版路由注册时直接不挂载（QA 可据此做出境与攻击面枚举）。
- 主体模型：`role ∈ {admin, member}`；`admin` 即"启用服务的管理员"。bootstrap 管理员由初始化向导创建（见 §5）。
- 错误体统一：`{ "error": { "code": "<机器码>", "message": "<人类可读>", "current_rev": <可选> } }`；401/403/404/409/422 语义见各端点。
- 时间一律 UTC ISO-8601；ID 一律服务端生成 ULID（迁移场景保留旧 task_id 作 `legacy_id` 映射，不要求全局一致）。

### 1.2 认证与账号

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | `{account, password}` → 设 cookie。account 为手机号或管理员指定登录名；密码未设置（未走激活）→ 401 `code=password_not_set` 并提示使用邀请码激活 |
| POST | `/api/v1/auth/activate` | `{invite_code, password}` 邀请码自助设密码 + 激活账号 + 建会话。**无初始密码概念**：管理员建号只产生 pending 用户 + 邀请码，密码全程由用户自设（裁决 cmsg_01m63fn448vz5fta7ahrggq9rk #1/#插单③） |
| POST | `/api/v1/auth/logout` | 清会话 |
| GET | `/api/v1/auth/me` | 当前用户 `{user_id, display_name, role, status, tenant_id}` |
| POST | `/api/v1/auth/change-password` | 主动改密（需验证旧密码） |

### 1.3 管理面（仅 admin，越权即 403）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/users` | 用户列表（含 status: active/disabled/pending） |
| POST | `/api/v1/admin/users` | 建号 `{display_name, account(手机号/登录名)}` → 创建 pending 用户并自动生成一次性邀请码（明文仅返回一次，服务端只存 hash）；**不返回任何密码**（裁决插单③） |
| PUT | `/api/v1/admin/users/{user_id}/status` | 启用/停用（停用即吊销全部会话） |
| POST | `/api/v1/admin/users/{user_id}/reset` | 重置密码 = 作废旧会话 + 重新签发邀请码（管理员仍不经手新密码，对齐裁决 #1） |
| POST | `/api/v1/admin/invites` | 生成邀请码（明文仅返回一次，服务端只存 hash；可设有效期/次数） |
| GET | `/api/v1/admin/invites` | 邀请码列表（脱敏：仅前 4 位 + 状态） |
| POST | `/api/v1/admin/instance/close` / `open` | 服务开关（管理员"启用服务"语义的运行时开关）。**停用语义按裁决 #4**：`close` 后**已登录会话不踢出、读操作继续放行**（员工可查看已同步内容），全部写操作（快照 PUT/资产 PUT/删除）→ 503 `code=service_closed`；`/api/v1/auth/login` 新登录 → 403 `code=service_closed`（登录页文案"请联系管理员"）；`/api/v1/instance/info.service_open=false` 供前端渲染顶部横幅 |

### 1.4 上下文数据面（核心契约：定稿文本上传 + 幂等重传）

资源模型：**一个会议 = 一个 context task**，服务端权威存储其定稿文本包。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/context/tasks` | 本人可见 task 列表（P0 = 本人 owner 的 task；分页 + 增量参数 `since`） |
| GET | `/api/v1/context/tasks/{task_id}` | task 定稿全文 + 元数据 + `server_rev` |
| PUT | `/api/v1/context/tasks/{task_id}/snapshot` | **上传/更新定稿文本快照**（契约见下） |
| DELETE | `/api/v1/context/tasks/{task_id}` | owner 删除（软删 → 保留 30 天回收站，admin 不可见内容；立即物理删除与否=待裁决 Q4） |

**上下文实体 DTO 统一字段（裁决插单①）**：所有上下文实体（task/资产）的列表与详情响应固定携带：

```
{ "visibility": "personal",        // P0 恒为 personal（服务端由 scope 列映射，UI 徽标组件依赖）
  "sync_status": "synced",         // 服务端视角最近对账态，见下
  "server_rev": N, "content_hash": "..." }
```

**sync_status 契约（裁决插单②）**——定稿文本同步队列的状态枚举 `{pending, syncing, synced, error}`，双端各管一段：
- **队列侧（权威）**：outbox 在客户端本机，队列状态由**本地控制面**新增只读端点 `GET /api/sync/queue` → `[{task_id, status: pending|syncing|synced|error, queued_at, last_error, retry_after}]`；Web UI 经 local origin 查询（与前端双 origin 封装一致），驱动"待同步到公司服务器"提示。服务停用期间 status 渲染映射 error→横幅语义由前端处理。
- **服务端侧（对账）**：task DTO 中 `sync_status` = 服务端按 `content_hash`/`server_rev` 对最近一次成功入库的判定（`synced` | `stale`），仅供非录制设备查看时显示"最后同步于…"；两者不一致以队列侧为准。

**快照上传契约（离线队列重传的幂等基础）**：

```
PUT /api/v1/context/tasks/{task_id}/snapshot
Idempotency-Key: <client_mutation_id>   # 客户端 outbox 每条记录的全局唯一 ID（UUIDv7），重传时不变
If-Match-Rev: <base_rev>                # 客户端所基于的 server_rev；首次上传为 0

Body（白名单字段，见 §2.4 出境清单）:
{
  "meta":     { "title", "meeting_time", "participants_text", "source": "client|web_import", "legacy_id" },
  "formal":   <转写定稿文本>,
  "summary":  <纪要文本>,
  "decisions": [ {decision_id, text, status_id, status_text, superseded_by, ...} ],
  "notes":    <笔记文本>,
  "insights_html": <洞察板 HTML 文本> | null,
  "content_hash": "<sha256(规范化正文)>"   # 客户端计算，服务端原样记录，用于对账
}

Response 200: { "server_rev": N, "content_hash": "...", "stored_at": "..." }   # 幂等命中：同 Idempotency-Key 返回首次结果，不重复写入
Response 201: 首次创建
Response 409: { "current_rev": M }   # If-Match-Rev 过期 → 客户端拉取最新、本地合并后以新 mutation_id 重推
Response 422: 字段超出白名单（防御性拒绝，QA 出境用例断言点）
```

幂等与乱序规则：
1. 服务端对 `(user_id, client_mutation_id)` 建唯一约束；同 Key 重放 → 直接返回原结果（HTTP 语义 200，响应体含 `idempotent_replay: true`）。
2. 同一 task 上 mutation 严格按 rev 串行：`base_rev != current_rev` → 409。**outbox 设计规则：客户端每个 task 的队列内只允许顺序消费，跨 task 可并行**；断网期间同一 task 多次编辑在客户端本地合并为一条最终快照再入队（last-merge-wins），天然规避中间态乱序。
3. 客户端 outbox 落本地数据目录 `outbox/<user>/`，成功回执后出队；重启恢复 = 扫描 outbox 重放（凭 Idempotency-Key 安全）。

**P0 明确不提供**（QA 白名单外的服务端能力，抓包应得 404）：
- 任何音频端点（`/api/audio`、`/api/download` 中的媒体部分不上服务端；Web 端无音频回放，仅文本——见 §6 待裁决 Q1）；
- 团队/企业共享读（scope 字段已预留但 P0 全部 `personal`）；
- 反向推送/WS 订阅（P0 Web 端轮询 `since` 即可）。

### 1.5 个人资产端点（术语/热词上云部分）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | `/api/v1/context/assets/hotwords` | 本人热词/术语资产全文快照（同 §1.4 幂等头） |
| GET/PUT | `/api/v1/context/assets/speaker-aliases` | 发言人**别名映射**（仅"显示名↔speaker 标签"文本；声纹 embedding 不在字段内，422 拒收） |

### 1.6 实例信息

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/instance/info` | 免登录最小信息：`{product: "oms-enterprise", version, service_open, ai_enabled, needs_bootstrap}`；初始化向导、客户端配对与前端"AI 助手未开启，联系管理员"提示均依赖本端点 |

### 1.7 AI 出网开关（实例级，裁决 cmsg_01m63frf0zk4ap0966st6t9hft QA-Q1：默认零出网）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | `/api/v1/admin/instance/ai` | `{enabled: false(默认), provider: {base_url, model, api_key(只写不回显)}}`；开启时**逐域加白名单**：允许出网的 host 集合仅 = 管理员配置的 base_url 域名，服务端网络层强制（非仅应用层判断） |
| POST | `/api/v1/ai/summary/generate` | `{task_id}` Web 端补生成纪要（仅 AI 开启时）；关闭态 → 409 `code=ai_disabled` |

语义：企业实例出厂**零出网**——除管理员显式开启 AI 并配置域名外，服务端进程不发起任何外部网络请求（QA 出境白名单对端枚举断言点）；服务端所有 LLM 代理调用写 `egress_audit`。定稿文本上云本身不依赖 AI 开关（快照 PUT 永远允许）。个人版 LLM 链路（客户端本机 Key）完全不经此通道。

### 1.8 设备配对（录音助手，前端契约请求⑤）与服务停用/账号停用数据语义（QA-Q3 裁决）

**配对流程（浏览器 Web 会话 ↔ 用户本机录音助手）**：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/pairings` | 需 Web 登录态 → 一次性短效配对码 `{pairing_code, expires_at(10min)}`，Web"连接录音助手"页展示 |
| POST | `/api/v1/auth/device-activate` | 助手凭 `{pairing_code, device_name}` 兑换**长效 device token**（服务端只存 hash；`Bearer device_token` 仅允许 §1.4/§1.5 上下文写端点与 `GET /api/v1/auth/me?as=user`，不允许登录态全量 API） |
| GET/DELETE | `/api/v1/devices`、`/api/v1/devices/{device_id}` | 用户自助管理已绑定设备；DELETE 即刻吊销该 device token（其 outbox 后续重传 403 `code=device_revoked`） |

**本地控制面 per-task 契约（前端契约请求①）**：助手与浏览器同机经 local origin（127.0.0.1）通信；浏览器首连 `GET /api/local/handshake` → `{local_token, paired_user_id}`，此后本地 `/api/record/*` 与 `/ws/transcript/{task_id}` 一律携带 `X-OMS-Local-Token`，录音状态接口按 `task_id` 参数化（`/api/record/status?task_id=`）。P0 一台机器同一时刻仅绑定一个 paired user，切换用户须重新配对——串音防护的结构前提。

**账号停用/服务停用数据保留语义（QA-Q3 裁决落地）**：
- `PUT users/{id}/status=disabled`：即刻吊销全部 session 与 device token（登录 403 `code=account_disabled`、同步重传 403）；其 ctx_tasks/ctx_assets **保留在企业服务器上（归属企业）**，不自动到期删除；管理台仅见元数据计数（内容不可读，QA-Q2），提供"整包删除该账号数据"操作（二次确认 + 审计留痕，物理删除幂等）。
- 实例 `service_closed`（裁决 #4）：会话不踢出、读放行、写 503；与账号停用是两条独立状态线，错误码不混用。

---

## 2. 数据层设计

### 2.1 DATA_ROOT 与实例布局

现状：全局 `DATA_ROOT = Path(os.environ.get("OMS_DATA_ROOT", Path.cwd() / "data"))`，一次性替换 store.py / task_store.py / settings_store.py / core/users.py 等十余处硬编码（评审已列明细）。

企业实例布局（Docker 卷挂载点即 DATA_ROOT）：

```
DATA_ROOT/
  instance.db                  # SQLite（WAL）：唯一权威业务库
  instance.db-wal / -shm
  blobs/<user_id>/<task_id>/rev<N>.json.gz   # 定稿快照压缩 blob（正文大，不进 DB 行）
  outbox/                      # 仅本地控制面使用；服务端无此目录
  legacy/                      # 存量迁移期源数据只读挂载（见 §5）
  secrets/instance.key         # 实例密钥（JWT_SECRET、加密主密钥），初始化向导生成
```

**服务端不设 users/<id> 目录树**——用户隔离在 DB 行级（user_id 列 + 查询强制过滤），blob 路径含 user 前缀且访问必经归属校验；"每用户本地数据目录"属于客户端侧概念，勿与实例侧混淆。

### 2.2 SQLite Schema（含 owner/scope 预留，P1 不再迁移）

```sql
-- 账号域
users(user_id ULID PK, login_account TEXT UNIQUE, phone TEXT UNIQUE NULL,
      display_name, password_hash, role CHECK(role IN('admin','member')),
      status CHECK('active','disabled','pending'), needs_password_change BOOL,
      created_at, updated_at)
sessions(session_id PK, user_id FK, jwt_jti UNIQUE, expires_at, revoked_at NULL)
invites(code_hash UNIQUE, created_by FK, max_uses, used_count, expires_at, disabled_at)
device_tokens(device_id PK, user_id FK, token_hash UNIQUE, device_name,
              revoked_at NULL, last_used_at)                    -- §1.8 配对
pairings(pairing_code_hash UNIQUE, user_id FK, expires_at, redeemed_at NULL)
instance_config(key TEXT PK, value_json, updated_by FK, updated_at)
  -- 键：service_open(bool), ai_enabled(bool), ai_provider{base_url,model,api_key_enc},
  --     egress_allowlist([host]), bootstrap_done(bool)；api_key 用 instance.key AES-GCM 加密

-- 上下文域（所有业务表强制三件套：owner_user_id / scope / tenant_id）
ctx_tasks(task_id TEXT PK,                 -- 'tsk_'+ULID；legacy_id 另列
          owner_user_id FK NOT NULL,        -- ▸ 预留列：P1 晋升不改表
          scope TEXT NOT NULL DEFAULT 'personal'
              CHECK(scope IN('personal','team','enterprise')),   -- P0 恒 personal
          tenant_id TEXT NULL,              -- P0 恒 NULL（单实例=单租户）
          acl TEXT NULL,                    -- P0 恒 NULL；P1 JSON {reader:[...],readOnly:bool}
          title, meeting_time, participants_text, source,
          status CHECK('active','deleted'), deleted_at,
          current_rev INT NOT NULL DEFAULT 0, content_hash, updated_at)
CREATE INDEX idx_ctx_tasks_owner ON ctx_tasks(owner_user_id, status, updated_at);

ctx_revisions(rev_id PK, task_id FK, rev INT, client_mutation_id TEXT,
              blob_path, content_hash, created_at,
              UNIQUE(task_id, rev), UNIQUE(owner_user_id, client_mutation_id))  -- 幂等键
ctx_entities(task_id FK, kind CHECK('formal','summary','decisions','notes','insights_html'),
             payload_json, current: BOOL)   -- 快照内分字段寻址，支持字段级 diff/对账

ctx_assets(asset_id PK, owner_user_id FK, kind CHECK('hotwords','speaker_aliases','decision_statuses'),
           scope DEFAULT 'personal', tenant_id NULL, acl NULL,
           current_rev, blob_path, updated_at, UNIQUE(owner_user_id, kind))

-- 凭据/偏好（服务端仅存非敏感偏好；见 §3）
user_prefs(user_id FK PK, prefs_json, updated_at)

-- 迁移台账（§5）
migrations(legacy_id TEXT PK, target_table, target_id, source_hash, migrated_at)

-- 出境审计（QA 数据出境白名单的可证伪来源）
egress_audit(ts, user_id, action, object_ref, byte_len, client_mutation_id)
```

并发与完整性：WAL + `busy_timeout`；写路径单连接串行（asyncio 队列包住 sqlite3），P0 不引入 ORM 以贴近现状；所有查询经统一 DAO 层，**DAO 函数签名强制携带 `actor_user_id`，无 actor 参数的查询直接 lint 失败**（越权测试可证伪的结构性保证，响应 QA 的框架需求）。

### 2.3 与现有 JSON 实体的映射

| 现状（全局单文件） | 去向 |
|---|---|
| data/tasks/<id>.json（含 notes/decisions/summary 内嵌） | ctx_tasks + ctx_revisions + ctx_entities（文本字段拆分入库） |
| data/decision_statuses.json | 两拆：实例级字典表（admin 编辑，全员可读）+ 个人自定义状态入 ctx_assets(kind=decision_statuses) |
| data/speakers.json / meeting_mappings.json | 显示名别名 → ctx_assets(speaker_aliases)；声纹 registry/embedding → **留本地，不迁移** |
| data/hotwords.txt / hotword-mappings | ctx_assets(hotwords)（本人份）；实例共享词表 P1 再议 |
| data/projects.json / project_index | P0 不上服务端（项目=本地文件夹绑定，语义属于本地控制面）；Web 端 P0 无项目视图——待裁决 Q3 |
| data/usage/*.jsonl | 服务端改为本地实例统计（供管理台概览），不含正文文本 |
| agent-workspace/、recordings/、chat_attachments blob | 全部留本地，服务端无对应目录 |

### 2.4 数据出境白名单（与裁决一致，供 QA 直接建枚举用例）

对外口径锚点（产品经理定稿，cmsg_01m63fn448vz5fta7ahrggq9rk #5，与同意卡/「数据位置」三行表/登录页隐私说明逐字一致，本契约字段集合以此为承诺边界）：

> 你的会议录音和音频只保存在这台电脑上，不会离开本机。
> 会议定稿后的文字内容（转写文本、纪要、决策流、笔记、术语）会保存到公司服务器，方便你在任何设备上查看。
> 你的声纹信息和 API 密钥永远不上传。

允许出现在 客户端→服务端 请求体中的**全部**字段：§1.4/§1.5 列出的快照白名单字段（纯文本/JSON 文本）——逐项映射承诺第二行的五个名词（转写文本=formal、纪要=summary、决策流=decisions、笔记=notes、术语=hotwords/speaker-aliases），无第六类。
禁止（服务端路由 422 防御性拒收 + 客户端出境拦截器双重门禁 + 抓包 0 命中断言）：
音频字节/文件引用路径之外的二进制、API Key/密码（change-password 与登录除外，走 TLS）、声纹 embedding、本地绝对路径、聊天附件 blob、LLM/ASR 原始凭据配置。

---

## 3. settings 按用户加密拆分

现状 settings.json 单文件含 API Key + 引擎配置 + feature flags，全局共享。

- **本地控制面（每台客户端）**：`DATA_ROOT_LOCAL/settings/<user_id>.enc.json`。API Key 等凭据按登录用户分文件；加密 = 主密钥派生（机器绑定 factor + 用户口令 PBKDF2）AES-GCM。断网闭环承诺不变：凭据只在本机。
- **服务端实例**：不存任何用户 API Key。仅存 user_prefs（UI 偏好、非敏感）。
- feature flags：拆为实例级（admin 管理台维护，入 instance.db）与本地级（留在客户端）。
- 例外通道 = 待裁决 Q2：若企业版摘要改由服务端代理 LLM，则服务端需要持有**企业自管的实例级 Key**（admin 在服务端录入、加密存 instance.key 保护下）——这不是"用户 Key 上云"，是"企业基础设施自带凭据"，但必须在数据治理承诺中单列。

---

## 4. 本地录音控制面 ↔ 服务端边界（接口归属清单）

保持 127.0.0.1 监听、永不出现在企业实例的路由：`/api/record/*`、`/ws/transcript/*`、`/api/engine/*`、`/api/models/*`、`/api/voiceprint/*`、`/api/workspace/open-*`、`/api/projects/*`（本地文件夹语义）、`/api/audio` 与 `/api/download`（媒体部分）。
企业实例上挂载的路由：§1 全部 `/api/v1/*` + 静态 Web。
判定规则（供前端封装双 origin client）：**本地控制面 = 现 desktop.py 进程原样承担；企业服务端 = 现 cloud_api 形态收敛为 /api/v1；两者路由集合零交集**，QA 按实例形态各出一份攻击面清单。

---

## 5. 存量单机数据归属与迁移（专节，裁决④落地）

场景：老用户在个人版桌面端升级/切换到企业实例时，本机全局数据首次归属到指定账号。

1. **默认初始账号**：手机账号 `13373013103`。初始化向导（DevOps 交付物）第一步由管理员**自助设置密码**创建该 bootstrap admin 账号（对齐裁决插单③：全程无密码下发）；迁移工具将存量数据绑定到该 login 对应的 user_id（向导完成前迁移不允许执行）。
2. **迁移入口**：客户端升级后出现"将本机历史会议导入企业空间"一次性动作（默认勾选、可跳过、可稍后手动触发）。流程：`oms-migrate --to <instance> --account 13373013103`。**归属确认按裁决 #3="告知即过"**：UI 归属卡纯告知，**后端不提供任何"用户确认归属"回执端点**，迁移工具与账号系统之间无确认握手；"音频仍留原机"由 §2.4 三行文案直接陈述。
3. **搬运范围**：tasks 定稿文本（含 notes/decisions/summary，逐条走 §1.4 快照 PUT，天然复用幂等）+ 本人热词 + 发言人别名。**不搬运**：音频、声纹、凭据、projects、agent-workspace（清单同 §2.3）。
4. **归属规则**：全部迁移对象 `owner_user_id = 13373013103 的 user_id`、`scope='personal'`。老数据不因"共享给同事"被隐式扩大可见范围——迁移只换存储位置，不换可见性。
5. **幂等与对账**：`migrations` 台账按 `legacy_id + source_hash` 去重，重复执行安全（重放返回既有目标）；迁移结束输出对账单（源 task 数 / 入库数 / 跳过数+原因 / content_hash 抽检结果），落本地 `logs/`，这是 QA 升级回归的门禁物证。
6. **回滚**：迁移是"复制-校验-保留源"三段式，源数据目录全程不动不删；服务端侧按台账批量 DELETE 即完全撤销。不做破坏性割接。
7. **边界情况**：同机多人共用过老数据的（历史上无用户维度），一律全量归 13373013103，由该账号后续在 P1 团队能力下自行处置——P0 不做"老数据二次拆分"，避免复杂度。

---

## 6. 产品问题裁决登记（v0.2 更新）

已裁决并写入本契约：
- Q1 Web 端音频 → **无音频端点**：企业版默认形态即"只能看和编辑文字、不能录音"（裁决 #2），服务端不挂载任何音频回放/下载路由。
- Q2 摘要生成位置 → 双通道并存：客户端本机 Key 生成（默认路径，零冲突）+ **服务端 AI 代理为管理员显式开启的可选增值**（默认关、逐域白名单、强制网络层门禁）——见 §1.7（QA-Q1 裁决）。
- Q3 纯 Web 用户价值 → 接受"查看+补录文本"为 P0 默认形态（裁决 #2，PRD 向项目方明示）。
- Q4'（=QA-Q3）账号停用数据保留 → 保留归属企业、可整包删除、不自动到期——见 §1.8。

仍开放（均不阻塞契约冻结与开工，按默认值先行）：
- Q4 用户自助删除的回收站语义：默认按本契约"软删 30 天、管理员不可读内容"实现；若项目方合规倾向"立即物理删除"，仅需改 DELETE 端点一处，不影响 schema。
- Q5 决策状态字典两层化（实例级+个人级）后，管理台是否含字典维护页：后端接口已按两层实现，UI 出不出页面由产品排期，不阻塞。

## 7.1 v1.1 修订（增量2–4 实现校准，2026-10-29；依赖方已群内播报）

1. **WS local_token 承载（前端问题裁决）**：浏览器 WebSocket 不能自定义请求头 → `/ws/transcript/{task_id}` 以查询参数 `?oms_local_token=` 承载；HTTP 面维持 `X-OMS-Local-Token` 头。契约 §1.8 相应修正。
2. **本地控制面端点实装**（assistant 形态，`OMS_EDITION=assistant` 才挂载）：`GET /api/local/handshake`（内存态 token，TTL 1h）、`POST /api/local/register`（配对码兑换 device token，state.json 0600）、`GET /api/sync/queue`、`POST /api/local/sync/enqueue`、`POST /api/local/sync/flush`、`GET /api/local/state`。
3. **outbox 合并策略（P0）**：409 时采纳服务端 current_rev 为新 base、同 mutation 重推（last-writer-wins）；断网指数退避（5s→5min 封顶）；恢复后到期自动收敛，重放幂等。字段级冲突合并留 P1。
4. **助手→实例通道强制直连**（不采纳环境代理变量）：代理会构成不可枚举出网点，与零出境纪律冲突；企业代理出站列 P1 显式配置项。
5. **错误码补充实现**（QA 三缺陷修复，c23b247）：`403 account_disabled`（停用+正确密码）、`403 device_revoked`（出示 Bearer 但凭据失效）、`400 invalid_header`（畸形 If-Match-Rev，快照/资产两端）、`422 client_mutation_conflict`（mutation 跨 task 复用）；`POST /api/v1/auth/device-activate` 响应增 `user_id` 字段。
6. 迁移命令面扩展：`python -m app.db migrate-legacy --source <dir> --account <login>`（§5 工具化落地）。

## 7. 工作量确认（设计→实施）

维持评审结论：P0 后端 ≈ 3-4 周单人，今晚指令下压缩推进、按增量交付。分解：DATA_ROOT+DAO 强制 actor 层（S）、SQLite schema+迁移（L）、快照/幂等/审计端点（M）、账号+邀请码+配对（M）、settings 加密拆分（M）、存量迁移工具+对账（M）、AI 出网门禁（S）、JWT_SECRET 稳定化与测试基建（S）。实施顺序不可反：schema/DAO → 数据面端点 → 迁移工具 → 账号面。

对 DevOps 契约（升级回滚）：
- 迁移命令名：`python -m app.db migrate`（幂等、事务化、失败中止不切流；`oms-db` 为其脚本别名）；健康检查沿用 `/healthz`。
- **P0 全部 schema 变更 additive-only**（只加表/加列，不改不删既有列）——满足"schema 双版本可读"的回滚硬前提；破坏性变更最早 P1 且需配套 expand-contract 流程。
- 数据卷契约修正：bind mount 至 `DATA_ROOT` 根即可；实例侧布局为 `instance.db + blobs/<user_id>/…`（**无 users/<id> 目录树**，用户隔离在 DB 行级，见 §2.1），compose 请以此为准微调。
