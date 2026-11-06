"""app/routers/record_lifecycle.py — 录制开始/停止（主流程）。

端点：
  POST /api/record/start  — 开始流式录音 + 启动实时转写
  POST /api/record/stop   — 停止录制，进入管线处理

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 record.py 拆分）
"""

import asyncio
import logging
import math
import struct
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

# 以模块方式引用 core.realtime_store：event_loop 全局在 startup 时才赋值，必须运行时通过 / Reference realtime_store as module: event_loop global is only assigned at startup, must read at runtime via
# rt_store.event_loop 读取（若按值 import 会像 _stream_task_id 一样恒为初始值 None） / rt_store.event_loop (import by value would always be initial None like _stream_task_id)
import core.realtime_store as rt_store
import core.settings_store as settings_store
from core import audio_stream, diarization_cluster, realtime_asr
from core.audio import (
    stop_recording_with_stream,
)
from core.errors import LocalEngineError
from core.i18n import _
from core.pipeline_runner import (
    SPEAKER_COUNT_MAX,
    SPEAKER_COUNT_MIN,
    run_pipeline_task,
)
from core.realtime_asr import RealtimeTranscriber
from core.realtime_chapters import RealtimeChapterGenerator
from core.realtime_store import (
    realtime_chapter_generators,
    realtime_diarizers,
    realtime_full_sealed,
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
    realtime_translators,
    resolve_realtime_speaker_name,
)
from core.realtime_summary import RealtimeSummarizer
from core.recording_recovery import cleanup_zombie_recording
from core.settings_store import get_silence_detection_config
from core.silence_detection import cleanup_silence_detection, silence_monitor_loop
from core.task_store import RECORDINGS_DIR, save_task_to_disk, tasks
from core.tasks_repo import set_task
from core.transcript_cleanup import derive_layers

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/record/start")
def start_record(background_tasks: BackgroundTasks):
    """开始流式录音，同时启动实时转写 / Start streaming recording and launch realtime transcription"""
    if audio_stream.is_stream_recording():
        raise HTTPException(400, _("Already recording"))

    # 配额预检：订阅用户额度用尽时阻止录制（自带 Key 用户不受限） / Quota pre-check: block recording when subscribed user quota exhausted (BYOK users unaffected)
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
        logger.warning(f"配额预检失败（不阻止录制）: {e}")

    task_id = str(uuid.uuid4())

    # 创建 asyncio Queue 用于 WebSocket 实时推送 / Create asyncio Queue for WebSocket realtime push
    queue: asyncio.Queue = asyncio.Queue()
    realtime_queues[task_id] = queue

    # 创建声纹聚类器（实时说话人分离，根据用户订阅状态选择 provider） / Create diarizer (realtime speaker separation; provider chosen by subscription)
    diarizer = diarization_cluster.create_realtime_diarizer()
    realtime_diarizers[task_id] = diarizer

    # 初始化实时说话人绑定映射 / Initialize realtime speaker binding map
    realtime_speaker_maps[task_id] = {}

    # 初始化全量实时转写记录（供文本桥接匹配，突破 REALTIME_BUFFER_MAX 限制） / Initialize full realtime transcript (for text bridge matching, bypassing REALTIME_BUFFER_MAX limit)
    realtime_full_transcripts[task_id] = []

    # 读取功能开关（仅用于后台延迟初始化，不阻塞关键路径） / Read feature flags (for deferred init, not blocking critical path)
    feature_flags = settings_store.get_feature_flags()

    # ── 延迟初始化：实时总结器 + 章节生成器 ── / ── Deferred init: realtime summarizer + chapter generator ──
    # 这些组件在 ASR 首句到达前初始化完成即可（通常需数秒），放到后台线程避免阻塞 HTTP 响应 / These components only need to be ready before the first ASR sentence arrives (typically seconds); defer to background to avoid blocking HTTP response
    summarizer_ref: dict[RealtimeSummarizer | None, None] = {None: None}
    chapter_gen_ref: dict[RealtimeChapterGenerator | None, None] = {None: None}

    def _init_auxiliary_components():
        """后台初始化辅助组件：实时总结 + 章节生成 + 磁盘持久化 + 静默检测 / Background init auxiliary components: realtime summary + chapters + disk persistence + silence detection"""
        try:
            # 实时总结器 / Realtime summarizer
            _summarizer = None
            if feature_flags["realtime_summary"]:
                summary_interval = feature_flags.get("realtime_summary_interval", 60)
                _summarizer = RealtimeSummarizer(
                    on_summary=lambda content: rt_store.push_realtime_msg(task_id, {
                        "type": "summary_update", "content": content
                    }),
                    on_status=lambda status: rt_store.push_realtime_msg(task_id, {
                        "type": "summary_status", "status": status
                    }),
                    on_countdown=lambda remaining: rt_store.push_realtime_msg(task_id, {
                        "type": "summary_countdown", "remaining": remaining
                    }),
                    interval=summary_interval,
                )
                realtime_summarizers[task_id] = _summarizer
                _summarizer.start()
            summarizer_ref[None] = _summarizer

            # 实时章节生成器 / Realtime chapter generator
            _chapter_gen = None
            if feature_flags["realtime_chapters"]:
                _chapter_gen = RealtimeChapterGenerator(
                    on_chapters=lambda chapters: rt_store.push_realtime_msg(task_id, {
                        "type": "chapters_update", "chapters": chapters
                    }),
                )
                realtime_chapter_generators[task_id] = _chapter_gen
                _chapter_gen.start()
            chapter_gen_ref[None] = _chapter_gen

            # 任务持久化到磁盘（内存中已存在，磁盘写入可延迟） / Persist task to disk (already in memory, disk write can defer)
            save_task_to_disk(task_id)

            # 静默检测 / Silence detection
            silence_config = get_silence_detection_config()
            if silence_config["enabled"]:
                now_ts = time.time()
                realtime_last_heartbeat[task_id] = now_ts
                realtime_last_sentence[task_id] = now_ts
                realtime_presence_scores[task_id] = float(silence_config["presence"]["score_max"])
                realtime_silence_warnings[task_id] = 0
                loop = rt_store.event_loop
                if loop and not loop.is_closed():
                    monitor_future = asyncio.run_coroutine_threadsafe(
                        silence_monitor_loop(task_id), loop
                    )
                    realtime_silence_monitors[task_id] = monitor_future
                    logger.info(f"[录制] 静默检测已启动: task={task_id[:8]}")
                else:
                    logger.warning(f"[录制] 主事件循环不可用，静默检测未启动: task={task_id[:8]}")

            logger.info(f"[录制] 辅助组件初始化完成: task={task_id[:8]}, summary={_summarizer is not None}, chapters={_chapter_gen is not None}")
        except Exception as e:
            logger.warning(f"[录制] 辅助组件初始化失败（不影响录音）: {e}")

    background_tasks.add_task(_init_auxiliary_components)

    # PCM 回调：将音频数据送入实时 ASR + 声纹聚类 / PCM callback: feed audio data to realtime ASR + diarizer
    # 注意：此回调在 stream_reader 线程执行 / Note: this callback runs in stream_reader thread
    transcriber_ref: dict[str, RealtimeTranscriber | None] = {"ref": None}
    _pcm_call_count = 0
    _last_speaker_count = 0  # 上次推送的说话人数量（避免重复推送） / Last pushed speaker count (avoid duplicate push)
    _volume_warned = False  # 音量过低警告只发一次 / Low volume warning fires only once
    _volume_samples: list[float] = []  # 前 N 次回调的 RMS dB 样本 / RMS dB samples from first N callbacks
    _VOLUME_CHECK_LIMIT = 600  # 前 600 次回调（≈60 秒）用于音量检测，窗口足够长以避免间歇沉默误报 / First 600 callbacks (~60s) for volume detection; long enough to avoid intermittent silence false positives
    _VOLUME_THRESHOLD_DB = -50.0  # 低于此值视为音量极低 / Below this is considered extremely low volume

    def pcm_callback(data: bytes) -> None:
        nonlocal _pcm_call_count, _last_speaker_count, _volume_warned
        _pcm_call_count += 1
        t = transcriber_ref.get("ref")
        if t and t.is_running:
            t.feed_audio(data)
        # 送入声纹聚类器
        diarizer.feed_audio(data)

        # ── 前 60 秒音量检测：提醒用户麦克风是否异常 ── / ── First 60s volume check: alert user if mic is abnormal ──
        if not _volume_warned and _pcm_call_count <= _VOLUME_CHECK_LIMIT:
            if len(data) >= 64:  # 至少 32 个样本才计算 / Need at least 32 samples to compute
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
                        f"[录制] 前 60 秒音量极低 (mean={avg_db:.1f} dB)，"
                        f"请检查麦克风或音频输入设备"
                    )
                    rt_store.push_realtime_msg(task_id, {
                        "type": "volume_warning",
                        "level": "low",
                        "avg_db": round(avg_db, 1),
                    })

        # 每 20 次回调（约 2 秒）检查一次说话人数量变化，推送更新 / Every 20 callbacks (~2s) check speaker count change and push update
        if _pcm_call_count % 20 == 0:
            active_count = diarizer.get_active_speaker_count()
            if active_count != _last_speaker_count:
                _last_speaker_count = active_count
                rt_store.push_realtime_msg(task_id, {
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
        # 启动流式录音（ffmpeg 采集 → PCM pipe → 写文件 + pcm_callback） / Start streaming recording (ffmpeg capture -> PCM pipe -> write file + pcm_callback)
        result = audio_stream.start_recording_with_stream(
            device=settings_store.RECORD_DEVICE,
            output_dir=RECORDINGS_DIR,
            task_id=task_id,
            pcm_callback=pcm_callback,
        )

        # 启动实时转写（优雅降级：失败不影响录音） / Start realtime transcription (graceful degradation: failure doesn't affect recording)
        # 注意：start() 可能阻塞（等待连接 + 重试），放到后台线程避免阻塞事件循环 / Note: start() may block (wait for connection + retry); run in background thread to avoid blocking event loop

        # 转写分层（PLAN-TRANSCRIPT-LAYERING）：口语清理开关做「会话级快照」，
        # 整场录制固定同一口径，避免一场纪要前后规则不一致。
        try:
            from app.settings_store import get_transcript_config
            _cleanup_enabled = bool(get_transcript_config().get("cleanup", {}).get("enabled", True))
        except Exception as e:
            logger.warning(f"[录制] 读取转写清理配置失败（按开启处理）: {e}")
            _cleanup_enabled = True

        def _on_sentence_end(s: dict) -> None:
            """定稿句子回调：推送 WebSocket + 送入实时总结 / Finalized sentence callback: push WebSocket + feed realtime summary"""
            # 过滤空文本（无人说话时 ASR 可能返回空句子） / Filter empty text (ASR may return empty sentences when no one speaks)
            raw_text = s.get("text", "")
            if not raw_text.strip():
                logger.debug(f"[录制] 跳过空句子: speaker={s.get('begin_time')}")
                return
            speaker_id = diarizer.get_speaker(
                begin_time=s.get("begin_time", 0) / 1000.0,
                end_time=s.get("end_time", 0) / 1000.0,
            )
            # 解析说话人姓名（从实时绑定映射中查找） / Resolve speaker name (from realtime binding map)
            speaker_name = resolve_realtime_speaker_name(task_id, speaker_id)

            # 口语清理（本地确定性规则，契约见 core.transcript_cleanup.derive_layers）：
            # - WS 消息 text 永远是原文，另附 clean_text/clean_ops（上屏可切视图）；
            # - 下游摘要/章节/翻译吃 clean（无事实内容的纯语气词句跳过）；
            # - realtime_store 缓存只取 text 白名单，AI 对话上下文仍是原文。
            layers = derive_layers(raw_text, enabled=_cleanup_enabled)
            ws_msg = {
                "type": "sentence",
                "text": raw_text,
                "begin_time": s.get("begin_time", 0),
                "end_time": s.get("end_time", 0),
                "speaker_id": speaker_id,
                "speaker_name": speaker_name,
            }
            if layers["clean_text"] is not None:
                ws_msg["clean_text"] = layers["clean_text"]
                ws_msg["clean_ops"] = layers["clean_ops"]
            feed_text = layers["feed_text"]
            rt_store.push_realtime_msg(task_id, ws_msg)
            # 更新最后定稿句子时间戳（供静默检测使用） / Update last finalized sentence timestamp (for silence detection)
            realtime_last_sentence[task_id] = time.time()
            # 清理后无事实内容（纯语气词句）：只上屏留痕，不喂下游
            if not feed_text.strip():
                return
            # 送入实时总结器（含说话人姓名） / Feed realtime summarizer (with speaker name)
            _summarizer = summarizer_ref.get(None)
            if _summarizer:
                _summarizer.feed_sentence({
                    **s,
                    "text": feed_text,
                    "speaker_name": speaker_name,
                })
            # 送入实时章节生成器 / Feed realtime chapter generator
            _chapter_gen = chapter_gen_ref.get(None)
            if _chapter_gen:
                _chapter_gen.feed_sentence({
                    **s,
                    "text": feed_text,
                    "speaker_name": speaker_name,
                })
            # 送入实时翻译器（若已启用） / Feed realtime translator (if enabled)
            translator = realtime_translators.get(task_id)
            if translator and translator.is_running:
                logger.debug(f"[录制] 句子送入翻译器: task={task_id[:8]}, text={feed_text[:40]}")
                translator.feed_sentence({
                    "text": feed_text,
                    "speaker_id": speaker_id,
                    "speaker_name": speaker_name,
                    "begin_time": s.get("begin_time", 0),
                    "end_time": s.get("end_time", 0),
                })

        # R9（WP-I）：local 模式默认用 LocalSegmentTranscriber 分段逐句上屏
        # （realtime_segments.enabled 默认 true）；仅显式关闭（逃生通道）时退回
        # RealtimeTranscriber，其 start() 抛 realtime_degraded_to_batch 降级声明
        # （WP-H，见 core/realtime_asr.py）；其余云端模式同样走 RealtimeTranscriber。
        _asr_mode_now = realtime_asr._get_asr_mode()
        _segments_cfg: dict = {}
        if _asr_mode_now == "local":
            try:
                from app.settings_store import get_engine_config
                _segments_cfg = get_engine_config()["local"].get("realtime_segments") or {}
            except Exception as e:
                logger.warning(f"[录制] 读取分段增量配置失败（按未开启处理）: {e}")

        _transcriber_callbacks = dict(
            on_partial=lambda text: rt_store.push_realtime_msg(task_id, {
                "type": "partial",
                "text": text,
                "speaker_id": diarizer.get_speaker(),
                "speaker_name": resolve_realtime_speaker_name(task_id, diarizer.get_speaker()),
            }),
            on_sentence_end=_on_sentence_end,
            on_error=lambda msg: rt_store.push_realtime_msg(task_id, {
                "type": "error", "message": msg
            }),
            on_complete=lambda: rt_store.push_realtime_msg(task_id, {
                "type": "ended"
            }),
        )
        if _asr_mode_now == "local" and _segments_cfg.get("enabled"):
            from core.realtime_local_asr import LocalSegmentTranscriber
            transcriber = LocalSegmentTranscriber(
                segment_config=_segments_cfg,
                on_status=lambda info: rt_store.push_realtime_msg(task_id, {"type": "status", **info}),
                **_transcriber_callbacks,
            )
        else:
            transcriber = realtime_asr.RealtimeTranscriber(**_transcriber_callbacks)

        def _start_transcriber_bg():
            """后台启动实时转写（含重试逻辑） / Background start realtime transcription (with retry logic)"""
            # ── 前置检查：proxy 模式下 token 缺失时直接跳过（优雅降级）──
            # Pre-check: skip realtime transcription when proxy token is missing (graceful degradation)
            try:
                _asr_mode = realtime_asr._get_asr_mode()
                if _asr_mode == "proxy" and not realtime_asr.ASR_PROXY_TOKEN:
                    logger.warning(f"[录制] ASR_PROXY_TOKEN 未配置，跳过实时转写（仅录音模式）: task={task_id[:8]}")
                    rt_store.push_realtime_msg(task_id, {
                        "type": "warning",
                        "message": _("ASR proxy token not configured. Realtime transcription disabled. Recording will continue normally.")
                    })
                    return
            except Exception:
                pass

            try:
                transcriber.start()
                transcriber_ref["ref"] = transcriber
                realtime_transcribers[task_id] = transcriber
                logger.info(f"[录制] 实时转写已启动: task={task_id[:8]}")
            except LocalEngineError as e:
                if e.error_code == "realtime_degraded_to_batch":
                    # WP-H 第 2 项：本地模式实时预览降级是设计内行为（非故障），
                    # 推非错误状态声明，与录音页本地模式横幅口径统一；
                    # 不得再推 type:"error" 红色报错（REQ-LOCAL-REALTIME-INCR AC 第 6 条）。
                    logger.info(f"[录制] 本地模式按设计降级为批处理（状态声明，非错误）: task={task_id[:8]}")
                    transcriber_ref["ref"] = None
                    rt_store.push_realtime_msg(task_id, {
                        "type": "status",
                        "status": "local_batch_mode",
                        "message": str(e),
                    })
                    return
                # 其余本地引擎错误（模型未就绪等）仍按失败处理
                logger.warning(f"[录制] 本地引擎实时转写启动失败（仅录音模式）: {e}")
                transcriber_ref["ref"] = None
                rt_store.push_realtime_msg(task_id, {
                    "type": "error",
                    "message": _("Realtime transcription unavailable: {err}, recording will continue normally").format(err=e)
                })
            except Exception as e:
                logger.warning(f"[录制] 实时转写启动失败（仅录音模式）: {e}")
                transcriber_ref["ref"] = None
                rt_store.push_realtime_msg(task_id, {
                    "type": "error",
                    "message": _("Realtime transcription unavailable: {err}, recording will continue normally").format(err=e)
                })

        threading.Thread(target=_start_transcriber_bg, daemon=True).start()

        output_path = result["output_path"]

        # 创建任务记录 / Create task record
        now = datetime.now()
        set_task(task_id, {
            "task_id": task_id,
            "status": "recording",
            "source": "record",
            "progress": 0,
            "message": _("Recording..."),
            "audio_name": "",
            "audio_path": str(output_path),
            "audio_duration": None,
            "speaker_count": None,
            "summary": None,
            "output_path": None,
            "created_at": now.isoformat(),
            "meeting_date": now.strftime("%Y-%m-%d"),
            "error": None,
        })
        # 磁盘持久化已委托给后台任务 _init_auxiliary_components() / Disk persistence deferred to background task

        logger.info(f"[录制] 开始: task={task_id[:8]}, 设备={settings_store.RECORD_DEVICE}")
        return {"task_id": task_id, "status": "recording"}

    except RuntimeError as e:
        realtime_queues.pop(task_id, None)
        # 录音失败时附带诊断信息，帮助用户和开发者定位问题
        # Attach diagnostic info when recording fails to help users and developers troubleshoot
        import platform as _platform

        from core.audio import check_ffmpeg
        diag_hint = ""
        if not check_ffmpeg():
            diag_hint = " | ffmpeg not found in PATH"
        elif _platform.system() == "Windows" and not settings_store.RECORD_DEVICE:
            diag_hint = " | auto-detection failed; set RECORD_DEVICE env var"
        raise HTTPException(500, _("Failed to start recording: {err}").format(err=str(e) + diag_hint))


class RecordStopRequest(BaseModel):
    notes: Optional[str] = None  # 用户录音期间输入的笔记 / User notes entered during recording


@router.post("/api/record/stop")
def stop_record(
    background_tasks: BackgroundTasks,
    data: Optional[RecordStopRequest] = None,
):
    """停止录制，录音文件自动进入管线处理 / Stop recording; audio file automatically enters pipeline processing

    注意：此端点必须用 def（非 async def），因为 stop_recording_with_stream() / Note: this endpoint must use def (not async def) because stop_recording_with_stream()
    包含 subprocess.wait / thread.join 等阻塞操作。 / contains blocking operations like subprocess.wait / thread.join.
    FastAPI 会自动在线程池中运行同步端点，避免阻塞事件循环。 / FastAPI auto-runs sync endpoints in thread pool to avoid blocking event loop.
    """
    if not audio_stream.is_stream_recording():
        # ── 兜底：静默检测自动关停 / Fallback: silence detection auto-stopped ──
        # 自动关停已 stop_recording + 派发纪要管线，realtime_transcribers 已被 pop，
        # tasks[tid] 状态推进到 processing 或终态。此时前端再点「结束录音」不应误判为 crashed。
        # 查 tasks 找 status 为 processing/completed/failed 且最近活跃的任务：
        # - 命中 → 返回正常响应，引导前端跳转 generating
        # - 仍是 recording（真僵尸）→ 走原清理逻辑并报错
        # Auto-stop already stopped recording + dispatched pipeline, realtime_transcribers popped,
        # tasks[tid] advanced to processing or terminal. Clicking "stop" must NOT be misjudged as
        # crashed. Scan tasks for one in processing/completed/failed with recent activity:
        # hit → return normal response guiding frontend to generating; still recording → real
        # zombie, run cleanup and raise.
        candidate_tid = None
        candidate_created = ""
        for _tid, _task in tasks.items():
            _s = _task.get("status")
            if _s in ("processing", "completed", "failed") and _task.get("auto_stop_reason"):
                _created = _task.get("created_at", "")
                if _created > candidate_created:
                    candidate_tid, candidate_created = _tid, _created
        if candidate_tid:
            t_state = tasks[candidate_tid].get("status")
            logger.info(f"[录制] stop 收到但 ffmpeg 已停（任务 {t_state}，静默检测自动关停）: task={candidate_tid[:8]}")
            # 静默检测已清理实时资源，这里仅清理可能残留的队列
            realtime_queues.pop(candidate_tid, None)
            return {
                "task_id": candidate_tid,
                "status": t_state,
                "duration": tasks[candidate_tid].get("audio_duration") or 0,
            }

        # ── 僵尸录音清理 / Zombie recording cleanup ──
        # ffmpeg 进程已崩溃但任务状态仍为 recording，需要清理
        # ffmpeg process crashed but task status is still "recording"; needs cleanup
        cleanup_zombie_recording()
        raise HTTPException(400, _("Not recording (recording process may have crashed)"))

    # 提取笔记 / Extract notes
    user_notes = data.notes if data else None

    try:
        # 1. 先停止实时转写 / 1. Stop realtime transcription first
        # 找到当前录制中的 task_id / Find currently recording task_id
        task_id = None
        estimated_speaker_count = None
        for tid, t in realtime_transcribers.items():
            task_id = tid
            break

        if task_id:
            transcriber = realtime_transcribers.pop(task_id, None)
            # R9/D-I2：本地分段增量转写的实时全文即定稿（stop() 已排空末段），
            # 会后不再重跑全量批转写；标记在下方保存 full_transcript 时一并落库。
            _incremental_finalized = bool(getattr(transcriber, "is_local_incremental", False))
            if transcriber:
                try:
                    transcriber.stop()
                except Exception as e:
                    logger.warning(f"实时转写停止异常: {e}")
            # 清理声纹聚类器，提取说话人数量供批管线使用 / Clean up diarizer; extract speaker count for batch pipeline
            diarizer = realtime_diarizers.pop(task_id, None)
            if diarizer:
                raw_count = diarizer.get_speaker_count()
                active_count = diarizer.get_active_speaker_count()
                # 执行后处理合并（解决 MFCC 时间漂移导致的过度分裂） / Run post-processing merge (resolve over-splitting from MFCC time drift)
                final_count = diarizer.finalize()
                # 优先使用有效说话人数量（过滤伪说话人），但不超过合并后数量 / Prefer active speaker count (filter pseudo speakers), but cap at merged count
                estimated_speaker_count = max(SPEAKER_COUNT_MIN, min(SPEAKER_COUNT_MAX, min(active_count, final_count)))
                vad_stats = diarizer.get_vad_stats()
                logger.info(
                    f"[录制] 声纹聚类统计: 原始={raw_count}, 有效={active_count}, "
                    f"合并后={final_count}, 钳制={estimated_speaker_count}, "
                    f"VAD语音段={vad_stats['speech_segments']}, "
                    f"VAD静音段={vad_stats['silence_segments']}, "
                    f"语音占比={vad_stats['speech_ratio']:.1%}"
                )
            # 停止实时总结器，保存最终摘要 / Stop realtime summarizer; save final summary
            summarizer = realtime_summarizers.pop(task_id, None)
            if summarizer:
                summarizer.stop()
                final_summary = summarizer.get_final_summary()
                if final_summary and task_id in tasks:
                    tasks[task_id]["realtime_summary"] = final_summary
                logger.info(f"[录制] 实时总结停止: {summarizer.summary_count} 次总结")
            # 停止实时章节生成器，保存最终章节 / Stop realtime chapter generator; save final chapters
            chapter_gen = realtime_chapter_generators.pop(task_id, None)
            if chapter_gen:
                chapter_gen.stop()
                final_chapters = chapter_gen.get_chapters()
                if final_chapters and task_id in tasks:
                    tasks[task_id]["realtime_chapters"] = final_chapters
                logger.info(f"[录制] 实时章节停止: {chapter_gen.update_count} 次更新")
            # 停止实时翻译器，保存翻译结果 / Stop realtime translator; save translation results
            translator = realtime_translators.pop(task_id, None)
            if translator:
                translator.stop()
                final_translations = translator.get_all_translations()
                if final_translations and task_id in tasks:
                    tasks[task_id]["translations"] = final_translations
                logger.info(f"[录制] 实时翻译停止: {translator.translation_count} 次翻译")
            # 提取实时说话人绑定（供批管线使用） / Extract realtime speaker bindings (for batch pipeline)
            realtime_binding = realtime_speaker_maps.pop(task_id, {})
            if realtime_binding and task_id in tasks:
                tasks[task_id]["realtime_speaker_binding"] = {
                    str(k): v for k, v in realtime_binding.items()
                }
                logger.info(f"[录制] 实时说话人绑定: {len(realtime_binding)} 条")
            # 保存全量实时转写记录（供文本桥接匹配，持久化到 task） / Save full realtime transcript (for text bridge matching; persist to task)
            full_transcript = realtime_full_transcripts.pop(task_id, [])
            if task_id in tasks:
                # DEF-PROXY-02：空列表也绑定引用 + 登记封存——SDK 线程迟到的句尾定稿
                # 经 realtime_full_sealed 同一列表对象落地，stop 竞态不再丢失实时句子
                tasks[task_id]["realtime_full_transcript"] = full_transcript
                realtime_full_sealed[task_id] = full_transcript
            if full_transcript and task_id in tasks:
                logger.info(f"[录制] 全量实时转写已保存: {len(full_transcript)} 条句子")
                # D-I2：增量段拼接即定稿——仅当增量转写器产出了内容才打标记；
                # 空内容（全部段被丢/纯静音）不打标，回退 stage1 全量批转写兜底。
                if _incremental_finalized:
                    tasks[task_id]["transcript_finalized_incremental"] = True
                    logger.info(f"[录制] 本地增量转写标记为定稿（会后不重跑全量，D-I2）: {len(full_transcript)} 句")
            # 停止静默监测协程，清理静默检测状态 / Stop silence monitoring coroutine; clean up silence detection state
            cleanup_silence_detection(task_id)

        # 2. 停止录音 / 2. Stop recording
        result = stop_recording_with_stream()
        if not task_id:
            task_id = result["task_id"]
        audio_path = result["output_path"]
        duration = result["duration"]

        if task_id not in tasks:
            raise HTTPException(404, _("Task not found"))

        # 3. 发送结束消息 / 3. Send end message
        rt_store.push_realtime_msg(task_id, {"type": "ended"})

        # 4. 更新任务信息 / 4. Update task info
        tasks[task_id]["audio_name"] = f"录音 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        tasks[task_id]["audio_duration"] = duration
        # DEF-PROXY-03 观测项：WAV 数据时长 vs 墙钟偏差自检（>15% 留痕，最终定性待有声样音复测）
        try:
            from core.audio import get_audio_duration
            _wav_dur = get_audio_duration(audio_path)
            if duration and duration > 5 and _wav_dur and abs(_wav_dur - duration) / duration > 0.15:
                tasks[task_id]["wav_wallclock_gap_sec"] = round(duration - _wav_dur, 1)
                logger.warning(
                    f"[录制] WAV 时长 {_wav_dur:.1f}s 与墙钟 {duration:.1f}s 偏差 >15%"
                    f"（DEF-PROXY-03 观测留痕，待样音复测定性）: task={task_id[:8]}"
                )
        except Exception as _e:
            logger.debug(f"[录制] WAV 时长自检失败（不阻断）: {_e}")
        if user_notes:
            tasks[task_id]["user_notes"] = user_notes

        # 用量计量：按录制时长记录实时转写用量 / Usage metering: record realtime transcription usage by recording duration
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

        # 5. 后台执行管线（归一化 → 上传 → 转写 → 纪要） / 5. Run pipeline in background (normalize -> upload -> transcribe -> summary)
        background_tasks.add_task(run_pipeline_task, task_id, audio_path, tasks[task_id]["audio_name"], None, estimated_speaker_count)

        # 6. 清理实时状态 / 6. Clean up realtime state
        realtime_queues.pop(task_id, None)

        logger.info(f"[录制] 完成: task={task_id[:8]}, 时长={duration:.1f}s")
        return {
            "task_id": task_id,
            "status": "processing",
            "duration": duration,
        }

    except RuntimeError as e:
        raise HTTPException(500, _("Failed to stop recording: {err}").format(err=e))
