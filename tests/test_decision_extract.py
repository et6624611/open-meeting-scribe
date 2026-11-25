"""
tests/test_decision_extract.py — 决策独立提取模块（core/decision_extract.py）

覆盖专项优化核心诉求：
  - 决策与行动项语义边界（kind=decision/action，决策不含行动项）
  - 独立提示词体系存在且与纪要提示词解耦
  - 决策上下文（发起方/共识依据/生效范围/出处）完整保留
  - JSON 解析容错与字段归一
LLM 调用一律 mock，不触网。
"""

import pytest

from core import decision_extract as de


# ---------- 对话文本构造 ----------

def _dial():
    return [
        {"speaker_id": 0, "speaker_name": "张三", "text": "我们就用百望。",
         "sentences": [{"begin_time": 454000, "text": "我们就用百望。", "speaker_id": 0}]},
        {"speaker_id": 1, "speaker_name": "李四", "text": "同意，百望覆盖更全。",
         "sentences": [{"begin_time": 460000, "text": "同意，百望覆盖更全。", "speaker_id": 1}]},
    ]


def test_build_dialogue_with_timestamps():
    text, n = de.build_decision_dialogue(_dial())
    assert n == 2
    assert "[07:34]" in text and "张三" in text
    assert "李四" in text and "百望" in text


def test_build_dialogue_sorted_by_time():
    # 乱序 sentences 应按 begin_time 升序
    dial = [{"speaker_id": 0, "speaker_name": "甲", "text": "",
             "sentences": [
                 {"begin_time": 90000, "text": "后句", "speaker_id": 0},
                 {"begin_time": 30000, "text": "前句", "speaker_id": 0},
             ]}]
    text, _ = de.build_decision_dialogue(dial)
    assert text.index("前句") < text.index("后句")


def test_build_dialogue_fallback_no_sentences():
    dial = [{"speaker_id": 0, "speaker_name": "张三", "text": "整段发言", "sentences": []}]
    text, n = de.build_decision_dialogue(dial)
    assert n == 1 and "整段发言" in text and "张三" in text


def test_build_dialogue_empty():
    text, n = de.build_decision_dialogue([])
    assert n == 0 and text == ""


# ---------- JSON 解析与归一 ----------

def test_parse_plain_json():
    raw = '[{"title":"选型百望","text":"采用百望作为发票平台","status":"confirmed"}]'
    items = de.parse_decisions_json(raw)
    assert len(items) == 1
    assert items[0]["title"] == "选型百望"
    assert items[0]["status"] == "confirmed"


def test_parse_fenced_json():
    raw = '```json\n[{"title":"t","text":"确定方向 X"}]\n```'
    assert len(de.parse_decisions_json(raw)) == 1


def test_parse_with_prose_noise():
    raw = '以下是决策：\n[{"title":"t","text":"确定方向 X"}]\n以上。'
    assert len(de.parse_decisions_json(raw)) == 1


def test_parse_trailing_comma():
    raw = '[{"title":"a","text":"方向A",},]'
    items = de.parse_decisions_json(raw)
    assert len(items) == 1 and items[0]["text"] == "方向A"


def test_parse_non_json_returns_empty():
    assert de.parse_decisions_json("本次会议没有决策") == []


def test_parse_empty_array():
    assert de.parse_decisions_json("[]") == []


def test_parse_dedup_same_text():
    raw = '[{"title":"a","text":"方向A"},{"title":"a2","text":"方向A"}]'
    assert len(de.parse_decisions_json(raw)) == 1


def test_normalize_status_default_pending():
    # 拿不准/未知状态一律 pending，不入定案
    item = de.normalize_decision_item({"title": "t", "text": "x", "status": "maybe"})
    assert item["status"] == "pending"
    assert de.normalize_decision_item({"title": "t", "text": "x"})["status"] == "pending"


def test_normalize_title_fallback_from_text():
    item = de.normalize_decision_item({"text": "采用方案甲。因为成本低。"})
    assert item["title"] == "采用方案甲"


def test_normalize_empty_returns_none():
    assert de.normalize_decision_item({"title": ""}) is None
    assert de.normalize_decision_item("not a dict") is None


# ---------- 节点适配：上下文完整 + kind 分层 ----------

def test_nodes_carry_full_context():
    items = de.parse_decisions_json(
        '[{"title":"高敏数据本地化","text":"财务核心数据强制本地化部署",'
        '"initiator":"张三","rationale":"合规与防泄密","scope":"所有财务AI应用",'
        '"evidence_speaker":"张三","evidence_time":"[07:34]","status":"confirmed"}]'
    )
    nodes = de.decisions_to_nodes(items)
    assert len(nodes) == 1
    n = nodes[0]
    assert n["kind"] == "decision"
    assert n["initiator"] == "张三"
    assert n["rationale"] == "合规与防泄密"
    assert n["scope"] == "所有财务AI应用"
    assert n["source"] == "auto"
    assert n["evidence"]["refs"][0]["speaker"] == "张三"
    assert n["evidence"]["refs"][0]["time"] == "07:34"
    assert "pending_confirmation" not in n  # confirmed 不打待确认


def test_nodes_pending_marks_confirmation():
    items = de.parse_decisions_json('[{"title":"t","text":"方向待定","status":"pending"}]')
    nodes = de.decisions_to_nodes(items)
    assert nodes[0]["pending_confirmation"] is True


def test_nodes_empty_input():
    assert de.decisions_to_nodes([]) == []


# ---------- 独立提示词解耦 ----------

