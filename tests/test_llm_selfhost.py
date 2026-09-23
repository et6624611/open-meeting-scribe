"""
tests/test_llm_selfhost.py — R4 LLM 自接增强测试（WP-A）

覆盖：Ollama / LM Studio 预设、POST /api/settings/test-llm 连通性测试
（10s 超时、可行动排错文案）、localhost 空 Key 容错、非 localhost https 警告。

运行方式：
  pytest tests/test_llm_selfhost.py -v
"""

import json

import pytest
import requests

import app.settings_store as settings_store
from core.llm import is_localhost_base_url


# ============================================================
# 预设与 localhost 判定
# ============================================================

class TestPresets:
    def test_ollama_preset(self):
        from app.routers.settings import PROVIDER_PRESETS
        preset = next(p for p in PROVIDER_PRESETS if "Ollama" in p["name"])
        assert preset["base_url"] == "http://localhost:11434/v1"
        assert preset["key_optional"] is True
        assert preset["localhost"] is True
        assert preset["models"]  # 提供建议模型

    def test_lm_studio_preset(self):
        from app.routers.settings import PROVIDER_PRESETS
        preset = next(p for p in PROVIDER_PRESETS if "LM Studio" in p["name"])
        assert preset["base_url"] == "http://localhost:1234/v1"
        assert preset["key_optional"] is True
        assert preset["localhost"] is True

    def test_presets_order_keeps_custom_last(self):
        from app.routers.settings import PROVIDER_PRESETS
        assert PROVIDER_PRESETS[-1]["name"] == "自定义"

    @pytest.mark.parametrize("url,expected", [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:1234/v1", True),
        ("http://[::1]:8080/v1", True),
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", False),
        ("http://192.168.1.10:11434/v1", False),
        ("", False),
    ])
    def test_is_localhost(self, url, expected):
        assert is_localhost_base_url(url) is expected


# ============================================================
# core/llm.py localhost 空 Key 容错
# ============================================================

class TestLlmLocalhostTolerance:
    @pytest.fixture
    def settings_file(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        monkeypatch.setattr(settings_store, "SETTINGS_FILE", path)
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        return path

    def test_headers_omit_auth_for_empty_key(self, settings_file, monkeypatch):
        settings_file.write_text(json.dumps({
            "llm": {"base_url": "http://localhost:11434/v1", "api_key": "", "model": "qwen3:8b"},
        }), encoding="utf-8")
        from core import llm as llm_mod
        headers = llm_mod._get_headers()
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_headers_include_explicit_local_key(self, settings_file):
        settings_file.write_text(json.dumps({
            "llm": {"base_url": "http://localhost:1234/v1", "api_key": "lm-studio", "model": "x"},
        }), encoding="utf-8")
        from core import llm as llm_mod
        headers = llm_mod._get_headers()
        assert headers["Authorization"] == "Bearer lm-studio"

    def test_non_localhost_still_requires_key(self, settings_file):
        """云端/远程端点空 Key 仍抛错——既有行为零变化"""
        settings_file.write_text(json.dumps({
            "llm": {"base_url": "https://api.deepseek.com/v1", "api_key": "", "model": "deepseek-chat"},
        }), encoding="utf-8")
        from core import llm as llm_mod
        with pytest.raises(RuntimeError):
            llm_mod._get_headers()

    def test_should_use_cloud_false_for_localhost(self, settings_file, monkeypatch):
        settings_file.write_text(json.dumps({
            "llm": {"base_url": "http://localhost:11434/v1", "api_key": "", "model": "qwen3:8b"},
        }), encoding="utf-8")
        from core import llm as llm_mod
        # 即使云端可用也不回退 / No cloud fallback even if cloud is enabled
        monkeypatch.setattr("core.cloud_client.is_cloud_enabled", lambda: True, raising=False)
        assert llm_mod._should_use_cloud() is False


# ============================================================
# POST /api/settings/test-llm
# ============================================================

class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text or "{}")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.server import app
    with TestClient(app) as c:
        yield c


