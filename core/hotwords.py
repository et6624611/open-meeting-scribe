"""
core/hotwords.py — 热词表管理 / Hotword vocabulary management

职责 / Responsibilities:
  1. 读取 data/hotwords.txt / Read data/hotwords.txt
  2. 创建/查询 DashScope 热词表 / Create/query DashScope hotword vocabulary
  3. 返回 vocabulary_id 供转写使用 / Return vocabulary_id for transcription

热词 API 说明 / Hotword API notes:
  - 新版 API 使用 target_model 字段（替代旧的 model 字段） / New API uses target_model field (replaces old model field)
  - 热词格式 / Format: {"text": "词语 / word", "weight": 4}（权重范围 / weight range 1-5，推荐 / recommended 4）
  - Qwen-Audio-3.0-ASR 系列模型支持最多 2000 个热词 / Qwen-Audio-3.0-ASR models support up to 2000 hotwords
  - 权重 50 为超级热词（最多 50 个），召回率大幅提升 / Weight 50 = super hotword (max 50), significantly boosts recall
  - 热词表为账号级资源（每账号最多 10 个），所有兼容模型共享 / Vocabulary is account-level (max 10 per account), shared across compatible models
"""

import logging
import re
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com"


def _get_api_key() -> str:
    from app.store import get_active_api_key
    key = get_active_api_key()
    if not key:
        raise RuntimeError("未设置 API Key，请在设置页面配置或通过 .env 配置 DASHSCOPE_API_KEY")
    return key


