"""工作区目录命名 / 上下文范围导出 / 多 IDE 规则文件。"""
import json

import pytest

import core.cli_engine.context_export as ce
from app.store import tasks as task_store


@pytest.fixture
def preview_root(tmp_path, monkeypatch):
    root = tmp_path / "_preview"
    root.mkdir()
    monkeypatch.setattr(ce, "PREVIEW_ROOT", root)
    return root


def _task(task_id: str, title: str = "产品周会", *, project_id=None, date="2026-10-15T10:00:00"):
    return {
        "task_id": task_id,
        "title": title,
        "meeting_date": date,
        "project_id": project_id,
        "todos": [],
        "dialogue": [],
    }


def test_meeting_dir_name_readable_with_stable_suffix():
    name = ce._meeting_dir_name(
        {"title": "产品 周会/评审", "meeting_date": "2026-10-15T10:00:00"},
        "5cdf8150-746a-4a8f-b370-e0f1f896baab",
    )
    assert name == "2026-10-15_产品_周会_评审__5cdf8150"
    assert name.endswith("__5cdf8150")


def test_meeting_dir_name_strips_audio_extension_and_fullwidth_colon():
    # 录音文件名兜底标题：剥扩展名，目录名不出现 "rec.wav"
    name = ce._meeting_dir_name(
        {"audio_name": "rec.wav", "meeting_date": "2026-10-12T10:00:00"},
        "toverrid1-abcd",
    )
    assert name == "2026-10-12_rec__toverrid"
    # 全角冒号归一为下划线，规避同步工具兼容问题
    name2 = ce._meeting_dir_name(
        {"title": "EAS升级项目：会计试验库", "meeting_date": "2026-10-19T10:00:00"},
        "deadbeef-1111-4000-8000-000000000001",
    )
    assert "：" not in name2
    assert name2.startswith("2026-10-19_EAS升级项目_")


def test_preview_dir_migrates_legacy_uuid_dir(preview_root):
    task_id = "5cdf8150-746a-4a8f-b370-e0f1f896baab"
    legacy = preview_root / "_standalone" / task_id
    legacy.mkdir(parents=True)

    ws = ce.preview_workspace_dir(task_id, None, _task(task_id))

    assert ws.name == "2026-10-15_产品周会__5cdf8150"
    assert ws.is_dir()
    assert not legacy.exists()
    assert (ws / "context").is_dir()


def test_export_preview_writes_one_ide_rule_and_hidden_index(preview_root):
    task_id = "5cdf8150-746a-4a8f-b370-e0f1f896baab"
    task = _task(task_id)

    result = ce.export_preview_context(task_id=task_id, task=task, ide_id="cursor")

    ws = preview_root / "_standalone" / "2026-10-15_产品周会__5cdf8150"
    assert result["workspace"] == str(ws.resolve())
    for rel in ("AGENTS.md", ".cursor/rules/meeting-context.mdc", "related.md"):
        assert (ws / rel).is_file(), rel
    for rel in (".github/copilot-instructions.md", "CLAUDE.md", "START_HERE.md",
                ".trae/rules/meeting-context.md", ".windsurf/rules/meeting-context.md"):
        assert not (ws / rel).exists(), rel

    index = json.loads(
        (preview_root / "_standalone" / ".oms" / "meetings.json").read_text(encoding="utf-8"))
    assert index["project_name"] == "独立会议"
    entry = next(m for m in index["meetings"] if m["task_id"] == task_id)
    assert entry["workspace_path"] == "2026-10-15_产品周会__5cdf8150/"
    assert not (preview_root / "_standalone" / "_meetings.json").exists()


def test_attach_ide_rule_switches_single_native_file(preview_root):
    ws = preview_root / "x"
    ws.mkdir()
    ce.attach_ide_rule(ws, "cursor")
    assert (ws / ".cursor/rules/meeting-context.mdc").is_file()

    ce.attach_ide_rule(ws, "trae-cn")
    assert (ws / ".trae/rules/meeting-context.md").is_file()
    assert not (ws / ".cursor/rules/meeting-context.mdc").exists()

    ce.attach_ide_rule(ws, "zed")
    assert not (ws / ".trae/rules/meeting-context.md").exists()


