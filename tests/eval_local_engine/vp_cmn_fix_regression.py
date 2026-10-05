#!/usr/bin/env python3
"""fix(ac6-cmn) 回归验收 — 云端 CMN 前处理统一后跨端零迁移兼容性复跑。

背景 / Context:
  QA 在 AC-6 抽查中发现云端 voiceprint-service（裸 fbank 无 CMN）与本地 FunASR
  CAM++（fbank+CMN）前处理口径不一致，跨端同人嵌入 cos 仅 ~0.62、EER 29.2%，
  「注册表双向零迁移兼容 / 误识率相对差异 ≤5%」不达标（见 53e917b、cf6f0e7、
  tests/eval_local_engine/EVAL-AC2-LOCAL-ENGINE.md §6）。项目方裁决以本地侧
  （有 CMN）为基准，云端 voiceprint-service/server.py::_extract_fbank 加 CMN。

本脚本复用 QA 的 AC-6 抽查方法论，验证修复后：
  1. 云端（修复后，本地起模型直接调用 server.extract_embedding）与本地 FunASR
     对同一组说话人的嵌入落在同一空间：跨端 cos 回升、EER/FPR 回落到同端水平。
  2. AC-6 判据：跨端误识率相对差异 ≤5%（以纯云同端为基线，向差不超过 5%）。
  3. 零迁移模拟：云端注册表 × 项目匹配器 × 本地查询嵌入，top-1 命中且过 margin 门槛。

不依赖已部署的云端服务，也不联网：直接在本地加载共享权重 campplus_cn_common.bin，
调用「修复后的 server.py」提取云侧嵌入，与 QA 缓存的本地 FunASR 嵌入对比。

运行 / Run:
  venv/bin/python tests/eval_local_engine/vp_cmn_fix_regression.py
产物 / Output:
  .eval_local_engine/results/vp_cmn_fix.json
"""
import json
import statistics
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "voiceprint-service"
EVAL = REPO / ".eval_local_engine"
sys.path.insert(0, str(SVC))   # server + models.cam_plus
sys.path.insert(0, str(REPO))  # core.voiceprint_registry

MATCH_THRESHOLD = 0.50
AC6_REL_DIFF_TOLERANCE = 0.05  # ≤5%


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
    if sw == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"不支持的采样宽度: {sw}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def l2(v):
    arr = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(arr)) or 1.0
    return (arr / n).tolist()


def cos(a, b) -> float:
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    va = va / (np.linalg.norm(va) or 1.0)
    vb = vb / (np.linalg.norm(vb) or 1.0)
    return float(va @ vb)


def eer_analysis(same: list[float], cross: list[float]) -> dict | None:
    if not same or not cross:
        return None
    best = None
    for cand in [i / 200 for i in range(0, 201)]:
        f = sum(1 for s in cross if s >= cand) / len(cross)
        t = sum(1 for s in same if s >= cand) / len(same)
        if best is None or abs(f - (1 - t)) < abs(best[1] - (1 - best[2])):
            best = (cand, f, t)
    ms, mc = statistics.mean(same), statistics.mean(cross)
    ss = (statistics.pstdev(same) + statistics.pstdev(cross)) / 2 or 1e-9
    return {
        "threshold": best[0],
        "fpr": round(best[1], 4),
        "tpr": round(best[2], 4),
        "eer": round((best[1] + (1 - best[2])) / 2, 4),
        "d_prime": round((ms - mc) / ss, 3),
    }


def combo(ref_map, tst_map, speakers, test_speakers) -> dict:
    same, cross, matrix = [], [], []
    for ts in test_speakers:
        for es in speakers:
            s = cos(ref_map[(es, "enroll")], tst_map[(ts, "test")])
            matrix.append({"enroll": es, "test": ts, "sim": round(s, 4)})
            (same if es == ts else cross).append(s)
    fpr = sum(1 for s in cross if s >= MATCH_THRESHOLD) / len(cross) if cross else None
    tpr = sum(1 for s in same if s >= MATCH_THRESHOLD) / len(same) if same else None
    return {
        "same_speaker_pairs": len(same),
        "cross_speaker_pairs": len(cross),
        "same_sim_mean": round(statistics.mean(same), 4) if same else None,
        "same_sim_min": round(min(same), 4) if same else None,
        "cross_sim_mean": round(statistics.mean(cross), 4) if cross else None,
        "cross_sim_max": round(max(cross), 4) if cross else None,
        "fpr_at_0.50": round(fpr, 4) if fpr is not None else None,
        "tpr_at_0.50": round(tpr, 4) if tpr is not None else None,
        "eer_analysis": eer_analysis(same, cross),
        "matrix": matrix,
    }


