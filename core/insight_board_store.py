"""
core/insight_board_store.py — 洞察板多看板 manifest 存储

实现从 core/insight_board.py 拆出，保持行为零变化。

职责：
- 一场会议多份板（manifest 为唯一权威）
- board_html_load / board_html_save / board_html_save_section
- invoke_create_board / invoke_revise_board（工具入口）
"""

import json
import logging
import re
import time
from pathlib import Path

from core.fs_atomic import atomic_write_json, atomic_write_text
from core.insight_board_html import (
    _RECAP_GUIDANCE,
    _TEXT_WALL_GUIDANCE,
    BOARD_HTML_CAP,
    _valid_task_id,
    detect_recap_floor,
    detect_text_wall,
    sanitize_board_html,
)

logger = logging.getLogger(__name__)


def _board_tasks_dir():
    """动态读取 BOARD_TASKS_DIR，使 monkeypatch.setattr(ib, 'BOARD_TASKS_DIR', ...) 穿透生效。"""
    import core.insight_board as ib
    return ib.BOARD_TASKS_DIR

DEFAULT_BOARD_ID = "main"
DEFAULT_BOARD_TITLE = "主看板"
BOARD_TITLE_MAX = 60
_BOARD_ID_RE = re.compile(r"^[\w-]{1,48}$")
_SECTION_ID_RE = re.compile(r"^[\w-]{1,64}$")


def _valid_board_id(board_id: str) -> bool:
    return bool(board_id) and bool(_BOARD_ID_RE.match(board_id))


def _legacy_html_path(task_id: str) -> Path:
    return _board_tasks_dir() / f"{task_id}.board.html"


def _manifest_path(task_id: str) -> Path:
    return _board_tasks_dir() / f"{task_id}.boards.json"


def _board_file_path(task_id: str, board_id: str) -> Path:
    return _board_tasks_dir() / f"{task_id}.board.{board_id}.html"


def _migrate_legacy_board(task_id: str, manifest: dict) -> dict:
    legacy = _legacy_html_path(task_id)
    if not legacy.exists():
        return manifest
    target = _board_file_path(task_id, DEFAULT_BOARD_ID)
    if not target.exists():
        try:
            legacy.rename(target)
        except OSError as e:
            logger.warning("[洞察板] 存量板迁移失败 task=%s: %s", task_id, e)
            return manifest
        try:
            legacy_meta = json.loads(
                (_board_tasks_dir() / f"{task_id}.board.meta.json").read_text(encoding="utf-8"))
            rev, upd = int(legacy_meta.get("revision") or 0), legacy_meta.get("updated_at")
        except (OSError, ValueError, TypeError):
            rev, upd = 1, int(time.time() * 1000)
    else:
        rev, upd = 0, None
    try:
        (_board_tasks_dir() / f"{task_id}.board.meta.json").unlink()
    except OSError:
        pass
    boards = list(manifest.get("boards") or [])
    if not any(b.get("board_id") == DEFAULT_BOARD_ID for b in boards):
        boards.insert(0, {"board_id": DEFAULT_BOARD_ID, "title": DEFAULT_BOARD_TITLE,
                          "file": DEFAULT_BOARD_ID, "revision": rev, "updated_at": upd})
    migrated = {"boards": boards,
                "default_board_id": manifest.get("default_board_id") or DEFAULT_BOARD_ID}
    atomic_write_json(_manifest_path(task_id), migrated)
    logger.info("[洞察板] 存量单文件板已迁移为 main task=%s rev=%s", task_id, rev)
    return migrated


def _read_manifest(task_id: str) -> dict:
    if not _valid_task_id(task_id):
        return {"boards": [], "default_board_id": DEFAULT_BOARD_ID}
    try:
        raw = json.loads(_manifest_path(task_id).read_text(encoding="utf-8"))
        manifest = {"boards": [b for b in (raw.get("boards") or []) if isinstance(b, dict)],
                    "default_board_id": raw.get("default_board_id") or DEFAULT_BOARD_ID}
    except (OSError, ValueError, TypeError):
        manifest = {"boards": [], "default_board_id": DEFAULT_BOARD_ID}
    if not manifest["boards"]:
        manifest = _migrate_legacy_board(task_id, manifest)
    if not manifest["boards"]:
        manifest["boards"] = [{"board_id": DEFAULT_BOARD_ID, "title": DEFAULT_BOARD_TITLE,
                               "file": DEFAULT_BOARD_ID, "revision": 0, "updated_at": None}]
    return manifest


