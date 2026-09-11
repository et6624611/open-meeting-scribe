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


# ============================================================
# 声纹域（V3）
# ============================================================

class TestVoiceprintRegistry:
    """GET /api/voiceprint/registry 返回声纹注册表"""

    def test_registry_ok(self, client):
        resp = client.get("/api/voiceprint/registry")
        assert resp.status_code == 200
        data = resp.json()
        assert "voiceprints" in data
        assert "total" in data
        assert isinstance(data["voiceprints"], list)


class TestVoiceprintStatus:
    """GET /api/voiceprint/status/{uuid} 返回声纹状态"""

    def test_status_unknown_speaker(self, client):
        resp = client.get("/api/voiceprint/status/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_voiceprint"] is False
        assert data["speaker_uuid"] == "00000000-0000-0000-0000-000000000000"


class TestVoiceprintMatchNotFound:
    """POST /api/voiceprint/tasks/{task_id}/match 不存在时返回 404"""

    def test_match_not_found(self, client):
        resp = client.post("/api/voiceprint/tasks/nonexistent-id/match")
        assert resp.status_code == 404


class TestVoiceprintModuleLoad:
    """core.voiceprint 模块可正常加载"""

    def test_module_imports(self):
        from core.voiceprint import (
            extract_embedding, load_registry, match_voiceprint,
            cosine_similarity, auto_identify_speakers, MATCH_THRESHOLD,
        )
        assert MATCH_THRESHOLD > 0
        registry = load_registry()
        assert isinstance(registry, dict)


class TestVoiceprintRegisterFromBinding:
    """声纹自动注册闭环：绑定确认后补录注册表，并可被后续自动匹配命中"""

    def test_register_from_binding_then_auto_match(self, tmp_path, monkeypatch):
        import numpy as np
        from scipy.io import wavfile
        from core import voiceprint

        # 注册表隔离到临时目录，避免污染真实数据
        monkeypatch.setattr(voiceprint, "REGISTRY_FILE", tmp_path / "voiceprint_registry.json")

        # 模拟嵌入提取（避免加载重模型）：按调用次序交替返回两个正交 192 维向量
        vec_a = np.zeros(192, dtype=np.float32); vec_a[0] = 1.0
        vec_b = np.zeros(192, dtype=np.float32); vec_b[1] = 1.0
        calls = {"n": 0}

        def fake_extract(audio, sample_rate=voiceprint.SAMPLE_RATE):
            vec = vec_a if calls["n"] % 2 == 0 else vec_b
            calls["n"] += 1
            return vec.copy()

        monkeypatch.setattr(voiceprint, "extract_embedding", fake_extract)

        # 合成 16kHz 单声道 WAV（5 秒）
        sr = 16000
        wav_path = tmp_path / "normalized.wav"
        wavfile.write(str(wav_path), sr, np.zeros(sr * 5, dtype=np.int16))

        dialogue = [
            {"speaker_id": 0, "sentences": [{"begin_time": 0, "end_time": 4000}]},
            {"speaker_id": 1, "sentences": [{"begin_time": 4000, "end_time": 5000}]},
        ]
        mapping = {0: "uuid-aaaa", 1: "uuid-bbbb"}

        # 注册：speaker 0 音频充足应入库；speaker 1 仅 1s 应被拒绝
        results = voiceprint.register_from_binding(wav_path, dialogue, mapping, meeting_id="m1")
        assert results["uuid-aaaa"]["status"] == "registered"
        assert results["uuid-bbbb"]["status"] == "insufficient_audio"
        assert voiceprint.get_voiceprint_status("uuid-aaaa") is True
        assert voiceprint.get_voiceprint_status("uuid-bbbb") is False

        # 自动匹配：speaker 0 提取向量与注册向量相同，应命中 uuid-aaaa
        calls["n"] = 0
        match_results = voiceprint.auto_identify_speakers(wav_path, dialogue)
        auto_mapping = voiceprint.build_auto_mapping(match_results)
        assert auto_mapping.get(0) == "uuid-aaaa"
        assert 1 not in auto_mapping  # 音频不足不参与匹配

    def test_auto_identify_skips_empty_registry(self, tmp_path, monkeypatch):
        """注册表为空时跳过自动匹配（不做无意义的嵌入提取）"""
        from core import voiceprint

        monkeypatch.setattr(voiceprint, "REGISTRY_FILE", tmp_path / "empty_registry.json")
        extracted = {"called": False}

        def fake_extract(audio, sample_rate=voiceprint.SAMPLE_RATE):
            extracted["called"] = True
            return None

        monkeypatch.setattr(voiceprint, "extract_embedding", fake_extract)

        results = voiceprint.auto_identify_speakers(
            tmp_path,  # 路径不存在也无妨：注册表检查在前
            [{"speaker_id": 0, "sentences": [{"begin_time": 0, "end_time": 5000}]}],
        )
        assert results == []
        assert extracted["called"] is False


