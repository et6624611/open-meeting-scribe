"""
tests/test_record_sentinel_contract.py — 录音来源保留值契约回归

重构后单一真实来源：record.device 存设备名字符串 或 保留值，UI 列表
由后端反推得到。本文件锁定以下行为不可回退：

  ┌──────────────────────┬─────────────────────────────────────────┐
  │ record.device 持久化  │ 解析结果（entry 层）                      │
  ├──────────────────────┼─────────────────────────────────────────┤
  │ ""                   │ 自动选择                                    │
  │ "__system__"         │ 系统内录（仅 macOS，audio_stream 里解析成 BlackHole） │
  │ "MacBook Pro麦克风"  │ 具体设备（直接透传）                         │
  └──────────────────────┴─────────────────────────────────────────┘

同时覆盖：
  - _build_entries 构造时自动排除 BlackHole（它由 system 行统一呈现）
  - 非 macOS 平台拒绝 "__system__"（400）
  - 平台默认不再硬编码 "MacBook Pro麦克风"，而是空串

隔离口径：monkeypatch settings_store.SETTINGS_FILE → tmp_path，
不触碰真实 data/settings.json；audio 枚举和 ffmpeg 全 mock。
"""

from __future__ import annotations

import json

import pytest

# ═══════════════════════════════════════════════════════════════════════
# 共享夹具
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """双层 SETTINGS_FILE → tmp_path，清 RECORD_DEVICE env。"""
    import app.settings_store as ss
    import core.settings_store as _core_ss

    sf = tmp_path / "settings.json"
    monkeypatch.setattr(ss, "SETTINGS_FILE", sf)
    monkeypatch.setattr(_core_ss, "SETTINGS_FILE", sf)
    monkeypatch.delenv("RECORD_DEVICE", raising=False)
    return ss, sf


@pytest.fixture(autouse=True)
def reset_audio_module_state():
    """audio_stream / audio_record 用模块级全局变量跟踪录制状态，
    fake Popen 的 poll() 永远返回 None 导致 pytest 跨测试串状态。
    每个测试前后重置这些哨兵变量。"""
    import core.audio_record as _ar
    import core.audio_stream as _as

    def _reset():
        _ar._record_process = None
        _ar._record_task_id = None
        _ar._record_output_path = None
        _ar._record_start_time = None
        _as._stream_process = None
        _as._stream_task_id = None
        _as._stream_output_path = None
        _as._stream_start_time = None
        _as._stream_running = False
        _as._stream_pcm_callback = None
        _as._stream_reader_thread = None
        _as._stream_paused = False
        _as._stream_paused_total = 0.0
        _as._stream_pause_start = None
        _as._stream_cb_queue = None
        _as._stream_cb_thread = None
        import threading
        _as._stream_cb_stop = threading.Event()
        _as._stream_cb_dropped = 0

    _reset()
    yield
    _reset()


@pytest.fixture()
def mocked_devices(monkeypatch):
    """固定设备列表：1 个 BlackHole + 3 个具体麦克风。"""
    devices = [
        {"index": 0, "name": "BlackHole 2ch", "type": "input"},
        {"index": 1, "name": "MacBook Pro麦克风", "type": "input"},
        {"index": 2, "name": '"My iPhone"的麦克风', "type": "input"},
        {"index": 3, "name": "Microsoft Teams Audio", "type": "input"},
    ]
    import app.routers.record_devices as rd

    monkeypatch.setattr(rd, "list_audio_devices", lambda: devices)
    monkeypatch.setattr(rd, "check_ffmpeg", lambda: True)
    return devices


# ═══════════════════════════════════════════════════════════════════════
# _current_entry：device 字符串 → UI entry value
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "device,is_win,expected",
    [
        ("", False, ""),              # 空串 → auto
        ("", True, ""),
        ("BlackHole 2ch", False, "__system__"),
        ("BlackHole 64ch", False, "__system__"),
        ("BlackHole 2ch", True, "BlackHole 2ch"),   # Windows 不识别 BlackHole → 当具体设备
        ("MacBook Pro麦克风", False, "MacBook Pro麦克风"),
        ("SomeUSBMic", True, "SomeUSBMic"),
    ],
)
def test_current_entry_mapping(device, is_win, expected):
    from app.routers.record_devices import _current_entry

    assert _current_entry(device, is_win) == expected


