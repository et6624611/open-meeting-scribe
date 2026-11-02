# 企业版 P1 后端契约：多团队空间数据模型与权限契约

- 版本：**v1.0（正式基线，随产品经理 2026-11-02 契约冻结令 cmsg_01m6d3zqvc3esgbhryqgzj9d6k 冻结；文件名保留 DRAFT 后缀仅作历史引用，版本号以本行为准）**
- v1.0 原地补注（2026-11-02，PM 拍板 cmsg_01m6d6s8g6nmd6sdetqh125qvk）：§8 成员端点请求体终态 {user_ids:[...]} 批量+422 错误面（D010），其余冻结内容不动
- v0.1→v1.0-draft 变更：§7 五题全部裁决销项；缺口A expand-contract 获产品批准（additive-only 首个例外成立）
- v1.0-draft→v1.0 变更（冻结令四项拍板落账）：① B5 第五锁定文案逐字入 §8；② U4 落定——发言人别名团队面维持只读；③ U5 落定——"项目=跨会议归组"不进 P1 首版；④ UI 规格 §9 字段依赖六条全部入 §8 核对项，两条冻结必含项（团队面 409 含 current_rev+最新全文快照；变更记录枚举覆盖"删除→恢复"闭环）写入契约正文。**K1 阻塞项随拍板定版**：§1/§8 审计枚举终名十二值（decision_delete/decision_restore 回滚面 + member_add/member_role_change/member_remove/role_transfer/team_archive 成员治理域），无"解散"字样、无审批态值
- 作者：后端工程师
- 日期：2026-11-02
- 裁决依据：项目方 2026-11-02（cmsg_01m6d392sd0cq3vaggs3rcgvqc）+ 产品经理复述定稿 v0.2（shared/REQUIREMENT-SPACES-P1-DRAFT-v0.2.md）+ UI 交互规格 v1.0（shared/P1-SPACES-UX-SPEC-v1.0.md）+ 产品经理冻结令（cmsg_01m6d3zqvc3esgbhryqgzj9d6k）
- 基线契约：P0-BACKEND-DESIGN-MULTIUSER-20261029.md v1.1（P0 已上线 schema 与 API）

---

## 0. 设计前提（v0.2 五条逐条落到数据层）

| # | 裁决 | 数据层落点 |
|---|------|-----------|
| 1 | 只有两层空间：私有 + 团队，不露出"企业"概念 | 用户可见实体只有 personal/team 两态；"企业级资产"仅作为**后台收集层**存在（§5），永不作为用户界面概念出现 |
| 2 | 团队自由组合、一人多团队、tenant 内多团队 | 新增 teams/team_members 表；团队不挂组织架构（无部门树实体） |
| 3 | 三档成员角色：只读/可编辑/团队管理员；改动留痕 | team_members.role 枚举 + 审计表（§4） |
| 4 | 团队空间内的决策自动成为企业级资产，"只收集不消费" | 决策资产收集表（§5）：入队即收集、只读不可编辑、不建任何消费界面 |
| 5 | 录音与逐字稿永不进团队空间 | 复制发布时**结构性排除** formal 字段与音频引用（§3.2 白名单），非 UI 隐藏而是数据模型层不可达 |

---

## 1. 实体模型（0002 迁移，除一处外全部 additive）

