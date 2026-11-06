"""
core/cli_engine/context_paths.py — 工作区路径与目录命名（从 context_export.py 拆出）
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# 模块级常量 / Module-level constants
_SLUG_MAX_CHARS = 24
_SHORT_KEY_CHARS = 8
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *[f"COM{i}" for i in range(1, 10)],
    *[f"LPT{i}" for i in range(1, 10)],
}
_MEDIA_EXT_RE = re.compile(
    r"\.(mp3|wav|m4a|aac|flac|ogg|opus|webm|wma|mp4|mov|mkv)$", re.IGNORECASE)
_MAX_TRANSCRIPT_CHARS = 40000
_MAX_SUMMARY_CHARS = 8000
_MAX_NOTES_CHARS = 8000      # 随记（用户手写原文）
_MAX_HISTORY_CHARS = 6000       # 对话历史整块字符上限
_MAX_HISTORY_TURNS = 10         # 最多保留前 N 轮对话
INSIGHTS_TASKS_DIR = Path("data/tasks")
_OMS_DIR = ".oms"
_IDE_RULE_FILES = {
    "cursor": ".cursor/rules/meeting-context.mdc",
    "vscode": ".github/copilot-instructions.md",
    "windsurf": ".windsurf/rules/meeting-context.md",
    "trae": ".trae/rules/meeting-context.md",
    "trae-cn": ".trae/rules/meeting-context.md",
    "claude-code": "CLAUDE.md",
}
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _ce():
    """聚合层自引用，使 monkeypatch.setattr(ce, 'X', ...) 穿透到子模块。"""
    import core.cli_engine.context_export as ce
    return ce


def _compute_workspace_root() -> Path:
    """计算工作区根目录，优先用 app.store.BASE_DIR（打包后落 exe 同级，持久），
    回退仓库根（开发模式等价）。PyInstaller _MEIPASS 临时目录重启丢失，必须避开。"""
    try:
        from app.store import BASE_DIR
        return BASE_DIR / "agent-workspace"
    except Exception:
        return Path(__file__).resolve().parents[2] / "agent-workspace"


WORKSPACE_ROOT = _compute_workspace_root()
PREVIEW_ROOT = WORKSPACE_ROOT / "_preview"


def _short_key(value: str | None) -> str:
    """取稳定短键：清洗后的前 8 位，用于目录后缀反查。"""
    raw = re.sub(r"[^0-9A-Za-z]", "", str(value or ""))
    return (raw[:_SHORT_KEY_CHARS] or "00000000").lower()


def _sanitize_segment(text: str, fallback: str, max_len: int = _SLUG_MAX_CHARS) -> str:
    """目录段清洗：去非法字符（含全角冒号，规避同步工具兼容问题）、压空白、处理 Windows 保留名与长度。"""
    s = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|：]+', "_", str(text or "").strip())
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("._")
    if not s:
        return fallback
    if s.split(".")[0].upper() in _WIN_RESERVED:
        s = "_" + s
    s = s[:max_len].rstrip("._")
    return s or fallback


def _meeting_date_slug(task: dict | None) -> str:
    """会议日期段：优先 meeting_date，回退 created_at，缺失时用「未定日期」。"""
    for key in ("meeting_date", "created_at"):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str((task or {}).get(key) or ""))
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return "未定日期"


def _meeting_dir_name(task: dict | None, task_id: str) -> str:
    """会议目录名：日期_标题__短ID。标题缺失用录音文件名兜底（剥扩展名）。"""
    title = (task or {}).get("title")
    if not title:
        title = _MEDIA_EXT_RE.sub("", str((task or {}).get("audio_name") or "").strip())
    return (f"{_meeting_date_slug(task)}_"
            f"{_sanitize_segment(title or '', '未命名会议')}__{_short_key(task_id)}")


def _project_display_name(project_id: str | None) -> str:
    """项目显示名：读知识库名称，缺失时用「知识库」。"""
    if not project_id:
        return "独立会议"
    try:
        from core import projects as projects_store
        project = projects_store.get_project(project_id)
        if project and project.get("name"):
            return str(project["name"])
    except Exception:  # noqa: BLE001 - 名称读取失败不阻断导出
        pass
    return "知识库"


def _find_meeting_dir(proj_dir: Path, task_id: str) -> Path | None:
    """按短键后缀查找会议目录；兼容旧版直接以 task_id 命名的目录。"""
    suffix = f"__{_short_key(task_id)}"
    if proj_dir.is_dir():
        for entry in sorted(proj_dir.iterdir()):
            if entry.is_dir() and entry.name.endswith(suffix):
                return entry
        legacy = proj_dir / task_id
        if legacy.is_dir():
            return legacy
    return None


def _project_dir_name(project_id: str) -> str:
    """项目目录名：<项目名>__<短ID>（project_preview_dir 与孤儿反查共用，避免两处拼名漂移）。"""
    return (f"{_sanitize_segment(_ce()._project_display_name(project_id), '知识库')}"
            f"__{_short_key(project_id)}")


def project_preview_dir(project_id: str | None) -> Path:
    """项目级工作区根：<项目名>__<短ID>；独立会议归入 _standalone。
    旧版 <project_id> 目录首次访问时惰性迁移。"""
    _ce().PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    if not project_id or project_id == "_standalone":
        root = _ce().PREVIEW_ROOT / "_standalone"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    target = _ce().PREVIEW_ROOT / _project_dir_name(project_id)
    legacy = _ce().PREVIEW_ROOT / project_id
    if legacy.is_dir():
        if not target.exists():
            try:
                legacy.rename(target)
            except OSError as e:  # noqa: BLE001 - 迁移失败保留旧目录，功能不中断
                logger.warning("[CLI引擎] 项目目录迁移失败 %s → %s: %s", legacy, target, e)
                return legacy.resolve()
        else:
            # 双目录并存：把旧目录里缺失的子项并入新目录后清理
            _merge_dir_into(legacy, target)
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _merge_dir_into(src: Path, dst: Path) -> None:
    """同任务双目录并存收口：把 src 里 dst 缺失的子项并过去，再删掉 src。
    同名子目录递归并入；只搬缺失项，绝不覆盖——用户在任一侧的改动都保留。"""
    if not src.is_dir() or not dst.is_dir():
        return
    for child in src.iterdir():
        dest = dst / child.name
        if child.is_dir() and dest.is_dir():
            _merge_dir_into(child, dest)
            continue
        if dest.exists():
            continue
        try:
            child.rename(dest)
        except OSError:
            pass
    try:
        src.rmdir()  # 只删得空的目录，搬不动的东西留下不动
    except OSError as e:  # noqa: BLE001
        logger.warning("[CLI引擎] 目录合并残留 %s → %s: %s", src, dst, e)


def workspace_dir(engine_id: str, task_id: str | None) -> Path:
    """返回并确保工作区目录存在；task_id 缺省用 general 命名空间。"""
    tid = task_id or "general"
    ws = (_ce().WORKSPACE_ROOT / engine_id / tid).resolve()
    (ws / "context").mkdir(parents=True, exist_ok=True)
    (ws / "output").mkdir(parents=True, exist_ok=True)
    return ws


def cleanup_workspace(engine_id: str, task_id: str | None) -> None:
    """删除指定工作区（面板会话删除时联动清理，方案 D5 修订要求）。"""
    tid = task_id or "general"
    ws = (_ce().WORKSPACE_ROOT / engine_id / tid).resolve()
    if ws.is_dir() and _ce().WORKSPACE_ROOT in ws.parents:
        shutil.rmtree(ws, ignore_errors=True)
        logger.info("[CLI引擎] 工作区已清理 %s", ws)


def sweep_expired_workspaces(retention_days: int) -> int:
    """
    按修改时间清理过期任务工作区（方案 R7/§3.10：workspace 用后可清）。

    retention_days <= 0 视为“不自动清理”，返回 0。返回删除的任务工作区目录数。
    仅删除 _ce().WORKSPACE_ROOT 之下两层（<engine_id>/<task_id>）的目录，避免误删。
    """
    import time
    if retention_days is None or retention_days <= 0:
        return 0
    cutoff = time.time() - retention_days * 86400
    removed = 0
    if not _ce().WORKSPACE_ROOT.is_dir():
        return 0
    for engine_dir in _ce().WORKSPACE_ROOT.iterdir():
        if not engine_dir.is_dir():
            continue
        for task_dir in engine_dir.iterdir():
            if not task_dir.is_dir():
                continue
            try:
                if task_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(task_dir, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    if removed:
        logger.info("[CLI引擎] 过期工作区清理 %d 个（保留 %d 天）", removed, retention_days)
    return removed


def preview_workspace_dir(task_id: str, project_id: str | None = None,
                          task: dict | None = None) -> Path:
    """返回 _preview 下的会议工作区路径：
    有 project_id → _preview/<项目名>__<短ID>/<日期>_<标题>__<短ID>/
    无 project_id → _preview/_standalone/<日期>_<标题>__<短ID>/
    旧版 UUID 目录在传入 task 时惰性改名；确保 context/ 与 output/ 存在。"""
    proj_dir = project_preview_dir(project_id)
    target_name = _meeting_dir_name(task, task_id) if task else None
    existing = _find_meeting_dir(proj_dir, task_id)

    # 标题/日期变化时跟随改名；旧版 <task_id> 目录也在这一步迁移
    if existing is not None and target_name and existing.name != target_name:
        target = proj_dir / target_name
        if not target.exists():
            try:
                existing.rename(target)
                existing = target
            except OSError as e:  # noqa: BLE001 - 改名失败沿用旧目录，功能不中断
                logger.warning("[CLI引擎] 会议目录改名失败 %s → %s: %s", existing, target, e)

    ws = existing or (proj_dir / (target_name or task_id))
    (ws / "context").mkdir(parents=True, exist_ok=True)
    (ws / "output").mkdir(parents=True, exist_ok=True)
    return ws.resolve()
