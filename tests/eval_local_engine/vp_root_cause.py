#!/usr/bin/env python3
"""WP-C AC-6 抽查 — 跨端嵌入差异根因定位实验（可复跑，QA 诊断用，不修改产品代码）。

假设：voiceprint-service（云端 cam++-v1-cloud）与 funasr 本地推理加载的是同一份
campplus_cn_common.bin 权重，但特征前处理不同——云端为裸 Kaldi fbank（无 CMN），
funasr CAMPPlus 管线在 fbank 后做时间维均值归一（CMN）。若假设成立：
  cos(云端服务嵌入, 本地复刻-无CMN) ≈ 1
  cos(funasr 嵌入, 本地复刻-有CMN) ≈ 1
  cos(无CMN, 有CMN) ≈ 0.6（即观察到的跨端同人相似度水平）

用 Spike 隔离环境运行：
  .spike_local_engine/venv/bin/python tests/eval_local_engine/vp_root_cause.py
产物：.eval_local_engine/results/vp_root_cause.json
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio.compliance.kaldi as K

REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / ".eval_local_engine"
WEIGHTS = REPO / ".spike_local_engine/ms_cache/models/iic--speech_campplus_sv_zh-cn_16k-common/snapshots/master/campplus_cn_common.bin"


def load_camplus_module():
    spec = importlib.util.spec_from_file_location(
        "cam_plus", REPO / "voiceprint-service/models/cam_plus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cos(a, b) -> float:
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) or 1.0))


def l2n(v):
    v = np.asarray(v, dtype=np.float64).ravel()
    return v / (np.linalg.norm(v) or 1.0)


def main() -> None:
    mod = load_camplus_module()
    model = mod.load_camplus(str(WEIGHTS), device="cpu")
    model.eval()

    clips = json.loads((EVAL / "refs/vp_clips.json").read_text(encoding="utf-8"))
    local = {(c["speaker"], c["role"]): c["embedding"]
             for c in json.loads((EVAL / "vp/local_embeddings.json").read_text(encoding="utf-8"))["clips"]}
    cloud = {(c["speaker"], c["role"]): c["embedding"]
             for c in json.loads((EVAL / "vp/cloud_embeddings.json").read_text(encoding="utf-8"))["clips"]}

    out = {"hypothesis": "同一权重 campplus_cn_common.bin；云端=裸fbank(无CMN)，funasr=fbank+CMN",
           "clips": []}
    for spk in clips:
        for c in spk["clips"]:
            key = (spk["name"], c["role"])
            if key not in cloud or key not in local:
                continue
            audio, sr = sf.read(REPO / c["path"], dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            x = torch.from_numpy(audio).unsqueeze(0)
            fbank = K.fbank(x, num_mel_bins=80, frame_length=25, frame_shift=10)
            with torch.no_grad():
                emb_nocmn = model(fbank)[0].numpy()
                emb_cmn = model(fbank - fbank.mean(dim=0, keepdim=True))[0].numpy()
            row = {
                "clip": f"{spk['name']}/{c['role']}",
                "cos_repro_nocmn_vs_cloud_service": round(cos(emb_nocmn, cloud[key]), 4),
                "cos_repro_cmn_vs_funasr_local": round(cos(emb_cmn, local[key]), 4),
                "cos_repro_nocmn_vs_repro_cmn": round(cos(emb_nocmn, emb_cmn), 4),
                "cos_cloud_service_vs_funasr_local": round(cos(cloud[key], local[key]), 4),
            }
            out["clips"].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    if out["clips"]:
        for k in out["clips"][0]:
            if k == "clip":
                continue
            vals = [r[k] for r in out["clips"]]
            out[f"mean_{k}"] = round(sum(vals) / len(vals), 4)
    dst = EVAL / "results" / "vp_root_cause.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[DONE] vp_root_cause → {dst}")


if __name__ == "__main__":
    main()