```sql
-- 团队主体
teams(team_id PK, tenant_id NULL, name, created_by FK users,
      status CHECK('active','archived'), created_at, archived_at)
team_members(team_id FK, user_id FK,
      role CHECK('viewer','editor','admin'),          -- 只读/可编辑/团队管理员
      added_by FK, joined_at, UNIQUE(team_id, user_id))
-- 每个团队至少一名 admin（应用层约束：创建者自动 admin；最后一名 admin 离开前必须移交）

-- 任务与团队的承接
ALTER TABLE ctx_tasks ADD COLUMN team_id REFERENCES teams(team_id);
-- 语义：scope='personal' ⇔ team_id IS NULL；scope='team' ⇔ team_id NOT NULL
-- 发布=创建"团队副本"行（§3），私有原件不动——与方案稿"放一份副本上去"逐字一致
CREATE INDEX idx_ctx_tasks_team ON ctx_tasks(team_id, status, updated_at);

-- 写作者归属（多编辑者承接，§6 承接复核第 2 项）
ALTER TABLE ctx_revisions ADD COLUMN actor_user_id REFERENCES users(user_id);
-- 回填 actor_user_id = owner_user_id；新写入两列都填（owner=行归属人/发布人，actor=本次写作者）

-- 团队内容留痕（裁决 3"改动留痕"+ 冻结必含项②"删除→恢复"闭环；K1 拍板定名，无"解散"字样、无审批态值）
team_edit_audit(audit_id PK, team_id FK, task_id FK NULL, rev INT NULL, actor_user_id FK,
                action CHECK('publish','edit','withdraw','decision_publish','decision_withdraw',
                             'decision_delete','decision_restore',
                             'member_add','member_role_change','member_remove','role_transfer','team_archive'),
                target_ref TEXT NULL,      -- decision_delete/decision_restore 指向的决策条目稳定 ID；恢复按钮定位锚
                pre_delete_rev INT NULL,   -- decision_delete 留痕额外记录删除前 rev；decision_restore=重推该历史版本（裁决③）
                content_hash, ts)          -- 只存指针与哈希，不存正文（隐私口径与 P0 egress_audit 同尺）

-- 企业级资产收集层（裁决 4"只收集不消费"）
enterprise_decision_assets(asset_id PK,
      source_task_id FK ctx_tasks, source_team_id FK teams,
      source_rev INT NOT NULL,          -- 捕获时源副本的 rev
      decision_id TEXT NOT NULL,        -- 源决策稳定 ID
      snapshot_json TEXT NOT NULL,       -- 决策文本态冻结快照（含 text/status/时间上下文）
      content_hash TEXT NOT NULL,        -- 快照哈希=追溯锚点
      collected_by FK users, collected_at,
      status CHECK('collected','withdrawn','stale'),
      withdrawn_at, UNIQUE(source_task_id, decision_id))
-- stale 规则：源决策其后任何 rev 修改或删除该决策 → 资产行标 stale 不删除（钩子留给未来的使用决策）
-- 本表 P1 只提供后台查询与导出原子的能力，不挂任何用户界面（QA 验收面：全站无"企业空间"字样）
```

**ctx_assets 的重建需求（唯一非 additive 项，见 §6 承接复核·缺口 A）**：团队共享词表无法在现表表达，需一次受控 expand-contract 重建。

---

## 2. 权限矩阵（DAO 层强制，延续 P0"无 actor 查询即 lint 失败"纪律）

| 动作 | viewer | editor | team admin | 实例 admin | 局外人 |
|------|--------|--------|-----------|-----------|--------|
| 列团队空间/读团队副本 | ✓ | ✓ | ✓ | ✗（内容不可读，延续 QA-Q2） | 404 |
| 编辑团队副本（快照 PUT） | ✗ | ✓ | ✓ | ✗ | 404 |
| 公开（发布副本）/撤回 | ✗ | ✓（自己原件） | ✓ | ✗ | 404 |
| 决策进资产层 | 自动（editor 发布决策即触发收集） | ✓ | ✓ | ✗ | — |
| 建团队/改名 | ✓（任何成员可建自己的团队） | — | — | ✗（实例 admin 不自动进任何团队） | — |
| 加/移除成员、调角色 | ✗ | ✗ | ✓ | ✗ | 404 |
| 归档团队 | ✗ | ✗ | ✓（二次确认） | ✗ | 404 |
| 整包删除团队数据（合规出口） | ✗ | ✗ | ✗ | ✓（留痕，对称 P0 停用账号整包删除） | — |

