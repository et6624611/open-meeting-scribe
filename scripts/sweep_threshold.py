"""
声纹阈值参数扫描

从评测会议提取 embedding 后缓存，快速遍历不同 (threshold, margin) 组合，
找最优准确率 / 误识率平衡点。
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.voiceprint import (
    VOICEPRINT_MODEL_VERSION,
    _l2,
    extract_embedding,
    load_registry,
)

MEETING_ID = "e6cda37b-4879-416d-ad81-c3035ec7eb43"
TASK_FILE = Path(f"data/tasks/{MEETING_ID}.json")
AUDIO_FILE = Path("data/uploads/e6cda37b_预付退款流程与客商主数据治理讨论.mp3")
MAPPING_FILE = Path("data/meeting_mappings.json")
MIN_SEGMENT_SEC = 3.0
MAX_SEGMENT_SEC = 12.0


def load_meeting_data():
    with open(TASK_FILE) as f:
        task = json.load(f)
    with open(MAPPING_FILE) as f:
        mm_list = json.load(f)
    mapping = {}
    for m in mm_list:
        if m["meeting_id"] == MEETING_ID:
            mapping = {int(k): v for k, v in m["mapping"].items()}
            break
    return task.get("dialogue", []), mapping


def convert_to_wav(mp3_path):
    wav_path = Path(tempfile.mktemp(suffix="_sweep.wav"))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "16000", "-ac", "1", "-f", "wav", str(wav_path)],
        capture_output=True, check=True,
    )
    return wav_path


def extract_all_embeddings(wav_path, dialogue, mapping, registry):
    """提取所有片段的 embedding，返回 (probes, labels)"""
    sr, audio = wavfile.read(str(wav_path))
    registered_uuids = {
        uid for uid, rec in registry.items()
        if rec.model_version == VOICEPRINT_MODEL_VERSION
    }

    # 构建注册表矩阵（与 match_voiceprint_detail 同逻辑）
    valid = {uid: rec for uid, rec in registry.items() if uid in registered_uuids}
    uuids = list(valid.keys())
    refs = np.stack([_l2(np.array(valid[u].embedding, dtype=np.float32)) for u in uuids])

    probes = []
    labels = []

    for d in dialogue:
        spk_id = d.get("speaker_id")
        if spk_id not in mapping:
            continue
        speaker_uuid = mapping[spk_id]
        if speaker_uuid not in registered_uuids:
            continue

        for sent in d.get("sentences", []):
            begin_ms = sent.get("begin_time", 0)
            end_ms = sent.get("end_time", 0)
            dur = (end_ms - begin_ms) / 1000.0
            if dur < MIN_SEGMENT_SEC:
                continue
            actual_end_ms = begin_ms + min(dur, MAX_SEGMENT_SEC) * 1000
            seg = audio[int(begin_ms / 1000 * sr):int(actual_end_ms / 1000 * sr)]
            if seg.dtype != np.float32:
                seg = seg.astype(np.float32) / 32768.0

            emb = extract_embedding(seg, sr)
            if emb is None:
                continue

            probe = _l2(emb)
            sims = refs @ probe
            probes.append(sims)
            labels.append(uuids.index(speaker_uuid))

    return np.array(probes), np.array(labels), uuids


def sweep(probes, labels, uuids):
    """遍历 (threshold, margin) 组合"""
    n = len(probes)
    print(f"评测片段: {n}")
    print()
    print(f"{'threshold':>10} {'margin':>8} {'正确':>5} {'准确率':>7} {'误识':>5} {'误识率':>7} {'拒识':>5}")
    print("-" * 60)

    best_acc = 0
    best_params = None

    for thr in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        for margin in [0.00, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10]:
            correct = 0
            wrong = 0
            rejected = 0

            for i in range(n):
                sims = probes[i]
                order = np.argsort(-sims)
                best_idx = int(order[0])
                best_sim = float(sims[order[0]])
                second_sim = float(sims[order[1]]) if len(order) > 1 else 0.0
                m = best_sim - second_sim

                accepted = best_sim >= thr and m >= margin
                if not accepted:
                    rejected += 1
                elif best_idx == labels[i]:
                    correct += 1
                else:
                    wrong += 1

            acc = correct / n if n else 0
            wrong_rate = wrong / n if n else 0
            marker = " ← 当前" if (abs(thr - 0.50) < 0.001 and abs(margin - 0.05) < 0.001) else ""
            if acc > best_acc:
                best_acc = acc
                best_params = (thr, margin)
                marker = " ★"
            print(f"{thr:>10.2f} {margin:>8.2f} {correct:>5} {acc:>7.1%} {wrong:>5} {wrong_rate:>7.1%} {rejected:>5}{marker}")

    print()
    if best_params:
        print(f"最优参数: threshold={best_params[0]}, margin={best_params[1]}, accuracy={best_acc:.1%}")


def main():
    print("加载数据...")
    dialogue, mapping = load_meeting_data()
    registry = load_registry()

    print("转换音频...")
    wav_path = convert_to_wav(AUDIO_FILE)

    try:
        print("提取 embedding（一次性）...")
        probes, labels, uuids = extract_all_embeddings(wav_path, dialogue, mapping, registry)
        print(f"提取完成: {len(probes)} 个有效片段")
        print()
        sweep(probes, labels, uuids)
    finally:
        wav_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
