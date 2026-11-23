# AI 会话：提问范围 + 问答/智能体明文模式（修订版）

- 状态：已实施（R2）
- 参考原型：`/Users/wangyongliang/Desktop/ai-panel-context-merged.html`（`.scope-btn` / `.mode-seg` / `.msg-who` / `.trace`）
- R2 变更：删除「本项目全部」；范围收敛为 `本场会议 | 全部会议`；检索器与范围块两条链路共用，避免双体系。

## 1. 背景与目标

当前 ComposerBar 的模式入口是纯图标 + 弹层，范围概念只存在于后端注入逻辑里，界面上不可见；消息流里也看不出这一问用的是什么范围、是否真的检索过。

目标：

1. 输入栏下方一眼看到「提问范围」和「问答 / 智能体」；
2. 每条用户消息回显「我 · 提问范围 X · 模式」；
3. 每条 AI 回复带一行 trace：范围 · 是否检索 · 命中场次 · 耗时。

范围必须真实生效：选「本场会议」不检索历史会议；选「全部会议」真的做关键词检索并注入命中片段。

## 2. 统一化原则（回应运维成本）

### 2.1 与 IDE 工作区的关系

不是两套内容，而是同一内容源的两种投影：

| 形态 | 内容来源 | 装配方式 |
|---|---|---|
| 问答上下文 | `tasks` + 项目文件夹 + 页面上下文 | 内存上下文块，注入系统提示词 |
| IDE / 智能体工作区 | 同上 | 落盘为 `AGENTS.md` / `transcript.md` / `summary.md` |
| 本次新增的「范围检索」 | 同上 | 唯一检索器产出唯一范围块，两条链路共用 |

本次不做：不把问答改成读写工作区，也不给智能体另写一套检索。**范围检索只实现一次**，问答追加到上下文块，智能体追加到工作区文本；两边看到的是同一段命中内容。

### 2.2 内容单元统一

范围只决定「按问题检索哪些会议」，不接管常驻注入：

- 常驻注入（会议转写/纪要/随记/决策、项目资料、页面上下文、@引用）每轮照旧，与范围无关。
- 范围只控制一件事：是否跨会议检索、检索多大范围。
- 因此不再需要「本项目全部」这种把项目资料和检索混在一起的档位；项目资料本来就一直在。

## 3. 范围定义

| 档位 | 含义 | 行为 |
|---|---|---|
| `meeting` 本场会议（默认） | 只用本场常驻注入内容 | 不跨会议检索，`searched=false` |
| `all` 全部会议 | 本场 + 全库历史会议 | 关键词检索最多 4 场，命中片段注入 |

正交关系：

- 范围 ↔ 会话档位 `auth_tier`：互不影响。
- 范围 ↔ 模式 `qa/agent`：互不影响，但两条链路消费同一份范围块。
- 范围 ↔ 常驻注入开关：互不影响，范围不是开关。

## 4. 交互设计

### 4.1 ComposerBar 控制行

从左到右：`范围触发器` → `问答 | 智能体` 分段 → `授权档位` → `模型` → 发送。

范围触发器：

- 搜索图标 + 当前范围文案 + chevron；`all` 时 `is-wide` 高亮（accent 边 + accent-soft 底）。
- 弹层（`usePopMenu`，`align: 'start'`，宽 288px）：
  - 头：`提问范围 · 检索去哪里找答案`；
  - 两行：标题 + 说明，选中行打勾；
  - 脚注：`检索召回用完即走，不占常驻注入预算。找「过往结论 / 谁定的」这类精确问题，决策中心 · 按议题会更准。`

模式控件：

- 明文分段「问答 | 智能体」，选中项反色填充。
- 移除旧模式图标触发器与弹层；`mode_agent_cost_hint` 挂到「智能体」按钮 `title`。

窄栏：

- 范围触发器只留图标；模式分段缩小内边距；不换行、不溢出。

### 4.2 消息回显

用户气泡上方：

```
我 · 提问范围 本场会议 · 问答
```

AI 正文下方、使用回显上方：

```
提问范围：全部会议 · 检索命中 3 场 · 1.2s
提问范围：本场会议 · 未检索 · 0.8s
提问范围：全部会议 · 检索未命中 · 0.9s
```

旧消息无 `scope/retrieval`：不显示 trace（不伪造历史事实）；用户侧回显按 `meeting` 兜底。

### 4.3 编辑态

ComposerBar 同时带范围与模式；范围回填 `msg.sendOptions.scope`，缺省 `meeting`；提交随 `editResend` 覆盖本轮。

## 5. 数据契约

### 5.1 前端类型（`frontend/src/api/chat.ts`）