class TestTestLlmEndpoint:
    def test_success_localhost_empty_key(self, client, monkeypatch):
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
            captured.update({"url": url, "headers": headers, "timeout": timeout})
            return _FakeResponse(200, '{"choices":[{"message":{"content":"pong"}}]}')

        monkeypatch.setattr(requests, "post", fake_post)
        resp = client.post("/api/settings/test-llm", json={
            "base_url": "http://localhost:11434/v1",
            "model": "qwen3:8b",
            "api_key": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["latency_ms"] >= 0
        assert data["model"] == "qwen3:8b"
        # 空 Key 不携带 Authorization / Empty key sends no Authorization header
        assert "Authorization" not in captured["headers"]
        # 超时 10s / Timeout is 10s per PRD R4
        assert captured["timeout"] == 10

    def test_service_down_actionable_hint(self, client, monkeypatch):
        def fake_post(url, **kwargs):
            raise requests.exceptions.ConnectionError("Connection refused")

        monkeypatch.setattr(requests, "post", fake_post)
        resp = client.post("/api/settings/test-llm", json={
            "base_url": "http://localhost:11434/v1", "model": "qwen3:8b", "api_key": "",
        })
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "service_down"
        # 排错文案可行动：提到启动服务与 CORS / Actionable copy mentions starting service & CORS
        assert "Ollama" in data["error"] or "LM Studio" in data["error"]
        assert "CORS" in data["error"]

    def test_model_not_pulled(self, client, monkeypatch):
        def fake_post(url, **kwargs):
            return _FakeResponse(404, '{"error":"model \'qwen3:99b\' not found, try pulling it first"}')

        monkeypatch.setattr(requests, "post", fake_post)
        resp = client.post("/api/settings/test-llm", json={
            "base_url": "http://localhost:11434/v1", "model": "qwen3:99b", "api_key": "",
        })
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "model_not_pulled"
        assert "ollama pull" in data["error"]

    def test_timeout(self, client, monkeypatch):
        def fake_post(url, **kwargs):
            raise requests.exceptions.Timeout()

        monkeypatch.setattr(requests, "post", fake_post)
        resp = client.post("/api/settings/test-llm", json={
            "base_url": "http://localhost:1234/v1", "model": "x", "api_key": "",
        })
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "timeout"

    def test_missing_key_for_non_localhost(self, client, monkeypatch):
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        resp = client.post("/api/settings/test-llm", json={
            "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "api_key": "",
        })
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "missing_key"

    def test_http_non_localhost_warns(self, client, monkeypatch):
        captured = {}

        def fake_post(url, headers=None, **kwargs):
            captured["headers"] = headers
            return _FakeResponse(200, "{}")

        monkeypatch.setattr(requests, "post", fake_post)
        resp = client.post("/api/settings/test-llm", json={
            "base_url": "http://192.168.1.10:8000/v1", "model": "m", "api_key": "sk-test-key-1234567890",
        })
        data = resp.json()
        assert data["ok"] is True
        assert "HTTPS" in data.get("warning", "")
        assert captured["headers"]["Authorization"] == "Bearer sk-test-key-1234567890"

    def test_auth_failed(self, client, monkeypatch):
        def fake_post(url, **kwargs):
            return _FakeResponse(401, "unauthorized")

        monkeypatch.setattr(requests, "post", fake_post)
        resp = client.post("/api/settings/test-llm", json={
            "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k", "api_key": "sk-wrong",
        })
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "auth_failed"

    def test_missing_base_url(self, client, monkeypatch):
        import app.routers.settings as settings_router
        monkeypatch.setattr(settings_router, "get_llm_config", lambda: {
            "provider": "DashScope", "base_url": "", "api_key": "", "model": "",
        })
        resp = client.post("/api/settings/test-llm", json={"base_url": "", "model": "", "api_key": ""})
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "invalid_config"


# ============================================================
# 保存设置：localhost 空 Key 不回填云端 Key（R4 验收「无 Key 保存不报错」）
# ============================================================

class TestSaveSettingsLocalhost:
    def test_save_localhost_without_key(self, client, tmp_path, monkeypatch):
        settings_file = tmp_path / "settings.json"
        monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-cloud-env-key-should-not-leak")

        resp = client.post("/api/settings", json={
            "llm": {
                "provider": "Ollama（本地）",
                "base_url": "http://localhost:11434/v1",
                "api_key": "",
                "model": "qwen3:8b",
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["llm"]["api_key_set"] is False

        saved = json.loads(settings_file.read_text(encoding="utf-8"))
        assert saved["llm"]["api_key"] == ""
        assert saved["llm"]["base_url"] == "http://localhost:11434/v1"

    def test_save_engine_block(self, client, tmp_path, monkeypatch):
        settings_file = tmp_path / "settings.json"
        monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)

        resp = client.post("/api/settings", json={
            "engine": {"mode": "local", "local": {"model_dir": "/tmp/m", "model_tier": "conservative"}},
        })
        assert resp.status_code == 200
        saved = json.loads(settings_file.read_text(encoding="utf-8"))
        assert saved["engine"]["mode"] == "local"
        assert saved["engine"]["local"]["model_tier"] == "conservative"

        # 非法值被白名单拒绝，回退默认 / Invalid values rejected by whitelist
        resp = client.post("/api/settings", json={
            "engine": {"mode": "bogus", "local": {"model_tier": "turbo"}},
        })
        saved = json.loads(settings_file.read_text(encoding="utf-8"))
        assert saved["engine"]["mode"] == "local"
        assert saved["engine"]["local"]["model_tier"] == "conservative"

    def test_get_settings_exposes_engine_and_presets(self, client, tmp_path, monkeypatch):
        settings_file = tmp_path / "settings.json"
        monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
        settings_file.write_text("{}", encoding="utf-8")

        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"]["mode"] == "cloud"
        assert data["engine"]["local"]["model_dir"] == "data/models/"
        assert data["engine"]["local"]["model_tier"] == "auto"
        names = [p["name"] for p in data["llm_provider_presets"]]
        assert "Ollama（本地）" in names
        assert "LM Studio（本地）" in names
