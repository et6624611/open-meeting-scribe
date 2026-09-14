"""
core/joblog.py — 会议纪要作业日志（per-task 事件流） / Meeting task job log (per-task event stream)

职责 / Responsibilities:
  1. 以 append-only JSONL 记录单个会议任务从录音 / 转写 / 声纹匹配 / / Record key operations in append-only JSONL for a meeting task: recording / transcription / voiceprint matching /
     绑定 / 纪要生成到 AI 动作的关键操作与运行事件 / binding / summary generation to AI actions.
  2. 为会议助手（AI 对话）提供渐进式上下文：先给轻量概要 / Provide progressive context for AI chat assistant: lightweight summary first,
     再按用户问题检索相关明细，避免全量日志塞入提示词 / then retrieve details by user query, avoiding full log in prompts.

设计原则 / Design principles:
  - 作业日志从属于会议纪要（task_id 为键）：会议助手针对某会议提问时 / Job log belongs to meeting task (keyed by task_id): when querying a specific meeting,
    加载的正是该会议此前发生过的操作与运行痕迹 / loads the operations and traces from that meeting.
  - 只记关键节点，不记 HTTP / 逐句转写等噪声 / Only log key milestones, not HTTP / per-sentence transcription noise.
  - 写入失败绝不影响主链路（静默降级 + 告警日志） / Write failures never affect main pipeline (silent degradation + warning log).

数据文件 / Data file:
  - data/tasks/{task_id}.joblog.jsonl（每行一个 JSON 事件 / one JSON event per line）
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 作业日志目录（与任务元数据同目录，扩展名 .jsonl 以区别于 {id}.json） / Job log directory (same dir as task metadata, .jsonl extension to distinguish from {id}.json)
TASKS_DIR = Path("data/tasks")
TASKS_DIR.mkdir(parents=True, exist_ok=True)

# 事件阶段枚举 / Event stage enumeration
STAGE_RECORD = "record"            # 录音控制 / Recording control
STAGE_TRANSCRIBE = "transcribe"    # 转写（stage1） / Transcription (stage1)
STAGE_VOICEPRINT = "voiceprint"    # 声纹匹配 / Voiceprint matching
STAGE_BIND = "bind"                # 说话人绑定 / Speaker binding
STAGE_SUMMARY = "summary"          # 纪要生成（stage2） / Summary generation (stage2)
STAGE_CHAT_ACTION = "chat_action"  # 会议助手执行的动作 / AI assistant actions
STAGE_ERROR = "error"              # 失败 / 异常 / Failure / Error

# 概要中保留的最近事件条数 / Number of recent events kept in summary
SUMMARY_RECENT = 5
# 明细检索返回上限 / Detail retrieval result limit
SEARCH_LIMIT = 8

# stage → 用户问题触发词（用于渐进式明细检索） / stage → user query trigger keywords (for progressive detail retrieval)
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
    追加一条作业事件 / Append a job event. 写入失败静默降级，绝不抛异常影响主链路 / Write failure is silently degraded, never raises to affect main pipeline.

    Args:
        task_id: 会议任务 ID / Meeting task ID
        stage: 事件阶段（见 STAGE_* 常量） / Event stage (see STAGE_* constants)
        message: 一句话描述（供概要与明细展示） / One-line description (for summary and detail display)
        level: info / warn / error
        detail: 可选结构化补充（如错误分类、命中明细） / Optional structured supplement (e.g. error classification, matched details)
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
    except Exception as e:  # 作业日志是旁路，不允许打断主流程 / Job log is side-channel, must not interrupt main flow
        logger.warning(f"[作业日志] 写入失败 task={task_id[:8]}: {e}")


def read_events(task_id: str, limit: Optional[int] = None) -> list[dict]:
    """
    读取作业事件（按时间正序） / Read job events (chronological order). 文件不存在或损坏返回空列表 / Returns empty list if file missing or corrupt.

    Args:
        limit: 仅返回最近 N 条；None 表示全部 / Return only last N events; None for all
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
                    continue  # 跳过损坏行 / Skip corrupt line
    except Exception as e:
        logger.warning(f"[作业日志] 读取失败 task={task_id[:8]}: {e}")
        return []
    return events[-limit:] if limit else events


def summarize_events(events: list[dict]) -> str:
    """
    生成轻量概要文本：按阶段计数 + 最近若干条一行式 / Generate lightweight summary text: per-stage counts + recent events one-liner.

    作为渐进式加载的第一层，让模型先掌握全局脉络 / First layer of progressive loading, gives model the global overview.
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
    按用户问题检索相关事件（渐进式加载的第二层：按需明细） / Retrieve relevant events by user query (second layer of progressive loading: on-demand details).

    检索策略 / Retrieval strategy:
      1. 阶段命中——问题含某 stage 的触发词，则取该 stage 全部事件 / Stage match — query contains trigger keywords for a stage, take all events of that stage;
      2. 文本命中——事件 message 与问题存在长度 ≥2 的公共子串 / Text match — event message and query share a common substring of length ≥2.
    返回按时间正序的最近 limit 条 / Returns last `limit` events in chronological order.
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
        # 双向子串：问题片段出现在 message，或 message 片段出现在问题 / Bidirectional substring: query fragment in message, or message fragment in query
        if any(tok in msg for tok in _tokens(query)) or any(tok in query for tok in _tokens(msg)):
            picked.append(ev)
    return picked[-limit:]


def _tokens(text: str, min_len: int = 2, max_len: int = 6) -> list[str]:
    """
    粗粒度中文分词：滑窗取连续子串作为候选 token / Coarse-grained Chinese tokenization: sliding window for candidate tokens.

    不引入分词库，用长度受限的 n-gram 近似关键词匹配 / No external tokenizer library; length-limited n-gram approximation for keyword matching.
    """
    text = (text or "").strip()
    toks = []
    for n in range(max_len, min_len - 1, -1):
        for i in range(0, max(0, len(text) - n) + 1):
            toks.append(text[i:i + n])
    return toks


def build_context(task_id: str, query: str) -> Optional[str]:
    """
    构建会议助手的作业日志上下文块（渐进式） / Build job log context block for AI assistant (progressive).

    第一层概要始终包含（命中意图时），第二层明细按 query 检索补充 / First layer summary always included (when intent matched), second layer details retrieved by query.
    无事件返回 None（调用方不注入） / Returns None if no events (caller skips injection).
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
