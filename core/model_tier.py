"""
core/model_tier.py — LLM 模型档位判定与小模型防幻觉提示词（R4 / WP-A）

职责：
  1. 从 settings 读取 engine.local.model_tier（auto | conservative | standard，默认 auto）
  2. auto 模式下按模型名解析参数规模：≤14B 判定为 conservative（保守档）
  3. 向纪要 / 洞察管线提供保守档防幻觉提示词后缀（standard 档返回空串，零行为变化）

设计依据：PRD-LOCAL-ENGINE R4（model_tier auto，≤14B 保守档）；
Spike §4 实测 qwen3:8b 达可用档，但小模型仍需防幻觉约束兜底。
"""

import logging
import re

logger = logging.getLogger(__name__)

# 保守档阈值：参数量 ≤14B 走防幻觉提示词 / Conservative tier threshold
CONSERVATIVE_MAX_SIZE_B = 14.0

# 模型名中的参数规模标记，如 qwen3:8b / llama-3.1-8b / deepseek-r1:70b / qwen2.5-coder-32b-instruct
_SIZE_PATTERN = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*b(?![\w])", re.IGNORECASE)

# 保守档防幻觉提示词后缀（追加到系统提示词末尾） / Anti-hallucination guard appended to system prompts
CONSERVATIVE_PROMPT_GUARD = """

【小模型防幻觉约束】当前由本地小参数模型生成，必须严格遵守：
1. 只依据用户提供的会议对话原文作答，禁止编造、推测或补全对话中未出现的事实、数字、日期、人名、职位与承诺。
2. 模板字段在对话中找不到对应信息时，一律填写「会议未提及」，不得用看似合理的内容占位。
3. 严格保持模板要求的结构与章节，不新增、不删减章节。
4. 对任何拿不准的内容，宁可省略也不要虚构。"""


def parse_model_size_b(model: str | None) -> float | None:
    """从模型名解析参数规模（单位 B）。无法解析返回 None。
    Parse parameter size (in billions) from a model name; None if unparseable.
    """
    if not model:
        return None
    match = _SIZE_PATTERN.search(model)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def get_configured_model_tier() -> str:
    """读取 settings 中的 model_tier 配置（默认 auto）。异常时回退 auto。
    Read engine.local.model_tier from settings (default auto).
    """
    try:
        from app.settings_store import load_settings
        engine = load_settings().get("engine", {}) or {}
        local = engine.get("local", {}) or {}
        tier = str(local.get("model_tier", "auto") or "auto").lower()
        if tier in ("auto", "conservative", "standard"):
            return tier
        logger.warning(f"未知 model_tier 配置: {tier}，回退 auto")
    except Exception as e:
        logger.warning(f"读取 model_tier 配置失败，回退 auto: {e}")
    return "auto"


def resolve_model_tier(model: str | None = None) -> str:
    """解析当前生效的模型档位 / Resolve effective model tier.

    返回 "conservative" 或 "standard"。
    - 显式配置 conservative / standard：直接采用；
    - auto（默认）：按模型名解析参数规模，≤14B → conservative；
      无法解析（如 qwen-plus / gpt-4o 等云端模型）→ standard，云端默认行为零变化。
    """
    tier = get_configured_model_tier()
    if tier in ("conservative", "standard"):
        return tier

    if model is None:
        try:
            from app.settings_store import get_llm_config
            model = get_llm_config().get("model", "")
        except Exception:
            model = ""

    size_b = parse_model_size_b(model)
    if size_b is not None and size_b <= CONSERVATIVE_MAX_SIZE_B:
        return "conservative"
    return "standard"


def get_tier_prompt_guard(model: str | None = None) -> str:
    """获取当前档位对应的提示词后缀 / Get prompt suffix for the effective tier.

    conservative → 防幻觉约束文本；standard → 空串（不改变既有提示词）。
    """
    if resolve_model_tier(model) == "conservative":
        return CONSERVATIVE_PROMPT_GUARD
    return ""
