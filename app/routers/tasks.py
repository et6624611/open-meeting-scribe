"""
app/routers/tasks.py — 转录提交 + 任务 CRUD + 音频/下载

作者：王永亮
创建：2026-09-03
版本：1.0.0
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.store import (
    TASKS_DIR,
    UPLOAD_DIR,
    run_pipeline_task,
    run_stage2_task,
    save_task_to_disk,
    tasks,
)
from core.audio import get_stream_recording_info, is_stream_recording
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


class TranscribeRequest(BaseModel):
    speaker_mapping: Optional[dict[str, str]] = None  # {"0": "uuid1", "1": "uuid2"}


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    meeting_date: Optional[str] = None  # "YYYY-MM-DD"，用户指定的实际开会日期
    project_id: Optional[str] = None  # 关联的项目 ID，传空字符串表示取消关联


class BatchArchiveRequest(BaseModel):
    task_ids: list[str]


@router.post("/api/transcribe")
async def create_transcribe_task(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    speaker_mapping: Optional[str] = None,  # JSON string: {"0": "uuid1", "1": "uuid2"}
    speaker_count: Optional[int] = Form(None),  # 说话人数量提示（2-100）；不传则自动估算
):
    """上传音频并提交转写任务"""
    # 验证文件类型
    allowed_types = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".webm"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_types:
        raise HTTPException(400, _("Unsupported file type: {ext}").format(ext=file_ext))

    # 验证 speaker_count 范围
    if speaker_count is not None and (speaker_count < 1 or speaker_count > 100):
        raise HTTPException(400, _("speaker_count must be between 1 and 100"))

    # 配额预检：订阅用户额度用尽时阻止上传（自带 Key 用户不受限）
    try:
        from core.metering import check_quota, is_metered
        from core.users import get_current_user
        current_user = get_current_user()
        if current_user and is_metered():
            quota_result = check_quota(current_user["id"])
            if not quota_result["allowed"]:
                raise HTTPException(
                    402,
                    {
                        "error": "quota_exhausted",
                        "remaining": quota_result["remaining"],
                        "message": _("Monthly transcription quota exhausted ({remaining} min remaining). Configure your own API Key to continue.").format(remaining=quota_result['remaining']),
                    },
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"配额预检失败（不阻止上传）: {e}")

    # 保存上传文件
    task_id = str(uuid.uuid4())
    safe_name = f"{task_id[:8]}_{file.filename}"
    audio_path = UPLOAD_DIR / safe_name

    content = await file.read()

    # 大小预检：防止超大文件耗尽磁盘空间
    MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, _("File too large (max {max} GB)").format(max=2))

    with open(audio_path, "wb") as f:
        f.write(content)

    # 解析 speaker_mapping
    mapping = None
    if speaker_mapping:
        try:
            raw = json.loads(speaker_mapping)
            mapping = {int(k): v for k, v in raw.items()}
        except Exception as e:
            logger.warning(f"解析 speaker_mapping 失败: {e}")

    # 创建任务记录
    now = datetime.now()
    tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "source": "upload",
        "progress": 0,
        "message": _("Awaiting processing"),
        "audio_name": file.filename,
        "audio_path": str(audio_path),
        "audio_duration": None,
        "speaker_count": None,
        "summary": None,
        "output_path": None,
        "created_at": now.isoformat(),
        "meeting_date": now.strftime("%Y-%m-%d"),
        "error": None,
        "error_category": None,
        "error_suggestion": None,
        "failed_stage": None,
        "retry_count": 0,
        "speaker_mapping": {},
    }

    # 后台执行（speaker_count 为 None 时 run_pipeline_task 内部自动估算）
    background_tasks.add_task(run_pipeline_task, task_id, audio_path, file.filename, mapping, speaker_count)

    return {"task_id": task_id, "status": "pending"}


@router.get("/api/tasks")
async def list_tasks():
    """获取任务列表"""
    task_list = sorted(
        tasks.values(),
        key=lambda x: (
            x.get("meeting_date") or x.get("created_at", ""),
            x.get("created_at", ""),
        ),
        reverse=True,
    )
    return {"tasks": task_list}


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    """查询任务状态（含 subprocess 状态检查）"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))
    task = tasks[task_id]
    # 录音中任务：附带实际已录制时长（供前端恢复累计计时）
    if task.get("status") == "recording" and is_stream_recording():
        info = get_stream_recording_info()
        if info:
            task = {**task, "elapsed": info["elapsed"]}
    # 已完成任务缺少章节时，后台自动补生成（兼容旧任务）
    if task.get("status") == "completed" and not task.get("chapters"):
        import threading

        from core.chapters import generate_chapters
        def _backfill_chapters():
            try:
                dialogue = task.get("dialogue", [])
                if not dialogue:
                    return
                from app.store import get_llm_config
                model = get_llm_config().get("model", "qwen-plus")
                chapters = generate_chapters(dialogue, model=model)
                tasks[task_id]["chapters"] = chapters
                save_task_to_disk(task_id)
                logger.info(f"[{task_id[:8]}] 补生成 {len(chapters)} 个章节")
            except Exception as e:
                logger.warning(f"[{task_id[:8]}] 补生成章节失败: {e}")
        threading.Thread(target=_backfill_chapters, daemon=True).start()
    return task


