"""
tests/test_routing_decision.py — 逐能力路由判定（真相源 = capability_source.{llm,asr}）

覆盖：
  - 逐能力来源判定：trial / byok / local_endpoint(llm) / local(asr) 各自独立
  - 未设置（source=""）→ unconfigured，不静默兜底
  - 静默语义消灭：未登录 / 配额耗尽 / Key 缺失一律明示 auto_switched + 事件记录
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
    """隔离自动改用事件的状态跳变缓存（避免测试间互相吞事件）。"""
    monkeypatch.setattr(rt, "_LAST_SWITCH_STATE", {}, raising=True)


@pytest.fixture(autouse=True)
def _isolate_env_keys(monkeypatch):
    """隔离进程环境中的真 Key。

    app/server.py startup 会把 settings 里的真实 DASHSCOPE_API_KEY 直接写进 os.environ
    （非 monkeypatch，不随测试回弹）；而 routing 的「BYOK Key 缺失」判定在 store
    桩返回空串后会回落读该环境变量。不抽真空，本机有真 Key 的开发机上这些用例必红。
    """
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)


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
def cap(monkeypatch):
    """设置逐能力生效来源桩（隔离文件系统与 users）。

    llm_src/asr_src 即 capability.effective；"" 表示未设置。
    fallback = 自动改用同意开关（逐能力，默认关，与生产缺省一致）。
    """
    def _set(expert=False, llm_src="", asr_src="", fallback=False):
        monkeypatch.setattr(ss, "get_expert_mode", lambda: expert)

        def _capstatus(prefer_subscription=None):
            return {
                "llm": {"explicit": llm_src, "override": bool(llm_src), "default": llm_src, "effective": llm_src},
                "asr": {"explicit": asr_src, "override": bool(asr_src), "default": asr_src, "effective": asr_src},
            }

        monkeypatch.setattr(ss, "get_capability_status", _capstatus)
        monkeypatch.setattr(ss, "get_auto_fallback",
                            lambda: {"llm": bool(fallback), "asr": bool(fallback)})
    return _set


DEFAULT = -1  # 不受计量限制
VALID_KEY = "sk-valid-local-api-key-0123456789"


@pytest.fixture()
def user_state(monkeypatch):
    def _set(prefer_subscription=False, quota=100, logged_in=True):
        user = None
        if logged_in:
            user = {"id": "u1", "provider": "sms", "quota": quota,
                    "prefs": {"prefer_subscription": prefer_subscription}}
        monkeypatch.setattr("core.users.get_current_user", lambda: user, raising=True)
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


@pytest.fixture()
def cloud(monkeypatch):
    def _set(enabled=True):
        monkeypatch.setattr("core.cloud_client.is_cloud_enabled", lambda: enabled, raising=True)
    return _set


@pytest.fixture()
def keys(monkeypatch):
    def _set(llm_key=VALID_KEY, llm_base_url="https://api.openai.com/v1",
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
# 未设置：逐能力 unconfigured，不静默兜底
# ============================================================


class TestUnconfigured:
    def test_unset_llm_is_unconfigured(self, cap, keys, cloud, user_state):
        cap(llm_src="")
        keys()
        cloud(True)
        user_state()
        d = rt.get_routing_decision("llm")
        assert d["unconfigured"] is True and d["route"] == "" and d["source"] == ""
        assert d["reason"] == "source_not_set"

    def test_should_use_cloud_raises_when_unset(self, cap, keys, cloud, user_state):
        cap(llm_src="")
        keys()
        cloud(True)
        user_state()
        from core.llm import _should_use_cloud
        with pytest.raises(RuntimeError):
            _should_use_cloud()

    def test_asr_unset_route_empty(self, cap, keys, cloud, user_state):
        cap(asr_src="")
        keys()
        user_state()
        assert rt.get_routing_decision("asr")["route"] == ""
        import core.transcribe as t
        assert t._get_asr_mode() == ""


# ============================================================
# 本机链路：ASR local（引擎）/ LLM local_endpoint（逐能力，不联动）
# ============================================================


class TestLocalChain:
    def test_asr_local_route_independent_of_llm(self, cap, keys, cloud, user_state):
        """ASR 选本机引擎不影响 LLM：LLM 仍按自身来源（trial）走云。"""
        cap(asr_src="local", llm_src="trial")
        keys()
        cloud(True)
        user_state(quota=100)
        assert rt.get_routing_decision("asr")["route"] == "local"
        assert rt.get_routing_decision("llm")["route"] == "cloud"

    def test_asr_local_not_metered(self, cap, keys, cloud):
        cap(asr_src="local")
        keys()
        cloud(True)
        # 不调用 user_state（它会桩掉 is_metered）；route local 应短路返回不计量
        from core.metering import is_metered
        assert is_metered() is False

    def test_llm_local_endpoint_zero_egress(self, cap, keys, cloud, user_state):
        cap(llm_src="local_endpoint")
        keys(llm_key="", llm_base_url="http://localhost:11434/v1")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["source"] == "local_endpoint"
        assert d["auto_switched"] is False

    def test_llm_local_endpoint_misconfigured(self, cap, keys, cloud, user_state):
        cap(llm_src="local_endpoint")
        keys(llm_key="", llm_base_url="https://api.openai.com/v1")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["reason"] == "local_endpoint_misconfigured"


# ============================================================
# 体验配额来源：登录/额度门槛、明示自动改用
# ============================================================


class TestTrialSource:
    def test_trial_llm_routes_cloud(self, cap, keys, cloud, user_state):
        cap(llm_src="trial")
        keys(llm_key="")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "cloud" and d["source"] == "trial"
        assert d["auto_switched"] is False and d["reason"] == ""

    def test_trial_asr_uses_proxy_transport(self, cap, keys, cloud, user_state):
        cap(asr_src="trial")
        keys(asr_mode="proxy", proxy_url="http://proxy.local")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("asr")
        assert d["route"] in ("proxy", "cloud") and d["source"] == "trial"

    def test_trial_quota_exhausted_auto_switches_with_event(self, cap, keys, cloud, user_state, events):
        cap(llm_src="trial", fallback=True)
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(quota=0)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["source"] == "byok"
        assert d["auto_switched"] is True and d["reason"] == "trial_quota_exhausted"
        assert any(e["type"] == "auto_switch" and e.get("reason") == "trial_quota_exhausted" for e in events)

    def test_trial_exhausted_no_fallback_stays_explicit(self, cap, keys, cloud, user_state):
        cap(llm_src="trial")
        keys(llm_key="")
        cloud(False)
        user_state(quota=0)
        d = rt.get_routing_decision("llm")
        assert d["source"] == "trial" and d["auto_switched"] is False
        assert d["reason"] == "trial_quota_exhausted_no_fallback"

    def test_trial_not_logged_in_auto_switches(self, cap, keys, cloud, user_state):
        cap(llm_src="trial", fallback=True)
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(logged_in=False)
        d = rt.get_routing_decision("llm")
        assert d["auto_switched"] is True and d["reason"] == "trial_requires_login"
        assert d["route"] == "direct"


# ============================================================
# 自带 Key 来源：Key 缺失明示改用体验
# ============================================================


class TestByokSource:
    def test_byok_direct_with_valid_key(self, cap, keys, cloud, user_state):
        cap(llm_src="byok", asr_src="byok")
        keys(llm_key=VALID_KEY, asr_mode="direct", asr_key=VALID_KEY)
        cloud(False)
        user_state(quota=100)
        assert rt.get_routing_decision("llm")["route"] == "direct"
        assert rt.get_routing_decision("asr")["route"] == "direct"

    def test_byok_missing_key_switches_to_trial_explicitly(self, cap, keys, cloud, user_state, events):
        cap(llm_src="byok", fallback=True)
        keys(llm_key="")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "cloud" and d["source"] == "trial"
        assert d["auto_switched"] is True and d["reason"] == "byok_key_missing"
        assert any(e["type"] == "auto_switch" and e.get("capability") == "llm" for e in events)

    def test_byok_missing_key_cloud_unavailable_fails_explicit(self, cap, keys, cloud, user_state):
        cap(llm_src="byok")
        keys(llm_key="")
        cloud(False)
        user_state(logged_in=False)
        d = rt.get_routing_decision("llm")
        assert d["route"] == "direct" and d["auto_switched"] is False
        assert d["reason"] == "byok_key_missing_cloud_unavailable"


# ============================================================
# 兼容：route_override 字段镜像 auto_switched（一个版本日落）
# ============================================================


class TestCompatMirror:
    def test_route_override_mirrors_auto_switched(self, cap, keys, cloud, user_state):
        cap(llm_src="trial", fallback=True)
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(quota=0)
        d = rt.get_routing_decision("llm")
        assert d["route_override"] == d["auto_switched"] is True

    def test_event_recorded_only_on_transition(self, cap, keys, cloud, user_state, events):
        cap(llm_src="trial", fallback=True)
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(quota=0)
        for _ in range(3):
            rt.get_routing_decision("llm")
        assert len([e for e in events if e.get("reason") == "trial_quota_exhausted"]) == 1


# ============================================================
# 自动改用同意开关：默认关闭，即使有已配置替代也不替用户切换
# ============================================================


class TestFallbackConsent:
    def test_trial_exhausted_consent_off_keeps_trial(self, cap, keys, cloud, user_state, events):
        """有可用 BYOK 替代但用户未同意 → 保持 trial，不自动改用、不落切换事件。"""
        cap(llm_src="trial", fallback=False)
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(quota=0)
        d = rt.get_routing_decision("llm")
        assert d["source"] == "trial" and d["auto_switched"] is False
        assert d["reason"] == "trial_quota_exhausted_no_fallback"
        assert events == []

    def test_trial_not_logged_in_consent_off_keeps_trial(self, cap, keys, cloud, user_state):
        cap(llm_src="trial", fallback=False)
        keys(llm_key=VALID_KEY)
        cloud(True)
        user_state(logged_in=False)
        d = rt.get_routing_decision("llm")
        assert d["source"] == "trial" and d["auto_switched"] is False
        assert d["reason"] == "trial_requires_login"

    def test_byok_missing_key_consent_off_keeps_byok(self, cap, keys, cloud, user_state):
        """BYOK 缺 Key 且体验可用，但未同意 → 保持 byok 并明示，不静默切回平台计费。"""
        cap(asr_src="byok", fallback=False)
        keys(asr_mode="direct", asr_key="")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("asr")
        assert d["source"] == "byok" and d["auto_switched"] is False
        assert d["reason"] == "byok_key_missing_cloud_unavailable"

    def test_consent_on_allows_switch_again(self, cap, keys, cloud, user_state):
        cap(asr_src="byok", fallback=True)
        keys(asr_mode="direct", asr_key="")
        cloud(True)
        user_state(quota=100)
        d = rt.get_routing_decision("asr")
        assert d["source"] == "trial" and d["auto_switched"] is True
        assert d["reason"] == "byok_key_missing"
