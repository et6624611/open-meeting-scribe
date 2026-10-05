"""
app/routers/decisions.py — 决策流跨会议聚合 / Cross-meeting decision-flow aggregation

作者：Yongliang Wang
创建：2026-09-24
版本：2.0.0

职责（DC-UNIFY-01，2026-09-27 项目方裁决）：
  决策只有一个对象——会议内的**决策流节点**（`task["todos"]`）。本模块只做一件事：
  为「决策中心」提供跨会议聚合查询（决策中心页数据源）。

  节点级写操作（改状态 / 编辑 / 删除 / 补录）统一走决策流既有的任务级端点
  `app/routers/notes.py` 的 `/api/tasks/{task_id}/todos*`，本模块不再另开一套 CRUD。

历史：v1.0.0 曾为独立的 decision 对象（`task["decisions"]`）提供任务级 CRUD 与
跨会议聚合（REQ-DECISION-CENTER R2 / DC-R2-b / DC-R2-c）。项目方裁决「只留决策流」后，
decision 对象与其端点一并下线，存量 `task["decisions"]` 不再被任何读路径消费。

契约事实源：docs/API_CONTRACTS.md §12。
旧任务 JSON 无 todos 字段一律按空数组读取（兼容性硬约束）。
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from typing import Literal

from app.store import tasks
from core.decision_flow import enrich_todo, status_of
from core.decision_status import known_ids, load_statuses
from core.decision_topic import cluster_topics
from core.i18n import _
from core.speakers import get_speaker_name_map

router = APIRouter(tags=["decisions"])


def _validate_date(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, _("Invalid date format, expected YYYY-MM-DD"))
    return value


@router.get("/api/decisions")
def list_all_decisions(
    since: str | None = Query(default=None, max_length=10),
    until: str | None = Query(default=None, max_length=10),
    kb_id: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=500),
    task_id: str | None = Query(default=None, max_length=100),
    group_by: Literal["meeting", "date", "topic"] | None = Query(default=None),
):
    """跨会议决策流聚合（决策中心数据源）/ Cross-meeting decision-flow aggregation.

    遍历内存任务表聚合（桌面单机数据量可承受，不引入数据库）。
    DC-R2-c：`status` 取值为状态字典 id（非封闭枚举）；每行附 status_name/color/closing 元信息。
    DC-UNIFY-01：数据源为 `task["todos"]`，行形状即决策流节点（text/title/assignee/why/how/outcome…）。
    DEBRISH-P2：`group_by=topic` 返回跨会议议题归并簇（全局视角）：同知识库下语义相近的
    节点聚为议题簇，主记录=最新非闭档，其余折叠为演变链；仅供展示，不改数据与写路径。
    """
    since = _validate_date(since, "since")
    until = _validate_date(until, "until")
    if status is not None and status not in known_ids():
        raise HTTPException(422, f"unknown status: {status}")

    status_meta = {s["id"]: s for s in load_statuses()}
    kb_cache: dict = {}
    try:
        owner_map = get_speaker_name_map()
    except Exception:
        owner_map = {}

    rows: list[dict] = []
    for tid, task in tasks.items():
        if task_id and tid != task_id:
            continue
        meeting_date = task.get("meeting_date")
        if since or until:
            # 日期过滤下无 meeting_date 的任务被排除 / Tasks without meeting_date are excluded when date filters apply
            if not meeting_date:
                continue
            if since and meeting_date < since:
                continue
            if until and meeting_date > until:
                continue
        project_id = task.get("project_id") or None
        if kb_id and project_id != kb_id:
            continue
        todos = task.get("todos")
        if not isinstance(todos, list):
            continue
        for node in todos:
            if not isinstance(node, dict):
                continue
            if status and status_of(node) != status:
                continue
            if q is not None:
                haystack = "\n".join([
                    str(node.get("text") or ""),
                    str(node.get("title") or ""),
                    str(node.get("why") or ""),
                ])
                if q not in haystack:
                    continue
            rows.append(enrich_todo(tid, task, node, status_meta, kb_cache, owner_map))

    # meeting_date 倒序，无日期沉底；同组内按创建时间倒序 / Newest meeting first, undated sink to the end
    rows.sort(key=lambda r: (r.get("meeting_date") or "", r.get("created_at") or ""), reverse=True)

    if not group_by:
        return {"decisions": rows, "total": len(rows)}

    # DEBRISH-P2：议题归并（全局视角）——对已过筛的平铺行做跨会议聚类
    if group_by == "topic":
        topics = cluster_topics(rows)
        return {"topics": topics, "total": len(rows), "topic_count": len(topics)}

    groups: dict[str, dict] = {}
    for row in rows:
        if group_by == "meeting":
            key = row["task_id"]
            label = row.get("meeting_title")
            meta = {"task_id": key, "meeting_date": row.get("meeting_date")}
        else:  # date
            key = row.get("meeting_date") or ""
            label = key or None
            meta = {"task_id": None, "meeting_date": key or None}
        group = groups.get(key)
        if group is None:
            group = {"key": key, "label": label, **meta, "decisions": []}
            groups[key] = group
        group["decisions"].append(row)

    return {"groups": list(groups.values()), "total": len(rows)}


def _collect_flow_rows() -> list[dict]:
    """无过滤全量聚合：全部任务的决策流节点经 enrich_todo 富化（议题归并的输入）。"""
    status_meta = {s["id"]: s for s in load_statuses()}
    kb_cache: dict = {}
    try:
        owner_map = get_speaker_name_map()
    except Exception:
        owner_map = {}
    rows: list[dict] = []
    for tid, task in tasks.items():
        todos = task.get("todos")
        if not isinstance(todos, list):
            continue
        for node in todos:
            if not isinstance(node, dict):
                continue
            rows.append(enrich_todo(tid, task, node, status_meta, kb_cache, owner_map))
    return rows


@router.get("/api/decisions/evolution")
def task_evolution(task_id: str = Query(..., max_length=100)):
    """单会议决策节点的跨会议演变归属（纪要页角标数据源）/ Per-meeting evolution membership.

    只输出跨会议议题簇（meeting_count >= 2）中属于本会议的节点：
    role=main 表示本节点即该议题最新推进；history 表示新推进发生在别的会议，
    latest 指向簇主记录（供跳转）。无跨会议归属的节点不出现在映射中。
    """
    if task_id not in tasks:
        raise HTTPException(404, _("Task not found"))

    rows = _collect_flow_rows()
    evolution: dict[str, dict] = {}
    for cluster in cluster_topics(rows):
        if cluster.get("meeting_count", 0) < 2:
            continue
        main = cluster["main"]
        members = [main, *cluster.get("history", [])]
        mine = [m for m in members if m.get("task_id") == task_id]
        if not mine:
            continue
        latest = {
            "task_id": main.get("task_id"),
            "todo_id": main.get("id"),
            "title": str(main.get("title") or "")[:200],
            "meeting_title": str(main.get("meeting_title") or "")[:200],
        }
        for node in mine:
            evolution[str(node.get("id"))] = {
                "topic_key": cluster["topic_key"],
                "topic_title": cluster.get("title") or "",
                "role": "main" if node is main else "history",
                "meeting_count": cluster["meeting_count"],
                "latest": latest,
            }
    return {"task_id": task_id, "evolution": evolution}
