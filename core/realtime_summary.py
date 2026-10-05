"""
core/realtime_summary.py — 实时增量总结引擎 / Realtime incremental summary engine

职责 / Responsibilities:
  1. 收集录音期间的定稿句子，按分钟窗口缓冲 / Collect finalized sentences during recording, buffer by minute windows
  2. 每 60 秒触发一次 LLM 增量总结 / Trigger LLM incremental summary every 60s
  3. 通过回调将摘要推送给前端 / Push summary to frontend via callback

增量策略 / Incremental strategy:
  - 首次总结 / First summary：仅传入当前缓冲区的句子 / Pass only current buffer sentences
  - 后续总结 / Subsequent: 传入「上次摘要」+「新增句子」，要求模型输出更新后的完整摘要 / Pass "last summary" + "new sentences", model outputs updated full summary
  - 使用 qwen-turbo（低延迟），max_tokens=1024 / Uses qwen-turbo (low latency), max_tokens=1024

限制 / Limitations:
  - 实时总结定位为「预览」，最终纪要仍走批管线 / Realtime summary is "preview"; final summary still goes through batch pipeline
  - 单次总结失败不影响后续周期 / Single summary failure does not affect subsequent cycles
"""

import asyncio
import logging
import threading
import time
from typing import Callable

from .llm import async_chat_completion_safe

logger = logging.getLogger(__name__)

# 总结周期（秒）
SUMMARY_INTERVAL = 60

# 实时总结模型（低延迟优先）
SUMMARY_MODEL = "qwen-turbo"

# 上次摘要截取长度（控制 token 消耗）
MAX_PREVIOUS_SUMMARY_CHARS = 1500

# 增量总结系统提示词
SUMMARY_SYSTEM_PROMPT = """你是一位专业的会议纪要助手。你的任务是根据会议对话内容，实时生成并更新会议纪要摘要。

## 核心原则
1. **忠于原文**：只基于提供的对话内容生成摘要，绝不编造或推测
2. **增量更新**：如果提供了「上次摘要」，在其基础上整合新增内容，保持连贯性
3. **内容不足时如实说明**：如果对话内容过短或不清晰，直接说明，不要硬凑
4. **简洁专业**：去除口语化表达，保留关键信息
5. **发言人标注**：对话中可能包含「发言人：内容」格式，在纪要中保留关键观点的发言人归属

## 输出格式
使用 Markdown 格式，结构如下：

### 会议摘要
[2-3句话概括当前讨论主题]

### 关键要点
- 要点1
- 要点2
- ...

### 待办/决策（如有）
- 相关内容

## 禁止行为
- 不要编造对话中未提及的内容
- 不要添加虚构的截止日期或负责人
- 对话少于 2 句有效内容时，输出"等待更多内容..."
"""


