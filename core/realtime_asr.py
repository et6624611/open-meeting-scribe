"""
core/realtime_asr.py — 实时转写引擎（DashScope qwen-audio-3.0-asr-flash-streaming）

职责：
  封装 DashScope 实时语音识别 SDK 的流式调用，提供：
  1. 启动 WebSocket 连接
  2. 接收 PCM 音频流并送入识别
  3. 通过回调收集实时句子（临时结果 + 定稿句子）
  4. 通过 asyncio.Queue 将结果推送给 WebSocket 端点

限制：
  - 实时 API 不支持说话人分离（无 speaker_id）
  - 说话人分离仅在批管线（paraformer-v2）中生效
  - 实时转写定位为「预览」，最终纪要仍走批管线

硬约束（详见 docs/API_CONTRACTS.md）：
  - 音频格式：PCM 16bit / 16kHz / 单声道
  - 每包音频建议 ~100ms（3200 bytes = 3200 帧 × 2 bytes）
  - WebSocket 地址：wss://dashscope.aliyuncs.com/api-ws/v1/inference

新模型特性（相比 paraformer-realtime-v2）：
  - 支持上下文增强（context）：传入领域术语/对话历史提升识别率
  - 支持即时热词（vocabulary）：随请求内联传入，无需预创建热词表
  - 同时兼容预编译热词（vocabulary_id）
  - 支持更多音频格式（pcm/wav/opus/speex/aac/amr），无时长限制
  - 支持句级 + 字级时间戳
"""

import os
import time
import asyncio
import logging
import threading
from typing import Callable

import dashscope
from dashscope.audio.asr import (
    Recognition,
    RecognitionCallback,
    RecognitionResult,
)

from .hotwords import apply_hotword_mappings

logger = logging.getLogger(__name__)

# DashScope WebSocket 地址（华北2北京地域）
DASHSCOPE_WS_URL = os.getenv(
    "DASHSCOPE_WS_URL",
    "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
)

# 每包音频大小：3200 帧 × 2 bytes/帧 = 6400 bytes（100ms @16kHz/16bit）
AUDIO_FRAME_SIZE = 6400


