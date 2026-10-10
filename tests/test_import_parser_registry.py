"""
tests/test_import_parser_registry.py — Parser Registry v2.0 单元测试

覆盖：
  1. 每个 parser 的 confidence + parse（happy path）
  2. 每个 parser 对不匹配格式的 confidence=0
  3. registry.best_match 正确选最高分
  4. parse_document_content 集成路径（含 summary 兜底）
  5. detect_content_type 兼容路径
  6. 边界：空文本 / 极短文本 / 混合噪声 / 空文件扩展名
  7. 向后兼容入口（parse_srt / parse_vtt / parse_markdown_transcript）
"""

import pytest

from core.import_parser import (
    CONTENT_TYPE_SUMMARY,
    CONTENT_TYPE_TRANSCRIPT,
    CONTENT_TYPE_UNKNOWN,
    InlineMarkdownParser,
    SpeakerNumberParser,
    StandaloneSpeakerParser,
    SrtParser,
    VttParser,
    _registry,
    detect_content_type,
    parse_document_content,
    parse_markdown_transcript,
    parse_srt,
    parse_vtt,
)


# ============================================================
# SrtParser
# ============================================================

class TestSrtParser:
    _PARSER = SrtParser()

    def test_confidence_ext_hits(self):
        text = "00:00:01,000 --> 00:00:05,000\nHello"
        assert self._PARSER.confidence(text, "meeting.srt") == pytest.approx(0.95)

    def test_confidence_content_hits(self):
        text = (
            "1\n00:00:01,000 --> 00:00:05,000\nA\n\n"
            "2\n00:00:06,000 --> 00:00:10,000\nB\n\n"
            "3\n00:00:11,000 --> 00:00:15,000\nC"
        )
        assert self._PARSER.confidence(text, "") >= 0.80

    def test_confidence_no_match(self):
        assert self._PARSER.confidence("张三：你好", "") == 0.0

    def test_parse_basic(self):
        text = (
            "1\n00:00:01,000 --> 00:00:05,000\nHello\n\n"
            "2\n00:00:06,000 --> 00:00:10,000\nWorld"
        )
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 1  # 都归到 speaker 0
        sentences = dlg[0]["sentences"]
        assert len(sentences) == 2
        assert sentences[0]["begin_time"] == 1000
        assert sentences[0]["end_time"] == 5000
        assert sentences[0]["text"] == "Hello"

    def test_parse_ignores_malformed_blocks(self):
        text = (
            "1\n00:00:01,000 --> 00:00:05,000\nGood\n\n"
            "garbage block\n\n"
            "2\n00:00:06,000 --> 00:00:10,000\nStill good"
        )
        dlg = self._PARSER.parse(text)
        assert len(dlg) >= 1
        texts = [s["text"] for s in dlg[0]["sentences"]]
        assert "Good" in texts
        assert "Still good" in texts

    def test_parse_empty_returns_empty(self):
        assert self._PARSER.parse("") == []


# ============================================================
# VttParser
# ============================================================

class TestVttParser:
    _PARSER = VttParser()

    def test_confidence_ext_hits(self):
        text = "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nHello"
        assert self._PARSER.confidence(text, "meeting.vtt") == pytest.approx(0.95)

    def test_confidence_content_hits(self):
        text = "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nHello"
        assert self._PARSER.confidence(text, "") == pytest.approx(0.85)

    def test_confidence_no_match(self):
        assert self._PARSER.confidence("张三：你好", "") == 0.0

    def test_parse_basic(self):
        text = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\nHello"
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 1
        assert dlg[0]["sentences"][0]["text"] == "Hello"

    def test_parse_strips_notes(self):
        text = (
            "WEBVTT\n\n"
            "NOTE this is a note\n\n"
            "1\n00:00:01.000 --> 00:00:05.000\nActual text"
        )
        dlg = self._PARSER.parse(text)
        texts = [s["text"] for s in dlg[0]["sentences"]]
        assert "this is a note" not in texts
        assert "Actual text" in texts


# ============================================================
# StandaloneSpeakerParser（本次修复的格式）
# ============================================================

