"""
tests/test_model_downloader.py — R5 模型下载器与常驻引擎架构测试（WP-B 后端）

覆盖：引导下载（进度/状态）、SHA256 校验与篡改拒载、断点续传（Range）、
可取消（保留 .part）、磁盘空间预检、存储位置配置、管理员权限门（D-R2）、
MODELSCOPE_CACHE 指向、引擎常驻子进程（ping/stop/篡改拒载启动）、
观测面完整性校验缓存（命中/TTL/失效/门禁不吃缓存）。

内嵌 ModelScope 桩 HTTP 服务器，无真实外网/大模型下载（对齐 R8 CI 约束）。

运行方式：
  pytest tests/test_model_downloader.py -v
"""

import hashlib
import json
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

import app.settings_store as settings_store
import core.model_downloader as downloader
from core.model_registry import MODEL_BY_KEY, get_model_root

TEST_MODEL_KEY = "fsmn-vad"  # 清单中最小的必需模型，用作下载测试载体
TEST_MODEL_ID = MODEL_BY_KEY[TEST_MODEL_KEY]["modelscope_id"]


# ============================================================
# ModelScope 桩服务器 / Stub ModelScope server
# ============================================================

class _StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        srv = self.server
        parsed = urlparse(self.path)
        if parsed.path.endswith("/repo/files"):
            files = []
            for path, content in srv.files.items():
                files.append({
                    "Path": path,
                    "Size": len(content),
                    "Sha256": srv.sha_override.get(path, hashlib.sha256(content).hexdigest()),
                    "Type": "blob",
                })
            body = json.dumps({"Code": 200, "Data": {"Files": files}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path.endswith("/repo"):
            file_path = parse_qs(parsed.query).get("FilePath", [""])[0]
            srv.download_counts[file_path] += 1
            data = srv.content_override.get(file_path, srv.files.get(file_path, b""))
            start = 0
            range_hdr = self.headers.get("Range")
            if range_hdr and srv.support_range:
                srv.range_log.append(range_hdr)
                start = int(range_hdr.split("=", 1)[1].rstrip("-"))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(len(data) - start))
            self.end_headers()
            chunk = srv.chunk_size
            for i in range(start, len(data), chunk):
                self.wfile.write(data[i:i + chunk])
                if srv.chunk_delay:
                    time.sleep(srv.chunk_delay)
            return

        self.send_response(404)
        self.end_headers()


@pytest.fixture
def stub_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    srv.files = {"model.pt": b"FAKE-WEIGHTS-" + bytes(range(256)) * 8, "config.json": b'{"k": 1}'}
    srv.sha_override = {}
    srv.content_override = {}
    srv.support_range = True
    srv.chunk_size = 64 * 1024
    srv.chunk_delay = 0
    srv.download_counts = Counter()
    srv.range_log = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def model_env(tmp_path, monkeypatch, stub_server):
    """隔离 settings/model_dir，并把下载源指向桩服务器。"""
    settings_file = tmp_path / "settings.json"
    model_dir = tmp_path / "models"
    settings_file.write_text(json.dumps({
        "engine": {"mode": "cloud", "local": {"model_dir": str(model_dir), "model_tier": "auto"}},
    }), encoding="utf-8")
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(downloader, "MODELSCOPE_API_BASE", f"http://127.0.0.1:{stub_server.server_address[1]}")
    # 清空进程内任务表，避免跨测试串扰 / Reset in-process job table
    with downloader._jobs_lock:
        downloader._jobs.clear()
    return {"settings_file": settings_file, "model_dir": model_dir, "server": stub_server}


def _wait_job(job_id: str, states: set, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = next(j for j in downloader.get_jobs() if j["id"] == job_id)
        if job["state"] in states:
            return job
        time.sleep(0.05)
    raise AssertionError(f"任务 {job_id} 未在 {timeout}s 内到达状态 {states}: {job}")


def _start(model_key: str = TEST_MODEL_KEY) -> str:
    result = downloader.start_download(model_key)
    assert result["ok"], result
    assert len(result["jobs"]) == 1
    return result["jobs"][0]["id"]


# ============================================================
# 下载主流程 / Download happy path
# ============================================================

class TestDownload:
    def test_download_success_and_integrity(self, model_env):
        job_id = _start()
        job = _wait_job(job_id, {"ready"}, timeout=20)
        assert job["error"] == ""
        assert job["downloaded_bytes"] == job["total_bytes"]

        # 权重落在 ModelScope SDK 兼容布局 hub/{id}/ 下
        root = get_model_root(TEST_MODEL_KEY)
        assert (root / "model.pt").exists()
        assert (root / "config.json").exists()
        assert not list(root.rglob("*.part"))

        # 完整性清单已写入且校验通过 / Integrity manifest written; verify passes
        assert downloader.verify_model(TEST_MODEL_KEY)["status"] == "ready"
        assert downloader.model_status(TEST_MODEL_KEY)["status"] == "ready"

    def test_progress_fields_exposed(self, model_env):
        job_id = _start()
        job = _wait_job(job_id, {"ready"}, timeout=20)
        for field in ("percent", "speed_bps", "eta_seconds", "remaining_bytes"):
            assert field in job

    def test_redownload_skips_ready_model(self, model_env):
        job_id = _start()
        _wait_job(job_id, {"ready"}, timeout=20)
        # 已就绪模型不再创建新任务 / Ready model produces no new job
        result = downloader.start_download(TEST_MODEL_KEY)
        assert result["ok"] and result["jobs"] == []

    def test_unknown_model_rejected(self, model_env):
        result = downloader.start_download("no-such-model")
        assert result["ok"] is False
        assert result["error_code"] == "unknown_model"


# ============================================================
# SHA256 校验与篡改拒载 / Checksum & tamper rejection
# ============================================================

class TestIntegrity:
    def test_checksum_mismatch_retries_once_then_manual(self, model_env):
        srv = model_env["server"]
        # 清单声明的 sha 与实际下发内容不一致 / Declared sha ≠ served bytes
        srv.sha_override["model.pt"] = "0" * 64
        job_id = _start()
        job = _wait_job(job_id, {"failed"}, timeout=30)
        assert "SHA256" in job["error"]
        # 自动重下 ≤1 次：首次 + 1 次重试 / Initial + exactly one retry
        assert srv.download_counts["model.pt"] == downloader.MAX_CHECKSUM_RETRIES + 1
        assert downloader.verify_model(TEST_MODEL_KEY)["status"] == "missing"

    def test_tampered_file_rejected_on_load(self, model_env):
        job_id = _start()
        _wait_job(job_id, {"ready"}, timeout=20)

        target = get_model_root(TEST_MODEL_KEY) / "model.pt"
        original = target.read_bytes()
        target.write_bytes(original[:-1] + bytes([original[-1] ^ 0xFF]))

        result = downloader.verify_model(TEST_MODEL_KEY)
        assert result["status"] == "tampered"
        assert "model.pt" in result["mismatched"]
        assert downloader.model_status(TEST_MODEL_KEY)["status"] == "tampered"

    def test_deleted_file_reported_missing(self, model_env):
        job_id = _start()
        _wait_job(job_id, {"ready"}, timeout=20)
        (get_model_root(TEST_MODEL_KEY) / "config.json").unlink()
        assert downloader.verify_model(TEST_MODEL_KEY)["status"] == "missing"

    def test_concurrent_integrity_saves_do_not_lose_entries(self, model_env):
        """并行写入完整性清单（"all" 下载并发完成）不得丢失条目。
        Parallel save_integrity_entry (concurrent "all" completions) must not drop entries.
        """
        import core.model_registry as registry

        keys = [f"m{i}" for i in range(16)]
        barrier = threading.Barrier(len(keys))

        def _save(k):
            barrier.wait()  # 最大化并发窗口 / maximize the race window
            registry.save_integrity_entry(k, {"f.bin": {"sha256": "a" * 64, "size": 1}})

        threads = [threading.Thread(target=_save, args=(k,)) for k in keys]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        manifest = registry.load_integrity_manifest()
        assert set(manifest.keys()) == set(keys), f"丢失条目: {set(keys) - set(manifest.keys())}"


# ============================================================
# 断点续传与取消 / Resume & cancel
# ============================================================

class TestResumeCancel:
    def test_resume_uses_range_and_completes(self, model_env):
        srv = model_env["server"]
        full = srv.files["model.pt"]
        root = get_model_root(TEST_MODEL_KEY)
        part = root / "model.pt.part"
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(full[:1024])

        job_id = _start()
        job = _wait_job(job_id, {"ready"}, timeout=20)
        assert job["state"] == "ready"
        # 服务端收到 Range 请求，且仅续传剩余部分 / Server saw a Range request
        assert any(r == "bytes=1024-" for r in srv.range_log)
        assert (root / "model.pt").read_bytes() == full
        assert downloader.verify_model(TEST_MODEL_KEY)["status"] == "ready"

    def test_cancel_keeps_part_for_resume(self, model_env):
        srv = model_env["server"]
        srv.files["model.pt"] = b"X" * (8 * 1024 * 1024)  # 8MB
        srv.chunk_size = 32 * 1024
        srv.chunk_delay = 0.01  # 节流保证取消窗口 / Throttle to guarantee a cancel window

        job_id = _start()
        # 等到有实际进度再取消 / Wait for real progress before cancelling
        deadline = time.time() + 10
        while time.time() < deadline:
            job = next(j for j in downloader.get_jobs() if j["id"] == job_id)
            if job["downloaded_bytes"] > 0:
                break
            time.sleep(0.02)
        result = downloader.cancel_download(job_id)
        assert result["ok"] is True
        job = _wait_job(job_id, {"cancelled"}, timeout=15)
        assert job["state"] == "cancelled"
        # .part 保留供续传 / .part retained for resume
        assert (get_model_root(TEST_MODEL_KEY) / "model.pt.part").exists()

    def test_cancel_unknown_job(self, model_env):
        assert downloader.cancel_download("nope")["ok"] is False


# ============================================================
# 磁盘空间预检 / Disk pre-check
# ============================================================

class TestDiskPrecheck:
    def test_insufficient_disk_fails_before_transfer(self, model_env, monkeypatch):
        monkeypatch.setattr(downloader, "get_disk_free_bytes", lambda p=None: 0)
        job_id = _start()
        job = _wait_job(job_id, {"failed"}, timeout=10)
        assert job["error_code"] == "insufficient_disk"
        assert "磁盘空间不足" in job["error"]
        # 未发生任何文件传输 / No file transfer happened
        assert model_env["server"].download_counts.total() == 0


# ============================================================
# 路由与权限（D-R2：管理员写、普通用户只读）
# ============================================================

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_client(client):
    from app.routers.admin import ADMIN_COOKIE, _create_admin_token
    client.cookies.set(ADMIN_COOKIE, _create_admin_token())
    return client


class TestModelsRouter:
    @pytest.fixture(autouse=True)
    def _multi_user_mode(self, monkeypatch):
        """本类校验 D-R2 多用户契约：变更面需管理员 cookie。

        动态读取的 is_local_single_user() 受 REQUIRE_AUTH 环境变量控制；server.py 中间件的
        导入期常量显式钉为 False（否则本类若最先导入 app.server，网关会随环境变量定格
        开启，只读 GET 面被 401 拦截），使本类聚焦 D-R2 路由级权限判定。
        """
        monkeypatch.setenv("REQUIRE_AUTH", "true")
        import app.server as _server

        monkeypatch.setattr(_server, "_REQUIRE_AUTH", False)

    def test_list_open_to_all_users(self, client, model_env):
        resp = client.get("/api/engine/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        keys = {m["key"] for m in data["models"]}
        assert keys == set(MODEL_BY_KEY)
        assert data["model_dir"] == str(model_env["model_dir"])

    def test_download_requires_admin(self, client, model_env):
        resp = client.post("/api/engine/download", json={"model_key": TEST_MODEL_KEY})
        assert resp.status_code == 401

    def test_cancel_requires_admin(self, client, model_env):
        assert client.post("/api/engine/download/abc/cancel").status_code == 401

    def test_engine_start_requires_admin(self, client, model_env):
        assert client.post("/api/engine/start").status_code == 401

    def test_storage_requires_admin(self, client, model_env):
        assert client.post("/api/engine/storage", json={"model_dir": "/tmp/x"}).status_code == 401

    def test_engine_status_readonly_for_all(self, client, model_env):
        resp = client.get("/api/engine/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["mode"] == "cloud"
        assert data["modelscope_cache"]
        # 多用户模式下无管理员 cookie → can_manage 为假（与变更面一致）
        assert data["can_manage"] is False

    def test_admin_download_disk_precheck_sync(self, admin_client, model_env, monkeypatch):
        monkeypatch.setattr(downloader, "get_disk_free_bytes", lambda p=None: 0)
        import app.routers.models as models_router
        monkeypatch.setattr(models_router, "get_disk_free_bytes", lambda p=None: 0)
        resp = admin_client.post("/api/engine/download", json={"model_key": TEST_MODEL_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "insufficient_disk"

    def test_admin_storage_config_persists(self, admin_client, model_env, tmp_path):
        new_dir = str(tmp_path / "custom-models")
        resp = admin_client.post("/api/engine/storage", json={"model_dir": new_dir})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        saved = json.loads(model_env["settings_file"].read_text(encoding="utf-8"))
        assert saved["engine"]["local"]["model_dir"] == new_dir

        resp = admin_client.get("/api/engine/storage")
        assert resp.json()["model_dir"] == new_dir

    def test_verify_endpoint(self, admin_client, model_env):
        job_id = _start()
        _wait_job(job_id, {"ready"}, timeout=20)
        resp = admin_client.post("/api/engine/verify", json={"model_key": TEST_MODEL_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "ready"


# ============================================================
# 常驻引擎子进程架构（Spike §3.2）
# ============================================================

class TestEngineHost:
    def test_modelscope_cache_points_at_model_dir(self, model_env):
        from core.engine_host import build_engine_env
        env = build_engine_env()
        assert env["MODELSCOPE_CACHE"] == str(model_env["model_dir"].resolve())

    def test_worker_command_dev_mode(self, model_env, monkeypatch):
        import sys

        from core.engine_host import build_worker_command
        # 隔离 shell 泄漏的 ENGINE_PYTHON（开发启动脚本常设它指向引擎 venv）
        monkeypatch.delenv("ENGINE_PYTHON", raising=False)
        cmd = build_worker_command()
        assert cmd == [sys.executable, "-m", "core.engine_worker"]

    def test_start_refuses_tampered_models(self, model_env, monkeypatch):
        import core.engine_host as engine_host
        monkeypatch.setattr(engine_host, "check_required_models", lambda: {
            "ready": False, "missing": [], "tampered": ["cam-plus"],
        })
        host = engine_host.EngineHost()
        result = host.start()
        assert result["ok"] is False
        assert result["error_code"] == "models_tampered"
        assert not host.is_running()

    def test_start_refuses_missing_models(self, model_env, monkeypatch):
        import core.engine_host as engine_host
        monkeypatch.setattr(engine_host, "check_required_models", lambda: {
            "ready": False, "missing": ["fsmn-vad"], "tampered": [],
        })
        host = engine_host.EngineHost()
        result = host.start()
        assert result["ok"] is False
        assert result["error_code"] == "models_missing"

    def test_resident_subprocess_ping_and_stop(self, model_env, monkeypatch):
        """常驻子进程真实启动：ping → verify_models → stop（开发态 python -m）。"""
        import core.engine_host as engine_host
        monkeypatch.setattr(engine_host, "check_required_models", lambda: {
            "ready": True, "missing": [], "tampered": [],
        })
        host = engine_host.EngineHost()
        try:
            result = host.start()
            assert result["ok"] is True, result
            assert host.is_running()

            pong = host.request("ping", timeout=30)
            assert pong["ok"] is True
            assert pong["protocol"] == 1

            verify = host.request("verify_models", timeout=30)
            assert verify["ok"] is True
            assert isinstance(verify["models"], dict)

            # WP-E R1 起推理体已落地：未知/缺失 task 显式 unsupported_task，而非静默成功
            infer = host.request("infer", {"audio": "x.wav"}, timeout=30)
            assert infer["ok"] is False
            assert infer["error_code"] == "unsupported_task"
        finally:
            stop = host.stop()
            assert stop["ok"] is True
            assert not host.is_running()

        # 幂等：重复 stop 不报错 / Idempotent stop
        assert host.stop()["ok"] is True


# ============================================================
# 观测面完整性校验缓存（status 提速的后端前提）
# ============================================================

class TestModelsCheckCache:
    """status 走缓存、start 门禁走实时：两者不得互相污染。"""

    @pytest.fixture(autouse=True)
    def _isolate_cache(self):
        import core.engine_host as engine_host
        engine_host.invalidate_models_check()
        yield
        engine_host.invalidate_models_check()

    @staticmethod
    def _patch_check(engine_host, monkeypatch, results):
        """按调用次序依次返回 results（用尽后重复末项），回传调用计数。"""
        calls = {"n": 0}

        def _fake():
            idx = min(calls["n"], len(results) - 1)
            calls["n"] += 1
            return dict(results[idx])

        monkeypatch.setattr(engine_host, "check_required_models", _fake)
        return calls

    def test_second_call_hits_cache(self, model_env, monkeypatch):
        import core.engine_host as engine_host
        calls = self._patch_check(engine_host, monkeypatch, [
            {"ready": True, "missing": [], "tampered": []},
        ])
        first = engine_host.check_required_models_cached()
        second = engine_host.check_required_models_cached()
        assert first["cached"] is False
        assert second["cached"] is True
        assert second["ready"] is True and second["missing"] == []
        assert calls["n"] == 1  # 命中时不重做哈希

    def test_invalidate_forces_recheck(self, model_env, monkeypatch):
        import core.engine_host as engine_host
        calls = self._patch_check(engine_host, monkeypatch, [
            {"ready": True, "missing": [], "tampered": []},
            {"ready": False, "missing": ["fsmn-vad"], "tampered": []},
        ])
        engine_host.check_required_models_cached()
        engine_host.invalidate_models_check()
        after = engine_host.check_required_models_cached()
        assert calls["n"] == 2
        assert after["cached"] is False
        assert after["ready"] is False and after["missing"] == ["fsmn-vad"]

    def test_ttl_expiry_recomputes(self, model_env, monkeypatch):
        import core.engine_host as engine_host
        monkeypatch.setattr(engine_host, "MODELS_CHECK_TTL_SECONDS", 0.0)
        calls = self._patch_check(engine_host, monkeypatch, [
            {"ready": True, "missing": [], "tampered": []},
        ])
        engine_host.check_required_models_cached()
        engine_host.check_required_models_cached()
        assert calls["n"] == 2  # TTL=0 时永不命中

    def test_model_dir_change_bypasses_cache(self, model_env, monkeypatch):
        """换存储目录 = 换一套权重：旧目录的结论不得沿用。"""
        import core.engine_host as engine_host
        import core.model_registry as registry
        calls = self._patch_check(engine_host, monkeypatch, [
            {"ready": True, "missing": [], "tampered": []},
            {"ready": False, "missing": ["fsmn-vad"], "tampered": []},
        ])
        assert engine_host.check_required_models_cached()["cached"] is False
        other = model_env["model_dir"].parent / "other-models"
        monkeypatch.setattr(registry, "get_model_dir", lambda: other)
        second = engine_host.check_required_models_cached()
        assert second["cached"] is False
        assert calls["n"] == 2

    def test_status_uses_cache_and_reports_freshness(self, model_env, monkeypatch):
        import core.engine_host as engine_host
        calls = self._patch_check(engine_host, monkeypatch, [
            {"ready": True, "missing": [], "tampered": []},
        ])
        host = engine_host.EngineHost()
        s1 = host.status()
        s2 = host.status()
        assert s1["models_ready"] is True and s2["models_ready"] is True
        assert s1["models_check_cached"] is False and s2["models_check_cached"] is True
        assert calls["n"] == 1
        assert s2["models_check_age_seconds"] >= 0

    def test_start_gate_never_serves_stale_ready(self, model_env, monkeypatch):
        """缓存里是 ready 旧结论，实时校验已转篡改 → start() 必须拒载（R5）。"""
        import core.engine_host as engine_host
        results = [{"ready": True, "missing": [], "tampered": []}]
        calls = self._patch_check(engine_host, monkeypatch, results)
        assert engine_host.check_required_models_cached()["ready"] is True  # 播种缓存

        results[0] = {"ready": False, "missing": [], "tampered": ["cam-plus"]}
        host = engine_host.EngineHost()
        try:
            result = host.start()
            assert result["ok"] is False
            assert result["error_code"] == "models_tampered"
            assert not host.is_running()
        finally:
            host.stop()
        assert calls["n"] == 2  # 门禁重做了一次实时校验
