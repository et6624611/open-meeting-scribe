"""
离线声纹识别准确性评测

用已标注说话人的会议音频（e6cda37b），对每位说话人提取多段声纹，
与注册表做匹配，统计识别率、相似度分布。
"""

import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.voiceprint import (
    VOICEPRINT_MODEL_VERSION,
    extract_embedding,
    load_registry,
    match_voiceprint_detail,
)

# ── 配置 ──────────────────────────────────────────────
MEETING_ID = "e6cda37b-4879-416d-ad81-c3035ec7eb43"
TASK_FILE = Path(f"data/tasks/{MEETING_ID}.json")
AUDIO_FILE = Path("data/uploads/e6cda37b_预付退款流程与客商主数据治理讨论.mp3")
MAPPING_FILE = Path("data/meeting_mappings.json")

# 最短提取时长（秒），太短的片段噪声大
MIN_SEGMENT_SEC = 3.0
# 最长提取时长（秒），截断避免多说话人混合
MAX_SEGMENT_SEC = 12.0


def load_meeting_data():
    """加载会议 dialogue + speaker 映射"""
    with open(TASK_FILE) as f:
        task = json.load(f)
    with open(MAPPING_FILE) as f:
        mm_list = json.load(f)

    # 找该会议的映射
    mapping = {}
    for m in mm_list:
        if m["meeting_id"] == MEETING_ID:
            mapping = {int(k): v for k, v in m["mapping"].items()}
            break

    dialogue = task.get("dialogue", [])
    return dialogue, mapping


def convert_to_wav(mp3_path: Path) -> Path:
    """MP3 → WAV（16kHz 单声道）"""
    wav_path = Path(tempfile.mktemp(suffix="_eval.wav"))
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp3_path),
            "-ar", "16000", "-ac", "1", "-f", "wav",
            str(wav_path),
        ],
        capture_output=True,
        check=True,
    )
    return wav_path


def extract_segments(wav_path: Path, dialogue: list, mapping: dict):
    """
    从音频中按句子时间戳提取各说话人的片段。

    Returns:
        {speaker_uuid: [(audio_segment, sentence_info), ...]}
    """
    from scipy.io import wavfile

    sr, audio = wavfile.read(str(wav_path))
    segments_by_speaker = defaultdict(list)

    for d in dialogue:
        spk_id = d.get("speaker_id")
        if spk_id not in mapping:
            continue
        speaker_uuid = mapping[spk_id]

        for sent in d.get("sentences", []):
            begin_ms = sent.get("begin_time", 0)
            end_ms = sent.get("end_time", 0)
            duration_sec = (end_ms - begin_ms) / 1000.0

            if duration_sec < MIN_SEGMENT_SEC:
                continue

            # 截断到 MAX_SEGMENT_SEC
            actual_end_ms = begin_ms + min(duration_sec, MAX_SEGMENT_SEC) * 1000

            begin_sample = int(begin_ms / 1000.0 * sr)
            end_sample = int(actual_end_ms / 1000.0 * sr)
            segment = audio[begin_sample:end_sample]
            # int16 → float32（CAM++ 需要浮点输入）
            if segment.dtype != np.float32:
                segment = segment.astype(np.float32) / 32768.0

            segments_by_speaker[speaker_uuid].append({
                "audio": segment,
                "sample_rate": sr,
                "begin_ms": begin_ms,
                "end_ms": actual_end_ms,
                "text": sent.get("text", "")[:30],
            })

    return segments_by_speaker


def evaluate(segments_by_speaker: dict, registry: dict):
    """
    对每段音频提取 embedding，与注册表匹配，统计结果。

    Returns:
        results: list of dicts with per-segment results
        summary: dict with aggregate metrics
    """
    results = []
    # 收集所有注册表 UUID（仅 cam++-v1）
    registered_uuids = {
        uid for uid, rec in registry.items()
        if rec.model_version == VOICEPRINT_MODEL_VERSION
    }

    for speaker_uuid, segments in segments_by_speaker.items():
        is_registered = speaker_uuid in registered_uuids
        if not is_registered:
            continue  # 跳过未注册的说话人

        for seg_info in segments:
            emb = extract_embedding(seg_info["audio"], seg_info["sample_rate"])
            if emb is None:
                continue  # 提取失败，跳过
            detail = match_voiceprint_detail(emb)

            results.append({
                "true_uuid": speaker_uuid,
                "pred_uuid": detail.best_uuid,
                "similarity": detail.best_sim,
                "second_sim": detail.second_sim,
                "margin": detail.margin,
                "accepted": detail.accepted,
                "correct": detail.best_uuid == speaker_uuid and detail.accepted,
                "begin_ms": seg_info["begin_ms"],
                "text": seg_info["text"],
            })

    # 汇总
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    accepted = sum(1 for r in results if r["accepted"])
    wrong_id = sum(
        1 for r in results
        if r["accepted"] and r["pred_uuid"] != r["true_uuid"]
    )

    # 按说话人统计
    per_speaker = defaultdict(lambda: {"total": 0, "correct": 0, "avg_sim": []})
    for r in results:
        uid = r["true_uuid"]
        per_speaker[uid]["total"] += 1
        per_speaker[uid]["correct"] += int(r["correct"])
        per_speaker[uid]["avg_sim"].append(r["similarity"])

    summary = {
        "total_segments": total,
        "correct": correct,
        "accuracy": correct / total if total else 0,
        "accepted": accepted,
        "wrong_id": wrong_id,
        "per_speaker": dict(per_speaker),
    }
    return results, summary


