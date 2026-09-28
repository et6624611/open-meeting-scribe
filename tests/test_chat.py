"""
tests/test_chat.py — AI 对话域冒烟测试

覆盖对话端点、编辑校验、作业日志、待办提取、页面上下文、动作检测等。
从 test_smoke.py 拆分而来。

运行方式：
  pytest tests/test_chat.py -v
"""

import pytest
from fastapi.testclient import TestClient

import app.settings_store as settings_store
from app.server import app


@pytest.fixture(autouse=True)
def _isolate_settings_file(tmp_path, monkeypatch):
    """DEF-RETEST-01/02 加固：chat 端点下沉调用 core.llm，其 provider/base_url/key
    来自 settings.json 回填（优先级高于环境变量）。本机 data/settings.json 若残留
    localhost 配置（如 Ollama 占位 Key），未 mock 的 async_chat_completion_full
    会真实触网并 404 → 503，使用例结果依赖实测机配置而非被测逻辑。此处把
    SETTINGS_FILE 指向不存在的临时路径并前置清除环境变量（先于 client fixture
    的 app 启动），使本域用例与本机配置彻底解耦；走默认云端代理（离线桩链路）。
    """
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "isolated-settings.json")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)


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

    def test_generating_page_context(self):
        """纪要页提示可结合洞察台结论作答（REQ-INSIGHT-DECK-POSTMEETING R3）"""
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("generating")
        assert ctx is not None
        assert "纪要" in ctx
        assert "洞察台" in ctx

    def test_unknown_page_returns_none(self):
        from app.routers.chat import _build_page_context
        ctx = _build_page_context("nonexistent_page")
        assert ctx is None


class TestBuildInsightsContextBlock:
    """洞察台注入块：三态行为、条数/字符上限、phase 标注（REQ-INSIGHT-DECK-POSTMEETING R3）"""

    def _write_insights(self, tmp_path, monkeypatch, messages):
        import json

        import core.chat_context as chat_context
        monkeypatch.setattr(chat_context, "INSIGHTS_TASKS_DIR", tmp_path)
        (tmp_path / "t1.insights.json").write_text(
            json.dumps({"messages": messages}, ensure_ascii=False), encoding="utf-8")
        return chat_context

    def test_no_file_returns_none(self, tmp_path, monkeypatch):
        import core.chat_context as chat_context
        monkeypatch.setattr(chat_context, "INSIGHTS_TASKS_DIR", tmp_path)
        assert chat_context.build_insights_context_block("missing-id") is None
        assert chat_context.build_insights_context_block(None) is None

    def test_empty_messages_returns_none(self, tmp_path, monkeypatch):
        cc = self._write_insights(tmp_path, monkeypatch, [])
        assert cc.build_insights_context_block("t1") is None

    def test_block_content_and_phase(self, tmp_path, monkeypatch):
        cc = self._write_insights(tmp_path, monkeypatch, [
            {"title": "会中发现", "body": "讨论缺口", "solution": "补人", "diagram": "flowchart LR", "phase": "meeting"},
            {"title": "会后发现", "body": "资源冲突", "phase": "post_meeting"},
        ])
        block = cc.build_insights_context_block("t1")
        assert block is not None
        assert "会议洞察台" in block
        assert "[会中] 会中发现" in block
        assert "[会后] 会后发现" in block
        assert "（该洞察附决策流图）" in block
        # diagram 源码不整段注入
        assert "flowchart LR" not in block

    def test_caps_items_at_five(self, tmp_path, monkeypatch):
        msgs = [{"title": f"洞察{i}", "body": "短内容", "phase": "meeting"} for i in range(9)]
        cc = self._write_insights(tmp_path, monkeypatch, msgs)
        block = cc.build_insights_context_block("t1")
        # 取最近 5 条：洞察4–洞察8 在，洞察3 及之前不在
        assert "洞察8" in block
        assert "洞察4" in block
        assert "洞察3" not in block
        assert block.count("- [会中]") == 5


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


# ============================================================
# 决策链待办 API
# ============================================================

