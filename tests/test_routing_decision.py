"""
tests/test_routing_decision.py — REQ-SETTINGS-IA 路由判定（两值决策层 + 逐能力来源）

覆盖：
  - §3.1 离线/联网两模式路由 + 计费三来源口径
  - §3.5 静默语义消灭：prefer_subscription 不再 override 路由；
    配额耗尽 / Key 缺失一律明示 auto_switched + 事件记录（Q3 三级提示数据源）
  - AC-6 未配置兜底等价（保留升级前行为）
运行：pytest tests/test_routing_decision.py -v
"""

import pytest

# 预导入（收集期、桩未激活时）：防桩被永久绑定进路由模块（跨文件顺序依赖）。
import app.routers.settings  # noqa: F401
import app.server  # noqa: F401
import app.settings_store as ss
import core.routing as rt


@pytest.fixture(autouse=True)
def _fresh_switch_state(monkeypatch):
    """隔离自动改用事件的状态跳变缓存与事件文件（避免测试间互相吞事件）。"""
    monkeypatch.setattr(rt, "_LAST_SWITCH_STATE", {}, raising=True)


@pytest.fixture()
def events(monkeypatch):
    """收集 record_event 调用。"""
    recorded = []

    def _record(event_type, **fields):
        recorded.append({"type": event_type, **fields})

    import core.settings_events as se
    monkeypatch.setattr(se, "record_event", _record, raising=True)
    return recorded


@pytest.fixture()
def access(monkeypatch):
    """设置 access_mode + 逐能力生效来源桩（隔离文件系统与 users）。

    llm_src/asr_src 传入即 capability.effective；offline 态强制 local。
    """
    def _set(mode, expert=False, llm_src="", asr_src=""):
        monkeypatch.setattr(ss, "get_access_mode", lambda: mode)
        monkeypatch.setattr(ss, "get_expert_mode", lambda: expert)

        def _cap(prefer_subscription=None):
            default = "trial" if prefer_subscription else "byok"
            if mode == "local":
                llm_eff = asr_eff = "local"
            else:
                llm_eff = llm_src or default
                asr_eff = asr_src or default
            return {"account_default": default,
                    "llm": {"explicit": llm_eff, "override": True, "default": default, "effective": llm_eff},
                    "asr": {"explicit": asr_eff, "override": True, "default": default, "effective": asr_eff}}

        monkeypatch.setattr(ss, "get_capability_status", _cap)
    return _set


@pytest.fixture()
def user_state(monkeypatch):
    def _set(prefer_subscription=False, quota=100, logged_in=True):
        user = None
        if logged_in:
            user = {"id": "u1", "provider": "sms", "quota": quota,
                    "prefs": {"prefer_subscription": prefer_subscription}}
        monkeypatch.setattr("core.users.get_current_user", lambda: user, raising=True)
        # check_quota 桩：remaining = quota（-1 表示不受计量限制由 quota=None 表达）
        import core.metering as mt
        monkeypatch.setattr(mt, "is_metered", lambda: logged_in and prefer_subscription is not None)

        def _check(user_id, estimated_minutes=0):
            if not logged_in:
                return {"allowed": True, "remaining": -1, "quota": -1, "used": 0, "warning": None}
            rem = DEFAULT if quota is None else quota
            return {"allowed": (rem == -1 or rem > 0), "remaining": rem,
                    "quota": rem, "used": 0, "warning": None}

        monkeypatch.setattr(mt, "check_quota", _check)
    return _set


DEFAULT = -1  # 不受计量限制
VALID_KEY = "sk-valid-local-api-key-0123456789"


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


# ============================================================
# §3.1 离线模式：结构性零出网
# ============================================================


class TestOfflineMode:
    def test_local_never_cloud_and_llm_offline(self, access, keys, cloud, user_state):
        access("local")
        keys()
        cloud(True)
        user_state(prefer_subscription=True)  # 即使勾选体验优先，离线也不切云
        d = rt.get_routing_decision("llm")
        assert d["route"] == "local" and d["source"] == "local"
        assert d["auto_switched"] is False
        from core.llm import _should_use_cloud
        assert _should_use_cloud() is False

    def test_local_asr_route(self, access, keys, cloud, user_state):
        access("local")
        keys()
        assert rt.get_routing_decision("asr")["route"] == "local"

    def test_local_not_metered_route_never_cloud(self, access, keys, cloud, user_state):
        access("local")
        keys()
        cloud(True)
        user_state(quota=100)
        for ctx in ("llm", "asr"):
            d = rt.get_routing_decision(ctx)
            assert d["route"] == "local" and d["auto_switched"] is False


# ============================================================
# §3.1/§3.5 联网模式：逐能力来源判定
# ============================================================


