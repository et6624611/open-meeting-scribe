#!/usr/bin/env python3
"""WP-C R4 实验 — LLM 最低推荐规格评测（可复跑，全程本机 Ollama，零云端消耗）。

方法：
  - 输入：本地 FunASR 转写的真实会议片段对话稿（SEG-2P 双人 / SEG-6P 六人），
    按 core/summarize.generate_summary 相同的用户消息结构组装；
  - 系统提示词：直接复用项目 core/summarize.SYSTEM_PROMPT（与生产一致）；
  - 模型档：qwen2.5:1.5b-instruct / qwen2.5:3b-instruct / qwen3:4b / qwen3:8b / qwen3:14b，
    统一 temperature=0.7、max_tokens=4096、qwen3 系列关闭思考模式（think=false）；
  - 评分：
    a) 结构正确率：7 项结构清单命中比例（标题/时间/参会/概要/结论/待办/议题）；
    b) 幻觉-词面：输出中不在转写原文与提示词模板内的专名/数字 token 数；
    c) 幻觉-裁判：qwen3:14b 固定裁判列出纪要中无原文依据的陈述条数；
    d) 延迟（秒）。

运行：venv/bin/python tests/eval_local_engine/run_llm_tiers.py
产物：.eval_local_engine/results/llm_tiers.json、results/llm_outputs/*.md
"""
import json
import re
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
EVAL = REPO / ".eval_local_engine"
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODELS = ["qwen2.5:1.5b-instruct", "qwen2.5:3b-instruct", "qwen3:4b", "qwen3:8b", "qwen3:14b"]
JUDGE = "qwen3:14b"
SEGMENTS = ["SEG-2P", "SEG-6P"]
STRUCT_CHECKS = ["# 会议纪要", "会议时间", "参会人员", "一、会议概要", "二、主要结论", "三、待办事项", "四、议题归类"]


def build_dialogue(seg_id: str) -> tuple[list[dict], str]:
    d = json.loads((EVAL / "results" / f"local_{seg_id}.json").read_text(encoding="utf-8"))
    merged: dict[int, list[str]] = {}
    order: list[int] = []
    for s in d["sentences"]:
        spk = s.get("spk", 0)
        if spk not in merged:
            merged[spk] = []
            order.append(spk)
        merged[spk].append(s["text"])
    dialogue = [{"speaker_id": spk, "speaker_name": f"Speaker {spk + 1}",
                 "text": "\n".join(merged[spk])} for spk in order]
    return dialogue, d["text"]


def build_user_content(dialogue: list[dict]) -> str:
    total_sentences = sum(len(d["text"].split("\n")) for d in dialogue)
    speaker_info = "，".join(f"Speaker {d['speaker_id'] + 1} = {d['speaker_name']}" for d in dialogue)
    uc = "请根据以下会议对话内容生成会议纪要：\n\n---\n"
    uc += f"**说话人数量**：{len(dialogue)} 位\n"
    uc += f"**发言人对应关系**：{speaker_info}\n"
    uc += f"**对话总句数**：{total_sentences} 句\n"
    uc += "---\n\n## 对话内容\n\n"
    for d in dialogue:
        uc += f"**{d['speaker_name']}**：{d['text']}\n\n"
    return uc


def call_ollama(model: str, messages: list[dict], temperature=0.7, max_tokens=4096) -> tuple[str, float]:
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "stream": False}
    if model.startswith("qwen3"):
        body["think"] = False
    t0 = time.time()
    resp = requests.post(OLLAMA_URL, json=body, timeout=1800)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return content, round(time.time() - t0, 1)


def norm_tokens(text: str) -> set[str]:
    t = re.sub(r"\s+", "", text)
    toks = set(re.findall(r"[\u4e00-\u9fff]{2,6}", t))
    toks |= set(re.findall(r"[0-9]+(?:\.[0-9]+)?%?", t))
    return toks


