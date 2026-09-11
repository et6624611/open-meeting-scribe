"""
app/store.py — 共享状态层

作者：王永亮
创建：2026-09-03
版本：1.0.0

集中管理所有跨路由的共享状态、配置常量与辅助函数。
各 router 模块通过 import 引用，避免循环依赖。
"""

import os
import json
import time
import struct
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np

from dotenv import load_dotenv
load_dotenv()

from core.pipeline import run_pipeline_stage1, run_pipeline_stage2, PipelineProgress
from core.summarize import parse_todos_from_summary
from core.realtime_asr import RealtimeTranscriber
from core.realtime_summary import RealtimeSummarizer
from core.realtime_chapters import RealtimeChapterGenerator
from core.diarization import SpeakerDiarizer
from core.errors import is_transient_error, classify_error
from core import speakers
from core import voiceprint
from core import text_bridge
from core import joblog

# speaker_count 估算范围上下限
SPEAKER_COUNT_MIN = 1
SPEAKER_COUNT_MAX = 10

# 自动重试配置（仅针对瞬时错误）
PIPELINE_MAX_RETRIES = 2
PIPELINE_RETRY_DELAYS = [2, 5]  # 秒

logger = logging.getLogger(__name__)

# ============================================================
# 配置常量
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

OUTPUT_DIR = Path("data/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

RECORDINGS_DIR = Path("data/recordings")
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

TASKS_DIR = Path("data/tasks")
TASKS_DIR.mkdir(parents=True, exist_ok=True)


def infer_task_source(task: dict) -> str:
    """推断任务来源：'record'（录音）或 'upload'（上传）。

    优先使用显式 source 字段；缺失时通过 audio_path 位置推断：
    - data/recordings/ 目录下 → 录音
    - data/uploads/ 目录下 → 上传
    - 均不匹配时默认 'upload'
    """
    source = task.get("source")
    if source in ("record", "upload"):
        return source
    audio_path = task.get("audio_path", "")
    if "recordings" in audio_path:
        return "record"
    if "uploads" in audio_path:
        return "upload"
    return "upload"  # 默认

HOTWORDS_FILE = Path("data/hotwords.txt")
HOTWORD_MAPPINGS_FILE = Path("data/hotword_mappings.txt")
SETTINGS_FILE = Path("data/settings.json")
PHILOSOPHIES_FILE = Path("data/philosophies.json")

# 录制设备名（默认麦克风，可通过环境变量覆盖；线上会议戴耳机场景可改为 "BlackHole 2ch"）
RECORD_DEVICE = os.getenv("RECORD_DEVICE", "MacBook Pro麦克风")

# ============================================================
# 共享状态
# ============================================================

# 任务存储（内存，重启丢失；生产环境应持久化）
tasks: dict[str, dict] = {}

# 实时转写状态（task_id → 相关信息）
realtime_queues: dict[str, asyncio.Queue] = {}       # WebSocket 消息队列
realtime_transcribers: dict[str, RealtimeTranscriber] = {}  # 实时转写器
realtime_diarizers: dict[str, SpeakerDiarizer] = {}  # 声纹聚类器
realtime_summarizers: dict[str, RealtimeSummarizer] = {}  # 实时总结器
realtime_chapter_generators: dict[str, RealtimeChapterGenerator] = {}  # 实时章节生成器
realtime_transcript_buffers: dict[str, list[dict]] = {}  # 实时转写缓冲（task_id → 最近 N 条句子）
realtime_full_transcripts: dict[str, list[dict]] = {}  # 全量实时转写（task_id → 所有句子，供文本桥接匹配）
realtime_speaker_maps: dict[str, dict[int, str]] = {}  # 实时说话人绑定（task_id → {speaker_id: speaker_uuid}）
event_loop: asyncio.AbstractEventLoop | None = None  # 主事件循环引用

# 静默检测状态（task_id → 相关信息，详见 docs/design/SILENCE_DETECTION.md）
realtime_last_heartbeat: dict[str, float] = {}       # 最后心跳时间戳
realtime_last_sentence: dict[str, float] = {}         # 最后 ASR 定稿句子时间戳
realtime_presence_scores: dict[str, float] = {}       # 前端上报的存在性评分
realtime_silence_warnings: dict[str, int] = {}        # 已发送提醒次数
realtime_silence_monitors: dict[str, asyncio.Task] = {}  # 静默监测协程任务

# 实时转写缓冲区最大条目数
REALTIME_BUFFER_MAX = 10

# ============================================================
# 持久化辅助函数
# ============================================================


def save_task_to_disk(task_id: str) -> None:
    """将任务数据持久化到磁盘（JSON 文件）"""
    task = tasks.get(task_id)
    if not task:
        return
    try:
        # 排除 transcription 字段（原始 ASR 返回数据，体积大且无实际消费场景）
        task_for_disk = {k: v for k, v in task.items() if k != "transcription"}
        task_file = TASKS_DIR / f"{task_id}.json"
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task_for_disk, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存任务到磁盘失败: {e}")


def _try_recover_orphan_recording(task: dict, task_id: str) -> bool:
    """
    尝试恢复孤儿录音：将 raw PCM 文件转为 WAV，保留任务供用户后续处理。

    Returns:
        True 表示恢复成功，False 表示无可恢复的音频数据。
    """
    audio_path_str = task.get("audio_path", "")
    if not audio_path_str:
        return False

    audio_path = Path(audio_path_str)
    # 推导 raw 文件路径（与 wav 同目录，同前缀，扩展名 .raw）
    raw_path = audio_path.with_suffix(".raw")

    if not raw_path.exists() or raw_path.stat().st_size == 0:
        return False

    # 将 raw PCM 转为 WAV（16kHz, mono, 16-bit）
    sample_rate = 16000
    channels = 1
    bits = 16
    data_size = raw_path.stat().st_size
    duration = data_size / (sample_rate * channels * bits // 8)

    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8

    try:
        with open(raw_path, "rb") as fin, open(audio_path, "wb") as fout:
            fout.write(b"RIFF")
            fout.write(struct.pack("<I", 36 + data_size))
            fout.write(b"WAVE")
            fout.write(b"fmt ")
            fout.write(struct.pack("<I", 16))
            fout.write(struct.pack("<H", 1))  # PCM
            fout.write(struct.pack("<H", channels))
            fout.write(struct.pack("<I", sample_rate))
            fout.write(struct.pack("<I", byte_rate))
            fout.write(struct.pack("<H", block_align))
            fout.write(struct.pack("<H", bits))
            fout.write(b"data")
            fout.write(struct.pack("<I", data_size))
            while True:
                chunk = fin.read(65536)
                if not chunk:
                    break
                fout.write(chunk)

        # 删除 raw 文件
        raw_path.unlink(missing_ok=True)

        # 更新任务状态为 pending，供用户触发处理
        task["status"] = "pending"
        task["progress"] = 0
        task["message"] = "服务重启前正在录制，音频已恢复，等待处理"
        task["audio_duration"] = round(duration, 1)
        task["_recovered_from_orphan"] = True
        tasks[task_id] = task
        save_task_to_disk(task_id)

        logger.info(
            f"[恢复] {task_id[:8]}: raw → WAV 完成，时长 {duration:.0f}s ({duration/60:.1f} 分钟)"
        )
        return True

    except Exception as e:
        logger.error(f"[恢复] {task_id[:8]}: raw → WAV 失败: {e}")
        return False


def load_tasks_from_disk() -> None:
    """启动时从磁盘恢复任务到内存（含迁移：剔除旧文件中的 transcription 字段）"""
    try:
        migrated = 0
        orphan_recording = 0
        speaker_count_fixed = 0
        for task_file in TASKS_DIR.glob("*.json"):
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)
            task_id = task.get("task_id")
            if task_id:
                # 迁移：若含 transcription 字段则剔除并回写
                if "transcription" in task:
                    del task["transcription"]
                    with open(task_file, "w", encoding="utf-8") as fw:
                        json.dump(task, fw, ensure_ascii=False, indent=2)
                    migrated += 1
                # 迁移：补充 meeting_date（从 created_at 提取）
                if not task.get("meeting_date") and task.get("created_at"):
                    try:
                        dt = datetime.fromisoformat(task["created_at"])
                        task["meeting_date"] = dt.strftime("%Y-%m-%d")
                        with open(task_file, "w", encoding="utf-8") as fw:
                            json.dump(task, fw, ensure_ascii=False, indent=2)
                        migrated += 1
                    except (ValueError, TypeError):
                        pass
                # 迁移：修正 speaker_count（旧版误用对话条目数，应为去重说话人数）
                dialogue = task.get("dialogue")
                if dialogue and isinstance(dialogue, list):
                    correct_count = len({d.get("speaker_id") for d in dialogue if d.get("speaker_id") is not None})
                    if task.get("speaker_count") != correct_count:
                        old = task.get("speaker_count")
                        task["speaker_count"] = correct_count
                        with open(task_file, "w", encoding="utf-8") as fw:
                            json.dump(task, fw, ensure_ascii=False, indent=2)
                        speaker_count_fixed += 1
                        logger.info(f"[迁移] {task_id[:8]} speaker_count: {old} → {correct_count}")
                # 恢复孤儿录音：服务重启后实时资源已丢失，但 raw 音频数据可能仍在
                if task.get("status") in ("recording", "paused"):
                    recovered = _try_recover_orphan_recording(task, task_id)
                    if recovered:
                        orphan_recording += 1  # 复用计数器，日志中标记为"已恢复"
                        continue
                    # 无可用音频数据，清理任务文件
                    task_file.unlink(missing_ok=True)
                    joblog_file = TASKS_DIR / f"{task_id}.joblog.jsonl"
                    joblog_file.unlink(missing_ok=True)
                    orphan_recording += 1
                    continue
                # 清理历史遗留的无内容 failed 任务（之前重启标记的孤儿，无音频/对话/摘要）
                if (task.get("status") == "failed"
                        and task.get("error") == "服务重启导致录音中断"
                        and not task.get("audio_name")
                        and not task.get("dialogue")
                        and not task.get("summary")):
                    task_file.unlink(missing_ok=True)
                    joblog_file = TASKS_DIR / f"{task_id}.joblog.jsonl"
                    joblog_file.unlink(missing_ok=True)
                    orphan_recording += 1
                    continue
                tasks[task_id] = task
        if tasks:
            logger.info(f"从磁盘恢复了 {len(tasks)} 个任务")
        if migrated:
            logger.info(f"已迁移 {migrated} 个任务（剔除 transcription 冗余数据）")
        if speaker_count_fixed:
            logger.info(f"已修正 {speaker_count_fixed} 个任务的说话人计数")
        if orphan_recording:
            recovered_count = sum(1 for t in tasks.values() if t.get("_recovered_from_orphan"))
            deleted_count = orphan_recording - recovered_count
            if recovered_count:
                logger.info(f"已恢复 {recovered_count} 个孤儿录音（服务重启前正在录制，音频已保留）")
            if deleted_count:
                logger.warning(f"已清理 {deleted_count} 个孤儿录音任务（无可用音频数据）")
    except Exception as e:
        logger.error(f"从磁盘加载任务失败: {e}")


def recover_interrupted_tasks() -> None:
    """
    启动时自动恢复中断的任务。

    扫描所有 processing / awaiting_mapping 状态的任务，根据已有数据判断断点位置：
      - 有 dialogue 数据 → Stage 1 已完成 → 从 Stage 2（纪要生成）恢复
        （awaiting_mapping 为历史遗留状态：新流程纪要不再等待绑定确认，一并补跑）
      - 无 dialogue 但有 audio_path 且文件存在 → 从 Stage 1（转写）重新开始
      - audio_path 不存在 → 标记为 failed
    """
    import threading

    recovered = 0
    failed = 0

    for task_id, task in list(tasks.items()):
        if task.get("status") not in ("processing", "awaiting_mapping"):
            continue

        audio_path_str = task.get("audio_path")
        audio_path = Path(audio_path_str) if audio_path_str else None

        if task.get("dialogue"):
            # Stage 1 已完成，从 Stage 2 恢复
            if not audio_path or not audio_path.exists():
                logger.warning(f"[恢复] {task_id[:8]} 录音文件不存在，标记为失败")
                task["status"] = "failed"
                task["error"] = "服务重启时录音文件已丢失"
                task["failed_stage"] = "summarize"
                task["error_category"] = "file_missing"
                task["error_suggestion"] = "请重新录制" if infer_task_source(task) == "record" else "请重新上传录音文件"
                save_task_to_disk(task_id)
                failed += 1
                continue

            # 恢复说话人映射
            mapping = {}
            for k, v in task.get("speaker_uuid_mapping", {}).items():
                try:
                    mapping[int(k)] = v
                except (ValueError, TypeError):
                    pass

            task["progress"] = 75
            task["message"] = "服务重启，正在恢复纪要生成..."
            save_task_to_disk(task_id)

            logger.info(f"[恢复] {task_id[:8]} 从 Stage 2（纪要生成）恢复")
            joblog.append_event(task_id, joblog.STAGE_SUMMARY, "服务重启后自动恢复纪要生成")

            t = threading.Thread(
                target=_run_stage2_for_task,
                args=(task_id, audio_path, mapping),
                daemon=True,
            )
            t.start()
            recovered += 1

        elif audio_path and audio_path.exists():
            # Stage 1 未完成，从 Stage 1 重新开始
            audio_name = task.get("audio_name", audio_path.name)

            # 重置 Stage 1 相关字段
            task["progress"] = 0
            task["message"] = "服务重启，正在恢复转写..."
            task["dialogue"] = None
            task["transcription"] = None
            task["speaker_count"] = None
            task["voiceprint_match"] = None
            task["voiceprint_auto_mapping"] = None
            save_task_to_disk(task_id)

            logger.info(f"[恢复] {task_id[:8]} 从 Stage 1（转写）恢复")
            joblog.append_event(task_id, joblog.STAGE_TRANSCRIBE, "服务重启后自动恢复转写")

            t = threading.Thread(
                target=run_pipeline_task,
                args=(task_id, audio_path, audio_name, None, None),
                daemon=True,
            )
            t.start()
            recovered += 1

        else:
            # 录音文件不存在，无法恢复
            logger.warning(f"[恢复] {task_id[:8]} 录音文件不存在，标记为失败")
            task["status"] = "failed"
            task["error"] = "服务重启时录音文件已丢失"
            task["failed_stage"] = "transcribe"
            task["error_category"] = "file_missing"
            task["error_suggestion"] = "请重新录制" if infer_task_source(task) == "record" else "请重新上传录音文件"
            save_task_to_disk(task_id)
            failed += 1

    if recovered:
        logger.info(f"[恢复] 已恢复 {recovered} 个中断任务")
    if failed:
        logger.warning(f"[恢复] {failed} 个任务因录音文件丢失无法恢复")


# ============================================================
# 实时推送辅助函数
# ============================================================


def push_realtime_msg(task_id: str, msg: dict) -> None:
    """
    从 SDK 线程安全地推送消息到 asyncio Queue。

    DashScope 回调在 SDK 内部线程执行，需要通过事件循环
    将消息投递到 asyncio.Queue，供 WebSocket 协程消费。
    """
    queue = realtime_queues.get(task_id)
    loop = event_loop
    if queue and loop and not loop.is_closed():
        try:
            asyncio.run_coroutine_threadsafe(queue.put(msg), loop)
        except Exception as e:
            logger.error(f"推送实时消息失败: {e}")

    # 定稿句子自动写入缓冲区（供 AI 对话上下文注入）
    if msg.get("type") == "sentence":
        sentence_entry = {
            "text": msg.get("text", ""),
            "speaker_id": msg.get("speaker_id"),
            "speaker_name": msg.get("speaker_name", ""),
            "begin_time": msg.get("begin_time", 0),
            "end_time": msg.get("end_time", 0),
        }
        buf = realtime_transcript_buffers.setdefault(task_id, [])
        buf.append(sentence_entry)
        # 只保留最近 N 条
        if len(buf) > REALTIME_BUFFER_MAX:
            realtime_transcript_buffers[task_id] = buf[-REALTIME_BUFFER_MAX:]
        # 同步写入全量转写（无上限，供文本桥接匹配）
        full = realtime_full_transcripts.setdefault(task_id, [])
        full.append(sentence_entry)


def resolve_realtime_speaker_name(task_id: str, speaker_id: int) -> str:
    """
    解析实时说话人姓名。

    优先级：
      1. 实时绑定映射（realtime_speaker_maps）
      2. 全局说话人列表（speakers.json）
      3. 兜底：发言人{speaker_id}
    """
    # 1. 查实时绑定映射
    binding_map = realtime_speaker_maps.get(task_id, {})
    speaker_uuid = binding_map.get(speaker_id)
    if speaker_uuid:
        spk = speakers.get_speaker_by_id(speaker_uuid)
        if spk:
            return spk.name

    # 2. 兜底
    return f"发言人{speaker_id + 1}"


# ============================================================
# 后台管线函数
# ============================================================


def estimate_speaker_count(audio_path: Path) -> int | None:
    """
    从音频文件快速估算说话人数量（采样法 + 谱聚类）。

    流程：
      1. 读取 WAV 文件头，计算总时长
      2. 在时长范围内均匀取 10-30 个采样点，每点提取 3 秒音频
      3. 对每个采样片段提取 CAM++ 声纹嵌入（降级 MFCC）
      4. 构建余弦相似度矩阵 → 谱聚类（eigengap 启发式）确定最优 k
      5. 与贪心聚类结果交叉验证，取更可靠的一方
      6. 钳制到 [SPEAKER_COUNT_MIN, SPEAKER_COUNT_MAX]

    谱聚类相比贪心余弦聚类的优势：
      - 不依赖固定阈值（贪心用 0.55，对不同录音适应性差）
      - eigengap 启发式自动确定最优簇数
      - 对非球形簇分布更鲁棒

    用于文件上传场景（无实时录音过程，缺少实时聚类估算值）。
    """
    try:
        import struct as _struct
        from core.audio import normalize_audio
        from core.diarization import (
            SpeakerDiarizer, SAMPLE_RATE,
            extract_speaker_feature, _is_speech,
        )

        # 先归一化为 WAV（上传文件可能是 MP3/M4A 等）
        normalized = normalize_audio(audio_path)

        with open(normalized, "rb") as f:
            # 读取 WAV 文件头，定位 data chunk
            riff = f.read(4)
            if riff != b"RIFF":
                logger.warning(f"[说话人估算] 非 WAV 文件: {audio_path.name}")
                return None

            f.read(4)  # file size
            f.read(4)  # WAVE

            data_offset = None
            audio_format = 1  # PCM
            num_channels = 1
            sample_rate = SAMPLE_RATE
            bits_per_sample = 16

            while True:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                chunk_size = _struct.unpack("<I", f.read(4))[0]

                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    audio_format = _struct.unpack("<H", fmt_data[0:2])[0]
                    num_channels = _struct.unpack("<H", fmt_data[2:4])[0]
                    sample_rate = _struct.unpack("<I", fmt_data[4:8])[0]
                    bits_per_sample = _struct.unpack("<H", fmt_data[14:16])[0]
                elif chunk_id == b"data":
                    data_offset = f.tell()
                    data_size = chunk_size
                    break
                else:
                    f.seek(chunk_size, 1)  # 跳过未知 chunk

            if data_offset is None:
                logger.warning("[说话人估算] 未找到 data chunk")
                return None

            # 计算音频时长
            bytes_per_sample = num_channels * bits_per_sample // 8
            total_samples = data_size // bytes_per_sample
            duration_sec = total_samples / sample_rate

            if duration_sec < 3:
                logger.info(f"[说话人估算] 音频过短 ({duration_sec:.1f}s)，默认 1 人")
                return 1

            # 均匀采样：10-30 个点，每点取 3 秒片段
            num_points = max(10, min(30, int(duration_sec / 10)))
            chunk_duration = 3.0  # 每段 3 秒
            chunk_bytes = int(chunk_duration * sample_rate * bytes_per_sample)

            # ── 提取特征向量（直接提取，不经过聚类器内部聚类） ──
            features = []
            diarizer = SpeakerDiarizer()  # 仍用贪心法做交叉验证

            for i in range(num_points):
                if num_points == 1:
                    sample_start = 0
                else:
                    sample_start = (i / (num_points - 1)) * (duration_sec - chunk_duration)
                sample_start = max(0, min(sample_start, duration_sec - chunk_duration))

                byte_pos = data_offset + int(sample_start * sample_rate * bytes_per_sample)
                f.seek(byte_pos)
                chunk_data = f.read(chunk_bytes)

                if len(chunk_data) < chunk_bytes:
                    continue

                # VAD 过滤：静音段不提取特征
                if not _is_speech(chunk_data):
                    continue

                feat = extract_speaker_feature(chunk_data)
                if feat is not None:
                    features.append(feat)

                # 同时馈入贪心聚类器（交叉验证用）
                diarizer.feed_audio(chunk_data, timestamp=sample_start)

            if len(features) < 3:
                # 特征不足，退化到贪心结果（含后处理合并）
                greedy_count = diarizer.finalize()
                clamped = max(SPEAKER_COUNT_MIN, min(SPEAKER_COUNT_MAX, greedy_count))
                logger.info(f"[说话人估算] 特征不足({len(features)})，仅贪心: {clamped}")
                return clamped

            # ── 谱聚类：eigengap 启发式确定最优 k ──
            spectral_count = _spectral_estimate_k(features)
            greedy_count = diarizer.finalize()  # 含后处理合并

            # 选择策略：
            # - 谱聚类结果在 [2, 8] 范围内时优先采信（eigengap 有明确信号）
            # - 否则退化到贪心结果
            if spectral_count is not None and 2 <= spectral_count <= 8:
                chosen = spectral_count
                method = "spectral"
            else:
                chosen = greedy_count
                method = "greedy"

            clamped = max(SPEAKER_COUNT_MIN, min(SPEAKER_COUNT_MAX, chosen))
            logger.info(
                f"[说话人估算] {audio_path.name}: 时长={duration_sec:.0f}s, "
                f"采样={num_points}点, 特征={len(features)}, "
                f"谱聚类={spectral_count}, 贪心={greedy_count}, "
                f"选用={chosen}({method}), 钳制={clamped}"
            )
            return clamped

    except Exception as e:
        logger.warning(f"[说话人估算] 失败: {e}")
        return None


def _spectral_estimate_k(
    features: list[np.ndarray],
    max_k: int = 8,
) -> int | None:
    """
    谱聚类 eigengap 启发式：自动确定最优簇数 k。

    算法：
      1. 构建余弦相似度矩阵 A（高斯核变换）
      2. 计算归一化图拉普拉斯 L_sym = I - D^{-1/2} A D^{-1/2}
      3. 求 L_sym 的前 max_k+1 个最小特征值
      4. 找最大 eigengap（相邻特征值之差最大的位置）

    Returns:
        最优 k（2~max_k），或 None（特征不足 / 计算失败）
    """
    n = len(features)
    if n < 4:
        return None

    F = np.stack(features)
    # L2 归一化（防御性）
    norms = np.linalg.norm(F, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-9)
    F = F / norms

    # 余弦相似度矩阵 → 高斯核（sigma 自适应）
    sim = F @ F.T
    np.fill_diagonal(sim, 0)  # 去掉自环

    # sigma = 所有正相似度的中位数（自适应带宽）
    positive_sims = sim[sim > 0]
    if len(positive_sims) == 0:
        return None
    sigma = float(np.median(positive_sims))
    if sigma < 1e-9:
        return None

    A = np.exp(-(1 - sim) / (2 * sigma ** 2))
    np.fill_diagonal(A, 0)

    # 归一化拉普拉斯 L_sym = I - D^{-1/2} A D^{-1/2}
    d = A.sum(axis=1)
    d_inv_sqrt = np.where(d > 1e-9, 1.0 / np.sqrt(d), 0)
    D_inv_sqrt = np.diag(d_inv_sqrt)
    L_sym = np.eye(n) - D_inv_sqrt @ A @ D_inv_sqrt

    # 对称化（消除数值误差）
    L_sym = (L_sym + L_sym.T) / 2

    # 求最小的 max_k+1 个特征值
    try:
        from scipy.linalg import eigh
        eigenvalues = eigh(
            L_sym,
            subset_by_index=[0, min(max_k, n - 1)],
            eigvals_only=True,
        )
    except Exception:
        return None

    eigenvalues = np.sort(np.real(eigenvalues))

    # eigengap：相邻特征值之差
    if len(eigenvalues) < 3:
        return None
    gaps = np.diff(eigenvalues[1:])  # 跳过第一个接近 0 的特征值

    if len(gaps) == 0:
        return None

    # 最大 eigengap 的位置 → k
    best_k = int(np.argmax(gaps) + 2)  # +2 补偿跳过第一个 + diff 偏移

    # 置信度检查：最大 gap 必须显著大于平均 gap
    mean_gap = float(np.mean(gaps))
    max_gap = float(gaps[np.argmax(gaps)])
    if max_gap < mean_gap * 1.5:
        # eigengap 信号不够强，返回 None（让调用方退化到贪心）
        logger.debug(
            f"[谱聚类] eigengap 信号弱: max={max_gap:.4f}, "
            f"mean={mean_gap:.4f}, ratio={max_gap/max(mean_gap,1e-9):.2f}"
        )
        return None

    logger.debug(f"[谱聚类] eigenvalues={eigenvalues[:min(6,len(eigenvalues))].round(4)}, k={best_k}")
    return best_k


def run_pipeline_task(task_id: str, audio_path: Path, audio_name: str, speaker_mapping: dict = None, speaker_count: int = None):
    """后台执行管线第一阶段（转写），完成后等待说话人绑定。含瞬时错误自动重试。"""
    def on_progress(p: PipelineProgress):
        tasks[task_id]["progress"] = p.percent
        tasks[task_id]["message"] = p.message
        tasks[task_id]["status"] = "processing" if p.percent >= 0 else "failed"
        logger.info(f"[{task_id[:8]}] {p}")

    def on_failure(e: Exception):
        """统一处理失败：分类错误、记录字段、落盘"""
        logger.exception(f"[{task_id[:8]}] 管线执行失败")
        err_info = classify_error(e)
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["failed_stage"] = "transcribe"
        tasks[task_id]["error_category"] = err_info["category"]
        tasks[task_id]["error_suggestion"] = err_info["suggestion"]
        joblog.append_event(
            task_id, joblog.STAGE_ERROR, f"转写阶段失败: {e}", level="error",
            detail={"category": err_info["category"], "suggestion": err_info["suggestion"]},
        )
        save_task_to_disk(task_id)

    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 0
    tasks[task_id]["retry_count"] = 0
    task_start = time.perf_counter()
    joblog.append_event(task_id, joblog.STAGE_TRANSCRIBE, "开始转写（stage1）")

    # 自动重试循环（仅针对瞬时错误）
    for attempt in range(PIPELINE_MAX_RETRIES + 1):
        try:
            # 文件上传路径：若未提供 speaker_count，自动估算
            if speaker_count is None:
                speaker_count = estimate_speaker_count(audio_path)
                if speaker_count:
                    logger.info(f"[{task_id[:8]}] 自动估算说话人数量: {speaker_count}")

            # 若估算时已生成归一化文件，复用之（避免重复 ffmpeg）
            normalized_path = audio_path.with_stem(f"{audio_path.stem}_normalized").with_suffix(".wav")
            pre_normalized = normalized_path if normalized_path.exists() else None

            # 只运行第一阶段：音频 → 对话稿
            result = run_pipeline_stage1(
                audio_path=pre_normalized or audio_path,
                on_progress=on_progress,
                speaker_count=speaker_count,
            )

            # 存储转写结果
            tasks[task_id]["audio_duration"] = result.get("audio_duration")
            tasks[task_id]["dialogue"] = result.get("dialogue")
            tasks[task_id]["transcription"] = result.get("transcription")
            dialogue = result.get("dialogue", [])
            tasks[task_id]["speaker_count"] = len({d.get("speaker_id") for d in dialogue})
            joblog.append_event(
                task_id, joblog.STAGE_TRANSCRIBE,
                f"转写完成，识别 {tasks[task_id]['speaker_count']} 位说话人",
            )

            # 用量计量：转写成功后记录音频时长
            try:
                from core.metering import is_metered, record_usage
                from core.users import get_current_user
                audio_dur = result.get("audio_duration")
                if audio_dur and is_metered():
                    current_user = get_current_user()
                    if current_user:
                        record_usage(
                            user_id=current_user["id"],
                            service="asr_batch",
                            duration_seconds=audio_dur,
                            task_id=task_id,
                            metadata={"model": "paraformer-v2", "provider": "DashScope"},
                        )
            except Exception as e:
                logger.warning(f"[{task_id[:8]}] 用量记录失败（不影响主流程）: {e}")

            # 检查是否有预设的说话人映射（向后兼容）
            if speaker_mapping:
                # 有预设映射，直接运行第二阶段
                save_task_to_disk(task_id)
                _run_stage2_for_task(task_id, audio_path, speaker_mapping)
            else:
                # V3++ 分层匹配策略：P0 文本桥接 → P1 声纹匹配 → P2 手动绑定
                normalized_path = result.get("normalized_path")
                if not normalized_path and pre_normalized:
                    normalized_path = str(pre_normalized)
                # 持久化归一化音频路径：供绑定后声纹补录与回溯采集脚本使用
                tasks[task_id]["normalized_path"] = normalized_path
                dialogue = result.get("dialogue", [])
                auto_mapping = {}
                match_sources = []  # 记录匹配来源（用于日志和提示）

                # ── P0：文本桥接匹配（确定性证据） ──
                realtime_full_transcript = tasks[task_id].get("realtime_full_transcript")
                realtime_speaker_binding = tasks[task_id].get("realtime_speaker_binding")
                text_bridge_matched = 0
                if realtime_full_transcript and realtime_speaker_binding and dialogue:
                    try:
                        tb_start = time.perf_counter()
                        # 构建说话人姓名映射
                        speaker_names = {}
                        for uuid in set(realtime_speaker_binding.values()):
                            spk = speakers.get_speaker_by_id(uuid)
                            if spk:
                                speaker_names[uuid] = spk.name
                        tb_results, tb_mapping = text_bridge.text_bridge_match(
                            realtime_full_transcript=realtime_full_transcript,
                            realtime_speaker_binding=realtime_speaker_binding,
                            dialogue=dialogue,
                            speaker_names=speaker_names,
                        )
                        tb_elapsed = time.perf_counter() - tb_start
                        text_bridge_matched = len(tb_mapping)
                        logger.info(f"[PERF] {task_id[:8]} P0 文本桥接匹配: {tb_elapsed:.3f}s, {text_bridge_matched} 位")
                        if tb_mapping:
                            auto_mapping.update(tb_mapping)
                            match_sources.append(f"文本桥接({text_bridge_matched}位)")
                            tasks[task_id]["text_bridge_match"] = [r.to_dict() for r in tb_results]
                            logger.info(
                                f"[{task_id[:8]}] P0 文本桥接匹配: "
                                f"{text_bridge_matched} 位说话人识别成功"
                            )
                            joblog.append_event(
                                task_id, joblog.STAGE_VOICEPRINT,
                                f"P0 文本桥接匹配命中 {text_bridge_matched} 位说话人",
                            )
                    except Exception as e:
                        logger.warning(f"[{task_id[:8]}] P0 文本桥接匹配失败: {e}")
                        joblog.append_event(
                            task_id, joblog.STAGE_VOICEPRINT,
                            f"P0 文本桥接匹配失败: {e}", level="warn",
                        )

                # ── P1：声纹向量匹配（概率性证据） ──
                # 仅对文本桥接未覆盖的说话人执行声纹匹配
                # 受 feature_flags.voiceprint_auto_match 开关控制（默认关闭）
                vp_enabled = get_feature_flags().get("voiceprint_auto_match", False)
                if vp_enabled and normalized_path and dialogue:
                    try:
                        vp_start = time.perf_counter()
                        vp_results = voiceprint.auto_identify_speakers(
                            audio_path=normalized_path,
                            dialogue=dialogue,
                        )
                        vp_elapsed = time.perf_counter() - vp_start
                        vp_mapping = voiceprint.build_auto_mapping(vp_results)
                        logger.info(f"[PERF] {task_id[:8]} P1 声纹匹配: {vp_elapsed:.3f}s")
                        # 合并：声纹匹配仅补充文本桥接未覆盖的 speaker_id
                        new_vp_matches = {
                            sid: uuid for sid, uuid in vp_mapping.items()
                            if sid not in auto_mapping
                        }
                        if new_vp_matches:
                            auto_mapping.update(new_vp_matches)
                            match_sources.append(f"声纹匹配({len(new_vp_matches)}位)")
                            logger.info(
                                f"[{task_id[:8]}] P1 声纹匹配补充: "
                                f"{len(new_vp_matches)} 位说话人"
                            )
                        # 始终记录声纹匹配结果（供前端展示）
                        tasks[task_id]["voiceprint_match"] = [r.to_dict() for r in vp_results]
                        tasks[task_id]["voiceprint_auto_mapping"] = {str(k): v for k, v in vp_mapping.items()}
                        if not new_vp_matches and not text_bridge_matched:
                            joblog.append_event(
                                task_id, joblog.STAGE_VOICEPRINT,
                                "P0+P1 均无匹配，降级为手动绑定", level="warn",
                            )
                    except Exception as e:
                        logger.warning(f"[{task_id[:8]}] P1 声纹匹配失败: {e}")
                        joblog.append_event(
                            task_id, joblog.STAGE_VOICEPRINT,
                            f"P1 声纹匹配失败: {e}", level="error",
                        )

                if match_sources:
                    logger.info(
                        f"[{task_id[:8]}] 分层匹配完成: {len(auto_mapping)} 位说话人, "
                        f"来源: {', '.join(match_sources)}"
                    )

                if auto_mapping:
                    # 有自动匹配结果，自动注册/更新声纹（时长加权）
                    if normalized_path and dialogue:
                        try:
                            reg_results = voiceprint.register_from_binding(
                                audio_path=normalized_path,
                                dialogue=dialogue,
                                mapping=auto_mapping,
                                meeting_id=task_id,
                            )
                            reg_ok = sum(1 for r in reg_results.values() if r["status"] == "registered")
                            if reg_ok > 0:
                                logger.info(
                                    f"[{task_id[:8]}] 自动匹配后声纹更新: "
                                    f"{reg_ok}/{len(auto_mapping)} 位说话人"
                                )
                        except Exception as e:
                            logger.warning(f"[{task_id[:8]}] 自动声纹更新失败（不影响主流程）: {e}")
                else:
                    # 无自动匹配：不阻塞管线，纪要先以通用说话人标签生成；
                    # 前端绑定栏保留，用户确认关联后按真实身份重新生成纪要
                    joblog.append_event(
                        task_id, joblog.STAGE_BIND,
                        "未命中自动匹配，先以通用标签生成纪要，等待用户事后关联说话人",
                    )

                # 直接运行第二阶段（不再等待用户确认绑定）
                save_task_to_disk(task_id)
                _run_stage2_for_task(task_id, audio_path, auto_mapping)

            return  # 成功，退出重试循环

        except Exception as e:
            if is_transient_error(e) and attempt < PIPELINE_MAX_RETRIES:
                # 瞬时错误且还有重试机会
                delay = PIPELINE_RETRY_DELAYS[attempt]
                tasks[task_id]["retry_count"] = attempt + 1
                tasks[task_id]["message"] = f"遇到临时错误，{delay}秒后自动重试 ({attempt + 1}/{PIPELINE_MAX_RETRIES})..."
                tasks[task_id]["progress"] = max(0, tasks[task_id].get("progress", 0) - 10)
                save_task_to_disk(task_id)
                logger.warning(f"[{task_id[:8]}] 瞬时错误，{delay}秒后重试 ({attempt + 1}/{PIPELINE_MAX_RETRIES}): {e}")
                joblog.append_event(
                    task_id, joblog.STAGE_TRANSCRIBE,
                    f"瞬时错误，{delay}s 后重试 ({attempt + 1}/{PIPELINE_MAX_RETRIES}): {e}", level="warn",
                )
                time.sleep(delay)
                continue
            else:
                # 永久错误或重试耗尽
                on_failure(e)
                return

    # 记录任务总耗时（无论成功失败）
    task_elapsed = time.perf_counter() - task_start
    logger.info(f"[PERF] {task_id[:8]} 管线任务总计: {task_elapsed:.3f}s")


def _run_stage2_for_task(task_id: str, audio_path: Path, speaker_mapping: dict = None):
    """为指定任务运行管线第二阶段（纪要生成）。含瞬时错误自动重试。"""
    stage2_start = time.perf_counter()

    def on_progress(p: PipelineProgress):
        tasks[task_id]["progress"] = p.percent
        tasks[task_id]["message"] = p.message
        logger.info(f"[{task_id[:8]}] {p}")

    def on_failure(e: Exception):
        """统一处理纪要阶段失败"""
        logger.exception(f"[{task_id[:8]}] 纪要生成失败")
        err_info = classify_error(e)
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["failed_stage"] = "summarize"
        tasks[task_id]["error_category"] = err_info["category"]
        tasks[task_id]["error_suggestion"] = err_info["suggestion"]
        joblog.append_event(
            task_id, joblog.STAGE_ERROR, f"纪要生成失败: {e}", level="error",
            detail={"category": err_info["category"], "suggestion": err_info["suggestion"]},
        )
        save_task_to_disk(task_id)

    # 自动重试循环（仅针对瞬时错误）
    for attempt in range(PIPELINE_MAX_RETRIES + 1):
        try:
            dialogue = tasks[task_id].get("dialogue", [])

            # 优先使用用户指定的 meeting_date，否则从 created_at 提取
            meeting_time = None
            if tasks[task_id].get("meeting_date"):
                try:
                    md = tasks[task_id]["meeting_date"]
                    created_dt = datetime.fromisoformat(tasks[task_id].get("created_at", ""))
                    time_str = created_dt.strftime("%H:%M")
                    meeting_time = f"{md} {time_str}"
                except (ValueError, TypeError):
                    meeting_time = tasks[task_id]["meeting_date"]
            if not meeting_time:
                created_at_str = tasks[task_id].get("created_at", "")
                if created_at_str:
                    try:
                        created_dt = datetime.fromisoformat(created_at_str)
                        meeting_time = created_dt.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        pass

            # 兜底：从音频文件名提取时间（格式：xxxxxxxx_YYYYMMDD_HHMMSS.wav）
            if not meeting_time and audio_path:
                import re
                m = re.search(r'_(\d{8})_(\d{6})\.', audio_path.name)
                if m:
                    try:
                        dt = datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S")
                        meeting_time = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        pass

            joblog.append_event(task_id, joblog.STAGE_SUMMARY, "开始生成纪要（stage2）")
            result = run_pipeline_stage2(
                dialogue=dialogue,
                speaker_mapping=speaker_mapping,
                audio_path=audio_path,
                on_progress=on_progress,
                meeting_time=meeting_time,
                user_notes=tasks[task_id].get("user_notes"),
            )

            tasks[task_id]["status"] = "completed"
            tasks[task_id]["progress"] = 100
            tasks[task_id]["message"] = "完成"
            tasks[task_id]["summary"] = result.get("summary")
            tasks[task_id]["title"] = result.get("title")
            tasks[task_id]["output_path"] = result.get("output_path")
            tasks[task_id]["dialogue"] = result.get("dialogue")
            tasks[task_id]["speaker_mapping"] = result.get("speaker_mapping", {})
            tasks[task_id]["speaker_uuid_mapping"] = result.get("speaker_uuid_mapping", {})
            tasks[task_id]["chapters"] = result.get("chapters", [])

            summary_text = result.get("summary", "")
            if summary_text:
                parsed_todos = parse_todos_from_summary(summary_text)
                if parsed_todos:
                    tasks[task_id]["todos"] = parsed_todos
                    logger.info(f"[{task_id[:8]}] 自动提取 {len(parsed_todos)} 条待办")

            joblog.append_event(task_id, joblog.STAGE_SUMMARY, "纪要生成完成")
            save_task_to_disk(task_id)

            stage2_elapsed = time.perf_counter() - stage2_start
            logger.info(f"[PERF] {task_id[:8]} 纪要任务总计: {stage2_elapsed:.3f}s")

            return  # 成功

        except Exception as e:
            if is_transient_error(e) and attempt < PIPELINE_MAX_RETRIES:
                delay = PIPELINE_RETRY_DELAYS[attempt]
                tasks[task_id]["retry_count"] = tasks[task_id].get("retry_count", 0) + 1
                tasks[task_id]["message"] = f"纪要生成遇到临时错误，{delay}秒后自动重试 ({attempt + 1}/{PIPELINE_MAX_RETRIES})..."
                save_task_to_disk(task_id)
                logger.warning(f"[{task_id[:8]}] 纪要阶段瞬时错误，{delay}秒后重试 ({attempt + 1}/{PIPELINE_MAX_RETRIES}): {e}")
                joblog.append_event(
                    task_id, joblog.STAGE_SUMMARY,
                    f"纪要瞬时错误，{delay}s 后重试 ({attempt + 1}/{PIPELINE_MAX_RETRIES}): {e}", level="warn",
                )
                time.sleep(delay)
                continue
            else:
                on_failure(e)
                return


def run_stage2_task(task_id: str, audio_path: Path, speaker_mapping: dict = None):
    """后台执行管线第二阶段（供 API 调用）"""
    _run_stage2_for_task(task_id, audio_path, speaker_mapping)


# ============================================================
# 设置管理辅助函数
# ============================================================


def load_settings() -> dict:
    """
    加载设置（从 settings.json）。

    返回空 dict 若文件不存在。
    """
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"加载 settings.json 失败: {e}")
            return {}
    return {}


