"""
core/silence_detection.py — 静默检测与用户存在性感知 / Silence detection and user presence awareness

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 静默检测状态清理（cleanup_silence_detection） / Silence detection state cleanup (cleanup_silence_detection)
  - 静默监测协程（silence_monitor_loop）：心跳超时检测 + ASR 无活动提醒 / Silence monitoring coroutine (silence_monitor_loop): heartbeat timeout + ASR inactivity reminder
  - 自动关停（auto_stop_recording） / Auto-stop recording (auto_stop_recording)

详见 / See: docs/design/SILENCE_DETECTION.md
从 app/routers/record.py 拆分而来 / Split from app/routers/record.py.
"""

import asyncio
import functools
import logging
import time
from datetime import datetime
from pathlib import Path

from app.store import (
    get_silence_detection_config,
    push_realtime_msg,
    realtime_chapter_generators,
    realtime_diarizers,
    realtime_full_transcripts,
    realtime_last_heartbeat,
    realtime_last_sentence,
    realtime_presence_scores,
    realtime_queues,
    realtime_silence_monitors,
    realtime_silence_warnings,
    realtime_speaker_maps,
    realtime_summarizers,
    realtime_transcribers,
    run_pipeline_task,
    save_task_to_disk,
    tasks,
)
from core.audio import is_stream_recording, stop_recording_with_stream
from core.i18n import _

logger = logging.getLogger(__name__)


def _log_pipeline_dispatch_result(task_id: str, future) -> None:
    """记录自动关停后管线派发结果（异常仅记日志，不冒泡回事件循环）。"""
    try:
        exc = future.exception()
        if exc is not None:
            logger.error(f"[静默检测] 自动关停后管线执行异常: task={task_id[:8]}: {exc}", exc_info=exc)
        else:
            logger.info(f"[静默检测] 自动关停后纪要管线执行完毕: task={task_id[:8]}")
    except asyncio.CancelledError:
        logger.warning(f"[静默检测] 自动关停后纪要管线任务被取消: task={task_id[:8]}")


def cleanup_silence_detection(task_id: str) -> None:
    """清理静默检测状态，取消监测协程"""
    monitor = realtime_silence_monitors.pop(task_id, None)
    if monitor and not monitor.done():
        monitor.cancel()
        logger.debug(f"[静默检测] 监测协程已取消: task={task_id[:8]}")
    realtime_last_heartbeat.pop(task_id, None)
    realtime_last_sentence.pop(task_id, None)
    realtime_presence_scores.pop(task_id, None)
    realtime_silence_warnings.pop(task_id, None)


async def silence_monitor_loop(task_id: str) -> None:
    """
    静默监测协程：每 10 秒检查一次，判断是否需要提醒或自动关停。

    检查逻辑：
    1. 心跳超时（前端不可达）→ 直接自动关停
    2. ASR 无活动 + 存在性评分低 → 三阶段提醒（温和 → 紧急 → 自动关停）
    """
    config = get_silence_detection_config()
    if not config["enabled"]:
        return

    heartbeat_timeout = config["presence"]["heartbeat_timeout_sec"]
    asr_timeout = config["audio"]["asr_no_sentence_timeout_sec"]
    threshold_warning = config["presence"]["threshold_warning"]
    gentle_countdown = config["action"]["gentle_countdown_sec"]
    urgent_countdown = config["action"]["urgent_countdown_sec"]
    max_warnings = config["action"]["max_warnings_per_session"]

    warning_stage = 0
    stage_enter_time = 0.0

    logger.info(f"[静默检测] 监测启动: task={task_id[:8]}, "
                f"heartbeat_timeout={heartbeat_timeout}s, asr_timeout={asr_timeout}s")

    try:
        while True:
            await asyncio.sleep(10)

            if not is_stream_recording():
                break

            now = time.time()

            # 检查 1：心跳超时
            last_hb = realtime_last_heartbeat.get(task_id, now)
            heartbeat_silent = now - last_hb
            if heartbeat_silent > heartbeat_timeout:
                logger.warning(
                    f"[静默检测] 心跳超时 ({heartbeat_silent:.0f}s > {heartbeat_timeout}s)，"
                    f"前端不可达，自动关停: task={task_id[:8]}"
                )
                await auto_stop_recording(task_id, reason="heartbeat_timeout")
                break

            # 检查 2：ASR 无活动 + 存在性评分
            last_sent = realtime_last_sentence.get(task_id, now)
            asr_silent = now - last_sent
            presence_score = realtime_presence_scores.get(task_id, 100.0)

            if asr_silent > asr_timeout and presence_score < threshold_warning:
                silent_minutes = int(asr_silent / 60)

                if warning_stage == 0:
                    logger.info(f"[静默检测] 发送温和提醒: task={task_id[:8]}, asr_silent={silent_minutes}min, score={presence_score:.0f}")
                    push_realtime_msg(task_id, {"type": "presence_warning", "level": "gentle", "silent_minutes": silent_minutes, "countdown_seconds": gentle_countdown})
                    warning_stage = 1
                    stage_enter_time = now
                    realtime_silence_warnings[task_id] = realtime_silence_warnings.get(task_id, 0) + 1

                elif warning_stage == 1:
                    if now - stage_enter_time > gentle_countdown:
                        logger.info(f"[静默检测] 发送紧急提醒: task={task_id[:8]}, 温和提醒超时 ({gentle_countdown}s)")
                        push_realtime_msg(task_id, {"type": "presence_warning", "level": "urgent", "silent_minutes": silent_minutes, "countdown_seconds": urgent_countdown})
                        warning_stage = 2
                        stage_enter_time = now
                        realtime_silence_warnings[task_id] = realtime_silence_warnings.get(task_id, 0) + 1

                elif warning_stage == 2:
                    if now - stage_enter_time > urgent_countdown:
                        logger.warning(f"[静默检测] 紧急提醒超时，自动关停: task={task_id[:8]}, asr_silent={silent_minutes}min, score={presence_score:.0f}")
                        await auto_stop_recording(task_id, reason="user_presence_timeout")
                        break

                if realtime_silence_warnings.get(task_id, 0) >= max_warnings * 2:
                    logger.warning(f"[静默检测] 已达最大提醒次数 ({max_warnings})，自动关停: task={task_id[:8]}")
                    await auto_stop_recording(task_id, reason="max_warnings_reached")
                    break

            else:
                if warning_stage > 0:
                    logger.info(f"[静默检测] 条件恢复，重置提醒阶段: task={task_id[:8]}, asr_silent={asr_silent:.0f}s, score={presence_score:.0f}")
                warning_stage = 0

    except asyncio.CancelledError:
        logger.info(f"[静默检测] 监测协程被取消: task={task_id[:8]}")
    except Exception as e:
        logger.error(f"[静默检测] 监测协程异常: {e}")


