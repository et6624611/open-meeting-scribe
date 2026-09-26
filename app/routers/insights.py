"""
app/routers/insights.py — AI 洞察路由端点 / AI insights route endpoints

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-25
版本 / Version: 2.3.0

提供综合洞察分析 REST 端点 / Provide unified insight analysis REST endpoint.
洞察消息按会议（task）持久化存储 / Insight messages persisted per meeting (task).
会后补分析基于任务全文在服务端构造输入并追加快照落盘（REQ-INSIGHT-DECK-POSTMEETING R2）。
"""

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.settings_store import load_settings
from app.store import tasks
from core.fs_atomic import atomic_write_json
from core.insights import run_analysis as core_run_analysis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insights"])

# 洞察消息存储目录（与 task 数据同目录） / Insight message storage dir (same as task data)
TASKS_DIR = Path("data/tasks")

# 会后补分析取样窗口（句）：取全文时间序最近 K 句 / Post-meeting sample window: latest K sentences
POST_ANALYSIS_MAX_LINES = int(os.getenv("OMS_INSIGHTS_POST_K", "40"))

# 会后补分析超时守护（秒）：超时返回 504 且不写盘 / Post-meeting timeout guard (504, no persist)
POST_ANALYSIS_TIMEOUT_SECONDS = float(os.getenv("OMS_INSIGHTS_POST_TIMEOUT", "60"))

# 同任务并发守卫：正在分析中的 task_id 集合（单事件循环内 check+add 无 await，原子）
# In-flight guard: task ids currently analyzing (check+add is atomic in one loop)
_post_analysis_running: set[str] = set()


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


def _flatten_dialogue_lines(task: dict) -> list[dict]:
    """将任务 dialogue 展平为时间序 [{text, speaker_id, begin_time}] / Flatten task dialogue to time-ordered transcript lines."""
    lines: list[dict] = []
    for item in task.get("dialogue") or []:
        sid = item.get("speaker_id", 0) or 0
        sents = item.get("sentences") or []
        for s in sents:
            text = (s.get("text") or "").strip()
            if text:
                lines.append({"text": text, "speaker_id": sid, "begin_time": s.get("begin_time", 0) or 0})
        if not sents:
            text = (item.get("text") or "").strip()
            if text:
                lines.append({"text": text, "speaker_id": sid, "begin_time": 0})
    lines.sort(key=lambda l: l["begin_time"])
    return lines


@router.post("/api/insights/analyze/task/{task_id}")
async def analyze_task_endpoint(task_id: str):
    """
    会后补分析端点 / Post-meeting analysis endpoint.

    服务端从任务 JSON 读取完整 dialogue 与章节，自行构造分析输入（最近 K 句），
    Server builds analysis input from the task's full dialogue and chapters (latest K lines);
    有发现时由后端追加快照落盘（phase=post_meeting），前端以重拉方式刷新，
    appends the snapshot server-side (phase=post_meeting) on finding; frontend reloads,
    规避前端全量覆盖保存的交叉竞态 / avoiding the frontend full-overwrite save race.
    幂等契约（v0.2.0）：同任务分析进行中再调→409；整体超时守护 60s→504 且不写盘。
    Idempotency: 409 while an analysis for the same task is in flight; 504 (no persist) on timeout.
    返回 / Returns: {result, messages}
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"error": "task_not_found", "message": "会议任务不存在"})
    if task.get("status") != "completed":
        raise HTTPException(status_code=400, detail={"error": "task_not_completed", "message": "会议尚未完成，无法执行会后洞察分析"})

    # 并发守卫：只防同时、不防先后（多次成功分析追加多批消息属预期）
    # Guard against concurrent runs only — repeated successful analyses append (expected)
    if task_id in _post_analysis_running:
        raise HTTPException(status_code=409, detail={"error": "analysis_in_flight", "message": "该会议正在分析中，请稍候"})
    _post_analysis_running.add(task_id)

    try:
        all_lines = _flatten_dialogue_lines(task)
        chapter_titles = [str(c.get("title", "")).strip() for c in task.get("chapters") or [] if c.get("title")]
        if not all_lines or not chapter_titles:
            raise HTTPException(status_code=400, detail={"error": "insufficient_content", "message": "转写内容或章节不足，无法执行会后洞察分析"})

        # 与无状态 /analyze 端点对等：注入当前激活角色 / Parity with stateless /analyze: role-aware prompt
        settings = load_settings()
        active_role = settings.get("active_agent")

        try:
            result = await asyncio.wait_for(
                core_run_analysis(
                    all_lines[-POST_ANALYSIS_MAX_LINES:],
                    chapter_titles,
                    role_name=active_role,
                ),
                timeout=POST_ANALYSIS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # 超时不写盘 / Timeout never persists
            logger.warning("[洞察台] 会后补分析超时 task=%s (%.0fs)", task_id, POST_ANALYSIS_TIMEOUT_SECONDS)
            raise HTTPException(status_code=504, detail={"error": "analysis_timeout", "message": "分析超时，请稍后重试"})

        messages = _load_insight_messages(task_id)
        if result.get("has_finding") and result.get("title"):
            new_msg = {
                "id": f"post-{uuid.uuid4().hex[:12]}",
                "title": result["title"],
                "body": result.get("body", ""),
                "actions": [],
                "timestamp": int(time.time() * 1000),
                "source": "system",
                "read": False,
                "category": "",
                "solution": result.get("solution", ""),
                "expanded": False,
                "acknowledged": False,
                "phase": "post_meeting",
            }
            if result.get("diagram"):
                new_msg["diagram"] = result["diagram"]
            messages = messages + [new_msg]
            TASKS_DIR.mkdir(parents=True, exist_ok=True)
            atomic_write_json(_insights_file(task_id), {"messages": messages})
            logger.info("[洞察台] 会后补分析落盘 task=%s title=%s", task_id, result["title"][:60])

        return {"result": result, "messages": messages}
    finally:
        _post_analysis_running.discard(task_id)


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