```ts
export type ChatScope = 'meeting' | 'all'

export interface RetrievalInfo {
  scope: ChatScope
  searched: boolean
  /** 命中的会议数 */
  hits: number
  meetings: Array<{ task_id: string; title: string; date: string; score: number }>
  latency_ms: number
}
```

- `SendSnapshot` 增 `scope?: ChatScope`。
- `ChatMessage` 增 `scope?: ChatScope`、`retrieval?: RetrievalInfo`。
- `ChatOptions` 增 `scope?: ChatScope`。
- `StreamCallbacks.onDone` 参数增 `scope?: ChatScope; retrieval?: RetrievalInfo`。

### 5.2 请求

`/api/chat`、`/api/chat/stream` body 增 `{ "scope": "meeting | all" }`；缺省/非法值按 `meeting`。

### 5.3 响应 / done

```json
{
  "scope": "all",
  "retrieval": {
    "scope": "all",
    "searched": true,
    "hits": 7,
    "shown": 4,
    "meetings": [{ "task_id": "t_1", "title": "需求评审", "date": "2026-11-02", "score": 18 }],
    "latency_ms": 4
  }
}
```

`meeting` 固定 `searched=false, hits=0, meetings=[]`。

> R3：`hits` 改为总命中数，`shown` 为实际注入场次（上限 4）；命中块同时给出决策项与纪要摘录，
> 避免智能体读不到工作区外会议文件时只能按时间线推断。

## 6. 后端实现

### 6.1 新增 `core/meeting_search.py`

```python
SCOPES = ("meeting", "all")

def normalize_scope(value: str | None) -> str:
    """None/非法 → 'meeting'。"""

def build_scope_context(
    scope: str | None,
    query: str,
    *,
    exclude_task_id: str | None = None,
    limit: int = 4,
) -> tuple[str, dict]:
    """唯一入口：返回 (上下文块, retrieval)。

    meeting → ("", {scope:'meeting', searched:False, hits:0, meetings:[], latency_ms:0})
    all     → 关键词检索全库历史会议，命中块 + 统计
    """
```

内部 `search_meetings(...)` 保持私有或模块内可测：

分词：小写，抽中文连续串与英文单词；中文串生成 bigram；过滤停用词（的/了/是/在/和/与/我/你/他/这/那/什么/如何/怎么/为什么）。

打分：

- 标题 8/词；摘要、`user_summary`、决策 4/词；对话句 2/词（每场最多 5 句）。
- 标题包含完整 query 额外 +30。
- 单场最多 3 段 snippet（≤120 字，截断加 `…`）。
- 数据源 `core.task_store.tasks`；标题 `title||audio_name`；日期 `meeting_date || created_at[:10]`；摘要 `core.chat_context.task_final_summary`；对话 `dialogue[].sentences[].text`；排除 `exclude_task_id`；空文本会议跳过。

块格式：

```
## 跨会议检索命中（提问范围：全部会议，共 3 场命中）
检索问题：<query>
### 1. <title>（<date>，相关度 <score>）
- <snippet>
...
说明：以上为历史会议片段，引用时标注会议标题与日期，不得改写为当前会议事实。
```

检索异常在 `build_scope_context` 内吞掉并 warning，返回空块 + `searched=false`。

### 6.2 `app/routers/chat_shared.py`

- `ChatRequest` 增 `scope: Optional[str] = None`。
- `_build_chat_context_blocks` 返回值改为 `tuple[list[str], list[dict], dict]`；`tests/test_chat.py:698` 只取 `[0]`，兼容。
- 维度 3 保持现有项目资料注入（与范围无关，属常驻注入）。
- 新增维度 3.5：调用 `build_scope_context(data.scope, user_message, exclude_task_id=data.task_id)`；有块则 append；命中同时追加 `source_files`：`{"title": title, "path": f"meeting/{task_id}", "name": title}`。
- 返回检索得到的 `retrieval`。

项目资料与范围解耦：不再按 scope 跳过项目资料。这是本次与 R1 的关键差异。

### 6.3 `app/routers/chat_stream_routes.py`

- `/api/chat`（约 431 行）接收三元组，回传 `scope` + `retrieval`（约 474-495 行）。
- `/api/chat/stream`（约 537 行）接收三元组；内置 done 事件（约 617-641 行）回传两字段。
- 智能体路径统一：
  - `_build_chat_context_blocks` 已算出的范围块不再重算；把该块作为 `shared_context` 传入 `_agent_engine_events`。
  - `_agent_engine_events` 将 `shared_context` 拼进 `page_ctx` 后交给 `cli_context_export.export_context`（复用现有 `page_context` 参数，不新增第二套检索）。
  - 终帧 `terminal` 写 `scope` + `retrieval`（由端点传入，不重复检索）。
  - 回退内置沿用内置 retrieval。

