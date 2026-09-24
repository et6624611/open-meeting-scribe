"""
core/realtime_asr.py — 实时转写引擎（代理模式 + 直连模式） / Realtime transcription engine (proxy + direct modes)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 2.1.0（双模式 / dual mode）

职责 / Responsibilities:
  封装实时流式转写，支持两种接入模式 / Encapsulate realtime streaming transcription, two access modes:
  1. 代理模式 / Proxy mode：通过 ASR 代理 WebSocket 中继到 DashScope / Relay to DashScope via ASR proxy WebSocket
  2. 直连模式 / Direct mode：使用 DashScope SDK 直连，用户自持 API Key / Direct DashScope SDK, user-supplied API Key

限制 / Limitations:
  - 实时 API 不支持说话人分离（无 speaker_id） / Realtime API does not support diarization (no speaker_id)
  - 说话人分离仅在批管线（paraformer-v2）中生效 / Diarization only works in batch pipeline (paraformer-v2)
  - 实时转写定位为「预览」，最终纪要仍走批管线 / Realtime transcription is "preview"; final summary still goes through batch pipeline

硬约束（详见 docs/API_CONTRACTS.md） / Hard constraints (see docs/API_CONTRACTS.md):
  - 音频格式 / Audio format: PCM 16bit / 16kHz / 单声道 / mono
  - 每包音频建议 ~100ms（3200 bytes = 3200 帧× 2 bytes） / Recommended ~100ms per packet (3200 bytes = 3200 frames × 2 bytes)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from typing import Callable
from urllib.parse import urlencode

import websockets

from core.i18n import _

from .hotwords import apply_hotword_mappings

logger = logging.getLogger(__name__)

def _get_asr_mode() -> str:
    """获取当前 ASR 接入模式（local / proxy / direct / cloud）。

    local 模式（R1 / PRD-LOCAL-ENGINE Non-Goal）：本地引擎不做云端同级实时流式转写，
    实时链路显性降级为「分段批处理」——最终转写由 core/transcribe.py 的本地批管线
    （FunASR 常驻子进程）在录音结束后完成；实时 WS 预览在本地模式下不启用，
    且绝不触达任何云端转写端点（R1 边界：防误配 / 保证零出网）。
    """
    try:
        from app.settings_store import get_engine_config
        if get_engine_config().get("mode") == "local":
            return "local"
    except Exception:
        pass
    try:
        from app.store import get_asr_config
        return get_asr_config().get("mode", "proxy")
    except Exception:
        return "proxy"


# ── 代理配置 ──
ASR_PROXY_URL = os.getenv("ASR_PROXY_URL", "").rstrip("/")
ASR_PROXY_TOKEN = os.getenv("ASR_PROXY_TOKEN", "")

# 每包音频大小：3200 帧 × 2 bytes/帧 = 6400 bytes（100ms @16kHz/16bit）
AUDIO_FRAME_SIZE = 6400

# 实时转写模型
REALTIME_MODEL = "qwen-audio-3.0-asr-flash-streaming"


def _make_sign(timestamp: str) -> str:
    """生成请求签名（代理模式）"""
    if not ASR_PROXY_TOKEN:
        raise RuntimeError("未配置 ASR_PROXY_TOKEN，无法调用 ASR 代理")
    return hmac.new(
        ASR_PROXY_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()


def _make_cloud_sign(timestamp: str) -> str:
    """生成云端请求签名（cloud 模式）"""
    cloud_token = os.getenv("CLOUD_API_TOKEN", "").strip()
    if not cloud_token:
        raise RuntimeError("未配置 CLOUD_API_TOKEN，无法调用云端 ASR 服务")
    return hmac.new(
        cloud_token.encode(),
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


def _get_cloud_ws_url(
    model: str = REALTIME_MODEL,
    sample_rate: int = 16000,
    language_hints: list[str] | None = None,
    vocabulary_id: str | None = None,
    user_id: str = "",
) -> str:
    """构造云端 WebSocket URL（cloud 模式通过云端服务器中继到同机 ASR 代理）"""
    cloud_url = os.getenv("CLOUD_API_URL", "").rstrip("/")
    if not cloud_url:
        raise RuntimeError("未配置 CLOUD_API_URL，无法调用云端 ASR 服务")

    # http:// → ws://
    cloud_ws = cloud_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{cloud_ws}/api/cloud/asr/ws"

    timestamp = str(int(time.time()))
    sign = _make_cloud_sign(timestamp)

    params = {
        "timestamp": timestamp,
        "sign": sign,
        "model": model,
        "sample_rate": sample_rate,
        "language_hints": ",".join(language_hints or ["zh", "en"]),
    }
    if vocabulary_id:
        params["vocabulary_id"] = vocabulary_id
    if user_id:
        params["user_id"] = user_id

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
        """启动实时转写（根据模式选择代理、云端或直连）"""
        if self._started:
            raise RuntimeError("实时转写已在运行中")

        mode = _get_asr_mode()

        if mode == "local":
            # R1 显性声明：本地引擎实时链路降级为分段批处理，不启用云端 WS 预览。
            # 录音本身不中断（数据落本地），最终转写由本地批管线（FunASR 子进程）完成。
            # 抛分类错误以复用既有「实时启动失败」处理路径（与 direct 模式缺 Key 行为一致），
            # 并保证 local 模式下绝不触达任何云端转写端点（零出网 / 防误配）。
            # R9（WP-I）分支处置：engine.local.realtime_segments.enabled=true 时
            # record.py 改用 core.realtime_local_asr.LocalSegmentTranscriber（分段增量
            # 上屏），不会走到本分支；本降级声明仅在分段未开启（默认）时生效，
            # record.py 侧按 WP-H 口径推非错误状态声明（type:"status"）。
            from core.errors import LocalEngineError
            raise LocalEngineError(
                "本地引擎模式下实时预览降级为分段批处理：录音不受影响，"
                "最终转写将在录音结束后由本机 FunASR 管线完成（不出网）。",
                error_code="realtime_degraded_to_batch",
                can_fallback_cloud=False,
            )

        if mode == "direct":
            self._start_direct()
        elif mode == "cloud":
            self._start_cloud()
        else:
            self._start_proxy()

    def _start_direct(self) -> None:
        """直连模式：使用 DashScope SDK 直连"""
        from app.store import get_asr_config
        cfg = get_asr_config()
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url", "https://dashscope.aliyuncs.com")

        if not api_key:
            raise RuntimeError("未配置 ASR API Key，请在设置页面配置语音转写服务或通过 .env 配置 DASHSCOPE_API_KEY")

        try:
            import dashscope
            from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

            dashscope.base_websocket_api_url = f"{base_url.replace('https://', 'wss://').replace('http://', 'ws://')}/api-ws/v1/inference"
            dashscope.api_key = api_key

            # 构建参数
            kwargs = {
                "model": REALTIME_MODEL,
                "format": "pcm",
                "sample_rate": self._sample_rate,
                "language_hints": self._language_hints,
                "semantic_punctuation_enabled": True,
                "disfluency_removal_enabled": False,
                "heartbeat": True,
            }
            if self._vocabulary_id:
                kwargs["vocabulary_id"] = self._vocabulary_id

            # 创建回调
            callback = RecognitionCallback()

            def _on_event(result):
                sentence = result.get_sentence()
                if not sentence or "text" not in sentence:
                    return
                text = sentence["text"]
                is_end = RecognitionResult.is_sentence_end(sentence)
                if is_end:
                    text = apply_hotword_mappings(text)
                    self._sentence_count += 1
                    if self._on_sentence_end:
                        self._on_sentence_end({
                            "text": text,
                            "begin_time": sentence.get("begin_time", 0),
                            "end_time": sentence.get("end_time", 0),
                        })
                else:
                    text = apply_hotword_mappings(text)
                    if self._on_partial:
                        self._on_partial(text)

            callback.on_event = _on_event
            callback.on_error = lambda result: self._on_error(f"实时转写错误: {result.message}") if self._on_error else None
            callback.on_complete = lambda: (self._on_complete() if self._on_complete else None)
            callback.on_open = lambda: None
            callback.on_close = lambda: None

            # 创建并启动识别器
            self._recognition = Recognition(callback=callback, **kwargs)
            self._recognition.start()

            self._started = True
            self._sentence_count = 0
            logger.info(f"[实时转写] 已启动（直连模式）{REALTIME_MODEL}")

        except ImportError:
            raise RuntimeError("直连模式需要 dashscope SDK，请运行: pip install dashscope")
        except Exception as e:
            error_msg = f"直连模式启动失败: {e}"
            logger.error(f"[实时转写] {error_msg}")
            if self._on_error:
                self._on_error(error_msg)
            raise RuntimeError(error_msg)

    def _start_proxy(self) -> None:
        """代理模式：通过 ASR 代理 WebSocket 中继"""

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

    def _start_cloud(self) -> None:
        """云端模式：通过云端服务器 WebSocket 代理中继到 ASR 代理"""
        # 获取当前用户 ID（供云端配额检查）
        user_id = ""
        try:
            from core.users import _load_user_data
            user_id = _load_user_data().get("current_user_id", "") or ""
        except Exception:
            pass

        ws_url = _get_cloud_ws_url(
            model=REALTIME_MODEL,
            sample_rate=self._sample_rate,
            language_hints=self._language_hints,
            vocabulary_id=self._vocabulary_id,
            user_id=user_id,
        )

        last_error_msg = None
        for attempt in range(self.MAX_RETRIES + 1):
            self._connect_event.clear()
            self._connect_error = None

            self._loop = asyncio.new_event_loop()
            self._audio_queue = asyncio.Queue()
            self._stop_event = asyncio.Event()

            self._thread = threading.Thread(
                target=self._run_ws_loop,
                args=(ws_url,),
                daemon=True,
            )
            self._thread.start()

            connected = self._connect_event.wait(timeout=5.0)

            if self._connect_error is not None:
                last_error_msg = self._connect_error
                is_rate_limit = (
                    "too many requests" in last_error_msg.lower()
                    or "throttl" in last_error_msg.lower()
                )
                if is_rate_limit and attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                    logger.warning(f"[实时转写] 云端限流，{delay}s 后重试 ({attempt + 1}/{self.MAX_RETRIES})...")
                    if self._on_error:
                        self._on_error(f"云端实时转写服务繁忙，{delay}秒后自动重试（{attempt + 1}/{self.MAX_RETRIES}）...")
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
                    logger.warning(f"[实时转写] 云端连接超时，{delay}s 后重试...")
                    time.sleep(delay)
                    self._cleanup()
                    continue
                else:
                    self._cleanup()
                    raise RuntimeError(f"云端实时转写启动失败（已重试{self.MAX_RETRIES}次）: {last_error_msg}")

            self._started = True
            self._sentence_count = 0
            logger.info(f"[实时转写] 已启动（云端模式）{REALTIME_MODEL}")
            return

        self._cleanup()
        raise RuntimeError(f"云端实时转写启动失败（已重试{self.MAX_RETRIES}次）: {last_error_msg}")

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
                            error_msg = data.get("message", _("Unknown error"))
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
        if not self._started:
            logger.warning(f"[实时转写] feed_audio 被忽略: started={self._started}")
            return

        # 直连模式：通过 SDK 送入音频
        if hasattr(self, '_recognition') and self._recognition:
            try:
                self._recognition.send_audio_frame(pcm_data)
            except Exception as e:
                logger.error(f"[实时转写] 送入音频失败: {e}")
            return

        # 代理模式：通过 WebSocket 送入
        if not self._audio_queue or not self._loop:
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

        # 直连模式：通过 SDK 停止
        if hasattr(self, '_recognition') and self._recognition:
            try:
                self._recognition.stop()
            except Exception:
                pass
            self._recognition = None
            self._started = False
            logger.info(f"[实时转写] 已停止（直连模式），共 {self._sentence_count} 句定稿")
            return

        # 代理模式：通过 WebSocket 停止

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
        """清理资源（代理模式）"""
        if hasattr(self, '_recognition') and self._recognition:
            try:
                self._recognition.stop()
            except Exception:
                pass
            self._recognition = None
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
