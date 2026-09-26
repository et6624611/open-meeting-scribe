"""
tests/test_access_mode_migration.py — REQ-SETTINGS-IA 数据模型、迁移与切换事务

覆盖：
  - §4 存量迁移映射表（local/hosted/byok/null/混配 全组合，AC-8）
  - §3.1 apply_access_mode 新口径（两值决策层 + 逐能力来源 + A2 投影）
  - §3.5 三态语义（override 持久化不被勾选改回，AC-5）
  - §3.2 反向同步降级为旧客户端兼容窗口（AC-1）
  - 切换事务失败全量回滚（AC-2：settings.json 逐字段零写入）
  - §3.4 voiceprint 字段后端下架（AC-3）
运行：pytest tests/test_access_mode_migration.py -v
"""

import json

import pytest

# 预导入：防 app.store 桩在首次导入时被永久绑定进路由模块（见 test_routing_decision 注释）
import app.routers.settings  # noqa: F401
import app.server  # noqa: F401
import app.settings_store as ss


@pytest.fixture(autouse=True)
def _no_logged_in_user(monkeypatch):
    """确定性：默认无 prefer_subscription 用户（账户默认 = byok；个别测试自行覆盖）。"""
    monkeypatch.setattr(ss, "_current_prefer_subscription", lambda: False)


@pytest.fixture()
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(ss, "SETTINGS_FILE", path)
    return path


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ============================================================
# §4 存量迁移映射表（AC-8：三值 + null + 混配全覆盖）
# ============================================================


class TestDeriveAccessMode:
    @pytest.mark.parametrize(
        "settings,expected",
        [
            ({"engine": {"mode": "local"}}, "local"),
            ({"engine": {"mode": "proxy"}}, "cloud"),
            ({"engine": {"mode": "cloud"}}, "cloud"),
            # A1 裁决已废止：direct + 订阅开不再推导为第三态，一律投影为联网
            ({"engine": {"mode": "direct"}}, "cloud"),
            ({}, None),
            ({"engine": {}}, None),
            ({"engine": {"mode": "unknown-value"}}, None),
        ],
    )
    def test_projection_table(self, settings, expected):
        assert ss.derive_access_mode(settings) == expected

    def test_prefer_subscription_no_longer_participates(self):
        """勾选不再参与模式推导（静默语义消灭）：开/关结论一致。"""
        s = {"engine": {"mode": "direct"}}
        assert ss.derive_access_mode(s, prefer_subscription=True) == \
            ss.derive_access_mode(s, prefer_subscription=False) == "cloud"