## 7. 前端实现

### 7.1 `useAiChat.ts`

- `ChatScope = 'meeting' | 'all'`；`chatScope` ref，localStorage 键 `ai_chat_scope`，合法值校验，缺省 `meeting`。
- `setChatScope`；在 return 中导出。

### 7.2 `useAiChatStreamCore.ts`

- `SendOverride` 增 `scope?: ChatScope`；`Deps` 增 `chatScope`。
- `sendRaw`：`effectiveScope = override?.scope ?? chatScope.value`；`sendOptions.scope = effectiveScope`；请求透传。
- `onDone`：落 `msg.scope`、`msg.retrieval`。

### 7.3 `ComposerBar.vue`

- props 增 `chatScope`；emits 增 `update:chatScope`。
- 范围触发器 + 两行弹层；`onPickScope` 关闭并发事件。
- 模式改为 `.mode-seg` 明文分段；删除旧模式弹层与相关 ref。
- 样式：`.scope-trigger`（含 `.is-wide`）、`.mode-seg`；compact 降级。

### 7.4 透传链

`AiChatComposer.vue` → `AiChatPanel.vue` → `AIPanel.vue`：新增 `chatScope` prop 与 `update:chatScope` emit，绑定 `chat.chatScope / chat.setChatScope`；`editResend / editAndResend` override 增 `scope`。

### 7.5 `AiMessageList.vue`

- 用户气泡前 `.msg-who`：`t('ai-panel.scope_user_echo', { scope, mode })`；范围 `sendOptions?.scope ?? 'meeting'`。
- AI 回复：有 `msg.scope || msg.retrieval` 才渲染 `.ai-scope-trace`。
- 编辑态：`editScope` 回填与提交。
- 样式对齐现有 mono 11px / `--surface-2`。

## 8. i18n 词条（zh-CN / en 同步）

```
scope_label                 提问范围 / Search scope
scope_meeting               本场会议 / This meeting
scope_meeting_hint          只用本场转写、纪要与随记，不检索 / Current meeting only
scope_all                   全部会议 / All meetings
scope_all_hint              跨项目检索历史会议，较慢 / Search historical meetings across projects
scope_note                  检索召回用完即走，不占常驻注入预算 / Retrieval is on demand
scope_user_echo             我 · 提问范围 {scope} · {mode} / Me · Scope {scope} · {mode}
scope_trace                 提问范围：{scope} · {retrieval} · {latency} / Scope: {scope} · {retrieval} · {latency}
scope_trace_hit             检索命中 {count} 场 / {count} meetings matched
scope_trace_miss            检索未命中 / No match
scope_trace_off             未检索 / Not searched
```

删除 R1 的 `scope_project*` 与 `scope_trace_no_project`。

## 9. 边界与降级

- 旧会话/旧消息无 `scope`：不显示 AI trace；用户回显按 `meeting`。
- 检索异常：不阻断对话，`searched=false`。
- 智能体模式与问答模式使用同一份范围块；不出现两套检索口径。
- 项目资料始终按现状注入（常驻），不随范围变化；用户若只想看本场，可用范围避免跨会议召回，项目资料仍可见——这是「内容本身统一」的取舍，需在文案中说明。
- 检索上限 4 场、每场 3 段。
- 不改动录音、逐字稿、纪要生成链路。

## 10. 验证

后端：

```bash
pytest tests/test_meeting_search.py tests/test_chat.py -q
```

`tests/test_meeting_search.py` 覆盖：

1. `normalize_scope(None/'project'/'x') == 'meeting'`；
2. 标题命中排序高于对话命中；
3. `exclude_task_id` 生效；
4. `build_scope_context('meeting', ...)` 返回空块且 `searched=False`；
5. `build_scope_context('all', ...)` 命中时块含「提问范围」与来源说明。

前端：

```bash
cd frontend && npm run build
```

手动冒烟：

1. 两档范围切换、`all` 高亮正确；
2. 用户消息回显范围+模式；AI trace 与选择一致；
3. 本场会议档无跨会议检索块；全部会议档有多场命中；
4. 刷新、切会话后回显仍在；
5. 窄栏不换行、不溢出；
6. 编辑旧消息再发送，范围回填并可改；
7. 问答与智能体各发一轮 `all`，注入的命中内容一致（同一检索器）。

## 11. 风险与回滚

- 风险：两档范围表达力有限；用户若需要「只在本项目内检索」，先不做，避免与项目资料常驻注入混淆（R2 明确删除）。
- 风险：关键词检索召回率有限；用命中场次与来源列表明示边界。
- 回滚：前端移除控件恢复原图标入口；后端 scope 缺省 `meeting`，删除调用即回现状。
