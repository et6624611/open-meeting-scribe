"""
app/routers/insights.py — AI 洞察路由端点 / AI insights route endpoints

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-17
版本 / Version: 2.2.0

提供综合洞察分析 REST 端点 / Provide unified insight analysis REST endpoint.
洞察消息按会议（task）持久化存储 / Insight messages persisted per meeting (task).
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.settings_store import load_settings
from core.insights import run_analysis as core_run_analysis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insights"])

# 洞察消息存储目录（与 task 数据同目录） / Insight message storage dir (same as task data)
TASKS_DIR = Path("data/tasks")


# ============================================================
# 请求模型 / Request Models
# ============================================================

class InsightAnalysisRequest(BaseModel):
    """洞察分析请求 / Insight analysis request."""
    recent_lines: list[dict]   # [{text, speaker_id, begin_time}]
    chapter_titles: list[str]


# ============================================================
# 分析端点 / Analysis Endpoints
# ============================================================

@router.post("/api/insights/analyze")
async def analyze_endpoint(data: InsightAnalysisRequest):
    """
    统一洞察分析端点 / Unified insight analysis endpoint.

    接收最近转写内容和章节标题，调用 LLM 执行综合洞察分析 / Receive recent transcript and chapter titles; call LLM for unified insight analysis.
    自动注入当前激活角色，使洞察 prompt 感知角色视角 / Auto-inject active agent role so insight prompts are role-aware.
    返回结构化结果 / Return structured result: {title, body, solution, has_finding, diagram, graph}
    """
    if not data.recent_lines or not data.chapter_titles:
        return {"title": "", "body": "", "solution": "", "has_finding": False, "diagram": "", "graph": None}

    # 读取当前激活角色 / Read current active agent
    settings = load_settings()
    active_role = settings.get("active_agent")

    result = await core_run_analysis(
        data.recent_lines,
        data.chapter_titles,
        role_name=active_role,
    )
    return result


# ============================================================
# 洞察消息持久化（按会议隔离） / Insight message persistence (per-meeting isolation)
# ============================================================

def _insights_file(task_id: str) -> Path:
    """获取指定会议的洞察消息存储路径 / Get insight message storage path for a meeting."""
    return TASKS_DIR / f"{task_id}.insights.json"


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
    """
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    messages = data.get("messages", [])
    try:
        f = _insights_file(task_id)
        f.write_text(
            json.dumps({"messages": messages}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return {"ok": True, "count": len(messages)}
    except Exception as e:
        logger.error("保存会议 %s 洞察消息失败: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))
