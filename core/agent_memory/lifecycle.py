"""core/agent_memory/lifecycle.py — 衰减归档与物理清理。

设计真源：docs/specs/agent-memory/spec.md §8 / §12 M2。
  - 冷存：180 天未用且 importance < 0.3 → archived；
  - 上限：每 namespace 500 条 open，超出按 (importance, recency) 归档；
  - 删除：软删 30 天后物理清理。
"""

from __future__ import annotations

from datetime import datetime

from core.agent_memory import store


def _parse_time(value) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _age_days(value, now_epoch: float) -> float | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return (now_epoch - parsed.timestamp()) / 86400


def _now_epoch(now) -> float:
    if now is None:
        return datetime.now().astimezone().timestamp()
    if isinstance(now, (int, float)):
        return float(now)
    parsed = _parse_time(now)
    return parsed.timestamp() if parsed else datetime.now().astimezone().timestamp()


def archive_stale(*, days: int = 180, importance_floor: float = 0.3, now=None) -> int:
    """冷存：长期未用且低重要度的开放条目转 archived。"""
    now_epoch = _now_epoch(now)
    archived = 0
    for item in store.load_all():
        if item.get("status") != "active" or item.get("valid_to"):
            continue
        if float(item.get("importance") or 0) >= importance_floor:
            continue
        reference = item.get("last_used_at") or item.get("recorded_at")
        age = _age_days(reference, now_epoch)
        if age is None or age < days:
            continue
        store.set_status(item["id"], "archived")
        archived += 1
    return archived


def enforce_capacity(*, max_open: int = 500) -> int:
    """每 namespace open 上限；超出按低重要度、旧记录优先归档。"""
    groups: dict[str, list[dict]] = {}
    for item in store.load_all():
        if item.get("status") != "active" or item.get("valid_to"):
            continue
        groups.setdefault(str(item.get("namespace") or ""), []).append(item)

    archived = 0
    for rows in groups.values():
        if len(rows) <= max_open:
            continue
        rows.sort(key=lambda it: (float(it.get("importance") or 0),
                                  str(it.get("recorded_at") or "")))
        for item in rows[:len(rows) - max_open]:
            store.set_status(item["id"], "archived")
            archived += 1
    return archived


def purge_deleted(*, days: int = 30, now=None) -> int:
    """软删超过 days 的条目物理删除。"""
    now_epoch = _now_epoch(now)
    purged = 0
    for item in list(store.load_all()):
        if item.get("status") != "deleted":
            continue
        age = _age_days(item.get("deleted_at") or item.get("recorded_at"), now_epoch)
        if age is None or age < days:
            continue
        if store.purge(item["id"]):
            purged += 1
    return purged


def run_lifecycle() -> dict[str, int]:
    return {
        "archived": archive_stale(),
        "capacity_archived": enforce_capacity(),
        "purged": purge_deleted(),
    }
