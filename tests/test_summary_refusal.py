"""纪要误拒守卫：充足对话遭模型拒答时抛 SummaryRefusalError，走瞬时重试。

回归背景：2026-10-01 实测，235 句对话的会议点「重新生成纪要」，
云端 qwen-plus 返回 16 字拒答话术「对话内容过短，无法生成有效纪要。」，
直接落盘覆盖了旧的好纪要。守卫口径见 core/summarize.is_summary_refusal。
"""

import pytest

import core.summarize as summarize
from core.errors import is_transient_error
from core.summarize import SummaryRefusalError, is_summary_refusal


def _long_dialogue(sentences: int = 20) -> list[dict]:
    sents = [{"text": f"第{i}句讨论内容。"} for i in range(sentences)]
    return [{"speaker_id": 0, "speaker_name": "张三",
             "text": "\n".join(s["text"] for s in sents), "sentences": sents}]


class TestIsSummaryRefusal:
    def test_refusal_phrase_long_dialogue(self):
        assert is_summary_refusal("对话内容过短，无法生成有效纪要。", 235) is True

    def test_empty_summary_long_dialogue(self):
        assert is_summary_refusal("", 20) is True
        assert is_summary_refusal(None, 20) is True

    def test_short_dialogue_not_intercepted(self):
        # 低于 10 句时拒答可能为真，放行（<3 句有本地守卫先行返回）
        assert is_summary_refusal("对话内容过短，无法生成有效纪要。", 5) is False

    def test_normal_summary_passes(self):
        assert is_summary_refusal("# 会议纪要\n" + "正文。" * 200, 20) is False

    def test_long_text_with_marker_passes(self):
        # 长文里引用拒答话术不算拒答（例如纪要讨论「内容不足」本身）
        text = "# 会议纪要\n" + "讨论。" * 150 + "\n有人提到对话内容过短的问题。\n" + "结论。" * 100
        assert is_summary_refusal(text, 20) is False


class TestGenerateSummaryRefusal:
    def test_refusal_raises(self, monkeypatch):
        monkeypatch.setattr(summarize, "chat_completion",
                            lambda *a, **k: "对话内容过短，无法生成有效纪要。")
        with pytest.raises(SummaryRefusalError):
            summarize.generate_summary(_long_dialogue(), model="qwen-plus")

    def test_normal_output_returned(self, monkeypatch):
        good = "# 会议纪要\n" + "结论若干。" * 50
        monkeypatch.setattr(summarize, "chat_completion", lambda *a, **k: good)
        assert summarize.generate_summary(_long_dialogue(), model="qwen-plus") == good


class TestTransientClassification:
    def test_refusal_is_transient(self):
        assert is_transient_error(SummaryRefusalError("模型误判对话内容不足")) is True


class TestSummarySanitize:
    """P0 净化：剥离正文前的推理/自检前言，归一漂移的章节标题。"""

    def test_strip_preface_before_heading(self):
        polluted = (
            "对话内容过长（816句）……根据本AI助手的核心原则，经严格校验，必须如实输出。\n\n"
            "# 会议纪要\n\n## 一、会议概要\n本次会议……"
        )
        cleaned = summarize.strip_minutes_preface(polluted)
        assert cleaned.startswith("# 会议纪要")
        assert "经严格校验" not in cleaned

    def test_strip_clean_summary_unchanged(self):
        good = "# 会议纪要\n\n## 一、会议概要\n正文"
        assert summarize.strip_minutes_preface(good) == good

    def test_meta_polluted_detection(self):
        assert summarize.is_summary_meta_polluted(
            "根据本AI助手的核心原则，经严格校验，必须如实输出。"
        ) is True
        assert summarize.is_summary_meta_polluted("# 会议纪要\n正文") is False
        assert summarize.is_summary_meta_polluted("一篇正常的会议纪要正文。") is False

    def test_section_heading_alias(self):
        for title in ("待办事项", "行动项", "后续任务"):
            text = f"## 三、{title}\n\n- [ ] 张三：联调"
            assert "## 三、决策事项" in summarize.normalize_section_headings(text)

    def test_generate_summary_strips_preface(self, monkeypatch):
        polluted = (
            "根据本AI助手的核心原则，经严格校验，必须如实输出。\n\n"
            "# 会议纪要\n\n## 一、会议概要\n正文若干。"
        )
        monkeypatch.setattr(summarize, "chat_completion", lambda *a, **k: polluted)
        out = summarize.generate_summary(_long_dialogue(), model="qwen-plus")
        assert out.startswith("# 会议纪要")

    def test_meta_polluted_retries_once(self, monkeypatch):
        polluted = "根据本AI助手的核心原则，经严格校验，必须如实输出。" * 5
        good = "# 会议纪要\n\n## 一、会议概要\n正文若干。"
        replies = iter([polluted, good])
        calls = []

        def fake(*a, **k):
            calls.append(1)
            return next(replies)

        monkeypatch.setattr(summarize, "chat_completion", fake)
        out = summarize.generate_summary(_long_dialogue(), model="qwen-plus")
        assert len(calls) == 2
        assert out.startswith("# 会议纪要")

    def test_long_analysis_without_heading_is_unusable(self):
        """模型把"会议诊断+拒答"写成长文时，也要判为不可用（本次真实回归样例）。"""
        analysis = (
            "对话内容虽长（816句），但缺乏清晰的会议结构、明确的议程与决策结论。\n\n"
            "### ✅ 结论\n**对话内容不足，无法生成完整会议纪要**。\n"
        ) * 6
        assert summarize.is_summary_unusable(analysis, total_sentences=816) is True
        assert summarize.is_summary_refusal(analysis, total_sentences=816) is True

    def test_unusable_twice_raises(self, monkeypatch):
        bad = "对话内容虽长，但缺乏清晰的会议结构。\n\n### 结论\n对话内容不足，无法生成完整会议纪要。" * 6
        monkeypatch.setattr(summarize, "chat_completion", lambda *a, **k: bad)
        try:
            summarize.generate_summary(_long_dialogue(), model="qwen-plus")
        except summarize.SummaryRefusalError:
            pass
        else:
            raise AssertionError("两次输出均不可用时应该抛出 SummaryRefusalError")

    def test_strip_fabricated_times_in_notes(self):
        text = (
            "- [ ] **张三**：整理接口文档（注：Speaker 3 11:05 要求验证；Speaker 4 19:41 提出异议）\n"
            "> 依据：Speaker 3（09:10）、Speaker 4（15:22）"
        )
        cleaned = summarize.strip_fabricated_times(text)
        assert "11:05" not in cleaned and "19:41" not in cleaned
        assert "09:10" not in cleaned and "15:22" not in cleaned
        assert "Speaker 3" in cleaned

    def test_dialogue_timestamp_detection(self):
        assert summarize.dialogue_has_timestamps(
            [{"sentences": [{"text": "a", "begin_time": 1000}]}]
        ) is True
        assert summarize.dialogue_has_timestamps(
            [{"sentences": [{"text": "a"}]}]
        ) is False

    def test_thin_negative_summary_detected(self):
        thin = (
            "# 会议纪要\n\n## 一、会议概要\n本次对话内容弥散。\n\n"
            "## 二、主要结论\n本次会议未形成明确结论。\n\n"
            "## 三、决策事项\n无明确待办事项。\n\n## 四、议题归类\n不适用议题归类。"
        )
        assert summarize.is_summary_too_thin(thin, 816) is True
        full = "# 会议纪要\n\n## 二、主要结论\n" + "会议确认了月结链路的三个关键约束。" * 80
        assert summarize.is_summary_too_thin(full, 816) is False
