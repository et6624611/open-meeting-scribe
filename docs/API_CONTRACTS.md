---
title: 外部接口契约
description: DashScope / 通义千问 API 技术细节的唯一事实源
author: Yongliang Wang
created_at: 2026-09-03
updated_at: 2026-09-30
status: published
---

# API_CONTRACTS — 外部接口契约（DashScope / 通义千问）

> 技术细节的**唯一事实源**。代码注释只引用本文，不复述。来源：阿里云百炼官方文档（2026-09 核对）。

## 0. 鉴权
- 全部用同一个 `DASHSCOPE_API_KEY`（环境变量读取，禁止硬编码）。
- 请求头：`Authorization: Bearer {api_key}`。
- 公共端点：`https://dashscope.aliyuncs.com`（本机已验证可达）。

---

## 1. 上传本地文件 → 临时 URL（内录/本地音频必走）
API **不支持本地文件 / Base64 / 二进制流**，只认公网 URL。DashScope 提供**免费临时存储**换 `oss://` URL。

**步骤一：获取上传凭证**
```
GET https://dashscope.aliyuncs.com/api/v1/uploads?action=getPolicy&model=paraformer-v2
Header: Authorization: Bearer {api_key}
→ data: { upload_host, upload_dir, oss_access_key_id, policy, signature, x_oss_object_acl, x_oss_forbid_overwrite }
```
**步骤二：POST 上传到 OSS**（multipart，字段用凭证里的值 + `key={upload_dir}/{文件名}` + `success_action_status=200` + `file`）
→ 返回临时 URL：`oss://{key}`

**限制**：单文件 ≤1GB；有效期 48h；文件与「模型名 + 主账号」绑定；上传凭证接口限流 100 QPS；文件上传后不可查询/下载，仅能用 URL 调用。

---

## 2. 提交转写任务（paraformer-v2，异步）
```
POST https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription
Header:
  Authorization: Bearer {api_key}
  Content-Type: application/json
  X-DashScope-Async: enable                     # 必带，否则无法提交
  X-DashScope-OssResourceResolve: enable        # 当 file_urls 用 oss:// 临时URL时必带
Body:
{
  "model": "paraformer-v2",
  "input": { "file_urls": ["oss://.../x.wav"] },   # 单次仅 1 个 URL；含空格/中文须先URL编码
  "parameters": {
    "channel_id": [0],
    "language_hints": ["zh", "en"],              # 仅 paraformer-v2 支持
    "diarization_enabled": true,                 # 说话人分离（仅单声道生效）
    "speaker_count": 2,                          # 可选，2–100，仅辅助不保证
    "disfluency_removal_enabled": false,         # 过滤语气词
    "timestamp_alignment_enabled": false,        # 时间戳校准
    "vocabulary_id": "xxx"                       # 可选，热词表ID
  }
}
→ output.task_id, output.task_status(PENDING)
```
> SDK 方式**不支持** `oss://` 前缀、也不能配 header → 本接口**必须用 `requests` 直调 RESTful**。

---

## 3. 轮询查询任务
```
POST https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}
Header: Authorization: Bearer {api_key}
→ output.task_status: PENDING / RUNNING / SUCCEEDED / FAILED
→ output.results[].transcription_url   # SUCCEEDED 后，24h 有效
→ output.results[].subtask_status      # 多子任务时逐个判断
```
下载 `transcription_url` 得结果 JSON。

---

## 4. 结果 JSON 关键字段
```
transcripts[].sentences[]:
  begin_time / end_time   # ms
  text                    # 句子文本
  sentence_id
  speaker_id              # 仅 diarization_enabled=true 时出现；0 起始
  words[]                 # 词级时间戳 + punctuation
properties: audio_format / channels / original_sampling_rate / original_duration_in_milliseconds
```
**组装对话稿**：按 `speaker_id` 归并 `sentences` → 「说话人N：文本」。

---

## 5. 纪要生成（通义千问）
- 模型：`qwen-plus`（默认）/ `qwen-max`。
- 调用：DashScope OpenAI 兼容端点或 dashscope SDK；同一个 `DASHSCOPE_API_KEY`。
- 输入：发言人对话稿；输出：结论 + 待办（谁 / 做什么 / 截止）+ 议题归类。
- 提示词与解析在 `core/summarize.py`。

---

## 6. 硬约束汇总（违背即失败）
| 约束 | 后果 | 对策 |
|------|------|------|
| 只认公网 URL | 本地文件直传报错 | 先走 §1 上传换 `oss://` |
| `oss://` 需 RESTful + `X-DashScope-OssResourceResolve` | SDK 调用失败 | 用 `requests` |
| 分离仅单声道 | 无 `speaker_id` | ffmpeg 下混单声道 |
| URL 含空格/中文未编码 | `InvalidFile.DownloadFailed` | 提交前 URL 编码 |
| 上传 ≤1GB / 48h | 超限失败/过期 | 常规会议足够；超长分段或自建 OSS |
| 缺 `X-DashScope-Async: enable` | 无法提交异步任务 | 必带该头 |
| 开分离且音频 >2h | 可能超时/失败 | 长音频分段 |
| 实时 API 不支持说话人分离 | 无 `speaker_id` | 实时仅做预览，最终纪要走批管线 |
| 实时音频须 PCM 16bit/16kHz/mono | 格式不匹配识别失败 | ffmpeg 输出 `s16le -ar 16000 -ac 1` |

## 7. 音频规格
- 单文件 ≤12 小时、≤2GB（转写上限）；上传接口 ≤1GB。
- 任意采样率；兼容 wav / mp3 / aac 等主流格式。

## 8. 计费
- 只对**语音内容时长**计费（非语音不计），约 **0.288 元/小时**量级，以百炼控制台实价为准。
- 指定多音轨（`channel_id:[0,1]`）每轨独立计费。
- 纪要按千问 token 计费。

---

## 9. 实时语音识别（qwen-audio-3.0-asr-flash-streaming，流式 WebSocket）

用于录音期间的实时转写预览。**不支持说话人分离**。

**WebSocket 地址**：`wss://dashscope.aliyuncs.com/api-ws/v1/inference`（代理模式下通过 `ws://proxy:8200/asr/ws` 中继）

**调用方式**（代理模式，客户端通过代理 WebSocket 中继）：
- 客户端连接 `ws://proxy:8200/asr/ws?timestamp=...&sign=...&model=...`
- 代理中继到 DashScope WebSocket
- 客户端发送 PCM 二进制帧 → 代理转发到 DashScope
- 代理接收 DashScope 识别结果 → 转发给客户端（JSON：`partial`/`sentence`/`error`/`complete`）

