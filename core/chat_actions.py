"""
core/chat_actions.py — AI 对话动作检测与执行

作者：王永亮
创建：2026-09-12
版本：1.0.0

职责：
  - 动作定义（ActionDef）与注册表（ACTION_REGISTRY）
  - 基于关键词的动作意图检测（_detect_action）
  - 动作执行引擎（execute_action）：录音控制、会议分析、任务管理、主题配色等

从 app/routers/chat.py 拆分而来。路由层仅保留端点定义与编排逻辑。
"""

import re
import json
import uuid
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime

from app.store import (
    tasks, HOTWORDS_FILE, HOTWORD_MAPPINGS_FILE, SETTINGS_FILE, RECORD_DEVICE,
    RECORDINGS_DIR,
    realtime_queues, realtime_transcribers, realtime_diarizers,
    realtime_summarizers, realtime_speaker_maps,
    push_realtime_msg, resolve_realtime_speaker_name,
    run_pipeline_task, run_stage2_task, save_task_to_disk,
    get_feature_flags,
)
from app.task_store import TASKS_DIR
from core.audio import (
    start_recording_with_stream, stop_recording_with_stream,
    pause_recording_with_stream, resume_recording_with_stream,
    is_stream_recording, get_stream_recording_info,
)
from core.realtime_asr import RealtimeTranscriber
from core.realtime_summary import RealtimeSummarizer
from core.diarization import create_realtime_diarizer
from core import speakers, hotwords

logger = logging.getLogger(__name__)


# ============================================================
# 动作定义
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


def detect_action(message: str) -> ActionDef | None:
    """根据用户消息检测是否包含可执行动作意图。"""
    msg_lower = message.lower()

    # 启发式：删除动词 + "主题" → delete_theme
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


# ============================================================
# 动作执行引擎
# ============================================================


def execute_action(action: ActionDef, task_id: str | None, message: str) -> dict:
    """执行检测到的动作，返回执行结果。

    注意：用 def（非 async def），内部含阻塞操作（录音启动、文件 I/O）。

    Args:
        action: 检测到的动作定义
        task_id: 当前关联的任务 ID（可为 None）
        message: 用户原始消息（用于主题配色推断等）
    """
    try:
        if action.name == "record_start":
            return _exec_record_start()
        elif action.name == "record_stop":
            return _exec_record_stop()
        elif action.name == "record_pause":
            return _exec_record_pause()
        elif action.name == "record_resume":
            return _exec_record_resume()
        elif action.name == "extract_todos":
            return _exec_extract_todos(task_id)
        elif action.name == "summarize_conclusions":
            return _exec_summarize_conclusions(task_id)
        elif action.name == "analyze_speakers":
            return _exec_analyze_speakers(task_id)
        elif action.name == "list_tasks":
            return _exec_list_tasks()
        elif action.name == "get_hotwords":
            return _exec_get_hotwords()
        elif action.name == "get_hotword_mappings":
            return _exec_get_hotword_mappings()
        elif action.name == "get_settings":
            return _exec_get_settings()
        elif action.name == "get_status":
            return _exec_get_status()
        elif action.name == "retranscribe":
            return _exec_retranscribe(task_id)
        elif action.name == "retry_summary":
            return _exec_retry_summary(task_id)
        elif action.name == "create_theme":
            return _exec_create_theme(message)
        elif action.name == "delete_theme":
            return _exec_delete_theme(message)
        else:
            return {"success": False, "message": f"未知动作: {action.name}", "data": None}

    except Exception as e:
        logger.error(f"执行动作 {action.name} 失败: {e}")
        return {"success": False, "message": f"操作失败: {e}", "data": None}


# ── 录音控制 ──

def _exec_record_start() -> dict:
    if is_stream_recording():
        return {"success": False, "message": "当前已在录制中，请先停止当前录音", "data": None}
    task_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    realtime_queues[task_id] = queue
    diarizer = create_realtime_diarizer()
    realtime_diarizers[task_id] = diarizer
    realtime_speaker_maps[task_id] = {}
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

    result = start_recording_with_stream(device=RECORD_DEVICE, output_dir=RECORDINGS_DIR, task_id=task_id, pcm_callback=pcm_callback)
    tasks[task_id] = {"task_id": task_id, "status": "recording", "source": "record", "progress": 0, "message": "正在录制...", "audio_name": "", "audio_path": str(result["output_path"]), "audio_duration": None, "speaker_count": None, "summary": None, "output_path": None, "created_at": datetime.now().isoformat(), "error": None, "speaker_mapping": {}}
    save_task_to_disk(task_id)
    return {"success": True, "message": f"录音已开始，会议 ID: {task_id[:8]}", "data": {"task_id": task_id}}


def _exec_record_stop() -> dict:
    if not is_stream_recording():
        return {"success": False, "message": "当前没有正在进行的录音", "data": None}
    result = stop_recording_with_stream()
    for tid, summ in list(realtime_summarizers.items()):
        summ.stop()
    return {"success": True, "message": f"录音已停止，音频时长 {result.get('duration', 0):.1f} 秒，正在生成纪要...", "data": result}


