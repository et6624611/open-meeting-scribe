#!/usr/bin/env python3
"""
desktop.py — Open Meeting Scribe 启动器（浏览器模式）/ Desktop launcher (browser mode)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-13
版本 / Version: 1.1.0

说明 / Description:
    本文件不再创建原生窗口。启动流程：
      1. 扫描端口，若发现本应用已在运行，直接打开浏览器指向它（单实例）；
      2. 否则选一个可用端口启动 FastAPI 服务；
      3. 服务就绪后用系统默认浏览器打开 http://127.0.0.1:<port>；
      4. 用户在页面内点「退出应用」后，停服务、停本地引擎、进程退出。

    No native window any more. The launcher reuses a running instance if found,
    otherwise starts FastAPI, opens the system default browser, and exits on
    POST /api/app/quit.

用法 / Usage:
    # 开发时直接运行 / Run directly during development
    python desktop.py

    # 或通过 CLI 子命令 / Or via CLI subcommand
    python cli.py app

    # PyInstaller 打包后双击即可运行 / Double-click to run after PyInstaller packaging
    OpenMeetingScribe.exe
"""

import logging
import os
import sys
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uvicorn

# ─── PyInstaller no-console 模式兼容 / PyInstaller no-console mode compatibility ───
# console=False 打包时 sys.stderr/stdout 为 None，
# uvicorn 日志配置会调用 sys.stderr.isatty() 导致 AttributeError。
# 在导入任何项目模块之前，确保标准流不为 None。
# When packaged with console=False, sys.stderr/stdout are None,
# uvicorn logging config calls sys.stderr.isatty() causing AttributeError.
# Ensure std streams are not None before importing any project module.
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")


def _setup_desktop_env():
    """PyInstaller frozen 环境下的配置自动初始化。

    桌面客户端（exe）首次启动时自动完成：
      1. 从 .env.example 模板创建 .env（若不存在）
      2. 注入桌面端默认值：ASR_MODE=cloud + 云端服务地址
      3. 从 exe 同级目录显式加载 .env（CWD 可能不是 exe 目录）
      4. 注入 SMS / Cloud 代理默认地址（桌面端连接云端服务）

    非 frozen 模式（开发环境）不做任何处理，直接返回。
    """
    if not getattr(sys, "frozen", False):
        return

    import shutil
    from pathlib import Path

    exe_dir = Path(sys.executable).parent
    env_file = exe_dir / ".env"
    env_example = exe_dir / ".env.example"

    # 1. 从模板创建 .env（首次启动）
    if not env_file.exists() and env_example.exists():
        shutil.copy2(str(env_example), str(env_file))
        # 桌面客户端默认使用云端代理模式（用户零配置）
        # Desktop client defaults to cloud proxy mode (zero config for users)
        with open(env_file, "a", encoding="utf-8") as f:
            f.write("\n# ── 桌面客户端自动配置（首次启动生成）──\n")
            f.write("# 云端代理模式：ASR/LLM 通过云端服务器中转，用户无需配置 API Key\n")
            f.write("ASR_MODE=cloud\n")

    # 2. 从 exe 同级目录显式加载 .env
    from dotenv import load_dotenv
    load_dotenv(str(env_file))

    # 3. 桌面端默认值注入
    # .env.example 模板中的占位符（如 http://your-server:8000）是非空字符串，
    # 简单的 if not os.getenv() 无法检测到。需要识别并替换占位符值。
    def _is_placeholder(value: str) -> bool:
        """检测环境变量是否为模板占位符値。"""
        if not value:
            return True
        v = value.lower()
        return (
            "your-" in v
            or "xxxx" in v
            or "sk-xxx" in v
            or value == "http://your-server:8000"
        )

    # 桌面端云端服务默认値：从 PyInstaller 内嵌的 desktop-secrets.env 读取。
    # Desktop cloud service defaults: read from PyInstaller-embedded desktop-secrets.env.
    #
    # 打包时 CI 将 GitHub Secrets 写入此文件；若文件不存在（未配置 secrets），
    # 云端功能不可用，本地模式（直连 DashScope API Key）仍正常工作。
    # CI writes GitHub Secrets to this file at build time; if absent, cloud features
    # are disabled and local mode (direct DashScope API Key) continues to work.
    _secrets_file = Path(getattr(sys, "_MEIPASS", "")) / "desktop-secrets.env"
    if _secrets_file.is_file():
        from dotenv import dotenv_values
        _desktop_secrets = dotenv_values(str(_secrets_file))
        for _key, _val in _desktop_secrets.items():
            if _val and _is_placeholder(os.getenv(_key, "")):
                os.environ[_key] = _val


