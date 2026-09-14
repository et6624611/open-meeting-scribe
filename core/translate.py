"""
core/translate.py — 实时翻译引擎 / Realtime translation engine

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
版本 / Version: 1.0.0

职责 / Responsibilities:
  1. 收集录音期间的定稿句子，按攒批窗口缓冲 / Collect finalized sentences during recording, buffer by batch window
  2. 达到批次大小或定时器到期后，批量调用 LLM 翻译 / Batch-translate when batch size reached or timer expires
  3. 通过回调将译文推送给前端 / Push translations to frontend via callback

攒批策略 / Batching strategy:
  - 每收到一句 feed_sentence()，加入缓冲区 / Each feed_sentence() call adds to buffer
  - 若缓冲达到 MAX_BATCH_SIZE(5) 句，立即触发翻译 / If buffer reaches MAX_BATCH_SIZE(5), trigger translation immediately
  - 否则启动/重置 BATCH_INTERVAL(5s) 定时器，到期后触发翻译 / Otherwise start/reset BATCH_INTERVAL(5s) timer, translate on expiry
  - 翻译结果与原文句子一一对应，保留 speaker_id / begin_time / end_time / Translation results correspond 1:1 with source sentences, preserving speaker_id / begin_time / end_time

限制 / Limitations:
  - 实时翻译定位为「会中预览」，最终译文仍可在会后批量精修 / Realtime translation is "in-meeting preview"; final translations can be batch-refined post-meeting
  - 单次翻译失败不影响后续批次
  - 翻译器按需创建（用户点击启用时），未启用时不产生任何 LLM 调用
"""

import asyncio
import json
import logging
import re
import threading
from typing import Callable

from .llm import async_chat_completion_safe

logger = logging.getLogger(__name__)

# ── 翻译参数 ──
TRANSLATION_MODEL = "qwen-turbo"       # 低延迟模型优先
BATCH_INTERVAL = 5                      # 攒批窗口（秒）
MAX_BATCH_SIZE = 5                      # 最大批次句数（攒够即翻）

# 语言名称映射（供 prompt 使用）
LANG_NAMES = {
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "zh-CN": "中文（简体）",
    "zh-TW": "中文（繁体）",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "ar": "阿拉伯语",
}

TRANSLATION_SYSTEM_PROMPT = """你是一位专业的会议翻译助手。你的任务是将会议对话句子逐句翻译为目标语言。

## 核心原则
1. **逐句对应**：输入是一个 JSON 数组，每个元素是一句原文。输出必须是相同长度的 JSON 数组，每个元素是对应句子的译文。顺序必须严格一致。
2. **忠于原意**：准确传达原文含义，不增删内容，不添加解释或注释
3. **保持专业**：使用目标语言的自然表达，去除口语化赘词但保留语气
4. **术语一致**：同一会议中出现的专有名词、人名、术语，在所有句子中保持统一译法
5. **格式保持**：只输出 JSON 数组，不要输出任何其他内容

## 输出格式
严格输出 JSON 数组，不要输出任何其他文本：

```json
["译文1", "译文2", "译文3"]
```

## 禁止行为
- 不要输出 JSON 数组以外的任何内容
- 不要改变数组长度（必须与输入句子数量完全一致）
- 不要合并或拆分句子
- 不要添加原文中没有的内容"""


