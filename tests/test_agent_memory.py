"""tests/test_agent_memory.py — 长期记忆验收（spec §13）。

覆盖：无来源拒收、重复写入收敛、不同 subject 不互相闭合、as_of 历史回捞、
namespace 隔离、开关关闭、角色文件不被写入、注入渲染。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agent_memory import inject, retrieve, schema, store


@pytest.fixture()
def memory_dir(tmp_path, monkeypatch):
    path = tmp_path / "memory"
    monkeypatch.setattr(store, "MEMORY_DIR", path)
    yield path


def _source(task_id: str = "t1", quote: str = "由李四负责") -> dict:
    return {"task_id": task_id, "quote": quote, "anchor": {}}


def _item(**overrides) -> dict:
    base = {
        "namespace": "task:t1",
        "kind": "fact",
        "subject": "项目A",
        "relation": "负责人",
        "object": "张三",
        "text": "项目A 负责人为张三",
        "source": _source(),
        "valid_from": "2025-03-01",
    }
    base.update(overrides)
    return base


def test_write_without_source_is_rejected(memory_dir):
    with pytest.raises(store.MemoryWriteError) as excinfo:
        store.upsert({
            "namespace": "task:t1",
            "kind": "fact",
            "text": "项目A 负责人为张三",
        })
    assert excinfo.value.code == "no_source"
    assert store.list_items() == []


def test_repeated_write_keeps_single_open_item(memory_dir):
    for _ in range(3):
        store.upsert(_item())
    assert store.stats()["open"] == 1
    assert len(store.list_items()) == 1


def test_different_subject_same_relation_does_not_close(memory_dir):
    store.upsert(_item(subject="项目A", object="张三", text="项目A 负责人为张三"))
    store.upsert(_item(subject="项目B", object="王五", text="项目B 负责人为王五",
                       source=_source(quote="王五负责项目B")))

    stats = store.stats()
    assert stats["open"] == 2
    assert stats["closed"] == 0


def test_as_of_reads_closed_history(memory_dir):
    store.upsert(_item(object="张三", text="项目A 负责人为张三",
                       valid_from="2025-03-01"))
    store.upsert(_item(object="李四", text="项目A 负责人为李四",
                       source=_source(quote="由李四负责"),
                       valid_from="2026-05-14"))

    stats = store.stats()
    assert stats["open"] == 1
    assert stats["closed"] == 1

    chain = schema.namespace_chain("t1", None, None)
    current = retrieve.search("项目A 负责人", chain, touch=False)
    assert [hit["object"] for hit in current] == ["李四"]

    historical = retrieve.search("项目A 负责人", chain, as_of="2026-01-01", touch=False)
    assert [hit["object"] for hit in historical] == ["张三"]

    # 闭合只改元数据，正文不变
    closed = [it for it in store.list_items() if it["valid_to"]][0]
    assert closed["text"] == "项目A 负责人为张三"


def test_namespace_isolation(memory_dir):
    store.upsert(_item(namespace="space:proj-x", object="张三",
                       text="项目A 负责人为张三"))

    other_space = schema.namespace_chain("t1", "proj-y", None)
    assert retrieve.search("项目A 负责人", other_space, touch=False) == []

    own_space = schema.namespace_chain("t1", "proj-x", None)
    assert len(retrieve.search("项目A 负责人", own_space, touch=False)) == 1


def test_duplicate_merges_tags_and_importance(memory_dir):
    store.upsert(_item(tags=["组织"], importance=0.4))
    outcome = store.upsert(_item(tags=["人事"], importance=0.9))

    assert outcome["action"] == "merged"
    items = store.list_items()
    assert len(items) == 1
    assert set(items[0]["tags"]) == {"组织", "人事"}
    assert items[0]["importance"] == pytest.approx(0.9)


def test_feature_flag_defaults():
    from core.settings_store import get_feature_flags

    flags = get_feature_flags()
    assert flags["agent_memory"] is True
    assert flags["agent_memory_consolidate"] is False


def test_flag_off_disables_both_blocks(memory_dir, monkeypatch):
    store.upsert(_item(namespace="role:pm", kind="preference",
                       subject="", relation="", object="",
                       text="汇报统一三段式", importance=0.9))

    import core.settings_store as settings_store

    monkeypatch.setattr(settings_store, "get_feature_flags",
                        lambda: {"agent_memory": False})
    assert inject.build_blocks("汇报", task_id="t1", role_name="pm") == []
    assert inject.build_core_prompt("pm") == ""


def test_inject_renders_core_and_archival(memory_dir):
    store.upsert(_item(namespace="role:pm", kind="preference",
                       subject="", relation="", object="",
                       text="汇报统一三段式", importance=0.9))
    store.upsert(_item(object="李四", text="项目A 负责人为李四",
                       source=_source(quote="由李四负责")))

    blocks = inject.build_blocks("项目A 负责人", task_id="t1", role_name="pm")
    joined = "\n".join(blocks)

    assert inject.CORE_HEADER in joined
    assert "汇报统一三段式" in joined
    assert inject.ARCHIVAL_HEADER in joined
    assert "项目A 负责人为李四" in joined
    # 来源可回溯到会议
    assert "t1" in joined


def test_role_files_unchanged_by_memory_writes(memory_dir):
    role_root = Path("data/agent/_roles")
    if not role_root.exists():
        pytest.skip("角色目录不存在，跳过文件不变性检查")

    before = {path: path.read_bytes() for path in role_root.rglob("*.md")}
    store.upsert(_item(namespace="role:pm", kind="preference",
                       subject="", relation="", object="",
                       text="偏好：先结论后论据", importance=0.9))
    store.close(store.list_items()[0]["id"])
    after = {path: path.read_bytes() for path in role_root.rglob("*.md")}

    assert before == after


def test_namespace_parsing():
    assert schema.parse_namespace("global") == {"kind": "global", "id": ""}
    assert schema.parse_namespace("task:t1") == {"kind": "task", "id": "t1"}
    with pytest.raises(ValueError):
        schema.parse_namespace("free-text")
    with pytest.raises(ValueError):
        schema.parse_namespace("space:")

    chain = schema.namespace_chain("t1", "p1", "pm")
    assert [entry["namespace"] for entry in chain] == [
        "task:t1", "space:p1", "role:pm", "global"]
    assert [entry["weight"] for entry in chain] == [1.0, 0.8, 0.7, 0.5]


def test_remember_tool_roundtrip(memory_dir):
    """工具面闭环：无来源拒收 → 带 quote 写入 → 检索命中 → 删除。"""
    from fastapi.testclient import TestClient

    from app.server import app
    from core.agent_tools import tokens as tk
    from core.task_store import tasks

    task_id = "memtest-0001"
    tasks[task_id] = {
        "task_id": task_id,
        "status": "completed",
        "decisions": [],
        "dialogue": [{"sentences": [{"text": "项目A 的负责人由李四负责"}]}],
    }
    try:
        with TestClient(app) as client:
            ctx = tk.issue_token(task_id=task_id, project_id=None,
                                 auth_tier="workspace_write")
            headers = {"Authorization": f"Bearer {ctx.token}"}

            rejected = client.post("/api/agent-tools/invoke", headers=headers, json={
                "name": "remember",
                "arguments": {"text": "一条无法回溯到逐字稿的结论", "kind": "fact"},
            })
            assert rejected.status_code == 422
            assert rejected.json()["detail"]["error"] == "no_source"

            accepted = client.post("/api/agent-tools/invoke", headers=headers, json={
                "name": "remember",
                "arguments": {
                    "text": "项目A 负责人为李四",
                    "kind": "fact",
                    "subject": "项目A",
                    "relation": "负责人",
                    "object": "李四",
                    "quote": "由李四负责",
                },
            })
            assert accepted.status_code == 200
            body = accepted.json()["result"]
            assert body["action"] == "inserted"
            assert body["quote"] == "由李四负责"
            memory_id = body["id"]
            assert store.stats()["open"] == 1

            found = client.post("/api/agent-tools/invoke", headers=headers, json={
                "name": "search_memory",
                "arguments": {"query": "项目A 负责人"},
            })
            items = json.loads(found.json()["result"])["items"]
            assert [item["object"] for item in items] == ["李四"]

            forgotten = client.post("/api/agent-tools/invoke", headers=headers, json={
                "name": "forget",
                "arguments": {"memory_id": memory_id},
            })
            assert forgotten.json()["result"]["deleted"] is True
            assert store.stats()["deleted"] == 1
    finally:
        tasks.pop(task_id, None)
