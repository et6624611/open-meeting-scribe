"""ASSET_SYNC P0 回归：定稿口径收口（G2/G3）+ 产物清理补全（G4/G5）。

契约来源：docs/design/ASSET_SYNC_ARCHITECTURE.md §6 P0。
"""

import pytest
from fastapi import BackgroundTasks

import app.routers.tasks as tasks_router
import core.task_store as task_store
from core.chat_context import task_final_summary
from core.docx_export import export_task_docx
from core.projects import _build_sync_markdown


def _task(**kw) -> dict:
    base = {
        "task_id": "p0test-0001",
        "title": "P0 回归会",
        "meeting_date": "2026-11-11",
        "summary": "AI 初稿内容",
        "dialogue": [],
        "decisions": [],
    }
    base.update(kw)
    return base


# ── G3：空串 user_summary 的定稿口径（存在即优先，非空即优先是错的） ──


def test_empty_user_summary_is_authoritative_in_kb_markdown():
    task = _task(user_summary="")
    assert task_final_summary(task) == ""
    md = _build_sync_markdown(task, ["summary"])
    # 用户显式清空纪要后，知识库副本不得回退展示 AI 初稿
    assert "AI 初稿内容" not in md
    assert "## 会议纪要" not in md


def test_kb_markdown_prefers_nonempty_user_summary():
    task = _task(user_summary="用户编辑版")
    md = _build_sync_markdown(task, ["summary"])
    assert "用户编辑版" in md
    assert "AI 初稿内容" not in md


# ── G2：docx 回退口径收口到定稿 ──


def test_docx_fallback_uses_final_summary(monkeypatch, tmp_path):
    captured = {}

    def fake_md2docx(md_text, out_path):
        captured["md"] = md_text
        return str(out_path)

    monkeypatch.setattr("core.docx_export.markdown_to_docx", fake_md2docx)
    task = _task(user_summary="用户编辑版", output_path=str(tmp_path / "不存在.md"))
    export_task_docx(task, tmp_path / "out.docx")
    assert captured["md"] == "用户编辑版"


def test_docx_fallback_empty_final_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "core.docx_export.markdown_to_docx",
        lambda *a: pytest.fail("定稿为空时不应渲染 docx"),
    )
    task = _task(user_summary="")
    with pytest.raises(FileNotFoundError):
        export_task_docx(task, tmp_path / "out.docx")


# ── G5：任务删除清理覆盖全部 sidecar ──


def test_purge_covers_formal_and_rewrites(monkeypatch, tmp_path):
    monkeypatch.setattr(tasks_router, "TASKS_DIR", tmp_path)
    monkeypatch.setattr(task_store, "TASKS_DIR", tmp_path)
    tid = "p0purge-0001"
    for suffix in (".json", ".joblog.jsonl", ".insights.json", ".formal.json", ".rewrites.jsonl"):
        (tmp_path / f"{tid}{suffix}").write_text("{}", encoding="utf-8")
    tasks_router._purge_task_artifacts(tid, {"task_id": tid})
    assert not list(tmp_path.glob(f"{tid}*"))


# ── G4：retranscribe 重置前清理旧导出件 ──


def test_retranscribe_removes_stale_exports(monkeypatch, tmp_path):
    monkeypatch.setattr(task_store, "TASKS_DIR", tmp_path)
    audio = tmp_path / "rec.wav"
    audio.write_bytes(b"RIFF")
    md = tmp_path / "rec_20261111_纪要.md"
    md.write_text("旧纪要", encoding="utf-8")
    docx = md.with_suffix(".docx")
    docx.write_bytes(b"PK")

    tid = "p0retrans-0001"
    task = _task(task_id=tid, audio_path=str(audio), output_path=str(md), status="completed")
    monkeypatch.setitem(tasks_router.tasks, tid, task)

    tasks_router.retranscribe_task(tid, BackgroundTasks(), None)

    assert not md.exists()
    assert not docx.exists()
    assert tasks_router.tasks[tid]["output_path"] is None
