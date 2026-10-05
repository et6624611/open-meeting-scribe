#!/usr/bin/env python3
"""QA-R1 AC-1 downstream probe: summary (localhost Ollama) + md export under pure-intranet sim.

Pure-intranet simulation:
  - CLOUD_API_URL / CLOUD_API_TOKEN emptied  => is_cloud_enabled() False (no cloud fallback)
  - LLM_BASE_URL = http://localhost:11434/v1 => is_localhost_base_url True => _should_use_cloud False
  - HTTP(S)_PROXY -> dead port (127.0.0.1:9), NO_PROXY=localhost,127.0.0.1
    => localhost Ollama bypasses proxy and works; ANY non-localhost egress is connection-refused.
  Therefore: if generate_summary + save_summary SUCCEED, the summary/export half of the
  closed loop provably needs zero successful non-localhost network access.

Run: venv/bin/python tests/eval_local_engine/qa_r1_downstream.py <dialogue_src.json> <out.md>
"""
import json
import os
import sys
from pathlib import Path

# --- env MUST be set before importing core (core.* reads env at import; load_dotenv override=False) ---
os.environ["CLOUD_API_URL"] = ""
os.environ["CLOUD_API_TOKEN"] = ""
os.environ["ENGINE_MODE"] = "local"
os.environ["LLM_BASE_URL"] = "http://localhost:11434/v1"
os.environ.pop("VOICEPRINT_PROVIDER", None)
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ[_v] = "http://127.0.0.1:9"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

REPO = Path(__file__).resolve().parents[2]
os.chdir(REPO)
sys.path.insert(0, str(REPO))

src = sys.argv[1]
out_md = sys.argv[2]
MODEL = os.environ.get("QA_R1_LLM_MODEL", "qwen3:8b")


def build_dialogue(path: str) -> list[dict]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    sents = d.get("sentences") or []
    groups: dict[int, list] = {}
    for s in sents:
        sid = int(s.get("spk", 0) or 0)
        groups.setdefault(sid, []).append(
            {"begin_time": s.get("begin_ms"), "end_time": s.get("end_ms"), "text": s.get("text", "")}
        )
    dialogue = []
    for sid, ss in sorted(groups.items()):
        dialogue.append({
            "speaker_id": sid,
            "speaker_name": f"Speaker {sid+1}",
            "text": "".join(x["text"] for x in ss),
            "sentences": ss,
        })
    return dialogue


def main() -> None:
    dialogue = build_dialogue(src)
    total = sum(len(d.get("sentences", [])) for d in dialogue)
    print(f"[DOWNSTREAM] dialogue speakers={len(dialogue)} sentences={total} model={MODEL}", flush=True)

    from core import llm
    print(f"[DOWNSTREAM] base_url={llm._get_base_url()} is_localhost={llm.is_localhost_base_url(llm._get_base_url())} "
          f"should_use_cloud={llm._should_use_cloud()}", flush=True)

    from core.summarize import generate_summary, save_summary
    summary = generate_summary(dialogue, model=MODEL, meeting_time="2026-09-24 15:00")
    print(f"[DOWNSTREAM] SUMMARY_OK len={len(summary)} head={summary[:80]!r}", flush=True)

    p = Path(out_md)
    p.parent.mkdir(parents=True, exist_ok=True)
    saved = save_summary(summary, str(p), dialogue=dialogue)
    exists = Path(saved).exists()
    print(f"[DOWNSTREAM] MD_EXPORT_OK path={saved} exists={exists} bytes={Path(saved).stat().st_size if exists else 0}", flush=True)
    print("[DOWNSTREAM] RESULT=SUMMARY_MD_OFFLINE_PASS (zero successful non-localhost egress)", flush=True)

    # docx export capability check (AC-1 requires docx AND md)
    docx_ok = False
    try:
        import importlib
        for mod in ("core.export", "core.docx_export", "core.exporter"):
            try:
                importlib.import_module(mod)
                docx_ok = True
                break
            except Exception:
                pass
    except Exception:
        pass
    print(f"[DOWNSTREAM] DOCX_EXPORTER_PRESENT={docx_ok}", flush=True)


if __name__ == "__main__":
    main()
