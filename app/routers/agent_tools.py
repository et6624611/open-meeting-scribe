"""
app/routers/agent_tools.py — 智能体反向工具调用端点 / Agent reverse tool-invocation endpoint

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

POST /api/agent-tools/invoke  {name, arguments}
  - 鉴权：Authorization: Bearer <短时令牌>（core.agent_tools.tokens 进程内注册表）
  - 读工具 → core.agent_loop.execute_tool（与内置 Agent 循环同一实现）
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

    tool = TOOLS_BY_NAME.get(payload.name)
    if not tool:
        raise HTTPException(404, {"error": "unknown_tool", "message": f"未知工具: {payload.name}"})

    # 授权档位：写工具要求可写档
    if tool["kind"] == "write" and not ctx.writable:
        raise HTTPException(403, {"error": "read_only",
                                  "message": f"当前授权档（{ctx.auth_tier}）为只读，禁止写操作 {payload.name}"})

    args = payload.arguments or {}

    # ── 读工具：复用内置 agent 循环的 execute_tool ──
    if tool["kind"] == "read":
        from core.agent_loop import execute_tool
        result = execute_tool(payload.name, args, task_id=ctx.task_id, project_id=ctx.project_id)
        return {"ok": True, "tool": payload.name, "result": result}

    # ── 写工具：复用 notes 路由既有受控函数（继承落盘 + 脏标记） ──
    return _dispatch_write(payload.name, args, ctx)


def _dispatch_write(name: str, args: dict, ctx) -> dict:
    from app.routers.notes import (
        InjectRequest,
        NotesUpdate,
        inject_content,
        update_task_summary,
    )

    if not ctx.task_id:
        raise HTTPException(400, {"error": "no_task", "message": "写操作需要关联具体会议任务"})

    if name == "update_summary":
        summary = str(args.get("summary", ""))[:20000]
        res = update_task_summary(ctx.task_id, NotesUpdate(notes=summary))
        logger.info("[agent-tools] update_summary task=%s len=%d", ctx.task_id, len(summary))
        audit_logger.info("[agent-engine] update_summary task=%s tier=%s chars=%d",
                          ctx.task_id, ctx.auth_tier, len(summary))
        return {"ok": True, "tool": name, "result": {"updated": True, "chars": len(summary)}, "echo": res}

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
            injected.append(r.get("item", {}).get("id"))
        logger.info("[agent-tools] inject_items task=%s n=%d", ctx.task_id, len(injected))
        audit_logger.info("[agent-engine] inject_items task=%s tier=%s count=%d",
                          ctx.task_id, ctx.auth_tier, len(injected))
        return {"ok": True, "tool": name, "result": {"injected": len(injected), "ids": injected}}

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
