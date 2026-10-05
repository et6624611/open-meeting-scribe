"""
app/routers/philosophy.py — 理念传播 / Philosophy dissemination

从 data/philosophies.json 随机返回一条理念，供前端在页面底部展示 / Randomly return a philosophy from data/philosophies.json for frontend footer display.
支持多语言：条目可为 {"zh": "...", "en": "..."} 格式，通过 lang 查询参数选择语种 / Multi-language support: entries can be {"zh": "...", "en": "..."} format; select language via lang query param.
支持按页面和 Tab 筛选：条目可含 page / tab 字段，API 优先精确匹配 page+tab，回退到 page 级，再回退到无限制通用条目 / Supports page+tab filtering: entries may carry page/tab fields; API prefers exact page+tab match, falls back to page-level, then to unrestricted generic entries.
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


def _match(item: dict, page: str | None, tab: str | None, *, exact: bool) -> bool:
    """判断条目是否匹配指定 page/tab 条件 / Check whether an entry matches the given page/tab criteria.
    exact=True 时要求条目同时拥有对应字段且值相等；exact=False 时仅要求条目不含该字段（通用条目） / When exact=True the entry must carry the field with matching value; when exact=False the entry must NOT carry that field (generic entry).
    """
    item_page = item.get("page")
    item_tab = item.get("tab")
    if exact:
        if page and item_page != page:
            return False
        if tab and item_tab != tab:
            return False
        # 至少匹配到 page 级别（允许无 tab 的 page 条目） / At least match page level (page entries without tab are allowed)
        return item_page == page if page else False
    # 通用条目：不含 page 和 tab 字段 / Generic entry: no page or tab fields
    return not item_page and not item_tab


@router.get("/api/philosophy/random")
def get_random_philosophy(lang: str = "zh", page: str | None = None, tab: str | None = None):
    """随机返回一条理念文本 / Randomly return a philosophy text.

    默认返回 {"text": "..."} 兼容旧调用 / Default returns {"text": "..."} for backward compat;
    传入 all=true 时返回 {"variants": {"zh": "...", "en": "..."}} 供前端按 locale 选取 / With all=true returns {"variants": {...}} for frontend locale selection.

    page / tab 参数用于按页面筛选，回退顺序：page+tab → page → 通用 / page/tab params filter by page; fallback order: page+tab → page → generic.
    """
    if not PHILOSOPHIES_FILE.exists():
        return {"text": "", "variants": {}}
    items = json.loads(PHILOSOPHIES_FILE.read_text(encoding="utf-8"))
    if not items:
        return {"text": "", "variants": {}}

    dicts = [i for i in items if isinstance(i, dict)]
    chosen = None

    # 回退链：精确 page+tab → page 级 → 通用条目 / Fallback chain: exact page+tab → page-level → generic
    if page and tab:
        candidates = [d for d in dicts if d.get("page") == page and d.get("tab") == tab]
        if candidates:
            chosen = random.choice(candidates)
    if chosen is None and page:
        candidates = [d for d in dicts if d.get("page") == page and not d.get("tab")]
        if candidates:
            chosen = random.choice(candidates)
    if chosen is None:
        candidates = [d for d in dicts if not d.get("page") and not d.get("tab")]
        if candidates:
            chosen = random.choice(candidates)

    # 兜底：所有条目中随机选 / Last resort: pick from all entries
    if chosen is None:
        chosen = random.choice(items)

    # 构造多语言变体 / Construct multilingual variants
    if isinstance(chosen, dict):
        variants = {k: v for k, v in chosen.items() if isinstance(v, str) and k not in ("page", "tab")}
    else:
        variants = {"zh": str(chosen)}
    return {"text": _resolve_text(chosen, lang), "variants": variants}
