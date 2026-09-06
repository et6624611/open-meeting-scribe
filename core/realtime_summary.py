"""
core/realtime_summary.py — 实时增量总结引擎

职责：
  1. 收集录音期间的定稿句子，按分钟窗口缓冲
  2. 每 60 秒触发一次 LLM 增量总结
  3. 通过回调将摘要推送给前端

增量策略：
  - 首次总结：仅传入当前缓冲区的句子
  - 后续总结：传入「上次摘要」+「新增句子」，要求模型输出更新后的完整摘要
  - 使用 qwen-turbo（低延迟），max_tokens=1024

限制：
  - 实时总结定位为「预览」，最终纪要仍走批管线
  - 单次总结失败不影响后续周期
"""

import asyncio
import logging
import threading
from typing import Callable

from .llm import chat_completion

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
        - LLM 调用在定时器线程中同步执行（不阻塞主事件循环）
        - 回调通过事件循环投递到 asyncio 世界
    """

    def __init__(
        self,
        on_summary: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ):
        """
        初始化实时总结器。

        Args:
            on_summary: 摘要更新回调，接收 Markdown 字符串
            on_status: 状态变化回调，接收状态字符串（"summarizing" / "idle" / "paused"）
        """
        self._on_summary = on_summary
        self._on_status = on_status

        # 句子缓冲
        self._buffer: list[dict] = []  # 当前分钟新增句子
        self._all_sentences: list[dict] = []  # 全部定稿句子
        self._previous_summary: str = ""  # 上次摘要

        # 定时器
        self._timer: threading.Timer | None = None
        self._started = False
        self._paused = False
        self._lock = threading.Lock()  # 保护缓冲区

        # 统计
        self._summary_count = 0

    def start(self) -> None:
        """启动定时器"""
        if self._started:
            raise RuntimeError("实时总结已在运行中")
        self._started = True
        self._paused = False
        self._schedule_next()
        logger.info("[实时总结] 已启动")

    def stop(self) -> None:
        """停止定时器"""
        self._started = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info(f"[实时总结] 已停止，共 {self._summary_count} 次总结")

    def pause(self) -> None:
        """暂停总结"""
        self._paused = True
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._on_status:
            self._on_status("paused")
        logger.info("[实时总结] 已暂停")

    def resume(self) -> None:
        """恢复总结"""
        self._paused = False
        if self._started:
            self._schedule_next()
        if self._on_status:
            self._on_status("idle")
        logger.info("[实时总结] 已恢复")

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
    def summary_count(self) -> int:
        return self._summary_count

    # ── 内部方法 ──

    def _schedule_next(self) -> None:
        """调度下一次总结"""
        if not self._started or self._paused:
            return
        self._timer = threading.Timer(SUMMARY_INTERVAL, self._do_summary)
        self._timer.daemon = True
        self._timer.start()

    def _do_summary(self) -> None:
        """执行一次增量总结"""
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

            summary = chat_completion(
                messages,
                model=SUMMARY_MODEL,
                max_tokens=1024,
                temperature=0.3,  # 低温度，更稳定
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
