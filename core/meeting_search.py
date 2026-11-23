"""跨会议关键词检索（提问范围的唯一检索器）。

问答与智能体两条链路都只通过 ``build_scope_context`` 获取检索结果，
避免为两种模式各维护一套检索口径。纯关键词 + 中文 bigram，不引入向量库。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from core.chat_context import task_final_summary
from core.task_store import tasks

logger = logging.getLogger(__name__)

SCOPES = ("meeting", "all")
DEFAULT_SCOPE = "meeting"
SCOPE_BLOCK_HEADER = "## 跨会议检索命中"

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-z0-9]+")
_DECISION_INTENT_RE = re.compile(r"决定|拍板|采用|启用|决议|通过|同意|结论|定下来")
_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "我", "你", "他", "这", "那",
    "什么", "如何", "怎么", "为什么", "a", "an", "the", "is", "are", "of",
}


def normalize_scope(value: str | None) -> str:
    """缺省/非法一律回落本场会议。"""
    return value if value in SCOPES else DEFAULT_SCOPE


def _has_decision_intent(query: str) -> bool:
    """决策类提问：优先把决策项摆到证据最前。"""
    return bool(_DECISION_INTENT_RE.search(query or ""))


def _query_terms(query: str) -> list[str]:
    """中文连续串 + bigram + 英文词，去停用词并保序去重。"""
    text = (query or "").lower()
    terms: list[str] = []
    for run in _CJK_RE.findall(text):
        if len(run) >= 2:
            terms.extend(run[i:i + 2] for i in range(len(run) - 1))
        if run not in _STOPWORDS:
            terms.append(run)
    terms.extend(w for w in _WORD_RE.findall(text) if len(w) >= 2 and w not in _STOPWORDS)
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term in _STOPWORDS or term in seen:
            continue
        seen.add(term)
        ordered.append(term)
    return ordered


def _count(text: str, term: str, cap: int = 2) -> int:
    return min(text.count(term), cap)


def _dialogue_lines(task: dict) -> list[str]:
    lines: list[str] = []
    for item in task.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        for sentence in item.get("sentences") or []:
            if not isinstance(sentence, dict):
                continue
            text = str(sentence.get("text") or "").strip()
            if text:
                lines.append(text)
    return lines


def _snippet(text: str, limit: int = 160) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"


def _meeting_date(task: dict) -> str:
    raw = task.get("meeting_date") or task.get("created_at") or ""
    return str(raw)[:10]


def _score_task(task: dict, query: str, terms: list[str], decision_intent: bool) -> dict | None:
    title = str(task.get("title") or task.get("audio_name") or "未命名会议")
    try:
        summary = task_final_summary(task) or ""
    except Exception:  # noqa: BLE001 - 单场摘要异常不影响其他会议
        summary = ""
    decision_items = [d for d in (task.get("decisions") or []) if isinstance(d, dict)]
    decisions_text = " ".join(str(d.get("text") or "") for d in decision_items)
    dialogue = _dialogue_lines(task)

    title_l = title.lower()
    summary_l = summary.lower()
    decisions_l = decisions_text.lower()

    score = 0
    title_hit = bool(query and query.lower() in title_l)
    if title_hit:
        score += 30
    for term in terms:
        score += _count(title_l, term) * 8
        score += _count(summary_l, term) * 4
        score += _count(decisions_l, term, cap=3) * 4

    dialogue_matches: list[str] = []
    for line in dialogue:
        line_l = line.lower()
        hits = sum(1 for term in terms if term in line_l)
        if not hits:
            continue
        score += hits * 2
        dialogue_matches.append(line)
        if len(dialogue_matches) >= 5:
            break

    if score <= 0:
        return None

    title_matched = title_hit or any(term in title_l for term in terms)
    summary_matched = any(term in summary_l for term in terms)

    # 决策类提问把决策项提到最高优先级；其余提问按标题→摘要→决策→对话排序。
    # 候选统一去重后再截断，避免同一段摘要按命中词重复占满片段位。
    priorities = ({"decision": 0, "summary": 1, "dialogue": 2, "title": 3}
                  if decision_intent
                  else {"title": 0, "summary": 1, "decision": 2, "dialogue": 3})
    candidates: list[tuple[int, str]] = []
    if title_matched:
        candidates.append((priorities["title"], title))
    if summary_matched:
        candidates.append((priorities["summary"], summary))
    for d in decision_items:
        text = str(d.get("text") or "").strip()
        if not text:
            continue
        matched = any(term in text.lower() for term in terms)
        if not matched and not decision_intent:
            continue
        status = "已完成" if d.get("done") else "待确认"
        assignee = str(d.get("assignee") or "").strip()
        meta = f"（{status}{'，' + assignee if assignee else ''}）"
        candidates.append((priorities["decision"], f"决策：{text}{meta}"))
    candidates.extend((priorities["dialogue"], line) for line in dialogue_matches)

    candidates.sort(key=lambda item: item[0])
    seen: set[str] = set()
    snippets: list[str] = []
    for _, text in candidates:
        normalized = " ".join(text.split())
        if normalized in seen:
            continue
        seen.add(normalized)
        snippets.append(_snippet(normalized))
        if len(snippets) >= 4:
            break

    return {
        "task_id": str(task.get("id") or task.get("task_id") or ""),
        "title": title,
        "date": _meeting_date(task),
        "score": score,
        "snippets": snippets,
        "summary": summary,
        "decisions": [
            f"{str(d.get('text') or '').strip()}（{'已完成' if d.get('done') else '待确认'}"
            f"{'，' + str(d.get('assignee')).strip() if d.get('assignee') else ''}）"
            for d in decision_items if str(d.get("text") or "").strip()
        ],
    }


def search_meetings(
    query: str,
    *,
    exclude_task_id: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """全库会议关键词检索，返回按相关度降序的命中（limit=None 返回全部）。"""
    terms = _query_terms(query)
    if not terms:
        return []

    decision_intent = _has_decision_intent(query)
    scored: list[dict] = []
    for task_id, task in list(tasks.items()):
        if not isinstance(task, dict) or task_id == exclude_task_id:
            continue
        result = _score_task({**task, "id": task_id}, query, terms, decision_intent)
        if result:
            scored.append(result)

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit] if limit is not None else scored


def _format_block(query: str, hits: list[dict], total: int) -> str:
    if not hits:
        return ""
    shown = f"，展示前 {len(hits)} 场" if total > len(hits) else ""
    lines = [f"{SCOPE_BLOCK_HEADER}（提问范围：全部会议，共 {total} 场命中{shown}）", f"检索问题：{query}"]
    for index, hit in enumerate(hits, start=1):
        lines.append(f"### {index}. {hit['title']}（{hit['date'] or '日期未知'}，相关度 {hit['score']}）")
        lines.extend(f"- {snippet}" for snippet in hit["snippets"])
        # 命中片段之外的决策事实与纪要摘录：智能体读不到工作区外的会议文件，
        # 把判定「哪场拍板」所需的证据随命中一起给出，避免只能按时间线猜。
        for decision in (hit.get("decisions") or [])[:5]:
            if not any(decision[:30] in snippet for snippet in hit["snippets"]):
                lines.append(f"- 决策项：{decision}")
        summary = hit.get("summary") or ""
        if summary and not any(summary[:30] in snippet for snippet in hit["snippets"]):
            lines.append(f"- 纪要摘录：{_snippet(summary, 300)}")
    lines.append(
        "说明：以上为历史会议证据（命中片段 + 决策项 + 纪要摘录），引用时标注会议标题与日期，"
        "不得改写为当前会议事实；证据不足时明确说明，不要按时间线推断决议。"
    )
    return "\n".join(lines)


def build_scope_context(
    scope: str | None,
    query: str,
    *,
    exclude_task_id: str | None = None,
    limit: int = 4,
) -> tuple[str, dict[str, Any]]:
    """唯一入口：返回 (上下文块, retrieval)。

    meeting → 空块 + searched=False；all → 全库检索命中块 + 统计。
    retrieval.hits 为总命中数，shown 为实际注入场次。
    检索异常不阻断对话，降级为未检索。
    """
    resolved = normalize_scope(scope)
    retrieval: dict[str, Any] = {
        "scope": resolved,
        "searched": False,
        "hits": 0,
        "shown": 0,
        "meetings": [],
        "latency_ms": 0,
    }
    if resolved != "all":
        return "", retrieval

    started = time.perf_counter()
    try:
        all_hits = search_meetings(query, exclude_task_id=exclude_task_id, limit=None)
    except Exception as exc:  # noqa: BLE001 - 检索失败不得阻断对话
        logger.warning("[范围检索] 检索失败，降级为未检索: %s", exc)
        return "", retrieval

    shown = all_hits[:limit]
    retrieval["searched"] = True
    retrieval["hits"] = len(all_hits)
    retrieval["shown"] = len(shown)
    retrieval["meetings"] = [
        {"task_id": h["task_id"], "title": h["title"], "date": h["date"], "score": h["score"]}
        for h in shown
    ]
    retrieval["latency_ms"] = round((time.perf_counter() - started) * 1000)
    return _format_block(query, shown, len(all_hits)), retrieval
