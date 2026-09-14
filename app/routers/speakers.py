"""
app/routers/speakers.py — 说话人 CRUD + 会议级绑定/纪要生成 / Speaker CRUD + meeting-level binding/summary generation

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 1.0.0
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.store import (
    run_stage2_task,
    save_task_to_disk,
    tasks,
)
from core import joblog, speakers, voiceprint
from core import users as user_module
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(tags=["speakers"])


class SpeakerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=500)


class SpeakerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    role: Optional[str] = Field(default=None, max_length=100)
    note: Optional[str] = Field(default=None, max_length=500)


class SaveMappingRequest(BaseModel):
    meeting_id: str
    meeting_name: str
    mapping: dict[str, str]  # {"0": "uuid1", "1": "uuid2"} 说话人映射 / Speaker mapping


class TaskSpeakerMapping(BaseModel):
    mapping: dict[str, str]  # {"0": "uuid1", "1": "uuid2"} 说话人映射 / Speaker mapping


@router.get("/api/speakers")
def list_speakers():
    """获取说话人列表（读 speakers.json） / Get speaker list (reads speakers.json)"""
    speaker_list = speakers.load_speakers()
    return {"speakers": [s.to_dict() for s in speaker_list]}


@router.post("/api/speakers")
def create_speaker(data: SpeakerCreate):
    """添加说话人（写 speakers.json） / Add speaker (writes speakers.json)"""
    if not data.name.strip():
        raise HTTPException(400, _("Name cannot be empty"))
    speaker = speakers.add_speaker(
        name=data.name.strip(),
        role=data.role.strip(),
        note=data.note.strip(),
    )
    return speaker.to_dict()


@router.put("/api/speakers/{speaker_id}")
def update_speaker(speaker_id: str, data: SpeakerUpdate):
    """更新说话人（写 speakers.json） / Update speaker (writes speakers.json)"""
    speaker = speakers.update_speaker(
        speaker_id=speaker_id,
        name=data.name.strip() if data.name else None,
        role=data.role.strip() if data.role is not None else None,
        note=data.note.strip() if data.note is not None else None,
    )
    if not speaker:
        raise HTTPException(404, _("Speaker not found"))
    return speaker.to_dict()


@router.delete("/api/speakers/{speaker_id}")
def delete_speaker(speaker_id: str):
    """删除说话人（写 speakers.json） / Delete speaker (writes speakers.json)"""
    if not speakers.delete_speaker(speaker_id):
        raise HTTPException(404, _("Speaker not found"))
    return {"deleted": True}


@router.put("/api/speakers/{speaker_id}/set-as-me")
def set_speaker_as_me(speaker_id: str):
    """将说话人设为当前用户（切换式） / Set speaker as current user (toggle).

    若该说话人已关联当前用户，则取消关联； / If already linked to current user, unlink;
    否则将当前用户关联到该说话人（自动解除旧关联）。 / Otherwise link current user (auto-unlink old association).
    """
    user = user_module.get_current_user()
    if not user:
        # 未配置用户信息时，自动创建默认本地用户 / Auto-create default local user when no user configured
        user = user_module.set_current_user("Local User")

    speaker = speakers.get_speaker_by_id(speaker_id)
    if not speaker:
        raise HTTPException(404, _("Speaker not found"))

    if speaker.linked_user_id == user["id"]:
        result = speakers.clear_linked_user(speaker_id)
    else:
        result = speakers.set_linked_user(speaker_id, user["id"])

    if not result:
        raise HTTPException(500, _("Operation failed"))
    return result.to_dict()


@router.get("/api/speakers/mapping/latest")
def get_latest_mapping():
    """获取最近一次会议映射（读 mappings.json） / Get latest meeting mapping (reads mappings.json)"""
    mapping = speakers.get_latest_mapping()
    if not mapping:
        return {"mapping": None}
    # 补充说话人姓名 / Enrich with speaker names
    name_map = speakers.get_speaker_name_map()
    mapping_with_names = {}
    for sid, speaker_uuid in mapping.mapping.items():
        name = name_map.get(speaker_uuid, f"Speaker {sid + 1}")
        mapping_with_names[str(sid)] = {
            "speaker_uuid": speaker_uuid,
            "name": name,
        }
    return {
        "mapping": {
            "meeting_id": mapping.meeting_id,
            "meeting_name": mapping.meeting_name,
            "created_at": mapping.created_at,
            "details": mapping_with_names,
        }
    }


@router.post("/api/speakers/mapping")
def save_mapping(data: SaveMappingRequest):
    """保存会议映射（写 mappings.json） / Save meeting mapping (writes mappings.json)"""
    # 转换 key 为 int / Convert keys to int
    mapping = {int(k): v for k, v in data.mapping.items()}
    result = speakers.save_meeting_mapping(
        meeting_id=data.meeting_id,
        meeting_name=data.meeting_name,
        mapping=mapping,
    )
    return {
        "meeting_id": result.meeting_id,
        "meeting_name": result.meeting_name,
        "created_at": result.created_at,
    }


@router.put("/api/tasks/{task_id}/speaker-mapping")
def update_speaker_mapping(
    task_id: str,
    data: TaskSpeakerMapping,
):
    """增量保存说话人映射（不触发纪要生成） / Incrementally save speaker mapping (without triggering summary generation).

    用于用户在前端绑定说话人时实时持久化， / For realtime persistence when user binds speakers in frontend,
    避免离开页面后绑定丢失。 / preventing binding loss on page leave.
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    if task["status"] not in ("awaiting_mapping", "completed"):
        raise HTTPException(400, _("Current status does not allow setting speaker mapping"))

    # 转换 key 为 int / Convert keys to int
    mapping = {int(k): v for k, v in data.mapping.items()}

    # 仅更新映射并持久化，不改变状态、不触发纪要生成 / Only update mapping and persist; no state change, no summary trigger
    tasks[task_id]["speaker_uuid_mapping"] = {str(k): v for k, v in mapping.items()}
    save_task_to_disk(task_id)

    return {"status": "ok", "mapping": tasks[task_id]["speaker_uuid_mapping"]}


