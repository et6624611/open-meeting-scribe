"""
core/summarize.py — 纪要提示词与解析

作者：王永亮
创建：2026-09-03
版本：1.0.0

职责：
  1. 构造纪要生成提示词
  2. 调用 LLM 生成纪要
  3. 解析输出为结构化格式（结论/待办/议题）
  4. 生成会议标题

输出格式：Markdown
"""

import logging
from core.i18n import _
from .llm import chat_completion

logger = logging.getLogger(__name__)


# 标题生成系统提示词
TITLE_SYSTEM_PROMPT = """你是一位专业的会议标题生成助手。根据会议对话内容，生成一个简洁、概括性的会议标题。

## 要求
1. 标题应简洁明了，一般不超过 20 个字
2. 标题应概括会议的核心主题或议题
3. 使用正式书面语
4. 如果对话内容过短或无法提取有效主题，返回"会议记录"

## 示例
- "产品需求评审会议"
- "Q3 预算方案讨论"
- "技术方案选型交流"
- "项目进度同步会"

只返回标题文本，不要添加任何其他内容或格式。"""


def generate_title(
    dialogue: list[dict],
    model: str = "qwen-plus",
) -> str:
    """
    根据对话稿生成会议标题。

    Args:
        dialogue: 对话稿列表
        model: LLM 模型名

    Returns:
        会议标题字符串
    """
    if not dialogue:
        return "会议记录"

    # 构造对话文本（截取前 2000 字符以控制 token 消耗）
    dialogue_text = ""
    for item in dialogue:
        speaker_name = item.get("speaker_name", f"Speaker {item.get('speaker_id', 0) + 1}")
        text = item.get("text", "").strip()
        if text:
            dialogue_text += f"{speaker_name}：{text}\n"
            if len(dialogue_text) > 2000:
                dialogue_text += "..."
                break

    if not dialogue_text.strip():
        return "会议记录"

    messages = [
        {"role": "system", "content": TITLE_SYSTEM_PROMPT},
        {"role": "user", "content": f"请为以下会议对话生成一个简洁的标题：\n\n{dialogue_text}"},
    ]

    try:
        logger.info("生成会议标题...")
        title = chat_completion(messages, model=model)
        title = title.strip().strip('"\'')
        # 限制长度
        if len(title) > 30:
            title = title[:30]
        logger.info(f"标题生成完成: {title}")
        return title
    except Exception as e:
        logger.warning(f"标题生成失败: {e}")
        return "会议记录"


# 纪要生成系统提示词
SYSTEM_PROMPT = """你是一位专业的会议纪要助手。你的任务是根据提供的会议对话内容，生成准确、结构化的会议纪要。

## 核心原则

1. **忠于原文**：只基于提供的对话内容生成纪要，绝不编造、推测或补充对话中未出现的信息
2. **内容不足时如实说明**：如果对话内容过短、不清晰或无法提取有效信息，直接说明"对话内容不足，无法生成完整纪要"，不要硬凑
3. **识别错误时标注**：如发现明显的语音识别错误（如乱码、不通顺的词语），在纪要中标注"[待确认]"
4. **用户笔记为辅助参考**：如提供「用户笔记」，仅作为理解会议背景的辅助参考，纪要内容仍必须以对话原文为依据，不得将笔记中未在对话中出现的内容写入纪要

## 输出结构

严格按以下结构输出，使用 Markdown 格式：

```
# 会议纪要

**会议时间**：[直接复制下方「会议时间」字段的原始值；若为"未提供"则从对话推断或留空]
**参会人员**：[说话人数量，如能区分则列出]
**纪要生成**：AI 自动生成

---

## 一、会议概要
[2-3句话概括会议主题和核心讨论内容。如内容不足，写"本次对话内容较短，主要涉及..."]

## 二、主要结论
[列出会议明确达成的结论或决策，每条用序号标注]
[如无明显结论，写"本次会议未形成明确结论"]

1. ...
2. ...

## 三、待办事项
[列出明确提到的后续任务]
[格式：- [ ] **负责人**：任务描述（截止日期）]
[如无待办，写"无明确待办事项"]

- [ ] ...

## 四、议题归类
[将讨论内容按主题归类，每个议题 1-2 句话总结]
[如议题单一，可合并到"会议概要"]

### 议题1：[标题]
[总结]

### 议题2：[标题]
[总结]

---
*本纪要由 AI 根据会议录音自动生成，仅供参考。如有疑义，请以原始录音为准。*
```

## 禁止行为

- ❌ 不要编造对话中未提及的结论、数据或决策
- ❌ 不要推测说话人的意图或补充未说出的内容
- ❌ 不要使用"可能""或许""推测"等词语来填充内容
- ❌ 不要在纪要中添加虚构的截止日期或负责人
- ❌ 对话少于 3 句有效内容时，直接输出"对话内容过短，无法生成有效纪要"

## 语言风格

- 简洁专业，去除口语化表达（"嗯""啊""那个"等）
- 保留关键数据、人名、项目名
- 区分不同发言人的观点，标注"说话人X认为..."
- 使用正式书面语，但不晦涩"""


