"""
core/decision_extract.py — 决策类信息的独立提取（专属提示词 + 独立 LLM 调用）

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-25

背景（专项优化：决策与行动项语义分层）：
  历史上「决策」由纪要生成的同一次 LLM 调用顺带产出——纪要 system prompt 里
  「主要结论」章节身兼"给人阅读的结论正文"与"决策流数据来源"两职，导致：
    1. 决策与待办/行动项共用一套提示词，边界模糊，纯执行动作（梳理文档、联调、
       排期等系统对接的必然步骤）被误判为决策；
    2. 决策缺失发起方、共识依据、生效范围等关键上下文。

  本模块把「决策提取」从纪要生成中彻底解耦：
    - 独立的 DECISION_EXTRACT_SYSTEM_PROMPT：只面向"什么是决策"，明确决策与
      行动项的语义边界，要求保留发起方/共识依据/生效范围/出处；
    - 独立的 LLM 调用与 JSON 结构化输出，不与纪要 Markdown、待办 checkbox 混杂；
    - 输出经确定性解析与字段归一后，由 `decisions_to_nodes` 适配为统一决策流节点
      （`core.decision_flow.make_decision_node` 形状），kind="decision"。

  数据流唯一来源：实时/转写管线（core/pipeline_runner.py）的决策仅由本模块供给；
  纪要正文保留「主要结论」供人阅读，但不再解析入决策流；行动项仍由纪要 checkbox
  解析（kind="action"）。纯纪要文本导入（无对话稿）退化为文本解析，不走本模块。

  设计约束：与既有决策解析同口径——JSON 解析/归一为确定性逻辑，LLM 仅负责
  "从对话里认出决策"，结构化校验、去重、节点构造均在本模块内闭环。
"""

import json
import logging
import re

from core.decision_flow import make_decision_node
from core.speakers import normalize_speaker_name

logger = logging.getLogger(__name__)

# 决策节点类型标识（与行动项 kind="action" 相对），供前端分层展示与过滤
DECISION_KIND = "decision"


