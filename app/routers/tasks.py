"""
app/routers/tasks.py — 转录提交 + 任务 CRUD + 音频/下载 / Transcription submission + task CRUD + audio/download

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 1.0.0
"""

import copy
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, field_validator

from app.store import (
    TASKS_DIR,
    UPLOAD_DIR,
    get_transcript_config,
    run_pipeline_task,
    run_stage2_task,
    save_task_to_disk,
    tasks,
)
from core.audio import get_stream_recording_info, is_stream_recording
from core.fs_atomic import stream_save_upload
from core.i18n import _
from core.transcript_cleanup import enrich_sentence

logger = logging.getLogger(__name__)

# 章节补生成去重锁：避免前端轮询每次 get_task 都启动新线程
# Chapters backfill in-flight guard: prevent spawning a new thread on every poll.
_chapters_backfill_inflight: set[str] = set()
# 已确认空转写的任务（dialogue 为空，无法补生成章节）
# Tasks confirmed to have empty transcription (cannot backfill chapters).
_chapters_empty_confirmed: set[str] = set()

router = APIRouter(tags=["tasks"])


class TranscribeRequest(BaseModel):
    speaker_mapping: Optional[dict[str, str]] = None  # {"0": "uuid1", "1": "uuid2"} 说话人映射 / Speaker mapping


class FormalizeRequest(BaseModel):
    """AI 书面化（PLAN-TRANSCRIPT-LAYERING WP-2）：sentence_ids 省略＝整场。"""
    sentence_ids: Optional[list[int]] = None


class OnePageConfig(BaseModel):
    """一页纸系数（会议级）：纪要/洞察各自一页、互不相加；仅改提供的键。
    契约见 docs/API_CONTRACTS.md one_page 条目。"""
    summary: Optional[float] = None
    insights: Optional[float] = None

    @field_validator("summary", "insights")
    @classmethod
    def _check_level(cls, v):
        # 合法档位 {0.5, 1, 1.5, 2}；接受 int 形式（JSON 1 → 1.0）
        if v is None:
            return v
        if v not in (0.5, 1.0, 1.5, 2.0):
            raise ValueError("one_page 系数仅支持 0.5 / 1 / 1.5 / 2 四档")
        return float(v)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    meeting_date: Optional[str] = None  # "YYYY-MM-DD"，用户指定的实际开会日期 / Actual meeting date specified by user
    project_id: Optional[str] = None  # 关联的项目 ID，传空字符串表示取消关联 / Linked project ID; empty string to unlink
    one_page: Optional[OnePageConfig] = None  # 一页纸系数（仅改提供键）/ Per-meeting one-page factors; partial update


class BatchArchiveRequest(BaseModel):
    task_ids: list[str]


class RetranscribeRequest(BaseModel):
    """重新识别请求体（全部字段可选，向后兼容无 body 调用）。"""

    engine_override: Optional[str] = None  # DEF-QA-R1-04（AC-4）：显式 "cloud"=切云端重跑；None=按当前设置


class CorrectTextRequest(BaseModel):
    """划词映射的全量回溯修正请求体 / Retroactive term correction request.

    old 是误识别写法（映射左值），new 是正确文本（映射右值）。
    """

    old: str
    new: str


