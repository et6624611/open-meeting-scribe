"""
scripts/eval_decision_extract.py — 决策独立提取的样本评估

对仓库内真实会议任务（含对话稿）实跑 core.decision_extract，输出：
  - 每场提取的决策清单（含发起方/依据/范围/出处）与纪要待办清单；
  - 决策→待办混入检测（决策内容是否出现在待办 checkbox 解析结果里，应为 0）；
  - 决策上下文字段覆盖率、提取成功率等汇总指标。

精确率/召回率（是否"真决策"、是否遗漏）需人工核对输出明细判定，
本脚本不虚构这两项数字；它产出供人工核对的结构化结果与可自动判定的隔离/成功率指标。

用法：
    .venv/bin/python scripts/eval_decision_extract.py --sample 8
    .venv/bin/python scripts/eval_decision_extract.py --ids 557c1d66-... 424c0a7f-...
报告默认写入 /tmp/decision_eval_report.json（测试输出不入仓库）。
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.decision_extract import extract_decisions  # noqa: E402
from core.summarize import parse_decision_checklist  # noqa: E402


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _task_files() -> list[Path]:
    return [
        p for p in (ROOT / "data" / "tasks").glob("*.json")
        if not p.name.endswith((".insights.json", ".formal.json"))
        and ".joblog" not in p.name and ".board" not in p.name
    ]


def eval_task(path: Path, timeout: float) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    dialogue = d.get("dialogue") or []
    summary = d.get("summary") or ""
    res = {
        "task_id": d.get("id") or path.stem,
        "title": d.get("title") or d.get("audio_name") or path.stem,
        "n_dialogue": len(dialogue),
        "n_sentences": sum(len(x.get("sentences") or []) for x in dialogue),
        "ok": False,
        "error": None,
        "decisions": [],
        "todos": [],
        "contamination": 0,   # 决策文本混入待办的条数
        "ctx_full": 0,        # 发起方+依据+范围均非空的决策数
    }
    try:
        items = extract_decisions(dialogue, meeting_time=d.get("meeting_date"), timeout=timeout)
        res["ok"] = True
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        items = []
    res["decisions"] = items

    todos = parse_decision_checklist(summary) if summary else []
    res["todos"] = [t.get("text") or "" for t in todos]

    todo_keys = [_norm(t) for t in res["todos"] if _norm(t)]
    for it in items:
        dt = _norm(it.get("text", ""))
        if it.get("initiator") and it.get("rationale") and it.get("scope"):
            res["ctx_full"] += 1
        # 决策内容若与任一待办高度重叠（互相包含），计为混入
        for tk in todo_keys:
            if len(dt) >= 6 and (dt in tk or (tk and tk in dt)):
                res["contamination"] += 1
                break
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=8, help="随机抽样场数")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ids", nargs="*", default=None, help="指定任务 id（可前缀）")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--out", default="/tmp/decision_eval_report.json")
    args = ap.parse_args()

    files = _task_files()
    # 仅保留有对话稿且有实质内容的任务
    candidates = []
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("dialogue") and sum(len(x.get("sentences") or []) for x in d["dialogue"]) >= 4:
            candidates.append(p)

    if args.ids:
        picked = [p for p in candidates if any(p.stem.startswith(i) for i in args.ids)]
    else:
        random.seed(args.seed)
        picked = random.sample(candidates, min(args.sample, len(candidates)))

    results = []
    for p in picked:
        r = eval_task(p, args.timeout)
        results.append(r)
        print(f"[{'OK' if r['ok'] else 'ERR'}] {r['title'][:30]:<32} "
              f"决策={len(r['decisions'])} 待办={len(r['todos'])} 混入={r['contamination']} "
              f"上下文完整={r['ctx_full']}" + (f" 错误={r['error']}" if r["error"] else ""))

    n = len(results)
    ok = sum(1 for r in results if r["ok"])
    total_dec = sum(len(r["decisions"]) for r in results)
    total_contam = sum(r["contamination"] for r in results)
    ctx_full = sum(r["ctx_full"] for r in results)

    print("\n===== 汇总 =====")
    print(f"评估场数: {n}  提取成功: {ok} ({ok / n * 100:.0f}%)" if n else "无样本")
    print(f"决策总数: {total_dec}  待办总数: {sum(len(r['todos']) for r in results)}")
    print(f"决策→待办混入条数: {total_contam}  (隔离率 {(1 - total_contam / total_dec) * 100:.0f}%)" if total_dec else "无决策")
    print(f"上下文完整决策: {ctx_full}/{total_dec} ({ctx_full / total_dec * 100:.0f}%)" if total_dec else "")
    print("\n注：决策精确率/召回率需人工核对报告明细判定，本脚本不虚构。")

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细报告: {args.out}")


if __name__ == "__main__":
    main()
