"""
core/recording_recovery.py — 录制异常恢复（僵尸录音清理）

T-24：原实现位于 app/routers/record_state.py，record_lifecycle 只能反向 import 同层路由
获取。该逻辑只操作 core 层状态（task_store / realtime_store / silence_detection），
下沉后两个录制路由共同引用，断开 router → router 耦合。

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-06
"""

import logging

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
from core.silence_detection import cleanup_silence_detection
from core.task_store import save_task_to_disk, tasks

logger = logging.getLogger(__name__)


def cleanup_zombie_recording() -> None:
    """清理僵尸录音：ffmpeg 进程已崩溃但任务状态仍为 recording。
    Clean up zombie recording: ffmpeg process crashed but task status is still 'recording'.

    将任务状态更新为 failed，清理所有实时资源。
    Updates task status to 'failed', cleans up all realtime resources.
    """
    # 查找处于 recording 状态但 ffmpeg 已死的任务 / Find tasks in 'recording' state but ffmpeg is dead
    zombie_task_id = None
    for tid, task in tasks.items():
        if task.get("status") == "recording":
            zombie_task_id = tid
            break

    if not zombie_task_id:
        return

    logger.warning(f"[录制] 检测到僵尸录音，正在清理: task={zombie_task_id[:8]}")

    # 更新任务状态 / Update task status
    if zombie_task_id in tasks:
        tasks[zombie_task_id]["status"] = "failed"
        tasks[zombie_task_id]["error"] = "Recording process crashed (ffmpeg unavailable or device not found)"
        save_task_to_disk(zombie_task_id)

    # 清理实时资源 / Clean up realtime resources
    realtime_transcribers.pop(zombie_task_id, None)
    realtime_diarizers.pop(zombie_task_id, None)
    realtime_summarizers.pop(zombie_task_id, None)
    realtime_chapter_generators.pop(zombie_task_id, None)
    realtime_translators.pop(zombie_task_id, None)
    realtime_speaker_maps.pop(zombie_task_id, None)
    realtime_full_transcripts.pop(zombie_task_id, None)
    realtime_full_sealed.pop(zombie_task_id, None)
    realtime_queues.pop(zombie_task_id, None)
    cleanup_silence_detection(zombie_task_id)

    logger.info(f"[录制] 僵尸录音清理完成: task={zombie_task_id[:8]}")
