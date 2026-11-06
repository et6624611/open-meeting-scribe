"""
core/cli_engine/context_index.py — 会议索引与跨会议台账（从 context_export.py 拆出）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from core.speakers import normalize_speaker_name

logger = logging.getLogger(__name__)

from .context_paths import (
    _OMS_DIR,
    _UUID_RE,
    _find_meeting_dir,
    _meeting_dir_name,
    _merge_dir_into,
    _project_dir_name,
    _short_key,
    project_preview_dir,
)
from .context_render import _now_iso, _summary_line, _write_md_with_meta


def _ce():
    import core.cli_engine.context_export as ce
    return ce


def _meetings_index_path(proj_dir: Path) -> Path:
    return proj_dir / _OMS_DIR / "meetings.json"


def _global_index_path() -> Path:
    return _ce().PREVIEW_ROOT / _OMS_DIR / "index.json"


def read_meetings_index(proj_dir: Path) -> dict:
    """读项目会议索引：优先 .oms/meetings.json，兼容旧 _meetings.json。"""
    for path in (_meetings_index_path(proj_dir), proj_dir / "_meetings.json"):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    return {}


def write_meetings_index(proj_dir: Path, data: dict) -> None:
    path = _meetings_index_path(proj_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    legacy = proj_dir / "_meetings.json"
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass


def read_global_index() -> dict:
    """读全局索引：优先 .oms/index.json，兼容旧 _index.json。"""
    for path in (_global_index_path(), _ce().PREVIEW_ROOT / "_index.json"):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    return {}


def _write_global_index(data: dict) -> None:
    path = _global_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    legacy = _ce().PREVIEW_ROOT / "_index.json"
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass


def _slim_meetings(meetings: list[dict]) -> list[dict]:
    """机器索引的会议级瘦身条目：够反查定位即可，不带正文类数据。"""
    return [{"task_id": m.get("task_id"), "title": m.get("title"),
             "meeting_date": m.get("meeting_date"),
             "workspace_path": m.get("workspace_path"),
             "has_summary": m.get("has_summary")} for m in meetings]


def _rebuild_global_index() -> None:
    """重建全局索引：从各项目会议索引反查 project_id，不再依赖目录名。
    含会议级条目——单场会议 AGENTS.md 让 agent 查它当全局索引，查不到就是废索引。"""
    _ce().PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    projects: list[dict] = []
    standalone_meetings: list[dict] = []
    try:
        for entry in sorted(_ce().PREVIEW_ROOT.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.name == "_standalone":
                # 按索引计数：目录数会把 未识别会议 归档目录也算进去
                standalone_meetings = _slim_meetings(
                    read_meetings_index(entry).get("meetings", []))
                continue
            if entry.name.startswith("_"):
                continue
            mi = read_meetings_index(entry)
            if not mi:
                continue
            pid = mi.get("project_id") or ""
            if not _UUID_RE.match(pid):
                continue  # 归属非法（如被误标 _standalone）不入全局列表
            projects.append({
                "project_id": pid,
                "project_name": mi.get("project_name") or _ce()._project_display_name(pid),
                "meeting_count": len(mi.get("meetings", [])),
                "meetings": _slim_meetings(mi.get("meetings", [])),
                "path": entry.name,
                "last_updated": _now_iso(),
            })
    except Exception:  # noqa: BLE001
        pass
    _write_global_index({
        "version": 1,
        "generated_at": _now_iso(),
        "projects": projects,
        "standalone_count": len(standalone_meetings),
        "standalone_meetings": standalone_meetings,
    })


def update_workspace_index(task_id: str, project_id: str | None, task: dict,
                           workspace_name: str | None = None) -> None:
    """增量更新项目级 .oms/meetings.json，并重建全局 .oms/index.json。"""
    proj_dir = project_preview_dir(project_id)
    index: dict = read_meetings_index(proj_dir)
    if not index:
        index = {"project_id": project_id or "_standalone",
                 "project_name": _ce()._project_display_name(project_id),
                 "version": 1, "generated_at": _now_iso(), "meetings": []}
    index["project_id"] = project_id or "_standalone"
    index["project_name"] = _ce()._project_display_name(project_id)

    ws = (proj_dir / workspace_name) if workspace_name else _find_meeting_dir(proj_dir, task_id)
    ctx_dir = (ws / "context") if ws else (proj_dir / task_id / "context")
    meetings = [m for m in index.get("meetings", []) if m.get("task_id") != task_id]
    meetings.append({
        "task_id": task_id,
        "title": task.get("title") or task.get("audio_name") or "未命名",
        "meeting_date": task.get("meeting_date") or "",
        "workspace_path": f"{ws.name}/" if ws else f"{task_id}/",
        "has_transcript": (ctx_dir / "transcript.md").exists(),
        "has_summary": (ctx_dir / "summary.md").exists(),
        "has_notes": (ctx_dir / "notes.md").exists(),
        "has_insights": (ctx_dir / "insights.md").exists(),
        "decision_count": len(task.get("decisions") or []),
        "speaker_count": _speaker_count(task),
        "last_updated": _now_iso(),
    })
    index["meetings"] = meetings
    index["generated_at"] = _now_iso()
    write_meetings_index(proj_dir, index)
    _rebuild_global_index()


def _project_members(project_id: str) -> list[dict]:
    """按日期倒序取项目内会议（任务库为空时先从磁盘加载）。"""
    _ce()._ensure_tasks_loaded()
    from app.store import tasks
    members = [t for t in tasks.values()
               if t.get("project_id") == project_id and t.get("task_id")]
    members.sort(key=lambda t: (t.get("meeting_date") or t.get("created_at") or ""), reverse=True)
    return members


def _decision_rows(members: list[dict], names: dict,
                   project_label: str | None = None) -> list[str]:
    """决策行生成；project_label 提供时输出全局六列（项目 | 日期 | 会议 | 节点 | 状态 | 负责人），
    否则五列（无项目列，供单作用域台账用）。"""
    from core.decision_flow import status_of
    out: list[str] = []
    for task in members:
        date = (task.get("meeting_date") or task.get("created_at") or "")[:10]
        title = (task.get("title") or task.get("audio_name") or "未命名").replace("|", "/")
        for decision in (task.get("decisions") or []):
            if not isinstance(decision, dict):
                continue
            text = (decision.get("title") or decision.get("text") or "").replace("|", "/").strip()
            if not text:
                continue
            sid = status_of(decision)
            state = names.get(sid, sid)
            assignee = (decision.get("assignee") or "未分配").replace("|", "/")
            if project_label:
                out.append(f"| {project_label} | {date} | {title} | {text} | {state} | {assignee} |")
            else:
                out.append(f"| {date} | {title} | {text} | {state} | {assignee} |")
    return out


def _decision_lines(members: list[dict]) -> list[str]:
    """跨会议决策台账：会议 / 节点 / 状态 / 负责人。"""
    from core.decision_status import load_statuses
    try:
        names = {s["id"]: s.get("name") or s["id"] for s in load_statuses()}
    except Exception:  # noqa: BLE001
        names = {}
    return (["| 日期 | 会议 | 决策 | 状态 | 负责人 |", "| --- | --- | --- | --- | --- |"]
            + _decision_rows(members, names))


def _write_global_decisions(projects_idx: list[dict], standalone_members: list[dict],
                            written: list[str]) -> None:
    """根级决策台账：聚合全部项目与独立会议（六列带项目归属）。
    根级规则文案「决策与决策见 _DECISIONS.md」必须有真实落点，不能悬空。"""
    from core.decision_status import load_statuses
    try:
        names = {s["id"]: s.get("name") or s["id"] for s in load_statuses()}
    except Exception:  # noqa: BLE001
        names = {}
    rows = ["| 项目 | 日期 | 会议 | 决策 | 状态 | 负责人 |",
            "| --- | --- | --- | --- | --- | --- |"]
    for item in projects_idx:
        pid = item["index"].get("project_id")
        if not pid or not _UUID_RE.match(pid):
            continue
        label = item["index"].get("project_name") or _ce()._project_display_name(pid)
        rows.extend(_decision_rows(_project_members(pid), names, label))
    if standalone_members:
        rows.extend(_decision_rows(standalone_members, names, "独立会议"))
    body = ("# 跨项目决策台账\n\n"
            "> 聚合全部知识库项目与独立会议的决策节点；项目内明细见各项目目录 `_DECISIONS.md`。\n\n"
            + "\n".join(rows) + "\n")
    _write_md_with_meta(_ce().PREVIEW_ROOT, "_DECISIONS.md",
                        {"generated_at": _now_iso(), "source": "decisions"},
                        body)
    written.append("_DECISIONS.md")


def _ensure_tasks_loaded() -> None:
    """任务库为空时从磁盘加载一次。索引/迁移以任务库为全量基准，
    服务进程启动时已加载，CLI/测试进程按需补载。"""
    from app.store import tasks as task_store
    if task_store:
        return
    try:
        from app.task_store import load_tasks_from_disk
        load_tasks_from_disk()
    except Exception as e:  # noqa: BLE001 - 加载失败按空库处理，不阻断导出
        logger.warning("[CLI引擎] 任务库加载失败: %s", e)


def _store_members(project_id: str | None) -> dict[str, dict]:
    """某范围（项目/独立会议）的全量任务，task_id → task。"""
    from app.store import tasks as task_store
    _ce()._ensure_tasks_loaded()
    if project_id:
        items = [t for t in task_store.values()
                 if t.get("project_id") == project_id and t.get("task_id")]
    else:
        items = [t for t in task_store.values()
                 if not t.get("project_id") and t.get("task_id")]
    return {t["task_id"]: t for t in items}


def _migrate_meeting_dirs(proj_dir: Path, project_id: str | None = None) -> None:
    """把遗留 <task_id> 目录批量改成可读名，并按任务库重建完整索引。
    此前索引只记录导出过的会议，历史会议既不被改名也不计数——这里以任务库为准全量对齐。
    不在任务库中的 UUID 目录视为孤儿，归档为 未识别会议__<短ID>。"""
    by_id = _store_members(project_id)

    # 1) 磁盘遗留 UUID 目录 → 可读名 / 孤儿归档
    if proj_dir.is_dir():
        for entry in sorted(proj_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            if not _UUID_RE.match(entry.name):
                continue
            task = by_id.get(entry.name)
            if task is not None:
                target = proj_dir / _meeting_dir_name(task, entry.name)
            else:
                # 与本范围对不上：旧版可能把项目会议错放进独立区，搬回所属项目；
                # 彻底无主才归档为 未识别会议__<短ID>
                from app.store import tasks as task_store
                owner = task_store.get(entry.name)
                if owner and owner.get("project_id"):
                    target = (project_preview_dir(owner["project_id"])
                              / _meeting_dir_name(owner, entry.name))
                else:
                    target = proj_dir / f"未识别会议__{entry.name[:8].lower()}"
            if target.exists():
                # 同任务已有正式工作区：旧目录是残留副本，缺失子项并入后清掉，防 ID 撞车脏副本
                _merge_dir_into(entry, target)
                continue
            try:
                entry.rename(target)
            except OSError as e:  # noqa: BLE001 - 单目录失败不阻断整体迁移
                logger.warning("[CLI引擎] 历史目录迁移失败 %s: %s", entry.name, e)

        # 1.5) 撞车归档清理：未识别会议__<key> 的 key 已命中任务库且真实工作区存在
        # → 当年是误归档的脏副本，缺失子项并入真实工作区后收掉（评估 2026-10-26 P0-4）
        from app.store import tasks as task_store
        by_key: dict[str, dict] = {}
        for tid, t in task_store.items():
            by_key.setdefault(_short_key(tid), t)
        for entry in sorted(proj_dir.iterdir()):
            if not entry.is_dir() or not entry.name.startswith("未识别会议__"):
                continue
            owner = by_key.get(entry.name.split("__", 1)[1])
            if owner is None:
                continue  # 真无主，保留归档待人工辨认
            pid = owner.get("project_id")
            pd = (_ce().PREVIEW_ROOT / _project_dir_name(pid) if pid and _UUID_RE.match(str(pid))
                  else _ce().PREVIEW_ROOT / "_standalone")
            real = (_find_meeting_dir(pd, owner["task_id"])
                    if pd.is_dir() else None)
            if real is not None:
                _merge_dir_into(entry, real)
                logger.info("[CLI引擎] 撞车归档已并入真实工作区 %s → %s", entry.name, real.name)

    # 2) 以任务库为准重建索引（历史会议只有导出过才入索引，是数量偏少的根因）
    old = {m.get("task_id"): m
           for m in read_meetings_index(proj_dir).get("meetings", [])}
    meetings = []
    for tid, task in by_id.items():
        ws = _find_meeting_dir(proj_dir, tid)
        ctx = (ws / "context") if ws else None
        meetings.append({
            "task_id": tid,
            "title": task.get("title") or task.get("audio_name") or "未命名",
            "meeting_date": task.get("meeting_date") or task.get("created_at") or "",
            "workspace_path": f"{ws.name}/" if ws else "",
            "has_transcript": bool(ctx and (ctx / "transcript.md").exists()),
            "has_summary": bool(ctx and (ctx / "summary.md").exists()),
            "has_notes": bool(ctx and (ctx / "notes.md").exists()),
            "has_insights": bool(ctx and (ctx / "insights.md").exists()),
            "decision_count": len(task.get("decisions") or []),
            "speaker_count": _speaker_count(task),
            "last_updated": old.get(tid, {}).get("last_updated") or _now_iso(),
        })
    meetings.sort(key=lambda m: m.get("meeting_date") or "", reverse=True)
    proj_id = project_id or "_standalone"
    write_meetings_index(proj_dir, {
        "project_id": proj_id,
        "project_name": "独立会议" if proj_id == "_standalone" else _ce()._project_display_name(proj_id),
        "version": 1,
        "generated_at": _now_iso(),
        "meetings": meetings,
    })


def _infer_project_id_from_dir(proj_dir: Path) -> str | None:
    """按目录内会议反查归属项目（索引 project_id 被污染时的自愈路径）。"""
    from app.store import tasks as task_store
    owners: set[str] = set()
    for m in read_meetings_index(proj_dir).get("meetings", []):
        t = task_store.get(m.get("task_id") or "")
        pid = (t or {}).get("project_id")
        if pid and _UUID_RE.match(pid):
            owners.add(pid)
    return owners.pop() if len(owners) == 1 else None


def _speaker_count(task: dict | None) -> int:
    """发言人数：dialogue 内实名去重（空名不计）。
    任务库 task.speaker_count 是导入时的对话条数，口径不对，索引一律现算。"""
    names = (normalize_speaker_name(d.get("speaker_name"))
             for d in (task or {}).get("dialogue") or [])
    return len({n for n in names if n})


def _sweep_junk_files() -> None:
    """清扫 Finder/同步工具留下的噪声文件（.DS_Store 等），保持工作区纯净。"""
    if not _ce().PREVIEW_ROOT.is_dir():
        return
    for path in _ce().PREVIEW_ROOT.rglob(".DS_Store"):
        try:
            path.unlink()
        except OSError:
            pass


def _migrate_all_dirs() -> None:
    """打开全部会议前批量迁移：所有项目与独立会议的旧目录一次性改名。
    目录归属只认任务库与合法 project_id，绝不给非独立目录盖 standalone 章——
    项目目录缺索引时若误标，会把独立会议灌进项目索引并连锁清空独立区。"""
    _ce()._ensure_tasks_loaded()
    _sweep_junk_files()
    if not _ce().PREVIEW_ROOT.is_dir():
        return
    for entry in sorted(_ce().PREVIEW_ROOT.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name == "_standalone":
            _migrate_meeting_dirs(entry, None)
            continue
        if entry.name.startswith("_"):
            continue
        pid = read_meetings_index(entry).get("project_id")
        if pid and not _UUID_RE.match(pid):
            pid = _infer_project_id_from_dir(entry)  # 被污染的归属，反查自愈
        if not pid and _UUID_RE.match(entry.name):
            pid = entry.name  # 旧版项目目录以 task_id 命名
        if not pid:
            pid = _infer_project_id_from_dir(entry)
        if not pid:
            logger.warning("[CLI引擎] 跳过无法识别归属的目录 %s", entry.name)
            continue
        _migrate_meeting_dirs(project_preview_dir(pid), pid)


def _write_scope_indexes(scope_dir: Path, scope_id: str, scope_name: str,
                         members: list[dict], written: list[str],
                         archive_note: bool = False) -> None:
    """写作用域级 `_INDEX.md`（会议清单）与 `_DECISIONS.md`（跨会议决策台账）。
    项目级与独立会议区共用——「决策与决策见 _DECISIONS.md」的指引必须在每个作用域有落点。"""
    rows = ["| 日期 | 会议 | 一句话结论 | 决策 | 目录 |", "| --- | --- | --- | --- | --- |"]
    for task in members:
        ws = _find_meeting_dir(scope_dir, task["task_id"])
        if not ws:
            continue
        date = (task.get("meeting_date") or task.get("created_at") or "")[:10]
        title = (task.get("title") or task.get("audio_name") or "未命名").replace("|", "/")
        has_summary = (ws / "context" / "summary.md").exists()
        summary = _summary_line(task).replace("|", "/")
        decision_count = len(task.get("decisions") or [])
        rows.append(f"| {date} | {title} | {summary or ('—' if has_summary else '（无纪要）')} "
                    f"| {decision_count} | `{ws.name}/` |")
    index_body = (f"# 会议索引：{scope_name}\n\n> 共 {len(members)} 场，按日期倒序。"
                  "先在这里定位，再进入目录读 context/。\n\n" + "\n".join(rows) + "\n")
    if archive_note:
        index_body += ("\n> 注：磁盘上的 `未识别会议__*` 目录是无主遗留归档，不属于任务库，"
                       "不列入本索引。\n")
    _write_md_with_meta(scope_dir, "_INDEX.md",
                        {"project_id": scope_id, "project_name": scope_name,
                         "generated_at": _now_iso(), "source": "index",
                         "meeting_count": len(members)}, index_body)
    written.append("_INDEX.md")

    decision_body = (f"# 跨会议决策台账：{scope_name}\n\n"
                     "> 只列本范围内会议产生的决策节点，状态取软件内决策字典。\n\n"
                     + "\n".join(_decision_lines(members)) + "\n")
    _write_md_with_meta(scope_dir, "_DECISIONS.md",
                        {"project_id": scope_id, "generated_at": _now_iso(), "source": "decisions"},
                        decision_body)
    written.append("_DECISIONS.md")
