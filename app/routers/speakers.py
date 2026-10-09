"""
app/routers/speakers.py — 说话人 CRUD + 会议级绑定/纪要生成 / Speaker CRUD + meeting-level binding/summary generation

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 1.0.0
"""

import logging
from datetime import datetime
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


def _mark_modified(task_id: str) -> None:
    """标记任务内容已修改，用于知识库同步脏检测 / Mark task content as modified for KB sync dirty detection."""
    tasks[task_id]["last_modified_at"] = datetime.now().isoformat()


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


class RosterUpdate(BaseModel):
    roster: list[str]  # 参会人姓名列表 / Participant name list


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
    # 同步清理 speaker_mapping 中已解绑项，避免前端 fallback 仍显示旧名 / Drop stale speaker_mapping entries for unbound speakers
    existing_sm = task.get("speaker_mapping") or {}
    new_sm = {k: v for k, v in existing_sm.items() if int(k) in mapping}
    if len(new_sm) != len(existing_sm):
        tasks[task_id]["speaker_mapping"] = new_sm
    _mark_modified(task_id)
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
    # 同步清 speaker_mapping 中已解绑项（Stage 2 会重写，但此处确保即刻一致）
    existing_sm = task.get("speaker_mapping") or {}
    new_sm = {k: v for k, v in existing_sm.items() if int(k) in mapping}
    if len(new_sm) != len(existing_sm):
        tasks[task_id]["speaker_mapping"] = new_sm
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


