步# 会议上下文资产管理（R1：可信检索与统计）

- 状态：待实施
- 关联：`docs/specs/chat-scope-mode/spec.md`（R2，本 spec 在其范围内做升级，不改范围档位语义）
- 触发问题：AI 会话中「本月 / 10月 / 9月」三问给出 141 / 107 / 27 三套互相矛盾的场次统计，且「只读 4 场」无解释。

## 1. 背景与问题

用户提问「本月与星瀚项目相关有哪些关键决策？」时，回复称「共命中 141 场，精选前 4 场」；追问「10月呢」得「命中 107 场」；再追问「9月呢」得「共命中 141 场，其中 9 月相关会议共 27 场」。三个数字互斥，用户无法判断哪个可信。

根因三条，缺一不可：

1. **检索器没有时间维度。** `core/meeting_search.py` 仅做中文 bigram + 关键词打分，「本月」「10月」被当作普通词元参与匹配，既无相对时间解析，也无 `meeting_date` 过滤。
2. **「命中」的定义过宽。** `_score_task` 只要 `score > 0` 即计入命中。「项目 / 相关 / 关键 / 决策」等泛词几乎每场都出现，候选量被放大成全库规模。141 是候选量，不是相关量。
3. **统计由模型代劳。** 上下文块头是自然语言「共 N 场命中，展示前 4 场」，模型在复述时改写、外推、甚至凭空生成数字（「9月相关 27 场」在任何数据源中都不存在）。前端 trace 又直接把该计数显示为「检索命中 N 场」，为错误口径背书。

一句话：候选数、相关数、注入数三个概念被压缩成一个 `hits`，且这个数字由模型转述。

## 2. 目标与非目标

### 2.1 目标（R1）

1. 相对时间可被解析并真实参与过滤，未给时间范围时不得假定「本月」。
2. 用 IDF 抑制泛词，使「相关」不再等价于「出现任意一个词」。
3. 统计口径拆为 `candidates / matched / injected` 三个字段，前后端同源。
4. 检索遥测不进入模型自由生成：块头结构化，前端 trace 由后端字段渲染。
5. 检索上限从「固定 4 场」改为「预算内可变」，并在块中显式声明截断。
6. 明确「全部会议」的空间、权限、生命周期与内容就绪边界，任何计数和权重都不得泄露无权访问的数据。
7. 复用现有决策唯一事实源、状态字典与跨会议议题归并，区分当前结论、历史演变和已替代决策。
8. 为每条注入片段返回最小证据锚点，使纪要、决策和对话片段均可回溯来源。
9. 用 `status=disabled/ok/error` 区分未检索、检索完成和检索失败；失败不得伪装成零命中。
10. 对用户显式统计问题提供后端确定性聚合，产出可原值引用、不可外推的 `verified_facts`。
11. 建立金样本验收，除数量与耗时外，必须验证命中对象、排除对象、排序、权限和证据正确性。

### 2.2 非目标（R1 不做）

- 不引入向量库、embedding、语义检索。
- 不把决策迁出 `task.decisions`，不新建决策表，不改写现有议题归并算法；复杂决策中心查询留待 R2。
- 不实现通用 BI 或任意自然语言统计；R1 仅支持 §5.2 白名单聚合。
- 不重构全局上下文预算器与对话滚动摘要（R2/R3）；R1 预算仅约束跨会议检索块。
- 不改工作区落盘结构与 IDE 资产形态（R3）。
- 不做逐字稿原文窗口回捞和前端精确高亮（R3）；R1 只落地证据标识与定位参数。
- 不改录音、逐字稿、纪要生成链路。

## 3. 术语与分层

### 3.1 三个计数

| 字段 | 定义 | 来源 |
|---|---|---|
| `candidates` | 可检索集合中通过时间、项目、排除本场等结构化过滤的会议数 | 过滤后、打分前 |
| `matched` | `candidates` 中相关度 ≥ 阈值的会议数 | 打分后 |
| `injected` | 实际写入上下文的会议数，受显式 `limit` 与字符预算共同约束 | 截断后 |

旧字段 `hits` 保留为 `matched` 的别名，`shown` 保留为 `injected` 的别名，避免前端与历史消息立刻断裂。`candidates >= matched >= injected` 只在 `status="ok"` 的检索结果上成立；失败时三个新字段均为 `null`，不得以 0 代替。

### 3.2 资产分层（本 spec 只定义，不迁移）

| 层 | 内容 | 用途 |
|---|---|---|
| L0 | 逐字稿原文 | 事实源，按窗口回捞 |
| L1 | 纪要（`task_final_summary`） | 检索与回答主力 |
| L2 | 决策（`task.decisions`，现有唯一事实源） | 精确回答「谁定的、定没定、是否已替代」 |
| L3 | 索引（元数据 + 词项） | 过滤与召回入口 |

