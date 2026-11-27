"""core/agent_memory/retrieve.py — 作用域链检索与常驻 core 选择。

设计真源：docs/specs/agent-memory/spec.md §3.1 / §6。
M0–M2 关键词层复用 ``core.meeting_search._query_terms`` 的分词与停用词口径，
不另写一套；向量层留到 M3，cos 项固定为 0。
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from core.agent_memory import schema, store
from core.meeting_search import _query_terms

CORE_MAX_ITEMS = 30
CORE_BUDGET_CHARS = 800
ARCHIVAL_TOP_K = 8
ARCHIVAL_BUDGET_CHARS = 1200


def _days_since(timestamp: str | None) -> float:
    if not timestamp:
        return 365.0
    try:
        moment = datetime.fromisoformat(str(timestamp))
    except ValueError:
        return 365.0
    now = datetime.now().astimezone()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - moment).total_seconds() / 86400)


def _recency(item: dict[str, Any]) -> float:
    stamp = item.get("last_used_at") or item.get("recorded_at")
    return math.exp(-_days_since(stamp) / 90)


def _haystack(item: dict[str, Any]) -> str:
    parts = [
        item.get("text") or "",
        item.get("subject") or "",
        item.get("relation") or "",
        item.get("object") or "",
        " ".join(item.get("tags") or []),
    ]
    return " ".join(parts).lower()


def _scope_map(chain: list[dict[str, Any]]) -> dict[str, float]:
    return {entry["namespace"]: float(entry.get("weight") or 0) for entry in chain}


def _scoped(chain: list[dict[str, Any]], *, as_of: str | None = None) -> list[dict[str, Any]]:
    weights = _scope_map(chain)
    return [
        item for item in store.load_index()
        if item.get("namespace") in weights and schema.is_open(item, as_of)
    ]


def _idf(items: list[dict[str, Any]], terms: list[str]) -> tuple[dict[str, float], float]:
    total = len(items)
    idf: dict[str, float] = {}
    for term in terms:
        df = sum(1 for item in items if term in _haystack(item))
        idf[term] = max(0.15, math.log((total + 1) / (df + 1)))
    return idf, sum(idf.values()) or 1.0


def search(
    query: str,
    chain: list[dict[str, Any]],
    *,
    as_of: str | None = None,
    top_k: int = ARCHIVAL_TOP_K,
    budget_chars: int = ARCHIVAL_BUDGET_CHARS,
    touch: bool = True,
) -> list[dict[str, Any]]:
    """按作用域链检索开放记忆，按预算截断并回写使用记录。"""
    pool = _scoped(chain, as_of=as_of)
    if not pool:
        return []

    weights = _scope_map(chain)
    terms = _query_terms(query)
    if not terms:
        return []
    idf, idf_total = _idf(pool, terms)

    scored: list[tuple[float, dict[str, Any]]] = []
    for item in pool:
        haystack = _haystack(item)
        raw = sum(weight for term, weight in idf.items() if term in haystack)
        if raw <= 0:
            continue
        keyword = min(1.0, raw / idf_total)
        score = (0.45 * keyword
                 + 0.10 * float(item.get("importance") or 0)
                 + 0.10 * _recency(item)) * weights.get(item.get("namespace"), 0)
        if score <= 0:
            continue
        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    chosen: list[dict[str, Any]] = []
    used = 0
    for score, item in scored:
        if len(chosen) >= max(1, int(top_k)):
            break
        length = len(str(item.get("text") or ""))
        if chosen and used + length > budget_chars:
            break
        enriched = {**item, "_score": round(score, 4)}
        chosen.append(enriched)
        used += length

    if touch and chosen:
        try:
            store.mark_used([item["id"] for item in chosen])
        except Exception:  # noqa: BLE001 - 使用统计失败不影响本轮注入
            pass
    return chosen


def select_core(
    chain: list[dict[str, Any]],
    *,
    max_items: int = CORE_MAX_ITEMS,
    budget_chars: int = CORE_BUDGET_CHARS,
) -> list[dict[str, Any]]:
    """常驻通道：L3 画像 + 高重要度 L2 事实，超预算降级到 archival（此处只做挑选）。"""
    weights = _scope_map(chain)
    candidates: list[dict[str, Any]] = []
    for item in store.load_index():
        namespace = item.get("namespace")
        if namespace not in weights or not schema.is_open(item):
            continue
        is_profile = item.get("kind") in ("preference", "habit")
        is_key_fact = float(item.get("importance") or 0) >= 0.8
        if not (is_profile or is_key_fact):
            continue
        priority = (1.0 if is_profile else 0.9) * weights[namespace]
        candidates.append({**item, "_priority": priority})

    candidates.sort(
        key=lambda it: (it["_priority"], float(it.get("importance") or 0), _recency(it)),
        reverse=True,
    )

    chosen: list[dict[str, Any]] = []
    used = 0
    for item in candidates:
        if len(chosen) >= max(1, int(max_items)):
            break
        length = len(str(item.get("text") or ""))
        if chosen and used + length > budget_chars:
            break
        chosen.append(item)
        used += length
    return chosen