# ============================================================
# 专属提示词：仅面向决策识别，与纪要生成/待办提取完全解耦
# ============================================================
DECISION_EXTRACT_SYSTEM_PROMPT = """你是会议「决策提取」专员。你的唯一职责是从会议对话中识别并抽取**决策类信息**，输出结构化决策清单。你不生成纪要、不提取待办、不复述讨论过程。

## 什么是「决策」（满足任一即为决策）

决策是会议中**达成共识、确定方向、明确规则或方案**的结论。
1. **定方向/定调**：确立目标、路线、定位、打法（如"分三步走""先做 A 再做 B""走本地化路线"）。
2. **定规则/标准**：确立规则、原则、红线、边界（如"高敏数据必须本地化""报销统一走 X 流程"）。
3. **定方案/选型**：选定方案、技术、供应商、路径或优先级（如"采用百望""用方案甲""先上 X 模块"）。
4. **定案共识**：出现明确拍板/统一口径的表述（"就这么定""采用 X""统一按 Y""以 X 为准"）。
5. **定性/结论**：对事件、问题、根因、现状形成明确的定性或结论性判断（如"事件定性为高危数据泄露""入侵源头是内部运维账户""根因是权限管控缺失"）。
6. **承接既有定案**：会议复述或确认此前已经定下的方案、规则、边界（"之前定的""领导拍的""按原方案""还是走 X"），且无人当场推翻，同样算决策（标 `confirmed`）；不得以"这是历史信息、不是本次结论"为由丢弃。

复盘会、研讨会、发布会、分享会同样可能产生决策——凡是"定下了方向/规则/方案/结论"的都要抽取，不要因会议偏讨论或偏执行就判定无决策。

## 什么**不是**决策（排除）

- **行动项/待办**：仅安排后续具体事务——"谁、在什么时间、做什么具体动作"，如"整理接口文档""联调""排期""写方案""发群里""约下次会议""对齐字段"。这类只有执行动作、没有方向性结论。
- **系统对接/流程的必然步骤**：为达成目标绕不开的执行环节（文档梳理、字段对齐、测试、上线排期），即便明确要做，也属行动项。
- **仅提出问题、暴露分歧而没有取舍的讨论**：只列问题、担忧或备选方案，未形成倾向或结论，才算排除；一旦有人给出明确方向且无人反对，按 `pending` 抽取。
- **明确被否决或搁置的提案**：仅当观点被明确否定、或"回去再定/以后再说"且无方向性共识时才排除。注意：某人提出方向性观点（即使带"我认为/我建议"）后，若获他人附和、无人反对，或对话围绕其形成结论，即构成决策，应抽取（视共识程度标 `confirmed` 或 `pending`），不得仅因措辞带"我认为"就丢弃。
- **纯现状陈述/信息同步/讨论过程**：介绍背景、汇报进度、中间表态与分歧，无结论性取舍。

> 判别口诀：决策回答"**定下了什么方向/规则/方案**"，行动项回答"**接下来谁去做什么**"。

## 混合句的处理（关键）

一句话若同时含"方向性结论 + 执行动作"，抽取其**方向性结论**作为决策，执行动作不写入 `text`。
例："我们决定统一走百望平台，接下来由张三梳理接口文档" → 决策 `text`="发票平台统一选型百望"；"梳理接口文档"是行动项，不进决策清单。

## 每条决策必须保留的上下文

- `title`：决策短标题，6-20 字，只概括结论要点。
- `text`：决策完整内容，一两句完整陈述**结论本身**（定了什么方向/规则/方案），不含后续执行步骤。
- `initiator`：发起方/主要推动人，用对话中的说话人姓名；无法判断则留空字符串。
- `rationale`：共识依据/理由——为什么这么定，依据哪段讨论、数据或约束；对话未体现则留空字符串。
- `scope`：生效范围/适用边界（适用对象、系统、团队、业务范围等）；未体现则留空字符串。
- `evidence_speaker`：出处对应的说话人姓名（与对话标注一致）。
- `evidence_time`：出处时间戳，格式 `[MM:SS]`，取该决策被明确敲定的那句发言时刻；**对话未标注时间时必须留空字符串，严禁推测或编造**。
- `status`：`confirmed`（对话中明确达成共识/拍板）或 `pending`（方向基本明确但仍带"待确认/再敲定"措辞）。

## 输出格式（硬约束）

只输出一个 JSON 数组，不要任何解释、前言或 Markdown 围栏。每个元素是一条决策，字段如上。确实无决策时才输出空数组 `[]`。

示例：
[
  {
    "title": "高敏财务数据强制本地化",
    "text": "涉及薪酬、供应商价格、涉税等财务核心信息的 AI 应用，一律本地化部署，禁用公有云。",
    "initiator": "张三",
    "rationale": "财务数据敏感，公有云存在合规与泄密风险。",
    "scope": "所有含财务核心信息的 AI 应用",
    "evidence_speaker": "张三",
    "evidence_time": "[07:34]",
    "status": "confirmed"
  }
]

## 铁律

- 忠于原文：只抽取对话中真实达成的决策，不编造、不推测、不补全未出现的结论。
- **应抽尽抽、不得遗漏**：凡符合判定标准的决策都要抽取；同一议题的多轮往复归并为一条终态结论。拿不准但确属方向性结论时，保留并标 `status=pending`，不要直接丢弃。
- **整场为空是例外，不是常态**：会议没有新拍板，不等于没有决策——既有定案的复述确认、对现状的定性判断同样要抽。只有通篇确实找不出一条方向/规则/方案/定性/历史定案时，才输出 `[]`。
- **不误判**：纯执行动作、必然步骤、事务安排不得当作决策输出，行动项不得混入决策清单。"""


# ============================================================
# 生效提示词解析：角色工作区 decision-prompt.md 优先，内置常量为兜底
# ============================================================

