"""
core/chapters.py — 章节生成模块 / Chapter generation module

职责 / Responsibilities:
  1. 分析对话稿，按议题变化自然分段 / Analyze dialogue, segment by topic changes
  2. 为每个章节生成标题、摘要、关键要点 / Generate title, summary, key points for each chapter
  3. 返回结构化章列表，供前端内联展示 / Return structured chapter list for inline frontend display

数据流 / Data flow:
  dialogue → LLM 分析 / analysis → chapters[]
  每个 chapter / Each chapter: {id, title, start_ms, end_ms, summary, key_points}

设计意图 / Design intent:
  章节是会议进程的阶段性标记，嵌入转写流中帮助用户快速定位议题变化 / Chapters mark meeting progress stages, embedded in transcript to help users quickly locate topic changes.
  不同于纪要的「议题归类」，章节关注时间线和进程感 / Unlike summary's "topic grouping", chapters focus on timeline and sense of progress.
"""

import json
import logging
import re

from core.speakers import normalize_speaker_name

from .llm import chat_completion

logger = logging.getLogger(__name__)

CHAPTERS_SYSTEM_PROMPT = """你是一位专业的会议分析助手。你的任务是将会议对话按议题变化划分为若干章节。

## 核心原则
1. **忠于原文**：只基于对话内容划分章节，不编造议题
2. **自然分段**：根据话题转换划分，不要强行平均分配
3. **章节数量**：一般 2-8 个章节，取决于会议时长和内容丰富度
4. **时间连续**：章节必须按时间顺序排列，不能交叉
5. **内容不足时**：如果对话少于 5 句有效内容，返回 1 个章节即可

## 划分标准
- 话题明显转变时开始新章节（如从"项目进度"转到"预算讨论"）
- 同一话题内的不同细节不拆分
- 开场寒暄/设备测试等可归入第一个章节或单独成章
- 每个章节至少包含 2 句有效对话

## 输出格式
严格输出 JSON 数组，不要输出任何其他内容：

```json
[
  {
    "id": 1,
    "title": "章节标题（不超过15字）",
    "start_sentence_idx": 0,
    "end_sentence_idx": 5,
    "summary": "一句话摘要（不超过50字）",
    "key_points": ["要点1", "要点2"]
  }
]
```

字段说明：
- id: 从 1 开始的章节编号
- title: 简洁的章节标题
- start_sentence_idx: 该章节第一句在所有句子列表中的索引（从 0 开始）
- end_sentence_idx: 该章节最后一句的索引（含）
- summary: 一句话概括该章节讨论内容
- key_points: 2-4 个关键要点，每个不超过 30 字

## 禁止行为
- 不要编造对话中未提及的内容
- 不要输出 JSON 以外的任何文本
- 不要遗漏任何句子（所有句子都必须归属某个章节）"""


