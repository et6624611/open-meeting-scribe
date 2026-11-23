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


def cleanup_zombie_recording(
    task_id: str | None = None,
    reason: str | None = None,
) -> None:
    """清理僵尸录音：ffmpeg 进程已崩溃但任务状态仍为 recording 或 paused。
    Clean up zombie recording: ffmpeg process crashed but task status is still
    'recording' or 'paused'.

    paused 任务同样可能僵尸：暂停期间休眠/设备停采触发看门狗强杀 ffmpeg，
    若不清理任务会卡在假 paused，恢复按钮永远 400（2026-11-23 事故）。

    将任务状态更新为 failed，清理所有实时资源。
    Updates task status to 'failed', cleans up all realtime resources.

    Args:
        task_id: 指定要清理的任务；None 时扫描状态为 recording/paused 的任务
        reason: 写入任务 error 字段的原因说明；None 时用默认文案
    """
    # 定位僵尸任务 / Locate the zombie task
    if task_id is not None:
        zombie_task_id = task_id if task_id in tasks else None
    else:
        zombie_task_id = None
        for tid, task in tasks.items():
            if task.get("status") in ("recording", "paused"):
                zombie_task_id = tid
                break

    if not zombie_task_id:
        return

    task_status = tasks.get(zombie_task_id, {}).get("status", "?")
    logger.warning(
        f"[录制] 检测到僵尸录音，正在清理: task={zombie_task_id[:8]} status={task_status}"
    )

    # 更新任务状态 / Update task status
    if zombie_task_id in tasks:
        tasks[zombie_task_id]["status"] = "failed"
        tasks[zombie_task_id]["error"] = reason or (
            "Recording process crashed (ffmpeg unavailable or device not found)"
        )
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