def get_decision_prompt(role_name: str | None = None) -> tuple[str, str]:
    """返回生效的决策提取提示词及其来源。

    提示词以角色工作区文件为准（可在「角色管理」中查看/编辑），
    文件缺失时回退到内置常量，保证老角色与纯代码部署可用。

    Returns:
        (prompt_text, source)，source ∈ {"role", "builtin"}
    """
    try:
        from core.agent_workspace import get_role_decision_prompt

        body = get_role_decision_prompt(role_name)
        if body:
            return body, "role"
    except Exception as e:  # noqa: BLE001 - 提示词加载失败不得阻断提取
        logger.warning(f"决策提取：读取角色提示词失败，回退内置：{e}")
    return DECISION_EXTRACT_SYSTEM_PROMPT, "builtin"


# ============================================================
# 对话文本构造（带说话人 + 时间戳，供模型定位出处）
# ============================================================

def _fmt_ts(ms: object) -> str:
    """毫秒 → [MM:SS]（≥1 小时为 [H:MM:SS]）；非法值返回空串。"""
    try:
        total = int(float(ms) / 1000)
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m:02d}:{s:02d}]"


def build_decision_dialogue(dialogue: list[dict]) -> tuple[str, int]:
    """把对话稿渲染为带「说话人 + [时间戳]」的逐句文本。

    优先逐句（sentences 含 begin_time），按时间升序，便于模型给出精确出处；
    无 sentences 时退化为按说话人条目的整段文本（无时间戳）。

    Returns:
        (对话文本, 有效句数)
    """
    # speaker_id → 展示名（真名归一，缺省占位）
    name_map: dict[object, str] = {}
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        if sid not in name_map:
            name = normalize_speaker_name(item.get("speaker_name"))
            name_map[sid] = name or f"Speaker {int(sid) + 1 if isinstance(sid, int) else sid}"

    # 收集逐句（带时间）
    timed: list[tuple[float, object, str]] = []
    has_time = False
    for item in dialogue:
        sid = item.get("speaker_id", 0)
        for s in (item.get("sentences") or []):
            text = (s.get("text") or "").strip()
            if not text:
                continue
            begin = s.get("begin_time", s.get("begin"))
            try:
                key = float(begin)
                has_time = True
            except (TypeError, ValueError):
                key = float("inf")
            timed.append((key, sid, text))

    lines: list[str] = []
    if timed:
        timed.sort(key=lambda x: x[0])
        for key, sid, text in timed:
            ts = _fmt_ts(key) if has_time and key != float("inf") else ""
            prefix = f"{name_map.get(sid, 'Speaker')}"
            lines.append(f"{prefix} {ts}：{text}" if ts else f"{prefix}：{text}")
        return "\n".join(lines), len(timed)

    # 退化：无 sentences，按说话人整段
    count = 0
    for item in dialogue:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        sid = item.get("speaker_id", 0)
        lines.append(f"{name_map.get(sid, 'Speaker')}：{text}")
        count += 1
    return "\n\n".join(lines), count


# ============================================================
# JSON 解析与字段归一（确定性，容错）
# ============================================================

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_json_array(raw: str) -> str | None:
    """从模型输出中抠出 JSON 数组文本：先剥围栏，再取首个 '[' 到末个 ']'。"""
    if not raw:
        return None
    text = raw.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    return text[start:end + 1]


def _parse_json_array(raw: str) -> list | None:
    """容错解析 JSON 数组：直解失败时去尾逗号重试；仍失败返回 None。"""
    arr_text = _extract_json_array(raw)
    if arr_text is None:
        return None
    try:
        data = json.loads(arr_text)
    except json.JSONDecodeError:
        # 去尾逗号（如 {"a":1}, ] / [1,2,]）
        cleaned = re.sub(r",\s*([}\]])", r"\1", arr_text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, list) else None


