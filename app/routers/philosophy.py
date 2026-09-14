"""
app/routers/philosophy.py — 理念传播 / Philosophy dissemination

从 data/philosophies.json 随机返回一条理念，供前端在页面底部展示 / Randomly return a philosophy from data/philosophies.json for frontend footer display.
支持多语言：条目可为 {"zh": "...", "en": "..."} 格式，通过 lang 查询参数选择语种 / Multi-language support: entries can be {"zh": "...", "en": "..."} format; select language via lang query param.
"""

import json
import random

from fastapi import APIRouter

from app.store import PHILOSOPHIES_FILE

router = APIRouter(tags=["philosophy"])


def _resolve_text(item: dict | str, lang: str) -> str:
    """从条目中提取指定语言的文本；兼容纯字符串格式 / Extract text in specified language from entry; compatible with plain string format."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get(lang) or item.get("zh") or ""
    return ""


@router.get("/api/philosophy/random")
def get_random_philosophy(lang: str = "zh"):
    """随机返回一条理念文本 / Randomly return a philosophy text.

    默认返回 {"text": "..."} 兼容旧调用 / Default returns {"text": "..."} for backward compat;
    传入 all=true 时返回 {"variants": {"zh": "...", "en": "..."}} 供前端按 locale 选取 / With all=true returns {"variants": {...}} for frontend locale selection.
    """
    if not PHILOSOPHIES_FILE.exists():
        return {"text": "", "variants": {}}
    items = json.loads(PHILOSOPHIES_FILE.read_text(encoding="utf-8"))
    if not items:
        return {"text": "", "variants": {}}
    chosen = random.choice(items)
    # 构造多语言变体 / Construct multilingual variants
    if isinstance(chosen, dict):
        variants = {k: v for k, v in chosen.items() if isinstance(v, str)}
    else:
        variants = {"zh": str(chosen)}
    return {"text": _resolve_text(chosen, lang), "variants": variants}
