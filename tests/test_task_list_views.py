"""GET /api/tasks?view=list 与 GET /api/tasks/search 契约。

列表视图剔除 dialogue / realtime_full_transcript，补 has_dialogue / speaker_share /
dialogue_duration；转写全文检索改由服务端端点承担（只回 task_id）。
"""
import pytest
from fastapi.testclient import TestClient

from app.server import app
from core import speaker_share as share_mod
from core.task_store import tasks as task_store

TID = "list-view-test-task"
OTHER_TID = "list-view-test-other"


def _dialogue():
    return [
        {
            "speaker_id": 0,
            "text": "先把这个税费扣下来。",
            "sentences": [
                {"begin_time": 0, "end_time": 4000, "text": "先把这个税费扣下来。",
                 "sentence_id": 1, "speaker_id": 0},
            ],
        },
        {
            "speaker_id": 2,
            "text": "我同意，走 Contract 条款。",
            "sentences": [
                {"begin_time": 4000, "end_time": 7000, "text": "我同意，走 Contract 条款。",
                 "sentence_id": 2, "speaker_id": 2},
            ],
        },
    ]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_share_cache():
    share_mod._CACHE.clear()
    yield
    share_mod._CACHE.clear()


@pytest.fixture
def task_with_transcript():
    task_store[TID] = {
        "task_id": TID,
        "status": "completed",
        "progress": 100,
        "message": "完成",
        "title": "税费讨论",
        "audio_name": "a.wav",
        "audio_duration": 7,
        "meeting_date": "2026-11-02",
        "created_at": "2026-11-02T10:00:00",
        "speaker_mapping": {"0": "张三", "2": "李四"},
        "dialogue": _dialogue(),
        "realtime_full_transcript": [{"text": "实时逐字稿"}],
        "chapters": [{"title": "开场"}],
        "decisions": [{"id": "d1", "text": "按合同条款执行"}],
    }
    task_store[OTHER_TID] = {
        "task_id": OTHER_TID,
        "status": "completed",
        "progress": 100,
        "message": "完成",
        "title": "空转写会议",
        "audio_name": "b.wav",
        "meeting_date": "2026-11-03",
        "created_at": "2026-11-03T10:00:00",
        "dialogue": [],
    }
    yield task_store[TID]
    task_store.pop(TID, None)
    task_store.pop(OTHER_TID, None)


def _item(client, view):
    resp = client.get("/api/tasks", params={"view": view})
    assert resp.status_code == 200
    return next(t for t in resp.json()["tasks"] if t["task_id"] == TID)


class TestTaskListViews:
    def test_list_drops_transcripts(self, client, task_with_transcript):
        item = _item(client, "list")
        assert "dialogue" not in item
        assert "realtime_full_transcript" not in item

    def test_list_keeps_light_artifacts(self, client, task_with_transcript):
        item = _item(client, "list")
        for key in ("chapters", "decisions", "speaker_mapping", "title", "audio_duration"):
            assert key in item

    def test_list_has_derived_fields(self, client, task_with_transcript):
        item = _item(client, "list")
        assert item["has_dialogue"] is True
        assert item["speaker_share"] == {"0": 4.0, "2": 3.0}
        assert item["dialogue_duration"] == 7.0

    def test_empty_dialogue_task(self, client, task_with_transcript):
        resp = client.get("/api/tasks", params={"view": "list"})
        other = next(t for t in resp.json()["tasks"] if t["task_id"] == OTHER_TID)
        assert other["has_dialogue"] is False
        assert other["speaker_share"] == {}
        assert other["dialogue_duration"] == 0.0

    def test_lite_contract_unchanged(self, client, task_with_transcript):
        item = _item(client, "lite")
        assert "dialogue" not in item
        assert "speaker_share" not in item
        assert item["status"] == "completed"

    def test_full_keeps_dialogue(self, client, task_with_transcript):
        item = _item(client, "full")
        assert item["dialogue"]
        assert "speaker_share" not in item

    def test_unknown_view_falls_back_to_full(self, client, task_with_transcript):
        item = _item(client, "wat")
        assert item["dialogue"]

    def test_share_cache_recomputes_on_dialogue_change(self, client, task_with_transcript):
        assert _item(client, "list")["speaker_share"] == {"0": 4.0, "2": 3.0}
        task_with_transcript["dialogue"] = _dialogue()[:1]
        assert _item(client, "list")["speaker_share"] == {"0": 4.0}


class TestTranscriptSearch:
    def _search(self, client, q):
        resp = client.get("/api/tasks/search", params={"q": q})
        assert resp.status_code == 200
        return resp.json()

    def test_hit(self, client, task_with_transcript):
        body = self._search(client, "税费")
        assert TID in body["task_ids"]
        assert body["truncated"] is False

    def test_hit_is_case_insensitive(self, client, task_with_transcript):
        assert TID in self._search(client, "contract")["task_ids"]

    def test_miss(self, client, task_with_transcript):
        assert TID not in self._search(client, "不存在的词汇xyz")["task_ids"]

    def test_empty_query(self, client, task_with_transcript):
        body = self._search(client, "   ")
        assert body == {"query": "", "task_ids": [], "truncated": False}

    def test_not_shadowed_by_detail_route(self, client, task_with_transcript):
        # /api/tasks/search 必须命中检索端点，而不是被 /api/tasks/{task_id} 吃掉
        assert "task_ids" in self._search(client, "税")

    def test_returns_ids_only(self, client, task_with_transcript):
        body = self._search(client, "税费")
        assert set(body) == {"query", "task_ids", "truncated"}
        assert all(isinstance(i, str) for i in body["task_ids"])
