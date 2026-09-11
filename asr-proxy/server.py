"""
ASR 代理服务 — 持有 DashScope API Key，为客户端提供语音转写中转

部署位置：云端服务器（通过环境变量配置）
职责：
  1. 接收客户端音频文件，上传到 DashScope 临时存储
  2. 提交批处理转写任务 + 内部轮询 + 返回完整结果
  3. WebSocket 中继实时流式转写

安全机制：
  - HTTP 请求须携带 X-ASR-Timestamp 和 X-ASR-Sign 头
  - WebSocket 连接须携带 timestamp + sign 查询参数
  - 签名 = HMAC-SHA256(token, timestamp)，token 为共享密钥
  - timestamp 超过 TTL（默认 5 分钟）视为过期拒绝
"""

import os
import time
import hmac
import hashlib
import json
import logging
import asyncio
import threading
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

# ============================================================
# 日志
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

ASR_PROXY_TOKEN = os.getenv("ASR_PROXY_TOKEN", "")
ASR_SIGN_TTL = int(os.getenv("ASR_SIGN_TTL", "300"))
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com"
DASHSCOPE_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"

POLL_INTERVAL = 3
POLL_TIMEOUT = 600

# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(title="ASR Proxy", version="1.0.0")


# ============================================================
# 签名校验
# ============================================================

