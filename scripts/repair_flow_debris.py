#!/usr/bin/env python3
"""
一次性脚本：修复决策流中的"加粗碎屑"节点（DEBRISH-F1）。
One-off script: repair decision-flow nodes mangled by the pre-fix parser.

背景：core/summarize.split_decision_title 旧正则不兼容「**[待确认] 标题**：正文」写法，
且解析循环先剥外层 [待确认] 前缀再拆标题，把 `**` 标记削成碎片——受影响纪要的
auto 决策流节点呈现 title 为空、text 以 `XXX**：…` 开头的碎屑形态。
解析器已修复（2026-09-30），本脚本回填修复存量任务 JSON 中的这类节点。

策略（保守口径）：
  1. 用修复后的解析器重新解析 task 纪要（user_summary 优先），得到干净节点集
  2. 碎屑节点（source=auto、title 为空、text 含 `**`）按归一化文本匹配干净节点：
     命中 → 原地补 title/text/pending_confirmation，**保留 id/status/owner/时间戳**
     （用户已改状态/负责人的编辑不丢失）
  3. 未命中 → 不触碰，计入 needs_review（用户可能已手改文本，无法安全对应）
  4. 非碎屑节点（手动/注入/backfill、已定结论）一律不动

用法 / Usage:
  python scripts/repair_flow_debris.py            # 干跑（默认，只报告不落盘）
  python scripts/repair_flow_debris.py --apply    # 实际落盘（原子写）
报告 / Report: data/_repair_flow_debris_report.json
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path / Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.fs_atomic import atomic_write_json
from core.summarize import parse_decisions_with_status

TASKS_DIR = ROOT / "data" / "tasks"
REPORT_FILE = ROOT / "data" / "_repair_flow_debris_report.json"

# [待确认] 前缀（与解析器口径一致：兼容全角括号与加粗包裹）
_PENDING_RE = re.compile(r"^\s*(?:\*\*)?[\[【]\s*待确认\s*[\]】](?:\*\*)?\s*[:：]?\s*")


def is_debris(node: dict) -> bool:
    """碎屑形态：auto 来源、无标题、正文残留 `**`（旧解析器削掉加粗前缀的产物）。"""
    return (
        node.get("source") == "auto"
        and not (node.get("title") or "").strip()
        and "**" in (node.get("text") or "")
    )


def norm(text: str) -> str:
    """归一键：剥 markdown 强调符与 [待确认] 前缀、压空白（不区分首尾，容忍改写残留）。"""
    t = _PENDING_RE.sub("", (text or "").strip())
    t = re.sub(r"[*_`]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def repair_task(task: dict) -> tuple[int, int, list[str]]:
    """
    修复单个任务的碎屑节点，返回 (修复数, 待人工复核数, 修复摘要列表)。
    就地修改 task["todos"]；调用方决定是否落盘。
    """
    todos = [t for t in (task.get("todos") or []) if isinstance(t, dict)]
    debris = [t for t in todos if is_debris(t)]
    if not debris:
        return 0, 0, []

    summary_text = (task.get("user_summary") or "").strip() or (task.get("summary") or "").strip()
    if not summary_text:
        return 0, len(debris), []

    parsed, _ = parse_decisions_with_status(summary_text)
    # 候选池键 = 标题：正文拼接归一（碎屑节点旧 text 正是未拆分的完整条目）；
    # 同时收正文键作兑底（用户改过标题前缀但正文完整的情形），同键保留首个
    pool: dict[str, dict] = {}
    for n in parsed:
        if not n.get("title"):
            continue
        pool.setdefault(norm(f"{n['title']}：{n.get('text') or ''}"), n)
        pool.setdefault(norm(n.get("text")), n)

    fixed, review, details = 0, 0, []
    for node in debris:
        match = pool.get(norm(node.get("text")))
        if match is None:
            review += 1
            details.append(f"  needs_review: {(node.get('text') or '')[:40]}…")
            continue
        # 用户在行间编辑过正文（why 已改）：只补标题与态标记，不覆盖已定案的 why
        why_edited = node.get("why") not in (None, "", node.get("text"))
        if not why_edited:
            node["text"] = match["text"]
            node["how"] = [match["text"]]
        node["title"] = match["title"]
        node["pending_confirmation"] = match.get("pending_confirmation", False)
        node["updated_at"] = datetime.now().isoformat()
        fixed += 1
        details.append(f"  fixed: **{match['title']}** | pending={node['pending_confirmation']}"
                       + (" | why 保留用户编辑" if why_edited else ""))
    return fixed, review, details


def main() -> int:
    apply_changes = "--apply" in sys.argv
    if not TASKS_DIR.exists():
        print(f"任务目录不存在: {TASKS_DIR}")
        return 1

    report = {
        "generated_at": datetime.now().isoformat(),
        "mode": "apply" if apply_changes else "dry_run",
        "total_scanned": 0,
        "tasks_repaired": 0,
        "nodes_fixed": 0,
        "nodes_needs_review": 0,
        "tasks": [],
    }

    for task_file in sorted(TASKS_DIR.glob("*.json")):
        if task_file.name.endswith((".insights.json", ".board.meta.json", ".joblog.json")):
            continue
        report["total_scanned"] += 1
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)
        except Exception as e:
            print(f"  失败 {task_file.stem[:8]}... | JSON 解析失败: {e}")
            continue

        try:
            fixed, review, details = repair_task(task)
        except Exception as e:
            print(f"  失败 {task_file.stem[:8]}... | 修复异常: {e}")
            continue

        if not fixed and not review:
            continue
        entry = {
            "task_id": task.get("task_id", task_file.stem),
            "title": task.get("title"),
            "fixed": fixed,
            "needs_review": review,
        }
        report["tasks"].append(entry)
        report["tasks_repaired"] += 1 if fixed else 0
        report["nodes_fixed"] += fixed
        report["nodes_needs_review"] += review
        print(f"  {task_file.stem[:8]}... | {task.get('title', '?')} | 修复 {fixed} / 待复核 {review}")
        for d in details:
            print(d)

        if fixed and apply_changes:
            atomic_write_json(task_file, task)

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(REPORT_FILE, report)

    print("\n===== 碎屑节点修复完成（%s）=====" % ("已落盘" if apply_changes else "干跑，未落盘"))
    print(f"扫描任务: {report['total_scanned']}")
    print(f"修复节点: {report['nodes_fixed']}（涉及 {report['tasks_repaired']} 场会议）")
    print(f"待人工复核: {report['nodes_needs_review']}")
    print(f"报告已写入: {REPORT_FILE}")
    if not apply_changes and report["nodes_fixed"]:
        print("确认无误后执行: python scripts/repair_flow_debris.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
