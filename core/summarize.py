"""
core/summarize.py — 纪要提示词与解析

作者：Yongliang Wang
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
from core.speakers import normalize_speaker_name

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
        # BE-R3 读取侧归一：存量占位名收敛为空后仅以结构标签入 prompt（不进成品标题）
        speaker_name = normalize_speaker_name(item.get("speaker_name")) or f"Speaker {item.get('speaker_id', 0) + 1}"
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
3. **专有名词存疑必须标注**：人名/系统名/机构名等专名若疑似语音识别错误（同音异形、不通顺，或同一对象多种写法），原样保留并紧跟标注 `[待确认]`；禁止将多个疑似错词合并成"标准名"或臆造别名关系
4. **区分已定结论与待确认提案**：含"还需确认/回去定/发群敲定"等措辞的事项视为未敲定，前缀 `[待确认]`，不用"已决定/已取消/明确"等完成口吻
5. **用户笔记仅作辅助**：如提供「用户笔记」，仅用于消歧与补全背景；禁止把笔记原文抄入纪要，禁止替笔记添加"已被采纳/已形成结论"等未出现的定性

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
[列出会议明确达成的结论或决策，每条用序号标注，采用「标题：正文」两要素写法]
[如无明显结论，写"本次会议未形成明确结论"]

1. **决策短标题**：该条决策的完整内容
2. **决策短标题**：该条决策的完整内容

**格式硬约束（决策结构化抽取依赖）**：
- 每条结论必须是独立的有序列表项（以 "1. "、"2. " 起头），一条一行
- 每一项采 `**短标题**：正文` 两段式——短标题 6-20 字只概括要点，完整内容写在冒号后
- 未敲定条目（见核心原则「区分已定结论与待确认提案」）必须以 `[待确认]` 前缀开头（置于加粗标题之前）
- 本节不要求写执行人/负责人（负责人归「待办事项」章节），无执行人不构成格式错误
- 本节除有序列表项外禁止出现其他文本；无结论时仅输出一行"本次会议未形成明确结论"

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
- ❌ 不要标注"全体共识/一致同意/明确同意"等原文未出现的表态；仅当有明确同意话术时才归属决策人
- ❌ 慎用直接引号；非逐字原文一律用转述，不得把概括包装成发言人原话
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

    # 构造发言人说明（按 speaker_id 去重，避免同一人多次发言被重复统计）
    seen_sids: set[int] = set()
    speaker_names = []
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        if sid in seen_sids:
            continue
        seen_sids.add(sid)
        # BE-R3：姓名归一，未命名以中性措辞占位（O3 保守口径，序号仅结构定位不进正文）
        name = normalize_speaker_name(item.get("speaker_name"))
        speaker_names.append(f"Speaker {sid + 1} = {name or '（未命名）'}")
    unique_speaker_count = len(speaker_names)
    speaker_info = "，".join(speaker_names)

    # 构造用户消息
    user_content = "请根据以下会议对话内容生成会议纪要：\n\n"
    user_content += "---\n"
    user_content += f"**说话人数量**：{unique_speaker_count} 位\n"
    user_content += f"**发言人对应关系**：{speaker_info}\n"
    user_content += f"**对话总句数**：{total_sentences} 句\n"
    if meeting_time:
        user_content += f"**会议时间**：{meeting_time}\n"
        user_content += f"**音频采集时间**：{meeting_time}\n"
    if user_notes:
        user_content += f"**用户笔记**（录音期间记录，供参考）：\n{user_notes}\n"
    user_content += "---\n\n"
    user_content += "## 对话内容\n\n"

    # 按说话人合并所有发言（避免同一人多次轮转产生 61 条对话，误导 LLM 误判参会人数）
    merged_texts: dict[int, list[str]] = {}
    speaker_order: list[int] = []
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        text = item.get("text", "").strip()
        if not text:
            continue
        if sid not in merged_texts:
            merged_texts[sid] = []
            speaker_order.append(sid)
        merged_texts[sid].append(text)

    for sid in speaker_order:
        # BE-R3：取首个归一后非空真名；存量占位名视同未命名，降级为结构标签
        name = next(
            (n for n in (normalize_speaker_name(item.get("speaker_name"))
                         for item in dialogue if item.get("speaker_id") == sid) if n),
            f"Speaker {sid + 1}"
        )
        combined = "\n".join(merged_texts[sid])
        user_content += f"**{name}**：{combined}\n\n"

    # Agent 角色工作区：优先从 summary-template.md 加载，回退到硬编码常量 / Agent workspace: prefer role template, fallback to hardcoded
    from core.agent_workspace import get_role_summary_prompt
    summary_prompt = get_role_summary_prompt() or SYSTEM_PROMPT

    # R4（WP-A）：小模型保守档追加防幻觉约束；standard 档为空串，行为零变化
    from core.model_tier import get_tier_prompt_guard
    summary_prompt += get_tier_prompt_guard(model)

    messages = [
        {"role": "system", "content": summary_prompt},
        {"role": "user", "content": user_content},
    ]

    logger.info(f"生成纪要: {unique_speaker_count} 位说话人（{len(dialogue)} 条对话）, 会议时间={meeting_time}")
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
        speaker_name = normalize_speaker_name(item.get("speaker_name")) or f"Speaker {speaker_id + 1}"
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


# ============================================================
# 决策解析（REQ-DECISION-CENTER R1）
# ============================================================

import re as _re

# 「主要结论」章节标题（兼容 "## 二、主要结论"、"## 主要结论" 等写法）
_CONCLUSIONS_HEADING_RE = _re.compile(r"^\s{0,3}#{1,6}\s*\S{0,6}[、.．]?\s*主要结论")
# 「决策」章节标题（RF-1：内置模板 v1.1 定义 "## 三、决策" 为决策栏数据来源，须整行精确匹配）
_DECISION_SECTION_HEADING_RE = _re.compile(r"^\s{0,3}#{1,6}\s*\S{0,6}[、.．]?\s*决策\s*$")
# 任意 Markdown 标题行 / 水平分隔线（章节终止符）；兼容 "##三、" 无空格写法
_SECTION_STOP_RE = _re.compile(r"^\s{0,3}(#{1,6}|-{3,}\s*$|\*{3,}\s*$)")
# 无序列表前缀（裸行宽容采集时剥除，含 checkbox 写法）
_BULLET_PREFIX_RE = _re.compile(r"^[-*•]\s+(?:\[[ xX]\]\s*)?")
# 有序列表项（"1. "、"2、"、"3．"）
_ORDERED_ITEM_RE = _re.compile(r"^\s*(\d{1,2})[.、．]\s+(\S.*)$")
# [待确认] 前缀（兼容全角括号与加粗包裹）
_PENDING_PREFIX_RE = _re.compile(r"^\s*(?:\*\*)?[\[【]\s*待确认\s*[\]】](?:\*\*)?\s*[:：]?\s*")
# 阴性说明语句（"本次会议未形成明确结论/决策"等）→ 空结果但非解析失败
_NEGATIVE_CONCLUSION_RE = _re.compile(r"(未形成|没有|无|暂无)[^。\n]{0,8}(明确|有效)?[^。\n]{0,4}(结论|决议|决策)")
# 整行阴性说明（裸行采集时须跳过，避免把"未形成结论"本身收成决策）
_NEGATIVE_LINE_RE = _re.compile(
    r"^(?:本次|本轮)?(?:会议|纪要)?[\s，,]*"
    r"(?:未形成|没有形成|未能形成|无|暂无|没有)"
    r"[\s]*(?:明确|有效|任何)?[\s]*(?:结论|决议|决策)[。，.、\s]*$"
)
# 模板占位行（整行被方括号包裹）
_TEMPLATE_PLACEHOLDER_RE = _re.compile(r"^\[[^\[\]]*\]$")
# 「**标题**：正文」两要素条目（DC-R2-b D5）：仅在加粗短标题后接冒号时拆分，
# 其余写法（裸行/叙述句）title 留空，展示侧按「内容首句」降级——不丢条目为第一原则
_DECISION_TITLE_RE = _re.compile(r"^\*\*\s*([^*：:]{1,40}?)\s*\*\*\s*[：:]\s*(\S.*)$")


def split_decision_title(text: str) -> tuple[str, str]:
    """把条目文本拆为 (title, content)；不符合两要素写法时返回 ("", 原文)。

    Split a conclusion item into (title, content); tolerant — no match yields ("", text).
    """
    m = _DECISION_TITLE_RE.match((text or "").strip())
    if not m:
        return "", (text or "").strip()
    title = m.group(1).strip()
    content = m.group(2).strip()
    if not content or len(content) < 2:
        # 只有标题没有正文：整体归入内容，不丢弃该条
        return "", (text or "").strip()
    return title, content


def _extract_section(summary: str, heading_re: _re.Pattern) -> str | None:
    """按标题正则提取单个章节正文（不含标题行），章节缺失时返回 None。"""
    if not summary:
        return None
    lines = summary.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if heading_re.match(line):
            start = i + 1
            break
    if start < 0:
        return None
    body = []
    for line in lines[start:]:
        if _SECTION_STOP_RE.match(line):
            break
        body.append(line)
    return "\n".join(body)


def extract_conclusions_section(summary: str) -> str | None:
    """
    提取纪要 Markdown 中「主要结论」章节正文。

    Returns:
        章节正文（不含标题行），章节缺失时返回 None
    """
    return _extract_section(summary, _CONCLUSIONS_HEADING_RE)


def extract_decisions_section(summary: str) -> str | None:
    """
    提取纪要 Markdown 中「决策」章节正文（RF-1：内置模板的决策栏数据来源章节）。

    Returns:
        章节正文（不含标题行），章节缺失时返回 None
    """
    return _extract_section(summary, _DECISION_SECTION_HEADING_RE)


def parse_decisions_with_status(summary: str) -> tuple[list[dict], str | None]:
    """
    从纪要「主要结论」与「决策」两个章节解析决策流节点（RF-1），并返回降级状态。

    DC-UNIFY-01：解析结果不再是独立的 decision 对象，而是**决策流节点**（todos 形状），
    默认落在「待确认」态（项目方裁决：自动生成但不擅自定案，由用户逐条确认）。

    内置默认模板下两节分工不同（结论清单 vs 可跟进决策点），两节结果按出现顺序
    合并去重（同一表述保留「主要结论」中的先见项）。

    与 parse_todos_from_summary() 并列的确定性解析（不引入第二次 LLM 调用）。
    宽容解析：优先有序列表项（"1. " 起），兼容裸行条目（存量回填写法多样）。

    Returns:
        (nodes, degrade_status)
        degrade_status: None=正常（含"无结论/无决策"阴性说明）；
                        "missing_section"=两章节均缺失；
                        "no_items"=章节存在但既无条目也非阴性说明（格式异常）
    """
    import uuid
    from datetime import datetime

    sections = [s for s in (
        extract_conclusions_section(summary),
        extract_decisions_section(summary),
    ) if s is not None]
    if not sections:
        logger.info("决策解析降级：纪要缺少「主要结论」/「决策」章节")
        return [], "missing_section"

    nodes: list[dict] = []
    seen_texts: set[str] = set()
    now_iso = datetime.now().isoformat()

    for section in sections:
        for raw_line in section.splitlines():
            line = raw_line.strip()
            if not line or len(line) < 2:
                continue
            if _TEMPLATE_PLACEHOLDER_RE.match(line):
                continue
            if _NEGATIVE_LINE_RE.match(line):
                continue

            m = _ORDERED_ITEM_RE.match(raw_line)
            text = m.group(2).strip() if m else _BULLET_PREFIX_RE.sub("", line).strip()
            if not text or len(text) < 2:
                continue

            pending = False
            pm = _PENDING_PREFIX_RE.match(text)
            if pm:
                pending = True
                text = text[pm.end():].strip()
            if not text or len(text) < 2:
                continue

            # DC-R2-b D5：两要素条目拆标题/正文；拆完的 content 参与查重与空条目判定
            title, content = split_decision_title(text)
            if content:
                text = content

            # 去除 markdown 强调符号后跨章节查重与空文本判定（文本本体保留原格式）
            dedup_key = _re.sub(r"[*_`]", "", text).strip()
            if not dedup_key or dedup_key in seen_texts:
                continue
            seen_texts.add(dedup_key)

            # 决策流节点形状（todos）：status=to_decide 由项目方裁决「自动生成但待用户定案」（三态口径）
            nodes.append({
                "id": str(uuid.uuid4()),
                "title": title,
                "text": text,
                "assignee": "",
                "owner_id": None,
                "done": False,
                "status": "to_decide",
                "how": [text],
                "owner_type": "self",
                "pending_confirmation": pending,
                "source": "auto",
                "created_at": now_iso,
                "updated_at": now_iso,
            })

    if not nodes:
        if any(_NEGATIVE_CONCLUSION_RE.search(s) for s in sections):
            # 阴性说明（"本次会议未形成明确结论/决策"）→ 正常空结果，不算降级
            return [], None
        logger.info("决策解析降级：「主要结论」/「决策」章节未解析出任何条目")
        return [], "no_items"

    logger.info(f"从纪要中解析出 {len(nodes)} 条决策（待确认）")
    return nodes, None


def parse_decisions_from_summary(summary: str) -> list[dict]:
    """
    从纪要「主要结论」/「决策」章节解析决策流节点（简化签名，与 parse_todos_from_summary 并列）。

    Returns:
        [{"id", "title", "text", "assignee", "owner_id", "done", "status", "how",
          "owner_type", "pending_confirmation", "source", "created_at", "updated_at"}, ...]
    """
    nodes, _ = parse_decisions_with_status(summary)
    return nodes


def decision_text_key(text: object) -> str:
    """决策文本归一键：去首尾空白 + 内部连续空白压单（墓碑匹配用）。
    auto 决策 id 每次重解析会变，故以归一化文本为身份键。"""
    import re as _re_key
    if not isinstance(text, str):
        return ""
    return _re_key.sub(r"\s+", " ", text.strip())


def build_decision_tombstone(node: dict) -> dict | None:
    """为被删的 auto 决策流节点生成墓碑条目；非 auto 不建（merge 本就不覆盖，无复活风险）。"""
    from datetime import datetime as _dt
    if not isinstance(node, dict) or node.get("source") != "auto":
        return None
    key = decision_text_key(node.get("text"))
    if not key:
        return None
    return {"text_key": key, "deleted_at": _dt.now().isoformat()}


def merge_flow_after_regen(
    existing: list[dict],
    parsed: list[dict],
    deletions: list[dict] | None = None,
) -> list[dict]:
    """
    重新生成纪要后的决策流合并（DC-UNIFY-01）。

    规则：
      1. 只覆盖 `source == "auto"` 的节点，手动/注入/AI 对话产生的节点一律保留
      2. 按 task 级墓碑（`decision_deletions`）筛掉被用户删过的 auto 节点，防重生成复活（DC-R2-BE）
      3. 保留项与新增项按归一化文本去重（行动项与结论条目常同文本）

    Args:
        existing: 任务当前 todos
        parsed: 本次解析出的 auto 节点（checkbox 待办 + 结论决策）
        deletions: 墓碑列表 [{"text_key": str, "deleted_at": str}]；None/缺省保持既有行为

    Returns:
        合并后的新列表（保留项在前，新 auto 在后）
    """
    kept = [t for t in (existing or []) if isinstance(t, dict) and t.get("source") != "auto"]
    tombstones = {
        t.get("text_key") for t in (deletions or []) if isinstance(t, dict) and t.get("text_key")
    }
    seen = {decision_text_key(t.get("text")) for t in kept}
    seen.discard("")
    merged: list[dict] = list(kept)
    for node in (parsed or []):
        if not isinstance(node, dict):
            continue
        key = decision_text_key(node.get("text"))
        if not key or key in tombstones or key in seen:
            continue
        seen.add(key)
        merged.append(node)
    return merged


# 向后兼容别名：旧名 merge_decisions_after_regen 语义已扩大为整条决策流
def merge_decisions_after_regen(existing: list[dict], parsed: list[dict], deletions: list[dict] | None = None) -> list[dict]:
    """已废弃：请用 `merge_flow_after_regen`（参数与行为完全一致）。"""
    return merge_flow_after_regen(existing, parsed, deletions)