class TestCloudTrialSource:
    def test_trial_llm_routes_cloud_and_reports_trial(self, access, keys, cloud, user_state):
        access("cloud", llm_src="trial", asr_src="trial")
        keys(llm_key="")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "cloud" and d["source"] == "trial"
        assert d["auto_switched"] is False and d["reason"] == ""

    def test_trial_asr_uses_proxy_transport(self, access, keys, cloud, user_state):
        access("cloud", asr_src="trial")
        keys(asr_mode="proxy", proxy_url="http://proxy.local")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("asr")
        assert d["route"] == "proxy" and d["source"] == "trial"

    def test_trial_asr_never_silently_direct(self, access, keys, cloud, user_state):
        """来源=体验但 asr.mode 投影分歧：按体验语义传输，绝不走自有 Key。"""
        access("cloud", asr_src="trial")
        keys(asr_mode="direct", asr_key=VALID_KEY)
        cloud(True)
        user_state(quota=100)
        assert rt.get_routing_decision("asr")["route"] in ("cloud", "proxy")

    def test_trial_quota_exhausted_auto_switches_with_event(self, access, keys, cloud, user_state, events):
        """配额耗尽 → 明示自动改用已就绪来源 + 落事件（禁用「降级」，L1-L3 数据源）。"""
        access("cloud", llm_src="trial")
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(quota=0)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct"
        assert d["source"] == "byok"
        assert d["auto_switched"] is True
        assert d["reason"] == "trial_quota_exhausted"
        assert any(e["type"] == "auto_switch" and e.get("reason") == "trial_quota_exhausted" for e in events)

    def test_trial_exhausted_no_fallback_stays_explicit(self, access, keys, cloud, user_state):
        access("cloud", llm_src="trial")
        keys(llm_key="")
        cloud(False)
        user_state(quota=0)
        d = rt.get_routing_decision("llm")
        assert d["source"] == "trial"
        assert d["auto_switched"] is False
        assert d["reason"] == "trial_quota_exhausted_no_fallback"

    def test_trial_not_logged_in_auto_switches(self, access, keys, cloud, user_state):
        access("cloud", llm_src="trial")
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(logged_in=False)
        d = rt.get_routing_decision("llm")
        assert d["auto_switched"] is True and d["reason"] == "trial_requires_login"
        assert d["route"] == "direct"


class TestCloudByokSource:
    def test_byok_direct_with_valid_key(self, access, keys, cloud, user_state):
        access("cloud", llm_src="byok", asr_src="byok")
        keys(llm_key=VALID_KEY, asr_mode="direct", asr_key=VALID_KEY)
        cloud(False)
        user_state(prefer_subscription=True, quota=100)
        assert rt.get_routing_decision("llm")["route"] == "direct"
        assert rt.get_routing_decision("asr")["route"] == "direct"

    def test_prefer_subscription_no_longer_overrides(self, access, keys, cloud, user_state):
        """第 5 刀：勾选不再改写显式来源路由（静默 route_override 语义消灭）。"""
        access("cloud", llm_src="byok")
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(prefer_subscription=True, quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["auto_switched"] is False and d["reason"] == ""

    def test_byok_missing_key_switches_to_trial_explicitly(self, access, keys, cloud, user_state, events):
        """Key 缺失：不再静默走平台计费——明示 auto_switched + 事件记录。"""
        access("cloud", llm_src="byok")
        keys(llm_key="")
        cloud(True)
        user_state(prefer_subscription=False, quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "cloud" and d["source"] == "trial"
        assert d["auto_switched"] is True and d["reason"] == "byok_key_missing"
        assert any(e["type"] == "auto_switch" and e.get("capability") == "llm" for e in events)

    def test_byok_missing_key_cloud_unavailable_fails_explicit(self, access, keys, cloud, user_state):
        access("cloud", llm_src="byok")
        keys(llm_key="")
        cloud(False)
        user_state(logged_in=False)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["auto_switched"] is False
        assert d["reason"] == "byok_key_missing_cloud_unavailable"


class TestCloudLocalEndpointSource:
    def test_local_endpoint_zero_egress(self, access, keys, cloud, user_state):
        access("cloud", llm_src="local_endpoint")
        keys(llm_key="", llm_base_url="http://localhost:11434/v1")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["source"] == "local_endpoint"
        assert d["auto_switched"] is False and d["reason"] == ""

    def test_local_endpoint_misconfigured_explicit(self, access, keys, cloud, user_state):
        """声明本机端点但 base_url 非 localhost：明示 misconfigured，不静默切云。"""
        access("cloud", llm_src="local_endpoint")
        keys(llm_key="", llm_base_url="https://api.openai.com/v1")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["reason"] == "local_endpoint_misconfigured"
        assert d["auto_switched"] is False


# ============================================================
# 兼容：route_override 字段镜像 auto_switched（一个版本日落）
# ============================================================


class TestCompatMirror:
    def test_route_override_mirrors_auto_switched(self, access, keys, cloud, user_state):
        access("cloud", llm_src="trial")
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(quota=0)
        d = rt.get_routing_decision("llm")
        assert d["route_override"] == d["auto_switched"] is True

    def test_event_recorded_only_on_transition(self, access, keys, cloud, user_state, events):
        access("cloud", llm_src="trial")
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(quota=0)
        for _ in range(3):
            rt.get_routing_decision("llm")
        assert len([e for e in events if e.get("reason") == "trial_quota_exhausted"]) == 1


# ============================================================
# AC-6 未配置（null）兜底：与升级前行为逐项等价（原样保留）
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