def _exec_record_pause() -> dict:
    if not is_stream_recording():
        return {"success": False, "message": "当前没有正在进行的录音", "data": None}
    pause_recording_with_stream()
    return {"success": True, "message": "录音已暂停", "data": None}


def _exec_record_resume() -> dict:
    if not is_stream_recording():
        return {"success": False, "message": "当前没有正在进行的录音", "data": None}
    resume_recording_with_stream()
    return {"success": True, "message": "录音已恢复", "data": None}


# ── 会议分析 ──

def _resolve_task_id(task_id: str | None) -> str | None:
    """解析任务 ID：若无效则回退到最近已完成的任务。"""
    if task_id and task_id in tasks:
        return task_id
    completed = [t for t in tasks.values() if t.get("status") == "completed" and t.get("summary")]
    return completed[0]["task_id"] if completed else None


def _exec_extract_todos(task_id: str | None) -> dict:
    tid = _resolve_task_id(task_id)
    if not tid:
        return {"success": False, "message": "暂无已完成的会议，无法提取待办", "data": None}
    task = tasks[tid]
    todos = task.get("todos", [])
    if not todos:
        return {"success": True, "message": f"会议「{task.get('audio_name', '未命名')}」暂无待办事项", "data": {"todos": []}}
    todo_list = "\n".join([f"- [{'x' if t.get('done') else ' '}] {t['text']} ({t.get('assignee', '未分配')})" for t in todos])
    return {"success": True, "message": f"会议「{task.get('audio_name', '未命名')}」共 {len(todos)} 条待办：\n{todo_list}", "data": {"todos": todos}}


def _exec_summarize_conclusions(task_id: str | None) -> dict:
    tid = _resolve_task_id(task_id)
    if not tid:
        return {"success": False, "message": "暂无已完成的会议", "data": None}
    task = tasks[tid]
    summary = task.get("summary", "")
    if not summary:
        return {"success": True, "message": "该会议尚未生成纪要", "data": None}
    return {"success": True, "message": f"会议「{task.get('audio_name', '未命名')}」纪要：\n{summary[:1500]}", "data": {"summary": summary}}


def _exec_analyze_speakers(task_id: str | None) -> dict:
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


# ── 信息查询 ──

def _exec_list_tasks() -> dict:
    task_list = sorted(tasks.values(), key=lambda x: x.get("created_at", ""), reverse=True)[:10]
    if not task_list:
        return {"success": True, "message": "暂无会议记录", "data": {"tasks": []}}
    lines = []
    for t in task_list:
        status_label = {"recording": " 录制中", "pending": " 待处理", "processing": "️ 处理中", "completed": "✅ 已完成", "failed": "❌ 失败"}.get(t.get("status", ""), t.get("status", ""))
        lines.append(f"- {t.get('audio_name', '未命名')} [{status_label}] ({t.get('created_at', '')[:16]})")
    return {"success": True, "message": "最近会议列表：\n" + "\n".join(lines), "data": {"tasks": task_list}}


def _exec_get_hotwords() -> dict:
    words = hotwords.load_hotwords(HOTWORDS_FILE)
    if not words:
        return {"success": True, "message": "当前无热词", "data": {"hotwords": []}}
    return {"success": True, "message": f"当前热词（{len(words)} 个）：\n" + "、".join(words), "data": {"hotwords": words}}


def _exec_get_hotword_mappings() -> dict:
    mappings = hotwords.load_hotword_mappings(HOTWORD_MAPPINGS_FILE)
    if not mappings:
        return {"success": True, "message": "当前无热词映射", "data": {"mappings": []}}
    lines = [f"{k} → {v}" for k, v in mappings]
    return {"success": True, "message": f"当前热词映射（{len(mappings)} 条）：\n" + "\n".join(lines), "data": {"mappings": [{"from": k, "to": v} for k, v in mappings]}}


def _exec_get_settings() -> dict:
    if SETTINGS_FILE.exists():
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    else:
        settings = {"model": "qwen-plus", "output_dir": "data/output/"}
    settings_display = "\n".join([f"- {k}: {v}" for k, v in settings.items() if k != "api_key"])
    return {"success": True, "message": f"当前设置：\n{settings_display}", "data": settings}


def _exec_get_status() -> dict:
    if is_stream_recording():
        info = get_stream_recording_info()
        return {"success": True, "message": f"录制状态：进行中\n设备: {RECORD_DEVICE}\n时长: {info.get('duration', 0):.1f} 秒", "data": info}
    return {"success": True, "message": "当前未在录制", "data": {"recording": False}}


# ── 重新处理 ──

def _exec_retranscribe(task_id: str | None) -> dict:
    if not task_id or task_id not in tasks:
        return {"success": False, "message": "请先选择一个会议，再要求重新解析", "data": None}
    task = tasks[task_id]
    audio_path = task.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        return {"success": False, "message": "录音文件不存在，无法重新识别", "data": None}
    tasks[task_id].update({"status": "processing", "progress": 0, "message": "正在重新识别...", "error": None, "summary": None, "output_path": None, "dialogue": None, "transcription": None, "speaker_mapping": {}, "speaker_uuid_mapping": {}, "title": None})
    save_task_to_disk(task_id)
    audio_name = task.get("audio_name", Path(audio_path).name)
    threading.Thread(target=run_pipeline_task, args=(task_id, Path(audio_path), audio_name, None, None), daemon=True).start()
    logger.info(f"[AI动作-重新识别] task={task_id[:8]}, audio={audio_name}")
    return {"success": True, "message": f"已提交「{task.get('audio_name', '未命名')}」的重新识别任务，正在后台处理中...", "data": {"task_id": task_id}}


