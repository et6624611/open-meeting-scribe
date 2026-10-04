"""
app/routers/record.py — 录制控制 + 实时总结/绑定 / Recording control + realtime summary/binding

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 2.0.0

v2.0 重构：WebSocket 端点与静默检测已拆分至独立模块。 / v2.0 refactor: WebSocket endpoints and silence detection split to independent modules.
  - app/routers/ws_transcript.py — WebSocket 实时转写端点 / WebSocket realtime transcription endpoint
  - core/silence_detection.py    — 静默检测协程与自动关停 / Silence detection coroutine and auto-stop
"""

import asyncio
import logging
import math
import struct
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

# 以模块方式引用 realtime_store：event_loop 全局在 startup 时才赋值，必须运行时通过 / Reference realtime_store as module: event_loop global is only assigned at startup, must read at runtime via
# rt_store.event_loop 读取（若按值 import 会像 _stream_task_id 一样恒为初始值 None） / rt_store.event_loop (import by value would always be initial None like _stream_task_id)
import app.realtime_store as rt_store
import app.store as store
from app.store import (
    RECORDINGS_DIR,
    SPEAKER_COUNT_MAX,
    SPEAKER_COUNT_MIN,
    TASKS_DIR,
    get_feature_flags,
    get_silence_detection_config,
    push_realtime_msg,
    realtime_chapter_generators,
    realtime_diarizers,
    realtime_full_transcripts,
    realtime_full_sealed,
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
    run_pipeline_task,
    save_task_to_disk,
    tasks,
)
from core import speakers
from core.audio import (
    get_stream_recording_info,
    is_stream_recording,
    list_audio_devices,
    pause_recording_with_stream,
    resume_recording_with_stream,
    start_recording_with_stream,
    stop_recording_with_stream,
)
from core.diarization import create_realtime_diarizer
from core.errors import LocalEngineError
from core.i18n import _
from core import realtime_asr
from core.realtime_asr import RealtimeTranscriber
from core.realtime_chapters import RealtimeChapterGenerator
from core.realtime_summary import RealtimeSummarizer
from core.silence_detection import cleanup_silence_detection, silence_monitor_loop
from core.transcript_cleanup import derive_layers

logger = logging.getLogger(__name__)

router = APIRouter(tags=["record"])


# ============================================================
# 录音设备诊断 / Recording Device Diagnostics
# ============================================================

@router.get("/api/record/devices")
def get_audio_devices():
    """列出系统可用的音频输入设备 + 当前录音设备配置。
    List available audio input devices + current recording device config.
    """
    import platform as _platform
    from core.audio import check_ffmpeg

    devices = list_audio_devices()
    is_win = _platform.system() == "Windows"

    return {
        "devices": devices,
        "current_device": store.RECORD_DEVICE,
        "platform": _platform.system(),
        "auto_detect": not store.RECORD_DEVICE if is_win else False,
        "ffmpeg_available": check_ffmpeg(),
    }


@router.get("/api/record/diagnostics")
def get_recording_diagnostics():
    """录音环境诊断信息，用于排查设备检测失败问题。
    Recording environment diagnostics for troubleshooting device detection failures.
    """
    import platform as _platform
    import shutil
    from core.audio import check_ffmpeg
    from core.audio_recording import (
        _WINDOWS_DEVICE_CACHE,
        _find_windows_audio_device,
        _find_windows_audio_device_ps,
    )

    is_win = _platform.system() == "Windows"
    ffmpeg_path = shutil.which("ffmpeg")
    devices = list_audio_devices()

    diag: dict = {
        "platform": _platform.system(),
        "ffmpeg_available": check_ffmpeg(),
        "ffmpeg_path": ffmpeg_path or "",
        "current_device": store.RECORD_DEVICE,
        "device_count": len(devices),
        "devices": devices,
    }

    if is_win:
        diag["windows"] = {
            "cached_device": _WINDOWS_DEVICE_CACHE,
            "ps_detection": _find_windows_audio_device_ps(),
            "ffmpeg_detection": _find_windows_audio_device(),
        }

    return diag


class RecordDeviceRequest(BaseModel):
    device: str  # 设备名称，空字符串表示自动检测 / Device name; empty string means auto-detect


@router.post("/api/record/device")
def set_record_device(req: RecordDeviceRequest):
    """设置录音设备（运行时生效并持久化到 settings.json，重启后按 settings>env>平台默认恢复；DEF-DEVICE-01-BE）。
    Set recording device (runtime effect + persisted to settings.json; restored on restart per settings > env > platform default).
    """
    from app.store import set_record_device as _set_device
    # 清除 Windows 设备缓存，使下次录音使用新设备
    # Clear Windows device cache so next recording uses the new device
    import core.audio_recording as _ar
    _ar._WINDOWS_DEVICE_CACHE = None

    _set_device(req.device)
    logger.info(f"[录制] 设备已更新: '{req.device}' ({'auto-detect' if not req.device else 'manual'})")
    return {"device": req.device, "auto_detect": not req.device}