R1 沿用现有标题、L1、L2 与已持久化对话行的打分和摘录，不新增 L0 索引或窗口回捞。

### 3.3 检索遥测与用户事实

- `candidates / matched / injected / latency_ms` 是**检索遥测**，仅用于解释系统行为，不是用户问题的答案。
- `verified_facts` 是后端按明确统计意图计算的**用户事实**，与遥测分字段返回；模型只能原值引用，不得据此推算其他数字。
- 业务内容中原本存在的金额、日期、数量不受遥测禁述规则限制；禁止的是模型自行生成或改写未经后端核验的会议、决策统计。

## 4. 检索架构：渐进式分层

R1 落地访问控制、结构化过滤、关键词加权与确定性聚合；后两级为后续阶段方向，接口预留。

1. **访问与结构化过滤**（R1）：空间与权限、生命周期、内容就绪、时间范围、项目归属、排除本场。
2. **关键词 + IDF 加权**（R1）：中文 bigram，泛词降权，阈值判定。
3. **确定性聚合**（R1）：白名单统计意图直接由后端计算，不经过相关度打分与注入预算。
4. **语义检索**（R3）：仅对 L1/L2 建索引。
5. **原文回捞**（R1.1 已落地清单+详情两档，逐字稿窗口仍属 R3）：按 `task_id` + 证据锚点定位窗口。
   - 清单档：`GET search_meetings`（MCP 读工具）返回标题/日期/相关度/一句摘录/`task_id`，支持 `limit/offset` 分页；
   - 详情档：`GET get_meeting_detail`（MCP 读工具）按 `task_id` 返回纪要、决策、随记，可选附带转写句；
   - 两档均只读、不绑定当前会话会议，写操作仍锁当前会议。

选择理由：会议数据强结构化，先用时间与项目把候选压到十位数量级，再谈相关性排序，成本最低、可解释性最好。纯向量方案无法处理「本月」这类硬约束；纯关键词方案无法处理模糊指代。

## 5. 检索契约

### 5.1 可检索集合与新鲜度

新增模块内统一入口 `_eligible_tasks(...)`，检索、IDF 和聚合必须消费同一份结果：

- **空间与权限**：有空间语境时，「全部会议」仅指当前空间内、当前用户按现有空间角色规则可见的会议；不得隐式跨空间。单机无空间语境时指本地全部可访问会议。权限判定复用现有访问层，检索器不得另写角色规则或新增会议级授权。
- **生命周期**：已删除、回收站中的会议排除；已归档但仍可访问的会议保留只读检索。无权限会议不得进入 IDF 的 `N/df`、任何计数、证据或错误详情。
- **内容就绪**：纪要生成中只读取已持久化内容，不读取半截缓冲区；无纪要但有已持久化对话的会议沿用现有对话检索；标题、纪要、决策、对话均为空的会议排除。
- **排除本场**：`exclude_task_id` 只用于避免重复注入检索证据；用户统计当前范围时，本场会议若符合过滤条件必须计入 `verified_facts`。
- **新鲜度**：R1 每次请求直接读取当前 `tasks` 与决策状态，不缓存打分结果或 IDF；纪要、决策、归属、权限变更从下一次请求生效，不得返回变更前快照。

过滤顺序固定为：访问与生命周期、内容就绪 → 时间/项目/排除本场 → 打分。聚合复用访问、生命周期、内容就绪与时间/项目过滤，但不排除本场、不打分。

### 5.2 查询路由与确定性统计

仅在 `scope="all"` 下用规则识别 `query_kind="retrieval" | "aggregate" | "mixed"`，不调用 LLM；`scope="meeting"` 保持现状，不执行全库统计：

- 命中「几场 / 多少场 / 多少会议 / 多少条决策 / 多少待决策 / 多少已替代」等明确统计句式时，产生聚合意图。
- 「最近 N 场」「本月关键决策」是检索；只有明确询问数量时才聚合。同时要求数量与内容时为 `mixed`，两条路径分别执行。
- 无法确定统计对象或状态时不猜测，退回检索或由模型追问。

R1 白名单聚合：

| `kind` | 口径 |
|---|---|
| `meeting_count` | 可访问且符合时间/项目过滤的去重会议数 |
| `decision_count` | 可访问且符合时间/项目过滤的决策节点数；可选 `status` 过滤或 `group_by="status"` |

约束：

- 决策状态统一经 `core.decision_flow.status_of` 与状态字典解析；`decision_count` 统计节点，不等同于议题簇数。
- 聚合不经过 IDF、相关度阈值、`limit` 或注入预算；`matched=0` 不影响已核验的统计值。
- 聚合结果写入 `verified_facts[]`：`kind/value/unit/status/time_range/time_label/filters`，分组时使用 `groups[]`；`value` 与分组值均为后端整数，0 是有效结果。
- `verified_facts` 与检索遥测分字段返回。模型可原值引用其中的数字，不得据此求和、换算、外推或生成未返回的分组。
- 聚合失败时不得返回默认值 0；整体 `status="error"`，`verified_facts=[]`，前端显示「统计失败」。

