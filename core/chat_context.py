"""
core/chat_context.py — AI 对话上下文构建与注入内容提取 / AI chat context building and injectable content extraction

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-30
版本 / Version: 1.2.0

职责 / Responsibilities:
  - 页面上下文构建（_build_page_context） / Page context building (_build_page_context)
  - 定稿纪要口径（task_final_summary） / Final summary resolution (user_summary over generated)
  - 说话人名称映射（build_speaker_name_map） / Speaker name mapping (build_speaker_name_map)
  - 洞察台注入块（build_insights_context_block） / Insight Deck injection block (build_insights_context_block)
  - 注入内容提取（extract_injectable_items） / Injectable content extraction (extract_injectable_items)
  - 作业日志意图检测（is_joblog_intent） / Job log intent detection (is_joblog_intent)

从 app/routers/chat.py 拆分而来 / Split from app/routers/chat.py.
"""

import json
import logging
import re
from pathlib import Path

from app.store import tasks
from core import hotwords, projects, speakers
from core.audio import is_stream_recording

logger = logging.getLogger(__name__)

# 洞察台注入块：存储路径与上限 / Insight Deck injection block: storage path and limits
INSIGHTS_TASKS_DIR = Path("data/tasks")
INSIGHTS_MAX_ITEMS = 5      # 最多注入最近 N 条洞察 / Max recent insights to inject
INSIGHTS_MAX_CHARS = 1200   # 整块字符上限 / Whole-block character cap

# 作业日志注入意图关键词
JOBLOG_INTENT_KEYWORDS = [
    "为什么", "为何", "怎么", "怎样", "如何", "原因", "失败", "出错", "报错",
    "错误", "卡", "没", "没有", "未", "过程", "流程", "发生", "做了", "操作",
    "运行", "日志", "记录", "进度", "状态", "重新", "重跑", "绑定", "声纹",
    "匹配", "解析", "转写", "纪要", "暂停", "恢复", "停止", "导出",
]


def is_joblog_intent(message: str) -> bool:
    """判断用户问题是否涉及操作/运行/流程/故障，决定是否注入作业日志。"""
    return any(kw in message for kw in JOBLOG_INTENT_KEYWORDS)


def build_speaker_name_map(task_id: str | None) -> dict:
    """构建说话人 ID → 名称映射。"""
    name_map = {}
    task = tasks.get(task_id) if task_id else None
    if task:
        mapping = task.get("speaker_mapping", {})
        for sid, name in mapping.items():
            try:
                name_map[int(sid)] = name
            except (ValueError, TypeError):
                pass
    if not name_map:
        for s in speakers.load_speakers():
            name_map[s.speaker_id] = s.name
    return name_map


def task_final_summary(task: dict | None) -> str:
    """定稿纪要口径：用户编辑过（user_summary 存在，含空串）即以它为准，否则回退生成稿。

    与前端纪要 Tab（useGeneratingData）逐字节同口径：AI 读到的纪要基线必须等于用户看到的纪要，
    否则 propose_summary 的 diff 会把用户手改内容静默回退。
    """
    if not task:
        return ""
    us = task.get("user_summary")
    if us is not None:
        return str(us)
    return str(task.get("summary") or "")


def task_notes(task: dict | None) -> str:
    """随记口径：用户录音期间手写原文（user_notes），无内容返回空串。"""
    if not task:
        return ""
    return str(task.get("user_notes") or "").strip()


def build_insights_context_block(task_id: str | None) -> str | None:
    """构建「会议洞察台」注入块（供 chat qa/stream 两条路径共用）。
    Build the Insight Deck injection block (shared by both chat qa/stream paths).

    读取 data/tasks/<task_id>.insights.json，取最近 N 条有效洞察，整块截断；
    Reads persisted insight messages, injects the latest N valid ones under a char cap;
    diagram 源码不整段注入（token 不友好），仅附一行提示 / diagram source is only hinted, never injected whole.
    文件不存在 / 无有效消息时返回 None（三态：有洞察/无洞察/无文件） / None when absent or empty.
    """
    if not task_id:
        return None
    f = INSIGHTS_TASKS_DIR / f"{task_id}.insights.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    # 过滤 deferred：AI 引用口径与用户可见有效卡一致（一页纸系数卡位预算，超位旧卡不入上下文）
    msgs = [m for m in data.get("messages", [])
            if (m.get("title") or "").strip() and (m.get("body") or "").strip()
            and not m.get("deferred")]
    if not msgs:
        return None

    header = "## 会议洞察台（AI 会中/会后观察，供参考非事实源）"
    lines: list[str] = []
    budget = INSIGHTS_MAX_CHARS - len(header) - 1
    used = 0
    for m in msgs[-INSIGHTS_MAX_ITEMS:]:
        phase = "会后" if m.get("phase") == "post_meeting" else "会中"
        entry = f"- [{phase}] {m['title'].strip()}：{m['body'].strip()[:200]}"
        solution = (m.get("solution") or "").strip()
        if solution:
            entry += f"（建议：{solution[:100]}）"
        # 备查注释随卡注入：页面可略过，追问时 AI 能补回（三层信息写作契约）
        # note layer rides along: users may skip it on page, but AI can answer with it
        note = (m.get("note") or "").strip()
        if note:
            entry += f"（注：{note[:60]}）"
        if (m.get("diagram") or "").strip():
            entry += "（该洞察附决策流图）"
        if used + len(entry) + 1 > budget:
            break
        lines.append(entry)
        used += len(entry) + 1
    if not lines:
        return None
    return header + "\n" + "\n".join(lines)


