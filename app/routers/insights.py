"""
app/routers/insights.py — AI 洞察路由端点 / AI insights route endpoints

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-30
版本 / Version: 3.0.0

洞察消息按会议（task）持久化存储 / Insight messages persisted per meeting (task).
洞察板：板生成/修订由会话工具（agent tools）服务端单一写入，前端只读重拉
（契约见 core/insight_board.py 与角色 insights.md）。

【已退役】无状态 /analyze 与会后补分析 /analyze/task 端点随「洞察共创 · 会话驱动」
一并下线：洞察卡片与板的产生/修订改由会话面板中的 agent 工具链完成。
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.store import tasks
from core.insight_board import (
    board_html_load,
    board_html_meta,
)
from core.insight_budget import apply_budget, normalize_factor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insights"])

# 洞察消息存储目录（与 task 数据同目录） / Insight message storage dir (same as task data)
TASKS_DIR = Path("data/tasks")

# ============================================================
# 洞察消息持久化（按会议隔离） / Insight message persistence (per-meeting isolation)
# ============================================================

def _insights_file(task_id: str) -> Path:
    """获取指定会议的洞察消息存储路径 / Get insight message storage path for a meeting."""
    return TASKS_DIR / f"{task_id}.insights.json"


def _load_insight_messages(task_id: str) -> list[dict]:
    """读取洞察消息列表（文件缺失/损坏返回空） / Load insight messages (empty on missing/corrupt)."""
    f = _insights_file(task_id)
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return list(data.get("messages", []))
    except Exception:
        return []


@router.get("/api/insights/messages/{task_id}")
async def get_insight_messages(task_id: str):
    """
    加载指定会议的洞察消息列表 / Load insight messages for a meeting.
    """
    f = _insights_file(task_id)
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
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    messages = data.get("messages", [])
    try:
        task = tasks.get(task_id)
        factor = normalize_factor((task.get("one_page") or {}).get("insights", 1)) if task else 1.0
        messages = apply_budget(messages, factor)
        f = _insights_file(task_id)
        f.write_text(
            json.dumps({"messages": messages}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return {"ok": True, "count": len(messages), "messages": messages}
    except Exception as e:
        logger.error("保存会议 %s 洞察消息失败: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 洞察板 / Insight Board endpoint
# 单一写入源在服务端（会话工具 revise_insight_board*），前端只读重拉。
# ============================================================

@router.get("/api/insights/board/{task_id}")
async def get_board(task_id: str, meta: str = ""):
    """读取会议洞察板（HTML 产物）/ Load board artifact.

    返回 / Returns: {html, revision, updated_at}；无板返回 {html: null, revision: 0}。
    meta=1 时只返版本（{revision, updated_at, exists}、几十字节、不含正文），
    供前端洞察 Tab 轮询比对版用（AI 在别的窗口写板也能被发现）。
    旧 Board Spec JSON 契约已随共创 HTML 模式退役（存量 .board.json 不迁移、不再呈现）。
    """
    if meta and meta != "0":
        return board_html_meta(task_id) or {"revision": 0, "updated_at": None, "exists": False}
    artifact = board_html_load(task_id)
    return artifact or {"html": None, "revision": 0, "updated_at": None}
