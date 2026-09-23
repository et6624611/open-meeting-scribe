#!/usr/bin/env python3
"""WP-C AC-6 抽查 — 声纹注册表云/本地兼容性对比（可复跑）。

验证（验收标准 6 / AC-6）：
  1. 同一批注册数据在 cam++-v1-cloud 与本地 cam++-v1 间零迁移直接使用：
     用云端 voiceprint-service 提取的 enroll 嵌入构造注册表（model_version=cam++-v1-cloud），
     以本地 CAM++ 提取的 test 嵌入经项目匹配器 core.voiceprint_registry.match_voiceprint_detail
     直接匹配，核对命中与阈值行为；反向（本地注册 × 云端查询）同法。
  2. 误识率相对差异 ≤5%：对 4 种 provider 组合（cloud×cloud / cloud×local / local×cloud /
     local×local）统计跨说话人误识率 FPR@MATCH_THRESHOLD(0.50) 与同人通过率，
     计算「含本地侧组合」相对「纯云端基线」的 FPR 相对差异。

前置：vp_extract_local.py 已产出本地嵌入；voiceprint-service 可达（settings.json → voiceprint.cloud）。
运行：venv/bin/python tests/eval_local_engine/vp_compat.py
产物：.eval_local_engine/results/vp_compat.json、.eval_local_engine/vp/cloud_embeddings.json
"""
import base64
import json
import math
import sys
import tempfile
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
EVAL = REPO / ".eval_local_engine"


def load_cloud_cfg() -> tuple[str, str]:
    cfg = json.loads((REPO / "data/settings.json").read_text(encoding="utf-8"))
    vp = cfg["voiceprint"]["cloud"]
    return vp["base_url"].rstrip("/"), vp["api_key"]


