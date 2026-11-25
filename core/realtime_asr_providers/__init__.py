"""core/realtime_asr_providers — 实时 ASR 多厂商适配层。

只服务「录音过程中的预览」链路；会后批处理仍走 core/transcribe.py 的 DashScope。
"""

from .base import (
    AudioChunker,
    RealtimeProviderSpec,
    RealtimeSessionClosed,
    WebSocketProviderBase,
)
from .registry import create_provider, get_spec, list_public_specs

__all__ = [
    "AudioChunker",
    "RealtimeProviderSpec",
    "RealtimeSessionClosed",
    "WebSocketProviderBase",
    "create_provider",
    "get_spec",
    "list_public_specs",
]
