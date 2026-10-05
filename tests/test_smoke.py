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
        import uuid

        from app.store import tasks

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
        import uuid

        from app.store import tasks

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
# 归档域
# ============================================================

class TestArchiveTask:
    """POST /api/tasks/{id}/archive 归档任务"""

    def test_archive_ok(self, client):
        import uuid

        from app.store import tasks

        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "progress": 100,
            "message": "完成",
            "audio_name": "test.wav",
            "audio_path": "/nonexistent/test.wav",
            "archived_at": None,
        }
        try:
            resp = client.post(f"/api/tasks/{task_id}/archive")
            assert resp.status_code == 200
            data = resp.json()
            assert data["archived_at"] is not None
        finally:
            tasks.pop(task_id, None)

    def test_archive_not_found(self, client):
        resp = client.post("/api/tasks/nonexistent-id/archive")
        assert resp.status_code == 404


class TestUnarchiveTask:
    """POST /api/tasks/{id}/unarchive 取消归档"""

    def test_unarchive_ok(self, client):
        import uuid

        from app.store import tasks

        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "progress": 100,
            "message": "完成",
            "audio_name": "test.wav",
            "audio_path": "/nonexistent/test.wav",
            "archived_at": "2026-09-13T10:00:00",
        }
        try:
            resp = client.post(f"/api/tasks/{task_id}/unarchive")
            assert resp.status_code == 200
            data = resp.json()
            assert data["archived_at"] is None
        finally:
            tasks.pop(task_id, None)


class TestBatchArchive:
    """POST /api/tasks/batch-archive 批量归档"""

    def test_batch_archive_ok(self, client):
        import uuid

        from app.store import tasks

        ids = []
        for _ in range(3):
            tid = str(uuid.uuid4())
            tasks[tid] = {
                "task_id": tid,
                "status": "completed",
                "progress": 100,
                "message": "完成",
                "audio_name": "test.wav",
                "audio_path": "/nonexistent/test.wav",
                "archived_at": None,
            }
            ids.append(tid)
        try:
            resp = client.post("/api/tasks/batch-archive", json={"task_ids": ids})
            assert resp.status_code == 200
            data = resp.json()
            assert data["archived"] == 3
            for tid in ids:
                assert tasks[tid]["archived_at"] is not None
        finally:
            for tid in ids:
                tasks.pop(tid, None)

    def test_batch_archive_partial(self, client):
        """部分 ID 不存在时，仅归档存在的任务"""
        import uuid

        from app.store import tasks

        tid = str(uuid.uuid4())
        tasks[tid] = {
            "task_id": tid,
            "status": "completed",
            "progress": 100,
            "message": "完成",
            "audio_name": "test.wav",
            "audio_path": "/nonexistent/test.wav",
            "archived_at": None,
        }
        try:
            resp = client.post("/api/tasks/batch-archive", json={"task_ids": [tid, "nonexistent"]})
            assert resp.status_code == 200
            data = resp.json()
            assert data["archived"] == 1
        finally:
            tasks.pop(tid, None)


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
        # REQ-SETTINGS-IA 第 4 刀（AC-3）：voiceprint 配置面已从 schema 下架；
        # 逐能力算力来源快照随 GET 暴露（详情层数据源）
        assert "voiceprint" not in data
        assert "capability" in data


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


# ============================================================
# AI 洞察域
# ============================================================

class TestInsightMessagesPersistence:
    """洞察消息按会议持久化"""

    def test_get_messages_not_found(self, client):
        """不存在的会议返回空列表"""
        resp = client.get("/api/insights/messages/nonexistent-task-id")
        assert resp.status_code == 200
        assert resp.json()["messages"] == []

    def test_save_and_load_messages(self, client, tmp_path, monkeypatch):
        """保存后加载应返回相同消息"""
        import app.routers.insights as insights_router
        monkeypatch.setattr(insights_router, "TASKS_DIR", tmp_path)
        task_id = "test-task-123"
        messages = [
            {"id": "msg-1", "title": "测试洞察", "body": "内容", "timestamp": 1234567890},
        ]
        resp = client.post(f"/api/insights/messages/{task_id}", json={"messages": messages})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # 加载
        resp = client.get(f"/api/insights/messages/{task_id}")
        assert resp.status_code == 200
        loaded = resp.json()["messages"]
        assert len(loaded) == 1
        assert loaded[0]["title"] == "测试洞察"


# ============================================================
# 实时翻译
# ============================================================

class TestRealtimeTranslator:
    """实时翻译器基本功能"""

    def test_translator_init_and_feed(self):
        """翻译器初始化、接收句子、停止不抛异常"""
        from core.translate import RealtimeTranslator

        translations_received = []

        def on_translation(translations):
            translations_received.extend(translations)

        translator = RealtimeTranslator(
            target_lang="en",
            on_translation=on_translation,
            on_status=lambda s: None,
        )
        assert translator.target_lang == "en"
        assert not translator.is_running
        assert not translator.is_stopped

        # 启动
        translator.start()
        assert translator.is_running

        # 送入句子（未启动 LLM，仅测试缓冲逻辑）
        translator.feed_sentence({
            "text": "今天我们来讨论项目进度",
            "speaker_id": 0,
            "speaker_name": "发言人1",
            "begin_time": 0,
            "end_time": 3000,
        })

        # 停止（会尝试翻译缓冲中的句子，但 LLM 调用会失败，不应抛异常）
        translator.stop()
        assert translator.is_stopped
        assert not translator.is_running

    def test_translator_set_target_lang(self):
        """热切换目标语言"""
        from core.translate import RealtimeTranslator

        translator = RealtimeTranslator(target_lang="en")
        translator.start()
        assert translator.target_lang == "en"

        translator.set_target_lang("ja")
        assert translator.target_lang == "ja"

        translator.stop()

    def test_translator_get_all_translations(self):
        """获取全量翻译结果"""
        from core.translate import RealtimeTranslator

        translator = RealtimeTranslator(target_lang="en")
        translator.start()
        translations = translator.get_all_translations()
        assert isinstance(translations, list)
        assert len(translations) == 0
        translator.stop()

    def test_translator_parse_response(self):
        """解析 LLM 返回的翻译结果"""
        from core.translate import RealtimeTranslator

        translator = RealtimeTranslator(target_lang="en")

        # 正常 JSON 数组
        result = translator._parse_response('["Hello", "World"]', 2)
        assert result == ["Hello", "World"]

        # 带 markdown 代码块
        result = translator._parse_response('```json\n["Hello", "World"]\n```', 2)
        assert result == ["Hello", "World"]

        # 数量不匹配时兆底
        result = translator._parse_response('invalid', 3)
        assert len(result) == 3
        assert all(t == "[翻译失败]" for t in result)
