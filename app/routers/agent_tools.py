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
from pydantic import BaseModel, Field

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
    logger.info("[agent-tools] invoke name=%s task_id=%s args_keys=%s",
                payload.name, ctx.task_id, list(payload.arguments.keys()))

    tool = TOOLS_BY_NAME.get(payload.name)
    if not tool:
        raise HTTPException(404, {"error": "unknown_tool", "message": f"未知工具: {payload.name}"})

    # 授权档位：写工具要求可写档；revise_insight_board 无正文时为读语义，只读档放行。
    # html 是过渡兼容字段，也必须参与写操作判定，避免只读档绕过门禁。
    args = payload.arguments or {}
    if tool["kind"] == "write" and not ctx.writable:
        has_board_content = any(str(args.get(key) or "").strip() for key in ("markdown", "html"))
        is_board_read = payload.name == "revise_insight_board" and not has_board_content
        if not is_board_read:
            raise HTTPException(403, {"error": "read_only",
                                      "message": f"当前授权档（{ctx.auth_tier}）为只读，禁止写操作 {payload.name}"})

    # ── 读工具：会议域工具唯一实现（core/agent_tools/impl.py） ──
    if tool["kind"] == "read":
        from core.agent_tools.impl import execute_tool
        result = execute_tool(payload.name, args, task_id=ctx.task_id, project_id=ctx.project_id)
        return {"ok": True, "tool": payload.name, "result": result}

    # ── 写工具：复用 notes 路由既有受控函数（继承落盘 + 脏标记） ──
    return _dispatch_write(payload.name, args, ctx)