def verify_signature(timestamp: str, sign: str) -> bool:
    if not ASR_PROXY_TOKEN:
        logger.error("ASR_PROXY_TOKEN 未配置")
        return False
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False
    now = int(time.time())
    if abs(now - ts) > ASR_SIGN_TTL:
        logger.warning(f"签名过期: timestamp={timestamp}, now={now}, ttl={ASR_SIGN_TTL}")
        return False
    expected = hmac.new(
        ASR_PROXY_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(sign, expected)


def check_auth(request: Request) -> None:
    timestamp = request.headers.get("X-ASR-Timestamp", "")
    sign = request.headers.get("X-ASR-Sign", "")
    if not timestamp or not sign:
        raise HTTPException(401, "缺少签名头 X-ASR-Timestamp / X-ASR-Sign")
    if not verify_signature(timestamp, sign):
        raise HTTPException(401, "签名校验失败")


def check_auth_ws(timestamp: str, sign: str) -> None:
    if not verify_signature(timestamp, sign):
        raise HTTPException(401, "WebSocket 签名校验失败")


# ============================================================
# DashScope 辅助函数
# ============================================================

def _dashscope_headers() -> dict:
    return {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }


def upload_to_dashscope(file_content: bytes, filename: str, model: str = "paraformer-v2") -> str:
    """上传文件到 DashScope 临时存储，返回 oss:// URL"""
    policy_url = f"{DASHSCOPE_BASE}/api/v1/uploads"
    params = {"action": "getPolicy", "model": model}
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}

    resp = requests.get(policy_url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    policy_data = resp.json()
    if "data" not in policy_data:
        raise RuntimeError(f"获取上传凭证失败: {policy_data}")

    policy = policy_data["data"]
    upload_host = policy["upload_host"]
    upload_dir = policy["upload_dir"]
    oss_key = f"{upload_dir}/{filename}"

    form_data = {
        "key": oss_key,
        "OSSAccessKeyId": policy["oss_access_key_id"],
        "policy": policy["policy"],
        "Signature": policy["signature"],
        "x-oss-object-acl": policy["x_oss_object_acl"],
        "x-oss-forbid-overwrite": policy["x_oss_forbid_overwrite"],
        "success_action_status": "200",
    }

    resp = requests.post(
        upload_host,
        data=form_data,
        files={"file": (filename, file_content)},
        timeout=600,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"上传失败: HTTP {resp.status_code} — {resp.text}")

    oss_url = f"oss://{oss_key}"
    logger.info(f"上传成功: {oss_url} ({len(file_content) / 1024 / 1024:.1f} MB)")
    return oss_url


def submit_transcription_task(
    file_url: str,
    model: str = "paraformer-v2",
    diarization_enabled: bool = True,
    language_hints: list[str] | None = None,
    speaker_count: int | None = None,
    vocabulary_id: str | None = None,
    disfluency_removal_enabled: bool = False,
) -> str:
    """提交转写任务，返回 task_id"""
    url = f"{DASHSCOPE_BASE}/api/v1/services/audio/asr/transcription"
    headers = _dashscope_headers()
    headers["X-DashScope-Async"] = "enable"

    if file_url.startswith("oss://"):
        headers["X-DashScope-OssResourceResolve"] = "enable"

    parameters = {}
    if diarization_enabled:
        parameters["diarization_enabled"] = True
    if language_hints:
        parameters["language_hints"] = language_hints
    if speaker_count:
        parameters["speaker_count"] = speaker_count
    if vocabulary_id:
        parameters["vocabulary_id"] = vocabulary_id
    if disfluency_removal_enabled:
        parameters["disfluency_removal_enabled"] = True

    body = {
        "model": model,
        "input": {"file_urls": [file_url]},
        "parameters": parameters,
    }

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "output" not in data or "task_id" not in data["output"]:
        raise RuntimeError(f"提交任务失败: {data}")

    task_id = data["output"]["task_id"]
    logger.info(f"任务已提交: task_id={task_id}")
    return task_id


def poll_task_result(task_id: str) -> dict:
    """轮询任务状态直到完成，返回 output dict"""
    url = f"{DASHSCOPE_BASE}/api/v1/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}

    start_time = time.time()
    last_status = ""

    while True:
        elapsed = time.time() - start_time
        if elapsed > POLL_TIMEOUT:
            raise TimeoutError(f"任务超时（>{POLL_TIMEOUT}s）: task_id={task_id}")

        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        output = data.get("output", {})
        status = output.get("task_status", "UNKNOWN")

        if status != last_status:
            logger.info(f"任务状态: {status} ({elapsed:.0f}s)")
            last_status = status

        if status == "SUCCEEDED":
            return output
        elif status == "FAILED":
            error_msg = output.get("message", "未知错误")
            raise RuntimeError(f"转写任务失败: {error_msg}")

        time.sleep(POLL_INTERVAL)


def download_transcription(transcription_url: str) -> dict:
    """下载转写结果 JSON"""
    resp = requests.get(transcription_url, timeout=60)
    resp.raise_for_status()
    return resp.json()


# ============================================================
# 请求模型
# ============================================================

class TranscribeRequest(BaseModel):
    file_url: str = Field(..., description="音频 URL（oss:// 或公网 URL）")
    model: str = Field("paraformer-v2", description="模型名")
    diarization_enabled: bool = Field(True, description="是否开启说话人分离")
    language_hints: list[str] | None = Field(None, description="语言提示")
    speaker_count: int | None = Field(None, description="说话人数量")
    vocabulary_id: str | None = Field(None, description="热词表 ID")
    disfluency_removal_enabled: bool = Field(False, description="过滤语气词")


# ============================================================
# HTTP 端点
# ============================================================

@app.post("/asr/upload")
def asr_upload(request: Request, file: bytes = None):
    """
    接收音频文件，上传到 DashScope 临时存储，返回 oss:// URL。

    请求：multipart/form-data，字段 file
    响应：{"oss_url": "oss://..."}
    """
    check_auth(request)

    if not DASHSCOPE_API_KEY:
        raise HTTPException(500, "服务端未配置 DASHSCOPE_API_KEY")

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(400, "请使用 multipart/form-data 上传文件")

    import asyncio
    # FastAPI 的 sync 端点中读取 form data
    # 由于是 sync def，FastAPI 在线程池中运行
    # 我们需要从 request 中获取文件
    # 使用同步方式读取 body 并解析
    raise HTTPException(501, "请使用 /asr/transcribe 直接提交转写（内含上传）")


@app.post("/asr/transcribe")
async def asr_transcribe(request: Request):
    """
    一站式转写：接收音频文件 → 上传 → 提交转写 → 轮询 → 返回完整结果。

    请求：multipart/form-data
      - file: 音频文件
      - model: 模型名（可选，默认 paraformer-v2）
      - diarization_enabled: 是否开启说话人分离（可选，默认 true）
      - language_hints: 语言提示（可选，JSON 数组）
      - speaker_count: 说话人数量（可选）
      - vocabulary_id: 热词表 ID（可选）
      - disfluency_removal_enabled: 过滤语气词（可选）

    或者 JSON body：
      - file_url: 已有的 oss:// 或公网 URL
      - 其他参数同上

    响应：转写结果 JSON（含 transcripts[].sentences[]）
    """
    check_auth(request)

    if not DASHSCOPE_API_KEY:
        raise HTTPException(500, "服务端未配置 DASHSCOPE_API_KEY")

    content_type = request.headers.get("content-type", "")

    # 解析参数
    model = "paraformer-v2"
    diarization_enabled = True
    language_hints = None
    speaker_count = None
    vocabulary_id = None
    disfluency_removal_enabled = False
    file_url = None

    if "multipart/form-data" in content_type:
        form = await request.form()

        file_obj = form.get("file")
        if not file_obj:
            raise HTTPException(400, "缺少 file 字段")

        file_content = await file_obj.read()
        filename = file_obj.filename or "audio.wav"

        model = form.get("model", "paraformer-v2")
        diarization_enabled = form.get("diarization_enabled", "true").lower() == "true"
        if form.get("language_hints"):
            try:
                language_hints = json.loads(form["language_hints"])
            except (json.JSONDecodeError, TypeError):
                language_hints = None
        if form.get("speaker_count"):
            try:
                speaker_count = int(form["speaker_count"])
            except (ValueError, TypeError):
                pass
        vocabulary_id = form.get("vocabulary_id") or None
        if form.get("disfluency_removal_enabled"):
            disfluency_removal_enabled = form["disfluency_removal_enabled"].lower() == "true"

        logger.info(f"收到转写请求: {filename} ({len(file_content) / 1024 / 1024:.1f} MB), model={model}")

        # 上传到 DashScope
        try:
            file_url = await asyncio.get_event_loop().run_in_executor(
                None, upload_to_dashscope, file_content, filename, model
            )
        except Exception as e:
            logger.error(f"上传失败: {e}")
            raise HTTPException(500, f"音频上传失败: {e}")

    elif "application/json" in content_type:
        body = await request.json()
        file_url = body.get("file_url")
        if not file_url:
            raise HTTPException(400, "缺少 file_url 字段")
        model = body.get("model", "paraformer-v2")
        diarization_enabled = body.get("diarization_enabled", True)
        language_hints = body.get("language_hints")
        speaker_count = body.get("speaker_count")
        vocabulary_id = body.get("vocabulary_id")
        disfluency_removal_enabled = body.get("disfluency_removal_enabled", False)
    else:
        raise HTTPException(400, "请使用 multipart/form-data 或 application/json")

    # 提交转写 + 轮询 + 下载结果（在线程池中执行，避免阻塞事件循环）
    loop = asyncio.get_event_loop()

    try:
        task_id = await loop.run_in_executor(
            None,
            lambda: submit_transcription_task(
                file_url=file_url,
                model=model,
                diarization_enabled=diarization_enabled,
                language_hints=language_hints,
                speaker_count=speaker_count,
                vocabulary_id=vocabulary_id,
                disfluency_removal_enabled=disfluency_removal_enabled,
            ),
        )

        output = await loop.run_in_executor(None, poll_task_result, task_id)

        results = output.get("results", [])
        if not results:
            raise HTTPException(500, "转写结果为空")

        transcription_url = results[0].get("transcription_url")
        if not transcription_url:
            raise HTTPException(500, "未获取到 transcription_url")

        transcription = await loop.run_in_executor(None, download_transcription, transcription_url)

        return {
            "task_id": task_id,
            "file_url": file_url,
            "transcription": transcription,
        }

    except TimeoutError as e:
        logger.error(f"转写超时: {e}")
        raise HTTPException(504, str(e))
    except RuntimeError as e:
        logger.error(f"转写失败: {e}")
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"转写异常: {e}")
        raise HTTPException(500, f"转写服务异常: {e}")


