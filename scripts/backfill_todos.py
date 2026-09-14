#!/usr/bin/env python3
"""
一次性脚本：为已有会议纪要回填待办事项。 / One-off script: backfill todos for existing meeting minutes.

遍历 data/tasks/ 下所有已完成的任务 JSON，
对含 summary 但 todos 为空的任务，调用 parse_todos_from_summary() 回填。
Iterate all completed task JSONs under data/tasks/,
for tasks with summary but empty todos, call parse_todos_from_summary() to backfill.

用法 / Usage: python scripts/backfill_todos.py
"""

import json
import sys
from pathlib import Path

# 确保项目根目录在 sys.path / Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.summarize import parse_todos_from_summary

TASKS_DIR = ROOT / "data" / "tasks"


def main():
    if not TASKS_DIR.exists():
        print(f"任务目录不存在: {TASKS_DIR}")
        return

    total = 0
    backfilled = 0
    skipped_no_summary = 0
    skipped_has_todos = 0
    skipped_no_match = 0

    for task_file in sorted(TASKS_DIR.glob("*.json")):
        total += 1
        with open(task_file, "r", encoding="utf-8") as f:
            task = json.load(f)

        task_id = task.get("task_id", task_file.stem)
        status = task.get("status", "")
        summary = task.get("summary", "")
        existing_todos = task.get("todos", [])

        # 只处理已完成且有纪要的任务 / Only process completed tasks with summary
        if status != "completed":
            print(f"  跳过 {task_id[:8]}... (状态: {status})")
            continue

        if not summary:
            skipped_no_summary += 1
            print(f"  跳过 {task_id[:8]}... (无纪要)")
            continue

        if existing_todos:
            skipped_has_todos += 1
            print(f"  跳过 {task_id[:8]}... (已有 {len(existing_todos)} 条待办)")
            continue

        # 解析待办 / Parse todos
        parsed = parse_todos_from_summary(summary)
        if not parsed:
            skipped_no_match += 1
            title = task.get("title", "(无标题)")
            print(f"  无待办 {task_id[:8]}... | {title}")
            continue

        # 回填并保存 / Backfill and save
        task["todos"] = parsed
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

        backfilled += 1
        title = task.get("title", "(无标题)")
        print(f"  已回填 {task_id[:8]}... | {len(parsed)} 条待办 | {title}")
        for item in parsed:
            assignee = item.get("assignee", "")
            deadline = item.get("deadline", "")
            suffix = ""
            if assignee:
                suffix += f" @{assignee}"
            if deadline:
                suffix += f" ({deadline})"
            print(f"    - [ ] {item['text']}{suffix}")

    print("\n===== 回填完成 =====")
    print(f"扫描任务: {total}")
    print(f"成功回填: {backfilled}")
    print(f"跳过(无纪要): {skipped_no_summary}")
    print(f"跳过(已有待办): {skipped_has_todos}")
    print(f"跳过(未匹配到待办): {skipped_no_match}")


if __name__ == "__main__":
    main()
