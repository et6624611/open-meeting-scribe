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
import queue
import re
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

# 引擎子进程启动超时（开发态 python -m 冷启动秒级；冻结态首次 import 可达 86s+）
# Engine subprocess start timeout (frozen funasr cold import can take 86s+)
ENGINE_START_TIMEOUT = 120
ENGINE_REQUEST_TIMEOUT = 180
ENGINE_STOP_TIMEOUT = 10

# DEF-QA-R1-03（方案①引擎预热）：warmup 请求超时。留量声明：须覆盖
# 「冻结态冷 import ≈86s + 四模型加载 ≈16s×2 + 慢速机型/杀软余量」，取 300s。
# 预热仅在后台线程等待，不阻塞 start()/首请求；超时只记日志、不判进程不健康。
ENGINE_WARMUP_TIMEOUT = 300

# ── D-I1 两级健康语义（R9 分段增量，REQ-LOCAL-REALTIME-INCR §6）──
# 单请求超时 = 请求级失败（丢该请求，保留引擎进程）；连续 N 次超时才判
# 进程级不健康并重启子进程。进程死亡（stdout 关闭）仍即时判不健康。
# N 可经环境变量覆盖，默认 3（待真机校准）。
ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS = int(
    os.environ.get("ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS", "3")
)

# ── 本地批转写时长感知超时（WP-H 第 1 项：导入音频 / 非实时长文件路径）──
# Duration-aware timeout for local batch ASR on non-realtime long-file paths.
# 固定 ENGINE_REQUEST_TIMEOUT=180s 会把 >~37 分钟音频（Spike RTF≈0.081 反推）
# 整场判死；此处按音频时长重算单请求上限：
#   timeout = clamp(duration × RTF 预算 + 固定余量, 下限 180s, 上限按支持时长封顶)
# RTF 预算取 0.5 s/s ≈ Spike 实测 0.081 的 6 倍余量（覆盖慢速 4 核 Windows 机型、
# ct-punc 标点与排队开销；待真机实测后可再收紧）。
LOCAL_ASR_RTF_BUDGET = 0.5
LOCAL_ASR_TIMEOUT_MARGIN = 60
# 本地批转写支持的单文件时长上限（口径与 PRD 文案一致；超限报可分类错误，不发引擎请求）
LOCAL_ASR_MAX_SUPPORTED_SECONDS = 4 * 3600


def estimate_local_asr_timeout(duration_s: float | None) -> float:
    """按音频时长估算本地批转写单请求超时（WP-H：超时口径与实际支持时长一致）。

    Args:
        duration_s: 音频时长（秒）；None/非正值时退回默认 ENGINE_REQUEST_TIMEOUT。

    Returns:
        单请求超时（秒），区间 [ENGINE_REQUEST_TIMEOUT, LOCAL_ASR_MAX_SUPPORTED_SECONDS
        × RTF 预算 + 余量]。
    """
    if not duration_s or duration_s <= 0:
        return float(ENGINE_REQUEST_TIMEOUT)
    budget = duration_s * LOCAL_ASR_RTF_BUDGET + LOCAL_ASR_TIMEOUT_MARGIN
    ceiling = LOCAL_ASR_MAX_SUPPORTED_SECONDS * LOCAL_ASR_RTF_BUDGET + LOCAL_ASR_TIMEOUT_MARGIN
    return float(min(max(budget, ENGINE_REQUEST_TIMEOUT), ceiling))

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


def resolve_worker_python() -> str:
    """引擎工作端解释器 / Engine worker interpreter.

    开发态主 venv 通常不含 funasr/torch（重依赖只随冻结包分发，或装在独立的
    本地引擎 venv 中），若用主进程 `sys.executable` 拉起 worker，推理阶段
    `from funasr import AutoModel` 即抛 `ModuleNotFoundError: No module named 'funasr'`。
    通过环境变量 ENGINE_PYTHON 显式指向装有 funasr/torch 的解释器即可修复；
    相对路径锚定到项目根。未设置时退回 `sys.executable`（冻结包内 funasr 已随包分发）。
    """
    custom = os.environ.get("ENGINE_PYTHON", "").strip()
    if not custom:
        return sys.executable
    path = Path(custom).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return str(path)


