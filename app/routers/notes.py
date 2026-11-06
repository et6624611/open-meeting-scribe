"""
app/routers/notes.py — 笔记 + AI 注入 + 决策 + 改写撤销 / Notes + AI injection + decisions + rewrite undo

端点清单：
  GET/PUT  /api/tasks/{id}/notes                随记读写
  PUT      /api/tasks/{id}/summary              纪要定稿写入
  GET/POST /api/tasks/{id}/injections[...]      AI 注入条目
  GET/POST/PUT/DELETE /api/tasks/{id}/decisions[...] 决策流节点
  GET      /api/tasks/{id}/rewrites             AI 写回快照列表（PROPOSAL §5.4）
  POST     /api/tasks/{id}/rewrites/restore     按快照/按轮撤销 AI 写回
"""

import logging
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.store import save_task_to_disk, tasks
from core import users as user_module
from core.decision_flow import enrich_decision, first_open_status, make_decision_node, resolve_owner, status_of
from core.decision_status import (
    SUPERSEDED_STATUS_ID,
    StatusError,
    is_closing,
    known_ids,
    load_statuses,
    validate_status_id,
)
from core.i18n import _
from core.speakers import get_speaker_name_map

router = APIRouter(tags=["notes"])
# 语义审计专用（与 server.py 的 audit 同名 logger 共享 logs/audit.log handler）
audit_logger = logging.getLogger("audit")


def _mark_modified(task_id: str) -> None:
    """标记任务内容已修改，用于知识库同步脏检测 / Mark task content as modified for KB sync dirty detection."""
    tasks[task_id]["last_modified_at"] = datetime.now().isoformat()

# 决策流状态与推进方类型 / Decision-flow status and owner types
# DC-UNIFY-01：status 不再是封闭枚举，合法性由状态字典校验（core.decision_status）
OwnerType = Literal["self", "agent", "colleague", "enterprise"]
_HOW_MAX_ITEMS = 50


def _apply_status(decision: dict, status: str) -> None:
    """写入状态并同步旧 done 布尔（闭档态 = 完成）。"""
    decision["status"] = status
    decision["done"] = is_closing(status)


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
    type: str = Field(..., max_length=50)  # decision | conclusion | decision  注入类型 / Injection type
    content: str = Field(..., max_length=10000)
    source_message: str = Field(default="", max_length=10000)


class DecisionToggleRequest(BaseModel):
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

    # 决策条目注入即入决策流（conclusion 只进注入区）/ A decision injection also enters the flow
    if req.type == "decision":
        decisions = task.setdefault("decisions", [])
        user = user_module.get_current_user()
        assignee = user["name"] if user else ""
        # DC-UNIFY-01：「**标题**：正文」写法时拆出 title，展示侧降级
        title = ""
        content = req.content
        from core.summarize import split_decision_title
        title, body = split_decision_title(req.content)
        content = body or req.content
        decision_item = make_decision_node(
            content,
            assignee=assignee,
            title=title,
            source="injection",
            node_id=item["id"],
            extra={"injection_id": item["id"]},
        )
        decisions.append(decision_item)

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
    # 同步删除关联的决策流节点 / Also delete the associated decision-flow node
    decisions = task.get("decisions", [])
    task["decisions"] = [t for t in decisions if t.get("injection_id") != injection_id]
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"ok": True}


# ============================================================
# AI 改写快照与撤销 / AI Rewrite Snapshots & Undo
# （PROPOSAL-AGENT-REWRITE-CHANNEL §5.3 快照强制契约 + §5.4 恢复入口）
# ============================================================

class RewriteRestoreRequest(BaseModel):
    snapshot_id: str | None = Field(default=None, max_length=64)
    turn_id: str | None = Field(default=None, max_length=128)


@router.get("/api/tasks/{task_id}/rewrites")
def list_task_rewrites(task_id: str, target: str | None = None,
                       turn_id: str | None = None):
    """列出本会议的 AI 写回快照（只回摘要不回旧值全文，避免响应体膨胀）。"""
    if not tasks.get(task_id):
        raise HTTPException(404, _("Task not found"))
    from core import rewrite_snapshots as rsv
    snaps = rsv.list_snapshots(task_id, target=target, turn_id=turn_id)
    return {"snapshots": [{
        "id": s.get("id"),
        "target": s.get("target"),
        "tool": s.get("tool"),
        "turn_id": s.get("turn_id") or "",
        "ts": s.get("ts"),
        "description": rsv.describe_change(s),
    } for s in snaps]}


