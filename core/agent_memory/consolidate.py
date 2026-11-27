"""core/agent_memory/consolidate.py — 会后巩固：定稿会议 → proposed 记忆。

设计真源：docs/specs/agent-memory/spec.md §5.4 / §12 M2。
  - 只产出 proposed，需用户采纳；
  - 每条必须能回溯到 source.task_id + 逐字 quote；
  - 开关默认关，手动调用可用 force 绕过。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from core.agent_memory import schema, store

logger = logging.getLogger(__name__)

MAX_ITEMS = 5
ALLOWED_KINDS = ("fact", "decision", "preference", "glossary")
MAX_SOURCE_CHARS = 6000

_WS_RE = re.compile(r"\s+")

SYSTEM_PROMPT = (
    "你是会议记忆提炼器。只输出 JSON 数组，不要解释、不要 Markdown。"
    "数组中每项是一个对象，字段：kind、text、quote、importance、subject、relation、object。"
)

USER_TEMPLATE = """从下面的会议材料提炼最多 {max_items} 条值得跨会话记住的信息。

规则：
1. kind 只能是 fact / decision / preference / glossary。
2. text 是一句独立可读的中文短句，不超过 200 字。
3. quote 必须逐字摘自材料原文，用于回溯，不得改写。
4. importance 取 0 到 1；项目级长期事实给高值，临时约定给低值。
5. 只提炼稳定信息，不复述会议流程，不编造材料中没有的内容。
6. 没有可记内容时输出 []。

会议材料：
{material}
"""


def _norm(text: str) -> str:
    return _WS_RE.sub("", str(text or ""))


def _task_source_text(task: dict[str, Any]) -> str:
    parts: list[str] = []
    summary = str(task.get("summary") or "").strip()
    if summary:
        parts.append(summary)
    notes = task.get("user_notes")
    if isinstance(notes, str) and notes.strip():
        parts.append(f"用户随记：\n{notes.strip()}")
    decisions = task.get("decisions")
    if isinstance(decisions, list):
        lines = []
        for node in decisions:
            if not isinstance(node, dict):
                continue
            title = str(node.get("title") or "").strip()
            body = str(node.get("decision") or "").strip()
            if title or body:
                lines.append(f"- {title}：{body}" if title and body else f"- {title or body}")
        if lines:
            parts.append("决策：\n" + "\n".join(lines))
    return "\n\n".join(parts)[:MAX_SOURCE_CHARS]


def _extract_json_array(text: str) -> list[dict] | None:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return [item for item in parsed if isinstance(item, dict)]


def _namespace_for(task: dict[str, Any]) -> str:
    project_id = str(task.get("project_id") or "").strip()
    if not project_id:
        return "global"
    try:
        return schema.namespace_for("space", project_id)
    except ValueError:
        return "global"


def _already_consolidated(task_id: str) -> bool:
    for item in store.load_all():
        source = item.get("source") or {}
        if source.get("task_id") == task_id:
            return True
    return False


def consolidate_task(
    task_id: str,
    *,
    force: bool = False,
    llm: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """单场巩固。返回 {task_id, created, skipped, reason}。"""
    result: dict[str, Any] = {"task_id": task_id, "created": 0, "skipped": 0, "reason": ""}

    if not force:
        from core.settings_store import get_feature_flags
        if not get_feature_flags().get("agent_memory_consolidate", False):
            result["reason"] = "disabled"
            return result

    from core.task_store import tasks
    task = tasks.get(task_id)
    if not isinstance(task, dict):
        result["reason"] = "task_not_found"
        return result
    if not force and task.get("status") != "completed":
        result["reason"] = "not_completed"
        return result
    if _already_consolidated(task_id):
        result["reason"] = "already_consolidated"
        return result

    material = _task_source_text(task)
    if not material:
        result["reason"] = "no_source_text"
        return result

    caller = llm
    if caller is None:
        from core.llm import chat_completion
        caller = chat_completion

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(max_items=MAX_ITEMS, material=material)},
    ]
    try:
        raw = caller(messages, temperature=0.2, max_tokens=900)
    except Exception as exc:
        logger.warning("[memory] 巩固 LLM 调用失败 task=%s: %s", task_id, exc)
        result["reason"] = "llm_error"
        return result

    candidates = _extract_json_array(raw)
    if candidates is None:
        result["reason"] = "bad_json"
        return result

    namespace = _namespace_for(task)
    corpus = _norm(material)
    created = 0
    skipped = 0
    for candidate in candidates:
        if created >= MAX_ITEMS:
            break
        kind = str(candidate.get("kind") or "fact").strip()
        if kind not in ALLOWED_KINDS:
            kind = "fact"
        text = " ".join(str(candidate.get("text") or "").split())
        quote = str(candidate.get("quote") or "").strip()
        if not text or len(text) > schema.MAX_TEXT_CHARS:
            skipped += 1
            continue
        if len(_norm(quote)) < 4 or _norm(quote) not in corpus:
            skipped += 1
            continue
        item = {
            "namespace": namespace,
            "kind": kind,
            "subject": str(candidate.get("subject") or "").strip(),
            "relation": str(candidate.get("relation") or "").strip(),
            "object": str(candidate.get("object") or "").strip(),
            "text": text,
            "status": "proposed",
            "importance": schema.clamp(candidate.get("importance"), 0.5),
            "source": {"task_id": task_id, "quote": quote, "anchor": {}},
        }
        try:
            store.upsert(item, require_source=True)
            created += 1
        except store.MemoryWriteError as exc:
            logger.info("[memory] 巩固条目被拒 task=%s code=%s", task_id, exc.code)
            skipped += 1

    store.audit("consolidate", {"id": task_id}, {"created": created, "skipped": skipped})
    result["created"] = created
    result["skipped"] = skipped
    return result


def consolidate_recent(limit: int = 20) -> dict[str, int]:
    """近 limit 场已完成任务逐场巩固（遵守开关）。"""
    from core.task_store import tasks

    completed = [
        (str(task.get("created_at") or ""), task_id)
        for task_id, task in tasks.items()
        if isinstance(task, dict) and task.get("status") == "completed"
    ]
    completed.sort(reverse=True)

    summary = {"tasks": 0, "created": 0, "skipped": 0}
    for _created_at, task_id in completed[:max(1, int(limit))]:
        try:
            outcome = consolidate_task(task_id)
        except Exception as exc:
            logger.warning("[memory] 巩固异常 task=%s: %s", task_id, exc)
            continue
        if outcome.get("reason") == "disabled":
            break
        summary["tasks"] += 1
        summary["created"] += int(outcome.get("created") or 0)
        summary["skipped"] += int(outcome.get("skipped") or 0)
    return summary