def _uses_external_worker_python() -> bool:
    """worker 是否由独立解释器拉起（非当前进程）——决定是否需要注入 PYTHONPATH。"""
    return not getattr(sys, "frozen", False) and resolve_worker_python() != sys.executable


def build_worker_command() -> list[str] | None:
    """引擎工作端启动命令 / Engine worker launch command.

    - 开发态：``<worker_python> -m core.engine_worker``（worker_python 默认当前解释器，
      可经 ENGINE_PYTHON 指向含 funasr/torch 的本地引擎 venv；``--engine-worker``
      再入保留为降级路径）
    - 冻结态：**独立引擎包**（D-G1 方案 A / B-1 修复）——定位外置
      ``<引擎根>/OMSEngine(.exe)``；找不到返回 ``None``（调用方给可行动提示，
      绝不静默回退云端，也不再再入主 exe——主包 excludes torch/funasr，再入必然失败）。
    """
    if getattr(sys, "frozen", False):
        from core.engine_paths import locate_engine_executable
        exe = locate_engine_executable()
        return [str(exe)] if exe else None
    return [resolve_worker_python(), "-m", "core.engine_worker"]


def build_worker_env() -> dict:
    """完整子进程环境（当前环境 + MODELSCOPE_CACHE + 开发态 PYTHONPATH）。

    当 worker 由独立解释器（ENGINE_PYTHON）拉起时，也必须把项目根写入 PYTHONPATH，
    否则该解释器找不到 `core.engine_worker`；因此非冻结态或跨解释器时统一注入。
    """
    env = dict(os.environ)
    env.update(build_engine_env())
    if not getattr(sys, "frozen", False) or _uses_external_worker_python():
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


# ── 完整性校验缓存（仅服务观测面） / Integrity-check cache (observation surface only)──
# check_required_models() 会对全部必装权重逐文件做 SHA256 哈希（约 2 GB），单次
# 3s+。此前 /api/engine/status 每次实时校验，既拖慢该端点（日志成排的 [PERF] 慢请
# 求），也使前端无法高频刷新进程存活态。此处按「模型目录锚定 + TTL + 显式失效」缓存
# 结果；start() 的拒载门禁仍走实时校验（force=True），R5「篡改拒载」不被削弱。
# TTL 可经环境变量覆盖；下载完成/取消/失败、显式校验、变更存储目录时显式失效。
MODELS_CHECK_TTL_SECONDS = float(os.environ.get("ENGINE_MODELS_CHECK_TTL", "60"))

_models_check_cache: dict = {}  # {"dir", "result", "checked_at", "expires_at"}
_models_check_lock = threading.Lock()


def invalidate_models_check() -> None:
    """丢弃完整性校验缓存（模型文件已经或即将变化时调用）。"""
    with _models_check_lock:
        _models_check_cache.clear()


