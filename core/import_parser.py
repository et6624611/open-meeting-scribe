"""
core/import_parser.py — 导入内容解析与智能识别 / Import content parsing and smart detection

职责 / Responsibilities:
  1. 智能识别文本内容类型（原文 transcript / 纪要 summary）
  2. 解析多种格式（Markdown、SRT、VTT、纯文本）为内部 dialogue 结构
  3. 从纪要 Markdown 中提取结构化信息

支持的内容来源 / Supported content sources:
  - 其他会议软件的转写稿导出（飞书、腾讯会议、Zoom 等）
  - 手动整理的会议纪要
  - 粘贴的文字内容

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-18
版本 / Version: 1.0.0
"""

import logging
import re
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
    """根据文件扩展名分类 / Classify file by extension.

    Returns:
        "audio" | "document" | "image" | "unsupported"
    """
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
    """在已有任务中查找可能的重复文件 / Find possible duplicate file in existing tasks.

    使用文件名 + 文件大小组合判定 / Use filename + file size combination for detection.

    Returns:
        匹配到的任务 dict，或 None / Matched task dict, or None
    """
    for task in tasks.values():
        if task.get("source") in ("record", "upload", "import_transcript", "import_summary"):
            if (task.get("audio_name") == filename
                    and task.get("audio_size") == file_size):
                return task
    return None


# ============================================================
# 内容类型智能识别 / Smart content type detection
# ============================================================

# 纪要特征模式 / Summary feature patterns
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

# 原文/转写稿特征模式 / Transcript feature patterns
_TRANSCRIPT_PATTERNS = [
    # SRT 时间轴格式 / SRT timestamp format
    re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}"),
    # VTT 时间轴格式 / VTT timestamp format
    re.compile(r"WEBVTT"),
    # 带时间戳的说话人标注 / Speaker labels with timestamps
    re.compile(r"^\[?\d{1,2}:\d{2}[:\]]\s*\*?\*?\w+", re.MULTILINE),
    # 飞书格式：说话人 + 时间范围 / Feishu format: speaker + time range
    re.compile(r"^\w+.*\d{1,2}:\d{2}[:\-]\d{1,2}:\d{2}", re.MULTILINE),
    # 通用说话人标注 / Generic speaker labels
    re.compile(r"^(?:说话人|Speaker)\s*\d+\s*[：:]", re.MULTILINE),
    # Markdown 加粗说话人 / Bold speaker names
    re.compile(r"^\*\*\w+\*\*\s*[：:]", re.MULTILINE),
    # Zoom 格式 / Zoom format
    re.compile(r"^\w+\s+\w+\s+\d{1,2}:\d{2}\s*(?:AM|PM)", re.MULTILINE | re.IGNORECASE),
]


def detect_content_type(text: str) -> str:
    """智能识别文本内容类型 / Smart detect text content type.

    通过正则匹配文本中的特征模式来判断内容是「原文/转写稿」还是「会议纪要」。
    优先匹配纪要特征（结构化程度更高），再匹配原文特征。

    Args:
        text: 文件内容或粘贴的文字

    Returns:
        "transcript" | "summary" | "unknown"
    """
    if not text or len(text.strip()) < 10:
        return CONTENT_TYPE_UNKNOWN

    # 统计纪要特征命中数 / Count summary pattern hits
    summary_hits = sum(1 for p in _SUMMARY_PATTERNS if p.search(text))
    # 统计原文特征命中数 / Count transcript pattern hits
    transcript_hits = sum(1 for p in _TRANSCRIPT_PATTERNS if p.search(text))

    logger.info(f"内容类型检测: 纪要特征={summary_hits}, 原文特征={transcript_hits}")

    # 纪要特征更明显 / Summary features dominate
    if summary_hits >= 2:
        return CONTENT_TYPE_SUMMARY
    # 原文特征明显 / Transcript features dominate
    if transcript_hits >= 2:
        return CONTENT_TYPE_TRANSCRIPT
    # 只有一个纪要强特征（如 "# 会议纪要"）也算 / Single strong summary feature counts
    if summary_hits == 1 and transcript_hits == 0:
        return CONTENT_TYPE_SUMMARY
    # 只有一个原文强特征 / Single strong transcript feature
    if transcript_hits == 1 and summary_hits == 0:
        return CONTENT_TYPE_TRANSCRIPT

    return CONTENT_TYPE_UNKNOWN


# ============================================================
# 转写稿解析器 / Transcript parsers
# ============================================================