@router.get("/api/download/{task_id}")
def download_summary(task_id: str):
    """下载纪要文件

    注意：用 def（非 async def），FileResponse 涉及文件 I/O，
    FastAPI 自动在线程池中运行，避免阻塞事件循环。
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    output_path = task.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(404, _("Minutes file not found"))

    return FileResponse(
        output_path,
        media_type="text/markdown",
        filename=Path(output_path).name,
    )


@router.get("/api/audio/{task_id}")
def serve_audio(task_id: str):
    """提供会议录音音频文件（支持 Range 请求，实现拖动进度条）

    注意：用 def（非 async def），大音频文件 I/O 会阻塞事件循环。
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    audio_path = task.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(404, _("Recording file not found"))

    audio_file = Path(audio_path)
    # 根据扩展名确定 MIME 类型
    ext = audio_file.suffix.lower()
    mime_map = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".mp4": "audio/mp4",
        ".webm": "audio/webm",
    }
    media_type = mime_map.get(ext, "application/octet-stream")

    return FileResponse(
        str(audio_file),
        media_type=media_type,
        filename=audio_file.name,
    )


@router.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    """删除任务（含文件删除 I/O）"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks.pop(task_id)

    # 清理原始音频文件
    audio_path = task.get("audio_path")
    if audio_path and Path(audio_path).exists():
        Path(audio_path).unlink()

    # 清理归一化中间文件
    normalized_path = task.get("normalized_path")
    if normalized_path:
        np = Path(normalized_path)
        if np.exists() and (not audio_path or str(np) != str(audio_path)):
            np.unlink(missing_ok=True)
    # 兜底：按命名规则查找归一化文件（兼容旧任务无 normalized_path 字段）
    if audio_path:
        ap = Path(audio_path)
        for suffix_pattern in ["_normalized.wav", "_normalized_normalized.wav"]:
            candidate = ap.with_stem(f"{ap.stem}{suffix_pattern.replace('.wav', '')}").with_suffix(".wav")
            if candidate.exists() and str(candidate) != str(ap):
                candidate.unlink(missing_ok=True)
        # 清理 .raw 临时文件（按命名规则）
        raw_candidate = ap.with_suffix(".raw")
        if raw_candidate.exists():
            raw_candidate.unlink(missing_ok=True)

    # 清理纪要输出文件
    output_path = task.get("output_path")
    if output_path and Path(output_path).exists():
        Path(output_path).unlink()

    # 删除持久化文件：任务 JSON、作业日志、AI 洞察消息
    for suffix in [".json", ".joblog.jsonl", ".insights.json"]:
        f = TASKS_DIR / f"{task_id}{suffix}"
        if f.exists():
            f.unlink()

    return {"deleted": True}


@router.post("/api/tasks/{task_id}/retranscribe")
def retranscribe_task(task_id: str, background_tasks: BackgroundTasks):
    """
    重新识别录音文件（含文件检查 + 写 tasks JSON）。

    重置任务状态并重新执行转写管线（归一化 → 上传 → ASR → 说话人分离 → 纪要）。
    保留原始音频文件，清除旧的转写结果。
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    audio_path = task.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(404, _("Recording file not found, cannot re-transcribe"))

    # 重置任务状态
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 0
    tasks[task_id]["message"] = _("Re-transcribing...")
    tasks[task_id]["error"] = None
    tasks[task_id]["error_category"] = None
    tasks[task_id]["error_suggestion"] = None
    tasks[task_id]["failed_stage"] = None
    tasks[task_id]["retry_count"] = 0
    tasks[task_id]["summary"] = None
    tasks[task_id]["output_path"] = None
    tasks[task_id]["dialogue"] = None
    tasks[task_id]["transcription"] = None
    tasks[task_id]["speaker_count"] = None
    tasks[task_id]["speaker_mapping"] = {}
    tasks[task_id]["speaker_uuid_mapping"] = {}
    tasks[task_id]["title"] = None
    tasks[task_id]["voiceprint_match"] = None
    tasks[task_id]["voiceprint_auto_mapping"] = None
    save_task_to_disk(task_id)

    # 后台重新执行管线（speaker_count 为 None 时自动估算）
    audio_name = task.get("audio_name", Path(audio_path).name)
    background_tasks.add_task(run_pipeline_task, task_id, Path(audio_path), audio_name, None, None)

    logger.info(f"[重新识别] task={task_id[:8]}, audio={audio_name}")
    return {"status": "processing", "message": _("Re-transcription task submitted")}


