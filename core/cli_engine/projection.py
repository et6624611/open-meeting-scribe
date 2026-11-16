"""
core/cli_engine/projection.py — 资产工作区单向投影（ASSET_SYNC P2）

SSOT（任务 JSON）→ agent-workspace/_preview 的增量投影：
  - 幂等：正文 hash 未变跳过重写（_write_md_with_meta 内建）
  - 锚点：.oms/projection.json 记录每文件投影 hash + content_rev，
    供回流侧（import_from_workspace）做三方冲突判定与防回环
  - 容错不降级：单文件原子写（要么完整要么不写）；渲染失败记 errors、
    整体 ok=False，绝不把半截批次标为已同步；失败不阻断主链路
  - 单写者约定：只有服务进程投影；CLI 引擎与外部 IDE 不写 context/

契约来源 / Source of truth: docs/design/ASSET_SYNC_ARCHITECTURE.md §3.4 / §4 / §6 P2。

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-11
版本 / Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
from datetime import datetime
from pathlib import Path

from core.fs_atomic import atomic_write_json

from .context_paths import (
    PREVIEW_ROOT,
    _find_meeting_dir,
    _project_dir_name,
    preview_workspace_dir,
)
from .context_render import _write_context_md_files

logger = logging.getLogger(__name__)

MANIFEST_NAME = "projection.json"

# per-task 投影锁：串行化同一会议的并发投影（进程内；跨进程遵循单写者约定）
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _task_lock(task_id: str) -> threading.Lock:
    with _locks_guard:
        lk = _locks.get(task_id)
        if lk is None:
            lk = threading.Lock()
            _locks[task_id] = lk
        return lk


# ── 正文规范化与 hash（投影/回流共用，必须同口径） ──


def normalize_body(text: str) -> str:
    """规范化正文：统一换行、去首尾空行与尾部空白——吸收编辑器/同步盘的无意义差异。"""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n").rstrip()


def body_hash(text: str) -> str:
    """正文 sha256（规范化后）。权威变更判据；mtime 仅作廉价预过滤。"""
    return "sha256:" + hashlib.sha256(normalize_body(text).encode("utf-8")).hexdigest()


def split_frontmatter_body(content: str) -> str:
    """剥 YAML frontmatter 取正文（与 import_from_workspace 同口径）；无 frontmatter 原样返回。"""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            return content[end + 3:].lstrip("\n")
    return content


# ── 投影清单（.oms/projection.json） ──


def manifest_path(ws: Path) -> Path:
    return ws / ".oms" / MANIFEST_NAME


def read_manifest(ws: Path) -> dict:
    """读投影清单；缺失/损坏按空处理（旧工作区降级为无锚点行为）。"""
    f = manifest_path(ws)
    if not f.exists():
        return {}
    try:
        import json
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - 坏清单不炸业务，重建即可
        return {}


def rebuild_manifest(ws: Path, task: dict | None, errors: dict | None = None) -> dict:
    """扫描 context/ 现状重建投影清单（全量导出与增量投影共用收口）。

    可回流文件（summary/notes）额外记 base_hash = 投影时 SSOT 定稿基线的 hash，
    供回流侧三方冲突判定（S vs P）；其余文件只有投影 hash。
    """
    from core.chat_context import task_final_summary, task_notes
    baselines: dict[str, str] = {}
    if task:
        baselines["context/summary.md"] = task_final_summary(task)
        baselines["context/notes.md"] = task_notes(task)
    ctx = ws / "context"
    files: dict[str, dict] = {}
    if ctx.is_dir():
        for f in sorted(ctx.iterdir()):
            if not f.is_file():
                continue
            rel = f"context/{f.name}"
            try:
                if f.suffix == ".md":
                    entry = {"hash": body_hash(split_frontmatter_body(f.read_text(encoding="utf-8")))}
                elif f.name == "decisions.json":
                    entry = {"hash": body_hash(f.read_text(encoding="utf-8"))}
                else:
                    continue
                if rel in baselines:
                    entry["base_hash"] = body_hash(baselines[rel])
                files[rel] = entry
            except OSError:
                continue
    manifest = {
        "task_id": (task or {}).get("task_id", ""),
        "content_rev": int((task or {}).get("content_rev") or 0),
        "projected_at": datetime.now().astimezone().isoformat(),
        "files": files,
        "errors": errors or {},
    }
    atomic_write_json(manifest_path(ws), manifest)
    return manifest


# ── 投影主入口 ──


def project_task(task_id: str) -> dict:
    """把任务定稿内容增量投影到资产工作区（触发点：生成完成/应用内编辑/重命名等）。

    返回 {workspace, file_count, ok, errors}；flag 关闭返回 skipped；
    任务不存在返回 error。渲染失败不抛异常（容错不降级：记 errors，ok=False）。
    """
    from core.settings_store import get_feature_flags
    if not get_feature_flags().get("asset_projection", True):
        return {"skipped": "flag_disabled"}
    from core.task_store import tasks
    task = tasks.get(task_id)
    if not task:
        return {"error": "task_not_found"}

    with _task_lock(task_id):
        ws = preview_workspace_dir(task_id, task.get("project_id"), task)
        ctx = ws / "context"
        written: list[str] = []
        errors: dict[str, str] = {}
        try:
            _write_context_md_files(ctx, task, task_id, {}, None, None, written)
        except Exception as e:  # noqa: BLE001 - 投影失败不阻断主链路，标 dirty 待重试
            errors["render"] = str(e)[:500]
            logger.warning("[资产投影] task=%s 渲染失败（标 dirty 待重试）: %s", task_id[:8], e)
        rebuild_manifest(ws, task, errors=errors)
        if errors:
            try:
                from core import joblog
                joblog.append_event(task_id, joblog.STAGE_SUMMARY,
                                    f"资产投影部分失败：{errors.get('render', '')[:120]}", level="warn")
            except Exception:  # noqa: BLE001
                pass
        return {"workspace": str(ws), "file_count": len(written),
                "ok": not errors, "errors": errors}


# ── 生命周期联动（删除/归档） ──


def _find_ws(task: dict) -> Path | None:
    """非创建式定位会议工作区目录（兼容旧版 UUID 项目目录）；找不到返回 None。"""
    task_id = task.get("task_id") or ""
    project_id = task.get("project_id")
    roots = ([PREVIEW_ROOT / _project_dir_name(project_id), PREVIEW_ROOT / project_id]
             if project_id else [PREVIEW_ROOT / "_standalone"])
    for root in roots:
        d = _find_meeting_dir(root, task_id)
        if d is not None:
            return d
    return None


def purge_meeting_workspace(task: dict) -> bool:
    """任务删除联动清理资产工作区（应用拥有 _preview；知识库副本用户拥有，不删）。"""
    d = _find_ws(task)
    if d is None:
        return False
    resolved = d.resolve()
    if PREVIEW_ROOT.resolve() not in resolved.parents:
        return False  # 安全闸：绝不在 _preview 之外动刀
    shutil.rmtree(resolved, ignore_errors=True)
    logger.info("[资产投影] 会议工作区已随任务删除 %s", resolved.name)
    return True


def set_archived(task_id: str, archived: bool) -> None:
    """归档/取消归档：仅在投影清单打标，不移动文件（保护外部引用）。"""
    try:
        from core.task_store import tasks
        task = tasks.get(task_id)
        if not task:
            return
        d = _find_ws(task)
        if d is None:
            return
        manifest = read_manifest(d)
        if not manifest:
            return
        manifest["archived"] = bool(archived)
        atomic_write_json(manifest_path(d), manifest)
    except Exception as e:  # noqa: BLE001 - 归档打标失败不阻断归档主流程
        logger.warning("[资产投影] 归档打标失败 task=%s: %s", task_id[:8], e)
