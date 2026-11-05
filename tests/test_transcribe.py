"""core/transcribe.py 单元测试：碎片合并、说话人归并、对话稿组装。

全部用固定 JSON fixture，无外部依赖，离线可跑。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import transcribe as t


# ── merge_fragments ────────────────────────────────────────────────


def _mk(text, begin, end, sid=0, sentence_id=0, words=None):
    return {
        "text": text,
        "begin_time": begin,
        "end_time": end,
        "speaker_id": sid,
        "sentence_id": sentence_id,
        "words": words or [],
    }


class TestMergeFragments:
    def test_empty(self):
        assert t.merge_fragments([]) == []

    def test_single_unchanged(self):
        one = [_mk("你好世界。", 0, 1000)]
        out = t.merge_fragments(one)
        assert len(out) == 1
        assert out[0]["text"] == "你好世界。"
        assert out[0]["begin_time"] == 0
        assert out[0]["end_time"] == 1000

    def test_fragment_short_gap_merges(self):
        # 第一句本身是碎片（<12字去标点）、gap < MERGE_GAP_MS → 应和下句合并
        # 注意：merge_fragments 是「当前句」驱动的——当前句完整（句末标点）时不会主动向下合并
        sents = [
            _mk("好的。", 0, 300),  # 碎片（去标点后 2 字）
            _mk("那我们开始今天的会议。", 350, 2000),
        ]
        out = t.merge_fragments(sents)
        assert len(out) == 1
        assert "好的" in out[0]["text"]
        assert "开始今天的会议" in out[0]["text"]
        assert out[0]["end_time"] == 2000

    def test_long_gap_breaks(self):
        sents = [
            _mk("第一段内容。", 0, 1000),
            _mk("第二段碎片。", 5000, 5500),  # gap=4000 > 2000
        ]
        out = t.merge_fragments(sents)
        assert len(out) == 2  # 不合并

    def test_incomplete_sentence_merges(self):
        # 第一句没以句末标点结尾 → 应合并
        sents = [
            _mk("让我们来讨论一下这个", 0, 1000),  # 没句号
            _mk("方案的可行性。", 1050, 2000),
        ]
        out = t.merge_fragments(sents)
        assert len(out) == 1
        assert "，" in out[0]["text"]  # 自动补了逗号连接器

    def test_word_split_bigram_merges(self):
        # 跨句拆词：上句末字 + 下句首字 组成 COMMON_BIGRAMS 里的词
        sents = [
            _mk("我们要优化", 0, 1000),
            _mk("流程和成本。", 1050, 2000),  # "流"+"程" = 流程（在 COMMON_BIGRAMS 里）
        ]
        out = t.merge_fragments(sents)
        assert len(out) == 1
        # 合并后应该有 "优化流程" 出现（中间自动补逗号）
        assert "优化，流程" in out[0]["text"] or "优化流程" in out[0]["text"]

    def test_preserves_sentence_id_and_words(self):
        words_a = [{"text": "大家", "begin": 0, "end": 100}]
        words_b = [{"text": "好", "begin": 1100, "end": 1200}]
        sents = [
            _mk("大家好", 0, 1100, sentence_id=3, words=words_a),
            _mk("世界。", 1150, 2000, sentence_id=4, words=words_b),
        ]
        out = t.merge_fragments(sents)
        assert len(out) == 1
        assert out[0]["sentence_id"] == 3  # 保留首句的 sentence_id
        assert len(out[0]["words"]) == 2  # words 被 extend
        assert out[0]["end_time"] == 2000


# ── correct_speaker_ids ───────────────────────────────────────────


class TestCorrectSpeakerIds:
    def test_too_short_list_unchanged(self):
        assert t.correct_speaker_ids([_mk("a", 0, 100)]) == [_mk("a", 0, 100)]
        assert t.correct_speaker_ids([_mk("a", 0, 100), _mk("b", 1100, 2000)])
        assert len(t.correct_speaker_ids([_mk("a", 0, 100), _mk("b", 1100, 2000)])) == 2

    def test_bridge_speaker_fix(self):
        # 中间句 speaker_id 异常，前后都是 sid=1 且 gap 都小
        sents = [
            _mk("甲发言第一段。", 0, 1500, sid=1),
            _mk("中间一句。", 1550, 2000, sid=2),  # 异常 speaker
            _mk("甲发言第三段。", 2050, 3500, sid=1),
        ]
        out = t.correct_speaker_ids(sents)
        assert out[1]["speaker_id"] == 1  # 被修正为前后一致

    def test_bridge_not_fixed_when_gap_large(self):
        sents = [
            _mk("甲发言。", 0, 1500, sid=1),
            _mk("中间。", 2500, 3000, sid=2),  # 与前句 gap=1000 > 800
            _mk("甲继续。", 3100, 4000, sid=1),
        ]
        out = t.correct_speaker_ids(sents)
        assert out[1]["speaker_id"] == 2  # 不修正，gap 太大

    def test_fragment_speaker_fix(self):
        # correct_speaker_ids 要求 len >= 3 才会工作
        sents = [
            _mk("张三说了一大段完整的发言内容。", 0, 2000, sid=1),
            _mk("好的。", 2100, 2300, sid=2),  # gap=100 < 500ms；碎片+不同 speaker
            _mk("王五也说了一段发言内容。", 3000, 4000, sid=3),
        ]
        out = t.correct_speaker_ids(sents)
        assert out[1]["speaker_id"] == 1

    def test_fragment_speaker_fix_not_triggered_on_long_sentence(self):
        sents = [
            _mk("张三说了一大段完整的发言内容。", 0, 2000, sid=1),
            _mk("李四也说了一大段完整的发言内容来回应。", 2050, 3500, sid=2),
        ]
        out = t.correct_speaker_ids(sents)
        assert out[1]["speaker_id"] == 2  # 不是碎片，不修正


# ── assemble_dialogue（端到端）────────────────────────────────────


SAMPLE_TRANSCRIPTION = {
    "transcripts": [
        {
            "sentences": [
                {"begin_time": 0, "end_time": 1500, "text": "大家好，欢迎参加今天的会议。",
                 "sentence_id": 0, "speaker_id": 0, "words": []},
                {"begin_time": 1550, "end_time": 2100, "text": "谢谢大家。",
                 "sentence_id": 1, "speaker_id": 0, "words": []},
                # 跨 speaker gap=3000-2100=900 > 2000？不，900 < 2000。
                # 那改成 gap=2500 隔开，防止 merge_fragments 跨 speaker 合并
                {"begin_time": 5000, "end_time": 6500, "text": "让我们来讨论一下今天的议题。",
                 "sentence_id": 2, "speaker_id": 1, "words": []},
                {"begin_time": 6550, "end_time": 7500, "text": "议题的重点在于预算和成本优化。",
                 "sentence_id": 3, "speaker_id": 1, "words": []},
            ]
        }
    ]
}


@pytest.fixture()
def _no_hotwords(monkeypatch):
    """assemble_dialogue 内部调 apply_hotword_mappings；测试直接文本时 identity 更稳。"""
    import core.transcribe as t
    monkeypatch.setattr(t, "apply_hotword_mappings", lambda text, **kw: text)


class TestAssembleDialogue:
    def test_empty_transcript(self, _no_hotwords):
        assert t.assemble_dialogue({}) == []
        assert t.assemble_dialogue({"transcripts": []}) == []
        assert t.assemble_dialogue({"transcripts": [{"sentences": []}]}) == []

    def test_groups_by_speaker_id(self, _no_hotwords):
        result = t.assemble_dialogue(SAMPLE_TRANSCRIPTION)
        # 两个 speaker_id → 2 条对话
        assert len(result) == 2
        spk_ids = [b["speaker_id"] for b in result]
        assert 0 in spk_ids
        assert 1 in spk_ids

    def test_merges_consecutive_same_speaker(self, _no_hotwords):
        result = t.assemble_dialogue(SAMPLE_TRANSCRIPTION)
        spk0 = next(b for b in result if b["speaker_id"] == 0)
        # merge_fragments 只合并「当前句驱动」的碎片化场景——当前句完整时不会主动合并
        # assemble_dialogue 的 speaker_id 归并会把同一 speaker_id 的连续句堆在一个 block 里
        assert len(spk0["sentences"]) == 2
        assert "大家好" in spk0["text"]
        assert "谢谢大家" in spk0["text"]

    def test_speaker1_not_merged_to_speaker0(self, _no_hotwords):
        result = t.assemble_dialogue(SAMPLE_TRANSCRIPTION)
        spk1 = next(b for b in result if b["speaker_id"] == 1)
        # speaker 不同的句子（跨 speaker gap 足够大）不合并
        assert len(spk1["sentences"]) == 2

    def test_speaker_fix_integration(self, _no_hotwords):
        # speaker 修正 + 碎片合并 联合工作
        raw = {
            "transcripts": [{
                "sentences": [
                    {"begin_time": 0, "end_time": 1500, "text": "甲说了一大段。",
                     "sentence_id": 0, "speaker_id": 0, "words": []},
                    {"begin_time": 1550, "end_time": 1800, "text": "对。",
                     "sentence_id": 1, "speaker_id": 1, "words": []},  # 碎片被错误分离
                    {"begin_time": 1850, "end_time": 3500, "text": "甲继续说下一段。",
                     "sentence_id": 2, "speaker_id": 0, "words": []},
                ]
            }]
        }
        result = t.assemble_dialogue(raw)
        # 碎片归并后应该只有 speaker_id=0 这一个对话块
        assert len(result) == 1
        assert result[0]["speaker_id"] == 0


# ── _sentence_ends_complete / _is_fragment / _detect_word_split ──


class TestHelperFuncs:
    def test_sentence_ends_complete(self):
        assert t._sentence_ends_complete("结束。")
        assert t._sentence_ends_complete("结束！")
        assert t._sentence_ends_complete("结束？")
        assert t._sentence_ends_complete("结束…")
        assert not t._sentence_ends_complete("没结束")
        assert not t._sentence_ends_complete("")
        assert not t._sentence_ends_complete("还没，")

    def test_is_fragment(self):
        assert t._is_fragment("嗯")
        assert t._is_fragment("好的。")
        assert t._is_fragment("对对对！")
        assert not t._is_fragment("这是一个比较长的句子应该不算碎片。")
        assert t._is_fragment("")  # 空串去标点后长度 0 < 12 → 也算碎片

    def test_detect_word_split(self):
        # "流" + "程" = "流程" → 在 COMMON_BIGRAMS
        assert t._detect_word_split("我们要优化流", "程和成本")
        assert not t._detect_word_split("我们要优化流", "x和成本")
        assert not t._detect_word_split("", "abc")
        assert not t._detect_word_split("abc", "")
        # 分句末标点不影响拆分检测
        assert t._detect_word_split("优化流，", "程")


# ── transcribe_audio 入口层 ───────────────────────────────────────


class TestTranscribeAudioEntry:
    def test_file_not_found(self, tmp_path, monkeypatch):
        missing = tmp_path / "nope.wav"
        with pytest.raises(FileNotFoundError):
            t.transcribe_audio(str(missing))

    def test_route_to_engine_override(self, tmp_path, monkeypatch):
        # engine_override 直接走对应分支，不需要真实路由配置
        fake_wav = tmp_path / "fake.wav"
        fake_wav.write_bytes(b"\x00" * 1024)

        called = {}

        def fake_proxy(*args, **kwargs):
            called["mode"] = "proxy"
            return [], {}

        def fake_cloud(*args, **kwargs):
            called["mode"] = "cloud"
            return [], {}

        def fake_local(*args, **kwargs):
            called["mode"] = "local"
            return [], {}

        def fake_direct(*args, **kwargs):
            called["mode"] = "direct"
            return [], {}

        monkeypatch.setattr(t, "_transcribe_proxy", fake_proxy)
        monkeypatch.setattr(t, "_transcribe_cloud", fake_cloud)
        monkeypatch.setattr(t, "_transcribe_local", fake_local)
        monkeypatch.setattr(t, "_transcribe_direct", fake_direct)

        for mode in ("proxy", "cloud", "local", "direct"):
            called.clear()
            t.transcribe_audio(str(fake_wav), engine_override=mode)
            assert called["mode"] == mode, f"engine_override={mode} 路由失败"

    def test_unknown_mode_falls_to_proxy(self, tmp_path, monkeypatch):
        fake_wav = tmp_path / "fake.wav"
        fake_wav.write_bytes(b"\x00" * 1024)

        called = {}

        def fake_proxy(*args, **kwargs):
            called["mode"] = "proxy"
            return [], {}

        monkeypatch.setattr(t, "_transcribe_proxy", fake_proxy)
        monkeypatch.setattr(t, "_get_asr_mode", lambda: "unknown-custom-mode")

        t.transcribe_audio(str(fake_wav))
        assert called["mode"] == "proxy"

    def test_no_route_raises(self, tmp_path, monkeypatch):
        fake_wav = tmp_path / "fake.wav"
        fake_wav.write_bytes(b"\x00" * 1024)

        monkeypatch.setattr(t, "_get_asr_mode", lambda: "")
        with pytest.raises(RuntimeError, match="ASR 转写来源未设置"):
            t.transcribe_audio(str(fake_wav))

    def test_file_too_large_1gb(self, tmp_path, monkeypatch):
        fake = tmp_path / "big.wav"
        fake.write_bytes(b"x")

        from unittest.mock import MagicMock

        real_stat_result = fake.stat()
        fake_result = MagicMock()
        fake_result.st_mode = real_stat_result.st_mode
        fake_result.st_ino = real_stat_result.st_ino
        fake_result.st_dev = real_stat_result.st_dev
        fake_result.st_nlink = real_stat_result.st_nlink
        fake_result.st_uid = real_stat_result.st_uid
        fake_result.st_gid = real_stat_result.st_gid
        fake_result.st_size = 1024 * 1024 * 1024 + 1  # > 1GB
        fake_result.st_atime = real_stat_result.st_atime
        fake_result.st_mtime = real_stat_result.st_mtime
        fake_result.st_ctime = real_stat_result.st_ctime

        # 3.12 的 Path.stat 会带 follow_symlinks 关键字，桩需透传任意参数
        monkeypatch.setattr(Path, "stat", lambda self, *args, **kwargs: fake_result)
        try:
            with pytest.raises(RuntimeError, match="文件过大"):
                t.transcribe_audio(str(fake))
        finally:
            monkeypatch.undo()


# ── _local_sentence_info_to_transcription ──────────────────────────


class TestLocalSentenceInfoMapping:
    def test_basic_mapping(self):
        raw = [
            {"start": 0, "end": 1500, "spk": 0, "text": "你好"},
            {"start": 1550, "end": 2500, "spk": 1, "text": "世界"},
        ]
        out = t._local_sentence_info_to_transcription(raw, diarization_enabled=True)
        sents = out["transcripts"][0]["sentences"]
        assert len(sents) == 2
        assert sents[0]["speaker_id"] == 0
        assert sents[1]["speaker_id"] == 1
        assert out["properties"]["original_duration_in_milliseconds"] == 2500

    def test_no_diarization_forces_spk0(self):
        raw = [
            {"start": 0, "end": 1000, "spk": 3, "text": "嗨"},
        ]
        out = t._local_sentence_info_to_transcription(raw, diarization_enabled=False)
        sents = out["transcripts"][0]["sentences"]
        assert sents[0]["speaker_id"] == 0

    def test_empty_list(self):
        out = t._local_sentence_info_to_transcription([])
        assert out["transcripts"][0]["sentences"] == []
        assert out["properties"]["original_duration_in_milliseconds"] == 0
