"""tests/test_settings_realtime_asr.py — 实时预览配置读写与解析。

锁定：
  - asr.realtime 独立落盘，不覆盖批处理字段；
  - 掩码/空凭据保存时保留存量；
  - auto 跟随现有 asr.mode 解析。
"""

import json

import pytest

import app.settings_store as settings_store
import core.settings_store as _core_ss


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", path)
    monkeypatch.setattr(_core_ss, "SETTINGS_FILE", path)
    monkeypatch.delenv("ASR_MODE", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    return path


def _saved(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_realtime_save_keeps_batch_fields(client, _isolated_settings):
    resp = client.post("/api/settings", json={
        "asr": {
            "mode": "direct",
            "base_url": "https://dashscope.aliyuncs.com",
            "api_key": "sk-batch-key-0000",
            "model": "paraformer-v2",
            "realtime": {
                "provider": "volcengine",
                "model": "bigmodel",
                "diarization": "auto",
                "credentials": {
                    "api_key": "volc-key-1111",
                    "resource_id": "volc.seedasr.sauc.duration",
                },
            },
        },
    })
    assert resp.status_code == 200
    asr = _saved(_isolated_settings)["asr"]
    assert asr["api_key"] == "sk-batch-key-0000"
    assert asr["model"] == "paraformer-v2"
    assert asr["realtime"]["provider"] == "volcengine"
    assert asr["realtime"]["credentials"]["api_key"] == "volc-key-1111"


def test_realtime_masked_credentials_are_kept(client, _isolated_settings):
    _isolated_settings.write_text(json.dumps({
        "asr": {
            "mode": "proxy",
            "realtime": {
                "provider": "volcengine",
                "credentials": {"api_key": "volc-secret-2222", "resource_id": "volc.bigasr.sauc.duration"},
            },
        },
    }), encoding="utf-8")

    resp = client.post("/api/settings", json={
        "asr": {
            "realtime": {
                "provider": "volcengine",
                "credentials": {"api_key": "****2222", "resource_id": "volc.bigasr.sauc.duration"},
            },
        },
    })
    assert resp.status_code == 200
    creds = _saved(_isolated_settings)["asr"]["realtime"]["credentials"]
    assert creds["api_key"] == "volc-secret-2222"


def test_get_returns_masked_realtime_and_providers(client, _isolated_settings):
    _isolated_settings.write_text(json.dumps({
        "asr": {
            "mode": "proxy",
            "realtime": {
                "provider": "volcengine",
                "model": "bigmodel",
                "credentials": {"api_key": "volc-secret-3333", "resource_id": "volc.bigasr.sauc.duration"},
            },
        },
    }), encoding="utf-8")

    data = client.get("/api/settings").json()
    rt = data["asr"]["realtime"]
    assert rt["provider"] == "volcengine"
    assert "****" in rt["credentials"]["api_key"]
    assert rt["credentials_set"]["api_key"] is True
    specs = {p["key"]: p for p in data["asr_realtime_providers"]}
    assert specs["volcengine"]["available"] is True
    assert specs["xfyun"]["available"] is False


def test_auto_resolution_follows_batch_mode(_isolated_settings, monkeypatch):
    _isolated_settings.write_text(json.dumps({
        "asr": {"mode": "direct", "api_key": "sk-auto-key", "base_url": "https://dashscope.aliyuncs.com"},
    }), encoding="utf-8")
    monkeypatch.delenv("ASR_MODE", raising=False)
    cfg = _core_ss.get_realtime_asr_config()
    assert cfg["provider"] == "auto"
    assert cfg["resolved_provider"] == "dashscope"
    assert cfg["credentials"]["api_key"] == "sk-auto-key"

    _isolated_settings.write_text(json.dumps({"asr": {"mode": "proxy"}}), encoding="utf-8")
    monkeypatch.setenv("ASR_PROXY_URL", "http://127.0.0.1:9999")
    cfg2 = _core_ss.get_realtime_asr_config()
    assert cfg2["resolved_provider"] == "proxy"


def test_explicit_volcengine_resolution(_isolated_settings):
    _isolated_settings.write_text(json.dumps({
        "asr": {
            "mode": "proxy",
            "realtime": {
                "provider": "volcengine",
                "credentials": {"api_key": "volc-key", "resource_id": "volc.seedasr.sauc.duration"},
            },
        },
    }), encoding="utf-8")
    cfg = _core_ss.get_realtime_asr_config()
    assert cfg["resolved_provider"] == "volcengine"
    assert cfg["byok"] is True