class TestDecisionFlowTodos:
    """决策流待办端点:字段透传、create 默认值、status↔done 同步"""

    @pytest.fixture
    def task_id(self, monkeypatch):
        import uuid

        from app.routers import notes as notes_mod
        # 避免测试写入磁盘 / Prevent disk writes during tests
        monkeypatch.setattr(notes_mod, "save_task_to_disk", lambda *_a, **_k: None)
        tid = str(uuid.uuid4())
        notes_mod.tasks[tid] = {"task_id": tid, "status": "completed", "todos": []}
        yield tid
        notes_mod.tasks.pop(tid, None)

    def test_create_todo_defaults(self, client, task_id):
        """新建决策节点应带默认 status/how/owner_type"""
        resp = client.post(f"/api/tasks/{task_id}/todos", json={"text": "采用云方案", "assignee": "张三"})
        assert resp.status_code == 200
        todo = resp.json()["todo"]
        assert todo["status"] == "to_decide"
        assert todo["how"] == ["采用云方案"]
        assert todo["owner_type"] == "self"
        assert todo["done"] is False

    def test_update_passes_through_decision_fields(self, client, task_id):
        """update 应透传 why/how/outcome/owner_type 并落库"""
        todo_id = client.post(f"/api/tasks/{task_id}/todos", json={"text": "数据迁移"}).json()["todo"]["id"]
        resp = client.put(f"/api/tasks/{task_id}/todos/{todo_id}", json={
            "why": "旧库无法支撑新模型",
            "how": ["导出", "映射", "校验"],
            "outcome": "减少 30% 对账工时",
            "owner_type": "colleague",
        })
        assert resp.status_code == 200
        todo = resp.json()["todo"]
        assert todo["why"] == "旧库无法支撑新模型"
        assert todo["how"] == ["导出", "映射", "校验"]
        assert todo["outcome"] == "减少 30% 对账工时"
        assert todo["owner_type"] == "colleague"

    def test_update_how_strips_blank_items(self, client, task_id):
        """how 应剔除空白步骤"""
        todo_id = client.post(f"/api/tasks/{task_id}/todos", json={"text": "x"}).json()["todo"]["id"]
        todo = client.put(f"/api/tasks/{task_id}/todos/{todo_id}", json={"how": ["a", "  ", "b", ""]}).json()["todo"]
        assert todo["how"] == ["a", "b"]

    def test_status_done_syncs_done_true(self, client, task_id):
        """status='done' 应同步 done=True"""
        todo_id = client.post(f"/api/tasks/{task_id}/todos", json={"text": "x"}).json()["todo"]["id"]
        todo = client.put(f"/api/tasks/{task_id}/todos/{todo_id}", json={"status": "done"}).json()["todo"]
        assert todo["status"] == "done"
        assert todo["done"] is True

    def test_status_in_progress_syncs_done_false(self, client, task_id):
        """从 done 回到 in_progress 应同步 done=False"""
        todo_id = client.post(f"/api/tasks/{task_id}/todos", json={"text": "x"}).json()["todo"]["id"]
        client.put(f"/api/tasks/{task_id}/todos/{todo_id}", json={"status": "done"})
        todo = client.put(f"/api/tasks/{task_id}/todos/{todo_id}", json={"status": "in_progress"}).json()["todo"]
        assert todo["status"] == "in_progress"
        assert todo["done"] is False

    def test_toggle_syncs_status(self, client, task_id):
        """toggle 完成态应同步 status"""
        todo_id = client.post(f"/api/tasks/{task_id}/todos", json={"text": "x"}).json()["todo"]["id"]
        todo = client.post(f"/api/tasks/{task_id}/todos/{todo_id}/toggle", json={"done": True}).json()["todo"]
        assert todo["done"] is True and todo["status"] == "done"
        todo = client.post(f"/api/tasks/{task_id}/todos/{todo_id}/toggle", json={"done": False}).json()["todo"]
        # DC-UNIFY-01：取消勾选回到状态字典的首个开放态（不再写死 in_progress）
        assert todo["done"] is False and todo["status"] == "to_decide"

    def test_invalid_status_rejected(self, client, task_id):
        """非法 status 应被拒绝(422)"""
        todo_id = client.post(f"/api/tasks/{task_id}/todos", json={"text": "x"}).json()["todo"]["id"]
        resp = client.put(f"/api/tasks/{task_id}/todos/{todo_id}", json={"status": "not_a_status"})
        assert resp.status_code == 422
