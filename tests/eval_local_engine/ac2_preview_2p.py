#!/usr/bin/env python3
"""AC-2 预览计算（SEG-2P 人工参照，非正式判级）。

只读复用 compute_metrics.py 的 cer()/normalize()，按其 human-ref 分支
（compute_metrics.py L339-347）同口径计算 SEG-2P：
  - cer_local_vs_humanref / cer_cloud_vs_humanref
  - ac2_relative_gap_vs_humanref = (local - cloud) / cloud，≤15% 判定
不修改 compute_metrics.py，不覆盖 results/metrics.json 及 qa_r1 任何证据。
产物：.eval_local_engine/results/metrics_ac2_preview_seg2p.json（新文件）
运行：venv/bin/python tests/eval_local_engine/ac2_preview_2p.py
"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compute_metrics as cm  # noqa: E402  (只读复用，不修改)

SID = "SEG-2P"
REF_FILE = HERE / "refs" / f"{SID}_human_ref.txt"
EVAL = cm.EVAL
OUT = EVAL / "results" / "metrics_ac2_preview_seg2p.json"

local = json.loads((EVAL / "results" / f"local_{SID}.json").read_text(encoding="utf-8"))
cloud = json.loads((EVAL / "results" / f"cloud_{SID}.json").read_text(encoding="utf-8"))
existing = json.loads((EVAL / "results" / "metrics.json").read_text(encoding="utf-8"))

ht = REF_FILE.read_text(encoding="utf-8")
lines = [ln for ln in ht.splitlines() if ln.strip()]
dash_lines = [i + 1 for i, ln in enumerate(ht.splitlines()) if ln.strip() == "—"]
norm_ref = cm.normalize(ht)
filler_counts = {f: norm_ref.count(f) for f in ("呃", "啊", "嗯")}

m_local = cm.cer(ht, local["text"])
m_cloud = cm.cer(ht, cloud["full_text"])
wl, wc = m_local["cer"], m_cloud["cer"]
gap = round((wl - wc) / wc, 4) if wc and wc > 0 else None

result = {
    "meta": {
        "purpose": "AC-2 预览计算（单档 SEG-2P，人工参照），不构成正式判级",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "script": "tests/eval_local_engine/ac2_preview_2p.py",
        "method_source": "compute_metrics.py human-ref 分支同口径（cer/normalize 只读复用）",
        "human_ref_file": str(REF_FILE),
        "human_ref_sha256": hashlib.sha256(REF_FILE.read_bytes()).hexdigest(),
        "human_ref_nonempty_lines": len(lines),
        "human_ref_dash_placeholder_lines": dash_lines,
        "normalization_rules": "NFKC 全角转半角、小写、去标点与符号(P/S 类)、去空白(含换行)、中文数字转阿拉伯数字；语气词(呃/啊/嗯)保留参与计分",
        "ref_norm_chars": len(norm_ref),
        "ref_filler_counts_after_normalize": filler_counts,
    },
    "segment": SID,
    "cer_local_vs_humanref": m_local,
    "cer_cloud_vs_humanref": m_cloud,
    "ac2_relative_gap_vs_humanref": gap,
    "ac2_pass_threshold_15pct": (gap is not None and gap <= 0.15),
    "qa_r1_baseline": {
        "cer_local_vs_cloudref_pseudo": existing[SID]["cer_local_vs_cloudref"]["cer"],
        "source": ".eval_local_engine/results/metrics.json (2026-09-24 15:02, QA-R1 伪参照)",
    },
    "deviation_vs_qa_r1": {
        "humanref_minus_pseudoref_pp": round((wl - existing[SID]["cer_local_vs_cloudref"]["cer"]) * 100, 2),
        "note": "百分点差 = cer_local_vs_humanref - cer_local_vs_cloudref(QA-R1 伪参照)",
    },
    "formal_judgement": "NOT_FINAL — 正式 AC-2 判级须待 SEG-4P/SEG-6P 人工参照回填后三档合并产出",
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1))
print(f"[DONE] preview metrics → {OUT}", file=sys.stderr)
