"""
app/routers/chat.py — AI 对话 + 动作检测/执行 + 注入提取
"""

import re
import json
import uuid
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import (
    tasks, HOTWORDS_FILE, HOTWORD_MAPPINGS_FILE, SETTINGS_FILE, RECORD_DEVICE,
    TASKS_DIR,
    realtime_queues, realtime_transcribers, realtime_diarizers,
    realtime_summarizers, realtime_speaker_maps, realtime_transcript_buffers,
    REALTIME_BUFFER_MAX,
    push_realtime_msg, resolve_realtime_speaker_name,
    run_pipeline_task, run_stage2_task, save_task_to_disk,
    get_feature_flags,
)
from core.audio import (
    start_recording_with_stream, stop_recording_with_stream,
    pause_recording_with_stream, resume_recording_with_stream,
    is_stream_recording, get_stream_recording_info,
)
from core.realtime_asr import RealtimeTranscriber
from core.realtime_summary import RealtimeSummarizer
from core.diarization import create_realtime_diarizer
from core import speakers, projects, hotwords, joblog
from core.llm import async_chat_completion
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# ============================================================
# 动作检测与执行
# ============================================================

class ActionDef:
    """动作定义"""
    def __init__(self, name: str, keywords: list[str], description: str):
        self.name = name
        self.keywords = keywords
        self.description = description


# 可执行动作注册表
# 关键词设计原则：包含短关键词（2-4字）以覆盖用户自然表述的变体
ACTION_REGISTRY: list[ActionDef] = [
    ActionDef("record_start", ["开始录音", "新建录音", "开始录制", "新建会议录音", "录制会议", "start recording", "开始会议", "新建会议", "开始录"], "开始新的会议录音"),
    ActionDef("record_stop", ["停止录音", "结束录音", "停止录制", "结束会议", "stop recording", "停止录", "结束录"], "停止当前录音"),
    ActionDef("record_pause", ["暂停录音", "暂停录制", "pause recording", "暂停"], "暂停当前录音"),
    ActionDef("record_resume", ["继续录音", "恢复录音", "resume recording", "继续录", "恢复录"], "恢复录音"),
    ActionDef("extract_todos", ["提取待办", "待办事项", "todos", "待办", "提取任务"], "从当前会议提取待办事项"),
    ActionDef("summarize_conclusions", ["关键结论", "总结结论", "总结关键决策", "conclusions", "总结关键"], "总结会议关键结论"),
    ActionDef("analyze_speakers", ["发言分析", "发言占比", "说话人分析", "speaker analysis", "发言统计"], "分析各发言人发言情况"),
    ActionDef("list_tasks", ["任务列表", "会议列表", "历史记录", "list tasks", "所有会议", "会议记录"], "列出所有会议任务"),
    ActionDef("get_hotwords", ["热词", "热词列表", "hotwords"], "查看当前热词"),
    ActionDef("get_hotword_mappings", ["热词映射", "映射列表", "hotword mappings", "映射表"], "查看热词映射"),
    ActionDef("get_settings", ["设置", "当前设置", "settings", "系统设置"], "查看系统设置"),
    ActionDef("get_status", ["状态", "录制状态", "当前状态", "status", "查询状态"], "查询当前录制状态"),
    ActionDef("retranscribe", ["重新解析", "重新识别", "重新转写", "重新处理音频", "重新分析音频", "retranscribe", "重新跑一遍", "重新处理", "重新分析", "重新转", "重新识别音频", "重新解析音频", "音频重新", "再转写", "再识别", "再解析", "再处理"], "重新识别当前会议音频"),
    ActionDef("retry_summary", ["重新生成纪要", "重新总结", "重新写纪要", "retry summary", "重新出纪要", "重新生成", "重新写", "重出纪要", "再生成纪要"], "仅重新生成当前会议纪要"),
    ActionDef("create_theme", ["创建主题", "新主题", "自定义主题", "换个主题色", "换个配色", "新建主题", "create theme", "自定义配色", "换个风格", "配色", "风格", "色调", "换色", "换肤", "皮肤", "主题色", "赛博", "莫兰迪", "霓虹"], "创建自定义主题配色"),
    ActionDef("delete_theme", ["删除主题", "移除主题", "删掉主题", "删主题", "去掉主题", "delete theme", "删除配色", "取消主题"], "删除自定义主题"),
]


def _detect_action(message: str) -> ActionDef | None:
    """根据用户消息检测是否包含可执行动作意图。"""
    msg_lower = message.lower()

    # 启发式：删除动词 + "主题" → delete_theme（处理"删掉赛博主题"等中间插入修饰词的情况）
    delete_verbs = ["删除", "删掉", "移除", "去掉", "取消", "删"]
    has_delete = any(v in msg_lower for v in delete_verbs)
    has_theme = "主题" in msg_lower or "配色" in msg_lower or "皮肤" in msg_lower or "风格" in msg_lower
    if has_delete and has_theme:
        for action in ACTION_REGISTRY:
            if action.name == "delete_theme":
                return action

    best_match: ActionDef | None = None
    best_score = 0

    for action in ACTION_REGISTRY:
        for kw in action.keywords:
            if kw.lower() in msg_lower:
                score = len(kw)
                if score > best_score:
                    best_score = score
                    best_match = action

    return best_match


# 作业日志注入意图关键词：仅当问题涉及操作/运行/流程/故障时才加载
# 作业日志上下文（"某些情况"），避免每轮对话都塞入日志噪声。
JOBLOG_INTENT_KEYWORDS = [
    "为什么", "为何", "怎么", "怎样", "如何", "原因", "失败", "出错", "报错",
    "错误", "卡", "没", "没有", "未", "过程", "流程", "发生", "做了", "操作",
    "运行", "日志", "记录", "进度", "状态", "重新", "重跑", "绑定", "声纹",
    "匹配", "解析", "转写", "纪要", "暂停", "恢复", "停止", "导出",
]


def _is_joblog_intent(message: str) -> bool:
    """判断用户问题是否涉及操作/运行/流程/故障，决定是否注入作业日志。"""
    return any(kw in message for kw in JOBLOG_INTENT_KEYWORDS)