### 5.3 时间解析

新增 `core/time_query.py`：

```python
def parse_time_range(query: str, now: date | None = None) -> dict:
    """返回 {kind, start, end, label}。

    kind: "range" | "recent_count" | "none"
    start/end: ISO 日期字符串，左闭右开
    label: 用于回显与块头，如 "2026-11"
    """
```

支持的表达（仅规则实现，不调用 LLM）：

| 表达 | 结果 |
|---|---|
| 本月 / 这个月 / 当月 | 当月 1 日 ~ 次月 1 日 |
| 上月 / 上个月 | 上月 1 日 ~ 当月 1 日 |
| N 月 / N 月份 | 当年 N 月；若晚于当前月，回落上一年 |
| 本季度 / 这季度 | 当季首日 ~ 次季首日 |
| 上季度 | 上季首日 ~ 当季首日 |
| 本周 / 这周 / 上周 | 周一 00:00 ~ 下周一 00:00 |
| 近 N 天 / 最近 N 天 | 今日减 N 天 ~ 明日 |
| 最近 N 次 / 最近 N 场 | `kind=recent_count, limit=N`，不做日期过滤 |
| `YYYY-MM` / `YYYY年M月` | 该自然月 |
| `YYYY-MM-DD` | 当日 |

约束：

- 解析不出返回 `kind="none"`，`start/end=None`，**不得**默认当月。
- 时间范围与会议日期比较使用 `meeting_date || created_at[:10]`；无日期的会议在 `kind="range"` 下排除，并计入 `undated_excluded`。
- 时间解析只作用于跨会议检索（`scope=all`），不改本场会议常驻注入。

### 5.4 项目过滤

- 读取 `projects.list_projects()` 名称；名称长度 ≥ 2 且完整出现在 query 中，视为项目过滤条件。
- 命中多个项目名时，取最长匹配，单值过滤。
- 会议 `project_id` 不匹配时排除；`project_id` 缺失的会议在项目过滤下排除。
- 未匹配到任何项目名时不加项目过滤（「星瀚」这类未建档名称由 IDF 处理，不硬编）。

### 5.5 决策状态与证据锚点

**决策口径：**

- 决策读取以 `task.decisions` 为唯一事实源，使用 `decision_flow.status_of`、`enrich_decision` 和现有状态字典，不得再用 `done` 布尔值替代全部状态。
- 每条决策证据携带 `status/status_name/status_closing/is_current`；有 `superseded_by` 时一并返回。
- 「当前 / 最新 / 最终怎么定」复用 `decision_topic.cluster_topics` 的主记录与演变链。归并前必须完成权限与结构化过滤；已替代节点只能作为历史证据，不得作为当前结论。没有有效当前结论时明确说明，不得以最新日期代替定案判断。
- 「演变 / 历史 / 之前怎么讨论」可返回历史节点，并显式标注其状态及与主记录的关系。
- R1 不修改归并阈值、主记录选择、状态写入与替代/撤销逻辑。

**最小证据契约：**

每条实际注入的标题、纪要、决策、对话片段必须对应一项 `evidence`：

```json
{
  "evidence_id": "t_1:decision:d_1",
  "task_id": "t_1",
  "asset_type": "decision",
  "asset_id": "d_1",
  "excerpt": "采用方案 B",
  "locator": { "decision_id": "d_1" },
  "status": "superseded",
  "is_current": false
}
```

- `asset_type`：`title | summary | decision | dialogue`；标题/纪要的 `asset_id` 分别为 `title/task_final_summary`，决策取节点 ID，对话取现有句子 ID。
- 对话无句子 ID 时，`asset_id="d<dialogue_index>:s<sentence_index>"`，`locator` 使用相同两个索引，有起止时间则附带；不得为 R1 迁移或改写逐字稿。
- `evidence_id` 由后端确定性生成；`excerpt` 只能来自已持久化原文的规范化与截断，不得由模型补写。
- `meetings[].evidence[]` 只包含实际注入片段，顺序与块内片段一致；未注入的 matched 会议不伪造证据。
- R1 前端保存并透传锚点即可；点击定位、原文窗口和精确高亮在 R3 接入。

### 5.6 打分与阈值

保留现有字段来源（标题、纪要、决策、对话），改权重算法：

```python
df(term) = 可检索集合中包含该词的会议数
idf(term) = max(0.15, log((N + 1) / (df + 1)))
```

