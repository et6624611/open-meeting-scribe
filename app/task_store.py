"""
app/task_store.py — 任务持久化与恢复

作者：王永亮
创建：2026-09-12
版本：1.0.0

职责：
  - 任务内存字典（tasks）
  - 任务磁盘持久化（save / load）
  - 启动时孤儿录音恢复与中断任务恢复

从 app/store.py 拆分而来，与原模块通过 re-export 保持向后兼容。
"""

import json
import struct
import logging
from pathlib import Path
from datetime import datetime
from core.i18n import _

from core import joblog

logger = logging.getLogger(__name__)

# ============================================================
# 目录常量
# ============================================================

TASKS_DIR = Path("data/tasks")
TASKS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 共享状态
# ============================================================

# 任务存储（内存，重启丢失；生产环境应持久化）
tasks: dict[str, dict] = {}


# ============================================================
# 辅助函数
# ============================================================


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


# ============================================================
# 持久化
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
        task["message"] = _("Recording was in progress before restart, audio recovered, awaiting processing")
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
    # 延迟导入，避免与 pipeline_runner 的循环依赖
    from core.pipeline_runner import run_pipeline_task, _run_stage2_for_task

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
            task["message"] = _("Server restart, resuming minute generation...")
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
            task["message"] = _("Server restart, resuming transcription...")
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
