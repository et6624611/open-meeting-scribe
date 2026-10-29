#!/usr/bin/env python3
"""
一次性迁移：决策流字段改名 / One-off migration: rename the decision-flow field.

背景（DC-UNIFY-02）：决策不是 todo。项目方裁决把「待办」从产品语汇与代码标识里彻底移除，
决策流节点的承载字段随 API 一起改名：

  task["todos"]     → task["decisions"]        （决策流节点，唯一事实源）
  task["decisions"] → task["legacy_decisions"] （DC-UNIFY-01 已下线的旧 decision 记录，存档不动）

两个键在同一任务里可能并存（历史数据），迁移按原始键序逐键改写，不做合并。
Renames the decision-flow key and archives the retired decision-record key, preserving
key order and payloads; both keys may coexist in legacy task JSONs.

用法 / Usage:
  python scripts/migrate_todos_to_decisions.py           # 预演，只出报告
  python scripts/migrate_todos_to_decisions.py --apply   # 落盘
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "data" / "tasks"

# 非任务主文件（同目录下的旁挂文件）/ Non-task sidecars living in the same directory
SKIP_SUFFIXES = (".formal.json", ".insights.json", ".joblog.jsonl")


def migrate_obj(obj: dict) -> tuple[dict, bool]:
    """逐键改写，保持原始键序 / Rewrite key by key, preserving order."""
    out: dict = {}
    changed = False
    for key, value in obj.items():
        if key == "todos":
            out["decisions"] = value
            changed = True
        elif key == "decisions":
            # 旧 decision 记录与决策流同名冲突，先让位到存档键
            out["legacy_decisions"] = value
            changed = True
        else:
            out[key] = value
    return out, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正写盘 / write changes")
    args = parser.parse_args()

    files = [
        p for p in sorted(TASKS_DIR.glob("*.json"))
        if not any(p.name.endswith(s) for s in SKIP_SUFFIXES)
    ]
    stats = {"tasks": 0, "todos": 0, "decisions": 0, "both": 0, "written": 0, "error": 0}
    for path in files:
        stats["tasks"] += 1
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # 坏文件不阻断全量迁移
            stats["error"] += 1
            print(f"[skip] {path.name}: {exc}")
            continue
        if not isinstance(obj, dict):
            continue
        has_todos = "todos" in obj
        has_decisions = "decisions" in obj
        if not (has_todos or has_decisions):
            continue
        stats["todos"] += int(has_todos)
        stats["decisions"] += int(has_decisions)
        stats["both"] += int(has_todos and has_decisions)
        new_obj, changed = migrate_obj(obj)
        if not changed:
            continue
        if args.apply:
            path.write_text(
                json.dumps(new_obj, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            stats["written"] += 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] tasks={stats['tasks']} todos={stats['todos']} "
          f"decisions={stats['decisions']} both={stats['both']} "
          f"written={stats['written']} errors={stats['error']}")
    return 1 if stats["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