- `N`：访问、生命周期和内容就绪过滤后的会议总数，在时间/项目过滤与排除本场前计算；无权访问的会议不得影响权重。
- 单场得分：`sum(idf(term) * min(tf, cap))`，`tf` 上限沿用现有规则（标题 2、纪要 2、决策 3、对话 2）。
- 标题包含完整 query：额外 `+3.0`。
- 标题命中任一词：额外 `+1.0`。
- **相关判定**：默认 `score >= 3.0` 才计入 `matched`。单个泛词即使按 IDF 下限在多字段命中，也不得独立达到阈值；阈值只能在金样本评审后调整常量，不得按单次查询动态变化。
- 相关性排序：`matched` 按 score 降序；同分按日期降序（新会优先），再按 `task_id` 保证稳定顺序。

对 141 场景的预期：`项目 / 相关 / 关键 / 决策` 的 df 接近 N，IDF 落入下限；只有「星瀚」等稀有词产生有效分。命中量应落到个位到十位，最终由金样本断言而非仅靠数量预期验收。

### 5.7 注入与预算

- `limit=None` 时仅按字符预算截断，`INJECT_MAX_CHARS = 6000`（可配置）；显式传入整数时同时受场次数上限与字符预算约束。
- 逐场累加完整块字符数，加入下一场会超预算即停；不得为塞入下一场而删除已声明的证据锚点。`injected` 为实际写入场次。
- 每场片段数沿用 4 段，单段 ≤ 160 字，纪要摘录 ≤ 300 字。
- `matched > injected` 时 `truncated=true`；先触达显式场次数则 `dropped_reason="limit"`，先触达字符预算则为 `"budget"`，无截断为 `"none"`。同时触达时优先 `"limit"`。
- 未展开命中必须留名：`dropped_total` 为未注入场次数，`dropped_meetings` 最多列 30 项，仅含 `task_id/title/date`，不含内容。该清单不占主证据的字符预算，用于让模型如实告知「另有 N 场」并提供下钻入口。

### 5.8 块格式

替换现有自然语言块头：

```
<retrieval scope="all" status="ok" query_kind="retrieval"
           time_range="2026-11-01..2026-12-01" time_label="2026-11"
           filters="project:星瀚" candidates="12" matched="5" injected="4"
           truncated="true" dropped_reason="budget">
检索问题：<query>
### 1. <title>（<date>，相关度 <score>）
- <snippet> [evidence:<evidence_id>]
- 决策项：<decision>（<status_name>，当前结论=<is_current>）[evidence:<evidence_id>]
- 纪要摘录：<summary> [evidence:<evidence_id>]
...
<dropped_meetings total="57" shown="30">
1. <title>（<date>，task_id=<task_id>）
...
</dropped_meetings>
</retrieval>
说明：以上为历史会议证据。检索遥测只读，禁止复述、改写或自行计算会议与决策统计；
引用时标注会议标题与日期，并保持决策的当前/历史/已替代状态；time_range="none" 表示用户未指定时间范围，
不得假定为「本月」；证据不足时直接回答「未找到」，不得按时间线推断。
dropped_meetings 只是未展开命中的标题清单，不含内容：需要细节时用检索工具按 task_id 取回；
工具不可用（问答模式）时如实说明「另有 N 场未展开」，不得据标题推断内容。
```

聚合或混合查询另附独立块：

```
<verified_facts>
[{"kind":"meeting_count","value":12,"unit":"meeting","status":"ok",
  "time_range":"2026-11-01..2026-12-01","time_label":"2026-11","filters":{}}]
</verified_facts>
说明：此块为后端已核验的用户事实，可原值引用；不得据此计算或推断其他统计。
```

`time_range="none"` 与 `time_label="未限定"` 必须显式出现。`matched=0` 时不生成检索证据块；失败时两类块均不生成，只返回结构化错误状态。

### 5.9 下钻工具契约（渐进式披露）

注入块只解决「一次能看多少」，取全与取深必须由模型按需调用，故新增两个只读 MCP 工具（`needs_task=false`，不绑定当前会话）：

**`search_meetings(query, limit=20, offset=0)`**

```json
{
  "query": "11月 会计事件库",
  "total": 61, "offset": 0, "limit": 20, "returned": 20,
  "has_more": true, "time_label": "2026-11",
  "items": [{"task_id": "t_1", "title": "…", "date": "2026-11-17", "score": 12.4, "snippet": "…"}],
  "hint": "命中超过 60 场时的收窄建议（可选）"
}
```

- 与注入块共用 `_eligible_tasks / _filter_candidates / _search_prepared`，不得另立检索口径或阈值。
- `limit` 上限 50；`offset` 越界返回空页且 `has_more=false`。
- 每场只返回 1 条最高优先摘录（`compact` 渲染），不返回 `evidence` 数组与完整纪要——详情靠下一档。
- `total > 60` 时附 `hint`，引导收窄时间/项目，不鼓励逐页翻全库。

**`get_meeting_detail(task_id, transcript_limit=0)`**

