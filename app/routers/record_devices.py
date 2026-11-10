"""app/routers/record_devices.py — 录音设备枚举 / 诊断 / 设置。

端点：
  GET  /api/record/devices      — 可用音频输入设备 + 当前配置 + 候选条目列表
  GET  /api/record/diagnostics  — 录音环境诊断
  POST /api/record/device       — 设置录音来源（设备名 或 保留值）

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 record.py 拆分）
"""

import logging
import platform as _platform

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import core.settings_store as settings_store
from core.audio import check_ffmpeg, list_audio_devices

logger = logging.getLogger(__name__)

router = APIRouter()

# macOS 系统内录的固定设备（虚拟声卡） / Fixed virtual device for macOS system audio capture
SYSTEM_LOOPBACK_DEVICE = "BlackHole 2ch"

# 保留值：不是真实设备名，而是让后端走特殊分支
# Sentinel value: not a real device name; the backend resolves it specially
SENTINEL_SYSTEM = "__system__"  # 系统内录 → 替换成 BlackHole
SENTINEL_AUTO = ""               # 自动选择 → 交给平台默认解析


def _current_entry(device: str, is_win: bool) -> str:
    """把当前 device 映射成 UI 里选中的条目值。
    Map the current device string to the entry value selected in the UI list.
    """
    if not device:
        return SENTINEL_AUTO
    if not is_win and device.startswith("BlackHole"):
        return SENTINEL_SYSTEM
    return device


def _build_entries(devices: list[dict], current_device: str, is_win: bool) -> list[dict]:
    """构造 UI 列表条目（自动 / 系统内录 / 具体设备）。
    Build the unified UI entry list (auto / system capture / concrete devices).
    """
    entries: list[dict] = []

    # 1. 自动选择
    # 平台默认动态取第一个非 BlackHole 物理输入设备——硬编码具体型号
    # 会在设备改名时让副标题撒谎（音频层按同样规则解析，保持承诺一致）。
    if is_win:
        platform_default = ""
    else:
        platform_default = next(
            (
                d.get("name", "")
                for d in devices
                if d.get("name", "") and not d.get("name", "").startswith("BlackHole")
            ),
            "",
        )
    auto_current = current_device or platform_default
    entries.append({
        "value": SENTINEL_AUTO,
        "label": "auto",
        "title": "自动选择",
        "subtitle": f"当前：{auto_current or '系统默认输入'}",
        "platform": None,  # 跨平台
    })

    # 2. 系统内录（仅 macOS，需 BlackHole）
    if not is_win:
        blackhole_present = any(
            d.get("name", "").startswith("BlackHole") for d in devices
        )
        entries.append({
            "value": SENTINEL_SYSTEM,
            "label": "system",
            "title": "系统内录",
            "subtitle": (
                f"设备 {SYSTEM_LOOPBACK_DEVICE} {'✓ 已检测到' if blackhole_present else '未检测到，请先安装 BlackHole'}"
            ),
            "platform": "Darwin",
        })

    # 3. 具体设备（排除 BlackHole，它已经在"系统内录"里了）
    for d in devices:
        name = d.get("name", "")
        if name.startswith("BlackHole"):
            continue
        entries.append({
            "value": name,
            "label": "device",
            "title": name,
            "subtitle": "",
            "platform": None,
        })

    return entries


@router.get("/api/record/devices")
def get_audio_devices():
    """列出系统可用的音频输入设备 + 当前录音设备配置 + UI 候选条目。
    List available audio input devices + current config + unified UI entry list.
    """
    devices = list_audio_devices()
    is_win = _platform.system() == "Windows"
    device, source = settings_store.get_record_device()

    return {
        "devices": devices,
        # 当前持久化的原始 device 值（含空串 / __system__ 可能已解析） / Raw persisted device value
        "current_device": settings_store.RECORD_DEVICE,
        # UI 选中的条目值（空串=自动，__system__=系统内录，否则是设备名）/ UI-selected entry value
        "current_entry": _current_entry(device, is_win),
        # 生效来源：settings / env / platform-default / Where the effective device came from
        "effective_source": source,
        "platform": _platform.system(),
        "auto_detect": not device if is_win else False,
        "ffmpeg_available": check_ffmpeg(),
        # 给前端渲染模态框用 / Entries for the modal list UI
        "entries": _build_entries(devices, settings_store.RECORD_DEVICE, is_win),
    }


@router.get("/api/record/diagnostics")
def get_recording_diagnostics():
    """录音环境诊断信息，用于排查设备检测失败问题。
    Recording environment diagnostics for troubleshooting device detection failures.
    """
    import shutil

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
    device: str = ""
    # 设备名，空串=自动选择，__system__=系统内录（macOS）
    # Device name; ""=auto, __system__=system capture on macOS


@router.post("/api/record/device")
def set_record_device(req: RecordDeviceRequest):
    """设置录音来源（运行时生效并持久化到 settings.json）。
    Set recording source (runtime effect + persisted to settings.json).
    """
    import core.audio_recording as _ar
    from core.settings_store import set_record_device as _set_device

    _ar._WINDOWS_DEVICE_CACHE = None
    device = req.device

    # 保留值合法性校验 / Sentinel validation
    if device == SENTINEL_SYSTEM and _platform.system() != "Darwin":
        raise HTTPException(400, "系统内录依赖 macOS 的 BlackHole 虚拟声卡")

    _set_device(device)
    entry = _current_entry(device, _platform.system() == "Windows")
    logger.info(f"[录制] 设备已更新: '{device}' (entry={entry}, source=settings)")
    return {"device": device, "entry": entry, "auto_detect": not device}
