#!/usr/bin/env python3
"""WP-C AC-2 评测 — 指标计算（可复跑）。

计算内容：
  1. 字错误率 CER（中文按字符级 Levenshtein，统一归一化：去标点/空白、全角转半角、
     小写、中文数字转阿拉伯数字）；
  2. 参照体系三层：
     a) cloud 全新转写作为伪参照 → CER(local vs cloud)、对称 CER(cloud vs local)；
     b) 自动共识参照（cloud 为基底，差异区按热词映射表裁决，无法裁决默认 cloud 并标记
        uncertain）→ CER(local vs consensus)、CER(cloud vs consensus)、相对差距；
     c) 人工校对参照（若存在 refs/<SEG>_human_ref.txt 则计算正式 AC-2 指标，优先级最高）；
  3. 说话人分离近似 DER：以云端全新转写 diarization 为伪参照时间线，10ms 帧粒度，
     穷举映射（≤8 说话人）求最优标签对齐，DER = (Miss + FA + Confusion) / Ref总时长；
     同时输出说话人计数误差与帧级一致率；
  4. 人工校对工作表（逐句对齐 cloud/local 文本，标记差异）。

运行：venv/bin/python tests/eval_local_engine/compute_metrics.py [SEG-ID ...]
产物：.eval_local_engine/results/metrics.json、refs/<SEG>_proofread_worksheet.md、
      refs/<SEG>_consensus.json
"""
import json
import re
import sys
import unicodedata
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / ".eval_local_engine"
MANIFEST = json.loads((REPO / "tests/eval_local_engine/eval_manifest.json").read_text(encoding="utf-8"))
FRAME_MS = 10

CN_NUM = "零一二三四五六七八九十万亿两"
CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "两": 2}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}
CN_BIGUNITS = {"万": 10000, "亿": 100000000}


def _cn_run_to_int(run: str):
    """把一个中文数字串转成整数；失败返回 None。"""
    total, section, num = 0, 0, None
    for ch in run:
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            if num is None:
                num = 1
            section += num * CN_UNITS[ch]
            num = None
        elif ch in CN_BIGUNITS:
            if num is None:
                num = 1
            section = (section + num) * CN_BIGUNITS[ch]
            total += section
            section, num = 0, None
        else:
            return None
    if num is not None:
        section += num
    return total + section


def normalize(text: str) -> str:
    """统一归一化：全角→半角、小写、去标点与空白、中文数字→阿拉伯数字。"""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    out = []
    for ch in text:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            continue
        out.append(ch)
    s = "".join(out)

    def repl(m):
        v = _cn_run_to_int(m.group(0))
        return str(v) if v is not None else m.group(0)

    s = re.sub(f"[{CN_NUM}]+", repl, s)
    return s


def edit_distance(a: str, b: str) -> int:
    return _edit_ops(a, b)["total"]


def _edit_ops(a: str, b: str) -> dict:
    """Levenshtein 距离 + 替换/插入/删除分解（回溯）。a=ref, b=hyp。"""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        row, prev = dp[i], dp[i - 1]
        ca = a[i - 1]
        for j in range(1, m + 1):
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (ca != b[j - 1]))
    i, j = n, m
    sub = ins = dele = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]):
            if a[i - 1] != b[j - 1]:
                sub += 1
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return {"total": sub + ins + dele, "sub": sub, "ins": ins, "del": dele}


def cer(ref: str, hyp: str) -> dict:
    r, h = normalize(ref), normalize(hyp)
    ops = _edit_ops(r, h)
    return {"ref_chars": len(r), "hyp_chars": len(h), "edits": ops["total"],
            "sub": ops["sub"], "ins": ops["ins"], "del": ops["del"],
            "cer": round(ops["total"] / len(r), 4) if r else None}


def load_hotword_mappings() -> list[tuple[str, str]]:
    f = REPO / "data/hotword_mappings.txt"
    pairs = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "→" in line:
                src, _, dst = line.partition("→")
                if src.strip() and dst.strip():
                    pairs.append((src.strip(), dst.strip()))
    return pairs


