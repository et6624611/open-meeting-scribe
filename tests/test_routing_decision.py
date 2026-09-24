"""
tests/test_routing_decision.py — REQ-ACCESS-MODE-CARDS T2 路由判定收口（AM-B1）

覆盖 AC-4（三模式路由 + 计费口径）、AC-5（D2 override 可感知）、AC-6（未配置兜底等价）。
运行：pytest tests/test_routing_decision.py -v
"""

import pytest

import app.settings_store as ss
import core.routing as rt


@pytest.fixture()
def access(monkeypatch):
    """设置 access_mode 桩（get_expert_mode 同步桩为 False，隔离文件系统）。"""
    def _set(mode, expert=False):
        monkeypatch.setattr(ss, "get_access_mode", lambda: mode)
        monkeypatch.setattr(ss, "get_expert_mode", lambda: expert)
    return _set


@pytest.fixture()
def user_state(monkeypatch):
    def _set(prefer_subscription=False, quota=100, logged_in=True):
        user = None
        if logged_in:
            user = {"id": "u1", "provider": "sms", "quota": quota,
                    "prefs": {"prefer_subscription": prefer_subscription}}
        monkeypatch.setattr("core.users.get_current_user", lambda: user, raising=True)
    return _set


@pytest.fixture()
def cloud(monkeypatch):
    def _set(enabled=True):
        monkeypatch.setattr("core.cloud_client.is_cloud_enabled", lambda: enabled, raising=True)
    return _set


@pytest.fixture()
def keys(monkeypatch):
    def _set(llm_key="sk-valid-local-api-key-0123456789", llm_base_url="https://api.openai.com/v1",
             asr_mode="proxy", asr_key="", proxy_url="http://proxy.local"):
        import app.store as store
        monkeypatch.setattr(store, "get_active_api_key", lambda: llm_key or "", raising=True)
        monkeypatch.setattr(store, "get_llm_config",
                            lambda: {"base_url": llm_base_url, "api_key": llm_key or "",
                                     "model": "gpt-4o", "provider": "OpenAI"}, raising=True)
        monkeypatch.setattr(store, "get_asr_config",
                            lambda: {"mode": asr_mode, "api_key": asr_key,
                                     "proxy_url": proxy_url, "provider": "DashScope",
                                     "model": "paraformer-v2", "base_url": ""}, raising=True)
    return _set


VALID_KEY = "sk-valid-local-api-key-0123456789"


# ============================================================
# AC-4 三模式路由判定
# ============================================================


class TestRoutedModes:
    def test_local_never_cloud_and_llm_offline(self, access, keys, cloud, user_state):
        access("local")
        keys()
        cloud(True)
        user_state(prefer_subscription=True)  # 即使开着订阅偏好，离线也不切云（R7 零出网）
        d = rt.get_routing_decision("llm")
        assert d["route"] == "local" and d["route_override"] is False
        from core.llm import _should_use_cloud
        assert _should_use_cloud() is False

    def test_local_asr_route(self, access, keys, cloud, user_state):
        access("local")
        keys()
        assert rt.get_routing_decision("asr")["route"] == "local"

    def test_hosted_llm_consumes_quota_path(self, access, keys, cloud, user_state):
        access("hosted")
        keys(llm_key="")
        cloud(True)
        user_state()
        d = rt.get_routing_decision("llm")
        assert d["route"] == "cloud"
        from core.llm import _should_use_cloud
        assert _should_use_cloud() is True

    def test_hosted_asr_uses_proxy_transport(self, access, keys, cloud, user_state):
        access("hosted")
        keys(asr_mode="proxy", proxy_url="http://proxy.local")
        cloud(True)
        user_state()
        assert rt.get_routing_decision("asr")["route"] == "proxy"

    def test_hosted_asr_never_silently_direct(self, access, keys, cloud, user_state):
        """旧配置分歧（engine=proxy 但 asr.mode=direct）：托管语义下不静默走自有 Key。"""
        access("hosted")
        keys(asr_mode="direct", asr_key=VALID_KEY)
        cloud(True)
        user_state()
        assert rt.get_routing_decision("asr")["route"] == "cloud"

    def test_byok_direct_with_valid_key(self, access, keys, cloud, user_state):
        access("byok")
        keys(llm_key=VALID_KEY, asr_mode="direct", asr_key=VALID_KEY)
        cloud(False)
        user_state(prefer_subscription=False)
        assert rt.get_routing_decision("llm")["route"] == "direct"
        assert rt.get_routing_decision("asr")["route"] == "direct"
        from core.llm import _should_use_cloud
        assert _should_use_cloud() is False


# ============================================================
# AC-4② 计费口径与 metering 一致：local 不计量 / hosted 计量 / byok 不消耗
# ============================================================


