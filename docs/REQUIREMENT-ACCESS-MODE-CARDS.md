---
title: 需求记录 — 接入方式三卡片（账户/服务/引擎/状态栏心智重构）
id: REQ-ACCESS-MODE-CARDS
version: 0.1.0
status: approved（D1–D4 与假设 A1–A3 已由项目方裁决，作为派工依据）
date: 2026-09-25
decided_by: 项目方（2026-09-25 裁决：D1 接受三卡片取代引擎/服务双分类；D2 登录态改变路由须显性告知；D3 声纹并入所属卡片不单独暴露；D4 保留专家模式给高级用户。假设确认：A1 direct+prefer_subscription 存量迁移归 hosted；A2 旧字段兼容窗口一个版本；A3 跳转参数统一命名 ?cat=access）
category: 体验重构 / 设置与状态信息架构
related:
  - docs/PRD-LOCAL-ENGINE.md（engine.mode 三态与 local_ready 双因子的原始定义）
  - docs/USAGE_METERING_DESIGN.md（prefer_subscription 配额消耗口径）
  - docs/GLOSSARY.md（需随本需求新增「接入方式」词条，消歧 服务/引擎）
  - docs/VUE_COMPONENT_MAP.md（SettingsView / EngineBadge / footer.status 组件映射）
  - docs/AUTH_DESIGN.md（登录态与体验额度）
owner: 项目管理员（定义）/ 待指派（工程实施）
---

# 需求记录：接入方式三卡片（REQ-ACCESS-MODE-CARDS）

## 1. Problem（要解决什么）

用户在组合「账户、服务、计算引擎、底部状态」四类配置时感到混乱。根因是**系统实现模型直接暴露给用户**，四个概念互相渗透且存在静默覆盖：

| 概念 | 用户视角的真实疑问 | 实际耦合点（代码证据） |
| --- | --- | --- |
| 账户 | 登不登录有什么区别？ | 登录态 + `prefer_subscription` 会隐性把 direct 强制切 cloud 代理消耗配额（`core/llm.py::_should_use_cloud`、`core/transcribe.py::_get_asr_mode`） |
| 服务 | 为什么要配 LLM + ASR + 声纹三套？ | 内部实现拆分；用户心智只有"转写"和"纪要"两个能力 |
| 计算引擎 | proxy/direct/local 和"服务"什么关系？ | `engine.mode==local` 优先级最高，直接覆盖 ASR/LLM 服务配置，先前配置静默失效（`app/settings_store.py`、`core/engine_host.py`） |
| 状态栏 | 那个三态标签是谁的状态？ | 由 4 个输入推导（`llm.base_url` + `api_key_set` + `userStore.isLoggedIn` + `engine.mode`）；与顶栏 EngineBadge 两个入口、两套跳转参数（`?tab=services` vs `?cat=engine`，`frontend/src/App.vue`、`EngineBadge.vue`） |

**一句话诊断**：用户面对"配置矩阵"，系统却没有告诉他唯一结论——"我现在能不能用、花谁的钱、数据去哪"。

## 2. 用户心智模型（设计依据）

用户的心智单位是"这次会议能不能变成纪要"，只关心三个维度：

1. **可行性**——现在能不能用（就绪 / 缺什么）；
2. **成本**——花自己的钱（自带 Key）、花平台的钱（订阅配额）、还是不花钱（本地）；
3. **数据去向**——录音上不上云（隐私）。

三个维度可被**同一个选择**（接入方式）同时表达，故合并 engine.mode 与服务配置为单一决策。

## 3. 方案（Scope）

新增用户侧统一字段 `access_mode ∈ {local, hosted, byok}` + `expert_mode`（布尔）。旧字段（engine.mode、asr.mode、prefer_subscription、provider/base_url/model、各 api_key）降级为底层实现细节，仅专家模式可见可编辑。

### R1 三张「接入方式」卡片

| 卡片 | 用户语言 | 内部映射 |
| --- | --- | --- |
| 离线模式（推荐入门） | 不联网、不花钱、数据不出本机 | access_mode=local → engine.mode=local |
| 托管模式 | 登录账号，用平台额度，即开即用 | hosted → proxy + 消耗订阅配额 |
| 自带 Key 模式 | 用自己的 API Key，不限时长 | byok → direct + 用户 Key |

- 选离线时，服务区块灰化并标注"由离线模式接管"（消除静默覆盖，实时联动禁用或显式提示）。
- 声纹服务配置并入所属卡片区块的折叠区（D3 裁决），不单独暴露。
- provider/base_url/model 等收进"高级设置"折叠区，仅 `expert_mode=true` 时展示（D4）。

### R2 状态栏只播"结论 + 原因 + 动作"

- 就绪态文案："离线就绪 / 托管就绪（剩余 n 次）/ 自带 Key 就绪"；未就绪 → 一句原因（如"还需登录"），点击跳唯一设置入口 `?cat=access`（A3）。
- EngineBadge 与 footer.status 两处入口统一跳转参数（A3），状态推导逻辑收敛到 `stores/engine.ts`。
- 模型组合串、API 延迟降级到 hover/详情，不再占主文案。

### R3 路由切换显性告知（D2）

