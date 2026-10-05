"""
asr-proxy/ws_relay.py — WebSocket 实时流式转写中继

职责：
  客户端通过 WebSocket 送入 PCM 音频帧，代理转发给 DashScope 并回传识别结果。
  认证通过查询参数 timestamp + sign 传递 HMAC 签名。

客户端消息：
  - {"type": "start"} — 开始识别（可选，连接后自动开始）
  - 二进制帧 — PCM 音频数据
  - {"type": "stop"} — 停止识别

代理消息：
  - {"type": "partial", "text": "..."} — 临时结果
  - {"type": "sentence", "text": "...", "begin_time": 0, "end_time": 0} — 定稿句子
  - {"type": "error", "message": "..."} — 错误
  - {"type": "complete"} — 识别完成
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# 延迟导入的模块级引用（避免循环导入，由 create_router 时注入）
_server_mod = None


def create_router(server_module) -> APIRouter:
    """
    创建 WebSocket 路由。

    Args:
        server_module: server 模块引用（提供 DASHSCOPE_API_KEY、DASHSCOPE_WS_URL、verify_signature）
    """
    global _server_mod
    _server_mod = server_module

    router = APIRouter()

    @router.websocket("/asr/ws")
    async def asr_websocket(
        websocket: WebSocket,
        timestamp: str = "",
        sign: str = "",
        model: str = "qwen-audio-3.0-asr-flash-streaming",
        sample_rate: int = 16000,
        language_hints: str = "zh,en",
        vocabulary_id: str = "",
    ):
        await _handle_ws_connection(
            websocket, timestamp, sign, model,
            sample_rate, language_hints, vocabulary_id,
        )

    return router


async def _handle_ws_connection(
    websocket: WebSocket,
    timestamp: str,
    sign: str,
    model: str,
    sample_rate: int,
    language_hints: str,
    vocabulary_id: str,
):
    """WebSocket 连接处理主函数"""
    DASHSCOPE_API_KEY = _server_mod.DASHSCOPE_API_KEY
    DASHSCOPE_WS_URL = _server_mod.DASHSCOPE_WS_URL
    verify_signature = _server_mod.verify_signature

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
        from dashscope.audio.asr import Recognition, RecognitionCallback

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