# ═══════════════════════════════════════════════════════════════════════
# _build_entries：UI 候选列表构造
# ═══════════════════════════════════════════════════════════════════════


def test_build_entries_macos_has_system_and_excludes_blackhole(mocked_devices):
    from app.routers.record_devices import _build_entries

    entries = _build_entries(mocked_devices, "BlackHole 2ch", is_win=False)

    values = [e["value"] for e in entries]
    # 必须有 auto / __system__ / 3 个具体设备，且具体设备列表中不含 BlackHole
    assert "" in values
    assert "__system__" in values
    # 具体设备条目数应等于输入减去 BlackHole（4 - 1 = 3）
    assert sum(1 for e in entries if e["label"] == "device") == 3
    assert not any(e["value"].startswith("BlackHole") for e in entries)
    # BlackHole 状态已写入 system 行副标题
    sys_entry = next(e for e in entries if e["value"] == "__system__")
    assert "✓ 已检测到" in sys_entry["subtitle"]
    assert "BlackHole" in sys_entry["subtitle"]
    # auto 行副标题显示当前解析设备
    auto_entry = next(e for e in entries if e["value"] == "")
    assert "BlackHole 2ch" in auto_entry["subtitle"]


def test_build_entries_macos_no_blackhole_uses_not_detected_subtitle(monkeypatch):
    devices = [{"index": 0, "name": "MacBook Pro麦克风", "type": "input"}]
    import app.routers.record_devices as rd
    monkeypatch.setattr(rd, "list_audio_devices", lambda: devices)

    entries = rd._build_entries(devices, "", is_win=False)
    sys_entry = next(e for e in entries if e["value"] == "__system__")
    assert "未检测到" in sys_entry["subtitle"]


def test_build_entries_windows_has_no_system_row(monkeypatch):
    devices = [{"index": 0, "name": "USB Mic", "type": "input"}]
    import app.routers.record_devices as rd
    monkeypatch.setattr(rd, "list_audio_devices", lambda: devices)

    entries = rd._build_entries(devices, "", is_win=True)
    values = [e["value"] for e in entries]
    assert "__system__" not in values
    assert "" in values
    assert sum(1 for e in entries if e["label"] == "device") == 1


def test_build_entries_auto_subtitle_falls_back_to_platform_default(mocked_devices):
    from app.routers.record_devices import _build_entries

    # 空 device 时，auto 行副标题显示平台默认设备（macOS = "MacBook Pro麦克风"）
    entries = _build_entries(mocked_devices, "", is_win=False)
    auto_entry = next(e for e in entries if e["value"] == "")
    assert "MacBook Pro麦克风" in auto_entry["subtitle"]


# ═══════════════════════════════════════════════════════════════════════
# GET /api/record/devices：契约回显
# ═══════════════════════════════════════════════════════════════════════


def test_get_devices_echoes_current_entry_and_entries(isolated_settings, monkeypatch, mocked_devices):
    ss, sf = isolated_settings
    # set_record_device 同时更新持久化文件和 core 层 RECORD_DEVICE 快照；
    # 仅 save_record_device 只写文件，快照仍为模块初始化时的默认值，
    # get_audio_devices() 读的是 RECORD_DEVICE 快照，会对不上。
    import core.settings_store as store

    store.set_record_device("__system__")

    from app.routers.record_devices import get_audio_devices

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    resp = get_audio_devices()

    assert resp["current_device"] == "__system__"
    assert resp["current_entry"] == "__system__"
    assert resp["effective_source"] == "settings"
    assert resp["platform"] == "Darwin"
    assert resp["ffmpeg_available"] is True
    # entries 有 auto + system + 3 个 device
    entries = resp["entries"]
    assert len(entries) == 5
    values = {e["value"] for e in entries}
    assert "" in values and "__system__" in values
    assert not any(v.startswith("BlackHole") for v in values if v)