**DashScope SDK 直调方式**（仅代理服务端内部使用）：
```python
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

dashscope.base_websocket_api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"

recognition = Recognition(
    model='qwen-audio-3.0-asr-flash-streaming',
    format='pcm',
    sample_rate=16000,
    language_hints=['zh', 'en'],
    semantic_punctuation_enabled=True,  # 会议场景用语义断句
    heartbeat=True,                     # 保持长连接
    callback=callback,                  # RecognitionCallback 实例
    # 可选：预编译热词表 ID
    # vocabulary_id='xxx',
    # 可选：即时热词（随请求内联传入，免创建热词表）
    # vocabulary={'张三': 5, '李四': 5},
)
# 启动（如有上下文增强，通过 raw_input 传入）
# context = [{"role": "user", "content": [{"type": "input_text", "text": "领域术语..."}]}]
# recognition.start(raw_input={"context": context})
recognition.start()
# 循环送入 PCM 数据（建议每包 ~100ms = 6400 bytes @16kHz/16bit/mono）
recognition.send_audio_frame(pcm_bytes)
recognition.stop()  # 阻塞直到所有结果返回
```

**回调事件**：
- `on_event(result)` → `result.get_sentence()` 返回句子 Dict
  - `RecognitionResult.is_sentence_end(sentence)` 判断是否定稿
  - 未定稿 = 临时结果（partial），定稿 = 最终句子
- `on_complete()` → 识别任务完成
- `on_error(result)` → 异常

**关键参数**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `semantic_punctuation_enabled` | False | 语义断句（会议场景推荐开启） |
| `max_sentence_silence` | 800ms | VAD 断句静音阈值 |
| `disfluency_removal_enabled` | False | 过滤语气词 |
| `vocabulary_id` | - | 预编译热词表 ID（需预先创建，target_model 须匹配） |
| `vocabulary` | - | 即时热词 Dict（如 `{"张三": 5}`，随请求内联传入） |
| `language_hints` | ["zh","en"] | 语种声明 |
| `heartbeat` | False | 静音时保持连接 |

**上下文增强（context）**：
- 通过 `raw_input={"context": [...]}` 传入，格式同多轮对话
- 可传入领域术语/对话历史，显著提升专有词汇识别率
- 引擎最多保留最近 5 轮上下文；仅传术语时 1 条即可
- 每轮文本总长度不超过 400 字符

**与批转写的关系**：
- 实时（qwen-audio-3.0-asr-flash-streaming）：流式、低延迟、无说话人分离 → 用于录音预览
- 批量（paraformer-v2）：异步、高准确率、有说话人分离 → 用于最终纪要
- 两者共用同一个 `DASHSCOPE_API_KEY`（代理服务端持有）

---

## 10. ASR 代理 API（客户端 ↔ 代理）

客户端不再直连 DashScope ASR API，所有转写请求通过 ASR 代理中转。详见 ADR-0012。

**代理地址**：通过 `.env` 中 `ASR_PROXY_URL` 配置

**认证**：所有请求须携带 HMAC-SHA256 签名
- HTTP 请求头：`X-ASR-Timestamp`（Unix 秒）+ `X-ASR-Sign`（HMAC-SHA256(token, timestamp)）
- WebSocket 查询参数：`timestamp` + `sign`
- 签名有效期 5 分钟防重放

### POST /asr/transcribe

一站式转写：接收音频文件 → 上传 → 提交 → 轮询 → 返回完整结果。

**请求**（multipart/form-data）：
- `file`: 音频文件
- `model`: 模型名（默认 `paraformer-v2`）
- `diarization_enabled`: 说话人分离（默认 `true`）
- `language_hints`: 语言提示（JSON 数组）
- `speaker_count`: 说话人数量
- `vocabulary_id`: 热词表 ID

**响应**：
```json
{
  "task_id": "xxx",
  "file_url": "oss://...",
  "transcription": { "transcripts": [...] }
}
```

### WebSocket /asr/ws

实时流式转写中继。

**查询参数**：`timestamp`, `sign`, `model`, `sample_rate`, `language_hints`, `vocabulary_id`

**客户端 → 代理**：二进制帧（PCM 音频）或 `{"type": "stop"}`
**代理 → 客户端**：`{"type": "partial"|"sentence"|"error"|"complete", ...}`

### GET /health

健康检查，返回 `{"status": "ok", "service": "asr-proxy", "dashscope_configured": true/false}`

---

## 11. 本地应用内部端点（QA-R1 缺陷修复批次 · 先行登记）

> 状态：**前端已按本节实现**（分支 `fix/qa-r1-def04-def02-frontend-20260924`）；后端由 `a4cdbd0ca795` 同批实现，合入前须双方核对确认。依据：QA-R1 缺陷派工 §2 DEF-QA-R1-04 / DEF-QA-R1-02。

### POST /api/tasks/{task_id}/retranscribe（DEF-QA-R1-04 改造）

- 请求体（JSON，可选）：`{"engine_override": "cloud"}`
  - 缺省（无请求体）：按当前引擎设置重跑，行为与现状完全一致（向后兼容）。
  - `engine_override="cloud"`：显式切云端引擎重跑；保持任务与笔记状态不丢失，复用 `pipeline_runner.on_failure` 落盘语义。
- 约束：**仅**在用户对「数据上云」显式确认后由前端调用，绝不静默上云（PRD R7）。
- 响应：`{"status": "processing", "message": "..."}`（与现状一致）。
- 消费方：`frontend/src/api/tasks.ts retranscribe(taskId, { engineOverride: 'cloud' })` → GeneratingView 失败卡片「切云端重试」。

### GET /api/download/{task_id}?format=docx|md（DEF-QA-R1-02 改造）

- 查询参数 `format`：`docx` | `md`；**缺省 `md`**（与现状行为一致，向后兼容）。
- `format=docx`：由 md 纪要生成 Word 文档（标题/说话人段落/时间戳映射为 Word 结构，中文不乱码），`Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`。
- 任务无 `output_path` 时返回 404（现状不变）。
- 消费方：`frontend/src/api/tasks.ts downloadSummaryUrl(taskId, format)` → LibraryView 批量导出弹窗。

### 任务 JSON 失败字段（已有落盘语义，前端自本批次开始消费）

`GET /api/tasks/{id}` 失败任务附带（`core/pipeline_runner.on_failure` 落盘）：

```json
{ "error_code": "engine_timeout", "can_fallback_cloud": true, "error_category": "local_engine" }
```

- `can_fallback_cloud=true` ⇒ 前端渲染「切云端重试」+ 显式确认；`false` ⇒ 按钮置灰 + 纯内网原因说明。
- 前端仅在 `error_category === "local_engine"` 时展示回退 UI。

---

## 12. 决策中心 API（DC-UNIFY-01 · 决策流是唯一决策对象）

> 依据 `docs/REQUIREMENT-DECISION-CENTER.md` v0.3.0。项目方 2026-09-27 裁决：只保留**决策流**（`task["todos"]`）
> 一种决策对象；原 `task["decisions"]`（decision 记录）及其任务级 CRUD、纪要页只读展示区全部下线，
> 存量 decision 数据不再迁移（磁盘保留、无读路径）。