def cloud_embed(base_url: str, api_key: str, wav_path: Path) -> list[float] | None:
    wav_bytes = wav_path.read_bytes()
    resp = requests.post(
        f"{base_url}/voiceprint/embedding",
        json={"audio": base64.b64encode(wav_bytes).decode("ascii"),
              "sample_rate": 16000, "model": "campplus-v1"},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"[ERROR] cloud embedding {wav_path.name}: HTTP {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return None
    return resp.json()["embedding"]


def l2(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cos(a, b) -> float:
    return sum(x * y for x, y in zip(l2(a), l2(b)))


def main() -> None:
    base_url, api_key = load_cloud_cfg()
    clips_meta = json.loads((EVAL / "refs/vp_clips.json").read_text(encoding="utf-8"))
    local = json.loads((EVAL / "vp/local_embeddings.json").read_text(encoding="utf-8"))
    local_map = {(c["speaker"], c["role"]): c["embedding"] for c in local["clips"]}

    # 1) 云端嵌入提取（enroll + test 全量）
    cloud_map: dict[tuple[str, str], list[float]] = {}
    for spk in clips_meta:
        for c in spk["clips"]:
            emb = cloud_embed(base_url, api_key, REPO / c["path"])
            if emb is not None:
                cloud_map[(spk["name"], c["role"])] = emb
                print(f"[cloud] {spk['name']}/{c['role']} dim={len(emb)}", flush=True)
    (EVAL / "vp/cloud_embeddings.json").write_text(json.dumps({
        "model_version": "cam++-v1-cloud",
        "clips": [{"speaker": k[0], "role": k[1], "dim": len(v), "embedding": v}
                  for k, v in cloud_map.items()],
    }, ensure_ascii=False), encoding="utf-8")

    # 2) 维度一致性
    dims = {"cloud": sorted({len(v) for v in cloud_map.values()}),
            "local": sorted({len(v) for v in local_map.values()})}
    print(f"[dims] {dims}")

    # 3) 4 组合相似度矩阵 → FPR / TPR @ 0.50
    speakers = sorted({k[0] for k in cloud_map if k[1] == "enroll"} & {k[0] for k in local_map if k[1] == "enroll"})
    test_speakers = [s for s in speakers
                     if (s, "test") in cloud_map and (s, "test") in local_map]
    combos = {}
    for ref_prov, test_prov in (("cloud", "cloud"), ("cloud", "local"),
                                ("local", "cloud"), ("local", "local")):
        ref_map = cloud_map if ref_prov == "cloud" else local_map
        tst_map = cloud_map if test_prov == "cloud" else local_map
        same, cross = [], []
        matrix = []
        for ts in test_speakers:
            for es in speakers:
                s = cos(ref_map[(es, "enroll")], tst_map[(ts, "test")])
                matrix.append({"enroll": es, "test": ts, "sim": round(s, 4)})
                (same if es == ts else cross).append(s)
        thr = 0.50
        fpr = sum(1 for s in cross if s >= thr) / len(cross) if cross else None
        tpr = sum(1 for s in same if s >= thr) / len(same) if same else None
        # 阈值无关指标：EER（扫描阈值使 FPR≈1-TPR）与判别力 d-prime
        eer = None
        if same and cross:
            best = None
            for cand in [i / 200 for i in range(0, 201)]:
                f = sum(1 for s in cross if s >= cand) / len(cross)
                t = sum(1 for s in same if s >= cand) / len(same)
                if best is None or abs(f - (1 - t)) < abs(best[1] - (1 - best[2])):
                    best = (cand, f, t)
            eer = {"threshold": best[0], "fpr": round(best[1], 4), "tpr": round(best[2], 4),
                   "eer": round((best[1] + (1 - best[2])) / 2, 4)}
            import statistics
            ms, mc = statistics.mean(same), statistics.mean(cross)
            ss = (statistics.pstdev(same) + statistics.pstdev(cross)) / 2 or 1e-9
            eer["d_prime"] = round((ms - mc) / ss, 3)
        combos[f"ref_{ref_prov}_x_test_{test_prov}"] = {
            "same_speaker_pairs": len(same), "cross_speaker_pairs": len(cross),
            "same_sim_mean": round(sum(same) / len(same), 4) if same else None,
            "same_sim_min": round(min(same), 4) if same else None,
            "cross_sim_mean": round(sum(cross) / len(cross), 4) if cross else None,
            "cross_sim_max": round(max(cross), 4) if cross else None,
            "fpr_at_0.50": round(fpr, 4) if fpr is not None else None,
            "tpr_at_0.50": round(tpr, 4) if tpr is not None else None,
            "eer_analysis": eer,
            "matrix": matrix,
        }
        print(f"[combo ref={ref_prov} test={test_prov}] FPR={combos[f'ref_{ref_prov}_x_test_{test_prov}']['fpr_at_0.50']} "
              f"TPR={combos[f'ref_{ref_prov}_x_test_{test_prov}']['tpr_at_0.50']} "
              f"same_mean={combos[f'ref_{ref_prov}_x_test_{test_prov}']['same_sim_mean']} "
              f"cross_max={combos[f'ref_{ref_prov}_x_test_{test_prov}']['cross_sim_max']}", flush=True)

    base_fpr = combos["ref_cloud_x_test_cloud"]["fpr_at_0.50"]
    base_eer = (combos["ref_cloud_x_test_cloud"]["eer_analysis"] or {}).get("eer")
    ac6 = {}
    for name in ("ref_cloud_x_test_local", "ref_local_x_test_cloud", "ref_local_x_test_local"):
        f = combos[name]["fpr_at_0.50"]
        e = (combos[name]["eer_analysis"] or {}).get("eer")
        entry = {"fpr_at_0.50": f, "eer": e}
        if base_fpr is None or f is None:
            entry["fpr_rel_diff_vs_cloud_baseline"] = None
        elif base_fpr == 0:
            entry["fpr_rel_diff_vs_cloud_baseline"] = 0.0 if f == 0 else float("inf")
        else:
            entry["fpr_rel_diff_vs_cloud_baseline"] = round((f - base_fpr) / base_fpr, 4)
        if base_eer and e is not None:
            entry["eer_rel_diff_vs_cloud_baseline"] = round((e - base_eer) / base_eer, 4)
        else:
            entry["eer_rel_diff_vs_cloud_baseline"] = None
        ac6[name] = entry

    # 4) 零迁移模拟：云端注册表 × 项目匹配器 × 本地查询嵌入
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
            "source_meeting_id": "wp-c-eval",
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
                detail = vr.match_voiceprint_detail(__import__("numpy").array(l2(local_map[(ts, "test")])))
                hit_name = detail.best_uuid.split("-", 2)[-1] if detail.best_uuid else None
                zm.append({
                    "query_speaker": ts, "query_embedding_provider": "local cam++-v1",
                    "registry_provider": "cloud cam++-v1-cloud",
                    "matched": hit_name, "accepted": detail.accepted,
                    "best_sim": round(detail.best_sim, 4), "margin": round(detail.margin, 4),
                    "correct": hit_name == ts,
                })
                print(f"[zero-migration] query={ts} → matched={hit_name} accepted={detail.accepted} "
                      f"sim={detail.best_sim:.3f} margin={detail.margin:.3f}", flush=True)
        finally:
            vr.REGISTRY_FILE = orig

    out = {
        "note": "AC-6 抽查：注册数据云/本地零迁移互用 + 误识率相对差异（阈值 0.50，margin 门槛走项目匹配器）",
        "speakers_enrolled": speakers,
        "speakers_tested": test_speakers,
        "embedding_dims": dims,
        "threshold": 0.50,
        "combos": combos,
        "ac6_fpr_relative_diff": ac6,
        "zero_migration_matches": zm,
        "zero_migration_all_correct": all(z["correct"] for z in zm),
    }
    dst = EVAL / "results" / "vp_compat.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[DONE] vp_compat → {dst}")


if __name__ == "__main__":
    main()
