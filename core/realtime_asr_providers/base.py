"""core/realtime_asr_providers/base.py — provider 契约与 WebSocket 基类。

设计约束：
  - 只暴露 start() / send_audio_frame(pcm) / stop()，
    以便直接放进 RealtimeTranscriber._recognition，复用现有 feed/stop/自愈路径。
  - 回调只出原始文本；热词映射与句子计数由 RealtimeTranscriber 统一处理。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


class RealtimeSessionClosed(RuntimeError):
    """识别会话已关闭（断线 / 服务端结束）。由 RealtimeTranscriber 触发自愈。"""


@dataclass
class RealtimeProviderSpec:
    """单个实时 ASR 厂商的静态描述（同时驱动前端动态表单）。"""

    key: str
    label_key: str
    available: bool
    transport: str
    models: list[str] = field(default_factory=list)
    default_model: str = ""
    allow_custom_model: bool = False
    credential_fields: list[dict] = field(default_factory=list)
    capabilities: dict = field(default_factory=dict)
    model_capabilities: dict[str, dict] = field(default_factory=dict)
    sample_rate: int = 16000
    chunk_bytes: int = 0
    docs_url: str = ""
    speaker_label_paths: list[str] = field(default_factory=list)

    def capabilities_for(self, model: str) -> dict:
        caps = dict(self.capabilities)
        override = self.model_capabilities.get(model or self.default_model)
        if override:
            caps.update(override)
        return caps

    def to_public_dict(self) -> dict:
        return asdict(self)


class AudioChunker:
    """把录音回调的不定长 PCM 块重新切成厂商要求的固定包长。"""

    def __init__(self, chunk_bytes: int):
        self._chunk_bytes = max(0, int(chunk_bytes))
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def push(self, data: bytes) -> list[bytes]:
        if not data:
            return []
        if not self._chunk_bytes:
            return [data]
        with self._lock:
            self._buffer.extend(data)
            chunks: list[bytes] = []
            while len(self._buffer) >= self._chunk_bytes:
                chunks.append(bytes(self._buffer[: self._chunk_bytes]))
                del self._buffer[: self._chunk_bytes]
            return chunks

    def flush(self) -> bytes:
        with self._lock:
            if not self._buffer:
                return b""
            tail = bytes(self._buffer)
            self._buffer.clear()
            return tail


class WebSocketProviderBase:
    """WebSocket 厂商基类：独立线程 + asyncio 循环 + 发送队列。

    子类实现：ws_url / ws_headers / on_open / encode_audio_frame /
    send_final / decode_message。
    """

    KEY = "base"
    CONNECT_TIMEOUT = 10.0
    CHUNK_BYTES = 0
    QUEUE_MAX = 200

    def __init__(
        self,
        on_partial: Callable[[str], None] | None = None,
        on_sentence_end: Callable[[dict], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_complete: Callable[[], None] | None = None,
        sample_rate: int = 16000,
        options: dict | None = None,
    ):
        self._on_partial = on_partial
        self._on_sentence_end = on_sentence_end
        self._on_error = on_error
        self._on_complete = on_complete
        self.sample_rate = sample_rate
        self.options = options or {}

        self._chunker = AudioChunker(self.CHUNK_BYTES)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._audio_queue: asyncio.Queue | None = None
        self._started = False
        self._closed = False
        self._connect_event = threading.Event()
        self._connect_error: str | None = None

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self) -> None:
        if self._started:
            raise RuntimeError("实时转写已在运行中")
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"asr-{self.KEY}"
        )
        self._thread.start()
        if not self._connect_event.wait(self.CONNECT_TIMEOUT):
            raise RuntimeError("实时转写连接超时")
        if self._connect_error:
            raise RuntimeError(self._connect_error)
        self._started = True

    def send_audio_frame(self, pcm: bytes) -> None:
        if not self._started:
            raise RealtimeSessionClosed("Speech recognition has stopped.")
        if self._closed:
            raise RealtimeSessionClosed("Speech recognition has stopped.")
        if not self._loop or not self._audio_queue:
            return
        for chunk in self._chunker.push(pcm):
            try:
                asyncio.run_coroutine_threadsafe(
                    self._audio_queue.put(chunk), self._loop
                )
            except Exception as exc:  # 队列所在循环已退出
                self._closed = True
                raise RealtimeSessionClosed(str(exc)) from exc

    def stop(self) -> None:
        self._started = False
        if self._loop and self._audio_queue:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._audio_queue.put(None), self._loop
                )
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    # ── 线程内事件循环 ────────────────────────────────────────

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        self._audio_queue = asyncio.Queue(maxsize=self.QUEUE_MAX)
        try:
            loop.run_until_complete(self._main())
        except Exception as exc:
            logger.error(f"[实时转写:{self.KEY}] 连接失败: {exc}")
            if not self._connect_event.is_set():
                self._connect_error = str(exc)
                self._connect_event.set()
        finally:
            try:
                loop.close()
            except Exception:
                pass

    async def _main(self) -> None:
        import websockets

        async with websockets.connect(
            self.ws_url(),
            additional_headers=self.ws_headers(),
            max_size=None,
            open_timeout=self.CONNECT_TIMEOUT,
        ) as ws:
            await self.on_open(ws)
            self._connect_event.set()
            recv_task = asyncio.create_task(self._recv_loop(ws))
            await self._send_loop(ws)
            try:
                await asyncio.wait_for(recv_task, timeout=5.0)
            except asyncio.TimeoutError:
                recv_task.cancel()
        self._closed = True

    async def _send_loop(self, ws) -> None:
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                tail = self._chunker.flush()
                if tail:
                    frame = self.encode_audio_frame(tail)
                    if frame:
                        await ws.send(frame)
                frame = self.send_final()
                if frame:
                    await ws.send(frame)
                return
            frame = self.encode_audio_frame(chunk)
            if frame:
                await ws.send(frame)

    async def _recv_loop(self, ws) -> None:
        try:
            async for raw in ws:
                for event in self.decode_message(raw):
                    self._dispatch(event)
        except Exception as exc:
            if not self._closed:
                self._closed = True
                self._emit_error(f"实时转写连接中断: {exc}")

    # ── 回调分发 ──────────────────────────────────────────────

    def _dispatch(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "partial" and self._on_partial:
            self._on_partial(event.get("text", ""))
        elif kind == "sentence" and self._on_sentence_end:
            self._on_sentence_end(event)
        elif kind == "error":
            self._emit_error(event.get("message", "实时转写错误"))
        elif kind == "done" and self._on_complete:
            self._on_complete()

    def _emit_error(self, message: str) -> None:
        logger.warning(f"[实时转写:{self.KEY}] {message}")
        if self._on_error:
            self._on_error(message)

    # ── 子类钩子 ──────────────────────────────────────────────

    def ws_url(self) -> str:
        raise NotImplementedError

    def ws_headers(self) -> dict:
        return {}

    async def on_open(self, ws) -> None:
        return None

    def encode_audio_frame(self, chunk: bytes) -> bytes | None:
        return chunk

    def send_final(self) -> bytes | None:
        return None

    def decode_message(self, raw) -> list[dict]:
        return []
