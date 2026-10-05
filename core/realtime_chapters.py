"""
core/realtime_chapters.py — 实时增量章节生成引擎 / Realtime incremental chapter generation engine

职责 / Responsibilities:
  1. 收集录音期间的定稿句子，按窗口缓冲 / Collect finalized sentences during recording, buffer by window
  2. 每 90 秒触发一次 LLM 增量章节分析 / Trigger LLM incremental chapter analysis every 90s
  3. 通过回调将章节列表推送给前端 / Push chapter list to frontend via callback

增量策略 / Incremental strategy:
  - 首次 / First: 传入当前缓冲句子，生成初始章节 / Pass current buffer sentences, generate initial chapters
  - 后续 / Subsequent: 传入「上次章节列表」+「新增句子」，要求模型检测话题变化、追加或调整章节 / Pass "last chapter list" + "new sentences", detect topic changes, append or adjust
  - 已完成章节保持不变，仅最后一个章节可能扩展或拆分 / Completed chapters stay unchanged; only last chapter may expand or split
  - 使用 qwen-turbo（低延迟），max_tokens=1536 / Uses qwen-turbo (low latency), max_tokens=1536

限制 / Limitations:
  - 实时章节定位为「进程感知」，最终章节仍走批管线 qwen-plus 精修 / Realtime chapters are "progress-aware"; final chapters still go through batch pipeline qwen-plus refinement
  - 单次分析失败不影响后续周期 / Single analysis failure does not affect subsequent cycles
"""

import asyncio
import json
import logging
import re
import threading
from typing import Callable

from .llm import async_chat_completion_safe

logger = logging.getLogger(__name__)

CHAPTERS_INTERVAL = 90

CHAPTERS_MODEL = "qwen-turbo"

MAX_PREVIOUS_CHAPTERS_CHARS = 2000

CHAPTERS_SYSTEM_PROMPT = """你是一位会议进程分析助手。你的任务是根据会议对话内容，实时追踪议题变化并划分章节。

## 核心原则
1. **忠于原文**：只基于对话内容划分章节，绝不编造议题
2. **增量稳定**：已完成的章节（非最后一个）不要修改其标题和摘要，只追加新章节或调整最后一个章节
3. **话题驱动**：只有话题明显转变时才开新章节（如从"项目进度"转到"预算讨论"）
4. **宁少勿多**：同一话题内的细节不拆分，5 分钟内的会议通常只有 1-2 个章节
5. **内容不足时**：如果对话少于 4 句有效内容，返回 1 个章节即可

## 输出格式
严格输出 JSON 数组，不要输出任何其他内容：

```json
[
  {
    "id": 1,
    "title": "章节标题（不超过12字）",
    "start_ms": 0,
    "end_ms": 30000,
    "summary": "一句话摘要（不超过40字）",
    "key_points": ["要点1", "要点2"]
  }
]
```

字段说明：
- id: 从 1 开始的章节编号
- title: 简洁的章节标题
- start_ms: 该章节开始的绝对时间（毫秒）
- end_ms: 该章节结束时间（毫秒），最后一个章节用当前最新句子的 end_time
- summary: 一句话概括该章节讨论内容
- key_points: 1-3 个关键要点，每个不超过 25 字

## 禁止行为
- 不要编造对话中未提及的内容
- 不要输出 JSON 以外的任何文本
- 不要修改已完成章节的标题和摘要"""


