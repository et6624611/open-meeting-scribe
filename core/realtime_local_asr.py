"""
core/realtime_local_asr.py — R9 本地分段增量上屏转写器（WP-I）

REQ-LOCAL-REALTIME-INCR v0.3.0 锁定口径：
  - D-I1：单段失败/超时 → 只丢该段、保留引擎（进程级健康由 EngineHost 两级语义负责，
    连续超时达阈值才重启，见 core/engine_host.py）；
  - D-I2：增量段拼接即定稿，会后不重跑全量（定稿路径见 core/pipeline_runner.py，
    由 record.stop_record 打 transcript_finalized_incremental 标记）；
  - D-I3：段长不拍固定数值，min_segment_s / min_silence_s / max_segment_s 全部
    可配置（app/settings_store.get_engine_config → local.realtime_segments；
    当前默认 5 / 0.8 / 30 为临时口径，待真机 20s/60s 各一场会延迟分布后由产品定值）。

目标（AC-9）：段闭合→上屏 P50 ≤8s、P95 ≤20s；音频完整性 <1s 漂移/30min。

三个坑的处置（派工单明令）：
  1. FunASR `spk` 是本次运行内局部编号、跨段不稳定 → 本转写器**不透传 spk**，
     只产出绝对时间轴上的 {text, begin_time, end_time}；跨段说话人归属复用
     record.py 既有接线：diarizer.feed_audio（PCM 双喂）+ SpeakerDiarizer.get_speaker
     （core/diarization_cluster.py 增量聚类）。
  2. 热词映射每段闭合时都过一遍（core.hotwords.apply_hotword_mappings，带缓存）。
  3. 内存不破 AC-3（16GB 机型 30min 峰值 ≤8GB）：PCM 只保留当前段缓冲
     （max_segment_s=30s ≈ 960KB），段闭合即写临时 wav 推理后立删；
     待推理队列有界（超限丢段并计数），不累积全量音频。

鸭子接口与 core.realtime_asr.RealtimeTranscriber 对齐：
  start() / feed_audio(pcm) / stop() / is_running / sentence_count，
  构造回调 on_partial / on_sentence_end / on_error / on_complete。
  注：on_partial 不使用（分段批推理无中间态；增量上屏由逐段 on_sentence_end 达成，
  前端复用既有 sentence 消息类型，无需 UI 改动）。
"""

import logging
import queue
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

from core.engine_host import ENGINE_REQUEST_TIMEOUT, estimate_local_asr_timeout, get_engine_host
from core.errors import LocalEngineError
from core.hotwords import apply_hotword_mappings

logger = logging.getLogger(__name__)

# PCM 口径：与 core/audio.py 流式录音一致（16kHz / 16bit / mono）
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
_BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH
# 每毫秒字节数（16000×2/1000）；用于绝对时间轴换算
_BYTES_PER_MS = _BYTES_PER_SECOND / 1000.0

# 能量 VAD 静音判定阈值（RMS，int16 满幅 32768 → ≈ -40 dBFS）。
# 仅用于段边界切分；段内句级 VAD 由 FunASR fsmn-vad 负责，阈值粗粒度可接受。
SILENCE_RMS_THRESHOLD = 300.0

# 待推理段队列上限（背压保护）：超限丢最旧段并计数（内存 AC-3 防线之一）。
# 推理 RTF≈0.081（Spike 实测）远快于实时，正常永不触顶；触顶即说明引擎已
# 严重滞后，此时保内存优先于保全量上屏（最终定稿仍有 stage1 批转写兜底）。
MAX_PENDING_SEGMENTS = 12

# stop() 排空等待上限（秒）。正常仅余 0~1 段（数秒内完成）；上限防引擎卡死时
# 阻塞 stop HTTP 请求过久。
DRAIN_JOIN_TIMEOUT = 300.0


class _Segment:
    """闭合段：PCM 数据 + 绝对时间轴偏移。"""

    __slots__ = ("pcm", "offset_ms", "duration_s")

    def __init__(self, pcm: bytes, offset_ms: int, duration_s: float):
        self.pcm = pcm
        self.offset_ms = offset_ms
        self.duration_s = duration_s