def test_get_devices_returns_empty_string_platform_default_when_unset(
    isolated_settings, monkeypatch, mocked_devices
):
    """重构裁决：平台默认 = 空串（不再硬编码 MacBook 麦克风）。"""
    import core.settings_store as _core_ss
    from app.routers.record_devices import get_audio_devices

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    # 清掉已有的 RECORD_DEVICE 快照，让 get_record_device 走到 env/default 分支
    monkeypatch.delenv("RECORD_DEVICE", raising=False)
    _core_ss.RECORD_DEVICE = ""  # 运行时常量也要归零

    resp = get_audio_devices()
    assert resp["current_device"] == ""
    assert resp["current_entry"] == ""
    assert resp["effective_source"] == "platform-default"


# ═══════════════════════════════════════════════════════════════════════
# POST /api/record/device：保留值合法性
# ═══════════════════════════════════════════════════════════════════════


def test_post_accepts_sentinel_system_on_macos(isolated_settings, monkeypatch):
    ss, sf = isolated_settings


    from app.routers.record_devices import RecordDeviceRequest, set_record_device

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    resp = set_record_device(RecordDeviceRequest(device="__system__"))
    assert resp["entry"] == "__system__"
    data = json.loads(sf.read_text(encoding="utf-8"))
    assert data["record"]["device"] == "__system__"


def test_post_rejects_sentinel_system_on_windows(isolated_settings, monkeypatch):
    ss, sf = isolated_settings

    from fastapi import HTTPException

    from app.routers.record_devices import RecordDeviceRequest, set_record_device

    monkeypatch.setattr("platform.system", lambda: "Windows")
    with pytest.raises(HTTPException) as excinfo:
        set_record_device(RecordDeviceRequest(device="__system__"))
    assert excinfo.value.status_code == 400
    assert "macOS" in excinfo.value.detail


def test_post_accepts_empty_string_for_auto(isolated_settings, monkeypatch):
    ss, sf = isolated_settings

    from app.routers.record_devices import RecordDeviceRequest, set_record_device

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    resp = set_record_device(RecordDeviceRequest(device=""))
    assert resp["entry"] == ""
    assert resp["auto_detect"] is True
    data = json.loads(sf.read_text(encoding="utf-8"))
    assert data["record"]["device"] == ""


def test_post_accepts_concrete_device_name(isolated_settings, monkeypatch):
    ss, sf = isolated_settings

    from app.routers.record_devices import RecordDeviceRequest, set_record_device

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    resp = set_record_device(RecordDeviceRequest(device="MacBook Pro麦克风"))
    assert resp["entry"] == "MacBook Pro麦克风"
    data = json.loads(sf.read_text(encoding="utf-8"))
    assert data["record"]["device"] == "MacBook Pro麦克风"


# ═══════════════════════════════════════════════════════════════════════
# settings_store：平台默认裁决（空串，不再硬编码设备名）
# ═══════════════════════════════════════════════════════════════════════


def test_platform_default_is_empty_string_not_macbook_mic(isolated_settings):
    ss, sf = isolated_settings
    # 无 settings、无 env → 平台默认 = ""
    device, source = ss.get_record_device()
    assert device == ""
    assert source == "platform-default"


def test_priority_chain_sentinel_values_inherit_settings_over_env(isolated_settings, monkeypatch):
    """__system__ / "" 都是 settings 显式选择，优先级应高于 env。"""
    ss, sf = isolated_settings
    monkeypatch.setenv("RECORD_DEVICE", "ShouldBeIgnored")
    ss.save_record_device("__system__")
    device, source = ss.get_record_device()
    assert device == "__system__" and source == "settings"


def test_existing_record_persistence_round_trip(isolated_settings):
    """__system__ 存下来再读回来必须一字不差（保留值不能被反解析改写成真实设备）。"""
    ss, sf = isolated_settings
    import core.settings_store as store

    store.set_record_device("__system__")
    device, source = store.get_record_device()
    assert (device, source) == ("__system__", "settings")
    assert store.RECORD_DEVICE == "__system__"


