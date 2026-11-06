"""app/routers/record_state.py — 录制状态查询与暂停/恢复/放弃 + 僵尸录音清理。

端点：
  GET  /api/record/status   — 当前录制状态
  POST /api/record/pause    — 暂停录制（联动暂停实时总结）
  POST /api/record/resume   — 恢复录制（联动恢复实时总结）
  POST /api/record/abandon  — 放弃录音（删除全部数据与文件）

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 record.py 拆分）
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.audio import (
    get_stream_recording_info,
    is_stream_recording,
    pause_recording_with_stream,
    resume_recording_with_stream,
    stop_recording_with_stream,
)
from core.i18n import _
from core.realtime_store import (
    realtime_chapter_generators,
    realtime_diarizers,
    realtime_full_sealed,
    realtime_full_transcripts,
    realtime_queues,
    realtime_speaker_maps,
    realtime_summarizers,
    realtime_transcribers,
    realtime_translators,
)
from core.recording_recovery import cleanup_zombie_recording
from core.silence_detection import cleanup_silence_detection
from core.task_store import TASKS_DIR, save_task_to_disk, tasks
from core.tasks_repo import remove_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/record/status")
async def record_status():
    """查询当前录制状态 / Get current recording status"""
    if is_stream_recording():
        info = get_stream_recording_info()
        return {
            "recording": True,
            "task_id": info["task_id"] if info else None,
            "elapsed": info["elapsed"] if info else 0,
            "paused": info.get("paused", False) if info else False,
        }
    return {"recording": False}


@router.post("/api/record/pause")
async def pause_record():
    """暂停录制（音频数据丢弃，实时转写停止接收） / Pause recording (audio discarded; realtime transcription stops receiving)"""
    if not is_stream_recording():
        cleanup_zombie_recording()
        raise HTTPException(400, _("Not recording (recording process may have crashed)"))
    try:
        # 通过访问器实时获取当前录制的 task_id（不可用按值导入的 _stream_task_id，其恒为 None） / Get current recording task_id via accessor (can't use _stream_task_id imported by value; always None)
        info = get_stream_recording_info()
        task_id = info["task_id"] if info else None
        pause_recording_with_stream()
        # 更新任务状态为 paused / Update task status to paused
        if task_id and task_id in tasks:
            tasks[task_id]["status"] = "paused"
            save_task_to_disk(task_id)
        # 联动暂停实时总结（仅当总结正在运行时） / Cascade-pause realtime summary (only when summarizer is running)
        summarizer = realtime_summarizers.get(task_id) if task_id else None
        summary_paused_by_recording = False
        if summarizer and summarizer.is_running and not summarizer.is_paused:
            summarizer.pause(source="recording")
            summary_paused_by_recording = True
        if not summarizer:
            logger.warning(f"[录制] 暂停联动：未找到实时总结器 task={task_id}")
        return {"status": "paused", "summary_paused": summary_paused_by_recording}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/api/record/resume")
async def resume_record():
    """恢复录制 / Resume recording"""
    if not is_stream_recording():
        cleanup_zombie_recording()
        raise HTTPException(400, _("Not recording (recording process may have crashed)"))
    try:
        # 通过访问器实时获取当前录制的 task_id（不可用按值导入的 _stream_task_id，其恒为 None） / Get current recording task_id via accessor (can't use _stream_task_id imported by value; always None)
        info = get_stream_recording_info()
        task_id = info["task_id"] if info else None
        resume_recording_with_stream()
        # 更新任务状态为 recording / Update task status to recording
        if task_id and task_id in tasks:
            tasks[task_id]["status"] = "recording"
            save_task_to_disk(task_id)
        # 联动恢复实时总结（仅当暂停是由录音触发时） / Cascade-resume realtime summary (only when pause was triggered by recording)
        summarizer = realtime_summarizers.get(task_id) if task_id else None
        summary_resumed = False
        if summarizer:
            summary_resumed = summarizer.auto_resume_for_recording()
        else:
            logger.warning(f"[录制] 恢复联动：未找到实时总结器 task={task_id}")
        return {"status": "recording", "summary_resumed": summary_resumed}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/api/record/abandon")
def abandon_record():
    """放弃录音：停止录制并删除所有相关数据和文件 / Abandon recording: stop and delete all related data and files"""
    if not is_stream_recording():
        cleanup_zombie_recording()
        return {"abandoned": True, "task_id": None, "message": "zombie recording cleaned up"}

    task_id = None
    try:
        # 1. 停止录音 / 1. Stop recording
        result = stop_recording_with_stream()
        task_id = result.get("task_id")

        # 2. 清理实时资源 / 2. Clean up realtime resources
        if task_id:
            transcriber = realtime_transcribers.pop(task_id, None)
            if transcriber:
                try:
                    transcriber.stop()
                except Exception as e:
                    logger.warning(f"放弃-转写停止异常: {e}")

            diarizer = realtime_diarizers.pop(task_id, None)
            if diarizer:
                try:
                    diarizer.stop()
                except Exception as e:
                    logger.warning(f"放弃-聚类停止异常: {e}")

            summarizer = realtime_summarizers.pop(task_id, None)
            if summarizer:
                summarizer.stop()

            chapter_gen = realtime_chapter_generators.pop(task_id, None)
            if chapter_gen:
                chapter_gen.stop()

            translator = realtime_translators.pop(task_id, None)
            if translator:
                translator.stop()

            realtime_speaker_maps.pop(task_id, None)
            realtime_full_transcripts.pop(task_id, None)
            realtime_full_sealed.pop(task_id, None)
            realtime_queues.pop(task_id, None)
            # 停止静默监测协程，清理静默检测状态 / Stop silence monitoring coroutine; clean up silence detection state
            cleanup_silence_detection(task_id)

        # 3. 删除音频文件 / 3. Delete audio file
        audio_path = result.get("output_path")
        if audio_path and Path(audio_path).exists():
            Path(audio_path).unlink()

        # 4. 删除任务记录 / 4. Delete task record
        if task_id:
            remove_task(task_id)
            task_file = TASKS_DIR / f"{task_id}.json"
            if task_file.exists():
                task_file.unlink()

        logger.info(f"[录制] 放弃: task={task_id[:8] if task_id else 'unknown'}")
        return {"abandoned": True, "task_id": task_id}

    except RuntimeError as e:
        raise HTTPException(500, _("Failed to abandon recording: {err}").format(err=e))