### 12.0 决策流节点（`task["todos"]` 数组元素）

```jsonc
{
  "id": "uuid4 字符串，任务内唯一",
  "title": "决策短标题（三要素之一，可为空串；auto/手动添加常为空）",
  "text": "决策正文（转述文本，不含 [待确认] 前缀）",
  "assignee": "执行人展示名（快照；有 owner_id 时读侧以说话人档案为权威解析）",
  "owner_id": "执行人说话人档案 uuid，未指派为 null",
  "owner_type": "self | agent | colleague | enterprise（等待谁推进，展示用）",
  "status": "状态字典 id（默认六态 to_decide/to_start/in_progress/to_confirm/superseded/done；用户可增删改）",
  "done": false,               // 兼容字段：等价于 status 属于闭档（完成类）态
  "superseded_by": null,       // 手动「已替代」快照：{task_id, todo_id, title, meeting_title, prev_status, marked_at}；未标记为 null
  "why": "决策正文（Markdown）",
  "how": ["执行步骤…"],         // 缺省视为 [text]
  "outcome": "完成后带来什么",
  "pending_confirmation": false, // 仅 auto 解析的历史标志位，不再作为筛选维度
  "source": "auto | manual | injection | backfill",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

- **状态字典化（DC-R2-c D6/D7 + DC-UNIFY-01 + DEBRISH-EVO）**：`status` 取值必为 `GET /api/decision-statuses` 中的 id（非法值 422）。字典默认集 = 决策流六态；系统锚点为 `done`（完成）与 `superseded`（已替代，闭档但语义不同于完成，专用于演变链手动替代，详见 §12.6），均不可改名不可删除，其余四态用户可维护。
- **`closing`（算完成类）语义**：带此标志的状态在默认视图隐藏并沉底，同时驱动 `done=true`；读侧 `status` 缺省时由 `done` 推导（历史 task JSON 零迁移）。
- **自动生成口径（项目方裁决）**：纪要「主要结论」章节的条目自动解析为决策流节点（模板 v1.4.0 已下线「决策」章节、改为单通道 + 终态归并；解析器仍兼容存量纪要的「决策」章节）；自动节点**统一落在 `to_decide`（待决策）态**，由用户逐条确认后才算定案；checkbox 行动项仍按既有规则入流（默认开放态）。
- **重新生成纪要**：只覆盖 `source=auto` 节点，手动/注入节点保留；命中 `task["decision_deletions"]` 墓碑（按归一化文本）的 auto 节点不复活（DC-R2-BE）。
- **执行人以说话人档案为权威**：`owner_id` 可解析且档案名非占位串 ⇒ 展示名取档案名（改名全局生效）；档案缺失时回退 `assignee` 快照，不报 422。
- **旧任务 JSON 无 `todos` 字段** ⇒ 读写路径按 `[]` 处理；无 `title`/`owner_id` 键 ⇒ 读侧按 `""`/`null` 给出，展示层降级为「正文即标题」。

### 12.1 节点级 CRUD（复用决策流端点，与纪要页同一套）

| 方法与路径 | 请求体 | 响应 | 错误 |
|---|---|---|---|
| `GET /api/tasks/{task_id}/todos` | — | `{"todos": [节点 + status_name/status_name_en/status_color/status_closing + 会议元信息]}` | 404 任务不存在 |
| `POST /api/tasks/{task_id}/todos` | `{text: str(1..500), assignee?: str="", why?: str(≤2000), title?: str(≤200), owner_id?: str|""=null, status?: <状态字典 id>}` | `{"todo": node}`（缺省 `source=manual`、`status=首个开放态`） | 404；422（含 status 不在字典内） |
| `PUT /api/tasks/{task_id}/todos/{todo_id}` | `{text?, title?, assignee?, owner_id?, why?, how?, outcome?, status?, owner_type?}`（仅更新携带字段） | `{"todo": node}` | 404 任务/节点不存在；422 status 非法 |
| `DELETE /api/tasks/{task_id}/todos/{todo_id}` | — | `{"ok": true}`（auto 节点同时落墓碑） | 404 |
| `POST /api/tasks/{task_id}/todos/{todo_id}/toggle` | `{done: bool}` | `{"todo": node}` | 404 |
| `POST /api/tasks/{task_id}/todos/{todo_id}/supersede` | `{by_task_id: str, by_todo_id: str}`（替代者节点） | `{"todo": node}`（status=`superseded`，写入 `superseded_by` 快照，原 status 存 `prev_status`） | 404 节点/替代者不存在；422 自身替代；409 已是 superseded（`detail.code=already_superseded`） |
| `DELETE /api/tasks/{task_id}/todos/{todo_id}/supersede` | — | `{"todo": node}`（恢复 `prev_status`；该状态已不在字典则降级首个开放态；清除快照） | 404；409 当前非 superseded（`detail.code=not_superseded`） |

写操作（POST/PUT/DELETE/toggle）一律触发 `_mark_modified` + `save_task_to_disk`（知识库脏检测链路，PRD AC-10）。

<!-- 旧 §12.1 的任务级 decision CRUD（GET/POST/PUT/DELETE /api/tasks/{id}/decisions*）已随 DC-UNIFY-01 下线；
     决策中心不再另开一套写入路径，一律走上表。 -->

### 12.2 聊天注入联动

`POST /api/tasks/{task_id}/inject` 当 `type` 为 `todo` 或 `decision` 时，均向 `task["todos"]` 追加一条决策流节点（`id` 与注入记录同值、`source="injection"`）；`decision` 类型额外拆 `**标题**：正文` 到 `title` 并落在 `to_confirm` 态，`todo` 类型落默认开放态。删除注入记录时级联删除该节点。

### 12.3 跨会议聚合 `GET /api/decisions`（决策中心数据源）

查询参数（全部可选，可叠加）：

| 参数 | 语义 |
|---|---|
| `since` / `until` | 按会议日期过滤，`YYYY-MM-DD`，闭区间；任务无 `meeting_date` 时在给定日期过滤下被排除 |
| `kb_id` | 按所属知识库（= `project_id`）过滤 |
| `status` | 状态字典 id 精确过滤（非封闭枚举）；非法值 422 |
| `q` | `text` / `title` / `why` 子串匹配（区分大小写） |
| `task_id` | 限定单场会议（纪要页快照用）；缺省为全量 |
| `group_by` | `meeting`\|`date`\|`topic`；缺省返回平铺列表 |

响应：行 = 决策流节点 + 状态字典元信息 + 来源会议元信息（`meeting_title` / `meeting_date` / `kb_id` / `kb_name`），分组结构与旧版一致。

- **状态元信息随行下发**：`status_name` / `status_name_en` / `status_color` / `status_closing` 由后端从字典解析，前端色点、徽标与沉底分层全部配置驱动（不写死 `st-*` 类名）；字典中查不到的历史 status 降级为首个开放态。
- 平铺与组内均按 `meeting_date` 倒序（无日期沉底）；默认视图「只看非闭档」由前端本地筛选（后端不默认过滤）。
- 数据源为后端内存任务表（桌面单机量级），无分页契约；`total` 随列表长度给出。
- **`group_by=topic`（DEBRISH-P2 全局视角）**：响应为 `{"topics": [TopicGroup…], "total": 参与归并的节点数, "topic_count": n}`。
  算法：同 `kb_id`（未关联归为 `null` 同桶）内、以「议题指纹」（`title`，无则正文首句）的字符二元组**重合度** ≥ 0.6 聚为同簇（`core/decision_topic`，确定性、零 LLM）。
  每簇 `TopicGroup = { topic_key, kb_id, kb_name, title, main, history[], size, meeting_count, confidence }`：
  - `main` = 最新非闭档节点（否则最新），`history` = 其余按时间倒序；`confidence` = 除 leader 外成员与 leader 的最小相似度（自动归并强度）。
  - **仅视图归并，不改数据**：`main`/`history` 都是各自会议独立的决策流节点（完整 FlowNode 形状），写操作仍走 §12.1 任务级端点；议题视图不引入新的持久化对象。

### 12.4 状态字典 CRUD（DC-R2-c · `data/decision_statuses.json`）

| 方法与路径 | 请求体 | 响应 | 错误 |
|---|---|---|---|
| `GET /api/decision-statuses` | — | `{"statuses": [status…], "total": n}`（按用户排序返回） | — |
| `POST /api/decision-statuses` | `{name: str(1..20), color?: str(≤64)="", closing?: bool=false}` | `{"status": status}` | 400 空名/重名 |
| `PUT /api/decision-statuses/{id}` | `{name?, color?, closing?}` | `{"status": status}` | 404 状态不存在；400 锚点改名/改闭档、重名、空名 |
| `DELETE /api/decision-statuses/{id}` | — | `{"ok": true, "removed": id, "reassigned": n}` | 404 状态不存在；400 系统锚点不可删 |
| `POST /api/decision-statuses/reorder` | `{order: [id…]}`（必须完整覆盖且不重复） | `{"statuses": [status…], "total": n}` | 400 集合不完整或重复 |

```json
// status 对象
{ "id": "to_decide | to_start | in_progress | to_confirm | done | st-<hex8>",
  "name": "待确认", "name_en": "To confirm",
  "color": "var(--st-confirm)", "closing": false, "system": false }
