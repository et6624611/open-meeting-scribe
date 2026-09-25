"""
tests/test_access_mode_migration.py — REQ-ACCESS-MODE-CARDS T1 迁移与读写（AM-B1）

覆盖 AC-1（§4 映射全组合）、AC-2（expert_mode 自动开启）、AC-3（旧字段兼容窗口读写）。
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
    """确定性：默认无 prefer_subscription 用户（个别测试自行覆盖）。"""
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
# AC-1 §4 迁移映射表：全部组合
# ============================================================


class TestDeriveAccessMode:
    @pytest.mark.parametrize(
        "settings,prefer_sub,expected",
        [
            ({"engine": {"mode": "local"}}, False, "local"),
            ({"engine": {"mode": "local"}}, True, "local"),
            ({"engine": {"mode": "proxy"}}, False, "hosted"),
            ({"engine": {"mode": "proxy"}}, True, "hosted"),
            # A-i1 延伸：cloud 与 proxy 同为云代理计费路径
            ({"engine": {"mode": "cloud"}}, False, "hosted"),
            # A1 裁决：direct + prefer_subscription=false → byok
            ({"engine": {"mode": "direct"}}, False, "byok"),
            # A1 裁决：direct + prefer_subscription=true → hosted
            ({"engine": {"mode": "direct"}}, True, "hosted"),
            # 未配置 → null（触发引导）
            ({}, False, None),
            ({"engine": {}}, False, None),
            ({"engine": {"mode": "unknown-value"}}, False, None),
        ],
    )
    def test_migration_table_all_combinations(self, settings, prefer_sub, expected):
        assert ss.derive_access_mode(settings, prefer_subscription=prefer_sub) == expected

    def test_prefer_subscription_defaults_to_current_user(self, monkeypatch):
        monkeypatch.setattr(
            ss, "_current_prefer_subscription", lambda: True, raising=True
        )
        assert ss.derive_access_mode({"engine": {"mode": "direct"}}) == "hosted"


class TestMigrateAccessMode:
    def test_migrate_writes_fields_and_preserves_legacy(self):
        original = {
            "engine": {"mode": "direct", "local": {"model_tier": "standard"}},
            "llm": {"provider": "OpenAI", "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-real-key-abcdefghij", "model": "gpt-4o"},
            "asr": {"mode": "direct", "api_key": "sk-asr-key-abcdefghijklmn"},
        }
        import copy
        settings = copy.deepcopy(original)

        changed = ss.migrate_access_mode(settings, prefer_subscription=False)

        assert changed is True
        assert settings["access_mode"] == "byok"
        assert settings["_access_mode_migrated"] is True
        # 旧字段逐字节保留（A2 回滚能力）
        for key, value in original.items():
            assert settings[key] == value

    def test_migrate_is_once_and_does_not_rederive(self):
        settings = {"engine": {"mode": "direct"}, "access_mode": "byok",
                    "_access_mode_migrated": True, "expert_mode": False}
        # 即使 prefer_subscription 变化，已迁移也不重推导（迁移是一次性的）
        assert ss.migrate_access_mode(settings, prefer_subscription=True) is False
        assert settings["access_mode"] == "byok"

    def test_migrate_preserves_explicit_expert_mode(self):
        settings = {"engine": {"mode": "proxy"}, "expert_mode": True}
        assert ss.migrate_access_mode(settings, prefer_subscription=False) is True
        assert settings["access_mode"] == "hosted"
        assert settings["expert_mode"] is True

    def test_run_migration_persists(self, settings_file):
        _write(settings_file, {"engine": {"mode": "direct"}})
        assert ss.run_access_mode_migration() is True
        persisted = _read(settings_file)
        assert persisted["access_mode"] == "byok"
        assert persisted["engine"]["mode"] == "direct"
        # 幂等：再次运行不变更、不再落盘
        assert ss.run_access_mode_migration() is False

    def test_unset_stays_null_and_triggers_onboarding(self, settings_file):
        _write(settings_file, {})
        assert ss.run_access_mode_migration() is True
        persisted = _read(settings_file)
        assert persisted["access_mode"] is None
        assert persisted["_access_mode_migrated"] is True
        assert ss.get_access_mode() is None


# ============================================================
# AC-2 expert_mode 自动开启
# ============================================================


class TestDeriveExpertMode:
    def test_standard_config_not_expert(self):
        settings = {
            "engine": {"mode": "direct"},
            "llm": {"provider": "DashScope", "model": "qwen-plus",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "api_key": "sk-normal-user-key-1234"},
            "asr": {"mode": "direct", "model": "paraformer-v2",
                    "base_url": "https://dashscope.aliyuncs.com"},
        }
        assert ss.derive_expert_mode(settings) is False

    @pytest.mark.parametrize(
        "settings",
        [
            # 自定义 LLM base_url 覆盖
            {"llm": {"base_url": "https://api.deepseek.com/v1"}},
            # 自定义 LLM model 覆盖
            {"llm": {"model": "qwen-max"}},
            # 自定义 ASR base_url 覆盖
            {"asr": {"base_url": "https://asr.example.com"}},
            # 自定义 ASR model 覆盖
            {"asr": {"model": "paraformer-v1"}},
            # 旧版 flat api_key（非默认 Key 组合）
            {"api_key": "sk-legacy"},
            # 声纹云配置非空
            {"voiceprint": {"cloud": {"api_key": "sk-vp-key"}}},
            # 声纹 provider 显式偏离 auto
            {"voiceprint": {"provider": "cloud"}},
            # 代理模式下出现自有 ASR Key（非默认 Key 组合）
            {"asr": {"mode": "proxy", "api_key": "sk-stray-key-abcdefghij"}},
        ],
    )
    def test_overrides_enable_expert_mode(self, settings):
        assert ss.derive_expert_mode(settings) is True


# ============================================================
# AC-3 旧字段兼容窗口：读取兼容 + 写路径同步旧字段
# ============================================================


class TestReadWriteCompat:
    def test_get_access_mode_lazy_derives_without_writing(self, settings_file, monkeypatch):
        _write(settings_file, {"engine": {"mode": "proxy"}})
        monkeypatch.setattr(ss, "_current_prefer_subscription", lambda: False)
        assert ss.get_access_mode() == "hosted"
        # 惰性推导不写盘（A-i2：GET 无副作用）
        assert "_access_mode_migrated" not in _read(settings_file)

    def test_get_access_mode_reads_persisted_after_migration(self, settings_file):
        _write(settings_file, {"engine": {"mode": "proxy"}, "access_mode": "byok",
                               "_access_mode_migrated": True})
        # 持久值优先：不因旧字段 proxy 而被改回 hosted
        assert ss.get_access_mode() == "byok"

    def test_set_access_mode_syncs_legacy_fields(self, settings_file):
        _write(settings_file, {"engine": {"mode": "cloud", "local": {"model_tier": "auto"}}})
        ss.set_access_mode("local")
        persisted = _read(settings_file)
        assert persisted["access_mode"] == "local"
        assert persisted["engine"]["mode"] == "local"
        assert persisted["engine"]["local"]["model_tier"] == "auto"  # 其余旧字段保留

        ss.set_access_mode("hosted")
        persisted = _read(settings_file)
        assert persisted["engine"]["mode"] == "proxy"
        assert persisted["asr"]["mode"] == "proxy"

        ss.set_access_mode("byok")
        persisted = _read(settings_file)
        assert persisted["engine"]["mode"] == "direct"
        assert persisted["asr"]["mode"] == "direct"

    def test_set_access_mode_rejects_invalid(self, settings_file):
        _write(settings_file, {})
        with pytest.raises(ValueError):
            ss.set_access_mode("teleport")
        assert _read(settings_file) == {}

    def test_legacy_fields_still_readable(self, settings_file):
        """旧版本模块（engine/asr 读取路径）在兼容窗口内继续可用。"""
        _write(settings_file, {"engine": {"mode": "local"}})
        assert ss.get_engine_config()["mode"] == "local"

    def test_set_expert_mode_completes_migration(self, settings_file):
        _write(settings_file, {"engine": {"mode": "direct"}})
        ss.set_expert_mode(True)
        persisted = _read(settings_file)
        assert persisted["expert_mode"] is True
        assert persisted["access_mode"] == "byok"  # 迁移顺带补全，不被惰性推导反复覆盖
        assert ss.get_expert_mode() is True


# ============================================================
# API 面（app/routers/settings.py）：读写扩展与兼容窗口重对齐
# ============================================================


class TestSettingsRouterAccessMode:
    def test_get_settings_exposes_new_fields(self, settings_file, monkeypatch):
        _write(settings_file, {"engine": {"mode": "direct"}, "access_mode": "byok",
                               "expert_mode": False, "_access_mode_migrated": True})
        import app.routers.settings as r
        resp = r.get_settings()
        assert resp["access_mode"] == "byok"
        assert resp["expert_mode"] is False

    def test_post_settings_applies_access_mode_with_legacy_sync(self, settings_file, monkeypatch):
        _write(settings_file, {})
        import app.routers.settings as r
        for value, expected_engine, expected_asr in [
            ("local", "local", None),
            ("hosted", "proxy", "proxy"),
            ("byok", "direct", "direct"),
        ]:
            r.save_settings({"access_mode": value})
            persisted = _read(settings_file)
            assert persisted["access_mode"] == value
            assert persisted["engine"]["mode"] == expected_engine
            if expected_asr:
                assert persisted["asr"]["mode"] == expected_asr

    def test_post_settings_realigns_on_legacy_engine_write(self, settings_file):
        """兼容窗口：旧客户端只写 engine.mode 时，access_mode 重对齐不漂移。"""
        _write(settings_file, {"engine": {"mode": "direct"}, "access_mode": "byok",
                               "_access_mode_migrated": True})
        import app.routers.settings as r
        r.save_settings({"engine": {"mode": "local"}})
        persisted = _read(settings_file)
        assert persisted["access_mode"] == "local"

    def test_post_settings_ignores_invalid_access_mode(self, settings_file):
        _write(settings_file, {"engine": {"mode": "direct"}, "access_mode": "byok",
                               "_access_mode_migrated": True})
        import app.routers.settings as r
        r.save_settings({"access_mode": "teleport"})
        assert _read(settings_file)["access_mode"] == "byok"

    def test_post_settings_explicit_expert_mode_persisted(self, settings_file):
        _write(settings_file, {})
        import app.routers.settings as r
        r.save_settings({"expert_mode": True})
        persisted = _read(settings_file)
        assert persisted["expert_mode"] is True
        assert persisted["_access_mode_migrated"] is True
