#!/usr/bin/env python3
"""
desktop.py — Open Meeting Scribe 桌面应用入口

作者：王永亮
创建：2026-09-13
版本：1.0.0

说明：
    在单进程中同时启动 FastAPI 后台服务与 pywebview 原生窗口，
    为用户提供独立桌面应用体验（无浏览器地址栏干扰）。

用法：
    # 开发时直接运行
    python desktop.py

    # 或通过 CLI 子命令
    python cli.py app

    # PyInstaller 打包后双击即可运行
    MeetingScribe.exe
"""

import logging
import sys
import threading
import time

# 加载环境变量（必须在导入项目模块之前）
from dotenv import load_dotenv

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 默认服务配置
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# 窗口配置
WINDOW_TITLE = "Open Meeting Scribe"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
MIN_WIDTH = 960
MIN_HEIGHT = 600


def _wait_for_server(host: str, port: int, timeout: float = 10.0) -> bool:
    """等待 FastAPI 服务就绪。

    通过轮询 HTTP 健康检查端点判断服务是否启动完成。

    Args:
        host: 服务地址
        port: 服务端口
        timeout: 最大等待时间（秒）

    Returns:
        True 表示服务已就绪，False 表示超时
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
    """在后台线程启动 FastAPI 服务。

    Args:
        host: 监听地址
        port: 监听端口

    Returns:
        uvicorn.Server 实例（可用于后续停止服务）
    """
    import uvicorn

    config = uvicorn.Config(
        "app.server:app",
        host=host,
        port=port,
        log_level="warning",
        # 禁用访问日志，减少桌面模式下的控制台噪音
        access_log=False,
    )
    server = uvicorn.Server(config)

    # 在后台守护线程中运行服务
    thread = threading.Thread(target=server.run, daemon=True, name="fastapi-server")
    thread.start()

    return server


def _create_and_run_window(url: str) -> None:
    """创建 pywebview 原生窗口并进入事件循环。

    Args:
        url: 要加载的页面地址
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

    # ─── 桌面端刷新快捷键注入 ───
    # 页面加载完成后注入 JS，监听 F5 键并派发自定义事件，
    # 由 Vue 应用层判断录音状态后决定是否执行刷新。
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

    # 进入事件循环（阻塞直到所有窗口关闭）
    webview.start()


def main(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    """桌面应用主入口。

    启动流程：
        1. 后台线程启动 FastAPI 服务
        2. 等待服务就绪
        3. 创建 pywebview 原生窗口
        4. 窗口关闭后优雅停止服务

    Args:
        host: 服务监听地址
        port: 服务监听端口

    Returns:
        退出码（0 表示正常退出）
    """
    logger.info(f"启动桌面应用: {WINDOW_TITLE}")
    logger.info(f"服务地址: http://{host}:{port}")

    # 1. 启动后台服务
    server = _start_server(host, port)

    # 2. 等待服务就绪
    logger.info("等待服务启动...")
    if not _wait_for_server(host, port):
        logger.error("服务启动超时，请检查端口是否被占用")
        return 1

    logger.info("服务已就绪，正在创建窗口...")

    # 3. 创建并运行窗口（阻塞）
    url = f"http://{host}:{port}"
    try:
        _create_and_run_window(url)
    except Exception as e:
        logger.exception(f"窗口创建失败: {e}")
        return 1

    # 4. 窗口关闭后，优雅停止服务
    logger.info("窗口已关闭，正在停止服务...")
    server.should_exit = True

    # 给服务一点时间完成清理
    time.sleep(0.5)

    logger.info("桌面应用已退出")
    return 0


if __name__ == "__main__":
    # 支持通过命令行参数覆盖默认配置
    import argparse

    parser = argparse.ArgumentParser(description="Open Meeting Scribe 桌面应用")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"服务地址（默认 {DEFAULT_HOST}）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"服务端口（默认 {DEFAULT_PORT}）")
    args = parser.parse_args()

    sys.exit(main(host=args.host, port=args.port))
