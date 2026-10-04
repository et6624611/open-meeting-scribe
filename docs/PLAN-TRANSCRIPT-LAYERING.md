# PLAN-TRANSCRIPT-LAYERING：转写文本三层分层 实施方案

- 状态：待评审
- 日期：2026-09-30
- 原型：`~/Downloads/transcript-layering-prototype.html`（17 项浏览器走查通过，含 420px 窄屏）
- 关联：[text_correction.py](../core/text_correction.py)（回溯纠错）、[rewrite_snapshots.py](../core/rewrite_snapshots.py)（AI 写回快照）、[routing.py](../core/routing.py)（算力来源与自动改用闸门）

---

## 1. 目标与范围

转写文本分三层，各自独立：

| 层 | 手段 | 时机 | 存储 |
|---|---|---|---|
| 原文 | ASR 直出 + 热词后处理（现状不动） | 实时 / 批转写 | `task.dialogue[].sentences[].text`，永不改写 |
| 清理版 | 本地确定性规则（语气词 / 口吃重复 / 标点） | 段闭合即派生 | **不落盘**，读取边界派生 |
| 书面版 | AI 逐句改写 + 语气存疑标记 | **仅会后**，整场或选区 | 独立 sidecar，不写回 task |

**文本流向（评审裁决 2026-09-30：清理版进下游）：**

| 消费者 | 输入文本 | 边界 |
|---|---|---|
| WS 上屏 / 会后转写展示 | 原文 + clean_text 双字段，视图切换 | 读取边界派生 |
| 实时摘要 / 实时章节 | **清理版** | `_on_sentence_end` feed 前替换 |
| 实时翻译 | **清理版** | 同上，译文锚点不变 |
| 会后纪要 / 标题 / 章节（含补生成、手动重生成） | **清理版**（深拷贝喂入，task.dialogue 保持原文） | stage2 与路由层 |
| 导出 md/docx 附稿 | 原文 | 不改 |
| AI 对话上下文（realtime store） | 原文 | 不改 |

### 1.1 做

1. 清理层：纯函数规则引擎，实时 WS 与会后 API 两个读取边界派生；**同时作为摘要 / 章节 / 翻译三类下游消费者的输入文本**；默认开，更多菜单逃生开关。
2. 书面层：会后对已完成会议生成逐句书面版；逐段对照原文；弱化 / 反转语气的句子显式 `tone_flag`；用量留痕。
3. 选区书面化：划词工具条对选中句生成书面版。
4. 会后自动生成开关（默认关）。

### 1.2 不做（v1 红线）

- ❌ 不修改、不覆盖逐字稿原文；引用、时间戳、说话人对齐、追责始终锚定原文。
- ❌ AI 不做识别纠错（同音字 / 专名误识仍走热词映射 + 划词回溯修正）。
- ❌ 会中（recording）不提供 AI 书面化入口，不调用 LLM，不产生延迟与扣费。
- ❌ 不进设置页常驻；开关只在转写面板「更多」菜单（遵循功能开关惯例）。
- ❌ 书面版 v1 不允许单句采纳写回原文；清理版 / 书面版不进入导出 md/docx（导出附稿仍为原文）。
- ❌ 清理版不进入 AI 对话上下文（realtime store 仍缓存原文，证据口径一致）。

---

## 2. 数据契约

### 2.1 settings.json 新键（[settings_store.py](../app/settings_store.py)）

```json
{
  "transcript": {
    "cleanup": { "enabled": true },          // 逃生通道，默认 true
    "formal":  { "auto_generate": false }    // 会后自动书面化，默认 false
  }
}
```

- 新增 `get_transcript_config() -> dict`，模式对齐 `get_engine_config()`（纯读、默认值兜底、容忍坏值）。
- [settings.py](../app/routers/settings.py) `GET /api/settings` 响应增 `transcript` 块；`save_settings` 白名单增两键（仿 `feature_flags` 的先取后合，L283/L344）。
- 不新增设置页组件。

### 2.2 WS 消息扩展（[ws_transcript.py](../app/routers/ws_transcript.py)）

`sentence` 与 `history` 消息增两个**可选**字段（清理开关关时缺省，前端按缺省＝原文处理）：

