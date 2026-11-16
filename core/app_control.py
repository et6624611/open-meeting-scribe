"""
core/app_control.py — 应用进程控制（桌面启动器模式）

浏览器模式下的进程生命周期约定：
  1. 启动器（desktop.py）先置位桌面模式，再启动 uvicorn；
  2. 前端「退出应用」调用 POST /api/app/quit，本模块置位退出事件；
  3. 启动器主线程等待事件后停服务、停本地引擎，进程退出。

非桌面模式（Docker / CLI server）不置位，退出端点直接拒绝，
避免远程调用意外停掉常驻服务。
"""

import threading

# 应用标识：/api/health 返回并用于启动器单实例探测，避免误认同端口的其他服务
APP_ID = "open-meeting-scribe"

_desktop_mode = False
_quit_event = threading.Event()


def enable_desktop_mode() -> None:
    """标记当前进程由桌面启动器拉起（退出端点仅在此时可用）。"""
    global _desktop_mode
    _desktop_mode = True


def is_desktop_mode() -> bool:
    """当前进程是否为桌面启动器模式。"""
    return _desktop_mode


def request_quit() -> None:
    """请求退出应用（由 /api/app/quit 调用）。"""
    _quit_event.set()


def wait_quit(timeout: float | None = None) -> bool:
    """阻塞等待退出请求；返回 True 表示收到退出信号。"""
    return _quit_event.wait(timeout)
