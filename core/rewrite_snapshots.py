"""
core/rewrite_snapshots.py — AI 写回的字段级快照与按轮恢复
Pre-write field-level snapshots for AI write-back, with per-turn restore.

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-30
更新 / Updated: 2026-09-30
版本 / Version: 1.0.0

契约来源 / Source of truth: 智能体改写通道方案 §5.3（快照强制契约）
与 §5.4（恢复入口）。要点：
  - 写回前**强制**记录被写字段旧值（适配器作者无法跳过：统一走 `snapshot_write`）
  - per-task sidecar（JSONL 追加）：task_id / target / 旧值 / turn_id / revision / ts
  - 每个 target 保留上限 N=20 版；过期文件并入既有 `retention_days` 清理
  - **只快照 AI 写回**，用户手改不快照（否则快照点要铺到全部 task 写入路径，成本失控）
  - 快照失败不阻断业务写入，但回执带 `snapshot: false`，让"本轮不可撤销"是可见事实

target 命名（与恢复实现一一对应）：
  decision_node:<nodeId>   整节点粒度（DC-UNIFY-01 唯一对象口径，按节点 id 寻址）
  summary                  task["user_summary"] 字段级
  notes                    task["user_notes"] 字段级
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 与任务/洞察产物同一事实源目录约定（cwd 相对）
SNAPSHOT_DIR = Path("data/tasks")
SNAPSHOT_SUFFIX = ".rewrites.jsonl"

# 每 target 保留版本上限（方案建议 N=20；超出即丢弃最旧，重写 sidecar）
MAX_VERSIONS_PER_TARGET = 20

TARGET_DECISION_NODE = "decision_node"
TARGET_SUMMARY = "summary"
TARGET_NOTES = "notes"


def snapshot_path(task_id: str) -> Path:
    return SNAPSHOT_DIR / f"{task_id}{SNAPSHOT_SUFFIX}"


def decision_node_target(node_id: str) -> str:
    """决策节点 target 键（按节点 id 寻址，粒度与撤销单元一致）。"""
    return f"{TARGET_DECISION_NODE}:{node_id}"


def _read_records(task_id: str) -> list[dict]:
    """读 sidecar 全量记录；文件缺失/坏行按空处理（坏行跳过，不炸业务写入）。"""
    f = snapshot_path(task_id)
    if not f.exists():
        return []
    out: list[dict] = []
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("id"):
                out.append(rec)
    except OSError as e:
        logger.warning("[改写快照] 读取失败 %s: %s", f, e)
    return out


def _write_records(task_id: str, records: list[dict]) -> None:
    """整表原子重写（同 fs_atomic 的 tmp+replace 语义，避免半截 JSONL）。"""
    from core.fs_atomic import atomic_write_text
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    atomic_write_text(snapshot_path(task_id), body)


def snapshot_write(task_id: str, target: str, old_value, *,
                   tool: str = "", turn_id: str = "",
                   revision: int | None = None,
                   old_absent: bool = False) -> str:
    """
    落盘被写字段的旧值，返回快照 id；失败返回空串（调用方须在回执标注不可撤销）。

    `old_absent=True` 表示该字段/节点此前不存在（如 inject 新建节点），
    恢复语义 = 撤销创建（删掉节点 / 移除字段），而非写回空值。
    """
    if not task_id or not target:
        return ""
    rec = {
        "id": str(uuid.uuid4()),
        "task_id": task_id,
        "target": target,
        "old": old_value,
        "old_absent": bool(old_absent),
        "tool": tool,
        "turn_id": turn_id or "",
        "revision": revision,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        records = _read_records(task_id)
        same_total = sum(1 for r in records if r.get("target") == target)
        if same_total + 1 > MAX_VERSIONS_PER_TARGET:
            # 超保留上限：整表原子重写并裁掉该 target 的最旧若干版
            records.append(rec)
            same = [r for r in records if r.get("target") == target]
            drop = {r["id"] for r in same[:-MAX_VERSIONS_PER_TARGET]}
            _write_records(task_id, [r for r in records if r.get("id") not in drop])
        else:
            # 常规路径：追写一行（append-only 成本最低，不需读全表）
            with snapshot_path(task_id).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
    except Exception as e:  # noqa: BLE001 - 快照失败不阻断写回，但必须留痕
        logger.error("[改写快照] 写入失败 task=%s target=%s: %s", task_id, target, e)
        return ""
    return str(rec["id"])


def list_snapshots(task_id: str, *, target: str | None = None,
                   turn_id: str | None = None) -> list[dict]:
    """按时间正序返回快照记录，可按 target / turn_id 过滤。"""
    recs = _read_records(task_id)
    if target:
        recs = [r for r in recs if r.get("target") == target]
    if turn_id:
        recs = [r for r in recs if r.get("turn_id") == turn_id]
    return recs


def latest_snapshot(task_id: str, target: str) -> dict | None:
    """指定 target 的最近一次快照（恢复的默认目标）。"""
    recs = list_snapshots(task_id, target=target)
    return recs[-1] if recs else None


def describe_change(rec: dict) -> str:
    """人类可读的一行变更描述（供前端"本轮改了什么"呈现，不含正文全文）。"""
    target = str(rec.get("target") or "")
    if target.startswith(f"{TARGET_DECISION_NODE}:"):
        node_id = target.split(":", 1)[1]
        old = rec.get("old")
        if isinstance(old, dict):
            title = (old.get("title") or old.get("text") or "")[:24]
            return f"决策节点「{title}」（原状态 {old.get('status') or '—'}）"
        if rec.get("old_absent"):
            return f"新建决策节点 {node_id[:8]}"
        return f"决策节点 {node_id[:8]}"
    label = {TARGET_SUMMARY: "会议纪要", TARGET_NOTES: "会议随记"}.get(target, target)
    return f"{label}"


def apply_restore(task: dict, rec: dict) -> tuple[bool, str]:
    """
    把一条快照的旧值写回内存 task 对象（**不落盘**，由调用方 save_task_to_disk）。

    返回 (是否变更, 说明)。task 需为可原地修改的 dict（与 app.store.tasks 同一对象）。
    """
    target = str(rec.get("target") or "")
    old = rec.get("old")
    absent = bool(rec.get("old_absent"))

    if target.startswith(f"{TARGET_DECISION_NODE}:"):
        node_id = target.split(":", 1)[1]
        todos = task.get("todos")
        if not isinstance(todos, list):
            todos = []
            task["todos"] = todos
        idx = next((i for i, t in enumerate(todos)
                    if isinstance(t, dict) and t.get("id") == node_id), -1)
        if absent:
            # 撤销创建：节点应不存在
            if idx < 0:
                return False, "节点已不存在，无需恢复"
            task["todos"] = [t for t in todos if not (isinstance(t, dict) and t.get("id") == node_id)]
            return True, "已撤销该节点的创建"
        if not isinstance(old, dict):
            return False, "快照内容不可用"
        if idx >= 0:
            task["todos"][idx] = old
        else:
            task["todos"].append(old)
        return True, "已恢复节点到改写前"

    if target == TARGET_SUMMARY:
        if absent:
            task.pop("user_summary", None)
            return True, "已回到未编辑纪要之前"
        task["user_summary"] = old if isinstance(old, str) else ""
        return True, "已恢复纪要"

    if target == TARGET_NOTES:
        if absent:
            task.pop("user_notes", None)
            return True, "已回到随记为空之前"
        task["user_notes"] = old if isinstance(old, str) else ""
        return True, "已恢复随记"

    return False, f"未知快照目标：{target}"


def restore_task(task_id: str, *, snapshot_id: str | None = None,
                 turn_id: str | None = None) -> dict:
    """
    恢复入口（供路由与工具面共用）：按 snapshot_id 单点恢复，或按 turn_id 逆序整轮回滚。

    走 tasks 内存对象 + save_task_to_disk + 脏标记，与 notes 路由同一落盘口径。
    恢复本身**不再产生快照**（回滚是纠错动作，不是 AI 改写；再快照会让撤销无限套娃）。
    """
    from app.store import save_task_to_disk, tasks

    if not task_id or task_id not in tasks:
        return {"ok": False, "error": "task_not_found", "message": "会议任务不存在"}
    task = tasks[task_id]

    if snapshot_id:
        recs = [r for r in list_snapshots(task_id) if r.get("id") == snapshot_id]
        if not recs:
            return {"ok": False, "error": "snapshot_not_found", "message": "快照不存在或已过期"}
        targets = [(recs[0], snapshot_id)]
    elif turn_id:
        recs = list_snapshots(task_id, turn_id=turn_id)
        if not recs:
            return {"ok": False, "error": "turn_not_found", "message": "本轮没有可撤销的改写"}
        # 逆序回滚：后发生的写先撤销，节点级才不会互相覆盖
        targets = [(r, str(r.get("id") or "")) for r in reversed(recs)]
    else:
        return {"ok": False, "error": "missing_target", "message": "需要 snapshot_id 或 turn_id"}

    applied: list[str] = []
    skipped: list[str] = []
    for rec, sid in targets:
        changed, note = apply_restore(task, rec)
        (applied if changed else skipped).append(f"{describe_change(rec)}：{note}")
    if not applied:
        return {"ok": False, "error": "nothing_to_restore",
                "message": "数据已是快照前状态", "skipped": skipped}

    task["last_modified_at"] = datetime.now().isoformat()
    save_task_to_disk(task_id)
    logger.info("[改写快照] 恢复 task=%s 条目=%d", task_id, len(applied))
    return {"ok": True, "restored": len(applied), "detail": applied, "skipped": skipped}


def sweep_expired_snapshots(retention_days: int) -> int:
    """按 mtime 清理过期 sidecar（与智能体工作区同一保留期口径，R7）。"""
    if not retention_days or retention_days <= 0 or not SNAPSHOT_DIR.is_dir():
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for f in SNAPSHOT_DIR.glob(f"*{SNAPSHOT_SUFFIX}"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("[改写快照] 过期快照清理 %d 个（保留 %d 天）", removed, retention_days)
    return removed
