"""
core/agent_tools/impl.py — 会议域工具实现（唯一来源） / Meeting-domain tool implementations (single source)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-29
版本 / Version: 1.0.0

自 core/agent_loop.py 迁入（工程化能力收敛决策：自建 ReAct 循环退役，CLI 为唯一智能体引擎）：
  - MCP 桥读工具经 app/routers/agent_tools.py 分发到这里的 execute_tool
  - 行为与原 agent_loop 实现逐字节一致，仅模块归属变化

包含：读工具 _tool_* 实现 + execute_tool 分发器 + 工具标签/图标。
"""

import json
import logging

from app.store import tasks
from core import hotwords as hw_module
from core.project_index import get_project_context_for_chat

logger = logging.getLogger(__name__)

# 工具名 → 中文标签（供前端显示） / Tool name → Chinese label for frontend display
TOOL_LABELS = {
    "get_meeting_info": "获取会议信息",
    "get_meeting_transcript": "读取会议转写",
    "get_meeting_todos": "查询待办事项",
    "search_project_files": "搜索项目资料",
    "get_hotwords": "获取热词列表",
    "get_system_settings": "获取系统设置",
    "revise_insight_board": "修订洞察板",
    "revise_insight_board_section": "修订洞察板单节",
}

TOOL_ICONS = {
    "get_meeting_info": "📋",
    "get_meeting_transcript": "💬",
    "get_meeting_todos": "✅",
    "search_project_files": "📂",
    "get_hotwords": "🔤",
    "get_system_settings": "⚙️",
    "revise_insight_board": "🖋️",
    "revise_insight_board_section": "📝",
}


# ============================================================
# 工具执行器 / Tool Executor
# ============================================================


def execute_tool(name: str, arguments: dict, task_id: str | None = None, project_id: str | None = None) -> str:
    """执行工具并返回 JSON 字符串结果 / Execute tool and return JSON string result."""
    try:
        if name == "get_meeting_info":
            return _tool_get_meeting_info(task_id)
        elif name == "get_meeting_transcript":
            return _tool_get_meeting_transcript(task_id, arguments.get("limit", 20))
        elif name == "get_meeting_todos":
            return _tool_get_meeting_todos(task_id)
        elif name == "search_project_files":
            return _tool_search_project_files(project_id, arguments.get("query", ""))
        elif name == "get_hotwords":
            return _tool_get_hotwords()
        elif name == "get_system_settings":
            return _tool_get_system_settings()
        elif name == "revise_insight_board":
            # 洞察共创板（读写双语义）：与 CLI 侧 agent_tools 路由共享唯一实现；task_id 取闭包不信任参数
            from core.insight_board import invoke_revise_board
            return json.dumps(invoke_revise_board(task_id or "", arguments), ensure_ascii=False)
        elif name == "revise_insight_board_section":
            # 单节共创：按 data-ib-id 只替那一节，其余节硬隔离；task_id 取闭包不信任参数
            from core.insight_board import board_html_save_section
            return json.dumps(board_html_save_section(
                task_id or "", str(arguments.get("section_id", "")), str(arguments.get("html", ""))), ensure_ascii=False)
        else:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    except Exception as e:
        logger.error("工具执行失败 [%s]: %s", name, e)
        return json.dumps({"error": f"工具执行失败: {e}"}, ensure_ascii=False)


def _realtime_sentences(task_id: str) -> list[dict]:
    """读取录音进行中的实时转写句子（全量优先，回退最近缓冲）。
    Realtime transcript sentences while recording is in progress (full list first,
    fallback to the capped ring buffer)."""
    from app import realtime_store
    full = realtime_store.realtime_full_transcripts.get(task_id)
    if full:
        return full
    return realtime_store.realtime_transcript_buffers.get(task_id) or []


def _tool_get_meeting_info(task_id: str | None) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    info = {
        "title": task.get("title") or task.get("audio_name") or "未命名会议",
        "status": task.get("status", "未知"),
        "audio_duration_seconds": task.get("audio_duration"),
        "speaker_count": task.get("speaker_count"),
        "created_at": task.get("created_at", ""),
    }
    if task.get("summary"):
        info["summary_preview"] = task["summary"][:300]
    # 录音中 dialogue 尚未交棒，补充实时转写句数，避免工具面谎报"无内容"
    if not (task.get("dialogue") or []):
        rt = _realtime_sentences(task_id)
        if rt:
            info["realtime_sentence_count"] = len(rt)
            info["realtime_note"] = "录音进行中，已产生实时转写，可调用 get_meeting_transcript 获取"
    return json.dumps(info, ensure_ascii=False)


