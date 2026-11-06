"""
core/paths.py — 安装根目录定位 / Installation root resolution

BASE_DIR：PyInstaller 打包后为 exe 所在目录（数据持久化落点）；
开发模式为仓库根目录。STATIC_DIR 等静态资源路径仍在 app.store 定义。
"""

import sys
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # PyInstaller 模式：exe 所在目录（_MEIPASS 临时目录重启丢失，数据不可落此）
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
