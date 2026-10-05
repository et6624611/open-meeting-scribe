"""
core/engine_paths.py — 本地引擎运行时路径锚点（R8 / WP-G，D-G3 裁决 (a)）

平台锚点规则：
  - 冻结态 Windows：``%LOCALAPPDATA%\\OpenMeetingScribe\\``（models\\ / logs\\ / engine\\）
  - 冻结态 macOS：``~/Library/Application Support/OpenMeetingScribe/``
  - 开发态（非 frozen）：项目根 ``data/``（历史布局不变，models/ logs/；引擎走 venv）

设计约束：
  - 安装目录只放**只读代码包**（D-G3）：权重、日志、引擎运行时数据一律落锚点，
    不要求管理员权限；
  - 引擎组件（onedir 独立引擎包，D-G1 方案 A）搜索序见 :func:`get_engine_dir_candidates`；
  - 修复 B-2：冻结态禁止用相对路径 ``data/models/``（会解析进只读 ``sys._MEIPASS`` bundle）。
"""

import os
import sys
from pathlib import Path

APP_DIR_NAME = "OpenMeetingScribe"

# 引擎组件可执行体名（无扩展名基名；Windows 加 .exe）
ENGINE_EXE_BASENAME = "OMSEngine"

# 引擎组件 manifest 文件名（D-G1 子项①：三条安装通道共用同一布局与 manifest）
ENGINE_MANIFEST_NAME = "engine-manifest.json"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_project_root() -> Path:
    """开发态项目根目录 / Project root in dev mode."""
    return Path(__file__).resolve().parent.parent


def get_runtime_anchor() -> Path:
    """引擎运行时数据锚点根目录（D-G3 (a)）。

    冻结态 Win → %LOCALAPPDATA%\\OpenMeetingScribe；冻结态 mac →
    ~/Library/Application Support/OpenMeetingScribe；开发态 → <项目根>/data。
    """
    if is_frozen():
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(base) / APP_DIR_NAME
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
        # 其他平台（不在发布矩阵内）：XDG 兜底
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(base) / APP_DIR_NAME.lower()
    return get_project_root() / "data"


def get_default_model_dir() -> Path:
    """模型权重默认目录（settings 未显式配置 model_dir 时使用）。

    开发态保持相对 ``data/models/``（历史行为不变，gitignored）；
    冻结态落平台锚点 ``<anchor>/models``（绝对路径，B-2 修复）。
    """
    if is_frozen():
        return get_runtime_anchor() / "models"
    return Path("data/models/")


def get_logs_dir() -> Path:
    """引擎日志目录（B-3：stderr 落盘位置）。"""
    if is_frozen():
        return get_runtime_anchor() / "logs"
    return get_project_root() / "data" / "logs"


def engine_exe_name() -> str:
    return ENGINE_EXE_BASENAME + (".exe" if sys.platform == "win32" else "")


def get_engine_dir_candidates() -> list[Path]:
    """冻结态引擎组件目录搜索序（D-G1：三条安装通道共用同一目录布局）。

    1. 环境变量 ``OMS_ENGINE_DIR`` 显式覆盖（运维/CI 冒烟用）；
    2. settings ``engine.local.engine_dir`` 显式覆盖（管理员配置）；
    3. 主程序 exe 同级 ``engine/``（Win Inno [Components] 安装布局，G-4）；
    4. 平台锚点 ``<anchor>/engine/``（mac L2 应用内一键落位 G-4b / Win 应用内安装）。
    """
    candidates: list[Path] = []

    env_dir = os.environ.get("OMS_ENGINE_DIR", "").strip()
    if env_dir:
        candidates.append(Path(env_dir).expanduser())

    try:
        from app.settings_store import get_engine_config
        cfg_dir = (get_engine_config()["local"].get("engine_dir") or "").strip()
        if cfg_dir:
            candidates.append(Path(cfg_dir).expanduser())
    except Exception:
        pass

    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "engine")
        candidates.append(get_runtime_anchor() / "engine")
    else:
        # 开发态：引擎走 venv（python -m core.engine_worker），此处仅提供项目根
        # engine/ 目录作为可选覆盖（如手工放置的引擎包冒烟）。
        candidates.append(get_project_root() / "engine")

    return candidates


def locate_engine_executable() -> Path | None:
    """在候选目录中定位引擎可执行体（存在且可执行即返回）。"""
    exe_name = engine_exe_name()
    for root in get_engine_dir_candidates():
        exe = root / exe_name
        if exe.is_file() and os.access(exe, os.X_OK):
            return exe
    return None


def locate_engine_manifest() -> dict | None:
    """读取已定位引擎根下的 engine-manifest.json；找不到/损坏返回 None。"""
    import json

    exe = locate_engine_executable()
    if exe is None:
        return None
    manifest_path = exe.parent / ENGINE_MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
