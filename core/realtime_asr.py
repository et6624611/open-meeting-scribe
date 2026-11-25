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
        from core.settings_store import get_engine_config
        if get_engine_config().get("mode") == "local":
            return "local"
    except Exception:
        pass
    try:
        from core.settings_store import get_asr_config
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


# 会话失效自愈（2026-11-19）：DashScope 直连识别器在空闲超时（暂停录制约 23s）
# 后会内部停止，此后 send_audio_frame 一直抛 "Speech recognition has stopped."。
# 原实现只打日志、_started 仍为 True，导致整场后半段无转写且 UI 无感。
# 现改为标记失效 + 一次性告知 + 后台自愈重建，连续自愈次数受上限保护。
STALE_HEAL_MAX = 3          # 单场连续自愈次数上限
STALE_HEAL_COOLDOWN = 30.0  # 两次自愈最小间隔（秒）


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

        # 直连识别器实例（直连模式专用）
        self._recognition = None

        # 会话失效自愈状态（见 STALE_HEAL_* 注释）
        self._restart_lock = threading.Lock()
        self._restarting = False
        self._stopping = False
        self._heal_attempts = 0
        self._last_heal_at = 0.0
        self._dead_notified = False

    def start(self) -> None:
        """启动实时转写（根据配置选择代理、云端、SDK 或厂商客户端）"""
        if self._started:
            raise RuntimeError("实时转写已在运行中")

        self._stopping = False
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

        self._start_configured()

    def _start_configured(self) -> None:
        """按实时预览配置分派：显式厂商优先，否则沿用原有 mode 链路。"""
        from core.settings_store import get_realtime_asr_config

        cfg = get_realtime_asr_config()
        if cfg.get("provider") == "auto":
            mode = _get_asr_mode()
            if mode == "direct":
                self._start_direct()
            elif mode == "cloud":
                self._start_cloud()
            else:
                self._start_proxy()
            return

        resolved = cfg.get("resolved_provider", "auto")
        if resolved in ("dashscope", "volcengine"):
            self._start_direct()
        elif resolved == "cloud":
            self._start_cloud()
        else:
            self._start_proxy()

    def _start_direct(self) -> None:
        """直连模式：DashScope SDK，或按 provider 选择厂商客户端。"""
        from core.settings_store import get_realtime_asr_config

        cfg = get_realtime_asr_config()
        resolved = cfg.get("resolved_provider", "dashscope")

        if resolved == "volcengine":
            self._start_provider("volcengine", cfg)
            return

        api_key = (cfg.get("credentials") or {}).get("api_key", "")
        base_url = cfg.get("base_url") or "https://dashscope.aliyuncs.com"

        if not api_key:
            raise RuntimeError("未配置 ASR API Key，请在设置页面配置语音转写服务或通过 .env 配置 DASHSCOPE_API_KEY")

        try:
            import dashscope
            from dashscope.audio.asr import Recognition, RecognitionCallback

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
                from dashscope.audio.asr import RecognitionResult

                sentence = result.get_sentence()
                if not sentence or "text" not in sentence:
                    return
                text = sentence["text"]
                if RecognitionResult.is_sentence_end(sentence):
                    self._handle_sentence({
                        "text": text,
                        "begin_time": sentence.get("begin_time", 0),
                        "end_time": sentence.get("end_time", 0),
                    })
                else:
                    self._handle_partial(text)

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

    def _start_provider(self, key: str, cfg: dict) -> None:
        """启动厂商 WebSocket 客户端（当前仅火山）。"""
        from core.realtime_asr_providers import create_provider
        from core.realtime_asr_providers.registry import get_spec

        spec = get_spec(key)
        caps = spec.capabilities_for(cfg.get("model", "")) if spec else {}
        enable_speaker = bool(caps.get("speaker_diarization")) and cfg.get("diarization") == "auto"
        provider_cfg = dict(cfg)
        provider_cfg["enable_speaker"] = enable_speaker

        provider = create_provider(
            key,
            provider_cfg,
            on_partial=self._handle_partial,
            on_sentence_end=self._handle_sentence,
            on_error=lambda msg: self._on_error(msg) if self._on_error else None,
            on_complete=lambda: self._on_complete() if self._on_complete else None,
            sample_rate=self._sample_rate,
        )
        try:
            provider.start()
        except Exception as e:
            error_msg = f"{key} 实时转写启动失败: {e}"
            logger.error(f"[实时转写] {error_msg}")
            if self._on_error:
                self._on_error(error_msg)
            raise RuntimeError(error_msg)

        self._recognition = provider
        self._started = True
        self._sentence_count = 0
        logger.info(f"[实时转写] 已启动（{key}），说话人分离={'开' if enable_speaker else '关'}")

    def _handle_partial(self, text: str) -> None:
        if not text:
            return
        if self._on_partial:
            self._on_partial(apply_hotword_mappings(text))

    def _handle_sentence(self, sentence: dict) -> None:
        text = sentence.get("text", "")
        if not text:
            return
        self._sentence_count += 1
        if self._on_sentence_end:
            payload = dict(sentence)
            payload["text"] = apply_hotword_mappings(text)
            self._on_sentence_end(payload)

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
        if self._recognition:
            try:
                self._recognition.send_audio_frame(pcm_data)
            except Exception as e:
                self._handle_feed_failure(e)
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

    def _handle_feed_failure(self, exc: Exception) -> None:
        """送帧失败处置：识别会话可能已停止（如暂停导致云端空闲超时）。

        原实现只打一行日志、_started 保持 True，前端仍然显示「转写中」，
        实际整场后半段无转写。现改为标记失效 + 一次性告知 + 后台自愈。
        """
        from core.realtime_asr_providers import RealtimeSessionClosed

        msg = str(exc)
        if not isinstance(exc, RealtimeSessionClosed) and "stopped" not in msg.lower():
            # 偶发送帧异常不代表会话已死，保留会话继续送帧
            logger.error(f"[实时转写] 送入音频失败: {msg}")
            return
        self._started = False
        self._recognition = None
        if self._dead_notified:
            return
        self._dead_notified = True
        logger.error(f"[实时转写] 识别会话已失效（{msg}），尝试自动恢复")
        if self._on_error:
            self._on_error("实时转写连接已中断，正在自动恢复…")
        self._try_self_heal()

    def _try_self_heal(self) -> None:
        """后台自愈重建（不阻塞 stream_reader 线程）。"""
        now = time.time()
        if self._stopping or self._restarting:
            return
        if self._heal_attempts >= STALE_HEAL_MAX:
            logger.error("[实时转写] 自愈次数已达上限，停止重试（录音与声纹识别不受影响）")
            return
        if now - self._last_heal_at < STALE_HEAL_COOLDOWN:
            return
        self._last_heal_at = now
        self._heal_attempts += 1
        threading.Thread(
            target=self.restart,
            kwargs={"reason": "会话失效自愈", "force": False},
            daemon=True,
            name="realtime-asr-heal",
        ).start()

    def restart(self, reason: str = "", force: bool = True) -> bool:
        """重建识别会话（暂停恢复 / 会话失效自愈）。

        与 stop() 的区别：旧识别器直接丢弃、不调用其 stop()——已失效会话
        stop 无意义，仍存活的会话调 stop 会触发 on_complete 误推 ended。
        force=False 用于自愈：若已被其它路径重建成功（_started=True）则跳过。
        """
        with self._restart_lock:
            if self._stopping:
                return False
            if not force and self._started:
                return False
            self._restarting = True
            count = self._sentence_count
            mode = "unknown"
            try:
                from core.settings_store import get_realtime_asr_config

                self._recognition = None
                self._started = False
                self._release_ws_session()
                mode = get_realtime_asr_config().get("resolved_provider", "auto")
                if mode == "local":
                    logger.warning("[实时转写] 当前为本地模式，跳过会话重建")
                    return False
                self._start_configured()
                self._sentence_count = count
                self._dead_notified = False
                if force:
                    # 手动/暂停恢复重建成功，重新给予自愈额度
                    self._heal_attempts = 0
                    self._last_heal_at = 0.0
                logger.info(
                    f"[实时转写] 会话已重建（{reason or '手动'}），累计 {count} 句定稿"
                )
                return True
            except Exception as e:
                logger.error(f"[实时转写] 会话重建失败（{reason or '手动'}）: {e}")
                self._started = False
                # 直连/厂商客户端内部已推 on_error，避免重复
                if mode not in ("dashscope", "volcengine") and self._on_error:
                    self._on_error(f"实时转写恢复失败：{e}")
                return False
            finally:
                self._restarting = False

    def _release_ws_session(self) -> None:
        """丢弃代理/云端旧 WebSocket 会话（直连模式无操作）。"""
        if self._loop or self._thread:
            self._cleanup()

    def stop(self) -> None:
        """停止实时转写"""
        self._stopping = True
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
