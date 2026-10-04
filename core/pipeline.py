"""
core/pipeline.py — 串联全流程 / Pipeline orchestrating all stages

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 1.0.0

职责 / Responsibilities:
  1. 编排：音频归一化 → 上传 → 转写 → 纪要 / Orchestrate: audio normalize → upload → transcribe → summary
  2. 输出 Markdown 纪要到 data/output/ / Output Markdown summary to data/output/
  3. 提供进度回调接口（供 UI 使用） / Provide progress callback interface (for UI)

数据流（详见 docs/ARCHITECTURE.md） / Data flow (see docs/ARCHITECTURE.md):
  音频文件 → ffmpeg 归一化 → 上传 DashScope → paraformer-v2 转写
  Audio file → ffmpeg normalize → upload to DashScope → paraformer-v2 transcribe
  → 组装对话稿 → qwen-plus 纪要 → Markdown 输出
  → assemble dialogue → qwen-plus summary → Markdown output
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from . import speakers
from .audio import get_audio_duration, normalize_audio
from .chapters import generate_chapters
from .hotwords import get_or_create_vocabulary
from .perf import perf_timer
from .summarize import generate_summary, generate_title, save_summary
from .transcribe import transcribe_audio
from .transcript_cleanup import clean_dialogue_for_consumers

logger = logging.getLogger(__name__)

# 加载环境变量 / Load environment variables
load_dotenv()


# 默认配置 / Default configuration
DEFAULT_CONFIG = {
    "asr_model": "paraformer-v2",
    "llm_model": "qwen-plus",
    "diarization_enabled": True,
    "language_hints": ["zh", "en"],
    "sample_rate": 16000,
    "channels": 1,
    "output_dir": "data/output",
}


class PipelineProgress:
    """管线进度回调数据 / Pipeline progress callback data"""
    def __init__(self, stage: str, message: str, percent: int = 0):
        self.stage = stage
        self.message = message
        self.percent = percent

    def __repr__(self):
        return f"[{self.percent}%] {self.stage}: {self.message}"


def run_pipeline_stage1(
    audio_path: str | Path,
    config: dict | None = None,
    on_progress: Callable[[PipelineProgress], None] | None = None,
    speaker_count: int | None = None,
    engine_override: str | None = None,
) -> dict:
    """
    管线第一阶段：音频 → 对话稿 / Pipeline stage 1: audio → dialogue.

    完成归一化、上传、转写、组装对话稿 / Perform normalization, upload, transcription, and dialogue assembly.
    返回对话稿和转写结果，供用户进行说话人绑定 / Return dialogue and transcription for speaker binding.

    Args:
        speaker_count: 说话人数量提示（来自实时声纹聚类估算），传给转写 API 辅助分离 / Speaker count hint (from realtime voiceprint clustering), passed to transcription API
        engine_override: 显式指定转写引擎模式（AC-4 云端回退用，如 "cloud"）；None 维持设置自动判定 / Explicit engine mode (AC-4 cloud fallback); None keeps settings-based selection

    Returns:
        {
            "dialogue": [...],
            "transcription": {...},
            "audio_duration": 秒 / seconds,
            "normalized_path": 归一化后的音频路径 / normalized audio path,
        }
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    def progress(stage: str, message: str, percent: int):
        p = PipelineProgress(stage, message, percent)
        logger.info(str(p))
        if on_progress:
            on_progress(p)

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    result = {}
    stage1_start = time.perf_counter()

    # 1. 音频归一化 / Audio normalization
    progress("audio", "正在归一化音频...", 10)
    with perf_timer("音频归一化", category="ffmpeg_normalize"):
        normalized = normalize_audio(
            audio_path,
            sample_rate=cfg["sample_rate"],
            channels=cfg["channels"],
        )
    audio_duration = get_audio_duration(normalized)
    result["audio_duration"] = audio_duration
    result["normalized_path"] = str(normalized)
    progress("audio", f"音频归一化完成 ({audio_duration:.1f}s)", 20)

    # ── 说话人数量兜底 / Speaker count fallback ──
    # 仅当实时聚类/采样估算给出了明确值且 < 2 时才干预 / Only intervene when clustering/sampling gives a definite value < 2.
    # speaker_count=None 的语义是"未知，交给 API 自动估计" / speaker_count=None means "unknown, let API auto-estimate",
    # 不应被当作 "< 2" 强制覆盖为 2 —— 否则会压制 API 的自动估计能力 / should NOT be treated as "< 2" and forced to 2 — that would suppress API auto-estimation
    # 对多人会议造成回归（如 4 人会被钉死成 2 人） / and cause regression for multi-speaker meetings (e.g. 4 speakers pinned to 2).
    FALLBACK_DURATION_THRESHOLD = 30.0  # 秒 / seconds
    if audio_duration > FALLBACK_DURATION_THRESHOLD and speaker_count is not None and speaker_count < 2:
        original_count = speaker_count
        speaker_count = 2
        logger.info(
            f"[说话人兜底] 音频 {audio_duration:.0f}s > {FALLBACK_DURATION_THRESHOLD}s "
            f"但估算说话人={original_count}，强制设为 2"
        )

    # 2. 热词表（可选） / Hotword vocabulary (optional)
    # cloud 模式下无本地 API Key，跳过热词表创建（热词映射后处理仍生效）
    # In cloud mode, no local API key available; skip vocabulary creation (hotword mappings post-processing still works)
    progress("hotwords", "检查热词表...", 35)
    with perf_timer("热词表检查"):
        try:
            vocabulary_id = get_or_create_vocabulary(target_model=cfg["asr_model"])
        except RuntimeError as e:
            logger.warning(f"热词表创建跳过（无本地 API Key 或配置缺失）: {e}")
            vocabulary_id = None
    if vocabulary_id:
        progress("hotwords", f"使用热词表: {vocabulary_id}", 40)
    else:
        progress("hotwords", "无热词", 40)

    # 3. 转写（代理负责上传 + 提交 + 轮询 + 下载） / Transcription (proxy handles upload + submit + poll + download)
    progress("transcribe", "提交转写任务...", 45)
    with perf_timer("转写（含上传+轮询）", category="transcribe"):
        dialogue, transcription = transcribe_audio(
            file_path=normalized,
            model=cfg["asr_model"],
            diarization_enabled=cfg["diarization_enabled"],
            language_hints=cfg["language_hints"],
            vocabulary_id=vocabulary_id,
            speaker_count=speaker_count,
            engine_override=engine_override,
        )
    progress("transcribe", "转写完成", 70)
    result["dialogue"] = dialogue
    result["transcription"] = transcription

    stage1_elapsed = time.perf_counter() - stage1_start
    logger.info(f"[PERF] 管线第一阶段总计: {stage1_elapsed:.3f}s")
    result["perf_stage1"] = stage1_elapsed

    return result