@router.post("/api/transcribe")
async def create_transcribe_task(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    speaker_mapping: Optional[str] = None,  # JSON string: {"0": "uuid1", "1": "uuid2"}
    speaker_count: Optional[int] = Form(None),  # 说话人数量提示（2-100）；不传则自动估算 / Speaker count hint (2-100); auto-estimate if omitted
):
    """上传音频并提交转写任务 / Upload audio and submit transcription task"""
    # 验证文件类型 / Validate file type
    allowed_types = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".webm"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_types:
        raise HTTPException(400, _("Unsupported file type: {ext}").format(ext=file_ext))

    # 验证 speaker_count 范围 / Validate speaker_count range
    if speaker_count is not None and (speaker_count < 1 or speaker_count > 100):
        raise HTTPException(400, _("speaker_count must be between 1 and 100"))

    # 配额预检：订阅用户额度用尽时阻止上传（自带 Key 用户不受限） / Quota pre-check: block upload when subscribed user quota exhausted (BYOK users unaffected)
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

    # 保存上传文件（流式分块读取，避免大文件 OOM） / Save uploaded file (stream chunked read, avoid OOM on large files)
    task_id = str(uuid.uuid4())
    safe_name = f"{task_id[:8]}_{file.filename}"
    audio_path = UPLOAD_DIR / safe_name

    MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
    await stream_save_upload(file, audio_path, max_size=MAX_UPLOAD_SIZE)

    # 解析 speaker_mapping / Parse speaker_mapping
    mapping = None
    if speaker_mapping:
        try:
            raw = json.loads(speaker_mapping)
            mapping = {int(k): v for k, v in raw.items()}
        except Exception as e:
            logger.warning(f"解析 speaker_mapping 失败: {e}")

    # 创建任务记录 / Create task record
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

    # 后台执行（speaker_count 为 None 时 run_pipeline_task 内部自动估算） / Run in background (speaker_count auto-estimated internally when None)
    background_tasks.add_task(run_pipeline_task, task_id, audio_path, file.filename, mapping, speaker_count)

    return {"task_id": task_id, "status": "pending"}


def _with_transcript_layers(task: dict) -> dict:
    """响应级附加转写分层（PLAN-TRANSCRIPT-LAYERING）：深拷贝 dialogue 富化 clean_text，
    加 transcript_layers 信封；绝不写回内存 task / 磁盘。列表与详情端点共用。"""
    try:
        cleanup_enabled = bool(get_transcript_config().get("cleanup", {}).get("enabled", True))
    except Exception:
        cleanup_enabled = True
    response = {"transcript_layers": {"cleanup": cleanup_enabled}}
    if cleanup_enabled:
        enriched_dialogue = copy.deepcopy(task.get("dialogue") or [])
        for block in enriched_dialogue:
            if not isinstance(block, dict):
                continue
            for sentence in block.get("sentences") or []:
                if isinstance(sentence, dict):
                    enrich_sentence(sentence)
        response["dialogue"] = enriched_dialogue
    return {**task, **response}


# 轻量列表（完成侦测器 5s 轮询用）：只回状态与标识字段，不含 dialogue/chapters/todos
# Lite list for the completion watcher poll: status/identity fields only, no heavy artifacts.
_LIST_LITE_FIELDS = (
    "task_id", "status", "progress", "message", "title", "audio_name",
    "meeting_date", "created_at", "archived_at",
    "error", "error_category", "error_suggestion", "failed_stage", "retry_count",
)


def _json_default(obj):
    """直出序列化兜底：bytes 按 FastAPI 旧 jsonable_encoder 口径 decode，其余 str 化。"""
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).decode("utf-8", errors="replace")
    return str(obj)


