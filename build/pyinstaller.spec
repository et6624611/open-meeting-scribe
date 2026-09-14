# -*- mode: python ; coding: utf-8 -*-
"""
Open Meeting Scribe — PyInstaller 打包配置
用法：在 Windows 上执行 pyinstaller build/pyinstaller.spec
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# 项目根目录
ROOT = Path(SPECPATH).parent

block_cipher = None

a = Analysis(
    [str(ROOT / 'desktop.py')],  # 桌面应用入口
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 前端静态文件
        (str(ROOT / 'app' / 'static'), 'app/static'),
        (str(ROOT / 'app' / 'admin_static'), 'app/admin_static'),
        # 数据模板（首次运行需要；CI 环境中可能不存在，动态收集）
    ] + [
        (str(ROOT / f), 'data')
        for f in ['data/hotwords.txt', 'data/philosophies.json']
        if (ROOT / f).is_file()
    ],
    hiddenimports=[
        # FastAPI / uvicorn 相关
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # ── 应用层（desktop.py 通过字符串 "app.server:app" 引用，静态分析无法追踪）──
        # 使用 collect_submodules 自动收集全部子模块，避免新增模块遗漏
        *collect_submodules('app'),
        *collect_submodules('core'),
        # pywebview 桌面窗口
        'webview',
        'webview.platforms.winforms',  # Windows 平台后端
        # 其他
        'multipart',
        'jose',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块（减小包体）
        'torch',
        'torchaudio',
        'matplotlib',
        'IPython',
        'notebook',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='OpenMeetingScribe',
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
    icon=str(ROOT / 'build' / 'icon.ico'),
)