def parse_srt(text: str) -> list[dict]:
    """解析 SRT 字幕格式为 dialogue 结构 / Parse SRT subtitle format into dialogue structure.

    SRT 格式:
        1
        00:00:01,000 --> 00:00:05,000
        说话内容

    Returns:
        dialogue 列表 / dialogue list
    """
    # 按双换行分割字幕块 / Split by double newline into subtitle blocks
    blocks = re.split(r"\n\s*\n", text.strip())
    entries = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # 第一行是序号 / First line is index
        # 第二行是时间轴 / Second line is timestamp
        ts_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1].strip()
        )
        if not ts_match:
            continue

        begin_ms = (int(ts_match.group(1)) * 3600 + int(ts_match.group(2)) * 60 + int(ts_match.group(3))) * 1000 + int(ts_match.group(4))
        end_ms = (int(ts_match.group(5)) * 3600 + int(ts_match.group(6)) * 60 + int(ts_match.group(7))) * 1000 + int(ts_match.group(8))

        # 剩余行是文本 / Remaining lines are text
        content = "\n".join(lines[2:]).strip()
        if not content:
            continue

        entries.append({
            "text": content,
            "begin_time": begin_ms,
            "end_time": end_ms,
            "speaker_id": 0,  # SRT 通常无说话人信息 / SRT usually has no speaker info
        })

    return _group_entries_into_dialogue(entries)


def parse_vtt(text: str) -> list[dict]:
    """解析 WebVTT 字幕格式 / Parse WebVTT subtitle format.

    Returns:
        dialogue 列表 / dialogue list
    """
    # 移除 WEBVTT 头部 / Remove WEBVTT header
    text = re.sub(r"^WEBVTT[^\n]*\n", "", text.strip())
    # 移除 NOTE 注释块 / Remove NOTE comment blocks
    text = re.sub(r"NOTE[^\n]*\n(?:.*\n)*?\n", "", text)
    return parse_srt(text)  # VTT 时间轴格式与 SRT 基本兼容 / VTT timestamp format is basically compatible with SRT


def parse_markdown_transcript(text: str) -> list[dict]:
    """解析 Markdown 格式的转写稿 / Parse Markdown format transcript.

    支持的格式 / Supported formats:
      - **张三**：内容...
      - [00:12:30] 说话人1：内容
      - 说话人 00:12:30-00:15:00：内容
      - Speaker 1: content

    Returns:
        dialogue 列表 / dialogue list
    """
    entries = []
    speaker_map: dict[str, int] = {}
    speaker_counter = 0

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # 模式 1: **说话人**：内容 / Pattern 1: **Speaker**: content
        m = re.match(r"^\*\*(.+?)\*\*\s*[：:]\s*(.+)$", line)
        if m:
            name = m.group(1).strip()
            content = m.group(2).strip()
            sid = _get_or_assign_speaker(name, speaker_map, speaker_counter)
            if sid == speaker_counter:
                speaker_counter += 1
            entries.append({"text": content, "speaker_id": sid, "begin_time": 0, "end_time": 0})
            continue

        # 模式 2: [HH:MM:SS] 说话人：内容 / Pattern 2: [HH:MM:SS] Speaker: content
        m = re.match(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*(.+?)[：:]\s*(.+)$", line)
        if m:
            name = m.group(2).strip()
            content = m.group(3).strip()
            sid = _get_or_assign_speaker(name, speaker_map, speaker_counter)
            if sid == speaker_counter:
                speaker_counter += 1
            begin_ms = _parse_time_str(m.group(1))
            entries.append({"text": content, "speaker_id": sid, "begin_time": begin_ms, "end_time": 0})
            continue

        # 模式 3: 说话人N：内容 / Pattern 3: Speaker N: content
        m = re.match(r"^(?:说话人|Speaker)\s*(\d+)\s*[：:]\s*(.+)$", line, re.IGNORECASE)
        if m:
            # BE-R1：占位编号仅用于 sid 归组，不再作为姓名落盘（id_to_name 不收录）
            content = m.group(2).strip()
            sid = int(m.group(1)) - 1  # 转为 0-based / Convert to 0-based
            entries.append({"text": content, "speaker_id": max(0, sid), "begin_time": 0, "end_time": 0})
            continue

        # 模式 4: 纯文本行（无说话人标注），归入 speaker 0 / Pattern 4: Plain text line, assign to speaker 0
        if len(line) > 5:  # 忽略过短的行 / Skip very short lines
            entries.append({"text": line, "speaker_id": 0, "begin_time": 0, "end_time": 0})

    return _group_entries_into_dialogue(entries, speaker_map)


def _get_or_assign_speaker(name: str, speaker_map: dict[str, int], next_id: int) -> int:
    """为说话人名称分配编号 / Assign ID to speaker name."""
    if name not in speaker_map:
        speaker_map[name] = next_id
    return speaker_map[name]


def _parse_time_str(time_str: str) -> int:
    """将时间字符串解析为毫秒 / Parse time string to milliseconds.

    支持格式 / Supported formats:
      - "1:23" → 83000
      - "1:23:45" → 5025000
      - "01:23:45,678" → 5025678
    """
    parts = re.split(r"[:：]", time_str)
    try:
        if len(parts) == 2:
            return (int(parts[0]) * 60 + int(parts[1])) * 1000
        elif len(parts) == 3:
            ms = 0
            # 处理秒中的逗号（SRT 格式） / Handle comma in seconds (SRT format)
            sec_parts = parts[2].replace(",", ".").split(".")
            ms = int(sec_parts[1]) if len(sec_parts) > 1 else 0
            return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(sec_parts[0])) * 1000 + ms
    except (ValueError, IndexError):
        pass
    return 0


