"""
core/realtime_asr.py — 实时转写引擎（通过 ASR 代理 WebSocket 中继）

作者：王永亮
创建：2026-09-03
版本：2.0.0（代理模式）

职责：
  封装 ASR 代理的 WebSocket 流式转写，提供：
  1. 建立 WebSocket 连接到代理
  2. 接收 PCM 音频流并送入
  3. 通过回调收集实时句子（临时结果 + 定稿句子）

架构（详见 docs/adr/0012-ASR转写走云端代理.md）：
  - 客户端通过 WebSocket 连接代理，代理中继到 DashScope
  - 客户端不再直接连 DashScope WebSocket

限制：
  - 实时 API 不支持说话人分离（无 speaker_id）
  - 说话人分离仅在批管线（paraformer-v2）中生效
  - 实时转写定位为「预览」，最终纪要仍走批管线

硬约束（详见 docs/API_CONTRACTS.md）：
  - 音频格式：PCM 16bit / 16kHz / 单声道
  - 每包音频建议 ~100ms（3200 bytes = 3200 帧 × 2 bytes）
"""

import os
import time
import hmac
import hashlib
import asyncio
import logging
import threading
import json
from typing import Callable
from urllib.parse import urlencode

import websockets

from .hotwords import apply_hotword_mappings

logger = logging.getLogger(__name__)

# ── 代理配置 ──
ASR_PROXY_URL = os.getenv("ASR_PROXY_URL", "http://47.116.10.194:8200").rstrip("/")
ASR_PROXY_TOKEN = os.getenv("ASR_PROXY_TOKEN", "")

# 每包音频大小：3200 帧 × 2 bytes/帧 = 6400 bytes（100ms @16kHz/16bit）
AUDIO_FRAME_SIZE = 6400

# 实时转写模型
REALTIME_MODEL = "qwen-audio-3.0-asr-flash-streaming"