def generate_summary(
    dialogue: list[dict],
    model: str = "qwen-plus",
    meeting_time: str | None = None,
    user_notes: str | None = None,
) -> str:
    """
    根据对话稿生成会议纪要。

    Args:
        dialogue: 对话稿列表
            [{"speaker_id": 0, "text": "...", "sentences": [...], "speaker_name": "张三"}, ...]
        model: LLM 模型名
        meeting_time: 会议时间（来自音频采集时间），如 "2026-09-03 14:30"
        user_notes: 用户录音期间输入的笔记，作为纪要生成的额外上下文

    Returns:
        Markdown 格式的纪要
    """
    if not dialogue:
        return "（对话稿为空，无法生成纪要）"

    # 统计有效句子数（dialogue 按说话人分组，需展开 sentences 计数）
    total_sentences = 0
    for d in dialogue:
        sents = d.get("sentences") or []
        total_sentences += len([s for s in sents if s.get("text", "").strip()])
    # 兜底：若无 sentences 字段，按说话人条目数估算
    if total_sentences == 0:
        total_sentences = len([d for d in dialogue if d.get("text", "").strip()])
    if total_sentences < 3:
        return _("Dialogue too short (only {count} sentences) to generate meaningful minutes. Please record a longer meeting audio.").format(count=total_sentences)

    # 构造发言人说明
    speaker_names = []
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        name = item.get("speaker_name", f"Speaker {sid + 1}")
        speaker_names.append(f"Speaker {sid + 1} = {name}")
    speaker_info = "，".join(speaker_names)

    # 构造用户消息
    user_content = "请根据以下会议对话内容生成会议纪要：\n\n"
    user_content += f"---\n"
    user_content += f"**说话人数量**：{len(dialogue)} 位\n"
    user_content += f"**发言人对应关系**：{speaker_info}\n"
    user_content += f"**对话总句数**：{total_sentences} 句\n"
    if meeting_time:
        user_content += f"**会议时间**：{meeting_time}\n"
        user_content += f"**音频采集时间**：{meeting_time}\n"
    if user_notes:
        user_content += f"**用户笔记**（录音期间记录，供参考）：\n{user_notes}\n"
    user_content += f"---\n\n"
    user_content += "## 对话内容\n\n"

    for item in dialogue:
        speaker_id = item.get("speaker_id", 0)
        speaker_name = item.get("speaker_name", f"Speaker {speaker_id + 1}")
        text = item.get("text", "").strip()
        if text:
            user_content += f"**{speaker_name}**：{text}\n\n"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    logger.info(f"生成纪要: {len(dialogue)} 位说话人, 会议时间={meeting_time}")
    summary = chat_completion(messages, model=model)

    # 后处理兜底：如果 LLM 仍输出"未提供"，用实际值替换
    if meeting_time and summary:
        summary = summary.replace("**会议时间**：未提供", f"**会议时间**：{meeting_time}")
        summary = summary.replace("**会议时间**:未提供", f"**会议时间**：{meeting_time}")
        summary = summary.replace("**会议时间**：未提供", f"**会议时间**：{meeting_time}")

    logger.info(f"纪要生成完成: {len(summary)} 字符")

    return summary


def format_dialogue_for_display(dialogue: list[dict]) -> str:
    """
    将对话稿格式化为可读文本（用于展示或调试）。

    Returns:
        格式化的对话文本
    """
    lines = []
    for item in dialogue:
        speaker_id = item.get("speaker_id", 0)
        speaker_name = item.get("speaker_name", f"Speaker {speaker_id + 1}")
        text = item.get("text", "").strip()
        if text:
            lines.append(f"【{speaker_name}】{text}")
    return "\n\n".join(lines)


def save_summary(
    summary: str,
    output_path: str,
    dialogue: list[dict] | None = None,
) -> str:
    """
    保存纪要到文件。

    Args:
        summary: 纪要内容（Markdown）
        output_path: 输出文件路径
        dialogue: 可选，同时保存对话稿

    Returns:
        保存的文件路径
    """
    from pathlib import Path

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = summary

    # 如提供对话稿，附加在纪要后面
    if dialogue:
        dialogue_text = format_dialogue_for_display(dialogue)
        content += "\n\n---\n\n## 附：原始对话稿\n\n"
        content += dialogue_text

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"纪要已保存: {output_path}")
    return str(output_path)


def parse_todos_from_summary(summary: str) -> list[dict]:
    """
    从纪要 Markdown 中解析待办事项。

    匹配格式：
      - [ ] **负责人**：任务描述（截止日期）
      - [ ] **负责人**：任务描述
      - [ ] 任务描述

    Returns:
        [{"id": str, "text": str, "assignee": str, "done": False, "source": "auto"}, ...]
    """
    import re
    import uuid

    todos = []
    seen_texts = set()

    checkbox_pattern = re.compile(
        r'^\s*-\s*\[\s*\]\s*(.+)$',
        re.MULTILINE,
    )

    assignee_pattern = re.compile(
        r'^\*\*(.+?)\*\*\s*[：:]\s*(.+)$',
    )

    deadline_pattern = re.compile(
        r'[（(]([^）)]*?(?:日|月|号|前|底|初|中|\d{1,4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2})[^）)]*)[）)]\s*$',
    )

    for m in checkbox_pattern.finditer(summary):
        raw = m.group(1).strip()
        if not raw or len(raw) < 4:
            continue

        assignee = ""
        task_text = raw

        am = assignee_pattern.match(raw)
        if am:
            assignee = am.group(1).strip()
            task_text = am.group(2).strip()

        deadline = ""
        dm = deadline_pattern.search(task_text)
        if dm:
            deadline = dm.group(1).strip()
            task_text = task_text[:dm.start()].strip()

        if not task_text or len(task_text) < 2:
            continue

        dedup_key = f"{assignee}:{task_text}"
        if dedup_key in seen_texts:
            continue
        seen_texts.add(dedup_key)

        item = {
            "id": str(uuid.uuid4())[:8],
            "text": task_text,
            "assignee": assignee,
            "done": False,
            "source": "auto",
        }
        if deadline:
            item["deadline"] = deadline

        todos.append(item)

    logger.info(f"从纪要中解析出 {len(todos)} 条待办")
    return todos
