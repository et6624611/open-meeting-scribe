"""
app/routers/notes.py — 笔记 + AI 注入 + 待办 / Notes + AI injection + todos
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.store import save_task_to_disk, tasks
from core import users as user_module
from core.i18n import _

router = APIRouter(tags=["notes"])


def _mark_modified(task_id: str) -> None:
    """标记任务内容已修改，用于知识库同步脏检测 / Mark task content as modified for KB sync dirty detection."""
    tasks[task_id]["last_modified_at"] = datetime.now().isoformat()

# 决策流状态与推进方类型 / Decision-flow status and owner types
DecisionStatus = Literal["to_decide", "to_start", "in_progress", "to_confirm", "done"]
OwnerType = Literal["self", "agent", "colleague", "enterprise"]
_HOW_MAX_ITEMS = 50


# ============================================================
# 笔记 API / Notes API
# ============================================================

class NotesUpdate(BaseModel):
    notes: str = Field("", max_length=100000)


@router.get("/api/tasks/{task_id}/notes")
def get_task_notes(task_id: str):
    """获取任务笔记 / Get task notes."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    return {"notes": task.get("user_notes", "")}


@router.put("/api/tasks/{task_id}/notes")
def update_task_notes(task_id: str, req: NotesUpdate):
    """保存任务笔记 / Save task notes."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    task["user_notes"] = req.notes
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"notes": req.notes}


@router.put("/api/tasks/{task_id}/summary")
def update_task_summary(task_id: str, req: NotesUpdate):
    """保存用户编辑的纪要 / Save user-edited summary."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    task["user_summary"] = req.notes
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"notes": req.notes}


# ============================================================
# AI 注入 API / AI Injection API
# ============================================================

class InjectRequest(BaseModel):
    type: str = Field(..., max_length=50)  # todo | conclusion | decision  注入类型 / Injection type
    content: str = Field(..., max_length=10000)
    source_message: str = Field(default="", max_length=10000)


class TodoToggleRequest(BaseModel):
    done: bool


@router.get("/api/tasks/{task_id}/injections")
def get_task_injections(task_id: str):
    """获取任务的所有注入内容 / Get all injections for a task."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    return {"injections": task.get("injections", [])}


@router.post("/api/tasks/{task_id}/inject")
def inject_content(task_id: str, req: InjectRequest):
    """注入一条 AI 识别内容 / Inject an AI-identified item."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    injections = task.setdefault("injections", [])
    item = {
        "id": str(uuid.uuid4()),
        "type": req.type,
        "content": req.content,
        "source_message": req.source_message,
        "injected_at": datetime.now().isoformat(),
        "applied": False,
    }
    injections.append(item)

    # 如果是 todo 类型，同步添加到 todos 列表 / If todo type, also add to todos list
    if req.type == "todo":
        todos = task.setdefault("todos", [])
        user = user_module.get_current_user()
        assignee = user["name"] if user else ""
        todo_item = {
            "id": item["id"],
            "text": req.content,
            "assignee": assignee,
            "done": False,
            "source": "injection",
            "status": "to_start",
            "how": [req.content],
            "owner_type": "self",
            "created_at": item["injected_at"],
            "injection_id": item["id"],
        }
        todos.append(todo_item)

    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"item": item}


@router.post("/api/tasks/{task_id}/injections/{injection_id}/apply")
def apply_injection(task_id: str, injection_id: str):
    """标记注入内容为已应用到纪要 / Mark injection as applied to summary."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    for item in task.get("injections", []):
        if item["id"] == injection_id:
            item["applied"] = True
            save_task_to_disk(task_id)
            return {"item": item}
    raise HTTPException(404, _("Injection content not found"))


@router.delete("/api/tasks/{task_id}/injections/{injection_id}")
def delete_injection(task_id: str, injection_id: str):
    """删除一条注入内容 / Delete an injection."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    injections = task.get("injections", [])
    task["injections"] = [i for i in injections if i["id"] != injection_id]
    # 同步删除关联的 todo / Also delete associated todo
    todos = task.get("todos", [])
    task["todos"] = [t for t in todos if t.get("injection_id") != injection_id]
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"ok": True}


