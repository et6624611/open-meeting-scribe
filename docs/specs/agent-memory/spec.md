# Agent 长期记忆与跨会话检索（v2 设计稿）

- 状态：设计稿，待评审
- 版本：v2.1（2026-11-27，UI 章节对齐原型 v3）
- 关联：`docs/specs/context-asset-management/spec.md`（R2/R3 检索与向量索引）
- 关联：`docs/adr/0017-agent角色系统从硬编码提示词到md工作区.md`、`docs/adr/0019-智能体模式本地CLI引擎与MCP反向桥.md`
- 触发问题：角色 Agent 无写入式记忆，跨会话信息只能靠每轮重建的会议上下文；长会话窗口 20 条即截断，早期结论丢失。

## 1. 背景与现状

当前系统具备四层"上下文"，但都不是记忆：

| 层 | 实现 | 持久 | 可写 | 可检索 |
|---|---|---|---|---|
| 会话内短期 | 前端 `oms_ai_chat`，按 taskId 分桶，每会话保留 20 条 | 浏览器本地 | 仅对话 | 否 |
| 会议/项目事实 | 每轮由 `chat_shared._build_chat_context_blocks` 重建 | 源数据持久 | 否 | 关键词检索会议 |
| 角色定义 | `data/agent/_roles/<role>/{AGENT.md,insights.md}` | 文件持久 | 用户手动 | 否 |
| 智能体会话延续 | CLI `--session-id/-r` + 工作区 `context/history.md` | 工作区 7 天 | CLI 自行 | 否 |

缺口四条：无写入通道、无记忆存储、无记忆检索、无淘汰机制。

## 2. 目标与非目标

### 2.1 目标

1. 提供可写入、可检索、可闭合、可删除的长期记忆层。
2. 记忆按 namespace 隔离，跨会话可检索，跨空间不串味。
3. 记忆条目必须可回溯到来源会议与锚点，无来源拒收。
4. 冲突用有效期闭合表达，不删除、不覆盖。
5. 记忆注入不污染实时事实；与当前会议冲突时当前会议优先。
6. 角色 `.md` 保持静态只读，记忆不写回角色文件。
7. 用户可查看、编辑、闭合、删除、导出全部记忆。

### 2.2 非目标

- 不引入图数据库；双时间轴用 JSON 字段模拟。
- M0–M2 不引入向量库；M3 复用 `core/embedding_provider.py`，不新增依赖。
- 不改逐字稿、纪要、决策现有落盘链路。
- 不做模型参数级记忆（微调）。
- 不把记忆写入角色 `.md`。

## 3. 术语与分层

### 3.1 两条通道

| 通道 | 内容 | 进入上下文方式 | 预算 |
|---|---|---|---|
| `core` | L3 画像 + 高重要度 L2 事实 | 直接拼进 prompt，不检索 | 30 条 / 800 字 |
| `archival` | 其余 L1/L2 条目 | 按需检索，top_k 8 | 1200 字 |

`core` 超预算的条目降级到 `archival`，不淘汰。

### 3.2 三层内容

| 层 | 内容 | namespace | 写入时机 | 生命周期 |
|---|---|---|---|---|
| L1 情节 | 会议内明确事实、用户纠正、临时约定 | `task:<id>` | 显式 `remember` | 随 task 归档 |
| L2 语义 | 跨会议稳定的项目背景、人物角色、长期约束 | `space:<id>` / `global` | 巩固进程 + 确认 | 衰减、闭合 |
| L3 画像 | 表达偏好、格式要求、工作习惯 | `role:<name>` / `global` | 用户手动 + 显式指令 | 仅手动删除 |

### 3.3 有效边与闭合

- `valid_to = null` 为开放边，默认参与检索。
- `valid_to` 非空为已闭合，保留可查，默认不注入。
- 闭合只改元数据字段，不改 `text`。

## 4. 数据模型

### 4.1 条目结构

```json
{
  "id": "mem_<uuid>",
  "namespace": "space:proj-a | role:pm | global | task:<task_id>",
  "kind": "preference | fact | decision | correction | habit | glossary",
  "subject": "项目A",
  "relation": "负责人",
  "object": "张三",
  "text": "项目A 负责人为张三，2026-05 起由李四接任",
  "tags": ["组织"],

  "valid_from": "2025-03-01",
  "valid_to": "2026-05-14",
  "time_confidence": "high | low",
  "recorded_at": "2026-05-14T10:22:00+08:00",

  "source": {
    "task_id": "913942e9",
    "quote": "由李四负责",
    "anchor": {"dialogue_index": 12, "sentence_index": 3}
  },
  "status": "proposed | active | archived | deleted",
  "invalidated_by": "mem_8f3a",
  "importance": 0.6,
  "confidence": 0.8,
  "last_used_at": null,
  "use_count": 0,
  "embedding_ref": null
}
```

