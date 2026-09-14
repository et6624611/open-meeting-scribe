"""
app/routers/projects.py — 项目管理 + 文件系统浏览 / Project management + filesystem browsing
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.store import tasks
from core import projects
from core.i18n import _

logger = logging.getLogger(__name__)

# 允许浏览/打开的根目录白名单 / Root directory whitelist for browsing/opening
_ALLOWED_BROWSE_ROOTS = [
    Path.home(),                           # 用户主目录 / User home directory
    Path("data").resolve(),                # 项目 data 目录 / Project data directory
]


def _is_path_allowed(path: Path, allowed_roots: list[Path]) -> bool:
    """检查路径是否在允许的根目录范围内（防止目录遍历）。 / Check if path is within allowed root directories (prevent directory traversal).

    使用 Path.is_relative_to 而非字符串 startswith，避免同前缀目录绕过 / Use Path.is_relative_to instead of str startswith to avoid same-prefix bypass
    （如 /home/user2 被 str.startswith("/home/user") 误判为允许）。 / (e.g. /home/user2 falsely passing str.startswith("/home/user")).
    """
    resolved = path.resolve()
    return any(resolved.is_relative_to(root.resolve()) for root in allowed_roots)


router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    folders: Optional[list[str]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None


class FolderAction(BaseModel):
    path: str


class FolderSyncConfig(BaseModel):
    path: str
    enabled: Optional[bool] = None
    content_types: Optional[list[str]] = None
    subfolder_name: Optional[str] = None


class SearchQuery(BaseModel):
    query: str
    limit: int = 5


@router.get("/api/filesystem/browse")
def browse_filesystem(path: Optional[str] = None):
    """浏览本地文件系统（仅返回目录）。 / Browse local filesystem (directories only).

    注意：用 def（非 async def），目录遍历（iterdir/is_dir）是阻塞 I/O， / Note: uses def (not async def); directory traversal (iterdir/is_dir) is blocking I/O,
    尤其在文件多的目录下会阻塞事件循环数百毫秒。 / especially in directories with many files, can block event loop for hundreds of ms.
    """
    target = Path(path) if path else Path.home()
    target = target.resolve()

    # 安全校验：限制可浏览范围 / Security check: restrict browsing scope
    if not _is_path_allowed(target, _ALLOWED_BROWSE_ROOTS):
        raise HTTPException(403, _("Access denied: path outside allowed directories"))

    if not target.exists():
        raise HTTPException(404, _("Path not found: {path}").format(path=target))
    if not target.is_dir():
        raise HTTPException(400, _("Not a directory: {path}").format(path=target))

    directories = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_dir() and not entry.name.startswith('.'):
                # 检查是否有子目录（用于前端展开指示器） / Check for subdirectories (for frontend expand indicator)
                has_children = False
                try:
                    has_children = any(
                        child.is_dir() and not child.name.startswith('.')
                        for child in entry.iterdir()
                    )
                except PermissionError:
                    pass
                directories.append({
                    "name": entry.name,
                    "path": str(entry),
                    "has_children": has_children,
                })
    except PermissionError:
        raise HTTPException(403, _("No permission to access: {path}").format(path=target))

    return {
        "current_path": str(target),
        "parent_path": str(target.parent) if target.parent != target else None,
        "home_path": str(Path.home()),
        "directories": directories,
    }


@router.post("/api/folders/open")
def open_folder_in_finder(data: FolderAction):
    """在系统文件管理器（Finder/资源管理器）中打开指定文件夹。 / Open folder in system file manager (Finder/Explorer)."""
    folder_path = data.path.strip()
    target = Path(folder_path)

    # 安全校验：限制可打开范围 / Security check: restrict opening scope
    if not _is_path_allowed(target, _ALLOWED_BROWSE_ROOTS):
        raise HTTPException(403, _("Access denied: path outside allowed directories"))

    if not target.exists():
        raise HTTPException(404, _("Folder not found: {path}").format(path=folder_path))
    if not target.is_dir():
        raise HTTPException(400, _("Not a directory: {path}").format(path=folder_path))

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as e:
        raise HTTPException(500, _("Failed to open folder: {err}").format(err=e))

    return {"opened": True, "path": str(target)}


@router.get("/api/projects")
def list_projects():
    """获取项目列表（读 projects.json） / Get project list (reads projects.json)"""
    project_list = projects.list_projects()
    return {"projects": project_list}


@router.post("/api/projects")
def create_project(data: ProjectCreate, background_tasks: BackgroundTasks):
    """创建项目（写 projects.json） / Create project (writes projects.json)"""
    if not data.name.strip():
        raise HTTPException(400, _("Knowledge base name cannot be empty"))
    # 验证文件夹路径 / Validate folder paths
    if data.folders:
        for f in data.folders:
            if not Path(f).exists() or not Path(f).is_dir():
                raise HTTPException(400, _("Folder not found: {path}").format(path=f))
    project = projects.create_project(name=data.name.strip(), folders=data.folders)
    # 自动触发索引构建 / Auto-trigger index build
    if data.folders:
        background_tasks.add_task(_do_scan_project, project["id"])
    return project


@router.get("/api/projects/{project_id}")
def get_project(project_id: str):
    """获取项目详情（读 projects.json + 索引文件 + 关联会议） / Get project details (reads projects.json + index files + linked meetings)"""
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(404, _("Knowledge base not found"))
    # 附加索引信息 / Attach index info
    index = projects.get_project_index(project_id)
    if index:
        project["file_count"] = index.get("total_files", 0)
        project["indexed_at"] = index.get("indexed_at")
    # 查询关联的会议纪要 / Query linked meeting minutes
    meetings = []
    for t in tasks.values():
        if t.get("project_id") == project_id:
            meetings.append({
                "task_id": t.get("task_id"),
                "title": t.get("title") or t.get("audio_name") or "未命名",
                "status": t.get("status"),
                "meeting_date": t.get("meeting_date"),
                "created_at": t.get("created_at"),
                "audio_duration": t.get("audio_duration"),
                "speaker_count": t.get("speaker_count"),
            })
    meetings.sort(key=lambda m: m.get("meeting_date") or m.get("created_at", ""), reverse=True)
    project["meetings"] = meetings
    return project


@router.put("/api/projects/{project_id}")
def update_project(project_id: str, data: ProjectUpdate):
    """更新项目（写 projects.json） / Update project (writes projects.json)"""
    project = projects.update_project(project_id, name=data.name)
    if not project:
        raise HTTPException(404, _("Knowledge base not found"))
    return project


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    """删除项目（写 projects.json） / Delete project (writes projects.json)"""
    if not projects.delete_project(project_id):
        raise HTTPException(404, _("Knowledge base not found"))
    return {"deleted": True}


@router.post("/api/projects/{project_id}/folders")
def add_project_folder(project_id: str, data: FolderAction, background_tasks: BackgroundTasks):
    """为项目添加文件夹（写 projects.json） / Add folder to project (writes projects.json)"""
    folder_path = data.path.strip()
    if not Path(folder_path).exists() or not Path(folder_path).is_dir():
        raise HTTPException(400, _("Folder not found: {path}").format(path=folder_path))
    project = projects.add_folder(project_id, folder_path)
    if not project:
        raise HTTPException(404, _("Knowledge base not found"))
    # 自动触发索引构建 / Auto-trigger index build
    background_tasks.add_task(_do_scan_project, project_id)
    return project


@router.delete("/api/projects/{project_id}/folders")
def remove_project_folder(project_id: str, data: FolderAction, background_tasks: BackgroundTasks):
    """从项目移除文件夹（写 projects.json） / Remove folder from project (writes projects.json)"""
    project = projects.remove_folder(project_id, data.path)
    if not project:
        raise HTTPException(404, _("Knowledge base not found"))
    # 自动触发索引重建 / Auto-trigger index rebuild
    background_tasks.add_task(_do_scan_project, project_id)
    return project


@router.put("/api/projects/{project_id}/folders/sync")
def update_folder_sync_config(project_id: str, data: FolderSyncConfig):
    """更新文件夹的自动同步配置 / Update folder auto-sync config"""
    config = {}
    if data.enabled is not None:
        config["enabled"] = data.enabled
    if data.content_types is not None:
        config["content_types"] = data.content_types
    if data.subfolder_name is not None:
        config["subfolder_name"] = data.subfolder_name
    result = projects.update_folder_sync(project_id, data.path, config)
    if not result:
        raise HTTPException(404, _("Knowledge base or folder not found"))
    return result


@router.post("/api/projects/{project_id}/sync")
def trigger_project_sync(project_id: str):
    """手动触发同步：将项目中所有已完成的会议同步写入启用了同步的文件夹 / Manually trigger sync: sync all completed meetings to sync-enabled folders"""
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(404, _("Knowledge base not found"))

    sync_folders = projects.get_sync_enabled_folders(project_id)
    if not sync_folders:
        return {"synced": 0, "message": _("No folders with sync enabled")}

    from core.projects import sync_meeting_to_folders

    synced_count = 0
    written_files = []
    for t in tasks.values():
        if t.get("project_id") == project_id and t.get("status") == "completed":
            written = sync_meeting_to_folders(t)
            if written:
                synced_count += 1
                written_files.extend(written)

    return {
        "synced": synced_count,
        "files": written_files,
        "message": _("Synced {count} meeting(s), wrote {files} file(s)").format(count=synced_count, files=len(written_files)),
    }


def _do_scan_project(project_id: str):
    """后台执行项目索引扫描（可复用） / Background project index scan (reusable)"""
    try:
        result = projects.scan_project(project_id)
        logger.info("项目索引构建完成: %s, %d 个文件", project_id, result.get("total_files", 0))
    except Exception as e:
        logger.error("项目索引构建失败: %s, %s", project_id, e)


@router.post("/api/projects/{project_id}/scan")
def scan_project(project_id: str, background_tasks: BackgroundTasks):
    """触发项目索引构建（后台执行） / Trigger project index build (background)"""
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(404, _("Knowledge base not found"))
    background_tasks.add_task(_do_scan_project, project_id)
    return {"status": "scanning", "message": _("Index build started")}


@router.get("/api/projects/{project_id}/files")
def get_project_files(project_id: str):
    """获取项目索引中的文件列表（读索引 JSON） / Get indexed file list (reads index JSON)"""
    index = projects.get_project_index(project_id)
    if not index:
        return {"files": [], "indexed_at": None}
    return {
        "files": index.get("files", []),
        "indexed_at": index.get("indexed_at"),
        "total_files": index.get("total_files", 0),
    }


@router.post("/api/projects/{project_id}/search")
def search_project_files(project_id: str, data: SearchQuery):
    """在项目索引中搜索（读索引 JSON） / Search project index (reads index JSON)"""
    results = projects.search_project(project_id, data.query, limit=data.limit)
    return {"results": results, "total": len(results)}
