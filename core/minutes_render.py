"""
core/minutes_render.py — 纪要下载按需渲染（ASSET_SYNC P1）

下载件不再生成时落盘冻结：从 SSOT（任务 JSON）按需渲染，口径与前端纪要 Tab /
AI 基线一致（task_final_summary：user_summary 存在即优先，含空串），并附原始
对话稿。渲染结果不落 data/output/——md 直接作响应返回，docx 转临时缓存件。
CLI（cli.py transcribe -o）保留文件输出，见 run_pipeline_stage2(emit_file=True)。

契约来源 / Source of truth: docs/design/ASSET_SYNC_ARCHITECTURE.md §5.1 / §6 P1。

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-11
版本 / Version: 1.0.0
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.chat_context import task_final_summary
from core.summarize import format_dialogue_for_display


def render_minutes_md(task: dict) -> str:
    """定稿纪要 + 原始对话稿附录（与旧 save_summary 落盘件同构，但从不落盘）。

    定稿口径收口 task_final_summary()：用户编辑（含显式清空）永远优先于 AI 初稿，
    修复旧落盘快照「编辑后下载仍是旧版」缺陷（G1）。
    """
    content = task_final_summary(task)
    dialogue = task.get("dialogue")
    if dialogue:
        content += "\n\n---\n\n## 附：原始对话稿\n\n"
        content += format_dialogue_for_display(dialogue)
    return content


def minutes_download_name(task: dict) -> str:
    """下载文件名：沿用旧落盘件命名规则 {音频stem}_{时间戳}_纪要.md（无音频 meeting 兜底）。"""
    audio_name = str(task.get("audio_name") or "").strip()
    stem = Path(audio_name).stem if audio_name else "meeting"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stem}_{timestamp}_纪要.md"


def docx_cache_name(task_id: str) -> str:
    """按需 docx 临时缓存件命名（data/output/ 下，retention 到期可清，任务删除联动清理）。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{task_id}_{timestamp}_纪要.docx"
