"""
core/agent_tools/impl.py — 会议域工具实现（唯一来源） / Meeting-domain tool implementations (single source)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-29
更新 / Updated: 2026-09-30
版本 / Version: 1.1.0

自 core/agent_loop.py 迁入（工程化能力收敛决策：自建 ReAct 循环退役，CLI 为唯一智能体引擎）：
  - MCP 桥读工具经 app/routers/agent_tools.py 分发到这里的 execute_tool
  - 行为与原 agent_loop 实现逐字节一致，仅模块归属变化

包含：读工具 _tool_* 实现 + execute_tool 分发器 + 工具标签/图标。
"""

import json
import logging
import re
import socket
import time
from html import unescape as _html_unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import requests as http_requests  # 统一重命名，避免 _tool_web_fetch 内 import 重名冲突

from core import hotwords as hw_module
from core.chat_context import task_final_summary, task_notes
from core.decision_flow import status_of
from core.decision_status import load_statuses
from core.project_index import get_project_context_for_chat
from core.task_store import tasks

logger = logging.getLogger(__name__)

# 随记读工具正文上限（字符）：用户手写区，超长截断并标注
_NOTES_MAX_CHARS = 6000
# 任意会议详情的纪要/随记正文上限（字符）与附带转写句数上限
_DETAIL_TEXT_MAX = 3000
_DETAIL_TRANSCRIPT_MAX = 50

# 工具名 → 中文标签（供前端显示） / Tool name → Chinese label for frontend display
TOOL_LABELS = {
    "get_meeting_info": "获取会议信息",
    "get_meeting_transcript": "读取会议转写",
    "get_meeting_notes": "读取会议随记",
    "get_meeting_decisions": "查询决策事项",
    "search_meetings": "跨会议检索",
    "get_meeting_detail": "读取会议详情",
    "search_project_files": "搜索项目资料",
    "get_hotwords": "获取热词列表",
    "get_system_settings": "获取系统设置",
    "update_decision_node": "改写决策节点",
    "delete_decision_node": "删除决策节点",
    "propose_notes": "提出随记改写建议",
    "propose_summary": "提出纪要改写建议",
    "revise_insight_board": "修订洞察板",
    "revise_insight_board_section": "修订洞察板单节",
    "list_insight_boards": "查看洞察板清单",
    "create_insight_board": "提议新建洞察板",
    "web_search": "联网搜索",
    "web_fetch": "网页抓取",
}

TOOL_ICONS = {
    "get_meeting_info": "📋",
    "get_meeting_transcript": "💬",
    "get_meeting_notes": "📝",
    "get_meeting_decisions": "✅",
    "search_meetings": "🗂️",
    "get_meeting_detail": "📄",
    "search_project_files": "📂",
    "get_hotwords": "🔤",
    "get_system_settings": "⚙️",
    "update_decision_node": "✏️",
    "delete_decision_node": "🗑️",
    "propose_notes": "🗒️",
    "propose_summary": "📝",
    "revise_insight_board": "🖋️",
    "revise_insight_board_section": "📝",
    "list_insight_boards": "📚",
    "create_insight_board": "➕",
    "web_search": "🔍",
    "web_fetch": "🌐",
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
        elif name == "get_meeting_notes":
            return _tool_get_meeting_notes(task_id)
        elif name == "get_meeting_decisions":
            return _tool_get_meeting_decisions(task_id)
        elif name == "search_meetings":
            # 跨会议清单：不吃 task_id 闭包，任何页面/会话都能用
            return _tool_search_meetings(arguments)
        elif name == "get_meeting_detail":
            # 任意会议详情：只读下钻入口，写工具仍锁当前会议
            return _tool_get_meeting_detail(
                str(arguments.get("task_id") or ""),
                arguments.get("transcript_limit", 0))
        elif name == "search_project_files":
            return _tool_search_project_files(project_id, arguments.get("query", ""))
        elif name == "get_hotwords":
            return _tool_get_hotwords()
        elif name == "search_memory":
            return _tool_search_memory(task_id, project_id, arguments)
        elif name == "web_search":
            return _tool_web_search(arguments.get("query", ""))
        elif name == "web_fetch":
            return _tool_web_fetch(arguments.get("url", ""))
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
                task_id or "", str(arguments.get("section_id", "")), str(arguments.get("html", "")),
                (str(arguments.get("board_id") or "").strip() or None)), ensure_ascii=False)
        elif name == "list_insight_boards":
            # 板清单（只读）：多板下先看清全景再选目标，避免盲写默认板
            from core.insight_board import boards_manifest
            return json.dumps(boards_manifest(task_id or ""), ensure_ascii=False)
        elif name == "create_insight_board":
            # 建板提案（不落盘）：与 propose_summary/propose_notes 同构——
            # 执行权在用户（前端确认卡 → POST .../boards），工具只产出建议。
            from core.insight_board import BOARD_TITLE_MAX, boards_manifest
            title = str(arguments.get("title") or "").strip()[:BOARD_TITLE_MAX]
            if not title:
                return json.dumps({"error": "title_required",
                                    "info": "新板标题必填"}, ensure_ascii=False)
            return json.dumps({
                "proposed": True, "title": title,
                "board_id": str(arguments.get("board_id") or "").strip(),
                "reason": str(arguments.get("reason") or ""),
                "boards": [b["board_id"] for b in boards_manifest(task_id or "")["boards"]],
                "note": "已作为待确认建板提案展示给用户，未经用户点「接受」不会新建任何板",
            }, ensure_ascii=False)
        else:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    except Exception as e:
        logger.error("工具执行失败 [%s]: %s", name, e)
        return json.dumps({"error": f"工具执行失败: {e}"}, ensure_ascii=False)