`status` 与 `valid_to` 正交：删除是另一回事，闭合不是删除。

### 4.2 存储布局

```
data/memory/
  index.json                    # 轻量索引，检索先读
  global/profile.json           # L3 全局
  global/semantic.json          # L2 全局
  spaces/<space_id>/semantic.json
  roles/<role_slug>/profile.json
  episodic/<yyyy-mm>.jsonl      # L1 追加写，按月分片
  audit.jsonl                   # add/close/reopen/delete 审计
```

写入统一走 `core/agent_memory/store.py`，持锁 + `fs_atomic.atomic_write_text`，禁止绕过。

### 4.3 namespace 规则

- 检索链固定为 `task → space → role → global`，权重 1.0 / 0.8 / 0.7 / 0.5。
- 单一 task 只会命中自身、所属 space、当前 role 与 global，不会跨 space。
- namespace 是强制前缀，不接受自由字符串。

## 5. 写入

### 5.1 三条通道

| 通道 | 触发 | 权限 | 落盘状态 | 默认 |
|---|---|---|---|---|
| `remember` 工具 | 智能体模式显式调用 | `workspace_write` / `full_task` | `active` | 可用 |
| 巩固进程 | 会后异步 | 系统任务 | `proposed` | 关 |
| 用户手动 | 记忆面板 / REST | 用户 | `active` | 可用 |

前两条必须带 `source`。服务端补齐当前轮锚点，补不出返回 `error=no_source` 并拒收。

### 5.2 闭合算法

`store.upsert` 是唯一实现：

```
1. 候选 = 同 namespace 且同 subject 且同 relation 且 valid_to IS NULL
2. 无候选 → insert，valid_from = 事件时间或 recorded_at
3. 有候选 → LLM 判定关系：
   a. 等价且不冲突 → NOOP，提 importance
   b. 冲突且时间明确 → close(旧, valid_to=t_new, invalidated_by=新id)
                       + insert(新, valid_from=t_new)
   c. 冲突但时间不明 → close(旧, valid_to=recorded_at, time_confidence=low)
   d. 不冲突（并存）→ insert，不闭合
```

判定键是 `(namespace, subject, relation)`，不是 `subject`。A、B 两个项目各有负责人时不会互相闭合。

无 LLM 可用时降级为规则判定：文本 bigram Jaccard ≥ 0.85 且 `object` 不同 → 视为冲突，`time_confidence=low`。

### 5.3 去重

同 namespace + 同 kind 下，bigram Jaccard ≥ 0.85 或一方包含另一方 → 合并 tags、提 importance，不新增条目。

### 5.4 巩固进程

- 独立任务，读定稿纪要 + 决策 + 随记，产出 0–5 条 `proposed`。
- 主对话不等待。
- 校验：无 source 丢弃、超 200 字丢弃、重复合并。
- 开关 `feature_flags.agent_memory_consolidate` 默认关。

## 6. 检索

```python
search(query, namespace_chain, as_of=None, top_k=8, budget_chars=1200) -> list[MemoryItem]
```

- 默认条件：`status = active AND valid_to IS NULL`。
- 带 `as_of`：`valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`。
- 打分：

```
score = (0.45*kw + 0.35*cos + 0.10*importance + 0.10*recency) * scope_weight
recency = exp(-days_since_last_used / 90)
```

- M1 关键词层复用 `core/meeting_search._query_terms` 的分词与 IDF，不另写一套。
- M3 向量层复用 `core/embedding_provider_` 的 provider 抽象，与 context-asset-management R3 共用索引。
- 超预算按分数截断，返回结果不含被截断标记的条目。
- 每次命中更新 `last_used_at`、`use_count`。

## 7. 注入

在 `app/routers/chat_shared.py::_build_chat_context_blocks` 新增两块，位置在会议上下文之后、跨会议检索块之前。

```
## 长期记忆·核心（常驻）
- [偏好] 汇报统一三段式

## 长期记忆·检索（与当前弱相关）
- [事实] 项目A 负责人 2026-05 起为李四（来源：《周会》2026-05-14）
```

