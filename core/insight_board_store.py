"""
core/insight_board_store.py — 洞察板存储入口（Markdown 版）

2026-11-12 重构：洞察板从「一场会议多份自包含 HTML + manifest」
简化为「一场会议一份 Markdown 文件」。

职责（对外暴露的唯一入口）：
- board_md_load / board_md_save / board_md_meta  —— 转发到 insight_board_md
- 多板接口（boards_manifest / invoke_create_board / board_html_save_section）
  保留为 NoOp 或返回固定值，避免上游 import 报错；逐步淘汰中。
- migrate_legacy_html_to_md  —— 统一由 core.insight_board_md 提供（聚合层转发）
"""

from __future__ import annotations

import logging
import re

from core.insight_board_md import (
    board_md_load,
    board_md_meta,
    board_md_save,
)

logger = logging.getLogger(__name__)


DEFAULT_BOARD_ID = "main"
DEFAULT_BOARD_TITLE = "主看板"
BOARD_TITLE_MAX = 60
_BOARD_ID_RE = re.compile(r"^[\w-]{1,48}$")


def _valid_board_id(board_id: str) -> bool:
    """兼容老签名：现在全场固定 "main"。"""
    return True  # 老调用方无需报 invalid


# ── 对外主入口（md 版） ──
def board_html_load(task_id: str, board_id: str | None = None) -> dict | None:
    """兼容老签名：内部读 insight.md。返回的 dict 仍带 "html" 键但值为 markdown
    （前端将从路由层切到新键 "markdown"，此处仅作过渡）。"""
    artifact = board_md_load(task_id)
    if artifact is None:
        return None
    return {
        "markdown": artifact["markdown"],
        "html": artifact["markdown"],  # 兼容过渡
        "revision": artifact["revision"],
        "updated_at": artifact["updated_at"],
        "board_id": artifact["board_id"],
        "title": artifact["title"],
    }


def board_html_meta(task_id: str, board_id: str | None = None) -> dict | None:
    m = board_md_meta(task_id)
    return m  # 已是标准形状


def board_html_save(
    task_id: str,
    html_or_md: str,
    *,
    content_floor: bool = False,  # 默认 False：保持老测试/老调用点口径不炸
    board_id: str | None = None,
    expected_revision: int | str | None = None,
) -> dict:
    """兼容老签名：把传入文本当作 markdown 处理。

    注意：默认 content_floor=False（与历史行为兼容），新调用点显式传 True 才跑复述/文字墙防线。
    """
    return board_md_save(
        task_id, str(html_or_md),
        content_floor=content_floor,
        expected_revision=expected_revision,
    )


# ── 多板相关（废弃，返回固定值保持上游 import 不炸） ──
def boards_manifest(task_id: str) -> dict:
    """一场会议固定一份板。"""
    m = board_md_meta(task_id)
    return {
        "boards": [{
            "board_id": m["board_id"],
            "title": m.get("title") or DEFAULT_BOARD_TITLE,
            "revision": m.get("revision") or 0,
            "updated_at": m.get("updated_at"),
            "exists": m.get("exists", False),
        }],
        "default_board_id": m["board_id"],
    }


def invoke_create_board(task_id: str, arguments: dict) -> dict:
    """废弃：不再支持多板。直接回 ok=false。"""
    return {"ok": False, "error": "multi_board_deprecated",
            "info": "洞察板已改为一场会议一份，不再支持多板拆分"}


def board_html_save_section(task_id: str, section_id: str, section_html: str,
                            board_id: str | None = None) -> dict:
    """废弃：单份 md 直接全量覆盖或用户手改。"""
    return {"ok": False, "error": "section_save_deprecated",
            "info": "洞察板已改为 Markdown 整份覆盖，单节修订请在前端直接编辑对应 section-id 块"}


def invoke_revise_board(task_id: str, arguments: dict) -> dict:
    """会话工具入口：读写 insight.md。空参或无正文 = 读；带正文 = 写。"""
    args = arguments or {}
    html_arg = args.get("html") or args.get("markdown")
    if html_arg is None or (isinstance(html_arg, str) and not html_arg.strip()):
        m = boards_manifest(task_id)
        artifact = board_md_load(task_id)
        if artifact is None:
            return {"ok": True, "markdown": None, "revision": 0,
                    "boards": m["boards"], "default_board_id": m["default_board_id"],
                    "info": "正文未取：本场会议尚无洞察板内容"}
        return {"ok": True,
                "markdown": artifact["markdown"],
                "revision": artifact["revision"],
                "board_id": artifact["board_id"],
                "title": artifact["title"],
                "boards": m["boards"],
                "default_board_id": m["default_board_id"]}
    exp_raw = args.get("expected_revision")
    expected_revision = None if exp_raw in (None, "") else exp_raw
    res = board_md_save(task_id, str(html_arg), expected_revision=expected_revision)
    if not res.get("ok"):
        return res
    return {"ok": True, "revision": res["revision"], "board_id": res["board_id"],
            "removed": res.get("removed", []),
            "info": "洞察板已更新，前端洞察 Tab 会自动重拉"}
