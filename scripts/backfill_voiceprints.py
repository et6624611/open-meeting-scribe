"""
scripts/backfill_voiceprints.py — 从已确认的会议绑定回溯采集声纹 / Backfill voiceprint extraction from confirmed meeting bindings

扫描 data/tasks/ 中已完成（completed）且带 speaker_uuid_mapping 的任务，
按绑定关系从归一化音频提取声纹写入注册表（data/voiceprint_registry.json），
使后续会议可以直接按声纹自动匹配身份。
Scan completed tasks with speaker_uuid_mapping in data/tasks/,
extract voiceprints from normalized audio based on bindings and write to registry (data/voiceprint_registry.json),
enabling subsequent meetings to auto-match identity by voiceprint.

适用场景：声纹自动注册闭环上线前已完成的历史会议，其绑定关系已确认
但注册表为空，需要一次性补录。
Use case: Historical meetings completed before voiceprint auto-registration launched,
where bindings are confirmed but registry is empty, requiring one-time backfill.

用法 / Usage:
    venv/bin/python scripts/backfill_voiceprints.py            # 回溯全部 / Backfill all
    venv/bin/python scripts/backfill_voiceprints.py <task前缀>  # 仅回溯指定 / Backfill specific only
"""

import json
import os
import sys
from pathlib import Path

# core.voiceprint 的数据目录为相对路径 data/，必须先切到项目根目录 / core.voiceprint data dir is relative path data/, must chdir to project root first
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from core import voiceprint  # noqa: E402
from core.speakers import get_speaker_by_id  # noqa: E402


def resolve_normalized(task: dict) -> Path | None:
    """
    解析任务对应的归一化 WAV 路径。 / Resolve normalized WAV path for task.

    优先级：任务字段 normalized_path → 命名约定（原文件名 + _normalized.wav）
    → 按任务 ID 前缀在 uploads/recordings 中 glob。
    Priority: task field normalized_path → naming convention (original name + _normalized.wav)
    → glob in uploads/recordings by task ID prefix.
    """
    cand = task.get("normalized_path")
    if cand and Path(cand).exists():
        return Path(cand)

    audio = Path(task.get("audio_path") or "")
    conv = audio.with_stem(f"{audio.stem}_normalized").with_suffix(".wav")
    if conv.exists():
        return conv

    for d in (ROOT / "data" / "uploads", ROOT / "data" / "recordings"):
        hits = [
            p for p in d.glob(f"{task['task_id'][:8]}*_normalized.wav")
            if not p.name.endswith("_normalized_normalized.wav")
        ]
        if hits:
            return hits[0]
    return None


def speaker_name(uuid: str) -> str:
    speaker = get_speaker_by_id(uuid)
    return speaker.name if speaker else uuid[:8]


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else None
    task_files = sorted((ROOT / "data" / "tasks").glob("*.json"))

    total_ok = 0
    for f in task_files:
        with open(f, encoding="utf-8") as fh:
            task = json.load(fh)
        tid = task.get("task_id", f.stem)
        if prefix and not tid.startswith(prefix):
            continue

        mapping = task.get("speaker_uuid_mapping") or {}
        dialogue = task.get("dialogue") or []
        if task.get("status") != "completed" or not mapping or not dialogue:
            continue

        wav = resolve_normalized(task)
        if wav is None:
            print(f"[跳过] {tid[:8]} {task.get('audio_name', '')}: 未找到归一化音频")
            continue

        print(f"[回溯] {tid[:8]} {task.get('title') or task.get('audio_name', '')} → {wav.name}")
        results = voiceprint.register_from_binding(
            audio_path=wav,
            dialogue=dialogue,
            mapping=mapping,
            meeting_id=tid,
        )
        for uuid, r in results.items():
            print(f"    - {speaker_name(uuid)}: {r['status']}（{r.get('duration_sec', 0)}s）")
            if r["status"] == "registered":
                total_ok += 1

    registry = voiceprint.load_registry()
    print(f"\n完成：本次回溯注册 {total_ok} 条，注册表共 {len(registry)} 人")
    for uuid, rec in registry.items():
        print(
            f"    {speaker_name(uuid)}: 样本数={rec.sample_count} "
            f"来源会议={rec.source_meeting_id[:8]} 更新={rec.updated_at[:19]}"
        )


if __name__ == "__main__":
    main()
