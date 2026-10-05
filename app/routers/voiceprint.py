"""
app/routers/voiceprint.py — 声纹管理 API / Voiceprint management API

端点 / Endpoints:
  GET    /api/voiceprint/registry          — 获取声纹注册表 / Get voiceprint registry
  GET    /api/voiceprint/status/{uuid}     — 查询声纹状态 / Get voiceprint status
  POST   /api/voiceprint/register          — 从音频片段注册声纹 / Register voiceprint from audio clip
  DELETE /api/voiceprint/{uuid}            — 删除声纹 / Delete voiceprint
  POST   /api/tasks/{task_id}/voiceprint-match — 自动声纹匹配 / Auto voiceprint matching
  POST   /api/voiceprint/tasks/{task_id}/dismiss — 忽略声纹建议 / Dismiss voiceprint suggestion
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import speakers, voiceprint
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voiceprint", tags=["voiceprint"])


class RegisterRequest(BaseModel):
    """声纹注册请求 / Voiceprint registration request."""
    speaker_uuid: str                      # 说话人 UUID / Speaker UUID
    audio_path: str                        # 音频文件路径 / Audio file path (WAV)
    begin_time: float = 0                  # 起始时间（秒） / Start time (seconds)
    end_time: float = 0                    # 结束时间（秒），0 表示到末尾 / End time (seconds); 0 = to end
    meeting_id: str = ""                   # 来源会议 ID / Source meeting ID


class VoiceprintStatusResponse(BaseModel):
    """声纹状态响应 / Voiceprint status response."""
    speaker_uuid: str
    has_voiceprint: bool
    registered_at: Optional[str] = None
    updated_at: Optional[str] = None
    sample_count: int = 0
    total_sample_duration: float = 0.0


@router.get("/registry")
def list_voiceprint_registry():
    """
    获取声纹注册表（含说话人姓名） / Get voiceprint registry (with speaker names).

    返回所有已注册声纹的说话人列表及注册信息 / Return all registered voiceprint speakers and registration info.
    """
    registry = voiceprint.load_registry()
    items = []
    for uuid, record in registry.items():
        speaker = speakers.get_speaker_by_id(uuid)
        items.append({
            "speaker_uuid": uuid,
            "speaker_name": speaker.name if speaker else "Unknown",
            "registered_at": record.registered_at,
            "updated_at": record.updated_at,
            "sample_count": record.sample_count,
            "total_sample_duration": round(record.total_sample_duration, 1),
            "source_meeting_id": record.source_meeting_id,
        })
    return {"voiceprints": items, "total": len(items)}


@router.get("/status/{speaker_uuid}")
def get_voiceprint_status(speaker_uuid: str):
    """查询指定说话人的声纹状态 / Get voiceprint status for a speaker."""
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
    从音频片段注册说话人声纹 / Register speaker voiceprint from audio clip.

    从指定音频文件的 [begin_time, end_time] 区间提取声纹嵌入 / Extract voiceprint embedding from [begin_time, end_time] interval,
    注册到指定说话人名下 / Register under specified speaker.
    """
    from core.audio import read_wav_float32

    audio_path = Path(req.audio_path)

    # 安全校验：限制音频文件必须在 data 目录内 / Security check: audio files must be within data directories
    _ALLOWED_AUDIO_DIRS = [
        Path("data/recordings").resolve(),
        Path("data/uploads").resolve(),
        Path("data/tasks").resolve(),
    ]
    resolved_audio = audio_path.resolve()
    # 使用 is_relative_to 而非 str.startswith，避免同前缀目录绕过 / Use is_relative_to (not str.startswith) to avoid prefix bypass
    if not any(resolved_audio.is_relative_to(d) for d in _ALLOWED_AUDIO_DIRS):
        raise HTTPException(403, _("Access denied: audio file outside allowed directories"))

    if not resolved_audio.exists():
        raise HTTPException(404, _("Audio file not found: {path}").format(path=req.audio_path))

    # 加载音频 / Load audio
    try:
        sr, audio_data = read_wav_float32(resolved_audio)
    except Exception as e:
        raise HTTPException(400, _("Failed to read audio: {err}").format(err=e))

    # 截取区间 / Extract segment
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

    # 提取声纹 / Extract voiceprint
    embedding = voiceprint.extract_embedding(segment, sr)
    if embedding is None:
        raise HTTPException(500, _("Voiceprint extraction failed (audio quality may be insufficient)"))

    # 注册 / Register
    record = voiceprint.register_voiceprint(
        speaker_uuid=req.speaker_uuid,
        embedding=embedding,
        source_meeting_id=req.meeting_id,
    )

    # 验证说话人存在 / Verify speaker exists
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
    """删除说话人声纹 / Delete speaker voiceprint."""
    if not voiceprint.delete_voiceprint(speaker_uuid):
        raise HTTPException(404, _("Voiceprint not found"))
    return {"deleted": True}


