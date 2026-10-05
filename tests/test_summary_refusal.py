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