def wordface_hallucination(minutes: str, transcript: str, prompt_text: str) -> list[str]:
    src = norm_tokens(transcript) | norm_tokens(prompt_text)
    # 模板/结构性词汇白名单（来自系统提示词本身 + 常见纪要用语）
    extra = {"会议纪要", "会议时间", "参会人员", "纪要生成", "自动生成", "会议概要", "主要结论",
             "待办事项", "议题归类", "负责人", "截止日期", "说话人", "原始录音", "仅供参考",
             "本纪要由", "会议录音", "生成", "如有疑义", "请以", "为准"}
    out = norm_tokens(minutes) - src - extra
    return sorted(out)


def judge_hallucination(minutes: str, transcript: str) -> list[str]:
    prompt = (
        "你是严格的质检员。下面是会议转写原文与据其生成的会议纪要。"
        "请列出纪要中所有在转写原文中找不到依据的陈述（编造的人名/机构/数字/日期/结论/待办/负责人等），"
        "合理的概括、去口语化改写、结构化重组不算幻觉。"
        '只输出 JSON：{"unsupported": ["..."]}，没有则输出 {"unsupported": []}。\n\n'
        f"## 转写原文\n{transcript}\n\n## 会议纪要\n{minutes}"
    )
    content, _ = call_ollama(JUDGE, [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=2048)
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return ["<judge 输出无法解析>"]
    try:
        return json.loads(m.group(0)).get("unsupported", [])
    except Exception:
        return ["<judge JSON 解析失败>"]


def main() -> None:
    from core.summarize import SYSTEM_PROMPT
    # 可选参数：仅跑指定模型（增量合并既有结果），如 run_llm_tiers.py qwen2.5:1.5b-instruct
    models = [m for m in sys.argv[1:] if m in MODELS] or MODELS
    outdir = EVAL / "results" / "llm_outputs"
    outdir.mkdir(parents=True, exist_ok=True)
    results = {"judge_model": JUDGE, "system_prompt_source": "core/summarize.SYSTEM_PROMPT",
               "runs": []}
    dst = EVAL / "results" / "llm_tiers.json"
    if dst.exists():  # 增量合并：保留本次未重跑模型的既有结果
        prev = json.loads(dst.read_text(encoding="utf-8"))
        results["runs"] = [r for r in prev.get("runs", []) if r.get("model") not in models]
    for seg_id in SEGMENTS:
        dialogue, transcript = build_dialogue(seg_id)
        uc = build_user_content(dialogue)
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": uc}]
        for model in models:
            try:
                minutes, latency = call_ollama(model, messages)
            except Exception as e:
                print(f"[{seg_id}/{model}] 调用失败: {e}", file=sys.stderr)
                results["runs"].append({"segment": seg_id, "model": model, "error": str(e)})
                continue
            (outdir / f"{model.replace(':', '_')}_{seg_id}.md").write_text(minutes, encoding="utf-8")
            struct_hits = [c for c in STRUCT_CHECKS if c in minutes]
            wf = wordface_hallucination(minutes, transcript, SYSTEM_PROMPT + uc)
            judged = judge_hallucination(minutes, transcript)
            run = {
                "segment": seg_id, "model": model, "latency_seconds": latency,
                "output_chars": len(minutes),
                "structure_score": round(len(struct_hits) / len(STRUCT_CHECKS), 3),
                "structure_missing": [c for c in STRUCT_CHECKS if c not in minutes],
                "wordface_unsupported_tokens": wf,
                "wordface_unsupported_count": len(wf),
                "judge_unsupported_claims": judged,
                "judge_unsupported_count": len(judged),
            }
            results["runs"].append(run)
            print(f"[{seg_id}/{model}] latency={latency}s struct={run['structure_score']} "
                  f"wordface={len(wf)} judged={len(judged)}", flush=True)
    dst = EVAL / "results" / "llm_tiers.json"
    dst.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[DONE] run_llm_tiers → {dst}")


if __name__ == "__main__":
    main()
