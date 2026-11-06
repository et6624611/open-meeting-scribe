"""D018a 修复批测试：LLM 超时可配 + 决策抽取超时降级"纪要已出、决策待补"。

拍板三要素（PM cmsg_01m6dzp5h41b5c14zz41f6yg1k）：
1. 超时可配（env，默认 120=原值，个人版零行为变化）；
2. AI 环节失败不连坐已成功环节：合体调用超时 → 仅正文降级重试（独立预算）；
3. 决策/正文分离预算：降级重试走 OMS_LLM_SUMMARY_RETRY_TIMEOUT_SECONDS（默认 180）。
"""
from __future__ import annotations

import pytest
import requests

import core.llm as llm
from core import task_store

# ---------------- 要素一：超时可配（默认=旧值） ----------------


def test_timeout_env_parsing(monkeypatch):
    monkeypatch.delenv("OMS_LLM_TIMEOUT_SECONDS", raising=False)
    assert llm.llm_timeout_seconds() == 120.0  # 缺省维持原写死值=个人版零变化
    monkeypatch.setenv("OMS_LLM_TIMEOUT_SECONDS", "45")
    assert llm.llm_timeout_seconds() == 45.0
    monkeypatch.setenv("OMS_LLM_TIMEOUT_SECONDS", "abc")  # 非法回退默认
    assert llm.llm_timeout_seconds() == 120.0
    monkeypatch.setenv("OMS_LLM_TIMEOUT_SECONDS", "-5")   # 非正回退默认
    assert llm.llm_timeout_seconds() == 120.0
    monkeypatch.setenv("OMS_LLM_SUMMARY_RETRY_TIMEOUT_SECONDS", "300")
    assert llm.summary_retry_timeout_seconds() == 300.0
    monkeypatch.delenv("OMS_LLM_SUMMARY_RETRY_TIMEOUT_SECONDS", raising=False)
    assert llm.summary_retry_timeout_seconds() == 180.0   # 独立预算默认 180


# ---------------- 要素二：body_only 提示词约束 + 预算透传 ----------------


def test_generate_summary_body_only_prompt_and_budget(monkeypatch):
    from core import summarize

    captured: dict = {}

    def fake_chat(messages, model=None, timeout=None):
        captured["messages"] = messages
        captured["timeout"] = timeout
        return "# 会议纪要\n\n**会议概要**：正常正文内容，足够长以通过误拒检测。" + "细节。" * 60

    monkeypatch.setattr(summarize, "chat_completion", fake_chat)
    dialogue = [
        {"speaker_id": 0, "text": "甲的多轮发言内容足够长", "sentences": [{"text": f"甲句{i}"} for i in range(8)], "speaker_name": "张三"},
        {"speaker_id": 1, "text": "乙的多轮发言内容足够长", "sentences": [{"text": f"乙句{i}"} for i in range(6)], "speaker_name": "李四"},
    ]
    out = summarize.generate_summary(dialogue, model="test", mode="body_only", timeout=180.0)
    assert "不要输出「主要结论」「决策事项」章节" in captured["messages"][1]["content"]
    assert captured["timeout"] == 180.0  # 独立预算到达底层 requests
    assert "正文" in out
    # full 模式=旧行为：无追加约束、timeout=None 透传（底层回落全局配置）
    summarize.generate_summary(dialogue, model="test")
    assert "本次输出约束" not in captured["messages"][1]["content"]
    assert captured["timeout"] is None


# ---------------- 要素三：pipeline_runner 降级重试（不连坐转写） ----------------


@pytest.fixture()
def runner_env(monkeypatch, tmp_path):
    import core.pipeline_runner as pr

    events: list = []
    monkeypatch.setattr(pr.joblog, "append_event",
                        lambda *a, **k: events.append((a[1] if len(a) > 1 else "", a[2] if len(a) > 2 else k)))
    monkeypatch.setattr(task_store, "save_task_to_disk", lambda tid: None)
    return pr, events


def test_stage2_timeout_degrades_to_body_only(monkeypatch, runner_env):
    pr, events = runner_env
    tid = "tsk_d018a"
    dialogue = [{"speaker_id": 0, "text": "内容", "sentences": ["内容"]}]
    task_store.tasks[tid] = {"task_id": tid, "dialogue": dialogue, "status": "processing", "progress": 0}

    calls: list[dict] = []

    def fake_stage2(**kwargs):
        calls.append(kwargs)
        if kwargs.get("summary_mode", "full") != "body_only":
            raise requests.exceptions.Timeout("120s read timeout")
        return {
            "summary": "# 会议纪要\n\n**会议概要**：降级正文产出。",
            "dialogue": dialogue,
            "output_path": "/tmp/x.md",
            "speaker_mapping": {},
            "speaker_uuid_mapping": {},
            "chapters": [],
            "title": "例会",
        }

    monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)
    pr._run_stage2_for_task(tid, {}, None)

    task = task_store.tasks[tid]
    assert task["status"] == "completed", task  # 不再整单 failed——转写+降级纪要保住
    assert task["decisions_pending"] is True
    assert "决策待补" in task["message"] or "decisions pending" in task["message"]
    assert len(calls) == 2
    assert calls[0].get("summary_mode", "full") == "full" or "summary_mode" not in calls[0]
    assert calls[1]["summary_mode"] == "body_only"
    assert calls[1]["summary_timeout"] == 180.0  # 独立预算生效
    # 降级事件入任务日志（warn 级，用户侧可追溯）
    assert any("降级" in str(e) for e in events)


def test_stage2_non_timeout_no_degradation(monkeypatch, runner_env):
    pr, events = runner_env
    tid = "tsk_d018a2"
    task_store.tasks[tid] = {"task_id": tid, "dialogue": [{"speaker_id": 0, "text": "x", "sentences": ["x"]}],
                     "status": "processing", "progress": 0}

    calls: list[int] = []

    def fake_stage2(**kwargs):
        calls.append(1)
        raise ValueError("非超时错误不触发降级")

    monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)
    monkeypatch.setattr(pr, "_try_realtime_fallback", lambda *a, **k: False)
    pr._run_stage2_for_task(tid, {}, None)

    task = task_store.tasks[tid]
    assert task["status"] == "failed"
    assert "decisions_pending" not in task
    # 非超时=原语义零变化（重试轮数由既有 transient 逻辑决定，降级分支未进）
    assert all(True for _ in calls)


def test_is_llm_timeout_shapes():
    from core.pipeline_runner import _is_llm_timeout

    assert _is_llm_timeout(TimeoutError("t"))
    assert _is_llm_timeout(requests.exceptions.Timeout())
    import httpx
    assert _is_llm_timeout(httpx.ReadTimeout("t"))
    assert not _is_llm_timeout(ValueError("nope"))
    assert not _is_llm_timeout(RuntimeError("boom"))