def _realtime_sentences(task_id: str) -> list[dict]:
    """读取录音进行中的实时转写句子（全量优先，回退最近缓冲）。
    Realtime transcript sentences while recording is in progress (full list first,
    fallback to the capped ring buffer)."""
    from core import realtime_store
    full = realtime_store.realtime_full_transcripts.get(task_id)
    if full:
        return full
    return realtime_store.realtime_transcript_buffers.get(task_id) or []


def _tool_get_meeting_info(task_id: str | None) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    # roster：已绑定姓名 + 手工录入名单 + 统计
    from core.speakers import normalize_speaker_mapping
    _map = normalize_speaker_mapping(task.get("speaker_mapping"))
    bound_names = [name for name in _map.values() if name]
    manual_roster = [str(n).strip() for n in (task.get("roster") or []) if str(n).strip()]
    # 合并去重（bound 优先保留顺序，manual 补充 bound 没有的）
    seen: set[str] = set()
    all_names: list[str] = []
    for name in bound_names + manual_roster:
        if name not in seen:
            seen.add(name)
            all_names.append(name)
    total_ids: set = set()
    for item in task.get("dialogue") or []:
        if isinstance(item, dict) and item.get("speaker_id") is not None:
            total_ids.add(str(item.get("speaker_id")))
    total_speaker_count = len(total_ids) if total_ids else len(_map)
    info = {
        "title": task.get("title") or task.get("audio_name") or "未命名会议",
        "status": task.get("status", "未知"),
        "audio_duration_seconds": task.get("audio_duration"),
        "roster": {
            "bound": bound_names,
            "manual": manual_roster,
            "all": all_names,
            "bound_count": len(bound_names),
            "manual_count": len(manual_roster),
            "total_speaker_count": total_speaker_count,
            "unbounded_count": max(0, total_speaker_count - len(bound_names)),
        },
        "created_at": task.get("created_at", ""),
    }
    # 纪要预览取定稿口径（与前端纪要 Tab 同源）：只读 AI 产物会让改写基线落在用户手改之前
    summary = task_final_summary(task).strip()
    if summary:
        info["summary_preview"] = summary[:300]
    # 随记：用户手写区，不告知存在性就等于不存在（2026-09-30 复盘）
    notes = task_notes(task)
    if notes:
        info["has_notes"] = True
        info["notes_preview"] = notes[:300]
        info["notes_note"] = "随记为用户手写原文，需全文调 get_meeting_notes；按随记更新纪要/决策时以随记为准"
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


def _tool_get_meeting_notes(task_id: str | None) -> str:
    """读取用户手写的会议随记（user_notes）。
    随记是用户原创区：本工具只读，任何改写须经用户在前端确认，不经工具落盘。"""
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    notes = task_notes(tasks[task_id])
    if not notes:
        return json.dumps({"info": "该会议暂无随记内容", "notes": "", "characters": 0},
                          ensure_ascii=False)
    out = {"notes": notes[:_NOTES_MAX_CHARS], "characters": len(notes),
           "note": "以下为用户录音期间手写的随记原文（非 AI 产物），可信度高于转写推断"}
    if len(notes) > _NOTES_MAX_CHARS:
        out["truncated"] = True
    return json.dumps(out, ensure_ascii=False)


