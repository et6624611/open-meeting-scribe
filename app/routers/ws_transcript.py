"""
app/routers/ws_transcript.py — WebSocket 实时转写端点 / WebSocket realtime transcription endpoint

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
版本 / Version: 1.1.0（新增实时翻译支持 / added realtime translation support）

职责 / Responsibilities:
  - WebSocket 实时转写端点（/ws/transcript/{task_id}） / WebSocket realtime transcription endpoint
  - 历史回放（句子 + 总结 + 章节 + 翻译） / History replay (sentences + summaries + chapters + translations)
  - 双向监听（队列消息 + 客户端心跳 + 翻译控制命令） / Bidirectional listening (queue messages + client heartbeat + translation control)

从 app/routers/record.py 拆分而来 / Split from app/routers/record.py.
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.store import (
    push_realtime_msg,
    realtime_chapter_generators,
    realtime_full_transcripts,
    realtime_last_heartbeat,
    realtime_presence_scores,
    realtime_queues,
    realtime_silence_warnings,
    realtime_summarizers,
    realtime_translations,
    realtime_translators,
    resolve_realtime_speaker_name,
)
from core.i18n import _, set_current_locale
from core.transcript_cleanup import enrich_sentence
from core.translate import RealtimeTranslator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/transcript/{task_id}")
async def websocket_transcript(websocket: WebSocket, task_id: str, locale: str = "zh_CN"):
    """实时转写 WebSocket。 / Realtime transcription WebSocket.

    前端在录音期间连接此端点，接收实时识别结果。 / Frontend connects during recording to receive realtime recognition results.
    通过 ?locale=zh_CN 查询参数传递语言偏好。 / Pass language preference via ?locale=zh_CN query parameter.
    消息格式（下行）： / Message format (downstream):
      {"type": "partial", "text": "...", "speaker_id": N, "speaker_name": "..."}    临时结果 / Partial result
      {"type": "sentence", "text": "原文", "clean_text": "清理版?", "clean_ops": [...], ...}
          定稿句子 / Finalized sentence。text 恒为逐字稿原文；clean_text/clean_ops 为可选
          派生字段（口语清理开启且有变化时存在；清理后为空串表示纯语气词句）。
      {"type": "history", ...}                                                      历史回放，字段同 sentence（clean_text 由回放时派生）
      {"type": "speaker_bound", "speaker_id": N, "speaker_name": "..."}             说话人绑定更新 / Speaker binding update
      {"type": "translation_update", "translations": [...]}                          批量译文推送 / Batch translation push
      {"type": "translation_status", "status": "...", "target_lang": "..."}          翻译状态同步 / Translation status sync
      {"type": "error", "message": "..."}       错误 / Error
      {"type": "ended"}                         转写结束 / Transcription ended

    消息格式（上行）： / Message format (upstream):
      {"type": "heartbeat", ...}                                                     心跳 / Heartbeat
      {"type": "translation_control", "action": "start|stop|set_lang", ...}          翻译控制 / Translation control
    """
    await websocket.accept()
    set_current_locale(locale)

    queue = realtime_queues.get(task_id)
    if not queue:
        await websocket.send_json({"type": "error", "message": _("Task not found or not recording")})
        await websocket.close()
        return

    logger.info(f"[WebSocket] 实时转写连接: task={task_id[:8]}")

    # 回放全量历史句子 / Replay full history sentences
    # 缓存只存原文（AI 对话上下文的事实源）；回放时按当前清理开关派生 clean_text。
    try:
        from app.settings_store import get_transcript_config
        _replay_cleanup = bool(get_transcript_config().get("cleanup", {}).get("enabled", True))
    except Exception:
        _replay_cleanup = True
    history = realtime_full_transcripts.get(task_id, [])
    if history:
        logger.info(f"[WebSocket] 回放历史: task={task_id[:8]}, {len(history)} 条句子")
        for item in history:
            sid = item.get("speaker_id", 0)
            speaker_name = resolve_realtime_speaker_name(task_id, sid) if sid else ""
            history_msg = {
                "type": "history", "text": item.get("text", ""),
                "speaker_id": sid, "speaker_name": speaker_name,
                "begin_time": item.get("begin_time", 0), "end_time": item.get("end_time", 0),
            }
            if _replay_cleanup:
                enrich_sentence(history_msg)
            await websocket.send_json(history_msg)

    # 回放实时总结 / Replay realtime summary
    summarizer = realtime_summarizers.get(task_id)
    if summarizer:
        current_summary = summarizer.get_final_summary()
        if current_summary:
            logger.info(f"[WebSocket] 回放实时总结: task={task_id[:8]}, {len(current_summary)} 字符")
            await websocket.send_json({"type": "summary_update", "content": current_summary})
        if summarizer.is_stopped:
            await websocket.send_json({"type": "summary_status", "status": "stopped"})
        elif summarizer.is_paused:
            await websocket.send_json({"type": "summary_status", "status": "paused", "remaining": summarizer.get_remaining(), "interval": summarizer.interval})
        elif summarizer.is_running:
            await websocket.send_json({"type": "summary_status", "status": "idle", "remaining": summarizer.get_remaining(), "interval": summarizer.interval})

    # 回放实时章节 / Replay realtime chapters
    chapter_gen = realtime_chapter_generators.get(task_id)
    if chapter_gen:
        current_chapters = chapter_gen.get_chapters()
        if current_chapters:
            logger.info(f"[WebSocket] 回放实时章节: task={task_id[:8]}, {len(current_chapters)} 个章节")
            await websocket.send_json({"type": "chapters_update", "chapters": current_chapters})

    # 回放实时翻译（已有翻译结果 + 翻译器状态） / Replay realtime translations (existing results + translator status)
    translations = realtime_translations.get(task_id, [])
    if translations:
        logger.info(f"[WebSocket] 回放实时翻译: task={task_id[:8]}, {len(translations)} 条译文")
        await websocket.send_json({"type": "translation_update", "translations": translations})
    translator = realtime_translators.get(task_id)
    if translator and translator.is_running:
        await websocket.send_json({
            "type": "translation_status",
            "status": "active",
            "target_lang": translator.target_lang,
        })

    # 初始化心跳时间戳 / Initialize heartbeat timestamp
    realtime_last_heartbeat[task_id] = time.time()

    try:
        while True:
            queue_task = asyncio.create_task(queue.get())
            receive_task = asyncio.create_task(websocket.receive_text())

            done, pending = await asyncio.wait(
                {queue_task, receive_task}, timeout=60.0, return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

            if not done:
                logger.info(f"[WebSocket] 超时关闭: task={task_id[:8]}")
                break

            if queue_task in done:
                try:
                    msg = queue_task.result()
                    await websocket.send_json(msg)
                    if msg.get("type") == "ended":
                        break
                except Exception as e:
                    logger.error(f"[WebSocket] 队列消息处理异常: {e}")
                    break

            if receive_task in done:
                try:
                    raw = receive_task.result()
                    data = json.loads(raw)
                    if data.get("type") == "heartbeat":
                        realtime_last_heartbeat[task_id] = time.time()
                        score = data.get("presence_score")
                        if score is not None:
                            realtime_presence_scores[task_id] = float(score)
                        if data.get("user_ack"):
                            realtime_silence_warnings[task_id] = 0
                            logger.info(f"[静默检测] 用户确认继续录制: task={task_id[:8]}")
                    elif data.get("type") == "translation_control":
                        _handle_translation_control(task_id, data, websocket)
                except WebSocketDisconnect:
                    logger.info(f"[WebSocket] 客户端断开: task={task_id[:8]}")
                    break
                except Exception as e:
                    logger.debug(f"[WebSocket] 客户端消息处理异常: {e}")

    except WebSocketDisconnect:
        logger.info(f"[WebSocket] 客户端断开: task={task_id[:8]}")
    except Exception as e:
        logger.error(f"[WebSocket] 异常: {e}")
    finally:
        realtime_last_heartbeat.pop(task_id, None)
        logger.info(f"[WebSocket] 连接结束: task={task_id[:8]}")


# ============================================================
# 翻译控制辅助函数 / Translation Control Helper Functions
# ============================================================


def _handle_translation_control(task_id: str, data: dict, websocket: WebSocket) -> None:
    """处理客户端上行的翻译控制命令。 / Handle client-side translation control commands.

    支持的动作 / Supported actions:
      - start: 创建并启动翻译器（若已存在则切换语言） / Create and start translator (switch lang if exists)
      - stop: 停止并移除翻译器 / Stop and remove translator
      - set_lang: 热切换目标语言 / Hot-switch target language
    """
    action = data.get("action", "")
    logger.info(f"[翻译控制] 收到命令: action={action}, task={task_id[:8]}, data={data}")

    if action == "start":
        target_lang = data.get("target_lang", "en")
        # 若已存在翻译器，先停止 / Stop existing translator if any
        existing = realtime_translators.get(task_id)
        if existing:
            existing.stop()

        def _on_translation(translations: list[dict]) -> None:
            """翻译完成回调：推送译文 + 追加到全量结果 / Translation complete callback: push translations + append to full results"""
            # 追加到全量翻译结果（供 WebSocket 回放） / Append to full translation results (for WebSocket replay)
            all_trans = realtime_translations.setdefault(task_id, [])
            all_trans.extend(translations)
            # 通过 WebSocket 推送给前端 / Push to frontend via WebSocket
            push_realtime_msg(task_id, {
                "type": "translation_update",
                "translations": translations,
            })

        def _on_status(status: str) -> None:
            """翻译状态回调：推送给前端 / Translation status callback: push to frontend"""
            translator = realtime_translators.get(task_id)
            push_realtime_msg(task_id, {
                "type": "translation_status",
                "status": status,
                "target_lang": translator.target_lang if translator else target_lang,
            })

        translator = RealtimeTranslator(
            target_lang=target_lang,
            on_translation=_on_translation,
            on_status=_on_status,
        )
        realtime_translators[task_id] = translator
        translator.start()
        logger.info(f"[WebSocket] 翻译器已启动: task={task_id[:8]}, lang={target_lang}")

    elif action == "stop":
        translator = realtime_translators.pop(task_id, None)
        if translator:
            translator.stop()
            # 保存全量翻译结果到任务（供会后查看） / Save full translation results to task (for post-meeting viewing)
            final_translations = translator.get_all_translations()
            if final_translations:
                realtime_translations[task_id] = final_translations
            logger.info(f"[WebSocket] 翻译器已停止: task={task_id[:8]}, {translator.translation_count} 次翻译")
        push_realtime_msg(task_id, {
            "type": "translation_status",
            "status": "stopped",
            "target_lang": "",
        })

    elif action == "set_lang":
        target_lang = data.get("target_lang", "en")
        translator = realtime_translators.get(task_id)
        if translator and translator.is_running:
            translator.set_target_lang(target_lang)
            logger.info(f"[WebSocket] 翻译目标语言切换: task={task_id[:8]}, lang={target_lang}")
        else:
            logger.warning(f"[WebSocket] 翻译器不存在或未运行，无法切换语言: task={task_id[:8]}")

    else:
        logger.warning(f"[WebSocket] 未知翻译控制动作: {action}")
