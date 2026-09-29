# -*- mode: python ; coding: utf-8 -*-
"""
Open Meeting Scribe — PyInstaller macOS 打包配置
用法：在 macOS 上执行 pyinstaller build/pyinstaller_macos.spec

前置条件：
1. 先运行 python build/convert_icon.py 生成 build/icon.icns
2. 确保已安装依赖：pip install -r requirements.txt pyinstaller

输出：
- dist/OpenMeetingScribe.app — macOS 应用包
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# 项目根目录
ROOT = Path(SPECPATH).parent

# 将项目根目录加入 sys.path，确保 collect_submodules 能找到 app/core 包
# （pathex 仅影响 PyInstaller 的模块图分析，不影响 spec 解析时的 Python import）
_root_str = str(ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

# 预先收集 app/core 全部子模块
_app_submodules = collect_submodules("app")
_core_submodules = collect_submodules("core")
print(f"[spec] app 子模块: {len(_app_submodules)} 个")
print(f"[spec] core 子模块: {len(_core_submodules)} 个")

block_cipher = None

# ── 数据文件（条件式收集，兼容 CI 环境） ──
# data/hotwords.txt 和 data/philosophies.json 在 .gitignore 中，
# CI 环境可能不存在，仅当文件实际存在时才加入打包清单。
_data_files = []
for _f in ["data/hotwords.txt", "data/philosophies.json"]:
    _full = ROOT / _f
    if _full.is_file():
        _data_files.append((str(_full), "data"))

# desktop-secrets.env 包含云端服务凭据，由 CI 构建时从 GitHub Secrets 生成。
# 本地测试时可手动创建；文件不存在时云端功能不可用，本地模式仍正常。
_desktop_secrets = ROOT / "desktop-secrets.env"
if _desktop_secrets.is_file():
    _data_files.append((str(_desktop_secrets), "."))
    print("[spec] desktop-secrets.env 已加入打包清单 ✓")
else:
    print("[spec] desktop-secrets.env 未找到，云端代理功能在打包版中将不可用")

a = Analysis(
    [str(ROOT / "desktop.py")],  # 桌面应用入口
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 前端静态文件
        (str(ROOT / "app" / "static"), "app/static"),
        (str(ROOT / "app" / "admin_static"), "app/admin_static"),
    ] + _data_files,
    hiddenimports=[
        # FastAPI / uvicorn 相关
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # ── 自动收集全部子模块（已在 spec 顶部预计算） ──
        # desktop.py 通过字符串 "app.server:app" 引用 uvicorn 应用，
        # PyInstaller 静态分析无法追踪此动态引用。
        *_app_submodules,
        *_core_submodules,
        # pywebview 桌面窗口 — macOS 使用 cocoa 后端（WKWebView）
        "webview",
        "webview.platforms.cocoa",
        # 其他
        "multipart",
        "jose",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块（减小包体）
        "torch",
        "torchaudio",
        "matplotlib",
        "IPython",
        "notebook",
        "pytest",
        # macOS 不需要其他平台后端
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "webview.platforms.cef",
        "webview.platforms.gtk",
        "webview.platforms.mshtml",
        "webview.platforms.win32",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── 图标处理 ──
# icon.icns 由 build/convert_icon.py 从 icon.ico 转换生成
_icon_path = ROOT / "build" / "icon.icns"
_icon = str(_icon_path) if _icon_path.is_file() else None
if _icon is None:
    print("警告：build/icon.icns 不存在，将使用默认图标")
    print("  请先运行：python build/convert_icon.py")

# macOS .app 使用 onedir 模式：EXE 仅包含脚本，
# binaries/datas 由 BUNDLE 放入 Frameworks/ 目录。
# Onefile 模式在 macOS .app 中已被弃用（v7.0 将报错）。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpenMeetingScribe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 桌面模式隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

# ── macOS .app 应用包 ──
app = BUNDLE(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="OpenMeetingScribe.app",
    icon=_icon,
    bundle_identifier="com.openmeeting.scribe",
    version="1.0.0",
    info_plist={
        "CFBundleDisplayName": "Open Meeting Scribe",
        "CFBundleName": "OpenMeetingScribe",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "会议助手需要使用麦克风进行录音",
        "NSAudioInputUsageDescription": "会议助手需要捕获系统音频进行转写",
    },
)
