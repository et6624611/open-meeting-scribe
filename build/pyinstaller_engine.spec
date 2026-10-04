# -*- mode: python ; coding: utf-8 -*-
"""
Open Meeting Scribe — 独立本地引擎包 PyInstaller 配置（R8 / WP-G，D-G1 方案 A）

用法（引擎构建环境需已安装 torch/funasr/modelscope，与主应用云包环境隔离）：
    pyinstaller build/pyinstaller_engine.spec

产物（onedir，三条安装通道共用同一布局，D-G1 子项①）：
    dist/OMSEngine/OMSEngine(.exe)      引擎可执行体（stdin/stdout JSON Lines）
    dist/OMSEngine/_internal/           冻结运行时（含 torch/funasr/modelscope）
    dist/OMSEngine/engine-manifest.json 由 build/make_engine_manifest.py 构建后生成

硬约束（AC-7）：
  - 本 spec 与主包 build/pyinstaller.spec / pyinstaller_macos.spec 完全独立，
    主包 excludes torch 的瘦身屏障不受影响，主包 spec 一字不动；
  - 引擎包**不包含**主应用（无 app.server / webview / fastapi 界面层），
    仅收 core 中引擎工作端所需模块。
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent

# spec 解析期 import 需要项目根在 sys.path（同主包 spec 的处理）
_root_str = str(ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

datas: list = []
binaries: list = []
hiddenimports: list = []

# ── 重依赖全量收集（funasr 数据文件/动态库多，collect_all 对齐 Spike 配方）──
for _pkg in ("funasr", "modelscope", "torch"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# torchaudio 为可选依赖（部分 funasr 管线用到）；构建环境未安装则跳过
try:
    _d, _b, _h = collect_all("torchaudio")
    datas += _d
    binaries += _b
    hiddenimports += _h
except Exception:
    print("[engine-spec] torchaudio 未安装，跳过（funasr 基础管线不需要）")

# ── 引擎工作端所需的项目内模块（最小集合，不收 app.server/界面层）──
hiddenimports += [
    "core.engine_worker",
    "core.engine_host",
    "core.engine_paths",
    "core.model_registry",
    "core.model_downloader",
    "core.fs_atomic",
    "core.errors",
    "app.settings_store",
    "requests",
]
# collect_submodules 兜底（捕获传递依赖遗漏）
hiddenimports += collect_submodules("core.engine_worker")

a = Analysis(
    [str(ROOT / "engine_entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 引擎包不需要界面层与开发工具（减小体积、缩小攻击面）
        "matplotlib",
        "IPython",
        "notebook",
        "pytest",
        "webview",
        "fastapi",
        "uvicorn",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir：二进制/数据由 COLLECT 落 _internal/
    name="OMSEngine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # torch 原生库经 UPX 压缩有损坏风险，引擎包统一禁用 UPX
    upx=False,
    runtime_tmpdir=None,
    console=True,  # 子进程形态：stderr 为日志通道，由宿主收集（B-3）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="OMSEngine",
)
