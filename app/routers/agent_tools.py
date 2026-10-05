"""
app/routers/agent_tools.py — 智能体反向工具调用端点 / Agent reverse tool-invocation endpoint

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

POST /api/agent-tools/invoke  {name, arguments}
  - 鉴权：Authorization: Bearer <短时令牌>（core.agent_tools.tokens 进程内注册表）
  - 读工具 → core.agent_tools.impl.execute_tool（会议域工具唯一实现）
  - 写工具 → app.routers.notes 既有函数（同一 tasks 内存 + save_task_to_disk + 脏标记）
  - 授权档位决定可调用集合：readonly 仅读；workspace_write/full_task 才可写

该前缀在 server.py 加入 JWT 豁免（用自有 bearer 保护），并仅监听本机回环使用。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from core.agent_tools.catalog import TOOLS_BY_NAME
from core.agent_tools.tokens import verify_token

logger = logging.getLogger(__name__)
# 语义审计专用（与 server.py 的 audit 同名 logger 共享 logs/audit.log handler）
audit_logger = logging.getLogger("audit")

router = APIRouter(tags=["agent-tools"])


class ToolInvoke(BaseModel):
    name: str = Field(..., max_length=64)
    arguments: dict = Field(default_factory=dict)


def _bearer(request: Request, authorization: str | None) -> str:
    """从 Authorization 头取 bearer 令牌（回退 query，兼容 stdio bridge）。"""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.query_params.get("token", "") or ""


@router.post("/api/agent-tools/invoke")
def invoke_tool(payload: ToolInvoke, request: Request,
                authorization: str | None = Header(default=None)):
    """
    单次工具调用分发。 / Dispatch one tool invocation from the MCP bridge.
    """
    token = _bearer(request, authorization)
    ctx = verify_token(token)
    if not ctx:
        raise HTTPException(401, {"error": "invalid_token", "message": "工具令牌无效或已过期"})

    tool = TOOLS_BY_NAME.get(payload.name)
    if not tool:
        raise HTTPException(404, {"error": "unknown_tool", "message": f"未知工具: {payload.name}"})

    # 授权档位：写工具要求可写档；例外：revise_insight_board 不带 html 时为读语义（取基线），只读档放行
    if tool["kind"] == "write" and not ctx.writable:
        if not (payload.name == "revise_insight_board" and "html" not in (payload.arguments or {})):
            raise HTTPException(403, {"error": "read_only",
                                      "message": f"当前授权档（{ctx.auth_tier}）为只读，禁止写操作 {payload.name}"})

    args = payload.arguments or {}

    # ── 读工具：会议域工具唯一实现（core/agent_tools/impl.py） ──
    if tool["kind"] == "read":
        from core.agent_tools.impl import execute_tool
        result = execute_tool(payload.name, args, task_id=ctx.task_id, project_id=ctx.project_id)
        return {"ok": True, "tool": payload.name, "result": result}

    # ── 写工具：复用 notes 路由既有受控函数（继承落盘 + 脏标记） ──
    return _dispatch_write(payload.name, args, ctx)


def _dispatch_write(name: str, args: dict, ctx) -> dict:
    import copy

    from app.routers.notes import (
        InjectRequest,
        NotesUpdate,
        TodoUpdateRequest,
        delete_todo,
        inject_content,
        update_task_summary,
        update_todo,
    )
    from app.store import tasks
    from core import rewrite_snapshots as rsv

    if not ctx.task_id:
        raise HTTPException(400, {"error": "no_task", "message": "写操作需要关联具体会议任务"})

    turn_id = getattr(ctx, "turn_id", "") or ""

    def _find_node(node_id: str) -> dict | None:
        task = tasks.get(ctx.task_id) or {}
        for t in task.get("todos") or []:
            if isinstance(t, dict) and t.get("id") == node_id:
                return t
        return None

    def _snapshot(target: str, old, *, absent: bool = False) -> bool:
        """写回前强制快照（§5.3 契约）；失败不阻断写入，但回执标 restorable=false。"""
        snap_id = rsv.snapshot_write(ctx.task_id, target, old, tool=name,
                                     turn_id=turn_id, old_absent=absent)
        return bool(snap_id)

    if name == "propose_summary":
        # 提案式纪要改写：后端不写 task、不落盘（区别于 update_summary）。
        # proposed 全文经 tool_call 事件的 args 回前端 diff 卡，用户接受后才走 PUT /summary 落盘。
        summary = str(args.get("summary", ""))[:20000]
        logger.info("[agent-tools] propose_summary task=%s len=%d", ctx.task_id, len(summary))
        audit_logger.info("[agent-engine] propose_summary task=%s tier=%s chars=%d (未落盘,待用户确认)",
                          ctx.task_id, ctx.auth_tier, len(summary))
        return {"ok": True, "tool": name, "result": {"proposed": True, "chars": len(summary)}}

    if name == "propose_notes":
        # 提案式随记改写：后端不写 task、不落盘（随记为用户原创区，PROPOSAL §5.3 市场模式 D）。
        # 建议全文经 tool_call 事件的 args 回前端 diff 卡，用户接受后才走 PUT /notes 落盘。
        notes = str(args.get("notes", ""))[:20000]
        logger.info("[agent-tools] propose_notes task=%s len=%d", ctx.task_id, len(notes))
        audit_logger.info("[agent-engine] propose_notes task=%s tier=%s chars=%d (未落盘,待用户确认)",
                          ctx.task_id, ctx.auth_tier, len(notes))
        return {"ok": True, "tool": name,
                "result": {"proposed": True, "chars": len(notes),
                           "note": "已作为待确认建议展示给用户，未经用户点「接受」不会写入随记"}}

    if name == "update_summary":
        summary = str(args.get("summary", ""))[:20000]
        task = tasks.get(ctx.task_id) or {}
        old_us = task.get("user_summary")
        # 快照存的是“改写前的定稿口径”，恢复时一并回退到 AI 初稿/未编辑态
        restorable = _snapshot(rsv.TARGET_SUMMARY,
                               old_us if old_us is not None else (task.get("summary") or ""),
                               absent=old_us is None)
        res = update_task_summary(ctx.task_id, NotesUpdate(notes=summary))
        logger.info("[agent-tools] update_summary task=%s len=%d", ctx.task_id, len(summary))
        audit_logger.info("[agent-engine] update_summary task=%s tier=%s chars=%d restorable=%s",
                          ctx.task_id, ctx.auth_tier, len(summary), restorable)
        return {"ok": True, "tool": name, "result": {"updated": True, "chars": len(summary),
                                                     "restorable": restorable}, "echo": res}

    if name == "inject_items":
        items = args.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(400, {"error": "bad_items", "message": "items 必须是非空数组"})
        injected = []
        for it in items[:50]:  # 单轮上限，防刷屏（方案 §3.9-7）
            itype = str(it.get("type", "")).strip()
            content = str(it.get("content", "")).strip()
            if itype not in ("todo", "conclusion", "decision") or not content:
                continue
            r = inject_content(ctx.task_id, InjectRequest(type=itype, content=content,
                                                            source_message="agent-engine"))
            item_id = r.get("item", {}).get("id")
            injected.append(item_id)
            # todo/decision 会同时开一个决策流节点（id 与注入条目一致）：快照“此前不存在”，
            # 撤销本轮即等价于删掉新建节点；conclusion 不开节点，无需快照
            if itype in ("todo", "decision") and item_id:
                _snapshot(rsv.decision_node_target(str(item_id)), None, absent=True)
        logger.info("[agent-tools] inject_items task=%s n=%d", ctx.task_id, len(injected))
        audit_logger.info("[agent-engine] inject_items task=%s tier=%s count=%d",
                          ctx.task_id, ctx.auth_tier, len(injected))
        return {"ok": True, "tool": name, "result": {"injected": len(injected), "ids": injected,
                                                     "restorable": True}}

    if name == "update_decision_node":
        # 决策节点改写：按节点 id 寻址，收口 notes.update_todo 同一口径（状态字典校验/脏标记/落盘）
        node_id = str(args.get("node_id", "")).strip()
        if not node_id:
            raise HTTPException(400, {"error": "missing_node_id",
                                      "message": "需要 node_id（先调 get_meeting_todos 取节点 id）"})
        node = _find_node(node_id)
        if node is None:
            raise HTTPException(404, {"error": "node_not_found",
                                      "message": f"决策节点不存在：{node_id}"})
        patch = {k: args.get(k) for k in ("title", "text", "status", "why", "outcome", "owner_type")
                 if args.get(k) is not None}
        if not patch:
            raise HTTPException(400, {"error": "empty_patch", "message": "未携带任何要改的字段"})
        # 状态先行校验：被拒的写不应留下一条"看起来能撤销"的空快照
        if "status" in patch:
            from core.decision_status import StatusError, validate_status_id
            try:
                patch["status"] = validate_status_id(patch["status"])
            except StatusError as exc:
                raise HTTPException(422, {"error": "bad_status",
                                          "message": f"{exc}（status 只能取 get_meeting_todos 返回的 available_statuses 中的 id）"})
        # 先过 Pydantic 校验（字段超长/枚举非法回 400），再落快照：被拒的写不留空快照
        try:
            req_model = TodoUpdateRequest(**patch)
        except ValidationError as exc:
            raise HTTPException(400, {"error": "bad_patch",
                                      "message": f"字段不合法：{exc.errors()[0].get('msg', exc)}"})
        restorable = _snapshot(rsv.decision_node_target(node_id), copy.deepcopy(node))
        res = update_todo(ctx.task_id, node_id, req_model)
        todo = res.get("todo") or {}
        logger.info("[agent-tools] update_decision_node task=%s node=%s fields=%s",
                    ctx.task_id, node_id, ",".join(patch))
        audit_logger.info("[agent-engine] update_decision_node task=%s tier=%s node=%s fields=%s status=%s",
                          ctx.task_id, ctx.auth_tier, node_id, ",".join(patch), todo.get("status"))
        return {"ok": True, "tool": name,
                "result": {"updated": True, "node_id": node_id,
                           "status": todo.get("status"), "title": todo.get("title"),
                           "restorable": restorable},
                "echo": res}

    if name == "delete_decision_node":
        node_id = str(args.get("node_id", "")).strip()
        if not node_id:
            raise HTTPException(400, {"error": "missing_node_id",
                                      "message": "需要 node_id（先调 get_meeting_todos 取节点 id）"})
        node = _find_node(node_id)
        if node is None:
            raise HTTPException(404, {"error": "node_not_found",
                                      "message": f"决策节点不存在：{node_id}"})
        restorable = _snapshot(rsv.decision_node_target(node_id), copy.deepcopy(node))
        res = delete_todo(ctx.task_id, node_id)  # auto 节点同步落防复活墓碑
        logger.info("[agent-tools] delete_decision_node task=%s node=%s", ctx.task_id, node_id)
        audit_logger.info("[agent-engine] delete_decision_node task=%s tier=%s node=%s restorable=%s",
                          ctx.task_id, ctx.auth_tier, node_id, restorable)
        return {"ok": True, "tool": name,
                "result": {"deleted": True, "node_id": node_id, "restorable": restorable},
                "echo": res}

    if name == "revise_insight_board":
        # 洞察共创 HTML 产物：唯一实现与内置引擎共享（core.insight_board.invoke_revise_board）
        from core.insight_board import invoke_revise_board
        result = invoke_revise_board(ctx.task_id, args)
        if args.get("html") and result.get("ok"):
            audit_logger.info("[agent-engine] revise_insight_board task=%s tier=%s chars=%d rev=%s",
                              ctx.task_id, ctx.auth_tier, len(str(args.get("html"))), result.get("revision"))
        return {"ok": bool(result.get("ok")), "tool": name, "result": result}

    if name == "revise_insight_board_section":
        # 单节共创：按 data-ib-id 只替那一节，其余节硬隔离
        from core.insight_board import board_html_save_section
        section_id = str(args.get("section_id", "")).strip()
        html_arg = str(args.get("html", ""))
        result = board_html_save_section(ctx.task_id, section_id, html_arg)
        if result.get("ok"):
            audit_logger.info("[agent-engine] revise_insight_board_section task=%s tier=%s sec=%s rev=%s",
                              ctx.task_id, ctx.auth_tier, section_id, result.get("revision"))
        return {"ok": bool(result.get("ok")), "tool": name, "result": result}

    raise HTTPException(404, {"error": "unhandled_write", "message": f"未实现的写工具: {name}"})


@router.post("/api/agent-tools/cleanup")
def cleanup_agent_workspace(data: dict):
    """
    删除面板会话时联动清理其智能体工作区（方案 D5 修订：数据留痕不只进不出）。

    body: {chat_session_id?, task_id?}；优先按 chat_session_id 定位（与写入时 workspace_key 一致）。
    仅删 agent-workspace/<engine_id>/<key>/（resolve 后必须位于 WORKSPACE_ROOT 下，防穿越）。
    CLI 自身会话存于 ~/.qoder，属外部二进制私有域，软件不触碰（§3.10-②）。
    """
    from app.store import get_chat_engine_config
    from core.cli_engine import cleanup_workspace

    key = str((data or {}).get("chat_session_id") or (data or {}).get("task_id") or "").strip()
    if not key:
        raise HTTPException(400, {"error": "missing_key", "message": "需要 chat_session_id 或 task_id"})
    engine_id = get_chat_engine_config()["engine_id"]
    cleanup_workspace(engine_id, key[:128])
    return {"ok": True, "cleaned": key[:128]}
