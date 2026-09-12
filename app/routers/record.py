"""
app/routers/record.py — 录制控制 + 实时总结/绑定

作者：王永亮
创建：2026-09-03
版本：2.0.0

v2.0 重构：WebSocket 端点与静默检测已拆分至独立模块。
  - app/routers/ws_transcript.py — WebSocket 实时转写端点
  - core/silence_detection.py    — 静默检测协程与自动关停
"""

import uuid
import asyncio
import logging
import math
import struct
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.store import (
    tasks, RECORD_DEVICE, RECORDINGS_DIR, TASKS_DIR,
    realtime_queues, realtime_transcribers, realtime_diarizers,
    realtime_summarizers, realtime_chapter_generators, realtime_speaker_maps,
    realtime_full_transcripts,
    realtime_last_heartbeat, realtime_last_sentence,
    realtime_presence_scores, realtime_silence_warnings, realtime_silence_monitors,
    save_task_to_disk, push_realtime_msg, resolve_realtime_speaker_name,
    run_pipeline_task, get_feature_flags, get_silence_detection_config,
    SPEAKER_COUNT_MIN, SPEAKER_COUNT_MAX,
)
# 以模块方式引用 realtime_store：event_loop 全局在 startup 时才赋值，必须运行时通过
# rt_store.event_loop 读取（若按值 import 会像 _stream_task_id 一样恒为初始值 None）
import app.realtime_store as rt_store
from core.audio import (
    start_recording_with_stream,
    stop_recording_with_stream,
    pause_recording_with_stream,
    resume_recording_with_stream,
    is_stream_recording,
    get_stream_recording_info,
)
from core.realtime_asr import RealtimeTranscriber
from core.realtime_summary import RealtimeSummarizer
from core.realtime_chapters import RealtimeChapterGenerator
from core.diarization import create_realtime_diarizer
from core.silence_detection import cleanup_silence_detection, silence_monitor_loop
from core import speakers
from core.i18n import _, set_current_locale

logger = logging.getLogger(__name__)

router = APIRouter(tags=["record"])


# ============================================================
# 录制控制
# ============================================================

