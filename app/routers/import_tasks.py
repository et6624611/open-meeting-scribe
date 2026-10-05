"""
app/routers/import_tasks.py — 统一导入端点 / Unified import endpoint

职责 / Responsibilities:
  1. 接收文件上传或文字粘贴，智能识别内容类型
  2. 音频文件 → 转发到现有转写管线
  3. 文档文件 → 解析为 dialogue 或直接存为 summary
  4. 重复检测与提示

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-18
版本 / Version: 1.0.0
"""

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.store import (
    TASKS_DIR,
    save_task_to_disk,
    tasks,
)
from core.fs_atomic import stream_save_upload
from core.i18n import _
from core.import_parser import (
    AUDIO_EXTENSIONS,
    CONTENT_TYPE_SUMMARY,
    CONTENT_TYPE_TRANSCRIPT,
    classify_file_type,
    find_duplicate_task,
    infer_title_from_content,
    parse_document_content,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["import"])


# ============================================================
# 请求/响应模型 / Request/Response models
# ============================================================

class ImportTextRequest(BaseModel):
    """粘贴文字导入请求 / Paste text import request"""
    content: str
    title: Optional[str] = None
    project_id: Optional[str] = None


class ImportCheckDuplicateRequest(BaseModel):
    """重复检测请求 / Duplicate detection request"""
    filename: str
    file_size: int


class ImportCheckDuplicateResponse(BaseModel):
    """重复检测响应 / Duplicate detection response"""
    is_duplicate: bool
    existing_task_id: Optional[str] = None
    existing_task_title: Optional[str] = None
    existing_task_date: Optional[str] = None
    existing_task_status: Optional[str] = None


# ============================================================
# 重复检测端点 / Duplicate detection endpoint
# ============================================================

@router.post("/api/import/check-duplicate")
def check_duplicate(req: ImportCheckDuplicateRequest):
    """检查文件是否已导入过 / Check if file has already been imported.

    前端在用户选择文件后、提交导入前调用此端点。
    Frontend calls this after user selects file, before submitting import.
    """
    matched = find_duplicate_task(req.filename, req.file_size, tasks)
    if matched:
        return ImportCheckDuplicateResponse(
            is_duplicate=True,
            existing_task_id=matched.get("task_id"),
            existing_task_title=matched.get("title") or matched.get("audio_name"),
            existing_task_date=matched.get("meeting_date"),
            existing_task_status=matched.get("status"),
        )
    return ImportCheckDuplicateResponse(is_duplicate=False)


# ============================================================
# 文件导入端点 / File import endpoint
# ============================================================

@router.post("/api/import/file")
async def import_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
):
    """统一文件导入 / Unified file import.

    支持的文件类型 / Supported file types:
      - 音频文件：走现有 ASR 管线 / Audio files: use existing ASR pipeline
      - 文档文件（.md/.txt/.srt/.vtt）：智能识别为原文或纪要 / Documents: smart detect as transcript or summary
      - 图片文件（Phase 2）/ Image files (Phase 2)
    """
    filename = file.filename or "unknown"
    file_type = classify_file_type(filename)

    if file_type == "unsupported":
        raise HTTPException(400, _("Unsupported file type: {ext}").format(ext=Path(filename).suffix))

    # ── 音频文件：转发到现有转写管线 / Audio: forward to existing transcription pipeline ──
    if file_type == "audio":
        return await _import_as_audio(background_tasks, file, title, project_id)

    # ── 文档文件：解析并创建任务 / Document: parse and create task ──
    if file_type == "document":
        return await _import_as_document(file, title, project_id, background_tasks)

    # ── 图片文件（Phase 2）/ Image files (Phase 2) ──
    if file_type == "image":
        raise HTTPException(
            400,
            _("Image import is not yet supported. Please use audio or document files.")
        )

    raise HTTPException(400, _("Unsupported file type"))