def _execute_action(action: ActionDef, data: "ChatRequest") -> dict:
    """执行检测到的动作，返回执行结果。

    注意：用 def（非 async def），内部含阻塞操作（录音启动、文件 I/O）。
    """
    try:
        if action.name == "record_start":
            if is_stream_recording():
                return {"success": False, "message": "当前已在录制中，请先停止当前录音", "data": None}
            task_id = str(uuid.uuid4())
            queue: asyncio.Queue = asyncio.Queue()
            realtime_queues[task_id] = queue
            diarizer = create_realtime_diarizer()
            realtime_diarizers[task_id] = diarizer
            realtime_speaker_maps[task_id] = {}
            # 根据功能开关决定是否启动实时总结
            feature_flags = get_feature_flags()
            summarizer = None
            if feature_flags["realtime_summary"]:
                summarizer = RealtimeSummarizer(
                    on_summary=lambda content: push_realtime_msg(task_id, {"type": "summary_update", "content": content}),
                    on_status=lambda status: push_realtime_msg(task_id, {"type": "summary_status", "status": status}),
                )
                realtime_summarizers[task_id] = summarizer
                summarizer.start()

            transcriber_ref: dict[str, RealtimeTranscriber | None] = {"ref": None}
            _pcm_call_count = 0

            def pcm_callback(audio_data: bytes) -> None:
                nonlocal _pcm_call_count
                _pcm_call_count += 1
                t = transcriber_ref.get("ref")
                if t and t.is_running:
                    t.feed_audio(audio_data)
                diarizer.feed_audio(audio_data)

            def _on_sentence_end(s: dict) -> None:
                if not s.get("text", "").strip():
                    return
                speaker_id = diarizer.get_speaker(begin_time=s.get("begin_time", 0) / 1000.0, end_time=s.get("end_time", 0) / 1000.0)
                speaker_name = resolve_realtime_speaker_name(task_id, speaker_id)
                push_realtime_msg(task_id, {"type": "sentence", "text": s["text"], "begin_time": s.get("begin_time", 0), "end_time": s.get("end_time", 0), "speaker_id": speaker_id, "speaker_name": speaker_name})
                if summarizer:
                    summarizer.feed_sentence({**s, "speaker_name": speaker_name})

            transcriber = RealtimeTranscriber(
                on_partial=lambda text: push_realtime_msg(task_id, {"type": "partial", "text": text, "speaker_id": diarizer.get_speaker(), "speaker_name": resolve_realtime_speaker_name(task_id, diarizer.get_speaker())}),
                on_sentence_end=_on_sentence_end,
                on_error=lambda msg: push_realtime_msg(task_id, {"type": "error", "message": msg}),
                on_complete=lambda: push_realtime_msg(task_id, {"type": "ended"}),
            )

            def _start_transcriber_bg():
                try:
                    transcriber.start()
                    transcriber_ref["ref"] = transcriber
                    realtime_transcribers[task_id] = transcriber
                except Exception as e:
                    logger.warning(f"实时转写启动失败: {e}")
                    transcriber_ref["ref"] = None

            threading.Thread(target=_start_transcriber_bg, daemon=True).start()

            from app.store import RECORDINGS_DIR, save_task_to_disk
            result = start_recording_with_stream(device=RECORD_DEVICE, output_dir=RECORDINGS_DIR, task_id=task_id, pcm_callback=pcm_callback)
            tasks[task_id] = {"task_id": task_id, "status": "recording", "source": "record", "progress": 0, "message": "正在录制...", "audio_name": "", "audio_path": str(result["output_path"]), "audio_duration": None, "speaker_count": None, "summary": None, "output_path": None, "created_at": datetime.now().isoformat(), "error": None, "speaker_mapping": {}}
            save_task_to_disk(task_id)
            return {"success": True, "message": f"录音已开始，会议 ID: {task_id[:8]}", "data": {"task_id": task_id}}

        elif action.name == "record_stop":
            if not is_stream_recording():
                return {"success": False, "message": "当前没有正在进行的录音", "data": None}
            result = stop_recording_with_stream()
            for tid, summ in list(realtime_summarizers.items()):
                summ.stop()
            return {"success": True, "message": f"录音已停止，音频时长 {result.get('duration', 0):.1f} 秒，正在生成纪要...", "data": result}

        elif action.name == "record_pause":
            if not is_stream_recording():
                return {"success": False, "message": "当前没有正在进行的录音", "data": None}
            pause_recording_with_stream()
            return {"success": True, "message": "录音已暂停", "data": None}

        elif action.name == "record_resume":
            if not is_stream_recording():
                return {"success": False, "message": "当前没有正在进行的录音", "data": None}
            resume_recording_with_stream()
            return {"success": True, "message": "录音已恢复", "data": None}

        elif action.name == "extract_todos":
            task_id = data.task_id
            if not task_id or task_id not in tasks:
                completed = [t for t in tasks.values() if t.get("status") == "completed" and t.get("summary")]
                if not completed:
                    return {"success": False, "message": "暂无已完成的会议，无法提取待办", "data": None}
                task_id = completed[0]["task_id"]
            task = tasks[task_id]
            todos = task.get("todos", [])
            if not todos:
                return {"success": True, "message": f"会议「{task.get('audio_name', '未命名')}」暂无待办事项", "data": {"todos": []}}
            todo_list = "\n".join([f"- [{'x' if t.get('done') else ' '}] {t['text']} ({t.get('assignee', '未分配')})" for t in todos])
            return {"success": True, "message": f"会议「{task.get('audio_name', '未命名')}」共 {len(todos)} 条待办：\n{todo_list}", "data": {"todos": todos}}

        elif action.name == "summarize_conclusions":
            task_id = data.task_id
            if not task_id or task_id not in tasks:
                completed = [t for t in tasks.values() if t.get("status") == "completed" and t.get("summary")]
                if not completed:
                    return {"success": False, "message": "暂无已完成的会议", "data": None}
                task_id = completed[0]["task_id"]
            task = tasks[task_id]
            summary = task.get("summary", "")
            if not summary:
                return {"success": True, "message": "该会议尚未生成纪要", "data": None}
            return {"success": True, "message": f"会议「{task.get('audio_name', '未命名')}」纪要：\n{summary[:1500]}", "data": {"summary": summary}}

        elif action.name == "analyze_speakers":
            task_id = data.task_id
            if not task_id or task_id not in tasks:
                return {"success": False, "message": "请先选择或创建一个会议", "data": None}
            task = tasks[task_id]
            dialogue = task.get("dialogue", [])
            if not dialogue:
                return {"success": False, "message": "该会议暂无对话数据", "data": None}
            speaker_stats: dict[str, int] = {}
            for item in dialogue:
                name = item.get("speaker_name", f"说话人{item.get('speaker_id', 0) + 1}")
                text_len = len(item.get("text", ""))
                speaker_stats[name] = speaker_stats.get(name, 0) + text_len
            total = sum(speaker_stats.values()) or 1
            analysis = "\n".join([f"- {name}: {chars} 字 ({chars/total*100:.1f}%)" for name, chars in sorted(speaker_stats.items(), key=lambda x: -x[1])])
            return {"success": True, "message": f"发言分析（共 {len(dialogue)} 条对话）：\n{analysis}", "data": {"speaker_stats": speaker_stats}}

        elif action.name == "list_tasks":
            task_list = sorted(tasks.values(), key=lambda x: x.get("created_at", ""), reverse=True)[:10]
            if not task_list:
                return {"success": True, "message": "暂无会议记录", "data": {"tasks": []}}
            lines = []
            for t in task_list:
                status_label = {"recording": " 录制中", "pending": " 待处理", "processing": "️ 处理中", "completed": "✅ 已完成", "failed": "❌ 失败"}.get(t.get("status", ""), t.get("status", ""))
                lines.append(f"- {t.get('audio_name', '未命名')} [{status_label}] ({t.get('created_at', '')[:16]})")
            return {"success": True, "message": "最近会议列表：\n" + "\n".join(lines), "data": {"tasks": task_list}}

        elif action.name == "get_hotwords":
            words = hotwords.load_hotwords(HOTWORDS_FILE)
            if not words:
                return {"success": True, "message": "当前无热词", "data": {"hotwords": []}}
            return {"success": True, "message": f"当前热词（{len(words)} 个）：\n" + "、".join(words), "data": {"hotwords": words}}

        elif action.name == "get_hotword_mappings":
            mappings = hotwords.load_hotword_mappings(HOTWORD_MAPPINGS_FILE)
            if not mappings:
                return {"success": True, "message": "当前无热词映射", "data": {"mappings": []}}
            lines = [f"{k} → {v}" for k, v in mappings]
            return {"success": True, "message": f"当前热词映射（{len(mappings)} 条）：\n" + "\n".join(lines), "data": {"mappings": [{"from": k, "to": v} for k, v in mappings]}}

        elif action.name == "get_settings":
            if SETTINGS_FILE.exists():
                settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            else:
                settings = {"model": "qwen-plus", "output_dir": "data/output/"}
            settings_display = "\n".join([f"- {k}: {v}" for k, v in settings.items() if k != "api_key"])
            return {"success": True, "message": f"当前设置：\n{settings_display}", "data": settings}

        elif action.name == "get_status":
            if is_stream_recording():
                info = get_stream_recording_info()
                return {"success": True, "message": f"录制状态：进行中\n设备: {RECORD_DEVICE}\n时长: {info.get('duration', 0):.1f} 秒", "data": info}
            return {"success": True, "message": "当前未在录制", "data": {"recording": False}}

        elif action.name == "retranscribe":
            task_id = data.task_id
            if not task_id or task_id not in tasks:
                return {"success": False, "message": "请先选择一个会议，再要求重新解析", "data": None}
            task = tasks[task_id]
            audio_path = task.get("audio_path")
            if not audio_path or not Path(audio_path).exists():
                return {"success": False, "message": "录音文件不存在，无法重新识别", "data": None}
            # 重置任务状态
            tasks[task_id]["status"] = "processing"
            tasks[task_id]["progress"] = 0
            tasks[task_id]["message"] = "正在重新识别..."
            tasks[task_id]["error"] = None
            tasks[task_id]["summary"] = None
            tasks[task_id]["output_path"] = None
            tasks[task_id]["dialogue"] = None
            tasks[task_id]["transcription"] = None
            tasks[task_id]["speaker_mapping"] = {}
            tasks[task_id]["speaker_uuid_mapping"] = {}
            tasks[task_id]["title"] = None
            save_task_to_disk(task_id)
            # 后台线程执行完整管线
            audio_name = task.get("audio_name", Path(audio_path).name)
            threading.Thread(
                target=run_pipeline_task,
                args=(task_id, Path(audio_path), audio_name, None, None),
                daemon=True,
            ).start()
            logger.info(f"[AI动作-重新识别] task={task_id[:8]}, audio={audio_name}")
            return {"success": True, "message": f"已提交「{task.get('audio_name', '未命名')}」的重新识别任务，正在后台处理中...", "data": {"task_id": task_id}}

        elif action.name == "retry_summary":
            task_id = data.task_id
            if not task_id or task_id not in tasks:
                return {"success": False, "message": "请先选择一个会议，再要求重新生成纪要", "data": None}
            task = tasks[task_id]
            if not task.get("dialogue"):
                return {"success": False, "message": "转写结果不存在，请先完成音频识别", "data": None}
            audio_path = task.get("audio_path")
            if not audio_path or not Path(audio_path).exists():
                return {"success": False, "message": "录音文件不存在", "data": None}
            # 重置纪要相关字段
            tasks[task_id]["status"] = "processing"
            tasks[task_id]["progress"] = 75
            tasks[task_id]["message"] = "正在重新生成纪要..."
            tasks[task_id]["error"] = None
            tasks[task_id]["summary"] = None
            tasks[task_id]["output_path"] = None
            tasks[task_id]["title"] = None
            save_task_to_disk(task_id)
            # 恢复说话人映射，后台线程重新生成纪要
            mapping = {int(k): v for k, v in task.get("speaker_uuid_mapping", {}).items()}
            threading.Thread(
                target=run_stage2_task,
                args=(task_id, Path(audio_path), mapping),
                daemon=True,
            ).start()
            logger.info(f"[AI动作-重新生成纪要] task={task_id[:8]}")
            return {"success": True, "message": f"已提交「{task.get('audio_name', '未命名')}」的纪要重新生成任务，正在后台处理中...", "data": {"task_id": task_id}}

        elif action.name == "create_theme":
            # 从用户消息中用关键词确定性推断色彩参数
            msg = data.message
            # 色相推断
            hue = 255  # 默认蓝
            if any(k in msg for k in ["红", "赤", "火", "红橙"]): hue = 10
            elif any(k in msg for k in ["橙", "橘", "珊瑚", "暖"]): hue = 40
            elif any(k in msg for k in ["黄", "金", "琥珀"]): hue = 70
            elif any(k in msg for k in ["绿", "森林", "草", "翠", "薄荷"]): hue = 145
            elif any(k in msg for k in ["青", "碧", "松石"]): hue = 185
            elif any(k in msg for k in ["蓝", "海", "天", "靛"]): hue = 230
            elif any(k in msg for k in ["紫", "薰衣草", "丁香", "葡萄"]): hue = 280
            elif any(k in msg for k in ["粉", "玫", "樱", "桃", "玫瑰"]): hue = 350
            elif any(k in msg for k in ["棕", "褐", "咖", "土"]): hue = 50
            # 彩度推断
            chroma = 0.16
            if any(k in msg for k in ["鲜艳", "明亮", "饱和", "浓", "亮色"]): chroma = 0.24
            elif any(k in msg for k in ["灰", "淡", "素", "低饱和", "莫兰迪", "柔和", "淡雅"]): chroma = 0.08
            # 亮度推断
            lightness = 0.98
            if any(k in msg for k in ["深色", "暗黑", "夜间", "暗色", "黑夜", "dark"]): lightness = 0.14
            elif any(k in msg for k in ["中灰", "灰色背景"]): lightness = 0.50
            # 风格预设：风格关键词覆盖默认色彩参数
            if any(k in msg for k in ["赛博", "赛博朋克", "cyberpunk"]):
                hue, chroma, lightness = 290, 0.28, 0.12
            elif any(k in msg for k in ["霓虹", "neon"]):
                hue, chroma, lightness = 310, 0.30, 0.13
            elif any(k in msg for k in ["莫兰迪"]):
                chroma = 0.06
            elif any(k in msg for k in ["暗夜", "暗黑", "哥特"]):
                hue, chroma, lightness = 260, 0.15, 0.10
            # 主题名称：提取引号中的内容，或用颜色描述
            name = "自定义主题"
            import re as _re
            quoted = _re.search(r'["\u201c]([^"\u201d]+)["\u201d]', msg)
            if quoted:
                name = quoted.group(1)
            else:
                color_names = ["红", "橙", "黄", "绿", "青", "蓝", "紫", "粉", "棕", "金",
                               "森林", "海洋", "薰衣草", "玫瑰", "暖阳", "夜色", "薄荷",
                               "珊瑚", "琥珀", "丁香", "葡萄", "樱花", "暗夜",
                               "赛博", "霓虹", "哥特"]
                for cn in color_names:
                    if cn in msg:
                        name = f"自定义·{cn}"
                        break

            return {
                "success": True,
                "message": f"已为你创建主题「{name}」，可在右上角主题切换中选择。",
                "data": {
                    "theme_name": name,
                    "accent_hue": hue,
                    "accent_chroma": chroma,
                    "bg_lightness": lightness,
                },
            }

        elif action.name == "delete_theme":
            # 从用户消息中提取要删除的主题名称
            msg = data.message
            import re as _re
            target_name = None

            # 尝试提取引号中的主题名
            quoted = _re.search(r'["\u201c]([^"\u201d]+)["\u201d]', msg)
            if quoted:
                target_name = quoted.group(1)
            else:
                # 尝试匹配"删除XX主题"中的XX
                for pattern in [r'(?:删除|移除|删掉|去掉|取消)(?:主题[：:]?\s*)["\u201c]?([^"\u201d，,\s]+)',
                                r'(?:删除|移除|删掉|去掉)(?:自定义[·.]?)?(\S{1,10}?)(?:主题|配色|风格|皮肤)']:
                    m = _re.search(pattern, msg)
                    if m:
                        target_name = m.group(1).strip()
                        break

            # 如果没找到具体名称，标记为"最近的"或"最后一个"
            if not target_name:
                if any(k in msg for k in ["最近", "最新", "最后", "刚创建"]):
                    target_name = "__last__"
                else:
                    target_name = "__last__"

            return {
                "success": True,
                "message": f"已删除主题。",
                "data": {
                    "theme_name": target_name,
                },
            }

        else:
            return {"success": False, "message": f"未知动作: {action.name}", "data": None}

    except Exception as e:
        logger.error(f"执行动作 {action.name} 失败: {e}")
        return {"success": False, "message": f"操作失败: {e}", "data": None}


