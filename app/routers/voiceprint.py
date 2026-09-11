"""
app/routers/voiceprint.py — 声纹管理 API

端点：
  GET    /api/voiceprint/registry          — 获取声纹注册表（含说话人姓名）
  GET    /api/voiceprint/status/{uuid}     — 查询指定说话人的声纹状态
  POST   /api/voiceprint/register          — 从音频片段注册声纹
  DELETE /api/voiceprint/{uuid}            — 删除声纹
  POST   /api/tasks/{task_id}/voiceprint-match — 对已完成转写的任务执行自动声纹匹配
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import voiceprint, speakers
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voiceprint", tags=["voiceprint"])


class RegisterRequest(BaseModel):
    """声纹注册请求"""
    speaker_uuid: str                      # 说话人 UUID
    audio_path: str                        # 音频文件路径（WAV）
    begin_time: float = 0                  # 起始时间（秒）
    end_time: float = 0                    # 结束时间（秒），0 表示到末尾
    meeting_id: str = ""                   # 来源会议 ID


class VoiceprintStatusResponse(BaseModel):
    """声纹状态响应"""
    speaker_uuid: str
    has_voiceprint: bool
    registered_at: Optional[str] = None
    updated_at: Optional[str] = None
    sample_count: int = 0
    total_sample_duration: float = 0.0


@router.get("/registry")
def list_voiceprint_registry():
    """
    获取声纹注册表（含说话人姓名）。

    返回所有已注册声纹的说话人列表及注册信息。
    """
    registry = voiceprint.load_registry()
    items = []
    for uuid, record in registry.items():
        speaker = speakers.get_speaker_by_id(uuid)
        items.append({
            "speaker_uuid": uuid,
            "speaker_name": speaker.name if speaker else "未知",
            "registered_at": record.registered_at,
            "updated_at": record.updated_at,
            "sample_count": record.sample_count,
            "total_sample_duration": round(record.total_sample_duration, 1),
            "source_meeting_id": record.source_meeting_id,
        })
    return {"voiceprints": items, "total": len(items)}


@router.get("/status/{speaker_uuid}")
def get_voiceprint_status(speaker_uuid: str):
    """查询指定说话人的声纹状态"""
    registry = voiceprint.load_registry()
    record = registry.get(speaker_uuid)
    if record:
        return VoiceprintStatusResponse(
            speaker_uuid=speaker_uuid,
            has_voiceprint=True,
            registered_at=record.registered_at,
            updated_at=record.updated_at,
            sample_count=record.sample_count,
            total_sample_duration=round(record.total_sample_duration, 1),
        )
    return VoiceprintStatusResponse(
        speaker_uuid=speaker_uuid,
        has_voiceprint=False,
    )


@router.post("/register")
def register_voiceprint(req: RegisterRequest):
    """
    从音频片段注册说话人声纹。

    从指定音频文件的 [begin_time, end_time] 区间提取声纹嵌入，
    注册到指定说话人名下。
    """
    from scipy.io import wavfile

    audio_path = Path(req.audio_path)
    if not audio_path.exists():
        raise HTTPException(404, _("Audio file not found: {path}").format(path=req.audio_path))

    # 加载音频
    try:
        sr, audio_data = wavfile.read(str(audio_path))
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32) / 32768.0
    except Exception as e:
        raise HTTPException(400, _("Failed to read audio: {err}").format(err=e))

    # 截取区间
    start_sample = int(req.begin_time * sr)
    if req.end_time > 0:
        end_sample = int(req.end_time * sr)
    else:
        end_sample = len(audio_data)

    if start_sample >= end_sample:
        raise HTTPException(400, _("Invalid time range"))

    segment = audio_data[start_sample:end_sample]
    duration_sec = len(segment) / sr

    if duration_sec < voiceprint.MIN_REGISTER_SEC:
        raise HTTPException(
            400,
            _("Audio too short: {dur}s (minimum {min}s required)").format(dur=f"{duration_sec:.1f}", min=voiceprint.MIN_REGISTER_SEC)
        )

    # 提取声纹
    embedding = voiceprint.extract_embedding(segment, sr)
    if embedding is None:
        raise HTTPException(500, _("Voiceprint extraction failed (audio quality may be insufficient)"))

    # 注册
    record = voiceprint.register_voiceprint(
        speaker_uuid=req.speaker_uuid,
        embedding=embedding,
        source_meeting_id=req.meeting_id,
    )

    # 验证说话人存在
    speaker = speakers.get_speaker_by_id(req.speaker_uuid)
    speaker_name = speaker.name if speaker else "未知"

    return {
        "speaker_uuid": req.speaker_uuid,
        "speaker_name": speaker_name,
        "duration_sec": round(duration_sec, 1),
        "registered_at": record.registered_at,
        "message": _("Voiceprint registered: {name}").format(name=speaker_name),
    }


@router.delete("/{speaker_uuid}")
def delete_voiceprint(speaker_uuid: str):
    """删除说话人声纹"""
    if not voiceprint.delete_voiceprint(speaker_uuid):
        raise HTTPException(404, _("Voiceprint not found"))
    return {"deleted": True}


# ============================================================
# 任务级声纹自动匹配
# ============================================================

class VoiceprintMatchTask(BaseModel):
    """声纹匹配请求体（可选参数）"""
    threshold: Optional[float] = None       # None 表示按比对空间自动取默认阈值


def _resolve_normalized_path(task: dict) -> Optional[str]:
    """
    解析任务对应的归一化 WAV 路径。

    优先级：任务字段 normalized_path → 命名约定（原文件名 + _normalized.wav）。
    """
    normalized_path = task.get("normalized_path")
    if normalized_path and Path(normalized_path).exists():
        return normalized_path
    # 兼容旧任务（转写时未持久化该字段）：按命名约定推导
    audio_path = task.get("audio_path")
    if audio_path:
        a = Path(audio_path)
        for cand in (
            a.with_stem(f"{a.stem}_normalized").with_suffix(".wav"),
            a.with_suffix(".wav"),
        ):
            if cand.exists():
                return str(cand)
    return None


@router.post("/rebuild/{speaker_uuid}")
def rebuild_voiceprint_from_meetings(speaker_uuid: str):
    """
    跨会议重建说话人声纹。

    人员独立于会议记录：扫描该说话人参与的所有已完成会议（按
    speaker_uuid_mapping 反查），从每场会议的归一化音频中提取其
    发言片段声纹，均值融合后整体覆盖注册表。相比单场会议注册，
    多场样本融合可抑制单场录音的信道偏置，提升跨会议判别力。
    """
    from app.store import tasks

    speaker = speakers.get_speaker_by_id(speaker_uuid)
    if not speaker:
        raise HTTPException(404, _("Speaker not found"))

    embeddings = []
    total_sec = 0.0
    source_meetings = []
    for task_id, task in tasks.items():
        if task.get("status") != "completed":
            continue
        mapping = task.get("speaker_uuid_mapping") or {}
        sids = []
        for k, v in mapping.items():
            if v != speaker_uuid:
                continue
            try:
                sids.append(int(k))
            except (TypeError, ValueError):
                continue
        if not sids:
            continue

        normalized_path = _resolve_normalized_path(task)
        if not normalized_path:
            continue
        dialogue = task.get("dialogue") or []
        for sid in sids:
            embedding, used_sec = voiceprint.extract_speaker_embedding(
                normalized_path, dialogue, sid
            )
            if embedding is not None:
                embeddings.append(embedding)
                total_sec += used_sec
                source_meetings.append(task_id)

    if not embeddings:
        raise HTTPException(
            400,
            _("This speaker has insufficient speech audio in all linked meetings (at least {min} sec per meeting)").format(min=voiceprint.MIN_REGISTER_SEC),
        )

    merged = voiceprint.merge_embeddings(embeddings)
    record = voiceprint.register_voiceprint(
        speaker_uuid,
        merged,
        source_meeting_id=source_meetings[-1],
        accumulate=False,
        sample_count=len(embeddings),
    )

    logger.info(
        f"[声纹] 跨会议重建: speaker={speaker_uuid[:8]}..., "
        f"{len(embeddings)} 场会议, 共 {total_sec:.1f}s"
    )
    return {
        "speaker_uuid": speaker_uuid,
        "speaker_name": speaker.name,
        "meeting_count": len(embeddings),
        "source_meetings": source_meetings,
        "duration_sec": round(total_sec, 1),
        "sample_count": record.sample_count,
        "updated_at": record.updated_at,
        "message": _("Voiceprint rebuilt from {count} meeting(s): {name}").format(count=len(embeddings), name=speaker.name),
    }


@router.post("/tasks/{task_id}/match")
def auto_match_task_voiceprint(task_id: str, req: Optional[VoiceprintMatchTask] = None):
    """
    对已完成转写的任务执行自动声纹匹配。

    从归一化音频中提取每位说话人的声纹，与注册表比对，
    返回匹配结果。匹配成功时自动构建 speaker_id → speaker_uuid 映射。
    """
    from app.store import tasks, save_task_to_disk

    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    dialogue = task.get("dialogue")
    if not dialogue:
        raise HTTPException(400, _("Task has no transcription result yet"))

    # 找归一化音频路径
    normalized_path = _resolve_normalized_path(task)
    if normalized_path:
        task["normalized_path"] = normalized_path
    if not normalized_path:
        raise HTTPException(400, _("Normalized audio unavailable"))

    threshold = req.threshold if req else None

    # 执行自动匹配
    results = voiceprint.auto_identify_speakers(
        audio_path=normalized_path,
        dialogue=dialogue,
        threshold=threshold,
    )

    # 构建自动映射
    auto_mapping = voiceprint.build_auto_mapping(results)

    # 将匹配结果写入任务
    task["voiceprint_match"] = [r.to_dict() for r in results]
    task["voiceprint_auto_mapping"] = {str(k): v for k, v in auto_mapping.items()}
    save_task_to_disk(task_id)

    matched_count = sum(1 for r in results if r.status == "matched")
    total = len(results)

    return {
        "task_id": task_id,
        "results": [r.to_dict() for r in results],
        "auto_mapping": {str(k): v for k, v in auto_mapping.items()},
        "summary": f"{matched_count}/{total} 位说话人自动识别成功",
    }