# ═══════════════════════════════════════════════════════════════════════
# audio_stream / audio_record：__system__ 保留值解析
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "module_name",
    ["core.audio_stream", "core.audio_record"],
)
def test_sentinel_system_resolves_to_blackhole_on_macos(
    module_name, isolated_settings, monkeypatch, tmp_path
):
    """device="__system__" 在 macOS 上应解析成 BlackHole 2ch 再交给 ffmpeg。"""
    ss, sf = isolated_settings
    import core.settings_store as store

    store.set_record_device("__system__")
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    import subprocess

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        # 返回最小 mock Popen，仅 poll() 返回 None 让调用方走到 start_time 赋值
        class _FakeProc:
            def poll(self):
                return None
            def kill(self):
                pass
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    # check_ffmpeg 在 audio_stream/audio_record 中是函数内延迟 `from core.audio import`，
    # 所以 monkeypatch 目标必须是 core.audio 模块
    import importlib

    import core.audio as _caudio

    mod = importlib.import_module(module_name)
    monkeypatch.setattr(_caudio, "check_ffmpeg", lambda: True)

    # 两个模块的入口函数签名不同：
    #   audio_record.start_recording(device, output_dir, task_id)
    #   audio_stream.start_recording_with_stream(device, output_dir, task_id, pcm_callback)
    if module_name.endswith("audio_stream"):
        import uuid
        try:
            mod.start_recording_with_stream(
                device="__system__", output_dir=tmp_path, task_id=uuid.uuid4().hex[:8]
            )
        except Exception:
            # 真 ffmpeg 子进程不存在，start 里还会读 stderr——我们只关心 Popen 调用时的 device 参数。
            # 抛错无所谓，Popen 已经被捕获。
            pass
    else:
        try:
            mod.start_recording(device="__system__", output_dir=tmp_path)
        except Exception:
            pass

    assert captured, "subprocess.Popen 未被调用"
    cmd = captured["cmd"]
    # ffmpeg 命令里 avfoundation 输入字符串必须包含 BlackHole 2ch
    # 命令形如 ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":BlackHole 2ch", ...]
    assert ":BlackHole 2ch" in " ".join(cmd), f"cmd 未包含 BlackHole: {cmd}"


@pytest.mark.parametrize(
    "module_name",
    ["core.audio_stream", "core.audio_record"],
)
def test_sentinel_system_rejected_on_windows(module_name, monkeypatch):
    """__system__ 是 macOS 专属保留值，Windows 调用应抛 RuntimeError。"""
    import importlib

    monkeypatch.setattr("platform.system", lambda: "Windows")
    import core.audio as _caudio
    mod = importlib.import_module(module_name)
    monkeypatch.setattr(_caudio, "check_ffmpeg", lambda: True)

    with pytest.raises(RuntimeError) as excinfo:
        if module_name.endswith("audio_stream"):
            mod.start_recording_with_stream(device="__system__", output_dir="/tmp")
        else:
            mod.start_recording(device="__system__", output_dir="/tmp")
    assert "macOS" in str(excinfo.value) or "BlackHole" in str(excinfo.value)


@pytest.mark.parametrize(
    "module_name",
    ["core.audio_stream", "core.audio_record"],
)
def test_device_none_falls_back_to_get_record_device_sentinel(
    module_name, isolated_settings, monkeypatch, tmp_path
):
    """device=None → get_record_device() 返回的保留值应被正确解析。"""
    ss, sf = isolated_settings
    import subprocess

    import core.settings_store as store

    store.set_record_device("__system__")
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd

        class _FakeProc:
            def poll(self):
                return None
            def kill(self):
                pass
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    import importlib

    import core.audio as _caudio

    mod = importlib.import_module(module_name)
    monkeypatch.setattr(_caudio, "check_ffmpeg", lambda: True)

    try:
        if module_name.endswith("audio_stream"):
            import uuid

            mod.start_recording_with_stream(
                device=None, output_dir=tmp_path, task_id=uuid.uuid4().hex[:8]
            )
        else:
            mod.start_recording(device=None, output_dir=tmp_path)
    except Exception:
        pass

    assert captured, "subprocess.Popen 未被调用"
    assert ":BlackHole 2ch" in " ".join(captured["cmd"])


