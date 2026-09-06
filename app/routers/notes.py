"""
app/routers/notes.py — 笔记 + AI 注入 + 待办
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import tasks, save_task_to_disk
from core import users as user_module

router = APIRouter(tags=["notes"])


# ============================================================
# 笔记 API
# ============================================================

class NotesUpdate(BaseModel):
    notes: str


@router.get("/api/tasks/{task_id}/notes")
def get_task_notes(task_id: str):
    """获取任务笔记"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {"notes": task.get("user_notes", "")}


@router.put("/api/tasks/{task_id}/notes")
def update_task_notes(task_id: str, req: NotesUpdate):
    """保存任务笔记（写 tasks JSON）"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    task["user_notes"] = req.notes
    save_task_to_disk(task_id)
    return {"notes": req.notes}


# ============================================================
# AI 注入 API
# ============================================================

class InjectRequest(BaseModel):
    type: str  # todo | conclusion | decision
    content: str
    source_message: str = ""


class TodoToggleRequest(BaseModel):
    done: bool


@router.get("/api/tasks/{task_id}/injections")
def get_task_injections(task_id: str):
    """获取任务的所有注入内容"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {"injections": task.get("injections", [])}


@router.post("/api/tasks/{task_id}/inject")
def inject_content(task_id: str, req: InjectRequest):
    """注入一条 AI 识别内容（写 tasks JSON）"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
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

    # 如果是 todo 类型，同步添加到 todos 列表
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
            "created_at": item["injected_at"],
            "injection_id": item["id"],
        }
        todos.append(todo_item)

    save_task_to_disk(task_id)
    return {"item": item}


@router.post("/api/tasks/{task_id}/injections/{injection_id}/apply")
def apply_injection(task_id: str, injection_id: str):
    """标记注入内容为已应用到纪要（写 tasks JSON）"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    for item in task.get("injections", []):
        if item["id"] == injection_id:
            item["applied"] = True
            save_task_to_disk(task_id)
            return {"item": item}
    raise HTTPException(404, "注入内容不存在")


@router.delete("/api/tasks/{task_id}/injections/{injection_id}")
def delete_injection(task_id: str, injection_id: str):
    """删除一条注入内容（写 tasks JSON）"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    injections = task.get("injections", [])
    task["injections"] = [i for i in injections if i["id"] != injection_id]
    # 同步删除关联的 todo
    todos = task.get("todos", [])
    task["todos"] = [t for t in todos if t.get("injection_id") != injection_id]
    save_task_to_disk(task_id)
    return {"ok": True}


# ============================================================
# 待办 API
# ============================================================

@router.get("/api/tasks/{task_id}/todos")
def get_task_todos(task_id: str):
    """获取任务的所有待办事项"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {"todos": task.get("todos", [])}


@router.post("/api/tasks/{task_id}/todos/{todo_id}/toggle")
def toggle_todo(task_id: str, todo_id: str, req: TodoToggleRequest):
    """切换待办完成状态（写 tasks JSON）"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    for todo in task.get("todos", []):
        if todo["id"] == todo_id:
            todo["done"] = req.done
            save_task_to_disk(task_id)
            return {"todo": todo}
    raise HTTPException(404, "待办不存在")


@router.delete("/api/tasks/{task_id}/todos/{todo_id}")
def delete_todo(task_id: str, todo_id: str):
    """删除一条待办（写 tasks JSON）"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    todos = task.get("todos", [])
    task["todos"] = [t for t in todos if t["id"] != todo_id]
    save_task_to_disk(task_id)
    return {"ok": True}
