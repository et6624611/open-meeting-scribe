"""
core/audio_recording.py — 录音控制（聚合入口）

作者 / Author: Yongliang Wang
更新 / Updated: 2026-11-06
版本 / Version: 2.0.0

按职责拆分为三个子模块，本模块为聚合入口：
- audio_devices.py  音频设备检测与列表
- audio_record.py   普通录音控制
- audio_stream.py   流式录音控制（单进程 WAV 落盘 + 文件 tail + 暂停/恢复）

所有符号通过模块级 __getattr__ 延迟转发到子模块，保持外部 import 与
monkeypatch（如 _WINDOWS_DEVICE_CACHE）兼容。
"""

from __future__ import annotations

from . import audio_devices as _devices
from . import audio_record as _record
from . import audio_stream as _stream

_SUBMODULES = (_devices, _record, _stream)

# ruff: noqa: F822 — 聚合层，符号通过 __getattr__ 动态转发到子模块
__all__ = [
    "_MACOS_DEVICE_NAMES", "_WINDOWS_DEVICE_CACHE",
    "_is_windows", "_find_windows_audio_device_ps", "_detect_windows_audio_device",
    "_should_auto_detect_on_windows", "_find_windows_audio_device",
    "_detect_macos_audio_device",
    "list_audio_devices", "_list_windows_audio_devices",
    "_list_windows_audio_devices_ps", "_list_windows_audio_devices_ffmpeg",
    "_list_macos_audio_devices",
    "_record_process", "_record_task_id", "_record_output_path", "_record_start_time",
    "_build_ffmpeg_record_cmd", "start_recording", "stop_recording",
    "is_recording", "get_recording_info",
    "_stream_process", "_stream_task_id",
    "_stream_output_path", "_stream_start_time",
    "_stream_reader_thread", "_stream_running", "_stream_paused", "_stream_pcm_callback",
    "_stream_paused_total", "_stream_pause_start",
    "_stream_cb_queue", "_stream_cb_thread", "_stream_cb_stop", "_stream_cb_dropped",
    "_build_ffmpeg_wav_cmd", "_wav_data_offset",
    "start_recording_with_stream", "_stream_reader_loop",
    "stop_recording_with_stream", "pause_recording_with_stream",
    "resume_recording_with_stream", "_raw_to_wav",
    "is_stream_recording", "get_stream_recording_info",
    "get_last_pause_duration",
]


def __getattr__(name: str):
    for m in _SUBMODULES:
        attr = getattr(m, name, None)
        if attr is not None or name in m.__dict__:
            return attr
    raise AttributeError(f"module 'core.audio_recording' has no attribute {name!r}")
