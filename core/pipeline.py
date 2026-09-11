"""
core/pipeline.py — 串联全流程

作者：王永亮
创建：2026-09-03
版本：1.0.0

职责：
  1. 编排：音频归一化 → 上传 → 转写 → 纪要
  2. 输出 Markdown 纪要到 data/output/
  3. 提供进度回调接口（供 UI 使用）

数据流（详见 docs/ARCHITECTURE.md）：
  音频文件 → ffmpeg 归一化 → 上传 DashScope → paraformer-v2 转写
  → 组装对话稿 → qwen-plus 纪要 → Markdown 输出
"""

import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Callable

from dotenv import load_dotenv

from .audio import normalize_audio, get_audio_duration
from .transcribe import transcribe_audio
from .hotwords import get_or_create_vocabulary
from .summarize import generate_summary, generate_title, save_summary
from .chapters import generate_chapters
from . import speakers
from .perf import perf_timer

logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()


# 默认配置
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
    """管线进度回调数据"""
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
) -> dict:
    """
    管线第一阶段：音频 → 对话稿。

    完成归一化、上传、转写、组装对话稿。
    返回对话稿和转写结果，供用户进行说话人绑定。

    Args:
        speaker_count: 说话人数量提示（来自实时声纹聚类估算），传给转写 API 辅助分离

    Returns:
        {
            "dialogue": [...],
            "transcription": {...},
            "audio_duration": 秒,
            "normalized_path": 归一化后的音频路径,
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

    # 1. 音频归一化
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

    # ── 说话人数量兜底 ──
    # 仅当实时聚类/采样估算给出了明确值且 < 2 时才干预。
    # speaker_count=None 的语义是"未知，交给 API 自动估计"，
    # 不应被当作 "< 2" 强制覆盖为 2 —— 否则会压制 API 的自动估计能力，
    # 对多人会议造成回归（如 4 人会被钉死成 2 人）。
    FALLBACK_DURATION_THRESHOLD = 30.0  # 秒
    if audio_duration > FALLBACK_DURATION_THRESHOLD and speaker_count is not None and speaker_count < 2:
        original_count = speaker_count
        speaker_count = 2
        logger.info(
            f"[说话人兜底] 音频 {audio_duration:.0f}s > {FALLBACK_DURATION_THRESHOLD}s "
            f"但估算说话人={original_count}，强制设为 2"
        )

    # 2. 热词表（可选）
    progress("hotwords", "检查热词表...", 35)
    with perf_timer("热词表检查"):
        vocabulary_id = get_or_create_vocabulary(target_model=cfg["asr_model"])
    if vocabulary_id:
        progress("hotwords", f"使用热词表: {vocabulary_id}", 40)
    else:
        progress("hotwords", "无热词", 40)

    # 3. 转写（代理负责上传 + 提交 + 轮询 + 下载）
    progress("transcribe", "提交转写任务...", 45)
    with perf_timer("转写（含上传+轮询）", category="transcribe"):
        dialogue, transcription = transcribe_audio(
            file_path=normalized,
            model=cfg["asr_model"],
            diarization_enabled=cfg["diarization_enabled"],
            language_hints=cfg["language_hints"],
            vocabulary_id=vocabulary_id,
            speaker_count=speaker_count,
        )
    progress("transcribe", "转写完成", 70)
    result["dialogue"] = dialogue
    result["transcription"] = transcription

    stage1_elapsed = time.perf_counter() - stage1_start
    logger.info(f"[PERF] 管线第一阶段总计: {stage1_elapsed:.3f}s")
    result["perf_stage1"] = stage1_elapsed

    return result


def run_pipeline_stage2(
    dialogue: list[dict],
    speaker_mapping: dict[int, str] | None = None,
    audio_path: str | Path | None = None,
    config: dict | None = None,
    on_progress: Callable[[PipelineProgress], None] | None = None,
    meeting_time: str | None = None,
    user_notes: str | None = None,
) -> dict:
    """
    管线第二阶段：对话稿 → 纪要。

    应用说话人姓名映射，生成纪要并保存。

    Args:
        dialogue: 第一阶段返回的对话稿
        speaker_mapping: {speaker_id: speaker_uuid} 映射
        audio_path: 音频路径（用于生成输出文件名）
        config: 配置覆盖
        on_progress: 进度回调
        meeting_time: 会议时间（来自音频采集时间），如 "2026-09-03 14:30"
        user_notes: 用户录音期间输入的笔记，作为纪要生成的上下文

    Returns:
        {
            "summary": "纪要文本",
            "dialogue": [...],  # 含 speaker_name
            "output_path": "纪要文件路径",
            "speaker_mapping": {speaker_id: speaker_name},
        }
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    # 从 settings 读取 LLM 模型（若 config 未显式覆盖）
    if not config or "llm_model" not in config:
        try:
            from app.store import get_llm_config
            cfg["llm_model"] = get_llm_config().get("model", cfg["llm_model"])
        except Exception:
            pass  # 保持默认值

    def progress(stage: str, message: str, percent: int):
        p = PipelineProgress(stage, message, percent)
        logger.info(str(p))
        if on_progress:
            on_progress(p)

    result = {}
    stage2_start = time.perf_counter()

    # 5. 说话人姓名化
    progress("speakers", "应用说话人姓名...", 75)
    if speaker_mapping:
        dialogue = speakers.apply_speaker_names(dialogue, speaker_mapping)
        speaker_name_map = {}
        for item in dialogue:
            sid = item.get("speaker_id", 0)
            name = item.get("speaker_name", f"说话人{sid + 1}")
            speaker_name_map[sid] = name
        result["speaker_mapping"] = speaker_name_map
        result["speaker_uuid_mapping"] = {str(k): v for k, v in speaker_mapping.items()}
        progress("speakers", f"已应用 {len(speaker_mapping)} 个姓名", 80)
    else:
        # 无绑定映射时，仍从 dialogue 构建默认姓名映射（确保前端说话人视图始终可显示）
        speaker_name_map = {}
        for item in dialogue:
            sid = item.get("speaker_id", 0)
            if sid not in speaker_name_map:
                speaker_name_map[sid] = item.get("speaker_name", f"说话人{sid + 1}")
        result["speaker_mapping"] = speaker_name_map
        result["speaker_uuid_mapping"] = {}
        progress("speakers", f"未配置姓名映射，使用默认名称（{len(speaker_name_map)} 位说话人）", 80)

    result["dialogue"] = dialogue

    # 6. 生成纪要
    progress("summarize", "正在生成纪要...", 85)
    with perf_timer("纪要生成", category="llm_sync"):
        summary = generate_summary(dialogue, model=cfg["llm_model"], meeting_time=meeting_time, user_notes=user_notes)
    progress("summarize", "纪要生成完成", 90)
    result["summary"] = summary

    # 6.5 生成标题
    progress("title", "正在生成标题...", 92)
    with perf_timer("标题生成", category="llm_sync"):
        title = generate_title(dialogue, model=cfg["llm_model"])
    progress("title", f"标题生成完成: {title}", 93)
    result["title"] = title

    # 6.6 生成章节
    progress("chapters", "正在划分章节...", 94)
    with perf_timer("章节生成", category="llm_sync"):
        chapters = generate_chapters(dialogue, model=cfg["llm_model"])
    progress("chapters", f"章节划分完成: {len(chapters)} 个章节", 96)
    result["chapters"] = chapters

    # 7. 保存
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
    执行完整管线：音频 → 纪要（向后兼容，内部调用两阶段）。

    Returns:
        合并后的结果字典
    """
    # 第一阶段：转写
    result1 = run_pipeline_stage1(audio_path, config, on_progress)

    # 第二阶段：纪要
    result2 = run_pipeline_stage2(
        dialogue=result1["dialogue"],
        speaker_mapping=speaker_mapping,
        audio_path=audio_path,
        config=config,
        on_progress=on_progress,
        meeting_time=meeting_time,
    )

    # 合并结果
    return {
        **result1,
        **result2,
    }


def run_pipeline_simple(audio_path: str | Path) -> str:
    """
    简化版管线：只返回纪要文本。

    用于快速测试或 CLI 调用。
    """
    result = run_pipeline(audio_path)
    return result["summary"]