def _write_manifest(task_id: str, manifest: dict) -> None:
    atomic_write_json(_manifest_path(task_id),
                      {"boards": manifest.get("boards") or [],
                       "default_board_id": manifest.get("default_board_id") or DEFAULT_BOARD_ID})


def _find_board_entry(manifest: dict, board_id: str | None) -> dict | None:
    bid = board_id or manifest.get("default_board_id") or DEFAULT_BOARD_ID
    for b in manifest.get("boards") or []:
        if b.get("board_id") == bid:
            return b
    return None


def boards_manifest(task_id: str) -> dict:
    if not _valid_task_id(task_id):
        return {"boards": [], "default_board_id": DEFAULT_BOARD_ID}
    m = _read_manifest(task_id)
    out = []
    for b in m.get("boards") or []:
        bid = str(b.get("board_id") or "")
        out.append({
            "board_id": bid,
            "title": b.get("title") or bid,
            "revision": int(b.get("revision") or 0),
            "updated_at": b.get("updated_at"),
            "exists": bool(_board_file_path(task_id, bid).exists()) if _valid_board_id(bid) else False,
        })
    return {"boards": out, "default_board_id": m.get("default_board_id") or DEFAULT_BOARD_ID}


def _next_board_id(manifest: dict) -> str:
    used = {str(b.get("board_id") or "") for b in manifest.get("boards") or []}
    n = 2
    while f"board-{n}" in used:
        n += 1
    return f"board-{n}"


def invoke_create_board(task_id: str, arguments: dict) -> dict:
    if not _valid_task_id(task_id):
        return {"ok": False, "error": "invalid_task_id"}
    args = arguments or {}
    title = str(args.get("title") or "").strip()[:BOARD_TITLE_MAX]
    if not title:
        return {"ok": False, "error": "title_required"}
    manifest = _read_manifest(task_id)
    board_id = str(args.get("board_id") or "").strip() or _next_board_id(manifest)
    if not _valid_board_id(board_id):
        return {"ok": False, "error": "invalid_board_id"}
    if _find_board_entry(manifest, board_id) is not None:
        return {"ok": False, "error": "board_exists", "board_id": board_id,
                "boards": [b.get("board_id") for b in manifest.get("boards") or []]}
    entry = {"board_id": board_id, "title": title, "file": board_id,
             "revision": 0, "updated_at": int(time.time() * 1000)}
    boards = list(manifest.get("boards") or []) + [entry]
    _write_manifest(task_id, {"boards": boards,
                              "default_board_id": manifest.get("default_board_id") or DEFAULT_BOARD_ID})
    logger.info("[洞察板] 建板 task=%s board=%s title=%s", task_id, board_id, title)
    return {"ok": True, "board_id": board_id, "title": title, "revision": 0,
            "info": f"已新建洞察板「{title}」（{board_id}），等待首次写入内容"}


def board_html_load(task_id: str, board_id: str | None = None) -> dict | None:
    if not _valid_task_id(task_id):
        return None
    if board_id is not None and not _valid_board_id(board_id):
        return None
    manifest = _read_manifest(task_id)
    entry = _find_board_entry(manifest, board_id)
    if entry is None:
        return None
    bid = str(entry.get("board_id"))
    path = _board_file_path(task_id, bid)
    if not path.exists():
        return None
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.warning("[洞察板] HTML 读取失败 task=%s board=%s", task_id, bid)
        return None
    return {"html": html, "revision": int(entry.get("revision") or 0),
            "updated_at": entry.get("updated_at"), "board_id": bid,
            "title": entry.get("title") or bid}