class TestVoiceprintRebuildAcrossMeetings:
    """跨会议声纹重建：人员独立于会议，聚合其参与的所有会议音频"""

    UUID = "11111111-2222-3333-4444-555555555555"

    def _prepare(self, tmp_path, monkeypatch, meeting_count):
        """隔离注册表、模拟嵌入提取、注入已完成会议任务"""
        import numpy as np
        from scipy.io import wavfile
        from types import SimpleNamespace
        from app import store
        from core import voiceprint, speakers

        monkeypatch.setattr(voiceprint, "REGISTRY_FILE", tmp_path / "registry.json")

        vec = np.zeros(192, dtype=np.float32)
        vec[0] = 1.0
        monkeypatch.setattr(
            voiceprint, "extract_embedding",
            lambda audio, sample_rate=voiceprint.SAMPLE_RATE: vec.copy(),
        )
        monkeypatch.setattr(
            speakers, "get_speaker_by_id",
            lambda uid: SimpleNamespace(name="测试人") if uid == self.UUID else None,
        )

        fake_tasks = {}
        for i in range(meeting_count):
            wav = tmp_path / f"m{i}_normalized.wav"
            wavfile.write(str(wav), 16000, np.zeros(16000 * 5, dtype=np.int16))
            fake_tasks[f"task-{i}"] = {
                "task_id": f"task-{i}",
                "status": "completed",
                "normalized_path": str(wav),
                "speaker_uuid_mapping": {"0": self.UUID},
                "dialogue": [
                    {"speaker_id": 0, "sentences": [{"begin_time": 0, "end_time": 4000}]},
                ],
            }
        monkeypatch.setattr(store, "tasks", fake_tasks)

    def test_rebuild_aggregates_all_meetings(self, client, tmp_path, monkeypatch):
        """两场会议的发言片段均参与重建，样本数等于会议数"""
        from core import voiceprint

        self._prepare(tmp_path, monkeypatch, meeting_count=2)
        resp = client.post(f"/api/voiceprint/rebuild/{self.UUID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meeting_count"] == 2
        assert data["sample_count"] == 2
        registry = voiceprint.load_registry()
        assert registry[self.UUID].sample_count == 2

    def test_rebuild_no_sufficient_audio(self, client, tmp_path, monkeypatch):
        """说话人存在但无足够发言音频时返回 400"""
        self._prepare(tmp_path, monkeypatch, meeting_count=0)
        resp = client.post(f"/api/voiceprint/rebuild/{self.UUID}")
        assert resp.status_code == 400

    def test_rebuild_unknown_speaker(self, client):
        """说话人不存在时返回 404"""
        resp = client.post("/api/voiceprint/rebuild/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


# ============================================================
# 错误分类域
# ============================================================

class TestErrorClassification:
    """core.errors 错误分类模块"""

    def test_module_imports(self):
        from core.errors import is_transient_error, classify_error
        assert callable(is_transient_error)
        assert callable(classify_error)

    def test_transient_error_detection(self):
        from core.errors import is_transient_error
        # 网络超时
        assert is_transient_error(TimeoutError("connection timed out")) is True
        assert is_transient_error(ConnectionError("connection refused")) is True
        # 关键词匹配
        assert is_transient_error(RuntimeError("Too many requests")) is True
        assert is_transient_error(RuntimeError("HTTP 429 rate limit")) is True
        assert is_transient_error(RuntimeError("503 Service Unavailable")) is True
        # 永久错误
        assert is_transient_error(FileNotFoundError("file not found")) is False
        assert is_transient_error(ValueError("invalid value")) is False

    def test_error_classification(self):
        from core.errors import classify_error
        # 瞬时错误
        result = classify_error(TimeoutError("timed out"))
        assert result["category"] == "transient"
        assert "建议" in result or "suggestion" in result

        # 音频错误
        result = classify_error(FileNotFoundError("音频文件不存在"))
        assert result["category"] == "audio"

        # API 配置错误
        result = classify_error(RuntimeError("未设置 DASHSCOPE_API_KEY"))
        assert result["category"] == "api_config"

        # 未知错误
        result = classify_error(RuntimeError("something weird happened"))
        assert result["category"] == "unknown"


class TestVoiceprintMatchMargin:
    """匹配门槛：最佳与次优优势不足时拒绝匹配（防同通道录音误判）"""

    @staticmethod
    def _vec(angle_deg: float) -> list:
        """构造 192 维单位向量，前 2 维按角度旋转，其余为 0，保证 L2 范数 = 1"""
        import math
        rad = math.radians(angle_deg)
        v = [0.0] * 192
        v[0] = math.cos(rad)
        v[1] = math.sin(rad)
        return v

    def test_margin_gate(self, tmp_path, monkeypatch):
        import numpy as np
        from core import voiceprint
        from core.voiceprint import VoiceprintRecord

        monkeypatch.setattr(voiceprint, "REGISTRY_FILE", tmp_path / "registry.json")
        # 注册两人，前 2 维余弦 ≈ 0.87（模拟高基线相似但 margin 足够）
        registry = {
            "uuid-a": VoiceprintRecord(speaker_uuid="uuid-a", embedding=self._vec(0.0)),
            "uuid-b": VoiceprintRecord(speaker_uuid="uuid-b", embedding=self._vec(30.0)),
        }
        voiceprint.save_registry(registry)

        # 查询与 a 完全一致：margin = 1 - 0.87 = 0.13 ≥ 门槛 → 命中 a
        hit = voiceprint.match_voiceprint(np.array(self._vec(0.0), dtype=np.float32))
        assert hit is not None and hit[0] == "uuid-a"

        # 查询落在两人正中间：双方相似度几乎相同，优势 ≈ 0 → 拒绝
        amb = voiceprint.match_voiceprint(np.array(self._vec(15.0), dtype=np.float32))
        assert amb is None



class TestVoiceprintSampleAccumulation:
    """多样本累积：重复注册按样本数加权平均，而非整体覆盖"""

    def test_accumulate_weighted_mean(self, tmp_path, monkeypatch):
        import numpy as np
        from core import voiceprint

        monkeypatch.setattr(voiceprint, "REGISTRY_FILE", tmp_path / "registry.json")

        first = np.array([1.0, 0.0], dtype=np.float32)
        voiceprint.register_voiceprint("uuid-a", first)

        second = np.array([0.0, 1.0], dtype=np.float32)
        record = voiceprint.register_voiceprint("uuid-a", second)

        assert record.sample_count == 2
        merged = np.array(record.embedding, dtype=np.float32)
        # 两个正交样本累积后应落在中间方向，而非被第二个样本整体覆盖
        assert merged[0] > 0.4 and merged[1] > 0.4
        assert abs(float(np.linalg.norm(merged)) - 1.0) < 1e-3

        # accumulate=False 时整体覆盖
        rec2 = voiceprint.register_voiceprint("uuid-a", second, accumulate=False)
        assert np.allclose(np.array(rec2.embedding, dtype=np.float32), second)


class TestJoblog:
    """作业日志：per-task 事件流的写入/概要/检索与渐进式上下文"""

    def test_append_and_read(self, tmp_path, monkeypatch):
        from core import joblog
        monkeypatch.setattr(joblog, "TASKS_DIR", tmp_path)

        joblog.append_event("t1", joblog.STAGE_TRANSCRIBE, "开始转写（stage1）")
        joblog.append_event("t1", joblog.STAGE_VOICEPRINT, "声纹自动匹配 0 命中", level="warn")

        events = joblog.read_events("t1")
        assert len(events) == 2
        assert events[0]["stage"] == "transcribe"
        assert events[1]["level"] == "warn"
        # 不存在的任务返回空列表
        assert joblog.read_events("nope") == []

    def test_summarize_and_search(self, tmp_path, monkeypatch):
        from core import joblog
        monkeypatch.setattr(joblog, "TASKS_DIR", tmp_path)

        joblog.append_event("t1", joblog.STAGE_TRANSCRIBE, "转写完成，识别 2 位说话人")
        joblog.append_event("t1", joblog.STAGE_VOICEPRINT, "声纹自动匹配 0 命中，降级为手动绑定", level="warn")
        joblog.append_event("t1", joblog.STAGE_SUMMARY, "纪要生成完成")

        events = joblog.read_events("t1")
        summary = joblog.summarize_events(events)
        assert "事件总数 3" in summary
        assert "纪要生成完成" in summary  # 最近事件进入概要

        # 按 stage 触发词检索：问声纹应命中 voiceprint 事件
        hits = joblog.search_events(events, "为什么声纹没匹配上")
        assert any(ev["stage"] == "voiceprint" for ev in hits)

    def test_build_context_progressive(self, tmp_path, monkeypatch):
        from core import joblog
        monkeypatch.setattr(joblog, "TASKS_DIR", tmp_path)

        # 无事件：不注入上下文
        assert joblog.build_context("empty", "为什么失败") is None

        joblog.append_event(
            "t1", joblog.STAGE_ERROR, "纪要生成失败: boom", level="error",
            detail={"category": "llm"},
        )
        ctx = joblog.build_context("t1", "为什么纪要失败")
        assert ctx is not None
        assert "作业日志概要" in ctx
        assert "相关作业明细" in ctx
        assert "纪要生成失败" in ctx

    def test_joblog_intent_gate(self):
        from app.routers.chat import _is_joblog_intent
        assert _is_joblog_intent("为什么声纹没有匹配上")
        assert _is_joblog_intent("纪要生成失败了吗")
        assert not _is_joblog_intent("你好")
        assert not _is_joblog_intent("今天天气不错")


# ============================================================
# 待办自动提取
# ============================================================

class TestParseTodosFromSummary:
    """parse_todos_from_summary 从纪要 Markdown 自动提取待办"""

    def test_basic_with_assignee(self):
        from core.summarize import parse_todos_from_summary
        summary = """## 三、待办事项
- [ ] **张三**：完成数据迁移方案
- [ ] **李四**：跟进服务器部署问题
"""
        todos = parse_todos_from_summary(summary)
        assert len(todos) == 2
        assert todos[0]["assignee"] == "张三"
        assert todos[0]["text"] == "完成数据迁移方案"
        assert todos[0]["done"] is False
        assert todos[0]["source"] == "auto"
        assert todos[1]["assignee"] == "李四"

    def test_with_deadline(self):
        from core.summarize import parse_todos_from_summary
        summary = "- [ ] **王五**：提交季度报告（9月10日）"
        todos = parse_todos_from_summary(summary)
        assert len(todos) == 1
        assert todos[0]["text"] == "提交季度报告"
        assert todos[0]["assignee"] == "王五"
        assert todos[0]["deadline"] == "9月10日"

    def test_without_assignee(self):
        from core.summarize import parse_todos_from_summary
        summary = "- [ ] 更新项目文档"
        todos = parse_todos_from_summary(summary)
        assert len(todos) == 1
        assert todos[0]["assignee"] == ""
        assert todos[0]["text"] == "更新项目文档"

    def test_dedup(self):
        from core.summarize import parse_todos_from_summary
        summary = "- [ ] **张三**：完成数据迁移方案\n- [ ] **张三**：完成数据迁移方案"
        todos = parse_todos_from_summary(summary)
        assert len(todos) == 1

    def test_empty_summary(self):
        from core.summarize import parse_todos_from_summary
        assert parse_todos_from_summary("") == []
        assert parse_todos_from_summary("无明确待办事项") == []

    def test_skip_completed_items(self):
        from core.summarize import parse_todos_from_summary
        summary = "- [x] 已完成的任务\n- [ ] 未完成的任务"
        todos = parse_todos_from_summary(summary)
        assert len(todos) == 1
        assert todos[0]["text"] == "未完成的任务"


# ============================================================
# AI 操作结果系统校验（ADR-0008）
# ============================================================

class TestChatEditVerification:
    """待办编辑：执行 + 磁盘回读校验 + 回复事后审计"""

    def _make_task(self, task_id):
        return {
            "task_id": task_id, "status": "completed", "audio_name": "校验测试会",
            "todos": [
                {"id": "t1", "text": "梳理会计事件库案例", "assignee": "张玉苗", "done": False},
                {"id": "t2", "text": "撰写初步报告", "assignee": "郝思南", "done": False},
            ],
        }

    def _patch_storage(self, monkeypatch, tmp_path, task_id):
        """隔离存储：tasks 字典与 TASKS_DIR 均指向测试沙箱"""
        import json
        from app import store
        from app.routers import chat as chat_mod
        fake_tasks = {task_id: self._make_task(task_id)}
        monkeypatch.setattr(store, "tasks", fake_tasks)
        monkeypatch.setattr(chat_mod, "tasks", fake_tasks)
        monkeypatch.setattr(store, "TASKS_DIR", tmp_path)
        monkeypatch.setattr(chat_mod, "TASKS_DIR", tmp_path)
        return chat_mod, json

    def test_execute_and_verify_assignee(self, tmp_path, monkeypatch):
        chat_mod, json = self._patch_storage(monkeypatch, tmp_path, "unit-edit-0001")
        ops = [{"op": "todo_assignee", "todo_id": "t1", "value": "张宇"}]
        changes = chat_mod._execute_and_verify_edits("unit-edit-0001", ops)
        assert len(changes) == 1
        assert changes[0]["verified"] is True
        assert changes[0]["old"] == "张玉苗" and changes[0]["new"] == "张宇"
        disk = json.loads((tmp_path / "unit-edit-0001.json").read_text(encoding="utf-8"))
        assert disk["todos"][0]["assignee"] == "张宇"

    def test_execute_and_verify_delete(self, tmp_path, monkeypatch):
        chat_mod, json = self._patch_storage(monkeypatch, tmp_path, "unit-edit-0002")
        changes = chat_mod._execute_and_verify_edits("unit-edit-0002", [{"op": "todo_delete", "todo_id": "t2"}])
        assert len(changes) == 1 and changes[0]["verified"] is True
        disk = json.loads((tmp_path / "unit-edit-0002.json").read_text(encoding="utf-8"))
        assert [t["id"] for t in disk["todos"]] == ["t1"]

    def test_noop_produces_no_changes(self, tmp_path, monkeypatch):
        chat_mod, _ = self._patch_storage(monkeypatch, tmp_path, "unit-edit-0003")
        ops = [{"op": "todo_assignee", "todo_id": "t1", "value": "张玉苗"}]
        assert chat_mod._execute_and_verify_edits("unit-edit-0003", ops) == []

    def test_sanitize_ops_whitelist(self):
        from app.routers import chat as chat_mod
        raw = '```json\n{"ops": [{"op": "todo_assignee", "todo_id": "t1", "value": "张宇"},' \
              ' {"op": "hack", "todo_id": "t1", "value": "x"},' \
              ' {"op": "todo_delete", "todo_id": "nope"}]}\n```'
        ops = chat_mod._sanitize_edit_ops(raw, {"t1", "t2"})
        assert len(ops) == 1 and ops[0]["op"] == "todo_assignee"

    def test_reply_claim_audit(self):
        from app.routers import chat as chat_mod
        # 无执行却声称操作 → 追加未执行提示
        audited = chat_mod._audit_reply_claims("已修正待办事项责任人姓名。", [])
        assert "系统校验" in audited and "未执行任何数据写操作" in audited
        # 有校验变更 → 追加执行结果清单
        changes = [{"op": "todo_assignee", "todo_id": "t1", "field": "assignee",
                    "old": "张玉苗", "new": "张宇", "verified": True}]
        audited = chat_mod._audit_reply_claims("好的。", changes)
        assert "系统校验" in audited and "张宇" in audited and "校验通过" in audited
        # 无声称无操作 → 原样返回
        assert chat_mod._audit_reply_claims("共 5 项待办。", []) == "共 5 项待办。"

    def test_chat_endpoint_edit_flow(self, client, tmp_path, monkeypatch):
        """端到端：编辑意图 → 执行校验 → 回复带系统校验结论与 verified_changes"""
        chat_mod, _ = self._patch_storage(monkeypatch, tmp_path, "unit-edit-0004")
        monkeypatch.setattr(chat_mod.joblog, "append_event", lambda *a, **k: None)
        calls = {"n": 0}

        async def fake_llm(messages, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:  # 第一次调用为意图解析
                return '{"ops": [{"op": "todo_assignee", "todo_id": "t1", "value": "张宇"}]}'
            return "相关待办责任人改为张宇。"

        monkeypatch.setattr(chat_mod, "async_chat_completion", fake_llm)
        resp = client.post("/api/chat", json={"message": "待办中张玉苗应该是张宇", "task_id": "unit-edit-0004"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified_changes"] and data["verified_changes"][0]["verified"] is True
        assert "系统校验" in data["reply"]
        # 编辑轮不再产出注入候选
        assert data["extracted_items"] == []
        # 关键词动作被编辑轮跳过
        assert data["action"] is None


# ============================================================
# 手机号短信认证域
# ============================================================

class TestSmsSendValidation:
    """POST /auth/sms/send 手机号格式校验"""

    def test_invalid_phone_short(self, client):
        """短号码返回 400"""
        resp = client.post("/auth/sms/send", json={"phone": "12345"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_invalid_phone_format(self, client):
        """非手机号格式返回 400"""
        resp = client.post("/auth/sms/send", json={"phone": "abcdefghijk"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_missing_phone_field(self, client):
        """缺少 phone 字段返回 422"""
        resp = client.post("/auth/sms/send", json={})
        assert resp.status_code == 422


class TestSmsVerifyValidation:
    """POST /auth/sms/verify 验证码校验"""

    def test_invalid_phone_returns_400(self, client):
        """手机号格式错误返回 400"""
        resp = client.post("/auth/sms/verify", json={"phone": "123", "code": "123456"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_empty_code_returns_400(self, client):
        """验证码为空返回 400"""
        resp = client.post("/auth/sms/verify", json={"phone": "13312343103", "code": ""})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_missing_fields_returns_422(self, client):
        """缺少必填字段返回 422"""
        resp = client.post("/auth/sms/verify", json={"phone": "13312343103"})
        assert resp.status_code == 422


class TestSmsSendHappyPath:
    """POST /auth/sms/send 有效号码发送路径

    回归背景：短信服务改为云端代理模式后，需确保代理返回成功时正确传递结果，
    代理返回失败时正确抛出错误而非 500。
    """

    def test_valid_phone_returns_success(self, client, monkeypatch):
        """有效手机号且代理返回 success=True 时应成功"""
        from core import sms

        # 隔离频率限制与真实网络调用
        monkeypatch.setattr(sms, "_sms_rate_limits", {})
        monkeypatch.setattr(sms, "_proxy_request", lambda path, payload: {
            "success": True,
            "expire_minutes": 5,
        })

        resp = client.post("/auth/sms/send", json={"phone": "13312343103"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["expire_minutes"] == 5

    def test_proxy_error_returns_400_json(self, client, monkeypatch):
        """代理返回 success=False 时应转为 400 JSON，而非 500"""
        from core import sms

        monkeypatch.setattr(sms, "_sms_rate_limits", {})
        monkeypatch.setattr(sms, "_proxy_request", lambda path, payload: {
            "success": False,
            "message": "模板不合法",
        })

        resp = client.post("/auth/sms/send", json={"phone": "13312343103"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "模板不合法" in data["message"]


class TestSmsCheckVerifyCode:
    """core.sms.check_verify_code 代理模式核验结果解析

    回归背景：短信服务改为云端代理后，核验结果由代理返回，
    需确保 success=true/false 正确映射为通过/失败。
    """

    def _patch_proxy(self, monkeypatch, *, success=True, message=""):
        from core import sms

        def fake_proxy(path, payload):
            return {"success": success, "message": message}

        monkeypatch.setattr(sms, "_proxy_request", fake_proxy)
        return sms

    def test_proxy_success_returns_true(self, monkeypatch):
        """代理返回 success=True 应判定核验通过"""
        sms = self._patch_proxy(monkeypatch, success=True)
        passed, reason = sms.check_verify_code("13312343103", "123456")
        assert passed is True
        assert reason == ""

    def test_proxy_failure_returns_false(self, monkeypatch):
        """代理返回 success=False 应判定核验失败"""
        sms = self._patch_proxy(monkeypatch, success=False, message="验证码错误或已过期")
        passed, reason = sms.check_verify_code("13312343103", "000000")
        assert passed is False
        assert reason == "验证码错误或已过期"

    def test_proxy_connection_error_returns_service_error(self, monkeypatch):
        """代理连接失败应视为服务异常，而非核验失败"""
        from core import sms

        def fake_proxy(path, payload):
            raise RuntimeError("短信代理连接失败: Connection refused")

        monkeypatch.setattr(sms, "_proxy_request", fake_proxy)
        passed, reason = sms.check_verify_code("13312343103", "123456")
        assert passed is False
        assert reason == "验证服务异常，请稍后重试"


# ============================================================
# 认证路由（auth）
# ============================================================

class TestAuthGithubLogin:
    """GET /auth/github 重定向到 GitHub 授权页"""

    def test_redirects_to_github(self, client):
        resp = client.get("/auth/github", follow_redirects=False)
        assert resp.status_code in (302, 307)
        location = resp.headers.get("location", "")
        assert "github.com" in location or "authorize" in location


class TestAuthMeNotLoggedIn:
    """GET /auth/me 未登录时返回 401"""

    def test_me_unauthorized(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401


class TestAuthLogout:
    """POST /auth/logout 正常返回"""

    def test_logout_ok(self, client):
        resp = client.post("/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data


class TestAuthCallbackMissingCode:
    """GET /auth/callback 缺少 code 参数时返回 400"""

    def test_callback_no_code(self, client):
        resp = client.get("/auth/callback?state=fake-state")
        assert resp.status_code == 400


# ============================================================
# AI 对话路由（chat）
# ============================================================

class TestChatEmptyMessage:
    """POST /api/chat 空消息返回 400"""

    def test_empty_message_rejected(self, client):
        resp = client.post("/api/chat", json={"message": "   "})
        assert resp.status_code == 400


class TestChatMissingMessage:
    """POST /api/chat 缺少 message 字段返回 422"""

    def test_missing_message_field(self, client):
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 422


class TestListModels:
    """GET /api/models 返回模型列表"""

    def test_models_ok(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0


class TestOptimizeEmptyText:
    """POST /api/optimize 空文本返回 400"""

    def test_empty_text_rejected(self, client):
        resp = client.post("/api/optimize", json={"text": "   "})
        assert resp.status_code == 400


# ============================================================
# AI 页面上下文感知（current_page）
# ============================================================

class TestBuildPageContext:
    """_build_page_context 根据页面名返回差异化上下文"""

    def test_start_page(self):
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("start")
        assert ctx is not None
        assert "首页" in ctx

    def test_speakers_page_returns_list_or_empty(self):
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("speakers")
        assert ctx is not None
        assert "说话人" in ctx

    def test_hotwords_page_returns_list_or_empty(self):
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("hotwords")
        assert ctx is not None
        assert "热词" in ctx

    def test_settings_page(self):
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("settings")
        assert ctx is not None
        assert "设置" in ctx

    def test_projects_page(self):
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("projects")
        assert ctx is not None
        assert "项目" in ctx

    def test_library_page(self):
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("library")
        assert ctx is not None
        assert "会议" in ctx

    def test_generating_page_returns_none(self):
        """纪要页由 task 上下文覆盖，无需额外页面上下文"""
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("generating")
        assert ctx is None

    def test_unknown_page_returns_none(self):
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("nonexistent_page")
        assert ctx is None


class TestChatWithCurrentPage:
    """POST /api/chat 传入 current_page 不报错"""

    def test_chat_with_page_field_accepted(self, client, monkeypatch):
        """current_page 字段被接受，端点不 500"""
        calls = {"n": 0}

        async def fake_llm(messages, **kwargs):
            calls["n"] += 1
            return "你好，我在首页可以帮你开始录音或上传音频。"

        from app.routers import chat as chat_mod
        monkeypatch.setattr(chat_mod, "async_chat_completion", fake_llm)

        resp = client.post("/api/chat", json={
            "message": "我能做什么",
            "current_page": "start",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data


# ============================================================
# 版本更新路由（update）
# ============================================================

class TestUpdateVersion:
    """GET /api/update/version 返回版本号"""

    def test_version_ok(self, client):
        resp = client.get("/api/update/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


class TestUpdateCheck:
    """GET /api/update/check 返回更新检查结果"""

    def test_check_ok(self, client):
        resp = client.get("/api/update/check")
        assert resp.status_code == 200
        data = resp.json()
        # 网络不可达时静默降级，但端点本身不 500
        assert isinstance(data, dict)


# ============================================================
# 用量查询路由（usage）
# ============================================================

class TestUsageSummary:
    """GET /api/usage/summary 返回用量汇总"""

    def test_summary_ok(self, client):
        resp = client.get("/api/usage/summary")
        assert resp.status_code == 200
        data = resp.json()
        # 未登录时返回 metered=False 或提示信息
        assert isinstance(data, dict)


class TestUsageHistory:
    """GET /api/usage/history 返回用量明细"""

    def test_history_ok(self, client):
        resp = client.get("/api/usage/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert isinstance(data["history"], (list, dict))


class TestUsageCheck:
    """GET /api/usage/check 配额预检"""

    def test_quota_check_ok(self, client):
        resp = client.get("/api/usage/check")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ============================================================
# 管理后台路由（admin）
# 注意：admin router 注册在独立的 admin_app 上（端口 8001），
# 不在主 app 上，因此需要创建独立的测试客户端。
# ============================================================

@pytest.fixture
def admin_client():
    """创建管理后台测试客户端"""
    from app.admin_server import admin_app
    with TestClient(admin_app) as c:
        yield c


class TestAdminLoginNoPassword:
    """POST /api/admin/login 未配置密码时返回 500"""

    def test_login_no_password_configured(self, admin_client, monkeypatch):
        from app.routers import admin as admin_mod
        monkeypatch.setattr(admin_mod, "ADMIN_PASSWORD", "")
        resp = admin_client.post("/api/admin/login", json={"password": "test"})
        assert resp.status_code == 500


class TestAdminLoginWrongPassword:
    """POST /api/admin/login 密码错误返回 401"""

    def test_wrong_password(self, admin_client, monkeypatch):
        from app.routers import admin as admin_mod
        monkeypatch.setattr(admin_mod, "ADMIN_PASSWORD", "correct-password")
        resp = admin_client.post("/api/admin/login", json={"password": "wrong-password"})
        assert resp.status_code == 401


class TestAdminMeUnauthorized:
    """GET /api/admin/me 未认证返回 401"""

    def test_me_unauthorized(self, admin_client):
        resp = admin_client.get("/api/admin/me")
        assert resp.status_code == 401


class TestAdminOverviewUnauthorized:
    """GET /api/admin/overview 未认证返回 401"""

    def test_overview_unauthorized(self, admin_client):
        resp = admin_client.get("/api/admin/overview")
        assert resp.status_code == 401


class TestAdminLogout:
    """POST /api/admin/logout 正常返回"""

    def test_logout_ok(self, admin_client):
        resp = admin_client.post("/api/admin/logout")
        assert resp.status_code == 200


# ============================================================
# 远程配置路由（config）
# ============================================================

class TestConfigAnnouncements:
    """GET /api/config/announcements 返回公告列表"""

    def test_announcements_ok(self, client):
        resp = client.get("/api/config/announcements")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert isinstance(data["messages"], list)


class TestConfigVersion:
    """GET /api/config/version 返回配置版本号"""

    def test_config_version_ok(self, client):
        resp = client.get("/api/config/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data


# ============================================================
# 理念传播路由（philosophy）
# ============================================================

class TestPhilosophyRandom:
    """GET /api/philosophy/random 返回随机理念"""

    def test_random_ok(self, client):
        resp = client.get("/api/philosophy/random")
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert isinstance(data["text"], str)


# ============================================================
# 文本桥接匹配（core/text_bridge.py）
# ============================================================

class TestNormalizeText:
    """_normalize_text 去除空白字符"""

    def test_remove_spaces(self):
        from core.text_bridge import _normalize_text
        assert _normalize_text("hello world") == "helloworld"
        assert _normalize_text("  你好  世界  ") == "你好世界"

    def test_empty_string(self):
        from core.text_bridge import _normalize_text
        assert _normalize_text("") == ""
        assert _normalize_text("   ") == ""


class TestTextSimilarity:
    """_text_similarity 文本相似度计算"""

    def test_exact_match(self):
        from core.text_bridge import _text_similarity
        assert _text_similarity("完全相同的文本", "完全相同的文本") == 1.0

    def test_high_similarity(self):
        from core.text_bridge import _text_similarity
        # 仅差一两个字
        sim = _text_similarity("今天讨论预算方案", "今天讨论预算方案吧")
        assert sim > 0.75

    def test_low_similarity(self):
        from core.text_bridge import _text_similarity
        sim = _text_similarity("今天天气很好", "股票市场大跌")
        assert sim < 0.5

    def test_empty_input(self):
        from core.text_bridge import _text_similarity
        assert _text_similarity("", "有内容") == 0.0
        assert _text_similarity("有内容", "") == 0.0
        assert _text_similarity("", "") == 0.0

    def test_length_ratio_filter(self):
        from core.text_bridge import _text_similarity
        # 长度差异超过 70% 时直接返回 0
        sim = _text_similarity("abc", "这是一段非常长的中文文本内容")
        assert sim == 0.0


class TestTextBridgeMatch:
    """text_bridge_match 核心匹配逻辑"""

    def _make_realtime(self, speaker_id, texts):
        """构造实时全量转写记录"""
        return [{"speaker_id": speaker_id, "text": t, "begin_time": i * 1000, "end_time": (i + 1) * 1000}
                for i, t in enumerate(texts)]

    def _make_dialogue(self, mappings):
        """构造批处理对话稿。mappings: {speaker_id: [text, ...]}"""
        dialogue = []
        for sid, texts in mappings.items():
            sentences = [{"text": t, "begin_time": i * 1000, "end_time": (i + 1) * 1000}
                         for i, t in enumerate(texts)]
            dialogue.append({"speaker_id": sid, "sentences": sentences})
        return dialogue

    def test_empty_inputs(self):
        from core.text_bridge import text_bridge_match
        results, mapping = text_bridge_match([], {}, [])
        assert results == [] and mapping == {}

    def test_no_bindings(self):
        from core.text_bridge import text_bridge_match
        rt = self._make_realtime(0, ["测试文本内容"])
        results, mapping = text_bridge_match(rt, {}, self._make_dialogue({0: ["测试文本内容"]}))
        assert results == [] and mapping == {}

    def test_perfect_match(self):
        """实时文本与批处理文本完全一致时正确匹配"""
        from core.text_bridge import text_bridge_match
        rt = self._make_realtime(0, ["讨论预算方案", "确认实施计划"])
        dialogue = self._make_dialogue({
            5: ["讨论预算方案", "其他内容"],
            6: ["无关话题"],
        })
        binding = {"0": "uuid-alice"}
        names = {"uuid-alice": "张三"}

        results, mapping = text_bridge_match(rt, binding, dialogue, names)
        assert len(results) == 1
        assert results[0].status == "matched"
        assert results[0].new_speaker_id == 5
        assert results[0].speaker_name == "张三"
        assert mapping[5] == "uuid-alice"

    def test_multiple_speakers_voting(self):
        """多位说话人各自独立匹配"""
        from core.text_bridge import text_bridge_match
        rt = (
            self._make_realtime(0, ["讨论预算方案", "确认实施计划", "审核财务报表"])
            + self._make_realtime(1, ["市场推广策略", "用户增长方案"])
        )
        dialogue = self._make_dialogue({
            3: ["讨论预算方案", "确认实施计划", "审核财务报表"],
            4: ["市场推广策略", "用户增长方案"],
        })
        binding = {"0": "uuid-alice", "1": "uuid-bob"}

        results, mapping = text_bridge_match(rt, binding, dialogue)
        assert len(results) == 2
        matched = [r for r in results if r.status == "matched"]
        assert len(matched) == 2
        assert mapping.get(3) == "uuid-alice"
        assert mapping.get(4) == "uuid-bob"

    def test_no_match_when_texts_differ(self):
        """实时文本与批处理文本完全不同时无匹配"""
        from core.text_bridge import text_bridge_match
        rt = self._make_realtime(0, ["今天天气很好"])
        dialogue = self._make_dialogue({0: ["股票市场大跌"]})
        binding = {"0": "uuid-alice"}

        results, mapping = text_bridge_match(rt, binding, dialogue)
        assert len(results) == 1
        assert results[0].status == "unmatched"
        assert mapping == {}

    def test_short_text_filtered(self):
        """过短的文本（< MIN_TEXT_LENGTH）被过滤不参与匹配"""
        from core.text_bridge import text_bridge_match
        rt = self._make_realtime(0, ["好", "嗯"])
        dialogue = self._make_dialogue({0: ["好", "嗯"]})
        binding = {"0": "uuid-alice"}

        results, mapping = text_bridge_match(rt, binding, dialogue)
        # 所有文本都短于 MIN_TEXT_LENGTH=4，无有效文本
        assert results == [] and mapping == {}

    def test_to_dict_output(self):
        """TextBridgeMatchResult.to_dict() 输出格式正确"""
        from core.text_bridge import TextBridgeMatchResult
        result = TextBridgeMatchResult(
            old_speaker_id=0,
            speaker_uuid="uuid-test",
            speaker_name="测试人",
            new_speaker_id=3,
            confidence=0.8567,
            hit_count=5,
            best_similarity=0.9234,
            status="matched",
        )
        d = result.to_dict()
        assert d["confidence"] == 0.857  # 四舍五入到 3 位
        assert d["best_similarity"] == 0.923
        assert d["status"] == "matched"
        assert d["new_speaker_id"] == 3


# ============================================================
# 动作检测关键词误命中回归（chat.py _detect_action）
# ============================================================

class TestDetectActionFalsePositive:
    """_detect_action 不应被「结论」等短词误触发 summarize_conclusions"""

    def test_generate_minutes_with_conclusion_not_triggered(self):
        """用户说「生成会议纪要包含结论」不应命中 summarize_conclusions"""
        from app.routers.chat import _detect_action
        result = _detect_action("请根据当前会议内容生成一份结构化会议纪要，包含议题、讨论要点和结论。")
        # 不应命中 summarize_conclusions（可能命中其他动作或返回 None）
        if result is not None:
            assert result.name != "summarize_conclusions"

    def test_explicit_conclusion_request_still_works(self):
        """明确请求「总结关键结论」仍应命中 summarize_conclusions"""
        from app.routers.chat import _detect_action
        result = _detect_action("请总结关键结论")
        assert result is not None
        assert result.name == "summarize_conclusions"

    def test_key_conclusion_still_works(self):
        """「关键结论」仍应命中 summarize_conclusions"""
        from app.routers.chat import _detect_action
        result = _detect_action("帮我整理一下关键结论")
        assert result is not None
        assert result.name == "summarize_conclusions"

    def test_bare_conclusion_not_triggered(self):
        """单独说「结论」不再触发 summarize_conclusions（避免误命中）"""
        from app.routers.chat import _detect_action
        result = _detect_action("结论")
        # 不再被短词「结论」触发
        if result is not None:
            assert result.name != "summarize_conclusions"


# ============================================================
# 输入校验边界测试
# ============================================================

class TestInputValidationSpeaker:
    """说话人名称长度限制"""

    def test_speaker_name_too_long(self, client):
        """名称超过 100 字返回 422"""
        resp = client.post("/api/speakers", json={"name": "A" * 101})
        assert resp.status_code == 422

    def test_speaker_name_empty_string(self, client):
        """空字符串名称返回 400（业务层校验）"""
        resp = client.post("/api/speakers", json={"name": ""})
        assert resp.status_code in (400, 422)


class TestInputValidationHotwords:
    """热词接口 Pydantic 模型校验"""

    def test_hotwords_save_accepts_valid_input(self, client):
        """正常热词保存应成功"""
        resp = client.post("/api/hotwords", json={"hotwords": "热词A\n热词B"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_hotwords_save_rejects_oversized_input(self, client):
        """超大文本应被 Pydantic 拒绝（422）"""
        resp = client.post("/api/hotwords", json={"hotwords": "A" * 50001})
        assert resp.status_code == 422


# ============================================================
# 静默检测配置
# ============================================================

class TestSilenceDetectionConfig:
    """静默检测配置加载"""

    def test_get_silence_detection_config_returns_defaults(self):
        """get_silence_detection_config() 应返回完整默认配置"""
        from app.store import get_silence_detection_config
        config = get_silence_detection_config()
        assert config["enabled"] is True
        assert "presence" in config
        assert "audio" in config
        assert "action" in config
        # 存在性评分参数
        assert config["presence"]["score_max"] == 100
        assert config["presence"]["heartbeat_timeout_sec"] == 90
        assert config["presence"]["threshold_warning"] == 20
        # 音频层参数
        assert config["audio"]["asr_no_sentence_timeout_sec"] == 300
        # 动作参数
        assert config["action"]["gentle_countdown_sec"] == 120
        assert config["action"]["urgent_countdown_sec"] == 60
        assert config["action"]["max_warnings_per_session"] == 2

    def test_silence_detection_state_dicts_exist(self):
        """静默检测状态字典应已初始化"""
        from app.store import (
            realtime_last_heartbeat, realtime_last_sentence,
            realtime_presence_scores, realtime_silence_warnings,
            realtime_silence_monitors,
        )
        assert isinstance(realtime_last_heartbeat, dict)
        assert isinstance(realtime_last_sentence, dict)
        assert isinstance(realtime_presence_scores, dict)
        assert isinstance(realtime_silence_warnings, dict)
        assert isinstance(realtime_silence_monitors, dict)
