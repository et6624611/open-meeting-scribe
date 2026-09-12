"""
app/realtime_store.py — 实时消息推送状态

作者：王永亮
创建：2026-09-12
版本：1.0.0

职责：
  - 实时转写 / 聚类 / 总结 / 章节生成器的状态字典
  - 静默检测状态
  - 跨线程消息推送（SDK 回调 → asyncio Queue）
  - 实时说话人姓名解析

从 app/store.py 拆分而来，与原模块通过 re-export 保持向后兼容。
"""

import asyncio
import logging

from core.realtime_asr import RealtimeTranscriber
from core.realtime_summary import RealtimeSummarizer
from core.realtime_chapters import RealtimeChapterGenerator
from core.diarization import SpeakerDiarizer
from core import speakers

logger = logging.getLogger(__name__)

# ============================================================
# 实时转写状态（task_id → 相关信息）
# ============================================================

realtime_queues: dict[str, asyncio.Queue] = {}       # WebSocket 消息队列
realtime_transcribers: dict[str, RealtimeTranscriber] = {}  # 实时转写器
realtime_diarizers: dict[str, SpeakerDiarizer] = {}  # 声纹聚类器
realtime_summarizers: dict[str, RealtimeSummarizer] = {}  # 实时总结器
realtime_chapter_generators: dict[str, RealtimeChapterGenerator] = {}  # 实时章节生成器
realtime_transcript_buffers: dict[str, list[dict]] = {}  # 实时转写缓冲（task_id → 最近 N 条句子）
realtime_full_transcripts: dict[str, list[dict]] = {}  # 全量实时转写（task_id → 所有句子，供文本桥接匹配）
realtime_speaker_maps: dict[str, dict[int, str]] = {}  # 实时说话人绑定（task_id → {speaker_id: speaker_uuid}）
event_loop: asyncio.AbstractEventLoop | None = None  # 主事件循环引用

# 静默检测状态（task_id → 相关信息，详见 docs/design/SILENCE_DETECTION.md）
realtime_last_heartbeat: dict[str, float] = {}       # 最后心跳时间戳
realtime_last_sentence: dict[str, float] = {}         # 最后 ASR 定稿句子时间戳
realtime_presence_scores: dict[str, float] = {}       # 前端上报的存在性评分
realtime_silence_warnings: dict[str, int] = {}        # 已发送提醒次数
realtime_silence_monitors: dict[str, asyncio.Task] = {}  # 静默监测协程任务

# 实时转写缓冲区最大条目数
REALTIME_BUFFER_MAX = 10


# ============================================================
# 实时推送辅助函数
# ============================================================


def push_realtime_msg(task_id: str, msg: dict) -> None:
    """
    从 SDK 线程安全地推送消息到 asyncio Queue。

    DashScope 回调在 SDK 内部线程执行，需要通过事件循环
    将消息投递到 asyncio.Queue，供 WebSocket 协程消费。
    """
    queue = realtime_queues.get(task_id)
    loop = event_loop
    if queue and loop and not loop.is_closed():
        try:
            asyncio.run_coroutine_threadsafe(queue.put(msg), loop)
        except Exception as e:
            logger.error(f"推送实时消息失败: {e}")

    # 定稿句子自动写入缓冲区（供 AI 对话上下文注入）
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
        # 只保留最近 N 条
        if len(buf) > REALTIME_BUFFER_MAX:
            realtime_transcript_buffers[task_id] = buf[-REALTIME_BUFFER_MAX:]
        # 同步写入全量转写（无上限，供文本桥接匹配）
        full = realtime_full_transcripts.setdefault(task_id, [])
        full.append(sentence_entry)


def resolve_realtime_speaker_name(task_id: str, speaker_id: int) -> str:
    """
    解析实时说话人姓名。

    优先级：
      1. 实时绑定映射（realtime_speaker_maps）
      2. 全局说话人列表（speakers.json）
      3. 兜底：发言人{speaker_id}
    """
    # 1. 查实时绑定映射
    binding_map = realtime_speaker_maps.get(task_id, {})
    speaker_uuid = binding_map.get(speaker_id)
    if speaker_uuid:
        spk = speakers.get_speaker_by_id(speaker_uuid)
        if spk:
            return spk.name

    # 2. 兜底
    return f"发言人{speaker_id + 1}"