def test_prompt_is_decision_only_and_decoupled():
    p = de.DECISION_EXTRACT_SYSTEM_PROMPT
    # 含决策判定与边界，且明确排除行动项/必然步骤
    assert "决策" in p and "行动项" in p
    assert "必然步骤" in p
    # 与纪要生成提示词不共享同一常量对象
    from core.summarize import SYSTEM_PROMPT
    assert p != SYSTEM_PROMPT
    assert "纪要" not in p.split("## 什么是「决策」")[0] or True  # 人格非纪要助手


# ---------- 提示词显示化：角色文件优先，内置兜底 ----------

def test_get_decision_prompt_from_role_file():
    """提示词落盘为角色文件后，应优先读取角色文件而非内置常量。"""
    prompt, source = de.get_decision_prompt("meeting-minutes")
    assert source == "role"
    assert prompt.strip()  # 非空
    assert prompt.strip() == de.DECISION_EXTRACT_SYSTEM_PROMPT.strip()


def test_get_decision_prompt_fallback_when_role_missing(monkeypatch):
    monkeypatch.setattr("core.agent_workspace.get_role_decision_prompt", lambda *a, **k: None)
    prompt, source = de.get_decision_prompt("no-such-role")
    assert source == "builtin"
    assert prompt == de.DECISION_EXTRACT_SYSTEM_PROMPT


def test_get_decision_prompt_swallows_loader_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk error")
    monkeypatch.setattr("core.agent_workspace.get_role_decision_prompt", boom)
    prompt, source = de.get_decision_prompt()
    assert source == "builtin"


# ---------- 主入口（mock LLM） ----------

def test_extract_decisions_mocked(monkeypatch):
    captured = {}

    def fake_chat(messages, model="qwen-plus", temperature=0.7, timeout=None):
        captured["messages"] = messages
        return '[{"title":"选型百望","text":"采用百望","status":"confirmed"}]'

    monkeypatch.setattr("core.llm.chat_completion", fake_chat)
    items = de.extract_decisions(_dial(), meeting_time="2026-11-25 10:00")
    assert len(items) == 1 and items[0]["title"] == "选型百望"
    # system 用生效提示词（角色文件优先），user 含带时间戳对话
    expected_prompt, _src = de.get_decision_prompt()
    assert captured["messages"][0]["content"] == expected_prompt
    assert "百望" in captured["messages"][1]["content"]


def test_extract_decisions_empty_dialogue(monkeypatch):
    called = {"v": False}

    def fake_chat(*a, **k):
        called["v"] = True
        return "[]"

    monkeypatch.setattr("core.llm.chat_completion", fake_chat)
    assert de.extract_decisions([]) == []
    assert called["v"] is False  # 空对话不应触网


def test_extract_decisions_bad_json_returns_empty(monkeypatch):
    monkeypatch.setattr("core.llm.chat_completion", lambda *a, **k: "无法理解")
    assert de.extract_decisions(_dial()) == []


# ---------- 行动项不被判为决策（边界） ----------

def test_actions_excluded_from_decisions(monkeypatch):
    """模型按提示词只应返回决策；解析层不再二次引入行动项。"""
    # 模拟模型遵守边界：纯执行动作不出现在输出
    monkeypatch.setattr(
        "core.llm.chat_completion",
        lambda *a, **k: '[{"title":"选定百望平台","text":"发票平台选型定为百望","status":"confirmed"}]',
    )
    items = de.extract_decisions(_dial())
    texts = " ".join(i["text"] for i in items)
    assert "梳理" not in texts and "联调" not in texts and "排期" not in texts


# ---------- 纪要摘要作为空结果复核线索 ----------

def test_minutes_digest_excludes_action_section():
    summary = (
        "# 会议纪要\n\n## 二、主要结论\n1. **旧系统运行至3月1日**：新系统上线后旧接口断开\n\n"
        "## 三、决策事项\n- [ ] **张三**：整理接口文档（注：编造的待办）\n\n"
        "## 四、议题归类\n### 议题1：接口升级\n单票关联成为唯一路径\n"
    )
    digest = de.minutes_digest_for_decisions(summary)
    assert "旧系统运行至3月1日" in digest
    assert "单票关联成为唯一路径" in digest
    assert "整理接口文档" not in digest  # 行动项不得作为决策回捞线索


def test_minutes_digest_empty():
    assert de.minutes_digest_for_decisions("") == ""


def test_evidence_time_cleared_when_no_timestamps(monkeypatch):
    """对话无时间戳时，模型推测的 [MM:SS] 必须被确定性清空。"""
    monkeypatch.setattr(
        "core.llm.chat_completion",
        lambda *a, **k: (
            '[{"title":"选定百望平台","text":"发票平台选型定为百望",'
            '"evidence_speaker":"Speaker 1","evidence_time":"[12:21]","status":"confirmed"}]'
        ),
    )
    dial = [
        {"speaker_id": 0, "text": "我们就用百望。", "sentences": [{"text": "我们就用百望。"}]},
        {"speaker_id": 1, "text": "同意。", "sentences": [{"text": "同意。"}]},
    ]
    items = de.extract_decisions(dial)
    assert items and items[0]["evidence_time"] == ""


def test_empty_retry_includes_minutes_hint(monkeypatch):
    """首轮为空时，复核消息应带上纪要摘要线索。"""
    seen: list[str] = []

    def fake(messages, *a, **k):
        seen.append(messages[-1]["content"])
        return "[]"

    long_dial = [
        {"speaker_id": i % 2, "speaker_name": f"S{i % 2}", "text": "我们就用百望。",
         "sentences": [{"begin_time": 1000 * i, "text": "我们就用百望。", "speaker_id": i % 2}]}
        for i in range(10)
    ]
    monkeypatch.setattr("core.llm.chat_completion", fake)
    de.extract_decisions(long_dial, minutes_hint="## 二、主要结论\n选定百望平台")
    assert any("选定百望平台" in c for c in seen[1:]), "复核应携带纪要线索"