async def auto_stop_recording(task_id: str, reason: str = "unknown") -> None:
    """
    自动停止录音（由静默监测协程调用）。

    在线程池中执行阻塞操作（stop_recording_with_stream）。
    """
    logger.warning(f"[静默检测] 开始自动关停: task={task_id[:8]}, reason={reason}")

    try:
        transcriber = realtime_transcribers.pop(task_id, None)
        if transcriber:
            try:
                transcriber.stop()
            except Exception as e:
                logger.warning(f"自动关停-转写停止异常: {e}")

        diarizer = realtime_diarizers.pop(task_id, None)
        if diarizer:
            try:
                diarizer.stop()
            except Exception as e:
                logger.warning(f"自动关停-聚类停止异常: {e}")

        summarizer = realtime_summarizers.pop(task_id, None)
        if summarizer:
            summarizer.stop()

        chapter_gen = realtime_chapter_generators.pop(task_id, None)
        if chapter_gen:
            chapter_gen.stop()

        realtime_speaker_maps.pop(task_id, None)
        realtime_full_transcripts.pop(task_id, None)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, stop_recording_with_stream)

        audio_path = result["output_path"]
        duration = result["duration"]

        if task_id in tasks:
            tasks[task_id]["audio_name"] = f"录音 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            tasks[task_id]["audio_duration"] = duration
            tasks[task_id]["auto_stop_reason"] = reason
            save_task_to_disk(task_id)

        push_realtime_msg(task_id, {"type": "auto_stopped", "reason": reason, "duration": duration, "message": _("Recording automatically stopped due to prolonged inactivity (saved {dur:.0f}s of audio)").format(dur=duration)})
        push_realtime_msg(task_id, {"type": "ended"})

        # run_pipeline_task 是同步阻塞函数，必须走线程池派发（与 record.py / task_store.py 一致）。
        # 预先取好 audio_name，避免回调执行时 tasks 条目已被清理触发 KeyError。
        # Fire the summary pipeline via executor: run_pipeline_task is sync/blocking,
        # so asyncio.ensure_future would raise TypeError (auto_stop callback crash, 09-30).
        audio_name = tasks.get(task_id, {}).get("audio_name", Path(audio_path).name)
        loop = asyncio.get_running_loop()
        pipeline_future = loop.run_in_executor(
            None, run_pipeline_task, task_id, audio_path, audio_name, None, None
        )
        pipeline_future.add_done_callback(functools.partial(_log_pipeline_dispatch_result, task_id))

        realtime_queues.pop(task_id, None)
        cleanup_silence_detection(task_id)

        logger.info(f"[静默检测] 自动关停完成: task={task_id[:8]}, duration={duration:.0f}s, reason={reason}")

    except Exception as e:
        logger.error(f"[静默检测] 自动关停失败: {e}")