def apply_mappings(text: str, pairs: list[tuple[str, str]]) -> str:
    for src, dst in pairs:
        text = text.replace(src, dst)
    return text


def align_sentences(local_sents: list[dict], cloud_sents: list[dict]) -> list[dict]:
    """多对一时间对齐：local 句子粒度通常比 cloud 细，多条 local 可对应同一条 cloud。

    返回按 cloud 句子排序的组：{"cloud": cs|None, "local": [ls...], "overlap_ms": int}
    未匹配任何 cloud 句的 local 句子单独成组（cloud=None）。
    """
    groups: list[dict] = [{"cloud": cs, "local": [], "overlap_ms": 0} for cs in cloud_sents]
    orphans: list[dict] = []
    for ls in local_sents:
        best, best_ov = None, 0
        for gi, g in enumerate(groups):
            cs = g["cloud"]
            ov = min(ls["end_ms"], cs["end_ms"]) - max(ls["begin_ms"], cs["begin_ms"])
            if ov > best_ov:
                best, best_ov = gi, ov
        if best is not None and best_ov > 0:
            groups[best]["local"].append(ls)
            groups[best]["overlap_ms"] += best_ov
        else:
            orphans.append(ls)
    for g in groups:
        g["local"].sort(key=lambda s: s["begin_ms"])
    out = [g for g in groups if g["local"] or g["cloud"]]
    for ls in orphans:
        out.append({"cloud": None, "local": [ls], "overlap_ms": 0})
    out.sort(key=lambda g: (g["cloud"] or g["local"][0])["begin_ms"])
    return out


def build_consensus(pairs: list[dict], mappings: list[tuple[str, str]]) -> tuple[str, list[dict]]:
    """共识参照：cloud 为基底；差异区若 local 含热词映射目标词而 cloud 含源词，则采纳 local。"""
    texts, uncertain = [], []
    for p in pairs:
        cs = p["cloud"]
        ltext = "".join(s["text"] for s in p["local"])
        if cs and not p["local"]:
            texts.append(cs["text"])
            continue
        if p["local"] and not cs:
            uncertain.append({"begin_ms": p["local"][0]["begin_ms"], "local": ltext, "cloud": None,
                              "decision": "local_included", "reason": "cloud 无对应句"})
            texts.append(ltext)
            continue
        if not cs or not ltext:
            continue
        ct, lt = normalize(cs["text"]), normalize(ltext)
        if ct == lt:
            texts.append(cs["text"])
            continue
        chosen, reason = cs["text"], "default_cloud"
        for src, dst in mappings:
            ns, nd = normalize(src), normalize(dst)
            if nd and nd in lt and nd not in ct and ns in ct:
                chosen, reason = ltext, f"hotword:{src}→{dst}"
                break
        if reason == "default_cloud":
            uncertain.append({"begin_ms": cs["begin_ms"], "cloud": cs["text"],
                              "local": ltext, "decision": "cloud_kept",
                              "reason": "无法自动裁决，默认云端，待人工复核"})
        texts.append(chosen)
    return "".join(texts), uncertain


