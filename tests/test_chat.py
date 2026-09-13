"""
tests/test_chat.py — AI 对话域冒烟测试

覆盖对话端点、编辑校验、作业日志、待办提取、页面上下文、动作检测等。
从 test_smoke.py 拆分而来。

运行方式：
  pytest tests/test_chat.py -v
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
# 作业日志
# ============================================================

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

        from app import task_store
        from app.routers import chat as chat_mod
        from core import chat_edits
        fake_tasks = {task_id: self._make_task(task_id)}
        monkeypatch.setattr(task_store, "tasks", fake_tasks)
        monkeypatch.setattr(chat_mod, "tasks", fake_tasks)
        monkeypatch.setattr(chat_edits, "tasks", fake_tasks)
        monkeypatch.setattr(task_store, "TASKS_DIR", tmp_path)
        monkeypatch.setattr(chat_mod, "TASKS_DIR", tmp_path)
        monkeypatch.setattr(chat_edits, "TASKS_DIR", tmp_path)
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
