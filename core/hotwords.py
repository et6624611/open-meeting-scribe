"""
core/hotwords.py — 热词表管理

职责：
  1. 读取 data/hotwords.txt
  2. 创建/查询 DashScope 热词表
  3. 返回 vocabulary_id 供转写使用

热词 API 说明：
  - 新版 API 使用 target_model 字段（替代旧的 model 字段）
  - 热词格式：{"text": "词语", "weight": 4}（权重范围 1-5，推荐 4）
  - Qwen-Audio-3.0-ASR 系列模型支持最多 2000 个热词
  - 权重 50 为超级热词（最多 50 个），召回率大幅提升
  - 热词表为账号级资源（每账号最多 10 个），所有兼容模型共享
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
    从文件加载热词列表。

    格式：一行一个词，# 开头为注释，空行忽略。
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
    创建 DashScope 热词表。

    Args:
        name: 热词表名称
        words: 热词列表
        target_model: 目标模型（热词表需与识别模型匹配）
                     实时转写：qwen-audio-3.0-asr-flash-streaming
                     批处理转写：paraformer-v2

    Returns:
        vocabulary_id，失败返回 None

    注意：
      - target_model 必须与实际使用的语音识别模型一致，否则热词不生效
      - 热词表创建后约需数秒编译，建议创建后查询状态为 OK 再使用
      - 如不需要可跳过，转写时不传 vocabulary_id
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

    # 构造热词列表（带默认权重 4，推荐起始值）
    # Qwen-Audio-3.0-ASR 系列最多 2000 个热词
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
    加载热词并创建热词表（如需要）。

    Args:
        hotwords_file: 热词文件路径
        name: 热词表名称前缀
        target_model: 目标模型（需与识别模型匹配）

    Returns:
        vocabulary_id 或 None
    """
    words = load_hotwords(hotwords_file)
    if not words:
        return None
    return create_vocabulary(name, words, target_model)


# ── 热词映射（后处理纠正） ──

# 模块级缓存：(file_path, mtime) → (mappings, compiled_patterns)
_mappings_cache: dict[str, tuple[float, list[tuple[str, str]], list[tuple[re.Pattern, str]]]] = {}


def invalidate_hotword_mappings_cache() -> None:
    """清除热词映射缓存（文件被外部修改后调用）"""
    _mappings_cache.clear()


def load_hotword_mappings(
    file_path: str | Path = "data/hotword_mappings.txt",
) -> list[tuple[str, str]]:
    """
    从文件加载热词映射列表（带 mtime 缓存）。

    格式：每行一条，`错误识别→正确文本`，# 开头为注释，空行忽略。

    Returns:
        [(asr_text, correct_text), ...]，按左串长度降序排列（长匹配优先）
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
            # 支持 → 和 -> 两种分隔符
            for sep in ("→", "->"):
                if sep in line:
                    left, right = line.split(sep, 1)
                    left, right = left.strip(), right.strip()
                    if left and right:
                        mappings.append((left, right))
                    break

    # 长匹配优先：按左串长度降序排列
    mappings.sort(key=lambda x: len(x[0]), reverse=True)
    logger.info(f"加载热词映射: {len(mappings)} 条")

    # 预编译正则（英文词用 \b 词边界，中文用直接替换）
    compiled = []
    for asr_text, correct_text in mappings:
        if _is_ascii_word(asr_text):
            compiled.append((
                re.compile(r"\b" + re.escape(asr_text) + r"\b", re.IGNORECASE),
                correct_text,
            ))

    _mappings_cache[key] = (mtime, mappings, compiled)
    return mappings


def _get_compiled_patterns(
    file_path: str | Path = "data/hotword_mappings.txt",
) -> list[tuple[re.Pattern, str]]:
    """获取预编译的正则映射（与 load_hotword_mappings 共享缓存）"""
    # 确保缓存已填充
    load_hotword_mappings(file_path)
    cached = _mappings_cache.get(str(Path(file_path)))
    return cached[2] if cached else []


def _is_ascii_word(pattern: str) -> bool:
    """判断是否为纯 ASCII 字母/数字组成的词（适合词边界匹配）"""
    return bool(re.match(r"^[A-Za-z0-9]+$", pattern))


def apply_hotword_mappings(
    text: str,
    mappings: list[tuple[str, str]] | None = None,
    mappings_file: str | Path = "data/hotword_mappings.txt",
) -> str:
    """
    对文本应用热词映射（后处理纠正）。

    匹配策略：
      - 纯英文/数字词：使用 \\b 词边界匹配，大小写不敏感（避免误替换子串）
      - 含中文的串：直接子串替换

    Args:
        text: 待处理文本
        mappings: 映射列表，为 None 时自动从文件加载（带缓存）
        mappings_file: 映射文件路径（仅 mappings 为 None 时使用）

    Returns:
        替换后的文本
    """
    if mappings is not None:
        # 调用方显式传入 mappings，走原逻辑（每次编译正则）
        for asr_text, correct_text in mappings:
            if _is_ascii_word(asr_text):
                pattern = re.compile(r"\b" + re.escape(asr_text) + r"\b", re.IGNORECASE)
                text = pattern.sub(correct_text, text)
            else:
                text = text.replace(asr_text, correct_text)
        return text

    # 使用缓存：预编译正则，避免每次重复读文件 + 编译
    raw_mappings = load_hotword_mappings(mappings_file)
    if not raw_mappings:
        return text

    compiled = _get_compiled_patterns(mappings_file)
    # raw_mappings 与 compiled 中英文条目顺序一致，用索引同步遍历
    ci = 0  # compiled 列表指针
    for asr_text, correct_text in raw_mappings:
        if _is_ascii_word(asr_text):
            if ci < len(compiled):
                pat, _ = compiled[ci]
                text = pat.sub(correct_text, text)
                ci += 1
        else:
            text = text.replace(asr_text, correct_text)

    return text