def _exec_retry_summary(task_id: str | None) -> dict:
    if not task_id or task_id not in tasks:
        return {"success": False, "message": "请先选择一个会议，再要求重新生成纪要", "data": None}
    task = tasks[task_id]
    if not task.get("dialogue"):
        return {"success": False, "message": "转写结果不存在，请先完成音频识别", "data": None}
    audio_path = task.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        return {"success": False, "message": "录音文件不存在", "data": None}
    tasks[task_id].update({"status": "processing", "progress": 75, "message": "正在重新生成纪要...", "error": None, "summary": None, "output_path": None, "title": None})
    save_task_to_disk(task_id)
    mapping = {int(k): v for k, v in task.get("speaker_uuid_mapping", {}).items()}
    threading.Thread(target=run_stage2_task, args=(task_id, Path(audio_path), mapping), daemon=True).start()
    logger.info(f"[AI动作-重新生成纪要] task={task_id[:8]}")
    return {"success": True, "message": f"已提交「{task.get('audio_name', '未命名')}」的纪要重新生成任务，正在后台处理中...", "data": {"task_id": task_id}}


# ── 主题配色 ──

def _exec_create_theme(message: str) -> dict:
    hue = 255
    if any(k in message for k in ["红", "赤", "火", "红橙"]): hue = 10
    elif any(k in message for k in ["橙", "橘", "珊瑚", "暖"]): hue = 40
    elif any(k in message for k in ["黄", "金", "琥珀"]): hue = 70
    elif any(k in message for k in ["绿", "森林", "草", "翠", "薄荷"]): hue = 145
    elif any(k in message for k in ["青", "碧", "松石"]): hue = 185
    elif any(k in message for k in ["蓝", "海", "天", "靛"]): hue = 230
    elif any(k in message for k in ["紫", "薰衣草", "丁香", "葡萄"]): hue = 280
    elif any(k in message for k in ["粉", "玫", "樱", "桃", "玫瑰"]): hue = 350
    elif any(k in message for k in ["棕", "褐", "咖", "土"]): hue = 50
    chroma = 0.16
    if any(k in message for k in ["鲜艳", "明亮", "饱和", "浓", "亮色"]): chroma = 0.24
    elif any(k in message for k in ["灰", "淡", "素", "低饱和", "莫兰迪", "柔和", "淡雅"]): chroma = 0.08
    lightness = 0.98
    if any(k in message for k in ["深色", "暗黑", "夜间", "暗色", "黑夜", "dark"]): lightness = 0.14
    elif any(k in message for k in ["中灰", "灰色背景"]): lightness = 0.50
    if any(k in message for k in ["赛博", "赛博朋克", "cyberpunk"]): hue, chroma, lightness = 290, 0.28, 0.12
    elif any(k in message for k in ["霓虹", "neon"]): hue, chroma, lightness = 310, 0.30, 0.13
    elif any(k in message for k in ["莫兰迪"]): chroma = 0.06
    elif any(k in message for k in ["暗夜", "暗黑", "哥特"]): hue, chroma, lightness = 260, 0.15, 0.10
    name = "自定义主题"
    quoted = re.search(r'["\u201c]([^"\u201d]+)["\u201d]', message)
    if quoted:
        name = quoted.group(1)
    else:
        for cn in ["红", "橙", "黄", "绿", "青", "蓝", "紫", "粉", "棕", "金", "森林", "海洋", "薰衣草", "玫瑰", "暖阳", "夜色", "薄荷", "珊瑚", "琥珀", "丁香", "葡萄", "樱花", "暗夜", "赛博", "霓虹", "哥特"]:
            if cn in message:
                name = f"自定义·{cn}"
                break
    return {"success": True, "message": f"已为你创建主题「{name}」，可在右上角主题切换中选择。", "data": {"theme_name": name, "accent_hue": hue, "accent_chroma": chroma, "bg_lightness": lightness}}


def _exec_delete_theme(message: str) -> dict:
    target_name = None
    quoted = re.search(r'["\u201c]([^"\u201d]+)["\u201d]', message)
    if quoted:
        target_name = quoted.group(1)
    else:
        for pattern in [r'(?:删除|移除|删掉|去掉|取消)(?:主题[：:]?\s*)["\u201c]?([^"\u201d，,\s]+)', r'(?:删除|移除|删掉|去掉)(?:自定义[·.]?)?(\S{1,10}?)(?:主题|配色|风格|皮肤)']:
            m = re.search(pattern, message)
            if m:
                target_name = m.group(1).strip()
                break
    if not target_name:
        target_name = "__last__"
    return {"success": True, "message": "已删除主题。", "data": {"theme_name": target_name}}
