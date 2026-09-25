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
  "title": "决策短标题（三要素之一，可为空串）",
  "text": "决策内容（转述文本，不含 [待确认] 前缀）",
  "owner_id": "执行人说话人档案 uuid，未指派为 null",
  "owner_name": "执行人展示名（读侧以档案为权威解析，档案缺失时回退写入快照）",
  "status": "active | superseded | revoked",
  "pending_confirmation": false,
  "source": "auto | backfill | manual | injection",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601",
  "superseded_by": { "task_id": "…", "decision_id": "…" },
  "related_todo_ids": ["同会议 todo id"]
}
```

- **三要素化（DC-R2-b，项目方裁决 D4/D5）**：`title` / `text`（内容）/ `owner`（执行人）；执行人以说话人档案为权威存 `owner_id`，因此档案改名全局跟随无需批量重写任务 JSON；`owner_name` 仅作展示快照与兜底。
- **存量兼容**：旧数据无 `title` / `owner_id` / `owner_name` 三键 ⇒ 读侧按 `""` / `null` 给出（不报错），展示层按「内容首行」降级为行首文本；存量任务文件**不做批量改写**。
- **auto 决策不指派执行人**（D5：AI 只要求标题+正文），抽取源为纪要「主要结论」/「决策」章节的 `**短标题**：正文` 条目式写法；不符合该写法的条目 `title` 为空串，`text` 保留整句（不丢条目）。
- 旧任务 JSON 无 `decisions` 字段 ⇒ 所有读写路径按 `[]` 处理，不报错。
- 重新生成纪要仅替换 `source=auto` 条目；`manual` / `injection` / `backfill` 保留。
- `superseded_by` 可为 `null`；来源会议被删除后引用悬空时读取不报错，前端按「引用已失效」降级显示。
- `related_todo_ids` v1 由前端/手动维护，自动抽取恒为 `[]`。
- `source=auto` 抽取源（RF-1 起）：纪要「主要结论」与「决策」两章节的条目按出现顺序合并去重；两节的阴性说明（"本次会议未形成明确结论/决策"）均视为正常空结果。

### 12.1 任务级 CRUD

| 方法与路径 | 请求体 | 响应 | 错误 |
|---|---|---|---|
| `GET /api/tasks/{task_id}/decisions` | — | `{"decisions": [decision…]}` | 404 任务不存在 |
| `POST /api/tasks/{task_id}/decisions` | `{text: str(1..2000), title?: str(0..200)="", owner_id?: str|""=null, owner_name?: str|""=null, pending_confirmation?: bool=false, related_todo_ids?: str[]=}` | `{"decision": decision}`（`source=manual`、`status=active`） | 404 任务不存在；422 校验失败 |
| `PUT /api/tasks/{task_id}/decisions/{decision_id}` | `{text?, title?, owner_id?, owner_name?, status?: "active"\|"superseded"\|"revoked", pending_confirmation?, related_todo_ids?}`（均可选，仅更新携带字段） | `{"decision": decision}` | 404 任务/决策不存在；422 |
| `DELETE /api/tasks/{task_id}/decisions/{decision_id}` | — | `{"ok": true}` | 404 任务/决策不存在 |
| `PATCH /api/tasks/{task_id}/decisions/{decision_id}/supersede` | `{task_id: str, decision_id: str}`（取代方定位，可跨任务） | `{"decision": decision}`（被标记项 `status=superseded`、`superseded_by` 已写入） | 404 任务不存在；404 决策不存在；404 取代方 task/decision 不存在；422 |

写操作（POST/PUT/DELETE/supersede）一律触发 `_mark_modified` + `save_task_to_disk`（知识库脏检测链路，PRD AC-10）。

**owner 字段写入口径（DC-R2-b）**：
- `owner_id` 能在说话人档案中解析且档案名非占位串 ⇒ `owner_name` 以**档案名为准**（覆盖传入快照）。
- 档案不存在/已删除 ⇒ 宽容回退传入的 `owner_name` 快照（**不报 422**，建档与提交之间的并发删除不应阻断补录）。
- PUT 下 `owner_id` / `owner_name` 的 **空串 = 清空指派**，**未传 = 保持原指派**（前端清空时显式下发空串）。

### 12.2 聊天注入联动

`POST /api/tasks/{task_id}/inject` 当 `type="decision"` 时，除注入记录外同步向 `task["decisions"]` 追加一项：`id` 与注入记录同值、`source="injection"`、`text=content`。删除该注入记录（`DELETE /api/tasks/{task_id}/injections/{injection_id}`）时级联删除对应决策项（与 todo 注入行为一致）。

### 12.3 跨任务聚合 `GET /api/decisions`

查询参数（全部可选，可叠加）：

| 参数 | 语义 |
|---|---|
| `since` / `until` | 按会议日期过滤，`YYYY-MM-DD`，闭区间；任务无 `meeting_date` 时在给定日期过滤下被排除 |
| `kb_id` | 按所属知识库（= `project_id`）过滤；未关联知识库的任务被排除 |
| `status` | `active`\|`superseded`\|`revoked` 精确过滤；非法值 422 |
| `q` | `text` 与 `title` 子串匹配（区分大小写，DC-R2-b 扩展至标题） |
| `group_by` | `meeting`\|`date`；缺省返回平铺列表 |

响应：

```jsonc
// 缺省（平铺）
{ "decisions": [ { …decision全部字段, "title": "决策自身标题（存量无键时为 ""）",
                 "owner_name": "执行人展示名（读侧解析）",
                 "task_id": "…", "meeting_title": "来源会议标题",
                 "meeting_date": "YYYY-MM-DD|null", "kb_id": "…|null", "kb_name": "…|null" } ] }
// group_by=meeting → 按会议分组；group_by=date → 按会议日期分组
{ "groups": [ { "key": "task_id 或 meeting_date", "label": "会议标题或日期",
               "task_id": "…(仅 group_by=meeting)", "meeting_date": "…",
               "decisions": [ 同平铺元素 ] } ] }
```

- **键位修正（DC-R2-b）**：行内 `title` 从「会议标题」改为「决策自身标题」，来源会议标题另下发 `meeting_title`（无会议标题时回退 `audio_name` 再回退 `task_id`）；`group_by=meeting` 的 `label` 取 `meeting_title`。前端分组头与跳转链路必须读 `meeting_title`。

- 平铺与组内均按 `meeting_date` 倒序（无日期沉底）。
- 决策中心「默认仅看生效中」由前端传 `status=active` 实现，后端不默认过滤。
- 数据源为后端内存任务表（桌面单机量级），无分页契约；`total` 字段随列表长度给出。

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

### 13.4 `POST /api/settings` 请求扩展

- 可选 `access_mode`：`"local"|"hosted"|"byok"|null`。非法值忽略并记日志（与 engine.mode 白名单口径一致）。写入时后端同步旧字段：local→`engine.mode=local`；hosted→`engine.mode=proxy`+`asr.mode=proxy`；byok→`engine.mode=direct`+`asr.mode=direct`（A2 回滚窗口）。
- 可选 `expert_mode`：仅接受布尔。
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
