"""
core/pipeline_runner.py — 管线编排（后台执行） / Pipeline orchestration (background execution)

职责 / Responsibilities:
  - 管线 Stage 1（转写）后台执行，含瞬时错误自动重试 / Pipeline Stage 1 (transcription) background execution with transient error auto-retry
  - 管线 Stage 2（纪要生成）后台执行，含瞬时错误自动重试 / Pipeline Stage 2 (summary) background execution with transient error auto-retry
  - 分层说话人匹配（P0 文本桥接 → P1 声纹匹配 → P2 手动绑定） / Layered speaker matching (P0 text bridge → P1 voiceprint → P2 manual binding)

说话人数量估算已拆分至 core/speaker_count.py / Speaker count estimation split to core/speaker_count.py

从 app/store.py 拆分而来 / Split from app/store.py. 依赖 / Dependencies:
  - app.task_store：任务字典与持久化 / Task dict and persistence
  - app.settings_store：功能开关 / Feature toggles
  - app.realtime_store：全量实时转写缓冲 / Full realtime transcription buffer
"""

import logging
import time
from datetime import datetime
from pathlib import Path

from app.settings_store import get_feature_flags
from app.task_store import save_task_to_disk, tasks
from core import joblog, speakers, text_bridge, voiceprint
from core.errors import classify_error, is_transient_error
from core.i18n import _
from core.pipeline import PipelineProgress, run_pipeline_stage1, run_pipeline_stage2
from core.speaker_count import estimate_speaker_count
from core.summarize import merge_flow_after_regen, parse_decisions_with_status, parse_todos_from_summary

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================

# 自动重试配置（仅针对瞬时错误）
PIPELINE_MAX_RETRIES = 2
PIPELINE_RETRY_DELAYS = [2, 5]  # 秒


def _cleanup_normalized_intermediate(task_id: str) -> None:
    """
    清理归一化中间文件（_normalized.wav）。

    Stage 1 完成后调用：声纹注册已在 Stage 1 内完成，
    归一化文件不再需要，删除以释放磁盘空间。
    仅当 auto_clean_intermediate 设置开启时执行。
    """
    try:
        from app.settings_store import get_storage_config
        if not get_storage_config().get("auto_clean_intermediate", True):
            return

        task = tasks.get(task_id, {})
        normalized_path = task.get("normalized_path")
        if not normalized_path:
            return

        np = Path(normalized_path)
        original_path = task.get("audio_path", "")
        # 确保不删除原始音频（仅删除与原始音频不同的归一化文件）
        if np.exists() and str(np) != str(original_path):
            size_mb = np.stat().st_size / 1024 / 1024
            np.unlink()
            logger.info(f"[{task_id[:8]}] 已清理归一化中间文件: {np.name} ({size_mb:.1f} MB)")
    except Exception as e:
        logger.warning(f"[{task_id[:8]}] 清理归一化文件失败（不影响主流程）: {e}")


# ============================================================
# 实时转写降级兜底 / Realtime transcription fallback
# ============================================================


def _build_dialogue_from_realtime(full_transcript: list[dict]) -> list[dict]:
    """将实时全量转写记录组装为与 assemble_dialogue 一致的对话稿结构。
    Assemble realtime full transcript into the same dialogue structure as assemble_dialogue.

    输入条目形如 {text, speaker_id, speaker_name, begin_time, end_time}。
    按相邻同 speaker_id 归并；空文本条目跳过。
    Entries look like {text, speaker_id, speaker_name, begin_time, end_time};
    consecutive sentences with the same speaker_id are merged; empty-text entries skipped.
    """
    dialogue: list[dict] = []
    for entry in full_transcript or []:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        sid = entry.get("speaker_id")
        if sid is None:
            sid = 0
        sentence = {
            "text": text,
            "begin_time": entry.get("begin_time", 0),
            "end_time": entry.get("end_time", 0),
            "speaker_id": sid,
        }
        if dialogue and dialogue[-1]["speaker_id"] == sid:
            dialogue[-1]["sentences"].append(sentence)
            dialogue[-1]["text"] += text
        else:
            block = {"speaker_id": sid, "text": text, "sentences": [sentence]}
            # 保留实时阶段已绑定的说话人姓名（若有） / Keep realtime-bound speaker name if present
            if entry.get("speaker_name"):
                block["speaker_name"] = entry["speaker_name"]
            dialogue.append(block)
    return dialogue


