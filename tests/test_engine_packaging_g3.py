"""
tests/test_engine_packaging_g3.py — WP-G G-1/G-3 冻结态打包缺陷回归（B-1/B-2/B-3）

覆盖：
  - B-2 复现与修复：冻结态模型目录不再解析进只读 bundle，落 D-G3 平台锚点；
    MODELSCOPE_CACHE 环境变量优先（引擎子进程与宿主一致）。
  - B-1 修复：冻结态 build_worker_command 定位外置独立引擎包（D-G1 方案 A），
    不再再入主 exe；组件三态判定（not_installed / broken / protocol_mismatch / ready）。
  - B-3 修复：引擎子进程 stderr 进环形缓冲 + 落盘日志 + 脱敏，启动失败回带摘要。
  - 协议版本握手：不匹配拒绝启动（engine_protocol_mismatch，不静默回退云端）。

运行（开发态即可，无需真实冻结包 / 无需 torch）：
    pytest tests/test_engine_packaging_g3.py
"""

import json
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.engine_paths as engine_paths  # noqa: E402
from core import engine_host  # noqa: E402
from core.engine_worker import PROTOCOL_VERSION  # noqa: E402
from core.model_registry import get_model_dir  # noqa: E402


# ─────────────────────────────────────────────────────────────
# 工具：模拟冻结态
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def frozen_win(monkeypatch, tmp_path):
    """模拟 Windows 冻结态：LOCALAPPDATA 锚点 + exe 同级目录。"""
    local_appdata = tmp_path / "LocalAppData"
    local_appdata.mkdir()
    exe_dir = tmp_path / "ProgramFiles" / "OMS"
    exe_dir.mkdir(parents=True)
    fake_exe = exe_dir / "OpenMeetingScribe.exe"
    fake_exe.write_text("stub")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEIPASS"), raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.delenv("OMS_ENGINE_DIR", raising=False)
    monkeypatch.delenv("MODELSCOPE_CACHE", raising=False)
    return {"tmp": tmp_path, "local_appdata": local_appdata, "exe_dir": exe_dir}


def _make_engine_package(root: Path, protocol: int = PROTOCOL_VERSION, with_manifest: bool = True) -> Path:
    """构造一个假引擎包目录（可执行体 + manifest），返回引擎根。"""
    root.mkdir(parents=True, exist_ok=True)
    exe = root / engine_paths.engine_exe_name()
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    if with_manifest:
        manifest = {
            "component": "oms-local-engine",
            "engine_version": "9.9.9-test",
            "protocol_version": protocol,
            "entry": exe.name,
            "files": {},
        }
        (root / engine_paths.ENGINE_MANIFEST_NAME).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
    return root


@pytest.fixture
def no_settings(monkeypatch):
    """隔离 settings.json（引擎配置全部走默认值）。"""
    import app.settings_store as settings_store
    monkeypatch.setattr(settings_store, "load_settings", lambda: {})


# ─────────────────────────────────────────────────────────────
# B-2：模型目录锚点
# ─────────────────────────────────────────────────────────────

class TestB2ModelDirAnchor:
    def test_frozen_win_model_dir_anchors_localappdata(self, frozen_win, no_settings):
        """B-2 修复：冻结态 Win 默认模型目录 = %LOCALAPPDATA%\\OpenMeetingScribe\\models，
        不再是相对路径（旧行为会解析进只读 _MEIPASS bundle）。"""
        model_dir = get_model_dir()
        anchor = frozen_win["local_appdata"] / "OpenMeetingScribe"
        assert model_dir == anchor / "models"
        assert "_MEIPASS" not in str(model_dir)
        assert model_dir.is_absolute()

    def test_frozen_win_cwd_not_bundle_root(self, frozen_win, no_settings, monkeypatch):
        """B-2 修复：引擎子进程 cwd = 引擎根（可执行体同级），不再是 __file__ 推导的 bundle 根。"""
        engine_root = _make_engine_package(frozen_win["local_appdata"] / "OpenMeetingScribe" / "engine")
        cmd = engine_host.build_worker_command()
        assert cmd == [str(engine_root / engine_paths.engine_exe_name())]
        # start() 冻结态 cwd 取 cmd[0] 的父目录（见 engine_host.start）
        assert str(Path(cmd[0]).resolve().parent) == str(engine_root.resolve())

    def test_modelscope_cache_env_wins(self, monkeypatch, tmp_path, no_settings):
        """引擎子进程内 MODELSCOPE_CACHE（宿主注入）优先于 settings/默认值。"""
        monkeypatch.setenv("MODELSCOPE_CACHE", str(tmp_path / "weights"))
        assert get_model_dir() == tmp_path / "weights"

    def test_dev_mode_keeps_data_models(self, monkeypatch, no_settings):
        """开发态默认仍 data/models/（D-G3：开发态不变）。"""
        monkeypatch.delenv("MODELSCOPE_CACHE", raising=False)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert get_model_dir() == Path("data/models/")


