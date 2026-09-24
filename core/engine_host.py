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
import re
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

# 引擎子进程启动超时（开发态 python -m 冷启动秒级；冻结态首次 import 可达 86s+）
# Engine subprocess start timeout (frozen funasr cold import can take 86s+)
ENGINE_START_TIMEOUT = 120
ENGINE_REQUEST_TIMEOUT = 180
ENGINE_STOP_TIMEOUT = 10

# 冻结态入口分派参数：desktop.py 的 __main__ 检测到该参数时进入引擎工作端。
# D-G1 子项②：保留为开发态/降级路径；冻结态正式路径走独立引擎包（B-1 修复）。
FROZEN_WORKER_FLAG = "--engine-worker"

# B-3：引擎子进程 stderr 收集——环形缓冲行数与启动失败时回带的尾部摘要上限
STDERR_TAIL_LINES = 200
STDERR_SUMMARY_CHARS = 2000
ENGINE_STDERR_LOG_NAME = "engine-stderr.log"

# B-3 最小脱敏：掩去凭据样式（sk-xxx / Bearer xxx / token=xxx / key=xxx）
# 顺序敏感：Bearer 规则须先于 authorization 通配规则，否则后者只掩到 "Bearer" 一词
_REDACT_RES = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]+"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.=]+", re.IGNORECASE),
    re.compile(r"((?:token|key|secret|password|authorization)\s*[=:]\s*)\S+", re.IGNORECASE),
]


def redact_stderr_line(line: str) -> str:
    """对引擎 stderr 行做最小脱敏（对齐 AC-8 / core.joblog 的脱敏精神）。"""
    for pattern in _REDACT_RES:
        line = pattern.sub(r"\1***", line)
    return line


def build_engine_env() -> dict:
    """构建引擎子进程环境变量补丁：MODELSCOPE_CACHE 指向外置权重目录。
    Env patch for the engine subprocess: MODELSCOPE_CACHE → external weights dir.
    """
    from core.model_registry import get_model_dir
    model_dir = Path(get_model_dir()).resolve()
    return {"MODELSCOPE_CACHE": str(model_dir)}


def build_worker_command() -> list[str] | None:
    """引擎工作端启动命令 / Engine worker launch command.

    - 开发态：``python -m core.engine_worker``（``--engine-worker`` 再入保留为降级路径）
    - 冻结态：**独立引擎包**（D-G1 方案 A / B-1 修复）——定位外置
      ``<引擎根>/OMSEngine(.exe)``；找不到返回 ``None``（调用方给可行动提示，
      绝不静默回退云端，也不再再入主 exe——主包 excludes torch/funasr，再入必然失败）。
    """
    if getattr(sys, "frozen", False):
        from core.engine_paths import locate_engine_executable
        exe = locate_engine_executable()
        return [str(exe)] if exe else None
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


def get_component_status() -> dict:
    """引擎组件（独立引擎包，D-G1）三态判定——G-5 首启引导数据源。

    state:
      - "not_installed"      未找到引擎可执行体（三态①：引导安装组件）
      - "broken"             找到可执行体但 manifest 缺失/损坏（引导重装）
      - "protocol_mismatch"  manifest 协议版本与主包不一致（三态③：引导升级组件，
                             拒绝启动、不得静默回退云端，D-G1 子项③）
      - "ready"              组件就绪（权重是否下载另由 models_ready 表达，三态②）

    开发态（非 frozen）无独立引擎包属正常：返回 {"state": "dev_mode"}，
    引擎走 venv `python -m core.engine_worker`。
    """
    from core.engine_paths import (
        get_engine_dir_candidates,
        locate_engine_executable,
        locate_engine_manifest,
    )
    from core.engine_worker import PROTOCOL_VERSION

    if not getattr(sys, "frozen", False):
        return {"state": "dev_mode", "protocol_version": PROTOCOL_VERSION}

    exe = locate_engine_executable()
    if exe is None:
        return {
            "state": "not_installed",
            "protocol_version": PROTOCOL_VERSION,
            "searched": [str(p) for p in get_engine_dir_candidates()],
        }

    manifest = locate_engine_manifest()
    if not manifest:
        return {
            "state": "broken",
            "engine_path": str(exe),
            "protocol_version": PROTOCOL_VERSION,
            "reason": "engine-manifest.json 缺失或损坏",
        }

    engine_protocol = manifest.get("protocol_version")
    if engine_protocol != PROTOCOL_VERSION:
        return {
            "state": "protocol_mismatch",
            "engine_path": str(exe),
            "engine_version": manifest.get("engine_version"),
            "engine_protocol_version": engine_protocol,
            "protocol_version": PROTOCOL_VERSION,
        }

    return {
        "state": "ready",
        "engine_path": str(exe),
        "engine_version": manifest.get("engine_version"),
        "engine_protocol_version": engine_protocol,
        "protocol_version": PROTOCOL_VERSION,
    }