@router.post("/api/record/start")
def start_record():
    """开始流式录音，同时启动实时转写"""
    if is_stream_recording():
        raise HTTPException(400, _("Already recording"))

    # 配额预检：订阅用户额度用尽时阻止录制（自带 Key 用户不受限）
    try:
        from core.metering import is_metered, check_quota
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
        logger.warning(f"配额预检失败（不阻止录制）: {e}")

    task_id = str(uuid.uuid4())

    # 创建 asyncio Queue 用于 WebSocket 实时推送
    queue: asyncio.Queue = asyncio.Queue()
    realtime_queues[task_id] = queue

    # 创建声纹聚类器（实时说话人分离，根据用户订阅状态选择 provider）
    diarizer = create_realtime_diarizer()
    realtime_diarizers[task_id] = diarizer

    # 初始化实时说话人绑定映射
    realtime_speaker_maps[task_id] = {}

    # 初始化全量实时转写记录（供文本桥接匹配，突破 REALTIME_BUFFER_MAX 限制）
    realtime_full_transcripts[task_id] = []

    # 读取功能开关
    feature_flags = get_feature_flags()

    # 创建实时总结器（增量摘要，可通过设置页关闭）
    summarizer = None
    if feature_flags["realtime_summary"]:
        summary_interval = feature_flags.get("realtime_summary_interval", 60)
        summarizer = RealtimeSummarizer(
            on_summary=lambda content: push_realtime_msg(task_id, {
                "type": "summary_update", "content": content
            }),
            on_status=lambda status: push_realtime_msg(task_id, {
                "type": "summary_status", "status": status
            }),
            on_countdown=lambda remaining: push_realtime_msg(task_id, {
                "type": "summary_countdown", "remaining": remaining
            }),
            interval=summary_interval,
        )
        realtime_summarizers[task_id] = summarizer
        summarizer.start()

    # 创建实时章节生成器（增量章节分析，可通过设置页关闭）
    chapter_gen = None
    if feature_flags["realtime_chapters"]:
        chapter_gen = RealtimeChapterGenerator(
            on_chapters=lambda chapters: push_realtime_msg(task_id, {
                "type": "chapters_update", "chapters": chapters
            }),
        )
        realtime_chapter_generators[task_id] = chapter_gen
        chapter_gen.start()

    # PCM 回调：将音频数据送入实时 ASR + 声纹聚类
    # 注意：此回调在 stream_reader 线程执行
    transcriber_ref: dict[str, RealtimeTranscriber | None] = {"ref": None}
    _pcm_call_count = 0
    _last_speaker_count = 0  # 上次推送的说话人数量（避免重复推送）
    _volume_warned = False  # 音量过低警告只发一次
    _volume_samples: list[float] = []  # 前 N 次回调的 RMS dB 样本
    _VOLUME_CHECK_LIMIT = 50  # 前 50 次回调（≈5 秒）用于音量检测
    _VOLUME_THRESHOLD_DB = -50.0  # 低于此值视为音量极低

    def pcm_callback(data: bytes) -> None:
        nonlocal _pcm_call_count, _last_speaker_count, _volume_warned
        _pcm_call_count += 1
        t = transcriber_ref.get("ref")
        if t and t.is_running:
            t.feed_audio(data)
        # 送入声纹聚类器
        diarizer.feed_audio(data)

        # ── 前 5 秒音量检测：提醒用户麦克风是否异常 ──
        if not _volume_warned and _pcm_call_count <= _VOLUME_CHECK_LIMIT:
            if len(data) >= 64:  # 至少 32 个样本才计算
                n_samples = len(data) // 2
                samples = struct.unpack(f'<{n_samples}h', data[:n_samples * 2])
                rms = (sum(s * s for s in samples) / n_samples) ** 0.5
                if rms > 0:
                    db = 20.0 * math.log10(rms / 32768.0)
                    _volume_samples.append(db)
            if _pcm_call_count == _VOLUME_CHECK_LIMIT and _volume_samples:
                avg_db = sum(_volume_samples) / len(_volume_samples)
                if avg_db < _VOLUME_THRESHOLD_DB:
                    _volume_warned = True
                    logger.warning(
                        f"[录制] 前 5 秒音量极低 (mean={avg_db:.1f} dB)，"
                        f"请检查麦克风或音频输入设备"
                    )
                    push_realtime_msg(task_id, {
                        "type": "volume_warning",
                        "level": "low",
                        "avg_db": round(avg_db, 1),
                    })

        # 每 20 次回调（约 2 秒）检查一次说话人数量变化，推送更新
        if _pcm_call_count % 20 == 0:
            active_count = diarizer.get_active_speaker_count()
            if active_count != _last_speaker_count:
                _last_speaker_count = active_count
                push_realtime_msg(task_id, {
                    "type": "speaker_count_update",
                    "count": active_count,
                    "speakers": [
                        {"id": sid, "name": resolve_realtime_speaker_name(task_id, sid)}
                        for sid in diarizer.get_active_speaker_ids()
                    ],
                })
        if _pcm_call_count <= 3 or _pcm_call_count % 50 == 0:
            logger.info(f"[pcm_callback] #{_pcm_call_count}: transcriber={'OK' if t else 'None'}, diarizer_speakers={diarizer.get_active_speaker_count()}")

    try:
        # 启动流式录音（ffmpeg 采集 → PCM pipe → 写文件 + pcm_callback）
        result = start_recording_with_stream(
            device=RECORD_DEVICE,
            output_dir=RECORDINGS_DIR,
            task_id=task_id,
            pcm_callback=pcm_callback,
        )

        # 启动实时转写（优雅降级：失败不影响录音）
        # 注意：start() 可能阻塞（等待连接 + 重试），放到后台线程避免阻塞事件循环
        def _on_sentence_end(s: dict) -> None:
            """定稿句子回调：推送 WebSocket + 送入实时总结"""
            # 过滤空文本（无人说话时 ASR 可能返回空句子）
            if not s.get("text", "").strip():
                logger.debug(f"[录制] 跳过空句子: speaker={s.get('begin_time')}")
                return
            speaker_id = diarizer.get_speaker(
                begin_time=s.get("begin_time", 0) / 1000.0,
                end_time=s.get("end_time", 0) / 1000.0,
            )
            # 解析说话人姓名（从实时绑定映射中查找）
            speaker_name = resolve_realtime_speaker_name(task_id, speaker_id)
            push_realtime_msg(task_id, {
                "type": "sentence",
                "text": s["text"],
                "begin_time": s.get("begin_time", 0),
                "end_time": s.get("end_time", 0),
                "speaker_id": speaker_id,
                "speaker_name": speaker_name,
            })
            # 更新最后定稿句子时间戳（供静默检测使用）
            realtime_last_sentence[task_id] = time.time()
            # 送入实时总结器（含说话人姓名）
            if summarizer:
                summarizer.feed_sentence({
                    **s,
                    "speaker_name": speaker_name,
                })
            # 送入实时章节生成器
            if chapter_gen:
                chapter_gen.feed_sentence({
                    **s,
                    "speaker_name": speaker_name,
                })

        transcriber = RealtimeTranscriber(
            on_partial=lambda text: push_realtime_msg(task_id, {
                "type": "partial",
                "text": text,
                "speaker_id": diarizer.get_speaker(),
                "speaker_name": resolve_realtime_speaker_name(task_id, diarizer.get_speaker()),
            }),
            on_sentence_end=_on_sentence_end,
            on_error=lambda msg: push_realtime_msg(task_id, {
                "type": "error", "message": msg
            }),
            on_complete=lambda: push_realtime_msg(task_id, {
                "type": "ended"
            }),
        )

        def _start_transcriber_bg():
            """后台启动实时转写（含重试逻辑）"""
            try:
                transcriber.start()
                transcriber_ref["ref"] = transcriber
                realtime_transcribers[task_id] = transcriber
                logger.info(f"[录制] 实时转写已启动: task={task_id[:8]}")
            except Exception as e:
                logger.warning(f"[录制] 实时转写启动失败（仅录音模式）: {e}")
                transcriber_ref["ref"] = None
                push_realtime_msg(task_id, {
                    "type": "error",
                    "message": f"实时转写不可用: {e}，录音仍会正常进行"
                })

        threading.Thread(target=_start_transcriber_bg, daemon=True).start()

        output_path = result["output_path"]

        # 创建任务记录
        now = datetime.now()
        tasks[task_id] = {
            "task_id": task_id,
            "status": "recording",
            "source": "record",
            "progress": 0,
            "message": "正在录制...",
            "audio_name": "",
            "audio_path": str(output_path),
            "audio_duration": None,
            "speaker_count": None,
            "summary": None,
            "output_path": None,
            "created_at": now.isoformat(),
            "meeting_date": now.strftime("%Y-%m-%d"),
            "error": None,
        }
        save_task_to_disk(task_id)

        # ── 初始化静默检测状态 ──
        silence_config = get_silence_detection_config()
        if silence_config["enabled"]:
            now_ts = time.time()
            realtime_last_heartbeat[task_id] = now_ts
            realtime_last_sentence[task_id] = now_ts
            realtime_presence_scores[task_id] = float(silence_config["presence"]["score_max"])
            realtime_silence_warnings[task_id] = 0
            # 启动静默监测协程（跨线程调度到主事件循环）
            # 注意：start_record 是同步端点，运行在 AnyIO worker 线程，该线程无事件循环，
            # 不能用 asyncio.get_event_loop()（会抛 "no current event loop"），
            # 必须用 startup 时捕获的 rt_store.event_loop + run_coroutine_threadsafe。
            loop = rt_store.event_loop
            if loop and not loop.is_closed():
                monitor_future = asyncio.run_coroutine_threadsafe(
                    silence_monitor_loop(task_id), loop
                )
                realtime_silence_monitors[task_id] = monitor_future
                logger.info(f"[录制] 静默检测已启动: task={task_id[:8]}")
            else:
                logger.warning(f"[录制] 主事件循环不可用，静默检测未启动: task={task_id[:8]}")

        logger.info(f"[录制] 开始: task={task_id[:8]}, 设备={RECORD_DEVICE}")
        return {"task_id": task_id, "status": "recording"}

    except RuntimeError as e:
        realtime_queues.pop(task_id, None)
        raise HTTPException(500, _("Failed to start recording: {err}").format(err=e))