def _dispatch_write(name: str, args: dict, ctx) -> dict:
    import copy

    from core import notes_service
    from core import rewrite_snapshots as rsv
    from core.task_store import tasks

    if not ctx.task_id:
        raise HTTPException(400, {"error": "no_task", "message": "写操作需要关联具体会议任务"})

    turn_id = getattr(ctx, "turn_id", "") or ""

    def _find_node(node_id: str) -> dict | None:
        task = tasks.get(ctx.task_id) or {}
        for t in task.get("decisions") or []:
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
        res = notes_service.update_summary(ctx.task_id, summary)
        logger.info("[agent-tools] update_summary task=%s len=%d", ctx.task_id, len(summary))
        audit_logger.info("[agent-engine] update_summary task=%s tier=%s chars=%d restorable=%s",
                          ctx.task_id, ctx.auth_tier, len(summary), restorable)
        return {"ok": True, "tool": name, "result": {"updated": True, "chars": len(summary),
                                                     "restorable": restorable},
                "echo": {"notes": res}}

    if name == "inject_items":
        items = args.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(400, {"error": "bad_items", "message": "items 必须是非空数组"})
        injected = []
        for it in items[:50]:  # 单轮上限，防刷屏（方案 §3.9-7）
            itype = str(it.get("type", "")).strip()
            content = str(it.get("content", "")).strip()
            if itype not in ("decision", "conclusion", "decision") or not content:
                continue
            item = notes_service.inject_item(ctx.task_id, itype, content, "agent-engine")
            item_id = item.get("id")
            injected.append(item_id)
            # decision/decision 会同时开一个决策流节点（id 与注入条目一致）：快照“此前不存在”，
            # 撤销本轮即等价于删掉新建节点；conclusion 不开节点，无需快照
            if itype in ("decision", "decision") and item_id:
                _snapshot(rsv.decision_node_target(str(item_id)), None, absent=True)
        logger.info("[agent-tools] inject_items task=%s n=%d", ctx.task_id, len(injected))
        audit_logger.info("[agent-engine] inject_items task=%s tier=%s count=%d",
                          ctx.task_id, ctx.auth_tier, len(injected))
        return {"ok": True, "tool": name, "result": {"injected": len(injected), "ids": injected,
                                                     "restorable": True}}

    if name == "update_decision_node":
        # 决策节点改写：按节点 id 寻址，收口 notes.update_decision 同一口径（状态字典校验/脏标记/落盘）
        node_id = str(args.get("node_id", "")).strip()
        if not node_id:
            raise HTTPException(400, {"error": "missing_node_id",
                                      "message": "需要 node_id（先调 get_meeting_decisions 取节点 id）"})
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
                                          "message": f"{exc}（status 只能取 get_meeting_decisions 返回的 available_statuses 中的 id）"})
        # 先过字段校验（超长/条目超限回 400），再落快照：被拒的写不留空快照
        try:
            notes_service.validate_patch(patch)
        except notes_service.NotesServiceError as exc:
            raise HTTPException(400, {"error": "bad_patch", "message": f"字段不合法：{exc.message}"})
        restorable = _snapshot(rsv.decision_node_target(node_id), copy.deepcopy(node))
        try:
            decision = notes_service.update_decision(ctx.task_id, node_id, patch)
        except notes_service.NotesServiceError as exc:
            raise HTTPException(422, {"error": "bad_patch", "message": exc.message})
        logger.info("[agent-tools] update_decision_node task=%s node=%s fields=%s",
                    ctx.task_id, node_id, ",".join(patch))
        audit_logger.info("[agent-engine] update_decision_node task=%s tier=%s node=%s fields=%s status=%s",
                          ctx.task_id, ctx.auth_tier, node_id, ",".join(patch), decision.get("status"))
        return {"ok": True, "tool": name,
                "result": {"updated": True, "node_id": node_id,
                           "status": decision.get("status"), "title": decision.get("title"),
                           "restorable": restorable},
                "echo": {"decision": decision}}

    if name == "delete_decision_node":
        node_id = str(args.get("node_id", "")).strip()
        if not node_id:
            raise HTTPException(400, {"error": "missing_node_id",
                                      "message": "需要 node_id（先调 get_meeting_decisions 取节点 id）"})
        node = _find_node(node_id)
        if node is None:
            raise HTTPException(404, {"error": "node_not_found",
                                      "message": f"决策节点不存在：{node_id}"})
        restorable = _snapshot(rsv.decision_node_target(node_id), copy.deepcopy(node))
        notes_service.delete_decision(ctx.task_id, node_id)  # auto 节点同步落防复活墓碑
        logger.info("[agent-tools] delete_decision_node task=%s node=%s", ctx.task_id, node_id)
        audit_logger.info("[agent-engine] delete_decision_node task=%s tier=%s node=%s restorable=%s",
                          ctx.task_id, ctx.auth_tier, node_id, restorable)
        return {"ok": True, "tool": name,
                "result": {"deleted": True, "node_id": node_id, "restorable": restorable},
                "echo": {"ok": True}}

    if name == "create_insight_board":
        # 建板提案（与 propose_summary/propose_notes 同构）：后端不碰磁盘。
        # 新板只能在用户点「接受」后经 POST /api/insights/board/{task_id}/boards 建立，
        # 因此本分支的审计措辞也写“未落盘,待用户确认”，便于回溯是谁点的接受。
        from core.insight_board import BOARD_TITLE_MAX
        title = str(args.get("title") or "").strip()[:BOARD_TITLE_MAX]
        if not title:
            raise HTTPException(400, {"error": "title_required",
                                      "message": "新板标题必填（create_insight_board 只提案，不落盘）"})
        logger.info("[agent-tools] create_insight_board task=%s title=%s", ctx.task_id, title)
        audit_logger.info("[agent-engine] create_insight_board task=%s tier=%s title=%s (未落盘,待用户确认)",
                          ctx.task_id, ctx.auth_tier, title)
        return {"ok": True, "tool": name,
                "result": {"proposed": True, "title": title,
                           "board_id": str(args.get("board_id") or "").strip(),
                           "note": "已作为待确认建板提案展示给用户，未经用户点「接受」不会新建任何板"}}

    if name == "revise_insight_board":
        # 洞察共创 Markdown：唯一实现与内置引擎共享（core.insight_board.invoke_revise_board）
        from core.insight_board import invoke_revise_board
        result = invoke_revise_board(ctx.task_id, args)
        board_content = args.get("markdown") or args.get("html")
        if board_content and result.get("ok"):
            audit_logger.info("[agent-engine] revise_insight_board task=%s tier=%s board=%s chars=%d rev=%s removed=%s",
                              ctx.task_id, ctx.auth_tier, result.get("board_id"),
                              len(str(board_content)), result.get("revision"),
                              result.get("removed") or "-")
        return {"ok": bool(result.get("ok")), "tool": name, "result": result}

    if name == "revise_insight_board_section":
        # 单节共创：按 data-ib-id 只替那一节，其余节硬隔离；多板下按 board_id 定位
        from core.insight_board import board_html_save_section
        section_id = str(args.get("section_id", "")).strip()
        html_arg = str(args.get("html", ""))
        bid = str(args.get("board_id") or "").strip() or None
        result = board_html_save_section(ctx.task_id, section_id, html_arg, bid)
        if result.get("ok"):
            audit_logger.info("[agent-engine] revise_insight_board_section task=%s tier=%s board=%s sec=%s rev=%s",
                              ctx.task_id, ctx.auth_tier, result.get("board_id"), section_id,
                              result.get("revision"))
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
    from core.cli_engine import cleanup_workspace
    from core.settings_store import get_chat_engine_config

    key = str((data or {}).get("chat_session_id") or (data or {}).get("task_id") or "").strip()
    if not key:
        raise HTTPException(400, {"error": "missing_key", "message": "需要 chat_session_id 或 task_id"})
    engine_id = get_chat_engine_config()["engine_id"]
    cleanup_workspace(engine_id, key[:128])
    return {"ok": True, "cleaned": key[:128]}
