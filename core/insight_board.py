"""
core/insight_board.py — 洞察板引擎（聚合入口） / Insight Board engine (facade)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-28
更新 / Updated: 2026-11-12
版本 / Version: 3.0.0

洞察板从「HTML 产物版」改为「单份 Markdown 文件版」（一场会议一份 insight.md）。
按职责拆分为四个子模块：
- insight_board_md.py   【新主模块】Markdown 读写 + 内容底线 + legacy 迁移
- insight_board_store.py 对外存储入口（转发到 md，老接口兼容）
- insight_board_html.py 【已退役】HTML 清洗与防线，保留供存量引用，逐步废弃
- insight_board_spec.py 【已退役】Board Spec v0.3 结构化契约

本模块仅做符号聚合（模块级 __getattr__ 延迟转发），保持既有
`from core.insight_board import X` 与 `import core.insight_board as ib; ib.X`
两种访问方式完全兼容。
"""

from __future__ import annotations

from . import insight_board_html as _html
from . import insight_board_md as _md
from . import insight_board_spec as _spec
from . import insight_board_store as _store

_SUBMODULES = (_md, _html, _spec, _store)

__all__ = [
    # md（新增主模块）
    "BOARD_MD_CAP", "parse_front_matter", "dump_front_matter",
    "_valid_task_id", "board_md_load", "board_md_meta", "board_md_save",
    "sanitize_board_md", "detect_recap_floor", "detect_text_wall",
    "migrate_legacy_html_to_md", "html_to_markdown",
    # store（转发到 md）
    "DEFAULT_BOARD_ID", "DEFAULT_BOARD_TITLE", "BOARD_TITLE_MAX",
    "_valid_board_id", "boards_manifest", "invoke_create_board",
    "board_html_load", "board_html_meta", "board_html_save",
    "board_html_save_section", "invoke_revise_board",
    # html（已退役，保留存量引用）
    "BOARD_HTML_CAP", "sanitize_board_html",
]


def __getattr__(name: str):
    for m in _SUBMODULES:
        attr = getattr(m, name, None)
        if attr is not None or name in m.__dict__:
            return attr
    raise AttributeError(f"module 'core.insight_board' has no attribute {name!r}")