def test_attach_ide_rule_removes_empty_parent_dirs(preview_root):
    # 旧版残留的空 .cursor/.windsurf 目录要收掉；用户自建文件不受波及
    ws = preview_root / "x"
    (ws / ".cursor").mkdir(parents=True)
    (ws / ".windsurf" / "rules").mkdir(parents=True)
    (ws / ".windsurf" / "rules" / "keep.md").write_text("user", encoding="utf-8")
    ce.attach_ide_rule(ws, "zed")
    assert not (ws / ".cursor").exists()
    assert (ws / ".windsurf" / "rules" / "keep.md").exists()


def test_rule_pointer_matches_scope_files():
    # 指引必须指向真实存在的文件：会议级看上级，项目级看本目录，全局看根
    assert "上级 `_DECISIONS.md`" in ce._rule_pointer("", level="meeting")
    assert "本目录 `_DECISIONS.md`" in ce._rule_pointer("", level="project")
    assert "根 `_DECISIONS.md`" in ce._rule_pointer("", level="global")


def test_speaker_count_dedupes_names(preview_root):
    task_id = "5cdf8150-746a-4a8f-b370-e0f1f896baab"
    task = _task(task_id)
    task["dialogue"] = [
        {"speaker_name": "张三", "text": "a"},
        {"speaker_name": "张三", "text": "b"},
        {"speaker_name": "李四", "text": "c"},
    ]
    ce.export_preview_context(task_id=task_id, task=task)
    index = json.loads(
        (preview_root / "_standalone" / ".oms" / "meetings.json").read_text(encoding="utf-8"))
    entry = next(m for m in index["meetings"] if m["task_id"] == task_id)
    assert entry["speaker_count"] == 2


def test_stale_orphan_archive_merged_when_real_workspace_exists(preview_root, monkeypatch):
    """撞车归档收口（评估 2026-10-26 P0-4）：同任务短 ID 一份在归档、一份是正式工作区
    时，归档是脏副本——缺失子项并入真实工作区后清掉，不丢数据、不覆盖已有文件。"""
    task_id = "1e578590-1111-4000-8000-000000000001"
    task = _task(task_id, "财务梳理会", date="2026-10-13T10:00:00")
    monkeypatch.setattr("app.store.tasks", {task_id: task})
    real = preview_root / "_standalone" / "2026-10-13_财务梳理会__1e578590"
    (real / "context").mkdir(parents=True)
    (real / "context" / "summary.md").write_text("---\ntask_id: x\n---\n\n正文", encoding="utf-8")
    stale = preview_root / "_standalone" / "未识别会议__1e578590"
    (stale / "output").mkdir(parents=True)
    (stale / "output" / "draft.md").write_text("遗留草稿", encoding="utf-8")

    ce._migrate_meeting_dirs(preview_root / "_standalone", None)

    assert not stale.exists()
    assert (real / "output" / "draft.md").exists()      # 缺失子项并入
    assert (real / "context" / "summary.md").read_text(encoding="utf-8").endswith("正文")


def test_true_orphan_archive_kept(preview_root, monkeypatch):
    # 真无主（key 不命中任务库）的归档保留，等人工辨认
    monkeypatch.setattr("app.store.tasks", {})
    monkeypatch.setattr(ce, "_ensure_tasks_loaded", lambda: None)
    orphan = preview_root / "_standalone" / "未识别会议__0123abcd"
    (orphan / "context").mkdir(parents=True)
    ce._migrate_meeting_dirs(preview_root / "_standalone", None)
    assert orphan.is_dir()