# ============================================================
# 数据编辑意图：LLM 结构化解析 → 后端执行 → 磁盘回读校验
#
# 设计原则（见 ADR-0008）：AI 无执行权，也无操作结果的单方叙述权。
# 数据修改由 LLM 解析为结构化操作、后端统一执行并回读磁盘校验，
# 回复叙述以校验结果为准，系统事后追加校验结论，杜绝幻觉操作声称。
# ============================================================

# 编辑意图门槛关键词：仅命中消息进入意图解析，避免每轮对话多付一次 LLM 调用
EDIT_INTENT_KEYWORDS = [
    "改为", "改成", "应该是", "应为", "修正", "修改", "更正", "换成", "更新为",
    "重命名", "删除待办", "去掉待办", "标记完成", "标记为", "勾选", "勾上", "改回", "写错", "名字错",
]

# 允许的编辑操作白名单：仅开放待办四类编辑
EDIT_OP_FIELDS = {"todo_assignee": "assignee", "todo_text": "text", "todo_done": "done"}

EDIT_INTENT_SYSTEM_PROMPT = """你是 Open Meeting Scribe 会议助手的意图解析器。唯一任务：判断用户消息是否包含对当前会议待办清单的数据编辑意图，并输出结构化操作。

允许的操作（op 仅限以下四种）：
- todo_assignee：修改待办责任人，value 为新姓名
- todo_text：修改待办内容，value 为新内容
- todo_done：修改待办完成状态，value 为 true 或 false
- todo_delete：删除待办，无需 value

规则：
- todo_id 必须取自给定待办清单中的 id，不得编造
- 用户提到旧姓名/旧值且多条待办命中时，对每条命中的待办各出一条操作
- 无编辑意图、或编辑对象不在待办清单中时，返回空操作
- 只输出 JSON，格式：{"ops": [{"op": "...", "todo_id": "...", "value": "..."}]}"""


