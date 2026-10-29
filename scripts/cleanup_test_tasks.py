"""
scripts/cleanup_test_tasks.py — 清理会议库中遗留的测试垃圾任务 / Cleanup leftover test-artifact tasks from the meeting library

背景 / Background:
    历史版本的测试用例（retry-summary / retranscribe / 洞察 / 文本修正等）经 save_task_to_disk
    把测试任务 JSON 写进了真实的 data/tasks/（相对路径未做会话隔离），导致会议库出现大量
    audio_name="test.wav"、title="会议记录" 的垃圾条目，删除后下次跑测试又会重生。
    现 tests/conftest.py 已增加 TASKS_DIR 会话隔离（治本）；本脚本负责清理历史遗留（治标）。

判定特征 / Detection features（命中任一即视为测试垃圾）:
    - audio_name == "test.wav"
    - audio_path 含 "pytest-"（pytest 临时目录，如 /private/var/.../pytest-of-xxx/pytest-12/...）
    - audio_path 含 "/nonexistent/"（用例构造的不存在路径）

安全护栏 / Safety:
    - 默认 dry-run，仅打印将被删除的清单；加 --apply 才真正删除。
    - 标题为「会议记录」但音频路径指向 data/recordings/ 或 data/uploads/ 的真实业务数据，
      不含上述测试特征 → 一律保留，绝不误删。
    - 删除任务主体 {id}.json 时，一并清理同前缀的旁路文件
      {id}.joblog.jsonl / {id}.insights.json / {id}.board.json / {id}.boards.json
      / {id}.board.html / {id}.board.<board_id>.html（多板形态按 glob 展开）。

用法 / Usage:
    venv/bin/python scripts/cleanup_test_tasks.py            # 预览（dry-run） / Preview
    venv/bin/python scripts/cleanup_test_tasks.py --apply    # 实际删除 / Actually delete
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "data" / "tasks"

# 测试垃圾判定关键词 / Test-artifact markers within audio_path
AUDIO_PATH_MARKERS = ("pytest-", "/nonexistent/")
TEST_AUDIO_NAMES = ("test.wav",)
# 随任务主体一并清理的旁路文件后缀 / Sidecar suffixes removed alongside the task body
# 多板后板文件形态为 `<id>.board.<board_id>.html` + manifest `<id>.boards.json`，
# 固定后缀已盖不住，由 collect_sidecars 按前缀 glob 补全。
SIDECAR_SUFFIXES = (".joblog.jsonl", ".insights.json", ".board.json", ".board.html",
                    ".board.meta.json", ".boards.json")
# 仅以这些旁路为入口扫描会误判任务主体的形态（不是任务本体）
NON_TASK_BODY_SUFFIXES = (".joblog.jsonl", ".insights.json", ".board.json", ".boards.json")


def collect_sidecars(task_id: str) -> list[Path]:
    """列出该任务的全部旁路文件（含多板形态）/ List every sidecar of a task id."""
    found: list[Path] = []
    for suf in SIDECAR_SUFFIXES:
        p = TASKS_DIR / f"{task_id}{suf}"
        if p.exists():
            found.append(p)
    # 多板 HTML：<task_id>.board.<board_id>.html（glob 形态，不靠 board_id 枚举）
    found.extend(p for p in sorted(TASKS_DIR.glob(f"{task_id}.board.*.html")) if p not in found)
    return found


def is_test_artifact(task: dict) -> tuple[bool, str]:
    """判断任务是否为测试垃圾，返回 (是否, 命中的原因)。/ Whether the task is a test artifact and the matched reason."""
    audio_name = (task.get("audio_name") or "").strip().lower()
    if audio_name in TEST_AUDIO_NAMES:
        return True, f"audio_name={task.get('audio_name')!r}"

    audio_path = task.get("audio_path") or ""
    for marker in AUDIO_PATH_MARKERS:
        if marker in audio_path:
            return True, f"audio_path 含 {marker!r}"

    return False, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="清理 data/tasks 中遗留的测试垃圾任务")
    parser.add_argument("--apply", action="store_true", help="实际执行删除（默认仅 dry-run 预览）")
    args = parser.parse_args()

    if not TASKS_DIR.exists():
        print(f"[跳过] 目录不存在：{TASKS_DIR}")
        return 0

    to_delete: list[tuple[Path, str]] = []
    kept_placeholder = 0  # 标题「会议记录」但属真实业务数据，予以保留
    total = 0

    for task_file in sorted(TASKS_DIR.glob("*.json")):
        # 排除旁路文件（只以任务主体为入口） / Skip sidecar files (iterate on task bodies only)
        if any(task_file.name.endswith(suf) for suf in NON_TASK_BODY_SUFFIXES):
            continue
        total += 1
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[警告] 无法解析，跳过：{task_file.name} ({e})")
            continue

        hit, reason = is_test_artifact(task)
        if hit:
            to_delete.append((task_file, reason))
        elif task.get("title") == "会议记录":
            kept_placeholder += 1

    mode = "APPLY（实际删除）" if args.apply else "DRY-RUN（仅预览）"
    print(f"扫描任务主体：{total} 个 | 命中测试垃圾：{len(to_delete)} 个 | 「会议记录」真实数据保留：{kept_placeholder} 个")
    print(f"模式：{mode}\n")

    deleted = 0
    removed_sidecars = 0
    for task_file, reason in to_delete:
        task_id = task_file.stem
        print(f"  - {task_file.name}  ← {reason}")
        if not args.apply:
            continue
        try:
            task_file.unlink()
            deleted += 1
        except OSError as e:
            print(f"    [删除失败] {task_file.name}: {e}")
            continue
        for side in collect_sidecars(task_id):
            try:
                side.unlink()
                removed_sidecars += 1
            except OSError as e:
                print(f"    [旁路删除失败] {side.name}: {e}")

    if args.apply:
        print(f"\n已删除 {deleted} 个测试垃圾任务主体，附带清理 {removed_sidecars} 个旁路文件。")
    else:
        print("\n（dry-run，未做任何改动。确认无误后加 --apply 执行。）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