def test_project_context_writes_cross_meeting_root(preview_root, monkeypatch):
    project_id = "7f3a2c1b-0000-4000-8000-000000000001"
    monkeypatch.setattr(ce, "_project_display_name", lambda pid: "产品研发")
    t1 = _task("a91b3e77-1111-4000-8000-000000000001", "需求评审",
               project_id=project_id, date="2026-10-08T09:00:00")
    t2 = _task("5cdf8150-2222-4000-8000-000000000002", "产品周会",
               project_id=project_id, date="2026-10-15T10:00:00")
    monkeypatch.setitem(task_store, t1["task_id"], t1)
    monkeypatch.setitem(task_store, t2["task_id"], t2)

    result = ce.export_project_context(project_id, ide_id="claude-code")

    proj = preview_root / "产品研发__7f3a2c1b"
    assert result["workspace"] == str(proj.resolve())
    assert result["meeting_count"] == 2
    for rel in ("AGENTS.md", "CLAUDE.md", "_INDEX.md", "_DECISIONS.md"):
        assert (proj / rel).is_file(), rel
    assert not (proj / "START_HERE.md").exists()
    assert not (proj / ".cursor").exists()
    assert (proj / "2026-10-15_产品周会__5cdf8150").is_dir()
    assert (proj / "2026-10-08_需求评审__a91b3e77").is_dir()

    index = json.loads((proj / ".oms" / "meetings.json").read_text(encoding="utf-8"))
    assert index["project_id"] == project_id
    assert index["project_name"] == "产品研发"
    assert len(index["meetings"]) == 2

    global_index = json.loads(
        (preview_root / ".oms" / "index.json").read_text(encoding="utf-8"))
    assert global_index["projects"][0]["project_id"] == project_id
    assert global_index["projects"][0]["meeting_count"] == 2


def test_global_context_indexes_and_migrates_legacy(preview_root, monkeypatch):
    monkeypatch.setattr(ce, "_project_display_name", lambda pid: "产品研发")
    project_id = "7f3a2c1b-0000-4000-8000-000000000001"
    t1 = _task("5cdf8150-2222-4000-8000-000000000002", "产品周会", project_id=project_id)
    t2 = _task("deadbeef-1111-4000-8000-000000000003", "客户访谈", date="2026-10-12T10:00:00")
    # 整库替换而非 setitem：独立会议范围按"无 project_id"过滤，前序测试
    # 留在真实任务库里的条目会污染计数（全量回归时已复现）
    monkeypatch.setattr("app.store.tasks", {t1["task_id"]: t1, t2["task_id"]: t2})
    ce.export_preview_context(task_id=t1["task_id"], task=t1, project_id=project_id)

    # 制造旧版痕迹：独立会议 UUID 目录 + 旧 _meetings.json + 孤儿目录（不在任务库）
    legacy_dir = preview_root / "_standalone" / "deadbeef-1111-4000-8000-000000000003"
    legacy_dir.mkdir(parents=True)
    orphan_dir = preview_root / "_standalone" / "0123abcd-9999-4000-8000-000000000099"
    orphan_dir.mkdir(parents=True)
    (preview_root / "_standalone" / "_meetings.json").write_text(json.dumps({
        "project_id": "_standalone", "project_name": "独立会议",
        "meetings": [{"task_id": t2["task_id"], "title": "客户访谈",
                      "meeting_date": "2026-10-12T10:00:00",
                      "workspace_path": f"{t2['task_id']}/"}],
    }, ensure_ascii=False), encoding="utf-8")

    result = ce.export_global_context(ide_id="vscode")

    assert result["project_count"] == 1
    for rel in ("AGENTS.md", "_INDEX.md", ".github/copilot-instructions.md"):
        assert (preview_root / rel).is_file(), rel
    for rel in ("START_HERE.md", "_index.json", ".cursor", ".trae", "CLAUDE.md"):
        assert not (preview_root / rel).exists(), rel

    # 库内会议 → 可读名；孤儿 → 归档名；旧索引文件清除
    migrated = preview_root / "_standalone" / "2026-10-12_客户访谈__deadbeef"
    assert migrated.is_dir()
    assert (preview_root / "_standalone" / "未识别会议__0123abcd").is_dir()
    assert not legacy_dir.exists()
    assert not orphan_dir.exists()
    assert not (preview_root / "_standalone" / "_meetings.json").exists()

    si = json.loads(
        (preview_root / "_standalone" / ".oms" / "meetings.json").read_text(encoding="utf-8"))
    assert len(si["meetings"]) == 1
    assert si["meetings"][0]["workspace_path"] == "2026-10-12_客户访谈__deadbeef/"

    global_index_body = (preview_root / "_INDEX.md").read_text(encoding="utf-8")
    assert "产品研发" in global_index_body
    assert "## 独立会议" in global_index_body
    assert "客户访谈" in global_index_body
    assert "未识别会议" not in global_index_body  # 孤儿不进索引，只在磁盘归档


