"""
app/task_store.py — 任务持久化与恢复 / Task persistence and recovery

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 任务内存字典（tasks） / Task memory dict (tasks)
  - 任务磁盘持久化（save / load） / Task disk persistence (save / load)
  - 启动时孤儿录音恢复与中断任务恢复 / Orphan recording recovery and interrupted task recovery on startup

从 app/store.py 拆分而来，与原模块通过 re-export 保持向后兼容 / Split from app/store.py; backward-compatible via re-export.
"""

import json
import logging
import struct
from datetime import datetime
from pathlib import Path

from core import joblog
from core.i18n import _

logger = logging.getLogger(__name__)

# ============================================================
# 目录常量 / Directory constants
# ============================================================

TASKS_DIR = Path("data/tasks")
TASKS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 共享状态 / Shared state
# ============================================================

# 任务存储（内存，重启丢失；生产环境应持久化） / Task storage (in-memory; lost on restart; should persist in production)
tasks: dict[str, dict] = {}


# ============================================================
# 辅助函数 / Helper functions
# ============================================================


def infer_task_source(task: dict) -> str:
    """推断任务来源 / Infer task source: 'record' (recording) or 'upload'.

    优先使用显式 source 字段；缺失时通过 audio_path 位置推断 / Prefer explicit source field; fallback to audio_path location:
    - data/recordings/ 目录下 → 录音 / Under data/recordings/ → recording
    - data/uploads/ 目录下 → 上传 / Under data/uploads/ → upload
    - 均不匹配时默认 'upload' / Default 'upload' if no match
    """
    source = task.get("source")
    if source in ("record", "upload"):
        return source
    audio_path = task.get("audio_path", "")
    if "recordings" in audio_path:
        return "record"
    if "uploads" in audio_path:
        return "upload"
    return "upload"  # 默认 / Default


# ============================================================
# 持久化 / Persistence
# ============================================================


def save_task_to_disk(task_id: str) -> None:
    """将任务数据持久化到磁盘（JSON 文件） / Persist task data to disk (JSON file)."""
    task = tasks.get(task_id)
    if not task:
        return
    try:
        # 排除 transcription 字段（原始 ASR 返回数据，体积大且无实际消费场景） / Exclude transcription field (raw ASR response; large size, no consumer)
        task_for_disk = {k: v for k, v in task.items() if k != "transcription"}
        task_file = TASKS_DIR / f"{task_id}.json"
        from core.fs_atomic import atomic_write_json
        atomic_write_json(task_file, task_for_disk)
    except Exception as e:
        logger.error(f"保存任务到磁盘失败: {e}")


def _try_recover_orphan_recording(task: dict, task_id: str) -> bool:
    """
    尝试恢复孤儿录音 / Attempt orphan recording recovery.

    v2 架构（ffmpeg 直接写 WAV）：
      - WAV 文件已由 ffmpeg 原生写入磁盘，只需验证有效性
      - 若 WAV 有效则直接恢复（无需转换）
      - 若 WAV 无效/不存在，降级查找残留 raw 文件（旧架构兼容）

    Returns:
        True 表示恢复成功 / Recovery succeeded; False 表示无可恢复的音频数据 / No recoverable audio data.
    """
    audio_path_str = task.get("audio_path", "")
    if not audio_path_str:
        return False

    audio_path = Path(audio_path_str)
    raw_path = audio_path.with_suffix(".raw")

    # ── 优先检查 WAV 文件（v2 架构：ffmpeg 直接写入）──
    if audio_path.exists() and audio_path.stat().st_size > 44:
        # WAV 文件有效（至少包含 44 字节 header）
        wav_size = audio_path.stat().st_size
        # 从 WAV header 读取实际数据大小（偏移 40-44 字节为 data chunk size）
        try:
            with open(audio_path, "rb") as f:
                f.seek(0)
                riff = f.read(4)
                if riff != b"RIFF":
                    raise ValueError("非 WAV 文件（缺少 RIFF 头）")
                f.read(4)  # file size - 8
                wave = f.read(4)
                if wave != b"WAVE":
                    raise ValueError("非 WAV 文件（缺少 WAVE 标记）")
                # 读取 data chunk size
                f.seek(40)
                data_size = struct.unpack("<I", f.read(4))[0]
                duration = data_size / (16000 * 1 * 2)  # 16kHz, mono, 16-bit
        except Exception:
            # WAV header 损坏，用文件大小估算
            duration = (wav_size - 44) / (16000 * 1 * 2)

        if duration < 0.1:
            duration = 0.1

        # 清理可能残留的 raw 文件（旧架构遗留）
        raw_path.unlink(missing_ok=True)

        # 状态设为 processing，recover_interrupted_tasks() 会自动接手开始转写
        task["status"] = "processing"
        task["progress"] = 0
        task["message"] = _("Server restart, resuming transcription...")
        task["audio_duration"] = round(duration, 1)
        task["_recovered_from_orphan"] = True
        tasks[task_id] = task
        save_task_to_disk(task_id)

        logger.info(
            f"[恢复] {task_id[:8]}: WAV 直接可用（v2 架构），时长 {duration:.0f}s ({duration/60:.1f} 分钟），将自动开始转写"
        )
        return True

    # ── 降级：检查 raw 文件（旧架构兼容）──
    if raw_path.exists() and raw_path.stat().st_size > 0:
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

            raw_path.unlink(missing_ok=True)

            # 状态设为 processing，recover_interrupted_tasks() 会自动接手开始转写
            task["status"] = "processing"
            task["progress"] = 0
            task["message"] = _("Server restart, resuming transcription...")
            task["audio_duration"] = round(duration, 1)
            task["_recovered_from_orphan"] = True
            tasks[task_id] = task
            save_task_to_disk(task_id)

            logger.info(
                f"[恢复] {task_id[:8]}: raw → WAV 完成（旧架构降级），时长 {duration:.0f}s ({duration/60:.1f} 分钟)，将自动开始转写"
            )
            return True

        except Exception as e:
            logger.error(f"[恢复] {task_id[:8]}: raw → WAV 失败: {e}")
            return False

    return False


