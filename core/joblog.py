"""
core/joblog.py — 会议纪要作业日志（per-task 事件流）

职责：
  1. 以 append-only JSONL 记录单个会议任务从录音 / 转写 / 声纹匹配 /
     绑定 / 纪要生成到 AI 动作的关键操作与运行事件。
  2. 为会议助手（AI 对话）提供渐进式上下文：先给轻量概要，
     再按用户问题检索相关明细，避免全量日志塞入提示词。

设计原则：
  - 作业日志从属于会议纪要（task_id 为键）：会议助手针对某会议提问时，
    加载的正是该会议此前发生过的操作与运行痕迹。
  - 只记关键节点，不记 HTTP / 逐句转写等噪声。
  - 写入失败绝不影响主链路（静默降级 + 告警日志）。

数据文件：
  - data/tasks/{task_id}.joblog.jsonl（每行一个 JSON 事件）
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 作业日志目录（与任务元数据同目录，扩展名 .jsonl 以区别于 {id}.json）
TASKS_DIR = Path("data/tasks")
TASKS_DIR.mkdir(parents=True, exist_ok=True)

# 事件阶段枚举
STAGE_RECORD = "record"            # 录音控制
STAGE_TRANSCRIBE = "transcribe"    # 转写（stage1）
STAGE_VOICEPRINT = "voiceprint"    # 声纹匹配
STAGE_BIND = "bind"                # 说话人绑定
STAGE_SUMMARY = "summary"          # 纪要生成（stage2）
STAGE_CHAT_ACTION = "chat_action"  # 会议助手执行的动作
STAGE_ERROR = "error"              # 失败 / 异常

# 概要中保留的最近事件条数
SUMMARY_RECENT = 5
# 明细检索返回上限
SEARCH_LIMIT = 8

# stage → 用户问题触发词（用于渐进式明细检索）
STAGE_KEYWORDS: dict[str, list[str]] = {
    STAGE_RECORD: ["录音", "录制", "暂停", "恢复", "停止"],
    STAGE_TRANSCRIBE: ["转写", "识别", "解析", "音频", "说话人数"],
    STAGE_VOICEPRINT: ["声纹", "匹配", "身份", "识别"],
    STAGE_BIND: ["绑定", "说话人", "姓名", "归属"],
    STAGE_SUMMARY: ["纪要", "总结", "摘要", "生成"],
    STAGE_CHAT_ACTION: ["操作", "动作", "助手", "执行"],
    STAGE_ERROR: ["失败", "错", "异常", "报错", "卡"],
}


def _log_file(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.joblog.jsonl"


def append_event(
    task_id: str,
    stage: str,
    message: str,
    level: str = "info",
    detail: Optional[dict] = None,
) -> None:
    """
    追加一条作业事件。写入失败静默降级，绝不抛异常影响主链路。

    Args:
        task_id: 会议任务 ID
        stage: 事件阶段（见 STAGE_* 常量）
        message: 一句话描述（供概要与明细展示）
        level: info / warn / error
        detail: 可选结构化补充（如错误分类、命中明细）
    """
    if not task_id:
        return
    event = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "stage": stage,
        "level": level,
        "message": message,
    }
    if detail:
        event["detail"] = detail
    try:
        with open(_log_file(task_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:  # 作业日志是旁路，不允许打断主流程
        logger.warning(f"[作业日志] 写入失败 task={task_id[:8]}: {e}")


def read_events(task_id: str, limit: Optional[int] = None) -> list[dict]:
    """
    读取作业事件（按时间正序）。文件不存在或损坏返回空列表。

    Args:
        limit: 仅返回最近 N 条；None 表示全部
    """
    path = _log_file(task_id)
    if not path.exists():
        return []
    events: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # 跳过损坏行
    except Exception as e:
        logger.warning(f"[作业日志] 读取失败 task={task_id[:8]}: {e}")
        return []
    return events[-limit:] if limit else events


def summarize_events(events: list[dict]) -> str:
    """
    生成轻量概要文本：按阶段计数 + 最近若干条一行式。

    作为渐进式加载的第一层，让模型先掌握全局脉络。
    """
    if not events:
        return ""
    counts: dict[str, int] = {}
    for ev in events:
        counts[ev.get("stage", "?")] = counts.get(ev.get("stage", "?"), 0) + 1
    count_text = "、".join(f"{k}×{v}" for k, v in counts.items())
    lines = [f"事件总数 {len(events)}（{count_text}）", "最近操作："]
    for ev in events[-SUMMARY_RECENT:]:
        lines.append(f"- {ev.get('ts', '?')} [{ev.get('stage', '?')}] {ev.get('message', '')}")
    return "\n".join(lines)


def search_events(events: list[dict], query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """
    按用户问题检索相关事件（渐进式加载的第二层：按需明细）。

    检索策略：
      1. 阶段命中——问题含某 stage 的触发词，则取该 stage 全部事件；
      2. 文本命中——事件 message 与问题存在长度 ≥2 的公共子串。
    返回按时间正序的最近 limit 条。
    """
    if not events or not query:
        return []
    hit_stages = {
        stage for stage, kws in STAGE_KEYWORDS.items() if any(kw in query for kw in kws)
    }
    picked: list[dict] = []
    for ev in events:
        if ev.get("stage") in hit_stages:
            picked.append(ev)
            continue
        msg = ev.get("message", "")
        # 双向子串：问题片段出现在 message，或 message 片段出现在问题
        if any(tok in msg for tok in _tokens(query)) or any(tok in query for tok in _tokens(msg)):
            picked.append(ev)
    return picked[-limit:]


def _tokens(text: str, min_len: int = 2, max_len: int = 6) -> list[str]:
    """
    粗粒度中文分词：滑窗取连续子串作为候选 token。

    不引入分词库，用长度受限的 n-gram 近似关键词匹配。
    """
    text = (text or "").strip()
    toks = []
    for n in range(max_len, min_len - 1, -1):
        for i in range(0, max(0, len(text) - n) + 1):
            toks.append(text[i:i + n])
    return toks


def build_context(task_id: str, query: str) -> Optional[str]:
    """
    构建会议助手的作业日志上下文块（渐进式）。

    第一层概要始终包含（命中意图时），第二层明细按 query 检索补充。
    无事件返回 None（调用方不注入）。
    """
    events = read_events(task_id)
    if not events:
        return None
    blocks = ["## 本会议作业日志概要\n" + summarize_events(events)]
    detail_events = search_events(events, query)
    if detail_events:
        lines = []
        for ev in detail_events:
            line = f"- {ev.get('ts', '?')} [{ev.get('stage', '?')}/{ev.get('level', 'info')}] {ev.get('message', '')}"
            if ev.get("detail"):
                line += f"（{json.dumps(ev['detail'], ensure_ascii=False)}）"
            lines.append(line)
        blocks.append("## 相关作业明细\n" + "\n".join(lines))
    return "\n\n".join(blocks)