@router.get("/api/tasks")
def list_tasks(view: str = "full"):
    """获取任务列表 / Get task list.

    view=lite：仅状态字段（供高频状态轮询，响应体小、不做转写富化）。 /
    view=lite: status fields only (for frequent status polling; small payload, no transcript enrichment).
    同步 def：重活（富化/序列化大对象）放线程池，不阻塞事件循环上的其他请求。 /
    sync def: heavy work runs in the worker threadpool instead of blocking the event loop.
    """
    task_list = sorted(
        tasks.values(),
        key=lambda x: (
            x.get("meeting_date") or x.get("created_at", ""),
            x.get("created_at", ""),
        ),
        reverse=True,
    )
    if view == "lite":
        payload = [{k: t.get(k) for k in _LIST_LITE_FIELDS if k in t} for t in task_list]
    else:
        payload = [_with_transcript_layers(task) for task in task_list]
    # 预序列化直出：默认 FastAPI jsonable_encoder 会逐元素校验整棵转写树（实测 36MB/76 场耗时 3~8s），
    # 任务数据来自 JSON 落盘，原生可序列化；bytes（个别运行时字段）按旧编码器口径 decode 兜底。
    body = json.dumps(
        {"tasks": payload}, ensure_ascii=False, separators=(",", ":"), default=_json_default,
    ).encode("utf-8")
    return Response(content=body, media_type="application/json")


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    """查询任务状态（含 subprocess 状态检查） / Get task status (incl. subprocess status check)"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))
    task = tasks[task_id]
    # 录音中任务：附带实际已录制时长（供前端恢复累计计时） / Recording task: include actual elapsed time (for frontend to restore timer)
    if task.get("status") == "recording" and is_stream_recording():
        info = get_stream_recording_info()
        if info:
            task = {**task, "elapsed": info["elapsed"]}
    # 已完成任务缺少章节时，后台自动补生成（兼容旧任务） / Auto-backfill chapters for completed tasks missing them (backward compat)
    if task.get("status") == "completed" and not task.get("chapters"):
        dialogue = task.get("dialogue", [])
        if not dialogue:
            # 空转写任务无法补生成章节；记录一次日志即可，前端靠 flatTranscript 判空显示空态
            # Empty transcription cannot backfill chapters; log once, frontend shows empty state.
            if task_id not in _chapters_empty_confirmed:
                _chapters_empty_confirmed.add(task_id)
                logger.info(f"[{task_id[:8]}] 转写为空，跳过章节补生成")
        elif task_id not in _chapters_backfill_inflight:
            import threading

            from core.chapters import generate_chapters
            _chapters_backfill_inflight.add(task_id)

            def _backfill_chapters():
                try:
                    from app.store import get_llm_config, get_transcript_config
                    from core.transcript_cleanup import clean_dialogue_for_consumers
                    model = get_llm_config().get("model", "qwen-plus")
                    # PLAN-TRANSCRIPT-LAYERING：章节吃清理版（深拷贝），task.dialogue 原文不动
                    enabled = bool(get_transcript_config().get("cleanup", {}).get("enabled", True))
                    chapters = generate_chapters(
                        clean_dialogue_for_consumers(dialogue, enabled=enabled), model=model
                    )
                    tasks[task_id]["chapters"] = chapters
                    save_task_to_disk(task_id)
                    logger.info(f"[{task_id[:8]}] 补生成 {len(chapters)} 个章节")
                except Exception as e:
                    logger.warning(f"[{task_id[:8]}] 补生成章节失败: {e}")
                finally:
                    _chapters_backfill_inflight.discard(task_id)
            threading.Thread(target=_backfill_chapters, daemon=True).start()

    # 转写分层（PLAN-TRANSCRIPT-LAYERING）：响应级富化清理版，绝不写回内存 task / 磁盘。
    # 热词回溯修正原文后，下次读取自动重算；存量会议零迁移。
    return _with_transcript_layers(task)


@router.post("/api/tasks/{task_id}/formalize")
def formalize_task(task_id: str, data: FormalizeRequest, background_tasks: BackgroundTasks):
    """AI 书面化（PLAN-TRANSCRIPT-LAYERING WP-2）：仅会后；先写 running sidecar，后台生成。

    sentence_ids 省略＝整场；带 id＝选区（WP-3，同端点 upsert）。
    会中/任务不存在/路由不可用/已有任务在跑 → 409（detail 带 code/reason）。
    """
    from core.transcript_formal import (
        FormalizeError,
        generate_formal_version,
        prepare_formalize,
    )

    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    ids = data.sentence_ids
    if ids is not None:
        if not ids or any(not isinstance(i, int) for i in ids):
            raise HTTPException(422, "sentence_ids must be a non-empty list of integers")
        ids = ids[:2000]  # 上限保护 / Upper bound guard

    try:
        prepare_formalize(task_id, ids)
    except FormalizeError as e:
        raise HTTPException(
            status_code=e.http_status,
            detail={"code": e.code, "reason": e.reason},
        )

    background_tasks.add_task(generate_formal_version, task_id, ids, _reserve=False)
    logger.info(f"[书面版] task={task_id[:8]} 已排队 scope={'selection' if ids else 'full'}")
    return {"status": "running", "scope": "selection" if ids else "full"}


@router.get("/api/tasks/{task_id}/formal")
def get_formal(task_id: str):
    """读取书面版 sidecar（实时 staleness 判定）；从未生成 → 404。"""
    from core.transcript_formal import load_formal

    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))
    doc = load_formal(task_id, tasks[task_id].get("dialogue"))
    if doc is None:
        raise HTTPException(404, "formal version not found")
    return doc


@router.get("/api/download/{task_id}")
def download_summary(task_id: str, format: str = "md"):
    """下载纪要文件 / Download summary file

    format=md（默认，向后兼容）→ Markdown 原文；format=docx → Word 纪要
    （DEF-QA-R1-02：标题/说话人段落/列表映射为 Word 结构，中文不乱码）。

    注意：用 def（非 async def），FileResponse 涉及文件 I/O，
    Note: uses def (not async def); FileResponse involves file I/O,
    FastAPI 自动在线程池中运行，避免阻塞事件循环。 / FastAPI auto-runs in thread pool to avoid blocking event loop.
    """
    if format not in ("md", "docx"):
        raise HTTPException(400, _("Unsupported download format: {format}").format(format=format))
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    output_path = task.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(404, _("Minutes file not found"))

    if format == "md":
        return FileResponse(
            output_path,
            media_type="text/markdown",
            filename=Path(output_path).name,
        )

    from core.docx_export import export_task_docx

    stem = Path(output_path).stem
    docx_path = Path(output_path).parent / f"{stem}.docx"
    try:
        export_task_docx(task, docx_path)
    except Exception as e:
        logger.exception(f"[{task_id[:8]}] docx 导出失败")
        raise HTTPException(500, _("Failed to generate docx: {error}").format(error=e))

    return FileResponse(
        str(docx_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=docx_path.name,
    )


@router.get("/api/audio/{task_id}")
def serve_audio(task_id: str):
    """提供会议录音音频文件（支持 Range 请求，实现拖动进度条） / Serve meeting recording audio (supports Range requests for seeking)

    注意：用 def（非 async def），大音频文件 I/O 会阻塞事件循环。 / Note: uses def (not async def); large audio file I/O would block event loop.
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    audio_path = task.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(404, _("Recording file not found"))

    audio_file = Path(audio_path)
    # 根据扩展名确定 MIME 类型 / Determine MIME type from extension
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
    """删除任务（含文件删除 I/O） / Delete task (incl. file deletion I/O)"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks.pop(task_id)

    # 清理原始音频文件 / Clean up original audio file
    audio_path = task.get("audio_path")
    if audio_path and Path(audio_path).exists():
        Path(audio_path).unlink()

    # 清理归一化中间文件 / Clean up normalized intermediate file
    normalized_path = task.get("normalized_path")
    if normalized_path:
        np = Path(normalized_path)
        if np.exists() and (not audio_path or str(np) != str(audio_path)):
            np.unlink(missing_ok=True)
    # 兜底：按命名规则查找归一化文件（兼容旧任务无 normalized_path 字段） / Fallback: find normalized files by naming convention (backward compat for tasks without normalized_path)
    if audio_path:
        ap = Path(audio_path)
        for suffix_pattern in ["_normalized.wav", "_normalized_normalized.wav"]:
            candidate = ap.with_stem(f"{ap.stem}{suffix_pattern.replace('.wav', '')}").with_suffix(".wav")
            if candidate.exists() and str(candidate) != str(ap):
                candidate.unlink(missing_ok=True)
        # 清理 .raw 临时文件（按命名规则） / Clean up .raw temp files (by naming convention)
        raw_candidate = ap.with_suffix(".raw")
        if raw_candidate.exists():
            raw_candidate.unlink(missing_ok=True)

    # 清理纪要输出文件 / Clean up summary output file
    output_path = task.get("output_path")
    if output_path and Path(output_path).exists():
        Path(output_path).unlink()
    # 清理按需生成的 docx 伴生文件（DEF-QA-R1-02：下载时写入同目录同名 .docx）
    if output_path:
        Path(output_path).with_suffix(".docx").unlink(missing_ok=True)

    # 删除持久化文件：任务 JSON、作业日志、AI 洞察消息 / Delete persisted files: task JSON, job log, AI insights
    for suffix in [".json", ".joblog.jsonl", ".insights.json"]:
        f = TASKS_DIR / f"{task_id}{suffix}"
        if f.exists():
            f.unlink()

    return {"deleted": True}


@router.post("/api/tasks/{task_id}/retranscribe")
def retranscribe_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    data: Optional[RetranscribeRequest] = None,
):
    """重新识别录音文件（含文件检查 + 写 tasks JSON） / Re-transcribe recording (incl. file check + write tasks JSON).

    重置任务状态并重新执行转写管线（归一化 → 上传 → ASR → 说话人分离 → 纪要）。 / Reset task state and re-run pipeline (normalize -> upload -> ASR -> diarization -> summary).
    保留原始音频文件，清除旧的转写结果。 / Keep original audio, clear old transcription results.

    DEF-QA-R1-04（AC-4 回退）：body.engine_override 传显式 "cloud" 时，本次重跑强制走
    云端转写（用于本地引擎失败后用户显式确认「切云端重跑」；绝不静默上云——必须由调用方
    显式声明）。任务音频与笔记状态不丢失（引擎选择不改变上方字段重置范围）。
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    audio_path = task.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(404, _("Recording file not found, cannot re-transcribe"))

    # engine_override 白名单：仅显式 "cloud"（当前缺陷范围）；其余值拒绝，防误配静默改道
    engine_override = (data.engine_override or "").strip().lower() if data and data.engine_override else None
    if engine_override is not None and engine_override != "cloud":
        raise HTTPException(
            400,
            _("Unsupported engine_override: {value} (only \"cloud\" is allowed)").format(value=engine_override),
        )
    if engine_override == "cloud":
        from core.cloud_client import is_cloud_enabled
        if not is_cloud_enabled():
            raise HTTPException(400, _("Cloud service is not configured. Connect to cloud or configure an API Key before retrying in the cloud."))

    # 重置任务状态 / Reset task state
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 0
    tasks[task_id]["message"] = _("Re-transcribing...")
    tasks[task_id]["error"] = None
    tasks[task_id]["error_category"] = None
    tasks[task_id]["error_suggestion"] = None
    tasks[task_id]["error_code"] = None
    tasks[task_id]["can_fallback_cloud"] = None
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

    # 后台重新执行管线（speaker_count 为 None 时自动估算） / Re-run pipeline in background (speaker_count auto-estimated when None)
    audio_name = task.get("audio_name", Path(audio_path).name)
    if engine_override == "cloud":
        from core import joblog
        joblog.append_event(
            task_id, joblog.STAGE_TRANSCRIBE,
            "用户显式确认切云端重跑（AC-4 engine_override=cloud）",
        )
        logger.info(f"[重新识别] task={task_id[:8]} 显式切换云端引擎重跑（AC-4）")
    background_tasks.add_task(
        run_pipeline_task, task_id, Path(audio_path), audio_name, None, None, engine_override
    )

    logger.info(f"[重新识别] task={task_id[:8]}, audio={audio_name}")
    return {"status": "processing", "message": _("Re-transcription task submitted")}


