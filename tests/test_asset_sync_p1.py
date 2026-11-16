"""ASSET_SYNC P1 回归：下载按需化（消灭 data/output 第三存在形式）。

契约来源：docs/design/ASSET_SYNC_ARCHITECTURE.md §5.1 / §6 P1。
验收：编辑后下载即新鲜；Web 管线零落盘；CLI 文件输出保留；缓存可清理。
"""
import os
import time

import pytest

import app.routers.tasks as tr
import core.pipeline as pl
import core.task_store as task_store
from core.minutes_render import render_minutes_md

# ── 渲染纯函数：定稿口径 + 对话稿附录 ──


def test_render_uses_final_summary_and_appends_dialogue():
    task = {
        "summary": "AI 初稿",
        "user_summary": "编辑版",
        "dialogue": [{"speaker_id": 0, "speaker_name": "张三", "text": "你好"}],
    }
    md = render_minutes_md(task)
    assert md.startswith("编辑版")
    assert "AI 初稿" not in md
    assert "## 附：原始对话稿" in md
    assert "【张三】你好" in md


def test_render_empty_final_and_no_dialogue_is_empty():
    assert render_minutes_md({"summary": "AI 初稿", "user_summary": ""}) == ""


# ── 下载端点：新鲜度 + 零落盘 + 忽略冻结快照 ──


def test_md_download_ignores_stale_frozen_file(tmp_path, monkeypatch):
    stale = tmp_path / "stale.md"
    stale.write_text("过期内容", encoding="utf-8")
    tid = "p1dl-0001"
    monkeypatch.setitem(tr.tasks, tid, {
        "task_id": tid, "summary": "AI 初稿", "user_summary": "新编辑版",
        "output_path": str(stale), "audio_name": "rec.wav",
    })
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    monkeypatch.setattr(tr, "OUTPUT_DIR", out_dir)

    resp = tr.download_summary(tid, format="md")
    body = resp.body.decode("utf-8")
    assert "新编辑版" in body
    assert "过期内容" not in body
    assert "filename*=utf-8''" in resp.headers["content-disposition"]
    # md 下载零落盘
    assert not list(out_dir.iterdir())


def test_md_download_empty_minutes_404(monkeypatch):
    tid = "p1dl-0002"
    monkeypatch.setitem(tr.tasks, tid, {"task_id": tid, "summary": None})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        tr.download_summary(tid, format="md")
    assert ei.value.status_code == 404


def test_docx_download_renders_from_ssot(tmp_path, monkeypatch):
    captured = {}

    def fake_md2docx(md_text, out_path):
        captured["md"] = md_text
        from pathlib import Path
        Path(out_path).write_bytes(b"PK")
        return str(out_path)

    monkeypatch.setattr("core.docx_export.markdown_to_docx", fake_md2docx)
    monkeypatch.setattr(tr, "OUTPUT_DIR", tmp_path)
    tid = "p1dl-0003"
    monkeypatch.setitem(tr.tasks, tid, {
        "task_id": tid, "summary": "AI 初稿", "user_summary": "docx 编辑版",
    })
    resp = tr.download_summary(tid, format="docx")
    assert captured["md"].startswith("docx 编辑版")
    assert "wordprocessingml" in resp.media_type


# ── stage2 emit_file：Web 零落盘 / CLI 保留 ──


@pytest.fixture
def stage2_mocks(monkeypatch):
    monkeypatch.setattr(pl, "generate_summary", lambda *a, **k: "纪要正文")
    monkeypatch.setattr(pl, "generate_title", lambda *a, **k: "标题")
    monkeypatch.setattr(pl, "generate_chapters", lambda *a, **k: [])


def test_stage2_emit_file_false_writes_nothing(tmp_path, stage2_mocks):
    result = pl.run_pipeline_stage2(
        dialogue=[], speaker_mapping=None, audio_path=None,
        config={"output_dir": str(tmp_path), "llm_model": "test"},
        emit_file=False,
    )
    assert result["output_path"] is None
    assert result["summary"] == "纪要正文"
    assert not list(tmp_path.iterdir())


def test_stage2_default_keeps_cli_file_output(tmp_path, stage2_mocks):
    result = pl.run_pipeline_stage2(
        dialogue=[], speaker_mapping=None, audio_path=None,
        config={"output_dir": str(tmp_path), "llm_model": "test"},
    )
    assert result["output_path"] is not None
    from pathlib import Path
    saved = Path(result["output_path"])
    assert saved.exists() and saved.parent == tmp_path
    assert "纪要正文" in saved.read_text(encoding="utf-8")


# ── 缓存清理：retention sweep + 任务删除联动 ──


def test_sweep_expired_docx_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(task_store, "OUTPUT_DIR", tmp_path)
    old = tmp_path / "t1_20260101_000000_纪要.docx"
    new = tmp_path / "t2_20261111_000000_纪要.docx"
    other = tmp_path / "无关文件.txt"
    for f in (old, new, other):
        f.write_bytes(b"PK")
    past = time.time() - 30 * 86400
    os.utime(old, (past, past))

    removed = task_store.sweep_expired_docx_cache(7)
    assert removed == 1
    assert not old.exists()
    assert new.exists() and other.exists()
    # retention <= 0 视为不清理
    assert task_store.sweep_expired_docx_cache(0) == 0


def test_purge_removes_docx_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(tr, "TASKS_DIR", tmp_path)
    monkeypatch.setattr(task_store, "TASKS_DIR", tmp_path)
    tid = "p1purge-0001"
    cache = tmp_path / f"{tid}_20261111_000000_纪要.docx"
    cache.write_bytes(b"PK")
    tr._purge_task_artifacts(tid, {"task_id": tid})
    assert not cache.exists()