- 返回 `title/date/project_id/summary/decisions[]/notes[]`，单段正文上限 3000 字并带 `*_truncated` 标记；`transcript_limit` 上限 50 句。
- `task_id` 不存在返回 `error=task_not_found`；已删除/回收站返回 `error=task_deleted`，不得泄露内容。
- 只读：任何写操作仍走绑定当前会议写工具，本工具不提供写入通道。


## 6. 统计与回显契约

原则：**检索遥测与用户事实分流；两者都只能由后端计算。**

- 后端 `retrieval` 是检索遥测唯一事实源，`verified_facts` 是用户统计答案唯一事实源，二者不得互相推导。
- 前端 trace 只渲染 `status / query_kind / matched / injected / time_label / latency`，不渲染 `candidates`（避免噪音）。
- `status="error"` 时只显示「检索失败」或「统计失败」，不得显示「相关 0 场」「0 条决策」；错误详情不暴露无权访问的会议信息。
- 模型不得复述检索遥测，但可原值引用 `verified_facts`；业务材料中的金额、日期和既有数量不受此限制。
- 历史消息无新字段时，前端按旧 `hits/shown` 降级显示，不伪造时间、证据或统计事实。旧响应无 `status` 时仅按 `searched` 映射为 `ok/disabled`，不得反向捏造错误。

前端文案调整为：

```
提问范围：全部会议 · 2026-11 · 相关 5 场 · 注入 4 场 · 12ms
提问范围：全部会议 · 相关 0 场 · 未注入 · 9ms
提问范围：全部会议 · 2026-11 · 已统计 · 10ms
提问范围：全部会议 · 检索失败 · 请稍后重试
提问范围：全部会议 · 统计失败 · 请稍后重试
提问范围：本场会议 · 未检索 · 8ms
```

## 7. 数据契约

### 7.1 后端

```python
build_scope_context(
    scope: str | None,
    query: str,
    *,
    exclude_task_id: str | None = None,
    limit: int | None = None,          # None → 仅按字符预算
    now: date | None = None,           # 测试注入
    access_context: dict | None = None, # 路由注入的已认证身份与当前空间
) -> tuple[str, dict]
```

`access_context=None` 只允许既有单机本地路径；具备空间/账号体系的路由必须显式传入。客户端不得通过 query 文本指定或扩大访问范围。

`retrieval` 结构：

```json
{
  "scope": "all",
  "status": "ok",
  "query_kind": "mixed",
  "searched": true,
  "time_range": "2026-11-01..2026-12-01",
  "time_label": "2026-11",
  "filters": { "project": "星瀚" },
  "candidates": 12,
  "matched": 5,
  "injected": 4,
  "truncated": true,
  "dropped_reason": "budget",
  "undated_excluded": 0,
  "hits": 5,
  "shown": 4,
  "meetings": [
    {
      "task_id": "t_1",
      "title": "需求评审",
      "date": "2026-11-02",
      "score": 7.4,
      "evidence": [
        {
          "evidence_id": "t_1:decision:d_1",
          "task_id": "t_1",
          "asset_type": "decision",
          "asset_id": "d_1",
          "excerpt": "采用方案 B",
          "locator": { "decision_id": "d_1" },
          "status": "done",
          "status_name": "已存档",
          "status_closing": true,
          "is_current": true
        }
      ]
    }
  ],
  "verified_facts": [
    {
      "kind": "meeting_count",
      "value": 12,
      "unit": "meeting",
      "status": "ok",
      "time_range": "2026-11-01..2026-12-01",
      "time_label": "2026-11",
      "filters": { "project": "星瀚" }
    }
  ],
  "latency_ms": 12
}
```

状态契约：

- `scope=meeting`：`status="disabled"`、`query_kind="retrieval"`、`searched=false`，三计数为 0，`time_range="none"`、`time_label="未限定"`，`verified_facts=[]`。
- `scope=all` 检索成功：`status="ok"`、`searched=true`；纯聚合成功时 `status="ok"`、`searched=false`，三计数为 0。
- 任一实际执行路径失败：`status="error"`、`error_kind="access" | "retrieval" | "aggregation"`，三新计数为 `null`，`meetings=[]`、`verified_facts=[]`。兼容字段 `hits/shown` 只能置 0，新前端在 error 下不得展示它们。
- `scope=all` 的统计聚合包含符合条件的本场会议；检索仍排除本场，避免重复注入。

### 7.2 前端

`frontend/src/api/chat.ts` 的 `RetrievalInfo` 增可选字段：

