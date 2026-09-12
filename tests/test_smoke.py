"""
tests/test_smoke.py — 关键路径冒烟测试

覆盖每个功能域至少一个关键 API，确保：
  - 应用可正常初始化
  - 核心端点可响应（不 500）
  - 录音启动不阻塞（防止 async/sync 边界回归）

运行方式：
  cd <项目根>
  source venv/bin/activate
  pytest tests/test_smoke.py -v

注意：声纹、对话、文本桥接、SMS/认证/管理等域的测试已拆分至独立文件：
  - tests/test_voiceprint.py — 声纹域
  - tests/test_chat.py — AI 对话域
  - tests/test_text_bridge.py — 文本桥接匹配域
  - tests/test_misc.py — 杂项域（SMS/认证/版本/用量/管理/配置/理念/错误分类/静默检测）
"""

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture
def client():
    """创建测试客户端"""
    with TestClient(app) as c:
        yield c


# ============================================================
# 基础可用性
# ============================================================

class TestServerStarts:
    """应用初始化成功"""

    def test_app_exists(self):
        assert app is not None
        assert app.title == "Open Meeting Scribe"


class TestIndexPage:
    """GET / 返回 HTML"""

    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Open Meeting Scribe" in resp.text


# ============================================================
# 任务域
# ============================================================

class TestListTasks:
    """GET /api/tasks 返回 200 + JSON"""

    def test_list_tasks_ok(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)


class TestGetTaskNotFound:
    """GET /api/tasks/{id} 不存在时返回 404"""

    def test_task_not_found(self, client):
        resp = client.get("/api/tasks/nonexistent-id")
        assert resp.status_code == 404


class TestRetranscribeNotFound:
    """POST /api/tasks/{id}/retranscribe 不存在时返回 404"""

    def test_retranscribe_not_found(self, client):
        resp = client.post("/api/tasks/nonexistent-id/retranscribe")
        assert resp.status_code == 404


class TestRetrySummaryNotFound:
    """POST /api/tasks/{id}/retry-summary 不存在时返回 404"""

    def test_retry_summary_not_found(self, client):
        resp = client.post("/api/tasks/nonexistent-id/retry-summary")
        assert resp.status_code == 404


class TestRetrySummaryNoDialogue:
    """POST /api/tasks/{id}/retry-summary 无 dialogue 时返回 400"""

    def test_retry_summary_no_dialogue(self, client):
        from app.store import tasks, save_task_to_disk
        import uuid

        # 创建一个无 dialogue 的任务
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "task_id": task_id,
            "status": "failed",
            "progress": 70,
            "message": "测试",
            "audio_name": "test.wav",
            "audio_path": "/nonexistent/path.wav",
            "dialogue": None,
            "error": "测试错误",
            "error_category": "unknown",
            "error_suggestion": "测试建议",
            "failed_stage": "summarize",
            "retry_count": 0,
            "speaker_uuid_mapping": {},
        }
        try:
            resp = client.post(f"/api/tasks/{task_id}/retry-summary")
            assert resp.status_code == 400
        finally:
            tasks.pop(task_id, None)


