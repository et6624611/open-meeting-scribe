#!/usr/bin/env python3
"""
一次性脚本：为存量会议纪要回填决策项。 / One-off script: backfill decisions for existing meeting minutes.

遍历 data/tasks/ 下所有任务 JSON，解析 user_summary（优先）或 summary 的
「主要结论」/「决策」章节（RF-1 双章节合并去重）→ 写入 task["decisions"]（source=backfill）。
Iterate all task JSONs under data/tasks/, parse the "主要结论" / "决策" sections of
user_summary (preferred) or summary into task["decisions"] with source=backfill.

幂等：任务已有非空 decisions 或存在 decisions_backfilled_at 标记则跳过；
解析降级（章节缺失/无条目）不写标记、计入失败清单，修正纪要后可重跑。
Idempotent: tasks with existing decisions or a decisions_backfilled_at marker
are skipped; degraded parses are reported as failures without the marker so a
corrected summary can be re-run.

用法 / Usage: python scripts/backfill_decisions.py
报告 / Report: data/_backfill_report.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path / Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.summarize import parse_decisions_with_status

TASKS_DIR = ROOT / "data" / "tasks"
REPORT_FILE = ROOT / "data" / "_backfill_report.json"

_REASON_BY_STATUS = {
    "missing_section": "纪要缺少「主要结论」/「决策」章节",
    "no_items": "「主要结论」/「决策」章节未解析出任何条目（格式异常）",
}


def _mark_backfilled(task: dict) -> None:
    task["decisions_backfilled_at"] = datetime.now().isoformat()


def backfill_task(task: dict) -> tuple[str, int, str]:
    """
    处理单个任务，返回 (结果类别, 回填条数, 失败原因)。
    Process one task; returns (category, added_count, failure_reason).
    """
    if task.get("decisions"):
        return "skipped_has_decisions", 0, ""
    if task.get("decisions_backfilled_at"):
        return "skipped_already_backfilled", 0, ""
    if task.get("status") != "completed":
        return "skipped_incomplete", 0, ""

    summary_text = (task.get("user_summary") or "").strip() or (task.get("summary") or "").strip()
    if not summary_text:
        return "skipped_no_summary", 0, ""

    decisions, parse_status = parse_decisions_with_status(summary_text)
    if parse_status:
        return "failed", 0, _REASON_BY_STATUS.get(parse_status, parse_status)

    if decisions:
        # 回填标记为 backfill 来源 / Tag backfilled items
        for item in decisions:
            item["source"] = "backfill"
        task["decisions"] = decisions
        _mark_backfilled(task)
        return "backfilled", len(decisions), ""

    # 阴性说明/正常空结果：写标记避免重复处理，但不新增条目
    _mark_backfilled(task)
    return "marked_empty", 0, ""


def main() -> int:
    if not TASKS_DIR.exists():
        print(f"任务目录不存在: {TASKS_DIR}")
        return 1

    report = {
        "generated_at": datetime.now().isoformat(),
        "total_scanned": 0,
        "backfilled": 0,
        "decisions_added": 0,
        "marked_empty": 0,
        "skipped_has_decisions": 0,
        "skipped_already_backfilled": 0,
        "skipped_incomplete": 0,
        "skipped_no_summary": 0,
        "failed": [],
    }

    for task_file in sorted(TASKS_DIR.glob("*.json")):
        report["total_scanned"] += 1
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)
        except Exception as e:
            report["failed"].append({"task_id": task_file.stem, "title": None, "reason": f"JSON 解析失败: {e}"})
            print(f"  失败 {task_file.stem[:8]}... | JSON 解析失败: {e}")
            continue

        task_id = task.get("task_id", task_file.stem)
        title = task.get("title", "(无标题)")
        try:
            category, added, reason = backfill_task(task)
        except Exception as e:
            report["failed"].append({"task_id": task_id, "title": title, "reason": f"解析异常: {e}"})
            print(f"  失败 {task_id[:8]}... | 解析异常: {e}")
            continue

        if category == "failed":
            report["failed"].append({"task_id": task_id, "title": title, "reason": reason})
            print(f"  失败 {task_id[:8]}... | {title} | {reason}")
            continue

        if category in ("backfilled", "marked_empty"):
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(task, f, ensure_ascii=False, indent=2)

        if category == "backfilled":
            report["backfilled"] += 1
            report["decisions_added"] += added
            print(f"  已回填 {task_id[:8]}... | {added} 条决策 | {title}")
            for item in task.get("decisions", []):
                pending = " [待确认]" if item.get("pending_confirmation") else ""
                print(f"    - {item['text']}{pending}")
        elif category == "marked_empty":
            report["marked_empty"] += 1
            print(f"  无决策 {task_id[:8]}... | {title}（已标记回填）")
        else:
            report[category] += 1
            print(f"  跳过 {task_id[:8]}... | {category.replace('_', ' ')}")

    report["failure_count"] = len(report["failed"])

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n===== 决策回填完成 =====")
    print(f"扫描任务: {report['total_scanned']}")
    print(f"成功回填: {report['backfilled']}（新增决策 {report['decisions_added']} 条）")
    print(f"标记无决策: {report['marked_empty']}")
    print(f"跳过(已有决策): {report['skipped_has_decisions']}")
    print(f"跳过(已回填过): {report['skipped_already_backfilled']}")
    print(f"跳过(未完成): {report['skipped_incomplete']}")
    print(f"跳过(无纪要): {report['skipped_no_summary']}")
    print(f"失败: {report['failure_count']}")
    print(f"报告已写入: {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