def _tool_get_meeting_transcript(task_id: str | None, limit: int) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    dialogue = task.get("dialogue") or []
    if not dialogue:
        # 会中场景：dialogue 要等停录后管线落盘，录音期间的实时定稿句在内存缓冲里，
        # 不回退就会让 AI 拿到谎报的"暂无转写记录"（2026-09-29 会中问答复盘）。
        rt = _realtime_sentences(task_id)
        if not rt:
            return json.dumps({"info": "该会议暂无转写记录"}, ensure_ascii=False)
        # 会中实名解析：条目自带 speaker_name 优先，回退 task.speaker_mapping（id→名）
        from core.speakers import normalize_speaker_name
        local_map: dict = {}
        for sid, nm in (task.get("speaker_mapping") or {}).items():
            try:
                local_map[int(sid)] = nm
            except (ValueError, TypeError):
                pass
        lines = []
        for entry in rt[-min(max(limit, 1), 50):]:
            text = (entry.get("text") or "").strip()
            if not text:
                continue
            ts_ms = entry.get("begin_time", 0)
            total_sec = int(ts_ms / 1000)
            m, sec = divmod(total_sec, 60)
            h, m = divmod(m, 60)
            ts = f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
            name = ((entry.get("speaker_name") or "").strip()
                    or normalize_speaker_name(local_map.get(entry.get("speaker_id")))
                    or "未识别发言人")
            lines.append(f"[{ts}] {name}: {text}")
        return json.dumps({
            "transcript_lines": lines,
            "total": len(lines),
            "in_progress": True,
            "note": "录音进行中，以上为实时转写原文（尚未落盘为正式 dialogue）",
        }, ensure_ascii=False)

    lines = []
    count = 0
    limit = min(limit, 50)
    for item in dialogue:
        if count >= limit:
            break
        name = item.get("speaker_name") or f"Speaker {item.get('speaker_id', 0) + 1}"
        sents = item.get("sentences") or []
        for s in sents:
            if count >= limit:
                break
            text = s.get("text", "").strip()
            if text:
                ts_ms = s.get("begin_time", 0)
                total_sec = int(ts_ms / 1000)
                m, sec = divmod(total_sec, 60)
                h, m = divmod(m, 60)
                ts = f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
                lines.append(f"[{ts}] {name}: {text}")
                count += 1
        if not sents:
            text = item.get("text", "").strip()
            if text:
                lines.append(f"{name}: {text}")
                count += 1

    return json.dumps({"transcript_lines": lines, "total": count}, ensure_ascii=False)


def _tool_get_meeting_todos(task_id: str | None) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    todos = task.get("todos") or []
    if not todos:
        return json.dumps({"info": "该会议暂无待办事项", "count": 0}, ensure_ascii=False)
    items = []
    for t in todos:
        items.append({
            "text": t.get("text", ""),
            "done": t.get("done", False),
            "assignee": t.get("assignee", "未分配"),
        })
    return json.dumps({"todos": items, "count": len(items)}, ensure_ascii=False)


def _tool_search_project_files(project_id: str | None, query: str) -> str:
    if not project_id:
        return json.dumps({"info": "当前没有关联的项目资料"}, ensure_ascii=False)
    if not query:
        return json.dumps({"info": "请提供搜索关键词"}, ensure_ascii=False)
    context_text, source_files = get_project_context_for_chat(project_id, query)
    if not context_text:
        return json.dumps({"info": f"未找到与「{query}」相关的项目资料", "files_found": 0}, ensure_ascii=False)
    file_names = [f.get("title") or f.get("name", "") for f in source_files]
    return json.dumps({
        "content": context_text[:3000],
        "files_found": len(file_names),
        "file_names": file_names,
    }, ensure_ascii=False)


def _tool_get_hotwords() -> str:
    words = hw_module.load_hotwords()
    if not words:
        return json.dumps({"info": "暂无自定义热词", "count": 0}, ensure_ascii=False)
    return json.dumps({"hotwords": words[:50], "count": len(words)}, ensure_ascii=False)


def _tool_get_system_settings() -> str:
    from app.store import load_settings
    settings = load_settings()
    safe_keys = ["language", "default_model", "theme", "hotwords_enabled"]
    info = {k: settings.get(k) for k in safe_keys if settings.get(k) is not None}
    return json.dumps(info, ensure_ascii=False)