def _finalize_incremental_transcript(task_id: str, audio_path: Path) -> bool:
    """D-I2（R9）：本地分段增量转写的定稿路径——增量段拼接即定稿，会后不重跑全量。

    record.stop_record 对 LocalSegmentTranscriber 产出的任务打
    transcript_finalized_incremental 标记；本函数据此跳过 stage1 全量批转写，
    直接用实时全量记录拼装对话稿并进入 stage2（纪要/章节等）。

    Returns:
        True: 定稿成功并已触发 stage2；False: 增量内容为空（应回退 stage1 兜底）。
    """
    full_transcript = tasks[task_id].get("realtime_full_transcript")
    dialogue = _build_dialogue_from_realtime(full_transcript) if full_transcript else []
    if not dialogue:
        return False

    tasks[task_id]["dialogue"] = dialogue
    tasks[task_id]["speaker_count"] = len({d.get("speaker_id") for d in dialogue})
    tasks[task_id]["transcript_source"] = "local_incremental"
    logger.info(
        f"[{task_id[:8]}] 本地增量转写定稿（D-I2，跳过 stage1 全量重跑）: "
        f"{len(full_transcript)} 句 → {len(dialogue)} 条对话"
    )
    joblog.append_event(
        task_id, joblog.STAGE_TRANSCRIBE,
        f"本地增量转写定稿（{len(full_transcript)} 句，未重跑全量）",
    )

    # 复用实时阶段的说话人绑定作为姓名映射（键转 int，UUID 翻译成真名） / Reuse realtime speaker binding (keys to int, UUID translated to real name)
    speaker_mapping = None
    binding = tasks[task_id].get("realtime_speaker_binding")
    if binding:
        try:
            speaker_mapping = {}
            for k, uuid in binding.items():
                spk = speakers.get_speaker_by_id(uuid)
                if spk:
                    speaker_mapping[int(k)] = spk.name
            if not speaker_mapping:
                speaker_mapping = None
        except (ValueError, TypeError):
            speaker_mapping = None

    save_task_to_disk(task_id)
    _cleanup_normalized_intermediate(task_id)
    _run_stage2_for_task(task_id, audio_path, speaker_mapping)
    return True


def _try_realtime_fallback(task_id: str, audio_path: Path) -> bool:
    """批转写失败/为空时，降级使用实时转写结果生成纪要。
    When batch transcription fails/yields empty, fall back to realtime transcript to generate the summary.

    Returns:
        True: 已成功降级并触发 stage2；False: 无可用实时数据，需走原失败流程。
        True: fallback succeeded and stage2 triggered; False: no realtime data, proceed with original failure path.
    """
    full_transcript = tasks[task_id].get("realtime_full_transcript")
    if not full_transcript:
        return False

    dialogue = _build_dialogue_from_realtime(full_transcript)
    if not dialogue:
        return False

    tasks[task_id]["dialogue"] = dialogue
    tasks[task_id]["speaker_count"] = len({d.get("speaker_id") for d in dialogue})
    tasks[task_id]["transcript_source"] = "realtime_fallback"
    logger.warning(
        f"[{task_id[:8]}] 批转写无有效语音，降级使用实时转写结果（{len(full_transcript)} 句 → {len(dialogue)} 条对话）"
    )
    joblog.append_event(
        task_id, joblog.STAGE_TRANSCRIBE,
        f"批转写无有效语音，降级使用实时转写结果（{len(full_transcript)} 句）", level="warn",
    )

    # 复用实时阶段的说话人绑定作为姓名映射（键转 int，UUID 翻译成真名） / Reuse realtime speaker binding as name mapping (keys to int, UUID translated to real name)
    speaker_mapping = None
    binding = tasks[task_id].get("realtime_speaker_binding")
    if binding:
        try:
            speaker_mapping = {}
            for k, uuid in binding.items():
                spk = speakers.get_speaker_by_id(uuid)
                if spk:
                    speaker_mapping[int(k)] = spk.name
            if not speaker_mapping:
                speaker_mapping = None
        except (ValueError, TypeError):
            speaker_mapping = None

    save_task_to_disk(task_id)
    # 降级不依赖归一化音频，按设置清理中间产物 / Fallback doesn't need normalized audio; clean intermediate per settings
    _cleanup_normalized_intermediate(task_id)
    _run_stage2_for_task(task_id, audio_path, speaker_mapping)
    return True


