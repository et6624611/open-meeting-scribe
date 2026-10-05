#!/usr/bin/env python3
"""QA-R1 AC-3 + AC-1(ASR path): 30-minute local FunASR full pipeline with peak-RSS sampling.

Runs the SAME four models the app uses (seaco-paraformer-zh + fsmn-vad + ct-punc + cam++)
via MODELSCOPE_CACHE=data/models (production layout), on a >=30-min real meeting slice.

Evidence produced:
  - AC-3: independent peak-RSS retest (WP-C reused Spike 3.3GB without independent retest).
  - AC-1: transcript + speaker diarization completed fully offline (run under proxy capture
          externally; disable_update=True suppresses ModelScope egress).

Run (spike venv, from worktree root):
  .spike_local_engine/venv/bin/python tests/eval_local_engine/qa_r1_asr_mem.py <wav> <out.json>
"""
import json
import os
import resource
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.chdir(REPO)
# Production model dir the app uses (core.engine_host.build_engine_env -> get_model_dir)
_MODEL_DIR = (REPO / "data/models").resolve()
os.environ.setdefault("MODELSCOPE_CACHE", str(_MODEL_DIR))

# QA-R1: simulate true network absence (dead-port proxy => connection refused for any egress).
# Proves the run below needs zero successful non-localhost network access.
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ[_v] = "http://127.0.0.1:9"
os.environ["NO_PROXY"] = ""
os.environ["no_proxy"] = ""

# AC-3 memory is measured on the SAME four weights/pipeline the app uses. The shipped
# engine_worker resolves models by ModelScope ID, which requires a modelscope.cn round-trip
# and fails offline (DEF-QA-R1-01); we therefore resolve to LOCAL FILESYSTEM PATHS (the
# proven fix direction, qa_r1_offline_probe T3) so the offline pipeline can actually run.
_H = _MODEL_DIR / "hub/iic"
MODELS = {
    "model": str(_H / "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"),
    "vad_model": str(_H / "speech_fsmn_vad_zh-cn-16k-common-pytorch"),
    "punc_model": str(_H / "punc_ct-transformer_cn-en-common-vocab471067-large"),
    "spk_model": str(_H / "speech_campplus_sv_zh-cn_16k-common"),
}

_peak_rss = [0]
_stop = [False]


def _sampler():
    """Sample current RSS (bytes) via psutil if available; ru_maxrss is the authoritative peak."""
    try:
        import psutil
        p = psutil.Process(os.getpid())
    except Exception:
        return
    while not _stop[0]:
        try:
            rss = p.memory_info().rss
            for c in p.children(recursive=True):
                try:
                    rss += c.memory_info().rss
                except Exception:
                    pass
            if rss > _peak_rss[0]:
                _peak_rss[0] = rss
        except Exception:
            pass
        time.sleep(0.3)


def main() -> None:
    wav = sys.argv[1]
    out = sys.argv[2]
    dur = float(sys.argv[3]) if len(sys.argv) > 3 else 1800.0

    t = threading.Thread(target=_sampler, daemon=True)
    t.start()

    from funasr import AutoModel

    t0 = time.time()
    model = AutoModel(**MODELS, disable_update=True, log_level="ERROR")
    load_s = round(time.time() - t0, 1)
    print(f"[LOAD] {load_s}s", flush=True)

    t1 = time.time()
    res = model.generate(input=wav, batch_size_s=300, merge_vad=True, merge_length_s=15)
    infer_s = round(time.time() - t1, 1)
    payload = res[0]
    sent = payload.get("sentence_info", [])

    # ru_maxrss on macOS is in bytes; on Linux in KB.
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    ru_children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if sys.platform == "darwin":
        peak_ru_bytes = ru
        peak_ru_child_bytes = ru_children
    else:
        peak_ru_bytes = ru * 1024
        peak_ru_child_bytes = ru_children * 1024
    _stop[0] = True
    time.sleep(0.4)
    peak_sampled = _peak_rss[0]
    peak_rss_bytes = max(peak_ru_bytes, peak_sampled)

    result = {
        "qa_round": "QA-R1",
        "form": "venv (spike funasr 1.4.16 / torch 2.14.0), NOT PyInstaller frozen package",
        "audio": wav,
        "audio_duration_s": dur,
        "modelscope_cache": os.environ["MODELSCOPE_CACHE"],
        "models": MODELS,
        "model_load_seconds": load_s,
        "infer_seconds": infer_s,
        "rtf": round(infer_s / dur, 4) if dur else None,
        "peak_rss_bytes": peak_rss_bytes,
        "peak_rss_gb": round(peak_rss_bytes / (1024**3), 3),
        "peak_rss_source": {
            "ru_maxrss_self_bytes": peak_ru_bytes,
            "ru_maxrss_children_bytes": peak_ru_child_bytes,
            "psutil_sampled_bytes": peak_sampled,
        },
        "ac3_threshold_gb": 8.0,
        "ac3_pass": bool(peak_rss_bytes / (1024**3) <= 8.0),
        "speakers_detected": sorted({s.get("spk") for s in sent}),
        "n_sentences": len(sent),
        "text_len": len(payload.get("text", "")),
        "text_head": payload.get("text", "")[:300],
        "sentences": [
            {"begin_ms": s.get("start"), "end_ms": s.get("end"),
             "spk": s.get("spk"), "text": s.get("text", "")}
            for s in sent
        ],
    }
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ASR] infer={infer_s}s rtf={result['rtf']} sentences={len(sent)} "
          f"speakers={result['speakers_detected']} text_len={result['text_len']}", flush=True)
    print(f"[MEM] peak_rss={result['peak_rss_gb']}GB (ru_self={round(peak_ru_bytes/1024**3,3)}GB "
          f"sampled={round(peak_sampled/1024**3,3)}GB) ac3_pass={result['ac3_pass']}", flush=True)
    print(f"[DONE] -> {out}", flush=True)


if __name__ == "__main__":
    main()
