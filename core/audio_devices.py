"""
core/audio_devices.py — 音频设备检测与列表（从 audio_recording.py 拆出）
"""
"""
core/audio_recording.py — macOS 系统内录与流式录音控制

职责：
  1. macOS 系统内录：通过 ffmpeg + avfoundation 从 BlackHole 2ch 采集系统音频
  2. 流式录音：PCM pipe 输出，供实时 ASR 消费
  3. 暂停/恢复控制
  4. 音频设备列表查询

依赖：
  core.audio — check_ffmpeg
  ffmpeg（系统已装）、BlackHole 2ch（虚拟声卡）
"""

import json
import logging
import platform
import re
import subprocess

logger = logging.getLogger(__name__)



_MACOS_DEVICE_NAMES = {"BlackHole 2ch", "MacBook Pro麦克风", "MacBook Pro Microphone"}
_WINDOWS_DEVICE_CACHE: str | None = None


def _is_windows() -> bool:
    """是否运行在 Windows 平台 / Whether running on Windows"""
    return platform.system() == "Windows"


def _find_windows_audio_device_ps() -> str:
    """通过 PowerShell 枚举 Windows 音频捕获设备（不依赖 ffmpeg）。
    Enumerate Windows audio capture devices via PowerShell (ffmpeg-independent).

    分两步查询：先精确匹配麦克风关键词，失败则回退到列出所有音频输入设备。
    Two-step query: first match microphone keywords precisely; fall back to listing
    all audio input devices if the first step finds nothing.

    Returns:
        设备友好名称，未找到返回空字符串 / Device friendly name, or empty string if not found
    """
    # 麦克风关键词（用于 Python 侧匹配，比 PowerShell -match 更可靠）
    # Microphone keywords (Python-side matching is more reliable than PowerShell -match)
    _MIC_KEYWORDS = ('microphone', '麦克风', 'mic array', 'mic-in', 'line in', '线路输入')

    def _run_ps_json(ps_script: str) -> list[dict]:
        """执行 PowerShell 脚本并解析 JSON 输出（多编码回退）。
        Run PowerShell script and parse JSON output (multi-encoding fallback).

        中文版 Windows 默认代码页为 GBK (cp936)，PowerShell 输出可能不是 UTF-8。
        先尝试 UTF-8，失败则回退到 GBK，避免中文设备名被替换为乱码。
        """
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=15,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if _is_windows() else 0,
            )
            if result.returncode != 0:
                stderr_text = result.stderr.decode("utf-8", errors="replace")[:200]
                logger.warning(f"PowerShell 脚本执行失败 (exit={result.returncode}): {stderr_text}")
                return []
            raw = result.stdout
            if not raw or not raw.strip():
                return []

            # 多编码回退：UTF-8 → GBK (cp936) → latin-1 / Multi-encoding fallback
            output = None
            for enc in ("utf-8", "gbk", "latin-1"):
                try:
                    output = raw.decode(enc).strip()
                    json.loads(output)  # 验证 JSON 可解析
                    break
                except (UnicodeDecodeError, json.JSONDecodeError):
                    output = None
                    continue
            if output is None:
                logger.warning("PowerShell 输出无法解码（尝试了 utf-8/gbk/latin-1）")
                return []

            data = json.loads(output)
            if isinstance(data, dict):
                data = [data]
            return data if isinstance(data, list) else []
        except FileNotFoundError:
            logger.warning("PowerShell 不可用")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("PowerShell 设备枚举超时（15s）")
            return []
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning(f"PowerShell 设备枚举异常: {e}")
            return []

    def _pick_mic(devices: list[dict], prefer_ok_status: bool = True) -> str:
        """从设备列表中优先选择麦克风设备。"""
        if not devices:
            return ""
        # 优先 Status=OK 且名称匹配麦克风关键词
        if prefer_ok_status:
            for item in devices:
                name = item.get("FriendlyName", "")
                status = item.get("Status", "")
                if name and status == "OK" and any(kw in name.lower() for kw in _MIC_KEYWORDS):
                    logger.info(f"PowerShell 检测到麦克风设备: {name} (Status={status})")
                    return name
        # 回退：任何名称匹配麦克风关键词的设备
        for item in devices:
            name = item.get("FriendlyName", "")
            if name and any(kw in name.lower() for kw in _MIC_KEYWORDS):
                logger.info(f"PowerShell 检测到麦克风设备（非 OK 状态）: {name}")
                return name
        # 回退：Status=OK 的任何音频设备
        if prefer_ok_status:
            for item in devices:
                name = item.get("FriendlyName", "")
                status = item.get("Status", "")
                if name and status == "OK":
                    logger.info(f"PowerShell 回退到音频设备: {name} (Status={status})")
                    return name
        # 最终回退：第一个有名称的设备
        for item in devices:
            name = item.get("FriendlyName", "")
            if name:
                logger.info(f"PowerShell 回退到音频设备（无状态过滤）: {name}")
                return name
        return ""

    # ── 策略 A: Win32_PnPEntity + AudioEndpoint（精确）── / ── Strategy A: Win32_PnPEntity + AudioEndpoint (precise) ──
    ps_narrow = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.PNPClass -eq 'AudioEndpoint' } | "
        "Select-Object FriendlyName, Status | "
        "ConvertTo-Json"
    )
    devices = _run_ps_json(ps_narrow)
    if devices:
        mic = _pick_mic(devices)
        if mic:
            return mic
        logger.info(f"PowerShell AudioEndpoint 找到 {len(devices)} 个设备但无匹配麦克风")

    # ── 策略 B: Get-PnpDevice AudioEndpoint（更现代的 API）── / ── Strategy B: Get-PnpDevice AudioEndpoint (more modern API) ──
    ps_pnp = (
        "Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName, Status | "
        "ConvertTo-Json"
    )
    devices = _run_ps_json(ps_pnp)
    if devices:
        mic = _pick_mic(devices, prefer_ok_status=False)
        if mic:
            return mic

    # ── 策略 C: Win32_SoundDevice（更宽泛的设备类别）── / ── Strategy C: Win32_SoundDevice (broader device class) ──
    ps_sound = (
        "Get-CimInstance Win32_SoundDevice | "
        "Select-Object Name, Status | "
        "ConvertTo-Json"
    )
    devices = _run_ps_json(ps_sound)
    if devices:
        # Win32_SoundDevice 使用 Name 而非 FriendlyName
        sound_devices = [{"FriendlyName": d.get("Name", ""), "Status": d.get("Status", "")} for d in devices]
        mic = _pick_mic(sound_devices)
        if mic:
            return mic

    logger.warning("PowerShell 所有策略均未找到音频输入设备")
    return ""