def load_hotwords(file_path: str | Path = "data/hotwords.txt") -> list[str]:
    """
    从文件加载热词列表 / Load hotwords from file.

    格式 / Format：一行一个词 / one word per line，# 开头为注释 / # for comments，空行忽略 / blank lines ignored.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        logger.debug(f"热词文件不存在: {file_path}")
        return []

    words = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                words.append(line)

    logger.info(f"加载热词: {len(words)} 个")
    return words


def create_vocabulary(
    name: str,
    words: list[str],
    target_model: str = "qwen-audio-3.0-asr-flash-streaming",
) -> str | None:
    """
    创建 DashScope 热词表 / Create DashScope hotword vocabulary.

    Args:
        name: 热词表名称 / Vocabulary name
        words: 热词列表 / Hotword list
        target_model: 目标模型（热词表需与识别模型匹配） / Target model (vocabulary must match ASR model)
                     实时转写 / Realtime: qwen-audio-3.0-asr-flash-streaming
                     批处理转写 / Batch: paraformer-v2

    Returns:
        vocabulary_id，失败返回 None / vocabulary_id, None on failure

    注意 / Notes:
      - target_model 必须与实际使用的语音识别模型一致，否则热词不生效 / Must match actual ASR model, otherwise hotwords won't take effect
      - 热词表创建后约需数秒编译，建议创建后查询状态为 OK 再使用 / Takes a few seconds to compile after creation; query status OK before use
      - 如不需要可跳过，转写时不传 vocabulary_id / Optional; skip vocabulary_id if not needed
    """
    if not words:
        logger.info("热词为空，跳过创建")
        return None

    api_key = _get_api_key()
    url = f"{DASHSCOPE_BASE}/api/v1/vocabularies"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 构造热词列表（带默认权重 4，推荐起始值） / Build hotword list (default weight 4, recommended starting value)
    # Qwen-Audio-3.0-ASR 系列最多 2000 个热词 / Qwen-Audio-3.0-ASR supports up to 2000 hotwords
    word_list = [{"text": w, "weight": 4} for w in words[:2000]]

    body = {
        "target_model": target_model,
        "prefix": name,
        "vocabulary": word_list,
    }

    try:
        logger.info(f"创建热词表: {name} ({len(words)} 个词, 目标模型={target_model})")
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        vocab_id = data.get("data", {}).get("vocabulary_id")
        logger.info(f"热词表创建成功: {vocab_id}")
        return vocab_id
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.warning("热词表 API 不可用（404），跳过热词功能")
        else:
            logger.warning(f"创建热词表失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"创建热词表异常: {e}")
        return None


def get_or_create_vocabulary(
    hotwords_file: str | Path = "data/hotwords.txt",
    name: str = "oms-hotwords",
    target_model: str = "qwen-audio-3.0-asr-flash-streaming",
) -> str | None:
    """
    加载热词并创建热词表（如需要） / Load hotwords and create vocabulary (if needed).

    Args:
        hotwords_file: 热词文件路径 / Hotword file path
        name: 热词表名称前缀 / Vocabulary name prefix
        target_model: 目标模型（需与识别模型匹配） / Target model (must match ASR model)

    Returns:
        vocabulary_id 或 None / vocabulary_id or None
    """
    words = load_hotwords(hotwords_file)
    if not words:
        return None
    return create_vocabulary(name, words, target_model)


# ── 热词映射（后处理纠正） / Hotword mappings (post-processing correction) ──

# 模块级缓存：(file_path, mtime) → (mappings, compiled_patterns) / Module-level cache
_mappings_cache: dict[str, tuple[float, list[tuple[str, str]], list[tuple[re.Pattern, str]]]] = {}


def invalidate_hotword_mappings_cache() -> None:
    """清除热词映射缓存（文件被外部修改后调用） / Clear hotword mapping cache (call after external file modification)"""
    _mappings_cache.clear()


def load_hotword_mappings(
    file_path: str | Path = "data/hotword_mappings.txt",
) -> list[tuple[str, str]]:
    """
    从文件加载热词映射列表（带 mtime 缓存） / Load hotword mapping list from file (with mtime cache).

    格式 / Format：每行一条 / one per line，`错误识别→正确文本 / wrong→correct`，# 开头为注释 / # for comments，空行忽略 / blank lines ignored.

    Returns:
        [(asr_text, correct_text), ...]，按左串长度降序排列（长匹配优先） / Sorted by left-string length descending (long match first)
    """
    file_path = Path(file_path)
    key = str(file_path)

    if not file_path.exists():
        _mappings_cache.pop(key, None)
        logger.debug(f"热词映射文件不存在: {file_path}")
        return []

    mtime = file_path.stat().st_mtime
    cached = _mappings_cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]

    mappings = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 支持 → 和 -> 两种分隔符 / Support both → and -> separators
            for sep in ("→", "->"):
                if sep in line:
                    left, right = line.split(sep, 1)
                    left, right = left.strip(), right.strip()
                    if left and right:
                        mappings.append((left, right))
                    break

    # 长匹配优先：按左串长度降序排列 / Long match first: sort by left-string length descending
    mappings.sort(key=lambda x: len(x[0]), reverse=True)
    logger.info(f"加载热词映射: {len(mappings)} 条")

    # 预编译正则（英文词用 ASCII 邻接边界，中文用直接替换） / Pre-compile regex (ASCII terms use the ASCII-adjacency boundary, CJK uses direct replacement)
    compiled = []
    for asr_text, correct_text in mappings:
        if _is_ascii_word(asr_text):
            compiled.append((
                ascii_term_pattern(asr_text),
                correct_text,
            ))

    _mappings_cache[key] = (mtime, mappings, compiled)
    return mappings


def _get_compiled_patterns(
    file_path: str | Path = "data/hotword_mappings.txt",
) -> list[tuple[re.Pattern, str]]:
    """获取预编译的正则映射（与 load_hotword_mappings 共享缓存） / Get pre-compiled regex mappings (shared cache with load_hotword_mappings)"""
    # 确保缓存已填充 / Ensure cache is populated
    load_hotword_mappings(file_path)
    cached = _mappings_cache.get(str(Path(file_path)))
    return cached[2] if cached else []


def _is_ascii_word(pattern: str) -> bool:
    """判断是否为纯 ASCII 字母/数字组成的词（适合词边界匹配） / Check if composed of pure ASCII letters/digits (suitable for word boundary matching)"""
    return bool(re.match(r"^[A-Za-z0-9]+$", pattern))


def ascii_term_pattern(term: str) -> re.Pattern:
    """ASCII 词条「独立成词」的判定正则 / Word-boundary pattern for an ASCII term.

    为何不用 `\\b`：Python 的 Unicode 语义下，中日韩假名/汉字也算 `\\w`，
    所以「与ES（」里 与 与 E 之间根本不存在 `\\b`，导致紧贴中文的英文编码（中文会议里
    最常见的形态）永远匹配不上：ES→EAS 写了却不生效，而用同一规则做的残留扫描也报 0，
    连「漏改告警」都是盲的。
    真正的边界语义应是「左右不挨其他 ASCII 字母/数字」：既能命中「与ES（」，
    又不会咬穿 FILES / ESB / ESG。

    Why not `\\b`: under Python's Unicode semantics CJK ideographs are `\\w`, so there is
    no boundary between 与 and E in 「与ES（」 and English codes glued to Chinese never match.
    The intended boundary is "not adjacent to another ASCII letter/digit".
    """
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def sub_term(text: str, asr_text: str, correct_text: str) -> tuple[str, int]:
    """
    按映射匹配规则替换单个词条，并返回命中次数 / Replace one term, returning the hit count.

    与 apply_hotword_mappings 共用同一匹配语义，区别只在于这里需要把命中数交回调用方
    （划词修正的全量回溯要据此告知用户到底改了几处）。
    Shares the matching semantics of apply_hotword_mappings; the only difference is that
    the hit count is handed back, which the retroactive correction flow needs to report.

    Returns:
        (替换后的文本, 命中次数) / (replaced text, hit count)
    """
    if not text or not asr_text:
        return text, 0
    if _is_ascii_word(asr_text):
        pattern = ascii_term_pattern(asr_text)
        # 替换侧用函数而非模板串：避免 correct_text 里的 \1 / \\ 被当作反向引用吞掉。
        # A callable replacement keeps correct_text literal (\1, \\ must not be reinterpreted).
        return pattern.subn(lambda _m: correct_text, text)
    hits = text.count(asr_text)
    if not hits:
        return text, 0
    return text.replace(asr_text, correct_text), hits


def apply_hotword_mappings(
    text: str,
    mappings: list[tuple[str, str]] | None = None,
    mappings_file: str | Path = "data/hotword_mappings.txt",
) -> str:
    """
    对文本应用热词映射（后处理纠正） / Apply hotword mappings to text (post-processing correction).

    匹配策略 / Matching strategy:
      - 纯英文/数字词：按 ASCII 邻接边界匹配，大小写不敏感（避免咬穿 FILES / ESB，
        同时能命中紧贴中文的「与ES」，详见 ascii_term_pattern）
        / Pure ASCII terms: bounded by non-ASCII-alphanumeric neighbours, case-insensitive
      - 含中文的串：直接子串替换 / Strings with Chinese: direct substring replacement

    Args:
        text: 待处理文本 / Text to process
        mappings: 映射列表，为 None 时自动从文件加载（带缓存） / Mapping list; if None, auto-load from file (cached)
        mappings_file: 映射文件路径（仅 mappings 为 None 时使用） / Mapping file path (only used when mappings is None)

    Returns:
        替换后的文本 / Replaced text
    """
    if mappings is not None:
        # 调用方显式传入 mappings，走原逻辑（每次编译正则） / Caller explicitly passes mappings, use original logic (compile regex each time)
        for asr_text, correct_text in mappings:
            if _is_ascii_word(asr_text):
                text = ascii_term_pattern(asr_text).sub(correct_text, text)
            else:
                text = text.replace(asr_text, correct_text)
        return text

    # 使用缓存：预编译正则，避免每次重复读文件 + 编译 / Use cache: pre-compiled regex, avoid repeated file reads + compilation
    raw_mappings = load_hotword_mappings(mappings_file)
    if not raw_mappings:
        return text

    compiled = _get_compiled_patterns(mappings_file)
    # raw_mappings 与 compiled 中英文条目顺序一致，用索引同步遍历 / raw_mappings and compiled have same order for CJK/English entries, traverse with index sync
    ci = 0  # compiled 列表指针 / compiled list pointer
    for asr_text, correct_text in raw_mappings:
        if _is_ascii_word(asr_text):
            if ci < len(compiled):
                pat, _ = compiled[ci]
                text = pat.sub(correct_text, text)
                ci += 1
        else:
            text = text.replace(asr_text, correct_text)

    return text