def test_global_export_never_poisons_indexless_project_dir(preview_root, monkeypatch):
    """回归：项目目录缺索引/索引被污染时，scope=all 曾把它误标为 standalone，
    把独立会议灌进项目索引并连锁清空独立区（电子档案系统事故）。"""
    monkeypatch.setattr(ce, "_project_display_name", lambda pid: "产品研发")
    project_id = "7f3a2c1b-0000-4000-8000-000000000001"
    t1 = _task("5cdf8150-2222-4000-8000-000000000002", "产品周会", project_id=project_id)
    t2 = _task("deadbeef-1111-4000-8000-000000000003", "客户访谈")
    monkeypatch.setattr("app.store.tasks", {t1["task_id"]: t1, t2["task_id"]: t2})
    ce.export_preview_context(task_id=t1["task_id"], task=t1, project_id=project_id)
    ce.export_preview_context(task_id=t2["task_id"], task=t2, project_id=None)

    # 事故形态：项目目录内索引被污染成 standalone（缺索引后误标所致）
    proj_dir = preview_root / "产品研发__7f3a2c1b"
    (proj_dir / ".oms" / "meetings.json").write_text(json.dumps({
        "project_id": "_standalone", "project_name": "独立会议",
        "meetings": [{"task_id": t2["task_id"], "title": "客户访谈",
                      "meeting_date": "2026-10-12", "workspace_path": ""}],
    }, ensure_ascii=False), encoding="utf-8")

    ce.export_global_context(ide_id="vscode")

    # 连锁反应被切断：独立区索引不被清空
    si = json.loads(
        (preview_root / "_standalone" / ".oms" / "meetings.json").read_text(encoding="utf-8"))
    assert [m["task_id"] for m in si["meetings"]] == [t2["task_id"]]

    # 被污染目录不进全局项目列表（project_id 非法者跳过）
    gi = json.loads(
        (preview_root / ".oms" / "index.json").read_text(encoding="utf-8"))
    assert all(p["project_id"] != "_standalone" for p in gi["projects"])


def test_global_export_writes_standalone_and_root_decisions(preview_root, monkeypatch):
    """评估 2026-10-26 P0-1/P0-2/P0-5 回归：standalone 索引/台账不能空转，
    根级 _DECISIONS.md 必须真实存在，机器索引必须含会议级条目。"""
    monkeypatch.setattr(ce, "_project_display_name", lambda pid: "产品研发")
    project_id = "7f3a2c1b-0000-4000-8000-000000000001"
    t1 = _task("5cdf8150-2222-4000-8000-000000000002", "产品周会", project_id=project_id)
    t2 = _task("deadbeef-1111-4000-8000-000000000003", "客户访谈", date="2026-10-12T10:00:00")
    monkeypatch.setattr("app.store.tasks", {t1["task_id"]: t1, t2["task_id"]: t2})
    ce.export_preview_context(task_id=t1["task_id"], task=t1, project_id=project_id)

    ce.export_global_context()

    # 独立区索引有内容、有归档说明；台账存在
    si_body = (preview_root / "_standalone" / "_INDEX.md").read_text(encoding="utf-8")
    assert "meeting_count: 1" in si_body and "客户访谈" in si_body
    assert "未识别会议" in si_body  # 归档目录说明
    si_decisions = (preview_root / "_standalone" / "_DECISIONS.md").read_text(encoding="utf-8")
    assert "独立会议" in si_decisions

    # 根级决策台账（规则文案「决策与待办见 _DECISIONS.md」的根级落点）
    root_decisions = (preview_root / "_DECISIONS.md").read_text(encoding="utf-8")
    assert "跨项目决策台账" in root_decisions

    # 机器索引含会议级条目，计数与条目一致
    gi = json.loads(
        (preview_root / ".oms" / "index.json").read_text(encoding="utf-8"))
    assert any(m["task_id"] == t2["task_id"] for m in gi["standalone_meetings"])
    assert gi["projects"][0]["meetings"]
    assert gi["standalone_count"] == len(gi["standalone_meetings"])


def test_ds_store_swept_on_global_export(preview_root, monkeypatch):
    monkeypatch.setattr("app.store.tasks", {})
    monkeypatch.setattr(ce, "_ensure_tasks_loaded", lambda: None)
    junk = preview_root / "_standalone" / "somemeeting" / ".DS_Store"
    junk.parent.mkdir(parents=True)
    junk.write_bytes(b"junk")
    ce.export_global_context()
    assert not junk.exists()
