"""
core/import_parser.py — 导入内容解析与智能识别 / Import content parsing and smart detection

职责 / Responsibilities:
  1. 智能识别文本内容类型（原文 transcript / 纪要 summary）
  2. 解析多种格式（Markdown、SRT、VTT、独立行说话人、同行说话人...）为内部 dialogue 结构
  3. 从纪要 Markdown 中提取结构化信息

架构 / Architecture (v2.0 — Parser Registry with Confidence):
  每种原文格式 = 一个独立 Parser 子类，自带 confidence(text, filename) -> float
  registry 遍历所有 parser 打分 → 选最高置信度 → 调用其 parse()
  新格式只需新增一个 Parser 子类，不动主流程

未来 AI 兜底 / Future AI fallback:
  当所有 parser confidence < 阈值（比如 0.6）时，返回 low_confidence 信号
  调用方可以选择：让用户手动确认 → 或调 AI 做结构化提取

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-18
版本 / Version: 2.0.0
"""

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# 内容类型枚举 / Content type enum
# ============================================================

CONTENT_TYPE_TRANSCRIPT = "transcript"
CONTENT_TYPE_SUMMARY = "summary"
CONTENT_TYPE_UNKNOWN = "unknown"


# ============================================================
# 文件格式分类 / File format classification
# ============================================================

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".webm"}
DOCUMENT_EXTENSIONS = {".md", ".txt", ".srt", ".vtt"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def classify_file_type(filename: str) -> str:
    """根据文件扩展名分类 / Classify file by extension."""
    ext = Path(filename).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "unsupported"


# ============================================================
# 重复检测 / Duplicate detection
# ============================================================

def find_duplicate_task(filename: str, file_size: int, tasks: dict) -> dict | None:
    """在已有任务中查找可能的重复文件 / Find possible duplicate file in existing tasks."""
    for task in tasks.values():
        if task.get("source") in ("record", "upload", "import_transcript", "import_summary"):
            if (task.get("audio_name") == filename
                    and task.get("audio_size") == file_size):
                return task
    return None


# ============================================================
# 纪要特征模式（保持原有 detect 兼容）/ Summary feature patterns
# ============================================================

_SUMMARY_PATTERNS = [
    # 中文纪要标题 / Chinese summary headings
    re.compile(r"^#\s*会议纪要", re.MULTILINE),
    re.compile(r"^##\s*会议概要", re.MULTILINE),
    re.compile(r"^##\s*会议概要", re.MULTILINE),
    re.compile(r"^##\s*主要结论", re.MULTILINE),
    re.compile(r"^##\s*待办事项", re.MULTILINE),
    re.compile(r"^##\s*议题归类", re.MULTILINE),
    re.compile(r"^##\s*行动项", re.MULTILINE),
    re.compile(r"^##\s*决议", re.MULTILINE),
    # 英文纪要标题 / English summary headings
    re.compile(r"^##\s*Meeting Summary", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^##\s*Key Conclusions", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^##\s*Action Items", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^##\s*Decisions", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^##\s*Minutes", re.MULTILINE | re.IGNORECASE),
    # 参会人员格式 / Participants format
    re.compile(r"\*\*参会人员\*\*[：:]", re.MULTILINE),
    re.compile(r"\*\*Participants\*\*[：:]", re.MULTILINE | re.IGNORECASE),
    # 纪要声明 / Summary disclaimer
    re.compile(r"本纪要由\s*AI\s*.*自动生成", re.MULTILINE),
    re.compile(r"Auto[- ]generated.*minutes", re.MULTILINE | re.IGNORECASE),
]


def detect_content_type(text: str) -> str:
    """智能识别文本内容类型 / Smart detect text content type.

    优先用 registry 里的 transcript parser 置信度判定，
    再用 summary pattern 兜底。保持与 v1.x 相同的返回值。

    Returns: "transcript" | "summary" | "unknown"
    """
    if not text or len(text.strip()) < 10:
        return CONTENT_TYPE_UNKNOWN

    # 1. 纪要特征命中 / Summary pattern hits
    summary_hits = sum(1 for p in _SUMMARY_PATTERNS if p.search(text))

    # 2. registry 里最佳 transcript parser 的置信度 / Best transcript parser confidence
    best_transcript = _registry.best_match(text, "")
    transcript_conf = best_transcript.confidence(text, "") if best_transcript else 0.0

    # 纪要优先（结构化更高）
    if summary_hits >= 2:
        return CONTENT_TYPE_SUMMARY
    if summary_hits == 1 and transcript_conf < 0.6:
        return CONTENT_TYPE_SUMMARY

    # transcript parser 置信度足够
    if transcript_conf >= 0.6:
        return CONTENT_TYPE_TRANSCRIPT

    # 模糊区间：summary 有弱特征
    if summary_hits >= 1:
        return CONTENT_TYPE_SUMMARY

    return CONTENT_TYPE_UNKNOWN


# ============================================================
# Parser 基类 + Registry / Parser Base + Registry
# ============================================================

class BaseParser(ABC):
    """原文格式解析器基类 / Base class for transcript format parsers.

    每个子类实现 confidence() 和 parse()。
    confidence 独立于 parse 调用，可以先打分再决定用谁。
    """

    name: str = "base"   # 格式名，日志/调试用

    @abstractmethod
    def confidence(self, text: str, filename: str = "") -> float:
        """返回 0.0 - 1.0 的置信度 / Return confidence 0.0-1.0.

        Args:
            text: 文件全文
            filename: 文件名（扩展名线索）

        置信度计算建议：
          - 扩展名完美匹配 → 0.95
          - 模式命中数 ÷ 总行数 的比例分
          - 0.0 表示完全不可能是此格式
        """
        ...

    @abstractmethod
    def parse(self, text: str) -> list[dict]:
        """解析为 dialogue 结构 / Parse into dialogue structure.

        Returns:
            dialogue 列表（内部结构），解析不出返回 []
        """
        ...


class _TranscriptRegistry:
    """Parser 注册表 / Registry of transcript parsers."""

    def __init__(self):
        self._parsers: list[BaseParser] = []

    def register(self, parser: BaseParser):
        self._parsers.append(parser)

    def best_match(self, text: str, filename: str = "") -> BaseParser | None:
        """返回置信度最高的 parser，或 None / Return highest-confidence parser or None."""
        if not text or len(text.strip()) < 10:
            return None
        scored = [(p, p.confidence(text, filename)) for p in self._parsers]
        # 过滤掉 0 置信度的
        scored = [(p, c) for p, c in scored if c > 0]
        if not scored:
            return None
        scored.sort(key=lambda x: x[1], reverse=True)
        best, conf = scored[0]
        logger.debug(f"[parser-registry] best_match={best.name}, confidence={conf:.2f}")
        return best

    def score_all(self, text: str, filename: str = "") -> list[tuple[str, float]]:
        """返回所有 parser 的打分列表（调试用）/ Return all scores for debug."""
        return [(p.name, p.confidence(text, filename)) for p in self._parsers]


_registry = _TranscriptRegistry()


# ============================================================
# Parser 子类 / Parser Implementations
# ============================================================

class SrtParser(BaseParser):
    """SRT 字幕格式解析 / SRT subtitle format parser."""
    name = "srt"

    # SRT 时间轴 / SRT timestamp arrow
    _TS_RE = re.compile(
        r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}"
    )
    _BLOCK_RE = re.compile(
        r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}",
        re.MULTILINE,
    )

    def confidence(self, text: str, filename: str = "") -> float:
        ext = Path(filename).suffix.lower() if filename else ""
        if ext == ".srt":
            return 0.95
        hits = self._BLOCK_RE.findall(text)
        if len(hits) >= 3:
            return 0.90
        if len(hits) >= 1:
            return 0.40  # 至少有一个 SRT 时间轴
        return 0.0

    def parse(self, text: str) -> list[dict]:
        blocks = re.split(r"\n\s*\n", text.strip())
        entries = []
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue
            ts_match = re.match(
                r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
                r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
                lines[1].strip(),
            )
            if not ts_match:
                continue
            begin_ms = (int(ts_match.group(1)) * 3600
                        + int(ts_match.group(2)) * 60
                        + int(ts_match.group(3))) * 1000 + int(ts_match.group(4))
            end_ms = (int(ts_match.group(5)) * 3600
                      + int(ts_match.group(6)) * 60
                      + int(ts_match.group(7))) * 1000 + int(ts_match.group(8))
            content = "\n".join(lines[2:]).strip()
            if not content:
                continue
            entries.append({
                "text": content,
                "begin_time": begin_ms,
                "end_time": end_ms,
                "speaker_id": 0,
            })
        return _group_entries_into_dialogue(entries)