@router.post("/api/tasks/{task_id}/retry-summary")
def retry_summary(task_id: str, background_tasks: BackgroundTasks):
    """仅重新生成纪要（转写结果已存在时，含文件检查 + 写 tasks JSON） / Regenerate summary only (when transcription exists; incl. file check + write tasks JSON).

    当转写成功但纪要生成失败时，无需重跑耗时的 ASR，只重跑纪要阶段。 / When transcription succeeded but summary failed, skip costly ASR and only re-run summary stage.
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    task = tasks[task_id]
    if not task.get("dialogue"):
        raise HTTPException(400, _("Transcription result not found, please use Re-transcribe"))

    audio_path = task.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(404, _("Recording file not found"))

    # 只重置 stage2 相关字段 / Only reset stage2-related fields
    # 保留旧 summary/title/output_path：重生成失败时旧产物不丢（模型误拒曾覆盖好纪要）
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 75
    tasks[task_id]["message"] = _("Regenerating minutes...")
    tasks[task_id]["error"] = None
    tasks[task_id]["error_category"] = None
    tasks[task_id]["error_suggestion"] = None
    tasks[task_id]["failed_stage"] = None
    tasks[task_id]["retry_count"] = 0
    save_task_to_disk(task_id)

    # 恢复说话人映射，后台重新生成纪要 / Restore speaker mapping, regenerate summary in background
    audio_path = Path(audio_path)
    mapping = {int(k): v for k, v in task.get("speaker_uuid_mapping", {}).items()}
    background_tasks.add_task(run_stage2_task, task_id, audio_path, mapping)

    logger.info(f"[重新生成纪要] task={task_id[:8]}")
    return {"status": "processing", "message": _("Regenerating minutes...")}


def _rebalance_insight_budget(task_id: str, factor) -> None:
    """按新系数立即重排洞察卡集可见层（deferred 标记搬家，不调 LLM）。

    失败不阻断 PATCH 主流程（系数已落盘，下次保存/分析路径会重新收口）。"""
    try:
        from app.routers.insights import _insights_file, _load_insight_messages
        from core.fs_atomic import atomic_write_json
        from core.insight_budget import apply_budget
        messages = _load_insight_messages(task_id)
        if not messages:
            return
        rebalanced = apply_budget(messages, factor)
        if rebalanced != messages:
            TASKS_DIR.mkdir(parents=True, exist_ok=True)
            atomic_write_json(_insights_file(task_id), {"messages": rebalanced})
            logger.info("[一页纸系数] task=%s 洞察卡集已按系数 %s 重排", task_id[:8], factor)
    except Exception as e:
        logger.warning("[一页纸系数] task=%s 洞察卡集重排失败（不影响系数保存）: %s", task_id[:8], e)


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, data: TaskUpdate):
    """更新任务信息（写 tasks JSON） / Update task info (write tasks JSON)"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    changed = False
    if data.title is not None:
        tasks[task_id]["title"] = data.title.strip() or None
        changed = True
    if data.meeting_date is not None:
        # 验证日期格式 / Validate date format
        try:
            datetime.strptime(data.meeting_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, _("Invalid date format, expected YYYY-MM-DD"))
        tasks[task_id]["meeting_date"] = data.meeting_date
        changed = True
    if data.project_id is not None:
        # 空字符串 = 取消关联，非空 = 绑定项目 / Empty string = unlink; non-empty = bind project
        tasks[task_id]["project_id"] = data.project_id.strip() or None
        changed = True
    if data.one_page is not None:
        # 仅覆盖显式提供的键；系数变更不改纪要内容，不标 last_modified_at（避免误触发知识库重同步）
        old = dict(tasks[task_id].get("one_page") or {})
        new = dict(old)
        insights_changed = False
        for key in ("summary", "insights"):
            if key in data.one_page.model_fields_set:
                val = getattr(data.one_page, key)
                if val is not None and new.get(key) != val:
                    new[key] = val
                    if key == "insights":
                        insights_changed = True
        tasks[task_id]["one_page"] = new
        save_task_to_disk(task_id)
        if insights_changed:
            # 洞察改档立即重排卡集可见层（纯展示侧搬家，不耗 LLM 配额）
            _rebalance_insight_budget(task_id, new.get("insights", 1))
    if changed:
        # 标记内容已修改，用于知识库同步脏检测 / Mark content as modified for KB sync dirty detection
        tasks[task_id]["last_modified_at"] = datetime.now().isoformat()
        save_task_to_disk(task_id)

    return tasks[task_id]