- 局外人（非本团队成员）访问团队副本一律 404（防枚举，P0 同尺）。
- 实例管理员可见**元数据**（团队数/成员数/资产计数），不可见内容——UI 规格按此设计管理台团队页。
- 用户离职/停用（P0 status=disabled）：自动从全部 team_members 撤 effective 成员身份（行保留审计），其发布的团队副本**保留**（团队空间内容归属团队，不随人走——这正是"信任空间"与 P0"归属+发布"的衔接点）。

---

## 3. 发布/撤回/编辑语义（副本模型）

### 3.1 发布（个人 → 某团队）
1. 复制原件**当前 rev** 为团队副本：新 ctx_tasks 行（team_id=目标团队, scope='team', owner_user_id=发布人, source_task_id=原件 id〔新列，追溯〕）。**一原件可发布到多个团队（裁决①）**：每团队独立副本行、独立时间线，撤回按团队互不影响。
2. 副本携带：title/meeting_time/participants/summary/notes/decisions 文本 + **insights_html 洞察板（裁决⑤：衍生文本，随入）** + 术语引用——**formal（逐字稿）结构性排除**（裁决 5，复制器白名单不含 formal；blob 快照 schema 同步禁字段，422 兜底）。
3. 原件标记 published_copies（计数即可，不锁编辑）。
4. 决策若含团队可见属性 → 资产收集钩子在副本每次 decisions 变化时触发（§5）。

### 3.2 副本编辑（多编辑者）
- 复用 P0 快照 PUT 协议（Idempotency-Key/If-Match-Rev/409），作用于**副本行**；任何 editor+ 成员可写，actor_user_id 记录写作者。
- 冲突语义升级：P0 是"单人离线队列 last-writer-wins"；P1 团队面冲突走 409→diff 合并（UI 规格 §6 并排对比）。**冻结必含项①**：团队面 409 响应必须携带 `current_rev` + 最新 rev 的**全文快照**（形态见 §8），使 UI 无需二次 GET 即可渲染新旧两版全文。个人面 409 形态保持 P0 不变，团队面扩展为单向兼容新增。这是 P0→P1 语义变化点之一，已随冻结令进前端/UI 派工单。
- 原件与副本**不双向同步**：发布后两条时间线独立；撤回=归档副本（原件不受影响）——避免 P1 就背上双向合并的复杂度（P1 风险清单同源规避）。

### 3.3 撤回
- 任何 editor+ 可撤回**自己发布**的副本；团队 admin 可撤回任意副本（治理出口）；撤回=status='deleted' 软删 + 资产行转 withdrawn，留痕完整。
- **删除权与回滚（裁决③）**：editor 可删除团队副本内他人发布的决策条目；回滚=从 team_edit_audit 定位删除前 rev、由任何 editor+ 重推该历史版本内容（副本 revisions 全量保留使回滚天然可行，UI 出"恢复"入口即可，无新协议）。

### 3.4 删除语义
- 原件删除不影响已发布副本（副本独立存续）；副本删除不影响原件与已收集资产（资产层 status=stale 标记源缺失——可追溯性是裁决 4 的核心承诺）。

---

**归档团队（裁决④）**：teams.status='archived' 后拒绝一切写入（发布/编辑/撤回中项除外——成员仍可撤回既有副本）；成员保留只读查看；"整包删除"治理口径留 P2（与实例管理台删除权同构）。新发布到归档团队=409 team_archived。

## 4. 团队共享资产（热词/发言人"全团队一份"）