```ts
export type RetrievalStatus = 'disabled' | 'ok' | 'error'
export type RetrievalQueryKind = 'retrieval' | 'aggregate' | 'mixed'

export interface EvidenceInfo {
  evidence_id: string
  task_id: string
  asset_type: 'title' | 'summary' | 'decision' | 'dialogue'
  asset_id: string
  excerpt: string
  locator: Record<string, string | number>
  status?: string
  status_name?: string
  status_closing?: boolean
  is_current?: boolean
  superseded_by?: Record<string, string>
}

export interface VerifiedFact {
  kind: 'meeting_count' | 'decision_count'
  value: number
  unit: 'meeting' | 'decision'
  status: 'ok'
  time_range: string
  time_label: string
  filters: Record<string, string>
  groups?: Array<{ status: string; status_name: string; value: number }>
}

export interface RetrievalInfo {
  scope: ChatScope
  status?: RetrievalStatus
  query_kind?: RetrievalQueryKind
  searched: boolean
  error_kind?: 'access' | 'retrieval' | 'aggregation'
  hits: number                    // 兼容：= matched；error 下不展示
  shown?: number                  // 兼容：= injected；error 下不展示
  candidates?: number | null
  matched?: number | null
  injected?: number | null
  time_range?: string
  time_label?: string
  filters?: Record<string, string>
  truncated?: boolean
  dropped_reason?: 'none' | 'limit' | 'budget'
  meetings: Array<{
    task_id: string
    title: string
    date: string
    score: number
    evidence?: EvidenceInfo[]
  }>
  verified_facts?: VerifiedFact[]
  latency_ms: number
}
```

## 8. 系统提示变更

`core/prompts.py` 的会话系统提示在现有「引用纪律」下追加五条硬规则：

1. `<retrieval>` 中的 `candidates/matched/injected` 等遥测字段只读，不得在回答里复述、换算或重述。
2. 只有 `<verified_facts>` 中的后端统计值可以原值引用；不得据此推算未返回的总数、分组或比例。
3. `time_range="none"` 时不得假定时间范围；用户未说时间就不提时间。
4. 检索证据不足时回答「未找到相关会议」，不得按时间线推断；`status="error"` 时说明检索或统计失败，不得改述为「没有数据」。
5. 引用决策必须保留当前、历史、闭档、已替代状态；已替代证据不得表述为当前结论。

## 9. 兼容与降级

- `scope=meeting` 行为不变，不调用跨会议检索或全库聚合，返回 `status="disabled"`。
- 检索或聚合异常不阻断对话，但返回 `status="error"` 与 `error_kind`，不生成证据/事实块；新计数为 `null`，不得伪装零结果。
- 权限或空间上下文校验失败时必须关闭访问并返回错误，不得回退成全库读取；只有既有单机本地路径允许 `access_context=None`。
- 无法生成证据锚点的片段不得注入；不得先注入无来源文本再等待 R3 补齐。
- 旧前端收到新字段时忽略未知键；新前端收到旧响应时用 `hits/shown` 兜底，且不显示证据状态或统计事实。
- 时间解析失败：按无时间范围处理，并在响应与 trace 明确 `time_range="none"`、`time_label="未限定"`；此时聚合统计当前空间全部可访问且符合其他过滤条件的数据，不默认本月。
- 现有 `tests/test_meeting_search.py` 中依赖 `hits` 的断言改为 `matched`，保留 `hits` 等价断言；新增 error 下禁止展示兼容计数的断言。

## 10. 验收标准

建立版本化金样本 `tests/fixtures/meeting_search_gold.json`，每场样本含空间、权限、生命周期、日期、项目、纪要、决策状态与对话；每问声明 `must_include / must_exclude / expected_top / expected_facts`，不得只断言数量。

| 编号 | 标准 | 验证方式 |
|---|---|---|
| AC-1 | 200 场金样本中，「本月与星瀚项目相关有哪些关键决策」返回当月范围，`candidates ≤ 30`、`matched ≤ 10`；全部 `must_include` 命中，所有 `must_exclude` 均不出现 | 单测 + 手工 |
| AC-2 | 同一会话追问「10月呢」「9月呢」，各自 `time_range` 互不相同；库中无 9 月数据时 `matched=0` 且回答明确「未找到」 | 手工冒烟 |
| AC-3 | 回答不出现后端未提供的会议/决策统计；`verified_facts` 只能原值出现，业务材料原有数字不受误伤 | 单测 + 人工 |
| AC-4 | 无时间词的查询 `time_range="none"`、`time_label="未限定"`，回答不出现「本月」 | 单测断言响应 + 人工 |
| AC-5 | `status="ok"` 时 `candidates ≥ matched ≥ injected`；`status="error"` 时三新计数均为 `null` | 单测 |
| AC-6 | 前端 trace 与后端 `matched/injected/status` 一致；未检索、零结果、检索失败、统计失败四种状态文案互不混淆 | 联调 |
| AC-7 | 本机 500 场以内检索耗时 ≤ 50ms，测试以断言判定并记录实测值，不仅打印 | 性能单测 |
| AC-8 | 跨空间同名会议不越权；已删除会议排除、可见归档可查；纪要/决策/归属/权限修改后下一请求生效，无权数据不影响 IDF 与任何计数 | 单测 |
| AC-9 | 「当前怎么定」只给有效主记录；已替代节点仅出现在历史证据；历史追问能返回带状态的演变链 | 单测 + 手工 |
| AC-10 | 每个注入片段均能在 `meetings[].evidence` 找到唯一锚点，类型、来源 ID、定位参数和摘录一致；无锚点片段为 0 | 单测 |
| AC-11 | 会议数、决策状态统计与金样本精确相等；聚合包含符合条件的本场会议，不受 IDF、`matched=0`、`limit=1` 和注入预算影响；失败不返回 0 | 单测 |
| AC-12 | `<20` 场小样本与 200 场样本均满足 `expected_top` 和排除项；单个泛词不能独立成为 matched，空查询与歧义统计不猜测 | 单测 |

