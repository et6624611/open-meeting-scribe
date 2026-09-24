---
title: 外部接口契约
description: DashScope / 通义千问 API 技术细节的唯一事实源
author: Yongliang Wang
created_at: 2026-09-03
updated_at: 2026-09-24
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

> 状态：**前端已按本节实现**（分支 `fix/qa-r1-def04-def02-frontend-20260924`）；后端由 `a4cdbd0ca795` 同批实现，合入前须双方核对确认。依据：`docs/QA-R1-DEFECTS-DISPATCH.md` §2 DEF-QA-R1-04 / DEF-QA-R1-02。

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

## 12. 决策中心 API（REQ-DECISION-CENTER B1 · DC-DEC-F1 前端派工依据）

> 依据 `docs/REQUIREMENT-DECISION-CENTER.md` v0.2.0 §R1/§R2。后端分支 `feat/req-decision-center-b1`，合入前本节即为前端契约事实源。

### 12.0 decision 数据对象（`task["decisions"]` 数组元素）

```json
{
  "id": "uuid4 字符串，任务内唯一",
  "text": "决策内容（转述文本，不含 [待确认] 前缀）",
  "status": "active | superseded | revoked",
  "pending_confirmation": false,
  "source": "auto | backfill | manual | injection",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601",
  "superseded_by": { "task_id": "…", "decision_id": "…" },
  "related_todo_ids": ["同会议 todo id"]
}
```

- 旧任务 JSON 无 `decisions` 字段 ⇒ 所有读写路径按 `[]` 处理，不报错。
- 重新生成纪要仅替换 `source=auto` 条目；`manual` / `injection` / `backfill` 保留。
- `superseded_by` 可为 `null`；来源会议被删除后引用悬空时读取不报错，前端按「引用已失效」降级显示。
- `related_todo_ids` v1 由前端/手动维护，自动抽取恒为 `[]`。
- `source=auto` 抽取源（RF-1 起）：纪要「主要结论」与「决策」两章节的条目按出现顺序合并去重；两节的阴性说明（"本次会议未形成明确结论/决策"）均视为正常空结果。

### 12.1 任务级 CRUD

| 方法与路径 | 请求体 | 响应 | 错误 |
|---|---|---|---|
| `GET /api/tasks/{task_id}/decisions` | — | `{"decisions": [decision…]}` | 404 任务不存在 |
| `POST /api/tasks/{task_id}/decisions` | `{text: str(1..2000), pending_confirmation?: bool=false, related_todo_ids?: str[]=}` | `{"decision": decision}`（`source=manual`、`status=active`） | 404 任务不存在；422 校验失败 |
| `PUT /api/tasks/{task_id}/decisions/{decision_id}` | `{text?, status?: "active"\|"superseded"\|"revoked", pending_confirmation?, related_todo_ids?}`（均可选，仅更新携带字段） | `{"decision": decision}` | 404 任务/决策不存在；422 |
| `DELETE /api/tasks/{task_id}/decisions/{decision_id}` | — | `{"ok": true}` | 404 任务/决策不存在 |
| `PATCH /api/tasks/{task_id}/decisions/{decision_id}/supersede` | `{task_id: str, decision_id: str}`（取代方定位，可跨任务） | `{"decision": decision}`（被标记项 `status=superseded`、`superseded_by` 已写入） | 404 任务不存在；404 决策不存在；404 取代方 task/decision 不存在；422 |

写操作（POST/PUT/DELETE/supersede）一律触发 `_mark_modified` + `save_task_to_disk`（知识库脏检测链路，PRD AC-10）。

### 12.2 聊天注入联动

`POST /api/tasks/{task_id}/inject` 当 `type="decision"` 时，除注入记录外同步向 `task["decisions"]` 追加一项：`id` 与注入记录同值、`source="injection"`、`text=content`。删除该注入记录（`DELETE /api/tasks/{task_id}/injections/{injection_id}`）时级联删除对应决策项（与 todo 注入行为一致）。

### 12.3 跨任务聚合 `GET /api/decisions`

查询参数（全部可选，可叠加）：

| 参数 | 语义 |
|---|---|
| `since` / `until` | 按会议日期过滤，`YYYY-MM-DD`，闭区间；任务无 `meeting_date` 时在给定日期过滤下被排除 |
| `kb_id` | 按所属知识库（= `project_id`）过滤；未关联知识库的任务被排除 |
| `status` | `active`\|`superseded`\|`revoked` 精确过滤；非法值 422 |
| `q` | `text` 子串匹配（区分大小写） |
| `group_by` | `meeting`\|`date`；缺省返回平铺列表 |

响应：

```jsonc
// 缺省（平铺）
{ "decisions": [ { …decision全部字段, "task_id": "…", "title": "会议标题",
                 "meeting_date": "YYYY-MM-DD|null", "kb_id": "…|null", "kb_name": "…|null" } ] }
// group_by=meeting → 按会议分组；group_by=date → 按会议日期分组
{ "groups": [ { "key": "task_id 或 meeting_date", "label": "会议标题或日期",
               "task_id": "…(仅 group_by=meeting)", "meeting_date": "…",
               "decisions": [ 同平铺元素 ] } ] }
```

- 平铺与组内均按 `meeting_date` 倒序（无日期沉底）。
- 决策中心「默认仅看生效中」由前端传 `status=active` 实现，后端不默认过滤。
- 数据源为后端内存任务表（桌面单机量级），无分页契约；`total` 字段随列表长度给出。