def _tool_get_meeting_decisions(task_id: str | None) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    decisions = task.get("decisions") or []
    if not decisions:
        return json.dumps({"info": "该会议暂无决策事项", "count": 0}, ensure_ascii=False)
    items = []
    for t in decisions:
        if not isinstance(t, dict):
            continue
        items.append({
            # 节点稳定 id：供按节点寻址改写/删除（PROPOSAL-AGENT-REWRITE-CHANNEL §9 前置项）
            "id": t.get("id", ""),
            "text": t.get("text", ""),
            "title": t.get("title", ""),
            "status": status_of(t),
            "done": t.get("done", False),
            "assignee": t.get("assignee", "未分配"),
        })
    # 状态字典随列表下发：否则模型只能猜 status id（update_decision_node 会 422）
    try:
        statuses = [{"id": s["id"], "name": s["name"], "closing": bool(s.get("closing"))}
                    for s in load_statuses()]
    except Exception:  # noqa: BLE001 - 字典不可用不影响节点读取
        statuses = []
    return json.dumps({"decisions": items, "count": len(items),
                       "available_statuses": statuses,
                       "status_note": "改写状态时 status 只能取 available_statuses 中的 id；"
                                      "用户已拍板的决策应推进到 closing=true 的状态"},
                      ensure_ascii=False)


def _tool_search_memory(task_id: str | None, project_id: str | None, arguments: dict) -> str:
    """检索长期记忆（跨会话）。作用域链 task → space → global。"""
    from core.agent_memory import retrieve, schema

    query = str(arguments.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "empty_query", "message": "检索词不能为空"},
                          ensure_ascii=False)
    try:
        top_k = int(arguments.get("top_k") or 8)
    except (TypeError, ValueError):
        top_k = 8
    chain = schema.namespace_chain(task_id, project_id, None)
    hits = retrieve.search(query, chain, top_k=top_k, touch=False)
    return json.dumps({
        "query": query,
        "returned": len(hits),
        "items": [
            {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "text": item.get("text"),
                "subject": item.get("subject"),
                "relation": item.get("relation"),
                "object": item.get("object"),
                "valid_from": item.get("valid_from"),
                "valid_to": item.get("valid_to"),
                "source_task_id": (item.get("source") or {}).get("task_id"),
                "score": item.get("_score"),
            }
            for item in hits
        ],
    }, ensure_ascii=False)