class RecordStopRequest(BaseModel):
    notes: Optional[str] = None  # 用户录音期间输入的笔记


@router.post("/api/record/stop")
def stop_record(
    background_tasks: BackgroundTasks,
    data: Optional[RecordStopRequest] = None,
):
    """停止录制，录音文件自动进入管线处理

    注意：此端点必须用 def（非 async def），因为 stop_recording_with_stream()
    包含 subprocess.wait / thread.join 等阻塞操作。
    FastAPI 会自动在线程池中运行同步端点，避免阻塞事件循环。
    """
    if not is_stream_recording():
        raise HTTPException(400, _("Not recording"))

    # 提取笔记
    user_notes = data.notes if data else None

    try:
        # 1. 先停止实时转写
        # 找到当前录制中的 task_id
        task_id = None
        estimated_speaker_count = None
        for tid, t in realtime_transcribers.items():
            task_id = tid
            break

        if task_id:
            transcriber = realtime_transcribers.pop(task_id, None)
            if transcriber:
                try:
                    transcriber.stop()
                except Exception as e:
                    logger.warning(f"实时转写停止异常: {e}")
            # 清理声纹聚类器，提取说话人数量供批管线使用
            diarizer = realtime_diarizers.pop(task_id, None)
            if diarizer:
                raw_count = diarizer.get_speaker_count()
                active_count = diarizer.get_active_speaker_count()
                # 执行后处理合并（解决 MFCC 时间漂移导致的过度分裂）
                final_count = diarizer.finalize()
                # 优先使用有效说话人数量（过滤伪说话人），但不超过合并后数量
                estimated_speaker_count = max(SPEAKER_COUNT_MIN, min(SPEAKER_COUNT_MAX, min(active_count, final_count)))
                vad_stats = diarizer.get_vad_stats()
                logger.info(
                    f"[录制] 声纹聚类统计: 原始={raw_count}, 有效={active_count}, "
                    f"合并后={final_count}, 钳制={estimated_speaker_count}, "
                    f"VAD语音段={vad_stats['speech_segments']}, "
                    f"VAD静音段={vad_stats['silence_segments']}, "
                    f"语音占比={vad_stats['speech_ratio']:.1%}"
                )
            # 停止实时总结器，保存最终摘要
            summarizer = realtime_summarizers.pop(task_id, None)
            if summarizer:
                summarizer.stop()
                final_summary = summarizer.get_final_summary()
                if final_summary and task_id in tasks:
                    tasks[task_id]["realtime_summary"] = final_summary
                logger.info(f"[录制] 实时总结停止: {summarizer.summary_count} 次总结")
            # 停止实时章节生成器，保存最终章节
            chapter_gen = realtime_chapter_generators.pop(task_id, None)
            if chapter_gen:
                chapter_gen.stop()
                final_chapters = chapter_gen.get_chapters()
                if final_chapters and task_id in tasks:
                    tasks[task_id]["realtime_chapters"] = final_chapters
                logger.info(f"[录制] 实时章节停止: {chapter_gen.update_count} 次更新")
            # 提取实时说话人绑定（供批管线使用）
            realtime_binding = realtime_speaker_maps.pop(task_id, {})
            if realtime_binding and task_id in tasks:
                tasks[task_id]["realtime_speaker_binding"] = {
                    str(k): v for k, v in realtime_binding.items()
                }
                logger.info(f"[录制] 实时说话人绑定: {len(realtime_binding)} 条")
            # 保存全量实时转写记录（供文本桥接匹配，持久化到 task）
            full_transcript = realtime_full_transcripts.pop(task_id, [])
            if full_transcript and task_id in tasks:
                tasks[task_id]["realtime_full_transcript"] = full_transcript
                logger.info(f"[录制] 全量实时转写已保存: {len(full_transcript)} 条句子")
            # 停止静默监测协程，清理静默检测状态
            cleanup_silence_detection(task_id)

        # 2. 停止录音
        result = stop_recording_with_stream()
        if not task_id:
            task_id = result["task_id"]
        audio_path = result["output_path"]
        duration = result["duration"]

        if task_id not in tasks:
            raise HTTPException(404, _("Task not found"))

        # 3. 发送结束消息
        push_realtime_msg(task_id, {"type": "ended"})

        # 4. 更新任务信息
        tasks[task_id]["audio_name"] = f"录音 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        tasks[task_id]["audio_duration"] = duration
        if user_notes:
            tasks[task_id]["user_notes"] = user_notes

        # 用量计量：按录制时长记录实时转写用量
        try:
            from core.metering import is_metered, record_usage
            from core.users import get_current_user
            if duration > 0 and is_metered():
                current_user = get_current_user()
                if current_user:
                    record_usage(
                        user_id=current_user["id"],
                        service="asr_realtime",
                        duration_seconds=duration,
                        task_id=task_id,
                        metadata={"model": "qwen-audio-3.0-asr-flash-streaming"},
                    )
        except Exception as e:
            logger.warning(f"[{task_id[:8]}] 实时用量记录失败（不影响主流程）: {e}")

        # 5. 后台执行管线（归一化 → 上传 → 转写 → 纪要）
        background_tasks.add_task(run_pipeline_task, task_id, audio_path, tasks[task_id]["audio_name"], None, estimated_speaker_count)

        # 6. 清理实时状态
        realtime_queues.pop(task_id, None)

        logger.info(f"[录制] 完成: task={task_id[:8]}, 时长={duration:.1f}s")
        return {
            "task_id": task_id,
            "status": "processing",
            "duration": duration,
        }

    except RuntimeError as e:
        raise HTTPException(500, _("Failed to stop recording: {err}").format(err=e))


