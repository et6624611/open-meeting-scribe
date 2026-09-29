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

# ── 关键：将项目根目录加入 sys.path ──
# pathex 仅影响 PyInstaller 的模块图分析，不影响 spec 解析时的 Python import。
# 如果不在此处显式添加 sys.path，collect_submodules 在 CI 环境中会因找不到
# app/core 包而返回空列表，导致打包后 exe 缺少整个应用模块。
_root_str = str(ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

# 预先收集 app/core 全部子模块（显式列举 + collect_submodules 双重保险）
_app_submodules = collect_submodules("app")
_core_submodules = collect_submodules("core")
print(f"[spec] app submodules: {len(_app_submodules)}: {_app_submodules}")
print(f"[spec] core submodules: {len(_core_submodules)}: {_core_submodules}")

block_cipher = None

a = Analysis(
    [str(ROOT / 'desktop.py')],  # 桌面应用入口
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 前端静态文件
        (str(ROOT / 'app' / 'static'), 'app/static'),
        (str(ROOT / 'app' / 'admin_static'), 'app/admin_static'),
        # 版本号文件（运行时读取）
        (str(ROOT / 'VERSION'), '.'),
        # i18n 翻译文件
        (str(ROOT / 'core' / 'i18n' / 'locales'), 'core/i18n/locales'),
        # 数据模板（首次运行需要；CI 环境中可能不存在，动态收集）
    ] + [
        (str(ROOT / f), 'data')
        for f in ['data/hotwords.txt', 'data/philosophies.json']
        if (ROOT / f).is_file()
    ] + (
        # 桌面端云端服务凭据（CI 构建时从 GitHub Secrets 生成）
        # 本地测试时手动创建；文件不存在时云端功能不可用，本地模式仍正常
        [(str(ROOT / 'desktop-secrets.env'), '.')]
        if (ROOT / 'desktop-secrets.env').is_file()
        else []
    ),
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
        # 显式列举确保即使 collect_submodules 失效也不会遗漏
        'app', 'app.server', 'app.admin_server', 'app.realtime_store',
        'app.settings_store', 'app.store', 'app.task_store',
        'app.routers', 'app.routers.admin', 'app.routers.admin_config',
        'app.routers.auth', 'app.routers.chat', 'app.routers.cloud_api',
        'app.routers.config', 'app.routers.hotwords', 'app.routers.insights',
        'app.routers.notes', 'app.routers.philosophy', 'app.routers.projects',
        'app.routers.record', 'app.routers.settings', 'app.routers.speakers',
        'app.routers.tasks', 'app.routers.update', 'app.routers.usage',
        'app.routers.user', 'app.routers.voiceprint', 'app.routers.ws_transcript',
        # ── 核心引擎层 ──
        'core', 'core.audio', 'core.audio_recording', 'core.auth',
        'core.chapters', 'core.chat_actions', 'core.chat_context', 'core.chat_edits',
        'core.cloud_client', 'core.diarization', 'core.diarization_cluster',
        'core.embedding_provider', 'core.errors', 'core.fs_atomic', 'core.hotwords',
        'core.i18n', 'core.i18n.middleware',
        'core.insights', 'core.joblog', 'core.llm', 'core.metering',
        'core.models', 'core.models.cam_plus',
        'core.perf', 'core.pipeline', 'core.pipeline_runner',
        'core.project_index', 'core.projects',
        'core.realtime_asr', 'core.realtime_chapters', 'core.realtime_summary',
        'core.remote_config', 'core.silence_detection', 'core.sms',
        'core.speaker_count', 'core.speakers', 'core.summarize',
        'core.text_bridge', 'core.transcribe', 'core.translate', 'core.upload',
        'core.users', 'core.version_check',
        'core.voiceprint', 'core.voiceprint_identify', 'core.voiceprint_registry',
        # ── collect_submodules 兜底（捕获上述可能遗漏的传递依赖） ──
        *_app_submodules,
        *_core_submodules,
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
