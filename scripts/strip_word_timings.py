"""
scripts/strip_word_timings.py — 剥离转写句级词时间戳（P2 数据迁移）
Strip sentence-level word timings from persisted tasks (P2 data migration).

背景 / Background:
    sentences[].words（词级时间戳）占任务 JSON 体积约 88%，应用内无任何读取方——
    它只在转写合并阶段（core/transcribe.py merge_fragments）被消费。自本次改动起
    新转写不再落盘该字段；本脚本把存量任务一次性对齐。
    Word timings are ~88% of task JSON size and are never read after transcription;
    new transcriptions no longer persist them, this script aligns existing tasks.

安全性 / Safety:
    - 默认只预演（dry-run），不改任何文件；加 --apply 才落盘
    - 落盘走 core.fs_atomic 原子写（临时文件 + fsync + rename）
    - 幂等：已无 words 的文件直接跳过
    - 执行前请先备份 data/tasks（例：tar -czf ~/oms-tasks-backup-$(date +%Y%m%d).tar.gz data/tasks）
    Dry-run by default; --apply to write. Atomic writes, idempotent. Back up data/tasks first.

用法 / Usage:
    venv/bin/python scripts/strip_word_timings.py            # 预演 / dry-run
    venv/bin/python scripts/strip_word_timings.py --apply    # 落盘 / apply
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TASKS_DIR = ROOT / "data" / "tasks"

# 旁挂文件不是任务主体（洞察板 manifest / 洞察消息 / 书面版 sidecar）
SIDECAR_SUFFIXES = (
    ".boards.json", ".board.json", ".board.meta.json", ".insights.json", ".formal.json",
)


def is_task_file(path: Path) -> bool:
    return path.suffix == ".json" and not path.name.endswith(SIDECAR_SUFFIXES)


def strip_words(task: dict) -> int:
    """原地剔除 sentences[].words，返回删除的句子数。"""
    removed = 0
    for block in task.get("dialogue") or []:
        if not isinstance(block, dict):
            continue
        for sentence in block.get("sentences") or []:
            if isinstance(sentence, dict) and "words" in sentence:
                sentence.pop("words", None)
                removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="剥离任务 JSON 中的句级词时间戳")
    parser.add_argument("--apply", action="store_true", help="真正落盘（默认只预演）")
    parser.add_argument("--dir", default=str(TASKS_DIR), help="任务目录，默认 data/tasks")
    args = parser.parse_args()

    tasks_dir = Path(args.dir)
    if not tasks_dir.is_dir():
        print(f"[ERROR] 目录不存在: {tasks_dir}")
        return 1

    from core.fs_atomic import atomic_write_json

    files = 0
    changed_files = 0
    removed_sentences = 0
    bytes_before = 0
    bytes_after = 0

    for path in sorted(tasks_dir.glob("*.json")):
        if not is_task_file(path):
            continue
        files += 1
        size_before = path.stat().st_size
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] 跳过无法解析的文件 {path.name}: {e}")
            continue
        removed = strip_words(task)
        if not removed:
            continue
        changed_files += 1
        removed_sentences += removed
        bytes_before += size_before
        if args.apply:
            atomic_write_json(path, task)
            bytes_after += path.stat().st_size
        else:
            # 预演：只估算，不落盘 / dry-run: estimate only
            bytes_after += size_before

    print(f"任务文件: {files}  命中: {changed_files}  剔除句子: {removed_sentences}")
    if args.apply:
        saved = bytes_before - bytes_after
        print(f"落盘完成: {bytes_before/1e6:.1f} MB → {bytes_after/1e6:.1f} MB（省 {saved/1e6:.1f} MB）")
    else:
        print("预演模式，未修改任何文件；确认后加 --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