@router.post("/api/tasks/{task_id}/rewrites/restore")
def restore_task_rewrites(task_id: str, req: RewriteRestoreRequest):
    """
    撤销 AI 写回：传 snapshot_id 单点恢复，传 turn_id 整轮逆序回滚（二者必传其一）。

    恢复后走同一落盘口径（save_task_to_disk + 脏标记），知识库同步与只读重拉自然生效。
    """
    if not tasks.get(task_id):
        raise HTTPException(404, _("Task not found"))
    if not (req.snapshot_id or req.turn_id):
        raise HTTPException(400, {"error": "missing_target",
                                  "message": _("Provide snapshot_id or turn_id")})
    from core import rewrite_snapshots as rsv
    result = rsv.restore_task(task_id, snapshot_id=req.snapshot_id, turn_id=req.turn_id)
    if not result.get("ok"):
        err = result.get("error") or "restore_failed"
        code = 404 if err in ("task_not_found", "snapshot_not_found", "turn_not_found") else 400
        raise HTTPException(code, {"error": err, "message": result.get("message", "")})
    _mark_modified(task_id)
    # 恢复也是内容变更，必须留下审计迹（AC5/AC6：无审计条目的变更视为异常）
    audit_logger.info("[agent-engine] restore_rewrites task=%s scope=%s restored=%d detail=%s",
                      task_id, req.snapshot_id or f"turn:{req.turn_id}",
                      result.get("restored", 0), "; ".join(result.get("detail") or []))
    return result


# ============================================================
# 决策 API / Decisions API
# ============================================================

@router.get("/api/tasks/{task_id}/decisions")
def get_task_decisions(task_id: str):
    """获取任务的全部决策流节点（附状态字典元信息）/ Get decision-flow nodes with status meta."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    status_meta = {s["id"]: s for s in load_statuses()}
    kb_cache: dict = {}
    try:
        owner_map = get_speaker_name_map()
    except Exception:
        owner_map = {}
    decisions = [
        enrich_decision(task_id, task, t, status_meta, kb_cache, owner_map)
        for t in task.get("decisions", []) if isinstance(t, dict)
    ]
    return {"decisions": decisions}


@router.post("/api/tasks/{task_id}/decisions/{decision_id}/toggle")
def toggle_decision(task_id: str, decision_id: str, req: DecisionToggleRequest):
    """切换决策完成状态 / Toggle decision completion status."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    for decision in task.get("decisions", []):
        if decision["id"] == decision_id:
            # 勾选完成 = 写入闭档态；取消勾选回到首个开放态（状态字典可被用户改，不能写死）
            _apply_status(decision, "done" if req.done else first_open_status())
            decision["updated_at"] = datetime.now().isoformat()
            _mark_modified(task_id)
            save_task_to_disk(task_id)
            return {"decision": decision}
    raise HTTPException(404, _("Decision not found"))


@router.delete("/api/tasks/{task_id}/decisions/{decision_id}")
def delete_decision(task_id: str, decision_id: str):
    """删除一条决策流节点 / Delete a decision-flow node."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    decisions = task.get("decisions", [])
    target = next((t for t in decisions if t.get("id") == decision_id), None)
    if target is not None:
        # DC-R2-BE：删掉的 auto 节点落墓碑，重新生成纪要时不复活（手动节点无此风险）
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
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"ok": True}


class DecisionCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    assignee: str = Field(default="", max_length=100)
    # 新建时允许直接携带决策正文（与更新接口的 why 字段一致） / Allow body text at creation (same `why` field as the update endpoint)
    why: str | None = Field(default=None, max_length=2000)
    # DC-UNIFY-01：承接原 decision 对象的三要素与执行人档案能力
    title: str | None = Field(default=None, max_length=200)
    owner_id: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=32)
    # 等待方（决策由谁推进）：新表单不再采集执行人，改用此四维推进方
    owner_type: OwnerType | None = None


class DecisionUpdateRequest(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    assignee: str | None = Field(default=None, max_length=100)
    # 决策链字段透传 / Decision-chain pass-through fields
    why: str | None = Field(default=None, max_length=2000)
    outcome: str | None = Field(default=None, max_length=2000)
    how: list[str] | None = Field(default=None, max_length=_HOW_MAX_ITEMS)
    title: str | None = Field(default=None, max_length=200)
    owner_id: str | None = Field(default=None, max_length=100)
    # DC-R2-c：状态不再是封闭枚举，合法性由状态字典校验（非法值 422）
    status: str | None = Field(default=None, max_length=32)
    owner_type: OwnerType | None = None


@router.post("/api/tasks/{task_id}/decisions")
def create_decision(task_id: str, req: DecisionCreateRequest):
    """手工添加一条决策流节点 / Manually add a decision-flow node."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    status = None
    if req.status:
        try:
            status = validate_status_id(req.status)
        except StatusError as exc:
            raise HTTPException(422, str(exc))
    decision_item = make_decision_node(
        req.text,
        assignee=req.assignee,
        owner_id=req.owner_id,
        title=req.title or "",
        why=req.why or "",
        source="manual",
        status=status,
        owner_type=req.owner_type or "self",
    )
    decision_item["done"] = is_closing(decision_item["status"])
    task.setdefault("decisions", []).append(decision_item)
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"decision": decision_item}


