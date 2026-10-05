#!/usr/bin/env python3
"""QA-R1 AC-1 probe: does the local FunASR engine load models TRULY OFFLINE?

Simulates network-absence by pointing HTTP(S)_PROXY at a dead port (connection refused),
then attempts AutoModel load + a short generate. Reports whether the cached weights are
usable without any successful network call.

Usage: qa_r1_offline_probe.py <MODELSCOPE_CACHE_dir> <wav>
"""
import os
import sys
import time
from pathlib import Path

cache = sys.argv[1]
wav = sys.argv[2]
os.environ["MODELSCOPE_CACHE"] = str(Path(cache).resolve())
# Simulate真断网: proxy to a dead port → any egress attempt gets connection-refused.
for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ[v] = "http://127.0.0.1:9"
os.environ["NO_PROXY"] = ""
os.environ["no_proxy"] = ""

MODELS = {
    "model": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "vad_model": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "punc_model": "iic/punc_ct-transformer_cn-en-common-vocab471067-large",
    "spk_model": "iic/speech_campplus_sv_zh-cn_16k-common",
}

print(f"[PROBE] cache={os.environ['MODELSCOPE_CACHE']}", flush=True)
print(f"[PROBE] proxy(dead-port offline sim)={os.environ['HTTPS_PROXY']}", flush=True)
try:
    from funasr import AutoModel
    t0 = time.time()
    model = AutoModel(**MODELS, disable_update=True, disable_pbar=True, log_level="ERROR")
    load_s = round(time.time() - t0, 1)
    print(f"[PROBE] LOAD_OK {load_s}s", flush=True)
    t1 = time.time()
    res = model.generate(input=wav, batch_size_s=300, merge_vad=True, merge_length_s=15)
    infer_s = round(time.time() - t1, 1)
    txt = (res[0].get("text", "") if res else "")
    print(f"[PROBE] GENERATE_OK infer={infer_s}s text_len={len(txt)} head={txt[:60]!r}", flush=True)
    print("[PROBE] RESULT=OFFLINE_LOAD_PASS", flush=True)
except Exception as e:
    print(f"[PROBE] LOAD_OR_INFER_FAIL {type(e).__name__}: {str(e)[:300]}", flush=True)
    print("[PROBE] RESULT=OFFLINE_LOAD_FAIL", flush=True)
    sys.exit(3)
