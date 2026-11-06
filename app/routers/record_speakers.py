"""app/routers/record_speakers.py — 实时说话人绑定。

端点：
  POST /api/record/bind-speaker      — 录音期间绑定 ASR 说话人编号 → 全局说话人档案
  GET  /api/record/speaker-bindings  — 当前录音的绑定状态

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 record.py 拆分）
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import (
    push_realtime_msg,
    realtime_full_transcripts,
    realtime_speaker_maps,
    realtime_summarizers,
    resolve_realtime_speaker_name,
    speakers,
)
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter()


class RealtimeBindSpeakerRequest(BaseModel):
    speaker_id: int         # ASR 说话人编号（0, 1, 2...） / ASR speaker index (0, 1, 2...)
    speaker_uuid: str       # speakers.json 中的说话人 UUID / Speaker UUID in speakers.json


@router.post("/api/record/bind-speaker")
async def realtime_bind_speaker(req: RealtimeBindSpeakerRequest):
    """实时说话人绑定。 / Realtime speaker binding.

    在录音期间将 ASR 说话人编号绑定到全局说话人档案。 / Bind ASR speaker index to global speaker profile during recording.
    绑定后立即通过 WebSocket 通知前端更新所有转写条目。 / Immediately notify frontend via WebSocket to update all transcript entries.
    """
    # 找到当前录制中的 task_id / Find currently recording task_id
    task_id = None
    for tid in realtime_speaker_maps:
        task_id = tid
        break
    if not task_id:
        raise HTTPException(400, _("No active recording"))

    # 验证说话人存在 / Verify speaker exists
    spk = speakers.get_speaker_by_id(req.speaker_uuid)
    if not spk:
        raise HTTPException(404, _("Speaker not found"))

    # 记录绑定前，先获取旧的兆底名称（用于更新缓冲区和全量转写） / Before recording binding, get old fallback name (for updating buffer and full transcript)
    old_name = resolve_realtime_speaker_name(task_id, req.speaker_id)

    # 记录绑定 / Record binding
    realtime_speaker_maps[task_id][req.speaker_id] = req.speaker_uuid
    logger.info(f"[实时绑定] speaker_{req.speaker_id} → {spk.name}")

    # 通过 WebSocket 广播绑定更新 / Broadcast binding update via WebSocket
    push_realtime_msg(task_id, {
        "type": "speaker_bound",
        "speaker_id": req.speaker_id,
        "speaker_uuid": req.speaker_uuid,
        "speaker_name": spk.name,
    })

    # 更新实时总结缓冲区中已缓冲句子的说话人姓名 / Update speaker name of buffered sentences in realtime summary buffer
    summarizer = realtime_summarizers.get(task_id)
    if summarizer and old_name != spk.name:
        summarizer.update_speaker_name(old_name, spk.name)

    # 更新全量实时转写记录中的说话人姓名（确保 WebSocket 重连回放时也显示真名） / Update speaker name in full realtime transcript (ensure real names shown on WebSocket reconnect replay)
    full_transcript = realtime_full_transcripts.get(task_id, [])
    for entry in full_transcript:
        if entry.get("speaker_id") == req.speaker_id:
            entry["speaker_name"] = spk.name

    return {
        "speaker_id": req.speaker_id,
        "speaker_name": spk.name,
        "speaker_uuid": req.speaker_uuid,
    }


@router.get("/api/record/speaker-bindings")
async def realtime_get_speaker_bindings():
    """获取当前录音的说话人绑定状态 / Get current recording's speaker binding status"""
    task_id = None
    for tid in realtime_speaker_maps:
        task_id = tid
        break
    if not task_id:
        return {"bindings": {}, "task_id": None}

    binding_map = realtime_speaker_maps.get(task_id, {})
    # 补充姓名 / Enrich with names
    result = {}
    for sid, spk_uuid in binding_map.items():
        spk = speakers.get_speaker_by_id(spk_uuid)
        result[str(sid)] = {
            "speaker_uuid": spk_uuid,
            "speaker_name": spk.name if spk else "",
        }
    return {"bindings": result, "task_id": task_id}
