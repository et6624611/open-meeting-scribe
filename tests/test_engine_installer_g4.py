"""
tests/test_engine_installer_g4.py — WP-G G-4/G-4b 引擎组件安装通道单测

覆盖（D-G1 子项①三条通道共用的核心同步路径 install_from_zip）：
  - 成功安装：解包 → manifest 逐文件 SHA256 校验 → 原子换入 <anchor>/engine/
  - 单层顶级目录（OMSEngine/...）自动剥壳
  - 失败路径：zip 不存在 / zip 整体校验失败 / manifest 缺失 / 文件校验失败 / zip-slip 拒绝
  - 升级换入：旧 engine/ 被替换且 engine.old 清理
  - Unix 可执行位
  - resolve_download_url 解析序

不触网、不触真实锚点目录（monkeypatch get_runtime_anchor → tmp_path）。
"""

import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

import core.engine_installer as ei


# ─────────────────────────── fixtures ───────────────────────────

@pytest.fixture(autouse=True)
def _reset_install_state():
    """每个用例前后重置模块级安装状态与取消标志（进程内单实例）。"""
    with ei._install_lock:
        ei._install_state.update({
            "running": False, "stage": "idle", "percent": 0.0,
            "bytes_done": 0, "bytes_total": 0, "ok": None,
            "error": None, "error_code": None, "target_dir": None,
            "finished_at": None,
        })
    ei._cancel_flag.clear()
    yield
    ei._cancel_flag.clear()


@pytest.fixture
def anchor(tmp_path, monkeypatch):
    """隔离运行时锚点：install 落位 tmp 而非真实 data/ 或 LOCALAPPDATA。"""
    a = tmp_path / "anchor"
    a.mkdir()
    monkeypatch.setattr("core.engine_paths.get_runtime_anchor", lambda: a)
    return a


# ─────────────────────────── helpers ───────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(files: dict[str, bytes]) -> bytes:
    # 与 build/make_engine_manifest.py 同规则：key 为相对引擎根路径（不含 zip 顶级目录）
    entries = {}
    for rel, data in files.items():
        entries[rel] = {"sha256": _sha256(data), "size": len(data)}
    return json.dumps({
        "component": "oms-engine",
        "engine_version": "9.9.9-test",
        "protocol_version": 1,
        "platform": "test",
        "files": entries,
    }, ensure_ascii=False).encode("utf-8")


def _make_zip(zip_path: Path, files: dict[str, bytes], top: str = "",
              extra_members: dict[str, bytes] | None = None,
              manifest_bytes: bytes | None = None) -> Path:
    """构建引擎包 zip。files 为引擎内容（含 manifest 由本函数生成，可用
    manifest_bytes 覆盖以注入损坏 manifest）；extra_members 原样写入（zip-slip 注入用）。"""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for rel, data in files.items():
            name = f"{top}/{rel}" if top else rel
            zf.writestr(name, data)
        mf = manifest_bytes if manifest_bytes is not None else _manifest(files)
        name = f"{top}/engine-manifest.json" if top else "engine-manifest.json"
        zf.writestr(name, mf)
        for name, data in (extra_members or {}).items():
            zf.writestr(name, data)
    return zip_path


_ENGINE_FILES = {
    "OMSEngine": b"#!/bin/sh\necho fake-engine\n",
    "_internal/base_library.zip": b"PK\x03\x04fake",
}


# ─────────────────────────── 成功路径 ───────────────────────────

class TestInstallSuccess:
    def test_install_from_zip_flat(self, anchor):
        zip_path = _make_zip(anchor.parent / "pkg.zip", _ENGINE_FILES)
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is True
        assert result["stage"] == "done"
        engine_dir = anchor / "engine"
        assert (engine_dir / "OMSEngine").is_file()
        assert (engine_dir / "engine-manifest.json").is_file()
        assert (engine_dir / "_internal" / "base_library.zip").is_file()
        assert not (anchor / "engine.new").exists()
        assert not (anchor / "engine.old").exists()

    def test_install_strips_single_top_dir(self, anchor):
        zip_path = _make_zip(anchor.parent / "pkg.zip", _ENGINE_FILES, top="OMSEngine")
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is True
        assert (anchor / "engine" / "OMSEngine").is_file()

    def test_unix_exec_bit(self, anchor):
        zip_path = _make_zip(anchor.parent / "pkg.zip", _ENGINE_FILES)
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is True
        exe = anchor / "engine" / "OMSEngine"
        if os.name != "nt":
            assert exe.stat().st_mode & 0o111

    def test_upgrade_replaces_old_engine(self, anchor):
        # 先装 v1
        z1 = _make_zip(anchor.parent / "v1.zip", {"OMSEngine": b"v1"})
        assert ei.install_from_zip(z1)["ok"] is True
        # 再装 v2：旧目录被替换，engine.old 清理
        z2 = _make_zip(anchor.parent / "v2.zip", {"OMSEngine": b"v2"})
        assert ei.install_from_zip(z2)["ok"] is True
        assert (anchor / "engine" / "OMSEngine").read_bytes() == b"v2"
        assert not (anchor / "engine.old").exists()

    def test_state_reflects_progress(self, anchor):
        zip_path = _make_zip(anchor.parent / "pkg.zip", _ENGINE_FILES)
        ei.install_from_zip(zip_path)
        st = ei.get_install_state()
        assert st["running"] is False
        assert st["percent"] == 100.0
        assert st["target_dir"] == str(anchor / "engine")
        assert st["finished_at"]


# ─────────────────────────── 失败路径 ───────────────────────────

