"""core/agent_memory/store.py — 记忆存储唯一写入口。

设计真源：docs/specs/agent-memory/spec.md §4.2 / §5。
  - 所有写入必须经本模块，持进程内锁 + fs_atomic 原子写；
  - 冲突用有效期闭合表达，不删除、不覆盖，不改 text；
  - 无 source 一律拒收（error=no_source）。
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Callable

from core.agent_memory import schema
from core.fs_atomic import atomic_write_json, atomic_write_text

logger = logging.getLogger(__name__)

# 测试可 monkeypatch 本模块级目录
MEMORY_DIR = Path("data") / "memory"

INDEX_FILE = "index.json"
AUDIT_FILE = "audit.jsonl"

_LOCK = threading.RLock()
_NORM_RE = re.compile(r"[\s\W_]+", re.UNICODE)


class MemoryWriteError(ValueError):
    """写入被拒（无来源、字段非法、条目不存在）。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


# ── 路径与分片 / Paths and shards ────────────────────────────────

def _root() -> Path:
    return Path(MEMORY_DIR)


def _shard_for(item: dict[str, Any]) -> Path:
    """按 namespace + kind 决定分片文件，与 spec §4.2 布局一致。"""
    ns = schema.parse_namespace(item["namespace"])
    if ns["kind"] == "task":
        month = str(item.get("recorded_at") or schema.now_iso())[:7]
        return _root() / "episodic" / f"{month}.jsonl"
    if ns["kind"] == "space":
        return _root() / "spaces" / ns["id"] / "semantic.json"
    if ns["kind"] == "role":
        return _root() / "roles" / ns["id"] / "profile.json"
    if item.get("kind") in ("preference", "habit"):
        return _root() / "global" / "profile.json"
    return _root() / "global" / "semantic.json"


def _iter_shard_files():
    root = _root()
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in (INDEX_FILE, AUDIT_FILE):
            continue
        if path.suffix in (".json", ".jsonl"):
            yield path


def _read_shard(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []
    if path.suffix == ".jsonl":
        items: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                items.append(obj)
        return items
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    raw = obj.get("items") if isinstance(obj, dict) else obj
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def _write_shard(path: Path, items: list[dict[str, Any]]) -> None:
    if path.suffix == ".jsonl":
        content = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items)
        atomic_write_text(path, content)
    else:
        atomic_write_json(path, {"version": 1, "items": items})


def load_all() -> list[dict[str, Any]]:
    """全量读取（各分片合并）。写路径内部使用，读路径优先用 load_index。"""
    items: list[dict[str, Any]] = []
    for path in _iter_shard_files():
        items.extend(_read_shard(path))
    return items


def load_index() -> list[dict[str, Any]]:
    """读取轻量索引；缺失或损坏时回退全量分片。"""
    path = _root() / INDEX_FILE
    if path.exists():
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            items = obj.get("items") if isinstance(obj, dict) else None
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
        except (OSError, json.JSONDecodeError):
            pass
    return load_all()


def _write_index(items: list[dict[str, Any]]) -> None:
    atomic_write_json(_root() / INDEX_FILE, {
        "version": 1,
        "updated_at": schema.now_iso(),
        "count": len(items),
        "items": items,
    })


