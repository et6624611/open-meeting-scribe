"""
core/insight_board.py — 洞察板引擎（聚合入口） / Insight Board engine (facade)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-28
更新 / Updated: 2026-11-06
版本 / Version: 2.0.0

洞察板（Insight Board）核心模块的聚合入口。按职责拆分为三个子模块：
- insight_board_spec.py  【已退役】Board Spec v0.3 校验/ops/JSON 持久化/LLM 生成
- insight_board_html.py  HTML 产物安全清洗 + 复述/文字墙内容底线检测
- insight_board_store.py 多看板 manifest 存储与读写入口

本模块仅做符号聚合（通过模块级 __getattr__ 延迟转发），保持既有
`from core.insight_board import X` 与 `import core.insight_board as ib; ib.X`
两种访问方式完全兼容。

【已退役】Board Spec v0.3 结构化契约随「洞察共创 · 会话驱动（HTML 产物版）」
下线，代码保留在 insight_board_spec.py 供追溯，不再被任何入口接线。
"""

from __future__ import annotations

from . import insight_board_html as _html
from . import insight_board_spec as _spec
from . import insight_board_store as _store

_SUBMODULES = (_spec, _html, _store)

# ruff: noqa: F822 — 聚合层，符号通过 __getattr__ 动态转发到子模块，静态分析盲区
__all__ = [
    # spec
    "SPEC_VERSION", "MAX_ZONES", "BOARD_TASKS_DIR",
    "CAP_TITLE", "CAP_SUMMARY", "CAP_LABEL", "CAP_TEXT", "CAP_DIAGRAM_SOURCE",
    "ZONE_STATUS", "ZONE_MATURITY", "VISUAL_KINDS", "TEXT_KINDS", "CELL_KINDS", "OP_KINDS",
    "BoardValidationError", "validate_board", "apply_ops",
    "board_path", "load_board", "save_board", "new_board", "build_board_digest",
    "BOARD_ANALYSIS_PROMPT", "run_board_analysis",
    # html
    "BOARD_HTML_CAP", "_valid_task_id", "sanitize_board_html",
    "detect_recap_floor", "detect_text_wall",
    # store
    "DEFAULT_BOARD_ID", "DEFAULT_BOARD_TITLE", "BOARD_TITLE_MAX",
    "_valid_board_id", "boards_manifest", "invoke_create_board",
    "board_html_load", "board_html_meta", "board_html_save",
    "board_html_save_section", "invoke_revise_board",
]


def __getattr__(name: str):
    for m in _SUBMODULES:
        attr = getattr(m, name, None)
        if attr is not None or name in m.__dict__:
            return attr
    raise AttributeError(f"module 'core.insight_board' has no attribute {name!r}")