def _make_sign(timestamp: str) -> str:
    """生成请求签名"""
    if not ASR_PROXY_TOKEN:
        raise RuntimeError("未配置 ASR_PROXY_TOKEN，无法调用 ASR 代理")
    return hmac.new(
        ASR_PROXY_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()


def _get_ws_url(
    model: str = REALTIME_MODEL,
    sample_rate: int = 16000,
    language_hints: list[str] | None = None,
    vocabulary_id: str | None = None,
) -> str:
    """构造代理 WebSocket URL（含签名查询参数）"""
    # 将 http:// 转为 ws://
    proxy_ws = ASR_PROXY_URL.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{proxy_ws}/asr/ws"

    timestamp = str(int(time.time()))
    sign = _make_sign(timestamp)

    params = {
        "timestamp": timestamp,
        "sign": sign,
        "model": model,
        "sample_rate": sample_rate,
        "language_hints": ",".join(language_hints or ["zh", "en"]),
    }
    if vocabulary_id:
        params["vocabulary_id"] = vocabulary_id

    return f"{ws_url}?{urlencode(params)}"


class RealtimeTranscriber:
    """
    实时转写器（代理模式）。

    用法：
        transcriber = RealtimeTranscriber(
            on_partial=...,
            on_sentence_end=...,
            on_error=...,
        )
        transcriber.start()
        while has_audio:
            transcriber.feed_audio(pcm_bytes)
        transcriber.stop()

    线程模型：
        - 独立线程运行 asyncio 事件循环管理 WebSocket
        - 回调在 WebSocket 接收线程执行
        - feed_audio() 可从任意线程调用
    """

    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]

    def __init__(
        self,
        on_partial: Callable[[str], None] | None = None,
        on_sentence_end: Callable[[dict], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_complete: Callable[[], None] | None = None,
        vocabulary_id: str | None = None,
        vocabulary: dict[str, int] | None = None,
        context: list[dict] | None = None,
        sample_rate: int = 16000,
        language_hints: list[str] | None = None,
    ):
        self._on_partial = on_partial
        self._on_sentence_end = on_sentence_end
        self._on_error = on_error
        self._on_complete = on_complete
        self._vocabulary_id = vocabulary_id
        self._vocabulary = vocabulary
        self._context = context
        self._sample_rate = sample_rate
        self._language_hints = language_hints or ["zh", "en"]
        self._started = False
        self._sentence_count = 0

        # WebSocket 管理
        self._ws = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._audio_queue: asyncio.Queue | None = None
        self._stop_event: asyncio.Event | None = None
        self._connect_event = threading.Event()
        self._connect_error: str | None = None

    def start(self) -> None:
        """启动实时转写（建立 WebSocket 连接到代理）"""
        if self._started:
            raise RuntimeError("实时转写已在运行中")

        ws_url = _get_ws_url(
            model=REALTIME_MODEL,
            sample_rate=self._sample_rate,
            language_hints=self._language_hints,
            vocabulary_id=self._vocabulary_id,
        )

        last_error_msg = None
        for attempt in range(self.MAX_RETRIES + 1):
            self._connect_event.clear()
            self._connect_error = None

            # 在独立线程中运行 asyncio 事件循环
            self._loop = asyncio.new_event_loop()
            self._audio_queue = asyncio.Queue()
            self._stop_event = asyncio.Event()

            self._thread = threading.Thread(
                target=self._run_ws_loop,
                args=(ws_url,),
                daemon=True,
            )
            self._thread.start()

            # 等待连接结果
            connected = self._connect_event.wait(timeout=5.0)

            if self._connect_error is not None:
                last_error_msg = self._connect_error
                is_rate_limit = (
                    "too many requests" in last_error_msg.lower()
                    or "throttl" in last_error_msg.lower()
                )
                if is_rate_limit and attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                    logger.warning(f"[实时转写] 限流，{delay}s 后重试 ({attempt + 1}/{self.MAX_RETRIES})...")
                    if self._on_error:
                        self._on_error(f"实时转写服务繁忙，{delay}秒后自动重试（{attempt + 1}/{self.MAX_RETRIES}）...")
                    time.sleep(delay)
                    self._cleanup()
                    continue
                else:
                    self._cleanup()
                    raise RuntimeError(last_error_msg)

            if not connected:
                last_error_msg = "连接超时"
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                    logger.warning(f"[实时转写] 连接超时，{delay}s 后重试...")
                    time.sleep(delay)
                    self._cleanup()
                    continue
                else:
                    self._cleanup()
                    raise RuntimeError(f"实时转写启动失败（已重试{self.MAX_RETRIES}次）: {last_error_msg}")

            # 连接成功
            self._started = True
            self._sentence_count = 0
            logger.info(f"[实时转写] 已启动（代理模式）{REALTIME_MODEL}")
            return

        self._cleanup()
        raise RuntimeError(f"实时转写启动失败（已重试{self.MAX_RETRIES}次）: {last_error_msg}")

    def _run_ws_loop(self, ws_url: str) -> None:
        """在独立线程中运行 WebSocket 事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._ws_main(ws_url))

    async def _ws_main(self, ws_url: str) -> None:
        """WebSocket 主循环"""
        try:
            async with websockets.connect(ws_url) as ws:
                self._ws = ws
                self._connect_event.set()  # 标记连接成功

                # 启动发送和接收任务
                send_task = asyncio.create_task(self._ws_send_loop())
                recv_task = asyncio.create_task(self._ws_recv_loop())

                # 等待任一任务完成
                done, pending = await asyncio.wait(
                    [send_task, recv_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # 取消未完成的任务
                for task in pending:
                    task.cancel()

        except Exception as e:
            error_msg = f"WebSocket 连接失败: {e}"
            logger.error(f"[实时转写] {error_msg}")
            self._connect_error = error_msg
            self._connect_event.set()
            if self._on_error:
                self._on_error(error_msg)
        finally:
            self._ws = None

    async def _ws_send_loop(self) -> None:
        """发送音频帧到代理"""
        try:
            while not self._stop_event.is_set():
                try:
                    audio_data = await asyncio.wait_for(
                        self._audio_queue.get(), timeout=0.5
                    )
                    if audio_data is None:  # 停止信号
                        # 发送停止消息
                        await self._ws.send(json.dumps({"type": "stop"}))
                        break
                    await self._ws.send(audio_data)
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            logger.error(f"[实时转写] 发送失败: {e}")

    async def _ws_recv_loop(self) -> None:
        """从代理接收识别结果"""
        try:
            async for message in self._ws:
                if isinstance(message, str):
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type", "")

                        if msg_type == "partial":
                            text = data.get("text", "")
                            text = apply_hotword_mappings(text)
                            if self._on_partial:
                                self._on_partial(text)

                        elif msg_type == "sentence":
                            text = data.get("text", "")
                            text = apply_hotword_mappings(text)
                            self._sentence_count += 1
                            if self._on_sentence_end:
                                self._on_sentence_end({
                                    "text": text,
                                    "begin_time": data.get("begin_time", 0),
                                    "end_time": data.get("end_time", 0),
                                })

                        elif msg_type == "error":
                            error_msg = data.get("message", "未知错误")
                            logger.error(f"[实时转写] 代理返回错误: {error_msg}")
                            if self._on_error:
                                self._on_error(error_msg)

                        elif msg_type == "complete":
                            logger.info("[实时转写] 识别完成")
                            if self._on_complete:
                                self._on_complete()
                            break

                    except json.JSONDecodeError:
                        pass
        except websockets.exceptions.ConnectionClosed:
            logger.info("[实时转写] WebSocket 连接已关闭")
        except Exception as e:
            logger.error(f"[实时转写] 接收失败: {e}")
            if self._on_error:
                self._on_error(str(e))

    def feed_audio(self, pcm_data: bytes) -> None:
        """送入 PCM 音频数据"""
        if not self._started or not self._audio_queue or not self._loop:
            logger.warning(f"[实时转写] feed_audio 被忽略: started={self._started}")
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._audio_queue.put(pcm_data), self._loop
            )
        except Exception as e:
            logger.error(f"[实时转写] 送入音频失败: {e}")

    def stop(self) -> None:
        """停止实时转写"""
        if not self._started:
            return

        logger.info(f"[实时转写] 停止中，共 {self._sentence_count} 句定稿")

        # 发送停止信号
        if self._audio_queue and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._audio_queue.put(None), self._loop
                )
            except Exception:
                pass

        if self._stop_event and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._stop_event.set(), self._loop
                )
            except Exception:
                pass

        self._cleanup()
        self._started = False
        logger.info(f"[实时转写] 已停止，共 {self._sentence_count} 句定稿")

    def _cleanup(self) -> None:
        """清理资源"""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._ws = None
        self._loop = None
        self._thread = None
        self._audio_queue = None
        self._stop_event = None

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def sentence_count(self) -> int:
        return self._sentence_count

    def increment_sentence_count(self) -> None:
        self._sentence_count += 1
