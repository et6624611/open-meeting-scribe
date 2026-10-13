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
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests as http_requests  # 统一重命名，避免 _tool_web_fetch 内 import 重名冲突

from app.store import tasks
from core import hotwords as hw_module
from core.chat_context import task_final_summary, task_notes
from core.decision_flow import status_of
from core.decision_status import load_statuses
from core.project_index import get_project_context_for_chat

logger = logging.getLogger(__name__)

# 随记读工具正文上限（字符）：用户手写区，超长截断并标注
_NOTES_MAX_CHARS = 6000

# 工具名 → 中文标签（供前端显示） / Tool name → Chinese label for frontend display
TOOL_LABELS = {
    "get_meeting_info": "获取会议信息",
    "get_meeting_transcript": "读取会议转写",
    "get_meeting_notes": "读取会议随记",
    "get_meeting_todos": "查询待办事项",
    "search_project_files": "搜索项目资料",
    "get_hotwords": "获取热词列表",
    "get_system_settings": "获取系统设置",
    "update_decision_node": "改写决策节点",
    "delete_decision_node": "删除决策节点",
    "propose_notes": "提出随记改写建议",
    "propose_summary": "提出纪要改写建议",
    "revise_insight_board": "修订洞察板",
    "revise_insight_board_section": "修订洞察板单节",
    "web_search": "联网搜索",
    "web_fetch": "网页抓取",
}

TOOL_ICONS = {
    "get_meeting_info": "📋",
    "get_meeting_transcript": "💬",
    "get_meeting_notes": "📝",
    "get_meeting_todos": "✅",
    "search_project_files": "📂",
    "get_hotwords": "🔤",
    "get_system_settings": "⚙️",
    "update_decision_node": "✏️",
    "delete_decision_node": "🗑️",
    "propose_notes": "🗒️",
    "propose_summary": "📝",
    "revise_insight_board": "🖋️",
    "revise_insight_board_section": "📝",
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
        elif name == "get_meeting_todos":
            return _tool_get_meeting_todos(task_id)
        elif name == "search_project_files":
            return _tool_search_project_files(project_id, arguments.get("query", ""))
        elif name == "get_hotwords":
            return _tool_get_hotwords()
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


def _tool_get_meeting_todos(task_id: str | None) -> str:
    if not task_id or task_id not in tasks:
        return json.dumps({"info": "当前没有关联的会议"}, ensure_ascii=False)
    task = tasks[task_id]
    todos = task.get("todos") or []
    if not todos:
        return json.dumps({"info": "该会议暂无待办事项", "count": 0}, ensure_ascii=False)
    items = []
    for t in todos:
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
    return json.dumps({"todos": items, "count": len(items),
                       "available_statuses": statuses,
                       "status_note": "改写状态时 status 只能取 available_statuses 中的 id；"
                                      "用户已拍板的决策应推进到 closing=true 的状态"},
                      ensure_ascii=False)


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

# Brave Search API（默认 provider）
_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_TIMEOUT = 10


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


def _get_web_search_config() -> dict | None:
    """取联网搜索配置；未配置返回 None。"""
    from app.store import load_settings
    settings = load_settings()
    ns = settings.get("web_search") or {}
    api_key = str(ns.get("api_key") or "").strip()
    if not api_key:
        return None
    return {"provider": str(ns.get("provider") or "brave").strip(), "api_key": api_key}


def _tool_web_search(query: str) -> str:
    """联网搜索（Brave Search API 默认）。"""
    q = str(query or "").strip()[:200]
    if not q:
        return json.dumps({"error": "empty_query", "message": "搜索关键词不能为空"}, ensure_ascii=False)

    cfg = _get_web_search_config()
    if not cfg:
        return json.dumps({
            "error": "web_search_not_configured",
            "message": "联网搜索尚未配置 API key。请在设置 → 智能体 → 联网搜索 中填入 Brave Search API Key。",
            "note": "未配置搜索 key，无法联网检索。可以依赖模型自身知识继续。",
        }, ensure_ascii=False)

    provider = cfg["provider"]
    api_key = cfg["api_key"]

    if provider == "brave":
        try:
            resp = http_requests.get(
                _BRAVE_SEARCH_URL,
                params={"q": q, "count": 8, "search_lang": "zh", "ui_lang": "zh-CN"},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                timeout=_BRAVE_TIMEOUT,
            )
        except http_requests.RequestException as e:
            return json.dumps({"error": "web_search_network",
                               "message": f"搜索请求失败（{e.__class__.__name__}）：{e}"},
                              ensure_ascii=False)

        if resp.status_code == 401:
            return json.dumps({"error": "web_search_auth",
                               "message": "API Key 无效（401），请检查设置中的联网搜索 Key"},
                              ensure_ascii=False)
        if resp.status_code == 429:
            return json.dumps({"error": "web_search_rate_limited",
                               "message": "搜索配额已耗尽（429），请稍后再试或升级套餐"},
                              ensure_ascii=False)
        if resp.status_code != 200:
            return json.dumps({"error": "web_search_http",
                               "message": f"搜索 API 返回 {resp.status_code}"},
                              ensure_ascii=False)

        try:
            data = resp.json()
        except ValueError:
            return json.dumps({"error": "web_search_parse",
                               "message": "搜索 API 返回无法解析的 JSON"},
                              ensure_ascii=False)

        results = []
        for item in (data.get("web") or {}).get("results", [])[:8]:
            results.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "url": item.get("url", ""),
            })
        return json.dumps({
            "query": q,
            "count": len(results),
            "results": results,
        }, ensure_ascii=False)
    else:
        return json.dumps({"error": "web_search_unknown_provider",
                           "message": f"未知搜索 provider: {provider}（当前仅支持 brave）"},
                          ensure_ascii=False)


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
