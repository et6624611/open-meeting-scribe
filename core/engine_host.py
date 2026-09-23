"""
core/engine_host.py — 本地引擎常驻子进程宿主（R5 / WP-B）

架构约束（Spike §3.2，PRD R5 实施约束①②③）：
  1. 常驻子进程：冻结态 funasr 冷 import 最高 86s，引擎启动一次后复用，
     禁止每任务冷启动；
  2. `__main__` 保护 + 显式 multiprocessing.freeze_support()：见 core/engine_worker.py
     与 desktop.py 入口，防止冻结包被子进程重复引导；
  3. onedir 冻结代码包与模型权重分目录：MODELSCOPE_CACHE 指向 settings 配置的
     模型目录（默认 data/models/），权重永不进冻结包。

宿主职责：
  - 启动前模型完整性预检（篡改拒载，R5 验收）
  - 子进程生命周期（启动 / 健康检查 / 停止）
  - JSON Lines 请求转发（core/engine_worker.py 为对端）
"""

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# 引擎子进程启动超时（开发态 python -m 冷启动秒级；冻结态首次 import 可达 86s+）
# Engine subprocess start timeout (frozen funasr cold import can take 86s+)
ENGINE_START_TIMEOUT = 120
ENGINE_REQUEST_TIMEOUT = 180
ENGINE_STOP_TIMEOUT = 10

# 冻结态入口分派参数：desktop.py 的 __main__ 检测到该参数时进入引擎工作端
# Frozen-mode dispatch flag handled by the desktop.py __main__ entry
FROZEN_WORKER_FLAG = "--engine-worker"


def build_engine_env() -> dict:
    """构建引擎子进程环境变量补丁：MODELSCOPE_CACHE 指向外置权重目录。
    Env patch for the engine subprocess: MODELSCOPE_CACHE → external weights dir.
    """
    from core.model_registry import get_model_dir
    model_dir = Path(get_model_dir()).resolve()
    return {"MODELSCOPE_CACHE": str(model_dir)}


