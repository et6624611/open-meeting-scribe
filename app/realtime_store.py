"""
app/realtime_store.py — 实时消息推送状态 / Realtime message push state

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 实时转写 / 聚类 / 总结 / 章节生成器的状态字典 / Realtime transcription / clustering / summary / chapter generator state dicts
  - 静默检测状态 / Silence detection state
  - 跨线程消息推送（SDK 回调 → asyncio Queue） / Cross-thread message push (SDK callback → asyncio Queue)
  - 实时说话人姓名解析 / Realtime speaker name resolution

从 app/store.py 拆分而来，与原模块通过 re-export 保持向后兼容 / Split from app/store.py; backward-compatible via re-export.
"""

import asyncio
import logging

from core import speakers
from core.diarization import SpeakerDiarizer
from core.realtime_asr import RealtimeTranscriber
from core.realtime_chapters import RealtimeChapterGenerator
from core.realtime_summary import RealtimeSummarizer
from core.translate import RealtimeTranslator

logger = logging.getLogger(__name__)

# ============================================================
# 实时转写状态（task_id → 相关信息） / Realtime transcription state (task_id → related info)
# ============================================================

realtime_queues: dict[str, asyncio.Queue] = {}       # WebSocket 消息队列 / WebSocket message queues
realtime_transcribers: dict[str, RealtimeTranscriber] = {}  # 实时转写器 / Realtime transcribers
realtime_diarizers: dict[str, SpeakerDiarizer] = {}  # 声纹聚类器 / Voiceprint clusterers
realtime_summarizers: dict[str, RealtimeSummarizer] = {}  # 实时总结器 / Realtime summarizers
realtime_chapter_generators: dict[str, RealtimeChapterGenerator] = {}  # 实时章节生成器 / Realtime chapter generators
realtime_translators: dict[str, RealtimeTranslator] = {}  # 实时翻译器（按需创建） / Realtime translators (created on demand)
realtime_translations: dict[str, list[dict]] = {}  # 全量翻译结果（task_id → 翻译条目列表，供 WebSocket 回放） / Full translation results (task_id → translation entries; for WebSocket replay)
realtime_transcript_buffers: dict[str, list[dict]] = {}  # 实时转写缓冲（task_id → 最近 N 条句子） / Realtime transcript buffer (task_id → last N sentences)
realtime_full_transcripts: dict[str, list[dict]] = {}  # 全量实时转写（task_id → 所有句子，供文本桥接匹配） / Full realtime transcript (task_id → all sentences; for text bridge matching)
# DEF-PROXY-02：stop 后封存表（task_id → 已交棒给 task 的列表引用），吸收 SDK 线程迟到定稿
realtime_full_sealed: dict[str, list[dict]] = {}
realtime_speaker_maps: dict[str, dict[int, str]] = {}  # 实时说话人绑定（task_id → {speaker_id: speaker_uuid}） / Realtime speaker binding (task_id → {speaker_id: speaker_uuid})
event_loop: asyncio.AbstractEventLoop | None = None  # 主事件循环引用 / Main event loop reference

# 静默检测状态（task_id → 相关信息，详见 docs/design/SILENCE_DETECTION.md） / Silence detection state (task_id → related info; see docs/design/SILENCE_DETECTION.md)
realtime_last_heartbeat: dict[str, float] = {}       # 最后心跳时间戳 / Last heartbeat timestamp
realtime_last_sentence: dict[str, float] = {}         # 最后 ASR 定稿句子时间戳 / Last ASR finalized sentence timestamp
realtime_presence_scores: dict[str, float] = {}       # 前端上报的存在性评分 / Frontend-reported presence scores
realtime_silence_warnings: dict[str, int] = {}        # 已发送提醒次数 / Warnings sent count
realtime_silence_monitors: dict[str, asyncio.Task] = {}  # 静默监测协程任务 / Silence monitor coroutine tasks

# 实时转写缓冲区最大条目数 / Realtime transcript buffer max entries
REALTIME_BUFFER_MAX = 10


# ============================================================
# 实时推送辅助函数 / Realtime Push Helper Functions
# ============================================================


def push_realtime_msg(task_id: str, msg: dict) -> None:
    """
    从 SDK 线程安全地推送消息到 asyncio Queue / Thread-safely push message from SDK thread to asyncio Queue.

    DashScope 回调在 SDK 内部线程执行，需要通过事件循环 / DashScope callbacks run in SDK internal thread; need event loop
    将消息投递到 asyncio.Queue，供 WebSocket 协程消费 / to deliver messages to asyncio.Queue for WebSocket coroutine consumption.
    """
    queue = realtime_queues.get(task_id)
    loop = event_loop
    if queue and loop and not loop.is_closed():
        try:
            asyncio.run_coroutine_threadsafe(queue.put(msg), loop)
        except Exception as e:
            logger.error(f"推送实时消息失败: {e}")

    # 定稿句子自动写入缓冲区（供 AI 对话上下文注入） / Auto-write finalized sentences to buffer (for AI chat context injection)
    if msg.get("type") == "sentence":
        sentence_entry = {
            "text": msg.get("text", ""),
            "speaker_id": msg.get("speaker_id"),
            "speaker_name": msg.get("speaker_name", ""),
            "begin_time": msg.get("begin_time", 0),
            "end_time": msg.get("end_time", 0),
        }
        buf = realtime_transcript_buffers.setdefault(task_id, [])
        buf.append(sentence_entry)
        # 只保留最近 N 条 / Keep only last N entries
        if len(buf) > REALTIME_BUFFER_MAX:
            realtime_transcript_buffers[task_id] = buf[-REALTIME_BUFFER_MAX:]
        # 同步写入全量转写（无上限，供文本桥接匹配） / Sync write to full transcript (unlimited; for text bridge matching)
        # DEF-PROXY-02 stop 竞态修复：若 stop 已封存（列表已交棒给 task），迟到的句尾定稿
        # 直接 append 到同一列表对象（task 持引用），不再落入孤儿新列表而丢失。
        full = realtime_full_transcripts.get(task_id)
        if full is None:
            full = realtime_full_sealed.get(task_id)
        if full is not None:
            full.append(sentence_entry)


def resolve_realtime_speaker_name(task_id: str, speaker_id: int) -> str:
    """
    Resolve realtime speaker display name.

    Priority:
      1. Realtime binding map (realtime_speaker_maps)
      2. Global speaker list (speakers.json)
      3. Fallback: empty string — frontend i18n renders "Speaker {id}"
    """
    # 1. Check realtime binding map / 检查实时绑定映射
    binding_map = realtime_speaker_maps.get(task_id, {})
    speaker_uuid = binding_map.get(speaker_id)
    if speaker_uuid:
        spk = speakers.get_speaker_by_id(speaker_uuid)
        if spk:
            return spk.name

    # 2. Fallback: return empty so frontend i18n handles display / 兆底：返回空字符串，由前端 i18n 处理显示
    return ""
