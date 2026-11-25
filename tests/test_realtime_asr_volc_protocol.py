"""tests/test_realtime_asr_volc_protocol.py — 火山二进制协议编解码。"""

import gzip
import json
import struct

from core.realtime_asr_providers.volcengine import (
    COMPRESS_GZIP,
    FLAG_FINAL,
    FLAG_SEQUENCE,
    MSG_AUDIO_ONLY,
    MSG_SERVER_RESPONSE,
    SERIAL_JSON,
    VolcengineProvider,
    _frame,
)


def _provider():
    return VolcengineProvider(
        credentials={"api_key": "k", "resource_id": "volc.seedasr.sauc.duration"},
        options={"speaker_label_paths": ["speaker", "speaker_id"]},
    )


def test_audio_frame_header_and_sequence():
    p = _provider()
    frame = p.encode_audio_frame(b"\x00\x01" * 4)
    assert frame[0] == 0x11
    assert frame[1] >> 4 == MSG_AUDIO_ONLY
    assert frame[1] & 0x0F == FLAG_SEQUENCE
    seq = struct.unpack(">i", frame[4:8])[0]
    size = struct.unpack(">I", frame[8:12])[0]
    assert seq == 1
    assert size == 8
    assert p.encode_audio_frame(b"x")[4:8] == struct.pack(">i", 2)


def test_final_frame_is_negative_sequence():
    p = _provider()
    frame = p.send_final()
    assert frame[1] & 0x0F == FLAG_FINAL
    assert struct.unpack(">i", frame[4:8])[0] < 0
    assert struct.unpack(">I", frame[8:12])[0] == 0


def test_registry_paths_decode_additions_speaker_id():
    """豆包真实返回把说话人放在 utterances[].additions.speaker_id。"""
    from core.realtime_asr_providers.registry import get_spec

    p = VolcengineProvider(
        credentials={"api_key": "k", "resource_id": "volc.seedasr.sauc.duration"},
        options={"speaker_label_paths": get_spec("volcengine").speaker_label_paths},
    )
    payload = json.dumps({
        "result": {
            "text": "你好",
            "utterances": [
                {"text": "你好", "start_time": 120, "end_time": 900,
                 "definite": True, "additions": {"speaker_id": "2"}},
            ],
        },
    }).encode("utf-8")
    raw = _frame(
        MSG_SERVER_RESPONSE, 0, gzip.compress(payload),
        serial=SERIAL_JSON, compress=COMPRESS_GZIP,
    )
    assert p.decode_message(raw)[0]["speaker_label"] == "2"


def test_decode_definite_sentence_with_speaker():
    payload = json.dumps({
        "result": {
            "text": "你好",
            "utterances": [
                {"text": "你好", "start_time": 120, "end_time": 900,
                 "definite": True, "speaker": "2"},
            ],
        },
    }).encode("utf-8")
    raw = _frame(
        MSG_SERVER_RESPONSE, 0, gzip.compress(payload),
        serial=SERIAL_JSON, compress=COMPRESS_GZIP,
    )
    events = _provider().decode_message(raw)
    assert events == [{
        "type": "sentence",
        "text": "你好",
        "begin_time": 120,
        "end_time": 900,
        "speaker_label": "2",
    }]


def test_decode_partial_text_and_dedup():
    p = _provider()
    payload = json.dumps({"result": {"text": "正在说", "utterances": []}}).encode("utf-8")
    raw = _frame(MSG_SERVER_RESPONSE, 0, gzip.compress(payload),
                 serial=SERIAL_JSON, compress=COMPRESS_GZIP)
    assert p.decode_message(raw) == [{"type": "partial", "text": "正在说"}]
    assert p.decode_message(raw) == []