class TestMigrateAccessMode:
    def test_hosted_migrates_to_cloud_trial(self):
        settings = {"engine": {"mode": "proxy"}, "asr": {"mode": "proxy"}, "access_mode": "hosted"}
        assert ss.migrate_access_mode(settings) is True
        assert settings["access_mode"] == "cloud"
        assert settings["capability_source"] == {"llm": "trial", "asr": "trial"}
        assert settings["capability_source_override"] == {"llm": False, "asr": False}
        assert settings["_settings_ia_migrated"] is True
        # A2 投影不变量：engine.mode=proxy 保留
        assert settings["engine"]["mode"] == "proxy"

    def test_byok_migrates_to_cloud_ownkey(self):
        settings = {"engine": {"mode": "direct"}, "asr": {"mode": "direct"}, "access_mode": "byok",
                    "llm": {"base_url": "https://api.openai.com/v1"}}
        assert ss.migrate_access_mode(settings) is True
        assert settings["access_mode"] == "cloud"
        assert settings["capability_source"] == {"llm": "byok", "asr": "byok"}
        assert settings["capability_source_override"] == {"llm": False, "asr": False}

    def test_byok_with_localhost_llm_detects_local_endpoint(self):
        settings = {"engine": {"mode": "direct"}, "access_mode": "byok",
                    "llm": {"base_url": "http://localhost:11434/v1"}}
        assert ss.migrate_access_mode(settings) is True
        assert settings["capability_source"]["llm"] == "local_endpoint"

    def test_local_stays_local(self):
        settings = {"engine": {"mode": "local"}, "access_mode": "local"}
        assert ss.migrate_access_mode(settings) is True
        assert settings["access_mode"] == "local"
        assert settings["capability_source"] == {"llm": "", "asr": ""}

    def test_null_stays_null_and_triggers_onboarding(self, settings_file):
        _write(settings_file, {})
        assert ss.run_access_mode_migration() is True
        persisted = _read(settings_file)
        assert persisted["access_mode"] is None
        assert persisted["_settings_ia_migrated"] is True
        assert ss.get_access_mode() is None

    def test_mixed_legacy_reads_actual_per_capability(self):
        """混配存量（hosted + asr.mode=direct）：ASR 按实际值读为自带 Key 并标覆盖，冲突明示不静默。"""
        settings = {"engine": {"mode": "proxy"}, "asr": {"mode": "direct"}, "access_mode": "hosted"}
        assert ss.migrate_access_mode(settings) is True
        assert settings["capability_source"] == {"llm": "trial", "asr": "byok"}
        assert settings["capability_source_override"] == {"llm": False, "asr": True}

    def test_migration_is_once(self):
        settings = {"engine": {"mode": "proxy"}, "access_mode": "cloud",
                    "capability_source": {"llm": "byok", "asr": "trial"},
                    "capability_source_override": {"llm": True, "asr": False},
                    "_settings_ia_migrated": True}
        assert ss.migrate_access_mode(settings) is False
        assert settings["capability_source"]["llm"] == "byok"

    def test_voiceprint_field_dropped_on_startup_migration(self, settings_file):
        """第 4 刀：存量 voiceprint 配置键随启动迁移一次性丢弃；注册表特征不属迁移范围。"""
        _write(settings_file, {"engine": {"mode": "local"},
                               "voiceprint": {"provider": "cloud",
                                              "cloud": {"base_url": "https://vp.example", "api_key": "sk-x"}}})
        assert ss.run_access_mode_migration() is True
        persisted = _read(settings_file)
        assert "voiceprint" not in persisted

    def test_expert_mode_no_longer_derived_from_voiceprint(self):
        """第 4 刀：声纹云配置不再参与专家态推导（字段已不存在）。"""
        assert ss.derive_expert_mode({"voiceprint": {"cloud": {"api_key": "sk-vp"}}}) is False


# ============================================================
# §3.1/§3.5 apply_access_mode：两值 + 逐能力来源 + override + A2 投影
# ============================================================


