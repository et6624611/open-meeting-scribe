"""tests/test_memory_consolidate.py — M2 巩固与生命周期（tasks-m2.md §3）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.server import app
from core.agent_memory import consolidate, lifecycle, store
from core.task_store import tasks

TASK_ID = "m2-task-0001"
SUMMARY = "项目A 负责人由李四负责。汇报统一三段式。"


@pytest.fixture()
def memory_dir(tmp_path, monkeypatch):
    path = tmp_path / "memory"
    monkeypatch.setattr(store, "MEMORY_DIR", path)
    yield path


@pytest.fixture()
def task():
    tasks[TASK_ID] = {
        "task_id": TASK_ID,
        "status": "completed",
        "created_at": "2026-11-20T10:00:00+08:00",
        "project_id": None,
        "summary": SUMMARY,
        "user_notes": "偏好：先结论后论据",
        "decisions": [{"title": "上线时间", "decision": "定在 12 月"}],
    }
    yield tasks[TASK_ID]
    tasks.pop(TASK_ID, None)


@pytest.fixture()
def client(memory_dir):
    with TestClient(app) as c:
        yield c


def _stub_llm(payload: list[dict]):
    def _call(messages, **kwargs):
        assert messages and messages[0]["role"] == "system"
        return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    return _call


def _seed(**overrides) -> dict:
    base = {
        "namespace": "global",
        "kind": "fact",
        "subject": "项目A",
        "relation": "负责人",
        "object": "张三",
        "text": "项目A 负责人为张三",
        "source": {"task_id": "seed", "quote": "由张三负责", "anchor": {}},
        "recorded_at": "2025-01-01T00:00:00+08:00",
        "importance": 0.5,
    }
    base.update(overrides)
    return store.upsert(base)["item"]


def _set_flag(monkeypatch, enabled: bool):
    import core.settings_store as settings_store
    monkeypatch.setattr(settings_store, "get_feature_flags",
                        lambda: {"agent_memory": True,
                                 "agent_memory_consolidate": enabled})


def test_disabled_by_default(memory_dir, task, monkeypatch):
    _set_flag(monkeypatch, False)
    outcome = consolidate.consolidate_task(TASK_ID, llm=_stub_llm([]))
    assert outcome["reason"] == "disabled"
    assert outcome["created"] == 0
    assert store.list_items() == []


def test_force_creates_proposed(memory_dir, task):
    payload = [
        {"kind": "fact", "text": "项目A 负责人为李四",
         "quote": "项目A 负责人由李四负责", "importance": 0.8},
        {"kind": "preference", "text": "汇报统一三段式",
         "quote": "汇报统一三段式", "importance": 0.9},
    ]
    outcome = consolidate.consolidate_task(TASK_ID, force=True, llm=_stub_llm(payload))
    assert outcome["created"] == 2
    assert store.stats()["proposed"] == 2
    assert all(it["source"]["task_id"] == TASK_ID for it in store.list_items())


def test_invalid_quote_and_long_text_are_dropped(memory_dir, task):
    payload = [
        {"kind": "fact", "text": "有效条目", "quote": "汇报统一三段式"},
        {"kind": "fact", "text": "引用不存在", "quote": "材料里没有这句话"},
        {"kind": "fact", "text": "长" * 201, "quote": "项目A 负责人由李四负责"},
    ]
    outcome = consolidate.consolidate_task(TASK_ID, force=True, llm=_stub_llm(payload))
    assert outcome["created"] == 1
    assert outcome["skipped"] == 2
    assert [it["text"] for it in store.list_items()] == ["有效条目"]


def test_idempotent(memory_dir, task):
    payload = [{"kind": "fact", "text": "项目A 负责人为李四",
                "quote": "项目A 负责人由李四负责"}]
    first = consolidate.consolidate_task(TASK_ID, force=True, llm=_stub_llm(payload))
    second = consolidate.consolidate_task(TASK_ID, force=True, llm=_stub_llm(payload))
    assert first["created"] == 1
    assert second["reason"] == "already_consolidated"
    assert len(store.list_items()) == 1


def test_project_namespace(memory_dir, task):
    task["project_id"] = "proj-a"
    payload = [{"kind": "fact", "text": "项目A 归属一线",
                "quote": "项目A 负责人由李四负责"}]
    consolidate.consolidate_task(TASK_ID, force=True, llm=_stub_llm(payload))
    assert store.list_items()[0]["namespace"] == "space:proj-a"


def test_archive_stale(memory_dir):
    old_low = _seed(subject="旧低", object="甲", text="旧低重要度",
                    importance=0.1, recorded_at="2025-01-01T00:00:00+08:00")
    old_high = _seed(subject="旧高", object="乙", text="旧高重要度",
                     importance=0.5, recorded_at="2025-01-01T00:00:00+08:00")

    archived = lifecycle.archive_stale(now="2026-11-27")
    assert archived == 1
    assert store.get(old_low["id"])["status"] == "archived"
    assert store.get(old_high["id"])["status"] == "active"


def test_enforce_capacity(memory_dir):
    for index in range(3):
        _seed(subject=f"容量{index}", object=f"对象{index}",
              text=f"容量条目{index}", importance=0.1 * (index + 1))

    archived = lifecycle.enforce_capacity(max_open=2)
    assert archived == 1
    assert store.stats()["archived"] == 1
    assert store.stats()["open"] == 2


def test_purge_deleted(memory_dir):
    old = _seed(subject="待清理", object="甲", text="待清理条目")
    fresh = _seed(subject="保留", object="乙", text="保留条目")
    store.delete(old["id"])
    store.delete(fresh["id"])

    items = store.load_all()
    for item in items:
        if item["id"] == old["id"]:
            item["deleted_at"] = "2025-01-01T00:00:00+08:00"
    store._save_all(items)

    purged = lifecycle.purge_deleted(now="2026-11-27")
    assert purged == 1
    assert store.get(old["id"]) is None
    assert store.get(fresh["id"]) is not None


def test_rest_consolidate_and_audit(client, task, monkeypatch):
    def fake_chat(messages, **kwargs):
        return json.dumps([
            {"kind": "fact", "text": "项目A 负责人为李四",
             "quote": "项目A 负责人由李四负责"},
        ], ensure_ascii=False)

    import core.llm as llm
    monkeypatch.setattr(llm, "chat_completion", fake_chat)

    resp = client.post(f"/api/memory/consolidate/{TASK_ID}")
    assert resp.status_code == 200
    assert resp.json()["created"] == 1

    missing = client.post("/api/memory/consolidate/no-such-task")
    assert missing.status_code == 404

    audit = client.get("/api/memory/audit").json()["items"]
    assert any(row.get("action") == "consolidate" for row in audit)
