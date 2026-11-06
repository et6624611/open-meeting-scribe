"""app/routers/record_devices.py — 录音设备枚举 / 诊断 / 设置。

端点：
  GET  /api/record/devices      — 可用音频输入设备 + 当前配置
  GET  /api/record/diagnostics  — 录音环境诊断
  POST /api/record/device       — 设置录音设备

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 record.py 拆分）
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

import core.settings_store as settings_store
from core.audio import list_audio_devices

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/record/devices")
def get_audio_devices():
    """列出系统可用的音频输入设备 + 当前录音设备配置。
    List available audio input devices + current recording device config.
    """
    import platform as _platform

    from core.audio import check_ffmpeg

    devices = list_audio_devices()
    is_win = _platform.system() == "Windows"

    return {
        "devices": devices,
        "current_device": settings_store.RECORD_DEVICE,
        "platform": _platform.system(),
        "auto_detect": not settings_store.RECORD_DEVICE if is_win else False,
        "ffmpeg_available": check_ffmpeg(),
    }


@router.get("/api/record/diagnostics")
def get_recording_diagnostics():
    """录音环境诊断信息，用于排查设备检测失败问题。
    Recording environment diagnostics for troubleshooting device detection failures.
    """
    import platform as _platform
    import shutil

    from core.audio import check_ffmpeg
    from core.audio_recording import (
        _WINDOWS_DEVICE_CACHE,
        _find_windows_audio_device,
        _find_windows_audio_device_ps,
    )

    is_win = _platform.system() == "Windows"
    ffmpeg_path = shutil.which("ffmpeg")
    devices = list_audio_devices()

    diag: dict = {
        "platform": _platform.system(),
        "ffmpeg_available": check_ffmpeg(),
        "ffmpeg_path": ffmpeg_path or "",
        "current_device": settings_store.RECORD_DEVICE,
        "device_count": len(devices),
        "devices": devices,
    }

    if is_win:
        diag["windows"] = {
            "cached_device": _WINDOWS_DEVICE_CACHE,
            "ps_detection": _find_windows_audio_device_ps(),
            "ffmpeg_detection": _find_windows_audio_device(),
        }

    return diag


class RecordDeviceRequest(BaseModel):
    device: str  # 设备名称，空字符串表示自动检测 / Device name; empty string means auto-detect


@router.post("/api/record/device")
def set_record_device(req: RecordDeviceRequest):
    """设置录音设备（运行时生效并持久化到 settings.json，重启后按 settings>env>平台默认恢复；DEF-DEVICE-01-BE）。
    Set recording device (runtime effect + persisted to settings.json; restored on restart per settings > env > platform default).
    """
    # 清除 Windows 设备缓存，使下次录音使用新设备
    # Clear Windows device cache so next recording uses the new device
    import core.audio_recording as _ar
    from core.settings_store import set_record_device as _set_device
    _ar._WINDOWS_DEVICE_CACHE = None

    _set_device(req.device)
    logger.info(f"[录制] 设备已更新: '{req.device}' ({'auto-detect' if not req.device else 'manual'})")
    return {"device": req.device, "auto_detect": not req.device}
