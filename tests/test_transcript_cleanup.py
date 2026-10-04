"""
tests/test_transcript_cleanup.py — 口语清理规则与分层派生契约（PLAN-TRANSCRIPT-LAYERING WP-1）

钉死的边界 / Contracted boundaries:
  - 填充词只在话语标记位置删除（「那个孩子」零误杀）；
  - 否定、自我纠正链、句尾情态词零改动；
  - 口吃合并三种形态：完全重复 / 前缀残段 / 后缀-前缀重叠；
  - 幂等：clean(clean(x)) == clean(x)；
  - 派生 helper：关闭时零行为变化；深拷贝隔离原文。
"""

import pytest

from core.transcript_cleanup import (
    clean_dialogue_for_consumers,
    clean_sentence,
    derive_layers,
    enrich_sentence,
)


# ── 填充词 ──────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    # 原型用例：句首 + 标点后 + 发语词 + 句尾啊
    ("嗯……那个，就是说我们下周三之前吧，得发出来啊。",
     "我们下周三之前吧，得发出来。"),
    ("呃，这个事我们再议。", "这个事我们再议。"),
    ("啊，那就这样。", "那就这样。"),
    ("他说的，嗯，我同意。", "他说的，我同意。"),
    ("就是说这个方案需要两周。", "这个方案需要两周。"),
    ("这事儿，怎么说呢，比较麻烦。", "这事儿，比较麻烦。"),
    ("先这样推，对吧。", "先这样推。"),
    ("好啊", "好"),
    # 英文：独立单词
    ("Uh, let's start.", "let's start."),
    ("um I think so", "I think so"),
    # 英文插入语：必须两侧停顿
    ("We need to, you know, ship it.", "We need to, ship it."),
    ("It's, kind of, okay.", "It's, okay."),
])
def test_fillers_removed_at_discourse_positions(raw, expected):
    assert clean_sentence(raw)["text"] == expected


@pytest.mark.parametrize("raw", [
    "那个孩子今天没来。",          # 限定词
    "这个问题我来答。",            # 限定词
    "就是这个意思。",              # 强调（后无停顿边界）
    "I like apples.",             # like 是动词
    "It looks kind of old.",      # kind of 无两侧标点，不删
    "你说的对吧？",                # 对吧前是实词（非停顿边界），不匹配
])
def test_filler_lookalikes_kept(raw):
    result = clean_sentence(raw)
    assert result["changed"] is False
    assert result["text"] == raw


# ── 红线：否定 / 自我纠正 / 情态 ─────────────────────────

@pytest.mark.parametrize("raw", [
    "我不是说不行，行吧，那就先这样。",
    "这个事吧……我不是说不行啊，嗯，行吧，那就先这样。",
    "他们用的是宽表，哦不对，是旷视那个，模型叫啥来着，Paraformer。",
    "不是A，是B。",
    "别删这句话。",
    "明天可能下雨，应该带伞。",
    "也许吧，我再想想。",
    "我没有说不做。",
])
def test_negation_correction_modality_untouched(raw):
    result = clean_sentence(raw)
    # 允许仅删除独立语气词（如「嗯」），但红线内容必须逐字保留
    for guarded in ("不是", "不行", "行吧", "哦不对", "宽表", "别", "可能",
                    "应该", "也许", "没有", "不做"):
        if guarded in raw:
            assert guarded in result["text"], f"{guarded!r} 不应被清理: {raw!r} → {result['text']!r}"


def test_oh_in_correction_chain_kept():
    """「哦」不入填充词表：自我纠正「哦不对」整段保留。"""
    raw = "是宽表，哦不对，是旷视。"
    assert clean_sentence(raw)["text"] == raw


# ── 口吃 / 重复 ─────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("得，得发出来。", "得发出来。"),                       # 前缀残段
    ("下周三，下周三之前。", "下周三之前。"),               # 后缀-前缀重叠
    ("我们下周三，下周三之前吧。", "我们下周三之前吧。"),   # 跨片段重叠
    ("方案，方案通过了。", "方案通过了。"),                 # 重叠
    ("可能，可能要再想想。", "可能要再想想。"),             # 情态词口吃仍合并（态度保留）
    ("好，好的。", "好的。"),
])
def test_stutter_merge(raw, expected):
    assert clean_sentence(raw)["text"] == expected


@pytest.mark.parametrize("raw", [
    "我们讨论一下，下午三点开会。",   # 「一下/下午」L1 巧合不合并
    "他去年去过，年会也参加了。",     # 无重叠
    "好好好，那就这么定。",           # 无标点叠字不处理
])
def test_non_stutter_kept(raw):
    assert clean_sentence(raw)["text"] == raw


