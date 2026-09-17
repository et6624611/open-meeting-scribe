# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Open Meeting Scribe
用于打包 Windows 桌面应用程序
"""

import sys
from pathlib import Path

block_cipher = None

# 项目根目录
ROOT_DIR = Path('.')

a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 前端静态文件
        ('app/static', 'app/static'),
        ('app/admin_static', 'app/admin_static'),
        # 国际化文件
        ('core/i18n/locales', 'core/i18n/locales'),
        # 版本文件
        ('VERSION', '.'),
        # 第三方许可声明（MIT/BSD/Apache 合规）
        ('THIRD_PARTY_NOTICES.md', '.'),
    ],
    hiddenimports=[
        # FastAPI 和 uvicorn
        'fastapi',
        'uvicorn',
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
        
        # pywebview
        'webview',
        'webview.platforms.edgechromium',
        
        # 项目核心模块
        'core',
        'core.audio',
        'core.audio_recording',
        'core.auth',
        'core.chapters',
        'core.chat_actions',
        'core.chat_context',
        'core.chat_edits',
        'core.diarization',
        'core.diarization_cluster',
        'core.embedding_provider',
        'core.errors',
        'core.fs_atomic',
        'core.hotwords',
        'core.insights',
        'core.joblog',
        'core.llm',
        'core.metering',
        'core.perf',
        'core.pipeline',
        'core.pipeline_runner',
        'core.project_index',
        'core.projects',
        'core.realtime_asr',
        'core.realtime_chapters',
        'core.realtime_summary',
        'core.remote_config',
        'core.silence_detection',
        'core.sms',
        'core.speaker_count',
        'core.speakers',
        'core.summarize',
        'core.text_bridge',
        'core.transcribe',
        'core.translate',
        'core.upload',
        'core.users',
        'core.version_check',
        'core.voiceprint',
        'core.voiceprint_identify',
        'core.voiceprint_registry',
        
        # 应用模块
        'app',
        'app.server',
        'app.admin_server',
        'app.realtime_store',
        'app.settings_store',
        'app.store',
        'app.task_store',
        
        # 路由模块
        'app.routers',
        'app.routers.admin',
        'app.routers.admin_config',
        'app.routers.auth',
        'app.routers.chat',
        'app.routers.config',
        'app.routers.hotwords',
        'app.routers.insights',
        'app.routers.notes',
        'app.routers.philosophy',
        'app.routers.projects',
        'app.routers.record',
        'app.routers.settings',
        'app.routers.speakers',
        'app.routers.tasks',
        'app.routers.update',
        'app.routers.usage',
        'app.routers.user',
        'app.routers.voiceprint',
        'app.routers.ws_transcript',
        
        # 第三方依赖
        'requests',
        'httpx',
        'dotenv',
        'jwt',
        'multipart',
        'websockets',
        'numpy',
        'scipy',
        'docx',
        'PyPDF2',
        'dashscope',
        'babel',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OpenMeetingScribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标: icon='icon.ico'
)