def _sanitize_edit_ops(raw: str, valid_ids: set) -> list[dict]:
    """解析 LLM 返回的 JSON，按操作白名单与合法 todo_id 过滤。"""
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        text = m.group(1) if m else text
    start = text.find("{")
    if start < 0:
        return []
    try:
        data = json.loads(text[start:])
    except Exception:
        return []
    ops = data.get("ops") if isinstance(data, dict) else None
    if not isinstance(ops, list):
        return []
    cleaned = []
    for op in ops[:20]:
        if not isinstance(op, dict):
            continue
        name = op.get("op")
        todo_id = op.get("todo_id")
        if name not in EDIT_OP_FIELDS and name != "todo_delete":
            continue
        if todo_id not in valid_ids:
            continue
        if name != "todo_delete" and "value" not in op:
            continue
        cleaned.append({"op": name, "todo_id": todo_id, "value": op.get("value")})
    return cleaned


async def _parse_edit_intent(message: str, task: dict) -> list[dict]:
    """用 LLM 从用户消息解析待办编辑意图，失败返回空列表（降级为普通对话）。"""
    todos = task.get("todos") or []
    if not todos:
        return []
    brief = [
        {"todo_id": t.get("id"), "text": t.get("text", ""), "assignee": t.get("assignee", ""), "done": bool(t.get("done"))}
        for t in todos
    ]
    messages = [
        {"role": "system", "content": EDIT_INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"用户消息：{message}\n\n当前待办清单（JSON）：\n{json.dumps(brief, ensure_ascii=False)}"},
    ]
    try:
        raw = await async_chat_completion(messages, model="qwen-plus", temperature=0.1, max_tokens=512)
    except Exception as e:
        logger.warning(f"编辑意图解析失败（降级为普通对话）: {e}")
        return []
    ops = _sanitize_edit_ops(raw, {t.get("id") for t in todos})
    if ops:
        logger.info(f"[AI对话] 解析到编辑意图: {ops}")
    return ops