规则：

1. 记忆块不参与统计，不与 `verified_facts` 混。
2. 与当前会议冲突时，当前会议优先。记忆只做背景，不做事实源。
3. 已闭合条目除显式回溯外不注入。
4. 角色级 `core` 拼在 `_agent_system_prompt` 的角色文件之后；问答模式不注入。
5. 智能体模式导出 `context/memory.md`，MCP 增加 `search_memory` 读工具。
6. `feature_flags.agent_memory=false` 时两块均不出现。

## 8. 生命周期

| 动作 | 规则 |
|---|---|
| 降级 | `core` 超预算 → 转 `archival`，不淘汰 |
| 冷存 | 180 天未用且 `importance < 0.3` → `archived`，不注入，可检索 |
| 上限 | 每 namespace 500 条 open，超出按 (importance, recency) 归档 |
| 删除 | 用户操作才物理删除；软删 30 天后清理 |
| 撤销 | 闭合后 5 秒内可撤销，写 `audit.jsonl` |
| 清理 | 服务启动 + 每日一次，与 `sweep_expired_workspaces` 同款调度 |

## 9. 权限与隐私

- 记忆继承 space 可见性，`space:X` 只在 X 内可检索。
- 单机无 space 语境时视为 global。
- 只存短句 + 锚点，不存音频、不存逐字稿全文。
- 本地明文 JSON，与现有 `data/` 一致；提供导出与全量删除。
- 记忆文本随 LLM 请求出网，与现有上下文一致，不新增出网点。

## 10. 代码接入点

### 10.1 新增

| 文件 | 职责 |
|---|---|
| `core/agent_memory/schema.py` | 条目结构、校验、namespace 解析 |
| `core/agent_memory/store.py` | 唯一写入口、闭合算法、去重、审计 |
| `core/agent_memory/retrieve.py` | 作用域链、打分、预算截断 |
| `core/agent_memory/inject.py` | core/archival 块渲染 |
| `core/agent_memory/consolidate.py` | 会后提炼 |
| `app/routers/memory.py` | REST：stats/list/patch/close/delete/accept/reject |
| `frontend/src/api/memory.ts` | 前端接口层 |
| `frontend/src/stores/memoryStore.ts` | 列表、选中、乐观更新 |
| `frontend/src/views/MemoryView.vue` 及 `components/memory/*` | 记忆面板（见 §11） |

### 10.2 修改

| 文件 | 改动 |
|---|---|
| `core/agent_tools/catalog.py` | 新增 `remember` / `forget` / `search_memory` |
| `core/agent_tools/impl.py` | 读工具分发 `search_memory` |
| `app/routers/agent_tools.py` | `_dispatch_write` 增写工具分支，校验档位与 source |
| `app/routers/chat_shared.py` | 注入两块；角色提示拼 `core` |
| `core/cli_engine/context_export.py` | 导出 `context/memory.md`，`AGENTS.md` 加记忆约束段 |
| `core/settings_store.py` | `feature_flags.agent_memory`（默认开）、`agent_memory_consolidate`（默认关） |
| `app/server.py` | 注册巩固钩子与清理定时器 |
| `frontend/src/views/SettingsView.vue` | AI 分类新增「AI 记忆」概览分区 |

## 11. UI 原型

### 11.1 设置页概览（设置 → AI → AI 记忆）

只放概览与入口，不放条目正文。

```
AI 记忆
跨会话记住偏好与事实，本地存储，可随时清除
────────────────────────────
状态      开放 42 · 已闭合 17 · 待确认 3
存储      <数据目录>/memory/            [打开目录]
开关      记忆启用        ●开
开关      会后自动巩固    ○关（产出待确认条目）
操作      [管理记忆]
```

`GET /api/memory/stats` 提供轻量计数，不拉全量。清空入口不在设置页。

### 11.2 记忆面板（`/memory`）

独立路由，保留左侧 rail，内容区最大宽 1080，居中；`< 900px` 折叠单栏。

**顶部**：标题「AI 记忆」+ 统计「开放 42 · 已闭合 17 · 待确认 3」（数字可点，等同切 chip）+ 右侧「导出」。

**工具行**：搜索框（防抖 300ms，`/` 聚焦）；状态 chips 单选（开放 / 已闭合 / 待确认 / 已归档，默认开放，带计数）；「筛选」popover 收 namespace、kind、时间范围。