def board_html_meta(task_id: str, board_id: str | None = None) -> dict | None:
    if not _valid_task_id(task_id):
        return None
    m = boards_manifest(task_id)
    boards = m["boards"]
    if board_id is not None:
        hit = next((b for b in boards if b["board_id"] == board_id), None)
        if hit is None:
            return None
        return {"revision": hit["revision"], "updated_at": hit["updated_at"],
                "exists": hit["exists"], "board_id": hit["board_id"]}
    head = next((b for b in boards if b["board_id"] == m["default_board_id"]),
                boards[0] if boards else None)
    return {"revision": head["revision"] if head else 0,
            "updated_at": head["updated_at"] if head else None,
            "exists": bool(head and head["exists"]),
            "board_id": head["board_id"] if head else m["default_board_id"],
            "boards": boards, "default_board_id": m["default_board_id"]}


def board_html_save(task_id: str, html: str, *, content_floor: bool = True,
                    board_id: str | None = None,
                    expected_revision: int | str | None = None) -> dict:
    if not _valid_task_id(task_id):
        return {"ok": False, "error": "invalid_task_id"}
    if not isinstance(html, str) or not html.strip():
        return {"ok": False, "error": "empty_html"}
    if len(html) > BOARD_HTML_CAP:
        return {"ok": False, "error": f"html_too_large(>{BOARD_HTML_CAP} chars)"}
    manifest = _read_manifest(task_id)
    entry = _find_board_entry(manifest, board_id)
    if entry is None:
        return {"ok": False, "error": "unknown_board_id",
                "board_id": board_id,
                "boards": [{"board_id": b.get("board_id"), "title": b.get("title"),
                             "revision": int(b.get("revision") or 0)}
                            for b in manifest.get("boards") or []],
                "hint": "需要新板请调用 create_insight_board 提案，由用户确认后才建板"}
    bid = str(entry.get("board_id"))
    prev_revision = int(entry.get("revision") or 0)
    if expected_revision is not None and not isinstance(expected_revision, bool):
        try:
            exp = int(expected_revision)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_expected_revision", "board_id": bid}
        if exp != prev_revision:
            logger.info("[洞察板] 基线过期 task=%s board=%s expected=%s current=%s",
                        task_id, bid, exp, prev_revision)
            return {"ok": False, "error": "stale_baseline", "board_id": bid,
                    "current_revision": prev_revision,
                    "hint": "你读到的基线已不是最新版，重新从 context/boards/ 或空参读回后再改"}
    cleaned, removed = sanitize_board_html(html)
    if not cleaned.strip():
        return {"ok": False, "error": "html_empty_after_sanitize", "removed": removed}
    if content_floor:
        recap_reasons = detect_recap_floor(cleaned)
        if recap_reasons:
            logger.info("[洞察板] 复述底线拒收 task=%s: %s", task_id, recap_reasons)
            return {"ok": False, "error": "board_is_recap", "reasons": recap_reasons,
                    "guidance": _RECAP_GUIDANCE, "removed": removed}
        total_sec, visual_sec = detect_text_wall(cleaned)
        if total_sec and visual_sec < (1 if total_sec == 1 else total_sec - 1):
            logger.info("[洞察板] 文字墙拒收 task=%s sections=%d visuals=%d",
                        task_id, total_sec, visual_sec)
            return {"ok": False, "error": "board_is_text_wall",
                    "reasons": [f"{total_sec} 个节中仅 {visual_sec} 个含主视觉（内联 SVG / canvas / mermaid 形态 pre / data URI 图片）"],
                    "guidance": _TEXT_WALL_GUIDANCE, "removed": removed}
    revision = prev_revision + 1
    now_ms = int(time.time() * 1000)
    atomic_write_text(_board_file_path(task_id, bid), cleaned)
    entry["revision"], entry["updated_at"] = revision, now_ms
    _write_manifest(task_id, manifest)
    logger.info("[洞察板] HTML 落盘 task=%s board=%s rev=%s chars=%d removed=%s",
                task_id, bid, revision, len(cleaned), removed or "-")
    return {"ok": True, "revision": revision, "removed": removed,
            "board_id": bid, "updated_at": now_ms}