def _group_entries_into_dialogue(
    entries: list[dict],
    speaker_names: dict[str, int] | None = None,
) -> list[dict]:
    """将条目按说话人分组为 dialogue 结构 / Group entries into dialogue structure by speaker.

    Args:
        entries: 解析出的条目列表 [{text, speaker_id, begin_time, end_time}, ...]
        speaker_names: 可选的说话人名称映射 {name: id}

    Returns:
        dialogue 列表，与系统内部结构一致 / dialogue list, consistent with internal structure
    """
    if not entries:
        return []

    # 按说话人分组 / Group by speaker
    speaker_groups: dict[int, list[dict]] = {}
    for entry in entries:
        sid = entry["speaker_id"]
        if sid not in speaker_groups:
            speaker_groups[sid] = []
        speaker_groups[sid].append(entry)

    # 构建 dialogue 结构 / Build dialogue structure
    dialogue = []
    # 反向映射：id → name / Reverse mapping: id → name（仅收录非占位真名，BE-R1）
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

def parse_document_content(content: str, filename: str = "") -> tuple[str, list[dict] | None, str | None]:
    """统一解析文档内容 / Unified document content parsing.

    根据文件扩展名和内容特征自动选择解析策略。

    Args:
        content: 文件文本内容 / File text content
        filename: 文件名（用于格式推断） / Filename (for format inference)

    Returns:
        (content_type, dialogue, summary_text)
        - content_type: "transcript" | "summary" | "unknown"
        - dialogue: 原文类型时返回 dialogue 列表，否则 None
        - summary_text: 纪要类型时返回纪要文本，否则 None
    """
    ext = Path(filename).suffix.lower() if filename else ""

    # 1. 按文件扩展名选择解析器 / Select parser by file extension
    if ext == ".srt":
        dialogue = parse_srt(content)
        if dialogue:
            return CONTENT_TYPE_TRANSCRIPT, dialogue, None
    elif ext == ".vtt":
        dialogue = parse_vtt(content)
        if dialogue:
            return CONTENT_TYPE_TRANSCRIPT, dialogue, None

    # 2. 智能识别内容类型 / Smart detect content type
    content_type = detect_content_type(content)

    if content_type == CONTENT_TYPE_SUMMARY:
        return CONTENT_TYPE_SUMMARY, None, content

    if content_type == CONTENT_TYPE_TRANSCRIPT:
        # 尝试解析为 dialogue / Try parsing as dialogue
        dialogue = parse_markdown_transcript(content)
        if dialogue:
            return CONTENT_TYPE_TRANSCRIPT, dialogue, None
        # 解析失败，降级为 unknown / Parse failed, fallback to unknown
        return CONTENT_TYPE_UNKNOWN, None, None

    # 3. 未知类型：尝试启发式解析 / Unknown type: try heuristic parsing
    # 先尝试当原文解析 / Try parsing as transcript first
    dialogue = parse_markdown_transcript(content)
    if dialogue and len(dialogue) >= 2:
        return CONTENT_TYPE_TRANSCRIPT, dialogue, None

    # 内容太短或无法识别 / Content too short or unrecognizable
    if len(content.strip()) < 50:
        return CONTENT_TYPE_UNKNOWN, None, None

    # 兜底：当纪要处理（用户粘贴的文本更可能是纪要） / Fallback: treat as summary
    return CONTENT_TYPE_SUMMARY, None, content


def infer_title_from_content(content: str, max_length: int = 30) -> str:
    """从内容推断会议标题 / Infer meeting title from content.

    Args:
        content: 文本内容 / Text content
        max_length: 标题最大长度 / Max title length

    Returns:
        推断的标题 / Inferred title
    """
    # 尝试从第一行标题提取 / Try extracting from first heading
    m = re.match(r"^#\s+(.+)$", content.strip(), re.MULTILINE)
    if m:
        title = m.group(1).strip()
        if title and title != "会议纪要":
            return title[:max_length]

    # 尝试从文件名推断（由调用方处理） / Try inferring from filename (handled by caller)
    # 兜底 / Fallback
    return ""