class TestInstallFailures:
    def test_zip_not_found(self, anchor):
        result = ei.install_from_zip(anchor / "missing.zip")
        assert result["ok"] is False
        assert result["error_code"] == "zip_not_found"

    def test_zip_sha256_mismatch(self, anchor):
        zip_path = _make_zip(anchor.parent / "pkg.zip", _ENGINE_FILES)
        result = ei.install_from_zip(zip_path, expected_sha256="0" * 64)
        assert result["ok"] is False
        assert result["error_code"] == "checksum_mismatch"
        assert not (anchor / "engine").exists()

    def test_zip_sha256_match_passes(self, anchor):
        zip_path = _make_zip(anchor.parent / "pkg.zip", _ENGINE_FILES)
        good = _sha256(zip_path.read_bytes())
        assert ei.install_from_zip(zip_path, expected_sha256=good)["ok"] is True

    def test_manifest_missing(self, anchor):
        zip_path = anchor.parent / "pkg.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("OMSEngine", b"fake")
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is False
        assert result["error_code"] == "manifest_missing"
        assert not (anchor / "engine").exists()
        assert not (anchor / "engine.new").exists()  # 失败清理暂存

    def test_manifest_invalid_json(self, anchor):
        zip_path = _make_zip(anchor.parent / "pkg.zip", _ENGINE_FILES,
                             manifest_bytes=b"{not-json")
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is False
        assert result["error_code"] == "manifest_invalid"

    def test_file_checksum_mismatch(self, anchor):
        mf = _manifest({"OMSEngine": b"original"})
        zip_path = anchor.parent / "pkg.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("OMSEngine", b"tampered!!")  # 与 manifest 不符
            zf.writestr("engine-manifest.json", mf)
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is False
        assert result["error_code"] == "checksum_mismatch"
        assert "OMSEngine" in result["error"]
        assert not (anchor / "engine").exists()

    def test_file_missing_vs_manifest(self, anchor):
        mf = _manifest({"OMSEngine": b"x", "missing.dll": b"y"})
        zip_path = anchor.parent / "pkg.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("OMSEngine", b"x")
            zf.writestr("engine-manifest.json", mf)
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is False
        assert result["error_code"] == "checksum_mismatch"

    def test_zip_slip_rejected(self, anchor):
        zip_path = _make_zip(
            anchor.parent / "pkg.zip", _ENGINE_FILES,
            extra_members={"../evil.txt": b"pwned"},
        )
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is False
        assert result["error_code"] == "bad_archive"
        assert not (anchor.parent / "evil.txt").exists()
        assert not (anchor / "engine").exists()

    def test_failed_install_keeps_previous_engine(self, anchor):
        good = _make_zip(anchor.parent / "good.zip", {"OMSEngine": b"v1"})
        assert ei.install_from_zip(good)["ok"] is True
        bad = _make_zip(anchor.parent / "bad.zip", _ENGINE_FILES,
                        manifest_bytes=b"{broken")
        assert ei.install_from_zip(bad)["ok"] is False
        # 既有安装不受失败升级影响
        assert (anchor / "engine" / "OMSEngine").read_bytes() == b"v1"


# ─────────────────────────── verify_manifest_files ───────────────────────────

class TestVerifyManifestFiles:
    def test_all_good(self, tmp_path):
        (tmp_path / "a.bin").write_bytes(b"aaa")
        mf = {"files": {"a.bin": {"sha256": _sha256(b"aaa")}}}
        assert ei.verify_manifest_files(tmp_path, mf) == []

    def test_bad_and_missing(self, tmp_path):
        (tmp_path / "a.bin").write_bytes(b"tampered")
        mf = {"files": {
            "a.bin": {"sha256": _sha256(b"aaa")},
            "gone.bin": {"sha256": _sha256(b"bbb")},
        }}
        bad = ei.verify_manifest_files(tmp_path, mf)
        assert set(bad) == {"a.bin", "gone.bin"}


# ─────────────────────────── resolve_download_url ───────────────────────────

class TestResolveDownloadUrl:
    def test_explicit_wins(self, monkeypatch):
        monkeypatch.setattr("app.settings_store.get_engine_config",
                            lambda: {"local": {"component_url": "http://cfg/x.zip"}})
        assert ei.resolve_download_url("http://explicit/y.zip") == "http://explicit/y.zip"

    def test_settings_component_url(self, monkeypatch):
        monkeypatch.setattr("app.settings_store.get_engine_config",
                            lambda: {"local": {"component_url": "http://cfg/x.zip"}})
        assert ei.resolve_download_url(None) == "http://cfg/x.zip"

    def test_default_release_convention(self, monkeypatch):
        monkeypatch.setattr("app.settings_store.get_engine_config",
                            lambda: {"local": {}})
        url = ei.resolve_download_url(None)
        assert url.startswith(ei.DEFAULT_RELEASE_BASE)
        assert url.endswith(f"OMSEngine-{ei._platform_tag()}.zip")


# ─────────────────────────── 并发保护 ───────────────────────────

class TestConcurrencyGuard:
    def test_second_install_rejected_while_running(self, anchor, monkeypatch):
        with ei._install_lock:
            ei._install_state["running"] = True
        zip_path = _make_zip(anchor.parent / "pkg.zip", _ENGINE_FILES)
        result = ei.install_from_zip(zip_path)
        assert result["ok"] is False
        assert result["error_code"] == "install_in_progress"

        started = ei.start_download_install("http://example.invalid/x.zip")
        assert started["ok"] is False
        assert started["error_code"] == "install_in_progress"