```

- **首次读取即迁移**：文件不存在时自动写入内置六态（`to_decide`/`to_start`/`in_progress`/`to_confirm`/`superseded` + `done` 锚点，`superseded` 位于 `done` 前）；已存在旧结构（以 decision 对象为中心的 active/superseded/revoked）时自动补齐缺失种子、剪除未被改过名的遗留态并回写。文件缺 `done` 锚点或脏数据时整体回退默认集，不阻断决策中心。
- **系统锚点为 `done` 与 `superseded`**（D6 + DEBRISH-EVO）：均不可改名、不可删除、不可改闭档位（两者默认 `closing=true`）；其余四态用户可改名/标色/排序/删除。
- **`color` 允许 CSS 变量表达式**（如 `var(--accent)`）或十六进制色值，前端内联使用以随主题联动。
- **`name_en` 仅内置状态有独立英文名**；自定义状态的 `name_en` 与 `name` 同值。
- **删除自定义状态的联动**：引用该状态的**决策流节点（todos）**当场回落到删后字典的首个开放态并逐任务落盘（`reassigned` 返回影响条数），不留悬空引用。

### 12.5 AI 写回快照与撤销（PROPOSAL-AGENT-REWRITE-CHANNEL §5.3/§5.4 · 已实现）

| 方法与路径 | 请求体 / 参数 | 响应 | 错误 |
|---|---|---|---|
| `GET /api/tasks/{task_id}/rewrites` | `target?`、`turn_id?` | `{"snapshots": [{id, target, tool, turn_id, ts, description}…]}` | 404 任务不存在 |
| `POST /api/tasks/{task_id}/rewrites/restore` | `{snapshot_id?: str(≤64), turn_id?: str(≤128)}`（二者传其一） | `{ok: true, restored: n, detail: [文本…], skipped: [文本…]}` | 404 任务/快照/本轮不存在；400 两者均缺或无可回滚内容 |

- **快照存储**：`data/tasks/<task_id>.rewrites.jsonl`（追加式 sidecar，与任务 JSON 同目录），每 target 保留上限 **N=20** 版；
  过期清理与智能体工作区共用 `chat_engine.retention_days` 口径（启动时 `sweep_expired_snapshots`）。
- **target 定名**：`decision_node:<nodeId>`（节点粒度，与 DC-UNIFY-01 唯一对象同寻址单元）/ `summary` / `notes`。
- **写入时机**：仅 **AI 会话写回**（`update_decision_node` / `delete_decision_node` / `inject_items` 新建 / `update_summary`）在落盘前强制快照；
  用户在前端的手动编辑不快照。被参数校验拒绝（400/422）的写**不留快照**。
- **列表只回摘要不回旧值全文**（`description` 为一行人类可读描述）；`restore` 按 `turn_id` 时**逆序**回滚整轮，
  恢复本身不再写快照（避免撤销无限套娃），但落 `[agent-engine] restore_rewrites` 审计条目。
- **工具面配套**：`get_meeting_todos` 除节点 `id/title/status` 外同时下发 `available_statuses`（`{id,name,closing}[]`）与 `status_note`，
  否则模型无合法 status 可用；`done.metadata` 携带 `rewritten / rewritten_tools / turn_id / task_id` 作为“本轮改了什么 + 能否撤销”的事实源。
- **前端联动**：写回成功后 AI 面板广播 `task-written` CustomEvent，会议详情页据此重拉 task 与决策列表；
  回复尾部展示「本轮已改写：{域}」并提供「撤销本轮改写」（转 `POST …/rewrites/restore`）。

### 12.6 决策演变链（DEBRISH-EVO · 手动替代 + 跨会议归属）

设计裁决：**聚类永不自动写状态**；演变关系只由用户在演变链历史项上**逐条手动标记**，不提供自动/批量替代。
旧决策被标记后进入系统闭档态 `superseded`，离开待办（默认视图隐藏、沉底），但保留只读快照与动作出口。

**替代端点**：见 §12.1 表尾两行（`POST/DELETE /api/tasks/{task_id}/todos/{todo_id}/supersede`）。
标记成功后写入节点字段 `superseded_by`：

```jsonc
{
  "task_id": "替代者所在任务",
  "todo_id": "替代者节点 id（快照；若被删除前端降级为「原决策已被删除」）",
  "title": "替代者标题快照",
  "meeting_title": "替代者会议标题快照",
  "prev_status": "标记前的状态 id（撤销时恢复；已被字典删除则降级首个开放态）",
  "marked_at": "ISO 8601"
}
```

**归属查询**（纪要页节点角标数据源）：

`GET /api/decisions/evolution?task_id=<id>`（未知 task 404）

```jsonc
{
  "task_id": "<id>",
  "evolution": {
    "<todo_id>": {
      "topic_key": "议题指纹（与 §12.3 group_by=topic 同算法同 key，可回跳决策中心定位）",
      "topic_title": "议题展示标题",
      "role": "main | history",   // main=本节点即该簇最新非闭档节点；history=最新推进在另一场会议
      "meeting_count": 3,
      "latest": { "task_id": "...", "todo_id": "...", "title": "...", "meeting_title": "..." }
    }
  }
}
```

- **必须全量 rows 聚类后再按 task 过滤**（先过滤则跨会议簇不成立）；单节点簇不返回（无演变语义）。
- 归属为读时计算（`core/decision_topic`，零持久化）；节点进入 superseded 后，簇主记录选取（跳过闭档）自动前移，前端下次 reload 即一致。

**前端路由锚点契约**：

| 入口 | 路由 | 行为 |
|---|---|---|
| 演变链节点「查看来源会议」 | `generating?tab=todos&todo=<id>&from=evolution` | 切决策面板；闭档组自动展开；节点滚动居中并闪烁 3 次；顶部来源横幅（可关闭） |
| 纪要页角标「议题全貌」 | `decisions?view=topic&topic=<topic_key>` | 切议题视图；展开该议题与其演变链；滚动定位 |
| history 角标「最新推进」 | 同第一条（指向 latest 节点） | 同上 |

---
## 13. 接入方式路由契约（REQ-ACCESS-MODE-CARDS · AM-B1 后端交付 · AM-F1 前端派工依据）

> 依据：`docs/REQUIREMENT-ACCESS-MODE-CARDS.md` v0.1.0 §3–§6。后端实现在分支 `feat/req-access-mode-b1`。
> 本契约合入前须与 §12（DC-DEC-B1 同文件追加）做顺序核对——两节无内容交集，仅同文件尾追加。

### 13.1 新增用户侧字段（`data/settings.json`，`app/settings_store.py`）

| 字段 | 类型 | 取值 | 说明 |
| --- | --- | --- | --- |
| `access_mode` | str \| null | `local` \| `hosted` \| `byok` \| `null` | 唯一路由判定数据源；`null`=未配置，触发 R4 引导 |
| `expert_mode` | bool | — | true 时前端展示旧版分类视图（D4）；存量自定义 base_url/model 覆盖或非默认 Key 组合自动置 true |
| `_access_mode_migrated` | bool | — | 一次性迁移标记；迁移后旧字段原样保留（A2 兼容窗口一个版本，写路径继续同步旧字段支持回滚） |

### 13.2 §4 一次性迁移映射（启动钩子 `run_access_mode_migration()`；未落盘时读取侧按同表惰性推导）

| 存量组合 | 迁移为 |
| --- | --- |
| `engine.mode=local` | `local` |
| `engine.mode=proxy`（含 `cloud`，同为云代理计费，A-i1） | `hosted` |
| `engine.mode=direct` 且 `prefer_subscription=false` | `byok` |
| `engine.mode=direct` 且 `prefer_subscription=true` | `hosted`（A1 裁决） |
| 未配置 | `null`（触发引导） |

### 13.3 `GET /api/settings` 响应扩展

新增顶层字段（其余字段不变，向后兼容）：

```json
{ "access_mode": "local|hosted|byok|null", "expert_mode": true }
```

另：响应含顶层 `transcript` 块，契约见 §17.1。

### 13.4 `POST /api/settings` 请求扩展

- 可选 `access_mode`：`"local"|"hosted"|"byok"|null`。非法值忽略并记日志（与 engine.mode 白名单口径一致）。写入时后端同步旧字段：local→`engine.mode=local`；hosted→`engine.mode=proxy`+`asr.mode=proxy`；byok→`engine.mode=direct`+`asr.mode=direct`（A2 回滚窗口）。
- 可选 `expert_mode`：仅接受布尔。
- 可选 `transcript`（部分合并，只传单块即可，契约见 §17.1）。
- 兼容窗口：旧客户端只写 `engine`/`asr` 时，后端按 13.2 映射**重对齐** `access_mode`，保证判定单源不漂移。

### 13.5 新端点 `GET /api/settings/routing`（路由结论查询，D2/AC-T2③）

前端（AM-F1 状态栏/引导/toast）唯一路由感知入口；后端判定实现于 `core/routing.get_routing_decision`。

```json
{
  "ok": true,
  "access_mode": "byok",
  "expert_mode": false,
  "onboarding_required": false,
  "llm": { "configured_access_mode": "byok", "expert_mode": false, "route": "cloud",
           "route_override": true, "reason": "prefer_subscription" },
  "asr": { "configured_access_mode": "byok", "expert_mode": false, "route": "cloud",
           "route_override": true, "reason": "prefer_subscription" },
  "quota": { "allowed": true, "remaining": 280.0, "quota": 300, "used": 20.0, "warning": null }
}
```

- `route ∈ {local, cloud, proxy, direct}`：`local`=离线引擎；`cloud`/`proxy`=托管计费路径（proxy 仅 ASR 传输细节）；`direct`=自有 Key 直连。
- `route_override=true` ⇒ 实际路由**偏离**所配置 access_mode 语义，前端须显性告知（D2 toast「本次起走平台额度」，一次且仅一次的判重由前端负责）。`reason` 枚举：
  - `prefer_subscription` — byok 用户开启「优先使用订阅流量」且配额>0、云端可用；
  - `byok_key_missing` — byok 配置但无有效 Key，回退云代理（与升级前行为等价）；
  - `byok_key_missing_cloud_unavailable` — 无 Key 且云端不可用，维持直连（调用将显式报错，不静默换计费路径）；
  - `legacy_unconfigured` — access_mode=null 未配置兜底（行为与升级前逐项等价）。
- `onboarding_required=true`（即 `access_mode=null`）⇒ 前端展示三卡片引导（R4）。
- `quota` 仅在 `core/metering.is_metered()=true` 时非 null（口径：hosted 消耗配额 / byok 走自有 Key / **local 恒不计量**，`route=local` 时 `is_metered()` 直接返回 false）。
- localhost 自持端点（Ollama/LM Studio）永不切云：`route_override` 判定在 localhost 守卫之后（PRD R4 绝不回退云端）。

### 13.6 路由判定唯一入口（消歧）

`_should_use_cloud`（`core/llm.py`）与 `_get_asr_mode`（`core/transcribe.py`）为薄适配层，仅调用 `core/routing.get_routing_decision(context)`；对 `engine.mode`/`prefer_subscription` 组合的读取只存在于 `core/routing.py`。旧字段读取兼容一个版本（A2），窗口结束后专家模式下只读写新字段。

---

## 14. 洞察台会后化 API（REQ-INSIGHT-DECK-POSTMEETING R2 · 已实现）

### POST /api/insights/analyze（新增可选字段 existing_insights · 只读累进 Phase 1）

- 请求体新增可选字段 `existing_insights?: [{title, body}]`：前端从当前卡片集构建的 title/body 结构化摘要（最近 8 条、单条 body 截 120 字、总量截 1800 字符），缺省 / 空时行为与旧版完全等价（向后兼容）。
- 服务端经 `core.insights.run_analysis(existing_insights=...)` 渲染为 user message 中的「已产出的洞察卡片」块（同样有 8 条 / 2000 字符双层截断），并约束模型：同主题不重复建卡（除非有明确增量发现）。
- 定位：**只读累进**——仅影响提示词输入，不改变单卡输出契约、写入模型与持久化契约（append + 前端全量覆盖语义不变）。

### 洞察板 API（Phase 2 · 已实现，契约见 core/insight_board.py）

- **GET /api/insights/board/{task_id}** → `{board: InsightBoard|null}`；无板/坏板（JSON 损坏或 schema 不合）均返回 null，前端降级到卡片视图。
- **POST /api/insights/board/analyze/task/{task_id}** → `{ok, board, changed, errors}`。服务端单一写入（与卡片管线同模型，前端只读重拉）：读任务全文最近 K 句（`OMS_BOARD_ANALYSIS_K` 默认 60）+ 当前板摘要，LLM 输出 zone patch ops（`upsert_zone`/`replace_cells`/`settle_zone`）；**ops 全部合法才应用并落盘** `data/tasks/<task_id>.board.json`（revision +1），任一非法整次丢弃（ok=false、板保持上一版本，返 200 不阻断展示）；无板时先建骨架板（revision 0，占位 flow 主视觉）。
- 错误：404 任务不存在；400 未完成/内容不足；**409 `board_in_flight`**（同任务修订进行中）；**504 `board_timeout`**（超时守护 `OMS_BOARD_ANALYSIS_TIMEOUT` 默认 **180s**——本地推理实测 50s+，不沿用卡片 60s 预算），超时不写盘。
- 卡片管线（insights.json）与板管线（board.json）**并行共存、互不写入**；zone.origin 回指卡片消息 id 作收敛溯源锚点。

### POST /api/insights/analyze/task/{task_id}（会后补分析）

- 无请求体。服务端从任务读取完整 `dialogue` 与 `chapters`，取时间序最近 `POST_ANALYSIS_MAX_LINES`（默认 40，环境变量 `OMS_INSIGHTS_POST_K` 可配）句构造分析输入，复用 `core.insights.run_analysis`（含角色 prompt 与 model_tier 防幻觉守卫，与无状态 `/api/insights/analyze` 对等）。
- 错误：404 任务不存在；400 `task_not_completed`（非 completed）/ `insufficient_content`（无转写或无章节）；**409 `analysis_in_flight`**（同任务已有分析在跑，不排队不并行；只防同时不防先后，多次成功分析追加多批消息属预期）；**504 `analysis_timeout`**（整体超时守护 `OMS_INSIGHTS_POST_TIMEOUT` 默认 60 秒，超时**不写盘**），`detail` 均为 `{error, message}` 结构；前端对 409/504 按提示文案处理不算失败。
- 响应：`{"result": {title, body, solution, has_finding, diagram, graph}, "messages": [...]}`。`has_finding=true` 时后端已**追加**写入 `data/tasks/<task_id>.insights.json`（原子写），新消息带 `phase: "post_meeting"`、`source: "system"`、`actions: []`；前端以响应 `messages` 整体替换本地列表（重拉语义），不经 `POST /api/insights/messages` 全量覆盖，规避交叉竞态。
- 无发现 / LLM 失败：返回安全默认值（`has_finding=false`），不写盘，`messages` 为存量列表。

### 洞察消息 `phase` 字段（向后兼容增量）

- `InsightMessage.phase?: "meeting" | "post_meeting"`；存量文件缺字段一律按 `"meeting"` 读取，前端卡片对 `post_meeting` 显示「会后」徽标。
- AI 会话上下文注入：chat qa/stream 两路径经 `core.chat_context.build_insights_context_block(task_id)` 注入「会议洞察台」块（最多 5 条 / 整块 1200 字符，diagram 源码不整段注入）；CLI 引擎工作区另导出 `context/insights.md`（全量）。

## 15. 划词映射回溯修正 API（REQ-SELECTION-CORRETO · 已实现）

### POST /api/tasks/{task_id}/correct-text

- 请求体：`{"old": "误识别写法", "new": "正确文本"}`（两侧均 `strip()`）。
- 语义：把一条 `错误识别→正确文本` 映射**全量回溯**应用到本场会议的**四份产物**——任务对象（转写原文 / 纪要 / 随记 / 章节 / 决策）、`<task_id>.insights.json`、`<task_id>.board.html`、`output_path` 指向的导出纪要 md。
- 匹配口径与转写链路**同源**（复用 `core.hotwords.sub_term` 与 `ascii_term_pattern`）：纯 ASCII 词按**ASCII 邻接边界**匹配（`(?<![A-Za-z0-9])词(?![A-Za-z0-9])`，大小写不敏感），含中文串走子串替换。
  不用 `\b`：Python Unicode 语义下汉字也算 `\w`，「与ES（」里汉字与字母之间不存在 `\b`，中文会议里最常见的「英文编码紧贴汉字」形态会全部匹配不上（ES→EAS 配了不生效）；而邻接边界既不误伤 `FILES` / `ESB` / `CH2O`。
- 改写范围按 **键名白名单** `core.text_correction.REWRITE_KEYS` 递归判定（非按路径枚举）：新增名为 `text` 的字段自动被覆盖，而 `task_id` / `audio_path` / `*_at` / `speaker_mapping` 等标识与路径永不触碰。
- 响应：`{ok, old, new, replaced, hits: {task, insights, board, export_md}, fields: {键名: 命中数}, residual, warnings}`。
  - `replaced` 为四份产物总命中数；**0 也是 200**（映射已存、本场会议恰好无该词），前端据此区分「已修正 N 处」与「未出现，无需修正」，不再无条件报成功。
  - `residual` 是白名单漏项告警：对全量产物再扫一次，`> 0` 即说明有新内容字段未进 `REWRITE_KEYS`（或受保护字段确实含词），路由层落 WARNING，不静默。
  - `warnings` 收集旁路文件读写失败；旁路失败不回滚任务主体（已命中即已生效），仅降级为提示。
- 落盘：任务主体仅在 `hits.task > 0` 时 `save_task_to_disk` 并刷新 `last_modified_at`（驱动知识库同步脏检测）；洞察板走 `board_html_save`（保留清洗防线 + `revision+1`）；洞察 JSON / md 用 `atomic_write_json|text`。幂等：重复调用第二次 `replaced=0`。
- 错误：400 任一侧为空 / `old == new`；404 任务不存在；500 修正过程异常。
- 与热词映射文件的关系：`data/hotword_mappings.txt` 仍是**转写时刻**后处理的唯一来源（`apply_hotword_mappings`），本端点不读写该文件，只消费调用方传入的一对词。

## 16. 一页纸系数 API（REQ-ONE-PAGE · 第一刀：纪要正文 + 洞察卡集 · 已实现）

设计共识（2026-09-29 定稿）：AI 生成内容受人脑上下文预算约束；系数从属单个会议（不进全局设置），UI 形态为面板头角标；纪要、洞察**各自一页、互不相加**；预算作用于生成侧取舍与存储侧卡位，**不是事后截断**；超限内容降级不删除（进可读、退可略）。本刀不动：决策流解析、洞察板 HTML 产物、实时增量总结、AI 对话回复长度。

### 任务 JSON 新增字段 `one_page`

- 结构：`"one_page": {"summary": 1, "insights": 1}`；合法档位 `{0.5, 1, 1.5, 2}`（两键独立）。
- 兼容：旧任务无字段时读取侧一律按系数 1 处理，无需迁移；随 `data/tasks/<id>.json` 落盘。

### PATCH /api/tasks/{task_id} 请求扩展 `one_page`

- 语义：**部分更新**，仅覆盖显式提供的子键（Pydantic `model_fields_set`）；非法档位 422；子键为 `null` = 不变。
- 副作用分面：`summary` 改档**仅存值**（下次生成/重生成纪要时由提示词预算块生效，不自动重算、不耗 LLM 配额；不刷 `last_modified_at`，避免误触知识库重同步）。`insights` 改档在**同请求内**对 `<task_id>.insights.json` 执行预算重排并落盘（纯展示层搬家，零 LLM）；重排失败不阻断 PATCH（下次保存/分析路径重新收口）。
- 响应返完整 task（含合并后的 `one_page`），前端角标据此即时刷新并乐观同步 `taskStore.patchTaskLocal`。

### 纪要面：篇幅预算块（core/summarize.py）

- `build_page_budget_block(factor)` 在 system prompt 尾部追加（位于角色模板与 model_tier 防幻觉守卫之后，两条 prompt 路径同点位）：结论层总预算 ≈ factor×900 字；主要结论 ≤ 5×factor（四舍五入，最少 1）；待办 ≤ 4×factor；概要 ≤ 3 句（0.5 档 1 句）；0.5 档「议题归类」不独立成节并入概要。
- 删除规则（写入 prompt）：先裁过程性描述，再裁低优先级条目；被裁内容不得转移至其他章节；内容少于预算时如实输出不注水。
- 链路：`generate_summary(..., one_page_factor)` ← `run_pipeline_stage2(..., one_page_factor)` ← `pipeline_runner` 读 `task.one_page.summary`（缺省 1）；`retry-summary` / `regenerate-summary` 经同一 stage2 链路自动携带。

### 洞察面：卡位预算（core/insight_budget.py）

- 换算表（与前端 `utils/pageBudget.ts` 一致）：系数→有效卡位 0.5→1 / 1→2 / 1.5→3 / 2→4；图卡（diagram 非空）上限 = ceil(卡位/2)，即 1 页 = 2 张时图 ≤1。
- 存储侧 `apply_budget(messages, factor)`（纯函数、返回浅拷贝新列表）：acknowledged 卡永不降级且优先占位（确认卡超容时有效层超容不强降，仅记 WARNING）；其余卡从新到旧回填卡位；未入选卡打 `deferred: true`，入选卡显式写 `deferred: false`。
- 守门收口点（均写盘前执行）：`POST /api/insights/messages/{task_id}`（会中全量覆盖保存）与 `POST /api/insights/analyze/task/{task_id}`（会后补分析追加）；另 PATCH 改档时重排（见上）。
- 生成侧：`run_analysis(..., card_budget={slots, active})` 非空时追加卡位短块（本轮至多新增 1 张、禁同义新开、满位默认 has_finding=false）；`InsightAnalysisRequest` 新增可选 `card_slots: int`（会中前端从 task 读取后携带；缺省不注入，旧客户端兼容）。
- `POST /api/insights/messages/{task_id}` 响应新增 `messages`（重排后全量列表，含 deferred 标记）；前端 `persistMessages` 以重拉语义替换本地，避免陈旧内存下次整体覆盖。

### AI 引用口径对齐（三处读取过滤 deferred）

- `core/chat_context.build_insights_context_block`（chat qa/stream 两路径共用）与 `core/cli_engine/context_export._render_insights` 仅注入未降级卡片，使 AI 引用集合与用户可见有效卡一致；现有「最近 N 条/字符截断」保留为第二道保险。
- 前端可见层：`RecInsightsPanel` 主卡流只渲染非 deferred 卡；deferred 卡归入底部默认收起的「历史观察」折叠组（标题+时间单行呈现）；未读计数/横幅仅统计有效层。
- 旧任务无 `deferred` 字段时前端/后端一律按未降级处理（`m.get("deferred")` 真值判定）。

---

## 17. 转写三层分层契约（PLAN-TRANSCRIPT-LAYERING · WP-1 口语清理层，已实现）

三层语义：**原文**（`text`/`dialogue`，永不改写，引用/追责锚点）｜**清理版**（`clean_text`，本地确定性规则派生：语气词、叠词、标点规整，默认开）｜**书面版**（AI 仅会后生成，WP-2；WP-1 前端仅锁定/未生成占位，无任何端点）。清理规则与红线见 `core/transcript_cleanup.py`（否定/自我纠正/句尾情态不动，幂等）。

### 17.1 设置 `transcript` 块（`data/settings.json`）

`GET /api/settings` 响应与 `POST /api/settings` 请求均含顶层：

```json
{ "transcript": { "cleanup": { "enabled": true }, "formal": { "auto_generate": false } } }
```

- `cleanup.enabled`（缺省 `true`）：口语清理总开关。POST 为**部分合并**，只传 `{"transcript":{"cleanup":{"enabled":false}}}` 即只改此键。
- `formal.auto_generate`（缺省 `false`）：WP-2 预留，WP-1 无消费方。
- 进行中的录制在启动时取**会话级快照**；录制途中改开关只影响新会话与历史回放富化，不回改已推消息（预期行为）。

### 17.2 WebSocket `/ws/transcript/{task_id}` 消息扩展

- `sentence`（定稿）：`text` 永远为原文；当前会话快照开启清理且规则命中时**附加** `clean_text`（清理后文本）与 `clean_ops`（命中明细）。清理结果为空（纯语气词句）时不附加，且该句只上屏、不喂下游。
- `history`（回放）：缓存只存原文，发送前按**当前**设置派生；命中时同样附加 `clean_text`/`clean_ops`，开关关则与旧客户端消息完全一致。
- `clean_ops` 为数组，元素 `{r, n, items?}`：

  | `r` | 含义 | `n` | `items` |
  | --- | --- | --- | --- |
  | `filler` | 删除语气词 | 删除次数 | 被删词列表 |
  | `dup` | 合并叠词/重复片段 | 合并次数 | 被合并片段列表 |
  | `punct` | 标点规整（含句首悬挂标点剥离） | 规整次数 | 无 |

  清理结果与原文相同（幂等无变更）时整个句子不带 clean 字段。

### 17.3 `GET /api/tasks/{task_id}` 响应级富化

- 顶层附加信封 `transcript_layers: {"cleanup": bool}`（当前设置快照）。
- `cleanup=true` 时返回的 `dialogue` 为**响应级深拷贝**，每个 `sentences[]` 命中清理则附加 `clean_text`/`clean_ops`（规则同上）；`cleanup=false` 时 dialogue 原样返回。
- **绝不写回**内存 task 与磁盘：热词回溯修正原文后下次读取自动重算，存量会议零迁移。

### 17.4 下游消费口径（清理版进下游，导出/缓存留原文）

- 吃清理版：会中实时摘要、实时章节、实时翻译的 feed（`feed_text`，空串句跳过）；会后纪要/标题/章节生成（`pipeline.stage2` 深拷贝 `consumer_dialogue`）、章节补生成 `_backfill_chapters`。
- 吃原文：md/docx 导出、`realtime_full_transcripts` 缓存（会中 AI 对话上下文事实源）、`save_summary` 落盘的 `dialogue`。
- 书面版（WP-2）不提供单句采纳写回；WP-1 无书面版读写端点。

## 17.5 转写三层分层契约（PLAN-TRANSCRIPT-LAYERING · WP-2 AI 书面版，已实现）

书面版是**会后**对整场转写逐句 AI 书面化的独立产物，落 sidecar 文件 `data/tasks/{task_id}.formal.json`，**绝不写回** `task.dialogue`。没有单句采纳/回写端点；md/docx 导出仍只吃原文。实现见 `core/transcript_formal.py`。

### 端点

**`POST /api/tasks/{task_id}/formalize`** — 触发书面化（后台任务，立即返回）。

- 请求体（可空＝整场）：`{"sentence_ids": [12, 13]}`。`sentence_ids` 须为整数数组；空列表/非整数 → 422；长度截断 2000。WP-3 前端划词工具条对选区覆盖句发该字段；省略＝整场。
- 闸门：任务不存在 → 404；任务未完成（会中）→ 409；算力路由复用 `get_routing_decision("llm")` 判定，不新增静默付费：trial 未登录/额度尽、BYOK 缺 key 且云端不可用、本机端点配置错/不支持等 → 409。
- 409 响应体：`{"detail": {"code": str, "reason": str}}`，`reason` 机器可读（如 `formalize_requires_postmeeting`、`formalize_already_running`、`formalize_route_unavailable`、`formalize_no_sentences`，路由原因另带底层 reason）。
- 成功：`200 {"status": "running", "scope": "full" | "selection"}`，生成在 BackgroundTasks 中执行；同一任务并发第二发 → 409 `formalize_already_running`。
- 整场重生成以当前 dialogue 重算签名并整文件替换；选区按 `sentence_id` upsert（仅当源签名未变时以旧 items 为基底）。

**`GET /api/tasks/{task_id}/formal`** — 读取书面版 sidecar。

- 从未生成 → 404。sidecar 文件损坏 → 200 返回 `status:"error"`、`error:"formal_sidecar_corrupt"` 占位。
- `status:"done"` 时实时重算源签名比对；原文被热词回溯修正等改写后返回 `status:"stale"`（stale 为读取派生态，不落盘），items 仍随响应返回供对照。

### sidecar 结构

```json
{
  "version": 1,
  "status": "running|done|error",
  "scope": "full|selection",
  "auto": false,
  "source_sig": { "count": 218, "hash": "sha1(...)" },
  "model": "qwen-plus",
  "source": "trial|byok|local_endpoint",
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 },
  "created_at": "2025-07-02T10:00:00",
  "finished_at": "",
  "error": "",
  "progress": { "done": 50, "total": 218 },
  "items": [ { "sentence_id": 0, "text": "…", "tone_flag": "weakened" } ]
}
```

- 源签名：对扁平句序列 `sentence_id|begin_ms|text\n` 求 sha1；`count` 为句数。锚点是 `sentence_id`（批转写/本地转写的扁平句下标，merge_fragments 后保留）。
- `items[].tone_flag` 为 `"weakened"` 或 `null`：模型不确定是否弱化了勉强/反转语气时也必须置标；前端对该句强制展示「⚠ 语气存疑」警示并支持逐句对照原文。
- 生成按 25 句/块调用同步 `chat_completion_full`（`core/llm.py`，temperature 0.2），每块严格校验返回 JSON 数组的 id 集合/数量/顺序；一块重试 1 次仍失败则整场置 `error`，items 回退基底不留半截；每块进度落盘。云端代理路径 usage 记 0（与异步通道同口径）。
- 前端 2s 轮询 GET；`running` 时 `progress.done/total` 驱动进度条。

### 自动钩子与设置

- `settings.transcript.formal.auto_generate=true`（缺省 false，§17.1 已登记）时，`pipeline.stage2` 落盘任务后由 daemon 线程触发整场书面化（`maybe_auto_formalize`）；任何异常仅记日志，不影响转写产物。
- 自动触发同样过路由闸门；不可用时静默跳过（无 sidecar），用户在面板手动点生成时才看到 409 原因。

### 选区书面化（WP-3 前端行为）

- 仅会后任务（`status:"completed"`）工具条按钮可用；会中/处理中划词按钮禁用（title 提示「会议完成后可用」），后端同有 409 兜底。
- 划词选区按 DOM Range 与 `.ts-line[data-sentence-id]` 的相交关系收集 `sentence_id`（去重、文档序排序）；纪要/备注/决策卡等 textarea 选区不出现该按钮。
- 触发后前端自动切到书面层 tab 并复用整场同一状态机（running 轮询 / done 留痕 / stale / error）；done 态仅选区覆盖句显示书面句与对照块，其余行回退显示清理版/原文（`formalMap` 未命中即回退，不产生占位文本）。
- 选区结果与整场共用同一 sidecar：选区按 sid upsert 累积；整场重新生成整文件替换。
