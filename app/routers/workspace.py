"""
app/routers/workspace.py — 工作区浏览/预览/刷新/导入/打开端点
Workspace browse/preview/refresh/import/open endpoints

独立白名单（PREVIEW_ROOT 为根），不扩 _ALLOWED_BROWSE_ROOTS——
那是用户文件浏览域，工作区是应用内部域，分离职责。
"""

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.settings_store import get_feature_flags
from core.cli_engine.context_export import (
    attach_ide_rule,
    export_global_context,
    export_project_context,
    import_from_workspace,
    preview_workspace_dir,
    project_preview_dir,
    read_global_index,
    read_meetings_index,
    refresh_workspace,
)
from core.cli_engine.ide_probe import detect_ides, launch_ide
from core.i18n import _
from core.task_store import tasks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspace"])

# 允许的文件扩展名（预览只读文本） / Allowed file extensions (read-only text preview)
_PREVIEWABLE_EXTS = {".md", ".json", ".txt"}
_MAX_PREVIEW_BYTES = 64 * 1024  # 64KB


class TaskAction(BaseModel):
    task_id: str


class OpenIdeAction(BaseModel):
    task_id: str
    ide_id: str
    scope: str = "meeting"  # meeting | project | all


def _resolve_preview_dir(task_id: str) -> Path:
    """根据 task_id 解析预览工作区目录（从 task 取 project_id 路由）。"""
    task = tasks.get(task_id)
    project_id = task.get("project_id") if task else None
    return preview_workspace_dir(task_id, project_id, task)


def _is_path_allowed(path: Path, root: Path) -> bool:
    """检查路径是否在允许的根目录范围内。"""
    try:
        resolved = path.resolve()
        return resolved.is_relative_to(root.resolve())
    except Exception:
        return False


@router.get("/api/workspace/tree")
def get_workspace_tree(task_id: str):
    """获取工作区文件树。 / Get workspace file tree."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    ws = _resolve_preview_dir(task_id)
    if not ws.is_dir():
        return {"path": str(ws), "nodes": [], "exists": False}

    def build_tree(dir_path: Path, rel_base: Path) -> list[dict]:
        nodes = []
        try:
            for entry in sorted(dir_path.iterdir(), key=lambda e: e.name.lower()):
                if entry.name.startswith(".") and entry.name != ".gitignore":
                    continue
                rel = entry.relative_to(rel_base)
                if entry.is_dir():
                    children = build_tree(entry, rel_base)
                    nodes.append({
                        "name": entry.name,
                        "type": "dir",
                        "rel_path": str(rel),
                        "size": 0,
                        "children": children,
                    })
                else:
                    nodes.append({
                        "name": entry.name,
                        "type": "file",
                        "rel_path": str(rel),
                        "size": entry.stat().st_size,
                    })
        except PermissionError:
            pass
        return nodes

    nodes = build_tree(ws, ws)
    return {"path": str(ws), "nodes": nodes, "exists": True}


@router.get("/api/workspace/file")
def get_workspace_file(task_id: str, rel_path: str):
    """获取工作区文件内容（只读文本预览）。 / Get workspace file content (read-only text)."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    ws = _resolve_preview_dir(task_id)
    target = (ws / rel_path).resolve()

    if not _is_path_allowed(target, ws):
        raise HTTPException(403, _("Access denied: path outside workspace"))

    if not target.exists() or not target.is_file():
        raise HTTPException(404, _("File not found: {path}").format(path=rel_path))

    if target.suffix not in _PREVIEWABLE_EXTS:
        raise HTTPException(400, _("File type not previewable: {ext}").format(ext=target.suffix))

    size = target.stat().st_size
    truncated = size > _MAX_PREVIEW_BYTES
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        if truncated:
            content = content[:_MAX_PREVIEW_BYTES] + "\n\n…（文件过大已截断）"
    except Exception as e:
        raise HTTPException(500, _("Failed to read file: {err}").format(err=e))

    return {"content": content, "truncated": truncated, "size": size, "path": rel_path}


