"""
core/notes_service.py — 会议笔记/注入/决策的受控写服务

T-24：原实现散在 notes 路由端点里，agent-tools 写通道只能 `from app.routers.notes import ...`
反向复用，形成 router → router 耦合。此处下沉为纯领域函数，两个入口共用同一实现
（继承落盘 + 脏标记 + 状态字典校验 + auto 节点墓碑）。

错误以 NotesServiceError 表达，由调用方（router / agent-tools）映射为各自的 HTTP 语义。

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-06
"""

from __future__ import annotations

import uuid
from datetime import datetime

from core import task_store, users
from core.decision_flow import make_decision_node, resolve_owner
from core.decision_status import StatusError, is_closing, validate_status_id

# 与路由层 Pydantic 约束保持一致（agent-tools 通道不经过 Pydantic，需在此兜底）
_FIELD_LIMITS = {
    "text": 500,
    "assignee": 100,
    "why": 2000,
    "outcome": 2000,
    "title": 200,
    "owner_id": 100,
    "status": 32,
}
_HOW_MAX_ITEMS = 50


class NotesServiceError(Exception):
    """受控写失败。code 供调用方映射 HTTP 状态与错误体。"""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _require_task(task_id: str) -> dict:
    task = task_store.tasks.get(task_id)
    if not task:
        raise NotesServiceError("task_not_found", "Task not found")
    return task


def mark_modified(task_id: str) -> None:
    """标记任务内容已修改，用于知识库同步脏检测。"""
    task_store.tasks[task_id]["last_modified_at"] = datetime.now().isoformat()


def _apply_status(decision: dict, status: str) -> None:
    """写入状态并同步旧 done 布尔（闭档态 = 完成）。"""
    decision["status"] = status
    decision["done"] = is_closing(status)


def validate_patch(patch: dict) -> None:
    """字段长度/条目上限校验（agent-tools 通道不经过 Pydantic，需在快照前先行挡下）。"""
    for field, limit in _FIELD_LIMITS.items():
        value = patch.get(field)
        if value is not None and len(str(value)) > limit:
            raise NotesServiceError("invalid_field", f"{field} 超出长度上限 {limit}")
    how = patch.get("how")
    if how is not None and len(how) > _HOW_MAX_ITEMS:
        raise NotesServiceError("invalid_field", f"how 超出条目上限 {_HOW_MAX_ITEMS}")


def update_summary(task_id: str, summary: str) -> str:
    """保存用户编辑的纪要（user_summary）。"""
    task = _require_task(task_id)
    task["user_summary"] = summary
    mark_modified(task_id)
    task_store.save_task_to_disk(task_id)
    return summary


def inject_item(task_id: str, item_type: str, content: str, source_message: str = "") -> dict:
    """注入一条 AI 识别内容；decision 类型同时进入决策流。"""
    task = _require_task(task_id)
    injections = task.setdefault("injections", [])
    item = {
        "id": str(uuid.uuid4()),
        "type": item_type,
        "content": content,
        "source_message": source_message,
        "injected_at": datetime.now().isoformat(),
        "applied": False,
    }
    injections.append(item)

    # 决策条目注入即入决策流（conclusion 只进注入区）
    if item_type == "decision":
        decisions = task.setdefault("decisions", [])
        user = users.get_current_user()
        assignee = user["name"] if user else ""
        from core.summarize import split_decision_title

        title, body = split_decision_title(content)
        decisions.append(make_decision_node(
            body or content,
            assignee=assignee,
            title=title,
            source="injection",
            node_id=item["id"],
            extra={"injection_id": item["id"]},
        ))

    mark_modified(task_id)
    task_store.save_task_to_disk(task_id)
    return item


def delete_decision(task_id: str, decision_id: str) -> bool:
    """删除一条决策流节点；auto 节点落墓碑，重新生成纪要时不复活。"""
    task = _require_task(task_id)
    decisions = task.get("decisions", [])
    target = next((t for t in decisions if t.get("id") == decision_id), None)
    if target is not None:
        from core.summarize import build_decision_tombstone

        tombstone = build_decision_tombstone(target)
        if tombstone is not None:
            deletions = task.get("decision_deletions")
            if not isinstance(deletions, list):
                deletions = []
            existing_keys = {t.get("text_key") for t in deletions if isinstance(t, dict)}
            if tombstone["text_key"] not in existing_keys:
                deletions.append(tombstone)
            task["decision_deletions"] = deletions
    task["decisions"] = [t for t in decisions if t.get("id") != decision_id]
    mark_modified(task_id)
    task_store.save_task_to_disk(task_id)
    return True


def update_decision(task_id: str, decision_id: str, patch: dict) -> dict:
    """编辑决策流节点内容/执行人/状态。patch 为 None 的字段表示不改。"""
    validate_patch(patch)
    task = _require_task(task_id)
    for decision in task.get("decisions", []):
        if decision["id"] != decision_id:
            continue
        if patch.get("text") is not None:
            decision["text"] = patch["text"]
        if patch.get("title") is not None:
            decision["title"] = str(patch["title"]).strip()
        # 执行人：显式携带 owner_id 时按档案权威解析，否则按快照名直写
        if patch.get("owner_id") is not None:
            oid, name = resolve_owner(patch["owner_id"], patch.get("assignee") or decision.get("assignee"))
            decision["owner_id"] = oid
            decision["assignee"] = name
        elif patch.get("assignee") is not None:
            decision["assignee"] = patch["assignee"]
        if patch.get("why") is not None:
            decision["why"] = patch["why"]
        if patch.get("outcome") is not None:
            decision["outcome"] = patch["outcome"]
        if patch.get("how") is not None:
            steps = [s.strip() for s in patch["how"] if s and s.strip()][:_HOW_MAX_ITEMS]
            # 空表或 [text] 冗余副本不落盘（缺省视为 [text] 是读侧约定，非存储内容）
            if not steps or steps == [str(decision.get("text") or "").strip()]:
                decision.pop("how", None)
            else:
                decision["how"] = steps
        if patch.get("owner_type") is not None:
            decision["owner_type"] = patch["owner_type"]
        if patch.get("status") is not None:
            try:
                _apply_status(decision, validate_status_id(patch["status"]))
            except StatusError as exc:
                raise NotesServiceError("invalid_status", str(exc))
        decision["updated_at"] = datetime.now().isoformat()
        mark_modified(task_id)
        task_store.save_task_to_disk(task_id)
        return decision
    raise NotesServiceError("decision_not_found", "Decision not found")
