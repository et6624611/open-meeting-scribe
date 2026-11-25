"""tests/test_realtime_speaker_resolver.py — 模型说话人优先与本机回退。"""

import core.diarization  # noqa: F401  （先加载依赖模块，避免循环导入）
from core.diarization_cluster import RealtimeSpeakerResolver


class FakeBase:
    def __init__(self):
        self.fed = 0
        self.stopped = False

    def feed_audio(self, pcm):
        self.fed += len(pcm)

    def get_speaker(self, begin_time=0, end_time=0):
        return 0

    def get_speaker_count(self):
        return 1

    def get_active_speaker_count(self, min_speech_sec=2.0):
        return 1

    def get_active_speaker_ids(self, min_speech_sec=2.0):
        return [0]

    def finalize(self):
        return 1

    def get_vad_stats(self):
        return {"speech_segments": 1, "silence_segments": 0, "speech_ratio": 1.0}

    def stop(self):
        self.stopped = True


def test_model_labels_skip_local_clustering():
    base = FakeBase()
    r = RealtimeSpeakerResolver(base=base, model_mode=True, diarization="auto")
    r.feed_audio(b"\x00\x00" * 100)

    assert r.resolve_sentence({"speaker_label": "A"}, 0, 1) == 0
    assert r.resolve_sentence({"speaker_label": "B"}, 1, 2) == 1
    assert r.resolve_sentence({"speaker_label": "A"}, 2, 3) == 0
    assert base.fed == 0
    assert r.get_speaker() == 0


def test_missing_labels_fall_back_to_local_with_offset():
    base = FakeBase()
    r = RealtimeSpeakerResolver(base=base, model_mode=True, diarization="auto")
    r.feed_audio(b"\x00\x00" * 400)

    # 第一句模型有标签 → id 0
    assert r.resolve_sentence({"speaker_label": "A"}, 0, 1) == 0
    # 后续连续 3 句无标签 → 启用本机回退，id 从 1 起编
    assert r.resolve_sentence({}, 1, 2) == -1
    r.feed_audio(b"\x00\x00" * 400)
    assert r.resolve_sentence({}, 2, 3) == -1
    sid = r.resolve_sentence({}, 3, 4)
    assert sid == 1
    assert base.fed > 0


def test_off_mode_returns_unknown():
    r = RealtimeSpeakerResolver(base=FakeBase(), model_mode=False, diarization="off")
    r.feed_audio(b"\x00\x00")
    assert r.resolve_sentence({"speaker_label": "A"}, 0, 1) == -1
    assert r.get_speaker() == -1
    assert r.get_speaker_count() == 0
    assert r.finalize() == 0


def test_local_mode_delegates():
    base = FakeBase()
    r = RealtimeSpeakerResolver(base=base, model_mode=False, diarization="auto")
    r.feed_audio(b"\x00\x00")
    assert base.fed == 2
    assert r.resolve_sentence({}, 0, 1) == 0
    assert r.get_speaker_count() == 1
    assert r.finalize() == 1
