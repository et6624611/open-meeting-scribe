"""
app/routers/decision_statuses.py — 决策状态字典 CRUD / Decision status dictionary

作者：Yongliang Wang
创建：2026-09-25
版本：1.0.0

契约事实源：docs/API_CONTRACTS.md §12.4（REQ-DECISION-CENTER-R2 · DC-R2-c · 裁决 D6/D7）。
DC-UNIFY-01：字典默认集 = 决策流五态；删除自定义状态时，引用该状态的
**决策流节点（todos）**当场回落到首个开放态并落盘（不留悬空引用）。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.store import save_task_to_disk, tasks
from core.decision_flow import status_of
from core.decision_status import (
    StatusError,
    create_status,
    delete_status,
    is_closing,
    load_statuses,
    reorder,
    update_status,
)

router = APIRouter(tags=["decision-statuses"])


class StatusCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=20)
    color: str = Field(default="", max_length=64)
    closing: bool = False


class StatusUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=20)
    color: str | None = Field(default=None, max_length=64)
    closing: bool | None = None


class StatusReorderRequest(BaseModel):
    order: list[str] = Field(..., min_length=1, max_length=50)


def _raise(exc: StatusError) -> None:
    """unknown → 404，其余校验失败 → 400（与决策流写入的错误口径一致）。"""
    msg = str(exc)
    raise HTTPException(404 if msg.startswith("unknown status") else 400, msg)


@router.get("/api/decision-statuses")
def list_statuses():
    """状态字典全量（含系统锚点与自定义状态，按用户排序返回）。"""
    statuses = load_statuses()
    return {"statuses": statuses, "total": len(statuses)}


@router.post("/api/decision-statuses")
def create_status_item(req: StatusCreateRequest):
    try:
        return {"status": create_status(req.name, req.color, req.closing)}
    except StatusError as exc:
        _raise(exc)


@router.put("/api/decision-statuses/{sid}")
def update_status_item(sid: str, req: StatusUpdateRequest):
    try:
        return {"status": update_status(sid, req.name, req.color, req.closing)}
    except StatusError as exc:
        _raise(exc)


@router.delete("/api/decision-statuses/{sid}")
def delete_status_item(sid: str):
    """删除自定义状态 + 把引用它的决策流节点回落到开放态（锚点不可删）。"""
    try:
        result = delete_status(sid)
    except StatusError as exc:
        _raise(exc)
    fallback = result["reassign_to"]
    reassigned = 0
    for task_id, task in list(tasks.items()):
        todos = task.get("todos")
        if not isinstance(todos, list):
            continue
        touched = False
        for todo in todos:
            if isinstance(todo, dict) and status_of(todo) == sid:
                todo["status"] = fallback
                todo["done"] = is_closing(fallback)
                touched = True
                reassigned += 1
        if touched:
            save_task_to_disk(task_id)
    return {"ok": True, "removed": sid, "reassigned": reassigned}


@router.post("/api/decision-statuses/reorder")
def reorder_statuses(req: StatusReorderRequest):
    try:
        statuses = reorder(req.order)
    except StatusError as exc:
        _raise(exc)
    from core.decision_status import save_statuses
    save_statuses(statuses)
    return {"statuses": statuses, "total": len(statuses)}