- 团队词表为 **team-owned asset**（非每人一份）：新表 team_assets(team_id, kind, current_rev, blob_path, content_hash, updated_at, PRIMARY KEY(team_id,kind))，编辑权=editor+，留痕入 team_edit_audit。
- 个人词表与团队词表的**应用合成规则**（转写时用哪份、优先级）属助手本地行为——P1 契约只定义服务端权威态；合成策略已裁决：并集、冲突个人为准（§7.2，不进契约承诺面）。
- 发言人别名：**团队面维持只读（U4 冻结拍板：P1 首版不做共享词表级，避免与声纹本地边界纠缠；需求如有再入 backlog）**。团队副本携带映射后的显示名文本（声纹仍不出本机，与 P0 边界一致）。

---

## 5. 企业级资产层（只收集不消费）

- 触发：团队副本 decisions 字段任何新增/变更/删除 → 同步 upsert enterprise_decision_assets（同事务，幂等按 (source_task_id, decision_id)）。
- 消费面 P1 **零界面**：无 API 读端点暴露列表（内部 status 维护脚本除外）；数据字典与追溯钩子（rev/哈希/collected_by/时间）齐全即履行"先收好、可追溯"。
- 明示预留：未来"汇总/检索/看板"立项时，本表是唯一事实源——避免届时做数据考古。
- 状态机定版终态（K3 观察项，PM 拍板 cmsg_01m6d86be2y0r5fe370f4d7n1y）：`stale` 是资产行"源内容已变"的终态标记，撤回不追溯改写；`withdrawn` 仅作用于撤回时仍有效（collected）的行。状态机不加边，未来裁决消费时再议。

---

## 6. P0 schema 承接复核（PM 要求的"第一时间播报"结论）

**好消息：核心骨架是当年按 P1 预留的，主链路零重建。**
- ctx_tasks 的 scope CHECK 已含 'team'（值域可用，无需改约束）+ 本方案加 team_id/source_task_id 均为 ADD COLUMN（additive ✓）。
- 快照 PUT/幂等/409 协议原样复用，多编辑者只是调用方变化。
- egress/审计双平面、软删回收站、停用级联全部继承。

**三项需注意，其中一项真缺口：**
- **缺口 A（真缺口，需一次受控重建）**：ctx_assets 的 `owner_user_id NOT NULL REFERENCES users` + `UNIQUE(owner_user_id, kind)` 使"团队拥有的词表"不可表达（团队不是 user；同一人建多团队也会撞 UNIQUE）。**不在旧表上打补丁**，0002 内做 expand-contract 重建（新表 + 数据搬迁 + 改名，单事务、失败自动回滚——DevOps 升级脚本已具备"备份前置+迁移事务化+回滚"三件套，此为本能力的第一个正式用例）。需 @DevOps工程师 确认迁移窗口纪律不变 + @QA工程师 该重建必须进升级回归用例（迁移前后个人词表内容 diff=∅）。**→ 产品已批准 additive-only 首个例外（三条件齐：P0 预留路径内/升级三件套兜底/QA 迁移回归同步）；DevOps 正式承接待一句话，做完写入企业版运维基线。**
- **语义修正 B（文档层，无迁移）**：ctx_revisions.owner_user_id 实际一直是"写作者"而非"归属人"（P0 actor==owner 恒等所以无暴露）；P1 起拆 owner/actor 两列，旧行回填 owner=actor。幂等键 P0 是 (owner,mutation)——P1 团队副本上建议按 (actor,mutation) 判定（应用层实现，旧表约束保留不冲突，UUID 串号概率可忽略，如实记录该放宽）。
- **纪律提醒 C**：P0"additive-only"承诺因缺口 A 出现**首个例外**——例外本身在 P0 文档 §7 预留的"P1 需 expand-contract"路径上，非违约，但播报义务在此：升级脚本与回滚演练必须覆盖该迁移。

## 7. 裁决档案（原"待产品经理裁决"——随冻结令全部销项）

