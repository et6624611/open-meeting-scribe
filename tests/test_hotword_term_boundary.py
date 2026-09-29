"""
tests/test_hotword_term_boundary.py — ASCII 词条的词边界判定契约

曾经的缺陷：`apply_hotword_mappings` 与回溯修正都用 `\\b` 判定英文词边界，而 Python 的
Unicode 语义把汉字也算作 `\\w` —— 「与ES（」里 与 与 E 之间不存在 `\\b`。后果是中文会议里
最常见的形态（英文编码紧贴汉字）永远匹配不上：ES→EAS 配了不生效，配 residual 残扫又用
同一规则，连漏改告警都报 0。现统一走 core.hotwords.ascii_term_pattern（左右不挨其他
ASCII 字母/数字）。
"""

import pytest

from core.hotwords import apply_hotword_mappings, ascii_term_pattern, sub_term
from core.text_correction import count_term

# 从真实纪要里摘的形态：前三种必须命中，后三种必须不命中（否则会咬穿单词）
MUST_MATCH = [
    "与ES（EAS/星瀚ERP系统）",
    "与ES/EAS-B/财务系统单向同步",
    "讨论ES。",
    "聚焦 H2 上线",
]
MUST_NOT_MATCH = [
    "FILES 目录",       # ES 在单词内部
    "ESB主数据中转",     # ES 是 ESB 的前缀
    "CH2O 分子式",       # H2 在单词内部
]


@pytest.mark.parametrize("text", MUST_MATCH)
def test_ascii_term_glued_to_cjk_is_matched(text):
    _replaced, hits = sub_term(text, "ES" if "ES" in text else "H2", "X")

    assert hits == 1, f"{text!r} 应命中 1 处，实际 {hits}"


@pytest.mark.parametrize("text", MUST_NOT_MATCH)
def test_ascii_term_inside_a_word_is_not_matched(text):
    _replaced, hits = sub_term(text, "ES" if "ES" in text else "H2", "X")

    assert hits == 0, f"{text!r} 不应被改写，实际命中 {hits}"


def test_matching_is_case_insensitive():
    replaced, hits = sub_term("es 与 ES 都要对齐", "ES", "EAS")

    assert hits == 2
    assert replaced == "EAS 与 EAS 都要对齐"


def test_transcription_pipeline_shares_the_same_rule():
    """转写侧（apply_hotword_mappings）与回溯侧（sub_term）必须同口径。"""
    text = "本次讨论与ES（EAS/星瀚ERP系统）的对接"

    assert apply_hotword_mappings(text, [("ES", "EAS")]) == text.replace("与ES", "与EAS")


def test_count_term_agrees_with_sub_term():
    """残扫与替换共用一个 pattern：两者一旦分叉，漏改就会从告警里消失。"""
    for text in (*MUST_MATCH, *MUST_NOT_MATCH):
        replaced, hits = sub_term(text, "ES", "EAS")
        assert count_term(text, "ES") == hits, text


def test_pattern_escapes_regex_metacharacters_in_the_term():
    """词条可能含 + . 等元字符（如 C++ / v1.0），必须按字面匹配。"""

    assert ascii_term_pattern("C++").sub("X", "用C++写的") == "用X写的"
    assert ascii_term_pattern("A1").sub("X", "XA1B") == "XA1B"   # 挨着字母不匹配