def _execute_and_verify_edits(task_id: str, ops: list[dict]) -> list[dict]:
    """执行待办编辑操作，并回读磁盘逐条校验结果。

    注意：用 def（非 async def），内部含文件写/读阻塞操作。
    返回变更记录列表，每条带 verified 标记（磁盘回读确认是否生效）。
    """
    task = tasks.get(task_id)
    if not task:
        return []
    todos = task.setdefault("todos", [])
    changes: list[dict] = []
    for op in ops:
        name, todo_id = op["op"], op["todo_id"]
        if name == "todo_delete":
            target = next((t for t in todos if t.get("id") == todo_id), None)
            if not target:
                continue
            old = target.get("text", "")
            task["todos"] = [t for t in task["todos"] if t.get("id") != todo_id]
            todos = task["todos"]
            changes.append({"op": name, "todo_id": todo_id, "field": "delete", "old": old, "new": None})
        else:
            field = EDIT_OP_FIELDS[name]
            target = next((t for t in todos if t.get("id") == todo_id), None)
            if not target:
                continue
            old = target.get(field)
            new = bool(op.get("value")) if field == "done" else op.get("value")
            if old == new:
                continue
            target[field] = new
            changes.append({"op": name, "todo_id": todo_id, "field": field, "old": old, "new": new})
    if not changes:
        return []
    save_task_to_disk(task_id)
    # 磁盘回读校验：只有回读确认生效的变更才算「被验证的操作结果」
    disk_todos: dict = {}
    try:
        disk = json.loads((TASKS_DIR / f"{task_id}.json").read_text(encoding="utf-8"))
        disk_todos = {t.get("id"): t for t in disk.get("todos", [])}
    except Exception as e:
        logger.error(f"编辑校验失败（磁盘回读异常）: {e}")
    for ch in changes:
        if ch["op"] == "todo_delete":
            ch["verified"] = ch["todo_id"] not in disk_todos
        else:
            dt = disk_todos.get(ch["todo_id"])
            ch["verified"] = dt is not None and dt.get(ch["field"]) == ch["new"]
    return changes


# 回复中的操作声称词：用于事后审计「AI 声称做了操作」
CLAIM_PATTERN = re.compile(r"已(修正|修改|更新|删除|添加|新增|重命名|勾选|替换|更改|改写|同步)")

_FIELD_LABELS = {"assignee": "责任人", "text": "待办内容", "done": "完成状态"}


def _describe_change(ch: dict) -> str:
    """单条变更记录的人类可读描述。"""
    if ch["op"] == "todo_delete":
        return f"删除待办「{ch['old']}」"
    return f"待办{_FIELD_LABELS.get(ch['field'], ch['field'])}「{ch['old']}」→「{ch['new']}」"


def _audit_reply_claims(reply: str, changes: list[dict]) -> str:
    """事后审计 AI 回复中的操作声称，按实际执行结果追加系统校验结论。"""
    if changes:
        lines = [
            f"- {_describe_change(ch)}：{'磁盘回读校验通过' if ch.get('verified') else '校验未通过，请刷新页面核对'}"
            for ch in changes
        ]
        return reply + "\n\n---\n✅ 系统校验（本轮执行结果，磁盘回读确认）：\n" + "\n".join(lines)
    if CLAIM_PATTERN.search(reply):
        logger.warning("[AI对话] 回复含操作声称但系统本轮未执行任何写操作，已追加校验提示")
        return reply + "\n\n---\n⚠️ 系统校验：本轮系统未执行任何数据写操作，上述操作描述与实际状态不符，数据保持不变。"
    return reply


# ============================================================
# 注入内容提取
# ============================================================

def _is_duplicate_todo(content: str, existing_todos: list[dict]) -> bool:
    """检查提取的待办是否已存在于任务待办列表中（模糊匹配）。"""
    content_norm = content.strip()
    for t in existing_todos:
        existing = t.get("text", "").strip()
        # 互相包含即视为重复
        if content_norm in existing or existing in content_norm:
            return True
        # 核心内容重叠度 > 60% 也视为重复
        if len(content_norm) > 10 and len(existing) > 10:
            common = len(set(content_norm) & set(existing))
            union = len(set(content_norm) | set(existing))
            if union > 0 and common / union > 0.6:
                return True
    return False


def _extract_injectable_items(reply: str, existing_todos: list[dict] | None = None) -> list[dict]:
    """从 AI 回复中提取可注入的结构化内容（待办/结论/决策）。
    
    Args:
        reply: AI 回复文本
        existing_todos: 当前任务已有的待办列表，用于去重过滤
    """
    items = []
    existing_todos = existing_todos or []

    # 提取待办（Markdown checkbox 格式）
    todo_pattern = re.compile(r'^\s*-\s*\[\s*\]\s*(.+)$', re.MULTILINE)
    for m in todo_pattern.finditer(reply):
        content = m.group(1).strip()
        if content and len(content) > 4:
            if not _is_duplicate_todo(content, existing_todos):
                items.append({"type": "todo", "content": content})

    # 提取带「待办」「需要」「后续」关键词的列表项
    action_keywords = re.compile(r'^\s*[-•·]\s*(?:.*?(?:待办|需要|后续|跟进|完成|处理|负责|尽快)).*$', re.MULTILINE)
    for m in action_keywords.finditer(reply):
        content = m.group(0).strip().lstrip('-•· ').strip()
        if content and len(content) > 4:
            if not any(i["content"] == content for i in items):
                if not _is_duplicate_todo(content, existing_todos):
                    items.append({"type": "todo", "content": content})

    # 提取结论/决策段落
    conclusion_pattern = re.compile(
        r'(?:^|\n)\s*(?:\d+[.、]|\*\*|•)\s*(?:.*?(?:结论|决定|确认|决策|方案|选择|确定).*)$',
        re.MULTILINE
    )
    for m in conclusion_pattern.finditer(reply):
        content = m.group(0).strip().lstrip('*').strip()
        if content and len(content) > 6:
            item_type = "decision" if any(kw in content for kw in ["决策", "方案", "选择"]) else "conclusion"
            if not any(i["content"] == content for i in items):
                items.append({"type": item_type, "content": content})

    return items


def _build_speaker_name_map(task_id: str) -> dict:
    """构建说话人 ID → 名称映射。"""
    name_map = {}
    task = tasks.get(task_id) if task_id else None

    if task:
        mapping = task.get("speaker_mapping", {})
        for sid, name in mapping.items():
            try:
                name_map[int(sid)] = name
            except (ValueError, TypeError):
                pass

    # 兜底：从全局说话人列表补充
    if not name_map:
        for s in speakers.load_speakers():
            name_map[s.speaker_id] = s.name

    return name_map