def _detect_windows_audio_device() -> str:
    """检测 Windows 音频输入设备（带缓存 + 双路并行 + ffmpeg 优先验证）。
    Detect Windows audio input device (cached + dual-path parallel + ffmpeg preference).

    策略 / Strategy:
      1. 缓存命中（同一进程生命周期内只检测一次）
      2. 并行运行 PowerShell WMI 和 ffmpeg dshow
      3. 优先使用 ffmpeg dshow 结果（设备名保证兼容录音命令）
      4. ffmpeg 失败时回退到 PowerShell 结果（最佳努力）
      5. 两者都失败则不缓存（允许用户插拔设备后重试）
    """
    global _WINDOWS_DEVICE_CACHE
    if _WINDOWS_DEVICE_CACHE is not None:
        logger.debug(f"使用缓存的 Windows 音频设备: {_WINDOWS_DEVICE_CACHE}")
        return _WINDOWS_DEVICE_CACHE

    # 双路并行检测：同时运行 PowerShell 和 ffmpeg，不互相阻塞
    # Dual-path detection: run both PowerShell and ffmpeg, neither blocks the other
    ps_device = ""
    ff_device = ""

    # 策略 A: PowerShell WMI（不依赖 ffmpeg，PyInstaller 环境更可靠）
    ps_device = _find_windows_audio_device_ps()
    if ps_device:
        logger.info(f"[设备检测] PowerShell 检测到: {ps_device}")

    # 策略 B: ffmpeg dshow（设备名保证兼容录音命令）
    ff_device = _find_windows_audio_device()
    if ff_device:
        logger.info(f"[设备检测] ffmpeg dshow 检测到: {ff_device}")

    # 优先使用 ffmpeg dshow 结果（设备名与录音命令 100% 兼容）
    # Prefer ffmpeg dshow result (device name 100% compatible with recording command)
    if ff_device:
        _WINDOWS_DEVICE_CACHE = ff_device
        return ff_device

    # ffmpeg 失败时回退到 PowerShell（最佳努力，设备名可能略有差异）
    # Fall back to PowerShell when ffmpeg fails (best effort, name may differ slightly)
    if ps_device:
        logger.warning(f"[设备检测] ffmpeg dshow 失败，使用 PowerShell 结果（设备名可能略有差异）: {ps_device}")
        _WINDOWS_DEVICE_CACHE = ps_device
        return ps_device

    logger.error("[设备检测] 所有策略均失败（PowerShell + ffmpeg dshow），无法自动检测音频设备")
    # 不缓存空结果 — 允许用户插拔设备后重试，无需重启应用
    # Don't cache empty result — allow retry after user plugs/unplugs device without restarting app
    return ""


