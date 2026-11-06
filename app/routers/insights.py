"""
app/routers/insights.py — AI 洞察路由端点 / AI insights route endpoints

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-10-29
版本 / Version: 4.0.0

洞察消息按会议（task）持久化存储 / Insight messages persisted per meeting (task).
洞察板：板生成/修订由会话工具（agent tools）服务端单一写入，前端只读重拉
（契约见 core/insight_board.py 与角色 insights.md）。一场会议可有多份板，
但**建板权属于用户**：本路由的 POST .../boards 是唯一执行点，只由「＋ 新建板」
或提案被用户点「接受」触发；工具面对未知 board_id 一律拒写（不隐式建板）。

【版式归 CLI】板是一份 AI 直出的自包含 HTML（可带 doctype/<style>/<script>），
应用不再剥壳；前端用 sandbox iframe 呈现，raw 端点则必须用 CSP sandbox 自我约束
（见 get_board_raw）。

【已退役】无状态 /analyze 与会后补分析 /analyze/task 端点随「洞察共创 · 会话驱动」
一并下线：洞察卡片与板的产生/修订改由会话面板中的 agent 工具链完成。
"""

import json
import logging
import webbrowser
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from core import task_store
from core.insight_board import (
    board_html_load,
    board_html_meta,
    boards_manifest,
    invoke_create_board,
)
from core.insight_budget import apply_budget, insights_file, normalize_factor
from core.task_store import tasks

logger = logging.getLogger(__name__)
# 语义审计专用（与 server.py 的 audit 同名 logger 共享 logs/audit.log handler）
audit_logger = logging.getLogger("audit")

router = APIRouter(tags=["insights"])

# ============================================================
# 洞察消息持久化（按会议隔离） / Insight message persistence (per-meeting isolation)
# ============================================================
# T-24：路径与读取口径统一由 core.insight_budget 提供，tasks 路由不再跨 router 反查。

@router.get("/api/insights/messages/{task_id}")
async def get_insight_messages(task_id: str):
    """
    加载指定会议的洞察消息列表 / Load insight messages for a meeting.
    """
    f = insights_file(task_id)
    if not f.exists():
        return {"messages": []}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return {"messages": data.get("messages", [])}
    except Exception as e:
        logger.warning("加载会议 %s 洞察消息失败: %s", task_id, e)
        return {"messages": []}