class RealtimeTranslator:
    """
    实时翻译器。

    用法：
        translator = RealtimeTranslator(
            target_lang="en",
            on_translation=lambda translations: ...,  # 译文更新回调
            on_status=lambda status: ...,             # 状态变化回调
        )
        translator.start()
        # 在 ASR 定稿句子回调中调用
        translator.feed_sentence({"text": "...", "speaker_id": 0, ...})
        # 录音结束时
        translator.stop()
        all_translations = translator.get_all_translations()

    线程模型：同 RealtimeSummarizer
      - 定时器在独立线程执行
      - LLM 调用通过 asyncio.run_coroutine_threadsafe 委托到事件循环线程池
      - 回调通过事件循环投递到 asyncio 世界
    """

    def __init__(
        self,
        target_lang: str = "en",
        on_translation: Callable[[list[dict]], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ):
        """
        初始化实时翻译器。

        Args:
            target_lang: 目标语言代码（如 "en", "ja", "ko"）
            on_translation: 译文更新回调，接收翻译结果列表
                           每项格式: {index, original_text, translated_text, speaker_id, begin_time, end_time}
            on_status: 状态变化回调，接收状态字符串（"translating" / "idle" / "stopped"）
        """
        self._target_lang = target_lang
        self._on_translation = on_translation
        self._on_status = on_status

        # 句子缓冲
        self._buffer: list[dict] = []       # 当前批次待翻译句子
        self._all_sentences: list[dict] = []  # 全部定稿句子（含已翻译）
        self._all_translations: list[dict] = []  # 全量翻译结果（供回放）
        self._sentence_index = 0            # 全局句子计数器（用于 index 字段）

        # 定时器
        self._timer: threading.Timer | None = None
        self._started = False
        self._stopped = False
        self._lock = threading.Lock()

        # 统计
        self._translation_count = 0

    def start(self) -> None:
        """启动翻译器"""
        if self._started:
            raise RuntimeError("实时翻译器已在运行中")
        self._started = True
        self._stopped = False
        logger.info(f"[实时翻译] 已启动（目标语言: {self._target_lang}）")
        if self._on_status:
            self._on_status("idle")

    def stop(self) -> None:
        """停止翻译器（翻译缓冲区中剩余内容后彻底关闭）"""
        self._started = False
        self._stopped = True
        if self._timer:
            self._timer.cancel()
            self._timer = None

        # 尝试翻译缓冲区中剩余的句子
        with self._lock:
            remaining = list(self._buffer)
            self._buffer.clear()

        if remaining:
            try:
                self._do_translation(remaining)
            except Exception as e:
                logger.warning(f"[实时翻译] 停止时翻译剩余失败: {e}")

        if self._on_status:
            self._on_status("stopped")
        logger.info(f"[实时翻译] 已停止，共 {self._translation_count} 次翻译")

    def feed_sentence(self, sentence: dict) -> None:
        """
        接收定稿句子。

        Args:
            sentence: {"text": "...", "speaker_id": N, "speaker_name": "...",
                       "begin_time": ms, "end_time": ms}
        """
        if not self._started:
            return

        with self._lock:
            self._buffer.append(sentence)
            self._all_sentences.append(sentence)
            current_buffer_size = len(self._buffer)

        logger.debug(f"[实时翻译] 收到句子 (缓冲 {current_buffer_size}): {sentence.get('text', '')[:40]}")

        # 达到最大批次大小，立即触发翻译
        if current_buffer_size >= MAX_BATCH_SIZE:
            self._flush_buffer()
        else:
            # 重置定时器（每次新句子到来都重置，等待更多句子攒批）
            self._reset_timer()

    def set_target_lang(self, lang: str) -> None:
        """
        热切换目标语言。

        切换后清空已有翻译结果，后续新句子将翻译为新语言。
        已翻译的句子译文保留（不清除历史）。
        """
        if lang == self._target_lang:
            return
        self._target_lang = lang
        logger.info(f"[实时翻译] 目标语言切换为: {lang}")
        # 清空缓冲（旧语言的待翻译句子不再有意义）
        with self._lock:
            self._buffer.clear()
            if self._timer:
                self._timer.cancel()
                self._timer = None
        if self._on_status:
            self._on_status("idle")

    def get_all_translations(self) -> list[dict]:
        """返回全量翻译结果（录音结束后调用，供持久化/回放）"""
        return list(self._all_translations)

    @property
    def target_lang(self) -> str:
        return self._target_lang

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    @property
    def translation_count(self) -> int:
        return self._translation_count

    # ── 内部方法 ──

    def _reset_timer(self) -> None:
        """重置攒批定时器（在锁外调用）"""
        if not self._started:
            return
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(BATCH_INTERVAL, self._flush_buffer)
        self._timer.daemon = True
        self._timer.start()

    def _flush_buffer(self) -> None:
        """取出当前缓冲区句子并触发翻译（在 Timer 线程中执行）"""
        if not self._started:
            return

        with self._lock:
            batch = list(self._buffer)
            self._buffer.clear()
            if self._timer:
                self._timer.cancel()
                self._timer = None

        if not batch:
            return

        try:
            self._do_translation(batch)
        except Exception as e:
            logger.warning(f"[实时翻译] 翻译失败: {e}")

    def _do_translation(self, batch: list[dict]) -> None:
        """
        执行一次批量翻译（在 Timer 线程中执行）。

        LLM 调用通过 run_coroutine_threadsafe 委托到事件循环线程池，
        使用 asyncio.to_thread 执行，不阻塞事件循环。
        """
        if not batch:
            return

        # 通知前端正在翻译
        if self._on_status:
            self._on_status("translating")

        try:
            # 构造翻译输入
            sentences_text = [s.get("text", "").strip() for s in batch]
            target_lang_name = LANG_NAMES.get(self._target_lang, self._target_lang)

            user_content = (
                f"请将以下 {len(sentences_text)} 句会议对话翻译为{target_lang_name}。\n\n"
                f"原文句子列表：\n{json.dumps(sentences_text, ensure_ascii=False)}"
            )

            messages = [
                {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            # 通过事件循环线程池执行 LLM 调用（不阻塞事件循环）
            from app.realtime_store import event_loop
            if event_loop and not event_loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(
                    async_chat_completion_safe(
                        messages,
                        model=TRANSLATION_MODEL,
                        max_tokens=2048,
                        temperature=0.3,
                    ),
                    event_loop,
                )
                raw = future.result()  # 在 Timer 线程中等待结果
            else:
                # 兜底：无事件循环时直接同步调用（不应发生）
                from .llm import chat_completion
                raw = chat_completion(
                    messages,
                    model=TRANSLATION_MODEL,
                    max_tokens=2048,
                    temperature=0.3,
                )

            if raw and raw.strip():
                translated_texts = self._parse_response(raw, len(batch))
                if translated_texts:
                    translations = []
                    for i, (sentence, translated_text) in enumerate(zip(batch, translated_texts)):
                        entry = {
                            "index": self._sentence_index,
                            "original_text": sentence.get("text", ""),
                            "translated_text": translated_text,
                            "speaker_id": sentence.get("speaker_id", 0),
                            "speaker_name": sentence.get("speaker_name", ""),
                            "begin_time": sentence.get("begin_time", 0),
                            "end_time": sentence.get("end_time", 0),
                        }
                        translations.append(entry)
                        self._sentence_index += 1

                    # 追加到全量结果
                    with self._lock:
                        self._all_translations.extend(translations)

                    self._translation_count += 1
                    if self._on_translation:
                        self._on_translation(translations)
                    logger.info(
                        f"[实时翻译] 第 {self._translation_count} 次翻译完成: "
                        f"{len(translations)} 句 → {self._target_lang}"
                    )

        except Exception as e:
            logger.warning(f"[实时翻译] LLM 调用失败: {e}")
            # 失败时仍需递增 sentence_index，避免后续 index 错位
            self._sentence_index += len(batch)
        finally:
            if self._on_status:
                self._on_status("idle")

    def _parse_response(self, raw: str, expected_count: int) -> list[str]:
        """
        解析 LLM 返回的翻译结果。

        期望格式：JSON 数组字符串，如 ["translation1", "translation2", ...]
        容错处理：提取 JSON 数组，若解析失败则按行拆分。
        """
        # 尝试提取 JSON 数组
        json_match = re.search(r'\[.*\]', raw, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                if isinstance(parsed, list) and len(parsed) == expected_count:
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                pass

        # 兜底：按行拆分（LLM 可能未严格输出 JSON）
        lines = [line.strip() for line in raw.strip().split('\n') if line.strip()]
        # 过滤掉可能的 markdown 标记
        lines = [ln for ln in lines if not ln.startswith('```') and not ln.startswith('[')]

        if len(lines) >= expected_count:
            return lines[:expected_count]

        # 最终兜底：返回空字符串填充，保持数量一致
        logger.warning(
            f"[实时翻译] 解析失败（期望 {expected_count} 句，"
            f"JSON 解析得到 {len(lines) if lines else 0} 行），使用原文兜底"
        )
        return ["[翻译失败]"] * expected_count