- byok 用户开启 `prefer_subscription` 导致路由切到 cloud 消耗配额时，toast 一次性显性说明（说清"本次起走平台额度"）。
- 任何跨模式的隐式路由变化都必须可被前端感知（后端提供事件或查询接口）。

### R4 首次使用引导

未登录且未配置时，首页/设置首屏出三卡片引导；`expert_mode` 开关位于高级设置内，开启后旧版分类视图（账户/服务/引擎）完整可用。

## 4. 数据迁移规则（A1/A2 已确认）

| 存量组合 | 迁移为 | 说明 |
| --- | --- | --- |
| engine.mode=local | local | — |
| engine.mode=proxy | hosted | — |
| engine.mode=direct 且 prefer_subscription=false | byok | — |
| engine.mode=direct 且 prefer_subscription=true | **hosted** | A1 裁决：实际行为已走云代理计费，归类与用户感知的花费一致 |
| 未配置 | null（触发引导） | — |

- 兼容窗口一个版本（A2）：旧字段继续写入保持回退能力，窗口结束后 expert_mode 下只读写新字段。
- 若存量配置含自定义 base_url/model 覆盖或非默认 Key 组合，自动置 `expert_mode=true`，保证高级用户配置不被卡片化流程吞掉。

## 5. 任务拆解与派工建议

| # | 任务 | 关键改动点 | 依赖 | 估算 | 角色 |
| --- | --- | --- | --- | --- | --- |
| T1 | 数据层与迁移 | `app/settings_store.py` | — | M | 后端 |
| T2 | 后端行为收口 | `core/llm.py::_should_use_cloud`、`core/transcribe.py::_get_asr_mode`、路由变化可感知接口 | T1 | M | 后端 |
| T3 | 三卡片组件 | `frontend/src/views/SettingsView.vue`（新增 AccessModeCards）、`stores` 联动 | T1 | L | 前端 |
| T4 | 引导与专家模式开关 | SettingsView + `LoginModal.vue` 入口 | T3 | S | 前端 |
| T5 | 状态栏/EngineBadge 统一 | `frontend/src/App.vue` footer.status、`EngineBadge.vue`、`stores/engine.ts` 收敛、D2 toast | T2+T3 | M | 前端 |
| T6 | 回归验证 | 三模式全链路 + 迁移用例（发版门禁） | T1–T5 | M | QA |

**执行顺序**：T1 → (T2 ∥ T3) → T4 → T5 → T6；T6 迁移用例部分可在 T1–T3 完成后先行。

**派工拆分建议**：AM-B1（后端：T1+T2）、AM-F1（前端：T3+T4+T5）、AM-Q1（T6，随 B1/F1 验收触发）。
⚠️ 冲突提示：前端工程师当前有 REQ-PROGRESS-P0（in-progress）与 DC-DEC-F1（dispatched）在途且均动 Settings/导航相关代码，AM-F1 需在两者合入后 rebase，或由产品决定排队顺序。

## 6. 验收标准（AC，逐任务）

- **AC-T1**：① access_mode/expert_mode 读写接口可用；② §4 迁移映射表全部组合有单测且通过；③ 旧字段一个版本内保持读取兼容。
- **AC-T2**：① 路由判定唯一入口为 access_mode（grep 级验证：`_should_use_cloud`/`_get_asr_mode` 不再独立读 engine.mode+prefer_subscription 组合）；② hosted 消耗配额、byok 走自有 Key、local 不计量三条计费路径与 `core/metering.py` 口径一致；③ 跨模式路由变化可通过接口/事件被前端查询。
- **AC-T3**：① 三卡片单选即得可用状态；② 选离线时服务区块灰化并标注"由离线模式接管"；③ LLM/ASR/声纹配置仅在 expert_mode=true 的折叠区出现；④ 声纹出现在所属卡片折叠区内，主视图无独立"声纹服务"入口。
- **AC-T4**：① 未登录未配置用户首屏见三卡片引导；② expert_mode 开关在高级设置内，开启后旧分类视图完整可用。
- **AC-T5**：① 状态栏主文案仅"结论（+原因/剩余量）"，模型串与延迟移入 hover/详情；② EngineBadge 与 footer.status 点击跳同一 `?cat=access`；③ byok→cloud 配额路由切换时 toast 显性告知一次且仅一次。
- **AC-T6**：① 三种接入模式各跑通一次录音→转写→纪要全链路；② §4 全部存量组合升级迁移用例通过（**发版门禁**）；③ 离线模式不泄露云模型名（沿用现有约束）；④ 配额扣减数额与 toast/状态栏文案一致。

## 7. 风险登记

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 迁移错误改变计费归属 | 高：用户被意外扣配额或 Key 泄露给非预期通道 | T6 迁移用例作发版门禁；灰度期保留回滚字段 |
| 前端在途单冲突（P0/F1 同动导航） | 中：合并冲突与回归成本 | AM-F1 排队或约定 rebase 顺序，产品拍板 |
| 老用户找不到旧设置入口 | 低：投诉/流失 | expert_mode 自动开启规则 + 引导文案 |

## 8. 非目标（Out of Scope）

- 不改动的账户体系与登录方式；不新增计费规则；不做引擎/服务内部实现变更；v1 不做多 profile 切换。