def _save_all(items: list[dict[str, Any]]) -> None:
    grouped: dict[Path, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(_shard_for(item), []).append(item)
    for stale in set(_iter_shard_files()) - set(grouped):
        try:
            stale.unlink()
        except OSError:
            pass
    for path, group in grouped.items():
        _write_shard(path, group)
    _write_index(items)


def _audit(action: str, item: dict[str, Any], extra: dict | None = None) -> None:
    record: dict[str, Any] = {
        "ts": schema.now_iso(),
        "action": action,
        "id": item.get("id"),
        "namespace": item.get("namespace"),
        "kind": item.get("kind"),
    }
    if extra:
        record.update(extra)
    path = _root() / AUDIT_FILE
    try:
        old = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        old = ""
    atomic_write_text(path, old + json.dumps(record, ensure_ascii=False) + "\n")


def audit(action: str, item: dict[str, Any], extra: dict | None = None) -> None:
    """公开审计写入口（巩固、生命周期等非条目级动作使用）。"""
    _audit(action, item, extra)


def read_audit(limit: int = 100) -> list[dict[str, Any]]:
    """读取 audit.jsonl 末尾 limit 条，倒序返回。"""
    path = _root() / AUDIT_FILE
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in lines[-max(1, int(limit)):]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    records.reverse()
    return records


# ── 文本相似度与闭合判定 / Similarity and closure decisions ──────

def _bigrams(text: str) -> set[str]:
    cleaned = _NORM_RE.sub("", str(text or "").lower())
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


def _jaccard(a: str, b: str) -> float:
    left, right = _bigrams(a), _bigrams(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def default_decide(new: dict[str, Any], old: dict[str, Any]) -> str:
    """无 LLM 时的规则判定：equal / conflict / coexist。

    判定键是 (namespace, subject, relation)：同一关系的 object 变了即为冲突；
    object 相同且文本高度相似视为等价；其余并存。
    """
    new_obj = str(new.get("object") or "").strip()
    old_obj = str(old.get("object") or "").strip()
    if new_obj and old_obj and new_obj != old_obj:
        return "conflict"
    if new_obj == old_obj and _jaccard(new.get("text") or "", old.get("text") or "") >= 0.85:
        return "equal"
    return "coexist"


def _find_duplicate(new: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        if item.get("status") == "deleted":
            continue
        if item.get("namespace") != new["namespace"] or item.get("kind") != new["kind"]:
            continue
        old_text = str(item.get("text") or "")
        if _jaccard(new["text"], old_text) >= 0.85:
            return item
        shorter, longer = sorted((new["text"], old_text), key=len)
        if len(shorter) >= 8 and shorter in longer:
            return item
    return None


# ── 写入 API / Write API ─────────────────────────────────────────

def upsert(
    item: dict[str, Any],
    *,
    decide: Callable[[dict, dict], str] | None = None,
    require_source: bool = True,
) -> dict[str, Any]:
    """唯一写入入口：去重 → 闭合判定 → 落盘 → 审计。

    Returns: {"item": 条目, "action": inserted|merged|noop|closed, "closed": [旧 id]}
    """
    if not isinstance(item, dict):
        raise MemoryWriteError("bad_item", "条目必须是对象")
    if require_source and not schema.has_source(item):
        raise MemoryWriteError("no_source", "记忆必须带 source.task_id 与 source.quote")

    explicit_time = bool(str(item.get("valid_from") or "").strip())
    new = schema.normalize_item(item)
    judge = decide or default_decide

    with _LOCK:
        items = load_all()

        duplicate = _find_duplicate(new, items)
        if duplicate is not None:
            duplicate["importance"] = round(
                max(float(duplicate.get("importance") or 0), new["importance"]), 3)
            duplicate["tags"] = list(dict.fromkeys(
                [*(duplicate.get("tags") or []), *new["tags"]]))
            _save_all(items)
            _audit("dedupe", duplicate, {"incoming": new["id"]})
            return {"item": duplicate, "action": "merged", "closed": []}

        candidates = [
            it for it in items
            if it.get("namespace") == new["namespace"]
            and it.get("subject") == new["subject"]
            and it.get("relation") == new["relation"]
            and it.get("status") == "active"
            and not it.get("valid_to")
        ]

        verdicts = [(old, judge(new, old)) for old in candidates]
        if any(verdict == "equal" for _old, verdict in verdicts):
            kept = next(old for old, verdict in verdicts if verdict == "equal")
            kept["importance"] = round(
                max(float(kept.get("importance") or 0), new["importance"]), 3)
            _save_all(items)
            _audit("noop", kept, {"incoming": new["id"]})
            return {"item": kept, "action": "noop", "closed": []}

        cut = new["valid_from"] if explicit_time else str(new["recorded_at"])[:10]
        closed_ids: list[str] = []
        for old, verdict in verdicts:
            if verdict != "conflict":
                continue
            old["valid_to"] = cut
            old["invalidated_by"] = new["id"]
            old["time_confidence"] = "high" if explicit_time else "low"
            closed_ids.append(old["id"])

        new["valid_from"] = cut
        items.append(new)
        _save_all(items)
        _audit("add", new, {"closed": closed_ids} if closed_ids else None)
        for old, verdict in verdicts:
            if verdict == "conflict":
                _audit("close", old, {"invalidated_by": new["id"], "valid_to": cut})
        return {
            "item": new,
            "action": "closed" if closed_ids else "inserted",
            "closed": closed_ids,
        }


def add(item: dict[str, Any], **kwargs) -> dict[str, Any]:
    """upsert 的别名，语义更直白。"""
    return upsert(item, **kwargs)


def get(memory_id: str) -> dict[str, Any] | None:
    for item in load_all():
        if item.get("id") == memory_id:
            return item
    return None


def close(
    memory_id: str,
    *,
    valid_to: str | None = None,
    invalidated_by: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """闭合一条记忆：只改元数据，不动 text。"""
    with _LOCK:
        items = load_all()
        target = next((it for it in items if it.get("id") == memory_id), None)
        if target is None:
            raise MemoryWriteError("not_found", f"记忆不存在：{memory_id}")
        target["valid_to"] = valid_to or schema.today()
        if invalidated_by:
            target["invalidated_by"] = invalidated_by
        _save_all(items)
        _audit("close", target, {"reason": reason} if reason else None)
        return target


def reopen(memory_id: str) -> dict[str, Any]:
    """重新打开已闭合条目。"""
    with _LOCK:
        items = load_all()
        target = next((it for it in items if it.get("id") == memory_id), None)
        if target is None:
            raise MemoryWriteError("not_found", f"记忆不存在：{memory_id}")
        target["valid_to"] = None
        target["invalidated_by"] = None
        if target.get("status") == "archived":
            target["status"] = "active"
        _save_all(items)
        _audit("reopen", target)
        return target


def update(memory_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """编辑条目：重新走 schema 校验，保持 id 与来源不变。"""
    with _LOCK:
        items = load_all()
        index = next((i for i, it in enumerate(items) if it.get("id") == memory_id), None)
        if index is None:
            raise MemoryWriteError("not_found", f"记忆不存在：{memory_id}")
        merged = {**items[index], **(patch or {})}
        merged["id"] = memory_id
        normalized = schema.normalize_item(merged)
        items[index] = normalized
        _save_all(items)
        _audit("update", normalized)
        return normalized


def delete(memory_id: str) -> dict[str, Any]:
    """软删除：status=deleted，30 天后由清理任务物理删除。"""
    with _LOCK:
        items = load_all()
        target = next((it for it in items if it.get("id") == memory_id), None)
        if target is None:
            raise MemoryWriteError("not_found", f"记忆不存在：{memory_id}")
        target["status"] = "deleted"
        target["deleted_at"] = schema.now_iso()
        _save_all(items)
        _audit("delete", target)
        return target


def set_status(memory_id: str, status: str) -> dict[str, Any]:
    """直接改状态（待确认采纳 / 面板操作）；校验合法状态。"""
    if status not in schema.STATUSES:
        raise MemoryWriteError("bad_status", f"非法状态：{status}")
    with _LOCK:
        items = load_all()
        target = next((it for it in items if it.get("id") == memory_id), None)
        if target is None:
            raise MemoryWriteError("not_found", f"记忆不存在：{memory_id}")
        target["status"] = status
        if status == "deleted":
            target["deleted_at"] = schema.now_iso()
        _save_all(items)
        _audit("status", target, {"status": status})
        return target


def purge(memory_id: str) -> bool:
    """物理删除。"""
    with _LOCK:
        items = load_all()
        kept = [it for it in items if it.get("id") != memory_id]
        if len(kept) == len(items):
            return False
        _save_all(kept)
        _audit("purge", {"id": memory_id})
        return True


def mark_used(memory_ids: list[str], *, when: str | None = None) -> int:
    """命中回写 last_used_at / use_count。"""
    wanted = {str(x) for x in (memory_ids or []) if x}
    if not wanted:
        return 0
    stamp = when or schema.now_iso()
    with _LOCK:
        items = load_all()
        hit = 0
        for item in items:
            if item.get("id") in wanted:
                item["last_used_at"] = stamp
                item["use_count"] = int(item.get("use_count") or 0) + 1
                hit += 1
        if hit:
            _save_all(items)
        return hit


# ── 读取 API / Read API ──────────────────────────────────────────

def list_items(
    *,
    status: str | None = None,
    namespace: str | None = None,
    kind: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    items = load_all()
    query = str(q or "").strip().lower()
    result: list[dict[str, Any]] = []
    for item in items:
        if status and item.get("status") != status:
            continue
        if namespace and item.get("namespace") != namespace:
            continue
        if kind and item.get("kind") != kind:
            continue
        if query and query not in str(item.get("text") or "").lower():
            continue
        result.append(item)
    result.sort(key=lambda it: str(it.get("recorded_at") or ""), reverse=True)
    return result


def stats() -> dict[str, int]:
    counts = {"open": 0, "closed": 0, "proposed": 0, "archived": 0,
              "deleted": 0, "total": 0}
    for item in load_all():
        counts["total"] += 1
        status = item.get("status")
        if status == "deleted":
            counts["deleted"] += 1
        elif status == "proposed":
            counts["proposed"] += 1
        elif status == "archived":
            counts["archived"] += 1
        elif status == "active" and item.get("valid_to"):
            counts["closed"] += 1
        elif status == "active":
            counts["open"] += 1
    return counts
