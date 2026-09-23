#!/usr/bin/env python3
"""WP-C AC-6 抽查 — 本地 CAM++ 声纹嵌入提取（可复跑）。

用 Spike 隔离环境的 funasr 加载 `iic/speech_campplus_sv_zh-cn_16k-common`（28MB，
与说话人分离共用同一份权重），对 .eval_local_engine/audio/vp/*.wav 提取 192 维嵌入。

必须用 Spike 隔离环境运行：
  .spike_local_engine/venv/bin/python tests/eval_local_engine/vp_extract_local.py

产物：.eval_local_engine/vp/local_embeddings.json
"""
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.chdir(REPO)
os.environ.setdefault("MODELSCOPE_CACHE", str(REPO / ".spike_local_engine/ms_cache"))

EVAL = REPO / ".eval_local_engine"
MODEL_ID = "iic/speech_campplus_sv_zh-cn_16k-common"


def main() -> None:
    clips = json.loads((EVAL / "refs/vp_clips.json").read_text(encoding="utf-8"))
    from funasr import AutoModel

    t0 = time.time()
    model = AutoModel(model=MODEL_ID, disable_update=True, log_level="ERROR")
    print(f"[LOAD] {time.time() - t0:.1f}s", flush=True)

    out = {"model_id": MODEL_ID, "model_version_local": "cam++-v1", "clips": []}
    for spk in clips:
        for c in spk["clips"]:
            path = REPO / c["path"]
            if not path.exists():
                print(f"[SKIP] {path}", file=sys.stderr)
                continue
            t1 = time.time()
            res = model.generate(input=str(path))
            emb = None
            payload = res[0] if isinstance(res, list) else res
            for key in ("spk_embedding", "embedding"):
                if key in payload:
                    emb = payload[key]
                    break
            if emb is None:
                print(f"[ERROR] {path.name}: 无 spk_embedding 字段，keys={list(payload.keys())}", file=sys.stderr)
                sys.exit(1)
            vec = emb.squeeze().tolist() if hasattr(emb, "squeeze") else list(emb)
            out["clips"].append({
                "speaker": spk["name"], "role": c["role"], "path": c["path"],
                "dim": len(vec), "embedding": vec,
                "infer_seconds": round(time.time() - t1, 2),
            })
            print(f"[{spk['name']}/{c['role']}] dim={len(vec)} infer={out['clips'][-1]['infer_seconds']}s", flush=True)

    dst = EVAL / "vp"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "local_embeddings.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"[DONE] vp_extract_local → {dst / 'local_embeddings.json'}")


if __name__ == "__main__":
    main()
