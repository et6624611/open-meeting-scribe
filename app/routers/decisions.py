"""
app/routers/decisions.py — 决策 CRUD + 跨会议聚合 / Decision CRUD + cross-meeting aggregation

作者：Yongliang Wang
创建：2026-09-24
版本：1.0.0

职责（REQ-DECISION-CENTER R2）：
  1. 任务级决策 CRUD 与 supersede 标记
  2. 跨任务决策聚合查询（决策中心数据源）

契约事实源：docs/API_CONTRACTS.md §12。
旧任务 JSON 无 decisions 字段一律按空数组读取（兼容性硬约束）。
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.store import save_task_to_disk, tasks
from core.i18n import _

router = APIRouter(tags=["decisions"])

# 决策生效状态 / Decision effect status
DecisionStatus = Literal["active", "superseded", "revoked"]


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
    pending_confirmation: bool = False
    related_todo_ids: list[str] = Field(default_factory=list, max_length=100)


class DecisionUpdateRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    status: DecisionStatus | None = None
    pending_confirmation: bool | None = None
    related_todo_ids: list[str] | None = Field(default=None, max_length=100)


class SupersedeRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=100)
    decision_id: str = Field(..., min_length=1, max_length=100)


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
    decision = {
        "id": str(uuid.uuid4()),
        "text": text,
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
    if req.status is not None:
        decision["status"] = req.status
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


@router.patch("/api/tasks/{task_id}/decisions/{decision_id}/supersede")
def supersede_task_decision(task_id: str, decision_id: str, req: SupersedeRequest):
    """标记决策已被取代 / Mark a decision as superseded by another (cross-meeting)."""
    task = _require_task(task_id)
    decision = _require_decision(task, decision_id)
    if req.task_id == task_id and req.decision_id == decision_id:
        raise HTTPException(400, _("A decision cannot supersede itself"))
    ref_task = tasks.get(req.task_id)
    if ref_task is None:
        raise HTTPException(404, _("Task not found"))
    ref_found = any(
        d.get("id") == req.decision_id for d in _get_decisions(ref_task)
    )
    if not ref_found:
        raise HTTPException(404, _("Decision not found"))
    decision["status"] = "superseded"
    decision["superseded_by"] = {"task_id": req.task_id, "decision_id": req.decision_id}
    decision["updated_at"] = datetime.now().isoformat()
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"decision": decision}


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


@router.get("/api/decisions")
def list_all_decisions(
    since: str | None = Query(default=None, max_length=10),
    until: str | None = Query(default=None, max_length=10),
    kb_id: str | None = Query(default=None, max_length=100),
    status: DecisionStatus | None = Query(default=None),
    q: str | None = Query(default=None, max_length=500),
    group_by: Literal["meeting", "date"] | None = Query(default=None),
):
    """跨会议决策聚合（决策中心数据源）/ Cross-meeting decision aggregation for the Decision Center.

    遍历内存任务表聚合（桌面单机数据量可承受，不引入数据库）。
    """
    since = _validate_date(since, "since")
    until = _validate_date(until, "until")

    kb_cache: dict[str, str | None] = {}
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
            if q is not None and q not in (d.get("text") or ""):
                continue
            rows.append({
                **d,
                "task_id": task_id,
                "title": task.get("title"),
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
            label = row.get("title")
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
