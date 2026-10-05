#!/usr/bin/env python3
"""WP-C AC-2 评测 — 云端 paraformer-v2 参照转写（可复跑）。

通过项目订阅通道（core.cloud_client.cloud_transcribe → CLOUD_API_URL）提交评测片段，
diarization_enabled=true（cloud_transcribe 内固定开启）。项目方已授权本次评测消耗配额
（估算见 EVAL-AC2-LOCAL-ENGINE.md §配额报备：3 段合计 1200s 音频）。

必须用项目 venv 运行（依赖 core/ 与 .env）：
  venv/bin/python tests/eval_local_engine/run_cloud_asr.py [SEG-ID ...]

产物：.eval_local_engine/results/cloud_<SEG>.json（原始返回 + 归一化句子时间线）
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import os

# 手动加载 .env（评测脚本独立于 server 启动路径）
for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

EVAL = REPO / ".eval_local_engine"
MANIFEST = json.loads((REPO / "tests/eval_local_engine/eval_manifest.json").read_text(encoding="utf-8"))
EVAL_USER_ID = "2e3d8ca0-bf8a-4b32-9305-714a1bd4b037"  # 133****3103（云端已注册用户，配额剩余 2386 分钟，本次消耗 ≈20 分钟）


def extract_sentences(raw: dict) -> list[dict]:
    """从 DashScope 原始 transcription 提取句子时间线（与 proxy/direct 模式一致的结构）。"""
    out = []
    tr = raw.get("transcription", raw)
    transcripts = tr.get("transcripts") or []
    for t in transcripts:
        for s in t.get("sentences", []):
            out.append({
                "begin_ms": s.get("begin_time"),
                "end_ms": s.get("end_time"),
                "speaker": str(s.get("speaker_id", "")),
                "text": s.get("text", ""),
            })
    out.sort(key=lambda x: (x["begin_ms"] or 0))
    return out


def main() -> None:
    only = set(sys.argv[1:])
    segs = [s for s in MANIFEST["segments"] if not only or s["id"] in only]
    from core.cloud_client import cloud_transcribe, is_cloud_enabled

    if not is_cloud_enabled():
        print("云端通道未启用（CLOUD_API_URL/TOKEN 缺失）", file=sys.stderr)
        sys.exit(2)

    results_dir = EVAL / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    total_audio_s = sum(s["duration_s"] for s in segs)
    print(f"[QUOTA] 本次将提交 {len(segs)} 段 / 合计 {total_audio_s}s 音频至云端 paraformer-v2", flush=True)

    for seg in segs:
        audio = EVAL / "audio" / f"{seg['id']}.wav"
        if not audio.exists():
            print(f"[SKIP] {audio} 不存在，先运行 prepare_segments.py", file=sys.stderr)
            continue
        t0 = time.time()
        result = cloud_transcribe(str(audio), user_id=EVAL_USER_ID, model="paraformer-v2")
        elapsed = round(time.time() - t0, 1)
        if result is None:
            print(f"[{seg['id']}] 云端转写失败", file=sys.stderr)
            sys.exit(1)
        sentences = extract_sentences(result)
        out = {
            "segment": seg["id"],
            "audio": str(audio.relative_to(REPO)),
            "model": "paraformer-v2",
            "channel": "cloud_subscription_relay",
            "elapsed_seconds": elapsed,
            "speakers_detected": sorted({s["speaker"] for s in sentences}),
            "sentences": sentences,
            "full_text": "".join(s["text"] for s in sentences),
            "raw": result,
        }
        dst = results_dir / f"cloud_{seg['id']}.json"
        dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{seg['id']}] elapsed={elapsed}s sentences={len(sentences)} "
              f"speakers={out['speakers_detected']} text_len={len(out['full_text'])}", flush=True)
    print("[DONE] run_cloud_asr")


if __name__ == "__main__":
    main()