def _tool_search_meetings(arguments: dict) -> str:
    """跨全部会议薄清单检索（分页）。不依赖当前会话 task 绑定。"""
    from core.meeting_search import search_meeting_list

    query = str(arguments.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "empty_query", "message": "检索词不能为空"},
                          ensure_ascii=False)
    try:
        limit = int(arguments.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = int(arguments.get("offset") or 0)
    except (TypeError, ValueError):
        offset = 0
    return json.dumps(search_meeting_list(query, limit=limit, offset=offset),
                      ensure_ascii=False)


def _tool_get_meeting_detail(task_id: str, transcript_limit: object = 0) -> str:
    """按 task_id 读取任意一场会议的详情（只读）。写操作不在此通道。"""
    tid = str(task_id or "").strip()
    if not tid:
        return json.dumps({"error": "task_id_required", "message": "必须提供会议的 task_id"},
                          ensure_ascii=False)
    task = tasks.get(tid)
    if not isinstance(task, dict):
        return json.dumps({"error": "task_not_found", "message": f"没有找到会议 {tid}"},
                          ensure_ascii=False)
    if (task.get("deleted") or task.get("trashed") or task.get("is_trash")
            or task.get("deleted_at") or task.get("trashed_at")):
        return json.dumps({"error": "task_deleted", "message": "该会议已删除，不提供内容"},
                          ensure_ascii=False)

    summary = task_final_summary(task).strip()
    notes = task_notes(task).strip()
    decisions = []
    for node in task.get("decisions") or []:
        if not isinstance(node, dict):
            continue
        superseded = node.get("superseded_by")
        decisions.append({
            "id": node.get("id", ""),
            "title": node.get("title", ""),
            "text": node.get("text", ""),
            "status": status_of(node),
            "superseded_by": superseded if isinstance(superseded, dict) else None,
        })

    # roster：已绑定姓名 + 手工录入名单 + 总说话人数（从 dialogue 去重 speaker_id 现算）
    from core.speakers import normalize_speaker_mapping
    _map = normalize_speaker_mapping(task.get("speaker_mapping"))
    bound_names = [name for name in _map.values() if name]
    manual_roster = [str(n).strip() for n in (task.get("roster") or []) if str(n).strip()]
    seen: set[str] = set()
    all_names: list[str] = []
    for name in bound_names + manual_roster:
        if name not in seen:
            seen.add(name)
            all_names.append(name)
    # 从 dialogue 算总 speaker_id 数
    total_ids: set = set()
    for item in task.get("dialogue") or []:
        if isinstance(item, dict) and item.get("speaker_id") is not None:
            total_ids.add(str(item.get("speaker_id")))
    total_speaker_count = len(total_ids) if total_ids else len(_map)

    out = {
        "task_id": tid,
        "title": task.get("title") or task.get("audio_name") or "未命名会议",
        "date": str(task.get("meeting_date") or task.get("created_at") or "")[:10],
        "project_id": task.get("project_id") or "",
        "summary": summary[:_DETAIL_TEXT_MAX],
        "summary_truncated": len(summary) > _DETAIL_TEXT_MAX,
        "decisions": decisions,
        "decision_count": len(decisions),
        "notes": notes[:_DETAIL_TEXT_MAX],
        "notes_truncated": len(notes) > _DETAIL_TEXT_MAX,
        "roster": {
            "bound": bound_names,
            "manual": manual_roster,
            "all": all_names,
            "bound_count": len(bound_names),
            "manual_count": len(manual_roster),
            "total_speaker_count": total_speaker_count,
            "unbounded_count": max(0, total_speaker_count - len(bound_names)),
        },
    }
    try:
        limit = max(0, min(int(transcript_limit or 0), _DETAIL_TRANSCRIPT_MAX))
    except (TypeError, ValueError):
        limit = 0
    if limit:
        witness = json.loads(_tool_get_meeting_transcript(tid, limit))
        out["transcript_lines"] = witness.get("transcript_lines") or []
    return json.dumps(out, ensure_ascii=False)


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
    from core.settings_store import load_settings
    settings = load_settings()
    safe_keys = ["language", "default_model", "theme", "hotwords_enabled"]
    info = {k: settings.get(k) for k in safe_keys if settings.get(k) is not None}
    return json.dumps(info, ensure_ascii=False)


# ============================================================
# 联网工具 / Web tools
# ============================================================

# SSRF 防护：禁掉的内网/保留网段前缀（IPv4 + IPv6 环回/链路本地）
_PRIVATE_IP_PREFIXES = (
    "127.", "10.", "192.168.", "169.254.", "0.",
    "::1", "fe80:", "fc00:", "fd00:",
)
_PRIVATE_IP_RANGES = (
    (0xAC100000, 0xAC1FFFFF),   # 172.16.0.0 - 172.31.255.255
)

# 免密搜索源：百度优先（中文覆盖面最好），Bing/DuckDuckGo 兜底；不需要 API Key
_BAIDU_SEARCH_URL = "https://www.baidu.com/s"
_BING_SEARCH_URL = "https://cn.bing.com/search"
_DDG_SEARCH_URL = "https://html.duckduckgo.com/html/"
_SEARCH_TIMEOUT = 10
_SEARCH_CACHE_TTL = 300
_SEARCH_CACHE_MAX = 32
_BAIDU_RESOLVE_LIMIT = 5  # 只还原前 5 条真实链接，控制额外请求量
_SEARCH_CACHE: dict[str, tuple[float, str]] = {}
_SEARCH_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _ip_in_private_range(ip_str: str) -> bool:
    """判定单个 IPv4 地址字符串是否属于内网/保留网段（含 172.16.0.0/12 数值范围）。"""
    for p in _PRIVATE_IP_PREFIXES:
        if ip_str.startswith(p):
            return True
    try:
        parts = ip_str.split(".")
        if len(parts) == 4:
            ip_int = (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
            for lo, hi in _PRIVATE_IP_RANGES:
                if lo <= ip_int <= hi:
                    return True
    except (ValueError, IndexError):
        pass
    return False


def _is_private_ip(host: str) -> bool:
    """判断 host 是否解析到内网/保留网段（SSRF 防护）。"""
    h = host.strip().lower().rstrip(".")
    # 先快速字符串匹配（常见内网段前缀）
    for p in _PRIVATE_IP_PREFIXES:
        if h.startswith(p):
            return True
    # 原始 host 是 IPv4 地址时做数值范围判定（含 172.16.0.0/12）
    if _ip_in_private_range(h):
        return True
    # DNS 解析后再对每个地址查一遍（前缀 + 数值范围都查）
    try:
        infos = socket.getaddrinfo(h, None)
        for info in infos:
            addr = info[4][0]
            if _ip_in_private_range(addr):
                return True
    except socket.gaierror:
        return True  # DNS 失败也挡住
    return False


def _url_safety_check(url: str) -> str | None:
    """URL 安全检查，返回错误消息（None 表示通过）。"""
    try:
        parsed = urlparse(url)
    except Exception:
        return "URL 格式无效"
    if parsed.scheme != "https":
        return "仅支持 HTTPS URL"
    host = parsed.hostname
    if not host:
        return "URL 缺少主机名"
    if _is_private_ip(host):
        return f"URL 指向内网地址（{host}），SSRF 防护已拦截"
    return None


def _clean_inline(text: str) -> str:
    """去标签 + 反转义 + 压缩空白。"""
    return re.sub(r"\s+", " ", _html_unescape(_strip_html(text))).strip()


_DDG_REDIRECT_HOSTS = ("duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com")


def _decode_ddg_url(url: str) -> str:
    """还原 DuckDuckGo 跳转链接（//duckduckgo.com/l/?uddg=<encoded>）。"""
    u = url.strip()
    if u.startswith("//"):
        u = "https:" + u
    try:
        parsed = urlparse(u)
        if any(parsed.netloc.endswith(h) for h in _DDG_REDIRECT_HOSTS) and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg")
            if target:
                return unquote(target[0])
    except Exception:
        pass
    return u


def _parse_bing_results(page: str, limit: int = 8) -> list[dict]:
    """解析 Bing 搜索结果页的 b_algo 列表。"""
    results: list[dict] = []
    for block in page.split('class="b_algo"')[1:]:
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        url = _html_unescape(m.group(1)).strip()
        title = _clean_inline(m.group(2))
        snippet = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        desc = _clean_inline(snippet.group(1)) if snippet else ""
        if title and url.startswith(("http://", "https://")):
            results.append({"title": title, "description": desc, "url": url})
        if len(results) >= limit:
            break
    return results


def _parse_ddg_results(page: str, limit: int = 8) -> list[dict]:
    """解析 DuckDuckGo HTML 结果的标题/摘要/链接。"""
    titles = re.findall(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)
    snippets = re.findall(
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', page, re.S)
    results: list[dict] = []
    for i, (url, title_html) in enumerate(titles[:limit]):
        url = _decode_ddg_url(_html_unescape(url))
        title = _clean_inline(title_html)
        desc = _clean_inline(snippets[i]) if i < len(snippets) else ""
        if title and url.startswith(("http://", "https://")):
            results.append({"title": title, "description": desc, "url": url})
    return results


_BAIDU_LINK_RE = re.compile(
    r'<h3[^>]*>\s*<a[^>]+href="(https?://www\.baidu\.com/link\?url=[^"]+)"[^>]*>(.*?)</a>',
    re.S,
)


def _resolve_baidu_link(href: str) -> str:
    """把百度跳转链还原成真实 URL；失败则保留原链。"""
    try:
        resp = http_requests.get(
            href, headers={"User-Agent": _SEARCH_UA}, timeout=5, allow_redirects=False)
        location = (resp.headers.get("Location") or "").strip()
        if location.startswith(("http://", "https://")):
            host = urlparse(location).hostname or ""
            if host and not _is_private_ip(host):
                return location
    except Exception:
        pass
    return href


def _parse_baidu_results(page: str, limit: int = 8) -> list[dict]:
    """解析百度结果页；标题/链接必取，摘要尽力提取。"""
    matches = list(_BAIDU_LINK_RE.finditer(page))[:limit]
    results: list[dict] = []
    for i, m in enumerate(matches):
        title = _clean_inline(m.group(2))
        if not title:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(page), m.end() + 3000)
        block = page[m.end():end]
        snippet = re.search(
            r'<span[^>]+class="[^"]*(?:content-right|abstract)[^"]*"[^>]*>(.*?)</span>',
            block, re.S,
        )
        desc = _clean_inline(snippet.group(1)) if snippet else ""
        href = _html_unescape(m.group(1))
        results.append({
            "title": title,
            "description": desc[:300],
            "url": _resolve_baidu_link(href) if i < _BAIDU_RESOLVE_LIMIT else href,
        })
    return results


def _search_web_page(url: str, params: dict, parser, limit: int = 8) -> list[dict]:
    """抓取免密搜索页并解析；非 200 直接抛错，交给上层切换下一个源。"""
    resp = http_requests.get(
        url,
        params=params,
        headers={
            "User-Agent": _SEARCH_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        timeout=_SEARCH_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return parser(resp.text, limit)


def _tool_web_search(query: str) -> str:
    """联网搜索：百度优先，Bing/DuckDuckGo 兜底，均不需要 API Key。"""
    q = str(query or "").strip()[:200]
    if not q:
        return json.dumps({"error": "empty_query", "message": "搜索关键词不能为空"}, ensure_ascii=False)

    cached = _SEARCH_CACHE.get(q)
    if cached and time.monotonic() - cached[0] < _SEARCH_CACHE_TTL:
        return cached[1]

    sources = (
        ("baidu", _BAIDU_SEARCH_URL, {"wd": q, "rn": 10}, _parse_baidu_results),
        ("bing", _BING_SEARCH_URL, {"q": q, "count": 10}, _parse_bing_results),
        ("duckduckgo", _DDG_SEARCH_URL, {"q": q}, _parse_ddg_results),
    )
    errors: list[str] = []
    for provider, url, params, parser in sources:
        try:
            results = _search_web_page(url, params, parser, limit=8)
        except Exception as e:
            errors.append(f"{provider}: {e.__class__.__name__}: {e}")
            continue
        if results:
            payload = json.dumps({
                "query": q,
                "provider": provider,
                "count": len(results),
                "results": results,
            }, ensure_ascii=False)
            if len(_SEARCH_CACHE) >= _SEARCH_CACHE_MAX:
                _SEARCH_CACHE.clear()
            _SEARCH_CACHE[q] = (time.monotonic(), payload)
            return payload
        errors.append(f"{provider}: 0 results")

    return json.dumps({
        "error": "web_search_network",
        "message": "搜索源均不可用：" + "；".join(errors),
    }, ensure_ascii=False)


def _tool_web_fetch(url: str) -> str:
    """网页抓取（HTTPS 强制 + SSRF 防护 + 截断上限）。"""
    u = str(url or "").strip()
    if not u:
        return json.dumps({"error": "empty_url", "message": "URL 不能为空"}, ensure_ascii=False)

    safety_err = _url_safety_check(u)
    if safety_err:
        return json.dumps({"error": "web_fetch_safety", "message": safety_err}, ensure_ascii=False)

    try:
        resp = http_requests.get(u, timeout=15, headers={
            "User-Agent": "OMS-Agent/1.0 (+web_fetch tool)",
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
        }, allow_redirects=True)
    except http_requests.RequestException as e:
        return json.dumps({"error": "web_fetch_network",
                           "message": f"请求失败（{e.__class__.__name__}）：{e}"},
                          ensure_ascii=False)

    # 重定向后再验一次 SSRF
    final_url = resp.url or u
    redirect_err = _url_safety_check(final_url)
    if redirect_err:
        return json.dumps({"error": "web_fetch_redirect_blocked",
                           "message": f"重定向后目标不安全：{redirect_err}"},
                          ensure_ascii=False)

    if resp.status_code != 200:
        return json.dumps({"error": "web_fetch_http",
                           "message": f"目标返回 HTTP {resp.status_code}"},
                          ensure_ascii=False)

    ctype = (resp.headers.get("content-type") or "").lower()
    if "html" in ctype:
        text = _strip_html(resp.text)
    elif "text" in ctype or "json" in ctype or "xml" in ctype:
        text = resp.text
    else:
        text = resp.text

    # 截断上限 10KB
    max_chars = 10240
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[内容已截断，上限 10KB]"

    return json.dumps({
        "url": final_url,
        "content_type": ctype,
        "chars": len(text),
        "content": text,
    }, ensure_ascii=False)


class _HtmlTextExtractor(HTMLParser):
    """极简 HTML 正文提取（script/style 跳过，标签内文本拼接）。"""

    def __init__(self):
        super().__init__()
        self._skip = 0
        self._out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip > 0:
            self._skip -= 1
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self._out.append("\n")

    def handle_data(self, data):
        if self._skip == 0:
            text = data.strip()
            if text:
                self._out.append(text)
                self._out.append(" ")


def _strip_html(html: str) -> str:
    """从 HTML 字符串提取纯文本（极简实现，够用就行）。"""
    parser = _HtmlTextExtractor()
    try:
        parser.feed(html[:200000])  # 前 200KB 足够
    except Exception:  # noqa: BLE001 - HTML 解析失败就降级返回原文前 10KB
        return html[:10000]
    out = "".join(parser._out)
    # 压缩多余空行和空格
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
