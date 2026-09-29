"""
app/routers/insights.py — AI 洞察路由端点 / AI insights route endpoints

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-28
版本 / Version: 2.5.0

提供综合洞察分析 REST 端点 / Provide unified insight analysis REST endpoint.
洞察消息按会议（task）持久化存储 / Insight messages persisted per meeting (task).
会后补分析基于任务全文在服务端构造输入并追加快照落盘（REQ-INSIGHT-DECK-POSTMEETING R2）。
洞察板（Phase 2）：板生成/修订由服务端单一写入，前端只读重拉（契约见 docs/INSIGHT_BOARD_SPEC_v0.md）。
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
from core.insight_board import (
    board_html_load,
    board_html_meta,
)
from core.insight_board import (
    load_board as board_load,
)
from core.insight_board import (
    new_board as board_new,
)
from core.insight_board import (
    run_board_analysis as core_run_board_analysis,
)
from core.insight_board import (
    save_board as board_save,
)
from core.insight_budget import active_count, apply_budget, card_slots, normalize_factor
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

# 板分析并发守卫与超时守护 / Board analysis guard & timeout
# 超时预算默认 180s：本地推理实测 50s+，沿用卡片 60s 会频繁 504（见 2026-09-28 故障分析）
_board_running: set[str] = set()
BOARD_ANALYSIS_MAX_LINES = int(os.getenv("OMS_BOARD_ANALYSIS_K", "60"))
BOARD_ANALYSIS_TIMEOUT_SECONDS = float(os.getenv("OMS_BOARD_ANALYSIS_TIMEOUT", "180"))


# ============================================================
# 请求模型 / Request Models
# ============================================================

class InsightAnalysisRequest(BaseModel):
    """洞察分析请求 / Insight analysis request."""
    recent_lines: list[dict]   # [{text, speaker_id, begin_time}]
    chapter_titles: list[str]
    # 已有洞察卡片摘要（只读累进，可选） [{title, body}] / Existing insight cards (read-only progressive, optional)
    existing_insights: list[dict] | None = None
    # 一页纸系数换算的有效卡位（会中前端从 task.one_page.insights 读取后携带；
    # 缺省不注入预算块，向后兼容） / Card slots from per-meeting one-page factor; None keeps legacy behavior
    card_slots: int | None = None


# ============================================================
# 分析端点 / Analysis Endpoints
# ============================================================

@router.post("/api/insights/analyze")
async def analyze_endpoint(data: InsightAnalysisRequest):
    """
    统一洞察分析端点 / Unified insight analysis endpoint.

    接收最近转写内容和章节标题，调用 LLM 执行综合洞察分析 / Receive recent transcript and chapter titles; call LLM for unified insight analysis.
    自动注入当前激活角色，使洞察 prompt 感知角色视角 / Auto-inject active agent role so insight prompts are role-aware.
    返回结构化结果 / Return structured result: {title, body, solution, note, has_finding, diagram, graph}
    """
    if not data.recent_lines or not data.chapter_titles:
        return {"title": "", "body": "", "solution": "", "note": "", "has_finding": False, "diagram": "", "graph": None}

    # 读取当前激活角色 / Read current active agent
    settings = load_settings()
    active_role = settings.get("active_agent")

    # 一页纸系数：前端携带卡位时注入生成侧预算块（active 以既有卡片摘要条数计）
    card_budget = None
    if data.card_slots and data.card_slots > 0:
        card_budget = {"slots": int(data.card_slots), "active": len(data.existing_insights or [])}

    result = await core_run_analysis(
        data.recent_lines,
        data.chapter_titles,
        role_name=active_role,
        existing_insights=data.existing_insights,
        card_budget=card_budget,
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

        # 一页纸系数（会议级）：生成侧卡位约束 + 落盘前预算重排共用同一口径
        factor = normalize_factor((task.get("one_page") or {}).get("insights", 1))
        slots = card_slots(factor)
        messages = _load_insight_messages(task_id)
        card_budget = {"slots": slots, "active": active_count(messages)}

        try:
            result = await asyncio.wait_for(
                core_run_analysis(
                    all_lines[-POST_ANALYSIS_MAX_LINES:],
                    chapter_titles,
                    role_name=active_role,
                    card_budget=card_budget,
                ),
                timeout=POST_ANALYSIS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # 超时不写盘 / Timeout never persists
            logger.warning("[洞察台] 会后补分析超时 task=%s (%.0fs)", task_id, POST_ANALYSIS_TIMEOUT_SECONDS)
            raise HTTPException(status_code=504, detail={"error": "analysis_timeout", "message": "分析超时，请稍后重试"})

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
                # 备查注释层（三层信息写作）：旧结果无此字段，降级空串 / note layer, tolerant of legacy results
                "note": result.get("note", ""),
                "expanded": False,
                "acknowledged": False,
                "phase": "post_meeting",
            }
            if result.get("diagram"):
                new_msg["diagram"] = result["diagram"]
            # 落盘前统一预算重排：新卡超位时旧卡降级 deferred，与会中保存路径同门收口
            messages = apply_budget(messages + [new_msg], factor)
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
    写盘前按 task.one_page.insights 系数执行预算重排（会中累积路径与会后路径同门收口）；
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
# 洞察板（Phase 2） / Insight Board endpoints
# 单一写入源在服务端（与会后补分析同模型），前端只读重拉；
# 校验不合的 ops 整次丢弃，板保持上一 revision（原子容错，不降级）。
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


# 【已退役】板 LLM 生成端点：随「洞察共创 · 会话驱动（HTML 产物版）」下线，
# 路由注销、函数保留不删（数据与代码留痕）；生成/修订改经会话工具 revise_insight_board。
# @router.post("/api/insights/board/analyze/task/{task_id}")
async def analyze_board_endpoint(task_id: str):
    """
    板生成/修订端点 / Board generation & revision endpoint.

    服务端读任务全文构造输入（最近 K 句，默认 60），携带当前板摘要跑一轮 ops 生成；
    Server builds input from task content with current-board digest, runs one ops-generation round;
    ops 全部合法才应用并落盘（revision +1），任一非法整次丢弃不落盘。
    Apply & persist only when the whole op batch validates; otherwise the board keeps its last revision.
    返回 / Returns: {ok, board, changed, errors, failure_class, model_usage?, weak_model_hint?}；并发 409，超时 504。
    failure_class=input|schema|connect|unknown；失败时附执行方回显，schema+小模型档位时附切换建议（AI 算力入口治理）。
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"error": "task_not_found", "message": "会议任务不存在"})
    if task.get("status") != "completed":
        raise HTTPException(status_code=400, detail={"error": "task_not_completed", "message": "会议尚未完成，无法生成洞察板"})
    if task_id in _board_running:
        raise HTTPException(status_code=409, detail={"error": "board_in_flight", "message": "该会议洞察板正在修订中，请稍候"})
    _board_running.add(task_id)

    try:
        all_lines = _flatten_dialogue_lines(task)
        chapter_titles = [str(c.get("title", "")).strip() for c in task.get("chapters") or [] if c.get("title")]
        if not all_lines or not chapter_titles:
            raise HTTPException(status_code=400, detail={"error": "insufficient_content", "message": "转写内容或章节不足，无法生成洞察板"})

        # 无板先建骨架板，使首轮 ops 可统一走 upsert 合并 / Seed an empty board so first round applies uniformly
        board = board_load(task_id) or board_new(task_id, str(task.get("title") or "未命名会议"))
        board["phase"] = "post_meeting"

        settings = load_settings()
        active_role = settings.get("active_agent")

        try:
            result = await asyncio.wait_for(
                core_run_board_analysis(
                    all_lines[-BOARD_ANALYSIS_MAX_LINES:],
                    chapter_titles,
                    existing_board=board,
                    role_name=active_role,
                ),
                timeout=BOARD_ANALYSIS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("[洞察板] 板分析超时 task=%s (%.0fs)", task_id, BOARD_ANALYSIS_TIMEOUT_SECONDS)
            raise HTTPException(status_code=504, detail={"error": "board_timeout", "message": "板修订超时，请稍后重试"})

        changed = bool(result.get("ok") and result.get("board") and result["board"].get("revision", 0) > board.get("revision", 0))
        if changed:
            board_save(result["board"])
            logger.info("[洞察板] 板落盘 task=%s rev=%s", task_id, result["board"]["revision"])

        # ok=False 也返 200：生成质量问题由前端提示，不阻断已有板展示
        # Validation failure returns 200 with ok=False: frontend hints, existing board stays visible
        failure_class = str(result.get("failure_class") or "")
        payload = {
            "ok": bool(result.get("ok")),
            "board": result.get("board") if changed else board,
            "changed": changed,
            "errors": result.get("errors", []),
            "failure_class": failure_class,
        }
        if failure_class:
            # 执行方回显：失败也要告知“谁跑的”；格式崩且处于保守档→建议切换更强模型
            from app.routers.chat import _chat_model_default, _model_usage_meta
            model = _chat_model_default()
            payload["model_usage"] = _model_usage_meta(model)
            from core.model_tier import resolve_model_tier
            payload["weak_model_hint"] = failure_class == "schema" and resolve_model_tier(model) == "conservative"
        return payload
    finally:
        _board_running.discard(task_id)
