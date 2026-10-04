"""GET /api/tasks?view=lite 轻量列表契约。

完成侦测器 5s 高频轮询只需要状态字段；全量列表携带全部转写（实测 76 场会议 35MB，
在 async 端点里同步富化会阻塞事件循环，导致点击重生成 2~3s 无响应）。
"""
import pytest
from fastapi.testclient import TestClient

from app.server import app
from app.store import tasks as task_store


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


TID = "lite-test-task"


@pytest.fixture
def heavy_task():
    task_store[TID] = {
        "task_id": TID,
        "status": "processing",
        "progress": 85,
        "message": "正在生成纪要...",
        "title": "重任务",
        "audio_name": "x.wav",
        "meeting_date": "2026-10-01",
        "created_at": "2026-10-01T10:00:00",
        "dialogue": [{"speaker_id": 0, "text": "x", "sentences": [{"text": "x"}]}],
        "chapters": [{"title": "第一章"}],
        "todos": [{"id": "t1", "text": "待办"}],
    }
    yield task_store[TID]
    task_store.pop(TID, None)


class TestTaskListLite:
    def test_lite_excludes_heavy_artifacts(self, client, heavy_task):
        resp = client.get("/api/tasks", params={"view": "lite"})
        assert resp.status_code == 200
        lite = next(t for t in resp.json()["tasks"] if t["task_id"] == TID)
        assert lite["status"] == "processing"
        assert lite["progress"] == 85
        assert lite["title"] == "重任务"
        assert "dialogue" not in lite
        assert "chapters" not in lite
        assert "todos" not in lite

    def test_full_keeps_artifacts(self, client, heavy_task):
        resp = client.get("/api/tasks")
        full = next(t for t in resp.json()["tasks"] if t["task_id"] == TID)
        assert "dialogue" in full
        assert "chapters" in full
        assert "todos" in full

    def test_unknown_view_falls_back_to_full(self, client, heavy_task):
        resp = client.get("/api/tasks", params={"view": "wat"})
        item = next(t for t in resp.json()["tasks"] if t["task_id"] == TID)
        assert "dialogue" in item