def build_worker_command() -> list[str]:
    """引擎工作端启动命令 / Engine worker launch command.

    - 开发态：`python -m core.engine_worker`
    - 冻结态：`<exe> --engine-worker`（由 desktop.py 入口分派，配合 freeze_support）
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, FROZEN_WORKER_FLAG]
    return [sys.executable, "-m", "core.engine_worker"]


def build_worker_env() -> dict:
    """完整子进程环境（当前环境 + MODELSCOPE_CACHE + 开发态 PYTHONPATH）。"""
    env = dict(os.environ)
    env.update(build_engine_env())
    if not getattr(sys, "frozen", False):
        project_root = str(Path(__file__).resolve().parent.parent)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{project_root}{os.pathsep}{existing}" if existing else project_root
    return env


def check_required_models() -> dict:
    """启动前预检：必需模型必须完整（篡改拒载）。
    Pre-start check: required models must be present and untampered.

    返回 {"ready": bool, "missing": [...], "tampered": [...]}
    """
    from core.model_downloader import verify_model
    from core.model_registry import MODEL_BY_KEY

    missing, tampered = [], []
    for key, meta in MODEL_BY_KEY.items():
        if meta["optional"]:
            continue
        result = verify_model(key)
        if result["status"] == "tampered":
            tampered.append(key)
        elif result["status"] != "ready":
            missing.append(key)
    return {"ready": not missing and not tampered, "missing": missing, "tampered": tampered}


class EngineHost:
    """常驻引擎子进程管理器（进程内单例）/ Resident engine subprocess manager."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._req_counter = 0

    # ── 生命周期 / Lifecycle ──

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> dict:
        """启动常驻引擎子进程（含模型完整性预检）。已运行则幂等返回。"""
        with self._lock:
            if self.is_running():
                return {"ok": True, "already_running": True, "pid": self._proc.pid}

            precheck = check_required_models()
            if not precheck["ready"]:
                if precheck["tampered"]:
                    return {
                        "ok": False,
                        "error_code": "models_tampered",
                        "error": f"模型文件校验失败（疑似被篡改），拒绝启动引擎: {', '.join(precheck['tampered'])}。请删除后重新下载。",
                        "detail": precheck,
                    }
                return {
                    "ok": False,
                    "error_code": "models_missing",
                    "error": f"本地引擎模型未就绪: {', '.join(precheck['missing'])}。请先在设置中下载模型。",
                    "detail": precheck,
                }

            cmd = build_worker_command()
            env = build_worker_env()
            logger.info(f"[引擎] 启动常驻子进程: {' '.join(cmd)} (MODELSCOPE_CACHE={env.get('MODELSCOPE_CACHE')})")
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
                text=True,
                encoding="utf-8",
                cwd=str(Path(__file__).resolve().parent.parent),
            )

        # 健康检查 / Health check
        try:
            pong = self.request("ping", timeout=ENGINE_START_TIMEOUT)
        except Exception as e:
            self.stop()
            return {"ok": False, "error_code": "engine_unhealthy", "error": f"引擎子进程启动失败: {e}"}
        if not pong.get("ok"):
            self.stop()
            return {"ok": False, "error_code": "engine_unhealthy", "error": f"引擎健康检查失败: {pong}"}
        return {"ok": True, "already_running": False, "pid": self._proc.pid}

    def stop(self) -> dict:
        """停止常驻子进程（优雅 stop 命令，超时后 terminate）。"""
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return {"ok": True, "already_stopped": True}
        try:
            proc.stdin.write(json.dumps({"id": "stop", "cmd": "stop"}) + "\n")
            proc.stdin.flush()
            proc.wait(timeout=ENGINE_STOP_TIMEOUT)
        except Exception:
            proc.terminate()
            try:
                proc.wait(timeout=ENGINE_STOP_TIMEOUT)
            except Exception:
                proc.kill()
        logger.info("[引擎] 常驻子进程已停止")
        return {"ok": True, "already_stopped": False}

    # ── 请求转发 / Request forwarding ──

    def request(self, cmd: str, params: dict | None = None, timeout: float = ENGINE_REQUEST_TIMEOUT) -> dict:
        """向常驻子进程发送一条 JSON Lines 请求并等待响应（带超时）。"""
        with self._lock:
            if not self.is_running():
                raise RuntimeError("引擎子进程未运行")
            self._req_counter += 1
            req_id = f"r{self._req_counter}"
            payload = json.dumps({"id": req_id, "cmd": cmd, "params": params or {}}, ensure_ascii=False)
            self._proc.stdin.write(payload + "\n")
            self._proc.stdin.flush()

            # 阻塞 readline 放入线程以支持超时（超时视为引擎不健康，调用方应 stop/重启）
            # Blocking readline runs in a thread to honor timeout; timeout ⇒ unhealthy engine
            box: dict = {}

            def _read():
                box["line"] = self._proc.stdout.readline()

            reader = threading.Thread(target=_read, daemon=True)
            reader.start()
            reader.join(timeout)
            if reader.is_alive():
                raise TimeoutError(f"引擎响应超时（{timeout}s）: cmd={cmd}")
            line = box.get("line", "")
            if not line:
                raise RuntimeError("引擎子进程意外退出（stdout 关闭）")
            resp = json.loads(line)
            if resp.get("id") != req_id:
                raise RuntimeError(f"引擎响应 ID 不匹配: expected={req_id}, got={resp.get('id')}")
            return resp

    def status(self) -> dict:
        from app.settings_store import get_engine_config
        cfg = get_engine_config()
        precheck = check_required_models()
        return {
            "mode": cfg["mode"],
            "model_dir": str(Path(cfg["local"]["model_dir"]).expanduser()),
            "modelscope_cache": build_engine_env()["MODELSCOPE_CACHE"],
            "process_running": self.is_running(),
            "pid": self._proc.pid if self.is_running() else None,
            "models_ready": precheck["ready"],
            "missing_models": precheck["missing"],
            "tampered_models": precheck["tampered"],
        }


# 进程内单例 / Process-wide singleton
_engine_host: EngineHost | None = None
_engine_host_lock = threading.Lock()


def get_engine_host() -> EngineHost:
    global _engine_host
    if _engine_host is None:
        with _engine_host_lock:
            if _engine_host is None:
                _engine_host = EngineHost()
    return _engine_host
