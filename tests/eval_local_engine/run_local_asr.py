#!/usr/bin/env python3
"""WP-C AC-2 评测 — 本地 FunASR 全管线转写（可复跑）。

模型组合（D-R1 采纳，Spike §2.1）：
  seaco-paraformer-zh + fsmn-vad + ct-punc + cam++（说话人分离）
模型缓存复用 Spike 下载（MODELSCOPE_CACHE=.spike_local_engine/ms_cache），全程离线。

必须用 Spike 隔离环境运行：
  .spike_local_engine/venv/bin/python tests/eval_local_engine/run_local_asr.py [SEG-ID ...]

产物：.eval_local_engine/results/local_<SEG>.json（含 sentence_info 时间戳/说话人、全文、耗时）
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
MANIFEST = json.loads((REPO / "tests/eval_local_engine/eval_manifest.json").read_text(encoding="utf-8"))

MODELS = {
    "model": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "vad_model": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "punc_model": "iic/punc_ct-transformer_cn-en-common-vocab471067-large",
    "spk_model": "iic/speech_campplus_sv_zh-cn_16k-common",
}


def main() -> None:
    only = set(sys.argv[1:])
    segs = [s for s in MANIFEST["segments"] if not only or s["id"] in only]
    if not segs:
        print(f"无匹配片段: {only}", file=sys.stderr)
        sys.exit(2)

    from funasr import AutoModel

    t0 = time.time()
    model = AutoModel(**MODELS, disable_update=True, log_level="ERROR")
    load_s = round(time.time() - t0, 1)
    print(f"[LOAD] {load_s}s", flush=True)

    results_dir = EVAL / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    for seg in segs:
        audio = EVAL / "audio" / f"{seg['id']}.wav"
        if not audio.exists():
            print(f"[SKIP] {audio} 不存在，先运行 prepare_segments.py", file=sys.stderr)
            continue
        t1 = time.time()
        res = model.generate(input=str(audio), batch_size_s=300, merge_vad=True, merge_length_s=15)
        infer_s = round(time.time() - t1, 1)
        payload = res[0]
        sent_info = payload.get("sentence_info", [])
        out = {
            "segment": seg["id"],
            "audio": str(audio.relative_to(REPO)),
            "models": MODELS,
            "model_load_seconds": load_s,
            "infer_seconds": infer_s,
            "rtf": round(infer_s / seg["duration_s"], 4),
            "text": payload.get("text", ""),
            "speakers_detected": sorted({s.get("spk") for s in sent_info}),
            "sentences": [
                {"begin_ms": s.get("start"), "end_ms": s.get("end"),
                 "spk": s.get("spk"), "text": s.get("text", "")}
                for s in sent_info
            ],
        }
        dst = results_dir / f"local_{seg['id']}.json"
        dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{seg['id']}] infer={infer_s}s rtf={out['rtf']} sentences={len(sent_info)} "
              f"speakers={out['speakers_detected']} text_len={len(out['text'])}", flush=True)
    print("[DONE] run_local_asr")


if __name__ == "__main__":
    main()