def _collect_speaker_names(dialogue: list[dict]) -> dict[int, str]:
    """采集 {speaker_id: 归一后姓名}（BE-R1：不落 Speaker 编号默认名，空串=未命名）。

    键保留可枚举（供 D5「未识别 N 人」聚合），姓名经读取侧归一化入口收敛。
    Collect {speaker_id: normalized_name}; empty string means unnamed (aggregated per D5).
    """
    from core.speakers import normalize_speaker_name
    names: dict[int, str] = {}
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        if sid not in names:
            names[sid] = normalize_speaker_name(item.get("speaker_name"))
    return names


def run_pipeline_stage2(
    dialogue: list[dict],
    speaker_mapping: dict[int, str] | None = None,
    audio_path: str | Path | None = None,
    config: dict | None = None,
    on_progress: Callable[[PipelineProgress], None] | None = None,
    meeting_time: str | None = None,
    user_notes: str | None = None,
    one_page_factor: float = 1.0,
) -> dict:
    """
    管线第二阶段：对话稿 → 纪要 / Pipeline stage 2: dialogue → summary.

    应用说话人姓名映射，生成纪要并保存 / Apply speaker name mapping, generate and save summary.

    Args:
        dialogue: 第一阶段返回的对话稿 / Dialogue from stage 1
        speaker_mapping: {speaker_id: speaker_uuid} 映射 / mapping
        audio_path: 音频路径（用于生成输出文件名） / Audio path (for output filename)
        config: 配置覆盖 / Config overrides
        on_progress: 进度回调 / Progress callback
        meeting_time: 会议时间（来自音频采集时间） / Meeting time (from audio capture time), e.g. "2026-09-03 14:30"
        user_notes: 用户录音期间输入的笔记，作为纪要生成的上下文 / User notes during recording, used as context for summary generation
        one_page_factor: 一页纸系数（会议级篇幅预算，透传给 generate_summary） / Per-meeting one-page factor

    Returns:
        {
            "summary": "纪要文本 / summary text",
            "dialogue": [...],  # 含 speaker_name / with speaker_name
            "output_path": "纪要文件路径 / summary file path",
            "speaker_mapping": {speaker_id: speaker_name},
        }
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    # 从 settings 读取 LLM 模型（若 config 未显式覆盖） / Load LLM model from settings (if not overridden by config)
    if not config or "llm_model" not in config:
        try:
            from app.store import get_llm_config
            cfg["llm_model"] = get_llm_config().get("model", cfg["llm_model"])
        except Exception:
            pass  # 保持默认值 / Keep default

    def progress(stage: str, message: str, percent: int):
        p = PipelineProgress(stage, message, percent)
        logger.info(str(p))
        if on_progress:
            on_progress(p)

    result = {}
    stage2_start = time.perf_counter()

    # 5. 说话人姓名化 / Apply speaker names
    progress("speakers", "应用说话人姓名...", 75)
    if speaker_mapping:
        dialogue = speakers.apply_speaker_names(dialogue, speaker_mapping)
        result["speaker_mapping"] = _collect_speaker_names(dialogue)
        result["speaker_uuid_mapping"] = {str(k): v for k, v in speaker_mapping.items()}
        progress("speakers", f"已应用 {len(speaker_mapping)} 个姓名", 80)
    else:
        # 无绑定映射：键保留、姓名留空（可枚举可计数），展示层按 D5「未识别 N 人」聚合 /
        # No binding mapping; keep keys enumerable with empty names, frontend aggregates per D5
        speaker_name_map = _collect_speaker_names(dialogue)
        result["speaker_mapping"] = speaker_name_map
        result["speaker_uuid_mapping"] = {}
        progress("speakers", f"未配置姓名映射，{len(speaker_name_map)} 位说话人待命名", 80)

    result["dialogue"] = dialogue

    # 转写分层（PLAN-TRANSCRIPT-LAYERING）：纪要/标题/章节吃「清理版」深拷贝，
    # result["dialogue"] 与 save_summary 导出仍是逐字稿原文。
    try:
        from app.store import get_transcript_config
        _cleanup_enabled = bool(get_transcript_config().get("cleanup", {}).get("enabled", True))
    except Exception:
        _cleanup_enabled = True
    consumer_dialogue = clean_dialogue_for_consumers(dialogue, enabled=_cleanup_enabled)

    # 6. 生成纪要 / Generate summary
    progress("summarize", "正在生成纪要...", 85)
    with perf_timer("纪要生成", category="llm_sync"):
        summary = generate_summary(consumer_dialogue, model=cfg["llm_model"], meeting_time=meeting_time, user_notes=user_notes,
                                   one_page_factor=one_page_factor)
    progress("summarize", "纪要生成完成", 90)
    result["summary"] = summary

    # 6.5 生成标题 / Generate title
    progress("title", "正在生成标题...", 92)
    with perf_timer("标题生成", category="llm_sync"):
        title = generate_title(consumer_dialogue, model=cfg["llm_model"])
    progress("title", f"标题生成完成: {title}", 93)
    result["title"] = title

    # 6.6 生成章节 / Generate chapters
    progress("chapters", "正在划分章节...", 94)
    with perf_timer("章节生成", category="llm_sync"):
        chapters = generate_chapters(consumer_dialogue, model=cfg["llm_model"])
    progress("chapters", f"章节划分完成: {len(chapters)} 个章节", 96)
    result["chapters"] = chapters

    # 7. 保存 / Save
    progress("save", "保存纪要...", 98)
    if audio_path:
        audio_path = Path(audio_path)
        output_dir = Path(cfg["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{audio_path.stem}_{timestamp}_纪要.md"
    else:
        output_dir = Path(cfg["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"meeting_{timestamp}_纪要.md"

    saved_path = save_summary(summary, output_path, dialogue)
    result["output_path"] = saved_path
    progress("done", f"完成！纪要已保存: {saved_path}", 100)

    stage2_elapsed = time.perf_counter() - stage2_start
    logger.info(f"[PERF] 管线第二阶段总计: {stage2_elapsed:.3f}s")
    result["perf_stage2"] = stage2_elapsed

    return result


def run_pipeline(
    audio_path: str | Path,
    output_path: str | Path | None = None,
    config: dict | None = None,
    on_progress: Callable[[PipelineProgress], None] | None = None,
    speaker_mapping: dict[int, str] | None = None,
    meeting_time: str | None = None,
) -> dict:
    """
    执行完整管线：音频 → 纪要（向后兼容，内部调用两阶段） / Run full pipeline: audio → summary (backward-compatible, internally calls two stages).

    Returns:
        合并后的结果字典 / Merged result dict
    """
    # 第一阶段：转写 / Stage 1: transcription
    result1 = run_pipeline_stage1(audio_path, config, on_progress)

    # 第二阶段：纪要 / Stage 2: summary
    result2 = run_pipeline_stage2(
        dialogue=result1["dialogue"],
        speaker_mapping=speaker_mapping,
        audio_path=audio_path,
        config=config,
        on_progress=on_progress,
        meeting_time=meeting_time,
    )

    # 合并结果 / Merge results
    return {
        **result1,
        **result2,
    }


def run_pipeline_simple(audio_path: str | Path) -> str:
    """
    简化版管线：只返回纪要文本 / Simplified pipeline: returns only summary text.

    用于快速测试或 CLI 调用 / For quick testing or CLI invocation.
    """
    result = run_pipeline(audio_path)
    return result["summary"]