async def _import_as_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    title: Optional[str],
    project_id: Optional[str],
) -> dict:
    """音频文件导入：复用现有转写管线 / Audio import: reuse existing transcription pipeline."""
    from app.routers.tasks import UPLOAD_DIR, run_pipeline_task

    # 保存上传文件（流式分块读取，避免大文件 OOM） / Save uploaded file (stream chunked read, avoid OOM on large files)
    task_id = str(uuid.uuid4())
    safe_name = f"{task_id[:8]}_{file.filename}"
    audio_path = UPLOAD_DIR / safe_name

    MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
    file_size = await stream_save_upload(file, audio_path, max_size=MAX_UPLOAD_SIZE)
    if file_size == 0:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(400, _("Empty file"))

    # 创建任务记录 / Create task record
    now = datetime.now()
    tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "source": "upload",
        "progress": 0,
        "message": _("Awaiting processing"),
        "audio_name": file.filename,
        "audio_size": file_size,
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

    if title:
        tasks[task_id]["title"] = title
    if project_id:
        tasks[task_id]["project_id"] = project_id

    # 后台执行管线 / Run pipeline in background
    background_tasks.add_task(run_pipeline_task, task_id, audio_path, file.filename, None, None)

    return {"task_id": task_id, "status": "pending", "import_type": "audio"}


async def _import_as_document(
    file: UploadFile,
    title: Optional[str],
    project_id: Optional[str],
    background_tasks: BackgroundTasks,
) -> dict:
    """文档文件导入：解析内容并创建任务 / Document import: parse content and create task."""
    # 流式分块读取并校验大小，避免超大文件 OOM / Stream chunked read with size check, avoid OOM on oversized files
    MAX_DOC_SIZE = 100 * 1024 * 1024  # 100 MB — 文档文件合理上限 / Reasonable limit for document files
    from core.fs_atomic import UPLOAD_CHUNK_SIZE

    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_DOC_SIZE:
            raise HTTPException(413, _("File too large (max {max} MB)").format(max=100))
        chunks.append(chunk)

    content_bytes = b"".join(chunks)
    if not content_bytes:
        raise HTTPException(400, _("Empty file"))

    # 尝试多种编码读取 / Try multiple encodings
    text = None
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
        try:
            text = content_bytes.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text is None:
        raise HTTPException(400, _("Unable to decode file. Please use UTF-8 encoding."))

    return _create_import_task(text, file.filename or "import.txt", title, project_id, background_tasks)