# ─────────────────────────────────────────────────────────────
# B-1：独立引擎包定位与组件三态
# ─────────────────────────────────────────────────────────────

class TestB1EnginePackage:
    def test_frozen_no_longer_reenters_main_exe(self, frozen_win, no_settings):
        """B-1 修复：组件未装时 build_worker_command 返回 None（拒绝启动），
        绝不返回 [主 exe, --engine-worker]（主包 excludes torch，再入必然失败）。"""
        assert engine_host.build_worker_command() is None

    def test_locates_engine_next_to_exe(self, frozen_win, no_settings):
        """搜索序③：主程序 exe 同级 engine/（Win Inno [Components] 布局，G-4）。"""
        engine_root = _make_engine_package(frozen_win["exe_dir"] / "engine")
        cmd = engine_host.build_worker_command()
        assert cmd == [str(engine_root / engine_paths.engine_exe_name())]

    def test_env_override_first(self, frozen_win, no_settings, monkeypatch):
        """搜索序①：OMS_ENGINE_DIR 显式覆盖优先。"""
        override = _make_engine_package(frozen_win["tmp"] / "custom-engine")
        _make_engine_package(frozen_win["exe_dir"] / "engine")
        monkeypatch.setenv("OMS_ENGINE_DIR", str(override))
        cmd = engine_host.build_worker_command()
        assert cmd == [str(override / engine_paths.engine_exe_name())]

    def test_component_state_not_installed(self, frozen_win, no_settings):
        st = engine_host.get_component_status()
        assert st["state"] == "not_installed"
        assert st["searched"]  # 附带已搜索目录（可行动提示）

    def test_component_state_ready(self, frozen_win, no_settings):
        _make_engine_package(frozen_win["local_appdata"] / "OpenMeetingScribe" / "engine")
        st = engine_host.get_component_status()
        assert st["state"] == "ready"
        assert st["engine_version"] == "9.9.9-test"

    def test_component_state_broken(self, frozen_win, no_settings):
        """可执行体在、manifest 缺失/损坏 → broken（三态指引：重装组件）。"""
        _make_engine_package(
            frozen_win["local_appdata"] / "OpenMeetingScribe" / "engine", with_manifest=False
        )
        assert engine_host.get_component_status()["state"] == "broken"

    def test_component_state_protocol_mismatch(self, frozen_win, no_settings):
        _make_engine_package(
            frozen_win["local_appdata"] / "OpenMeetingScribe" / "engine",
            protocol=PROTOCOL_VERSION + 1,
        )
        st = engine_host.get_component_status()
        assert st["state"] == "protocol_mismatch"

    def test_start_refuses_on_missing_component(self, frozen_win, no_settings):
        """D-G1 子项③：组件缺失 → 拒绝启动 + 可行动提示（不静默回退云端）。"""
        result = engine_host.EngineHost().start()
        assert result["ok"] is False
        assert result["error_code"] == "engine_component_missing"
        assert "安装本地引擎" in result["error"]

    def test_dev_mode_state(self, monkeypatch, no_settings):
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert engine_host.get_component_status()["state"] == "dev_mode"


# ─────────────────────────────────────────────────────────────
# B-3：stderr 收集 + 脱敏 + 协议握手（真实子进程驱动）
# ─────────────────────────────────────────────────────────────

_FAKE_WORKER = r"""
import json, sys
sys.stderr.write("boot noise token=supersecret123 sk-abcdefgh12345678\n")
sys.stderr.write("ENGINE_STDERR_MARKER funasr import ok\n")
sys.stderr.flush()
line = sys.stdin.readline()
req = json.loads(line)
if req.get("cmd") == "ping":
    resp = {"id": req.get("id"), "ok": True, "protocol": PROTOCOL}
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()
# 排空后续指令，等待 stop
for line in sys.stdin:
    try:
        req = json.loads(line)
    except Exception:
        continue
    if req.get("cmd") == "stop":
        break
"""


def _fake_worker_script(tmp_path: Path, protocol: int) -> Path:
    script = tmp_path / "fake_worker.py"
    script.write_text(_FAKE_WORKER.replace("PROTOCOL", str(protocol)), encoding="utf-8")
    return script


@pytest.fixture
def dev_host_env(monkeypatch, tmp_path, no_settings):
    """开发态 EngineHost.start 测试环境：绕过模型预检/组件判定，stderr 日志落 tmp。"""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("MODELSCOPE_CACHE", raising=False)
    monkeypatch.setattr(engine_host, "check_required_models",
                        lambda: {"ready": True, "missing": [], "tampered": []})
    monkeypatch.setattr(engine_host, "get_component_status", lambda: {"state": "dev_mode"})
    monkeypatch.setattr(engine_paths, "get_logs_dir", lambda: tmp_path / "logs")
    return tmp_path


