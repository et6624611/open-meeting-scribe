"""
core/decision_flow.py — 决策流（唯一决策对象）的共享读写口径
                     Shared read/write helpers for the unified decision flow

作者：Yongliang Wang
创建：2026-09-27
版本：1.0.0

背景（DC-UNIFY-01）：项目方裁决「决策」只有一个对象——会议内的决策流节点
（`task["todos"]`）。原 `task["decisions"]`（decision 记录）与其只读展示区一并下线，
本模块把过去分散在 `app/routers/decisions.py` / `notes.py` 的口径收敛为单一事实源：

  1. `resolve_owner`：执行人以说话人档案为权威（id 可解析则跟随档案名，改名全局生效），
     档案缺失时宽容回退快照名，不阻断写入
  2. `status_of`：读取节点状态，缺省由旧 `done` 布尔推导（兼容无 status 的历史 task JSON）
  3. `first_open_status`：状态回落用的开放态（字典可能被用户删改，不能写死 id）
  4. `make_todo_node`：新建决策流节点的统一形状（纪要页手动添加 / AI 注入 / 决策中心补录共用）
  5. `enrich_todo`：聚合读侧随行下发状态字典与会议/知识库元信息，前端不再写死枚举

契约事实源：docs/API_CONTRACTS.md §12。
"""

import uuid
from datetime import datetime

from core.decision_status import DEFAULT_STATUS_ID, load_statuses
from core.speakers import get_speaker_name_map, normalize_speaker_name

# 自动解析/AI 注入产生的节点默认态：待决策（项目方裁决：自动生成但不擅自定案）
AUTO_STATUS_ID = "to_decide"
# 手动添加产生的节点默认态
MANUAL_STATUS_ID = DEFAULT_STATUS_ID


def resolve_owner(owner_id: object, snapshot: object) -> tuple[str | None, str]:
    """执行人以说话人档案为权威：id 可解析则取档案名，否则回退快照名。

    档案不存在/被删时不报错——建档与提交之间的并发删除不应阻断写入。
    返回 (owner_id 或 None, 快照名)。
    """
    oid = owner_id.strip() if isinstance(owner_id, str) else ""
    name = snapshot.strip() if isinstance(snapshot, str) else ""
    if oid:
        try:
            archived = get_speaker_name_map().get(oid)
        except Exception:
            archived = None
        if archived:
            # 占位档案名（Speaker N 等）不当执行人（REQ-SPK-RN 口径同源）
            return oid, normalize_speaker_name(archived) or name
    return (oid or None), name


def owner_display(node: dict, name_map: dict[str, str]) -> str:
    """读侧执行人展示名：有档案 id 取档案名（改名全局跟随），否则回退快照。"""
    oid = node.get("owner_id")
    if isinstance(oid, str) and oid:
        archived = name_map.get(oid)
        if archived:
            return normalize_speaker_name(archived) or str(node.get("assignee") or "")
    snapshot = node.get("assignee")
    return str(snapshot) if isinstance(snapshot, str) else ""


def status_of(node: dict) -> str:
    """节点状态：显式 status 优先，缺省由旧 done 布尔推导（历史 task JSON 兼容）。"""
    sid = node.get("status")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    return "done" if node.get("done") else MANUAL_STATUS_ID


def first_open_status() -> str:
    """回落/重置用的开放态：取字典中第一个非闭档状态，全闭档时退到完成态。

    状态字典可被用户改名/删除/重排，因此不能写死某个 id。
    """
    statuses = load_statuses()
    for s in statuses:
        if not s["closing"]:
            return s["id"]
    return statuses[-1]["id"] if statuses else MANUAL_STATUS_ID


def make_todo_node(
    text: str,
    *,
    assignee: str = "",
    owner_id: str | None = None,
    title: str = "",
    why: str = "",
    source: str = "manual",
    status: str | None = None,
    owner_type: str = "self",
    node_id: str | None = None,
    extra: dict | None = None,
) -> dict:
    """构造一条决策流节点（纪要页/注入/补录共用同一形状）。

    `how` 初始为 [text] 是决策流面板的既有约定（路径首条即标题），保持不变。
    """
    now = datetime.now().isoformat()
    oid, owner_name = resolve_owner(owner_id, assignee)
    node = {
        "id": node_id or str(uuid.uuid4()),
        "title": (title or "").strip(),
        "text": text,
        "assignee": owner_name,
        "owner_id": oid,
        "done": False,
        "source": source,
        "status": status or (AUTO_STATUS_ID if source == "auto" or source == "injection" else MANUAL_STATUS_ID),
        "how": [text],
        "owner_type": owner_type or "self",
        "created_at": now,
        "updated_at": now,
    }
    if why and why.strip():
        node["why"] = why.strip()
    if extra:
        node.update(extra)
    return node


def enrich_todo(
    task_id: str,
    task: dict,
    node: dict,
    status_meta: dict[str, dict],
    kb_cache: dict,
    owner_map: dict[str, str],
) -> dict:
    """聚合读侧：节点 + 状态字典元信息 + 会议/知识库上下文，前端配置驱动渲染。

    字典外的历史 status 值按 `first_open_status()` 降级展示，不抛错（数据诚实）。
    """
    sid = status_of(node)
    meta = status_meta.get(sid)
    if meta is None:
        sid = first_open_status()
        meta = status_meta.get(sid) or {}
    project_id = task.get("project_id") or None
    closing = bool(meta.get("closing", False))
    return {
        **node,
        "status": sid,
        "status_name": meta.get("name") or sid,
        "status_name_en": meta.get("name_en") or sid,
        "status_color": meta.get("color") or "var(--muted)",
        "status_closing": closing,
        "assignee": owner_display(node, owner_map),
        # 旧字段兼容：只认布尔的读侧（导出/第三方）继续看 done
        "done": bool(node.get("done")) or closing,
        "task_id": task_id,
        "meeting_title": task.get("title") or task.get("audio_name") or task_id,
        "meeting_date": task.get("meeting_date"),
        "kb_id": project_id,
        "kb_name": _kb_name(project_id, kb_cache),
    }


def _kb_name(project_id: str | None, cache: dict) -> str | None:
    """知识库名解析（带调用内缓存，聚合数百条时不重复读盘）。"""
    if not project_id:
        return None
    if project_id not in cache:
        try:
            from core.projects import get_project
            cache[project_id] = (get_project(project_id) or {}).get("name")
        except Exception:
            cache[project_id] = None
    return cache[project_id]