def _register_voiceprints_bg(
    task_id: str,
    normalized_path: str,
    dialogue: list,
    mapping: dict,
):
    """后台：按已确认绑定补录声纹（自动注册闭环，失败不影响纪要主链路） / Background: register voiceprints per confirmed bindings (auto-register loop; failure doesn't affect summary pipeline)"""
    try:
        results = voiceprint.register_from_binding(
            audio_path=normalized_path,
            dialogue=dialogue,
            mapping=mapping,
            meeting_id=task_id,
        )
        ok = sum(1 for r in results.values() if r["status"] == "registered")
        logger.info(f"[{task_id[:8]}] 声纹自动注册: {ok}/{len(mapping)} 位说话人")
    except Exception as e:
        logger.warning(f"[{task_id[:8]}] 声纹自动注册失败（不影响纪要）: {e}")


@router.post("/api/tasks/{task_id}/speaker-mapping")
def set_speaker_mapping(
    task_id: str,
    background_tasks: BackgroundTasks,
    data: TaskSpeakerMapping,
):
    """设置说话人映射并触发纪要生成。 / Set speaker mapping and trigger summary generation.

    在转写完成后调用，将 speaker_id 绑定到具体说话人， / Called after transcription; bind speaker_id to specific speakers,
    然后自动生成纪要。 / then auto-generate summary.
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    if task["status"] not in ("awaiting_mapping", "completed"):
        raise HTTPException(400, _("Current status does not allow setting speaker mapping"))

    # 转换 key 为 int / Convert keys to int
    mapping = {int(k): v for k, v in data.mapping.items()}

    # 保存会议映射（用于历史复用） / Save meeting mapping (for history reuse)
    audio_name = task.get("audio_name", task_id)
    speakers.save_meeting_mapping(
        meeting_id=task_id,
        meeting_name=audio_name,
        mapping=mapping,
    )

    # 更新任务状态（提前写入 speaker_uuid_mapping，确保刷新后绑定不丢失） / Update task state (write speaker_uuid_mapping early to ensure bindings survive refresh)
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 75
    tasks[task_id]["message"] = _("Generating minutes...")
    tasks[task_id]["speaker_uuid_mapping"] = {str(k): v for k, v in mapping.items()}
    # 作业日志：记录确认绑定（含姓名，便于会议助手回溯） / Job log: record confirmed bindings (with names for meeting assistant traceability)
    names = []
    for uuid in mapping.values():
        spk = speakers.get_speaker_by_id(uuid)
        names.append(spk.name if spk else uuid[:8])
    joblog.append_event(
        task_id, joblog.STAGE_BIND,
        f"确认绑定 {len(mapping)} 位说话人（{'、'.join(names)}），触发纪要生成",
    )
    save_task_to_disk(task_id)

    # 后台运行第二阶段 / Run stage 2 in background
    audio_path = Path(task["audio_path"])
    background_tasks.add_task(run_stage2_task, task_id, audio_path, mapping)

    # V3：按确认的绑定补录声纹，供后续会议自动匹配（纪要完成后执行，不阻塞） / V3: Register voiceprints per confirmed bindings for future auto-matching (after summary; non-blocking)
    normalized_path = task.get("normalized_path")
    if not normalized_path:
        # 兼容旧任务（未持久化该字段）：按命名约定推导归一化音频 / Backward compat (field not persisted): derive normalized audio by naming convention
        candidate = audio_path.with_stem(f"{audio_path.stem}_normalized").with_suffix(".wav")
        normalized_path = str(candidate) if candidate.exists() else None
    dialogue = task.get("dialogue") or []
    if normalized_path and dialogue:
        background_tasks.add_task(
            _register_voiceprints_bg, task_id, normalized_path, dialogue, mapping,
        )

    return {"status": "processing", "message": _("Generating minutes...")}


@router.post("/api/tasks/{task_id}/regenerate-summary")
def regenerate_summary(
    task_id: str,
    background_tasks: BackgroundTasks,
):
    """使用当前说话人映射重新生成纪要。 / Regenerate summary using current speaker mapping.

    用于用户修改说话人绑定后重新生成纪要。 / Used when user modifies speaker bindings to regenerate summary.
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(400, _("Task not yet completed"))

    # 获取 UUID 映射（优先）或从姓名映射反查 / Get UUID mapping (preferred) or reverse-lookup from name mapping
    uuid_mapping = task.get("speaker_uuid_mapping", {})
    if not uuid_mapping:
        # 尝试从姓名映射反查 UUID / Try reverse-lookup UUID from name mapping
        name_mapping = task.get("speaker_mapping", {})
        if not name_mapping:
            raise HTTPException(400, _("Speaker mapping not set"))
        name_to_uuid = {s.name: s.speaker_id for s in speakers.load_speakers()}
        uuid_mapping = {sid: name_to_uuid[name] for sid, name in name_mapping.items() if name in name_to_uuid}

    # 转换回 {int: str} 格式 / Convert back to {int: str} format
    mapping = {int(k): v for k, v in uuid_mapping.items()}

    # 更新任务状态 / Update task state
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 75
    tasks[task_id]["message"] = _("Regenerating minutes...")
    save_task_to_disk(task_id)

    # 后台运行第二阶段 / Run stage 2 in background
    audio_path = Path(task["audio_path"])
    background_tasks.add_task(run_stage2_task, task_id, audio_path, mapping)

    return {"status": "processing", "message": _("Regenerating minutes...")}