def _build_page_context(page: str) -> str | None:
    """根据前端页面构建差异化上下文。

    每个页面注入与该页面场景相关的数据摘要，让 AI 回复更贴合用户当前操作。
    返回格式化文本，或 None（无需注入）。
    """
    if page == "start":
        return (
            "## 当前页面\n"
            "用户在首页，可以开始新录音或上传音频文件。"
            "可用操作：开始录音、上传音频、查看历史会议。"
        )

    if page == "recording":
        # 录音页的上下文已由 task 维度覆盖，仅补充页面提示
        if is_stream_recording():
            return "## 当前页面\n用户正在录音中，可通过对话控制录音（暂停/停止）。"
        return None

    if page == "generating":
        # 纪要页的上下文已由 task 维度充分覆盖
        return None

    if page == "speakers":
        spk_list = speakers.load_speakers()
        if not spk_list:
            return "## 当前页面\n用户在说话人管理页面，当前暂无注册的说话人。"
        lines = [f"- {s.name}" + (f"（{s.role}）" if s.role else "") for s in spk_list[:20]]
        text = "## 当前页面：说话人管理\n当前注册的说话人：\n" + "\n".join(lines)
        if len(spk_list) > 20:
            text += f"\n（共 {len(spk_list)} 人，仅展示前 20 位）"
        return text

    if page == "hotwords":
        hw_list = hotwords.load_hotwords()
        if not hw_list:
            return "## 当前页面\n用户在热词管理页面，当前暂无自定义热词。"
        lines = [f"- {w}" for w in hw_list[:30]]
        text = "## 当前页面：热词管理\n当前热词列表：\n" + "\n".join(lines)
        if len(hw_list) > 30:
            text += f"\n（共 {len(hw_list)} 个，仅展示前 30 个）"
        # 补充热词映射
        mappings = hotwords.load_hotword_mappings()
        if mappings:
            map_lines = [f"- {wrong} → {right}" for wrong, right in mappings[:15]]
            text += "\n\n热词映射（ASR 纠错）：\n" + "\n".join(map_lines)
        return text

    if page == "settings":
        # 注入非敏感设置摘要
        from app.store import load_settings
        settings = load_settings()
        if not settings:
            return "## 当前页面\n用户在系统设置页面，当前使用默认配置。"
        safe_keys = ["language", "default_model", "record_device", "theme", "hotwords_enabled"]
        lines = []
        for k in safe_keys:
            v = settings.get(k)
            if v is not None:
                lines.append(f"- {k}: {v}")
        if lines:
            return "## 当前页面：系统设置\n当前配置：\n" + "\n".join(lines)
        return "## 当前页面\n用户在系统设置页面。"

    if page == "projects":
        proj_list = projects.list_projects()
        if not proj_list:
            return "## 当前页面\n用户在项目管理页面，当前暂无项目。"
        lines = [f"- {p.get('name', '未命名')}（{p.get('file_count', 0)} 个文件）" for p in proj_list[:15]]
        text = "## 当前页面：项目管理\n当前项目列表：\n" + "\n".join(lines)
        if len(proj_list) > 15:
            text += f"\n（共 {len(proj_list)} 个项目）"
        return text

    if page == "library":
        total = len(tasks)
        if total == 0:
            return "## 当前页面\n用户在会议库页面，当前暂无会议记录。"
        # 按状态统计
        status_counts: dict[str, int] = {}
        for t in tasks.values():
            s = t.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
        status_line = "、".join(f"{k}: {v}" for k, v in status_counts.items())
        # 最近 5 个会议
        recent = sorted(tasks.values(), key=lambda t: t.get("created_at", ""), reverse=True)[:5]
        recent_lines = [f"- {t.get('title') or t.get('audio_name') or '未命名'}（{t.get('status', '')}）" for t in recent]
        return (
            f"## 当前页面：会议库\n"
            f"共 {total} 个会议（{status_line}）。\n"
            f"最近会议：\n" + "\n".join(recent_lines)
        )

    return None


# ============================================================
# AI 对话端点
# ============================================================

class ChatRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    history: Optional[list[dict]] = None
    realtime_transcripts: Optional[list[dict]] = None
    mode: Optional[str] = None  # "agent" | "qa"
    model: Optional[str] = None  # 前端选择的模型 ID
    current_page: Optional[str] = None  # 前端当前页面路由名


# AI 对话系统提示词（基于 Anthropic 2026 最佳实践重构）
CHAT_SYSTEM_PROMPT = """<role>
你是 Open Meeting Scribe 的 AI 会议助手，专注于帮助用户高效处理会议录音、生成结构化纪要、并从项目资料中提取关键信息。
</role>

<capabilities>
## 核心能力
1. **会议处理**：录音控制、转写、说话人分离、纪要生成
2. **内容分析**：提取待办、总结结论、分析发言占比
3. **项目问答**：基于用户关联的项目资料文件夹，回答业务问题
4. **动作执行**：系统自动检测用户意图并执行操作（录音、分析、主题等）
5. **数据编辑**：待办修改由系统解析、执行、磁盘回读校验，你只转述结果
</capabilities>

<constraints>
## 操作权限边界（最高优先级）
- 你**没有执行权**：不能修改、删除、写入任何数据
- 操作结果只能引用「系统动作执行结果」块，那是系统验证过的唯一事实
- 若该块不存在或标明失败，禁止使用"已修正/已更新/已删除"等表述
- 不要在回复中复述待办清单或纪要全文（系统界面已展示）

## 已支持的操作（全部已实现，禁止回答"不支持"）
- 录音控制：开始/停止/暂停/恢复录音
- 会议分析：提取待办、总结结论、发言分析
- 任务管理：列出所有会议任务
- 信息查询：热词、热词映射、系统设置、录制状态
- 重新处理：重新识别音频、重新生成纪要
- 主题配色：创建/删除自定义主题

当用户描述命中上述操作时，必须视为操作触发，绝不能回答"暂不支持"。
</constraints>

<output_format>
## 回复规范（第一优先级：简洁）

本系统已承载大量信息（转写全文、结构化纪要、待办清单、项目资料），用户不缺信息，缺的是提炼。

1. **直击要点**：第一句话就是答案或结论，不要铺垫
2. **不复述已知信息**：系统已展示的内容不要重复搬运
3. **不复述动作流程**：系统已执行动作时，只说结果，不说"我已经帮你做了 XX"
4. **不寒不客套**：不用"好的""当然可以""没问题"开头
5. **控制篇幅**：简单问题 1-2 句；列举时用精简列表，每条不超过一行
6. **不解释自身能力**：除非用户问"你能做什么"，否则不主动介绍
</output_format>

<instructions>
## 项目资料回答规范（关键）

当用户询问项目相关问题时，系统会注入相关文件的完整内容（最多 5 个文件，每个最多 2000 字符）。

### 回答步骤
1. **识别问题类型**：
   - "有哪些..." → 列举 + 每项给出具体内容
   - "怎么做..." → 给出步骤/流程
   - "是什么..." → 给出定义 + 关键属性

2. **从文件内容中提取信息**：
   - 不要只说"见 XX 文件"
   - 直接引用文件中的具体内容（定义、字段、流程等）
   - 如果文件中有表格/列表，用````格式````还原

3. **组织回答**：
   - 先给结论（1 句话）
   - 再展开细节（列表/表格）
   - 最后标注来源（📎 文件名）

### 示例对比

❌ 错误回答：
"客商主数据需要治理，来源：/04_数据治理/客商/README.md"

✅ 正确回答：
"客商主数据包括客户和供应商两类，需要治理的内容：
- 客户编码：统一为 10 位数字，前 3 位为区域码
- 供应商资质：需审核营业执照、税务登记证
- 合并规则：同一统一社会信用代码视为同一供应商
📎 客商/README.md"
</instructions>

<examples>
## 其他规范
- 引用项目资料用「📎 文件名」标注来源
- 当前有会议上下文时，优先基于会议内容回答
- 不确定时，诚实说明
</examples>

<context>
## 当前状态
- 软件版本：v1 云方案
- ASR 模型：paraformer-v2
- 纪要模型：qwen-plus
- 系统会注入「当前页面」上下文，据此调整回复的侧重点
"""

