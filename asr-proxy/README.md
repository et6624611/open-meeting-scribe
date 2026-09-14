# ASR 代理服务

```
客户端 → ASR 代理 (<your-server-ip>:8200) → DashScope API
```

持有 DashScope API Key，为客户端提供语音转写中转服务。客户端不再存储任何 DashScope Key。

## 安全机制

- HTTP 请求须携带 `X-ASR-Timestamp` 和 `X-ASR-Sign` 头
- WebSocket 连接须携带 `timestamp` + `sign` 查询参数
- 签名 = HMAC-SHA256(token, timestamp)，token 为共享密钥
- timestamp 超过 TTL（默认 5 分钟）视为过期拒绝
- 常量时间比较，防时序攻击

## 端点

### POST /asr/transcribe

一站式转写：接收音频文件 → 上传到 DashScope → 提交转写 → 轮询 → 返回完整结果。

**请求头**：
- `X-ASR-Timestamp`: Unix 时间戳（秒）
- `X-ASR-Sign`: HMAC-SHA256 签名

**请求体**（multipart/form-data）：
- `file`: 音频文件
- `model`: 模型名（可选，默认 `paraformer-v2`）
- `diarization_enabled`: 是否开启说话人分离（可选，默认 `true`）
- `language_hints`: 语言提示（可选，JSON 数组如 `["zh","en"]`）
- `speaker_count`: 说话人数量（可选）
- `vocabulary_id`: 热词表 ID（可选）
- `disfluency_removal_enabled`: 过滤语气词（可选）

**或 JSON body**：
- `file_url`: 已有的 `oss://` 或公网 URL
- 其他参数同上

**响应**：
```json
{
  "task_id": "xxx",
  "file_url": "oss://...",
  "transcription": {
    "transcripts": [{
      "sentences": [
        {"text": "...", "begin_time": 0, "end_time": 1000, "speaker_id": 0}
      ]
    }]
  }
}
```

### WebSocket /asr/ws

实时流式转写中继。

**查询参数**：
- `timestamp`: Unix 时间戳（秒）
- `sign`: HMAC-SHA256 签名
- `model`: 模型名（默认 `qwen-audio-3.0-asr-flash-streaming`）
- `sample_rate`: 采样率（默认 16000）
- `language_hints`: 语言提示（逗号分隔，默认 `zh,en`）
- `vocabulary_id`: 热词表 ID（可选）

**客户端 → 代理**：
- 二进制帧：PCM 音频数据（16bit, 16kHz, 单声道）
- `{"type": "stop"}`：停止识别

**代理 → 客户端**：
- `{"type": "partial", "text": "..."}`：临时结果
- `{"type": "sentence", "text": "...", "begin_time": 0, "end_time": 0}`：定稿句子
- `{"type": "error", "message": "..."}`：错误
- `{"type": "complete"}`：识别完成

### GET /health

健康检查。

## 部署

```bash
# 在服务器上
cd /opt/asr-proxy
source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8200
```

或使用部署脚本：
```bash
ssh root@<your-server-ip> 'bash -s' < asr-proxy/deploy.sh
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `ASR_PROXY_TOKEN` | 共享密钥（与客户端一致） |
| `ASR_SIGN_TTL` | 签名有效期（秒），默认 300 |
| `DASHSCOPE_API_KEY` | 平台 DashScope API Key |