# ============================================================
# 任务级声纹自动匹配 / Task-level Auto Voiceprint Matching
# ============================================================

class VoiceprintMatchTask(BaseModel):
    """声纹匹配请求体（可选参数） / Voiceprint match request (optional params)."""
    threshold: Optional[float] = None       # None 表示按比对空间自动取默认阈值 / None = auto default threshold


def _resolve_normalized_path(task: dict) -> Optional[str]:
    """
    解析任务对应的归一化 WAV 路径 / Resolve normalized WAV path for a task.

    优先级 / Priority：任务字段 normalized_path → 命名约定 / task field normalized_path → naming convention (filename + _normalized.wav).
    """
    normalized_path = task.get("normalized_path")
    if normalized_path and Path(normalized_path).exists():
        return normalized_path
    # 兼容旧任务（转写时未持久化该字段）：按命名约定推导 / Backward compat for legacy tasks (field not persisted): derive by naming convention
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
    跨会议重建说话人声纹 / Cross-meeting speaker voiceprint rebuild.

    人员独立于会议记录 / Speakers are independent of meeting records: 扫描该说话人参与的所有已完成会议 / scan all completed meetings for this speaker
    （按 speaker_uuid_mapping 反查），从每场会议的归一化音频中提取其 / (reverse lookup via speaker_uuid_mapping); extract voiceprint from
    发言片段声纹，均值融合后整体覆盖注册表 / each meeting's normalized audio; mean-fusion then overwrite registry.
    相比单场会议注册，多场样本融合可抑制单场录音的信道偏置，提升跨会议判别力 / Multi-meeting fusion suppresses single-session channel bias; improves cross-meeting discrimination.
    """
    from app.store import tasks

    speaker = speakers.get_speaker_by_id(speaker_uuid)
    if not speaker:
        raise HTTPException(404, _("Speaker not found"))

    # v2.1：每场会议切多个 chunk 样本（带会议标签），整体替换写入。
    # 跨会议多 chunk 既覆盖信道变异，又让个人阈值有足够样本可标定。
    samples: list[tuple] = []
    total_sec = 0.0
    source_meetings: list[str] = []
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
        got_any_in_task = False
        for sid in sids:
            group, _total = voiceprint.extract_speaker_embedding_group(
                normalized_path, dialogue, sid
            )
            for embedding, used_sec in group:
                samples.append((embedding, used_sec, task_id))
                total_sec += used_sec
                got_any_in_task = True
        if got_any_in_task:
            source_meetings.append(task_id)

    if not samples:
        raise HTTPException(
            400,
            _("This speaker has insufficient speech audio in all linked meetings (at least {min} sec per meeting)").format(min=voiceprint.MIN_REGISTER_SEC),
        )

    record = voiceprint.register_voiceprint_samples(
        speaker_uuid,
        samples,
        meeting_id=source_meetings[-1],
        accumulate=False,
    )

    logger.info(
        f"[声纹] 跨会议重建: speaker={speaker_uuid[:8]}..., "
        f"{len(source_meetings)} 场会议, {len(samples)} 个样本, 共 {total_sec:.1f}s"
    )
    return {
        "speaker_uuid": speaker_uuid,
        "speaker_name": speaker.name,
        "meeting_count": len(source_meetings),
        "source_meetings": source_meetings,
        # 以裁剪后实际入库样本时长为准（端点扫描的 total_sec 可能超出全局上限）
        "duration_sec": round(record.total_sample_duration, 1),
        "sample_count": record.sample_count,
        "updated_at": record.updated_at,
        "message": _("Voiceprint rebuilt from {count} meeting(s): {name}").format(count=len(source_meetings), name=speaker.name),
    }


@router.post("/tasks/{task_id}/match")
def auto_match_task_voiceprint(task_id: str, req: Optional[VoiceprintMatchTask] = None):
    """
    对已完成转写的任务执行自动声纹匹配 / Auto voiceprint matching for completed transcription tasks.

    从归一化音频中提取每位说话人的声纹，与注册表比对 / Extract each speaker's voiceprint from normalized audio; compare with registry.
    返回匹配结果 / Return match results. 匹配成功时自动构建 speaker_id → speaker_uuid 映射 / On success, auto-build speaker_id → speaker_uuid mapping.
    """
    from app.store import save_task_to_disk, tasks

    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    dialogue = task.get("dialogue")
    if not dialogue:
        raise HTTPException(400, _("Task has no transcription result yet"))

    # 找归一化音频路径 / Find normalized audio path
    normalized_path = _resolve_normalized_path(task)
    if normalized_path:
        task["normalized_path"] = normalized_path
    if not normalized_path:
        raise HTTPException(400, _("Normalized audio unavailable"))

    threshold = req.threshold if req else None

    # 锚点排除：本场已确认绑定的注册人不再参与声纹建议（一人不可占两位）/
    # Anchor exclusion: speakers already bound in this meeting are not candidates.
    uuid_mapping = task.get("speaker_uuid_mapping") or {}
    locked_uuids = {str(u) for u in uuid_mapping.values() if u}
    # 已绑定的 ASR 说话人本身也不再识别（不给已确认的人产出反向建议）
    bound_sids = {int(k) for k in uuid_mapping.keys() if str(k).lstrip("-").isdigit()}

    # 执行自动匹配 / Execute auto matching
    results = voiceprint.auto_identify_speakers(
        audio_path=normalized_path,
        dialogue=dialogue,
        threshold=threshold,
        exclude_uuids=locked_uuids or None,
        bound_sids=bound_sids or None,
    )

    # 构建自动映射 / Build auto mapping
    auto_mapping = voiceprint.build_auto_mapping(results)

    # 将匹配结果写入任务（重跑视为重新评估，清空历史忽略记录） / Write results (rerun = fresh evaluation, reset dismissals)
    task["voiceprint_match"] = [r.to_dict() for r in results]
    task["voiceprint_auto_mapping"] = {str(k): v for k, v in auto_mapping.items()}
    task["voiceprint_dismissed"] = []
    save_task_to_disk(task_id)

    matched_count = sum(1 for r in results if r.status == "matched")
    total = len(results)

    return {
        "task_id": task_id,
        "results": [r.to_dict() for r in results],
        "auto_mapping": {str(k): v for k, v in auto_mapping.items()},
        "summary": f"{matched_count}/{total} 位说话人自动识别成功",
    }


class VoiceprintDismissRequest(BaseModel):
    """忽略声纹建议请求 / Dismiss voiceprint suggestion request."""
    speaker_id: int


@router.post("/tasks/{task_id}/dismiss")
def dismiss_voiceprint_suggestion(task_id: str, req: VoiceprintDismissRequest):
    """
    忽略指定说话人的声纹建议（本场会议不再显示） / Dismiss voiceprint suggestion for a speaker.

    仅影响建议展示，不改动任何绑定 / Only affects suggestion display, never touches bindings.
    重跑识别时自动清空 / Reset automatically on rerun.
    """
    from app.store import save_task_to_disk, tasks

    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))
    task = tasks[task_id]
    dismissed = task.get("voiceprint_dismissed") or []
    if req.speaker_id not in dismissed:
        dismissed = sorted({*dismissed, req.speaker_id})
        task["voiceprint_dismissed"] = dismissed
        save_task_to_disk(task_id)
    return {"task_id": task_id, "dismissed": dismissed}