# 智能问答模式系统提示词：仅基于上下文回答，不执行任何操作
CHAT_QA_SYSTEM_PROMPT = """<role>
你是 Open Meeting Scribe 的智能问答模式。你的唯一职责是基于当前会议的转写内容、纪要、项目资料等上下文信息回答用户问题。
</role>

<constraints>
## 严格限制
- 你**不能执行任何操作**：不能修改设置、不能编辑纪要、不能控制录音、不能创建主题
- 你**只能基于提供的上下文回答**：包括会议转写、会议纪要、项目资料
- 如果上下文中没有相关信息，诚实告知用户「当前会议资料中未找到相关内容」
- 不要猜测或编造上下文中不存在的信息
- 如果用户要求执行操作（如「帮我修改」「开始录音」），告知用户当前处于智能问答模式，建议切换到智能体模式
</constraints>

<output_format>
## 回复规范
1. 直击要点，不铺垫
2. 引用上下文中的具体内容，标注来源
3. 简单问题 1-2 句；复杂问题用精简列表
4. 不确定时诚实说明
</output_format>
"""

@router.post("/api/chat")
async def chat(data: ChatRequest):
    """AI 对话端点（含动作检测与执行）。"""
    user_message = data.message.strip()
    if not user_message:
        raise HTTPException(400, _("Message cannot be empty"))

    # 根据模式选择系统提示词
    is_qa_mode = data.mode == "qa"
    system_prompt = CHAT_QA_SYSTEM_PROMPT if is_qa_mode else CHAT_SYSTEM_PROMPT
    context_blocks = []
    action_result: dict | None = None

    # 确定使用的模型（前端选择 > 设置中的默认模型）
    chat_model = data.model or "qwen-plus"

    # ─ 步骤 0: 数据编辑意图（仅智能体模式；QA 模式跳过所有操作）──
    edit_changes: list[dict] = []
    edit_turn = False
    if not is_qa_mode and data.task_id and data.task_id in tasks and any(kw in user_message for kw in EDIT_INTENT_KEYWORDS):
        ops = await _parse_edit_intent(user_message, tasks[data.task_id])
        if ops:
            edit_turn = True
            edit_changes = await asyncio.to_thread(_execute_and_verify_edits, data.task_id, ops)
            if edit_changes:
                result_text = "\n".join(
                    f"- {_describe_change(ch)}：{'校验通过' if ch.get('verified') else '校验未通过'}"
                    for ch in edit_changes
                )
            else:
                result_text = "未产生实际变更（当前状态已符合用户要求）"
            context_blocks.append(
                "## 系统动作执行结果（已验证，唯一事实）\n"
                f"系统已执行待办编辑并磁盘回读校验：\n{result_text}\n"
                "回复中的操作结果只能引用以上内容，不得声称其他变更。"
            )
            joblog.append_event(
                data.task_id, joblog.STAGE_CHAT_ACTION,
                f"会议助手执行待办编辑: {len(edit_changes)} 项变更（校验通过 {sum(1 for c in edit_changes if c.get('verified'))}）",
                level="info" if edit_changes else "warn",
            )

    # ─ 步骤 1: 关键词动作检测与执行（编辑轮/QA 模式跳过，避免重复动作）──
    detected_action = None if (edit_turn or is_qa_mode) else _detect_action(user_message)
    if detected_action:
        logger.info(f"[AI对话] 检测到动作意图: {detected_action.name} (关键词匹配)")
        action_result = _execute_action(detected_action, data)
        if action_result:
            status = "成功" if action_result.get("success") else "失败"
            context_blocks.append(
                f"## 系统动作执行结果\n"
                f"动作: {detected_action.description}\n"
                f"状态: {status}\n"
                f"结果: {action_result.get('message', '无')}"
            )
            # 作业日志：记录会议助手执行过的动作（从属于该会议）
            tid = (action_result.get("data") or {}).get("task_id") or data.task_id
            if tid:
                joblog.append_event(
                    tid, joblog.STAGE_CHAT_ACTION,
                    f"会议助手执行动作 {detected_action.name}: {status} — {action_result.get('message', '')}",
                    level="info" if action_result.get("success") else "error",
                )

    # ── 维度 1: 实时转写流 ───
    realtime_entries = []

    if data.realtime_transcripts:
        realtime_entries = data.realtime_transcripts[-REALTIME_BUFFER_MAX:]
    elif data.task_id and data.task_id in realtime_transcript_buffers:
        realtime_entries = realtime_transcript_buffers[data.task_id]

    if realtime_entries:
        speaker_name_map = _build_speaker_name_map(data.task_id) if data.task_id else {}
        lines = []
        for entry in realtime_entries[-10:]:
            sid = entry.get("speaker_id")
            name = speaker_name_map.get(sid, f"发言人{sid + 1}" if sid else "未知")
            text = entry.get("text", "").strip()
            if text:
                lines.append(f"{name}：{text}")
        if lines:
            context_blocks.append(
                "## 实时会议对话（最近发言）\n" + "\n".join(lines)
            )

    # ── 维度 2: 当前会议上下文（元信息 + 纪要/对话）──
    if data.task_id and data.task_id in tasks:
        task = tasks[data.task_id]

        # 始终注入会议元信息（标题、时长、说话人、状态、音频路径等）
        meta_lines = [
            f"- 会议标题：{task.get('title') or task.get('audio_name') or '未命名'}",
            f"- 会议状态：{task.get('status', '未知')}",
        ]
        if task.get("audio_duration"):
            dur = task["audio_duration"]
            meta_lines.append(f"- 音频时长：{int(dur // 60)} 分 {int(dur % 60)} 秒")
        if task.get("speaker_count"):
            meta_lines.append(f"- 说话人数量：{task['speaker_count']}")
        audio_path = task.get("audio_path", "")
        if audio_path and Path(audio_path).exists():
            meta_lines.append(f"- 音频文件：{Path(audio_path).name}（已存在）")
        elif audio_path:
            meta_lines.append(f"- 音频文件：{Path(audio_path).name}（路径记录但文件不存在）")
        if task.get("error"):
            meta_lines.append(f"- 错误信息：{task['error']}")
        context_blocks.append("## 当前会议信息\n" + "\n".join(meta_lines))

        # 纪要 / 对话片段（按需注入）
        # 若 summary 是生成失败的错误信息（如"对话内容过短"），视为无纪要，回退到对话注入
        summary = task.get("summary") or ""
        is_summary_error = "内容过短" in summary or "无法生成有效纪要" in summary
        if summary and not is_summary_error:
            context_blocks.append(
                f"## 当前会议纪要\n{summary[:2000]}"
            )
        elif task.get("dialogue") and not realtime_entries:
            # 回退：展开 sentences 字段注入对话（dialogue 按说话人分组，需展开）
            dialogue_lines = []
            for item in task["dialogue"]:
                name = item.get("speaker_name", f"说话人{item.get('speaker_id', 0) + 1}")
                sents = item.get("sentences") or []
                for s in sents:
                    text = s.get("text", "").strip()
                    if text:
                        dialogue_lines.append(f"{name}：{text}")
                # 兜底：若无 sentences 字段，用顶层 text
                if not sents:
                    text = item.get("text", "").strip()
                    if text:
                        dialogue_lines.append(f"{name}：{text}")
            dialogue_text = "\n".join(dialogue_lines)
            if dialogue_text:
                context_blocks.append(
                    f"## 当前会议对话\n{dialogue_text[:3000]}"
                )

        # 待办事项（始终注入，便于 LLM 回答结论/待办相关问题）
        todos = task.get("todos") or []
        if todos:
            todo_lines = []
            for t in todos:
                status = "✅" if t.get("done") else "⬜"
                assignee = t.get("assignee", "未分配")
                todo_lines.append(f"- [{status}] {t.get('text', '')}（责任人：{assignee}）")
            context_blocks.append("## 当前会议待办事项\n" + "\n".join(todo_lines))

        # ── 维度 2.5: 作业日志（渐进式：概要常驻 + 按需明细；仅操作类意图注入）──
        if _is_joblog_intent(user_message):
            joblog_ctx = joblog.build_context(data.task_id, user_message)
            if joblog_ctx:
                context_blocks.append(joblog_ctx)

    # ── 维度 3: 关联项目资料（优先前端传入，兜底从 task 读取）──
    source_files = []
    resolved_project_id = data.project_id
    if not resolved_project_id and data.task_id and data.task_id in tasks:
        resolved_project_id = tasks[data.task_id].get("project_id")
    if resolved_project_id:
        context_text, source_files = projects.get_project_context_for_chat(
            resolved_project_id, user_message
        )
        if context_text:
            context_blocks.append(context_text)

    # ── 维度 5: 页面上下文（根据前端当前页面注入差异化数据）──
    if data.current_page:
        page_ctx = _build_page_context(data.current_page)
        if page_ctx:
            context_blocks.append(page_ctx)

    # 拼接所有上下文块到系统提示词末尾
    if context_blocks:
        system_prompt += "\n\n" + "\n\n---\n\n".join(context_blocks)

    # 注入内容审计日志：记录每轮注入了哪些块及其长度，便于排查 LLM 幻觉来源
    logger.info(
        "[AI对话] 注入块 task=%s mode=%s blocks=%d 详情=%s",
        data.task_id,
        data.mode,
        len(context_blocks),
        [
            {"head": b[:120].replace("\n", " "), "len": len(b)}
            for b in context_blocks
        ],
    )

    # ── 维度 4: 对话历史 ──
    messages = [{"role": "system", "content": system_prompt}]

    if data.history:
        recent = data.history[-10:]
        for msg in recent:
            role = "user" if msg.get("role") == "user" else "assistant"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    # 调用 LLM（异步，不阻塞事件循环）
    try:
        reply = await async_chat_completion(messages, model=chat_model, max_tokens=2048)
        # 事后审计：回复中的操作声称必须与系统实际执行结果一致
        reply = _audit_reply_claims(reply, edit_changes)
        # 编辑轮的回复不是新注入内容来源，避免把改写后的待办再当新待办注入
        existing_todos = tasks.get(data.task_id, {}).get("todos", []) if data.task_id else []
        extracted_items = [] if edit_changes else _extract_injectable_items(reply, existing_todos)
        return {
            "reply": reply,
            "sources": source_files,
            "extracted_items": extracted_items,
            "verified_changes": edit_changes,
            "action": {
                "name": detected_action.name if detected_action else None,
                "success": action_result.get("success") if action_result else None,
                "data": action_result.get("data") if action_result else None,
            } if detected_action else None,
        }
    except Exception as e:
        logger.error("AI 对话失败: %s", e)
        raise HTTPException(500, _("AI conversation failed: {err}").format(err=e))


