"""ASSET_SYNC P3 回归：回流三方 hash 冲突判定（决策表四象限 + 防回环）。

契约来源：docs/design/ASSET_SYNC_ARCHITECTURE.md §4.2 / §6 P3。
S=SSOT 定稿 hash / P=投影清单 hash / F=文件实际 hash。
"""
import pytest

import core.cli_engine.context_paths as cp
import core.cli_engine.projection as pj
import core.task_store as task_store
from core.cli_engine.context_export import import_from_workspace

TID = "5cdf8150-746a-4a8f-b370-e0f1f896baab"


@pytest.fixture
def preview_root(tmp_path, monkeypatch):
    root = tmp_path / "_preview"
    root.mkdir()
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
        "user_notes": "用户随记原文",
        "dialogue": [],
        "decisions": [],
    }
    monkeypatch.setattr(task_store, "tasks", {TID: t})
    return t


def _ws(preview_root):
    return preview_root / "_standalone" / f"2026-11-11_产品周会__{TID[:8]}"


def _edit_body(path, new_body: str):
    """模拟外部 IDE 编辑：保留 frontmatter，替换正文（不更新 content_hash）。"""
    content = path.read_text(encoding="utf-8")
    end = content.find("---", 3)
    path.write_text(content[:end + 3] + "\n\n" + new_body, encoding="utf-8")


# ── 象限 1：F==P，S==P → 无变化 ──


def test_no_changes_after_projection(preview_root, task):
    pj.project_task(TID)
    r = import_from_workspace(TID)
    assert r["has_changes"] is False
    assert r["summary"] is None and r["notes"] is None


# ── 象限 2：F==P，S!=P → 仅 SSOT 前进，防回环（不是外部编辑） ──


def test_ssot_advanced_without_projection_is_not_external_change(preview_root, task):
    pj.project_task(TID)
    task["user_summary"] = "应用内编辑但尚未投影"  # 直接改 SSOT，不走 mark_modified
    r = import_from_workspace(TID)
    assert r["has_changes"] is False  # F==P → 判无外部改动
    # 投影补齐后依然无变更
    pj.project_task(TID)
    assert import_from_workspace(TID)["has_changes"] is False


# ── 象限 3：F!=P，S==P → 纯外部改动提案（conflict=False） ──


def test_pure_external_change_proposes_without_conflict(preview_root, task):
    pj.project_task(TID)
    _edit_body(_ws(preview_root) / "context" / "summary.md", "外部 IDE 改写的内容")
    r = import_from_workspace(TID)
    assert r["has_changes"] is True
    assert r["summary"]["proposed"] == "外部 IDE 改写的内容"
    assert r["summary"]["baseline"] == "AI 初稿纪要"
    assert r["summary"]["conflict"] is False


# ── 象限 4：F!=P，S!=P → 双侧冲突（conflict=True，用户裁决） ──


def test_both_sides_changed_flags_conflict(preview_root, task):
    pj.project_task(TID)
    task["user_summary"] = "应用内编辑版"  # SSOT 前进（未投影）
    _edit_body(_ws(preview_root) / "context" / "summary.md", "外部 IDE 改写的内容")
    r = import_from_workspace(TID)
    assert r["has_changes"] is True
    assert r["summary"]["conflict"] is True
    # baseline 取 SSOT 当前定稿，外部改动只是提案素材
    assert r["summary"]["baseline"] == "应用内编辑版"
    assert r["summary"]["proposed"] == "外部 IDE 改写的内容"


# ── 锚点校验与降级 ──


def test_task_id_mismatch_rejected(preview_root, task):
    pj.project_task(TID)
    f = _ws(preview_root) / "context" / "summary.md"
    content = f.read_text(encoding="utf-8")
    f.write_text(content.replace(f"task_id: \"{TID}\"", "task_id: \"别的会议\""), encoding="utf-8")
    r = import_from_workspace(TID)
    assert r["error"] == "task_id_mismatch"


def test_legacy_workspace_without_manifest_falls_back(preview_root, task):
    pj.project_task(TID)
    pj.manifest_path(_ws(preview_root)).unlink()  # 旧工作区无清单
    _edit_body(_ws(preview_root) / "context" / "summary.md", "外部改动")
    r = import_from_workspace(TID)
    assert r["has_changes"] is True
    assert r["summary"]["conflict"] is False  # 无锚点不判冲突（降级旧行为）


# ── notes 域：头部声明剥离 + hash 同口径防回环 ──


def test_notes_untouched_no_changes(preview_root, task):
    pj.project_task(TID)
    r = import_from_workspace(TID)
    assert r["notes"] is None  # raw_body hash 与投影同口径，不误报


def test_notes_external_append_proposes_stripped_body(preview_root, task):
    pj.project_task(TID)
    f = _ws(preview_root) / "context" / "notes.md"
    content = f.read_text(encoding="utf-8")
    end = content.find("---", 3)
    raw_body = content[end + 3:].lstrip("\n")
    _edit_body(f, raw_body + "\n外部补充一条")
    r = import_from_workspace(TID)
    assert r["has_changes"] is True
    assert r["notes"]["proposed"] == "用户随记原文\n外部补充一条"
    assert r["notes"]["baseline"] == "用户随记原文"
    assert r["notes"]["conflict"] is False