1. 原件发多团队 → **允许**。每团队独立副本、撤回互不影响（已落 §3.1）。
2. 词表合成 → **并集、冲突个人为准**；助手本地策略，不进契约承诺面（已落 §4）。
3. editor 删他人条目 → **能删 + 留痕可回滚**（已落 §3.3；"只能加不能删会让团队空间退化成只进不出的垃圾场"为产品定性）。
4. 归档团队 → **保留只读**、拒绝新写入（409 team_archived）、可撤回既有副本；整包删除留 P2（已落 §3.3 后段）。
5. 洞察板 HTML → **随副本进团队**，按项目方边界原话（"除音频、转写以外"）直接推导，无需再问（已落 §3.1 携带清单）。
6. U4 发言人别名 → **P1 首版团队面维持只读**，不做共享词表级；需求如有再入 backlog（冻结令拍板二，已落 §4）。
7. U5 "项目=跨会议归组" → **不进 P1 首版**，登记后续单列；T-002 债由决策聚合视图+团队词表偿还（冻结令拍板三）。

## 8. API 契约（v1.0 已冻结；UI 交互规格 v1.0 §9 字段依赖六条全部为本节核对项，其中①②为冻结必含项）

端点清单：
- `GET/POST /api/v1/teams`、`GET/PUT /api/v1/teams/{id}`、`PUT /api/v1/teams/{id}/archive`
- `POST /api/v1/teams/{id}/members` 请求体终态（D010 拍板，冻结后原地补注）：`{user_ids: [...], role?}` 批量形态；字段缺失/非数组/空数组=422 invalid_member_payload 明示（禁 404 静默）；个体不存在/已成员 → `failed:[{user_id, code}]` 承载，`added` 与 `failed` 同时返回 201；权限判定先行（非成员 404/viewer·editor 403 不因批量结果吞掉）。`GET/DELETE /api/v1/teams/{id}/members[/{user_id}]`、`PUT .../members/{user_id}/role` 不变
- `POST /api/v1/context/tasks/{id}/publish`、`DELETE /api/v1/context/teams/{id}/tasks/{task_id}`（撤回）
- 团队副本读写：`GET /api/v1/context/teams/{id}/tasks[/{task_id}]`、快照 PUT 复用 §1.4 协议（actor 从会话取，无新增头）
- `GET/PUT /api/v1/context/teams/{id}/assets/{kind}`（团队词表）
- `GET /api/v1/teams/{id}/audit`（变更记录，新增，核对项②）
- `GET /api/v1/users/search`（建团队选成员，新增，依赖 5）
- 空间上下文切换的列表面：`GET /api/v1/context/teams`（依赖 1/6）

字段依赖核对项（逐条对 UI 规格 v1.0 §9）：

1. **团队列表（依赖 1+6）**：`GET /api/v1/context/teams` 返回 `[{team_id, name, my_role(admin/editor/viewer), member_count, joined_at, status}]`——切换器直用；"我已被加入团队"轻提示按 joined_at 首访判断，不建未读态端点。归档团队按规格 §2 以只读标记随列表返回。
2. **发布/撤回粒度（依赖 2）**：发布与撤回端点支持**纪要粒度与单条决策粒度**两种 payload：`POST .../publish {team_id, mode: "task"|"decision", decision_id?}`；撤回同构。决策粒度发布即触发资产收集钩子（§5），并写 decision_publish 留痕。
3. **团队面 409 形态（必含项①，§6 并排对比硬依赖）**：团队副本快照 PUT 冲突响应升级为
   `409 {"error":"rev_conflict","current_rev":<int>,"latest":<当前最新 rev 的全文快照，形态同 GET 任务 DTO>}`——UI 单响应即得新旧两版全文做并排 diff。个人面 409 保持 P0 `{current_rev}` 形态不变；团队面新增 `latest` 字段为单向兼容扩展。
