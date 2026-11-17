"""转写响应形状：句级词时间戳（words）不得出现在接口响应里。

背景：`sentences[].words` 占 dialogue 序列化体积约 88%，前端无任何消费方。
响应层统一剔除（清理版开/关两种口径），且绝不写回内存 task / 磁盘。
"""
import pytest
from fastapi.testclient import TestClient

from app.server import app
from core.task_store import tasks as task_store

TID = "shape-test-task"

DIALOGUE = [
    {
        "speaker_id": 0,
        "text": "就用100块钱这个税费。",
        "sentences": [
            {
                "begin_time": 0,
                "end_time": 3000,
                "text": "就用100块钱这个税费。",
                "sentence_id": 1,
                "speaker_id": 0,
                "words": [
                    {"begin_time": 0, "end_time": 197, "text": "就", "punctuation": ""},
                    {"begin_time": 197, "end_time": 1400, "text": "用100块钱", "punctuation": ""},
                ],
            }
        ],
    }
]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def task_with_words():
    task_store[TID] = {
        "task_id": TID,
        "status": "completed",
        "progress": 100,
        "message": "完成",
        "title": "词时间戳任务",
        "audio_name": "x.wav",
        "meeting_date": "2026-11-01",
        "created_at": "2026-11-01T10:00:00",
        "chapters": [{"title": "第一章"}],
        "dialogue": DIALOGUE,
    }
    yield task_store[TID]
    task_store.pop(TID, None)


def _sentences(dialogue):
    return [s for block in dialogue for s in block.get("sentences") or []]


class TestWordsStripped:
    def test_detail_has_no_words(self, client, task_with_words):
        resp = client.get(f"/api/tasks/{TID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dialogue"], "转写不应被整体清空"
        for sentence in _sentences(body["dialogue"]):
            assert "words" not in sentence

    def test_full_list_has_no_words(self, client, task_with_words):
        resp = client.get("/api/tasks")
        item = next(t for t in resp.json()["tasks"] if t["task_id"] == TID)
        for sentence in _sentences(item["dialogue"]):
            assert "words" not in sentence

    def test_cleanup_disabled_still_strips(self, client, task_with_words, monkeypatch):
        from app.routers import tasks as tasks_router

        monkeypatch.setattr(
            tasks_router, "get_transcript_config", lambda: {"cleanup": {"enabled": False}}
        )
        body = client.get(f"/api/tasks/{TID}").json()
        assert body["transcript_layers"]["cleanup"] is False
        assert body["dialogue"]
        for sentence in _sentences(body["dialogue"]):
            assert "words" not in sentence

    def test_text_and_timestamps_unchanged(self, client, task_with_words):
        body = client.get(f"/api/tasks/{TID}").json()
        actual = _sentences(body["dialogue"])[0]
        expected = _sentences(DIALOGUE)[0]
        for key in ("begin_time", "end_time", "text", "sentence_id", "speaker_id"):
            assert actual[key] == expected[key]

    def test_memory_task_keeps_words(self, client, task_with_words):
        client.get(f"/api/tasks/{TID}")
        assert "words" in _sentences(task_with_words["dialogue"])[0]
