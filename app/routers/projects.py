"""
app/routers/projects.py — 项目管理 + 文件系统浏览
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from core import projects
from core.i18n import _
from app.store import tasks

logger = logging.getLogger(__name__)

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
    """
    浏览本地文件系统（仅返回目录）。

    注意：用 def（非 async def），目录遍历（iterdir/is_dir）是阻塞 I/O，
    尤其在文件多的目录下会阻塞事件循环数百毫秒。
    """
    target = Path(path) if path else Path.home()
    target = target.resolve()

    if not target.exists():
        raise HTTPException(404, _("Path not found: {path}").format(path=target))
    if not target.is_dir():
        raise HTTPException(400, _("Not a directory: {path}").format(path=target))

    directories = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_dir() and not entry.name.startswith('.'):
                # 检查是否有子目录（用于前端展开指示器）
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
    """
    在系统文件管理器（Finder/资源管理器）中打开指定文件夹。
    """
    folder_path = data.path.strip()
    target = Path(folder_path)
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
    """获取项目列表（读 projects.json）"""
    project_list = projects.list_projects()
    return {"projects": project_list}


@router.post("/api/projects")
def create_project(data: ProjectCreate, background_tasks: BackgroundTasks):
    """创建项目（写 projects.json）"""
    if not data.name.strip():
        raise HTTPException(400, _("Project name cannot be empty"))
    # 验证文件夹路径
    if data.folders:
        for f in data.folders:
            if not Path(f).exists() or not Path(f).is_dir():
                raise HTTPException(400, _("Folder not found: {path}").format(path=f))
    project = projects.create_project(name=data.name.strip(), folders=data.folders)
    # 自动触发索引构建
    if data.folders:
        background_tasks.add_task(_do_scan_project, project["id"])
    return project


@router.get("/api/projects/{project_id}")
def get_project(project_id: str):
    """获取项目详情（读 projects.json + 索引文件 + 关联会议）"""
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(404, _("Project not found"))
    # 附加索引信息
    index = projects.get_project_index(project_id)
    if index:
        project["file_count"] = index.get("total_files", 0)
        project["indexed_at"] = index.get("indexed_at")
    # 查询关联的会议纪要
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
    """更新项目（写 projects.json）"""
    project = projects.update_project(project_id, name=data.name)
    if not project:
        raise HTTPException(404, _("Project not found"))
    return project


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    """删除项目（写 projects.json）"""
    if not projects.delete_project(project_id):
        raise HTTPException(404, _("Project not found"))
    return {"deleted": True}


@router.post("/api/projects/{project_id}/folders")
def add_project_folder(project_id: str, data: FolderAction, background_tasks: BackgroundTasks):
    """为项目添加文件夹（写 projects.json）"""
    folder_path = data.path.strip()
    if not Path(folder_path).exists() or not Path(folder_path).is_dir():
        raise HTTPException(400, _("Folder not found: {path}").format(path=folder_path))
    project = projects.add_folder(project_id, folder_path)
    if not project:
        raise HTTPException(404, _("Project not found"))
    # 自动触发索引构建
    background_tasks.add_task(_do_scan_project, project_id)
    return project


@router.delete("/api/projects/{project_id}/folders")
def remove_project_folder(project_id: str, data: FolderAction, background_tasks: BackgroundTasks):
    """从项目移除文件夹（写 projects.json）"""
    project = projects.remove_folder(project_id, data.path)
    if not project:
        raise HTTPException(404, _("Project not found"))
    # 自动触发索引重建
    background_tasks.add_task(_do_scan_project, project_id)
    return project


@router.put("/api/projects/{project_id}/folders/sync")
def update_folder_sync_config(project_id: str, data: FolderSyncConfig):
    """更新文件夹的自动同步配置"""
    config = {}
    if data.enabled is not None:
        config["enabled"] = data.enabled
    if data.content_types is not None:
        config["content_types"] = data.content_types
    if data.subfolder_name is not None:
        config["subfolder_name"] = data.subfolder_name
    result = projects.update_folder_sync(project_id, data.path, config)
    if not result:
        raise HTTPException(404, _("Project or folder not found"))
    return result


@router.post("/api/projects/{project_id}/sync")
def trigger_project_sync(project_id: str):
    """手动触发同步：将项目中所有已完成的会议同步写入启用了同步的文件夹"""
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(404, _("Project not found"))

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
    """后台执行项目索引扫描（可复用）"""
    try:
        result = projects.scan_project(project_id)
        logger.info("项目索引构建完成: %s, %d 个文件", project_id, result.get("total_files", 0))
    except Exception as e:
        logger.error("项目索引构建失败: %s, %s", project_id, e)


@router.post("/api/projects/{project_id}/scan")
def scan_project(project_id: str, background_tasks: BackgroundTasks):
    """触发项目索引构建（后台执行）"""
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(404, _("Project not found"))
    background_tasks.add_task(_do_scan_project, project_id)
    return {"status": "scanning", "message": _("Index build started")}


@router.get("/api/projects/{project_id}/files")
def get_project_files(project_id: str):
    """获取项目索引中的文件列表（读索引 JSON）"""
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
    """在项目索引中搜索（读索引 JSON）"""
    results = projects.search_project(project_id, data.query, limit=data.limit)
    return {"results": results, "total": len(results)}