# ============================================================
# 文稿优化端点
# ============================================================

OPTIMIZE_SYSTEM_PROMPT = """你是一位专业的中文文稿润色助手。请对用户提供的文本进行优化，遵循以下原则：

1. **保持原意**：不改变原文的核心意思和观点
2. **语言流畅**：修正语病、消除冗余、改善句式结构
3. **逻辑清晰**：确保论述有条理，段落衔接自然
4. **用词准确**：替换模糊或不当的措辞
5. **格式规范**：修正标点符号、数字格式等细节

规则：
- 直接输出优化后的文本，不要添加解释或说明
- 如果原文已经是高质量的，保持原文不变
- 保留原文的段落结构
- 如果原文包含代码、公式等专业内容，保持原样"""


class OptimizeRequest(BaseModel):
    text: str
    model: Optional[str] = None


@router.post("/api/optimize")
async def optimize_text(data: OptimizeRequest):
    """文稿优化端点：调用 LLM 对文本进行润色优化。"""
    text = data.text.strip()
    if not text:
        raise HTTPException(400, _("Text cannot be empty"))

    model = data.model or "qwen-plus"
    messages = [
        {"role": "system", "content": OPTIMIZE_SYSTEM_PROMPT},
        {"role": "user", "content": f"请优化以下文本：\n\n{text}"},
    ]

    try:
        optimized = await async_chat_completion(messages, model=model, max_tokens=4096, temperature=0.3)
        return {"ok": True, "original": text, "optimized": optimized.strip()}
    except Exception as e:
        logger.error("文稿优化失败: %s", e)
        raise HTTPException(500, _("Text refinement failed: {err}").format(err=e))


# ============================================================
# 可用模型列表
# ============================================================

# DashScope 支持的模型列表（2025 年常用）
DASHSCOPE_MODELS = [
    {"id": "qwen-plus", "name": "Qwen3.7-Plus", "provider": "DashScope"},
    {"id": "qwen-max", "name": "Qwen3.7-Max", "provider": "DashScope"},
    {"id": "qwen-turbo", "name": "Qwen3.7-Turbo", "provider": "DashScope"},
    {"id": "qwen-long", "name": "Qwen-Long", "provider": "DashScope"},
    {"id": "qwen2.5-72b-instruct", "name": "Qwen2.5-72B", "provider": "DashScope"},
    {"id": "qwen2.5-32b-instruct", "name": "Qwen2.5-32B", "provider": "DashScope"},
]

# 其他 Provider 常用模型
OTHER_MODELS = [
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI"},
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "provider": "Anthropic"},
    {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "DeepSeek"},
    {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner", "provider": "DeepSeek"},
]


@router.get("/api/models")
async def list_models():
    """获取可用模型列表（供前端模型选择器使用）。"""
    return {
        "models": DASHSCOPE_MODELS + OTHER_MODELS,
        "dashscope_models": DASHSCOPE_MODELS,
    }