def main() -> None:
    # ---- 1) 起修复后的云侧模型（本地，共享权重，不联网） ----
    import server
    from models.cam_plus import load_camplus

    weights = SVC / "models" / "campplus_cn_common.bin"
    server._model = load_camplus(str(weights), device="cpu")
    server._model.eval()
    print(f"[server] 修复后 CAM++ 已加载 (weights={weights.name})", flush=True)

    clips_meta = json.loads((EVAL / "refs/vp_clips.json").read_text(encoding="utf-8"))
    speakers_with_clips = [s for s in clips_meta if s["clips"]]

    # ---- 2) 云侧（修复后 CMN）嵌入 ----
    cloud_map: dict[tuple[str, str], list[float]] = {}
    for spk in speakers_with_clips:
        for c in spk["clips"]:
            audio, sr = read_wav(REPO / c["path"])
            emb = server.extract_embedding(audio, sr)
            if emb is None:
                raise RuntimeError(f"云侧提取失败: {c['path']}")
            cloud_map[(spk["name"], c["role"])] = l2(emb.tolist())
            print(f"[cloud-cmn] {spk['name']}/{c['role']} dim={len(emb)}", flush=True)

    # ---- 3) 本地 FunASR（CMN）缓存嵌入（QA 产物） ----
    local_doc = json.loads((EVAL / "vp/local_embeddings.json").read_text(encoding="utf-8"))
    local_map = {(c["speaker"], c["role"]): l2(c["embedding"]) for c in local_doc["clips"]}

    speakers = sorted({k[0] for k in cloud_map if k[1] == "enroll"}
                      & {k[0] for k in local_map if k[1] == "enroll"})
    test_speakers = [s for s in speakers
                     if (s, "test") in cloud_map and (s, "test") in local_map]
    print(f"[speakers] enroll={speakers} test={test_speakers}", flush=True)

    # ---- 4) 跨端一致性直检：同一片段 云(CMN) vs 本地(FunASR CMN) ----
    per_clip_cos = []
    for spk in speakers:
        for role in ("enroll", "test"):
            if (spk, role) in cloud_map and (spk, role) in local_map:
                per_clip_cos.append({
                    "speaker": spk, "role": role,
                    "cos_cloud_cmn_vs_local_cmn": round(cos(cloud_map[(spk, role)], local_map[(spk, role)]), 4),
                })
    mean_direct_cos = round(statistics.mean([c["cos_cloud_cmn_vs_local_cmn"] for c in per_clip_cos]), 4)
    print(f"[direct] 同片段 云(CMN) vs 本地(CMN) 平均 cos = {mean_direct_cos} "
          f"(修复前跨端约 0.6834)", flush=True)

    # ---- 5) 4 组合矩阵 ----
    combos = {
        "ref_cloud_x_test_cloud": combo(cloud_map, cloud_map, speakers, test_speakers),
        "ref_cloud_x_test_local": combo(cloud_map, local_map, speakers, test_speakers),
        "ref_local_x_test_cloud": combo(local_map, cloud_map, speakers, test_speakers),
        "ref_local_x_test_local": combo(local_map, local_map, speakers, test_speakers),
    }
    for name, c in combos.items():
        print(f"[combo {name}] same_mean={c['same_sim_mean']} same_min={c['same_sim_min']} "
              f"cross_max={c['cross_sim_max']} FPR={c['fpr_at_0.50']} "
              f"EER={c['eer_analysis']['eer']} d'={c['eer_analysis']['d_prime']}", flush=True)

    # ---- 6) AC-6 判据：跨端相对纯云同端基线误识率相对差异 ≤5% ----
    base = combos["ref_cloud_x_test_cloud"]
    base_fpr = base["fpr_at_0.50"]
    base_eer = base["eer_analysis"]["eer"]
    ac6 = {}
    for name in ("ref_cloud_x_test_local", "ref_local_x_test_cloud", "ref_local_x_test_local"):
        c = combos[name]
        f = c["fpr_at_0.50"]
        e = c["eer_analysis"]["eer"]

        def rel(x, b):
            if b is None or x is None:
                return None
            if b == 0:
                return 0.0 if x == 0 else float("inf")
            return round((x - b) / b, 4)

        ac6[name] = {
            "fpr_at_0.50": f, "eer": e,
            "fpr_rel_diff_vs_cloud_baseline": rel(f, base_fpr),
            "eer_rel_diff_vs_cloud_baseline": rel(e, base_eer),
        }

    def within(x_rel) -> bool:
        # 向优（负）或劣化不超过 5% 均判通过
        return x_rel is not None and x_rel <= AC6_REL_DIFF_TOLERANCE

    cross_combos = ("ref_cloud_x_test_local", "ref_local_x_test_cloud")
    eer_pass = all(within(ac6[n]["eer_rel_diff_vs_cloud_baseline"]) for n in cross_combos)
    fpr_pass = all(within(ac6[n]["fpr_rel_diff_vs_cloud_baseline"]) for n in cross_combos)

    # ---- 7) 零迁移模拟：云端(CMN)注册表 × 项目匹配器 × 本地(CMN)查询 ----
    import core.voiceprint_registry as vr
    registry = {}
    for i, s in enumerate(speakers):
        registry[f"eval-{i}-{s}"] = {
            "speaker_uuid": f"eval-{i}-{s}",
            "embedding": l2(cloud_map[(s, "enroll")]),
            "registered_at": "2026-09-23T00:00:00",
            "updated_at": "2026-09-23T00:00:00",
            "sample_count": 1,
            "total_sample_duration": 25.0,
            "source_meeting_id": "ac6-cmn-fix",
            "model_version": "cam++-v1-cloud",
        }
    with tempfile.TemporaryDirectory() as td:
        reg_path = Path(td) / "voiceprint_registry.json"
        reg_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
        orig = vr.REGISTRY_FILE
        vr.REGISTRY_FILE = reg_path
        try:
            zm = []
            for ts in test_speakers:
                detail = vr.match_voiceprint_detail(np.array(l2(local_map[(ts, "test")])))
                hit = detail.best_uuid.split("-", 2)[-1] if detail.best_uuid else None
                zm.append({
                    "query_speaker": ts,
                    "query_embedding_provider": "local FunASR cam++-v1 (CMN)",
                    "registry_provider": "cloud cam++-v1-cloud (CMN, 修复后)",
                    "matched": hit, "accepted": detail.accepted,
                    "best_sim": round(detail.best_sim, 4), "margin": round(detail.margin, 4),
                    "correct": hit == ts,
                })
                print(f"[zero-migration] query={ts} → matched={hit} accepted={detail.accepted} "
                      f"sim={detail.best_sim:.3f} margin={detail.margin:.3f}", flush=True)
        finally:
            vr.REGISTRY_FILE = orig

    zm_all_correct = all(z["correct"] for z in zm)
    zm_all_accepted = all(z["accepted"] for z in zm)

    ac6_pass = eer_pass and fpr_pass and zm_all_correct and zm_all_accepted
    out = {
        "note": "fix(ac6-cmn) 回归：云端加 CMN 后跨端零迁移兼容复跑（本地起模型，不联网，复用 QA 缓存本地嵌入）",
        "baseline_choice": "local (FunASR fbank+CMN)；云侧 server.py::_extract_fbank 加 CMN 对齐",
        "speakers_enrolled": speakers,
        "speakers_tested": test_speakers,
        "match_threshold": MATCH_THRESHOLD,
        "ac6_rel_diff_tolerance": AC6_REL_DIFF_TOLERANCE,
        "direct_same_clip_cos_cloud_cmn_vs_local_cmn": {
            "mean": mean_direct_cos,
            "per_clip": per_clip_cos,
            "pre_fix_cross_end_mean_cos": 0.6834,
        },
        "combos": combos,
        "ac6_rel_diff": ac6,
        "ac6_checks": {
            "cross_end_eer_rel_diff_within_5pct": eer_pass,
            "cross_end_fpr_rel_diff_within_5pct": fpr_pass,
            "zero_migration_all_correct": zm_all_correct,
            "zero_migration_all_accepted": zm_all_accepted,
        },
        "zero_migration_matches": zm,
        "ac6_pass": ac6_pass,
    }
    dst = EVAL / "results" / "vp_cmn_fix.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[AC-6] eer_within={eer_pass} fpr_within={fpr_pass} "
          f"zm_correct={zm_all_correct} zm_accepted={zm_all_accepted} → {'PASS' if ac6_pass else 'FAIL'}")
    print(f"[DONE] vp_cmn_fix → {dst}")
    sys.exit(0 if ac6_pass else 1)


if __name__ == "__main__":
    main()