_registry.register(SrtParser())


class VttParser(BaseParser):
    """WebVTT 字幕格式解析 / WebVTT subtitle format parser."""
    name = "vtt"

    _WEBVTT_RE = re.compile(r"^WEBVTT", re.MULTILINE)

    def confidence(self, text: str, filename: str = "") -> float:
        ext = Path(filename).suffix.lower() if filename else ""
        if ext == ".vtt":
            return 0.95
        if self._WEBVTT_RE.search(text):
            return 0.85
        return 0.0

    def parse(self, text: str) -> list[dict]:
        text = re.sub(r"^WEBVTT[^\n]*\n", "", text.strip())
        text = re.sub(r"NOTE[^\n]*\n(?:.*\n)*?\n", "", text)
        return _registry._parsers[0].parse(text)  # 复用 SRT 解析


_registry.register(VttParser())


class StandaloneSpeakerParser(BaseParser):
    """独立行说话人格式：姓名(时间戳): 单独一行，内容在下一行 / Standalone speaker line parser.

    例 / Example:
        王永亮(00:00:28):
        石老师，咱们可以开始了。

        SJXRSCM_Stephen(00:00:31):
        好的，我来介绍一下...
    """
    name = "standalone_speaker"

    _SPEAKER_RE = re.compile(
        r"^(?P<name>[\u4e00-\u9fa5A-Za-z0-9_]+)"
        r"(?:\((?P<time>\d{1,2}:\d{2}(?::\d{2})?)\))?"
        r"\s*[：:]\s*$"
    )

    def confidence(self, text: str, filename: str = "") -> float:
        lines = text.split("\n")
        total = len(lines)
        if total == 0:
            return 0.0
        hits = sum(1 for line in lines if self._SPEAKER_RE.match(line.strip()))
        # 比例 ≥ 15% 且至少有 2 行
        ratio = hits / total
        if hits >= 2 and ratio >= 0.15:
            return min(0.90, 0.5 + ratio)
        if hits >= 1 and ratio >= 0.10:
            return 0.35
        return 0.0

    def parse(self, text: str) -> list[dict]:
        entries = []
        speaker_map: dict[str, int] = {}
        speaker_counter = 0
        active_sid: int | None = None
        active_begin_ms: int = 0
        content_buffer: list[str] = []

        def _flush_buffer():
            nonlocal content_buffer
            if content_buffer and active_sid is not None:
                content = "\n".join(content_buffer).strip()
                if content:
                    entries.append({
                        "text": content,
                        "speaker_id": active_sid,
                        "begin_time": active_begin_ms,
                        "end_time": 0,
                    })
            content_buffer = []

        for line in text.split("\n"):
            line = line.strip()
            m = self._SPEAKER_RE.match(line)
            if m:
                _flush_buffer()
                name = m.group("name").strip()
                sid = _get_or_assign_speaker(name, speaker_map, speaker_counter)
                if sid == speaker_counter:
                    speaker_counter += 1
                active_sid = sid
                active_begin_ms = _parse_time_str(m.group("time")) if m.group("time") else 0
                continue
            if not line:
                continue
            if active_sid is not None:
                content_buffer.append(line)
                continue
            # 非独立行模式下的纯文本行 → speaker 0
            if len(line) > 5:
                entries.append({"text": line, "speaker_id": 0, "begin_time": 0, "end_time": 0})

        _flush_buffer()
        return _group_entries_into_dialogue(entries, speaker_map)