def _s(value: object) -> str:
    """归一为去空白字符串；非字符串标量转字符串，None/容器归空。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def normalize_decision_item(item: dict) -> dict | None:
    """归一单条原始决策为内部结构；缺 title/text 视为无效返回 None。

    输出键：title/text/initiator/rationale/scope/evidence_speaker/evidence_time/status。
    status 仅 confirmed|pending，缺省 pending（拿不准不入定案）。
    """
    if not isinstance(item, dict):
        return None
    title = _s(item.get("title"))
    text = _s(item.get("text")) or title
    if not text:
        return None
    if not title:
        # 无标题时取正文首句截断
        title = re.split(r"[。．.！!；;\n]", text, maxsplit=1)[0].strip()[:20]
    status = _s(item.get("status")).lower()
    status = "confirmed" if status == "confirmed" else "pending"
    return {
        "title": title,
        "text": text,
        "initiator": _s(item.get("initiator")),
        "rationale": _s(item.get("rationale")),
        "scope": _s(item.get("scope")),
        "evidence_speaker": _s(item.get("evidence_speaker")),
        "evidence_time": _s(item.get("evidence_time")),
        "status": status,
    }


def parse_decisions_json(raw: str) -> list[dict]:
    """解析模型输出为归一决策清单；解析失败/无有效项返回空列表。"""
    data = _parse_json_array(raw)
    if not data:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for raw_item in data:
        norm = normalize_decision_item(raw_item)
        if not norm:
            continue
        key = re.sub(r"\s+", "", norm["text"]).lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(norm)
    return items


# ============================================================
# 对外主入口：独立 LLM 调用提取决策
# ============================================================

_MINUTES_DIGEST_RE = re.compile(
    r"^[ \t]{0,3}#{1,6}[ \t]*(?:[一二三四五六七八九十0-9]+[、.．][ \t]*)?"
    r"(?:主要结论|议题归类)[ \t]*$", re.MULTILINE
)


def minutes_digest_for_decisions(summary: str, max_chars: int = 2500) -> str:
    """截取纪要「主要结论」「议题归类」两节，作为决策空结果复核的定位线索。

    刻意排除「决策事项」节（内容为行动项），避免把待办当作决策回捞。
    """
    text = summary or ""
    if not text:
        return ""
    picks: list[str] = []
    capturing = False
    cap_level = 0
    for line in text.splitlines():
        hm = re.match(r"^[ \t]{0,3}(#{1,6})[ \t]", line)
        if hm:
            level = len(hm.group(1))
            if _MINUTES_DIGEST_RE.match(line):
                capturing, cap_level = True, level
                picks.append(line.strip("# ").strip())
            elif capturing and level > cap_level:
                # 节内子标题（如「### 议题1：…」）保留
                picks.append(line.strip("# ").strip())
            else:
                capturing = False
            continue
        if capturing:
            picks.append(line)
    return "\n".join(picks).strip()[:max_chars].strip()


def _dialogue_has_time(dialogue: list[dict]) -> bool:
    """对话稿是否带可用时间戳（begin_time）。"""
    for item in dialogue or []:
        for s in item.get("sentences") or []:
            try:
                float(s.get("begin_time", s.get("begin")))
                return True
            except (TypeError, ValueError):
                continue
    return False


def extract_decisions(
    dialogue: list[dict],
    model: str = "qwen-plus",
    meeting_time: str | None = None,
    timeout: float | None = None,
    role_name: str | None = None,
    minutes_hint: str = "",
) -> list[dict]:
    """从对话稿独立提取决策清单（专属提示词，独立于纪要/待办）。

    Args:
        dialogue: 对话稿 [{"speaker_id", "text", "sentences", "speaker_name"?}, ...]
        model: LLM 模型名（与纪要同档）
        meeting_time: 会议时间（可选，仅作上下文）
        timeout: LLM 调用独立超时预算
        role_name: 角色名（决定读取哪个角色的 decision-prompt.md）
        minutes_hint: 同场纪要的「主要结论/议题归类」摘要，仅作空结果复核的定位线索

    Returns:
        归一决策清单（见 normalize_decision_item）。无决策/解析失败返回 []。

    Raises:
        仅当 LLM 调用本身抛错时向上抛（由调用方决定降级策略）；
        JSON 解析失败不抛错，记告警并返回 []。
    """
    if not dialogue:
        return []

    dialogue_text, n_sentences = build_decision_dialogue(dialogue)
    if n_sentences < 1 or not dialogue_text.strip():
        logger.info("决策提取：对话内容为空，返回空清单")
        return []

    system_prompt, prompt_source = get_decision_prompt(role_name)
    logger.info(f"决策提取：生效提示词来源={prompt_source}（角色={role_name or 'default'}）")

    user_content = "请从以下会议对话中提取全部决策类信息（只输出 JSON 数组）。\n\n"
    if meeting_time:
        user_content += f"会议时间：{meeting_time}\n"
    user_content += f"对话共 {n_sentences} 句。\n\n---\n{dialogue_text}\n---"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    from core.llm import chat_completion
    # 低温度：决策提取是判定式任务，低温提升一致性与可复现性
    raw = chat_completion(messages, model=model, temperature=0.2, timeout=timeout)

    items = parse_decisions_json(raw or "")

    # 召回兜底：首轮为空且对话有实质内容时复核一次——低质量/口语化转写中，
    # 方向性结论、定性判断易被首轮漏判（实测：复盘会"纯服务端架构"、评估会
    # "方案适用性有限"等）。复核仍要求只输出决策，不放宽行动项边界，保精确率。
    if not items and n_sentences >= 8:
        if minutes_hint and minutes_hint.strip():
            # 有纪要候选时用"逐条核对"而非"重新发现"：口语化长对话中，开放式复核
            # 极易被判无决策（实测两次均返回 []），给定候选后模型才愿意落到具体条目。
            retry_messages = messages + [
                {"role": "assistant", "content": raw or "[]"},
                {"role": "user", "content": (
                    "首轮未识别到决策。以下候选项摘自同场会议纪要：\n"
                    f"{minutes_hint.strip()}\n\n"
                    "请逐条核对对话原文：能由对话支撑的方向/规则/方案/结论，按决策格式输出"
                    "（共识不充分标 pending，不要因为“待确认”就丢弃）；对话中找不到依据的丢弃；"
                    "纯事务安排、功能讲解不算决策。候选全部无依据时才输出 []。"
                )},
            ]
        else:
            retry_messages = messages + [
                {"role": "assistant", "content": raw or "[]"},
                {"role": "user", "content": (
                    "请复核是否遗漏了决策：对话中若有「确定了方向/规则/方案/结论/定性」的内容"
                    "（包括某人明确提出并获认可的观点、对事件或问题的定性结论），请补充输出这些"
                    "决策的 JSON 数组（字段同前）。纯事务安排、产品介绍、功能讲解、讨论过程不算决策；"
                    "确实无任何结论时才输出 []。"
                )},
            ]
        raw_retry = chat_completion(retry_messages, model=model, temperature=0.2, timeout=timeout)
        items = parse_decisions_json(raw_retry or "")
        if items:
            logger.info(f"决策提取：复核捞回 {len(items)} 条决策")

    if not items:
        logger.warning(f"决策提取：未解析出有效决策（原始返回 {len(raw or '')} 字符）")
    else:
        # 对话无时间戳时，模型仍会照模板推测 [MM:SS]，确定性清空（实测编出 12:21/1:23:10）
        if not _dialogue_has_time(dialogue):
            for it in items:
                if it.get("evidence_time"):
                    it["evidence_time"] = ""
            logger.info("决策提取：对话无时间戳，已清空推测的出处时间")
        logger.info(f"决策提取：解析出 {len(items)} 条决策（{n_sentences} 句对话）")
    return items


# ============================================================
# 适配为统一决策流节点（kind="decision"）
# ============================================================

def _norm_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def is_duplicate_of_existing(content: str, existing_decisions: list[dict] | None) -> bool:
    """待注入决策是否已存在于会议决策流（互含或 Jaccard 相似度 > 60%）。"""
    content_norm = _norm_text(content)
    if not content_norm:
        return True
    for t in existing_decisions or []:
        existing = _norm_text(t.get("text", ""))
        if not existing:
            continue
        if content_norm in existing or existing in content_norm:
            return True
        if len(content_norm) > 10 and len(existing) > 10:
            common = len(set(content_norm) & set(existing))
            union = len(set(content_norm) | set(existing))
            if union > 0 and common / union > 0.6:
                return True
    return False


# 回复过短时几乎不可能含方向性结论，跳过 LLM 调用（成本与延迟保护）
REPLY_MIN_CHARS = 40


def extract_decisions_from_reply(
    reply: str,
    existing_decisions: list[dict] | None = None,
    model: str = "qwen-plus",
    timeout: float | None = None,
    role_name: str | None = None,
) -> list[dict]:
    """从会议助手的回复文本中提取决策（复用决策专属提示词，独立 LLM 判定）。

    与纪要实现共用 `get_decision_prompt` 的口径：判定什么是决策、什么是行动项
    完全一致，杜绝"关键词命中即决策"的宽口径误报。

    Returns:
        归一决策清单（见 normalize_decision_item），并剔除已存在于决策流的重复项。
        无决策/解析失败返回 []。
    """
    text = (reply or "").strip()
    if len(text) < REPLY_MIN_CHARS:
        return []
    # 回复是 AI 生成文本，截断上限防超长输入抬高判定成本
    text = text[:12000]

    system_prompt, prompt_source = get_decision_prompt(role_name)
    logger.info(f"回复决策提取：生效提示词来源={prompt_source}（角色={role_name or 'default'}）")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            "以下是会议助手刚刚给出的回复，请从中提取决策类信息（只输出 JSON 数组）。\n"
            "执行动作/待办不算决策；回复未体现的内容不得编造。\n\n"
            f"---\n{text}\n---"
        )},
    ]

    from core.llm import chat_completion
    raw = chat_completion(messages, model=model, temperature=0.2, timeout=timeout)

    items = parse_decisions_json(raw or "")
    return [it for it in items if not is_duplicate_of_existing(it["text"], existing_decisions)]


def decision_extra(item: dict) -> dict:
    """决策上下文 → 决策流节点 extra（发起方/共识依据/生效范围/出处/待确认标记）。

    自动提取与对话注入共用同一口径，避免两处字段名漂移。
    """
    extra: dict = {"kind": DECISION_KIND}
    if item.get("initiator"):
        extra["initiator"] = item["initiator"]
    if item.get("rationale"):
        extra["rationale"] = item["rationale"]
    if item.get("scope"):
        extra["scope"] = item["scope"]
    # 出处：说话人 + 时间戳（剥方括号入 refs.time，与既有 evidence.refs 口径一致）
    spk = item.get("evidence_speaker") or ""
    ts = (item.get("evidence_time") or "").strip().strip("[]")
    if spk or ts:
        ref: dict = {}
        if spk:
            ref["speaker"] = spk
        if ts:
            ref["time"] = ts
        note_text = " ".join(x for x in [spk, f"[{ts}]" if ts else ""] if x).strip()
        extra["evidence"] = {"text": note_text, "refs": [ref] if ref else []}
    if item.get("status") == "pending":
        extra["pending_confirmation"] = True
    return extra


def decisions_to_nodes(items: list[dict]) -> list[dict]:
    """把归一决策清单适配为决策流节点（make_decision_node 形状）。

    - source="auto"（自动提取，默认待确认态，与既有口径一致）；
    - kind="decision"；发起方/共识依据/生效范围入 extra；
    - 出处（说话人+时间戳）归一为 evidence 结构，与既有 evidence 口径兼容；
    - status=pending 的决策打 pending_confirmation 标记。
    """
    nodes: list[dict] = []
    for it in items:
        # 发起方作为执行人快照（决策的"负责人"语义弱于行动项，仅作归属参考）
        node = make_decision_node(
            it["text"],
            title=it.get("title") or "",
            assignee=it.get("initiator") or "",
            source="auto",
            extra=decision_extra(it),
        )
        nodes.append(node)
    return nodes


def decisions_to_injectable_items(items: list[dict]) -> list[dict]:
    """把归一决策清单适配为前端注入项（字段与 decision-prompt 输出对齐）。"""
    return [
        {
            "type": DECISION_KIND,
            "content": it["text"],
            "title": it.get("title") or "",
            "initiator": it.get("initiator") or "",
            "rationale": it.get("rationale") or "",
            "scope": it.get("scope") or "",
            "evidence_speaker": it.get("evidence_speaker") or "",
            "evidence_time": it.get("evidence_time") or "",
            "status": it.get("status") or "pending",
        }
        for it in items
    ]
