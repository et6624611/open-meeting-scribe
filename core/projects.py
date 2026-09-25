"""
core/projects.py — 项目关联管理 / Project association management

职责 / Responsibilities:
  1. 项目 CRUD（关联本地文件夹） / Project CRUD (associate local folders)
  2. 文件夹同步配置与会议纪要写入 / Folder sync configuration and meeting summary writing

数据文件 / Data files:
  data/projects.json — 项目配置 / Project configuration

索引与检索已拆分至 core/project_index.py / Index and retrieval split to core/project_index.py
"""

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 数据路径 / Data paths
DATA_DIR = Path("data")
PROJECTS_FILE = DATA_DIR / "projects.json"
INDEX_DIR = DATA_DIR / "project_index"

# 同步写入的子目录默认名称（在关联文件夹下创建，集中存放自动纪要） / Default subfolder name for sync (created under associated folder for auto-summaries)
DEFAULT_SYNC_SUBFOLDER_NAME = "OpenMeetingScribe"


# ============================================================
# 项目 CRUD / Project CRUD
# ============================================================

def _load_projects() -> list[dict]:
    """从磁盘加载项目列表 / Load project list from disk"""
    if not PROJECTS_FILE.exists():
        return []
    try:
        with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载项目数据失败: {e}")
        return []


def _save_projects(projects: list[dict]) -> None:
    """保存项目列表到磁盘（原子写入） / Save project list to disk (atomic write)"""
    from core.fs_atomic import atomic_write_json
    atomic_write_json(PROJECTS_FILE, projects)


def list_projects() -> list[dict]:
    """获取所有项目（含索引摘要信息） / Get all projects (with index summary)"""
    projects = _load_projects()
    for p in projects:
        index = get_project_index(p["id"])
        if index:
            p["file_count"] = index.get("total_files", 0)
            p["indexed_at"] = index.get("indexed_at")
        else:
            p["file_count"] = 0
            p["indexed_at"] = None
    return projects


def get_project(project_id: str) -> dict | None:
    """获取单个项目 / Get single project"""
    for p in _load_projects():
        if p["id"] == project_id:
            return p
    return None


def create_project(name: str, folders: list[str] | None = None) -> dict:
    """创建项目 / Create project"""
    projects = _load_projects()
    project = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "folders": [
            {"path": f, "added_at": datetime.now().isoformat()}
            for f in (folders or [])
        ],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    projects.append(project)
    _save_projects(projects)
    logger.info(f"创建项目: {project['name']} ({project['id'][:8]})")
    return project


def update_project(project_id: str, name: str | None = None) -> dict | None:
    """更新项目基本信息 / Update project basic info"""
    projects = _load_projects()
    for p in projects:
        if p["id"] == project_id:
            if name is not None:
                p["name"] = name.strip()
            p["updated_at"] = datetime.now().isoformat()
            _save_projects(projects)
            return p
    return None


def delete_project(project_id: str) -> bool:
    """删除项目及其索引 / Delete project and its index"""
    projects = _load_projects()
    new_projects = [p for p in projects if p["id"] != project_id]
    if len(new_projects) == len(projects):
        return False
    _save_projects(new_projects)
    # 清理索引 / Clean up index
    index_file = INDEX_DIR / f"{project_id}.json"
    if index_file.exists():
        index_file.unlink()
    logger.info(f"删除项目: {project_id[:8]}")
    return True


def add_folder(project_id: str, folder_path: str) -> dict | None:
    """为项目添加文件夹 / Add folder to project"""
    projects = _load_projects()
    for p in projects:
        if p["id"] == project_id:
            existing = [f["path"] for f in p.get("folders", [])]
            if folder_path not in existing:
                p.setdefault("folders", []).append({
                    "path": folder_path,
                    "added_at": datetime.now().isoformat(),
                })
                p["updated_at"] = datetime.now().isoformat()
                _save_projects(projects)
            return p
    return None


def remove_folder(project_id: str, folder_path: str) -> dict | None:
    """从项目移除文件夹 / Remove folder from project"""
    projects = _load_projects()
    for p in projects:
        if p["id"] == project_id:
            p["folders"] = [
                f for f in p.get("folders", [])
                if f["path"] != folder_path
            ]
            p["updated_at"] = datetime.now().isoformat()
            _save_projects(projects)
            return p
    return None


# ============================================================
# 文件夹同步配置 / Folder sync configuration
# ============================================================