def build_page_context(page: str) -> str | None:
    """根据前端页面构建差异化上下文。返回格式化文本或 None。"""
    if page == "start":
        return "## 当前页面\n用户在首页，可以开始新录音或上传音频文件。可用操作：开始录音、上传音频、查看历史会议。"

    if page == "recording":
        if is_stream_recording():
            return "## 当前页面\n用户正在录音中，可通过对话控制录音（暂停/停止）。"
        return None

    if page == "generating":
        return "## 当前页面\n用户正在查看已完成的会议纪要，可结合纪要、待办与洞察台结论回答问题。"

    if page == "speakers":
        spk_list = speakers.load_speakers()
        if not spk_list:
            return "## 当前页面\n用户在说话人管理页面，当前暂无注册的说话人。"
        lines = [f"- {s.name}" + (f"（{s.role}）" if s.role else "") for s in spk_list[:20]]
        text = "## 当前页面：说话人管理\n当前注册的说话人：\n" + "\n".join(lines)
        if len(spk_list) > 20:
            text += f"\n（共 {len(spk_list)} 人，仅展示前 20 位）"
        return text

    if page == "hotwords":
        hw_list = hotwords.load_hotwords()
        if not hw_list:
            return "## 当前页面\n用户在热词管理页面，当前暂无自定义热词。"
        lines = [f"- {w}" for w in hw_list[:30]]
        text = "## 当前页面：热词管理\n当前热词列表：\n" + "\n".join(lines)
        if len(hw_list) > 30:
            text += f"\n（共 {len(hw_list)} 个，仅展示前 30 个）"
        mappings = hotwords.load_hotword_mappings()
        if mappings:
            map_lines = [f"- {wrong} → {right}" for wrong, right in mappings[:15]]
            text += "\n\n热词映射（ASR 纠错）：\n" + "\n".join(map_lines)
        return text

    if page == "settings":
        from app.store import load_settings
        settings = load_settings()
        if not settings:
            return "## 当前页面\n用户在系统设置页面，当前使用默认配置。"
        safe_keys = ["language", "default_model", "record_device", "theme", "hotwords_enabled"]
        lines = [f"- {k}: {settings.get(k)}" for k in safe_keys if settings.get(k) is not None]
        if lines:
            return "## 当前页面：系统设置\n当前配置：\n" + "\n".join(lines)
        return "## 当前页面\n用户在系统设置页面。"

    if page == "projects":
        proj_list = projects.list_projects()
        if not proj_list:
            return "## 当前页面\n用户在项目管理页面，当前暂无项目。"
        lines = [f"- {p.get('name', '未命名')}（{p.get('file_count', 0)} 个文件）" for p in proj_list[:15]]
        text = "## 当前页面：项目管理\n当前项目列表：\n" + "\n".join(lines)
        if len(proj_list) > 15:
            text += f"\n（共 {len(proj_list)} 个项目）"
        return text

    if page == "library":
        total = len(tasks)
        if total == 0:
            return "## 当前页面\n用户在会议库页面，当前暂无会议记录。"
        status_counts: dict[str, int] = {}
        for t in tasks.values():
            s = t.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
        status_line = "、".join(f"{k}: {v}" for k, v in status_counts.items())
        recent = sorted(tasks.values(), key=lambda t: t.get("created_at", ""), reverse=True)[:5]
        recent_lines = [f"- {t.get('title') or t.get('audio_name') or '未命名'}（{t.get('status', '')}）" for t in recent]
        return f"## 当前页面：会议库\n共 {total} 个会议（{status_line}）。\n最近会议：\n" + "\n".join(recent_lines)

    return None


# ============================================================
# 注入内容提取
# ============================================================


def _is_duplicate_todo(content: str, existing_todos: list[dict]) -> bool:
    """检查提取的待办是否已存在（模糊匹配）。"""
    content_norm = content.strip()
    for t in existing_todos:
        existing = t.get("text", "").strip()
        if content_norm in existing or existing in content_norm:
            return True
        if len(content_norm) > 10 and len(existing) > 10:
            common = len(set(content_norm) & set(existing))
            union = len(set(content_norm) | set(existing))
            if union > 0 and common / union > 0.6:
                return True
    return False


def extract_injectable_items(reply: str, existing_todos: list[dict] | None = None) -> list[dict]:
    """从 AI 回复中提取可注入的结构化内容（待办/结论/决策）。"""
    items = []
    existing_todos = existing_todos or []

    # 提取待办（Markdown checkbox 格式）
    for m in re.finditer(r'^\s*-\s*\[\s*\]\s*(.+)$', reply, re.MULTILINE):
        content = m.group(1).strip()
        if content and len(content) > 4 and not _is_duplicate_todo(content, existing_todos):
            items.append({"type": "todo", "content": content})

    # 提取带关键词的列表项
    for m in re.finditer(r'^\s*[-•·]\s*(?:.*?(?:待办|需要|后续|跟进|完成|处理|负责|尽快)).*$', reply, re.MULTILINE):
        content = m.group(0).strip().lstrip('-•· ').strip()
        if content and len(content) > 4 and not any(i["content"] == content for i in items) and not _is_duplicate_todo(content, existing_todos):
            items.append({"type": "todo", "content": content})

    # 提取结论/决策段落
    for m in re.finditer(r'(?:^|\n)\s*(?:\d+[.、]|\*\*|•)\s*(?:.*?(?:结论|决定|确认|决策|方案|选择|确定).*)$', reply, re.MULTILINE):
        content = m.group(0).strip().lstrip('*').strip()
        if content and len(content) > 6 and not any(i["content"] == content for i in items):
            item_type = "decision" if any(kw in content for kw in ["决策", "方案", "选择"]) else "conclusion"
            items.append({"type": item_type, "content": content})

    return items
