"""
app/routers/decisions.py — 决策 CRUD + 跨会议聚合 / Decision CRUD + cross-meeting aggregation

作者：Yongliang Wang
创建：2026-09-24
版本：1.0.0

职责（REQ-DECISION-CENTER R2）：
  1. 任务级决策 CRUD
  2. 跨任务决策聚合查询（决策中心数据源）

契约事实源：docs/API_CONTRACTS.md §12。
旧任务 JSON 无 decisions 字段一律按空数组读取（兼容性硬约束）。
DC-R2-b（D4/D5）：决策引入三要素 title / text(内容) / owner（执行人以说话人档案为权威）。
DC-R2-c（D6/D7）：status 从封闭枚举改为状态字典（core/decision_status）；
supersede/revoke 写回端点下线（项目方选择「只留完成为系统锚点，砍掉取代/撤销」），
存量 `superseded_by` 保留只读展示不再写入。
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.store import save_task_to_disk, tasks
from core.decision_status import StatusError, known_ids, load_statuses, validate_status_id
from core.i18n import _
from core.speakers import get_speaker_name_map, normalize_speaker_name

router = APIRouter(tags=["decisions"])


def _resolve_owner(owner_id: object, owner_name: object) -> tuple[str | None, str]:
    """执行人以说话人档案为权威（D4）：id 可解析则跟随档案名（改名全局生效）。

    档案不存在/被删时宽容回退写入库的快照名，不报 422——建档与提交之间的并发
    删除不应阻断补录。返回 (owner_id 或 None, owner_name 快照)。
    """
    oid = (owner_id or "").strip() if isinstance(owner_id, str) else ""
    snapshot = (owner_name or "").strip() if isinstance(owner_name, str) else ""
    if oid:
        try:
            archived = get_speaker_name_map().get(oid)
        except Exception:
            archived = None
        if archived:
            # 占位档案名（Speaker N 等）不当执行人（REQ-SPK-RN 口径同源）
            return oid, normalize_speaker_name(archived) or snapshot
    return (oid or None), snapshot


def _mark_modified(task_id: str) -> None:
    """标记任务内容已修改，用于知识库同步脏检测 / Mark task content as modified for KB sync dirty detection."""
    tasks[task_id]["last_modified_at"] = datetime.now().isoformat()


def _get_decisions(task: dict) -> list[dict]:
    """读取任务决策列表；缺字段/脏数据按空数组处理 / Missing or malformed field degrades to []."""
    decisions = task.get("decisions")
    return decisions if isinstance(decisions, list) else []


def _require_task(task_id: str) -> dict:
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    return task


def _require_decision(task: dict, decision_id: str) -> dict:
    for d in _get_decisions(task):
        if d.get("id") == decision_id:
            return d
    raise HTTPException(404, _("Decision not found"))


# ============================================================
# 任务级决策 CRUD / Task-scoped decision CRUD
# ============================================================

class DecisionCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    title: str = Field(default="", max_length=200)
    owner_id: str | None = Field(default=None, max_length=100)
    owner_name: str | None = Field(default=None, max_length=100)
    pending_confirmation: bool = False
    related_todo_ids: list[str] = Field(default_factory=list, max_length=100)


class DecisionUpdateRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=200)
    owner_id: str | None = Field(default=None, max_length=100)
    owner_name: str | None = Field(default=None, max_length=100)
    # DC-R2-c：状态不再是封闭枚举，合法性由状态字典校验（非法值 422）
    status: str | None = Field(default=None, max_length=32)
    pending_confirmation: bool | None = None
    related_todo_ids: list[str] | None = Field(default=None, max_length=100)


@router.get("/api/tasks/{task_id}/decisions")
def get_task_decisions(task_id: str):
    """获取任务的所有决策 / Get all decisions for a task."""
    task = _require_task(task_id)
    return {"decisions": _get_decisions(task)}


@router.post("/api/tasks/{task_id}/decisions")
def create_task_decision(task_id: str, req: DecisionCreateRequest):
    """手动补录一条决策 / Manually add a decision."""
    task = _require_task(task_id)
    text = req.text.strip()
    if not text:
        raise HTTPException(422, "text cannot be blank")
    now_iso = datetime.now().isoformat()
    owner_id, owner_name = _resolve_owner(req.owner_id, req.owner_name)
    decision = {
        "id": str(uuid.uuid4()),
        # 三要素（D4/D5）：title 可空（存量与 auto 决策都为空，展示侧降级），text = 内容
        "title": req.title.strip(),
        "text": text,
        "owner_id": owner_id,
        "owner_name": owner_name,
        "status": "active",
        "pending_confirmation": req.pending_confirmation,
        "source": "manual",
        "created_at": now_iso,
        "updated_at": now_iso,
        "superseded_by": None,
        "related_todo_ids": [s for s in req.related_todo_ids if s][:100],
    }
    task.setdefault("decisions", []).append(decision)
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"decision": decision}


@router.put("/api/tasks/{task_id}/decisions/{decision_id}")
def update_task_decision(task_id: str, decision_id: str, req: DecisionUpdateRequest):
    """编辑决策内容/状态 / Edit decision text/status."""
    task = _require_task(task_id)
    decision = _require_decision(task, decision_id)
    if req.text is not None:
        stripped = req.text.strip()
        if not stripped:
            raise HTTPException(422, "text cannot be blank")
        decision["text"] = stripped
    if req.title is not None:
        decision["title"] = req.title.strip()
    # 执行人：仅当请求显式携带 owner 字段时重写（空串 = 清空指派，区别于未传）
    if req.owner_id is not None or req.owner_name is not None:
        owner_id, owner_name = _resolve_owner(req.owner_id, req.owner_name)
        decision["owner_id"] = owner_id
        decision["owner_name"] = owner_name
    if req.status is not None:
        try:
            decision["status"] = validate_status_id(req.status)
        except StatusError as exc:
            raise HTTPException(422, str(exc))
    if req.pending_confirmation is not None:
        decision["pending_confirmation"] = req.pending_confirmation
    if req.related_todo_ids is not None:
        decision["related_todo_ids"] = [s for s in req.related_todo_ids if s][:100]
    decision["updated_at"] = datetime.now().isoformat()
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"decision": decision}


@router.delete("/api/tasks/{task_id}/decisions/{decision_id}")
def delete_task_decision(task_id: str, decision_id: str):
    """删除一条决策；被删的 auto 决策落 task 级墓碑，防重生成复活（DC-R2-BE）。"""
    task = _require_task(task_id)
    decision = _require_decision(task, decision_id)
    # 墓碑：仅 auto 需建（manual/injection/backfill 本就不被重生成覆盖）
    from core.summarize import build_decision_tombstone
    tombstone = build_decision_tombstone(decision)
    if tombstone is not None:
        deletions = task.get("decision_deletions")
        if not isinstance(deletions, list):
            deletions = []
        existing_keys = {t.get("text_key") for t in deletions if isinstance(t, dict)}
        if tombstone["text_key"] not in existing_keys:
            deletions.append(tombstone)
        task["decision_deletions"] = deletions
    task["decisions"] = [d for d in _get_decisions(task) if d.get("id") != decision_id]
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"ok": True}


# DC-R2-c（D6）：supersede 写回端点已下线（取代/撤销不再是系统行为）；
# 存量 superseded_by 仍随决策对象透出，由前端只读展示（见 §12.0）。


# ============================================================
# 跨任务聚合 / Cross-task aggregation
# ============================================================


def _kb_name(project_id: str | None, cache: dict) -> str | None:
    if not project_id:
        return None
    if project_id not in cache:
        try:
            from core.projects import get_project
            project = get_project(project_id)
            cache[project_id] = (project or {}).get("name")
        except Exception:
            cache[project_id] = None
    return cache[project_id]


def _validate_date(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, _("Invalid date format, expected YYYY-MM-DD"))
    return value


def _owner_display(decision: dict, name_map: dict[str, str]) -> str:
    """读侧执行人展示名：有档案 id 则取档案名（改名全局跟随），否则回退快照。"""
    oid = decision.get("owner_id")
    if isinstance(oid, str) and oid:
        archived = name_map.get(oid)
        if archived:
            return normalize_speaker_name(archived) or str(decision.get("owner_name") or "")
    snapshot = decision.get("owner_name")
    return str(snapshot) if isinstance(snapshot, str) else ""


@router.get("/api/decisions")
def list_all_decisions(
    since: str | None = Query(default=None, max_length=10),
    until: str | None = Query(default=None, max_length=10),
    kb_id: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=500),
    group_by: Literal["meeting", "date"] | None = Query(default=None),
):
    """跨会议决策聚合（决策中心数据源）/ Cross-meeting decision aggregation for the Decision Center.

    遍历内存任务表聚合（桌面单机数据量可承受，不引入数据库）。
    DC-R2-c：`status` 取值为状态字典 id（非封闭枚举）；每行附 status_name/color/closing 元信息。
    """
    since = _validate_date(since, "since")
    until = _validate_date(until, "until")
    if status is not None and status not in known_ids():
        raise HTTPException(422, f"unknown status: {status}")

    status_meta = {s["id"]: s for s in load_statuses()}
    kb_cache: dict[str, str | None] = {}
    try:
        owner_map = get_speaker_name_map()
    except Exception:
        owner_map = {}
    rows: list[dict] = []
    for task_id, task in tasks.items():
        meeting_date = task.get("meeting_date")
        if since or until:
            # 日期过滤下无 meeting_date 的任务被排除 / Tasks without meeting_date are excluded when date filters apply
            if not meeting_date:
                continue
            if since and meeting_date < since:
                continue
            if until and meeting_date > until:
                continue
        project_id = task.get("project_id") or None
        if kb_id and project_id != kb_id:
            continue
        for d in _get_decisions(task):
            if status and d.get("status") != status:
                continue
            if q is not None and q not in f"{d.get('text') or ''}\n{d.get('title') or ''}":
                continue
            sid = str(d.get("status") or "active")
            meta = status_meta.get(sid)
            rows.append({
                **d,
                # 决策自身标题（三要素，存量无此键→""）；会议标题改用 meeting_title 下发（旧 `title` 语义冲突修正）
                "title": d.get("title") or "",
                "owner_id": d.get("owner_id") or None,
                "owner_name": _owner_display(d, owner_map),
                # DC-R2-c：状态字典元信息随行下发，前端不再写死枚举（徽标/颜色/沉底均配置驱动）
                "status_name": (meta or {}).get("name") or sid,
                "status_name_en": (meta or {}).get("name_en") or sid,
                "status_color": (meta or {}).get("color") or "var(--muted)",
                "status_closing": bool((meta or {}).get("closing", sid != "active")),
                "task_id": task_id,
                "meeting_title": task.get("title") or task.get("audio_name") or task_id,
                "meeting_date": meeting_date,
                "kb_id": project_id,
                "kb_name": _kb_name(project_id, kb_cache),
            })

    # meeting_date 倒序，无日期沉底；同组内按创建时间倒序 / Newest meeting first, undated sink to the end
    rows.sort(key=lambda r: (r.get("meeting_date") or "", r.get("created_at") or ""), reverse=True)

    if not group_by:
        return {"decisions": rows, "total": len(rows)}

    groups: dict[str, dict] = {}
    for row in rows:
        if group_by == "meeting":
            key = row["task_id"]
            label = row.get("meeting_title")
            meta = {"task_id": key, "meeting_date": row.get("meeting_date")}
        else:  # date
            key = row.get("meeting_date") or ""
            label = key or None
            meta = {"task_id": None, "meeting_date": key or None}
        group = groups.get(key)
        if group is None:
            group = {"key": key, "label": label, **meta, "decisions": []}
            groups[key] = group
        group["decisions"].append(row)

    return {"groups": list(groups.values()), "total": len(rows)}
