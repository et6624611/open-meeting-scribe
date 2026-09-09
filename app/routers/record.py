"""
app/routers/record.py — 录制控制 + 实时转写 WS + 实时总结/绑定

作者：王永亮
创建：2026-09-03
版本：1.0.0
"""

import uuid
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.store import (
    tasks, RECORD_DEVICE, RECORDINGS_DIR, TASKS_DIR,
    realtime_queues, realtime_transcribers, realtime_diarizers,
    realtime_summarizers, realtime_chapter_generators, realtime_speaker_maps,
    realtime_full_transcripts,
    save_task_to_disk, push_realtime_msg, resolve_realtime_speaker_name,
    run_pipeline_task, get_feature_flags,
    SPEAKER_COUNT_MIN, SPEAKER_COUNT_MAX,
)
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
from core import speakers

logger = logging.getLogger(__name__)

router = APIRouter(tags=["record"])


# ============================================================
# 录制控制
# ============================================================

@router.post("/api/record/start")
def start_record():
    """开始流式录音，同时启动实时转写"""
    if is_stream_recording():
        raise HTTPException(400, "已在录制中")

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
                        "message": f"本月转写额度已用完（剩余 {quota_result['remaining']} 分钟），可配置自有 API Key 继续使用",
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

    def pcm_callback(data: bytes) -> None:
        nonlocal _pcm_call_count, _last_speaker_count
        _pcm_call_count += 1
        t = transcriber_ref.get("ref")
        if t and t.is_running:
            t.feed_audio(data)
        # 送入声纹聚类器
        diarizer.feed_audio(data)
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

        logger.info(f"[录制] 开始: task={task_id[:8]}, 设备={RECORD_DEVICE}")
        return {"task_id": task_id, "status": "recording"}

    except RuntimeError as e:
        realtime_queues.pop(task_id, None)
        raise HTTPException(500, f"录制启动失败: {e}")


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
        raise HTTPException(400, "未在录制中")

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

        # 2. 停止录音
        result = stop_recording_with_stream()
        if not task_id:
            task_id = result["task_id"]
        audio_path = result["output_path"]
        duration = result["duration"]

        if task_id not in tasks:
            raise HTTPException(404, "任务不存在")

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
        raise HTTPException(500, f"录制停止失败: {e}")


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
        raise HTTPException(400, "未在录制中")
    try:
        pause_recording_with_stream()
        return {"status": "paused"}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/api/record/resume")
async def resume_record():
    """恢复录制"""
    if not is_stream_recording():
        raise HTTPException(400, "未在录制中")
    try:
        resume_recording_with_stream()
        return {"status": "recording"}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/api/record/abandon")
def abandon_record():
    """放弃录音：停止录制并删除所有相关数据和文件"""
    if not is_stream_recording():
        raise HTTPException(400, "未在录制中")

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
        raise HTTPException(500, f"放弃录音失败: {e}")


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
        raise HTTPException(400, "无活跃的实时总结")
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
        raise HTTPException(400, "无活跃的实时总结")
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
        raise HTTPException(400, "无活跃的实时总结")
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
        raise HTTPException(400, "无活跃的实时总结")
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
        raise HTTPException(400, "无活跃的实时总结")
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
        raise HTTPException(400, "无活跃的录音")

    # 验证说话人存在
    spk = speakers.get_speaker_by_id(req.speaker_uuid)
    if not spk:
        raise HTTPException(404, "说话人不存在")

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


# ============================================================
# WebSocket 实时转写
# ============================================================

@router.websocket("/ws/transcript/{task_id}")
async def websocket_transcript(websocket: WebSocket, task_id: str):
    """
    实时转写 WebSocket。

    前端在录音期间连接此端点，接收实时识别结果。
    消息格式（下行）：
      {"type": "partial", "text": "...", "speaker_id": N, "speaker_name": "..."}    临时结果
      {"type": "sentence", "text": "...", "speaker_id": N, "speaker_name": "..."}   定稿句子
      {"type": "speaker_bound", "speaker_id": N, "speaker_name": "..."}             说话人绑定更新
      {"type": "error", "message": "..."}       错误
      {"type": "ended"}                         转写结束
    """
    await websocket.accept()

    queue = realtime_queues.get(task_id)
    if not queue:
        await websocket.send_json({"type": "error", "message": "任务不存在或未在录制"})
        await websocket.close()
        return

    logger.info(f"[WebSocket] 实时转写连接: task={task_id[:8]}")

    # 回放缓冲区中的历史句子（页面刷新恢复时不丢失转写内容）
    from app.store import realtime_transcript_buffers, realtime_summarizers as _summarizers, realtime_chapter_generators as _chapter_gens
    history = realtime_transcript_buffers.get(task_id, [])
    if history:
        logger.info(f"[WebSocket] 回放历史: task={task_id[:8]}, {len(history)} 条句子")
        for item in history:
            # 回放时重新解析说话人姓名（可能已被绑定）
            sid = item.get("speaker_id", 0)
            speaker_name = resolve_realtime_speaker_name(task_id, sid) if sid else ""
            await websocket.send_json({
                "type": "history",
                "text": item.get("text", ""),
                "speaker_id": sid,
                "speaker_name": speaker_name,
                "begin_time": item.get("begin_time", 0),
                "end_time": item.get("end_time", 0),
            })

    # 回放当前实时总结内容和状态（页面刷新恢复时不丢失摘要）
    summarizer = realtime_summarizers.get(task_id)
    if summarizer:
        current_summary = summarizer.get_final_summary()
        if current_summary:
            logger.info(f"[WebSocket] 回放实时总结: task={task_id[:8]}, {len(current_summary)} 字符")
            await websocket.send_json({
                "type": "summary_update",
                "content": current_summary,
            })
        # 回放总结器当前状态（idle / paused / stopped）+ 剩余秒数 + 间隔
        if summarizer.is_stopped:
            await websocket.send_json({"type": "summary_status", "status": "stopped"})
        elif summarizer.is_paused:
            await websocket.send_json({
                "type": "summary_status", "status": "paused",
                "remaining": summarizer.get_remaining(),
                "interval": summarizer.interval,
            })
        elif summarizer.is_running:
            await websocket.send_json({
                "type": "summary_status", "status": "idle",
                "remaining": summarizer.get_remaining(),
                "interval": summarizer.interval,
            })

    # 回放当前实时章节（页面刷新恢复时不丢失章节进度）
    chapter_gen = _chapter_gens.get(task_id)
    if chapter_gen:
        current_chapters = chapter_gen.get_chapters()
        if current_chapters:
            logger.info(f"[WebSocket] 回放实时章节: task={task_id[:8]}, {len(current_chapters)} 个章节")
            await websocket.send_json({
                "type": "chapters_update",
                "chapters": current_chapters,
            })

    try:
        while True:
            # 从队列取消息（由 SDK 回调通过 push_realtime_msg 投递）
            msg = await asyncio.wait_for(queue.get(), timeout=60.0)
            await websocket.send_json(msg)
            if msg.get("type") == "ended":
                break
    except asyncio.TimeoutError:
        # 60 秒无新消息，正常关闭
        logger.info(f"[WebSocket] 超时关闭: task={task_id[:8]}")
    except WebSocketDisconnect:
        logger.info(f"[WebSocket] 客户端断开: task={task_id[:8]}")
    except Exception as e:
        logger.error(f"[WebSocket] 异常: {e}")
    finally:
        logger.info(f"[WebSocket] 连接结束: task={task_id[:8]}")
