"""
tests/test_percap_migration.py — 逐能力算力来源：迁移、写入、投影与切换事务

覆盖：
  - ensure_percap_migrated：存量 access_mode → capability_source 映射，移除旧字段，幂等
  - apply_capability_source / set_capability_source：逐能力校验、"" 允许、旧字段投影
  - get_capability_status：effective = 显式值（"" = 未设置）
  - run_percap_migration：启动迁移丢弃 access_mode / voiceprint
  - POST /api/settings/capability 事务：ASR 进入 local 启停引擎、失败全量回滚
运行：pytest tests/test_percap_migration.py -v
"""

import json

import pytest

# 预导入：防 app.store 桩在首次导入时被永久绑定进路由模块
import app.routers.settings as settings_router  # noqa: F401
import app.server  # noqa: F401
import app.settings_store as ss


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
# ensure_percap_migrated：存量映射
# ============================================================


class TestEnsurePercapMigrated:
    def test_local_maps_to_asr_local_and_llm_local_endpoint(self):
        s = {"access_mode": "local", "engine": {"mode": "local"},
             "llm": {"base_url": "http://localhost:11434/v1"}}
        assert ss.ensure_percap_migrated(s) is True
        assert s["capability_source"]["asr"] == "local"
        assert s["capability_source"]["llm"] == "local_endpoint"
        assert "access_mode" not in s
        assert "capability_source_override" not in s
        assert s["_percap_migrated"] is True

    def test_local_llm_nonlocalhost_falls_byok(self):
        s = {"access_mode": "local", "llm": {"base_url": "https://api.openai.com/v1"}}
        ss.ensure_percap_migrated(s)
        assert s["capability_source"]["llm"] == "byok"
        assert s["capability_source"]["asr"] == "local"

    def test_cloud_keeps_existing_sources(self):
        s = {"access_mode": "cloud", "capability_source": {"llm": "byok", "asr": "trial"}}
        ss.ensure_percap_migrated(s)
        assert s["capability_source"] == {"llm": "byok", "asr": "trial"}
        assert "access_mode" not in s

    def test_hosted_seeds_trial(self):
        s = {"access_mode": "hosted"}
        ss.ensure_percap_migrated(s)
        assert s["capability_source"] == {"llm": "trial", "asr": "trial"}

    def test_byok_seeds_byok(self):
        s = {"access_mode": "byok", "llm": {"base_url": "https://api.openai.com/v1"}}
        ss.ensure_percap_migrated(s)
        assert s["capability_source"]["llm"] == "byok"
        assert s["capability_source"]["asr"] == "byok"

    def test_null_leaves_unset(self):
        s = {}
        ss.ensure_percap_migrated(s)
        assert s["capability_source"] == {"llm": "", "asr": ""}

    def test_idempotent(self):
        s = {"access_mode": "local"}
        assert ss.ensure_percap_migrated(s) is True
        assert ss.ensure_percap_migrated(s) is False

    def test_projects_legacy_engine_mode_local(self):
        s = {"access_mode": "local", "llm": {"base_url": "http://localhost:11434/v1"}}
        ss.ensure_percap_migrated(s)
        assert s["engine"]["mode"] == "local"  # asr=local → 旧字段投影


# ============================================================
# apply / set capability source
# ============================================================


class TestApplyCapabilitySource:
    def test_valid_write_and_persist(self, settings_file):
        _write(settings_file, {"capability_source": {"llm": "trial", "asr": "trial"}})
        ss.set_capability_source({"asr": "local"})
        assert _read(settings_file)["capability_source"]["asr"] == "local"

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError):
            ss.apply_capability_source({}, {"llm": "bogus"})

    def test_llm_local_not_allowed(self):
        with pytest.raises(ValueError):
            ss.apply_capability_source({}, {"llm": "local"})

    def test_asr_local_allowed(self):
        s = {}
        ss.apply_capability_source(s, {"asr": "local"})
        assert s["capability_source"]["asr"] == "local"

    def test_unset_allowed(self):
        s = {"capability_source": {"llm": "trial", "asr": "trial"}}
        ss.apply_capability_source(s, {"llm": ""})
        assert s["capability_source"]["llm"] == ""


# ============================================================
# get_capability_status
# ============================================================


class TestGetCapabilityStatus:
    def test_effective_equals_explicit(self, settings_file):
        _write(settings_file, {"capability_source": {"llm": "byok", "asr": "local"}})
        cap = ss.get_capability_status()
        assert cap["llm"]["effective"] == "byok"
        assert cap["asr"]["effective"] == "local"

    def test_unset_returns_empty(self, settings_file):
        _write(settings_file, {})
        cap = ss.get_capability_status()
        assert cap["llm"]["effective"] == "" and cap["asr"]["effective"] == ""


# ============================================================
# run_percap_migration（启动钩子）
# ============================================================


class TestRunPercapMigration:
    def test_drops_access_mode_and_voiceprint(self, settings_file):
        _write(settings_file, {
            "access_mode": "cloud",
            "capability_source": {"llm": "trial", "asr": "trial"},
            "voiceprint": {"provider": "cloud"},
        })
        assert ss.run_percap_migration() is True
        persisted = _read(settings_file)
        assert "access_mode" not in persisted
        assert "voiceprint" not in persisted
        assert persisted["_percap_migrated"] is True


# ============================================================
# POST /api/settings/capability 事务
# ============================================================


class _FakeHost:
    def __init__(self, ok=True):
        self.ok = ok
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        return {"ok": self.ok}

    def stop(self):
        self.stopped = True
        return {"ok": self.ok}

    def is_running(self):
        return self.started and not self.stopped


class TestSwitchCapabilityTransaction:
    def test_asr_to_local_starts_engine_and_writes(self, settings_file, monkeypatch):
        import core.engine_host as eh
        _write(settings_file, {"capability_source": {"llm": "trial", "asr": "trial"}})
        host = _FakeHost()
        monkeypatch.setattr(eh, "get_engine_host", lambda: host)
        res = settings_router.switch_capability_source({"capability_source": {"asr": "local"}})
        assert res["ok"] is True
        assert host.started is True
        assert _read(settings_file)["capability_source"]["asr"] == "local"

    def test_engine_start_failure_writes_nothing(self, settings_file, monkeypatch):
        import core.engine_host as eh
        _write(settings_file, {"capability_source": {"llm": "trial", "asr": "trial"}})
        host = _FakeHost(ok=False)
        monkeypatch.setattr(eh, "get_engine_host", lambda: host)
        res = settings_router.switch_capability_source({"capability_source": {"asr": "local"}})
        assert res["ok"] is False and res["failed_stage"] == "engine_start"
        assert _read(settings_file)["capability_source"]["asr"] == "trial"  # 未落盘

    def test_invalid_capability_rejected_before_write(self, settings_file):
        _write(settings_file, {"capability_source": {"llm": "trial", "asr": "trial"}})
        res = settings_router.switch_capability_source({"capability_source": {"llm": "bogus"}})
        assert res["ok"] is False and res["failed_stage"] == "validate"
        assert _read(settings_file)["capability_source"]["llm"] == "trial"

    def test_llm_source_change_does_not_touch_engine(self, settings_file, monkeypatch):
        import core.engine_host as eh
        _write(settings_file, {"capability_source": {"llm": "trial", "asr": "trial"}})
        host = _FakeHost()
        monkeypatch.setattr(eh, "get_engine_host", lambda: host)
        res = settings_router.switch_capability_source({"capability_source": {"llm": "byok"}})
        assert res["ok"] is True
        assert host.started is False and host.stopped is False