@router.post("/api/tasks/{task_id}/correct-text")
def correct_task_text_endpoint(task_id: str, data: CorrectTextRequest):
    """把一条「误识别→正确文本」映射全量回溯应用到本场会议 / Apply one wrong→correct mapping retroactively.

    热词映射本身只在转写时刻生效（core.hotwords.apply_hotword_mappings），已存会议的旧文本
    不受影响；本端点补上回溯这一环：任务对象 + 洞察 JSON + 洞察板 HTML + 导出纪要 md 一并改写。
    命中明细随响应返回，前端据此报真实数量（旧实现只改 DOM 且无条件报「已修正」）。

    注意：用 def（非 async def），多份文件的读写 I/O 会阻塞事件循环，
    FastAPI 自动在线程池执行。 / Uses def so file I/O runs in the thread pool.
    """
    old, new = data.old.strip(), data.new.strip()
    if not old or not new:
        raise HTTPException(400, _("Correction source and target must not be empty"))
    if old == new:
        raise HTTPException(400, _("Correction source and target are identical"))
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    from core.text_correction import correct_task_text

    try:
        result = correct_task_text(tasks[task_id], task_id, old, new)
    except Exception as e:
        logger.exception(f"[{task_id[:8]}] 文本回溯修正失败")
        raise HTTPException(500, _("Text correction failed: {error}").format(error=e))

    if result["hits"]["task"]:
        # 任务主体确实变了才落盘；顺带置脏，让知识库同步提示跟上手改
        # Persist only when the task body actually changed; mark dirty for KB sync.
        tasks[task_id]["last_modified_at"] = datetime.now().isoformat()
        save_task_to_disk(task_id)
    if result["residual"]:
        # 白名单没覆盖到的位置：不静默，留条痕供补录 REWRITE_KEYS
        # Leftovers mean REWRITE_KEYS is incomplete — surface it instead of swallowing.
        logger.warning(
            "[%s] 文本修正后仍残留 %s 处，需补充 core.text_correction.REWRITE_KEYS",
            task_id[:8], result["residual"],
        )
    return result


