"""EP0-BE 增量3 测试：存量数据归属迁移（裁决④）幂等 + 对账单 + 白名单。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db.config import DataRoot
from app.db.dao import EnterpriseStore
from app.db.database import migrate
from app.db.legacy_import import LegacyImporter
from app.db.security import hash_password

LEGACY_TASK = {
    "task_id": "00bbce17-972a-4ab0-a265-f2f943ec7f96",
    "status": "done",
    "title": "转让规则评审会",
    "meeting_date": "2026-10-12",
    "audio_path": "/Users/x/data/recordings/a.wav",  # 白名单外——绝不上行
    "audio_name": "a.wav",
    "roster": ["乔晓军", "王永亮"],
    "speaker_mapping": {"0": "乔晓军"},
    "dialogue": [
        {"speaker_id": 0, "text": "下面这的转让规则啊，需要配置内容。", "sentences": [{"text": "片段"}]},
        {"speaker_id": 1, "text": "同意，按方案A执行。"},
    ],
    "summary": "会议确定按方案A执行转让规则配置。",
    "user_notes": "笔记：核对新PMS术语",
    "decisions": [{"id": "d1", "text": "选方案A", "status": "confirmed", "superseded_by": None}],
}
JOB_ONLY = {"task_id": "job-only-1", "status": "error", "error": "chunk_failed", "progress": {"done": 1, "total": 9}}


@pytest.fixture()
def env(tmp_path):
    src = tmp_path / "legacy_data" / "tasks"
    src.mkdir(parents=True)
    (src / f"{LEGACY_TASK['task_id']}.json").write_text(json.dumps(LEGACY_TASK, ensure_ascii=False), encoding="utf-8")
    (src / "job-only-1.json").write_text(json.dumps(JOB_ONLY), encoding="utf-8")
    (src / f"{LEGACY_TASK['task_id']}.insights.json").write_text("{}")
    (src / f"{LEGACY_TASK['task_id']}.formal.json").write_text("{}")
    base = tmp_path / "legacy_data"
    (base / "hotwords.txt").write_text("新PMS\n苍穹\n一S\n", encoding="utf-8")
    (base / "speakers.json").write_text(
        json.dumps([{"speaker_id": "sp1", "name": "乔晓军", "embedding": [0.1, 0.2]}], ensure_ascii=False), encoding="utf-8"
    )
    (base / "decision_statuses.json").write_text(json.dumps([{"id": "confirmed", "label": "已确认", "order": 1}]), encoding="utf-8")

    root = tmp_path / "ENTERPRISE_DATA"
    store = EnterpriseStore(DataRoot(root=root))
    migrate(store.conn)
    now = "2026-10-29T00:00:00+00:00"
    with store.conn:
        store.conn.execute(
            "INSERT INTO users(user_id, login_account, phone, display_name, password_hash, role, status, created_at, updated_at)"
            " VALUES ('usr_owner','13373013103','13373013103','超级个体',?,'admin','active',?,?)",
            (hash_password("Owner-Pw-0001"), now, now),
        )
    return store, base


def test_migrate_legacy_first_run(env):
    store, base = env
    report = LegacyImporter(store, base, "13373013103").run()
    assert report["scanned"] == 2  # insights/formal sidecar 不计数
    assert report["migrated_tasks"] == 1
    assert report["skipped"].get("no_text_content") == 1
    assert sorted(report["assets"]) == ["decision_statuses", "hotwords", "speaker_aliases"]
    assert report["spot_check"] == {"checked": 1, "ok": 1}
    assert Path(report["report_path"]).exists()

    rows = store.conn.execute("SELECT task_id FROM ctx_tasks WHERE owner_user_id='usr_owner'").fetchall()
    assert len(rows) == 1
    task = store.get_task(actor_user_id="usr_owner", task_id=rows[0]["task_id"])
    assert task["meta"]["legacy_id"] == LEGACY_TASK["task_id"]
    assert task["visibility"] == "personal"
    assert "乔晓军: 下面这的转让规则" in task["formal"]
    assert task["summary"] == LEGACY_TASK["summary"]
    assert task["meta"]["participants_text"] == "乔晓军、王永亮"
    # 音频引用绝不进白名单
    blob = store.conn.execute("SELECT blob_path FROM ctx_revisions WHERE task_id=?", (rows[0]["task_id"],)).fetchone()
    import gzip

    raw = gzip.decompress(Path(blob["blob_path"]).read_bytes()).decode("utf-8")
    assert "audio_path" not in raw and "a.wav" not in raw
    aliases = store.get_asset(actor_user_id="usr_owner", kind="speaker_aliases")
    assert aliases["payload"] == {"sp1": "乔晓军"}  # embedding 字段不读入
    hw = store.get_asset(actor_user_id="usr_owner", kind="hotwords")
    assert hw["payload"] == ["新PMS", "苍穹", "一S"]


def test_migrate_legacy_idempotent_rerun(env):
    store, base = env
    LegacyImporter(store, base, "13373013103").run()
    report2 = LegacyImporter(store, base, "13373013103").run()
    assert report2["migrated_tasks"] == 0
    assert report2["skipped"].get("already_migrated") == 1
    n = store.conn.execute("SELECT COUNT(*) c FROM ctx_revisions").fetchone()["c"]
    assert n == 1  # 重跑不重复入库
    ledger = store.conn.execute("SELECT COUNT(*) c FROM legacy_import_ledger").fetchone()["c"]
    assert ledger == 1


def test_migrate_legacy_changed_source_updates_rev(env):
    store, base = env
    LegacyImporter(store, base, "13373013103").run()
    f = base / "tasks" / f"{LEGACY_TASK['task_id']}.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["user_notes"] = "笔记更新：补充术语核对结论"
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    report = LegacyImporter(store, base, "13373013103").run()
    assert report["migrated_tasks"] == 1  # 源变化 → 新 mutation 重推
    tid = store.conn.execute("SELECT task_id FROM ctx_tasks").fetchone()["task_id"]
    assert store.conn.execute("SELECT current_rev FROM ctx_tasks WHERE task_id=?", (tid,)).fetchone()["current_rev"] == 2


def test_migrate_legacy_missing_account_aborts(env):
    store, base = env
    with pytest.raises(SystemExit):
        LegacyImporter(store, base, "19900000000")


def test_migrate_legacy_readonly_source(env):
    store, base = env
    before = sorted(p.name for p in (base / "tasks").iterdir())
    LegacyImporter(store, base, "13373013103").run()
    after = sorted(p.name for p in (base / "tasks").iterdir())
    assert before == after  # 复制-校验-保留源：源目录零改动
