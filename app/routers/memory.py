"""app/routers/memory.py — 长期记忆 REST 接口。

设计真源：docs/specs/agent-memory/spec.md §11.2 / tasks.md §1.2。
所有写入仍经 core.agent_memory.store，本层只做参数映射与错误编码。
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from core.agent_memory import schema
from core.agent_memory import store

router = APIRouter(tags=["memory"])

_VIEWS = ("open", "closed", "proposed", "archived")
_EDITABLE = (
    "text", "kind", "namespace", "subject", "relation", "object",
    "tags", "valid_from", "valid_to", "importance",
)


def _error(status: int, code: str, message: str = "") -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message or code})


def _write_error(exc: store.MemoryWriteError) -> JSONResponse:
    status = 404 if exc.code == "not_found" else 422
    return _error(status, exc.code, str(exc))


def _view_matches(item: dict, view: str) -> bool:
    status = item.get("status")
    if view == "open":
        return status == "active" and not item.get("valid_to")
    if view == "closed":
        return status == "active" and bool(item.get("valid_to"))
    return status == view


def _sort_key(item: dict) -> str:
    return f"{item.get('recorded_at') or ''}|{item.get('id') or ''}"


@router.get("/api/memory/stats")
def memory_stats():
    return store.stats()


@router.get("/api/memory")
def list_memory(
    view: str = Query("open"),
    namespace: str | None = Query(None),
    kind: str | None = Query(None),
    q: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50),
):
    if view not in _VIEWS:
        return _error(422, "bad_view", f"非法视图：{view}")
    if kind and kind not in schema.KINDS:
        return _error(422, "bad_kind", f"非法类型：{kind}")
    if cursor is not None and "|" not in cursor:
        return _error(422, "bad_cursor", "游标格式非法")
    size = max(1, min(int(limit), 200))

    rows = [
        item for item in store.list_items(namespace=namespace, kind=kind, q=q)
        if _view_matches(item, view)
    ]
    rows.sort(key=_sort_key, reverse=True)
    if cursor:
        rows = [item for item in rows if _sort_key(item) < cursor]

    page = rows[:size]
    next_cursor = _sort_key(page[-1]) if len(rows) > size and page else None
    return {"items": page, "next_cursor": next_cursor}


@router.post("/api/memory")
def create_memory(payload: dict):
    """用户手动新建：无逐字稿来源，source 标记 manual。"""
    try:
        item = {
            **payload,
            "id": "",
            "status": "active",
            "source": {"manual": True},
        }
        outcome = store.upsert(item, require_source=False)
        return outcome["item"]
    except store.MemoryWriteError as exc:
        return _write_error(exc)
    except ValueError as exc:
        return _error(422, "bad_item", str(exc))


@router.patch("/api/memory/{memory_id}")
def update_memory(memory_id: str, payload: dict):
    patch = {key: value for key, value in (payload or {}).items() if key in _EDITABLE}
    if not patch:
        return _error(422, "empty_patch", "没有可更新字段")
    try:
        return store.update(memory_id, patch)
    except store.MemoryWriteError as exc:
        return _write_error(exc)
    except ValueError as exc:
        return _error(422, "bad_item", str(exc))


@router.post("/api/memory/{memory_id}/close")
def close_memory(memory_id: str, payload: dict | None = None):
    body = payload or {}
    try:
        return store.close(
            memory_id,
            valid_to=body.get("valid_to"),
            invalidated_by=body.get("invalidated_by"),
            reason=str(body.get("reason") or ""),
        )
    except store.MemoryWriteError as exc:
        return _write_error(exc)


@router.post("/api/memory/{memory_id}/reopen")
def reopen_memory(memory_id: str):
    try:
        return store.reopen(memory_id)
    except store.MemoryWriteError as exc:
        return _write_error(exc)


@router.delete("/api/memory/{memory_id}")
def delete_memory(memory_id: str):
    try:
        return store.delete(memory_id)
    except store.MemoryWriteError as exc:
        return _write_error(exc)


@router.post("/api/memory/{memory_id}/accept")
def accept_memory(memory_id: str):
    try:
        return store.set_status(memory_id, "active")
    except store.MemoryWriteError as exc:
        return _write_error(exc)


@router.post("/api/memory/{memory_id}/reject")
def reject_memory(memory_id: str):
    try:
        return store.delete(memory_id)
    except store.MemoryWriteError as exc:
        return _write_error(exc)


@router.post("/api/memory/consolidate/{task_id}")
def consolidate_memory(task_id: str):
    """手动触发单场会后巩固（force=True，绕过默认开关）。"""
    from core.agent_memory.consolidate import consolidate_task

    try:
        result = consolidate_task(task_id, force=True)
    except Exception as exc:
        return _error(422, "consolidate_failed", str(exc))
    if result.get("reason") == "task_not_found":
        return _error(404, "not_found", f"会议不存在：{task_id}")
    return result


@router.get("/api/memory/audit")
def memory_audit(limit: int = Query(100)):
    return {"items": store.read_audit(limit)}


@router.get("/api/memory/export")
def export_memory():
    items = store.load_all()
    filename = f"memory-export-{schema.today().replace('-', '')}.json"
    return JSONResponse(
        content={
            "version": 1,
            "exported_at": schema.now_iso(),
            "count": len(items),
            "items": items,
        },
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