4. **变更记录端点（必含项②，裁决③回滚面硬依赖）**：`GET /api/v1/teams/{id}/audit?cursor&limit` 倒序分页、团队全员可读（viewer 只读无操作）。操作类型枚举终值（K1 拍板定名，= §1 team_edit_audit action CHECK 全集，十二值逐字）：`publish / edit / withdraw / decision_publish / decision_withdraw / decision_delete / decision_restore / member_add / member_role_change / member_remove / role_transfer / team_archive`。**"删除→恢复"闭环**：`decision_delete` 条目携带 `target_ref` + `pre_delete_rev`，前端"恢复"按钮据二者重推历史版本；`decision_restore` 本身亦为新留痕条目（规格 §7），恢复后内容=删除前 rev 内容。措辞归一：全文无"解散/dissolve"类值，归档语义统一 `team_archive`（UI §9.4"解散"字样以本节为准）；红线：枚举只到"操作记录"粒度，不含任何审批/待确认状态值（pending_approval 类出现即 FAIL）。§1 表为 0002 全新表，枚举定名无存量迁移问题。
5. **用户搜索（依赖 5）**：`GET /api/v1/users/search?q=`——任何 active 用户可调（建团队拉成员场景）；仅返回 `[{user_id, display_name}]`，不暴露手机号/邮箱等联系面（管理台列表端点权限面不同，不开放给普通成员复用）。
6.5 **发布态读面（v1.0 补漏注，PM 拍板二 cmsg_01m6d71fe7b1nbgkaq3eh1pmpf：属补漏不属改冻结）**：规格 §4.3"已公开到 N 个团队"角标与逐团队撤回的数据面定版为**内嵌原件 DTO**，不建独立端点——`GET /api/v1/context/tasks[/{id}]` 返回增加 `published_copies: [{team_id, team_name, copy_task_id, granularity(task|decision), current_rev, updated_at}]`（仅 active 副本；撤回即从该列表消失，撤回面=读面闭环）；角标"N 个团队"由 FE 按 distinct team_id 归并。

6.6 **排序锚定版（K4，PM 拍板 cmsg_01m6dbsdbtz5ehe9n6nc4z1ky0）**：团队内容面/决策聚合的排序锚=**公开时刻** `published_at`——语义为副本首次 publish 留痕时间（`MIN(team_edit_audit.ts) where action∈{publish,decision_publish}`，无留痕回退行 updated_at；ctx_tasks 无 created_at 列，属透出非新造、零迁移）。**编辑不顶序**：后续 edit/republish 不改 published_at，变更可见性由变更记录页承担，两页各司其职（§7 设计本意）。字段统一出现在三处 DTO：published_copies 行、`GET /context/teams/{id}/tasks` 列表行、团队副本详情。

7. **B5 第五锁定文案基准（冻结令拍板一，逐字）**：
   > 公开到团队的内容里不会包含录音音频和逐字转写，它们永远只保存在您的设备上。

   挂点仅公开确认弹窗一处（FE lockedCopy.ts 单源扩行，禁手抄；防锁定面扩张纪律沿用）。后端与该文辞互为表里：§3.1 复制器白名单**结构性排除** formal 与音频引用 + blob schema 禁字段 422 兜底，即此承诺的可证伪实现面——QA 后端断言走白名单用例，UI 断言走逐字（六表面之一，与 P0 三行卡同级）。变更记录/团队首页同义表述用普通文案，不入 B5 逐字范围。

错误码延续：成员门槛不足=403（角色是明示语义非资源隐藏）；非成员访问团队资源=404；归档团队写入=409 team_archived；决策资产层无公开端点（404 by design，QA 断言点）。

## 9. 工作量粗估（P1-IMP 批次细拆见项目管理员台账登记）
teams/成员/ACL 域：M；副本发布/编辑/撤回链（含复制器白名单+diff UI 契约）：L；团队词表+ctx_assets 重建：M；决策资产收集钩子：S；审计留痕（含 §8 必含项②双字段）：S。合计后端 ≈ 4-5 周单人（与 P1"硬骨头"预判一致），副本编辑的前端 diff 体验为最大不确定项。
