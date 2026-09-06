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

**WebSocket 地址**：`wss://dashscope.aliyuncs.com/api-ws/v1/inference`

**调用方式**（DashScope Python SDK）：
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
- 两者共用同一个 `DASHSCOPE_API_KEY`
