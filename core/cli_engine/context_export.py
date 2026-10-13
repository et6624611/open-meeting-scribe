"""
core/cli_engine/context_export.py — 会议上下文序列化到 CLI 工作区
Serialize meeting context into the CLI agent workspace (files, not one giant prompt).

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
更新 / Updated: 2026-09-30
版本 / Version: 1.2.0

职责 / Responsibilities:
  - 把四维会议上下文落成工作区文件，供 CLI 用自身检索能力按需读取（方案 §3.1）
  - 工作区物理隔离于 data/（SPIKE M3 / §3.10）：agent-workspace/<engine_id>/<task_id>/
  - 严禁把 settings.json 或其字段复制进工作区（§3.7-4 红线）

原则：大文件走工作区、小关键信息进 prompt；项目知识库用 --add-dir 挂载而非复制。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from core.speakers import normalize_speaker_name

logger = logging.getLogger(__name__)


def _compute_workspace_root() -> Path:
    """计算工作区根目录，优先用 app.store.BASE_DIR（打包后落 exe 同级，持久），
    回退仓库根（开发模式等价）。PyInstaller _MEIPASS 临时目录重启丢失，必须避开。"""
    try:
        from app.store import BASE_DIR
        return BASE_DIR / "agent-workspace"
    except Exception:
        return Path(__file__).resolve().parents[2] / "agent-workspace"


# 工作区根目录：与 app.store.BASE_DIR 同源（打包后落 exe 同级，持久） /
# Workspace root: same source as app.store.BASE_DIR (persists next to exe in PyInstaller)
WORKSPACE_ROOT = _compute_workspace_root()
# 预生成工作区根目录（资源管理视图浏览的命名空间，与 AI 对话工作区隔离） /
# Preview workspace root (namespace for resource explorer; isolated from AI chat workspaces)
PREVIEW_ROOT = WORKSPACE_ROOT / "_preview"

# 单文件体量上限（字符），超限截断并标注，避免工作区无限膨胀（R4）
_MAX_TRANSCRIPT_CHARS = 40000
_MAX_SUMMARY_CHARS = 8000
_MAX_NOTES_CHARS = 8000      # 随记（用户手写原文）
_MAX_HISTORY_CHARS = 6000       # 对话历史整块字符上限
_MAX_HISTORY_TURNS = 10         # 最多保留前 N 轮对话

# 洞察消息存储目录：与后端同一事实源约定（cwd 相对） / Insight messages dir (same cwd-relative convention as routers)
INSIGHTS_TASKS_DIR = Path("data/tasks")


# ============================================================
# 元数据 frontmatter 辅助 / Metadata frontmatter helpers
# ============================================================

def _now_iso() -> str:
    """当前时间 ISO 8601 带本地时区。 / Current time in ISO 8601 with local timezone."""
    return datetime.now().astimezone().isoformat()


def _format_yaml_frontmatter(meta: dict) -> str:
    """手写 YAML frontmatter（避免 pyyaml 依赖）。 / Hand-write YAML frontmatter (no pyyaml dependency)."""
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            joined = ", ".join(str(v) for v in value)
            lines.append(f"{key}: [{joined}]")
        else:
            safe = str(value).replace('"', '\\"')
            lines.append(f'{key}: "{safe}"')
    lines.append("---")
    return "\n".join(lines)


def _write_md_with_meta(ctx_dir: Path, filename: str, meta: dict, body: str) -> None:
    """写带 YAML frontmatter 的 Markdown 文件。 / Write a Markdown file with YAML frontmatter.

    meta 字段：task_id/meeting_title/generated_at/source/version + 各文件特定字段。
    body 是正文（含标题行，函数在 frontmatter 与 body 之间加空行）。
    """
    frontmatter = _format_yaml_frontmatter(meta)
    content = f"{frontmatter}\n\n{body}"
    (ctx_dir / filename).write_text(content, encoding="utf-8")


def _base_meta(task_id: str | None, task: dict | None, source: str) -> dict:
    """构造通用 frontmatter 字段。 / Build common frontmatter fields."""
    title = ""
    if task:
        title = task.get("title") or task.get("audio_name") or ""
    return {
        "task_id": task_id or "",
        "meeting_title": title,
        "generated_at": _now_iso(),
        "source": source,
        "version": 1,
    }


def workspace_dir(engine_id: str, task_id: str | None) -> Path:
    """返回并确保工作区目录存在；task_id 缺省用 general 命名空间。"""
    tid = task_id or "general"
    ws = (WORKSPACE_ROOT / engine_id / tid).resolve()
    (ws / "context").mkdir(parents=True, exist_ok=True)
    (ws / "output").mkdir(parents=True, exist_ok=True)
    return ws


def _flatten_dialogue(task: dict, speaker_map: dict) -> list[tuple[str, str]]:
    """将 task.dialogue 展开为 (说话人名, 文本) 序列。"""
    pairs: list[tuple[str, str]] = []
    for item in task.get("dialogue") or []:
        name = normalize_speaker_name(item.get("speaker_name")) or "未识别发言人"
        sents = item.get("sentences") or []
        if sents:
            for s in sents:
                text = (s.get("text") or "").strip()
                if text:
                    pairs.append((name, text))
        else:
            text = (item.get("text") or "").strip()
            if text:
                pairs.append((name, text))
    return pairs


def _realtime_pairs(entries: list[dict] | None, task: dict,
                    speaker_map: dict, task_id: str | None) -> list[tuple[str, str]]:
    """录音进行中 dialogue 尚未落盘，用实时定稿句渲染转写（会中问答复盘 2026-09-29）。
    来源优先级：前端快照 > 后端全量缓冲 > 最近缓冲；说话人名用内存映射按 id 解析。"""
    entries = entries or []
    if not entries and task_id:
        from app import realtime_store  # 同进程内存只读，与 chat 内置链路同一事实源
        entries = (realtime_store.realtime_full_transcripts.get(task_id)
                   or realtime_store.realtime_transcript_buffers.get(task_id) or [])
    if not entries:
        return []
    # task.speaker_mapping（id→名）优先，回退全局 speaker_map
    local_map: dict = {}
    for sid, name in (task.get("speaker_mapping") or {}).items():
        try:
            local_map[int(sid)] = name
        except (ValueError, TypeError):
            pass
    pairs: list[tuple[str, str]] = []
    for entry in entries:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        name = ((entry.get("speaker_name") or "").strip()
                or normalize_speaker_name(local_map.get(entry.get("speaker_id")))
                or normalize_speaker_name(speaker_map.get(entry.get("speaker_id")))
                or "未识别发言人")
        pairs.append((name, text))
    return pairs


def _render_transcript(pairs: list[tuple[str, str]]) -> str:
    """将 (说话人名, 文本) 序列渲染为 Markdown。"""
    out = "\n".join(f"{name}：{text}" for name, text in pairs)
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
    # 过滤 deferred：与 chat 侧 build_insights_context_block 同口径，仅注入用户可见的有效卡
    valid = [m for m in msgs if (m.get("title") or "").strip() and not m.get("deferred")]
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
        # 备查注释随卡导出：与 chat 侧 build_insights_context_block 同口径（三层信息写作契约）
        note = (m.get("note") or "").strip()
        if note:
            block += f"\n> 注：{note}\n"
        diagram = (m.get("diagram") or "").strip()
        if diagram:
            block += f"\n```mermaid\n{diagram}\n```\n"
        blocks.append(block)
    parts.extend(blocks)
    return "\n---\n".join(parts)


def _render_history(history: list[dict] | None) -> str:
    """将前端传来的对话历史序列化为 Markdown，供 CLI 即使 session resume 失败仍可读取上文。
    Serialize conversation history to Markdown so the CLI retains prior turns even when
    session resume (-r) fails or was never attempted."""
    if not history:
        return ""
    # 过滤当前轮的空 assistant 占位和空内容消息，只保留有效历史
    turns = [m for m in history if (m.get("content") or "").strip()]
    # 排除最后一条 user 消息（它会被写入 brief 的用户问题段，避免重复）
    if turns and turns[-1].get("role") == "user":
        turns = turns[:-1]
    if not turns:
        return ""
    # 取最近 N 轮
    turns = turns[-_MAX_HISTORY_TURNS:]
    parts = ["# 前序对话（同一会话的早期轮次，供延续上下文）\n"]
    total_chars = 0
    for t in turns:
        role_label = "用户" if t.get("role") == "user" else "助手"
        content = t["content"].strip()
        # 单条消息截断：助手消息可能非常长，限制为 1500 字符
        if len(content) > 1500:
            content = content[:1500] + "\n…（已截断）"
        segment = f"## {role_label}\n{content}\n"
        if total_chars + len(segment) > _MAX_HISTORY_CHARS:
            parts.append("\n…（更早历史已省略）")
            break
        parts.append(segment)
        total_chars += len(segment)
    return "\n---\n".join(parts)


def _build_permission_section(auth_tier: str | None) -> str:
    """
    按本轮授权档生成 AGENTS.md 权限段（模式即权限，PROPOSAL-AGENT-REWRITE-CHANNEL §5.2）。

    置于角色段之后并声明"以本段为准"：覆写存量角色 AGENT.md（含用户自建区 _roles/my/）
    的"没有执行权"绝对禁令——不改用户资产文件，运行时分段解耦。
    问答模式（内置单流）不经本函数：其只读语义由内置 prompt 与无工具通道天然保障。
    """
    if auth_tier in ("workspace_write", "full_task"):
        return (
            "## 本轮权限段（最高优先级，以本段为准；与上文角色描述冲突时按本段执行）\n"
            "当前为智能体可写档：你拥有协助写回权。\n"
            "- 用户要求修改/重新生成随记、纪要、决策、洞察板时，必须调用对应的集成工具（MCP）完成落盘；"
            "仅在对话里描述计划、读取基线后就收尾，不算完成。\n"
            "- 纪要（summary）改写例外：必须调用 propose_summary 产出待确认提案，由用户在前端接受后才落盘；"
            "不得直接调用 update_summary 覆盖纪要。\n"
            "- 决策推进（如「这些条已确认/定为结论」）：先 get_meeting_todos 取节点 id 与状态字典，"
            "再逐条调 update_decision_node（status 只取字典里的 id）；已有节点不得用 inject_items 重复追加。\n"
            "- 随记（notes）是用户原创区：改写必须调用 propose_notes 产出待确认提案，由用户在前端点「接受」后才落盘；"
            "未经接受，严禁声称已写入或修改随记。也不要把随记内容当纪要写（纪要走 propose_summary）。\n"
            "- 改写前先读基线（如 revise_insight_board 不带 html 即读当前板；纪要覆盖前先从工作区读回原文）。\n"
            "- 落盘成功后，回复中必须明确告知用户改了哪个域、对应版本/条数；"
            "工具回执中 restorable=false 表示本轮未能建立撤销快照，需如实告知用户改动不可一键回退。\n"
            "- 直写边界：文件编辑工具只允许写 output/ 产物区；任务数据（纪要/随记/决策/洞察板）"
            "必须经集成工具落盘，严禁绕过工具直接改工作区外数据文件。\n")
    return (
        "## 本轮权限段（最高优先级，以本段为准；与上文角色描述冲突时按本段执行）\n"
        "当前为只读档：你没有执行权，不能修改、删除、写入任何数据。\n"
        "- 若用户要求改写某域，说明需切换到智能体（可写）模式后执行，不要声称已完成任何修改。\n"
        "- 禁止使用\"已修正/已更新/已删除/已重新生成\"等表述描述未发生的写入。\n")


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

        todos = task.get("todos") or []
        if todos:
            (ctx / "todos.json").write_text(
                json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append("context/todos.json")

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
        from app.chat_attachment_store import load_bytes  # 局部 import：避免 core→app 模块级依赖

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
        "任何对会议纪要/待办的正式修改必须通过提供的集成工具（MCP）完成，不得直接改工作区外文件。\n")
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
            "【强制执行】洞察板生成三步：",
            "① revise_insight_board() 空参 → ② web_search ×最多2次 → ③ revise_insight_board(html=<完整HTML>) 落盘",
            "缺第③步就是任务失败——后端没有 board.html，用户洞察 tab 是空的。",
            "不要在搜索后直接回复用户。必须看到工具回执 revision≥1 再回复。",
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


# ============================================================
# 预览工作区（资源管理视图） / Preview workspace (resource explorer)
# ============================================================

def preview_workspace_dir(task_id: str, project_id: str | None = None) -> Path:
    """返回 _preview 下的工作区路径，按 project_id 路由：
    有 project_id → _preview/<project_id>/<task_id>/
    无 project_id → _preview/_standalone/<task_id>/
    确保 context/ 和 output/ 子目录存在。"""
    PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    if project_id:
        ws = (PREVIEW_ROOT / project_id / task_id).resolve()
    else:
        ws = (PREVIEW_ROOT / "_standalone" / task_id).resolve()
    (ws / "context").mkdir(parents=True, exist_ok=True)
    (ws / "output").mkdir(parents=True, exist_ok=True)
    return ws


def _write_context_md_files(ctx: Path, task: dict, task_id: str | None,
                             speaker_map: dict, realtime_entries: list[dict] | None,
                             history: list[dict] | None,
                             written: list[str]) -> None:
    """写 context/ 下的 .md 和 todos.json 文件（export_context 与 export_preview_context 共用）。
    Write context/ .md and todos.json files (shared by export_context and export_preview_context)."""
    from core.chat_context import task_final_summary, task_notes

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

        todos = task.get("todos") or []
        if todos:
            (ctx / "todos.json").write_text(
                json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append("context/todos.json")

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


def export_preview_context(*, task_id: str, task: dict,
                           project_id: str | None = None,
                           realtime_entries: list[dict] | None = None) -> dict:
    """预生成工作区（无 user_message/attachments/history），返回 {workspace, file_count}。
    复用 _write_context_md_files 的渲染逻辑，写带 frontmatter 的 .md 文件。"""
    ws = preview_workspace_dir(task_id, project_id)
    ctx = ws / "context"
    written: list[str] = []

    _write_context_md_files(ctx, task, task_id, {}, realtime_entries, None, written)

    # 精简 AGENTS.md（预览工作区，无对话权限段，含跨会议探索指引） /
    # Minimal AGENTS.md (preview workspace; no permission section; includes cross-meeting guidance)
    agents_parts = [
        "# 会议助手预览工作区\n",
        "## 说明\n本工作区由 OpenMeetingScribe 自动生成（预览模式），供浏览和外部 IDE 探索。"
        "context/ 目录为会议只读上下文，output/ 目录为可写产物区。"
        "如需修改会议纪要/待办，请通过软件内的 AI 面板或集成工具完成。\n",
        "## 目录结构\n"
        "- `context/` — 会议只读上下文：transcript.md / summary.md / notes.md / insights.md / history.md / todos.json，均带 YAML frontmatter（task_id / meeting_title / generated_at / source / 等）\n"
        "- `output/` — 可写产物区\n"
        "- `AGENTS.md` — 本文件\n",
    ]
    if project_id:
        agents_parts.append(
            "## 跨会议探索\n本工作区位于项目级目录 `_preview/<project_id>/<task_id>/` 下。"
            "上级目录 `_preview/<project_id>/_meetings.json` 索引了同项目所有会议，每条含 "
            "`task_id` / `title` / `meeting_date` / `workspace_path` 字段。"
            "可逐个进入子目录读取 context/ 下的 .md 进行跨会议探索。\n"
            "更上级 `_preview/_index.json` 索引了所有项目（含独立会议），可发现其他项目。\n")
    else:
        agents_parts.append(
            "## 跨会议探索\n本工作区为独立会议（未关联知识库），位于 `_preview/_standalone/<task_id>/`。"
            "上级 `_preview/_standalone/` 下可能有其他独立会议工作区；"
            "全局索引 `_preview/_index.json` 含所有项目（含独立会议计数），可发现其他会议工作区。\n")
    (ws / "AGENTS.md").write_text("\n".join(agents_parts), encoding="utf-8")
    written.append("AGENTS.md")

    update_workspace_index(task_id, project_id, task)

    logger.info("[CLI引擎] 预览工作区生成 task=%s ws=%s files=%d", task_id, ws, len(written))
    return {"workspace": str(ws), "file_count": len(written)}


def update_workspace_index(task_id: str, project_id: str | None, task: dict) -> None:
    """增量更新 _index.json（全局）和 _meetings.json（项目级）。"""
    # 更新项目级索引 / Update project-level index
    if project_id:
        proj_dir = PREVIEW_ROOT / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        index_file = proj_dir / "_meetings.json"
        index: dict = {}
        if index_file.exists():
            try:
                index = json.loads(index_file.read_text(encoding="utf-8"))
            except Exception:
                index = {}
        if not index:
            index = {"project_id": project_id, "project_name": "", "version": 1,
                     "generated_at": _now_iso(), "meetings": []}
        meetings = index.get("meetings", [])
        meetings = [m for m in meetings if m.get("task_id") != task_id]
        ctx_dir = proj_dir / task_id / "context"
        meetings.append({
            "task_id": task_id,
            "title": task.get("title") or task.get("audio_name") or "未命名",
            "meeting_date": task.get("meeting_date") or "",
            "has_transcript": (ctx_dir / "transcript.md").exists(),
            "has_summary": (ctx_dir / "summary.md").exists(),
            "has_notes": (ctx_dir / "notes.md").exists(),
            "has_insights": (ctx_dir / "insights.md").exists(),
            "todo_count": len(task.get("todos") or []),
            "speaker_count": len(set(
                normalize_speaker_name(d.get("speaker_name")) or ""
                for d in (task.get("dialogue") or []))),
            "last_updated": _now_iso(),
        })
        index["meetings"] = meetings
        index["generated_at"] = _now_iso()
        index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    # 更新全局索引 / Update global index
    global_index_file = PREVIEW_ROOT / "_index.json"
    PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    global_index: dict = {}
    if global_index_file.exists():
        try:
            global_index = json.loads(global_index_file.read_text(encoding="utf-8"))
        except Exception:
            global_index = {}
    if not global_index:
        global_index = {"version": 1, "generated_at": _now_iso(), "projects": [], "standalone_count": 0}

    projects = []
    standalone_count = 0
    try:
        for entry in sorted(PREVIEW_ROOT.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                if entry.name == "_standalone" and entry.is_dir():
                    standalone_count = sum(1 for sub in entry.iterdir() if sub.is_dir())
                continue
            meetings_file = entry / "_meetings.json"
            proj_name = ""
            meeting_count = 0
            if meetings_file.exists():
                try:
                    mi = json.loads(meetings_file.read_text(encoding="utf-8"))
                    proj_name = mi.get("project_name", "")
                    meeting_count = len(mi.get("meetings", []))
                except Exception:
                    pass
            projects.append({
                "project_id": entry.name,
                "project_name": proj_name,
                "meeting_count": meeting_count,
                "last_updated": _now_iso(),
            })
    except Exception:
        pass
    global_index["projects"] = projects
    global_index["standalone_count"] = standalone_count
    global_index["generated_at"] = _now_iso()
    global_index_file.write_text(
        json.dumps(global_index, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_workspace(task_id: str) -> dict:
    """刷新指定工作区（复用 export_preview_context），返回 {workspace, file_count}。"""
    from app.store import tasks
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
    from app.store import tasks
    from core.chat_context import task_final_summary, task_notes
    task = tasks.get(task_id)
    if not task:
        return {"error": "task_not_found"}
    project_id = task.get("project_id")
    ws = preview_workspace_dir(task_id, project_id)
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
