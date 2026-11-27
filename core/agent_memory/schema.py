"""core/agent_memory/schema.py — 记忆条目结构、namespace 解析与校验。

设计真源：docs/specs/agent-memory/spec.md §3 / §4 / §4.3。
  - 两条通道：core（常驻）/ archival（检索），由 retrieve 决定，不在条目上落字段。
  - 三层内容：L1 情节（task）/ L2 语义（space、global）/ L3 画像（role、global）。
  - namespace 是强制前缀，不接受自由字符串。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

KINDS = ("preference", "fact", "decision", "correction", "habit", "glossary")
KIND_LABELS = {
    "preference": "偏好",
    "fact": "事实",
    "decision": "决策",
    "correction": "纠正",
    "habit": "习惯",
    "glossary": "术语",
}

STATUSES = ("proposed", "active", "archived", "deleted")

NS_KINDS = ("task", "space", "role", "global")
# 检索链权重：task → space → role → global（spec §4.3）
SCOPE_WEIGHTS = {"task": 1.0, "space": 0.8, "role": 0.7, "global": 0.5}

# 单条正文上限（spec §5.4 / §11.2）
MAX_TEXT_CHARS = 200

_NS_ID_RE = re.compile(r"^[^\s/:]{1,128}$")


def now_iso() -> str:
    """本地时区 ISO 时间，秒级。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    """本地日期 YYYY-MM-DD。"""
    return datetime.now().astimezone().date().isoformat()


def new_id() -> str:
    return f"mem_{uuid.uuid4().hex[:12]}"


def parse_namespace(namespace: str) -> dict[str, str]:
    """解析 namespace，非法直接抛 ValueError。

    global / task:<id> / space:<id> / role:<slug>
    """
    raw = str(namespace or "").strip()
    if raw == "global":
        return {"kind": "global", "id": ""}
    head, sep, tail = raw.partition(":")
    if not sep or head not in NS_KINDS:
        raise ValueError(f"bad_namespace: {namespace}")
    if head == "global" or not _NS_ID_RE.match(tail):
        raise ValueError(f"bad_namespace: {namespace}")
    return {"kind": head, "id": tail}


def namespace_for(kind: str, ident: str | None = None) -> str:
    if kind == "global":
        return "global"
    if kind not in NS_KINDS:
        raise ValueError(f"bad_namespace_kind: {kind}")
    if not ident or not _NS_ID_RE.match(str(ident)):
        raise ValueError(f"bad_namespace_id: {ident}")
    return f"{kind}:{ident}"


def namespace_chain(
    task_id: str | None = None,
    space_id: str | None = None,
    role_name: str | None = None,
) -> list[dict[str, Any]]:
    """构建检索作用域链，顺序 task → space → role → global。"""
    chain: list[dict[str, Any]] = []
    for kind, ident in (("task", task_id), ("space", space_id), ("role", role_name)):
        if not ident:
            continue
        try:
            ns = namespace_for(kind, ident)
        except ValueError:
            # 非法 id 不阻断检索，跳过该层
            continue
        chain.append({"namespace": ns, "kind": kind, "id": ident,
                      "weight": SCOPE_WEIGHTS[kind]})
    chain.append({"namespace": "global", "kind": "global", "id": "",
                  "weight": SCOPE_WEIGHTS["global"]})
    return chain


def clamp(value: object, default: float = 0.5) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, num))


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """补齐默认值并校验；不合法抛 ValueError，调用方负责拒收。"""
    if not isinstance(item, dict):
        raise ValueError("item_not_object")

    text = " ".join(str(item.get("text") or "").split())
    if not text:
        raise ValueError("text_required")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"text_too_long: {len(text)} > {MAX_TEXT_CHARS}")

    namespace = str(item.get("namespace") or "").strip()
    parse_namespace(namespace)

    kind = str(item.get("kind") or "fact").strip()
    if kind not in KINDS:
        raise ValueError(f"bad_kind: {kind}")

    status = str(item.get("status") or "active").strip()
    if status not in STATUSES:
        raise ValueError(f"bad_status: {status}")

    tags = item.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]
    clean_tags = []
    for tag in tags:
        value = str(tag or "").strip()
        if value and value not in clean_tags:
            clean_tags.append(value)

    source = item.get("source")
    if source is not None:
        if not isinstance(source, dict):
            raise ValueError("bad_source")
        source = dict(source)

    recorded_at = str(item.get("recorded_at") or "").strip() or now_iso()
    valid_from = str(item.get("valid_from") or "").strip() or recorded_at[:10]
    valid_to = item.get("valid_to")
    valid_to = str(valid_to).strip() if valid_to else None

    normalized = {
        "id": str(item.get("id") or new_id()),
        "namespace": namespace,
        "kind": kind,
        "subject": str(item.get("subject") or "").strip(),
        "relation": str(item.get("relation") or "").strip(),
        "object": str(item.get("object") or "").strip(),
        "text": text,
        "tags": clean_tags,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "time_confidence": str(item.get("time_confidence") or "high"),
        "recorded_at": recorded_at,
        "source": source,
        "status": status,
        "invalidated_by": item.get("invalidated_by"),
        "importance": clamp(item.get("importance"), 0.5),
        "confidence": clamp(item.get("confidence"), 0.8),
        "last_used_at": item.get("last_used_at"),
        "use_count": int(item.get("use_count") or 0),
        "embedding_ref": item.get("embedding_ref"),
    }
    if normalized["time_confidence"] not in ("high", "low"):
        normalized["time_confidence"] = "high"
    return normalized


def has_source(item: dict[str, Any]) -> bool:
    """写入必须可回溯：task_id + quote 齐备。"""
    source = item.get("source") or {}
    return bool(str(source.get("task_id") or "").strip()
                and str(source.get("quote") or "").strip())


def is_open(item: dict[str, Any], as_of: str | None = None) -> bool:
    """开放边判定；带 as_of 时按有效期双时间轴过滤。"""
    if item.get("status") != "active":
        return False
    valid_from = str(item.get("valid_from") or "")
    valid_to = item.get("valid_to")
    if as_of:
        if valid_from and valid_from > as_of:
            return False
        return not valid_to or str(valid_to) > as_of
    return not valid_to
