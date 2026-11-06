"""
core/cli_engine/context_export.py — CLI 引擎上下文导出（聚合入口）

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
更新 / Updated: 2026-11-06
版本 / Version: 2.0.0

按职责拆分为三个子模块，本模块为聚合入口：
- context_paths.py   路径与目录命名/迁移/清理 + 模块级常量
- context_render.py  上下文模板拼装与 Markdown 渲染
- context_index.py   会议索引与跨会议台账

顶层导出函数保留在本模块，其余符号通过模块级 __getattr__ 延迟转发到子模块，
保持外部 import 与 monkeypatch 兼容。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .context_index import (
    _migrate_all_dirs,
    _migrate_meeting_dirs,
    _project_members,
    _rebuild_global_index,
    _store_members,
    _write_global_decisions,
    _write_scope_indexes,
    read_meetings_index,
    update_workspace_index,
)
from .context_paths import (
    _MAX_NOTES_CHARS,
    _MAX_SUMMARY_CHARS,
    _UUID_RE,
    _meeting_date_slug,
    preview_workspace_dir,
    project_preview_dir,
    workspace_dir,
)
from .context_render import (
    _base_meta,
    _build_permission_section,
    _flatten_dialogue,
    _now_iso,
    _realtime_pairs,
    _render_history,
    _render_insights,
    _render_transcript,
    _start_here,
    _start_here_meeting,
    _write_agent_rules,
    _write_board_files,
    _write_context_md_files,
    _write_md_with_meta,
)

logger = logging.getLogger(__name__)

_SUBMODULES_NAMES = ("context_paths", "context_render", "context_index")


def _ce():
    return __import__("core.cli_engine.context_export", fromlist=["context_export"])


def __getattr__(name: str):
    import importlib
    for sub in _SUBMODULES_NAMES:
        m = importlib.import_module(f".{sub}", __package__)
        attr = getattr(m, name, None)
        if attr is not None or name in m.__dict__:
            return attr
    raise AttributeError(f"module 'core.cli_engine.context_export' has no attribute {name!r}")

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
    history: list[dict] | None = None,
    realtime_entries: list[dict] | None = None,
    auth_tier: str | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """
    将会议上下文写入工作区文件，返回调用元数据。 / Write context files, return invocation metadata.

    workspace_key：工作区目录主键，优先用面板会话 id（chat_session_id）使工作区与
    CLI 会话对齐 → 删除会话标签可精确定位清理（方案 D5）；缺省回退 task_id。

    history：前端传来的同会话历史消息列表，序列化为 context/history.md，
    确保即使 session resume 失败 CLI 仍可读回上文（修复多轮上下文割裂）。

    realtime_entries：录音进行中前端快照的实时定稿句；dialogue 尚未落盘时用它
    渲染 transcript.md，避免会中提问时 CLI 看到"无转写"（2026-09-29 会中问答复盘）。

    Returns:
        {"workspace": str, "add_dirs": [str], "brief": str}
        brief 为进入 --append-system-prompt 的轻量任务说明。
    """
    ws = workspace_dir(engine_id, workspace_key or task_id)
    ctx = ws / "context"
    speaker_map = speaker_map or {}
    # 定稿口径与会话/前端同源（局部 import：CLI 引擎不在后端进程预热 core.chat_context）
    from core.chat_context import task_final_summary, task_notes

    written: list[str] = []

    if task:
        pairs = _flatten_dialogue(task, speaker_map)
        in_progress = False
        if not pairs:
            pairs = _realtime_pairs(realtime_entries, task, speaker_map, task_id)
            in_progress = bool(pairs)
        if pairs:
            header = ("# 会议转写原文（说话人已实名化；录音进行中，以下为实时转写）\n\n"
                      if in_progress else "# 会议转写原文（说话人已实名化）\n\n")
            rendered = _render_transcript(pairs)
            transcript_body = header + rendered
            _write_md_with_meta(ctx, "transcript.md", {
                **_base_meta(task_id, task, "transcript"),
                "speaker_count": len(set(name for name, _ in pairs)),
                "char_count": len(transcript_body),
                "truncated": "转写过长已截断" in rendered,
                "is_realtime": in_progress,
            }, transcript_body)
            written.append("context/transcript.md")

        summary = task_final_summary(task).strip()
        if summary and "内容过短" not in summary and "无法生成有效纪要" not in summary:
            summary_body = "# 当前会议纪要（用户已编辑时为编辑后版本）\n\n" + summary[:_MAX_SUMMARY_CHARS]
            _write_md_with_meta(ctx, "summary.md", {
                **_base_meta(task_id, task, "summary"),
                "char_count": len(summary_body),
                "truncated": len(summary) > _MAX_SUMMARY_CHARS,
                "chapter_count": len(task.get("chapters") or []),
                "edited_by_user": bool(task.get("summary_edited")),
            }, summary_body)
            written.append("context/summary.md")

        # 随记：四域中唯一的用户原创区，此前从未导出给 CLI——用户把共识结论写进随记
        # 要求同步决策面板时，工作区里没有 notes，AI 只能报「读不到」（2026-09-30 复盘）
        notes = task_notes(task)
        if notes:
            body = notes[:_MAX_NOTES_CHARS]
            truncated_notes = len(notes) > _MAX_NOTES_CHARS
            if truncated_notes:
                body += '\n…（随记过长已截断）'
            notes_body = (
                '# 会议随记（用户手写原文，非 AI 产物）\n\n'
                '> 随记是用户本人记录的会议要点，可信度高于转写推断。当用户要求'
                '「按随记更新纪要/决策」时，以随记表述为准；随记属用户原创区，'
                '如需改写只能走 propose_notes 提案通道（用户接受后才落盘）。\n\n' + body)
            _write_md_with_meta(ctx, 'notes.md', {
                **_base_meta(task_id, task, "notes"),
                "char_count": len(notes_body),
                "truncated": truncated_notes,
            }, notes_body)
            written.append('context/notes.md')

        decisions = task.get("decisions") or []
        if decisions:
            (ctx / "decisions.json").write_text(
                json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append("context/decisions.json")

    # 洞察台观察结论（持久化文件，工作区文件模式对 token 预算宽松，全量不截断）
    # Insight Deck observations (full render; workspace-file mode tolerates larger context)
    insights_md = _render_insights(task_id)
    if insights_md:
        insight_count = insights_md.count("\n## ")
        phases_set: set[str] = set()
        if "会中" in insights_md:
            phases_set.add("in_meeting")
        if "会后" in insights_md:
            phases_set.add("post_meeting")
        _write_md_with_meta(ctx, "insights.md", {
            **_base_meta(task_id, task, "insights"),
            "insight_count": insight_count,
            "phases": sorted(phases_set),
        }, insights_md)
        written.append("context/insights.md")

    # 洞察板 HTML 基线：多轮共创不从零重写的根因修复（见 _write_board_files）
    _write_board_files(ctx, task_id, written)

    # 对话历史（保障多轮上下文连续性，防止 session resume 失败时上下文割裂）
    # Conversation history: guards multi-turn continuity when session resume fails
    history_md = _render_history(history)
    if history_md:
        history_turns = [m for m in (history or []) if (m.get("content") or "").strip()]
        if history_turns and history_turns[-1].get("role") == "user":
            history_turns = history_turns[:-1]
        _write_md_with_meta(ctx, "history.md", {
            **_base_meta(task_id, task, "history"),
            "turn_count": len(history_turns),
            "truncated": "更早历史已省略" in history_md,
        }, history_md)
        written.append("context/history.md")

    # @附件：用户本轮显式上传的本地文件与图片，原样复制到 context/attachments/
    # （智能体具备文件读取/解析能力，不在后端预抽取，避免与内置链路重复实现解析）
    attachment_lines: list[str] = []
    if attachments:
        from core.chat_attachment_store import load_bytes  # 局部 import：附件存储已下沉 core 层

        attach_dir = ctx / "attachments"
        attach_dir.mkdir(parents=True, exist_ok=True)
        used_names: set[str] = set()
        for i, ref in enumerate(attachments):
            try:
                meta, blob = load_bytes(str(ref.get("id", "")))
            except Exception:  # noqa: BLE001 - 单个附件缺失不阻断其余上下文
                continue
            safe = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", meta["filename"]).strip("._") or f"file_{i}"
            if safe in used_names:
                safe = f"{i}_{safe}"
            used_names.add(safe)
            (attach_dir / safe).write_bytes(blob)
            attachment_lines.append(
                f"- context/attachments/{safe}（{meta['content_type']}，{meta['size']} 字节）")
            written.append(f"context/attachments/{safe}")

    # 页面上下文 + 角色说明 → AGENTS.md（CLI 启动自动读取，替代巨型 prompt 注入）
    agents_parts = ["# 会议助手工作区\n"]
    if role_prompt:
        agents_parts.append("## 角色\n" + role_prompt.strip() + "\n")
    if page_context:
        agents_parts.append("## 环境\n" + page_context.strip() + "\n")
    # 模式即权限（§5.2）：按本轮落档注入权限段，置于角色段之后（后声明者胜）
    agents_parts.append(_build_permission_section(auth_tier))
    if attachment_lines:
        agents_parts.append(
            "## 用户本轮上传的附件\n以下文件为用户显式提供，可用你的文件读取能力直接解析"
            "（文本/表格/PDF/图片）。引用其内容时标注文件名；读不到或无法解析时明说，禁止臆测。\n"
            + "\n".join(attachment_lines) + "\n")
    agents_parts.append(
        "## 说明\n本工作区由 OpenMeetingScribe 自动生成。"
        "context/ 目录为会议只读上下文，output/ 目录为你的可写产物区。"
        "任何对会议纪要/决策的正式修改必须通过提供的集成工具（MCP）完成，不得直接改工作区外文件。\n")
    agents_md = "\n".join(agents_parts)
    (ws / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    written.append("AGENTS.md")

    # 轻量 brief：仅当前问题 + 关键指针，重内容靠 CLI 自行读取工作区
    brief_lines = [
        "你是嵌入在会议软件中的工程化助手。用户当前问题如下。",
        "会议上下文已就绪于工作区文件：" + (", ".join(written) or "（无会议数据，仅当前问题）"),
    ]
    # 当存在对话历史时，显式引导 CLI 阅读上文以保持连续性
    if history_md:
        brief_lines.append(
            "\n## 多轮对话连续性\n"
            "本会话存在前序对话（见 context/history.md）。请将其作为上下文延续，"
            "理解用户当前消息是对前一轮回复的追问/确认/延伸，不要当作全新对话重新开始。"
        )
    brief_lines += [
        "",
        "## 用户本轮问题",
        user_message.strip(),
    ]
    # 条件化洞察板强约束：用户意图是洞察板生成时，在 brief 末尾硬注入完成契约
    _BOARD_KEYWORDS = ("洞察板", "insight.board", "insight board", "insightboard")
    _is_board_intent = any(kw.lower() in user_message.lower() for kw in _BOARD_KEYWORDS)
    if _is_board_intent:
        brief_lines += [
            "",
            "【强制执行】洞察板共创三步：",
            "① 读工作区 context/boards/index.md 选板，再 Read context/boards/<board_id>.html 拿基线（无此文件=首版，revision=0）",
            "   → ② web_search ×最多2次 → ③ revise_insight_board(board_id, html=<完整HTML>, expected_revision=<读到的版本号>) 落盘",
            "缺第③步就是任务失败——后端没有板文件，用户洞察 tab 是空的。",
            "收到 error=stale_baseline 说明基线已过期，重读后再改；不要把旧基线直接覆盖上去。",
            "不要在搜索后直接回复用户。必须看到工具回执 revision≥1 再回复。",
            "版式（doctype / <style> / 配色 / 脚本）由你负责；图片字体一律 data URI 内联。",
        ]
    brief = "\n".join(brief_lines)

    # 项目知识库：以绝对路径 --add-dir 挂载，不复制（M3/§3.1）
    add_dirs: list[str] = []
    project_path = (task or {}).get("project_path")
    if project_path and Path(project_path).is_dir():
        add_dirs.append(str(Path(project_path).resolve()))

    logger.info("[CLI引擎] 上下文导出 task=%s ws=%s files=%d", task_id, ws, len(written))
    return {"workspace": str(ws), "add_dirs": add_dirs, "brief": brief}


def export_preview_context(*, task_id: str, task: dict,
                           project_id: str | None = None,
                           realtime_entries: list[dict] | None = None,
                           ide_id: str | None = None) -> dict:
    """预生成工作区（无 user_message/attachments/history），返回 {workspace, file_count}。
    复用 _write_context_md_files 的渲染逻辑，写带 frontmatter 的 .md 文件。"""
    ws = preview_workspace_dir(task_id, project_id, task)
    ctx = ws / "context"
    written: list[str] = []

    _write_context_md_files(ctx, task, task_id, {}, realtime_entries, None, written)

    title = task.get("title") or task.get("audio_name") or "未命名会议"
    agents_parts = [
        f"# 会议上下文：{title}\n",
        f"## 本场信息\n- 日期：{_meeting_date_slug(task)}\n- 任务 ID：{task_id}\n"
        f"- 目录：`{ws.name}/`\n",
        "## 说明\n本工作区由 OpenMeetingScribe 自动生成（预览模式），供浏览和外部 IDE 探索。"
        "context/ 目录为会议只读上下文，output/ 目录为可写产物区。"
        "如需修改会议纪要/决策，请通过软件内的 AI 面板或集成工具完成。\n",
        "## 目录结构\n"
        "- `context/` — 会议只读上下文：transcript.md / summary.md / notes.md / insights.md / history.md / decisions.json，均带 YAML frontmatter（task_id / meeting_title / generated_at / source / 等）\n"
        "- `output/` — 可写产物区\n"
        "- `related.md` — 同项目关联会议的标题/日期/相对路径列表（带 frontmatter）\n"
        "- `AGENTS.md` — 本文件\n",
    ]
    if project_id:
        agents_parts.append(
            "## 跨会议探索\n本工作区只是单场会议。上级 `_INDEX.md` 与 `.oms/meetings.json` 索引了同项目所有会议，"
            "每条含 `task_id` / `title` / `meeting_date` / `workspace_path`。"
            "若需要跨会议上下文，优先在软件里用「在 IDE 中继续」选择「本项目」或「全部会议」，"
            "会直接打开含 `AGENTS.md` 与 `_INDEX.md` 的上层根目录。\n")
    else:
        agents_parts.append(
            "## 跨会议探索\n本工作区为独立会议（未关联知识库）。"
            "上级 `_standalone/` 下可能有其他独立会议，全局索引见 `_preview/.oms/index.json`。\n")
    agents_parts.append(_start_here_meeting(title))
    agents_md = "\n".join(agents_parts)
    written.extend(_write_agent_rules(ws, agents_md,
                                      "本目录为单场会议上下文；跨会议请看上级索引。",
                                      ide_id=ide_id, level="meeting"))

    update_workspace_index(task_id, project_id, task, workspace_name=ws.name)

    # 写 related.md：列出同项目关联会议的标题/日期/相对路径（人类可读，放工作区根与 AGENTS.md 同级）
    related_parts = [
        "# 关联会议\n",
        "## 说明\n本文件列出同项目（知识库）的其他会议工作区，供跨会议探索。"
        "路径为相对路径，从本工作区上级目录出发。\n",
    ]
    if project_id:
        idx = read_meetings_index(project_preview_dir(project_id))
        others = [m for m in idx.get("meetings", []) if m.get("task_id") != task_id]
        if others:
            related_parts.append("## 同项目会议\n")
            for m in others:
                title = m.get("title", "未命名")
                date = m.get("meeting_date", "")
                wp = m.get("workspace_path", f"{m.get('task_id', '')}/")
                related_parts.append(f"- **{title}**（{date}）→ `{wp}`\n")
        else:
            related_parts.append("## 同项目会议\n本项目暂无其他会议。\n")
    else:
        related_parts.append("## 同项目会议\n本工作区为独立会议（未关联知识库），无同项目关联会议。"
            "全局索引见上级 `.oms/index.json`。\n")
    _write_md_with_meta(ws, "related.md", {
        **_base_meta(task_id, task, "related"),
    }, "\n".join(related_parts))
    written.append("related.md")

    logger.info("[CLI引擎] 预览工作区生成 task=%s ws=%s files=%d", task_id, ws, len(written))
    return {"workspace": str(ws), "file_count": len(written)}


def export_project_context(project_id: str, ide_id: str | None = None) -> dict:
    """导出项目级上下文根：AGENTS.md + _INDEX.md + _DECISIONS.md。
    单场目录按需补齐（只生成缺失的），已存在的保留用户/IDE 改动。"""
    if not project_id or not _UUID_RE.match(project_id):
        raise ValueError(f"invalid project_id: {project_id!r}")
    proj_dir = project_preview_dir(project_id)
    _migrate_meeting_dirs(proj_dir, project_id)
    name = _ce()._project_display_name(project_id)
    members = _project_members(project_id)

    for task in members:
        tid = task["task_id"]
        ws = preview_workspace_dir(tid, project_id, task)
        if not (ws / "context" / "summary.md").exists() and not (ws / "context" / "transcript.md").exists():
            export_preview_context(task_id=tid, task=task, project_id=project_id, ide_id=ide_id)

    written: list[str] = []
    _write_scope_indexes(proj_dir, project_id, name, members, written)

    agents_body = (
        f"# 会议知识库：{name}\n\n"
        "## 项目概况\n"
        f"- 会议数：{len(members)}\n"
        f"- 索引：`_INDEX.md`（会议清单） / `_DECISIONS.md`（跨会议决策台账）\n"
        "- 单场上下文：`<会议目录>/context/`\n\n"
        "## 阅读顺序\n"
        "1. 读 `_INDEX.md`，按日期与摘要找相关会议。\n"
        "2. 需要决策时读 `_DECISIONS.md`。\n"
        "3. 再进入对应会议目录读 `context/summary.md`，没有纪要就读 `context/transcript.md`；"
        "需要原话证据时也读它。\n"
        "4. 不要一次性通读所有转写，先索引后定点，控制上下文预算。\n\n"
        "## 工作约束\n"
        "- 本目录是只读会议上下文，`output/` 可写，用于放草稿与产物。\n"
        "- 正式修改纪要/随记/决策必须回到软件内 AI 面板或集成工具，不要直接改任务数据。\n"
        "- 引用结论时标注来源会议与文件，跨会议冲突要显式指出。\n\n"
        + _start_here(f"{name} · 项目级"))
    written.extend(_write_agent_rules(proj_dir, agents_body,
                                      "本目录为项目级会议知识库，含本项目全部会议。",
                                      ide_id=ide_id, level="project"))

    _rebuild_global_index()
    logger.info("[CLI引擎] 项目上下文导出 project=%s ws=%s meetings=%d", project_id, proj_dir, len(members))
    return {"workspace": str(proj_dir), "file_count": len(written),
            "meeting_count": len(members), "scope": "project"}


def export_global_context(ide_id: str | None = None) -> dict:
    """导出全局上下文根：所有项目与独立会议的索引。"""
    _ce().PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    _migrate_all_dirs()

    # 独立会议逐场补齐工作区（只生成缺失的）——否则索引列了全量，
    # 文件树里却只有导出过的寥寥数场，用户看到的"会议数"严重失真
    for tid, task in _store_members(None).items():
        ws = preview_workspace_dir(tid, None, task)
        if (ws / "context" / "summary.md").exists() or (ws / "context" / "transcript.md").exists():
            continue
        try:
            export_preview_context(task_id=tid, task=task, project_id=None, ide_id=ide_id)
        except Exception as e:  # noqa: BLE001 - 单场失败不阻断全局导出
            logger.warning("[CLI引擎] 独立会议上下文补齐失败 %s: %s", tid[:8], e)
    _rebuild_global_index()
    projects_idx: list[dict] = []
    standalone_meetings: list[dict] = []
    try:
        for entry in sorted(_ce().PREVIEW_ROOT.iterdir()):
            if not entry.is_dir() or entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            mi = read_meetings_index(entry)
            if mi:
                projects_idx.append({"dir": entry, "index": mi})
        si = read_meetings_index(_ce().PREVIEW_ROOT / "_standalone")
        standalone_meetings = si.get("meetings", [])
    except Exception:  # noqa: BLE001
        pass

    # 同步补齐各项目根入口，避免“全部会议”里只有光秃秃的目录
    for item in projects_idx:
        pid = item["index"].get("project_id")
        if not pid or not _UUID_RE.match(pid):
            continue  # 非法归属（如被误标 _standalone）不导出，防污染独立区
        try:
            export_project_context(pid, ide_id=ide_id)
        except Exception as e:  # noqa: BLE001 - 单项目失败不阻断全局导出
            logger.warning("[CLI引擎] 项目上下文补齐失败 %s: %s", pid, e)

    # 补齐会重写各项目索引，行数据以导出后的新鲜索引为准
    written: list[str] = []

    # 独立会议区自己的索引/台账：根级与会议级规则都会指向 _DECISIONS.md，standalone 不能空转
    standalone_members = sorted(
        _store_members(None).values(),
        key=lambda t: (t.get("meeting_date") or t.get("created_at") or ""), reverse=True)
    _write_scope_indexes(_ce().PREVIEW_ROOT / "_standalone", "_standalone", "独立会议",
                         standalone_members, written, archive_note=True)
    _write_global_decisions(projects_idx, standalone_members, written)

    proj_rows = ["| 项目 | 会议数 | 目录 |", "| --- | --- | --- |"]
    for item in projects_idx:
        pid = item["index"].get("project_id")
        if not pid or not _UUID_RE.match(pid):
            continue
        mi = read_meetings_index(item["dir"]) or item["index"]
        proj_rows.append(f"| {mi.get('project_name') or _ce()._project_display_name(pid)} "
                         f"| {len(mi.get('meetings', []))} | `{item['dir'].name}/` |")
    if standalone_meetings:
        proj_rows.append(f"| 独立会议 | {len(standalone_meetings)} | `_standalone/` |")
        standalone_rows = ["| 日期 | 会议 | 目录 |", "| --- | --- | --- |"]
        for m in standalone_meetings:
            date = (m.get("meeting_date") or "")[:10]
            title = (m.get("title") or "未命名").replace("|", "/")
            wp = m.get("workspace_path") or ""
            standalone_rows.append(f"| {date or '—'} | {title} | `{wp}` |" if wp
                                   else f"| {date or '—'} | {title}（上下文未生成） | — |")
        index_body = ("# 全部会议索引\n\n> 全部知识库项目与独立会议。先选项目，再进项目内 `_INDEX.md`。\n\n"
                      + "\n".join(proj_rows)
                      + "\n\n## 独立会议\n\n" + "\n".join(standalone_rows) + "\n")
    else:
        index_body = ("# 全部会议索引\n\n> 全部知识库项目与独立会议。先选项目，再进项目内 `_INDEX.md`。\n\n"
                      + "\n".join(proj_rows) + "\n")
    _write_md_with_meta(_ce().PREVIEW_ROOT, "_INDEX.md",
                        {"generated_at": _now_iso(), "source": "global_index",
                         "project_count": len(projects_idx),
                         "standalone_count": len(standalone_meetings)}, index_body)
    written.append("_INDEX.md")

    agents_body = (
        "# 全部会议知识库\n\n"
        "## 结构\n"
        "- 每个项目一个目录：`<项目名>__<短ID>/`，内含 `AGENTS.md`、`_INDEX.md`、`_DECISIONS.md`。\n"
        "- 未关联知识库的会议在 `_standalone/`，同样内含 `_INDEX.md` 与 `_DECISIONS.md`。\n"
        "- 根目录：`_INDEX.md`（全部会议索引）与 `_DECISIONS.md`（跨项目决策台账）。\n"
        "- 机器索引 `.oms/index.json` 含会议级条目（task_id / workspace_path / has_summary），供程序反查。\n\n"
        "## 阅读顺序\n"
        "1. 按用户问题先选定项目。\n"
        "2. 进项目读 `_INDEX.md` 与 `_DECISIONS.md`；跨项目议题看根 `_DECISIONS.md`。\n"
        "3. 再进单场会议目录读 `context/summary.md`，没有纪要就读 `context/transcript.md`。\n"
        "4. 不要通读全部转写。\n\n"
        "## 工作约束\n"
        "- 会议上下文只读，`output/` 可写。\n"
        "- 正式改任务数据必须回到软件内 AI 面板或集成工具。\n"
        "- 跨项目引用时标注项目、会议与文件。\n\n"
        + _start_here("全部会议"))
    written.extend(_write_agent_rules(_ce().PREVIEW_ROOT, agents_body,
                                      "本目录为全部会议知识库，含多个项目。",
                                      ide_id=ide_id))

    logger.info("[CLI引擎] 全局上下文导出 ws=%s projects=%d", _ce().PREVIEW_ROOT, len(projects_idx))
    return {"workspace": str(_ce().PREVIEW_ROOT), "file_count": len(written),
            "project_count": len(projects_idx), "scope": "all"}


def refresh_workspace(task_id: str) -> dict:
    """刷新指定工作区（复用 export_preview_context），返回 {workspace, file_count}。"""
    from core.task_store import tasks
    task = tasks.get(task_id)
    if not task:
        return {"error": "task_not_found"}
    project_id = task.get("project_id")
    return export_preview_context(task_id=task_id, task=task, project_id=project_id)


def import_from_workspace(task_id: str) -> dict:
    """解析工作区 .md frontmatter，返回可导入的 summary/notes 变更（propose 格式）。
    只解析 summary.md 和 notes.md；frontmatter 的 task_id 必须匹配，否则拒收。
    返回 {has_changes, summary: {baseline, proposed}|null, notes: {baseline, proposed}|null, source_mtime, task_id}。
    baseline = 当前定稿口径（user_summary/user_notes 优先），proposed = 工作区 .md body；
    两者不同才标记为变更，走 propose 通道（不直接覆盖，用户在前端接受才落盘）。"""
    from core.chat_context import task_final_summary, task_notes
    from core.task_store import tasks
    task = tasks.get(task_id)
    if not task:
        return {"error": "task_not_found"}
    project_id = task.get("project_id")
    ws = preview_workspace_dir(task_id, project_id, task)
    ctx = ws / "context"
    result: dict = {"has_changes": False, "summary": None, "notes": None,
                    "source_mtime": None, "task_id": task_id}

    baselines = {"summary.md": task_final_summary(task), "notes.md": task_notes(task)}
    for filename in ("summary.md", "notes.md"):
        f = ctx / filename
        if not f.exists():
            continue
        try:
            content = f.read_text(encoding="utf-8")
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    frontmatter = content[3:end].strip()
                    body = content[end + 3:].lstrip("\n")
                    for line in frontmatter.split("\n"):
                        if line.strip().startswith("task_id:"):
                            fm_task_id = line.split(":", 1)[1].strip().strip('"')
                            if fm_task_id and fm_task_id != task_id:
                                return {"error": "task_id_mismatch",
                                        "expected": task_id, "found": fm_task_id}
                    key = filename.replace(".md", "")
                    # notes.md body 含固定头部声明（# 会议随记 + > 随记是...），剥掉取用户实际 notes，
                    # 与 baseline（task_notes）口径一致；外部 IDE 改头部声明不算用户内容变更。
                    if key == "notes" and body.startswith("# 会议随记"):
                        parts = body.split("\n\n", 2)
                        if len(parts) >= 3:
                            body = parts[2]
                    baseline = baselines[filename]
                    if body != baseline:
                        result[key] = {"baseline": baseline, "proposed": body}
                        result["has_changes"] = True
                    mtime = f.stat().st_mtime
                    if result["source_mtime"] is None or mtime > result["source_mtime"]:
                        result["source_mtime"] = mtime
        except Exception as e:
            logger.warning("[CLI引擎] 导入解析失败 %s: %s", filename, e)

    return result