@app.websocket("/asr/ws")
async def asr_websocket(
    websocket: WebSocket,
    timestamp: str = "",
    sign: str = "",
    model: str = "qwen-audio-3.0-asr-flash-streaming",
    sample_rate: int = 16000,
    language_hints: str = "zh,en",
    vocabulary_id: str = "",
):
    """
    实时流式转写 WebSocket 中继。

    客户端通过 WebSocket 送入 PCM 音频帧，代理转发给 DashScope 并回传识别结果。

    认证：通过查询参数 timestamp + sign 传递 HMAC 签名。

    客户端消息（JSON text）：
      - {"type": "start"} — 开始识别（可选，连接后自动开始）
      - 二进制帧 — PCM 音频数据
      - {"type": "stop"} — 停止识别

    代理消息（JSON text）：
      - {"type": "partial", "text": "..."} — 临时结果
      - {"type": "sentence", "text": "...", "begin_time": 0, "end_time": 0} — 定稿句子
      - {"type": "error", "message": "..."} — 错误
      - {"type": "complete"} — 识别完成
    """
    if not DASHSCOPE_API_KEY:
        await websocket.close(code=1011, reason="服务端未配置 DASHSCOPE_API_KEY")
        return

    # 校验签名
    if not verify_signature(timestamp, sign):
        await websocket.close(code=1008, reason="签名校验失败")
        return

    await websocket.accept()
    logger.info(f"[ASR WS] 客户端已连接, model={model}")

    # 在线程中运行 DashScope SDK（SDK 内部用线程管理 WebSocket）
    loop = asyncio.get_event_loop()
    recognition = None
    error_event = asyncio.Event()
    error_message = None

    def on_partial(text: str):
        """SDK 回调：临时结果 → 发送给客户端"""
        try:
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({"type": "partial", "text": text}),
                loop,
            )
        except Exception as e:
            logger.error(f"[ASR WS] 发送 partial 失败: {e}")

    def on_sentence_end(sentence: dict):
        """SDK 回调：定稿句子 → 发送给客户端"""
        try:
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({
                    "type": "sentence",
                    "text": sentence.get("text", ""),
                    "begin_time": sentence.get("begin_time", 0),
                    "end_time": sentence.get("end_time", 0),
                }),
                loop,
            )
        except Exception as e:
            logger.error(f"[ASR WS] 发送 sentence 失败: {e}")

    def on_error(msg: str):
        """SDK 回调：错误 → 发送给客户端"""
        nonlocal error_message
        error_message = msg
        try:
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({"type": "error", "message": msg}),
                loop,
            )
        except Exception:
            pass
        error_event.set()

    def on_complete():
        """SDK 回调：完成"""
        try:
            asyncio.run_coroutine_threadsafe(
                websocket.send_json({"type": "complete"}),
                loop,
            )
        except Exception:
            pass

    try:
        # 导入 DashScope SDK
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

        dashscope.base_websocket_api_url = DASHSCOPE_WS_URL
        dashscope.api_key = DASHSCOPE_API_KEY

        # 构建识别参数
        kwargs = {
            "model": model,
            "format": "pcm",
            "sample_rate": sample_rate,
            "language_hints": language_hints.split(",") if language_hints else ["zh", "en"],
            "semantic_punctuation_enabled": True,
            "disfluency_removal_enabled": False,
            "heartbeat": True,
        }
        if vocabulary_id:
            kwargs["vocabulary_id"] = vocabulary_id

        # 创建回调
        callback = RecognitionCallback()
        callback.on_event = lambda result: _handle_sdk_event(result, on_partial, on_sentence_end)
        callback.on_error = lambda result: on_error(f"实时转写错误: {result.message}")
        callback.on_complete = on_complete
        callback.on_open = lambda: None
        callback.on_close = lambda: None

        # 创建并启动识别器（callback 必须作为构造参数传入）
        recognition = Recognition(callback=callback, **kwargs)
        recognition.start()

        logger.info("[ASR WS] DashScope 识别器已启动")

        # 主循环：接收客户端消息
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"]:
                # 二进制帧 = PCM 音频数据
                if recognition:
                    try:
                        recognition.send_audio_frame(message["bytes"])
                    except Exception as e:
                        logger.error(f"[ASR WS] 送入音频失败: {e}")
                        await websocket.send_json({"type": "error", "message": f"送入音频失败: {e}"})
                        break

            elif "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "stop":
                        logger.info("[ASR WS] 收到停止信号")
                        if recognition:
                            recognition.stop()
                        await websocket.send_json({"type": "complete"})
                        break

                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        logger.info("[ASR WS] 客户端已断开")
    except Exception as e:
        logger.error(f"[ASR WS] 异常: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if recognition:
            try:
                recognition.stop()
            except Exception:
                pass
        logger.info("[ASR WS] 连接已清理")


def _handle_sdk_event(result, on_partial, on_sentence_end):
    """处理 DashScope SDK 事件"""
    from dashscope.audio.asr import RecognitionResult
    sentence = result.get_sentence()
    if not sentence or "text" not in sentence:
        return
    text = sentence["text"]
    is_end = RecognitionResult.is_sentence_end(sentence)
    if is_end:
        on_sentence_end({
            "text": text,
            "begin_time": sentence.get("begin_time", 0),
            "end_time": sentence.get("end_time", 0),
        })
    else:
        on_partial(text)


@app.get("/health")
def health():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "asr-proxy",
        "dashscope_configured": bool(DASHSCOPE_API_KEY),
    }


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn

    if not ASR_PROXY_TOKEN:
        logger.error("ASR_PROXY_TOKEN 未配置，服务拒绝启动")
        exit(1)

    if not DASHSCOPE_API_KEY:
        logger.error("DASHSCOPE_API_KEY 未配置")
        exit(1)

    logger.info("ASR 代理服务启动中...")
    uvicorn.run(app, host="0.0.0.0", port=8200)
