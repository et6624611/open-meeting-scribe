"""
app/realtime_store.py — 兼容 re-export 层 / Compatibility re-export layer

实际实现已下沉至 core/realtime_store.py；本文件保留以维持既有 import 路径。
/ Implementation sunk to core/realtime_store.py; this file remains for backward-compat import paths.

使用模块 __getattr__ 动态代理，保证运行时 setattr(core.realtime_store, ...) 能在本层可见。
"""

import core.realtime_store as _core


def __getattr__(name):
    """动态代理到 core.realtime_store。"""
    if name.startswith("_"):
        raise AttributeError(name)
    try:
        return getattr(_core, name)
    except AttributeError:
        raise AttributeError(f"module 'app.realtime_store' has no attribute {name!r}")


__all__ = [
    "REALTIME_BUFFER_MAX",
    "event_loop",
    "push_realtime_msg",
    "realtime_chapter_generators",
    "realtime_diarizers",
    "realtime_full_sealed",
    "realtime_full_transcripts",
    "realtime_last_heartbeat",
    "realtime_last_sentence",
    "realtime_presence_scores",
    "realtime_queues",
    "realtime_silence_monitors",
    "realtime_silence_warnings",
    "realtime_speaker_maps",
    "realtime_summarizers",
    "realtime_transcript_buffers",
    "realtime_transcribers",
    "realtime_translations",
    "realtime_translators",
    "resolve_realtime_speaker_name",
]