class TestApplyAccessMode:
    def test_invalid_mode_raises(self):
        settings = {"engine": {"mode": "local"}}
        with pytest.raises(ValueError):
            ss.apply_access_mode(settings, "teleport")

    def test_local_projects_engine_mode(self):
        settings = {"engine": {"mode": "proxy", "local": {"model_tier": "standard"}}, "asr": {"mode": "proxy"}}
        ss.apply_access_mode(settings, "local")
        assert settings["access_mode"] == "local"
        assert settings["engine"]["mode"] == "local"
        assert settings["engine"]["local"]["model_tier"] == "standard"

    def test_cloud_with_capability_sources_projects_per_capability(self):
        settings = {"engine": {"mode": "local"}, "asr": {"mode": "proxy"}}
        ss.apply_access_mode(settings, "cloud",
                             sources={"llm": "local_endpoint", "asr": "byok"})
        assert settings["access_mode"] == "cloud"
        # llm=local_endpoint → direct；asr=byok → direct
        assert settings["engine"]["mode"] == "direct"
        assert settings["asr"]["mode"] == "direct"
        assert settings["capability_source_override"] == {"llm": True, "asr": True}

    def test_trial_projects_proxy(self):
        settings = {}
        ss.apply_access_mode(settings, "cloud", sources={"llm": "trial", "asr": "trial"})
        assert settings["engine"]["mode"] == "proxy"
        assert settings["asr"]["mode"] == "proxy"

    def test_legacy_enum_normalized_not_rejected(self):
        """旧客户端提交存量枚举：归一化为联网 + 对应来源，不报错不静默。"""
        settings = {}
        ss.apply_access_mode(settings, "hosted")
        assert settings["access_mode"] == "cloud"
        assert settings["capability_source"] == {"llm": "trial", "asr": "trial"}
        settings = {}
        ss.apply_access_mode(settings, "byok")
        assert settings["access_mode"] == "cloud"
        assert settings["capability_source"] == {"llm": "byok", "asr": "byok"}

    def test_manual_selection_sets_override(self, monkeypatch):
        """详情层任何手动改选即标覆盖（AC-5 持久化前提）。"""
        settings = {"access_mode": "cloud",
                    "capability_source": {"llm": "trial", "asr": "trial"},
                    "capability_source_override": {"llm": False, "asr": False}}
        ss.apply_access_mode(settings, "cloud", sources={"llm": "byok"})
        assert settings["capability_source"]["llm"] == "byok"
        assert settings["capability_source_override"]["llm"] is True
        assert settings["capability_source_override"]["asr"] is False

    def test_cloud_init_fills_account_default_when_unset(self):
        """首次切联网：未初始化的能力补账户默认（显式联动，非静默 override）。"""
        settings = {"access_mode": None, "capability_source": {}, "capability_source_override": {}}
        ss.apply_access_mode(settings, "cloud", sources=None, prefer_subscription=True)
        assert settings["capability_source"] == {"llm": "trial", "asr": "trial"}
        assert settings["capability_source_override"] == {"llm": False, "asr": False}


class TestCapabilityStatus:
    def _settings_with(self, monkeypatch, tmp_path, sources, overrides, access="cloud"):
        import app.settings_store as mod
        f = tmp_path / "settings.json"
        _write(f, {"access_mode": access, "capability_source": sources,
                   "capability_source_override": overrides, "_settings_ia_migrated": True})
        monkeypatch.setattr(mod, "SETTINGS_FILE", f)

    def test_override_wins_and_persists(self, monkeypatch, tmp_path):
        """已覆盖能力不被账户默认改回（AC-5）。"""
        self._settings_with(monkeypatch, tmp_path,
                            {"llm": "byok", "asr": "trial"}, {"llm": True, "asr": False})
        cap = ss.get_capability_status(prefer_subscription=True)  # 勾选开 → 默认 trial
        assert cap["llm"]["effective"] == "byok" and cap["llm"]["override"] is True
        assert cap["asr"]["effective"] == "trial" and cap["asr"]["override"] is False

    def test_default_follows_checkbox(self, monkeypatch, tmp_path):
        self._settings_with(monkeypatch, tmp_path,
                            {"llm": "byok", "asr": "byok"}, {"llm": False, "asr": False})
        cap = ss.get_capability_status(prefer_subscription=True)
        assert cap["llm"]["effective"] == "trial" and cap["asr"]["effective"] == "trial"
        cap = ss.get_capability_status(prefer_subscription=False)
        assert cap["llm"]["effective"] == "byok" and cap["asr"]["effective"] == "byok"

    def test_offline_takeover(self, monkeypatch, tmp_path):
        """离线态第四形态：effective=local 本机接管。"""
        self._settings_with(monkeypatch, tmp_path,
                            {"llm": "trial", "asr": "trial"}, {"llm": False, "asr": False}, access="local")
        cap = ss.get_capability_status(prefer_subscription=True)
        assert cap["llm"]["effective"] == "local" and cap["asr"]["effective"] == "local"