def load_tasks_from_disk() -> None:
    """启动时从磁盘恢复任务到内存（含迁移：剔除旧文件中的 transcription 字段） / Restore tasks from disk on startup (with migration: strip transcription field from legacy files)."""
    try:
        migrated = 0
        orphan_recording = 0
        speaker_count_fixed = 0
        for task_file in TASKS_DIR.glob("*.json"):
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)
            task_id = task.get("task_id")
            if task_id:
                # 迁移：若含 transcription 字段则剔除并回写 / Migration: strip transcription field if present and rewrite
                if "transcription" in task:
                    del task["transcription"]
                    with open(task_file, "w", encoding="utf-8") as fw:
                        json.dump(task, fw, ensure_ascii=False, indent=2)
                    migrated += 1
                # 迁移：补充 meeting_date（从 created_at 提取） / Migration: populate meeting_date (extract from created_at)
                if not task.get("meeting_date") and task.get("created_at"):
                    try:
                        dt = datetime.fromisoformat(task["created_at"])
                        task["meeting_date"] = dt.strftime("%Y-%m-%d")
                        with open(task_file, "w", encoding="utf-8") as fw:
                            json.dump(task, fw, ensure_ascii=False, indent=2)
                        migrated += 1
                    except (ValueError, TypeError):
                        pass
                # 迁移：修正 speaker_count（旧版误用对话条目数，应为去重说话人数） / Migration: fix speaker_count (legacy used dialogue count; should be unique speakers)
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
                # 恢复孤儿录音：服务重启后实时资源已丢失，但 raw 音频数据可能仍在 / Recover orphan recordings: realtime resources lost after restart, but raw audio may still exist
                if task.get("status") in ("recording", "paused"):
                    recovered = _try_recover_orphan_recording(task, task_id)
                    if recovered:
                        orphan_recording += 1  # 复用计数器，日志中标记为“已恢复” / Reuse counter; logged as "recovered"
                        continue
                    # 无可用音频数据，清理任务文件 / No recoverable audio; cleanup task file
                    task_file.unlink(missing_ok=True)
                    (TASKS_DIR / f"{task_id}.joblog.jsonl").unlink(missing_ok=True)
                    (TASKS_DIR / f"{task_id}.insights.json").unlink(missing_ok=True)
                    orphan_recording += 1
                    continue
                # 清理历史遗留的无内容 failed 任务（之前重启标记的孤儿，无音频/对话/摘要） / Cleanup legacy empty failed tasks (orphans from prior restarts; no audio/dialogue/summary)
                if (task.get("status") == "failed"
                        and task.get("error") == "服务重启导致录音中断"
                        and not task.get("audio_name")
                        and not task.get("dialogue")
                        and not task.get("summary")):
                    task_file.unlink(missing_ok=True)
                    (TASKS_DIR / f"{task_id}.joblog.jsonl").unlink(missing_ok=True)
                    (TASKS_DIR / f"{task_id}.insights.json").unlink(missing_ok=True)
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
    启动时自动恢复中断的任务 / Auto-recover interrupted tasks on startup.

    扫描所有 processing / awaiting_mapping 状态的任务，根据已有数据判断断点位置 / Scan all processing / awaiting_mapping tasks; determine breakpoint based on existing data:
      - 有 dialogue 数据 → Stage 1 已完成 → 从 Stage 2（纪要生成）恢复 / Has dialogue data → Stage 1 done → resume from Stage 2 (summary generation)
        （awaiting_mapping 为历史遗留状态：新流程纪要不再等待绑定确认，一并补跑） / (awaiting_mapping is legacy state; new flow no longer waits for binding confirmation)
      - 无 dialogue 但有 audio_path 且文件存在 → 从 Stage 1（转写）重新开始 / No dialogue but audio_path exists → restart from Stage 1 (transcription)
      - audio_path 不存在 → 标记为 failed / audio_path missing → mark as failed
    """
    import threading

    # 延迟导入，避免与 pipeline_runner 的循环依赖 / Deferred import to avoid circular dependency with pipeline_runner
    from core.pipeline_runner import _run_stage2_for_task, run_pipeline_task

    recovered = 0
    failed = 0

    for task_id, task in list(tasks.items()):
        if task.get("status") not in ("processing", "awaiting_mapping"):
            continue

        audio_path_str = task.get("audio_path")
        audio_path = Path(audio_path_str) if audio_path_str else None

        if task.get("dialogue"):
            # Stage 1 已完成，从 Stage 2 恢复 / Stage 1 done; resume from Stage 2
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

            # 恢复说话人映射 / Restore speaker mapping
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
            # Stage 1 未完成，从 Stage 1 重新开始 / Stage 1 incomplete; restart from Stage 1
            audio_name = task.get("audio_name", audio_path.name)

            # 重置 Stage 1 相关字段 / Reset Stage 1 related fields
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
            # 录音文件不存在，无法恢复 / Audio file missing; cannot recover
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


def cleanup_orphaned_intermediate_files() -> dict:
    """
    清理磁盘上的冗余/孤儿中间文件 / Cleanup redundant/orphan intermediate files on disk.

    清理目标 / Cleanup targets:
      1. _normalized_normalized* 文件（重复归一化产物，管线 Bug 遗留） / Duplicate normalized files (duplicate normalization artifacts; legacy pipeline bug)
      2. 孤儿 .raw 文件（不属于任何活跃任务的临时 PCM） / Orphan .raw files (temp PCM not belonging to any active task)

    Returns:
        {"duplicate_normalized": int, "orphan_raw": int, "freed_bytes": int}
    """
    freed = 0
    dup_count = 0
    raw_count = 0

    # 收集所有任务关联的音频路径（用于判断 .raw 是否为孤儿） / Collect all task audio paths (to determine if .raw is orphaned)
    known_audio_stems = set()
    for task in tasks.values():
        ap = task.get("audio_path")
        if ap:
            known_audio_stems.add(Path(ap).stem)

    # 扫描 recordings 和 uploads 目录 / Scan recordings and uploads directories
    for scan_dir in [Path("data/recordings"), Path("data/uploads")]:
        if not scan_dir.exists():
            continue

        for f in scan_dir.iterdir():
            if not f.is_file():
                continue

            # 1. 清理重复归一化文件（_normalized_normalized*） / Cleanup duplicate normalized files (_normalized_normalized*)
            if "_normalized_normalized" in f.name:
                size = f.stat().st_size
                try:
                    f.unlink()
                    dup_count += 1
                    freed += size
                    logger.debug(f"[清理] 删除冗余归一化文件: {f.name} ({size / 1024 / 1024:.1f} MB)")
                except Exception as e:
                    logger.warning(f"[清理] 删除失败: {f.name}: {e}")
                continue

            # 2. 清理孤儿 .raw 文件（不属于任何已知任务） / Cleanup orphan .raw files (not belonging to any known task)
            if f.suffix == ".raw":
                stem = f.stem
                if stem not in known_audio_stems:
                    size = f.stat().st_size
                    try:
                        f.unlink()
                        raw_count += 1
                        freed += size
                        logger.debug(f"[清理] 删除孤儿 .raw 文件: {f.name} ({size / 1024 / 1024:.1f} MB)")
                    except Exception as e:
                        logger.warning(f"[清理] 删除失败: {f.name}: {e}")

    result = {"duplicate_normalized": dup_count, "orphan_raw": raw_count, "freed_bytes": freed}
    if dup_count or raw_count:
        logger.info(f"[清理] 启动清理完成: {dup_count} 个冗余归一化 + {raw_count} 个孤儿 .raw = {freed / 1024 / 1024:.1f} MB")
    return result