def _should_auto_detect_on_windows(device: str) -> bool:
    """在 Windows 上判断是否需要自动检测设备。
    On Windows, determine whether the device should be auto-detected.

    当设备名为空、为 macOS 专属设备名、或不存在于 Windows DirectShow 设备列表时，返回 True。
    """
    if not device:
        return True
    if device in _MACOS_DEVICE_NAMES:
        return True
    return False


def _find_windows_audio_device() -> str:
    """在 Windows 上自动查找可用的音频输入设备。
    Auto-detect an available audio input device on Windows.

    优先选择包含 'stereo mix'/'立体声混音' 的设备（系统内录最佳），
    其次选择第一个可用的音频输入设备。
    Prefer 'Stereo Mix' (system loopback); fall back to first available input.
    """
    cmd = ["ffmpeg", "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "dummy"]
    try:
        # 使用 UTF-8 编码读取，errors="replace" 防止非法字节导致解码失败
        # Use UTF-8 encoding to read, errors="replace" to prevent decode failures on invalid bytes
        result = subprocess.run(
            cmd, capture_output=True, timeout=10,
            stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace",
        )
        output = result.stderr  # dshow 设备列表输出在 stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""

    devices = []
    in_audio = False
    for line in output.split("\n"):
        if "DirectShow audio devices" in line:
            in_audio = True
            continue
        if "DirectShow video devices" in line:
            in_audio = False
            continue
        if in_audio:
            match = re.search(r'\[.*?\]\s+"(.+?)"', line)
            if match:
                devices.append(match.group(1))

    if not devices:
        return ""

    # 优先选择立体声混音（系统内录） / Prefer Stereo Mix (system loopback)
    for d in devices:
        if "stereo mix" in d.lower() or "立体声混音" in d:
            return d

    # 回退到第一个可用设备 / Fall back to first available
    return devices[0]


def list_audio_devices() -> list[dict]:
    """
    列出系统可用的音频输入设备。
    List available audio input devices.

    macOS: avfoundation
    Windows: dshow (DirectShow)

    Returns:
        [{"index": 0, "name": "设备名", "type": "audio"}, ...]
    """
    if _is_windows():
        return _list_windows_audio_devices()
    return _list_macos_audio_devices()


def _list_windows_audio_devices() -> list[dict]:
    """列出 Windows 音频输入设备（PowerShell 优先，ffmpeg 后备）。
    List Windows audio input devices (PowerShell first, ffmpeg fallback).
    """
    # 优先使用 PowerShell（不依赖 ffmpeg，PyInstaller 环境更可靠）
    # Prefer PowerShell (ffmpeg-independent, more reliable in PyInstaller environments)
    devices = _list_windows_audio_devices_ps()
    if devices:
        return devices

    # 后备：ffmpeg dshow
    logger.info("PowerShell 设备列表为空，回退到 ffmpeg dshow")
    return _list_windows_audio_devices_ffmpeg()


def _list_windows_audio_devices_ps() -> list[dict]:
    """通过 PowerShell 列出 Windows 音频输入设备（宽泛枚举 + Python 侧排序）。
    List Windows audio input devices (broad enumeration + Python-side sorting).

    不再在 PowerShell 端过滤设备名称，而是枚举所有 AudioEndpoint 设备，
    在 Python 侧按麦克风关键词排序。这样能覆盖更多设备类型。
    """
    ps_script = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.PNPClass -eq 'AudioEndpoint' } | "
        "Select-Object FriendlyName, Status | "
        "ConvertTo-Json"
    )
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=15,
            stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if _is_windows() else 0,
        )
        if result.returncode != 0:
            return []
        output = result.stdout.strip()
        if not output:
            return []

        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]

        _MIC_KEYWORDS = ('microphone', '麦克风', 'mic array', 'mic-in')
        all_devices = []
        for item in data:
            name = item.get("FriendlyName", "")
            if name:
                all_devices.append({"name": name, "status": item.get("Status", "")})

        # 排序：麦克风 + OK 状态优先
        def _sort_key(d: dict) -> tuple:
            is_mic = any(kw in d["name"].lower() for kw in _MIC_KEYWORDS)
            is_ok = d["status"] == "OK"
            return (not is_mic, not is_ok)  # False < True，所以取反后排前面
        all_devices.sort(key=_sort_key)

        return [{"index": idx, "name": d["name"], "type": "audio"} for idx, d in enumerate(all_devices)]
    except Exception as e:
        logger.warning(f"PowerShell 设备列表异常: {e}")
        return []


