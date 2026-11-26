"""确定性统计（白名单聚合） / Deterministic aggregation over the eligible collection

背景（context-asset-management R1 §5.2）：「命中几场 / 多少待决策」这类明确统计问题
曾由模型在复述上下文时外推甚至编造。R1 把统计意图识别与计算收归后端：
仅识别明确数量句式，白名单内直接计算，结果写入 ``verified_facts``，
模型只能原值引用，不得据此换算或外推。

约束：
  - 仅 ``scope=all`` 生效；不调用 LLM
  - 复用 ``core.meeting_search._eligible_tasks`` 与时间/项目过滤，不另立口径
  - 不经过 IDF、相关度阈值、limit 或注入预算
  - 聚合失败抛异常，由调用方整体置 ``status="error"``，绝不返回默认 0
"""

from __future__ import annotations

import re

from core.decision_flow import status_of
from core.decision_status import load_statuses
from core.meeting_search import (
    _eligible_tasks,
    _filter_candidates,
    _public_filters,
    _resolve_project_filter,
)
from core.time_query import parse_time_range

# 明确数量句式：只有这些词才产生聚合意图
_COUNT_RE = re.compile(
    r"几场|多少场|多少次会|多少次会议?|多少个会议|多少会议|"
    r"多少条决策|多少项决策|多少决策|多少条待决策|多少待决策|"
    r"多少已替代|多少条已替代|几条决策|几个决策"
)
# 同时要求数量与内容 → mixed；两条路径分别执行
_CONTENT_RE = re.compile(r"有哪些|哪些|什么|怎么|如何|谁|列出|清单|名单|关键|详情|内容|分别|讨论|涉及")

_DECISION_RE = re.compile(r"决策|待决策|待办|已替代|议题")

_STATUS_KEYWORDS = (
    (re.compile(r"已替代|被替代"), "superseded"),
    (re.compile(r"待决策|待确认|待办|未定"), "to_decide"),
    (re.compile(r"已存档|已完成|闭档|已定案"), "done"),
    (re.compile(r"进行中"), "in_progress"),
)
_GROUP_BY_RE = re.compile(r"各状态|按状态|状态分布|分别按状态|状态各自")

_UNIT = {"meeting_count": "meeting", "decision_count": "decision"}


def classify_query(query: str) -> str:
    """查询路由：retrieval / aggregate / mixed（规则实现，不调用 LLM）。"""
    text = str(query or "")
    has_count = bool(_COUNT_RE.search(text))
    has_content = bool(_CONTENT_RE.search(text))
    if has_count and has_content:
        return "mixed"
    if has_count:
        return "aggregate"
    return "retrieval"


def aggregate_kind(query: str) -> str:
    """白名单聚合种类：meeting_count / decision_count。"""
    return "decision_count" if _DECISION_RE.search(query or "") else "meeting_count"


def _status_filter(query: str) -> str | None:
    for pattern, status_id in _STATUS_KEYWORDS:
        if pattern.search(query or ""):
            return status_id
    return None


def _status_names() -> tuple[list[str], dict[str, str]]:
    statuses = load_statuses()
    order = [str(s.get("id")) for s in statuses if isinstance(s, dict)]
    names = {str(s.get("id")): str(s.get("name") or s.get("id")) for s in statuses if isinstance(s, dict)}
    return order, names


def _fact_base(time_range: dict, filters: dict | None) -> dict:
    if time_range.get("kind") == "range":
        time_value = f"{time_range.get('start')}..{time_range.get('end')}"
        label = time_range.get("label") or time_value
    else:
        time_value, label = "none", "未限定"
    return {
        "status": "ok",
        "time_range": time_value,
        "time_label": label,
        "filters": _public_filters(filters),
    }


def aggregate_from(
    query: str,
    eligible: list[tuple[str, dict]],
    time_range: dict,
    filters: dict | None,
) -> list[dict]:
    """在已构建的可检索集合上做白名单聚合。

    聚合包含符合条件的本场会议（调用方不传 exclude），不受 matched=0、
    limit=1 或注入预算影响。任何异常向上抛，由调用方置 status=error。
    """
    base = _fact_base(time_range, filters)
    # 聚合不排除本场：candidates 即符合时间/项目过滤的全部可访问会议
    candidates, _undated = _filter_candidates(eligible, time_range, filters, None)
    kind = aggregate_kind(query)

    if kind == "meeting_count":
        return [{
            "kind": "meeting_count",
            "value": len(candidates),
            "unit": _UNIT[kind],
            **base,
        }]

    order, names = _status_names()
    status_id = _status_filter(query)
    group_by = bool(_GROUP_BY_RE.search(query or ""))

    nodes: list[str] = []
    for _task_id, task in candidates:
        for node in task.get("decisions") or []:
            if isinstance(node, dict) and str(node.get("text") or "").strip():
                nodes.append(status_of(node))

    if status_id and not group_by:
        value = sum(1 for sid in nodes if sid == status_id)
        return [{
            "kind": "decision_count",
            "value": value,
            "unit": _UNIT[kind],
            **base,
        }]

    if group_by:
        counts: dict[str, int] = {sid: 0 for sid in order}
        for sid in nodes:
            counts[sid] = counts.get(sid, 0) + 1
        # 字典外历史值不隐藏，排在已知状态之后
        for sid in nodes:
            counts.setdefault(sid, 0)
        groups = [
            {"status": sid, "status_name": names.get(sid, sid), "value": value}
            for sid, value in counts.items()
        ]
        return [{
            "kind": "decision_count",
            "value": sum(counts.values()),
            "unit": _UNIT[kind],
            "groups": groups,
            **base,
        }]

    return [{
        "kind": "decision_count",
        "value": len(nodes),
        "unit": _UNIT[kind],
        **base,
    }]


def aggregate_facts(
    query: str,
    *,
    time_range: dict | None = None,
    filters: dict | None = None,
    access_context: dict | None = None,
    now=None,
) -> list[dict]:
    """独立调用入口：自行构建可检索集合并聚合（供测试与外部调用）。"""
    eligible = _eligible_tasks(access_context)
    if time_range is None:
        time_range = parse_time_range(query, now)
    if filters is None:
        filters = _resolve_project_filter(query)
    return aggregate_from(query, eligible, time_range, filters)