def _create_import_task(
    text: str,
    filename: str,
    title: Optional[str],
    project_id: Optional[str],
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """根据解析结果创建任务 / Create task based on parsing result.

    Args:
        background_tasks: FastAPI BackgroundTasks（从 async 端点传入）或 None（从 sync 端点用 threading）
    """
    from core.pipeline_runner import run_stage2_task

    content_type, dialogue, summary_text = parse_document_content(text, filename)

    task_id = str(uuid.uuid4())
    now = datetime.now()

    # 推断标题 / Infer title
    inferred_title = title or infer_title_from_content(text)
    if not inferred_title:
        # 从文件名推断 / Infer from filename
        stem = Path(filename).stem
        # 清理文件名中可能的日期/ID前缀 / Clean possible date/ID prefixes
        inferred_title = stem[:30] if stem else _("Imported Meeting")

    if content_type == CONTENT_TYPE_TRANSCRIPT and dialogue:
        # ── 原文类型：创建任务，后台跑 Stage 2（纪要生成） / Transcript: create task, run Stage 2 in background ──
        tasks[task_id] = {
            "task_id": task_id,
            "status": "processing",
            "source": "import_transcript",
            "progress": 50,
            "message": _("Generating summary from imported transcript..."),
            "audio_name": filename,
            "audio_size": len(text.encode("utf-8")),
            "audio_path": "",
            "audio_duration": None,
            "speaker_count": len(dialogue),
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
            "dialogue": dialogue,
            "title": inferred_title,
        }

        if project_id:
            tasks[task_id]["project_id"] = project_id

        save_task_to_disk(task_id)

        # 后台运行 Stage 2（纪要生成） / Run Stage 2 (summary generation) in background
        # audio_path 传空 Path，因为原文导入不需要音频 / Pass empty Path since transcript import doesn't need audio
        if background_tasks is not None:
            # async 端点调用：使用 FastAPI BackgroundTasks / Called from async endpoint
            background_tasks.add_task(run_stage2_task, task_id, Path(""), None)
        else:
            # sync 端点调用：使用 threading / Called from sync endpoint
            t = threading.Thread(target=run_stage2_task, args=(task_id, Path(""), None), daemon=True)
            t.start()

        logger.info(f"[导入] 原文导入: task={task_id[:8]}, speakers={len(dialogue)}, file={filename}")

        return {
            "task_id": task_id,
            "status": "processing",
            "import_type": "transcript",
            "title": inferred_title,
            "speaker_count": len(dialogue),
        }

    elif content_type == CONTENT_TYPE_SUMMARY and summary_text:
        # ── 纪要类型：直接存为已完成任务 / Summary: store directly as completed task ──
        tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "source": "import_summary",
            "progress": 100,
            "message": _("Import complete"),
            "audio_name": filename,
            "audio_size": len(text.encode("utf-8")),
            "audio_path": "",
            "audio_duration": None,
            "speaker_count": None,
            "summary": summary_text,
            "user_summary": summary_text,
            "output_path": "",
            "created_at": now.isoformat(),
            "meeting_date": now.strftime("%Y-%m-%d"),
            "error": None,
            "error_category": None,
            "error_suggestion": None,
            "failed_stage": None,
            "retry_count": 0,
            "speaker_mapping": {},
            "dialogue": [],
            "title": inferred_title,
        }

        if project_id:
            tasks[task_id]["project_id"] = project_id

        save_task_to_disk(task_id)

        # DC-UNIFY-01：行动项与结论合流为唯一一条决策流（结论以「待确认」态入盘）
        try:
            from core import joblog
            from core.summarize import merge_flow_after_regen, parse_decisions_with_status, parse_todos_from_summary
            parsed_todos = parse_todos_from_summary(summary_text)
            parsed_decisions, parse_status = parse_decisions_with_status(summary_text)
            tasks[task_id]["todos"] = merge_flow_after_regen(
                tasks[task_id].get("todos") or [],
                parsed_todos + parsed_decisions,
                tasks[task_id].get("decision_deletions"),  # DC-R2-BE 墓碑：导入重解析同样不复活已删 auto
            )
            if parsed_todos or parsed_decisions or parse_status:
                save_task_to_disk(task_id)
            if parse_status:
                logger.warning(f"[导入] 决策解析降级（{parse_status}）: task={task_id[:8]}")
                joblog.append_event(
                    task_id, joblog.STAGE_SUMMARY,
                    f"导入决策解析降级（{parse_status}）：结论节点置空，不影响导入", level="warn",
                )
        except Exception as e:
            logger.warning(f"[导入] 决策流提取失败（不影响导入）: {e}")
            try:
                from core import joblog
                joblog.append_event(
                    task_id, joblog.STAGE_SUMMARY,
                    f"导入决策流提取异常（不影响导入）: {e}", level="warn",
                )
            except Exception:
                pass

        logger.info(f"[导入] 纪要导入: task={task_id[:8]}, file={filename}")

        return {
            "task_id": task_id,
            "status": "completed",
            "import_type": "summary",
            "title": inferred_title,
        }

    else:
        # ── 无法识别：存为原始文本，让用户在详情页编辑 / Unknown: store as raw text for user to edit ──
        tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "source": "import_summary",
            "progress": 100,
            "message": _("Imported as raw text. You can edit the summary in the meeting detail page."),
            "audio_name": filename,
            "audio_size": len(text.encode("utf-8")),
            "audio_path": "",
            "audio_duration": None,
            "speaker_count": None,
            "summary": text,
            "user_summary": text,
            "output_path": "",
            "created_at": now.isoformat(),
            "meeting_date": now.strftime("%Y-%m-%d"),
            "error": None,
            "error_category": None,
            "error_suggestion": None,
            "failed_stage": None,
            "retry_count": 0,
            "speaker_mapping": {},
            "dialogue": [],
            "title": inferred_title,
        }

        if project_id:
            tasks[task_id]["project_id"] = project_id

        save_task_to_disk(task_id)

        logger.info(f"[导入] 未知类型导入: task={task_id[:8]}, file={filename}")

        return {
            "task_id": task_id,
            "status": "completed",
            "import_type": "unknown",
            "title": inferred_title,
        }


# ============================================================
# 文字粘贴导入端点 / Text paste import endpoint
# ============================================================

@router.post("/api/import/text")
def import_text(req: ImportTextRequest):
    """粘贴文字导入 / Paste text import.

    接受用户粘贴的文字内容，智能识别为原文或纪要。
    Accept pasted text content, smart detect as transcript or summary.
    """
    if not req.content or len(req.content.strip()) < 10:
        raise HTTPException(400, _("Content too short. Please paste at least 10 characters."))

    # sync 端点：background_tasks 传 None，内部用 threading 调度 Stage 2
    # sync endpoint: pass None for background_tasks, use threading internally for Stage 2
    return _create_import_task(req.content, "pasted_text.txt", req.title, req.project_id, None)
