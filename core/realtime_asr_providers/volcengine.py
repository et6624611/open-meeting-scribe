"""core/realtime_asr_providers/volcengine.py — 火山引擎大模型流式 ASR。

协议：wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
  - 4 字节 header + 可选 sequence + 4 字节 payload size + payload
  - full client request / audio only / full server response 三类消息
  - JSON + gzip 压缩
"""

from __future__ import annotations

import gzip
import json
import logging
import struct
import uuid

from .base import WebSocketProviderBase

logger = logging.getLogger(__name__)

DEFAULT_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
# 豆包流式语音识别 2.0 小时版（按音频处理时长计费）
DEFAULT_RESOURCE_ID = "volc.seedasr.sauc.duration"

MSG_FULL_CLIENT = 0b0001
MSG_AUDIO_ONLY = 0b0010
MSG_SERVER_RESPONSE = 0b1001
MSG_ERROR = 0b1111

FLAG_NONE = 0b0000
FLAG_SEQUENCE = 0b0001
FLAG_FINAL = 0b0011

SERIAL_JSON = 0b0001
COMPRESS_GZIP = 0b0001


def _header(msg_type: int, flags: int, serial: int = 0, compress: int = 0) -> bytes:
    return bytes([
        (0x01 << 4) | 0x01,                 # version=1, header size=1
        (msg_type << 4) | flags,
        (serial << 4) | compress,
        0x00,
    ])


def _frame(msg_type: int, flags: int, payload: bytes, sequence: int | None = None,
           serial: int = 0, compress: int = 0) -> bytes:
    out = bytearray(_header(msg_type, flags, serial, compress))
    if sequence is not None:
        out.extend(struct.pack(">i", sequence))
    out.extend(struct.pack(">I", len(payload)))
    out.extend(payload)
    return bytes(out)


def _pick(data: dict, paths: list[str]):
    for path in paths:
        cur = data
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


class VolcengineProvider(WebSocketProviderBase):
    KEY = "volcengine"
    CHUNK_BYTES = 6400          # 200ms @ 16k/16bit/mono
    CONNECT_TIMEOUT = 10.0

    def __init__(self, credentials: dict, model: str = "bigmodel", **kwargs):
        super().__init__(**kwargs)
        self._credentials = credentials or {}
        self._model = model or "bigmodel"
        # full client request 由服务器隐式编号为 1（不带 sequence 字段），
        # 第一帧 audio 带 sequence=2 才能匹配服务器 autoAssignedSequence 计数器。
        self._sequence = 2
        self._emitted: set[tuple] = set()
        self._last_partial = ""
        self._request_id = str(uuid.uuid4())

    # ── 连接 ──────────────────────────────────────────────────

    def ws_url(self) -> str:
        url = self.options.get("base_url") or ""
        if url and not url.startswith(("ws://", "wss://")):
            logger.warning(f"[火山实时] base_url 不是 ws(s):// 协议 ({url})，使用默认端点")
            url = ""
        return url or DEFAULT_URL

    def ws_headers(self) -> dict:
        resource_id = (
            self._credentials.get("resource_id") or DEFAULT_RESOURCE_ID
        ).strip()
        return {
            "X-Api-Key": self._credentials.get("api_key", ""),
            "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()),
            "X-Api-Request-Id": self._request_id,
            "X-Api-Sequence": "-1",
        }

    async def on_open(self, ws) -> None:
        request = {
            "model_name": self._model,
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "show_utterances": True,
            "result_type": "full",
        }
        if self.options.get("enable_speaker"):
            # 文档：双向流式优化版开启 enable_speaker_info 必须同时开 enable_nonstream
            request["enable_nonstream"] = True
            request["enable_speaker_info"] = True
            request["ssd_version"] = "200"
        config = {
            "user": {"uid": "open-meeting-scribe"},
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": self.sample_rate,
                "bits": 16,
                "channel": 1,
            },
            "request": request,
        }
        payload = gzip.compress(json.dumps(config).encode("utf-8"))
        # full client request 不带 sequence，由服务器隐式编号为 1
        await ws.send(_frame(
            MSG_FULL_CLIENT, FLAG_NONE, payload,
            serial=SERIAL_JSON, compress=COMPRESS_GZIP,
        ))

    def encode_audio_frame(self, chunk: bytes) -> bytes:
        frame = _frame(
            MSG_AUDIO_ONLY, FLAG_SEQUENCE, chunk, sequence=self._sequence
        )
        self._sequence += 1
        return frame

    def send_final(self) -> bytes:
        return _frame(
            MSG_AUDIO_ONLY, FLAG_FINAL, b"", sequence=-self._sequence
        )

    # ── 解析 ──────────────────────────────────────────────────

    def decode_message(self, raw) -> list[dict]:
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if len(raw) < 4:
            return []
        header_size = (raw[0] & 0x0F) * 4
        msg_type = raw[1] >> 4
        flags = raw[1] & 0x0F
        compression = raw[2] & 0x0F
        pos = header_size
        if flags in (FLAG_SEQUENCE, FLAG_FINAL) and len(raw) >= pos + 4:
            pos += 4
        if len(raw) < pos + 4:
            return []
        size = struct.unpack(">I", raw[pos:pos + 4])[0]
        pos += 4
        payload = raw[pos:pos + size]
        if compression == COMPRESS_GZIP and payload:
            try:
                payload = gzip.decompress(payload)
            except Exception:
                pass

        if msg_type == MSG_ERROR:
            message = payload.decode("utf-8", "ignore")
            return [{"type": "error", "message": message[:300]}]
        if msg_type != MSG_SERVER_RESPONSE or not payload:
            return []

        try:
            data = json.loads(payload.decode("utf-8", "ignore"))
        except Exception:
            logger.debug(f"[火山实时] 无法解析响应: {payload[:120]!r}")
            return []

        code = data.get("code")
        if code not in (None, 0) and not data.get("result"):
            return [{"type": "error", "message": str(data.get("message") or code)[:300]}]

        result = data.get("result") or {}
        utterances = result.get("utterances") or []
        events: list[dict] = []

        for item in utterances:
            text = (item.get("text") or "").strip()
            if not text or not item.get("definite"):
                continue
            begin = int(item.get("start_time") or 0)
            end = int(item.get("end_time") or 0)
            key = (begin, end, text)
            if key in self._emitted:
                continue
            self._emitted.add(key)
            event = {
                "type": "sentence",
                "text": text,
                "begin_time": begin,
                "end_time": end,
            }
            label = _pick(item, self.options.get("speaker_label_paths") or [])
            if label is not None:
                event["speaker_label"] = str(label)
            events.append(event)

        if not events:
            partial = (result.get("text") or "").strip()
            if partial and partial != self._last_partial:
                self._last_partial = partial
                events.append({"type": "partial", "text": partial})
        return events