**左列表（250px）**：正文优先（两行截断），下一行是单行 meta：类型圆点 + 类型名 + namespace + 日期。类型名是可点标签，点击即按该类型筛选，与筛选 popover 共用同一状态。

状态编码只走一条通道——左侧 3px 竖条：

| 状态 | 左侧竖条 | 正文 |
|---|---|---|
| 默认 | 透明 | 正常色 |
| 选中 | 保持状态色 | 背景 `--accent-soft` + 1px 内描边 |
| 待确认 | `--warn` | 正常色 |
| 已闭合 | `--muted` 实线 | `--muted` |
| 已归档 | `--border-strong` 实线 | `--muted` |

选中不得占用左边框，否则会覆盖状态。闭合不用虚线、不用删除线，归档不用斜体——中文伪斜体发虚，虚线在 3px 宽度不可辨且已被空态占位占用。

超过 100 条启用虚拟滚动。

**右详情**：标题（正文全文）+ 状态标签（开放中 / 已闭合 / 待确认 / 已归档）+ 两组字段：

- 「出身」：类型、namespace、来源。
- 「生命周期」：有效期、使用情况。

底部操作按状态变化：

| 状态 | 操作 |
|---|---|
| 开放 | 编辑 / 闭合 / 删除 |
| 已闭合 | 编辑 / 重新打开 / 删除 |
| 待确认 | 采纳 / 忽略 |
| 新增中 | 保存 / 取消 |

- 来源可点：`《项目周会》2026-10-12 · 第 3 轮` → `/meeting/<id>?dialogue=3`；手动创建条目不显示轮次。
- 有效期显示「2026-10-12 起 · 未闭合」或「2025-03-01 → 2026-05-14（已闭合）」，闭合时追加「被《周会》2026-05-14 新记录替代」，可回跳新条目。
- 「+ 新增」在详情区打开行内表单：类型、作用域、正文（≤200 字，必填）。手动创建来源标记为「手动」，不可回溯会议。

**待确认流**：列表顶部横幅「3 条记忆待确认 [逐条处理] [全部忽略]」；逐条处理时详情底部换成「采纳 / 忽略」。

- 采纳后还原条目的原类型（`originalKind`），不得一律记为「事实」。
- 采纳后自动跳到下一条待确认；本批清空时提示「本批待确认处理完毕」。
- 「全部忽略」提供 5 秒撤销，与单条删除的确认口径对齐。

**交互与键盘**

| 操作 | 行为 |
|---|---|
| `/` | 聚焦搜索（输入框、文本框、下拉聚焦时不抢） |
| `↑` `↓` | 移动选中项，详情同步 |
| `Enter` | 在列表项上进入行内编辑 |
| `Delete` | 在列表项上触发删除确认 |
| `Esc` | 清空搜索 → 关闭新增表单 → 关闭筛选 → 取消编辑 |

批量多选（Cmd/Ctrl + 点击）暂不实现，列入待确认项。

编辑保存后检索索引与 core 缓存立即失效，下次对话生效，不实时重排列表。

**空态 / 加载 / 异常**

- 空态：图标 +「还没有记忆」+「在对话中说"记住…"，或会后自动提炼」。
- 搜索无结果：保留筛选条件，显示「清除条件」。
- 加载：列表 4 条骨架 + 详情骨架。
- 失败：单行错误 +「重试」，不清空已加载数据。

**危险操作**

- 单条删除：确认弹窗，显示正文前 40 字。
- 批量删除：确认弹窗 + 条数。
- 清空全部：不在本页，放设置页高级项，要求输入「清空」二字。
- 闭合不弹确认，toast 提供 5 秒撤销。

**i18n**

`memory.title`、`memory.stats`、`memory.search_ph`、`memory.filter`、`memory.status.{open,closed,proposed,archived}`、`memory.action.{edit,close,delete,export}`、`memory.source_goto`、`memory.empty.{title,desc}`、`memory.confirm.{delete,desc}`、`memory.toast.{closed,undone}`。

**接口**

| UI | 接口 |
|---|---|
| 统计条 | `GET /api/memory/stats` |
| 列表 | `GET /api/memory?status=&namespace=&kind=&q=&cursor=` |
| 详情 | 列表项携带全字段，不单独请求 |
| 新增 | `POST /api/memory` |
| 编辑 | `PATCH /api/memory/{id}` |
| 闭合 | `POST /api/memory/{id}/close` |
| 删除 | `DELETE /api/memory/{id}` |
| 待确认 | `POST /api/memory/{id}/accept` / `/reject` |