def timeline_to_frames(sentences: list[dict], label_key: str, total_ms: int) -> list:
    n = total_ms // FRAME_MS + 1
    frames = [-1] * n
    for s in sentences:
        b, e = max(0, s["begin_ms"] or 0), min(total_ms, s["end_ms"] or 0)
        lab = s.get(label_key)
        for i in range(b // FRAME_MS, max(b // FRAME_MS, (e + FRAME_MS - 1) // FRAME_MS)):
            if i < n:
                frames[i] = lab if lab is not None else -1
    return frames


def der_approx(ref_sents: list[dict], hyp_sents: list[dict], total_ms: int) -> dict:
    """伪参照 DER：ref=云端句子时间线，hyp=本地 sentence_info。穷举标签映射（≤8 人）。"""
    ref_f = timeline_to_frames(ref_sents, "speaker", total_ms)
    hyp_f = timeline_to_frames(hyp_sents, "spk", total_ms)
    ref_labels = sorted({f for f in ref_f if f != -1}, key=str)
    hyp_labels = sorted({f for f in hyp_f if f != -1}, key=lambda x: (x is None, x))
    # 重叠矩阵
    ov = {}
    for hl in hyp_labels:
        for rl in ref_labels:
            c = sum(1 for a, b in zip(ref_f, hyp_f) if a == rl and b == hl)
            if c:
                ov[(hl, rl)] = c
    best_map, best_score = {}, -1
    if len(hyp_labels) <= 8 and len(ref_labels) <= 8:
        for perm in permutations(ref_labels, min(len(hyp_labels), len(ref_labels))):
            m = dict(zip(hyp_labels[:len(perm)], perm))
            score = sum(ov.get((h, r), 0) for h, r in m.items())
            if score > best_score:
                best_map, best_score = m, score
    else:  # 贪心兜底
        used = set()
        for hl in hyp_labels:
            cands = sorted(((c, rl) for (h, rl), c in ov.items() if h == hl and rl not in used), reverse=True)
            if cands:
                best_map[hl] = cands[0][1]
                used.add(cands[0][1])
    miss = sum(1 for a, b in zip(ref_f, hyp_f) if a != -1 and b == -1)
    fa = sum(1 for a, b in zip(ref_f, hyp_f) if a == -1 and b != -1)
    conf = sum(1 for a, b in zip(ref_f, hyp_f)
               if a != -1 and b != -1 and best_map.get(b) != a)
    agree = sum(1 for a, b in zip(ref_f, hyp_f) if a != -1 and b != -1 and best_map.get(b) == a)
    total_ref = sum(1 for a in ref_f if a != -1)
    der = (miss + fa + conf) / total_ref if total_ref else None
    return {
        "note": "伪参照 DER：以云端 paraformer-v2 diarization 为参照时间线（非人工标注真值），帧粒度 10ms，穷举最优标签映射",
        "ref_speakers": len(ref_labels), "hyp_speakers": len(hyp_labels),
        "label_map_hyp_to_ref": {str(k): str(v) for k, v in best_map.items()},
        "ref_speech_seconds": round(total_ref * FRAME_MS / 1000, 1),
        "miss_seconds": round(miss * FRAME_MS / 1000, 1),
        "false_alarm_seconds": round(fa * FRAME_MS / 1000, 1),
        "confusion_seconds": round(conf * FRAME_MS / 1000, 1),
        "der": round(der, 4) if der is not None else None,
        "frame_agreement_on_ref_speech": round(agree / total_ref, 4) if total_ref else None,
    }


def write_worksheet(seg_id: str, pairs: list[dict], path: Path) -> None:
    lines = [f"# {seg_id} 人工校对工作表（AC-2 正式参照产出用）",
             "",
             "校对方法：逐句听音频裁决 cloud/local 两版文本，将最终参照文本（每句一行，无需时间戳）",
             f"保存为 `refs/{seg_id}_human_ref.txt` 后重跑 compute_metrics.py 即得正式 AC-2 指标。",
             "",
             "| 时间(s) | 云端 paraformer-v2 | 本地 FunASR | 一致 |",
             "|---|---|---|---|"]
    for p in pairs:
        c = p["cloud"]
        ltext = "".join(s["text"] for s in p["local"]) or None
        t = ((c or p["local"][0])["begin_ms"] or 0) / 1000
        ct = (c or {}).get("text", "—").replace("|", "\\|") if c else "—"
        lt = (ltext or "—").replace("|", "\\|")
        same = "✅" if c and ltext and normalize(c["text"]) == normalize(ltext) else "⚠️"
        lines.append(f"| {t:.1f} | {ct} | {lt} | {same} |")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    only = set(sys.argv[1:])
    segs = [s for s in MANIFEST["segments"] if not only or s["id"] in only]
    mappings = load_hotword_mappings()
    all_metrics = {}
    for seg in segs:
        sid = seg["id"]
        lf = EVAL / "results" / f"local_{sid}.json"
        cf = EVAL / "results" / f"cloud_{sid}.json"
        if not lf.exists() or not cf.exists():
            print(f"[SKIP] {sid}: 缺少 local/cloud 结果", file=sys.stderr)
            continue
        local = json.loads(lf.read_text(encoding="utf-8"))
        cloud = json.loads(cf.read_text(encoding="utf-8"))
        total_ms = seg["duration_s"] * 1000

        pairs = align_sentences(local["sentences"], cloud["sentences"])
        consensus_text, uncertain = build_consensus(pairs, mappings)
        (EVAL / "refs" / f"{sid}_consensus.json").write_text(json.dumps({
            "segment": sid, "method": "cloud 基底 + 热词映射裁决；uncertain 句默认云端待人工复核",
            "uncertain_count": len(uncertain), "uncertain": uncertain,
            "consensus_text": consensus_text,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        write_worksheet(sid, pairs, EVAL / "refs" / f"{sid}_proofread_worksheet.md")

        m = {
            "segment": sid,
            "expected_speakers": seg["expected_speakers"],
            "speakers_detected_local": len(local["speakers_detected"]),
            "speakers_detected_cloud": len(cloud["speakers_detected"]),
            "local_infer_seconds": local["infer_seconds"],
            "local_rtf": local["rtf"],
            "cloud_elapsed_seconds": cloud["elapsed_seconds"],
            "cer_local_vs_cloudref": cer(cloud["full_text"], local["text"]),
            "cer_cloud_vs_localref": cer(local["text"], cloud["full_text"]),
            "cer_local_vs_consensus": cer(consensus_text, local["text"]),
            "cer_cloud_vs_consensus": cer(consensus_text, cloud["full_text"]),
            "consensus_uncertain_sentences": len(uncertain),
            "der_local_vs_cloud_pseudoref": der_approx(cloud["sentences"], local["sentences"], total_ms),
        }
        # 辅助参照 DER：历史全量转写时间线（人工绑定姓名，全局上下文分离，质量高于片段重跑）
        hist_file = EVAL / "refs" / f"{sid}_cloud_timeline.json"
        if hist_file.exists():
            hist = json.loads(hist_file.read_text(encoding="utf-8"))
            m["der_local_vs_hist_timeline"] = der_approx(hist["sentences"], local["sentences"], total_ms)
            m["hist_timeline_speakers"] = len({s["speaker"] for s in hist["sentences"]})
        # 热词映射后的补充口径（两引擎同规则替换后再算，衡量 R2 热词必配项的收益）
        if mappings:
            m["cer_local_vs_cloudref_hotword_applied"] = cer(
                apply_mappings(cloud["full_text"], mappings),
                apply_mappings(local["text"], mappings))
        # 人工参照（若已校对）→ 正式 AC-2 指标
        human = EVAL / "refs" / f"{sid}_human_ref.txt"
        if human.exists():
            ht = human.read_text(encoding="utf-8")
            m["cer_local_vs_humanref"] = cer(ht, local["text"])
            m["cer_cloud_vs_humanref"] = cer(ht, cloud["full_text"])
            wl, wc = m["cer_local_vs_humanref"]["cer"], m["cer_cloud_vs_humanref"]["cer"]
            if wc and wc > 0:
                m["ac2_relative_gap_vs_humanref"] = round((wl - wc) / wc, 4)
                m["ac2_pass_threshold_15pct"] = m["ac2_relative_gap_vs_humanref"] <= 0.15
        all_metrics[sid] = m
        print(f"[{sid}] CER(local|cloud-ref)={m['cer_local_vs_cloudref']['cer']} "
              f"CER(local|consensus)={m['cer_local_vs_consensus']['cer']} "
              f"CER(cloud|consensus)={m['cer_cloud_vs_consensus']['cer']} "
              f"DER(fresh)={m['der_local_vs_cloud_pseudoref']['der']} "
              f"DER(hist)={m.get('der_local_vs_hist_timeline', {}).get('der')} "
              f"spk local/cloud/expected={m['speakers_detected_local']}/"
              f"{m['speakers_detected_cloud']}/{m['expected_speakers']}", flush=True)

    dst = EVAL / "results" / "metrics.json"
    dst.write_text(json.dumps(all_metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[DONE] compute_metrics → {dst}")


if __name__ == "__main__":
    main()
