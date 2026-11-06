"""app/routers/record_summary.py — 实时总结控制。

端点：
  POST /api/record/summary/pause    — 暂停实时总结
  POST /api/record/summary/resume   — 恢复实时总结
  POST /api/record/summary/stop     — 停止实时总结
  POST /api/record/summary/restart  — 重启实时总结
  POST /api/record/summary/interval — 热更新总结间隔

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 record.py 拆分）
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.i18n import _
from core.realtime_store import realtime_summarizers

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/record/summary/pause")
async def pause_summary():
    """暂停实时总结 / Pause realtime summary"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.pause()
    return {"status": "paused"}


@router.post("/api/record/summary/resume")
async def resume_summary():
    """恢复实时总结 / Resume realtime summary"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.resume()
    return {"status": "resumed"}


@router.post("/api/record/summary/stop")
async def stop_summary():
    """停止实时总结（彻底关闭，需手动恢复） / Stop realtime summary (fully stopped; manual restart required)"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.stop()
    return {"status": "stopped"}


@router.post("/api/record/summary/restart")
async def restart_summary():
    """重新启动已停止的实时总结 / Restart previously stopped realtime summary"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.restart()
    return {"status": "restarted"}


class SummaryIntervalRequest(BaseModel):
    interval: int  # 秒，可选 30/60/120/300 / Seconds; options: 30/60/120/300


@router.post("/api/record/summary/interval")
async def set_summary_interval(req: SummaryIntervalRequest):
    """热更新实时总结间隔（录音中立即生效） / Hot-update realtime summary interval (takes effect immediately during recording)"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    # 下限 30 秒 / Minimum 30 seconds
    new_interval = max(30, req.interval)
    summarizer.set_interval(new_interval)
    return {"status": "updated", "interval": summarizer.interval}
