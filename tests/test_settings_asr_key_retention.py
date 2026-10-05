"""
tests/test_settings_asr_key_retention.py — 代理模式保存不再擦除 BYOK api_key

背景（ASR 配置统一方案 · 即选即用）：来源选择器的「选为当前来源」写路径
pickCloudSource → POST /api/settings { capability_source }（不带 asr 块）。
旧实现在 asr.mode=proxy 分支重建 merged_asr 时丢弃 api_key 键，导致用户已保存
的自带 Key 被静默擦除且不可恢复。本用例锁定回归：direct+key 保存后，
再经代理模式分支保存（含仅 capability_source），api_key 必须原样落盘。

运行方式：
  pytest tests/test_settings_asr_key_retention.py -v
"""

import json

import pytest

import app.settings_store as settings_store


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.server import app
    with TestClient(app) as c:
        yield c


class TestAsrKeyRetention:
    @pytest.fixture(autouse=True)
    def _isolated_settings(self, tmp_path, monkeypatch):
        self.path = tmp_path / "settings.json"
        monkeypatch.setattr(settings_store, "SETTINGS_FILE", self.path)
        monkeypatch.delenv("ASR_MODE", raising=False)
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    def _saved_asr(self):
        return json.loads(self.path.read_text(encoding="utf-8")).get("asr", {})

    def test_direct_key_survives_capability_source_save(self, client):
        """先存 direct + api_key，再点「选为当前来源」（仅 capability_source）→ Key 仍在。"""
        resp = client.post("/api/settings", json={
            "asr": {
                "mode": "direct",
                "provider": "DashScope",
                "base_url": "https://dashscope.aliyuncs.com",
                "api_key": "sk-retention-test-key-FAKE-0000",
                "model": "paraformer-v2",
            },
        })
        assert resp.status_code == 200
        assert self._saved_asr()["api_key"] == "sk-retention-test-key-FAKE-0000"

        # capability_source 显式保存不携带 asr 块；旧版 else 分支重建时会丢 Key
        resp2 = client.post("/api/settings", json={"capability_source": {"asr": "trial"}})
        assert resp2.status_code == 200
        assert self._saved_asr()["api_key"] == "sk-retention-test-key-FAKE-0000"

    def test_proxy_save_keeps_existing_key(self, client):
        """代理模式下保存其他设置域（feature_flags）→ asr.api_key 原样保留。"""
        self.path.write_text(json.dumps({
            "asr": {
                "mode": "proxy",
                "provider": "DashScope",
                "model": "paraformer-v2",
                "api_key": "sk-proxy-keep-me-1234567890",
            },
        }), encoding="utf-8")

        resp = client.post("/api/settings", json={"feature_flags": {"update_check": False}})
        assert resp.status_code == 200
        asr = self._saved_asr()
        assert asr["api_key"] == "sk-proxy-keep-me-1234567890"
        assert asr["mode"] == "proxy"

    def test_explicit_key_still_wins_in_direct_mode(self, client):
        """直连分支显式提交新 Key 仍正常覆盖（行为零变化）。"""
        self.path.write_text(json.dumps({
            "asr": {"mode": "direct", "api_key": "sk-old-key-value-1234567890", "model": "paraformer-v2"},
        }), encoding="utf-8")

        resp = client.post("/api/settings", json={
            "asr": {"mode": "direct", "api_key": "sk-brand-new-key-9876543210"},
        })
        assert resp.status_code == 200
        assert self._saved_asr()["api_key"] == "sk-brand-new-key-9876543210"