class TestGetAccessModeCompat:
    def test_legacy_persisted_value_projects_to_cloud(self, settings_file):
        _write(settings_file, {"access_mode": "byok", "_access_mode_migrated": True,
                               "_settings_ia_migrated": True})
        assert ss.get_access_mode() == "cloud"

    def test_illegal_persisted_value_falls_to_none(self, settings_file):
        _write(settings_file, {"access_mode": "teleport", "_settings_ia_migrated": True})
        assert ss.get_access_mode() is None

    def test_set_access_mode_persists_with_projection(self, settings_file):
        _write(settings_file, {})
        ss.set_access_mode("cloud", sources={"llm": "trial", "asr": "trial"})
        persisted = _read(settings_file)
        assert persisted["access_mode"] == "cloud"
        assert persisted["engine"]["mode"] == "proxy"
        assert persisted["asr"]["mode"] == "proxy"


# ============================================================
# API 面：POST 写入口收敛 + 反向同步降级 + 切换事务
# ============================================================


class TestSettingsRouterAccessMode:
    def test_get_settings_exposes_capability_not_voiceprint(self, settings_file):
        _write(settings_file, {"access_mode": "cloud", "capability_source": {"llm": "trial", "asr": "byok"},
                               "capability_source_override": {"llm": False, "asr": True},
                               "_settings_ia_migrated": True})
        import app.routers.settings as r
        resp = r.get_settings()
        assert resp["access_mode"] == "cloud"
        assert "voiceprint" not in resp
        assert resp["capability"]["llm"]["effective"] in ("trial", "byok")

    def test_post_access_mode_writes_and_projects(self, settings_file):
        _write(settings_file, {})
        import app.routers.settings as r
        r.save_settings({"access_mode": "cloud", "capability_source": {"llm": "byok", "asr": "trial"}})
        persisted = _read(settings_file)
        assert persisted["access_mode"] == "cloud"
        assert persisted["capability_source"] == {"llm": "byok", "asr": "trial"}
        assert persisted["capability_source_override"] == {"llm": True, "asr": True}
        assert persisted["engine"]["mode"] == "direct"   # llm=byok
        assert persisted["asr"]["mode"] == "proxy"        # asr=trial

    def test_post_voiceprint_ignored_and_legacy_dropped(self, settings_file):
        _write(settings_file, {"voiceprint": {"provider": "cloud"}})
        import app.routers.settings as r
        r.save_settings({"voiceprint": {"provider": "local"}, "output_dir": "data/out/"})
        persisted = _read(settings_file)
        assert "voiceprint" not in persisted

    def test_service_param_save_does_not_realign(self, settings_file):
        """§3.2：新 UI 服务页保存 asr（mode 与存量一致）不再触发反向重对齐。"""
        _write(settings_file, {"engine": {"mode": "direct"}, "asr": {"mode": "direct"},
                               "access_mode": "cloud", "_access_mode_migrated": True,
                               "_settings_ia_migrated": True})
        import app.routers.settings as r
        r.save_settings({"asr": {"mode": "direct", "model": "paraformer-v2"}})
        assert _read(settings_file)["access_mode"] == "cloud"

    def test_legacy_engine_write_still_realigns_in_window(self, settings_file):
        """旧客户端改变投影字段：兼容窗口内仍重对齐（日落前保留）。"""
        _write(settings_file, {"engine": {"mode": "direct"}, "access_mode": "cloud",
                               "_access_mode_migrated": True, "_settings_ia_migrated": True})
        import app.routers.settings as r
        r.save_settings({"engine": {"mode": "local"}})
        assert _read(settings_file)["access_mode"] == "local"

    def test_post_rejects_illegal_access_mode(self, settings_file):
        _write(settings_file, {"access_mode": "cloud"})
        import app.routers.settings as r
        r.save_settings({"access_mode": "teleport"})
        assert _read(settings_file)["access_mode"] == "cloud"