## 11. 分阶段计划

- **R1（本 spec）**：访问与就绪边界、时间解析、IDF、三计数、决策状态、证据锚点、结构化块、确定性统计、错误状态、金样本与 trace。
- **R2**：复杂决策中心查询与议题筛选；全局上下文 token 预算器、跨来源去重与对话滚动摘要。
- **R3**：L1/L2 向量索引；按证据锚点进行原文窗口回捞；前端点击定位与精确高亮；工作区改为导航层。

R2/R3 另立 spec，不在本次实施范围。

## 12. 任务清单

### T1 可检索集合与状态边界

- [ ] `core/meeting_search.py` 新增 `_eligible_tasks(...)`，复用现有空间访问判定，落实 §5.1 的权限、生命周期、内容就绪和新鲜度规则。
- [ ] `build_scope_context` 增 `access_context`，路由注入已认证身份与当前空间；非单机路径缺失或校验失败必须 fail closed。
- [ ] 增加 `status/error_kind/query_kind`；区分 disabled、ok、error，error 下新计数为 `null`。
- [ ] 新增跨空间、删除、归档、生成中、空内容、编辑后下一请求生效测试。
- 验收：无权数据不出现在 IDF、计数、块、证据和错误详情中；四种状态语义符合 §7.1。

### T2 时间解析

- [ ] 新建 `core/time_query.py`：`parse_time_range(query, now=None) -> {kind, start, end, label}`。
- [ ] 覆盖 §5.3 表格全部表达；解析失败返回 `kind="none"`，禁止默认当月。
- [ ] 新建 `tests/test_time_query.py`：本月 / 上月 / N 月跨年回落 / 季度 / 近 N 天 / 最近 N 场 / 无时间词 / 歧义文本。
- 验收：`pytest tests/test_time_query.py -q` 全绿；`now` 注入固定日期后结果可复现。

### T3 项目过滤与 IDF 打分

- [ ] `core/meeting_search.py` 新增 `_resolve_project_filter(query)`，按已建档项目名最长匹配。
- [ ] 新增 `_idf_weights(eligible_tasks, terms)`，统一为 `idf=max(0.15, log((N+1)/(df+1)))`；`N/df` 仅基于可检索集合。
- [ ] `_score_task` 改为 `sum(idf * min(tf, cap))`；标题全匹配 `+3.0`、标题词命中 `+1.0`，默认相关阈值 3.0。
- [ ] 时间/项目/排除本场过滤在打分前执行；无日期会议计入 `undated_excluded`；同分增加 `task_id` 稳定排序。
- [ ] `search_meetings` 签名增 `time_range`、`filters`、`access_context`，保持可单独调用。
- 验收：200 场与 `<20` 场金样本均满足 must_include、must_exclude、expected_top；数量目标仅作为补充。

### T4 决策状态与证据锚点

- [ ] 决策读取改用 `decision_flow.status_of/enrich_decision` 与状态字典，返回当前、闭档、已替代状态。
- [ ] 当前/最新/最终类问题复用 `decision_topic.cluster_topics`；权限和结构化过滤先于归并，已替代节点不得作为当前结论。
- [ ] 为实际注入的 title/summary/decision/dialogue 片段生成 §5.5 的 `evidence`，对话缺 ID 时使用现有索引定位。
- [ ] 无锚点片段丢弃；不得改写决策归并、状态写入或逐字稿存储。
- 验收：证据与片段一一对应；当前决策、历史演变、superseded 和越权归并测试全绿。

### T5 三计数、预算与结构化块

- [ ] `build_scope_context` 返回 `candidates/matched/injected/truncated/dropped_reason`，保留 `hits/shown` 兼容别名。
- [ ] `limit=None` 仅按 `INJECT_MAX_CHARS=6000` 截断；显式 limit 同时受数量与预算约束，原因按 §5.7 返回。
- [ ] `_format_block` 改为 §5.8 的 `<retrieval ...>` 与独立 `<verified_facts>` 结构，遥测和事实不得混写。
- [ ] `core/prompts.py` 挂 §8 五条硬规则，覆盖 verified_facts 引用与失败不得说成无数据。
- 验收：块可稳定解析，不变式、预算、limit、零结果和错误状态用例全绿。