@router.post("/api/tasks/{task_id}/apply-speaker-names")
def apply_speaker_names_endpoint(
    task_id: str,
    background_tasks: BackgroundTasks,
    data: TaskSpeakerMapping,
):
    """确认关联时按真实姓名原地替换纪要/原文/待办中的通用说话人标签，不重跑 LLM。
    On confirm-binding, in-place replace generic speaker labels with real names across
    summary / dialogue / todos, without re-running Stage 2 (no LLM call).

    与 `/speaker-mapping`（触发 Stage 2 全量重生成）解耦：本端点仅做即时文本替换，
    不覆盖用户对纪要的手工编辑，也不消耗 LLM 配额；若需将姓名改写进纪要叙述，
    用户可主动点击工具栏「重新生成纪要」。
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(400, _("Task not yet completed"))

    mapping = {int(k): v for k, v in data.mapping.items() if v}

    # 无有效绑定：仅持久化 uuid 映射，原样返回当前字段
    if not mapping:
        tasks[task_id]["speaker_uuid_mapping"] = {}
        save_task_to_disk(task_id)
        return _speaker_names_response(task_id)

    # 保存会议映射（用于历史复用） / Save meeting mapping for history reuse
    speakers.save_meeting_mapping(
        meeting_id=task_id,
        meeting_name=task.get("audio_name", task_id),
        mapping=mapping,
    )

    name_by_sid = speakers.resolve_speaker_names(mapping)

    # 1) 对话稿姓名化（驱动原文面板与说话人视图） / Apply names to dialogue
    dialogue = task.get("dialogue") or []
    new_dialogue = speakers.apply_speaker_names(dialogue, mapping) if dialogue else []
    speaker_name_map = {
        str(it.get("speaker_id", 0)): it.get("speaker_name")
        for it in new_dialogue if it.get("speaker_name")
    }

    # 2) 纪要正文原地替换（summary 与 user_summary 分别处理，保留用户编辑） / In-place replace in summary & user_summary
    new_summary, sum_hits = speakers.replace_speaker_labels(task.get("summary") or "", name_by_sid)
    user_summary = task.get("user_summary")
    new_user_summary = None
    if user_summary is not None:
        new_user_summary, _uh = speakers.replace_speaker_labels(user_summary, name_by_sid)

    # 3) 待办负责人/描述原地替换 / In-place replace in todos
    new_todos = []
    for td in (task.get("todos") or []):
        t2 = dict(td)
        if t2.get("assignee"):
            t2["assignee"], _ah = speakers.replace_speaker_labels(t2["assignee"], name_by_sid)
        if t2.get("text"):
            t2["text"], _th = speakers.replace_speaker_labels(t2["text"], name_by_sid)
        new_todos.append(t2)

    # 4) 落库 / Persist
    tasks[task_id]["speaker_uuid_mapping"] = {str(k): v for k, v in mapping.items()}
    # 保留未解绑项的旧名（可能来自 ASR 自动识别），再覆盖新绑定名；已解绑的 sid 直接清除
    old_sm = task.get("speaker_mapping", {})
    kept_old = {k: v for k, v in old_sm.items() if int(k) in mapping}
    tasks[task_id]["speaker_mapping"] = {**kept_old, **speaker_name_map}
    tasks[task_id]["summary"] = new_summary
    if user_summary is not None:
        tasks[task_id]["user_summary"] = new_user_summary
    if dialogue:
        tasks[task_id]["dialogue"] = new_dialogue
    if task.get("todos") is not None:
        tasks[task_id]["todos"] = new_todos
    _mark_modified(task_id)
    save_task_to_disk(task_id)

    # 5) 重写输出文件 + 知识库同步（尽力而为，失败不影响主链路） / Rewrite output file + KB sync (best-effort)
    try:
        output_path = task.get("output_path")
        if output_path and Path(output_path).exists():
            from core.summarize import save_summary
            display = new_user_summary if new_user_summary is not None else new_summary
            save_summary(display, output_path, new_dialogue or None)
    except Exception as e:
        logger.warning(f"[{task_id[:8]}] 原地替换后重写纪要文件失败（不影响）: {e}")
    try:
        from core.projects import sync_meeting_to_folders
        sync_meeting_to_folders(tasks[task_id])
    except Exception as e:
        logger.warning(f"[{task_id[:8]}] 原地替换后知识库同步失败（不影响）: {e}")

    joblog.append_event(
        task_id, joblog.STAGE_BIND,
        f"确认关联：原地替换 {len(name_by_sid)} 位说话人姓名（命中 {sum_hits} 处，不重跑纪要）",
    )

    # 声纹自动注册闭环（与全量重生成路径保持一致，后台执行不阻塞） / Voiceprint auto-register (parity; background, non-blocking)
    normalized_path = task.get("normalized_path")
    if not normalized_path:
        audio_path = Path(task["audio_path"])
        candidate = audio_path.with_stem(f"{audio_path.stem}_normalized").with_suffix(".wav")
        normalized_path = str(candidate) if candidate.exists() else None
    if normalized_path and dialogue:
        background_tasks.add_task(_register_voiceprints_bg, task_id, normalized_path, new_dialogue, mapping)

    return _speaker_names_response(task_id)


def _speaker_names_response(task_id: str) -> dict:
    """统一返回原地替换后的任务展示字段 / Return display fields after in-place replacement."""
    t = tasks[task_id]
    return {
        "status": t["status"],
        "summary": t.get("summary"),
        "user_summary": t.get("user_summary"),
        "dialogue": t.get("dialogue"),
        "speaker_mapping": t.get("speaker_mapping", {}),
        "speaker_uuid_mapping": t.get("speaker_uuid_mapping", {}),
        "todos": t.get("todos"),
    }


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


@router.put("/api/tasks/{task_id}/roster")
def update_roster(task_id: str, data: RosterUpdate):
    """更新参会人名单（独立于说话人绑定，不触发声纹注册） / Update meeting roster (independent of speaker binding; no voiceprint registration).

    仅记录「谁参加了这次会议」，与 ASR 说话人检测 / Only records "who attended this meeting"; unrelated
    和身份绑定完全解耦。 / to ASR speaker detection or identity binding.
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    # 去重 + 去空 / Deduplicate + strip empties
    seen: set[str] = set()
    cleaned: list[str] = []
    for name in data.roster:
        n = name.strip()
        if n and n not in seen:
            seen.add(n)
            cleaned.append(n)

    tasks[task_id]["roster"] = cleaned
    _mark_modified(task_id)
    save_task_to_disk(task_id)

    return {"status": "ok", "roster": cleaned}
