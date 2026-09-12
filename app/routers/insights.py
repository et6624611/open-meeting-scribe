"""
app/routers/insights.py — AI 洞察路由端点

作者：王永亮
创建：2026-09-12
更新：2026-09-12
版本：2.1.0

提供洞察分析 REST 端点：上下文关联、盲点揭示、共识提炼。
洞察消息按会议（task）持久化存储。
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.insights import run_analysis as core_run_analysis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insights"])

# 洞察消息存储目录（与 task 数据同目录）
TASKS_DIR = Path("data/tasks")


# ============================================================
# 请求模型
# ============================================================

class InsightAnalysisRequest(BaseModel):
    """洞察分析请求"""
    recent_lines: list[dict]   # [{text, speaker_id, begin_time}]
    chapter_titles: list[str]
    analysis_type: str = "context"  # context | blindspot | consensus


# ============================================================
# 分析端点
# ============================================================

@router.post("/api/insights/analyze")
async def analyze_endpoint(data: InsightAnalysisRequest):
    """
    统一洞察分析端点。

    接收最近转写内容、章节标题和分析类型，调用 LLM 执行深度分析。
    返回结构化结果：{title, body, solution, has_finding}
    """
    if not data.recent_lines or not data.chapter_titles:
        return {"title": "", "body": "", "solution": "", "has_finding": False}

    result = await core_run_analysis(
        data.recent_lines,
        data.chapter_titles,
        data.analysis_type,
    )
    return result


# ============================================================
# 洞察消息持久化（按会议隔离）
# ============================================================

def _insights_file(task_id: str) -> Path:
    """获取指定会议的洞察消息存储路径"""
    return TASKS_DIR / f"{task_id}.insights.json"


@router.get("/api/insights/messages/{task_id}")
async def get_insight_messages(task_id: str):
    """
    加载指定会议的洞察消息列表。
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
    保存指定会议的洞察消息列表。
    请求体：{"messages": [...]}
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
