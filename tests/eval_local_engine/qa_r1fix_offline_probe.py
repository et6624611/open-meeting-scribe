#!/usr/bin/env python3
"""QA-R1 DEF-01 修复活体探针（macOS）：死端口代理下经 EngineHost 全路径加载+推理。

对齐 docs/QA-R1-DEFECTS-DISPATCH.md §2 DEF-QA-R1-01 Done 判据 1（T1 场景改后须 PASS）
与 DEF-QA-R1-03 Done 判据（预热移出首请求加载 + 30 分钟整场不整场失败）。

与 QA 原探针 qa_r1_offline_probe.py 的区别：不再手调 AutoModel，而是驱动项目真实
运行链路 —— EngineHost 常驻子进程 + warmup + infer(asr/embedding)，子进程全程继承
死端口代理环境（HTTP(S)_PROXY=http://127.0.0.1:9 ⇒ 任何出网尝试 connection-refused）。

环境：Spike 隔离 venv（.spike_local_engine/venv，funasr/torch），cwd=项目根，
模型权重位于 data/models（与下载器同源布局）。

Usage: qa_r1fix_offline_probe.py <short.wav> <long.wav>
"""
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

short_wav, long_wav = sys.argv[1], sys.argv[2]

# ── 模拟真断网：死端口代理（沿用 QA-R1 死端口代理法，§3.5 流程教训）──
for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ[v] = "http://127.0.0.1:9"
os.environ["NO_PROXY"] = ""
os.environ["no_proxy"] = ""

import logging  # noqa: E402

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from core.engine_host import estimate_local_asr_timeout, get_engine_host  # noqa: E402


def wait_warmup(host, deadline_s=300):
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        st = host.status().get("warmup_state")
        if st == "done":
            return round(time.time() - t0, 1)
        if st == "failed":
            return -1
        time.sleep(1.0)
    return -2


def main():
    host = get_engine_host()
    t0 = time.time()
    start = host.start()
    print(f"[P1] ENGINE_START {json.dumps(start, ensure_ascii=False)} in {time.time()-t0:.1f}s", flush=True)
    if not start.get("ok"):
        print("[P1] RESULT=ENGINE_START_FAIL", flush=True)
        return 3

    # ── DEF-03：健康检查后自动预热；等待加载完成（此期间零出网，代理已死端口）──
    warm_s = wait_warmup(host)
    if warm_s < 0:
        print(f"[P2] WARMUP state={'FAILED' if warm_s == -1 else 'TIMEOUT'}", flush=True)
        print("[P2] RESULT=WARMUP_FAIL", flush=True)
        return 4
    print(f"[P2] WARMUP_DONE {warm_s}s (offline: dead-port proxy active)", flush=True)

    # ── DEF-01 AC：ASR 短音频推理出真实结果 ──
    t = time.time()
    resp = host.infer("asr", {"audio_path": short_wav}, timeout=estimate_local_asr_timeout(60))
    dt = round(time.time() - t, 1)
    text = resp.get("text", "")
    print(f"[P3] ASR_SHORT {dt}s text_len={len(text)} head={text[:40]!r}", flush=True)
    if not text:
        print("[P3] RESULT=ASR_SHORT_EMPTY", flush=True)
        return 5

    # ── DEF-01 AC：CAM++ 声纹加载+推理（T2 同源路径）──
    t = time.time()
    emb = host.infer("embedding", {"audio_path": short_wav}, timeout=120)
    dt = round(time.time() - t, 1)
    print(f"[P4] EMBED_OK {dt}s dim={emb.get('dim')}", flush=True)
    if emb.get("dim") != 192:
        print("[P4] RESULT=EMBED_BAD_DIM", flush=True)
        return 6

    # ── DEF-03 AC：30 分钟整场推理，首请求不再叠加模型加载 ──
    from core.audio import get_audio_duration
    dur = get_audio_duration(long_wav)
    timeout = estimate_local_asr_timeout(dur)
    t = time.time()
    resp30 = host.infer("asr", {"audio_path": long_wav}, timeout=timeout)
    dt30 = round(time.time() - t, 1)
    text30 = resp30.get("text", "")
    print(
        f"[P5] ASR_30MIN infer={dt30}s (timeout_budget={timeout:.0f}s, "
        f"duration={dur/60:.1f}min) text_len={len(text30)} "
        f"infer_reported={resp30.get('infer_seconds')}s",
        flush=True,
    )
    if not text30 or dt30 >= timeout:
        print("[P5] RESULT=ASR_30MIN_FAIL", flush=True)
        return 7

    host.stop()
    print("[PROBE] RESULT=QA_R1_FIX_OFFLINE_PASS (T1-scenario PASS after fix, warmup + 30min ok)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