class TestB3StderrAndHandshake:
    def test_stderr_captured_redacted_and_logged(self, dev_host_env, monkeypatch):
        tmp_path = dev_host_env
        script = _fake_worker_script(tmp_path, PROTOCOL_VERSION)
        monkeypatch.setattr(engine_host, "build_worker_command",
                            lambda: [sys.executable, str(script)])

        host = engine_host.EngineHost()
        result = host.start()
        try:
            assert result["ok"] is True, result
            # stderr 泵线程为异步，等待标记行出现
            summary = ""
            for _ in range(100):
                summary = host.get_stderr_summary()
                if "ENGINE_STDERR_MARKER" in summary:
                    break
                threading.Event().wait(0.05)
            assert "ENGINE_STDERR_MARKER" in summary
            # 脱敏：凭据样式不得原文出现
            assert "supersecret123" not in summary
            assert "sk-abcdefgh12345678" not in summary
            # 落盘日志（B-3：<锚点>/logs/engine-stderr.log）
            log_file = tmp_path / "logs" / engine_host.ENGINE_STDERR_LOG_NAME
            assert log_file.is_file()
            content = log_file.read_text(encoding="utf-8")
            assert "ENGINE_STDERR_MARKER" in content
            assert "supersecret123" not in content
        finally:
            host.stop()

    def test_protocol_mismatch_refuses_start(self, dev_host_env, monkeypatch):
        """D-G1 子项③：ping 通但协议版本不匹配 → 拒绝启动，错误码 engine_protocol_mismatch。"""
        tmp_path = dev_host_env
        script = _fake_worker_script(tmp_path, PROTOCOL_VERSION + 999)
        monkeypatch.setattr(engine_host, "build_worker_command",
                            lambda: [sys.executable, str(script)])

        host = engine_host.EngineHost()
        result = host.start()
        try:
            assert result["ok"] is False
            assert result["error_code"] == "engine_protocol_mismatch"
            assert "升级本地引擎组件" in result["error"]
        finally:
            host.stop()

    def test_start_failure_carries_stderr_summary(self, dev_host_env, monkeypatch):
        """启动失败（进程早退）→ error.detail 携带 stderr 尾部摘要（可诊断性）。"""
        tmp_path = dev_host_env
        script = tmp_path / "crash_worker.py"
        script.write_text(
            "import sys\nsys.stderr.write('FATAL_IMPORT_ERROR marker\\n')\nsys.exit(3)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(engine_host, "build_worker_command",
                            lambda: [sys.executable, str(script)])
        monkeypatch.setattr(engine_host, "ENGINE_START_TIMEOUT", 5)

        host = engine_host.EngineHost()
        result = host.start()
        assert result["ok"] is False
        assert result["error_code"] == "engine_unhealthy"
        assert "FATAL_IMPORT_ERROR" in result["detail"].get("stderr_tail", "")
        assert "重试" in result["error"]  # D-G5：可行动提示，不直丢 engine_unhealthy 原文


class TestRedaction:
    @pytest.mark.parametrize("raw,masked", [
        ("api key sk-live_ABC123456789 end", "sk-live_ABC123456789"),
        ("Authorization: Bearer eyJhbGciOi.abc=", "eyJhbGciOi.abc="),
        ("config token=hunter2 loaded", "hunter2"),
        ("password: abc123", "abc123"),
    ])
    def test_redact(self, raw, masked):
        assert masked not in engine_host.redact_stderr_line(raw)

    def test_plain_lines_untouched(self):
        line = "funasr 1.4.16 imported in 42s"
        assert engine_host.redact_stderr_line(line) == line


# ─────────────────────────────────────────────────────────────
# AC-7：主包 spec 一字不动（静态守护，防误改）
# ─────────────────────────────────────────────────────────────

class TestAC7MainSpecUntouched:
    def test_main_specs_have_no_engine_entry(self):
        """引擎入口 engine_entry.py 只能出现在 pyinstaller_engine.spec。"""
        for spec in ("build/pyinstaller.spec", "build/pyinstaller_macos.spec"):
            text = (PROJECT_ROOT / spec).read_text(encoding="utf-8")
            assert "engine_entry" not in text, f"{spec} 被引擎包污染（违反 D-G1/AC-7）"
            assert "'torch'" in text or '"torch"' in text, f"{spec} excludes 屏障缺失"

    def test_engine_spec_is_separate_file(self):
        assert (PROJECT_ROOT / "build" / "pyinstaller_engine.spec").is_file()
