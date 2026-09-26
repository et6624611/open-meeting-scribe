"""
core/cli_engine/context_export.py — 会议上下文序列化到 CLI 工作区
Serialize meeting context into the CLI agent workspace (files, not one giant prompt).

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
更新 / Updated: 2026-09-25
版本 / Version: 1.1.0

职责 / Responsibilities:
  - 把四维会议上下文落成工作区文件，供 CLI 用自身检索能力按需读取（方案 §3.1）
  - 工作区物理隔离于 data/（SPIKE M3 / §3.10）：agent-workspace/<engine_id>/<task_id>/
  - 严禁把 settings.json 或其字段复制进工作区（§3.7-4 红线）

原则：大文件走工作区、小关键信息进 prompt；项目知识库用 --add-dir 挂载而非复制。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.speakers import normalize_speaker_name

logger = logging.getLogger(__name__)

# 工作区根目录：仓库根下 agent-workspace/，与 data/（含 settings.json）无父子关系（M3）
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT / "agent-workspace"

# 单文件体量上限（字符），超限截断并标注，避免工作区无限膨胀（R4）
_MAX_TRANSCRIPT_CHARS = 40000
_MAX_SUMMARY_CHARS = 8000

# 洞察消息存储目录：与后端同一事实源约定（cwd 相对） / Insight messages dir (same cwd-relative convention as routers)
INSIGHTS_TASKS_DIR = Path("data/tasks")


def workspace_dir(engine_id: str, task_id: str | None) -> Path:
    """返回并确保工作区目录存在；task_id 缺省用 general 命名空间。"""
    tid = task_id or "general"
    ws = (WORKSPACE_ROOT / engine_id / tid).resolve()
    (ws / "context").mkdir(parents=True, exist_ok=True)
    (ws / "output").mkdir(parents=True, exist_ok=True)
    return ws


def _render_transcript(task: dict, speaker_map: dict) -> str:
    """将 task.dialogue 渲染为带时间戳、说话人实名化的 Markdown。"""
    dialogue = task.get("dialogue") or []
    lines: list[str] = []
    for item in dialogue:
        name = normalize_speaker_name(item.get("speaker_name")) or "未识别发言人"
        sents = item.get("sentences") or []
        if sents:
            for s in sents:
                text = (s.get("text") or "").strip()
                if text:
                    lines.append(f"{name}：{text}")
        else:
            text = (item.get("text") or "").strip()
            if text:
                lines.append(f"{name}：{text}")
    out = "\n".join(lines)
    if len(out) > _MAX_TRANSCRIPT_CHARS:
        out = out[:_MAX_TRANSCRIPT_CHARS] + "\n…（转写过长已截断）"
    return out


def _render_insights(task_id: str | None) -> str:
    """读取会议洞察消息并渲染为 Markdown；无洞察 / 无文件时返回空串。
    Render persisted insight messages; empty string when absent or none."""
    if not task_id:
        return ""
    f = INSIGHTS_TASKS_DIR / f"{task_id}.insights.json"
    if not f.exists():
        return ""
    try:
        msgs = json.loads(f.read_text(encoding="utf-8")).get("messages", [])
    except Exception:
        return ""
    valid = [m for m in msgs if (m.get("title") or "").strip()]
    if not valid:
        return ""
    parts = ["# 会议洞察台（AI 会中/会后观察，供参考非事实源）\n"]
    blocks = []
    for m in valid:
        phase = "会后" if m.get("phase") == "post_meeting" else "会中"
        block = f"## [{phase}] {m['title'].strip()}\n\n{(m.get('body') or '').strip()}\n"
        solution = (m.get("solution") or "").strip()
        if solution:
            block += f"\n**行动建议**：{solution}\n"
        diagram = (m.get("diagram") or "").strip()
        if diagram:
            block += f"\n```mermaid\n{diagram}\n```\n"
        blocks.append(block)
    parts.extend(blocks)
    return "\n---\n".join(parts)


def export_context(
    *,
    engine_id: str,
    task: dict | None,
    task_id: str | None,
    user_message: str,
    page_context: str = "",
    role_prompt: str = "",
    speaker_map: dict | None = None,
    workspace_key: str | None = None,
) -> dict:
    """
    将会议上下文写入工作区文件，返回调用元数据。 / Write context files, return invocation metadata.

    workspace_key：工作区目录主键，优先用面板会话 id（chat_session_id）使工作区与
    CLI 会话对齐 → 删除会话标签可精确定位清理（方案 D5）；缺省回退 task_id。

    Returns:
        {"workspace": str, "add_dirs": [str], "brief": str}
        brief 为进入 --append-system-prompt 的轻量任务说明。
    """
    ws = workspace_dir(engine_id, workspace_key or task_id)
    ctx = ws / "context"
    speaker_map = speaker_map or {}

    written: list[str] = []

    if task:
        transcript = _render_transcript(task, speaker_map)
        if transcript:
            (ctx / "transcript.md").write_text(
                "# 会议转写原文（说话人已实名化）\n\n" + transcript, encoding="utf-8")
            written.append("context/transcript.md")

        summary = (task.get("summary") or "").strip()
        if summary and "内容过短" not in summary and "无法生成有效纪要" not in summary:
            (ctx / "summary.md").write_text(
                "# 当前会议纪要\n\n" + summary[:_MAX_SUMMARY_CHARS], encoding="utf-8")
            written.append("context/summary.md")

        todos = task.get("todos") or []
        if todos:
            (ctx / "todos.json").write_text(
                json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append("context/todos.json")

    # 洞察台观察结论（持久化文件，工作区文件模式对 token 预算宽松，全量不截断）
    # Insight Deck observations (full render; workspace-file mode tolerates larger context)
    insights_md = _render_insights(task_id)
    if insights_md:
        (ctx / "insights.md").write_text(insights_md, encoding="utf-8")
        written.append("context/insights.md")

    # 页面上下文 + 角色说明 → AGENTS.md（CLI 启动自动读取，替代巨型 prompt 注入）
    agents_parts = ["# 会议助手工作区\n"]
    if role_prompt:
        agents_parts.append("## 角色\n" + role_prompt.strip() + "\n")
    if page_context:
        agents_parts.append("## 环境\n" + page_context.strip() + "\n")
    agents_parts.append(
        "## 说明\n本工作区由 OpenMeetingScribe 自动生成。"
        "context/ 目录为会议只读上下文，output/ 目录为你的可写产物区。"
        "任何对会议纪要/待办的正式修改必须通过提供的集成工具（MCP）完成，不得直接改工作区外文件。\n")
    agents_md = "\n".join(agents_parts)
    (ws / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    written.append("AGENTS.md")

    # 轻量 brief：仅当前问题 + 关键指针，重内容靠 CLI 自行读取工作区
    brief_lines = [
        "你是嵌入在会议软件中的工程化助手。用户当前问题如下。",
        "会议上下文已就绪于工作区文件：" + (", ".join(written) or "（无会议数据，仅当前问题）"),
        "",
        "## 用户本轮问题",
        user_message.strip(),
    ]
    brief = "\n".join(brief_lines)

    # 项目知识库：以绝对路径 --add-dir 挂载，不复制（M3/§3.1）
    add_dirs: list[str] = []
    project_path = (task or {}).get("project_path")
    if project_path and Path(project_path).is_dir():
        add_dirs.append(str(Path(project_path).resolve()))

    logger.info("[CLI引擎] 上下文导出 task=%s ws=%s files=%d", task_id, ws, len(written))
    return {"workspace": str(ws), "add_dirs": add_dirs, "brief": brief}


def cleanup_workspace(engine_id: str, task_id: str | None) -> None:
    """删除指定工作区（面板会话删除时联动清理，方案 D5 修订要求）。"""
    import shutil
    tid = task_id or "general"
    ws = (WORKSPACE_ROOT / engine_id / tid).resolve()
    if ws.is_dir() and WORKSPACE_ROOT in ws.parents:
        shutil.rmtree(ws, ignore_errors=True)
        logger.info("[CLI引擎] 工作区已清理 %s", ws)


def sweep_expired_workspaces(retention_days: int) -> int:
    """
    按修改时间清理过期任务工作区（方案 R7/§3.10：workspace 用后可清）。

    retention_days <= 0 视为“不自动清理”，返回 0。返回删除的任务工作区目录数。
    仅删除 WORKSPACE_ROOT 之下两层（<engine_id>/<task_id>）的目录，避免误删。
    """
    import shutil
    import time
    if retention_days is None or retention_days <= 0:
        return 0
    cutoff = time.time() - retention_days * 86400
    removed = 0
    if not WORKSPACE_ROOT.is_dir():
        return 0
    for engine_dir in WORKSPACE_ROOT.iterdir():
        if not engine_dir.is_dir():
            continue
        for task_dir in engine_dir.iterdir():
            if not task_dir.is_dir():
                continue
            try:
                if task_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(task_dir, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    if removed:
        logger.info("[CLI引擎] 过期工作区清理 %d 个（保留 %d 天）", removed, retention_days)
    return removed