_registry.register(StandaloneSpeakerParser())


class InlineMarkdownParser(BaseParser):
    """同行说话人格式：**张三**：内容 或 [00:12:30] 张三：内容 / Inline speaker formats."""
    name = "inline_markdown"

    # **说话人**：内容
    _BOLD_RE = re.compile(r"^\*\*(.+?)\*\*\s*[：:]\s*(.+)$", re.MULTILINE)
    # [HH:MM:SS] 说话人：内容
    _BRACKET_RE = re.compile(
        r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*(.+?)[：:]\s*(.+)$", re.MULTILINE
    )

    def confidence(self, text: str, filename: str = "") -> float:
        lines = text.split("\n")
        total = len(lines)
        if total == 0:
            return 0.0
        bold_hits = sum(1 for l in lines if self._BOLD_RE.match(l.strip()))
        bracket_hits = sum(1 for l in lines if self._BRACKET_RE.match(l.strip()))
        hits = bold_hits + bracket_hits
        ratio = hits / total
        if hits >= 3:
            return min(0.85, 0.5 + ratio)
        if hits >= 1:
            return 0.30
        return 0.0

    def parse(self, text: str) -> list[dict]:
        entries = []
        speaker_map: dict[str, int] = {}
        speaker_counter = 0

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            m = re.match(r"^\*\*(.+?)\*\*\s*[：:]\s*(.+)$", line)
            if m:
                name = m.group(1).strip()
                content = m.group(2).strip()
                sid = _get_or_assign_speaker(name, speaker_map, speaker_counter)
                if sid == speaker_counter:
                    speaker_counter += 1
                entries.append({"text": content, "speaker_id": sid,
                                "begin_time": 0, "end_time": 0})
                continue

            m = re.match(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*(.+?)[：:]\s*(.+)$", line)
            if m:
                name = m.group(2).strip()
                content = m.group(3).strip()
                sid = _get_or_assign_speaker(name, speaker_map, speaker_counter)
                if sid == speaker_counter:
                    speaker_counter += 1
                begin_ms = _parse_time_str(m.group(1))
                entries.append({"text": content, "speaker_id": sid,
                                "begin_time": begin_ms, "end_time": 0})
                continue

        return _group_entries_into_dialogue(entries, speaker_map)


_registry.register(InlineMarkdownParser())


class SpeakerNumberParser(BaseParser):
    """占位编号格式：说话人 N：内容 / Speaker N: content."""
    name = "speaker_number"

    _RE = re.compile(r"^(?:说话人|Speaker)\s*(\d+)\s*[：:]\s*(.+)$", re.IGNORECASE)

    def confidence(self, text: str, filename: str = "") -> float:
        lines = text.split("\n")
        total = len(lines)
        if total == 0:
            return 0.0
        hits = sum(1 for l in lines if self._RE.match(l.strip()))
        ratio = hits / total
        if hits >= 2 and ratio >= 0.10:
            return min(0.80, 0.4 + ratio)
        if hits >= 1:
            return 0.25
        return 0.0

    def parse(self, text: str) -> list[dict]:
        entries = []
        for line in text.split("\n"):
            line = line.strip()
            m = self._RE.match(line)
            if m:
                sid = max(0, int(m.group(1)) - 1)
                content = m.group(2).strip()
                entries.append({"text": content, "speaker_id": sid,
                                "begin_time": 0, "end_time": 0})
        return _group_entries_into_dialogue(entries)


_registry.register(SpeakerNumberParser())


# ============================================================
# 保留旧函数签名（向后兼容）/ Legacy function aliases
# ============================================================

def parse_srt(text: str) -> list[dict]:
    """解析 SRT 字幕格式 / Parse SRT subtitle format.

    向后兼容入口，实际委托给 SrtParser.
    """
    return SrtParser().parse(text)


def parse_vtt(text: str) -> list[dict]:
    """解析 WebVTT 字幕格式 / Parse WebVTT subtitle format.

    向后兼容入口，实际委托给 VttParser.
    """
    return VttParser().parse(text)


def parse_markdown_transcript(text: str) -> list[dict]:
    """解析 Markdown/独立行/同行说话人格式 / Parse Markdown-format transcript.

    委托给 registry 中置信度最高的 parser。
    保持 v1.x 行为：任何 parser 都能吃下的混合格式。
    """
    best = _registry.best_match(text, "")
    if best:
        return best.parse(text)
    return []


# ============================================================
# 共享基础设施 / Shared helpers
# ============================================================

def _get_or_assign_speaker(name: str, speaker_map: dict[str, int], next_id: int) -> int:
    if name not in speaker_map:
        speaker_map[name] = next_id
    return speaker_map[name]


def _parse_time_str(time_str: str) -> int:
    parts = re.split(r"[:：]", time_str)
    try:
        if len(parts) == 2:
            return (int(parts[0]) * 60 + int(parts[1])) * 1000
        elif len(parts) == 3:
            ms = 0
            sec_parts = parts[2].replace(",", ".").split(".")
            ms = int(sec_parts[1]) if len(sec_parts) > 1 else 0
            return (int(parts[0]) * 3600 + int(parts[1]) * 60
                    + int(sec_parts[0])) * 1000 + ms
    except (ValueError, IndexError):
        pass
    return 0


def _group_entries_into_dialogue(
    entries: list[dict],
    speaker_names: dict[str, int] | None = None,
) -> list[dict]:
    """将 entries 按 speaker_id 分组成 dialogue 结构 / Group entries into dialogue."""
    if not entries:
        return []

    speaker_groups: dict[int, list[dict]] = {}
    for entry in entries:
        sid = entry["speaker_id"]
        speaker_groups.setdefault(sid, []).append(entry)

    dialogue = []
    from core.speakers import normalize_speaker_name
    id_to_name: dict[int, str] = {}
    if speaker_names:
        for name, sid in speaker_names.items():
            real = normalize_speaker_name(name)
            if real:
                id_to_name[sid] = real

    for sid in sorted(speaker_groups.keys()):
        group = speaker_groups[sid]
        sentences = []
        texts = []
        for i, entry in enumerate(group):
            sentences.append({
                "begin_time": entry.get("begin_time", 0),
                "end_time": entry.get("end_time", 0),
                "text": entry["text"],
                "sentence_id": i,
                "speaker_id": sid,
            })
            texts.append(entry["text"])

        dialogue.append({
            "speaker_id": sid,
            "speaker_name": id_to_name.get(sid, ""),
            "text": "\n".join(texts),
            "sentences": sentences,
        })

    return dialogue


# ============================================================
# 统一解析入口 / Unified parsing entry point
# ============================================================

def parse_document_content(
    content: str,
    filename: str = "",
) -> tuple[str, list[dict] | None, str | None]:
    """统一解析文档内容 / Unified document content parsing.

    v2.0 行为变化：registry 遍历所有 parser 打分，
    选最高置信度的来解析；所有 parser 都不给分才走 summary 兜底。

    Args:
        content: 文件文本内容
        filename: 文件名（扩展名用作 parser confidence 线索）

    Returns:
        (content_type, dialogue, summary_text)
    """
    if not content or len(content.strip()) < 10:
        return CONTENT_TYPE_UNKNOWN, None, None

    # 1. 纪要特征命中 → 优先判 summary
    summary_hits = sum(1 for p in _SUMMARY_PATTERNS if p.search(content))

    # 2. registry 里最佳 parser
    best = _registry.best_match(content, filename)
    best_conf = best.confidence(content, filename) if best else 0.0

    logger.info(
        f"[import-parser] filename={filename}, summary_hits={summary_hits}, "
        f"best_parser={best.name if best else 'none'}, conf={best_conf:.2f}"
    )

    # 纪要强特征 + parser 置信度不高 → 判 summary
    if summary_hits >= 2 and best_conf < 0.6:
        return CONTENT_TYPE_SUMMARY, None, content

    # parser 置信度足够 → 走 transcript
    # 阈值 0.35 覆盖：SRT 时间轴命中 1 个 (0.40) / VttParser 特征命中 /
    # StandaloneSpeakerParser 低比例命中 / InlineMarkdownParser 1 处命中
    if best and best_conf >= 0.35:
        dialogue = best.parse(content)
        if dialogue and len(dialogue) >= 1:
            return CONTENT_TYPE_TRANSCRIPT, dialogue, None

    # 纪要弱特征 + parser 没把握 → 判 summary
    if summary_hits >= 1:
        return CONTENT_TYPE_SUMMARY, None, content

    # 兜底：内容太短
    if len(content.strip()) < 50:
        return CONTENT_TYPE_UNKNOWN, None, None

    # 启发式：尝试让所有 parser 都试一遍，取能产出 dialogue 的
    if not best:
        for parser in _registry._parsers:
            dialogue = parser.parse(content)
            if dialogue and len(dialogue) >= 2:
                return CONTENT_TYPE_TRANSCRIPT, dialogue, None

    # 最终兜底 → summary
    return CONTENT_TYPE_SUMMARY, None, content


# ============================================================
# 标题推断 / Title inference
# ============================================================

def infer_title_from_content(content: str, max_length: int = 30) -> str:
    """从内容推断会议标题 / Infer meeting title from content."""
    m = re.match(r"^#\s+(.+)$", content.strip(), re.MULTILINE)
    if m:
        title = m.group(1).strip()
        if title and title != "会议纪要":
            return title[:max_length]
    return ""
