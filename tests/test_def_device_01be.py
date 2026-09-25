"""
tests/test_def_device_01be.py — DEF-DEVICE-01-BE 录音设备持久化回归（验收 §2 四条）

隔离口径：monkeypatch settings_store.SETTINGS_FILE → tmp_path（同 test_llm_selfhost 夹具惯例），
不触碰真实 data/settings.json。
"""
import json

import pytest


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """把 SETTINGS_FILE 指到临时路径并清除 RECORD_DEVICE 环境变量。"""
    import app.settings_store as ss

    sf = tmp_path / "settings.json"
    monkeypatch.setattr(ss, "SETTINGS_FILE", sf)
    monkeypatch.delenv("RECORD_DEVICE", raising=False)
    return ss, sf


def test_save_then_reload_restores_device(isolated_settings):
    """验收③（等价：重启恢复）：save 后重新解析得到上次选择。"""
    ss, sf = isolated_settings
    ss.save_record_device("BlackHole 2ch")
    device, source = ss.get_record_device()
    assert device == "BlackHole 2ch"
    assert source == "settings"


def test_empty_string_is_valid_persisted_value(isolated_settings):
    """裁决口径：空串「自动检测」为合法持久值（键存在即生效，不被 env/默认覆盖）。"""
    ss, sf = isolated_settings
    ss.save_record_device("")
    monkey_env = True
    import os
    os.environ["RECORD_DEVICE"] = "SomeMic"
    try:
        device, source = ss.get_record_device()
        assert device == "" and source == "settings"  # settings 优先（项目方裁决）
    finally:
        del os.environ["RECORD_DEVICE"]


def test_priority_settings_over_env_over_default(isolated_settings, monkeypatch):
    """优先级链：settings 已配置→settings；未配置+env→env；皆无→平台默认。"""
    ss, sf = isolated_settings
    # 无 settings 无 env → 平台默认
    device, source = ss.get_record_device()
    assert source == "platform-default"
    # env 生效
    monkeypatch.setenv("RECORD_DEVICE", "EnvMic")
    device, source = ss.get_record_device()
    assert (device, source) == ("EnvMic", "env")
    # settings 覆盖 env（裁决口径）
    ss.save_record_device("SettingsMic")
    device, source = ss.get_record_device()
    assert (device, source) == ("SettingsMic", "settings")


def test_store_set_record_device_persists(isolated_settings, tmp_path, monkeypatch):
    """POST 语义：store.set_record_device 同时更新运行时值并落盘。"""
    ss, sf = isolated_settings
    import app.store as store

    monkeypatch.setattr(store, "RECORD_DEVICE", "orig")  # 测后自动恢复全局值
    store.set_record_device("MicX")
    assert store.RECORD_DEVICE == "MicX"
    data = json.loads(sf.read_text(encoding="utf-8"))
    assert data.get("record", {}).get("device") == "MicX"


def test_persist_failure_does_not_break_runtime(monkeypatch, tmp_path):
    """持久化异常降级：运行时值仍生效（不阻断录音链路）。"""
    import app.settings_store as ss
    import app.store as store

    broken = tmp_path / "broken" / "settings.json"  # 父目录不存在 → 写盘失败
    monkeypatch.setattr(ss, "SETTINGS_FILE", broken)
    store.set_record_device("MicY")
    assert store.RECORD_DEVICE == "MicY"


def test_api_post_then_get_reflects_persisted_device(isolated_settings, monkeypatch):
    """验收③ API 面：POST /api/record/device → GET /api/record/devices 回显（同进程内）。"""
    ss, sf = isolated_settings
    import app.store as store

    monkeypatch.setattr(store, "RECORD_DEVICE", "MicZ")
    # 直接驱动 setter（路由函数为薄封装，TestClient 起全应用需 JWT/环境，此处按函数级断言等价契约）
    from app.routers.record import RecordDeviceRequest, set_record_device

    resp = set_record_device(RecordDeviceRequest(device="MicZ"))
    assert resp["device"] == "MicZ" and resp["auto_detect"] is False
    data = json.loads(sf.read_text(encoding="utf-8"))
    assert data["record"]["device"] == "MicZ"
    # 重启等价：重新解析
    assert ss.get_record_device() == ("MicZ", "settings")
