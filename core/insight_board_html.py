"""
core/insight_board_html.py — 洞察板 HTML 产物清洗与内容底线

实现从 core/insight_board.py 拆出，保持行为零变化。

职责：
- sanitize_board_html：安全清洗（移除 iframe/object/embed/base/form、on* 事件、危险 URL）
- detect_recap_floor：启发式检测板是否退化为会议复述
- detect_text_wall：检测板是否退化为纯文字墙
"""

import logging
import re
from html import unescape as _html_unescape

logger = logging.getLogger(__name__)

BOARD_HTML_CAP = 300_000  # 单份板 HTML 字节上限，防失控膨胀 / Board HTML size cap

_DROP_TAGS = ("iframe", "object", "embed", "base", "form")


def _valid_task_id(task_id: str) -> bool:
    """task_id 为 uuid 形态；拒绝路径穿越字符 / Reject traversal chars in task_id."""
    return bool(task_id) and "/" not in task_id and "\\" not in task_id and ".." not in task_id


def sanitize_board_html(html: str) -> tuple[str, list[str]]:
    """安全清洗：返回 (净化后文本, 被改动的字节项列表)。"""
    removed: list[str] = []
    out = html or ""
    for tag in _DROP_TAGS:
        pattern = re.compile(
            rf"<{tag}\b[^>]*>.*?</{tag}>|<{tag}\b[^>]*/?>|</{tag}>",
            re.DOTALL | re.IGNORECASE,
        )
        out, n = pattern.subn("", out)
        if n:
            removed.append(f"<{tag}>×{n}")
    out, n_on = re.subn(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", out, flags=re.IGNORECASE)
    if n_on:
        removed.append(f"on*×{n_on}")
    out, n_url = re.subn(
        r"""((?:href|src)\s*=\s*["'])(?:\s*(?:javascript|data:text/html)[^"']*)(["'])""",
        r"\1#\2", out, flags=re.IGNORECASE,
    )
    if n_url:
        removed.append(f"dangerous-url×{n_url}")
    return out, removed


_RECAP_TITLE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"决策流|待确认决策|决策清单|决策列表|决议事项|决议清单"), "决策清单（决策中心已承载）"),
    (re.compile(r"议题归类|议题梳理|议题清单|议题列表|讨论议题"), "议题归类（纪要章节已承载）"),
    (re.compile(r"决策追踪|决策事项|决策清单|决策列表|待办追踪|待办事项|待办清单|待办列表|行动项清单|任务分工|人员分工|分工表"), "决策/分工清单（纪要决策已承载）"),
    (re.compile(r"会议全景|会议概览|会议纪要|纪要概览|会议总结|会议摘要"), "会议全景/纪要复述"),
    (re.compile(r"风险与未决|风险清单|风险梳理|未决事项"), "风险罗列式节（困境必须紧跟解法，不许只罗列）"),
)
_SOLUTION_TITLE_HINT = re.compile(r"解法|解决方案|对策|破局|锦囊|最优方案")
_TITLE_ATTR_RE = re.compile(r'data-ib-title=["\']([^"\']+)["\']', re.IGNORECASE)
_HEADING_RE = re.compile(r"<h[1-4]\b[^>]*>(.*?)</h[1-4]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_DC_CODE_RE = re.compile(r"DC[-－\s]*\d", re.IGNORECASE)
_TOPIC_CODE_RE = re.compile(r"议题\s*[0-9０-９]")
_SPEAKER_REF_RE = re.compile(r"说话人\s*[0-9０-９]|Speaker\s*[0-9]", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"依据[：:][^。；\n]{0,40}(?:说话人|Speaker)", re.IGNORECASE)
_DEADLINE_RE = re.compile(r"截止|deadline|\d{1,2}\s*月\s*\d{1,2}\s*日", re.IGNORECASE)
_RECAP_STAT_LABELS = ("待确认决策", "议题归类", "决策事项", "待办事项")

_SECTION_RE = re.compile(r"<section\b[^>]*\bdata-ib-id\b[^>]*>(.*?)</section>",
                         re.IGNORECASE | re.DOTALL)
_VISUAL_MARK_RE = re.compile(
    r"""<svg\b|<canvas\b|<img\b[^>]*\bsrc=\s*"?data:image|"""
    r"""class=["'][^"']*\b(?:ib-flow|ib-tree|ib-compare|ib-grid|ib-visual)\b""",
    re.IGNORECASE)

_MERMAID_PRE_RE = re.compile(r"<pre\b[^>]*>(.*?)</pre>", re.IGNORECASE | re.DOTALL)
_MERMAID_TYPES = ("flowchart", "graph", "sequenceDiagram", "stateDiagram-v2",
                  "stateDiagram", "mindmap", "timeline")
_MERMAID_DIRECTIVE_RE = re.compile(r"^%%\{.*\}%%\s*$")

_TEXT_WALL_GUIDANCE = (
    "洞察板是图不是文章：每个困境一节，先画后主文，纯文字段落/列表组成的节不允许落盘。"
    "请为每个节补一个主视觉，形态任选其一："
    "① 内联 <svg>（自己画图，资源一律 data URI 内联）；"
    "② mermaid 形态的 <pre>（首词必须是 flowchart/graph/sequenceDiagram/stateDiagram/mindmap/timeline 等图类型关键字）；"
    "③ <canvas>；④ src 为 data URI 的 <img>。"
    "mermaid 边标签是标配：A -->|标签| B；节点文字≤12 字、每图≤10 节点；"
    "源码内禁写 < > &（用「小于」「与」等中文替代，防止截断 HTML）、禁 click 语句。"
    "表格、div 条块不计主视觉。版式与样式由你自己负责，改完整份重新提交。"
)

_RECAP_GUIDANCE = (
    "洞察板的唯一任务是针对本场会议暴露的困境，给出会上没人想到的 AI 最优解法"
    "（你被授权调用外部行业知识、标准实践、成熟架构来构造解法），而不是整理会议内容。"
    "请重做整份 HTML：每节按「困境（一句话界定）→ 外部最优解法（具体可执行，附原理或出处）→ 落地步骤与取舍」组织；"
    "删除决策清单（含 DC 编号）、议题/章节归类、决策分工（谁做什么、截止日期）、参会人立场与「谁说了什么」、"
    "带说话人/时间戳的依据流水、会议概览与摘要复述——这些逐字稿、纪要页、决策中心已经承载；"
    "风险与未决项每条必须紧跟一个可落地解法，不许只罗列问题。"
    "若读取到的旧基线本身就是复述结构，直接推倒重做为解法结构，不受版式继承条款约束。"
)


def _mermaid_pre_ok(inner: str) -> bool:
    for raw in (inner or "").splitlines():
        line = raw.strip()
        if not line or _MERMAID_DIRECTIVE_RE.match(line):
            continue
        return line.split()[0] in _MERMAID_TYPES if line.split() else False
    return False


def _section_has_visual(body: str) -> bool:
    pres = _MERMAID_PRE_RE.findall(body)
    if pres:
        return any(_mermaid_pre_ok(inner) for inner in pres)
    return bool(_VISUAL_MARK_RE.search(body))


def _board_text_and_titles(board_html: str) -> tuple[str, list[str]]:
    titles = [m.strip() for m in _TITLE_ATTR_RE.findall(board_html) if m.strip()]
    for raw in _HEADING_RE.findall(board_html):
        t = _TAG_RE.sub("", raw).strip()
        if t:
            titles.append(t)
    text = _html_unescape(_TAG_RE.sub(" ", board_html))
    return re.sub(r"\s+", " ", text), titles


def detect_recap_floor(board_html: str) -> list[str]:
    text, titles = _board_text_and_titles(board_html or "")
    score = 0
    reasons: list[str] = []

    bad_titles: list[str] = []
    for t in titles:
        if _SOLUTION_TITLE_HINT.search(t):
            continue
        for pat, label in _RECAP_TITLE_PATTERNS:
            if pat.search(t):
                bad_titles.append(f"「{t[:20]}」={label}")
                break
    if bad_titles:
        score += 1
        reasons.append("复述型节标题 " + "；".join(dict.fromkeys(bad_titles))[:300])

    if len(_DC_CODE_RE.findall(text)) >= 2 or len(_TOPIC_CODE_RE.findall(text)) >= 2:
        score += 1
        reasons.append("DC/议题编号罗列（DC-1、议题1 等——决策与纪要已有各自编号体系）")

    stat_hits = [w for w in _RECAP_STAT_LABELS if w in text]
    if len(stat_hits) >= 2:
        score += 1
        reasons.append("决策/议题/决策统计徽标：" + "、".join(stat_hits))

    speaker_hits = len(_SPEAKER_REF_RE.findall(text))
    evidence_hits = len(_EVIDENCE_RE.findall(text))
    if speaker_hits + evidence_hits >= 4:
        score += 1
        reasons.append(
            f"密集记录发言人（说话人/Speaker 引用 {speaker_hits} 处、依据句 {evidence_hits} 处）"
            "——板不应记录谁说了什么")

    if speaker_hits >= 3 and _DEADLINE_RE.search(text):
        score += 1
        reasons.append("按人派活+截止日期的决策分工表")

    return reasons if score >= 2 else []


def detect_text_wall(board_html: str) -> tuple[int, int]:
    sections = _SECTION_RE.findall(board_html or "")
    if not sections:
        return 0, 0
    visual = sum(1 for body in sections if _section_has_visual(body))
    return len(sections), visual