@router.get("/api/record/status")
async def record_status():
    """查询当前录制状态"""
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
    """暂停录制（音频数据丢弃，实时转写停止接收）"""
    if not is_stream_recording():
        raise HTTPException(400, _("Not recording"))
    try:
        # 通过访问器实时获取当前录制的 task_id（不可用按值导入的 _stream_task_id，其恒为 None）
        info = get_stream_recording_info()
        task_id = info["task_id"] if info else None
        pause_recording_with_stream()
        # 更新任务状态为 paused
        if task_id and task_id in tasks:
            tasks[task_id]["status"] = "paused"
            save_task_to_disk(task_id)
        # 联动暂停实时总结（仅当总结正在运行时）
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
    """恢复录制"""
    if not is_stream_recording():
        raise HTTPException(400, _("Not recording"))
    try:
        # 通过访问器实时获取当前录制的 task_id（不可用按值导入的 _stream_task_id，其恒为 None）
        info = get_stream_recording_info()
        task_id = info["task_id"] if info else None
        resume_recording_with_stream()
        # 更新任务状态为 recording
        if task_id and task_id in tasks:
            tasks[task_id]["status"] = "recording"
            save_task_to_disk(task_id)
        # 联动恢复实时总结（仅当暂停是由录音触发时）
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
    """放弃录音：停止录制并删除所有相关数据和文件"""
    if not is_stream_recording():
        raise HTTPException(400, _("Not recording"))

    task_id = None
    try:
        # 1. 停止录音
        result = stop_recording_with_stream()
        task_id = result.get("task_id")

        # 2. 清理实时资源
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

            realtime_speaker_maps.pop(task_id, None)
            realtime_full_transcripts.pop(task_id, None)
            realtime_queues.pop(task_id, None)
            # 停止静默监测协程，清理静默检测状态
            cleanup_silence_detection(task_id)

        # 3. 删除音频文件
        audio_path = result.get("output_path")
        if audio_path and Path(audio_path).exists():
            Path(audio_path).unlink()

        # 4. 删除任务记录
        if task_id and task_id in tasks:
            tasks.pop(task_id)
        if task_id:
            task_file = TASKS_DIR / f"{task_id}.json"
            if task_file.exists():
                task_file.unlink()

        logger.info(f"[录制] 放弃: task={task_id[:8] if task_id else 'unknown'}")
        return {"abandoned": True, "task_id": task_id}

    except RuntimeError as e:
        raise HTTPException(500, _("Failed to abandon recording: {err}").format(err=e))