# 必须在 load_dotenv / 导入项目模块之前执行 / Must run before load_dotenv / importing project modules
_setup_desktop_env()

# 加载环境变量（非 frozen 模式下从 CWD 加载） / Load env vars (non-frozen: load from CWD)
from dotenv import load_dotenv

load_dotenv()

# 配置日志 / Configure logging
# console=False 下 stderr 指向 devnull，另写 logs/desktop.log 便于用户侧排障。
# With console=False stderr goes to devnull; also write logs/desktop.log for diagnosis.
_log_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
if getattr(sys, "frozen", False):
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    _log_dir = Path(sys.executable).parent / "logs"
    _log_dir.mkdir(exist_ok=True)
    _log_handlers.append(
        RotatingFileHandler(
            _log_dir / "desktop.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=_log_handlers,
    force=True,
)
logger = logging.getLogger(__name__)

# 默认服务配置 / Default server config
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
# 端口顺延上限 / Port scan limit: 8000-8019
PORT_SCAN_LIMIT = 20
# 退出请求到达后，留出响应回传时间再停服务 / Grace period before shutdown
QUIT_GRACE_SECONDS = 0.3


def _probe_running_instance(host: str, port: int, timeout: float = 0.6) -> bool:
    """探测该端口上是否为本应用实例。 / Check whether the port serves this app.

    通过 /api/health 的 app 标识判定，避免把同端口的其他服务误认为已启动实例。
    """
    import httpx

    from core.app_control import APP_ID

    try:
        resp = httpx.get(f"http://{host}:{port}/api/health", timeout=timeout)
        if resp.status_code >= 500:
            return False
        data = resp.json()
    except Exception:
        return False
    return isinstance(data, dict) and data.get("app") == APP_ID


def _port_bindable(host: str, port: int) -> bool:
    """端口是否可绑定（本机回环）。 / Whether the loopback port can be bound."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Windows 的 SO_REUSEADDR 允许抢占已监听端口，必须用 SO_EXCLUSIVEADDRUSE
    # 才能真实检测占用；POSIX 反之，SO_REUSEADDR 不抢占活动监听。
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _find_existing_instance(host: str, base_port: int) -> int | None:
    """扫描端口，返回已运行本应用的端口（单实例复用）。 / Port of a running instance, if any."""
    for port in range(base_port, base_port + PORT_SCAN_LIMIT):
        if _probe_running_instance(host, port):
            return port
    return None


def _pick_port(host: str, start_port: int) -> int | None:
    """从 start_port 起找第一个可绑定端口。 / First bindable port from start_port."""
    for port in range(start_port, start_port + PORT_SCAN_LIMIT):
        if _port_bindable(host, port):
            return port
    return None


def _wait_for_server(server: "uvicorn.Server", thread: threading.Thread, timeout: float = 15.0) -> bool:
    """等待 uvicorn 完成启动；线程异常退出即判失败。 / Wait until uvicorn starts."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if server.started:
            return True
        if not thread.is_alive():
            return False
        time.sleep(0.1)

    return False


def _start_server(host: str, port: int) -> tuple["uvicorn.Server", threading.Thread]:
    """在后台线程启动 FastAPI 服务。 / Start FastAPI server in background thread."""
    import uvicorn

    config = uvicorn.Config(
        "app.server:app",
        host=host,
        port=port,
        log_level="warning",
        # 禁用访问日志，减少控制台噪音 / Disable access log to reduce console noise
        access_log=False,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name="fastapi-server")
    thread.start()

    return server, thread


def _open_browser(url: str) -> bool:
    """用系统默认浏览器打开地址。 / Open the URL in the system default browser."""
    import webbrowser

    try:
        if webbrowser.open(url, new=2):
            logger.info(f"已在默认浏览器打开: {url}")
            return True
    except Exception as e:
        logger.warning(f"自动打开浏览器失败: {e}")
    logger.warning(f"未能自动打开浏览器，请手动访问: {url}")
    return False


def _shutdown_server(server: "uvicorn.Server") -> None:
    """停止服务并回收本地引擎子进程。 / Stop server and resident engine subprocess."""
    server.should_exit = True

    try:
        from core.engine_host import get_engine_host
        engine = get_engine_host()
        if engine.is_running():
            engine.stop()
    except Exception:
        pass

    # 给服务一点时间完成清理 / Give server time to clean up
    time.sleep(0.5)


def main(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    """启动器主入口。 / Launcher main entry.

    Args:
        host: 服务监听地址 / Server listen address
        port: 首选端口（被占用时顺延） / Preferred port (falls through when taken)

    Returns:
        退出码（0 表示正常退出） / Exit code (0 = normal exit)
    """
    from core import app_control

    # ── 单实例：已有本应用在跑，直接把浏览器指过去 ──
    # Single instance: reuse the running app and just open the browser.
    existing_port = _find_existing_instance(host, port)
    if existing_port is not None:
        url = f"http://{host}:{existing_port}"
        logger.info(f"检测到本应用已在运行: {url}")
        _open_browser(url)
        return 0

    app_control.enable_desktop_mode()

    # ── 启动服务：端口被其他程序占用时顺延；绑定竞争失败时再试下一个 ──
    # Start server: fall through on occupied ports, retry on bind races.
    server = None
    target_port = port
    search_from = port
    for _ in range(3):
        candidate = _pick_port(host, search_from)
        if candidate is None:
            logger.error(
                f"端口 {port}-{port + PORT_SCAN_LIMIT - 1} 全部被占用，无法启动服务"
            )
            return 1
        srv, thread = _start_server(host, candidate)
        if _wait_for_server(srv, thread):
            server, target_port = srv, candidate
            break
        srv.should_exit = True
        search_from = candidate + 1

    if server is None:
        logger.error("服务启动失败，请查看 logs/server.log")
        return 1

    url = f"http://{host}:{target_port}"
    logger.info(f"服务已就绪: {url}")
    _open_browser(url)
    logger.info("服务运行中；在页面「设置 → 系统 → 退出应用」可停止服务")

    # ── 等待页面内退出请求（Ctrl+C 亦可） ──
    # Wait for the in-page quit request (Ctrl+C also works).
    try:
        while not app_control.wait_quit(0.5):
            pass
        logger.info("收到退出请求")
    except KeyboardInterrupt:
        logger.info("收到中断信号")

    time.sleep(QUIT_GRACE_SECONDS)
    _shutdown_server(server)
    logger.info("应用已退出")
    return 0


if __name__ == "__main__":
    # Spike §3.2 / PRD R5 实施约束②：冻结包多进程必须显式 freeze_support，
    # 且引擎子进程入口分派必须在 __main__ 保护内，防止冻结包被重复引导
    import multiprocessing
    multiprocessing.freeze_support()

    # 引擎常驻子进程分派（冻结态由 core.engine_host 以 `<exe> --engine-worker` 拉起）
    if "--engine-worker" in sys.argv:
        from core.engine_worker import main as engine_worker_main
        sys.exit(engine_worker_main())

    # 支持通过命令行参数覆盖默认配置 / Support overriding default config via CLI args
    import argparse

    parser = argparse.ArgumentParser(description="Open Meeting Scribe 启动器")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"服务地址（默认 {DEFAULT_HOST}）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"服务端口（默认 {DEFAULT_PORT}）")
    args = parser.parse_args()

    sys.exit(main(host=args.host, port=args.port))