@router.post("/api/tasks/{task_id}/retry-summary")
def retry_summary(task_id: str, background_tasks: BackgroundTasks):
    """
    仅重新生成纪要（转写结果已存在时，含文件检查 + 写 tasks JSON）。

    当转写成功但纪要生成失败时，无需重跑耗时的 ASR，只重跑纪要阶段。
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    if not task.get("dialogue"):
        raise HTTPException(400, _("Transcription result not found, please use Re-transcribe"))

    audio_path = task.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(404, _("Recording file not found"))

    # 只重置 stage2 相关字段
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 75
    tasks[task_id]["message"] = _("Regenerating minutes...")
    tasks[task_id]["error"] = None
    tasks[task_id]["error_category"] = None
    tasks[task_id]["error_suggestion"] = None
    tasks[task_id]["failed_stage"] = None
    tasks[task_id]["retry_count"] = 0
    tasks[task_id]["summary"] = None
    tasks[task_id]["output_path"] = None
    tasks[task_id]["title"] = None
    save_task_to_disk(task_id)

    # 恢复说话人映射，后台重新生成纪要
    audio_path = Path(audio_path)
    mapping = {int(k): v for k, v in task.get("speaker_uuid_mapping", {}).items()}
    background_tasks.add_task(run_stage2_task, task_id, audio_path, mapping)

    logger.info(f"[重新生成纪要] task={task_id[:8]}")
    return {"status": "processing", "message": _("Regenerating minutes...")}


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, data: TaskUpdate):
    """更新任务信息（写 tasks JSON）"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    changed = False
    if data.title is not None:
        tasks[task_id]["title"] = data.title.strip() or None
        changed = True
    if data.meeting_date is not None:
        # 验证日期格式
        try:
            datetime.strptime(data.meeting_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, _("Invalid date format, expected YYYY-MM-DD"))
        tasks[task_id]["meeting_date"] = data.meeting_date
        changed = True
    if data.project_id is not None:
        # 空字符串 = 取消关联，非空 = 绑定项目
        tasks[task_id]["project_id"] = data.project_id.strip() or None
        changed = True
    if changed:
        save_task_to_disk(task_id)

    return tasks[task_id]


@router.get("/api/tasks/{task_id}/sync-status")
def get_task_sync_status(task_id: str):
    """查询任务的项目同步状态：是否可同步、目标文件夹信息"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    project_id = task.get("project_id")
    if not project_id or task.get("status") != "completed":
        return {"can_sync": False, "reason": _("Task not completed or not linked to a knowledge base")}

    from core.projects import get_project, get_sync_enabled_folders
    project = get_project(project_id)
    if not project:
        return {"can_sync": False, "reason": _("Linked knowledge base does not exist")}

    sync_folders = get_sync_enabled_folders(project_id)
    if not sync_folders:
        return {"can_sync": False, "reason": _("Knowledge base folder sync not enabled")}

    return {
        "can_sync": True,
        "project_name": project.get("name", ""),
        "folders": [
            {
                "path": f["path"],
                "subfolder": f.get("subfolder_name", ".meetings"),
                "content_types": f.get("content_types", ["summary", "action_items"]),
            }
            for f in sync_folders
        ],
    }


@router.post("/api/tasks/{task_id}/archive")
def archive_task(task_id: str):
    """归档任务（标记 archived_at 时间戳）"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))
    tasks[task_id]["archived_at"] = datetime.now().isoformat()
    save_task_to_disk(task_id)
    logger.info(f"[{task_id[:8]}] 任务已归档")
    return tasks[task_id]


@router.post("/api/tasks/{task_id}/unarchive")
def unarchive_task(task_id: str):
    """取消归档"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))
    tasks[task_id]["archived_at"] = None
    save_task_to_disk(task_id)
    logger.info(f"[{task_id[:8]}] 任务已取消归档")
    return tasks[task_id]


@router.post("/api/tasks/batch-archive")
def batch_archive_tasks(data: BatchArchiveRequest):
    """批量归档任务"""
    archived = []
    for task_id in data.task_ids:
        if task_id in tasks:
            tasks[task_id]["archived_at"] = datetime.now().isoformat()
            save_task_to_disk(task_id)
            archived.append(task_id)
    logger.info(f"批量归档 {len(archived)}/{len(data.task_ids)} 个任务")
    return {"archived": len(archived)}


@router.post("/api/tasks/{task_id}/sync-to-project")
def sync_task_to_project(task_id: str):
    """手动将会议纪要同步写入关联项目的文件夹"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    if task.get("status") != "completed":
        raise HTTPException(400, _("Task not completed, cannot sync"))

    project_id = task.get("project_id")
    if not project_id:
        raise HTTPException(400, _("Task is not linked to a knowledge base"))

    from core.projects import sync_meeting_to_folders
    written = sync_meeting_to_folders(task)
    if not written:
        return {"synced": False, "message": _("No target folder to sync")}

    logger.info(f"[{task_id[:8]}] 手动同步到项目文件夹，写入 {len(written)} 个文件")
    return {
        "synced": True,
        "files": written,
        "message": _("Wrote {count} file(s) to knowledge base folder").format(count=len(written)),
    }