```json
{
  "type": "sentence",
  "text": "嗯……那个方案得，得发出来",
  "clean_text": "方案得发出来",
  "clean_ops": [{"r": "filler", "n": 2}, {"r": "dup", "n": 1}],
  "begin_time": 0, "end_time": 0, "speaker_id": 0, "speaker_name": ""
}
```

- `partial` 不清理（临时文本不做任何加工）。
- 契约文档同步更新 `docs/API_CONTRACTS.md` 的 WS 小节。

### 2.3 会后任务读取富化（不入库）

[GET /api/tasks/{task_id}](../app/routers/tasks.py) 响应中，对 `dialogue[].sentences[]` 逐句附加 `clean_text` / `clean_ops`（开关关或缺省句不加 `clean_text` 键）。

**关键约束：响应级富化，先拷贝再附加，绝不写回内存 task 与磁盘。** 这样：

- 热词回溯修正（[text_correction.py](../core/text_correction.py)）改完原文后，清理版下次读取自动重算，无需进 `REWRITE_KEYS` 白名单；
- 零数据迁移，存量会议打开即有清理版。

响应信封增 `transcript_layers: {"cleanup": true}`，供前端判定分段控件可用性。

### 2.4 书面版 sidecar

新文件 `data/tasks/{task_id}.formal.json`（与 `.insights.json` / `.board.html` / `.rewrites.jsonl` 同目录同生命周期口径）：

```json
{
  "version": 1,
  "status": "running | done | error",
  "scope": "full | selection",
  "auto": false,
  "source_sig": { "count": 42, "hash": "sha1-of-raw-sentences" },
  "model": "qwen-plus",
  "source": "trial | byok | local_endpoint",
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
  "created_at": "", "finished_at": "",
  "error": "",
  "items": [
    {"sentence_id": 3, "begin_time": 184000, "text": "方案需在下周三之前发出。", "tone_flag": null},
    {"sentence_id": 7, "begin_time": 312000, "text": "此事原则上同意，先按此推进。", "tone_flag": "weakened"}
  ]
}
```

