"""core/agent_memory/inject.py — 记忆块渲染与接入帮助函数。

设计真源：docs/specs/agent-memory/spec.md §7。
  - core 块直接进 prompt，不检索；
  - archival 块按当前问题检索后注入；
  - 记忆只做背景，不与当前会议事实混。
"""

from __future__ import annotations

from typing import Any

from core.agent_memory import retrieve, schema

CORE_HEADER = "## 长期记忆·核心（常驻）"
ARCHIVAL_HEADER = "## 长期记忆·检索（与当前弱相关）"


def _enabled() -> bool:
    """feature_flags.agent_memory 总开关；设置读取失败按开启处理。"""
    try:
        from core.settings_store import get_feature_flags

        return bool(get_feature_flags().get("agent_memory", True))
    except Exception:  # noqa: BLE001
        return True


def _source_label(item: dict[str, Any]) -> str:
    source = item.get("source") or {}
    task_id = str(source.get("task_id") or "").strip()
    if not task_id:
        return "手动"
    title = ""
    date = ""
    try:
        from core.task_store import tasks

        task = tasks.get(task_id)
        if isinstance(task, dict):
            title = str(task.get("title") or task.get("audio_name") or "").strip()
            date = str(task.get("meeting_date") or task.get("created_at") or "")[:10]
    except Exception:  # noqa: BLE001 - 来源标题缺失不影响注入
        pass
    if title and date:
        return f"《{title}》{date}"
    return f"《{title}》" if title else task_id


def _line(item: dict[str, Any], *, with_source: bool) -> str:
    label = schema.KIND_LABELS.get(str(item.get("kind") or ""), "记忆")
    line = f"- [{label}] {item.get('text')}"
    if with_source:
        line += f"（来源：{_source_label(item)}）"
    return line


def render_core(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = [CORE_HEADER]
    lines.extend(_line(item, with_source=False) for item in items)
    return "\n".join(lines)


def render_archival(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = [ARCHIVAL_HEADER]
    lines.extend(_line(item, with_source=True) for item in items)
    return "\n".join(lines)


def build_blocks(
    query: str,
    *,
    task_id: str | None = None,
    space_id: str | None = None,
    role_name: str | None = None,
) -> list[str]:
    """返回本轮要注入的上下文块（core 在前，archival 在后）。"""
    if not _enabled():
        return []
    chain = schema.namespace_chain(task_id, space_id, role_name)
    core = retrieve.select_core(chain)
    core_ids = {item.get("id") for item in core}
    archival = [
        item for item in retrieve.search(query, chain)
        if item.get("id") not in core_ids
    ]
    blocks: list[str] = []
    core_block = render_core(core)
    if core_block:
        blocks.append(core_block)
    archival_block = render_archival(archival)
    if archival_block:
        blocks.append(archival_block)
    return blocks


def build_core_prompt(role_name: str | None) -> str:
    """角色级 core 块：拼在角色 AGENT.md 之后，随智能体会话全程可见。"""
    if not _enabled():
        return ""
    chain = schema.namespace_chain(None, None, role_name)
    return render_core(retrieve.select_core(chain))