# ============================================================
# 后台管线函数
# ============================================================


def run_pipeline_task(
    task_id: str,
    audio_path: Path,
    audio_name: str,
    speaker_mapping: dict = None,
    speaker_count: int = None,
    engine_override: str = None,
):
    """后台执行管线第一阶段（转写），完成后等待说话人绑定。含瞬时错误自动重试。

    engine_override（DEF-QA-R1-04 / AC-4）：显式引擎模式（如 "cloud"），仅在用户
    于本地失败后**显式确认**切云端重试时由端点传入；None 维持设置自动判定。
    任务音频与笔记状态由既有任务存储独立持久化，回退重跑不丢失（AC-4）。
    """
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
        # AC-4：本地引擎失败时携带回退标志与错误码，供 UI 在用户显式确认后
        # 以 transcribe_audio(engine_override="cloud") 重跑（绝不静默上云，PRD R7）。
        tasks[task_id]["error_code"] = err_info.get("error_code", "")
        tasks[task_id]["can_fallback_cloud"] = err_info.get("can_fallback_cloud", False)
        joblog.append_event(
            task_id, joblog.STAGE_ERROR, f"转写阶段失败: {e}", level="error",
            detail={"category": err_info["category"], "suggestion": err_info["suggestion"]},
        )
        save_task_to_disk(task_id)

    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = 0
    tasks[task_id]["retry_count"] = 0
    task_start = time.perf_counter()

    # D-I2（R9）：本地分段增量转写已在会中逐段定稿 → 跳过 stage1 全量重跑，
    # 直接拼接定稿并进 stage2；增量内容为空时撤销标记，回退下方 stage1 兜底。
    if tasks[task_id].get("transcript_finalized_incremental"):
        joblog.append_event(task_id, joblog.STAGE_TRANSCRIBE, "本地增量定稿路径（D-I2，跳过全量转写）")
        if _finalize_incremental_transcript(task_id, audio_path):
            return
        tasks[task_id]["transcript_finalized_incremental"] = False
        logger.warning(f"[{task_id[:8]}] 增量定稿内容为空，回退 stage1 全量转写兜底")
        joblog.append_event(
            task_id, joblog.STAGE_TRANSCRIBE,
            "增量定稿内容为空，回退全量转写兜底", level="warn",
        )

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
                engine_override=engine_override,
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

            # 空转写降级兜底：批转写成功但无有效对话稿（如 VAD 判静音）时，
            # 若存在实时转写内容则降级用其生成纪要，而非整单失败。
            # Empty-transcription fallback: when batch ASR succeeds but yields no dialogue
            # (e.g. VAD judged silence), fall back to realtime transcript if available.
            if not dialogue:
                # 先持久化归一化路径，供降级兜底内部清理中间文件 / Persist normalized path so fallback can clean the intermediate file
                tasks[task_id]["normalized_path"] = result.get("normalized_path")
                if _try_realtime_fallback(task_id, audio_path):
                    return

            # 检查是否有预设的说话人映射（向后兼容）
            if speaker_mapping:
                # 有预设映射，直接运行第二阶段
                save_task_to_disk(task_id)
                _cleanup_normalized_intermediate(task_id)
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
                        # 锚点：文本桥接已命中或本场已确认绑定的注册人不参与声纹分配
                        locked = {
                            str(u) for u in auto_mapping.values() if u
                        } | {
                            str(u) for u in (tasks[task_id].get("speaker_uuid_mapping") or {}).values() if u
                        }
                        vp_results = voiceprint.auto_identify_speakers(
                            audio_path=normalized_path,
                            dialogue=dialogue,
                            exclude_uuids=locked or None,
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

                # 声纹底库只接受用户手工确认的绑定（见 speakers.py set_speaker_mapping
                # → _register_voiceprints_bg）；P0 文本桥接 / P1 声纹等自动识别命中
                # 不回写声纹，防止误识别结果自我强化、污染底库。
                if not auto_mapping:
                    # 无自动匹配：不阻塞管线，纪要先以通用说话人标签生成；
                    # 前端绑定栏保留，用户确认关联后按真实身份重新生成纪要
                    joblog.append_event(
                        task_id, joblog.STAGE_BIND,
                        "未命中自动匹配，先以通用标签生成纪要，等待用户事后关联说话人",
                    )

                # 直接运行第二阶段（不再等待用户确认绑定）
                save_task_to_disk(task_id)

                # 清理中间产物：归一化文件在 Stage 1 完成后不再需要
                # （声纹注册已在 Stage 1 内完成，Stage 2 不依赖归一化音频）
                _cleanup_normalized_intermediate(task_id)

                _run_stage2_for_task(task_id, audio_path, auto_mapping)

            return  # 成功，退出重试循环

        except Exception as e:
            if is_transient_error(e) and attempt < PIPELINE_MAX_RETRIES:
                # 瞬时错误且还有重试机会
                delay = PIPELINE_RETRY_DELAYS[attempt]
                tasks[task_id]["retry_count"] = attempt + 1
                tasks[task_id]["message"] = _("Encountered transient error, retrying in {delay}s ({attempt}/{max_retries})...").format(delay=delay, attempt=attempt + 1, max_retries=PIPELINE_MAX_RETRIES)
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
                # 非瞬时错误（如 SUCCESS_WITH_NO_VALID_FRAGMENT 静音判定）且存在实时转写内容时，
                # 降级用实时结果生成纪要，避免整单失败；瞬时错误保留给用户手动重试（批转写质量更高）。
                # For non-transient errors (e.g. SUCCESS_WITH_NO_VALID_FRAGMENT) with realtime content available,
                # fall back to realtime results; transient errors are left for manual retry (higher batch quality).
                if not is_transient_error(e) and _try_realtime_fallback(task_id, audio_path):
                    return
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

            # 空转写检测：ASR 未识别到有效内容时，不应继续生成纪要并标记 completed，
            # 否则前端会因 chapters 为空而陷入"章节划分中..."无限加载态。
            # Empty transcription guard: when ASR yields no content, mark failed instead of completed.
            if not dialogue:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["progress"] = 100
                tasks[task_id]["error"] = "empty_transcription"
                tasks[task_id]["failed_stage"] = "transcribe"
                tasks[task_id]["error_category"] = "audio"
                tasks[task_id]["error_suggestion"] = _("No valid speech detected in the audio. Please check the recording quality and try again.")
                tasks[task_id]["message"] = _("No valid speech detected")
                joblog.append_event(
                    task_id, joblog.STAGE_ERROR,
                    "转写结果为空，未识别到有效语音内容，标记为 failed", level="error",
                    detail={"category": "audio", "reason": "empty_dialogue"},
                )
                save_task_to_disk(task_id)
                logger.warning(f"[{task_id[:8]}] 转写结果为空（dialogue=0），标记为 failed")
                return

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
            # 一页纸系数：从属单个会议，旧任务缺字段按 1 兜底（契约见 docs/API_CONTRACTS.md）
            one_page_factor = float((tasks[task_id].get("one_page") or {}).get("summary", 1) or 1)
            result = run_pipeline_stage2(
                dialogue=dialogue,
                speaker_mapping=speaker_mapping,
                audio_path=audio_path,
                on_progress=on_progress,
                meeting_time=meeting_time,
                user_notes=tasks[task_id].get("user_notes"),
                one_page_factor=one_page_factor,
            )

            tasks[task_id]["status"] = "completed"
            tasks[task_id]["progress"] = 100
            tasks[task_id]["message"] = _("Completed")
            tasks[task_id]["summary"] = result.get("summary")
            tasks[task_id]["title"] = result.get("title")
            tasks[task_id]["output_path"] = result.get("output_path")
            tasks[task_id]["dialogue"] = result.get("dialogue")
            tasks[task_id]["speaker_mapping"] = result.get("speaker_mapping", {})
            tasks[task_id]["speaker_uuid_mapping"] = result.get("speaker_uuid_mapping", {})
            tasks[task_id]["chapters"] = result.get("chapters", [])

            summary_text = result.get("summary", "")
            if summary_text:
                # DC-UNIFY-01：行动项（checkbox）与结论（主要结论/决策）合流为唯一一条决策流，
                # 后者以「待确认」态入盘；只覆盖 source=auto，手动/注入节点与墓碑均保留（DC-R2-BE）。
                try:
                    parsed_todos = parse_todos_from_summary(summary_text)
                    parsed_decisions, parse_status = parse_decisions_with_status(summary_text)
                    tasks[task_id]["todos"] = merge_flow_after_regen(
                        tasks[task_id].get("todos") or [],
                        parsed_todos + parsed_decisions,
                        tasks[task_id].get("decision_deletions"),
                    )
                    if parsed_todos or parsed_decisions:
                        logger.info(
                            f"[{task_id[:8]}] 自动提取决策流 {len(parsed_todos) + len(parsed_decisions)} 条"
                            f"（行动项 {len(parsed_todos)} · 结论 {len(parsed_decisions)}）"
                        )
                    if parse_status:
                        logger.warning(f"[{task_id[:8]}] 决策解析降级（{parse_status}），本轮 auto 结论置空")
                        joblog.append_event(
                            task_id, joblog.STAGE_SUMMARY,
                            f"决策解析降级（{parse_status}）：本轮 auto 结论置空，不影响任务状态", level="warn",
                        )
                except Exception as e:
                    kept = [t for t in (tasks[task_id].get("todos") or []) if t.get("source") != "auto"]
                    tasks[task_id]["todos"] = kept
                    logger.warning(f"[{task_id[:8]}] 决策流提取异常（不阻断流水线）: {e}")
                    joblog.append_event(
                        task_id, joblog.STAGE_SUMMARY,
                        f"决策流提取异常，auto 节点置空（不阻断流水线）: {e}", level="warn",
                    )

            joblog.append_event(task_id, joblog.STAGE_SUMMARY, "纪要生成完成")
            save_task_to_disk(task_id)

            # 转写分层 WP-2：设置开启且 llm 路由可用时，会后自动生成书面版。
            # 守护线程执行；跳过/失败均仅日志，sidecar error 自描述，不影响会议产物。
            try:
                from core.transcript_formal import maybe_auto_formalize
                maybe_auto_formalize(task_id)
            except Exception as e:
                logger.warning(f"[{task_id[:8]}] 自动书面化钩子异常（不影响产物）: {e}")

            # [管线] 首次完成后自动同步到知识库文件夹（仅当关联项目且启用同步时） /
            # Auto-sync to knowledge base folder on first completion (only when project linked and sync enabled)
            try:
                from core.projects import sync_meeting_to_folders
                synced_files = sync_meeting_to_folders(tasks[task_id])
                if synced_files:
                    logger.info(f"[{task_id[:8]}] 首次完成自动同步到知识库，写入 {len(synced_files)} 个文件")
                    joblog.append_event(
                        task_id, joblog.STAGE_SUMMARY,
                        f"自动同步到知识库，写入 {len(synced_files)} 个文件",
                    )
            except Exception as e:
                logger.warning(f"[{task_id[:8]}] 首次完成自动同步失败（不影响主流程）: {e}")

            stage2_elapsed = time.perf_counter() - stage2_start
            logger.info(f"[PERF] {task_id[:8]} 纪要任务总计: {stage2_elapsed:.3f}s")

            return  # 成功

        except Exception as e:
            if is_transient_error(e) and attempt < PIPELINE_MAX_RETRIES:
                delay = PIPELINE_RETRY_DELAYS[attempt]
                tasks[task_id]["retry_count"] = tasks[task_id].get("retry_count", 0) + 1
                tasks[task_id]["message"] = _("Minute generation encountered transient error, retrying in {delay}s ({attempt}/{max_retries})...").format(delay=delay, attempt=tasks[task_id].get("retry_count", 0) + 1, max_retries=PIPELINE_MAX_RETRIES)
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
# Re-export（兼容现有 import 路径）
# ============================================================

from core.speaker_count import (  # noqa: E402,F401
    SPEAKER_COUNT_MAX,
    SPEAKER_COUNT_MIN,
)