def check_required_models_cached(force: bool = False) -> dict:
    """带缓存的必装模型完整性校验，供观测面（status / 徽章）使用。

    返回结构同 check_required_models()，额外携带 cached / age_seconds。
    force=True 时跳过读取但仍回填缓存，用于门禁后的结果播种。
    """
    from core.model_registry import get_model_dir
    try:
        anchor = str(Path(get_model_dir()).expanduser().resolve())
    except OSError:
        anchor = str(Path(get_model_dir()).expanduser())
    now = time.time()

    if not force:
        with _models_check_lock:
            hit = _models_check_cache
            if hit.get("dir") == anchor and hit.get("expires_at", 0) > now:
                out = dict(hit["result"])
                out["cached"] = True
                out["age_seconds"] = round(now - hit["checked_at"], 1)
                return out

    result = check_required_models()
    checked_at = time.time()
    with _models_check_lock:
        _models_check_cache.clear()
        _models_check_cache.update({
            "dir": anchor,
            "result": dict(result),
            "checked_at": checked_at,
            "expires_at": checked_at + MODELS_CHECK_TTL_SECONDS,
        })
    result["cached"] = False
    result["age_seconds"] = 0.0
    return result


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
        # D-I1：常驻读取线程把 stdout 行推入响应队列；请求级超时只丢该请求，
        # 过期响应按 id 重同步丢弃；连续超时达阈值才重启子进程。
        self._resp_queue: queue.Queue | None = None
        self._stale_ids: set[str] = set()
        self._consecutive_timeouts = 0
        # DEF-QA-R1-03：预热状态（None=未开始 / running / done / failed），仅供观测
        self._warmup_state: str | None = None
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

            # 门禁走实时校验并回填观测缓存（force=True 播种，R5 篡改拒载不削弱）
            precheck = check_required_models_cached(force=True)
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
            # D-I1：为当前子进程建立响应队列 + 常驻读取线程（stdout 关闭时推 None 哨兵）
            self._resp_queue = queue.Queue()
            self._stale_ids = set()
            self._consecutive_timeouts = 0
            self._warmup_state = None
            resp_queue = self._resp_queue
            proc = self._proc

            def _reader_loop():
                try:
                    while True:
                        line = proc.stdout.readline()
                        if not line:
                            break
                        resp_queue.put(line)
                except Exception:
                    pass
                finally:
                    resp_queue.put(None)  # 哨兵：stdout 关闭 / 进程死亡

            threading.Thread(target=_reader_loop, daemon=True, name="engine-host-reader").start()
            # B-3：stderr 独立泵（逐行脱敏 + 环形缓冲 + 落盘）
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
        # DEF-QA-R1-03（方案①预热）：健康检查+协议握手通过后后台预热模型加载，把 ≈16s
        # （冻结态含冷 import 可达 ≈102s）的加载从首个推理请求中移出；
        # 预热失败/超时不影响启动——真实使用仍走请求级惰性加载与错误分类。
        self._kick_warmup()
        return {"ok": True, "already_running": False, "pid": self._proc.pid}

    def _kick_warmup(self) -> None:
        """后台线程发送 warmup 请求（DEF-QA-R1-03）。不阻塞 start()，异常仅记日志。"""
        self._warmup_state = "running"

        def _warm():
            try:
                resp = self.request("warmup", timeout=ENGINE_WARMUP_TIMEOUT)
                if resp.get("ok"):
                    self._warmup_state = "done"
                    logger.info(
                        f"[引擎] 预热完成 ({resp.get('seconds')}s): {resp.get('warmed')}"
                    )
                else:
                    self._warmup_state = "failed"
                    logger.warning(
                        f"[引擎] 预热失败（不阻塞按需加载）: {resp.get('error_code')} {resp.get('error')}"
                    )
            except Exception as e:
                self._warmup_state = "failed"
                logger.warning(f"[引擎] 预热异常（忽略，不影响主流程）: {e}")

        threading.Thread(target=_warm, daemon=True, name="engine-warmup").start()

    def stop(self) -> dict:
        """停止常驻子进程（优雅 stop 命令，超时后 terminate）。"""
        with self._lock:
            proc, self._proc = self._proc, None
            self._resp_queue = None
            self._stale_ids = set()
            self._consecutive_timeouts = 0
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
        """向常驻子进程发送一条 JSON Lines 请求并等待响应（带超时）。

        D-I1 两级健康语义：
          - 单请求超时 → 请求级失败（TimeoutError），进程保留；本次 req_id 记入
            过期集合，迟到的响应在后续请求读取时按 id 重同步丢弃；
          - 连续 ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS 次超时 → 进程级不健康，
            stop() 重启（下次 infer 自动拉起）；
          - stdout 关闭（None 哨兵 = 进程死亡/OOM）→ 仍即时 RuntimeError。
        """
        try:
            with self._lock:
                if not self.is_running():
                    raise RuntimeError("引擎子进程未运行")
                resp_queue = self._resp_queue
                if resp_queue is None:
                    raise RuntimeError("引擎响应队列未初始化")
                self._req_counter += 1
                req_id = f"r{self._req_counter}"
                payload = json.dumps({"id": req_id, "cmd": cmd, "params": params or {}}, ensure_ascii=False)
                self._proc.stdin.write(payload + "\n")
                self._proc.stdin.flush()

                deadline = time.monotonic() + timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"引擎响应超时（{timeout}s）: cmd={cmd}")
                    try:
                        item = resp_queue.get(timeout=remaining)
                    except queue.Empty:
                        raise TimeoutError(f"引擎响应超时（{timeout}s）: cmd={cmd}")
                    if item is None:
                        # 哨兵：stdout 关闭 → 进程死亡（OOM 等），即时判不健康
                        raise RuntimeError("引擎子进程意外退出（stdout 关闭）")
                    try:
                        resp = json.loads(item)
                    except json.JSONDecodeError:
                        # 协议重同步：丢弃非 JSON 行（第三方库偶发 print 污染 stdout），
                        # 继续等待本请求的合法应答行；worker 侧已用 _quiet_stdout 屏蔽主源。
                        logger.warning(f"[引擎] 丢弃非 JSON 输出行: {item[:120]!r}")
                        continue
                    rid = resp.get("id")
                    if rid == req_id:
                        self._consecutive_timeouts = 0
                        return resp
                    if rid in self._stale_ids:
                        # 过期响应（此前超时请求的迟到回包）：重同步丢弃，继续等本请求
                        logger.debug(f"[引擎] 丢弃过期响应: id={rid}（等待 {req_id}）")
                        continue
                    raise RuntimeError(f"引擎响应 ID 不匹配: expected={req_id}, got={rid}")
        except TimeoutError:
            with self._lock:
                self._stale_ids.add(req_id)
                self._consecutive_timeouts += 1
                hits = self._consecutive_timeouts
                restart = hits >= ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS
                if restart:
                    self._consecutive_timeouts = 0
                    self._stale_ids = set()
            if restart:
                logger.warning(
                    f"[引擎] 连续 {hits} 次请求超时，判进程级不健康，重启子进程（D-I1）"
                )
                self.stop()
            else:
                logger.warning(
                    f"[引擎] 请求超时（连续 {hits}/{ENGINE_UNHEALTHY_CONSECUTIVE_TIMEOUTS}），"
                    f"保留进程: cmd={cmd}"
                )
            raise
        except RuntimeError:
            with self._lock:
                self._consecutive_timeouts = 0
                self._stale_ids = set()
            raise

    def status(self) -> dict:
        from app.settings_store import get_engine_config
        cfg = get_engine_config()
        # 观测面走缓存校验（~毫秒级），使前端可对进程存活态做常规刷新；
        # 门禁侧（start）仍为实时校验，见 check_required_models_cached 注释。
        precheck = check_required_models_cached()
        running = self.is_running()
        return {
            "mode": cfg["mode"],
            "model_dir": str(Path(cfg["local"]["model_dir"]).expanduser()),
            "modelscope_cache": build_engine_env()["MODELSCOPE_CACHE"],
            "process_running": running,
            "pid": self._proc.pid if running else None,
            "models_ready": precheck["ready"],
            "missing_models": precheck["missing"],
            "tampered_models": precheck["tampered"],
            # 完整性校验结果是否为缓存命中 + 距上次实检的秒数（诊断用）
            "models_check_cached": bool(precheck.get("cached")),
            "models_check_age_seconds": precheck.get("age_seconds", 0.0),
            "warmup_state": self._warmup_state,  # DEF-QA-R1-03：None/running/done/failed
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
            # D-I1 两级语义：单请求超时不立即杀进程（request() 内部按连续超时
            # 阈值决定是否重启）；调用方只承担本次请求失败。
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