def update_folder_sync(project_id: str, folder_path: str, sync_config: dict) -> dict | None:
    """
    更新文件夹的同步配置 / Update folder sync configuration.

    sync_config 可包含 / sync_config may contain:
      - enabled: bool — 是否启用自动同步 / Whether to enable auto sync
      - content_types: list[str] — 要写入的内容类型 / Content types to write ("summary", "action_items")
      - subfolder_name: str — 自定义同步子目录名称（默认 / default "OpenMeetingScribe"）
    """
    projects = _load_projects()
    for p in projects:
        if p["id"] == project_id:
            for f in p.get("folders", []):
                if f["path"] == folder_path:
                    if "enabled" in sync_config:
                        f["sync_enabled"] = bool(sync_config["enabled"])
                    if "content_types" in sync_config:
                        valid_types = {"summary", "action_items"}
                        f["sync_content_types"] = [
                            t for t in sync_config["content_types"]
                            if t in valid_types
                        ]
                    if "subfolder_name" in sync_config:
                        raw = (sync_config["subfolder_name"] or "").strip()
                        cleaned = re.sub(r'[<>:"/\\|?*]', '_', raw)[:100]
                        f["sync_subfolder_name"] = cleaned if cleaned else DEFAULT_SYNC_SUBFOLDER_NAME
                    p["updated_at"] = datetime.now().isoformat()
                    _save_projects(projects)
                    return f
    return None


def get_sync_enabled_folders(project_id: str) -> list[dict]:
    """
    获取项目中启用了同步的文件夹列表 / Get list of folders with sync enabled in project.

    返回 / Returns [{"path": str, "content_types": list[str], "output_dir": str, "subfolder_name": str}, ...]
    output_dir 为实际写入纪要文件的子目录路径 / output_dir is the actual subfolder path for writing summaries.
    """
    project = get_project(project_id)
    if not project:
        return []
    result = []
    for f in project.get("folders", []):
        if f.get("sync_enabled"):
            subfolder_name = f.get("sync_subfolder_name") or DEFAULT_SYNC_SUBFOLDER_NAME
            output_dir = str(Path(f["path"]) / subfolder_name)
            result.append({
                "path": f["path"],
                "content_types": f.get("sync_content_types", ["summary", "action_items"]),
                "output_dir": output_dir,
                "subfolder_name": subfolder_name,
            })
    return result


def _build_sync_markdown(task: dict, content_types: list[str]) -> str:
    """
    根据会议任务数据和选中的内容类型，生成 Markdown 文件内容 / Generate Markdown file content from meeting task data and selected content types.

    包含 YAML frontmatter 元数据 + 选中的内容区块 / Includes YAML frontmatter metadata + selected content blocks.
    """
    task_id = task.get("task_id", "")
    title = task.get("title") or task.get("audio_name") or "未命名会议"
    meeting_date = task.get("meeting_date") or ""
    audio_duration = task.get("audio_duration")
    duration_minutes = round(audio_duration / 60) if audio_duration else None
    project_id = task.get("project_id", "")

    # 获取项目名称 / Get project name
    project_name = ""
    if project_id:
        project = get_project(project_id)
        if project:
            project_name = project.get("name", "")

    # 提取参与者（从 speaker_mapping 或 dialogue） / Extract participants (from speaker_mapping or dialogue)
    # BE-R3：占位名（含历史存量 Speaker N/说话人N）不入参与者，知识库 .md 成品不露编号名
    from core.speakers import is_unnamed_speaker
    participants = []
    speaker_map = task.get("speaker_mapping", {}) or {}
    for _spk_id, name in speaker_map.items():
        if name and not is_unnamed_speaker(name) and name not in participants:
            participants.append(name)
    if not participants:
        dialogue = task.get("dialogue", []) or []
        for seg in dialogue:
            spk = seg.get("speaker")
            if spk and not is_unnamed_speaker(spk) and spk not in participants:
                participants.append(spk)
            if len(participants) >= 10:
                break

    # 构建 YAML frontmatter / Build YAML frontmatter
    now_iso = datetime.now().isoformat()
    lines = [
        "---",
        'source: "Open Meeting Scribe"',
        'type: "auto_meeting_note"',
        f'meeting_id: "{task_id}"',
        f'title: "{title}"',
        f'date: "{meeting_date}"',
    ]
    if duration_minutes is not None:
        lines.append(f'duration_minutes: {duration_minutes}')
    if participants:
        lines.append('participants:')
        for name in participants:
            lines.append(f'  - "{name}"')
    if project_name:
        lines.append(f'project: "{project_name}"')
    lines.append(f'generated_at: "{now_iso}"')
    lines.append('generator: "Open Meeting Scribe v1"')

    # 声明包含的内容区块 / Declare included content blocks
    active_types = []
    if "summary" in content_types:
        active_types.append("summary")
    if "action_items" in content_types:
        active_types.append("action_items")
    lines.append('content_types:')
    for ct in active_types:
        lines.append(f'  - "{ct}"')
    lines.append("---")
    lines.append("")

    # 正文标题 / Body title
    lines.append(f"# {title}")
    lines.append("")

    # 会议纪要区块 / Summary section
    # 优先使用用户编辑版本，回退到 LLM 原始输出 / Prefer user-edited version, fallback to LLM original
    if "summary" in content_types:
        summary = task.get("user_summary") or task.get("summary", "")
        if summary:
            lines.append("## 会议纪要")
            lines.append("")
            lines.append(summary)
            lines.append("")

    # 待办事项区块（仅在未选择纪要时独立输出，避免与纪要正文中的待办重复） / Action items section (only standalone when summary not selected, to avoid duplication)
    if "action_items" in content_types and "summary" not in content_types:
        todos = task.get("todos", []) or []
        if todos:
            lines.append("## 待办事项")
            lines.append("")
            for todo in todos:
                text = todo.get("text", "")
                assignee = todo.get("assignee", "")
                done = todo.get("done", False)
                checkbox = "[x]" if done else "[ ]"
                if assignee:
                    lines.append(f"- {checkbox} **{assignee}**：{text}")
                else:
                    lines.append(f"- {checkbox} {text}")
            lines.append("")

    return "\n".join(lines)


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符 / Sanitize illegal characters from filename"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:200] if name else "未命名"