# ── 标点与形态 ──────────────────────────────────────────

def test_ellipsis_forms():
    # 句首悬挂省略号（filler 残留）剥离
    assert clean_sentence("呃。。。那个方案。")["text"] == "那个方案。"
    assert clean_sentence("嗯...行吧")["text"] == "行吧"
    # 句中省略号是真实停顿，保留
    assert "……" in clean_sentence("这个事吧……我不是说不行。")["text"]


def test_punct_collision_and_empty():
    assert clean_sentence("呃，啊，那个，")["text"] == ""
    assert clean_sentence("")["text"] == ""
    assert clean_sentence("   ")["changed"] is False


def test_number_punctuation_protected():
    raw = "预算大概 1,000.50 元。"
    assert clean_sentence(raw)["text"] == raw


def test_english_punctuation_keeps_space():
    result = clean_sentence("Uh, we need to ship it tomorrow, right?")
    assert result["text"] == "we need to ship it tomorrow, right?"


@pytest.mark.parametrize("raw", [
    "嗯……那个，就是说我们下周三之前吧，得发出来啊。",
    "我们下周三，下周三之前吧。",
    "呃，啊，那个，",
    "Uh, you know, it's, like, fine.",
])
def test_idempotent(raw):
    once = clean_sentence(raw)["text"]
    twice = clean_sentence(once)["text"]
    assert twice == once


def test_ops_bookkeeping():
    result = clean_sentence("嗯，呃，得，得发出来。")
    rules = {op["r"]: op for op in result["ops"]}
    assert "filler" in rules
    assert rules["filler"]["n"] == len(rules["filler"]["items"]) == 2
    assert rules["dup"]["items"] == ["得"]
    assert result["text"] == "得发出来。"


# ── derive_layers：实时咽喉契约 ─────────────────────────

def test_derive_layers_disabled_is_passthrough():
    raw = "嗯，那个方案。"
    layers = derive_layers(raw, enabled=False)
    assert layers == {"clean_text": None, "clean_ops": None, "feed_text": raw}


def test_derive_layers_enabled_no_change():
    raw = "会议定在十点。"
    layers = derive_layers(raw, enabled=True)
    assert layers["clean_text"] is None
    assert layers["feed_text"] == raw


def test_derive_layers_enabled_changed():
    layers = derive_layers("呃，开会吧。", enabled=True)
    assert layers["clean_text"] == "开会吧。"
    assert layers["feed_text"] == "开会吧。"
    assert any(op["r"] == "filler" for op in layers["clean_ops"])


def test_derive_layers_all_filler_sentence_feeds_empty():
    layers = derive_layers("呃，啊，那个，", enabled=True)
    assert layers["clean_text"] == ""
    assert layers["feed_text"] == ""


# ── enrich_sentence：展示富化 ───────────────────────────

def test_enrich_sentence_adds_fields_only_when_changed():
    sent = {"text": "呃，开会吧。", "sentence_id": 1}
    enrich_sentence(sent)
    assert sent["clean_text"] == "开会吧。"
    assert "clean_ops" in sent

    untouched = {"text": "会议定在十点。", "sentence_id": 2}
    enrich_sentence(untouched)
    assert "clean_text" not in untouched
    assert "clean_ops" not in untouched


# ── clean_dialogue_for_consumers：深拷贝隔离 ────────────

def _sample_dialogue():
    return [
        {"speaker_id": 0, "sentences": [
            {"sentence_id": 0, "text": "嗯，那个方案，得，得发出来。"},
            {"sentence_id": 1, "text": "会议定在十点。"},
        ]},
    ]


def test_consumer_dialogue_disabled_returns_same_object():
    dialogue = _sample_dialogue()
    assert clean_dialogue_for_consumers(dialogue, enabled=False) is dialogue


def test_consumer_dialogue_enabled_deepcopies_and_cleans():
    dialogue = _sample_dialogue()
    cloned = clean_dialogue_for_consumers(dialogue, enabled=True)
    assert cloned is not dialogue
    assert cloned[0] is not dialogue[0]
    assert cloned[0]["sentences"][0]["text"] == "那个方案，得发出来。"
    # 原文事实源不动
    assert dialogue[0]["sentences"][0]["text"] == "嗯，那个方案，得，得发出来。"
    # 无变化句保持文本
    assert cloned[0]["sentences"][1]["text"] == "会议定在十点。"