class TestRetrySummaryOk:
    """POST /api/tasks/{id}/retry-summary 有 dialogue 时返回 200"""

    def test_retry_summary_with_dialogue(self, client, tmp_path):
        from app.store import tasks
        import uuid

        # 创建一个有 dialogue 的临时音频文件
        audio_file = tmp_path / "test_audio.wav"
        audio_file.write_bytes(b"fake audio data")

        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "task_id": task_id,
            "status": "failed",
            "progress": 70,
            "message": "测试",
            "audio_name": "test.wav",
            "audio_path": str(audio_file),
            "dialogue": [{"speaker_id": 0, "text": "测试文本", "sentences": []}],
            "error": "纪要生成失败",
            "error_category": "transient",
            "error_suggestion": "服务暂时不可用",
            "failed_stage": "summarize",
            "retry_count": 0,
            "speaker_uuid_mapping": {"0": "test-uuid"},
            "summary": None,
            "output_path": None,
            "title": None,
            "created_at": "2026-09-04T10:00:00",
            "user_notes": None,
        }
        try:
            resp = client.post(f"/api/tasks/{task_id}/retry-summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "processing"
            # 注：TestClient 中 BackgroundTasks 同步执行，此处任务可能已完成或失败
            # 只验证错误字段被清除（核心逻辑正确性）
            assert tasks[task_id]["error"] is None
            assert tasks[task_id]["failed_stage"] is None
        finally:
            tasks.pop(task_id, None)


# ============================================================
# 说话人域
# ============================================================

class TestSpeakerCrud:
    """POST + GET /api/speakers 基本 CRUD"""

    def test_list_speakers(self, client):
        resp = client.get("/api/speakers")
        assert resp.status_code == 200
        data = resp.json()
        assert "speakers" in data

    def test_create_speaker_empty_name(self, client):
        """空姓名应返回 400"""
        resp = client.post("/api/speakers", json={"name": "  "})
        assert resp.status_code == 400


# ============================================================
# 设置域
# ============================================================

class TestGetSettings:
    """GET /api/settings 返回 200"""

    def test_settings_ok(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm" in data
        assert "asr" in data
        assert "voiceprint" in data


# ============================================================
# 热词域
# ============================================================

class TestGetHotwords:
    """GET /api/hotwords 返回 200"""

    def test_hotwords_ok(self, client):
        resp = client.get("/api/hotwords")
        assert resp.status_code == 200
        data = resp.json()
        assert "hotwords" in data
        assert "count" in data


class TestGetHotwordMappings:
    """GET /api/hotword-mappings 返回 200"""

    def test_mappings_ok(self, client):
        resp = client.get("/api/hotword-mappings")
        assert resp.status_code == 200
        data = resp.json()
        assert "mappings" in data


# ============================================================
# 用户域
# ============================================================

class TestGetUser:
    """GET /api/user 返回 200"""

    def test_user_ok(self, client):
        resp = client.get("/api/user")
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data


# ============================================================
# 录制域（核心：防阻塞回归）
# ============================================================

class TestRecordStatus:
    """GET /api/record/status 返回 200"""

    def test_record_status_ok(self, client):
        resp = client.get("/api/record/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "recording" in data


class TestRecordStartNotHang:
    """
    POST /api/record/start 在 5 秒内返回。

    核心回归测试：防止 async def 端点内执行阻塞操作卡死事件循环。
    如果端点阻塞超过 5 秒，pytest 会超时失败。
    """

    def test_record_start_responds_within_timeout(self, client):
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError("录音启动端点阻塞超过 5 秒！")

        # macOS 支持 SIGALRM
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)
        try:
            resp = client.post("/api/record/start")
            signal.alarm(0)  # 取消定时器
            # 可能成功（200）或因设备不可用失败（500），但必须在 5 秒内返回
            assert resp.status_code in (200, 400, 500)
        except TimeoutError:
            pytest.fail("录音启动端点阻塞超过 5 秒，事件循环可能被卡死")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


# ============================================================
# 项目域
# ============================================================

class TestListProjects:
    """GET /api/projects 返回 200"""

    def test_projects_ok(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data


# ============================================================
# 笔记/待办域
# ============================================================

class TestNotesNotFound:
    """GET /api/tasks/{id}/notes 不存在时返回 404"""

    def test_notes_not_found(self, client):
        resp = client.get("/api/tasks/nonexistent-id/notes")
        assert resp.status_code == 404


class TestTodosNotFound:
    """GET /api/tasks/{id}/todos 不存在时返回 404"""

    def test_todos_not_found(self, client):
        resp = client.get("/api/tasks/nonexistent-id/todos")
        assert resp.status_code == 404
