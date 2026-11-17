"""
app/routers/insights.py — AI 洞察路由端点 / AI insights route endpoints

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-11-12
版本 / Version: 5.0.0

洞察板：一场会议一份 Markdown 文件（data/tasks/{task_id}.insight.md）。
不再多板、不再会中实时 insights.json。
板生成/修订由会话工具（agent tools）服务端单一写入，前端只读重拉。

【版式归 CLI】板是一份 AI 直出的 GFM Markdown，前端用常规 Markdown 渲染器呈现
（mermaid 图从 ```mermaid fence 渲染为 SVG）。不再 sandbox iframe + 原始 HTML 桥接。

存量 HTML 板首次被访问时会自动迁移为 insight.md（合并多板主板 + 转 md）。

【会中实时已退役】messages 端点保留兼容（返回空数组），不再被前端调用。
"""

import logging
import webbrowser

from fastapi import APIRouter, HTTPException, Request

from core.insight_board import (
    board_md_load,
    board_md_meta,
    boards_manifest,
    migrate_legacy_html_to_md,
)

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")

router = APIRouter(tags=["insights"])


# ============================================================
# 洞察板 / Insight Board endpoints
# ============================================================

@router.get("/api/insights/board/{task_id}")
async def get_board(task_id: str, meta: str = "", board_id: str = ""):
    """读取会议洞察板（Markdown 产物）/ Load insight board artifact.

    返回 / Returns: {markdown, revision, updated_at, board_id, title}；
    无板或尚未生成为 {markdown: null, revision: 0}。
    meta=1 时只返版本（含 boards 固定数组），供前端洞察 Tab 轮询比对。
    """
    # 首次访问触发存量迁移
    migrate_legacy_html_to_md(task_id)

    if meta and meta != "0":
        return board_md_meta(task_id) or {"revision": 0, "updated_at": None,
                                          "exists": False, "board_id": "main"}
    artifact = board_md_load(task_id)
    if artifact is None:
        return {"markdown": None, "revision": 0, "updated_at": None,
                "board_id": "main", "title": "主看板"}
    return {
        "markdown": artifact["markdown"],
        "revision": artifact["revision"],
        "updated_at": artifact["updated_at"],
        "board_id": artifact["board_id"],
        "title": artifact["title"],
    }


@router.get("/api/insights/board/{task_id}/boards")
async def list_boards(task_id: str):
    """固定单板。前端 tab 轨可直接隐藏（只有一份）。"""
    migrate_legacy_html_to_md(task_id)
    return boards_manifest(task_id)


@router.post("/api/insights/board/{task_id}/boards")
async def create_board(task_id: str, payload: dict):
    """废弃：不再支持多板拆分。"""
    raise HTTPException(405, {"error": "multi_board_deprecated",
                              "info": "洞察板已改为一场会议一份，不再支持多板"})


@router.get("/api/insights/board/{task_id}/raw")
async def get_board_raw(task_id: str, board_id: str = "", rev: str = ""):
    """原始 Markdown 直出（供调试/复制）。"""
    migrate_legacy_html_to_md(task_id)
    artifact = board_md_load(task_id)
    if not artifact or not artifact.get("markdown"):
        raise HTTPException(404, {"error": "no_board", "message": "该会议尚无洞察板内容"})
    if rev.strip() and rev.strip().isdigit() and int(rev) != int(artifact.get("revision") or 0):
        raise HTTPException(409, {"error": "revision_moved",
                                  "message": f"板已前进到 rev {artifact.get('revision')}，请刷新后重开",
                                  "current_revision": artifact.get("revision")})
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=artifact["markdown"],
                              headers={"X-Content-Type-Options": "nosniff",
                                       "Cache-Control": "no-store"})


@router.post("/api/insights/board/{task_id}/open")
async def open_board(task_id: str, request: Request, payload: dict):
    """在系统浏览器里打开洞察板浏览页。"""
    viewer_path = f"/board/{task_id}"
    absolute = str(request.base_url).rstrip("/") + viewer_path
    opened = webbrowser.open(absolute)
    audit_logger.info("[board] OPEN_VIEWER | task=%s url=%s opened=%s", task_id, absolute, opened)
    return {"ok": bool(opened), "url": absolute}


# ============================================================
# 会中实时洞察（已退役，返回空数组保持兼容）
# ============================================================

@router.get("/api/insights/messages/{task_id}")
async def get_insight_messages(task_id: str):
    """已退役：会中实时洞察链路已关闭。始终返回空。"""
    return {"messages": []}


@router.post("/api/insights/messages/{task_id}")
async def save_insight_messages(task_id: str, data: dict):
    """已退役：写入静默忽略。"""
    return {"ok": True, "count": 0, "messages": []}
