# -*- mode: python ; coding: utf-8 -*-
"""
Open Meeting Scribe — PyInstaller 打包配置
用法：在 Windows 上执行 pyinstaller build/pyinstaller.spec
"""

import os
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(SPECPATH).parent

block_cipher = None

a = Analysis(
    [str(ROOT / 'cli.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 前端静态文件
        (str(ROOT / 'app' / 'static'), 'app/static'),
        (str(ROOT / 'app' / 'admin_static'), 'app/admin_static'),
        # 数据模板（首次运行需要）
        (str(ROOT / 'data' / 'hotwords.txt'), 'data'),
        (str(ROOT / 'data' / 'philosophies.json'), 'data'),
        # 核心模型文件（声纹权重已迁移至云端，此处仅保留空目录结构）
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
        # 路由模块（动态导入）
        'app.routers.admin',
        'app.routers.auth',
        'app.routers.chat',
        'app.routers.config',
        'app.routers.hotwords',
        'app.routers.notes',
        'app.routers.philosophy',
        'app.routers.projects',
        'app.routers.record',
        'app.routers.settings',
        'app.routers.speakers',
        'app.routers.tasks',
        'app.routers.usage',
        'app.routers.user',
        'app.routers.voiceprint',
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
    name='MeetingScribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 保留控制台窗口（显示日志）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: 添加图标 build/icon.ico
)