@router.post("/api/workspace/refresh")
def refresh_workspace_api(data: TaskAction):
    """刷新工作区（从软件数据重新生成）。 / Refresh workspace from app data."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    result = refresh_workspace(data.task_id)
    if result.get("error"):
        raise HTTPException(404, result["error"])
    return result


@router.post("/api/workspace/import")
def import_workspace_api(data: TaskAction):
    """从工作区导入 summary/notes 变更（走 propose 通道）。 / Import changes from workspace."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    result = import_from_workspace(data.task_id)
    if result.get("error"):
        status = 404 if result["error"] == "task_not_found" else 400
        raise HTTPException(status, result["error"])
    return result


@router.post("/api/workspace/open-finder")
def open_in_finder(data: TaskAction):
    """在系统文件管理器中打开工作区。 / Open workspace in system file manager."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    ws = _resolve_preview_dir(data.task_id)
    if not ws.is_dir():
        raise HTTPException(404, _("Workspace not found"))

    try:
        if sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", str(ws)], close_fds=True, start_new_session=True)
        elif sys.platform == "win32":
            import subprocess
            subprocess.Popen(["explorer", str(ws)], close_fds=True, start_new_session=True)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(ws)], close_fds=True, start_new_session=True)
    except Exception as e:
        raise HTTPException(500, _("Failed to open folder: {err}").format(err=e))

    return {"opened": True, "path": str(ws)}


@router.post("/api/workspace/open-ide")
def open_in_ide(data: OpenIdeAction):
    """启动 IDE 打开工作区，可指定上下文范围（单场 / 项目 / 全部）。"""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    task = tasks.get(data.task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))

    scope = (data.scope or "meeting").lower()
    try:
        if scope == "project" and task.get("project_id"):
            export = export_project_context(task["project_id"], ide_id=data.ide_id)
            ws = Path(export["workspace"])
        elif scope == "all":
            export = export_global_context(ide_id=data.ide_id)
            ws = Path(export["workspace"])
        else:
            scope = "meeting"
            export = {}
            ws = _resolve_preview_dir(data.task_id)
            # 单场目录不重新导出，只补当前 IDE 的原生规则入口
            attach_ide_rule(ws, data.ide_id, "本目录为单场会议上下文；跨会议请看上级索引。")
    except Exception as e:  # noqa: BLE001 - 导出失败按 500 回传，前端提示可重试
        logger.exception("[IDE] 上下文导出失败 task=%s scope=%s", data.task_id, scope)
        raise HTTPException(500, _("Failed to prepare workspace: {err}").format(err=e))

    if not ws.is_dir():
        raise HTTPException(404, _("Workspace not found"))

    result = launch_ide(data.ide_id, ws)
    if not result["launched"]:
        raise HTTPException(400, result.get("error", "launch_failed"))
    return {**result, "workspace": str(ws), "scope": scope,
            "file_count": export.get("file_count", 0)}


@router.get("/api/workspace/ides")
def list_ides():
    """列出系统已安装的 IDE。 / List installed IDEs."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))
    return {"ides": detect_ides()}


@router.get("/api/workspace/projects")
def list_workspace_projects():
    """获取全局工作区索引。 / Get global workspace index."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    index = read_global_index()
    if not index:
        return {"projects": [], "standalone_count": 0, "exists": False}
    return {**index, "exists": True}


@router.get("/api/workspace/project/{project_id}/meetings")
def list_project_meetings(project_id: str):
    """获取项目内会议索引。 / Get project meetings index."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    index = read_meetings_index(project_preview_dir(project_id))
    if not index:
        return {"meetings": [], "exists": False}
    return {**index, "exists": True}


@router.get("/api/workspace/preview")
def generate_preview(task_id: str):
    """预生成工作区（进会议页时调用）。 / Pre-generate workspace (on entering meeting page)."""
    if not get_feature_flags().get("workspace_explorer", True):
        raise HTTPException(403, _("Workspace explorer is disabled"))

    from core.cli_engine.context_export import export_preview_context
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    project_id = task.get("project_id")
    return export_preview_context(task_id=task_id, task=task, project_id=project_id)