def generate_chapters(
    dialogue: list[dict],
    model: str = "qwen-plus",
) -> list[dict]:
    """
    根据对话稿生成章节列表 / Generate chapter list from dialogue.

    Args:
        dialogue: 对话稿列表，每项含 speaker_id, text, sentences 等 / Dialogue list, each item contains speaker_id, text, sentences, etc.
        model: LLM 模型名 / LLM model name

    Returns:
        章节列表，每项含 / Chapter list, each item contains:
        {
            "id": int,
            "title": str,
            "start_ms": int,      # 开始时间（毫秒） / Start time (ms)
            "end_ms": int,         # 结束时间（毫秒） / End time (ms)
            "summary": str,
            "key_points": list[str],
        }
    """
    if not dialogue:
        return []

    # 收集所有句子并排序，建立索引映射 / Collect all sentences, sort, and build index mapping
    all_sentences = []
    for speaker in dialogue:
        sid = speaker.get("speaker_id", 0)
        # BE-R3 读取侧归一：存量占位名收敛为空后以结构标签入 prompt（不进章节成品）
        speaker_name = normalize_speaker_name(speaker.get("speaker_name")) or f"Speaker {sid + 1}"
        for sent in (speaker.get("sentences") or []):
            all_sentences.append({
                "speaker_id": sid,
                "speaker_name": speaker_name,
                "text": sent.get("text", ""),
                "begin_time": sent.get("begin_time", 0),
                "end_time": sent.get("end_time", 0),
            })
    all_sentences.sort(key=lambda s: s["begin_time"])

    if len(all_sentences) < 3:
        # 内容过少，返回单章节 / Too few content, return single chapter
        if all_sentences:
            return [{
                "id": 1,
                "title": "会议记录",
                "start_ms": all_sentences[0]["begin_time"],
                "end_ms": all_sentences[-1]["end_time"],
                "summary": all_sentences[0]["text"][:50],
                "key_points": [s["text"][:30] for s in all_sentences[:3]],
            }]
        return []

    # 构造对话文本（带索引标注） / Build dialogue text (with index annotations)
    dialogue_text = ""
    for idx, sent in enumerate(all_sentences):
        dialogue_text += f"[{idx}] {sent['speaker_name']}：{sent['text']}\n"
        if len(dialogue_text) > 6000:
            dialogue_text += f"...（共 {len(all_sentences)} 句，已截断）\n"
            break

    user_content = (
        f"以下会议对话共 {len(all_sentences)} 句，"
        f"时间跨度 {all_sentences[0]['begin_time']}ms - {all_sentences[-1]['end_time']}ms。\n"
        f"请按议题变化划分章节：\n\n{dialogue_text}"
    )

    messages = [
        {"role": "system", "content": CHAPTERS_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        logger.info(f"生成章节: {len(all_sentences)} 句对话")
        raw = chat_completion(messages, model=model, temperature=0.3, max_tokens=2048)
        chapters = _parse_chapters_response(raw, all_sentences)
        logger.info(f"章节生成完成: {len(chapters)} 个章节")
        return chapters
    except Exception as e:
        logger.warning(f"章节生成失败: {e}")
        return _fallback_single_chapter(all_sentences)


def _parse_chapters_response(raw: str, all_sentences: list[dict]) -> list[dict]:
    """解析 LLM 返回的 JSON 章节数据，映射时间戳 / Parse JSON chapter data from LLM, map timestamps."""
    # 提取 JSON 部分（兼容 markdown 代码块包裹） / Extract JSON part (compatible with markdown code block wrapping)
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = raw.strip()

    # 尝试找到数组 / Try to find array
    arr_match = re.search(r'\[.*\]', json_str, re.DOTALL)
    if arr_match:
        json_str = arr_match.group(0)

    parsed = json.loads(json_str)
    if not isinstance(parsed, list):
        raise ValueError("LLM 返回的不是数组")

    total = len(all_sentences)
    chapters = []

    for item in parsed:
        if not isinstance(item, dict):
            continue

        start_idx = max(0, min(int(item.get("start_sentence_idx", 0)), total - 1))
        end_idx = max(start_idx, min(int(item.get("end_sentence_idx", total - 1)), total - 1))

        start_ms = all_sentences[start_idx]["begin_time"]
        end_ms = all_sentences[end_idx].get("end_time", all_sentences[end_idx]["begin_time"] + 1000)

        key_points = item.get("key_points", [])
        if isinstance(key_points, list):
            key_points = [str(p)[:50] for p in key_points[:5]]
        else:
            key_points = []

        chapters.append({
            "id": int(item.get("id", len(chapters) + 1)),
            "title": str(item.get("title", "未命名章节"))[:20],
            "start_ms": start_ms,
            "end_ms": end_ms,
            "summary": str(item.get("summary", ""))[:100],
            "key_points": key_points,
        })

    # 重新编号 / Renumber
    for i, ch in enumerate(chapters):
        ch["id"] = i + 1

    if not chapters:
        return _fallback_single_chapter(all_sentences)

    return chapters


def _fallback_single_chapter(all_sentences: list[dict]) -> list[dict]:
    """兜底：返回单章节 / Fallback: return single chapter."""
    return [{
        "id": 1,
        "title": "会议记录",
        "start_ms": all_sentences[0]["begin_time"],
        "end_ms": all_sentences[-1].get("end_time", all_sentences[-1]["begin_time"] + 1000),
        "summary": all_sentences[0]["text"][:50] if all_sentences else "",
        "key_points": [s["text"][:30] for s in all_sentences[:3]],
    }]