def print_report(results: list, summary: dict, speakers: dict):
    """打印评测报告"""
    # 建 UUID → name 映射
    uuid_to_name = {s["speaker_id"]: s["name"] for s in speakers}

    print("=" * 70)
    print("声纹识别离线评测报告")
    print(f"会议: {MEETING_ID[:8]}")
    print(f"Encoder: {VOICEPRINT_MODEL_VERSION}")
    print("=" * 70)

    # 总体指标
    print("\n【总体指标】")
    print(f"  评测片段数: {summary['total_segments']}")
    print(f"  正确识别:   {summary['correct']}")
    print(f"  识别准确率: {summary['accuracy']:.1%}")
    print(f"  误识（匹配到错误人）: {summary['wrong_id']}")
    print(f"  拒识（未通过门槛）:   {summary['accepted'] - summary['correct'] + summary['wrong_id']}")

    # 按说话人
    print("\n【按说话人】")
    print(f"  {'姓名': <6} {'片段':>4} {'正确':>4} {'准确率':>6} {'平均相似度':>10}")
    print(f"  {'-'*40}")
    for uid, stats in sorted(summary["per_speaker"].items()):
        name = uuid_to_name.get(uid, uid[:8])
        avg_sim = np.mean(stats["avg_sim"]) if stats["avg_sim"] else 0
        acc = stats["correct"] / stats["total"] if stats["total"] else 0
        print(f"  {name: <6} {stats['total']:>4} {stats['correct']:>4} {acc:>6.1%} {avg_sim:>10.4f}")

    # 相似度分布
    correct_sims = [r["similarity"] for r in results if r["correct"]]
    wrong_sims = [
        r["similarity"] for r in results
        if r["accepted"] and r["pred_uuid"] != r["true_uuid"]
    ]
    rejected_sims = [r["similarity"] for r in results if not r["accepted"]]

    print("\n【相似度分布】")
    if correct_sims:
        print(f"  正确匹配 (n={len(correct_sims)}): "
              f"mean={np.mean(correct_sims):.4f}  "
              f"min={np.min(correct_sims):.4f}  "
              f"max={np.max(correct_sims):.4f}  "
              f"std={np.std(correct_sims):.4f}")
    if wrong_sims:
        print(f"  错误匹配 (n={len(wrong_sims)}): "
              f"mean={np.mean(wrong_sims):.4f}  "
              f"min={np.min(wrong_sims):.4f}  "
              f"max={np.max(wrong_sims):.4f}")
    if rejected_sims:
        print(f"  被拒绝   (n={len(rejected_sims)}): "
              f"mean={np.mean(rejected_sims):.4f}  "
              f"min={np.min(rejected_sims):.4f}  "
              f"max={np.max(rejected_sims):.4f}")

    # 错误详情
    errors = [r for r in results if not r["correct"]]
    if errors:
        print("\n【错误详情】（前 10 条）")
        for r in errors[:10]:
            true_name = uuid_to_name.get(r["true_uuid"], r["true_uuid"][:8])
            pred_name = uuid_to_name.get(r["pred_uuid"], r["pred_uuid"][:8] if r["pred_uuid"] else "None")
            status = "误识" if r["accepted"] else "拒识"
            print(f"  [{status}] {true_name} → 预测 {pred_name}  "
                  f"sim={r['similarity']:.4f}  margin={r['margin']:.4f}  "
                  f"t={r['begin_ms']/1000:.0f}s  \"{r['text']}\"")

    print()


def main():
    print("加载数据...")
    dialogue, mapping = load_meeting_data()
    registry = load_registry()

    with open("data/speakers.json") as f:
        speakers = json.load(f)

    registered_count = sum(
        1 for r in registry.values()
        if r.model_version == VOICEPRINT_MODEL_VERSION
    )
    print(f"注册表: {registered_count} 条 (cam++-v1)")
    print(f"会议映射: {len(mapping)} 个说话人")

    print("转换音频...")
    wav_path = convert_to_wav(AUDIO_FILE)

    try:
        print("提取片段...")
        segments = extract_segments(wav_path, dialogue, mapping)
        for uid, segs in segments.items():
            name = next((s["name"] for s in speakers if s["speaker_id"] == uid), uid[:8])
            total_sec = sum((s["end_ms"] - s["begin_ms"]) / 1000 for s in segs)
            print(f"  {name}: {len(segs)} 段, {total_sec:.0f}s")

        print("评测中（提取 embedding + 匹配）...")
        results, summary = evaluate(segments, registry)

        print_report(results, summary, speakers)

    finally:
        wav_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
