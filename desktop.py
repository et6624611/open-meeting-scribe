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
# 在导入任何依赖 logging 的模块之前，确保标准流不为 None。
# When packaged with console=False, sys.stderr/stdout are None,
# uvicorn logging config calls sys.stderr.isatty() causing AttributeError.
# Ensure std streams are not None before importing any module that depends on logging.
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

# 加载环境变量（必须在导入项目模块之前） / Load env vars (must be before importing project modules)
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

    # 给服务一点时间完成清理 / Give server time to clean up
    time.sleep(0.5)

    logger.info("桌面应用已退出")
    return 0


if __name__ == "__main__":
    # 支持通过命令行参数覆盖默认配置 / Support overriding default config via CLI args
    import argparse

    parser = argparse.ArgumentParser(description="Open Meeting Scribe 桌面应用")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"服务地址（默认 {DEFAULT_HOST}）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"服务端口（默认 {DEFAULT_PORT}）")
    args = parser.parse_args()

    sys.exit(main(host=args.host, port=args.port))