class _TranscriptCallback(RecognitionCallback):
    """
    DashScope 实时识别回调。

    将识别结果通过回调函数传出（由 RealtimeTranscriber 注入）。
    回调在 SDK 内部线程执行，需注意线程安全。
    """

    def __init__(
        self,
        on_partial: Callable[[str], None] | None = None,
        on_sentence_end: Callable[[dict], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_complete: Callable[[], None] | None = None,
    ):
        self._on_partial = on_partial
        self._on_sentence_end = on_sentence_end
        self._on_error = on_error
        self._on_complete = on_complete
        # 连接状态信号：用于 start() 中同步等待连接结果
        self._connect_event = threading.Event()
        self._connect_error: str | None = None

    def on_open(self) -> None:
        logger.info("[实时转写] WebSocket 连接已建立")
        self._connect_event.set()  # 标记连接成功

    def on_close(self) -> None:
        logger.info("[实时转写] WebSocket 连接已关闭")

    def on_complete(self) -> None:
        logger.info("[实时转写] 识别任务完成")
        if self._on_complete:
            self._on_complete()

    def on_error(self, result: RecognitionResult) -> None:
        msg = f"实时转写错误: {result.message}"
        logger.error(msg)
        self._connect_error = result.message
        self._connect_event.set()  # 标记收到错误（连接失败）
        if self._on_error:
            self._on_error(msg)

    def wait_for_connect(self, timeout: float = 3.0) -> str | None:
        """
        等待连接结果（成功或错误）。

        Returns:
            None: 连接成功
            str: 错误信息（连接失败）
        """
        self._connect_event.wait(timeout=timeout)
        return self._connect_error

    def on_event(self, result: RecognitionResult) -> None:
        """
        收到识别结果。

        - 句子未完成 → on_partial（临时结果，会不断更新）
        - 句子已完成 → on_sentence_end（定稿句子）
        """
        sentence = result.get_sentence()
        if not sentence or "text" not in sentence:
            logger.debug(f"[实时转写] on_event: 无有效 sentence, sentence={sentence}")
            return

        text = sentence["text"]
        is_end = RecognitionResult.is_sentence_end(sentence)

        # 热词映射纠正（如 ES→EAS系统）
        text = apply_hotword_mappings(text)

        logger.info(f"[实时转写] on_event: text='{text[:40]}', is_end={is_end}")

        if is_end:
            # 定稿句子
            logger.debug(f"[实时转写] 定稿: {text}")
            if self._on_sentence_end:
                self._on_sentence_end({
                    "text": text,
                    "begin_time": sentence.get("begin_time", 0),
                    "end_time": sentence.get("end_time", 0),
                })
        else:
            # 临时结果（句子还在识别中）
            if self._on_partial:
                self._on_partial(text)


# 实时转写模型（官方推荐首选，详见 docs/adr/0004）
REALTIME_MODEL = "qwen-audio-3.0-asr-flash-streaming"


class RealtimeTranscriber:
    """
    实时转写器。

    用法：
        transcriber = RealtimeTranscriber(
            on_partial=...,        # 临时结果回调
            on_sentence_end=...,   # 定稿句子回调
            on_error=...,          # 错误回调
        )
        transcriber.start()
        # 循环送入 PCM 数据
        while has_audio:
            transcriber.feed_audio(pcm_bytes)
        transcriber.stop()

    线程模型：
        - SDK 内部用独立线程管理 WebSocket
        - 回调在 SDK 线程执行
        - feed_audio() 可从任意线程调用
    """

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
        """
        初始化实时转写器。

        Args:
            on_partial: 临时结果回调（句子未完成时触发）
            on_sentence_end: 定稿句子回调
            on_error: 错误回调
            on_complete: 识别完成回调
            vocabulary_id: 预编译热词表 ID（可选，需预先创建）
            vocabulary: 即时热词（可选，如 {"张三": 5, "李四": 5}，随请求内联传入）
            context: 上下文增强（可选，传入领域术语/对话历史提升识别率）
                     格式：[{"role": "user", "content": [{"type": "input_text", "text": "..."}]}]
            sample_rate: 采样率（默认 16000Hz）
            language_hints: 语言提示（默认 ["zh", "en"]）
        """
        self._on_partial = on_partial
        self._on_sentence_end = on_sentence_end
        self._on_error = on_error
        self._on_complete = on_complete
        self._vocabulary_id = vocabulary_id
        self._vocabulary = vocabulary
        self._context = context
        self._sample_rate = sample_rate
        self._language_hints = language_hints or ["zh", "en"]
        self._recognition: Recognition | None = None
        self._started = False
        self._sentence_count = 0

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]  # 指数退避：2s, 5s, 10s

    def start(self) -> None:
        """
        启动实时转写（建立 WebSocket 连接）。

        遇到限流错误时自动重试（最多 MAX_RETRIES 次，指数退避）。
        限流错误通过 SDK 回调返回，通过 wait_for_connect() 同步检测。
        """
        if self._started:
            raise RuntimeError("实时转写已在运行中")

        # 配置 DashScope WebSocket 地址
        dashscope.base_websocket_api_url = DASHSCOPE_WS_URL

        # 确保 API Key 已设置
        from app.store import get_asr_config
        api_key = get_asr_config()["api_key"]
        if not api_key:
            raise RuntimeError("未设置 ASR API Key，请在设置页面配置语音转写服务或通过 .env 配置 DASHSCOPE_API_KEY")
        dashscope.api_key = api_key

        # 构建识别参数
        # 新模型 qwen-audio-3.0-asr-flash-streaming 支持：
        # - vocabulary_id: 预编译热词表 ID
        # - vocabulary: 即时热词（内联传入）
        # - context: 上下文增强（领域术语/对话历史）
        kwargs = {
            "model": REALTIME_MODEL,
            "format": "pcm",
            "sample_rate": self._sample_rate,
            "language_hints": self._language_hints,
            "semantic_punctuation_enabled": True,  # 会议场景用语义断句
            "disfluency_removal_enabled": False,
            "heartbeat": True,  # 保持长连接
        }
        if self._vocabulary_id:
            kwargs["vocabulary_id"] = self._vocabulary_id
        if self._vocabulary:
            kwargs["vocabulary"] = self._vocabulary

        # 带重试的启动（应对限流）
        last_error_msg = None
        for attempt in range(self.MAX_RETRIES + 1):
            # 每次重试都创建新的回调实例
            callback = _TranscriptCallback(
                on_partial=self._on_partial,
                on_sentence_end=self._on_sentence_end,
                on_error=self._on_error if attempt == self.MAX_RETRIES else None,  # 重试时不转发错误
                on_complete=self._on_complete,
            )
            kwargs["callback"] = callback

            try:
                self._recognition = Recognition(**kwargs)

                # 上下文增强通过 raw_input 传入（SDK 协议：input.context 字段）
                if self._context:
                    raw_input = {"context": self._context}
                    self._recognition.start(raw_input=raw_input)
                else:
                    self._recognition.start()

                # 等待 SDK 回调确认连接结果（on_open 或 on_error）
                error_msg = callback.wait_for_connect(timeout=5.0)

                if error_msg is not None:
                    # 连接失败（通过回调返回的错误）
                    raise RuntimeError(error_msg)

                # 连接成功
                self._started = True
                self._sentence_count = 0
                logger.info(f"[实时转写] 已启动 {REALTIME_MODEL}")
                return  # 启动成功

            except Exception as e:
                last_error_msg = str(e)
                is_rate_limit = (
                    "too many requests" in last_error_msg.lower()
                    or "throttl" in last_error_msg.lower()
                )

                if is_rate_limit and attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                    logger.warning(
                        f"[实时转写] 限流，{delay}s 后重试 ({attempt + 1}/{self.MAX_RETRIES})..."
                    )
                    # 重试时给用户友好的进度提示
                    if self._on_error:
                        self._on_error(
                            f"实时转写服务繁忙，{delay}秒后自动重试（{attempt + 1}/{self.MAX_RETRIES}）..."
                        )
                    time.sleep(delay)
                    # 清理失败的实例
                    try:
                        if self._recognition:
                            self._recognition.stop()
                    except Exception:
                        pass
                    self._recognition = None
                    continue
                else:
                    # 非限流错误或已达最大重试次数
                    try:
                        if self._recognition:
                            self._recognition.stop()
                    except Exception:
                        pass
                    self._recognition = None
                    raise

        # 所有重试都失败
        self._recognition = None
        raise RuntimeError(f"实时转写启动失败（已重试{self.MAX_RETRIES}次）: {last_error_msg}")

    def feed_audio(self, pcm_data: bytes) -> None:
        """
        送入 PCM 音频数据。

        Args:
            pcm_data: PCM 16bit 单声道数据，建议每次 6400 bytes（100ms）
        """
        if not self._started or not self._recognition:
            logger.warning(f"[实时转写] feed_audio 被忽略: started={self._started}, rec={self._recognition is not None}")
            return
        try:
            self._recognition.send_audio_frame(pcm_data)
        except Exception as e:
            logger.error(f"[实时转写] 送入音频失败: {e}")

    def stop(self) -> None:
        """停止实时转写，等待所有结果返回"""
        if not self._started or not self._recognition:
            return

        try:
            self._recognition.stop()
            logger.info(f"[实时转写] 已停止，共 {self._sentence_count} 句定稿")
        except Exception as e:
            logger.error(f"[实时转写] 停止失败: {e}")
        finally:
            self._started = False
            self._recognition = None

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def sentence_count(self) -> int:
        return self._sentence_count

    def increment_sentence_count(self) -> None:
        self._sentence_count += 1