### T6 确定性统计、API 与前端

- [ ] 新建 `core/meeting_facts.py` 与 `tests/test_meeting_facts.py`，仅实现 §5.2 的 retrieval/aggregate/mixed 路由及两类白名单聚合。
- [ ] 聚合复用可检索集合与时间/项目过滤，包含符合条件的本场会议，不经 IDF、limit 或注入预算；失败不返回默认 0。
- [ ] 聊天请求链路透传 `access_context`，响应增 `status/query_kind/error_kind/verified_facts` 和 `meetings[].evidence`。
- [ ] `frontend/src/api/chat.ts` 按 §7.2 更新类型；`AiMessageList.vue` 区分检索、统计、未检索与失败；旧消息仅用 `hits/shown` 降级。
- [ ] `ai-panel.json`（zh-CN / en）增加时间、注入、已统计、检索失败、统计失败词条。
- 验收：AC-3/6/11 通过；`cd frontend && npm run build` 通过；旧会话不伪造数字或证据。

### T7 金样本、回归与冒烟

- [ ] 新建 `tests/fixtures/meeting_search_gold.json`，覆盖权限、时间、项目、泛词、当前/已替代决策、统计、空库和小样本。
- [ ] `pytest tests/test_time_query.py tests/test_meeting_search.py tests/test_meeting_facts.py tests/test_chat.py -q`。
- [ ] 性能测试在本机 500 场样本上断言 ≤50ms 并记录实测值。
- [ ] 手工三问「本月 / 10月 / 9月」，追加「本月几场」「多少待决策」「当前怎么定」「历史怎么演变」及故障注入，核对 trace、verified_facts、证据与回答。
- [ ] `git diff --stat` 复核未触碰录音、逐字稿、纪要生成与决策写入逻辑。
- 验收：§10 十二条 AC 全部通过并记录实测值。

### T8 渐进式下钻：清单 + 详情工具（R1.1）

- [x] `core/meeting_search.py` 增 `compact` 渲染与 `search_meeting_list(query, limit, offset)`，复用既有过滤/阈值/排序。
- [x] 注入块增 `dropped_total / dropped_meetings`（≤30 项，仅标题/日期/id）与 `<dropped_meetings>` 段。
- [x] `core/agent_tools/catalog.py` 增只读工具 `search_meetings`、`get_meeting_detail`，`needs_task=false`；`impl.py` 实现分页与按 `task_id` 取详情。
- [x] `RETRIEVAL_DISCIPLINE` 增第 6 条：全量/汇总类提问必须翻页取全，不得用注入样本冒充全量。
- [x] `tests/test_meeting_search.py` 覆盖分页无重叠、compact 单条、时间过滤、越界页、收窄提示、dropped 清单；`tests/test_agent_tools.py` 覆盖无会话绑定检索、任意会议详情、缺失/已删除拒绝。
- 验收：问「把 11 月所有涉及 X 的决策列成表」时，模型按 `offset` 取到 `has_more=false` 后作答，条数与 `total` 一致；写操作仍锁当前会议。

## 13. 风险与回滚

- 风险：IDF 在会议数很少时（<20）权重不稳定，可能漏召回。缓解：统一下限 0.15、标题额外加分，并用小样本金样本验证，不仅检查大库噪声。
- 风险：`parse_time_range` 误判「10点」「三季度目标」等词。缓解：只匹配明确时间句式，命中多个时取最长；解析不确定则不设范围。
- 风险：项目名过滤误伤（项目名本身是常用词）。缓解：仅匹配已建档项目名，且要求长度 ≥ 2。
- 风险：统计意图误识别或聚合口径与检索不一致。缓解：仅识别明确句式，复用同一可检索集合与时间/项目过滤，金样本直接断言精确值。
- 风险：议题误归并导致当前结论错误。缓解：不改现有算法，权限过滤先于归并；保留主记录、历史和 superseded 状态，证据可回到原决策节点。
- 风险：旧对话没有稳定句子 ID，索引定位在结构变化后可能失效。缓解：R1 同时保留会议 ID 与摘录，结构变化时宁可丢弃片段；稳定原文锚点在 R3 处理。
- 风险：权限上下文缺省造成越权。缓解：非单机路径 fail closed，测试覆盖无权数据对 IDF 和统计的侧信道影响。
- 回滚：按 R1 变更集整体回滚；`retrieval` 新字段对旧前端保持可选，`hits/shown` 继续提供兼容值。不得只回滚权限过滤而保留跨空间聚合。
