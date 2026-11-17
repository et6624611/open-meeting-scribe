"""scripts/strip_word_timings.py 迁移脚本：幂等、只动任务主体、可预演。"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "strip_word_timings", ROOT / "scripts" / "strip_word_timings.py"
)


@pytest.fixture(scope="module")
def mod():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


def _task(sentences):
    return {
        "task_id": "mig-1",
        "status": "completed",
        "dialogue": [{"speaker_id": 0, "text": "示例", "sentences": sentences}],
    }


def _sent(text, sid=1):
    return {"begin_time": 0, "end_time": 1000, "text": text, "sentence_id": sid,
            "speaker_id": 0, "words": [{"begin_time": 0, "end_time": 100, "text": "示"}]}


def _run(mod, monkeypatch, tmp_path, apply=False):
    argv = ["strip_word_timings.py", "--dir", str(tmp_path)]
    if apply:
        argv.append("--apply")
    monkeypatch.setattr("sys.argv", argv)
    return mod.main()


def test_strip_words_removes_and_counts(mod):
    task = _task([_sent("一"), _sent("二")])
    assert mod.strip_words(task) == 2
    assert all("words" not in s for s in task["dialogue"][0]["sentences"])
    # 幂等
    assert mod.strip_words(task) == 0


def test_dry_run_does_not_touch_disk(mod, tmp_path, monkeypatch, capsys):
    path = tmp_path / "mig-1.json"
    path.write_text(json.dumps(_task([_sent("一")]), ensure_ascii=False), encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    assert _run(mod, monkeypatch, tmp_path) == 0
    assert path.read_text(encoding="utf-8") == before
    assert "预演模式" in capsys.readouterr().out


def test_apply_strips_and_is_idempotent(mod, tmp_path, monkeypatch):
    path = tmp_path / "mig-1.json"
    path.write_text(json.dumps(_task([_sent("一")]), ensure_ascii=False, indent=2), encoding="utf-8")
    size_before = path.stat().st_size

    assert _run(mod, monkeypatch, tmp_path, apply=True) == 0
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "words" not in saved["dialogue"][0]["sentences"][0]
    assert path.stat().st_size < size_before

    # 第二次运行无命中，不应报错
    assert _run(mod, monkeypatch, tmp_path, apply=True) == 0


def test_sidecar_files_untouched(mod, tmp_path, monkeypatch):
    sidecar = tmp_path / "mig-1.insights.json"
    sidecar.write_text('{"words": [1, 2]}', encoding="utf-8")

    assert _run(mod, monkeypatch, tmp_path, apply=True) == 0
    assert sidecar.read_text(encoding="utf-8") == '{"words": [1, 2]}'