@router.put("/api/tasks/{task_id}/decisions/{decision_id}")
def update_decision(task_id: str, decision_id: str, req: DecisionUpdateRequest):
    """编辑决策流节点内容/执行人/状态 / Edit a decision-flow node."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, _("Task not found"))
    for decision in task.get("decisions", []):
        if decision["id"] == decision_id:
            if req.text is not None:
                decision["text"] = req.text
            if req.title is not None:
                decision["title"] = req.title.strip()
            # 执行人：显式携带 owner_id 时按档案权威解析，否则按快照名直写
            if req.owner_id is not None:
                oid, name = resolve_owner(req.owner_id, req.assignee or decision.get("assignee"))
                decision["owner_id"] = oid
                decision["assignee"] = name
            elif req.assignee is not None:
                decision["assignee"] = req.assignee
            if req.why is not None:
                decision["why"] = req.why
            if req.outcome is not None:
                decision["outcome"] = req.outcome
            if req.how is not None:
                steps = [s.strip() for s in req.how if s and s.strip()][:_HOW_MAX_ITEMS]
                # 空表或 [text] 冗余副本不落盘（缺省视为 [text] 是读侧约定，非存储内容）
                if not steps or steps == [str(decision.get("text") or "").strip()]:
                    decision.pop("how", None)
                else:
                    decision["how"] = steps
            if req.owner_type is not None:
                decision["owner_type"] = req.owner_type
            if req.status is not None:
                try:
                    _apply_status(decision, validate_status_id(req.status))
                except StatusError as exc:
                    raise HTTPException(422, str(exc))
            decision["updated_at"] = datetime.now().isoformat()
            _mark_modified(task_id)
            save_task_to_disk(task_id)
            return {"decision": decision}
    raise HTTPException(404, _("Decision not found"))


# ============================================================
# 决策演变链：标记 / 撤销「已被替代」 / Supersede flow
# ============================================================
# 关系只能由用户手动建立（读时议题聚类仅做展示，永不写状态）。
# 旧节点闭档为系统态 superseded，并冗余新决策标题/会议名快照防死链；
# 撤销时恢复标记前的原状态（prev_status），不丢用户中间修改。

class SupersedeRequest(BaseModel):
    by_task_id: str = Field(..., min_length=1, max_length=100)
    by_decision_id: str = Field(..., min_length=1, max_length=100)


def _find_decision(task_id: str, decision_id: str) -> tuple[dict, dict] | None:
    task = tasks.get(task_id)
    if not isinstance(task, dict):
        return None
    for decision in task.get("decisions", []):
        if isinstance(decision, dict) and decision.get("id") == decision_id:
            return task, decision
    return None


@router.post("/api/tasks/{task_id}/decisions/{decision_id}/supersede")
def supersede_decision(task_id: str, decision_id: str, req: SupersedeRequest):
    """把旧决策标记为已被另一会议（或同会议）的新决策替代 / Mark a node superseded."""
    found = _find_decision(task_id, decision_id)
    if not found:
        raise HTTPException(404, _("Decision not found"))
    task, decision = found

    if status_of(decision) == SUPERSEDED_STATUS_ID:
        raise HTTPException(409, detail={"code": "already_superseded",
                                         "reason": "Decision is already marked as superseded"})
    if req.by_task_id == task_id and req.by_decision_id == decision_id:
        raise HTTPException(422, _("A decision cannot supersede itself"))

    target = _find_decision(req.by_task_id, req.by_decision_id)
    if not target:
        raise HTTPException(404, _("Superseding decision not found"))
    target_task, target_decision = target

    prev = status_of(decision)
    decision["superseded_by"] = {
        "task_id": req.by_task_id,
        "decision_id": req.by_decision_id,
        "title": str(target_decision.get("title") or target_decision.get("text") or "")[:200],
        "meeting_title": str(target_task.get("title") or "")[:200],
        "prev_status": prev,
        "marked_at": datetime.now().isoformat(),
    }
    _apply_status(decision, SUPERSEDED_STATUS_ID)
    decision["updated_at"] = datetime.now().isoformat()
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    audit_logger.info("decision_superseded task=%s decision=%s by_task=%s by_decision=%s",
                      task_id, decision_id, req.by_task_id, req.by_decision_id)
    return {"decision": decision}


@router.delete("/api/tasks/{task_id}/decisions/{decision_id}/supersede")
def revert_supersede(task_id: str, decision_id: str):
    """撤销「已被替代」：恢复标记前状态 / Revert a superseded marking."""
    found = _find_decision(task_id, decision_id)
    if not found:
        raise HTTPException(404, _("Decision not found"))
    task, decision = found

    if status_of(decision) != SUPERSEDED_STATUS_ID:
        raise HTTPException(409, detail={"code": "not_superseded",
                                         "reason": "Decision is not marked as superseded"})
    prev = str((decision.get("superseded_by") or {}).get("prev_status") or "")
    decision.pop("superseded_by", None)
    # 原状态若已被用户从字典删除，降级到开放首态，避免复活非法状态
    restore = prev if prev in known_ids() else "to_decide"
    _apply_status(decision, restore)
    decision["updated_at"] = datetime.now().isoformat()
    _mark_modified(task_id)
    save_task_to_disk(task_id)
    return {"decision": decision}
