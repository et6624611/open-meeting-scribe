"""
声纹匹配方法对比评测

对比两种匹配策略在真实会议数据上的准确率：
  - 旧方法（v3）：逐人独立匹配，每人独立取最高相似度
  - 新方法（v4）：per-meeting 中心化 + 匈牙利算法一对一分配
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
    MATCH_THRESHOLD,
    MAX_SEC_PER_SPEAKER,
    MIN_MATCH_MARGIN,
    MIN_REGISTER_SEC,
    VOICEPRINT_MODEL_VERSION,
    _cap_segments,
    _collect_speaker_segments,
    _l2,
    cosine_similarity,
    extract_embedding,
    load_registry,
    match_voiceprint_detail,
)

# ── 配置 ──────────────────────────────────────────────
MEETING_ID = "e6cda37b-4879-416d-ad81-c3035ec7eb43"
TASK_FILE = Path(f"data/tasks/{MEETING_ID}.json")
AUDIO_FILE = Path("data/uploads/e6cda37b_预付退款流程与客商主数据治理讨论.mp3")
MAPPING_FILE = Path("data/meeting_mappings.json")


def load_ground_truth():
    """加载会议映射（speaker_id → speaker_uuid）作为 ground truth"""
    with open(MAPPING_FILE) as f:
        mm_list = json.load(f)
    for m in mm_list:
        if m["meeting_id"] == MEETING_ID:
            return {int(k): v for k, v in m["mapping"].items()}
    return {}


def convert_to_wav(mp3_path: Path) -> Path:
    wav_path = Path(tempfile.mktemp(suffix="_eval.wav"))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path),
         "-ar", "16000", "-ac", "1", "-f", "wav", str(wav_path)],
        capture_output=True, check=True,
    )
    return wav_path


def extract_per_speaker_embeddings(wav_path: Path, gt_mapping: dict):
    """
    按 ground truth 的 speaker_id 提取每人的嵌入（与 auto_identify_speakers 同逻辑）
    Returns: {speaker_id: embedding}
    """
    sr, audio = wavfile.read(str(wav_path))
    with open(TASK_FILE) as f:
        task = json.load(f)
    dialogue = task.get("dialogue", [])
    speaker_segments = _collect_speaker_segments(dialogue)

    embeddings = {}
    for sid in sorted(gt_mapping.keys()):
        segs = speaker_segments.get(sid, [])
        total_sec = sum(e - b for b, e in segs)
        if total_sec < MIN_REGISTER_SEC:
            continue
        capped = _cap_segments(segs, MAX_SEC_PER_SPEAKER)
        chunks = [audio[int(b * sr):int(e * sr)] for b, e in capped]
        chunks = [c for c in chunks if len(c) > 0]
        if not chunks:
            continue
        emb = extract_embedding(np.concatenate(chunks), sr)
        if emb is not None:
            embeddings[sid] = emb
    return embeddings


def eval_old_method(embeddings: dict, gt_mapping: dict, registry: dict):
    """旧方法：逐人独立匹配（match_voiceprint_detail）"""
    results = []
    for sid, emb in embeddings.items():
        true_uuid = gt_mapping[sid]
        detail = match_voiceprint_detail(emb)
        results.append({
            "sid": sid,
            "true_uuid": true_uuid,
            "pred_uuid": detail.best_uuid,
            "sim": detail.best_sim,
            "margin": detail.margin,
            "accepted": detail.accepted,
            "correct": detail.best_uuid == true_uuid and detail.accepted,
        })
    return results


def eval_new_method(embeddings: dict, gt_mapping: dict, registry: dict):
    """新方法：per-meeting 中心化 + 匈牙利算法"""
    from scipy.optimize import linear_sum_assignment

    valid = {
        u: r for u, r in registry.items()
        if r.model_version == VOICEPRINT_MODEL_VERSION
    }
    if not valid:
        return []

    sids = sorted(embeddings.keys())
    emb_array = np.stack([embeddings[sid] for sid in sids])

    # Per-meeting 中心化
    if len(sids) >= 2:
        mean_emb = np.mean(emb_array, axis=0)
        centered = emb_array - mean_emb
    else:
        centered = emb_array

    # 参考向量
    ref_uuids = list(valid.keys())
    ref_embs = np.stack([
        _l2(np.array(valid[u].embedding, dtype=np.float32))
        for u in ref_uuids
    ])

    # 相似度矩阵
    n_speakers = len(sids)
    n_refs = len(ref_uuids)
    sim_matrix = np.zeros((n_speakers, n_refs), dtype=np.float32)
    for i in range(n_speakers):
        probe = centered[i]
        if np.linalg.norm(probe) < 1e-9:
            continue
        for j in range(n_refs):
            sim_matrix[i, j] = cosine_similarity(probe, ref_embs[j])

    # 匈牙利算法
    row_ind, col_ind = linear_sum_assignment(-sim_matrix)
    assigned = {}
    for r, c in zip(row_ind, col_ind):
        if r < n_speakers and c < n_refs:
            assigned[r] = c

    results = []
    for i, sid in enumerate(sids):
        true_uuid = gt_mapping[sid]
        if i not in assigned:
            results.append({
                "sid": sid, "true_uuid": true_uuid,
                "pred_uuid": None, "sim": 0.0,
                "margin": 0.0, "accepted": False, "correct": False,
            })
            continue

        j = assigned[i]
        best_uuid = ref_uuids[j]
        best_sim = float(sim_matrix[i, j])

        sorted_sims = np.sort(sim_matrix[i])[::-1]
        second_sim = float(sorted_sims[1]) if len(sorted_sims) > 1 else 0.0
        margin = best_sim - second_sim

        accepted = margin >= MIN_MATCH_MARGIN  # 中心化空间仅看 margin
        results.append({
            "sid": sid,
            "true_uuid": true_uuid,
            "pred_uuid": best_uuid,
            "sim": best_sim,
            "margin": margin,
            "accepted": accepted,
            "correct": best_uuid == true_uuid and accepted,
        })
    return results


def print_comparison(old_results, new_results, speakers: dict):
    """对比打印两种方法的结果"""
    uuid_to_name = {s["speaker_id"]: s["name"] for s in speakers}

    print("=" * 78)
    print(f"声纹匹配方法对比评测 — 会议 {MEETING_ID[:8]}")
    print(f"Encoder: {VOICEPRINT_MODEL_VERSION}  阈值: {MATCH_THRESHOLD}  margin: {MIN_MATCH_MARGIN}")
    print("=" * 78)

    # 总体对比
    old_correct = sum(1 for r in old_results if r["correct"])
    new_correct = sum(1 for r in new_results if r["correct"])
    old_wrong = sum(1 for r in old_results if r["accepted"] and r["pred_uuid"] != r["true_uuid"])
    new_wrong = sum(1 for r in new_results if r["accepted"] and r["pred_uuid"] != r["true_uuid"])
    old_rejected = sum(1 for r in old_results if not r["accepted"])
    new_rejected = sum(1 for r in new_results if not r["accepted"])

    print(f"\n{'指标':<20} {'旧方法(独立匹配)':>20} {'新方法(统筹分配)':>20}")
    print(f"{'-'*62}")
    print(f"{'总说话人':<20} {len(old_results):>20} {len(new_results):>20}")
    print(f"{'正确识别':<20} {old_correct:>20} {new_correct:>20}")
    print(f"{'误识（匹配到错误人）':<20} {old_wrong:>20} {new_wrong:>20}")
    print(f"{'拒识（未通过门槛）':<20} {old_rejected:>20} {new_rejected:>20}")
    old_acc = old_correct / len(old_results) if old_results else 0
    new_acc = new_correct / len(new_results) if new_results else 0
    print(f"{'准确率':<20} {old_acc:>19.1%} {new_acc:>19.1%}")

    # 逐人对比
    print(f"\n{'逐人对比':}")
    print(f"  {'姓名':<8} {'旧·预测':>10} {'旧·sim':>8} {'旧·margin':>10} {'旧·结果':>6}"
          f"  {'新·预测':>10} {'新·sim':>8} {'新·margin':>10} {'新·结果':>6}")
    print(f"  {'-'*80}")

    old_by_sid = {r["sid"]: r for r in old_results}
    new_by_sid = {r["sid"]: r for r in new_results}
    all_sids = sorted(set(list(old_by_sid.keys()) + list(new_by_sid.keys())))

    for sid in all_sids:
        name = uuid_to_name.get(sid, sid)
        o = old_by_sid.get(sid, {})
        n = new_by_sid.get(sid, {})

        o_name = uuid_to_name.get(o.get("pred_uuid"), "?") if o.get("pred_uuid") else "-"
        n_name = uuid_to_name.get(n.get("pred_uuid"), "?") if n.get("pred_uuid") else "-"
        o_status = "✓" if o.get("correct") else ("✗" if o.get("accepted") else "—")
        n_status = "✓" if n.get("correct") else ("✗" if n.get("accepted") else "—")

        print(f"  {name:<8} {o_name:>10} {o.get('sim', 0):>8.3f} {o.get('margin', 0):>10.3f} {o_status:>6}"
              f"  {n_name:>10} {n.get('sim', 0):>8.3f} {n.get('margin', 0):>10.3f} {n_status:>6}")

    # 相似度分布对比
    print(f"\n{'相似度分布':}")
    old_sims = [r["sim"] for r in old_results if r["pred_uuid"]]
    new_sims = [r["sim"] for r in new_results if r["pred_uuid"]]
    if old_sims:
        print(f"  旧方法: mean={np.mean(old_sims):.4f}  "
              f"min={np.min(old_sims):.4f}  max={np.max(old_sims):.4f}  "
              f"std={np.std(old_sims):.4f}")
    if new_sims:
        print(f"  新方法: mean={np.mean(new_sims):.4f}  "
              f"min={np.min(new_sims):.4f}  max={np.max(new_sims):.4f}  "
              f"std={np.std(new_sims):.4f}")

    print()


def main():
    print("加载数据...")
    gt_mapping = load_ground_truth()
    registry = load_registry()
    with open("data/speakers.json") as f:
        speakers = json.load(f)

    registered_count = sum(
        1 for r in registry.values()
        if r.model_version == VOICEPRINT_MODEL_VERSION
    )
    print(f"注册表: {registered_count} 条 (cam++-v1)")
    print(f"Ground truth: {len(gt_mapping)} 个说话人")

    print("转换音频...")
    wav_path = convert_to_wav(AUDIO_FILE)

    try:
        print("提取各说话人嵌入...")
        embeddings = extract_per_speaker_embeddings(wav_path, gt_mapping)
        print(f"  有效嵌入: {len(embeddings)}/{len(gt_mapping)} 位说话人")

        print("旧方法评测（逐人独立匹配）...")
        old_results = eval_old_method(embeddings, gt_mapping, registry)

        print("新方法评测（per-meeting 中心化 + 匈牙利算法）...")
        new_results = eval_new_method(embeddings, gt_mapping, registry)

        print_comparison(old_results, new_results, speakers)

    finally:
        wav_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