- 锚点 = `sentence_id`（批转写契约既有字段，[transcribe.py:208](../core/transcribe.py#L208)），`begin_time` 仅作校验。
- `source_sig` = 扁平句数 + 原文 sha1。重新转写 / 回溯修正后读取时比对：不一致 → API 返回 `status: "stale"`，前端要求重新生成，不展示错位书面版。
- 选区生成：items 按 `sentence_id` upsert；整场生成：整文件替换。
- 原子写（`core.fs_atomic.atomic_write_json`）。

---

## 3. 后端任务

### WP-1 清理层

**新建 `core/transcript_cleanup.py`**

```python
def clean_sentence(text: str) -> dict:
    """返回 {text, changed, ops}。纯函数、无 I/O、无随机、可离线、可复现。"""
```

v1 规则集（每条规则一个 id，删除即记账到 `ops`）：

1. `filler` 填充词：
   - 中文：嗯、呃、啊、呀、嘛、哦、诶、哎、唉、那个、这个、就是、就是说、怎么说呢、你懂吧、对吧（仅作话语标记时，词边界 / 标点邻接判定，不做子串删除——"那个孩子"中的"那个"不删）；
   - 英文：uh、um、er、you know、I mean、like、sort of、kind of（保守边界，同 Hotword 的 ASCII 邻接匹配做法）。
2. `dup` 口吃 / 相邻重复：
   - 叠字误识：`X，X` / `XX`（如"得，得"→"得"）；
   - 被填充词 / 标点隔开的同串重复（"下周三，呃，下周三之前"→ 保留带后续内容的一次出现）。
3. `punct` 标点整理：连续标点合并、省略号规范化、句中冗余空白。

**明确不碰（测试钉死）：**

- 否定词及其邻接内容：不 / 没 / 别 / 没有 / 不是（"我不是说不行"原样保留）；
- 自我纠正链："X，哦不对，Y"、"不是 X，是 Y" 整段保留；
- 句尾情态词（吧 / 可能 / 应该 / 也许）：属态度证据，v1 一律不删（"行吧"≠"行"）；
- 数字、日期、人名、专名、英文词内部。

**挂载点（实时唯一咽喉）：** [record.py:389 `_on_sentence_end`](../app/routers/record.py#L389) —— 本地分段与云端流式两条链路在此汇合，热词之后做三件事：

1. `clean = clean_sentence(s["text"])`（开关在录制启动时快照，见下）；
2. WS `sentence` 消息：`text` 保持原文，附加 `clean_text` / `clean_ops`；
3. **下游 feed 替换**：summarizer / chapter_gen / translator 三处收到的句对象用 `clean.text` 覆盖 `text` 字段（说话人 / 时间戳不变，译文与摘要锚点不受影响）。开关关时整条链路零行为变化。

**设置生效时机（会话级快照）：** 清理开关在录制启动路由（record.py 读 `get_engine_config()` 同一位置）读取一次，随整场录制固定。会中切换菜单只改前端显示偏好（WS 仍按会话快照决定是否携带 clean_text）；下游输入不中途变口径，避免一场纪要前后规则不一致。会后各边界按当前设置实时派生。

**挂载点（WS 回放）：** [ws_transcript.py:78 history 回放](../app/routers/ws_transcript.py#L78) 对缓存原文逐句派生后再下发；`realtime_full_transcripts` 缓存本身保持原文。

**挂载点（会后消费者，统一 helper）：** 模块内另提供 `clean_dialogue_for_consumers(dialogue) -> dialogue`（深拷贝、逐句替换 `text` 为 clean；开关关时原样返回不拷贝）。调用点：

- [pipeline.py stage2](../core/pipeline.py#L257)：`generate_summary` / `generate_title` / `generate_chapters` 吃清理拷贝；`result["dialogue"]` 与 `save_summary` 导出仍用原文；
- [tasks.py:218 `_backfill_chapters`](../app/routers/tasks.py#L218)：补生成章节吃清理拷贝；
- [speakers.py:407 `regenerate_summary`](../app/routers/speakers.py#L407)：手动重生成纪要吃清理拷贝。

**挂载点（会后展示）：** tasks.get_task 响应拷贝上富化（§2.3）。

测试：新建 `tests/test_transcript_cleanup.py`——填充词删除、叠字合并、被标点隔开的短语重复、否定句零改动、自我纠正零改动、"那个孩子"零误杀、英文 filler、幂等（clean(clean(x))==clean(x)）、空串 / 纯标点、ops 记账准确；`clean_dialogue_for_consumers` 深拷贝隔离（改返回对象不影响原 dialogue）、关闭时返回原对象。record.py 挂载点补回调级测试：下游收到 clean、WS 收到双字段、缓存原文不变。

### WP-2 书面版（整场）

**新建 `core/transcript_formal.py`**

- `source_signature(dialogue) -> {count, hash}`
- `generate_formal_version(task_id, sentence_ids: list[int] | None, *, auto=False) -> dict`
  1. 前置：任务存在且 `status == "completed"`，否则返回 `formalize_requires_postmeeting`；
  2. 路由：`get_routing_decision("llm")`；route 不可用（含 trial 额度尽 / byok 缺 Key 且未同意自动改用）→ 返回 routing 的 reason，不发起调用。**不新增任何静默切付费逻辑**，闸门完全复用；
  3. 取扁平句子（`sentence_id` 锚点），按 ≤25 句切块；
  4. 逐块 `core.llm.chat_completion`（同步，后台线程执行），要求严格 JSON 数组回填，`temperature=0.2`；
  5. 块失败重试 1 次；仍失败 → 整任务 `error`（不留半截 items）；
  6. 落 sidecar：模型、source、`LlmResult.usage`、时间、auto 标记全部留痕；
  7. trial 路由的配额计量沿用现有云端 LLM 计量口径（与纪要生成同路径，不自造计量）。

提示词契约要点（落为模块内常量，单测锁定）：

- 输入带 `sentence_id` 的句子数组，输出**同 id、同数量、同顺序** JSON；缺 id / 多 id 的块判失败；
- 只改口语表达为书面语：去啰嗦、补主语可、连句可；**不得增删事实、不得改数字 / 日期 / 人名 / 专名**；
- 原文出现犹豫、勉强、否定条件时（"行吧""我不是说不行""再说吧"），书面句必须给 `"tone_flag": "weakened"`，由前端警示；模型不确定时也置标；
- 不输出 JSON 以外内容（去 ```fence 解析，解析失败重试 1 次）。

**路由（[tasks.py](../app/routers/tasks.py) 新增）：**

- `POST /api/tasks/{task_id}/formalize`，body `{ "sentence_ids": [..] }`（可省＝整场）
  - 用 `BackgroundTasks` 后台跑（对齐同文件 retry-summary 模式，L438）；先写 `running` sidecar 再返回；
  - 会中 → 409 `formalize_requires_postmeeting`；路由不可用 → 409 带 routing reason。
- `GET /api/tasks/{task_id}/formal` → sidecar + 实时 staleness 判定；无文件 404。

**自动生成钩子：** [pipeline.py stage2 纪要完成后](../core/pipeline.py#L255)，条件全满足才触发：`transcript.formal.auto_generate == true` 且 llm route 可用；失败仅日志 + sidecar error，不影响会议产物。

测试：`tests/test_transcript_formal.py`——monkeypatch `chat_completion` 返回契约 JSON：正常回填、tone_flag 判定、缺 id 块判错、切块边界、running→done 状态、stale 签名、会中 409、byok 缺 Key 未同意时 409、auto 开关关闭时不触发。

### WP-3 选区书面化 + 收尾

- 选区端点复用 WP-2 同一 POST（带 `sentence_ids`）；
- 前端划词动作（§4.4）；
- i18n、文档、CHANGELOG。

---

## 4. 前端任务

### 4.1 新增 composable：`composables/useTranscriptLayers.ts`

统一状态机，会中 / 会后两面板共用：

- `view: 'clean' | 'raw' | 'formal'`（默认 cleanup 开 → clean；关 → raw）；
- `cleanupEnabled`（来自 GET /api/settings 的 `transcript.cleanup.enabled`，切换即调 save settings，乐观更新 + 回滚）；
- `formalState: 'locked'（会中）| 'absent' | 'running' | 'done' | 'stale' | 'error'`；
- `lineText(line)`：按 view 取 `clean_text` / `text` / formalMap[id]；
- `generate(sentenceIds?)`、`pollFormal()`（running 时 2s 轮询，复用 `usePolling` 模式）；
- token 估算：`max(1, round(原文字符/1.6))`，UI 标"估算"。

### 4.2 新增 `api/transcriptLayers.ts`

`getFormal(taskId)`、`formalize(taskId, sentenceIds?)` 两个薄封装。

### 4.3 [recording/RecTranscriptPanel.vue](../frontend/src/views/recording/RecTranscriptPanel.vue)（会中）

- 头部加三段分段控件（书面版带锁）+ 更多菜单增两项（口语清理开关 / AI 书面化禁用项"会后可用"），菜单结构沿用现有翻译菜单（L26-60）与 `usePopMenu`；
- lines 数据入口 [useWebSocket.ts:180](../frontend/src/composables/useWebSocket.ts#L180) 的 `sentence` / `history` 分支把 `clean_text` / `clean_ops` 并入 line；
- 行渲染：清理视图显示 clean_text，行尾"已清理·原文"小标展开原文 + ops 明细；原文视图行尾"只读·引用锚点"；
- 书面 tab：仅黄色引导条，无列表无生成按钮（原型 bar-live）；
- 清理开关关闭：跳原文视图，清理段置灰（WS 后续消息不再带 clean_text，历史 line 已有值也不展示）。

### 4.4 [generating/TranscriptPanel.vue](../frontend/src/views/generating/TranscriptPanel.vue)（会后）

- 同一分段控件；书面 tab 三态：absent 空态（估算 tokens + 生成按钮）/ running 进度条 / done（留痕条：模型 · tokens · 时间 · tone 计数 + 重新生成）；stale / error 横幅；
- done 行尾"对照原文"展开双行 diff；`tone_flag` 句挂红色"⚠ 语气存疑"标，对照块内置警示文案（原型第 2 段）；
- 数据源：`flatTranscript` 已扁平化带 sentence_id（[useGeneratingData.ts:117](../frontend/src/composables/useGeneratingData.ts#L117)），formal map 按 id 取；
- [SelectionToolbar.vue](../frontend/src/components/SelectionToolbar.vue) 增"✨ AI 书面化选区"：取选区覆盖句的 sentence_id → formalize → 完成后切书面视图；任务未完成时禁用。

### 4.5 i18n / 样式 / 验收

- 文案入 `recording.json` / `generating.json` / `common.json`，zh-CN + en 同步；
- 样式并入 `recording.css` / `meeting-view.css`，复用现有色板，不引新视觉语言；
- 验收：`vue-tsc` 零错、前端构建通过；按原型 17 项走查单回归（含清理明细、否定句保留、对照、tone 警示、会中锁定、开关逃生、420px 窄屏）。

---

## 5. 切片顺序与验收门

| 切片 | 后端 | 前端 | 验收门 |
|---|---|---|---|
| WP-1 清理层 | cleanup 模块 + 实时咽喉 + 会后三消费者挂载 + 设置键 | useWebSocket 取字段 + 会中面板三段 / 回览 / 开关 | pytest 新增全绿；实时摘要/章节/翻译与会后纪要/章节均吃清理版且 task.dialogue 原文不变；关开关零行为变化；Ruff 干净 |
| WP-2 书面整场 | formal 模块 + sidecar + 两路由 + 自动钩子 + 设置键 | 会后面板三态 / 留痕 / 对照 / tone | 假 LLM 单测全绿；真实路由走通 byok 与 local_endpoint；会中 409；stale 重生成 |
| WP-3 选区收尾 | 同 POST 复用 | 划词动作 + i18n + 文档 | 选区生成、整场覆盖、窄屏走查；CHANGELOG |

---

## 6. 决策记录

1. **清理版不落盘、读取边界派生。** 规则可复现、零成本；天然规避回溯修正后的双写不一致，免数据迁移。
2. **实时挂载点选 `_on_sentence_end` 而非引擎内部。** 本地 / 云端两链路唯一汇合点，引擎保持与产品语义解耦（与热词在引擎内调用的现状不同——清理是产品层视图，不污染 ASR 产物）。
3. **书面版锚定 sentence_id + source_sig 失效检测。** 不做文本偏移对齐（AI 重写后偏移必错）；重新转写后宁可要求重生成，不展示错配内容。
4. **tone_flag 是强制契约而非可选项。** 语义反转是本方案最大风险，模型必须对弱化 / 勉强语气显式担责，前端默认展示警示。
5. **自动生成默认关、手动生成走既有路由闸门。** 扣费授权 / 留痕完全复用 capability_source + auto_fallback + LlmResult.usage，不造第二套。
6. **不进设置页。** 清理开关默认开 + 逃生通道；自动书面化开关藏功能区更多菜单。
7. **清理版进摘要 / 章节 / 翻译，仅在消费者边界替换（评审裁决）。** task.dialogue 与实时缓存仍是唯一原文事实源；会后用深拷贝喂 LLM，杜绝清理逻辑污染落盘。代价：清理规则误删会影响纪要质量——由保守规则集（否定 / 自我纠正 / 情态词零改动）、可复现单测、逃生开关三层兜底。
8. **清理开关会话级快照。** 录制启动读一次，一场会议口径一致；会中切菜单只改显示，不中途换下游输入。

## 7. 已定裁决与遗留开放项

已定（2026-09-30 评审）：

1. ~~清理版是否进下游？~~ → **进**：摘要、章节、翻译吃清理版；导出附稿与 AI 对话上下文仍吃原文。
2. 导出 md/docx 是否含清理 / 书面版？（v1 **不含**，导出仍为原文；后续可加导出选项）
3. ~~书面版是否允许单句采纳写回？~~ → **不允许**，采纳即破坏"原文不可变"心智；需要时另开提案，走 rewrite_snapshots 快照通道。

遗留（实现时默认按括号口径，评审可否决）：

4. local_endpoint 作为书面化算力时菜单副文案不显示"耗额度"，按 routing source 动态措辞。