class TestMeteringAlignment:
    def test_local_not_metered_even_for_sms_user(self, access, keys, cloud, user_state):
        access("local")
        keys()
        cloud(True)
        user_state(quota=100)
        from core.metering import is_metered
        assert is_metered() is False

    def test_hosted_metered_for_sms_user(self, access, keys, cloud, user_state):
        access("hosted")
        keys()
        cloud(True)
        user_state(quota=100)
        from core.metering import is_metered
        assert is_metered() is True

    def test_byok_quota_untouched_without_pref(self, access, keys, cloud, user_state):
        access("byok")
        keys(llm_key=VALID_KEY, asr_mode="direct", asr_key=VALID_KEY)
        cloud(True)
        user_state(prefer_subscription=False, quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["route_override"] is False


# ============================================================
# AC-5 D2：跨模式隐式路由变化可查询
# ============================================================


class TestRouteOverride:
    def test_byok_prefer_subscription_overrides_to_cloud(self, access, keys, cloud, user_state):
        access("byok")
        keys(llm_key=VALID_KEY, asr_mode="direct", asr_key=VALID_KEY)
        cloud(True)
        user_state(prefer_subscription=True, quota=100)
        for ctx in ("llm", "asr"):
            d = rt.get_routing_decision(ctx)
            assert d["route"] == "cloud"
            assert d["route_override"] is True
            assert d["reason"] == "prefer_subscription"

    def test_quota_exhausted_falls_back_to_direct(self, access, keys, cloud, user_state):
        """配额耗尽不误扣也不误切：回落自有 Key（与体验期口径一致）。"""
        access("byok")
        keys(llm_key=VALID_KEY, asr_mode="direct", asr_key=VALID_KEY)
        cloud(True)
        user_state(prefer_subscription=True, quota=0)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["route_override"] is False

    def test_localhost_endpoint_never_overrides(self, access, keys, cloud, user_state):
        """R4 边界：Ollama/LM Studio 自持端点先于一切 override，绝不切云。"""
        access("byok")
        keys(llm_key="", llm_base_url="http://localhost:11434/v1")
        cloud(True)
        user_state(prefer_subscription=True, quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["route_override"] is False

    def test_byok_missing_key_falls_back_with_reason(self, access, keys, cloud, user_state):
        access("byok")
        keys(llm_key="", asr_mode="direct", asr_key="")
        cloud(True)
        user_state(prefer_subscription=False)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "cloud"
        assert d["route_override"] is True
        assert d["reason"] == "byok_key_missing"

    def test_routing_endpoint_exposes_override_to_frontend(self, access, keys, cloud, user_state):
        """AC-T2③：GET /api/settings/routing 可查询 override 事件与配额。"""
        access("byok")
        keys(llm_key=VALID_KEY, asr_mode="direct", asr_key=VALID_KEY)
        cloud(True)
        user_state(prefer_subscription=True, quota=100)
        import app.routers.settings as r
        resp = r.get_routing_status()
        assert resp["ok"] is True
        assert resp["access_mode"] == "byok"
        assert resp["onboarding_required"] is False
        assert resp["llm"]["route_override"] is True
        assert resp["llm"]["reason"] == "prefer_subscription"
        assert resp["asr"]["route"] == "cloud"


# ============================================================
# AC-6 未配置（null）兜底：与升级前行为逐项等价
# ============================================================


class TestLegacyFallback:
    def test_valid_key_no_pref_stays_direct(self, access, keys, cloud, user_state):
        access(None)
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(prefer_subscription=False)
        from core.llm import _should_use_cloud
        assert _should_use_cloud() is False

    def test_no_key_cloud_enabled_uses_cloud(self, access, keys, cloud, user_state):
        access(None)
        keys(llm_key="")
        cloud(True)
        user_state()
        from core.llm import _should_use_cloud
        assert _should_use_cloud() is True

    def test_localhost_guard_precedes_subscription_pref(self, access, keys, cloud, user_state):
        """等价锚定：与 test_llm_selfhost 既有契约一致（localhost 先于 ps）。"""
        access(None)
        keys(llm_key="", llm_base_url="http://127.0.0.1:1234/v1")
        cloud(True)
        user_state(prefer_subscription=True, quota=100)
        from core.llm import _should_use_cloud
        assert _should_use_cloud() is False

    def test_asr_engine_local_still_local(self, access, keys, cloud, user_state, monkeypatch):
        access(None)
        keys(asr_mode="proxy", proxy_url="http://proxy.local")
        cloud(False)
        user_state()
        monkeypatch.setattr(ss, "get_engine_config", lambda: {"mode": "local", "local": {}})
        import core.transcribe as t
        assert t._get_asr_mode() == "local"

    def test_asr_legacy_direct_with_pref_switches_cloud(self, access, keys, cloud, user_state, monkeypatch):
        access(None)
        keys(asr_mode="direct", asr_key=VALID_KEY)
        cloud(True)
        user_state(prefer_subscription=True, quota=100)
        monkeypatch.setattr(ss, "get_engine_config", lambda: {"mode": "direct", "local": {}})
        import core.transcribe as t
        assert t._get_asr_mode() == "cloud"

    def test_null_access_requires_onboarding(self, access, keys, cloud, user_state):
        access(None)
        keys()
        cloud(False)
        user_state(logged_in=False)
        import app.routers.settings as r
        resp = r.get_routing_status()
        assert resp["onboarding_required"] is True
        assert resp["llm"]["reason"] == "legacy_unconfigured"