列表用 cursor 分页，不用 offset。

**约束**

1. 浮层一律走 `frontend/src/utils/popoverPosition.ts`，不手写定位。
2. 左边框只编码状态，选中用背景 + 内描边，两者不共用通道。
3. 色板全 token 化，禁止在组件规则里硬编码 `oklch()`。
4. 闭合与归档用实线 + 正文弱化，不用虚线、删除线、斜体。
5. 本页不做嵌套滚动。

**无障碍**

- 列表容器 `role="list"`，每项 `role="listitem"` + `tabindex="0"`。
- 类型筛选标签是独立 `<button>`，可单独聚焦并带 `aria-pressed`。
- 设置页开关用 `role="switch"` + `aria-checked`。
- 加载与错误态下统计显示 `—`，不展示上一次的旧计数。

## 12. 阶段

| 阶段 | 范围 | 出口 |
|---|---|---|
| M0 | store + 闭合算法 + 关键词检索 + core 注入 + `remember` | 能写、能查、能进上下文 |
| M1 | 手动面板 + REST + 去重 + 角色 core + 设置页概览 | 用户可见可管 |
| M2 | 巩固进程 + proposed 确认 + 衰减归档 + 审计 | 自动化闭环 |
| M3 | 向量召回，与 context-asset-management R3 共用 | 语义检索 |

M0 必须独立可用，不依赖 M2。

## 13. 验收

1. 无 `source` 的写入 100% 拒收。
2. 同一事实连续写 3 次，open 条目数仍为 1。
3. 不同 `subject` 同 `relation` 不互相闭合。
4. `as_of=2026-01` 能取回已闭合的历史值。
5. 越 namespace 检索返回空。
6. 1000 条量级纯本地检索 P95 < 50ms。
7. `agent_memory=false` 后两块记忆均不出现。
8. 记忆块不进入 `verified_facts`，与当前会议冲突时以会议为准。
9. 角色 `.md` 文件在任意写入后保持不变。
10. `test_core_layer_purity.py` 通过。

## 14. 风险

| 风险 | 对策 |
|---|---|
| 误闭合 | 三元组判定键 + 时间不明标 `low` |
| 记忆污染 | 强制 source；巩固产出 `proposed` |
| core 膨胀 | 800 字硬预算，超出降 `archival` |
| 上下文变慢 | `core` 不走向量；`archival` 有 top_k 与预算双限 |
| 与 R2/R3 重复 | 共用分词、IDF、embedding provider，记忆只加 namespace 层 |
| 记忆与决策双写 | 记忆只做背景事实，决策仍只落 `task.decisions` |

## 15. 待决项

1. 巩固进程默认值：建议默认关（`proposed` 待确认）。
2. M3 向量后端：建议复用 `core/embedding_provider.py`，不新增依赖。
3. 记忆是否随角色包导出：建议默认不含，需显式勾选。

## 附录 A：开源实现参考

| 框架 | 关键机制 | 本方案借鉴点 |
|---|---|---|
| Mem0 | LLM 抽取事实 + 向量/图存储；论文版 ADD/UPDATE/DELETE/NOOP，现行改为单遍只追加 | 抽取比对；后期只追加不覆盖 |
| Zep / Graphiti | 时序知识图谱，双时间轴（valid time + transaction time），旧边闭合不删除 | §3.3 有效期闭合、`as_of` 回溯 |
| Letta（原 MemGPT） | core memory blocks 常驻 + archival 向量库；sleep-time agent 后台巩固 | §3.1 core/archival 二分、§5.4 巩固进程 |
| LangMem | 语义/情节/程序三类记忆；热路径与后台两条写入路径；namespace 隔离 | 三类内容划分、namespace 链 |
| MemOS | MemCube 统一内容与元数据，支持组合、迁移、版本 | 元数据与来源字段设计 |

参考链接：

- Mem0 文档：https://docs.mem0.ai/core-concepts/how-it-works
- Mem0 论文：https://arxiv.org/pdf/2504.19413
- Zep 论文：https://arxiv.org/pdf/2501.13956
- Letta 记忆块：https://docs.letta.com/v1-sdk/memory/memory-blocks
- Letta sleep-time：https://www.letta.com/blog/sleep-time-compute/
- LangChain 长期记忆：https://docs.langchain.com/oss/python/langchain-long-term-memory
- MemOS 论文：https://arxiv.org/pdf/2507.03724v4
