"""tests/test_memory_api.py — 长期记忆 REST 接口（tasks.md §1.5）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.server import app
from core.agent_memory import store


@pytest.fixture()
def memory_dir(tmp_path, monkeypatch):
    path = tmp_path / "memory"
    monkeypatch.setattr(store, "MEMORY_DIR", path)
    yield path


@pytest.fixture()
def client(memory_dir):
    with TestClient(app) as c:
        yield c


def _seed(**overrides) -> dict:
    base = {
        "namespace": "task:t1",
        "kind": "fact",
        "subject": "项目A",
        "relation": "负责人",
        "object": "张三",
        "text": "项目A 负责人为张三",
        "source": {"task_id": "t1", "quote": "由张三负责", "anchor": {}},
    }
    base.update(overrides)
    return store.upsert(base)["item"]


def test_manual_create_marks_manual_source(client):
    resp = client.post("/api/memory", json={
        "text": "汇报统一三段式",
        "kind": "preference",
        "namespace": "global",
    })
    assert resp.status_code == 200
    item = resp.json()
    assert item["status"] == "active"
    assert item["source"] == {"manual": True}
    assert client.get("/api/memory/stats").json()["open"] == 1


def test_list_filters_open_and_closed(client):
    opened = _seed(text="项目A 负责人为张三")
    _seed(text="项目A 负责人为李四",
          object="李四", source={"task_id": "t1", "quote": "由李四负责"},
          valid_from="2026-05-14")
    _ = opened

    open_items = client.get("/api/memory", params={"view": "open"}).json()["items"]
    closed_items = client.get("/api/memory", params={"view": "closed"}).json()["items"]
    assert [it["object"] for it in open_items] == ["李四"]
    assert [it["object"] for it in closed_items] == ["张三"]


def test_cursor_pagination(client):
    for text in ("记忆一", "记忆二", "记忆三"):
        client.post("/api/memory", json={
            "text": text, "kind": "fact", "namespace": "global"})

    first = client.get("/api/memory", params={"view": "open", "limit": 2}).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"]

    second = client.get("/api/memory", params={
        "view": "open", "limit": 2, "cursor": first["next_cursor"]}).json()
    ids = [it["id"] for it in first["items"]] + [it["id"] for it in second["items"]]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert second["next_cursor"] is None


def test_patch_edits_text_and_ignores_status(client):
    item = _seed()
    resp = client.patch(f"/api/memory/{item['id']}", json={
        "text": "项目A 负责人为张三（更新）",
        "status": "archived",
    })
    assert resp.status_code == 200
    assert resp.json()["text"] == "项目A 负责人为张三（更新）"
    assert resp.json()["status"] == "active"
    assert client.get("/api/memory/stats").json()["open"] == 1


def test_close_and_reopen(client):
    item = _seed()
    assert client.post(f"/api/memory/{item['id']}/close").status_code == 200
    stats = client.get("/api/memory/stats").json()
    assert stats["closed"] == 1 and stats["open"] == 0

    assert client.post(f"/api/memory/{item['id']}/reopen").status_code == 200
    stats = client.get("/api/memory/stats").json()
    assert stats["open"] == 1 and stats["closed"] == 0


def test_accept_and_reject_proposed(client):
    accepted = _seed(text="待确认记忆甲", status="proposed",
                     source={"task_id": "t1", "quote": "甲"})
    rejected = _seed(text="待确认记忆乙", status="proposed", subject="项目B",
                     source={"task_id": "t1", "quote": "乙"})

    assert client.post(f"/api/memory/{accepted['id']}/accept").json()["status"] == "active"
    assert client.post(f"/api/memory/{rejected['id']}/reject").json()["status"] == "deleted"
    stats = client.get("/api/memory/stats").json()
    assert stats["proposed"] == 0
    assert stats["deleted"] == 1


def test_delete_is_soft(client):
    item = _seed()
    assert client.delete(f"/api/memory/{item['id']}").json()["status"] == "deleted"
    assert client.get("/api/memory/stats").json()["deleted"] == 1


def test_export_returns_attachment(client):
    _seed()
    resp = client.get("/api/memory/export")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    body = json.loads(resp.text)
    assert body["count"] == 1
    assert body["items"][0]["object"] == "张三"


def test_missing_id_returns_404(client):
    resp = client.patch("/api/memory/mem_missing", json={"text": "不存在"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_bad_view_returns_422(client):
    resp = client.get("/api/memory", params={"view": "unknown"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "bad_view"