class EngineHost:
    """常驻引擎子进程管理器（进程内单例）/ Resident engine subprocess manager."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._req_counter = 0
        # B-3：引擎子进程 stderr 环形缓冲（最近 N 行，脱敏后），启动失败时回带摘要
        self._stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._stderr_thread: threading.Thread | None = None
        self._stderr_log_file = None

    # ── 生命周期 / Lifecycle ──

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def get_stderr_summary(self, max_chars: int = STDERR_SUMMARY_CHARS) -> str:
        """B-3：引擎子进程 stderr 尾部摘要（脱敏后），用于失败诊断与任务日志。"""
        text = "\n".join(self._stderr_tail).strip()
        if len(text) > max_chars:
            text = "…" + text[-max_chars:]
        return text

    def _pump_stderr(self, proc: subprocess.Popen, log_path: Path | None) -> None:
        """B-3：stderr 读取线程——逐行脱敏后进 logger / 环形缓冲 / 落盘日志。"""
        log_file = None
        try:
            if log_path is not None:
                try:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    log_file = log_path.open("a", encoding="utf-8")
                except Exception as e:
                    logger.warning(f"[引擎] stderr 日志文件打开失败（不影响主链路）: {e}")
            for raw in proc.stderr:
                line = redact_stderr_line(raw.rstrip("\n"))
                self._stderr_tail.append(line)
                logger.warning(f"[引擎:stderr] {line}")
                if log_file is not None:
                    try:
                        log_file.write(line + "\n")
                        log_file.flush()
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            if log_file is not None:
                try:
                    log_file.close()
                except Exception:
                    pass

    def start(self) -> dict:
        """启动常驻引擎子进程（组件三态判定 + 模型完整性预检 + 协议版本握手）。

        已运行则幂等返回。冻结态走独立引擎包（D-G1 方案 A）；组件缺失/损坏/
        协议不匹配一律拒绝启动并返回可行动的分级指引（D-G5），不静默回退云端。
        """
        with self._lock:
            if self.is_running():
                return {"ok": True, "already_running": True, "pid": self._proc.pid}

            # 组件三态判定（G-5 数据源同函数，冻结态生效）
            component = get_component_status()
            if component["state"] == "not_installed":
                return {
                    "ok": False,
                    "error_code": "engine_component_missing",
                    "error": "本地引擎组件未安装。请在「设置 → 本地引擎」点击『安装本地引擎』；"
                             "内网环境请联系管理员导入离线引擎包。",
                    "detail": component,
                }
            if component["state"] == "broken":
                return {
                    "ok": False,
                    "error_code": "engine_component_broken",
                    "error": "本地引擎组件损坏（engine-manifest.json 缺失或不可读）。"
                             "请在「设置 → 本地引擎」重新安装引擎组件。",
                    "detail": component,
                }
            if component["state"] == "protocol_mismatch":
                # D-G1 子项③：协议版本不匹配 → 拒绝启动，不得静默回退云端
                return {
                    "ok": False,
                    "error_code": "engine_protocol_mismatch",
                    "error": f"本地引擎组件与主程序版本不匹配（组件协议 v{component.get('engine_protocol_version')}，"
                             f"主程序要求 v{component.get('protocol_version')}）。请升级本地引擎组件后重试。",
                    "detail": component,
                }

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
            if cmd is None:
                # 理论不可达（component ready 时必能定位），防御性兜底
                return {
                    "ok": False,
                    "error_code": "engine_component_missing",
                    "error": "本地引擎组件未找到，请在「设置 → 本地引擎」重新安装。",
                    "detail": component,
                }
            env = build_worker_env()

            # B-2 修复：cwd 不再用 __file__ 推导（冻结态是只读 _MEIPASS bundle）——
            # 冻结态用引擎根目录，开发态保持项目根。
            if getattr(sys, "frozen", False):
                cwd = str(Path(cmd[0]).resolve().parent)
            else:
                cwd = str(Path(__file__).resolve().parent.parent)

            # B-3：stderr 落盘位置 = 运行时锚点 logs/（D-G3；开发态 data/logs/）
            from core.engine_paths import get_logs_dir
            stderr_log_path = get_logs_dir() / ENGINE_STDERR_LOG_NAME

            self._stderr_tail.clear()
            logger.info(f"[引擎] 启动常驻子进程: {' '.join(cmd)} (cwd={cwd}, MODELSCOPE_CACHE={env.get('MODELSCOPE_CACHE')}, stderr_log={stderr_log_path})")

            popen_kwargs: dict = {}
            if sys.platform == "win32":
                # GUI 主程序（console=False）拉起控制台子进程会闪窗，显式抑制
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                **popen_kwargs,
            )
            self._stderr_thread = threading.Thread(
                target=self._pump_stderr,
                args=(self._proc, stderr_log_path),
                daemon=True,
                name="engine-stderr-pump",
            )
            self._stderr_thread.start()

        # 健康检查 + 协议版本握手（D-G1 子项①：ping 响应携带 protocol 字段）
        from core.engine_worker import PROTOCOL_VERSION
        try:
            pong = self.request("ping", timeout=ENGINE_START_TIMEOUT)
        except Exception as e:
            self.stop()
            return {
                "ok": False,
                "error_code": "engine_unhealthy",
                # D-G5：给可行动提示（首启耗时预期 + 日志位置 + 重试），不直丢原始异常
                "error": f"本地引擎启动失败或超时（首次启动约需 1–2 分钟）。请重试；若持续失败，"
                         f"查看日志 {stderr_log_path} 并联系支持。原始错误: {e}",
                "detail": {"stderr_tail": self.get_stderr_summary(), "stderr_log": str(stderr_log_path)},
            }
        if not pong.get("ok"):
            self.stop()
            return {
                "ok": False,
                "error_code": "engine_unhealthy",
                "error": "本地引擎健康检查失败，请重试或重新安装引擎组件。",
                "detail": {"pong": pong, "stderr_tail": self.get_stderr_summary(), "stderr_log": str(stderr_log_path)},
            }
        engine_protocol = pong.get("protocol")
        if engine_protocol != PROTOCOL_VERSION:
            self.stop()
            return {
                "ok": False,
                "error_code": "engine_protocol_mismatch",
                "error": f"本地引擎组件与主程序协议版本不匹配（组件 v{engine_protocol}，主程序要求 v{PROTOCOL_VERSION}）。"
                         "请升级本地引擎组件后重试。",
                "detail": {"engine_protocol_version": engine_protocol, "protocol_version": PROTOCOL_VERSION,
                           "stderr_tail": self.get_stderr_summary()},
            }
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
            # G-5 三态：组件级状态（not_installed / broken / protocol_mismatch / ready / dev_mode）
            "component": get_component_status(),
        }

    # ── 本地推理（R1/R3 统一入口） / Local inference (unified entry for R1/R3) ──

    def infer(self, task: str, params: dict | None = None, timeout: float = ENGINE_REQUEST_TIMEOUT) -> dict:
        """确保常驻子进程运行并转发一次推理请求，失败统一归为 LocalEngineError。

        Ensure the resident subprocess is up, forward one inference request, and
        normalize any failure into a classified LocalEngineError (carries
        can_fallback_cloud so callers can offer an explicit cloud retry — AC-4).

        Args:
            task: "asr" | "embedding"
            params: 透传给 worker 的推理参数（如 audio_path）
            timeout: 单请求超时（秒）

        Returns:
            worker 成功响应 dict（含 task 特定字段）

        Raises:
            LocalEngineError: 模型未就绪/子进程不健康/超时/推理失败
        """
        from core.errors import LocalEngineError

        can_fallback = _cloud_fallback_available()

        # 自动拉起常驻子进程（幂等）；启动失败按错误码分类
        if not self.is_running():
            start = self.start()
            if not start.get("ok"):
                code = start.get("error_code", "engine_unhealthy")
                # D-G1 子项③：协议版本不匹配 → 拒绝启动，不提供云端回退选项
                #（必须修复组件本身；其余错误码保留 AC-4 显式云端重试语义）
                fallback = can_fallback and code != "engine_protocol_mismatch"
                raise LocalEngineError(
                    start.get("error", "本地引擎启动失败"),
                    error_code=code,
                    can_fallback_cloud=fallback,
                    detail=start.get("detail", {}),
                )

        try:
            resp = self.request("infer", {"task": task, **(params or {})}, timeout=timeout)
        except TimeoutError as e:
            # 超时视为子进程不健康：停掉以便下次请求重新拉起（PRD 7.3 错误分类）
            self.stop()
            raise LocalEngineError(str(e), error_code="engine_timeout", can_fallback_cloud=can_fallback)
        except RuntimeError as e:
            raise LocalEngineError(str(e), error_code="engine_unhealthy", can_fallback_cloud=can_fallback)

        if not resp.get("ok"):
            raise LocalEngineError(
                resp.get("error", "本地推理失败"),
                error_code=resp.get("error_code", "inference_failed"),
                can_fallback_cloud=can_fallback,
                detail={k: v for k, v in resp.items() if k not in ("id", "protocol")},
            )
        return resp


def _cloud_fallback_available() -> bool:
    """AC-4：本地失败时是否具备回退云端的条件（云端已启用）。"""
    try:
        from core.cloud_client import is_cloud_enabled
        return bool(is_cloud_enabled())
    except Exception:
        return False


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
