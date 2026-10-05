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
    # 逐能力真相源：预置 LLM/ASR 来源=trial，使 chat 走默认云端代理桩链路（否则未设置会拦截）。
    settings_store.save_settings_to_disk({"capability_source": {"llm": "trial", "asr": "trial"}})


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
- [ ] **陈一**：完成数据迁移方案
- [ ] **刘二**：跟进服务器部署问题
"""
        todos = parse_todos_from_summary(summary)
        assert len(todos) == 2
        assert todos[0]["assignee"] == "陈一"
        assert todos[0]["text"] == "完成数据迁移方案"
        assert todos[0]["done"] is False
        assert todos[0]["source"] == "auto"
        assert todos[1]["assignee"] == "刘二"

    def test_with_deadline(self):
        from core.summarize import parse_todos_from_summary
        summary = "- [ ] **王三**：提交季度报告（9月10日）"
        todos = parse_todos_from_summary(summary)
        assert len(todos) == 1
        assert todos[0]["text"] == "提交季度报告"
        assert todos[0]["assignee"] == "王三"
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
        summary = "- [ ] **陈一**：完成数据迁移方案\n- [ ] **陈一**：完成数据迁移方案"
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
                {"id": "t1", "text": "梳理会计事件库案例", "assignee": "赵甲", "done": False},
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
        ops = [{"op": "todo_assignee", "todo_id": "t1", "value": "钱乙"}]
        changes = chat_mod._execute_and_verify_edits("unit-edit-0001", ops)
        assert len(changes) == 1
        assert changes[0]["verified"] is True
        assert changes[0]["old"] == "赵甲" and changes[0]["new"] == "钱乙"
        disk = json.loads((tmp_path / "unit-edit-0001.json").read_text(encoding="utf-8"))
        assert disk["todos"][0]["assignee"] == "钱乙"

    def test_execute_and_verify_delete(self, tmp_path, monkeypatch):
        chat_mod, json = self._patch_storage(monkeypatch, tmp_path, "unit-edit-0002")
        changes = chat_mod._execute_and_verify_edits("unit-edit-0002", [{"op": "todo_delete", "todo_id": "t2"}])
        assert len(changes) == 1 and changes[0]["verified"] is True
        disk = json.loads((tmp_path / "unit-edit-0002.json").read_text(encoding="utf-8"))
        assert [t["id"] for t in disk["todos"]] == ["t1"]

    def test_noop_produces_no_changes(self, tmp_path, monkeypatch):
        chat_mod, _ = self._patch_storage(monkeypatch, tmp_path, "unit-edit-0003")
        ops = [{"op": "todo_assignee", "todo_id": "t1", "value": "赵甲"}]
        assert chat_mod._execute_and_verify_edits("unit-edit-0003", ops) == []

    def test_sanitize_ops_whitelist(self):
        from app.routers import chat as chat_mod
        raw = '```json\n{"ops": [{"op": "todo_assignee", "todo_id": "t1", "value": "钱乙"},' \
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
                    "old": "赵甲", "new": "钱乙", "verified": True}]
        audited = chat_mod._audit_reply_claims("好的。", changes)
        assert "系统校验" in audited and "钱乙" in audited and "校验通过" in audited
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
                return '{"ops": [{"op": "todo_assignee", "todo_id": "t1", "value": "钱乙"}]}'
            return "相关待办责任人改为钱乙。"

        monkeypatch.setattr(chat_mod, "async_chat_completion", fake_llm)
        resp = client.post("/api/chat", json={"message": "待办中赵甲应该是钱乙", "task_id": "unit-edit-0004"})
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


class TestAgentSystemPromptInsightContract:
    """智能体系统提示词必须全程携带角色的洞察板解法契约（insights.md），
    不依赖模型是否决定调用 revise_insight_board。"""

    def test_default_role_includes_insight_board_contract(self):
        from app.routers.chat import _agent_system_prompt
        prompt = _agent_system_prompt(None)  # 默认角色 meeting-minutes
        # 来自 AGENT.md
        assert "AI 会议助手" in prompt
        # 来自 insights.md 的解法契约关键锚点
        assert "会上没人想到" in prompt
        assert "禁止入板" in prompt or "一律不写进洞察板" in prompt
        assert "board_is_recap" in prompt

    def test_unknown_role_falls_back_without_insight_contract(self):
        from app.routers.chat import CHAT_SYSTEM_PROMPT, _agent_system_prompt
        prompt = _agent_system_prompt("role-that-does-not-exist-xyz")
        assert prompt == CHAT_SYSTEM_PROMPT
        assert "board_is_recap" not in prompt

    def test_qa_prompt_does_not_carry_board_contract(self):
        # 问答模式无工具调用权，不承载洞察板写板职责
        from app.routers.chat import CHAT_QA_SYSTEM_PROMPT
        assert "board_is_recap" not in CHAT_QA_SYSTEM_PROMPT


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
# 会话自动命名（/api/chat/title）
# ============================================================

class TestChatTitle:
    """POST /api/chat/title：生成 + 清洗 + 失败静默降级"""

    def test_sanitize_strips_quotes_and_punct(self):
        from app.routers.chat import _sanitize_chat_title
        assert _sanitize_chat_title('"项目排期讨论"。') == "项目排期讨论"
        assert _sanitize_chat_title("《预算评审》\n第二行忽略") == "预算评审"
        assert _sanitize_chat_title("   ") == ""
        assert _sanitize_chat_title("") == ""
        assert _sanitize_chat_title("这是一个非常非常非常非常长的会话标题超出限制") == "这是一个非常非常非常非常长的会话标题超出"

    def test_title_ok(self, client, monkeypatch):
        import app.routers.chat as chat_mod

        async def fake_llm(messages, **kwargs):
            return '"待办核对与责任人确认"'

        monkeypatch.setattr(chat_mod, "async_chat_completion", fake_llm)
        resp = client.post("/api/chat/title", json={
            "first_message": "帮我把待办里的责任人核对一下",
            "reply": "已核对，共 3 处不一致……",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["title"] == "待办核对与责任人确认"

    def test_title_llm_failure_degrades_silently(self, client, monkeypatch):
        import app.routers.chat as chat_mod

        async def boom(messages, **kwargs):
            raise RuntimeError("llm down")

        monkeypatch.setattr(chat_mod, "async_chat_completion", boom)
        resp = client.post("/api/chat/title", json={"first_message": "总结一下会议"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["title"] == ""

    def test_empty_first_message_rejected(self, client):
        resp = client.post("/api/chat/title", json={"first_message": "  "})
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
        resp = client.post(f"/api/tasks/{task_id}/todos", json={"text": "采用云方案", "assignee": "陈一"})
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


# ============================================================
# @ 引用令牌（用户显式引用，升级替换自动采样口径）
# ============================================================

class TestMentionContext:
    """@原文/@纪要/@随记 令牌：全量显式块注入、升级替换采样块、缺失说明块、无令牌回归"""

    @staticmethod
    def _make_task(dialogue=None, summary=None, notes=None):
        task = {"title": "测试会议", "status": "completed"}
        if dialogue is not None:
            task["dialogue"] = dialogue
        if summary is not None:
            task["summary"] = summary
        if notes is not None:
            task["user_notes"] = notes
        return task

    @staticmethod
    def _build(message, task=None, realtime=None, monkeypatch=None):
        import app.routers.chat as chat_mod
        from app.routers.chat import ChatRequest, _build_chat_context_blocks
        if monkeypatch is not None:
            if task is not None:
                monkeypatch.setitem(chat_mod.tasks, "t1", task)
            else:
                monkeypatch.delitem(chat_mod.tasks, "t1", raising=False)
            if realtime is not None:
                monkeypatch.setitem(chat_mod.realtime_transcript_buffers, "t1", realtime)
            else:
                monkeypatch.delitem(chat_mod.realtime_transcript_buffers, "t1", raising=False)
        data = ChatRequest(message=message, task_id="t1" if (task is not None or realtime is not None) else None)
        return _build_chat_context_blocks(data, is_qa_mode=True)[0]

    def test_scan_tokens(self):
        from app.routers.chat import _scan_mention_tokens
        assert _scan_mention_tokens("@原文 谁说的") == {"@原文"}
        assert _scan_mention_tokens("对比 @纪要 和 @随记") == {"@纪要", "@随记"}
        # 英文环境令牌别名：归一为中文令牌（大小写不敏感）
        assert _scan_mention_tokens("@transcript who said that") == {"@原文"}
        assert _scan_mention_tokens("Compare @Summary and @NOTES") == {"@纪要", "@随记"}
        # 边界：@ 前无空白/行首不触发（与前端词边界规则一致）
        assert _scan_mention_tokens("邮箱是a@原文.com") == set()
        assert _scan_mention_tokens("mail me at a@transcript.com") == set()
        # 残缺令牌忽略
        assert _scan_mention_tokens("看 @原 这段") == set()
        assert _scan_mention_tokens("see @tran") == set()

    def test_transcript_full_replaces_sampling(self, monkeypatch):
        dialogue = [
            {"speaker_name": "陈一", "sentences": [{"text": "第一句关于预算", "begin_time": 1000}]},
            {"speaker_name": "刘二", "sentences": [{"text": "第二句关于排期", "begin_time": 2000}]},
            {"speaker_name": "陈一", "sentences": [{"text": "第三句关于验收", "begin_time": 3000}]},
        ]
        blocks = self._build("@原文 预算是谁提的", task=self._make_task(dialogue=dialogue, summary="纪要"), monkeypatch=monkeypatch)
        full = [b for b in blocks if b.startswith("## 用户显式引用（@原文）")]
        assert len(full) == 1
        assert "第一句关于预算" in full[0] and "第二句关于排期" in full[0] and "第三句关于验收" in full[0]
        # 升级替换：采样时间轴块不得同时出现
        assert not any("智能采样" in b for b in blocks)

    def test_transcript_cap_truncates(self, monkeypatch):
        from app.routers.chat import MENTION_TRANSCRIPT_CAP
        long_text = "长" * (MENTION_TRANSCRIPT_CAP + 500)
        dialogue = [{"speaker_name": "陈一", "sentences": [{"text": long_text, "begin_time": 1000}]}]
        blocks = self._build("@原文 概述一下", task=self._make_task(dialogue=dialogue), monkeypatch=monkeypatch)
        full = [b for b in blocks if b.startswith("## 用户显式引用（@原文）")][0]
        assert "已截断至前" in full and len(full) < MENTION_TRANSCRIPT_CAP + 200

    def test_transcript_realtime_full(self, monkeypatch):
        realtime = [
            {"speaker_id": "spk1", "text": "会中发言一", "begin_time": 1000},
            {"speaker_id": "spk2", "text": "会中发言二", "begin_time": 2000},
        ]
        blocks = self._build("@原文 刚才说了什么", realtime=realtime, monkeypatch=monkeypatch)
        full = [b for b in blocks if b.startswith("## 用户显式引用（@原文）")]
        assert len(full) == 1 and "会中发言一" in full[0] and "会中发言二" in full[0]
        # 升级替换：自动「最近发言」块不得出现
        assert not any("最近发言" in b for b in blocks)

    def test_transcript_missing_notice(self, monkeypatch):
        blocks = self._build("@原文 有哪些结论", task=self._make_task(), monkeypatch=monkeypatch)
        assert any("@原文" in b and "暂无逐字稿原文" in b for b in blocks)

    def test_summary_full_replaces_cap(self, monkeypatch):
        tail = "尾部关键结论" * 50
        summary = "开头" + "填充" * 1500 + tail  # > 2000 字
        blocks = self._build("@纪要 结论是什么", task=self._make_task(summary=summary), monkeypatch=monkeypatch)
        full = [b for b in blocks if b.startswith("## 用户显式引用（@纪要）")]
        assert len(full) == 1 and tail in full[0]
        # 升级替换：采样口径纪要块不得同时出现
        assert not any(b.startswith("## 当前会议纪要") for b in blocks)

    def test_summary_missing_notice(self, monkeypatch):
        blocks = self._build("@纪要 总结一下", task=self._make_task(dialogue=[{"speaker_name": "陈一", "sentences": [{"text": "x", "begin_time": 0}]}]), monkeypatch=monkeypatch)
        assert any("@纪要" in b and "暂无可用纪要" in b for b in blocks)

    def test_notes_full_and_missing(self, monkeypatch):
        tail = "随记尾部要点" * 50
        notes = "随记开头" + "记" * 2200 + tail
        blocks = self._build("@随记 我记了什么", task=self._make_task(notes=notes), monkeypatch=monkeypatch)
        full = [b for b in blocks if b.startswith("## 用户显式引用（@随记）")]
        assert len(full) == 1 and tail in full[0]
        assert not any(b.startswith("## 用户随记（录音期间手写原文") for b in blocks)
        # 缺失 → 说明块
        blocks2 = self._build("@随记 我记了什么", task=self._make_task(), monkeypatch=monkeypatch)
        assert any("@随记" in b and "暂无用户随记" in b for b in blocks2)

    def test_multi_tokens_combined(self, monkeypatch):
        dialogue = [{"speaker_name": "陈一", "sentences": [{"text": "对话内容", "begin_time": 1000}]}]
        task = self._make_task(dialogue=dialogue, notes="手写要点")
        blocks = self._build("@原文 @随记 都看看", task=task, monkeypatch=monkeypatch)
        assert any(b.startswith("## 用户显式引用（@原文）") and "对话内容" in b for b in blocks)
        assert any(b.startswith("## 用户显式引用（@随记）") and "手写要点" in b for b in blocks)

    def test_no_tokens_behavior_unchanged(self, monkeypatch):
        dialogue = [{"speaker_name": "陈一", "sentences": [{"text": "普通句子", "begin_time": 1000}]}]
        blocks = self._build("总结一下", task=self._make_task(dialogue=dialogue, summary="短纪要"), monkeypatch=monkeypatch)
        assert any(b.startswith("## 当前会议对话时间轴") and "普通句子" in b for b in blocks)
        assert any(b.startswith("## 当前会议纪要") for b in blocks)
        assert not any("用户显式引用" in b for b in blocks)


# ============================================================
# @附件：本地文件与图片
# ============================================================
class TestAttachment:
    """附件存储、内容展开与端点。"""

    @pytest.fixture(autouse=True)
    def _isolate_attachments_dir(self, tmp_path, monkeypatch):
        import app.chat_attachment_store as store_mod
        monkeypatch.setattr(store_mod, "ATTACHMENTS_DIR", tmp_path / "attachments")
        store_mod.ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 存储层 ──
    def test_store_save_and_load(self):
        from app.chat_attachment_store import get_meta, load_bytes, save_attachment
        meta = save_attachment("笔记.txt", "text/plain", b"hello")
        assert meta["filename"] == "笔记.txt" and meta["size"] == 5
        loaded_meta, data = load_bytes(meta["id"])
        assert loaded_meta["id"] == meta["id"] and data == b"hello"
        assert get_meta(meta["id"])["content_type"] == "text/plain"

    def test_store_rejects_empty_and_oversize(self):
        from app.chat_attachment_store import ATTACHMENT_MAX_BYTES, AttachmentError, save_attachment
        with pytest.raises(AttachmentError):
            save_attachment("x.txt", "text/plain", b"")
        with pytest.raises(AttachmentError):
            save_attachment("big.bin", "application/octet-stream", b"x" * (ATTACHMENT_MAX_BYTES + 1))

    def test_store_invalid_id_and_delete(self):
        from app.chat_attachment_store import AttachmentError, delete_attachment, get_meta
        with pytest.raises(AttachmentError):
            get_meta("../evil")
        with pytest.raises(AttachmentError):
            get_meta("nonexistent")
        delete_attachment("nonexistent")  # 静默

    # ── 内容展开 ──
    def test_image_part_base64(self):
        from app.chat_attachment_store import save_attachment
        from app.routers.chat import _build_attachment_parts
        # 最小 PNG 字节（1x1 透明）
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082")
        meta = save_attachment("图.png", "image/png", png)
        parts, notice = _build_attachment_parts([{"id": meta["id"]}])
        assert len(parts) == 1 and parts[0]["type"] == "image_url"
        assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
        assert "图.png" in notice and "1 张图片" in notice

    def test_text_file_extracted(self):
        from app.chat_attachment_store import save_attachment
        from app.routers.chat import _build_attachment_parts
        meta = save_attachment("资料.md", "text/markdown", "# 标题\n正文内容".encode())
        parts, notice = _build_attachment_parts([{"id": meta["id"]}])
        assert len(parts) == 1 and parts[0]["type"] == "text"
        assert "正文内容" in parts[0]["text"] and "资料.md" in parts[0]["text"]

    def test_text_cap_truncates(self):
        from app.chat_attachment_store import save_attachment
        from app.routers.chat import ATTACHMENT_TEXT_CAP, _build_attachment_parts
        long = ("字" * (ATTACHMENT_TEXT_CAP + 200)).encode()
        meta = save_attachment("long.txt", "text/plain", long)
        parts, _ = _build_attachment_parts([{"id": meta["id"]}])
        assert "已截断" in parts[0]["text"]

    def test_unreadable_binary_notice(self):
        from app.chat_attachment_store import save_attachment
        from app.routers.chat import _build_attachment_parts
        # .xlsx 无解析库；且伪造字节不是有效 zip
        meta = save_attachment("表格.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               b"\x00\x01\x02binary")
        parts, notice = _build_attachment_parts([{"id": meta["id"]}])
        assert "无法解析" in parts[0]["text"] and "表格.xlsx" in parts[0]["text"]
        assert "禁止" in parts[0]["text"]

    def test_missing_attachment_raises(self):
        from app.chat_attachment_store import AttachmentError
        from app.routers.chat import _build_attachment_parts
        with pytest.raises(AttachmentError):
            _build_attachment_parts([{"id": "deadbeef"}])

    # ── 端点 ──
    def test_upload_endpoint(self, client):
        resp = client.post(
            "/api/chat/attachments",
            files=[("files", ("a.txt", b"content", "text/plain")),
                   ("files", ("b.txt", b"more", "text/plain"))])
        assert resp.status_code == 200
        metas = resp.json()["attachments"]
        assert len(metas) == 2
        assert {m["filename"] for m in metas} == {"a.txt", "b.txt"}

    def test_upload_oversize_413(self, client):
        big = b"x" * (10 * 1024 * 1024 + 10)
        resp = client.post("/api/chat/attachments",
                           files=[("files", ("big.bin", big, "application/octet-stream"))])
        assert resp.status_code == 413

    def test_fetch_attachment_endpoint(self, client):
        up = client.post("/api/chat/attachments",
                         files=[("files", ("读我.txt", "原文".encode(), "text/plain"))])
        attach_id = up.json()["attachments"][0]["id"]
        resp = client.get(f"/api/chat/attachments/{attach_id}")
        assert resp.status_code == 200 and resp.content == "原文".encode()
        # 不存在 → 404
        assert client.get("/api/chat/attachments/nope123").status_code == 404

    def test_stream_missing_attachment_400(self, client):
        resp = client.post("/api/chat/stream", json={
            "message": "问题", "attachments": [{"id": "nonexistent"}]})
        assert resp.status_code == 400

    def test_stream_too_many_attachments_400(self, client):
        resp = client.post("/api/chat/stream", json={
            "message": "问题",
            "attachments": [{"id": str(i)} for i in range(7)]})
        assert resp.status_code == 400