class TestStandaloneSpeakerParser:
    _PARSER = StandaloneSpeakerParser()

    _SAMPLE = (
        "王永亮(00:00:28):\n"
        "石老师，咱们可以开始了。\n"
        "\n"
        "SJXRSCM_Stephen(00:00:31):\n"
        "好的，我先介绍一下流程。\n"
        "大概分三部分。\n"
        "\n"
        "王永亮(00:01:00):\n"
        "好的，开始吧。"
    )

    def test_confidence_good(self):
        conf = self._PARSER.confidence(self._SAMPLE, "")
        assert conf >= 0.5

    def test_confidence_no_match(self):
        assert self._PARSER.confidence("**张三**：你好", "") == 0.0

    def test_confidence_too_few_hits(self):
        # 只有 1 行像独立说话人 → 低分
        text = "王永亮(00:00:28):\n一句话内容\n其他普通文字\n更多普通文字"
        assert self._PARSER.confidence(text, "") < 0.4

    def test_parse_basic(self):
        dlg = self._PARSER.parse(self._SAMPLE)
        assert len(dlg) == 2

        yongliang = next(d for d in dlg if d["speaker_name"] == "王永亮")
        stephen = next(d for d in dlg if d["speaker_name"] == "SJXRSCM_Stephen")

        assert len(yongliang["sentences"]) == 2
        assert yongliang["sentences"][0]["begin_time"] == 28000
        assert yongliang["sentences"][0]["text"] == "石老师，咱们可以开始了。"
        assert yongliang["sentences"][1]["begin_time"] == 60000
        assert yongliang["sentences"][1]["text"] == "好的，开始吧。"

        assert len(stephen["sentences"]) == 1
        assert stephen["sentences"][0]["begin_time"] == 31000
        # 多行内容合并
        assert "好的，我先介绍一下流程。" in stephen["sentences"][0]["text"]
        assert "大概分三部分。" in stephen["sentences"][0]["text"]

    def test_parse_no_timestamp(self):
        text = (
            "张三:\n"
            "今天讨论一下。\n"
            "\n"
            "李四:\n"
            "好的，我来回应。"
        )
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 2
        zs = next(d for d in dlg if d["speaker_name"] == "张三")
        assert zs["sentences"][0]["begin_time"] == 0

    def test_parse_chinese_colon(self):
        text = "张三：\n你好世界"
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 1
        assert dlg[0]["speaker_name"] == "张三"
        assert dlg[0]["sentences"][0]["text"] == "你好世界"

    def test_parse_empty(self):
        assert self._PARSER.parse("") == []


# ============================================================
# InlineMarkdownParser
# ============================================================

class TestInlineMarkdownParser:
    _PARSER = InlineMarkdownParser()

    def test_confidence_bold(self):
        text = "**张三**：你好\n**李四**：好的\n**王五**：收到"
        assert self._PARSER.confidence(text, "") >= 0.4

    def test_confidence_bracket(self):
        text = "[00:01:00] 张三：你好\n[00:02:00] 李四：好的\n[00:03:00] 王五：收到"
        assert self._PARSER.confidence(text, "") >= 0.4

    def test_confidence_no_match(self):
        assert self._PARSER.confidence("王永亮(00:00:28):", "") == 0.0

    def test_parse_bold(self):
        text = "**张三**：今天讨论\n**李四**：好的，我来"
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 2
        names = {d["speaker_name"] for d in dlg}
        assert names == {"张三", "李四"}

    def test_parse_bracket_with_time(self):
        text = "[00:01:00] 张三：你好\n[00:02:30] 李四：好的"
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 2
        zs = next(d for d in dlg if d["speaker_name"] == "张三")
        assert zs["sentences"][0]["begin_time"] == 60000
        ls = next(d for d in dlg if d["speaker_name"] == "李四")
        assert ls["sentences"][0]["begin_time"] == 150000

    def test_parse_mixed_bold_and_bracket(self):
        text = "**张三**：第一个\n[00:02:00] 李四：第二个"
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 2

    def test_parse_no_hit_returns_empty(self):
        assert self._PARSER.parse("普通文本，没有标注") == []


# ============================================================
# SpeakerNumberParser
# ============================================================

class TestSpeakerNumberParser:
    _PARSER = SpeakerNumberParser()

    def test_confidence_good(self):
        text = "说话人 1：你好\n说话人 2：好的\n说话人 3：收到"
        assert self._PARSER.confidence(text, "") >= 0.5

    def test_confidence_english(self):
        text = "Speaker 1: hello\nSpeaker 2: hi"
        assert self._PARSER.confidence(text, "") >= 0.3

    def test_confidence_no_match(self):
        assert self._PARSER.confidence("张三：你好", "") == 0.0

    def test_parse_chinese(self):
        text = "说话人 1：你好\n说话人 2：好的"
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 2
        assert dlg[0]["speaker_id"] == 0
        assert dlg[1]["speaker_id"] == 1

    def test_parse_english(self):
        text = "Speaker 3: third person"
        dlg = self._PARSER.parse(text)
        assert len(dlg) == 1
        assert dlg[0]["speaker_id"] == 2

    def test_parse_no_hit(self):
        assert self._PARSER.parse("普通文本") == []


# ============================================================
# Registry 选择逻辑
# ============================================================

class TestRegistryBestMatch:
    def test_picks_srt_by_extension(self):
        parser = _registry.best_match("some timestamp text", "x.srt")
        assert parser.name == "srt"

    def test_picks_vtt_by_extension(self):
        parser = _registry.best_match("WEBVTT\n00:00:01.000 --> 00:00:05.000\nHi", "x.vtt")
        assert parser.name == "vtt"

    def test_picks_standalone_speaker_for_that_format(self):
        text = "王永亮(00:00:28):\n你好\n\nStephen(00:00:31):\n好的"
        parser = _registry.best_match(text, "")
        assert parser.name == "standalone_speaker"

    def test_picks_inline_markdown_for_bold_format(self):
        text = "**张三**：你好\n**李四**：好的"
        parser = _registry.best_match(text, "")
        assert parser.name == "inline_markdown"

    def test_returns_none_for_junk(self):
        assert _registry.best_match("  \n  \n", "") is None

    def test_score_all_returns_all_parsers(self):
        scores = _registry.score_all("**张三**：你好", "")
        names = [n for n, _ in scores]
        assert "srt" in names
        assert "standalone_speaker" in names
        assert len(scores) == 5  # 5 parsers registered