def save_settings_to_disk(settings: dict) -> None:
    """持久化设置到 settings.json"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def mask_api_key(key: str) -> str:
    """
    API Key 脱敏：仅显示前 3 位和后 4 位，中间用 **** 替代。

    示例：sk-abc...xyz → sk-****xyz
    若 key 长度不足 8 位，全部用 **** 替代。
    """
    if not key or len(key) < 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


def get_active_api_key() -> str:
    """
    获取当前生效的 LLM API Key。

    优先级：
      1. settings.json 中的 llm.api_key
      2. 旧版 settings.json 中的 api_key（向后兼容）
      3. 环境变量 DASHSCOPE_API_KEY
      4. 空字符串

    注意：ASR 模块请使用 get_asr_config() 获取独立的 ASR Key。
    """
    settings = load_settings()

    # 新版格式：llm.api_key
    llm_config = settings.get("llm", {})
    if llm_config.get("api_key"):
        return llm_config["api_key"]

    # 旧版格式：api_key（向后兼容）
    if settings.get("api_key"):
        return settings["api_key"]

    # 环境变量兜底
    return os.getenv("DASHSCOPE_API_KEY", "")


def get_llm_config() -> dict:
    """
    获取 LLM 配置（从 settings.json）。

    返回格式：
      {
        "provider": "DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-...",  # 明文（仅内部使用）
        "model": "qwen-plus"
      }

    若未配置，返回默认值（DashScope）。
    """
    settings = load_settings()
    llm_config = settings.get("llm", {})

    # 向后兼容：若 llm 不存在但 api_key 存在，迁移为新版格式
    if not llm_config and settings.get("api_key"):
        llm_config = {
            "provider": "DashScope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": settings["api_key"],
            "model": settings.get("model", "qwen-plus"),
        }

    # 默认值
    return {
        "provider": llm_config.get("provider", "DashScope"),
        "base_url": llm_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "api_key": llm_config.get("api_key", get_active_api_key()),
        "model": llm_config.get("model", "qwen-plus"),
    }


def get_asr_config() -> dict:
    """
    获取 ASR（语音转写）配置。

    代理模式下，客户端不再持有 DashScope API Key，所有 ASR 请求通过代理服务器中转。
    返回格式：
      {
        "provider": "DashScope",
        "proxy_url": "http://your-asr-proxy-server:8200",
        "model": "paraformer-v2",
        "source": "platform"  # 始终为 platform（代理模式）
      }

    详见 docs/adr/0012-ASR转写走云端代理.md
    """
    return {
        "provider": "DashScope",
        "proxy_url": os.getenv("ASR_PROXY_URL", ""),
        "model": "paraformer-v2",
        "source": "platform",
    }


def get_voiceprint_config() -> dict:
    """
    获取声纹识别配置（从 settings.json）。

    返回格式：
      {
        "provider": "auto",       # "local" / "cloud" / "auto"
        "cloud": {
          "base_url": "",
          "api_key": ""
        }
      }

    环境变量 VOICEPRINT_PROVIDER / VOICEPRINT_API_KEY / VOICEPRINT_BASE_URL
    可覆盖 settings.json 中的对应字段。
    """
    settings = load_settings()
    vp_config = settings.get("voiceprint", {})
    cloud_config = vp_config.get("cloud", {})

    return {
        "provider": vp_config.get("provider", "auto"),
        "cloud": {
            "base_url": cloud_config.get("base_url", ""),
            "api_key": cloud_config.get("api_key", ""),
        },
    }


def get_feature_flags() -> dict:
    """
    获取功能开关配置（从 settings.json）。

    返回格式：
      {
        "realtime_chapters": true,   # 实时章节生成
        "realtime_summary": true,    # 实时总结生成
        "realtime_summary_interval": 60,  # 总结间隔（秒），可选 30/60/120/300
        "update_check": true,        # 软件更新提示
        "voiceprint_auto_match": false  # 声纹自动识别（实验性，默认关闭）
      }

    未配置的字段：realtime_* / update_check 默认启用（true），
    voiceprint_auto_match 默认关闭（false）——CAM++ 模型精度尚未达标。
    """
    settings = load_settings()
    ff = settings.get("feature_flags", {})
    return {
        "realtime_chapters": ff.get("realtime_chapters", True),
        "realtime_summary": ff.get("realtime_summary", True),
        "realtime_summary_interval": ff.get("realtime_summary_interval", 60),
        "update_check": ff.get("update_check", True),
        "voiceprint_auto_match": ff.get("voiceprint_auto_match", False),
    }


def get_silence_detection_config() -> dict:
    """
    获取静默检测配置（从 settings.json）。

    详见 docs/design/SILENCE_DETECTION.md。

    返回格式：
      {
        "enabled": true,
        "presence": { ... },   # 存在性评分参数
        "audio": { ... },      # 音频层阈值
        "action": { ... }      # 提醒与关停参数
      }
    """
    settings = load_settings()
    sd = settings.get("silence_detection", {})
    return {
        "enabled": sd.get("enabled", True),
        "presence": {
            "score_max": sd.get("presence", {}).get("score_max", 100),
            "score_decay_per_sec": sd.get("presence", {}).get("score_decay_per_sec", 1),
            "score_interaction_boost": sd.get("presence", {}).get("score_interaction_boost", 100),
            "score_visibility_return": sd.get("presence", {}).get("score_visibility_return", 80),
            "score_focus_return": sd.get("presence", {}).get("score_focus_return", 60),
            "score_heartbeat": sd.get("presence", {}).get("score_heartbeat", 20),
            "score_visibility_hidden_multiplier": sd.get("presence", {}).get("score_visibility_hidden_multiplier", 0.3),
            "score_blur_multiplier": sd.get("presence", {}).get("score_blur_multiplier", 0.5),
            "threshold_warning": sd.get("presence", {}).get("threshold_warning", 20),
            "heartbeat_interval_sec": sd.get("presence", {}).get("heartbeat_interval_sec", 30),
            "heartbeat_timeout_sec": sd.get("presence", {}).get("heartbeat_timeout_sec", 90),
        },
        "audio": {
            "rms_silence_db": sd.get("audio", {}).get("rms_silence_db", -45),
            "asr_no_sentence_timeout_sec": sd.get("audio", {}).get("asr_no_sentence_timeout_sec", 300),
        },
        "action": {
            "gentle_countdown_sec": sd.get("action", {}).get("gentle_countdown_sec", 120),
            "urgent_countdown_sec": sd.get("action", {}).get("urgent_countdown_sec", 60),
            "max_warnings_per_session": sd.get("action", {}).get("max_warnings_per_session", 2),
        },
    }
