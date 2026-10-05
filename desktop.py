#!/usr/bin/env python3
"""
desktop.py — Open Meeting Scribe 桌面应用入口 / Open Meeting Scribe desktop app entry

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-13
版本 / Version: 1.0.0

说明 / Description:
    在单进程中同时启动 FastAPI 后台服务与 pywebview 原生窗口，
    为用户提供独立桌面应用体验（无浏览器地址栏干扰）。
    Launch FastAPI background server and pywebview native window in a single process,
    providing a standalone desktop app experience (no browser address bar).

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

    from pathlib import Path
    import shutil

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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 默认服务配置 / Default server config
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# 窗口配置 / Window config
WINDOW_TITLE = "Open Meeting Scribe"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
MIN_WIDTH = 960
MIN_HEIGHT = 600


def _wait_for_server(host: str, port: int, timeout: float = 10.0) -> bool:
    """等待 FastAPI 服务就绪。 / Wait for FastAPI server to be ready.

    通过轮询 HTTP 健康检查端点判断服务是否启动完成。 / Poll HTTP health endpoint to determine if server has started.

    Args:
        host: 服务地址 / Server address
        port: 服务端口 / Server port
        timeout: 最大等待时间（秒） / Max wait time (seconds)

    Returns:
        True 表示服务已就绪，False 表示超时 / True if server is ready, False if timed out
    """
    import httpx

    url = f"http://{host}:{port}/api/health"
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.2)

    return False


def _start_server(host: str, port: int) -> "uvicorn.Server":
    """在后台线程启动 FastAPI 服务。 / Start FastAPI server in background thread.

    Args:
        host: 监听地址 / Listen address
        port: 监听端口 / Listen port

    Returns:
        uvicorn.Server 实例（可用于后续停止服务） / uvicorn.Server instance (can be used to stop server later)
    """
    import uvicorn

    config = uvicorn.Config(
        "app.server:app",
        host=host,
        port=port,
        log_level="warning",
        # 禁用访问日志，减少桌面模式下的控制台噪音 / Disable access log, reduce console noise in desktop mode
        access_log=False,
    )
    server = uvicorn.Server(config)

    # 在后台守护线程中运行服务 / Run server in background daemon thread
    thread = threading.Thread(target=server.run, daemon=True, name="fastapi-server")
    thread.start()

    return server


def _create_and_run_window(url: str) -> None:
    """创建 pywebview 原生窗口并进入事件循环。 / Create pywebview native window and enter event loop.

    Args:
        url: 要加载的页面地址 / Page URL to load
    """
    import webview

    logger.info(f"创建桌面窗口: {WINDOW_TITLE}")

    window = webview.create_window(
        title=WINDOW_TITLE,
        url=url,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        resizable=True,
        text_select=True,
    )

    # ─── 桌面端原生对话框 / Native folder dialog for desktop ───
    # 通过 pywebview expose 机制将 Python 函数暴露给前端 JS，
    # 前端调用 window.pywebview.api.select_native_folder() 即可弹出 OS 原生文件夹选择器。
    # macOS → NSOpenPanel（Finder 风格），Windows → IFileOpenDialog（资源管理器风格）。
    # Expose Python function to frontend JS via pywebview bridge,
    # frontend calls window.pywebview.api.select_native_folder() to open OS native folder picker.
    # macOS → NSOpenPanel (Finder-style), Windows → IFileOpenDialog (Explorer-style).
    def select_native_folder() -> str:
        """弹出操作系统原生文件夹选择对话框，返回选中路径（空串表示取消）。
        Pop up OS native folder picker, return selected path (empty string if cancelled).
        """
        from pathlib import Path
        try:
            result = window.create_file_dialog(
                dialog_type=webview.FOLDER_DIALOG,
                directory=str(Path.home()),
                allow_multiple=False,
            )
            if result and len(result) > 0:
                logger.info(f"原生文件夹选择器返回: {result[0]}")
                return result[0]
        except Exception as e:
            logger.warning(f"原生文件夹选择器调用失败: {e}")
        return ""

    window.expose(select_native_folder)

    # ─── 桌面端刷新快捷键注入 / Desktop refresh hotkey injection ───
    # 页面加载完成后注入 JS，监听 F5 键并派发自定义事件，
    # 由 Vue 应用层判断录音状态后决定是否执行刷新。
    # Inject JS after page load to listen for F5 key and dispatch custom event,
    # Vue app layer decides whether to refresh based on recording state.
    def _on_loaded():
        window.evaluate_js("""
            document.addEventListener('keydown', function(e) {
                if (e.key === 'F5') {
                    e.preventDefault();
                    window.dispatchEvent(new CustomEvent('oms:reload-requested'));
                }
            });
        """)
        logger.info("桌面端刷新快捷键已注入 (F5)")
        logger.info("原生文件夹选择器已暴露给前端 (select_native_folder)")

    window.events.loaded += _on_loaded

    # 进入事件循环（阻塞直到所有窗口关闭） / Enter event loop (blocks until all windows closed)
    webview.start()


def main(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    """桌面应用主入口。 / Desktop app main entry.

    启动流程 / Startup flow:
        1. 后台线程启动 FastAPI 服务 / Start FastAPI server in background thread
        2. 等待服务就绪 / Wait for server to be ready
        3. 创建 pywebview 原生窗口 / Create pywebview native window
        4. 窗口关闭后优雅停止服务 / Gracefully stop server after window closes

    Args:
        host: 服务监听地址 / Server listen address
        port: 服务监听端口 / Server listen port

    Returns:
        退出码（0 表示正常退出） / Exit code (0 = normal exit)
    """
    logger.info(f"启动桌面应用: {WINDOW_TITLE}")
    logger.info(f"服务地址: http://{host}:{port}")

    # 1. 启动后台服务 / 1. Start background server
    server = _start_server(host, port)

    # 2. 等待服务就绪 / 2. Wait for server to be ready
    logger.info("等待服务启动...")
    if not _wait_for_server(host, port):
        logger.error("服务启动超时，请检查端口是否被占用")
        return 1

    logger.info("服务已就绪，正在创建窗口...")

    # 3. 创建并运行窗口（阻塞） / 3. Create and run window (blocking)
    url = f"http://{host}:{port}"
    try:
        _create_and_run_window(url)
    except Exception as e:
        logger.exception(f"窗口创建失败: {e}")
        return 1

    # 4. 窗口关闭后，优雅停止服务 / 4. After window closes, gracefully stop server
    logger.info("窗口已关闭，正在停止服务...")
    server.should_exit = True

    # 停止本地引擎常驻子进程（若在运行） / Stop resident engine subprocess if running
    try:
        from core.engine_host import get_engine_host
        engine = get_engine_host()
        if engine.is_running():
            engine.stop()
    except Exception:
        pass

    # 给服务一点时间完成清理 / Give server time to clean up
    time.sleep(0.5)

    logger.info("桌面应用已退出")
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

    parser = argparse.ArgumentParser(description="Open Meeting Scribe 桌面应用")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"服务地址（默认 {DEFAULT_HOST}）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"服务端口（默认 {DEFAULT_PORT}）")
    args = parser.parse_args()

    sys.exit(main(host=args.host, port=args.port))