@router.post("/api/insights/messages/{task_id}")
async def save_insight_messages(task_id: str, data: dict):
    """
    保存指定会议的洞察消息列表 / Save insight messages for a meeting.
    请求体 / Body: {"messages": [...]}
    写盘前按 task.one_page.insights 系数执行预算重排；
    任务不存在时按系数 1 处理（旧任务兼容口径）。
    """
    task_store.TASKS_DIR.mkdir(parents=True, exist_ok=True)
    messages = data.get("messages", [])
    try:
        task = tasks.get(task_id)
        factor = normalize_factor((task.get("one_page") or {}).get("insights", 1)) if task else 1.0
        messages = apply_budget(messages, factor)
        f = insights_file(task_id)
        f.write_text(
            json.dumps({"messages": messages}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return {"ok": True, "count": len(messages), "messages": messages}
    except Exception as e:
        logger.error("保存会议 %s 洞察消息失败: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 洞察板 / Insight Board endpoints
# 单一写入源在服务端（会话工具 revise_insight_board*），前端只读重拉。
# ============================================================

# raw 出口的 CSP：板经 srcdoc 渲染时是 opaque origin（Origin: null），被 server.py 的
# 写请求 Origin 守卫拦住；但 raw 端点是**站内同源文档**，那守卫在此失效（带真实宿主 origin）。
# 因此 `Content-Security-Policy: sandbox` 是裸 HTML 出口的唯一防线，不可省。
# sandbox 指令在 Chrome 与 WebKit（pywebview/WKWebView）均受支持；allow-scripts 保留
# 板内交互能力，但不给 allow-same-origin，从而落回 opaque origin。
BOARD_RAW_CSP = "sandbox allow-scripts"


@router.get("/api/insights/board/{task_id}")
async def get_board(task_id: str, meta: str = "", board_id: str = ""):
    """读取会议洞察板（HTML 产物）/ Load board artifact.

    返回 / Returns: {html, revision, updated_at, board_id, title}；无板返回 {html: null, revision: 0}。
    board_id 缺省取 manifest 的 default_board_id。
    meta=1 时只返版本（含全部板的 revision 列表，不含正文），
    供前端洞察 Tab 轮询比对版用（AI 在别的窗口写板也能被发现）。
    旧 Board Spec JSON 契约已随共创 HTML 模式退役（存量 .board.json 不迁移、不再呈现）。
    """
    bid = board_id.strip() or None
    if meta and meta != "0":
        m = board_html_meta(task_id, bid) or {
            "revision": 0, "updated_at": None, "exists": False,
            "boards": [], "default_board_id": "main"}
        return m
    artifact = board_html_load(task_id, bid)
    return artifact or {"html": None, "revision": 0, "updated_at": None,
                        "board_id": bid or "", "title": ""}


@router.get("/api/insights/board/{task_id}/boards")
async def list_boards(task_id: str):
    """列出本场会议的全部板（manifest）/ List boards manifest for the meeting.

    返回 / Returns: {boards: [{board_id,title,revision,updated_at,exists}], default_board_id}。
    前端板 tab 轨与轮询都只读这里（一次请求拿全部版本）。
    """
    return boards_manifest(task_id)


@router.post("/api/insights/board/{task_id}/boards")
async def create_board(task_id: str, payload: dict):
    """建板唯一执行点（只写 manifest 条目，不产生 HTML）/ Create a board entry (user intent only).

    body: {title（必填）, board_id?（缺省服务端生成 board-2/board-3…）}。
    调用方只能是用户意志的出口：前端「＋ 新建板」，或 create_insight_board 提案
    被点「接受」后的同一个端点。AI 单方面调用本端点不算“用户显式新建”，
    因此会话侧必须经确认卡而不是直接 HTTP。
    审计落盘区分两条通道（source=ui|proposal），便于回溯是谁点的。
    """
    payload = payload or {}
    source = str(payload.get("source") or "ui").strip()[:20]
    result = invoke_create_board(task_id, payload)
    if not result.get("ok"):
        code = 400 if result.get("error") in ("title_required", "invalid_board_id",
                                              "invalid_task_id") else 409
        raise HTTPException(code, result)
    audit_logger.info(
        "[board] CREATE_BOARD | task=%s board=%s title=%s source=%s",
        task_id, result.get("board_id"), result.get("title"), source)
    return {"ok": True, **result}


@router.get("/api/insights/board/{task_id}/raw", response_class=HTMLResponse)
async def get_board_raw(task_id: str, board_id: str = "", rev: str = ""):
    """原始出口：直回磁盘字节 / Serve the raw board HTML as authored by the CLI.

    必须带 `Content-Security-Policy: sandbox allow-scripts`（理由见 BOARD_RAW_CSP 注释）。
    rev 非空且与当前 revision 不一致时回 409：避免“用户以为在看 A 版，实际拿到的是轮询间隙的新版”。
    """
    bid = board_id.strip() or None
    artifact = board_html_load(task_id, bid)
    if not artifact or not artifact.get("html"):
        raise HTTPException(404, {"error": "no_board", "message": "该会议尚无洞察板内容"})
    if rev.strip() and rev.strip().isdigit() and int(rev) != int(artifact.get("revision") or 0):
        raise HTTPException(409, {"error": "revision_moved",
                                  "message": f"板已前进到 rev {artifact.get('revision')}，请刷新后重开",
                                  "current_revision": artifact.get("revision")})
    return HTMLResponse(content=artifact["html"],
                        headers={"Content-Security-Policy": BOARD_RAW_CSP,
                                 "X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "no-store"})


@router.post("/api/insights/board/{task_id}/open")
async def open_board(task_id: str, request: Request, payload: dict):
    """在系统浏览器里打开洞察板浏览页 / Open the board viewer in the system browser.

    为什么不是直接打开 raw：板里的 mermaid 主视觉靠应用侧渲染（桥接脚本把源码 postMessage
    给父页、父页渲成 SVG 再回传），raw 只回磁盘字节、不注入任何东西，因此在浏览器里直接
    打开 raw 会看到 flowchart 源码而不是图，也拿不到主题令牌。浏览页（/board/{task_id}）
    复用同一个 InsightBoard 组件：图正常渲染、主题跟随，而板仍在 sandbox iframe 内，
    安全边界不因“换个入口”而下降。

    走后端而非 window.open：pywebview 里 window.open 不可靠。跳转目标由本端按 task_id
    自行拼接，不接受客户端传入 URL，避免本端点变成开放重定向器。
    """
    bid = str((payload or {}).get("board_id") or "").strip()
    qs = f"?board_id={quote(bid)}" if bid else ""
    viewer_path = f"/board/{task_id}{qs}"
    absolute = str(request.base_url).rstrip("/") + viewer_path
    opened = webbrowser.open(absolute)
    audit_logger.info(
        "[board] OPEN_VIEWER | task=%s url=%s opened=%s", task_id, absolute, opened)
    return {"ok": bool(opened), "url": absolute}