# ============================================================
# parse_document_content 集成路径
# ============================================================

class TestParseDocumentContent:
    def test_transcript_srt(self):
        text = "1\n00:00:01,000 --> 00:00:05,000\nHello"
        ctype, dialogue, summary = parse_document_content(text, "m.srt")
        assert ctype == CONTENT_TYPE_TRANSCRIPT
        assert dialogue is not None
        assert summary is None

    def test_transcript_standalone_speaker(self):
        text = (
            "王永亮(00:00:28):\n你好\n\n"
            "Stephen(00:00:31):\n好的"
        )
        ctype, dialogue, summary = parse_document_content(text, "m.md")
        assert ctype == CONTENT_TYPE_TRANSCRIPT
        assert dialogue is not None
        assert len(dialogue) == 2

    def test_summary_by_markdown_headings(self):
        text = "# 会议纪要\n## 主要结论\n讨论了项目进度\n## 待办事项\n- [ ] 张三完成报表"
        ctype, dialogue, summary = parse_document_content(text, "m.md")
        assert ctype == CONTENT_TYPE_SUMMARY
        assert dialogue is None
        assert summary is not None
        assert "会议纪要" in summary

    def test_empty_text(self):
        ctype, dialogue, summary = parse_document_content("", "")
        assert ctype == CONTENT_TYPE_UNKNOWN
        assert dialogue is None
        assert summary is None

    def test_too_short_text(self):
        ctype, dialogue, summary = parse_document_content("短", "")
        assert ctype == CONTENT_TYPE_UNKNOWN

    def test_fallback_to_summary_for_plain_text(self):
        # 既不是 transcript 格式也没有 summary 标题 → 兜底 summary
        text = (
            "今天我们讨论了一下项目的进度问题，张三认为应该加快节奏，"
            "李四表示同意，王五说需要再看看细节部分再定。"
        )
        ctype, dialogue, summary = parse_document_content(text, "notes.txt")
        assert ctype == CONTENT_TYPE_SUMMARY

    def test_pure_srt_content_no_extension(self):
        text = (
            "1\n00:00:01,000 --> 00:00:05,000\nHello\n\n"
            "2\n00:00:06,000 --> 00:00:10,000\nWorld"
        )
        ctype, dialogue, summary = parse_document_content(text, "")
        assert ctype == CONTENT_TYPE_TRANSCRIPT
        assert dialogue is not None


# ============================================================
# detect_content_type 兼容路径
# ============================================================

class TestDetectContentType:
    def test_transcript_via_registry(self):
        text = "王永亮(00:00:28):\n你好\n\nStephen(00:00:31):\n好的"
        assert detect_content_type(text) == CONTENT_TYPE_TRANSCRIPT

    def test_summary_via_pattern(self):
        text = "# 会议纪要\n## 主要结论\n讨论了项目进度"
        assert detect_content_type(text) == CONTENT_TYPE_SUMMARY

    def test_unknown_short(self):
        assert detect_content_type("") == CONTENT_TYPE_UNKNOWN
        assert detect_content_type("短") == CONTENT_TYPE_UNKNOWN


# ============================================================
# 向后兼容入口
# ============================================================

class TestLegacyEntrypoints:
    def test_parse_srt_delegates(self):
        text = "1\n00:00:01,000 --> 00:00:05,000\nHello"
        dlg = parse_srt(text)
        assert len(dlg) >= 1
        assert dlg[0]["sentences"][0]["text"] == "Hello"

    def test_parse_vtt_delegates(self):
        text = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\nHello"
        dlg = parse_vtt(text)
        assert len(dlg) >= 1
        assert dlg[0]["sentences"][0]["text"] == "Hello"

    def test_parse_markdown_transcript_delegates_to_best(self):
        # 独立行格式
        text1 = "张三(00:00:01):\n你好\n\n李四(00:00:02):\n好的"
        dlg1 = parse_markdown_transcript(text1)
        assert len(dlg1) == 2

        # 同行格式
        text2 = "**张三**：你好\n**李四**：好的"
        dlg2 = parse_markdown_transcript(text2)
        assert len(dlg2) == 2

        # 说话人N
        text3 = "说话人 1：你好\n说话人 2：好的"
        dlg3 = parse_markdown_transcript(text3)
        assert len(dlg3) == 2

    def test_parse_markdown_transcript_unknown_returns_empty(self):
        assert parse_markdown_transcript("没有任何说话人标注的普通文本") == []
