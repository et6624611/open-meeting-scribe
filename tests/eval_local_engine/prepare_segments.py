#!/usr/bin/env python3
"""WP-C AC-2 评测 — 样本准备（可复跑）。

功能：
  1. 按 eval_manifest.json 从整场会议 normalized wav 切出评测片段（SEG-2P/4P/6P）；
  2. 从任务 JSON 导出各片段的云端参照时间线（句子级 speaker/begin/end/text，时间轴平移到片段内）；
  3. 为声纹兼容抽查切出每名说话人的纯净单人片段（enroll/test 各 1 条）。

运行：python3 tests/eval_local_engine/prepare_segments.py
产物（全部在 .eval_local_engine/，不入库）：
  audio/SEG-*.wav、audio/vp/<speaker>_{enroll,test}.wav
  refs/SEG-*_cloud_timeline.json、refs/vp_clips.json
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "eval_manifest.json").read_text(encoding="utf-8"))
EVAL = REPO / MANIFEST["eval_root"]


def run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-v", "error", "-y", *args]
    subprocess.run(cmd, check=True, cwd=REPO)


def cut_wav(src: str, start_s: float, dur_s: float, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-ss", str(start_s), "-t", str(dur_s), "-i", src, "-c", "copy", str(dst)])


def cloud_sentences(task_json: str) -> list[dict]:
    d = json.loads((REPO / task_json).read_text(encoding="utf-8"))
    out = []
    for blk in d.get("dialogue", []):
        name = blk.get("speaker_name") or f"spk{blk.get('speaker_id')}"
        for s in blk.get("sentences", []):
            out.append({
                "begin_ms": s["begin_time"],
                "end_ms": s["end_time"],
                "speaker": name,
                "text": s.get("text", ""),
            })
    out.sort(key=lambda x: x["begin_ms"])
    return out


def prepare_segments() -> None:
    for seg in MANIFEST["segments"]:
        sid = seg["id"]
        dst = EVAL / "audio" / f"{sid}.wav"
        cut_wav(seg["source_wav"], seg["offset_s"], seg["duration_s"], dst)
        off_ms = seg["offset_s"] * 1000
        end_ms = off_ms + seg["duration_s"] * 1000
        timeline = []
        for s in cloud_sentences(seg["task_json"]):
            if s["end_ms"] <= off_ms or s["begin_ms"] >= end_ms:
                continue
            timeline.append({
                **s,
                "begin_ms": max(0, s["begin_ms"] - off_ms),
                "end_ms": min(end_ms - off_ms, s["end_ms"] - off_ms),
            })
        ref = EVAL / "refs" / f"{sid}_cloud_timeline.json"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(json.dumps({
            "segment": sid,
            "source": seg["origin"],
            "offset_s": seg["offset_s"],
            "duration_s": seg["duration_s"],
            "expected_speakers": seg["expected_speakers"],
            "note": "云端 paraformer-v2 历史全量转写（人工绑定说话人姓名）在片段窗口内的句子时间线；仅用于选段与 DER 的辅助对照，正式云端参照以 run_cloud_asr.py 的全新转写为准",
            "sentences": timeline,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        spk = sorted({s["speaker"] for s in timeline})
        print(f"[{sid}] cut {seg['duration_s']}s @ {seg['offset_s']}s, timeline sentences={len(timeline)}, speakers={spk}")


def pure_runs(sentences: list[dict], speaker: str, gap_merge_ms=1200, guard_ms=2000):
    """找出该说话人的纯净连续发言区间（与他人语音无重叠，句间空隙 < gap_merge_ms 则合并）。"""
    mine = [s for s in sentences if s["speaker"] == speaker]
    others = [s for s in sentences if s["speaker"] != speaker]
    runs = []
    cur = None
    for s in mine:
        if cur and s["begin_ms"] - cur["end_ms"] <= gap_merge_ms:
            cur["end_ms"] = max(cur["end_ms"], s["end_ms"])
        else:
            if cur:
                runs.append(cur)
            cur = {"begin_ms": s["begin_ms"], "end_ms": s["end_ms"]}
    if cur:
        runs.append(cur)
    clean = []
    for r in runs:
        lo, hi = r["begin_ms"] - guard_ms, r["end_ms"] + guard_ms
        if any(o["begin_ms"] < hi and o["end_ms"] > lo for o in others):
            continue
        r["seconds"] = (r["end_ms"] - r["begin_ms"]) / 1000
        clean.append(r)
    return clean


def prepare_vp_clips() -> None:
    cfg = MANIFEST["voiceprint_clips"]
    min_s, target_s, n_clips = cfg["min_clip_seconds"], cfg["target_clip_seconds"], cfg["clips_per_speaker"]
    out = []
    for spk in cfg["speakers"]:
        sents = cloud_sentences(spk["task_json"])
        runs = [r for r in pure_runs(sents, spk["name"]) if r["seconds"] >= min_s]
        runs.sort(key=lambda r: -r["seconds"])
        picks = []
        for i, r in enumerate(runs[:n_clips]):
            dur = min(r["seconds"], max(target_s, min_s))
            tag = "enroll" if i == 0 else "test"
            dst = EVAL / "audio" / "vp" / f"{spk['name']}_{tag}.wav"
            cut_wav(spk["source_wav"], r["begin_ms"] / 1000, dur, dst)
            picks.append({"role": tag, "path": str(dst.relative_to(REPO)),
                          "begin_ms": r["begin_ms"], "seconds": round(dur, 1),
                          "source_wav": spk["source_wav"]})
            print(f"[vp] {spk['name']} {tag}: {dur:.1f}s @ {r['begin_ms']/1000:.1f}s")
        if len(picks) < n_clips:
            print(f"[vp][WARN] {spk['name']} 纯净片段不足 {n_clips} 条（仅 {len(picks)}）", file=sys.stderr)
        out.append({"name": spk["name"], "clips": picks})
    vp_dir = EVAL / "audio" / "vp"
    vp_dir.mkdir(parents=True, exist_ok=True)
    (EVAL / "refs" / "vp_clips.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    prepare_segments()
    prepare_vp_clips()
    print("[DONE] prepare_segments")