def sync_meeting_to_folders(task: dict) -> list[str]:
    """
    将会议纪要同步写入所有启用了同步的项目文件夹 / Sync meeting summary to all project folders with sync enabled.

    文件命名 / File naming: YYYY-MM-DD_会议标题_自动纪要.md / meeting title auto summary.md

    返回成功写入的文件路径列表 / Returns list of successfully written file paths.
    """
    project_id = task.get("project_id")
    if not project_id:
        return []

    sync_folders = get_sync_enabled_folders(project_id)
    if not sync_folders:
        return []

    title = task.get("title") or task.get("audio_name") or "未命名会议"
    meeting_date = task.get("meeting_date") or ""
    date_prefix = meeting_date if meeting_date else datetime.now().strftime("%Y-%m-%d")

    safe_title = _sanitize_filename(title)
    filename = f"{date_prefix}_{safe_title}_自动纪要.md"

    written = []
    for folder_info in sync_folders:
        folder_path = Path(folder_info["path"])
        if not folder_path.exists() or not folder_path.is_dir():
            logger.warning("同步目标文件夹不存在: %s", folder_path)
            continue

        # 在关联文件夹下创建同步子目录，集中存放自动纪要 / Create sync subfolder under associated folder for auto-summaries
        subfolder_name = folder_info.get("subfolder_name") or DEFAULT_SYNC_SUBFOLDER_NAME
        output_dir = folder_path / subfolder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        content_types = folder_info.get("content_types", ["summary", "action_items"])
        md_content = _build_sync_markdown(task, content_types)

        target_file = output_dir / filename
        try:
            target_file.write_text(md_content, encoding="utf-8")
            written.append(str(target_file))
            logger.info("会议纪要已同步: %s", target_file)
        except Exception as e:
            logger.error("写入同步文件失败 %s: %s", target_file, e)

    # 同步成功后更新 last_synced_at 并持久化 / Update last_synced_at after successful sync and persist
    if written:
        task["last_synced_at"] = datetime.now().isoformat()
        try:
            from app.task_store import save_task_to_disk
            save_task_to_disk(task.get("task_id", ""))
        except Exception as e:
            logger.warning("保存 last_synced_at 失败: %s", e)

    return written


# ============================================================
# Re-export（兼容现有 import 路径） / Re-export (backward-compatible import paths)
# ============================================================

from core.project_index import (  # noqa: E402,F401
    extract_text,
    get_project_context_for_chat,
    get_project_index,
    is_index_stale,
    scan_project,
    search_project,
)