class RealtimeSummarizer:
    """
    实时增量总结器。

    用法：
        summarizer = RealtimeSummarizer(
            on_summary=lambda content: ...,   # 摘要更新回调
            on_status=lambda status: ...,     # 状态变化回调
        )
        summarizer.start()
        # 在 ASR 回调中调用
        summarizer.feed_sentence({"text": "...", "begin_time": 0, "end_time": 1000})
        # 录音结束时
        summarizer.stop()
        final = summarizer.get_final_summary()

    线程模型：
        - 定时器在独立线程执行
        - LLM 调用通过 asyncio.run_coroutine_threadsafe 委托到事件循环线程池
          （使用 async_chat_completion_safe + asyncio.to_thread），不阻塞事件循环
        - 回调通过事件循环投递到 asyncio 世界
    """

    def __init__(
        self,
        on_summary: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_countdown: Callable[[int], None] | None = None,
        interval: int = SUMMARY_INTERVAL,
    ):
        """
        初始化实时总结器。

        Args:
            on_summary: 摘要更新回调，接收 Markdown 字符串
            on_status: 状态变化回调，接收状态字符串（"summarizing" / "idle" / "paused" / "stopped"）
            on_countdown: 倒计时回调，接收剩余秒数（每秒推送一次）
            interval: 总结间隔秒数（默认 60，最小 30）
        """
        self._on_summary = on_summary
        self._on_status = on_status
        self._on_countdown = on_countdown

        # 总结间隔（下限 30 秒，防止 API 调用过于频繁）
        self._interval = max(30, interval)

        # 句子缓冲
        self._buffer: list[dict] = []  # 当前分钟新增句子
        self._all_sentences: list[dict] = []  # 全部定稿句子
        self._previous_summary: str = ""  # 上次摘要

        # 定时器
        self._timer: threading.Timer | None = None
        self._timer_started_at: float = 0  # 当前计时周期起始时间戳
        self._started = False
        self._paused = False
        self._stopped = False
        self._paused_by_recording = False  # 标记暂停是否由录音暂停触发
        self._lock = threading.Lock()  # 保护缓冲区

        # 倒计时推送线程
        self._countdown_thread: threading.Thread | None = None
        self._countdown_stop_event = threading.Event()

        # 统计
        self._summary_count = 0

    def start(self) -> None:
        """启动定时器"""
        if self._started:
            raise RuntimeError("实时总结已在运行中")
        self._started = True
        self._paused = False
        self._paused_by_recording = False
        self._stopped = False
        self._schedule_next()
        logger.info(f"[实时总结] 已启动（间隔 {self._interval}s）")

    def stop(self) -> None:
        """停止定时器（彻底关闭）"""
        self._started = False
        self._stopped = True
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._stop_countdown()
        if self._on_status:
            self._on_status("stopped")
        logger.info(f"[实时总结] 已停止，共 {self._summary_count} 次总结")

    def pause(self, source: str = "manual") -> None:
        """
        暂停总结（冻结倒计时）

        Args:
            source: 暂停来源，"manual"（用户手动）或 "recording"（录音暂停联动）
        """
        self._paused = True
        self._paused_by_recording = (source == "recording")
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._stop_countdown()
        if self._on_status:
            self._on_status("paused")
        logger.info(f"[实时总结] 已暂停（来源: {source}）")

    def resume(self) -> None:
        """恢复总结"""
        self._paused = False
        self._paused_by_recording = False
        if self._started:
            self._schedule_next()
        if self._on_status:
            self._on_status("idle")
        logger.info("[实时总结] 已恢复")

    def auto_resume_for_recording(self) -> bool:
        """
        录音恢复时自动恢复总结（仅当暂停是由录音触发时）

        Returns:
            bool: 是否实际执行了恢复
        """
        if self._paused and self._paused_by_recording and not self._stopped:
            self.resume()
            logger.info("[实时总结] 因录音恢复而自动恢复")
            return True
        return False

    def restart(self) -> None:
        """从已停止状态重新启动"""
        if not self._stopped:
            return
        self._stopped = False
        self._started = True
        self._paused = False
        self._paused_by_recording = False
        self._schedule_next()
        if self._on_status:
            self._on_status("idle")
        logger.info("[实时总结] 已重新启动")

    def feed_sentence(self, sentence: dict) -> None:
        """
        接收定稿句子。

        Args:
            sentence: {"text": "...", "begin_time": ms, "end_time": ms}
                      可选 "speaker_name" 字段，用于在总结中标注发言人
        """
        if not self._started:
            return
        with self._lock:
            self._buffer.append(sentence)
            self._all_sentences.append(sentence)
        logger.debug(f"[实时总结] 收到句子: {sentence.get('text', '')[:40]}")

    def update_speaker_name(self, old_name: str, new_name: str) -> None:
        """
        更新缓冲区中所有句子的说话人姓名（绑定后调用）。

        确保下一次增量总结使用绑定后的真实姓名，而非通用编号。
        """
        with self._lock:
            updated = 0
            for s in self._buffer:
                if s.get("speaker_name") == old_name:
                    s["speaker_name"] = new_name
                    updated += 1
            for s in self._all_sentences:
                if s.get("speaker_name") == old_name:
                    s["speaker_name"] = new_name
            if updated:
                logger.info(f"[实时总结] 更新说话人姓名: '{old_name}' → '{new_name}'（{updated} 条缓冲区句子）")

    def get_final_summary(self) -> str:
        """返回最终摘要（录音结束后调用）"""
        return self._previous_summary

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_paused_by_recording(self) -> bool:
        return self._paused_by_recording

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    @property
    def summary_count(self) -> int:
        return self._summary_count

    @property
    def interval(self) -> int:
        return self._interval

    def get_remaining(self) -> int:
        """获取当前计时周期剩余秒数（供 WebSocket 回放用）"""
        if not self._started or self._paused or self._stopped:
            return 0
        if self._timer_started_at <= 0:
            return self._interval
        elapsed = time.monotonic() - self._timer_started_at
        remaining = max(0, self._interval - int(elapsed))
        return remaining

    def set_interval(self, new_interval: int) -> None:
        """
        热更新总结间隔。

        若在运行中，立即重启当前计时周期（剩余时间按新间隔重新计算）。
        最小值 30 秒，防止 API 调用过于频繁。
        """
        self._interval = max(30, new_interval)
        if self._started and not self._paused:
            # 重启当前计时周期
            if self._timer:
                self._timer.cancel()
            self._stop_countdown()
            self._schedule_next()
            logger.info(f"[实时总结] 间隔已热更新为 {self._interval}s")
        else:
            logger.info(f"[实时总结] 间隔已更新为 {self._interval}s（下次启动生效）")

    # ── 内部方法 ──

    def _schedule_next(self) -> None:
        """调度下一次总结"""
        if not self._started or self._paused:
            return
        self._timer_started_at = time.monotonic()
        self._timer = threading.Timer(self._interval, self._do_summary)
        self._timer.daemon = True
        self._timer.start()
        # 启动倒计时推送线程
        self._start_countdown()

    def _start_countdown(self) -> None:
        """启动倒计时推送线程（每秒推送剩余秒数）"""
        self._stop_countdown()  # 先确保旧线程已停止
        self._countdown_stop_event = threading.Event()

        def _countdown_loop():
            while not self._countdown_stop_event.is_set():
                if not self._started or self._paused:
                    break
                remaining = self.get_remaining()
                if self._on_countdown and remaining >= 0:
                    self._on_countdown(remaining)
                self._countdown_stop_event.wait(1.0)

        self._countdown_thread = threading.Thread(target=_countdown_loop, daemon=True)
        self._countdown_thread.start()

    def _stop_countdown(self) -> None:
        """停止倒计时推送线程"""
        self._countdown_stop_event.set()
        if self._countdown_thread and self._countdown_thread.is_alive():
            self._countdown_thread.join(timeout=2.0)
        self._countdown_thread = None

    def _do_summary(self) -> None:
        """执行一次增量总结（在 Timer 线程中执行）

        LLM 调用通过 run_coroutine_threadsafe 委托到事件循环线程池，
        使用 asyncio.to_thread 执行，不阻塞事件循环。
        """
        if not self._started or self._paused:
            return

        # 取出当前缓冲区内容并清空
        with self._lock:
            new_sentences = list(self._buffer)
            self._buffer.clear()

        if not new_sentences:
            # 无新内容，跳过但继续调度
            logger.debug("[实时总结] 无新内容，跳过")
            self._schedule_next()
            return

        # 停止倒计时（总结中不推送倒计时）
        self._stop_countdown()

        # 通知前端正在总结
        if self._on_status:
            self._on_status("summarizing")

        try:
            # 构造新内容文本（含发言人标注）
            new_text = ""
            for s in new_sentences:
                speaker = s.get("speaker_name", "")
                text = s.get("text", "")
                if speaker:
                    new_text += f"{speaker}：{text}\n"
                else:
                    new_text += f"{text}\n"
            new_text = new_text.strip()

            # 构造 prompt
            if self._previous_summary:
                # 增量模式：上次摘要 + 新内容
                prev = self._previous_summary[:MAX_PREVIOUS_SUMMARY_CHARS]
                user_content = (
                    f"## 上次摘要\n{prev}\n\n"
                    f"## 新增对话片段\n{new_text}\n\n"
                    f"请基于新增内容，更新上述摘要。保持格式一致，整合新信息，去除过时内容。"
                )
            else:
                # 首次总结
                user_content = (
                    f"## 对话片段\n{new_text}\n\n"
                    f"请根据以上对话内容生成会议纪要摘要。"
                )

            messages = [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            # 通过事件循环线程池执行 LLM 调用（不阻塞事件循环）
            from app.store import event_loop
            if event_loop and not event_loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(
                    async_chat_completion_safe(
                        messages,
                        model=SUMMARY_MODEL,
                        max_tokens=1024,
                        temperature=0.3,
                    ),
                    event_loop,
                )
                summary = future.result()  # 在 Timer 线程中等待结果
            else:
                # 兑底：无事件循环时直接同步调用（不应发生）
                from .llm import chat_completion
                summary = chat_completion(
                    messages,
                    model=SUMMARY_MODEL,
                    max_tokens=1024,
                    temperature=0.3,
                )

            if summary and summary.strip():
                self._previous_summary = summary.strip()
                self._summary_count += 1
                if self._on_summary:
                    self._on_summary(self._previous_summary)
                logger.info(f"[实时总结] 第 {self._summary_count} 次总结完成，{len(self._previous_summary)} 字符")

        except Exception as e:
            logger.warning(f"[实时总结] 总结失败: {e}")
        finally:
            if self._on_status:
                self._on_status("idle")
            # 继续调度
            self._schedule_next()