class _StubHost:
    def __init__(self, start_ok=True, stop_ok=True, running=True, code=None):
        self._start_ok, self._stop_ok, self._running, self._code = start_ok, stop_ok, running, code
        self.started = self.stopped = 0

    def start(self):
        self.started += 1
        return {"ok": self._start_ok, "error_code": self._code, "error": None if self._start_ok else "模型缺失"}

    def stop(self):
        self.stopped += 1
        return {"ok": self._stop_ok, "error_code": self._code}

    def is_running(self):
        return self._running


class TestSwitchAccessModeTransaction:
    """AC-2：切换必经事务；任一环节失败 → settings.json 逐字段比对零写入（全量回滚）。"""

    def _patch_host(self, monkeypatch, host):
        import core.engine_host as eh
        monkeypatch.setattr(eh, "get_engine_host", lambda: host, raising=True)

    def test_success_offline_switch_starts_engine_and_writes(self, settings_file, monkeypatch):
        _write(settings_file, {"engine": {"mode": "proxy"}, "access_mode": "cloud",
                               "_settings_ia_migrated": True})
        host = _StubHost(start_ok=True, running=False)
        self._patch_host(monkeypatch, host)
        import app.routers.settings as r
        resp = r.switch_access_mode({"access_mode": "local"})
        assert resp["ok"] is True and host.started == 1
        persisted = _read(settings_file)
        assert persisted["access_mode"] == "local"
        assert persisted["engine"]["mode"] == "local"

    def test_engine_start_failure_writes_nothing(self, settings_file, monkeypatch):
        before = json.dumps({"engine": {"mode": "proxy"}, "access_mode": "cloud",
                             "llm": {"model": "qwen-plus"}, "_settings_ia_migrated": True},
                            ensure_ascii=False)
        _write_path = settings_file
        _write_path.write_text(before, encoding="utf-8")
        host = _StubHost(start_ok=False, code="models_missing")
        self._patch_host(monkeypatch, host)
        import app.routers.settings as r
        resp = r.switch_access_mode({"access_mode": "local"})
        assert resp["ok"] is False and resp["failed_stage"] == "engine_start"
        assert resp["error_code"] == "models_missing"
        # 逐字段比对零写入
        assert _read(_write_path) == json.loads(before)

    def test_engine_stop_failure_rolls_back(self, settings_file, monkeypatch):
        before = {"engine": {"mode": "local"}, "access_mode": "local", "_settings_ia_migrated": True}
        _write(settings_file, before)
        host = _StubHost(stop_ok=False, running=True, code="ipc_error")
        self._patch_host(monkeypatch, host)
        import app.routers.settings as r
        resp = r.switch_access_mode({"access_mode": "cloud",
                                     "capability_source": {"llm": "trial", "asr": "trial"}})
        assert resp["ok"] is False and resp["failed_stage"] == "engine_stop"
        # 全量回滚：逐字段比对零写入
        assert _read(settings_file) == before

    def test_illegal_capability_rejected_before_any_write(self, settings_file, monkeypatch):
        _write(settings_file, {"access_mode": "local"})
        self._patch_host(monkeypatch, _StubHost())
        import app.routers.settings as r
        resp = r.switch_access_mode({"access_mode": "cloud", "capability_source": {"asr": "local_endpoint"}})
        assert resp["ok"] is False and resp["failed_stage"] == "validate"
        assert _read(settings_file) == {"access_mode": "local"}

    def test_routing_status_exposes_capability_and_auto_switch(self, settings_file, monkeypatch):
        _write(settings_file, {"access_mode": "cloud",
                               "capability_source": {"llm": "trial", "asr": "trial"},
                               "capability_source_override": {"llm": False, "asr": False},
                               "_settings_ia_migrated": True})
        import app.routers.settings as r
        resp = r.get_routing_status()
        assert resp["ok"] is True
        assert resp["access_mode"] == "cloud"
        assert "capability" in resp and "auto_switch" in resp and "recent_events" in resp
        assert resp["auto_switch"]["count"] >= 0