def _list_windows_audio_devices_ffmpeg() -> list[dict]:
    """通过 ffmpeg dshow 列出 Windows DirectShow 音频输入设备。"""
    cmd = ["ffmpeg", "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "dummy"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=10,
            stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace",
        )
        output = result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []

    devices = []
    in_audio = False
    idx = 0
    for line in output.split("\n"):
        if "DirectShow audio devices" in line:
            in_audio = True
            continue
        if "DirectShow video devices" in line:
            in_audio = False
            continue
        if in_audio:
            match = re.search(r'\[.*?\]\s+"(.+?)"', line)
            if match:
                devices.append({
                    "index": idx,
                    "name": match.group(1),
                    "type": "audio",
                })
                idx += 1
    return devices


def _list_macos_audio_devices() -> list[dict]:
    """列出 macOS avfoundation 音频输入设备。"""
    cmd = ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
        output = result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    devices = []
    in_audio = False
    for line in output.split("\n"):
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if "AVFoundation video devices" in line:
            in_audio = False
            continue
        if in_audio:
            # 格式: [AVFoundation indev @ 0x...] [0] BlackHole 2ch
            match = re.search(r'\[(\d+)\]\s+(.+)', line)
            if match:
                devices.append({
                    "index": int(match.group(1)),
                    "name": match.group(2).strip(),
                    "type": "audio",
                })

    return devices


def _detect_macos_audio_device() -> str:
    """macOS "自动选择"解析：返回第一个非 BlackHole 的物理音频输入设备。
    Resolve macOS auto-select to the first non-BlackHole physical input device.

    BlackHole 是虚拟声卡（系统内录专用），当默认会静默录到空音频；
    硬编码 "MacBook Pro麦克风" 会在设备改名时静默失败，故动态枚举。
    """
    for d in _list_macos_audio_devices():
        name = d.get("name", "")
        if name and not name.startswith("BlackHole"):
            return name
    return ""