# ═══════════════════════════════════════════════════════════════════════
# macOS 空串（自动选择）→ 动态解析成第一个非 BlackHole 物理输入设备
# ═══════════════════════════════════════════════════════════════════════


def test_detect_macos_audio_device_skips_blackhole(monkeypatch):
    """自动选择必须跳过 BlackHole——它是虚拟声卡，当默认会静默录空音频。"""
    import core.audio_devices as ad

    monkeypatch.setattr(
        ad,
        "_list_macos_audio_devices",
        lambda: [
            {"index": 0, "name": "BlackHole 2ch", "type": "audio"},
            {"index": 1, "name": "MacBook Pro麦克风", "type": "audio"},
        ],
    )
    assert ad._detect_macos_audio_device() == "MacBook Pro麦克风"


def test_detect_macos_audio_device_empty_when_only_blackhole(monkeypatch):
    """机器上只有 BlackHole 时返回空串，让上层报"设备未配置"而不是静默录空。"""
    import core.audio_devices as ad

    monkeypatch.setattr(
        ad,
        "_list_macos_audio_devices",
        lambda: [{"index": 0, "name": "BlackHole 2ch", "type": "audio"}],
    )
    assert ad._detect_macos_audio_device() == ""


@pytest.mark.parametrize(
    "module_name",
    ["core.audio_stream", "core.audio_record"],
)
def test_empty_device_auto_resolves_to_first_non_blackhole_on_macos(
    module_name, isolated_settings, monkeypatch, tmp_path
):
    """device=None + settings 空串（自动选择）在 macOS 上应解析成第一个非 BlackHole 设备。"""
    ss, sf = isolated_settings
    import core.settings_store as store

    store.set_record_device("")  # 自动选择
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    import subprocess

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd

        class _FakeProc:
            def poll(self):
                return None
            def kill(self):
                pass
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    import importlib

    import core.audio as _caudio

    mod = importlib.import_module(module_name)
    monkeypatch.setattr(_caudio, "check_ffmpeg", lambda: True)
    monkeypatch.setattr(mod, "_detect_macos_audio_device", lambda: "MacBook Pro麦克风")

    try:
        if module_name.endswith("audio_stream"):
            import uuid

            mod.start_recording_with_stream(
                device=None, output_dir=tmp_path, task_id=uuid.uuid4().hex[:8]
            )
        else:
            mod.start_recording(device=None, output_dir=tmp_path)
    except Exception:
        pass

    assert captured, "subprocess.Popen 未被调用"
    assert ":MacBook Pro麦克风" in " ".join(captured["cmd"])


@pytest.mark.parametrize(
    "module_name",
    ["core.audio_stream", "core.audio_record"],
)
def test_empty_device_no_macos_devices_raises_macos_specific_message(
    module_name, isolated_settings, monkeypatch, tmp_path
):
    """macOS 自动选择枚举不到设备时，错误文案必须是 macOS 指引（不许再写死 Windows）。"""
    ss, sf = isolated_settings
    import core.settings_store as store

    store.set_record_device("")
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    import importlib

    import core.audio as _caudio

    mod = importlib.import_module(module_name)
    monkeypatch.setattr(_caudio, "check_ffmpeg", lambda: True)
    monkeypatch.setattr(mod, "_detect_macos_audio_device", lambda: "")

    with pytest.raises(RuntimeError) as excinfo:
        if module_name.endswith("audio_stream"):
            mod.start_recording_with_stream(device=None, output_dir=tmp_path)
        else:
            mod.start_recording(device=None, output_dir=tmp_path)
    msg = str(excinfo.value)
    assert "macOS" in msg
    assert "Windows" not in msg