@router.get("/api/tasks/{task_id}/sync-status")
def get_task_sync_status(task_id: str):
    """查询任务的项目同步状态：是否可同步、目标文件夹信息 / Get task project sync status: whether syncable, target folder info"""
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
        # 脏检测：比较 last_modified_at 与 last_synced_at / Dirty detection: compare last_modified_at vs last_synced_at
        "is_dirty": (task.get("last_modified_at") or "") > (task.get("last_synced_at") or ""),
        "last_synced_at": task.get("last_synced_at"),
        "last_modified_at": task.get("last_modified_at"),
    }


@router.post("/api/tasks/{task_id}/archive")
def archive_task(task_id: str):
    """归档任务（标记 archived_at 时间戳） / Archive task (mark archived_at timestamp)"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))
    tasks[task_id]["archived_at"] = datetime.now().isoformat()
    save_task_to_disk(task_id)
    logger.info(f"[{task_id[:8]}] 任务已归档")
    return tasks[task_id]


@router.post("/api/tasks/{task_id}/unarchive")
def unarchive_task(task_id: str):
    """取消归档 / Unarchive task"""
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))
    tasks[task_id]["archived_at"] = None
    save_task_to_disk(task_id)
    logger.info(f"[{task_id[:8]}] 任务已取消归档")
    return tasks[task_id]


@router.post("/api/tasks/batch-archive")
def batch_archive_tasks(data: BatchArchiveRequest):
    """批量归档任务 / Batch archive tasks"""
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
    """手动将会议纪要同步写入关联项目的文件夹 / Manually sync meeting summary to linked project folders"""
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