class RealtimeChapterGenerator:
    """
    实时增量章节生成器。

    用法：
        generator = RealtimeChapterGenerator(
            on_chapters=lambda chapters: ...,  # 章节更新回调
        )
        generator.start()
        generator.feed_sentence({"text": "...", "begin_time": 0, "end_time": 1000})
        generator.stop()

    线程模型：同 RealtimeSummarizer（LLM 调用通过事件循环线程池执行）
    """

    def __init__(
        self,
        on_chapters: Callable[[list[dict]], None] | None = None,
    ):
        self._on_chapters = on_chapters

        self._buffer: list[dict] = []
        self._all_sentences: list[dict] = []
        self._previous_chapters: list[dict] = []

        self._timer: threading.Timer | None = None
        self._started = False
        self._lock = threading.Lock()

        self._update_count = 0

    def start(self) -> None:
        if self._started:
            raise RuntimeError("实时章节生成器已在运行中")
        self._started = True
        self._schedule_next()
        logger.info("[实时章节] 已启动")

    def stop(self) -> None:
        self._started = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info(f"[实时章节] 已停止，共 {self._update_count} 次更新")

    def feed_sentence(self, sentence: dict) -> None:
        if not self._started:
            return
        with self._lock:
            self._buffer.append(sentence)
            self._all_sentences.append(sentence)

    def get_chapters(self) -> list[dict]:
        return list(self._previous_chapters)

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def update_count(self) -> int:
        return self._update_count

    # ── 内部方法 ──

    def _schedule_next(self) -> None:
        if not self._started:
            return
        self._timer = threading.Timer(CHAPTERS_INTERVAL, self._do_chapters)
        self._timer.daemon = True
        self._timer.start()

    def _do_chapters(self) -> None:
        """执行一次增量章节分析（在 Timer 线程中执行）

        LLM 调用通过 run_coroutine_threadsafe 委托到事件循环线程池，
        使用 asyncio.to_thread 执行，不阻塞事件循环。
        """
        if not self._started:
            return

        with self._lock:
            new_sentences = list(self._buffer)
            self._buffer.clear()
            all_sentences = list(self._all_sentences)

        if not new_sentences:
            logger.debug("[实时章节] 无新内容，跳过")
            self._schedule_next()
            return

        if len(all_sentences) < 3:
            logger.debug(f"[实时章节] 句子不足({len(all_sentences)})，跳过")
            self._schedule_next()
            return

        try:
            dialogue_text = ""
            for idx, s in enumerate(all_sentences):
                speaker = s.get("speaker_name", "")
                text = s.get("text", "")
                prefix = f"[{idx}] "
                if speaker:
                    prefix += f"{speaker}："
                dialogue_text += f"{prefix}{text}\n"
                if len(dialogue_text) > 4000:
                    dialogue_text += f"...（共 {len(all_sentences)} 句，已截断）\n"
                    break

            time_range = (
                f"{all_sentences[0]['begin_time']}ms - "
                f"{all_sentences[-1]['end_time']}ms"
            )

            if self._previous_chapters:
                prev_text = json.dumps(
                    self._previous_chapters, ensure_ascii=False, indent=2
                )
                if len(prev_text) > MAX_PREVIOUS_CHAPTERS_CHARS:
                    prev_text = prev_text[:MAX_PREVIOUS_CHAPTERS_CHARS] + "\n...(截断)"

                new_text = ""
                for s in new_sentences:
                    speaker = s.get("speaker_name", "")
                    text = s.get("text", "")
                    if speaker:
                        new_text += f"{speaker}：{text}\n"
                    else:
                        new_text += f"{text}\n"

                user_content = (
                    f"## 上次章节列表\n{prev_text}\n\n"
                    f"## 新增对话片段（{time_range}）\n{new_text.strip()}\n\n"
                    f"请基于新增内容更新章节列表。"
                    f"已完成章节（非最后一个）保持不变，仅在检测到新话题时追加新章节。"
                    f"最后一个章节的 end_ms 更新为最新句子的 end_time。"
                )
            else:
                user_content = (
                    f"## 对话内容（{time_range}，共 {len(all_sentences)} 句）\n"
                    f"{dialogue_text}\n"
                    f"请根据以上对话内容划分章节。"
                )

            messages = [
                {"role": "system", "content": CHAPTERS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            # 通过事件循环线程池执行 LLM 调用（不阻塞事件循环）
            from app.store import event_loop
            if event_loop and not event_loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(
                    async_chat_completion_safe(
                        messages,
                        model=CHAPTERS_MODEL,
                        max_tokens=1536,
                        temperature=0.3,
                    ),
                    event_loop,
                )
                raw = future.result()  # 在 Timer 线程中等待结果
            else:
                # 兑底：无事件循环时直接同步调用（不应发生）
                from .llm import chat_completion
                raw = chat_completion(
                    messages,
                    model=CHAPTERS_MODEL,
                    max_tokens=1536,
                    temperature=0.3,
                )

            if raw and raw.strip():
                chapters = self._parse_response(raw, all_sentences)
                if chapters:
                    self._previous_chapters = chapters
                    self._update_count += 1
                    if self._on_chapters:
                        self._on_chapters(chapters)
                    logger.info(
                        f"[实时章节] 第 {self._update_count} 次更新: "
                        f"{len(chapters)} 个章节"
                    )

        except Exception as e:
            logger.warning(f"[实时章节] 分析失败: {e}")
        finally:
            self._schedule_next()

    def _parse_response(self, raw: str, all_sentences: list[dict]) -> list[dict]:
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            json_str = raw.strip()

        arr_match = re.search(r'\[.*\]', json_str, re.DOTALL)
        if arr_match:
            json_str = arr_match.group(0)

        parsed = json.loads(json_str)
        if not isinstance(parsed, list):
            raise ValueError("返回的不是数组")

        chapters = []
        for item in parsed:
            if not isinstance(item, dict):
                continue

            key_points = item.get("key_points", [])
            if isinstance(key_points, list):
                key_points = [str(p)[:30] for p in key_points[:4]]
            else:
                key_points = []

            chapters.append({
                "id": int(item.get("id", len(chapters) + 1)),
                "title": str(item.get("title", "讨论中"))[:15],
                "start_ms": int(item.get("start_ms", 0)),
                "end_ms": int(item.get("end_ms", 0)),
                "summary": str(item.get("summary", ""))[:60],
                "key_points": key_points,
            })

        for i, ch in enumerate(chapters):
            ch["id"] = i + 1

        return chapters