def _section_pattern(section_id: str) -> re.Pattern:
    return re.compile(
        r'<section\b[^>]*\bdata-ib-id=["\']' + re.escape(section_id) + r'["\'][^>]*>.*?</section>',
        re.DOTALL | re.IGNORECASE,
    )


def board_html_save_section(task_id: str, section_id: str, section_html: str,
                            board_id: str | None = None) -> dict:
    if not _valid_task_id(task_id):
        return {"ok": False, "error": "invalid_task_id"}
    if not isinstance(section_id, str) or not _SECTION_ID_RE.match(section_id):
        return {"ok": False, "error": "invalid_section_id"}
    if not isinstance(section_html, str) or not section_html.strip():
        return {"ok": False, "error": "empty_section"}
    cleaned, _removed = sanitize_board_html(section_html)
    if not cleaned.strip():
        return {"ok": False, "error": "section_empty_after_sanitize"}
    if f'data-ib-id="{section_id}"' not in cleaned and f"data-ib-id='{section_id}'" not in cleaned:
        cleaned = re.sub(r"<section\b", f'<section data-ib-id="{section_id}"', cleaned, count=1, flags=re.IGNORECASE)
    cur = board_html_load(task_id, board_id)
    if not cur or not cur.get("html"):
        manifest = _read_manifest(task_id)
        if _find_board_entry(manifest, board_id) is None:
            return {"ok": False, "error": "unknown_board_id", "board_id": board_id,
                    "boards": [b.get("board_id") for b in manifest.get("boards") or []],
                    "hint": "需要新板请调用 create_insight_board 提案，由用户确认"}
        return {"ok": False, "error": "no_board"}
    m = _section_pattern(section_id).search(cur["html"])
    if not m:
        return {"ok": False, "error": "section_not_found", "section_id": section_id}
    merged = cur["html"][:m.start()] + cleaned + cur["html"][m.end():]
    res = board_html_save(task_id, merged, board_id=cur["board_id"],
                          expected_revision=cur["revision"])
    if not res.get("ok"):
        return res
    logger.info("[洞察板] 单节补丁 task=%s board=%s sec=%s rev=%s",
                task_id, cur["board_id"], section_id, res["revision"])
    return {"ok": True, "revision": res["revision"], "section_id": section_id,
            "board_id": res["board_id"],
            "info": f"洞察板『{section_id}』这一节已更新，其余节保持不变"}


def invoke_revise_board(task_id: str, arguments: dict) -> dict:
    args = arguments or {}
    bid_arg = str(args.get("board_id") or "").strip() or None
    if bid_arg is not None and not _valid_board_id(bid_arg):
        return {"ok": False, "error": "invalid_board_id", "board_id": bid_arg}
    html_arg = args.get("html")
    if html_arg is None or (isinstance(html_arg, str) and not html_arg.strip()):
        m = boards_manifest(task_id)
        artifact = board_html_load(task_id, bid_arg)
        if artifact is None:
            return {"ok": True, "html": None, "revision": 0,
                    "boards": [{"board_id": b["board_id"], "title": b["title"],
                                 "revision": b["revision"], "exists": b["exists"]}
                                for b in m["boards"]],
                    "default_board_id": m["default_board_id"],
                    "info": "正文未取：请带 board_id 重调本工具（空参读只回清单）。尚无内容的板 revision=0，首版可直接整份落盘"}
        return {"ok": True, **artifact}
    exp_raw = args.get("expected_revision")
    expected_revision = None if exp_raw in (None, "") else exp_raw
    res = board_html_save(task_id, str(html_arg), board_id=bid_arg,
                          expected_revision=expected_revision)
    if not res.get("ok"):
        return res
    return {"ok": True, "revision": res["revision"], "board_id": res["board_id"],
            "removed": res.get("removed", []),
            "info": "洞察板已更新，前端板区会自动重拉（点「刷新」可立即对齐）"}
