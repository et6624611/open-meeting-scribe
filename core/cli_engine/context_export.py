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
from pathlib import Path

from core.speakers import normalize_speaker_name

logger = logging.getLogger(__name__)

# 工作区根目录：仓库根下 agent-workspace/，与 data/（含 settings.json）无父子关系（M3）
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT / "agent-workspace"

# 单文件体量上限（字符），超限截断并标注，避免工作区无限膨胀（R4）
_MAX_TRANSCRIPT_CHARS = 40000
_MAX_SUMMARY_CHARS = 8000
_MAX_NOTES_CHARS = 8000      # 随记（用户手写原文）
_MAX_HISTORY_CHARS = 6000       # 对话历史整块字符上限
_MAX_HISTORY_TURNS = 10         # 最多保留前 N 轮对话

# 洞察消息存储目录：与后端同一事实源约定（cwd 相对） / Insight messages dir (same cwd-relative convention as routers)
INSIGHTS_TASKS_DIR = Path("data/tasks")


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
            (ctx / "transcript.md").write_text(header + _render_transcript(pairs),
                                               encoding="utf-8")
            written.append("context/transcript.md")

        summary = task_final_summary(task).strip()
        if summary and "内容过短" not in summary and "无法生成有效纪要" not in summary:
            (ctx / "summary.md").write_text(
                "# 当前会议纪要（用户已编辑时为编辑后版本）\n\n" + summary[:_MAX_SUMMARY_CHARS],
                encoding="utf-8")
            written.append("context/summary.md")

        # 随记：四域中唯一的用户原创区，此前从未导出给 CLI——用户把共识结论写进随记
        # 要求同步决策面板时，工作区里没有 notes，AI 只能报「读不到」（2026-09-30 复盘）
        notes = task_notes(task)
        if notes:
            body = notes[:_MAX_NOTES_CHARS]
            if len(notes) > _MAX_NOTES_CHARS:
                body += '\n…（随记过长已截断）'
            (ctx / 'notes.md').write_text(
                '# 会议随记（用户手写原文，非 AI 产物）\n\n'
                '> 随记是用户本人记录的会议要点，可信度高于转写推断。当用户要求'
                '「按随记更新纪要/决策」时，以随记表述为准；随记属用户原创区，'
                '如需改写只能走 propose_notes 提案通道（用户接受后才落盘）。\n\n' + body, encoding='utf-8')
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
        (ctx / "insights.md").write_text(insights_md, encoding="utf-8")
        written.append("context/insights.md")

    # 对话历史（保障多轮上下文连续性，防止 session resume 失败时上下文割裂）
    # Conversation history: guards multi-turn continuity when session resume fails
    history_md = _render_history(history)
    if history_md:
        (ctx / "history.md").write_text(history_md, encoding="utf-8")
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