# ============================================================
# 待办 API / Todos API
# ============================================================

@router.get("/api/tasks/{task_id}/todos")
def get_task_todos(task_id: str):
    """获取任务的所有待办事项 / Get all todos for a task."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    return {"todos": task.get("todos", [])}


@router.post("/api/tasks/{task_id}/todos/{todo_id}/toggle")
def toggle_todo(task_id: str, todo_id: str, req: TodoToggleRequest):
    """切换待办完成状态 / Toggle todo completion status."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    for todo in task.get("todos", []):
        if todo["id"] == todo_id:
            todo["done"] = req.done
            # 同步决策流状态:done 与 status 保持一致 / Keep done and status in sync
            todo["status"] = "done" if req.done else "in_progress"
            _mark_modified(task_id)
            save_task_to_disk(task_id)
            return {"todo": todo}
    raise HTTPException(404, _("To-do not found"))


@router.delete("/api/tasks/{task_id}/todos/{todo_id}")
def delete_todo(task_id: str, todo_id: str):
    """删除一条待办 / Delete a todo."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    todos = task.get("todos", [])
    task["todos"] = [t for t in todos if t["id"] != todo_id]
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"ok": True}


class TodoCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    assignee: str = Field(default="", max_length=100)
    # 新建时允许直接携带决策正文（与更新接口的 why 字段一致） / Allow body text at creation (same `why` field as the update endpoint)
    why: str | None = Field(default=None, max_length=2000)


class TodoUpdateRequest(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    assignee: str | None = Field(default=None, max_length=100)
    # 决策链字段透传 / Decision-chain pass-through fields
    why: str | None = Field(default=None, max_length=2000)
    outcome: str | None = Field(default=None, max_length=2000)
    how: list[str] | None = Field(default=None, max_length=_HOW_MAX_ITEMS)
    status: DecisionStatus | None = None
    owner_type: OwnerType | None = None


@router.post("/api/tasks/{task_id}/todos")
def create_todo(task_id: str, req: TodoCreateRequest):
    """手工添加一条决策节点 / Manually add a decision node."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    todos = task.setdefault("todos", [])
    todo_item = {
        "id": str(uuid.uuid4()),
        "text": req.text,
        "assignee": req.assignee,
        "done": False,
        "source": "manual",
        "status": "to_start",
        "how": [req.text],
        "owner_type": "self",
        "created_at": datetime.now().isoformat(),
    }
    if req.why and req.why.strip():
        todo_item["why"] = req.why.strip()
    todos.append(todo_item)
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"todo": todo_item}


@router.put("/api/tasks/{task_id}/todos/{todo_id}")
def update_todo(task_id: str, todo_id: str, req: TodoUpdateRequest):
    """编辑决策节点内容/执行人/决策链字段 / Edit decision node fields."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    for todo in task.get("todos", []):
        if todo["id"] == todo_id:
            if req.text is not None:
                todo["text"] = req.text
            if req.assignee is not None:
                todo["assignee"] = req.assignee
            if req.why is not None:
                todo["why"] = req.why
            if req.outcome is not None:
                todo["outcome"] = req.outcome
            if req.how is not None:
                todo["how"] = [s.strip() for s in req.how if s and s.strip()][:_HOW_MAX_ITEMS]
            if req.owner_type is not None:
                todo["owner_type"] = req.owner_type
            if req.status is not None:
                todo["status"] = req.status
                # status 与 done 保持同步 / Keep status and done in sync
                todo["done"] = req.status == "done"
            _mark_modified(task_id)
            save_task_to_disk(task_id)
            return {"todo": todo}
    raise HTTPException(404, _("To-do not found"))