class LocalSegmentTranscriber:
    """本地引擎分段增量转写器（R9 / WP-I）。

    与 RealtimeTranscriber 鸭子兼容，供 record.py 在
    「local 模式 + realtime_segments.enabled」时替换使用。
    """

    # record.stop_record 以此标记识别增量定稿路径（D-I2）
    is_local_incremental = True

    def __init__(
        self,
        on_partial=None,
        on_sentence_end=None,
        on_error=None,
        on_complete=None,
        on_status=None,
        segment_config: dict | None = None,
        **_ignored,
    ):
        self._on_sentence_end = on_sentence_end
        self._on_error = on_error
        self._on_complete = on_complete
        # 非错误状态声明回调（AC-I2：丢段推 segment_skipped 提示，绝不推 error）
        self._on_status = on_status
        cfg = segment_config or {}
        # D-I3：段参数全部可配置；默认值为临时口径（待真机校准）
        self.min_segment_s = float(cfg.get("min_segment_s", 5.0))
        self.min_silence_s = float(cfg.get("min_silence_s", 0.8))
        self.max_segment_s = float(cfg.get("max_segment_s", 30.0))

        self._started = False
        self._sentence_count = 0
        self.segments_inferred = 0
        self.segments_dropped = 0

        # 当前段缓冲（仅一段，AC-3 内存防线）
        self._buf = bytearray()
        self._buf_silence_bytes = 0        # 当前段尾部连续静音字节数
        self._offset_ms = 0                # 当前段在整场音频中的绝对起点（ms）
        self._feed_lock = threading.Lock() # feed_audio 来自 stream_reader 单线程，锁仅防 stop 竞态

        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None

    # ── 生命周期（与 RealtimeTranscriber 鸭子对齐） ──

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def sentence_count(self) -> int:
        return self._sentence_count

    def start(self) -> None:
        """启动分段转写：预检并拉起常驻引擎子进程，起推理工作线程。

        Raises:
            LocalEngineError: 模型未就绪/引擎拉起失败（真实故障，由 record.py 推 error）
        """
        if self._started:
            raise RuntimeError("实时转写已在运行中")

        # 引擎预检 + 预热（冻结态冷启动可达 86s，必须在录音开始后尽早完成；
        # 失败抛分类 LocalEngineError，与 WP-H「真实故障仍按失败处理」口径一致）
        start_result = get_engine_host().start()
        if not start_result.get("ok"):
            from core.engine_host import _cloud_fallback_available
            raise LocalEngineError(
                start_result.get("error", "本地引擎启动失败"),
                error_code=start_result.get("error_code", "engine_unhealthy"),
                can_fallback_cloud=_cloud_fallback_available(),
                detail=start_result.get("detail", {}),
            )

        self._started = True
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="local-segment-asr"
        )
        self._worker.start()
        logger.info(
            f"[本地分段] 转写器已启动: min_segment={self.min_segment_s}s, "
            f"min_silence={self.min_silence_s}s, max_segment={self.max_segment_s}s"
        )

    def feed_audio(self, pcm_data: bytes) -> None:
        """接收 PCM（16k/16bit/mono，stream_reader 线程 100ms 块）；只做轻量切段，不阻塞。"""
        if not self._started or not pcm_data:
            return
        with self._feed_lock:
            if not self._started:
                return
            self._buf.extend(pcm_data)
            if self._is_silent(pcm_data):
                self._buf_silence_bytes += len(pcm_data)
            else:
                self._buf_silence_bytes = 0

            buf_s = len(self._buf) / _BYTES_PER_SECOND
            silence_s = self._buf_silence_bytes / _BYTES_PER_SECOND
            if (buf_s >= self.min_segment_s and silence_s >= self.min_silence_s) or \
                    buf_s >= self.max_segment_s:
                self._close_segment()

    def stop(self) -> None:
        """停止：当前缓冲作为末段闭合，排空推理队列后触发 on_complete。"""
        if not self._started:
            return
        with self._feed_lock:
            self._started = False
            # 末段不足 min_segment_s 也闭合（音频完整性：<1s 漂移口径要求不丢尾部）
            if len(self._buf) >= int(0.2 * _BYTES_PER_SECOND):
                self._close_segment()
        self._queue.put(None)  # 排空哨兵（FIFO：先处理完已入队段）
        if self._worker:
            self._worker.join(timeout=DRAIN_JOIN_TIMEOUT)
            if self._worker.is_alive():
                logger.warning(
                    f"[本地分段] 排空超时（{DRAIN_JOIN_TIMEOUT:.0f}s），"
                    f"未处理段数≈{self._queue.qsize()}（定稿仍走已上屏内容）"
                )
        logger.info(
            f"[本地分段] 转写器停止: 段推理={self.segments_inferred}, "
            f"段丢弃={self.segments_dropped}, 定稿句={self._sentence_count}"
        )
        if self._on_complete:
            try:
                self._on_complete()
            except Exception as e:
                logger.warning(f"[本地分段] on_complete 回调异常: {e}")

    # ── 切段 ──

    @staticmethod
    def _is_silent(pcm_data: bytes) -> bool:
        """能量 VAD：整块 RMS 低于阈值视为静音块（100ms 粒度足够切段用）。"""
        try:
            samples = np.frombuffer(pcm_data, dtype=np.int16)
            if samples.size == 0:
                return True
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
            return rms < SILENCE_RMS_THRESHOLD
        except Exception:
            return False

    def _close_segment(self) -> None:
        """闭合当前段并入队（调用方须持 _feed_lock）。队列满时丢最旧段（背压）。"""
        pcm = bytes(self._buf)
        duration_s = len(pcm) / _BYTES_PER_SECOND
        seg = _Segment(pcm=pcm, offset_ms=int(self._offset_ms), duration_s=duration_s)
        self._offset_ms += int(len(pcm) / _BYTES_PER_MS)
        self._buf = bytearray()
        self._buf_silence_bytes = 0

        while self._queue.qsize() >= MAX_PENDING_SEGMENTS:
            try:
                dropped = self._queue.get_nowait()
            except queue.Empty:
                break
            if dropped is None:  # 不误吞停止哨兵
                self._queue.put(None)
                break
            self.segments_dropped += 1
            logger.warning(
                f"[本地分段] 待推理队列满（{MAX_PENDING_SEGMENTS}），丢弃最旧段"
                f"（{dropped.duration_s:.1f}s @ {dropped.offset_ms}ms）——引擎推理严重滞后"
            )
            self._notify_skipped(
                dropped,
                f"一个音频段因引擎处理滞后被跳过（{dropped.duration_s:.1f}s @ "
                f"{dropped.offset_ms / 1000:.0f}s 处），录音不受影响",
            )
        self._queue.put(seg)

    # ── 推理工作线程 ──

    def _notify_skipped(self, seg: "_Segment", reason: str) -> None:
        """丢段时推非错误状态声明（AC-I2）：绝不经 on_error（红色报错）。"""
        if self._on_status:
            try:
                self._on_status({
                    "status": "segment_skipped",
                    "message": reason,
                    "offset_ms": seg.offset_ms,
                    "duration_s": round(seg.duration_s, 1),
                })
            except Exception as e:
                logger.warning(f"[本地分段] on_status 回调异常: {e}")

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            try:
                self._infer_segment(item)
            except Exception as e:
                # D-I1：单段失败/超时只丢该段，保留引擎、继续后续段。
                # 进程级不健康由 EngineHost 连续超时阈值负责重启；此处不上抛、
                # 不推 on_error（红色报错），推非错误 segment_skipped 状态声明。
                self.segments_dropped += 1
                reason = (
                    f"一个音频段处理失败已跳过（{item.duration_s:.1f}s @ "
                    f"{item.offset_ms / 1000:.0f}s 处），录音与后续转写不受影响"
                )
                logger.warning(
                    f"[本地分段] 段推理失败，丢弃该段并继续（{item.duration_s:.1f}s "
                    f"@ {item.offset_ms}ms）: {e}"
                )
                self._notify_skipped(item, reason)

    def _infer_segment(self, seg: _Segment) -> None:
        """单段推理：临时 wav → EngineHost.infer(asr) → 逐句回调（绝对时间轴）。"""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="oms_seg_", suffix=".wav", delete=False
            ) as tf:
                tmp_path = tf.name
            with wave.open(tmp_path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(SAMPLE_WIDTH)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(seg.pcm)

            timeout = max(estimate_local_asr_timeout(seg.duration_s), float(ENGINE_REQUEST_TIMEOUT))
            resp = get_engine_host().infer("asr", {"audio_path": tmp_path}, timeout=timeout)
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    pass

        self.segments_inferred += 1
        sentence_info = resp.get("sentence_info") or []
        emitted = 0
        for sent in sentence_info:
            text = (sent.get("text") or "").strip()
            if not text:
                continue
            # 坑②：热词映射每段闭合时都过一遍（带缓存，代价可忽略）
            text = apply_hotword_mappings(text)
            # 坑①：不透传 FunASR 局部 spk；说话人归属由 record.py 的
            # SpeakerDiarizer.get_speaker(begin, end) 增量聚类完成
            payload = {
                "text": text,
                "begin_time": seg.offset_ms + int(sent.get("start", 0)),
                "end_time": seg.offset_ms + int(sent.get("end", 0)),
            }
            self._sentence_count += 1
            emitted += 1
            if self._on_sentence_end:
                self._on_sentence_end(payload)
        logger.info(
            f"[本地分段] 段闭合上屏: {seg.duration_s:.1f}s @ {seg.offset_ms}ms → "
            f"{emitted} 句（累计 {self._sentence_count}）"
        )