# ============================================================
# 实时总结控制
# ============================================================

@router.post("/api/record/summary/pause")
async def pause_summary():
    """暂停实时总结"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.pause()
    return {"status": "paused"}


@router.post("/api/record/summary/resume")
async def resume_summary():
    """恢复实时总结"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.resume()
    return {"status": "resumed"}


@router.post("/api/record/summary/stop")
async def stop_summary():
    """停止实时总结（彻底关闭，需手动恢复）"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.stop()
    return {"status": "stopped"}


@router.post("/api/record/summary/restart")
async def restart_summary():
    """重新启动已停止的实时总结"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.restart()
    return {"status": "restarted"}


class SummaryIntervalRequest(BaseModel):
    interval: int  # 秒，可选 30/60/120/300


@router.post("/api/record/summary/interval")
async def set_summary_interval(req: SummaryIntervalRequest):
    """热更新实时总结间隔（录音中立即生效）"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    # 下限 30 秒
    new_interval = max(30, req.interval)
    summarizer.set_interval(new_interval)
    return {"status": "updated", "interval": summarizer.interval}


# ============================================================
# 实时说话人绑定
# ============================================================

class RealtimeBindSpeakerRequest(BaseModel):
    speaker_id: int         # ASR 说话人编号（0, 1, 2...）
    speaker_uuid: str       # speakers.json 中的说话人 UUID


@router.post("/api/record/bind-speaker")
async def realtime_bind_speaker(req: RealtimeBindSpeakerRequest):
    """
    实时说话人绑定。

    在录音期间将 ASR 说话人编号绑定到全局说话人档案。
    绑定后立即通过 WebSocket 通知前端更新所有转写条目。
    """
    # 找到当前录制中的 task_id
    task_id = None
    for tid in realtime_speaker_maps:
        task_id = tid
        break
    if not task_id:
        raise HTTPException(400, _("No active recording"))

    # 验证说话人存在
    spk = speakers.get_speaker_by_id(req.speaker_uuid)
    if not spk:
        raise HTTPException(404, _("Speaker not found"))

    # 记录绑定前，先获取旧的兆底名称（用于更新缓冲区和全量转写）
    old_name = resolve_realtime_speaker_name(task_id, req.speaker_id)

    # 记录绑定
    realtime_speaker_maps[task_id][req.speaker_id] = req.speaker_uuid
    logger.info(f"[实时绑定] speaker_{req.speaker_id} → {spk.name}")

    # 通过 WebSocket 广播绑定更新
    push_realtime_msg(task_id, {
        "type": "speaker_bound",
        "speaker_id": req.speaker_id,
        "speaker_uuid": req.speaker_uuid,
        "speaker_name": spk.name,
    })

    # 更新实时总结缓冲区中已缓冲句子的说话人姓名
    summarizer = realtime_summarizers.get(task_id)
    if summarizer and old_name != spk.name:
        summarizer.update_speaker_name(old_name, spk.name)

    # 更新全量实时转写记录中的说话人姓名（确保 WebSocket 重连回放时也显示真名）
    full_transcript = realtime_full_transcripts.get(task_id, [])
    for entry in full_transcript:
        if entry.get("speaker_id") == req.speaker_id:
            entry["speaker_name"] = spk.name

    return {
        "speaker_id": req.speaker_id,
        "speaker_name": spk.name,
        "speaker_uuid": req.speaker_uuid,
    }


@router.get("/api/record/speaker-bindings")
async def realtime_get_speaker_bindings():
    """获取当前录音的说话人绑定状态"""
    task_id = None
    for tid in realtime_speaker_maps:
        task_id = tid
        break
    if not task_id:
        return {"bindings": {}, "task_id": None}

    binding_map = realtime_speaker_maps.get(task_id, {})
    # 补充姓名
    result = {}
    for sid, uuid in binding_map.items():
        spk = speakers.get_speaker_by_id(uuid)
        result[str(sid)] = {
            "speaker_uuid": uuid,
            "speaker_name": spk.name if spk else f"发言人{sid + 1}",
        }
    return {"bindings": result, "task_id": task_id}

