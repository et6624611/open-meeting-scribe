"""
core/cli_engine/ide_probe.py — IDE 探测与启动 / IDE detection and launching

作者 / Author: Yongliang Wang
创建 / Created: 2026-10-13
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 探测系统已安装的 IDE（VSCode/Cursor/Zed/Windsurf/Trae/Claude Code）
  - 启动 IDE 打开指定工作区目录（一次性 detach，不复用 runner.py 流式 CLI 会话）

原则：写死注册表 + shutil.which 探测，不引入额外依赖。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# IDE 注册表（按探测优先级排序） / IDE registry (ordered by detection priority)
# 兼容中文/空格安装路径的变体（Trae CN/Trae Solo 不同包名）
IDE_REGISTRY: list[dict] = [
    {"ide_id": "vscode", "binary": "code", "display_name": "VSCode"},
    {"ide_id": "cursor", "binary": "cursor", "display_name": "Cursor"},
    {"ide_id": "zed", "binary": "zeditor", "display_name": "Zed"},
    {"ide_id": "windsurf", "binary": "windsurf", "display_name": "Windsurf"},
    {"ide_id": "trae", "binary": "trae", "display_name": "Trae"},
    {"ide_id": "trae-cn", "binary": "trae-cn", "display_name": "Trae CN"},
    {"ide_id": "claude-code", "binary": "claude", "display_name": "Claude Code"},
]

# macOS .app 路径回退（CLI 不在 PATH 时用 .app 目录） /
# macOS .app fallback paths (when CLI binary not in PATH)
_MACOS_APP_PATHS: dict[str, str] = {
    "vscode": "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
    "cursor": "/Applications/Cursor.app/Contents/Resources/app/bin/cursor",
    "zed": "/Applications/Zed.app/Contents/MacOS/cli",
    "windsurf": "/Applications/Windsurf.app/Contents/Resources/app/bin/windsurf",
    "trae": "/Applications/Trae.app/Contents/Resources/app/bin/trae",
    "trae-cn": "/Applications/Trae CN.app/Contents/Resources/app/bin/trae-cn",
}


def _find_binary(binary: str) -> str | None:
    """查找可执行文件路径：先 PATH，再 macOS .app 回退。 / Find binary: PATH first, then macOS .app fallback."""
    path = shutil.which(binary)
    if path:
        return path
    if sys.platform == "darwin":
        app_path = _MACOS_APP_PATHS.get(binary)
        if app_path and Path(app_path).exists():
            return app_path
    return None


def detect_ides() -> list[dict]:
    """探测系统已安装的 IDE。 / Detect installed IDEs.

    Returns:
        [{"ide_id", "display_name", "available", "path"}]
    """
    result = []
    for ide in IDE_REGISTRY:
        path = _find_binary(ide["binary"])
        result.append({
            "ide_id": ide["ide_id"],
            "display_name": ide["display_name"],
            "available": bool(path),
            "path": path or "",
        })
    return result


def launch_ide(ide_id: str, workspace_path: Path) -> dict:
    """启动 IDE 打开指定目录（一次性 detach）。 / Launch IDE to open a directory (one-shot detach).

    Returns:
        {"launched": bool, "cmd": str, "error": str?}
    """
    ide = next((i for i in IDE_REGISTRY if i["ide_id"] == ide_id), None)
    if not ide:
        return {"launched": False, "cmd": "", "error": f"unknown_ide: {ide_id}"}

    binary = _find_binary(ide["binary"])
    if not binary:
        return {"launched": False, "cmd": ide["binary"],
                "error": f"not_installed: {ide['display_name']}"}

    workspace_path = workspace_path.resolve()
    if not workspace_path.is_dir():
        return {"launched": False, "cmd": binary,
                "error": f"not_a_directory: {workspace_path}"}

    cmd = [binary, str(workspace_path)]
    try:
        # 一次性 detach：close_fds + start_new_session 确保子进程独立于父进程 /
        # One-shot detach: close_fds + start_new_session ensures child is independent
        subprocess.Popen(
            cmd,
            close_fds=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("[IDE] 启动 %s 打开 %s", ide["display_name"], workspace_path)
        return {"launched": True, "cmd": " ".join(cmd)}
    except Exception as e:
        return {"launched": False, "cmd": " ".join(cmd), "error": str(e)}