def _cleanup_zombie_recording() -> None:
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


# ============================================================
# 录制控制 / Recording Control
# ============================================================

@router.post("/api/record/start")
def start_record(background_tasks: BackgroundTasks):
    """开始流式录音，同时启动实时转写 / Start streaming recording and launch realtime transcription"""
    if is_stream_recording():
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
    diarizer = create_realtime_diarizer()
    realtime_diarizers[task_id] = diarizer

    # 初始化实时说话人绑定映射 / Initialize realtime speaker binding map
    realtime_speaker_maps[task_id] = {}

    # 初始化全量实时转写记录（供文本桥接匹配，突破 REALTIME_BUFFER_MAX 限制） / Initialize full realtime transcript (for text bridge matching, bypassing REALTIME_BUFFER_MAX limit)
    realtime_full_transcripts[task_id] = []

    # 读取功能开关（仅用于后台延迟初始化，不阻塞关键路径） / Read feature flags (for deferred init, not blocking critical path)
    feature_flags = get_feature_flags()

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
                realtime_summarizers[task_id] = _summarizer
                _summarizer.start()
            summarizer_ref[None] = _summarizer

            # 实时章节生成器 / Realtime chapter generator
            _chapter_gen = None
            if feature_flags["realtime_chapters"]:
                _chapter_gen = RealtimeChapterGenerator(
                    on_chapters=lambda chapters: push_realtime_msg(task_id, {
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
                    push_realtime_msg(task_id, {
                        "type": "volume_warning",
                        "level": "low",
                        "avg_db": round(avg_db, 1),
                    })

        # 每 20 次回调（约 2 秒）检查一次说话人数量变化，推送更新 / Every 20 callbacks (~2s) check speaker count change and push update
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
        # 启动流式录音（ffmpeg 采集 → PCM pipe → 写文件 + pcm_callback） / Start streaming recording (ffmpeg capture -> PCM pipe -> write file + pcm_callback)
        result = start_recording_with_stream(
            device=store.RECORD_DEVICE,
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
            push_realtime_msg(task_id, ws_msg)
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
        if _asr_mode_now == "local" and _segments_cfg.get("enabled"):
            from core.realtime_local_asr import LocalSegmentTranscriber
            transcriber = LocalSegmentTranscriber(
                segment_config=_segments_cfg,
                on_status=lambda info: push_realtime_msg(task_id, {"type": "status", **info}),
                **_transcriber_callbacks,
            )
        else:
            transcriber = RealtimeTranscriber(**_transcriber_callbacks)

        def _start_transcriber_bg():
            """后台启动实时转写（含重试逻辑） / Background start realtime transcription (with retry logic)"""
            # ── 前置检查：proxy 模式下 token 缺失时直接跳过（优雅降级）──
            # Pre-check: skip realtime transcription when proxy token is missing (graceful degradation)
            try:
                _asr_mode = realtime_asr._get_asr_mode()
                if _asr_mode == "proxy" and not realtime_asr.ASR_PROXY_TOKEN:
                    logger.warning(f"[录制] ASR_PROXY_TOKEN 未配置，跳过实时转写（仅录音模式）: task={task_id[:8]}")
                    push_realtime_msg(task_id, {
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
                    push_realtime_msg(task_id, {
                        "type": "status",
                        "status": "local_batch_mode",
                        "message": str(e),
                    })
                    return
                # 其余本地引擎错误（模型未就绪等）仍按失败处理
                logger.warning(f"[录制] 本地引擎实时转写启动失败（仅录音模式）: {e}")
                transcriber_ref["ref"] = None
                push_realtime_msg(task_id, {
                    "type": "error",
                    "message": _("Realtime transcription unavailable: {err}, recording will continue normally").format(err=e)
                })
            except Exception as e:
                logger.warning(f"[录制] 实时转写启动失败（仅录音模式）: {e}")
                transcriber_ref["ref"] = None
                push_realtime_msg(task_id, {
                    "type": "error",
                    "message": _("Realtime transcription unavailable: {err}, recording will continue normally").format(err=e)
                })

        threading.Thread(target=_start_transcriber_bg, daemon=True).start()

        output_path = result["output_path"]

        # 创建任务记录 / Create task record
        now = datetime.now()
        tasks[task_id] = {
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
        }
        # 磁盘持久化已委托给后台任务 _init_auxiliary_components() / Disk persistence deferred to background task

        logger.info(f"[录制] 开始: task={task_id[:8]}, 设备={store.RECORD_DEVICE}")
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
        elif _platform.system() == "Windows" and not store.RECORD_DEVICE:
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
    if not is_stream_recording():
        # ── 僵尸录音清理 / Zombie recording cleanup ──
        # ffmpeg 进程已崩溃但任务状态仍为 recording，需要清理
        # ffmpeg process crashed but task status is still "recording"; needs cleanup
        _cleanup_zombie_recording()
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
        push_realtime_msg(task_id, {"type": "ended"})

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
        _cleanup_zombie_recording()
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
        _cleanup_zombie_recording()
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
        _cleanup_zombie_recording()
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
# 实时总结控制 / Realtime Summary Control
# ============================================================

@router.post("/api/record/summary/pause")
async def pause_summary():
    """暂停实时总结 / Pause realtime summary"""
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
    """恢复实时总结 / Resume realtime summary"""
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
    """停止实时总结（彻底关闭，需手动恢复） / Stop realtime summary (fully stopped; manual restart required)"""
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
    """重新启动已停止的实时总结 / Restart previously stopped realtime summary"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    summarizer.restart()
    return {"status": "restarted"}


class SummaryIntervalRequest(BaseModel):
    interval: int  # 秒，可选 30/60/120/300 / Seconds; options: 30/60/120/300


@router.post("/api/record/summary/interval")
async def set_summary_interval(req: SummaryIntervalRequest):
    """热更新实时总结间隔（录音中立即生效） / Hot-update realtime summary interval (takes effect immediately during recording)"""
    summarizer = None
    for tid, s in realtime_summarizers.items():
        summarizer = s
        break
    if not summarizer:
        raise HTTPException(400, _("No active real-time summary"))
    # 下限 30 秒 / Minimum 30 seconds
    new_interval = max(30, req.interval)
    summarizer.set_interval(new_interval)
    return {"status": "updated", "interval": summarizer.interval}


# ============================================================
# 实时说话人绑定 / Realtime Speaker Binding
# ============================================================

class RealtimeBindSpeakerRequest(BaseModel):
    speaker_id: int         # ASR 说话人编号（0, 1, 2...） / ASR speaker index (0, 1, 2...)
    speaker_uuid: str       # speakers.json 中的说话人 UUID / Speaker UUID in speakers.json


@router.post("/api/record/bind-speaker")
async def realtime_bind_speaker(req: RealtimeBindSpeakerRequest):
    """实时说话人绑定。 / Realtime speaker binding.

    在录音期间将 ASR 说话人编号绑定到全局说话人档案。 / Bind ASR speaker index to global speaker profile during recording.
    绑定后立即通过 WebSocket 通知前端更新所有转写条目。 / Immediately notify frontend via WebSocket to update all transcript entries.
    """
    # 找到当前录制中的 task_id / Find currently recording task_id
    task_id = None
    for tid in realtime_speaker_maps:
        task_id = tid
        break
    if not task_id:
        raise HTTPException(400, _("No active recording"))

    # 验证说话人存在 / Verify speaker exists
    spk = speakers.get_speaker_by_id(req.speaker_uuid)
    if not spk:
        raise HTTPException(404, _("Speaker not found"))

    # 记录绑定前，先获取旧的兆底名称（用于更新缓冲区和全量转写） / Before recording binding, get old fallback name (for updating buffer and full transcript)
    old_name = resolve_realtime_speaker_name(task_id, req.speaker_id)

    # 记录绑定 / Record binding
    realtime_speaker_maps[task_id][req.speaker_id] = req.speaker_uuid
    logger.info(f"[实时绑定] speaker_{req.speaker_id} → {spk.name}")

    # 通过 WebSocket 广播绑定更新 / Broadcast binding update via WebSocket
    push_realtime_msg(task_id, {
        "type": "speaker_bound",
        "speaker_id": req.speaker_id,
        "speaker_uuid": req.speaker_uuid,
        "speaker_name": spk.name,
    })

    # 更新实时总结缓冲区中已缓冲句子的说话人姓名 / Update speaker name of buffered sentences in realtime summary buffer
    summarizer = realtime_summarizers.get(task_id)
    if summarizer and old_name != spk.name:
        summarizer.update_speaker_name(old_name, spk.name)

    # 更新全量实时转写记录中的说话人姓名（确保 WebSocket 重连回放时也显示真名） / Update speaker name in full realtime transcript (ensure real names shown on WebSocket reconnect replay)
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
    """获取当前录音的说话人绑定状态 / Get current recording's speaker binding status"""
    task_id = None
    for tid in realtime_speaker_maps:
        task_id = tid
        break
    if not task_id:
        return {"bindings": {}, "task_id": None}

    binding_map = realtime_speaker_maps.get(task_id, {})
    # 补充姓名 / Enrich with names
    result = {}
    for sid, spk_uuid in binding_map.items():
        spk = speakers.get_speaker_by_id(spk_uuid)
        result[str(sid)] = {
            "speaker_uuid": spk_uuid,
            "speaker_name": spk.name if spk else "",
        }
    return {"bindings": result, "task_id": task_id}

