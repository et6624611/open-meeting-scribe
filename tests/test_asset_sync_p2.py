"""ASSET_SYNC P2 回归：资产工作区单向投影（幂等/增量/生命周期/容错不降级）。

契约来源：docs/design/ASSET_SYNC_ARCHITECTURE.md §3.4 / §4 / §6 P2。
"""

import pytest

import app.routers.tasks as tr
import core.cli_engine.context_paths as cp
import core.cli_engine.projection as pj
import core.task_store as task_store
from core import notes_service

TID = "5cdf8150-746a-4a8f-b370-e0f1f896baab"


@pytest.fixture
def preview_root(tmp_path, monkeypatch):
    root = tmp_path / "_preview"
    root.mkdir()
    # projection 模块级 import 了 PREVIEW_ROOT，两处都要 patch
    monkeypatch.setattr(cp, "PREVIEW_ROOT", root)
    monkeypatch.setattr(pj, "PREVIEW_ROOT", root)
    return root


@pytest.fixture
def task(monkeypatch):
    t = {
        "task_id": TID,
        "title": "产品周会",
        "meeting_date": "2026-11-11T10:00:00",
        "summary": "AI 初稿纪要",
        "dialogue": [{"speaker_id": 0, "speaker_name": "张三", "text": "开始吧"}],
        "decisions": [],
    }
    monkeypatch.setattr(task_store, "tasks", {TID: t})
    return t


def _ws(preview_root):
    return preview_root / "_standalone" / f"2026-11-11_产品周会__{TID[:8]}"


# ── 幂等与增量 ──


def test_project_idempotent_second_call_zero_writes(preview_root, task, monkeypatch):
    r1 = pj.project_task(TID)
    assert r1["ok"] is True
    summary_md = _ws(preview_root) / "context" / "summary.md"
    assert summary_md.is_file()
    before = (summary_md.read_bytes(), summary_md.stat().st_mtime_ns)

    calls = []
    import core.fs_atomic as fa
    orig = fa.atomic_write_text

    def spy(path, content, *a, **k):
        calls.append(str(path))
        return orig(path, content, *a, **k)

    monkeypatch.setattr(fa, "atomic_write_text", spy)
    r2 = pj.project_task(TID)
    assert r2["ok"] is True
    # 正文 hash 未变 → context/ 零重写（manifest 经 atomic_write_json 重建属正常）
    assert not any("/context/" in c for c in calls)
    assert (summary_md.read_bytes(), summary_md.stat().st_mtime_ns) == before


def test_project_incremental_only_changed_file(preview_root, task):
    pj.project_task(TID)
    ws = _ws(preview_root)
    transcript = ws / "context" / "transcript.md"
    t_before = transcript.stat().st_mtime_ns

    task["user_summary"] = "用户编辑后的纪要"
    pj.project_task(TID)

    body = (ws / "context" / "summary.md").read_text(encoding="utf-8")
    assert "用户编辑后的纪要" in body
    assert transcript.stat().st_mtime_ns == t_before  # 未变文件不重写


def test_manifest_hash_and_frontmatter_anchors(preview_root, task):
    task["content_rev"] = 7
    pj.project_task(TID)
    ws = _ws(preview_root)
    manifest = pj.read_manifest(ws)
    assert manifest["task_id"] == TID
    assert manifest["content_rev"] == 7
    entry = manifest["files"]["context/summary.md"]
    content = (ws / "context" / "summary.md").read_text(encoding="utf-8")
    assert f'content_hash: "{entry["hash"]}"' in content
    assert "content_rev: 7" in content
    assert 'projection: "readonly"' in content
    # hash 与正文同口径
    assert entry["hash"] == pj.body_hash(pj.split_frontmatter_body(content))


# ── 脏标记收口：rev 递增 + 自动投影 ──


def test_mark_modified_increments_rev_and_projects(preview_root, task):
    notes_service.mark_modified(TID)
    assert task["content_rev"] == 1
    assert task["last_modified_at"]
    assert (_ws(preview_root) / "context" / "summary.md").is_file()
    notes_service.mark_modified(TID)
    assert task["content_rev"] == 2


def test_projection_flag_disabled_skips(preview_root, task, monkeypatch):
    monkeypatch.setattr("core.settings_store.get_feature_flags",
                        lambda: {"asset_projection": False})
    r = pj.project_task(TID)
    assert r == {"skipped": "flag_disabled"}
    assert not _ws(preview_root).exists()


# ── 生命周期：改名跟随 / 归档打标 / 删除清理 ──


def test_rename_follows_title(preview_root, task):
    pj.project_task(TID)
    old = _ws(preview_root)
    task["title"] = "改名后的会"
    pj.project_task(TID)
    new = preview_root / "_standalone" / f"2026-11-11_改名后的会__{TID[:8]}"
    assert new.is_dir() and (new / "context" / "summary.md").is_file()
    assert not old.exists()


def test_set_archived_marks_manifest_without_moving(preview_root, task):
    pj.project_task(TID)
    pj.set_archived(TID, True)
    assert pj.read_manifest(_ws(preview_root))["archived"] is True
    assert _ws(preview_root).is_dir()  # 不移动文件
    pj.set_archived(TID, False)
    assert pj.read_manifest(_ws(preview_root))["archived"] is False


def test_purge_meeting_workspace(preview_root, task):
    pj.project_task(TID)
    assert pj.purge_meeting_workspace(task) is True
    assert not _ws(preview_root).exists()
    assert pj.purge_meeting_workspace(task) is False  # 幂等


def test_delete_endpoint_purges_workspace(preview_root, task, monkeypatch, tmp_path):
    pj.project_task(TID)
    monkeypatch.setattr(tr, "TASKS_DIR", tmp_path)
    monkeypatch.setattr(tr, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(task_store, "TASKS_DIR", tmp_path)
    tr._purge_task_artifacts(TID, task)
    assert not _ws(preview_root).exists()


# ── 容错不降级：部分失败不标已同步 ──


def test_partial_failure_records_errors_not_synced(preview_root, task, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("渲染中断")

    monkeypatch.setattr(pj, "_write_context_md_files", boom)
    r = pj.project_task(TID)
    assert r["ok"] is False
    assert "render" in r["errors"]
    manifest = pj.read_manifest(_ws(preview_root))
    assert manifest["errors"]["render"].startswith("渲染中断")


def test_projection_failure_does_not_block_mark_modified(preview_root, task, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("投影炸了")

    monkeypatch.setattr(pj, "project_task", boom)
    notes_service.mark_modified(TID)  # 不得抛异常
    assert task["content_rev"] == 1
