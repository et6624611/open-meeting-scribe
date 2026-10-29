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
import shutil
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

# 目录命名：日期_标题__短ID（机器键保留在后缀，人可读在前缀）
_SLUG_MAX_CHARS = 24
_SHORT_KEY_CHARS = 8
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *[f"COM{i}" for i in range(1, 10)],
    *[f"LPT{i}" for i in range(1, 10)],
}


def _short_key(value: str | None) -> str:
    """取稳定短键：清洗后的前 8 位，用于目录后缀反查。"""
    raw = re.sub(r"[^0-9A-Za-z]", "", str(value or ""))
    return (raw[:_SHORT_KEY_CHARS] or "00000000").lower()


def _sanitize_segment(text: str, fallback: str, max_len: int = _SLUG_MAX_CHARS) -> str:
    """目录段清洗：去非法字符（含全角冒号，规避同步工具兼容问题）、压空白、处理 Windows 保留名与长度。"""
    s = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|：]+', "_", str(text or "").strip())
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("._")
    if not s:
        return fallback
    if s.split(".")[0].upper() in _WIN_RESERVED:
        s = "_" + s
    s = s[:max_len].rstrip("._")
    return s or fallback


def _meeting_date_slug(task: dict | None) -> str:
    """会议日期段：优先 meeting_date，回退 created_at，缺失时用「未定日期」。"""
    for key in ("meeting_date", "created_at"):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str((task or {}).get(key) or ""))
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return "未定日期"


# 音频/视频常见扩展名：用原始文件名兜底标题时剥掉，避免目录名出现 "rec.wav"
_MEDIA_EXT_RE = re.compile(
    r"\.(mp3|wav|m4a|aac|flac|ogg|opus|webm|wma|mp4|mov|mkv)$", re.IGNORECASE)


def _meeting_dir_name(task: dict | None, task_id: str) -> str:
    """会议目录名：日期_标题__短ID。标题缺失用录音文件名兜底（剥扩展名）。"""
    title = (task or {}).get("title")
    if not title:
        title = _MEDIA_EXT_RE.sub("", str((task or {}).get("audio_name") or "").strip())
    return (f"{_meeting_date_slug(task)}_"
            f"{_sanitize_segment(title or '', '未命名会议')}__{_short_key(task_id)}")


def _project_display_name(project_id: str | None) -> str:
    """项目显示名：读知识库名称，缺失时用「知识库」。"""
    if not project_id:
        return "独立会议"
    try:
        from core import projects as projects_store
        project = projects_store.get_project(project_id)
        if project and project.get("name"):
            return str(project["name"])
    except Exception:  # noqa: BLE001 - 名称读取失败不阻断导出
        pass
    return "知识库"


def _find_meeting_dir(proj_dir: Path, task_id: str) -> Path | None:
    """按短键后缀查找会议目录；兼容旧版直接以 task_id 命名的目录。"""
    suffix = f"__{_short_key(task_id)}"
    if proj_dir.is_dir():
        for entry in sorted(proj_dir.iterdir()):
            if entry.is_dir() and entry.name.endswith(suffix):
                return entry
        legacy = proj_dir / task_id
        if legacy.is_dir():
            return legacy
    return None


def _project_dir_name(project_id: str) -> str:
    """项目目录名：<项目名>__<短ID>（project_preview_dir 与孤儿反查共用，避免两处拼名漂移）。"""
    return (f"{_sanitize_segment(_project_display_name(project_id), '知识库')}"
            f"__{_short_key(project_id)}")


def project_preview_dir(project_id: str | None) -> Path:
    """项目级工作区根：<项目名>__<短ID>；独立会议归入 _standalone。
    旧版 <project_id> 目录首次访问时惰性迁移。"""
    PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    if not project_id or project_id == "_standalone":
        root = PREVIEW_ROOT / "_standalone"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    target = PREVIEW_ROOT / _project_dir_name(project_id)
    legacy = PREVIEW_ROOT / project_id
    if legacy.is_dir():
        if not target.exists():
            try:
                legacy.rename(target)
            except OSError as e:  # noqa: BLE001 - 迁移失败保留旧目录，功能不中断
                logger.warning("[CLI引擎] 项目目录迁移失败 %s → %s: %s", legacy, target, e)
                return legacy.resolve()
        else:
            # 双目录并存：把旧目录里缺失的子项并入新目录后清理
            _merge_dir_into(legacy, target)
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _merge_dir_into(src: Path, dst: Path) -> None:
    """同任务双目录并存收口：把 src 里 dst 缺失的子项并过去，再删掉 src。
    同名子目录递归并入；只搬缺失项，绝不覆盖——用户在任一侧的改动都保留。"""
    if not src.is_dir() or not dst.is_dir():
        return
    for child in src.iterdir():
        dest = dst / child.name
        if child.is_dir() and dest.is_dir():
            _merge_dir_into(child, dest)
            continue
        if dest.exists():
            continue
        try:
            child.rename(dest)
        except OSError:
            pass
    try:
        src.rmdir()  # 只删得空的目录，搬不动的东西留下不动
    except OSError as e:  # noqa: BLE001
        logger.warning("[CLI引擎] 目录合并残留 %s → %s: %s", src, dst, e)

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
            "- 决策推进（如「这些条已确认/定为结论」）：先 get_meeting_decisions 取节点 id 与状态字典，"
            "再逐条调 update_decision_node（status 只取字典里的 id）；已有节点不得用 inject_items 重复追加。\n"
            "- 随记（notes）是用户原创区：改写必须调用 propose_notes 产出待确认提案，由用户在前端点「接受」后才落盘；"
            "未经接受，严禁声称已写入或修改随记。也不要把随记内容当纪要写（纪要走 propose_summary）。\n"
            "- 改写前先读基线（洞察板读工作区 `context/boards/<board_id>.html` 与 `context/boards/index.md`，"
            "落盘时带上读到的 expected_revision；纪要覆盖前先从工作区读回原文）。\n"
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


def cleanup_workspace(engine_id: str, task_id: str | None) -> None:
    """删除指定工作区（面板会话删除时联动清理，方案 D5 修订要求）。"""
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

def preview_workspace_dir(task_id: str, project_id: str | None = None,
                          task: dict | None = None) -> Path:
    """返回 _preview 下的会议工作区路径：
    有 project_id → _preview/<项目名>__<短ID>/<日期>_<标题>__<短ID>/
    无 project_id → _preview/_standalone/<日期>_<标题>__<短ID>/
    旧版 UUID 目录在传入 task 时惰性改名；确保 context/ 与 output/ 存在。"""
    proj_dir = project_preview_dir(project_id)
    target_name = _meeting_dir_name(task, task_id) if task else None
    existing = _find_meeting_dir(proj_dir, task_id)

    # 标题/日期变化时跟随改名；旧版 <task_id> 目录也在这一步迁移
    if existing is not None and target_name and existing.name != target_name:
        target = proj_dir / target_name
        if not target.exists():
            try:
                existing.rename(target)
                existing = target
            except OSError as e:  # noqa: BLE001 - 改名失败沿用旧目录，功能不中断
                logger.warning("[CLI引擎] 会议目录改名失败 %s → %s: %s", existing, target, e)

    ws = existing or (proj_dir / (target_name or task_id))
    (ws / "context").mkdir(parents=True, exist_ok=True)
    (ws / "output").mkdir(parents=True, exist_ok=True)
    return ws.resolve()


def _write_context_md_files(ctx: Path, task: dict, task_id: str | None,
                             speaker_map: dict, realtime_entries: list[dict] | None,
                             history: list[dict] | None,
                             written: list[str]) -> None:
    """写 context/ 下的 .md 和 decisions.json 文件（export_context 与 export_preview_context 共用）。
    Write context/ .md and decisions.json files (shared by export_context and export_preview_context)."""
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

        decisions = task.get("decisions") or []
        if decisions:
            (ctx / "decisions.json").write_text(
                json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append("context/decisions.json")

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

    # 洞察板 HTML 基线（与正式会话工作区同口径，两个出口保持一致）
    _write_board_files(ctx, str(task_id or ""), written)

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


# 机器索引统一收进 .oms/，不进用户视野；旧位置读取后自动迁移
_OMS_DIR = ".oms"

# IDE → 原生规则文件；只给实际打开的 IDE 生成一套，其余不落盘
_IDE_RULE_FILES = {
    "cursor": ".cursor/rules/meeting-context.mdc",
    "vscode": ".github/copilot-instructions.md",
    "windsurf": ".windsurf/rules/meeting-context.md",
    "trae": ".trae/rules/meeting-context.md",
    "trae-cn": ".trae/rules/meeting-context.md",
    "claude-code": "CLAUDE.md",
}


def _rule_pointer(scope_note: str, level: str = "global") -> str:
    """给非 AGENTS.md 体系的 IDE 留一行入口，避免各平台规则文件重复长文。
    按作用层级指向真实存在的索引/台账文件——指引落空的文件名比没有指引更糟。"""
    if level == "meeting":
        pointers = ("开始前先读 `AGENTS.md`；跨会议见上级 `_INDEX.md`，"
                    "决策与决策见上级 `_DECISIONS.md`（如有）。")
    elif level == "project":
        pointers = ("开始前先读 `AGENTS.md`（工作约束与阅读顺序）与 `_INDEX.md`（会议索引）；"
                    "决策与决策见本目录 `_DECISIONS.md`。")
    else:
        pointers = ("开始前先读 `AGENTS.md`（工作约束与阅读顺序）与 `_INDEX.md`（会议索引）；"
                    "决策与决策见根 `_DECISIONS.md` 与各项目内 `_DECISIONS.md`。")
    return (
        "# 会议知识库\n\n"
        "本目录由 OpenMeetingScribe 生成，会议上下文已就绪。\n"
        f"{scope_note}\n"
        f"{pointers}不要通读全部转写，先索引后定点。\n")


def attach_ide_rule(root: Path, ide_id: str | None, scope_note: str = "",
                    level: str = "global") -> list[str]:
    """按实际打开的 IDE 写一份原生规则文件，并清掉其他 IDE 的旧文件与空目录。
    未识别 IDE 时只留 AGENTS.md，避免多套规则在文件树里制造噪音。"""
    rel = _IDE_RULE_FILES.get(str(ide_id or "").lower(), "")
    keep = {rel} if rel else set()
    body = _rule_pointer(scope_note, level=level)
    if rel.endswith(".mdc"):
        body = "---\ndescription: OpenMeetingScribe 会议上下文\nalwaysApply: true\n---\n\n" + body
    if rel:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    for stale in set(_IDE_RULE_FILES.values()) - keep:
        stale_path = root / stale
        if stale_path.is_file():
            try:
                stale_path.unlink()
            except OSError:
                pass
    # rules 子目录删空后再收父目录；目录里有用户自建文件时 rmdir 自然失败，不受影响
    for d in (root / ".cursor" / "rules", root / ".cursor",
              root / ".trae" / "rules", root / ".trae",
              root / ".windsurf" / "rules", root / ".windsurf",
              root / ".github"):
        try:
            d.rmdir()  # 只删空目录
        except OSError:
            pass
    return [rel] if rel else []


def _write_agent_rules(root: Path, agents_body: str, scope_note: str,
                       ide_id: str | None = None, level: str = "global") -> list[str]:
    """写 AGENTS.md + 当前 IDE 的原生规则入口。"""
    (root / "AGENTS.md").write_text(agents_body, encoding="utf-8")
    # 旧版 START_HERE.md 已并入 AGENTS.md，清掉残留
    stale_start = root / "START_HERE.md"
    if stale_start.is_file():
        try:
            stale_start.unlink()
        except OSError:
            pass
    # 页面预生成不认识 IDE，保留已有规则文件；只有真正打开 IDE 时才切换
    if not ide_id:
        return ["AGENTS.md"]
    return ["AGENTS.md", *attach_ide_rule(root, ide_id, scope_note, level=level)]


def _meetings_index_path(proj_dir: Path) -> Path:
    return proj_dir / _OMS_DIR / "meetings.json"


def _global_index_path() -> Path:
    return PREVIEW_ROOT / _OMS_DIR / "index.json"


def read_meetings_index(proj_dir: Path) -> dict:
    """读项目会议索引：优先 .oms/meetings.json，兼容旧 _meetings.json。"""
    for path in (_meetings_index_path(proj_dir), proj_dir / "_meetings.json"):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    return {}


def write_meetings_index(proj_dir: Path, data: dict) -> None:
    path = _meetings_index_path(proj_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    legacy = proj_dir / "_meetings.json"
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass


def read_global_index() -> dict:
    """读全局索引：优先 .oms/index.json，兼容旧 _index.json。"""
    for path in (_global_index_path(), PREVIEW_ROOT / "_index.json"):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    return {}


def _write_global_index(data: dict) -> None:
    path = _global_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    legacy = PREVIEW_ROOT / "_index.json"
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass


def _start_here(scope_label: str) -> str:
    """任务模板：并入 AGENTS.md，避免根目录多一个入口文件。"""
    return (
        f"## 推荐任务 · {scope_label}\n\n"
        "以下是现成任务，可直接把提示词交给 IDE 里的智能体。\n\n"
        "### 1. 项目进展周报\n"
        "提示词：读 `_INDEX.md` 与各会议 `context/summary.md`（没有纪要的会议改读其 "
        "`context/transcript.md`），按「本周结论 / 进展 / "
        "风险 / 下周动作」输出一份周报，每条结论标注来源会议。\n\n"
        "### 2. 跨会议决策梳理\n"
        "提示词：读 `_DECISIONS.md` 与相关会议，找出仍未闭环的决策，列出「议题 / 当前状态 / "
        "卡点 / 建议下一步」，不要把已完成的再列一遍。\n\n"
        "### 3. 决策与风险盘点\n"
        "提示词：汇总所有未完成决策，按负责人分组，标注逾期风险与来源会议；"
        "只读，不要直接改任务数据。\n\n"
        "### 说明\n正式改纪要、随记、决策请在软件内通过 AI 面板或集成工具完成；"
        "本目录的 `output/` 可写，用于放你产出的稿子。\n")


def _start_here_meeting(title: str) -> str:
    """单场会议的任务模板。"""
    return (
        f"## 推荐任务 · {title}\n\n"
        "先用 `context/summary.md` 建立全局（没有 summary.md 就直接读 `transcript.md`），"
        "需要原话证据时再查 `transcript.md`。\n\n"
        "### 1. 提炼行动项\n"
        "提示词：从纪要与转写中提炼行动项，按负责人分组，标注原文依据与截止时间；"
        "只输出建议，不要直接改任务数据。\n\n"
        "### 2. 按章节优化纪要\n"
        "提示词：保留事实与结论，压缩重复表述，补齐每章的「结论 / 依据 / 待确认」，"
        "把改写稿放到 `output/summary-draft.md`。\n\n"
        "### 3. 对外同步稿\n"
        "提示词：基于本场会议生成一份对外同步稿，只保留已达成一致的结论，"
        "去掉内部讨论与未定事项，标注仍需确认的问题。\n\n"
        "### 说明\n正式落盘请回到软件内 AI 面板或集成工具；`output/` 可写。\n")


def _summary_line(task: dict, limit: int = 60) -> str:
    """取纪要首行作索引摘要；无纪要返回空串。"""
    try:
        from core.chat_context import task_final_summary
        text = task_final_summary(task).strip()
    except Exception:  # noqa: BLE001
        text = ""
    for line in text.splitlines():
        line = re.sub(r"^[#>\-\*\s]+", "", line).strip()
        if line and "内容过短" not in line and "无法生成有效纪要" not in line:
            return line[:limit] + ("…" if len(line) > limit else "")
    return ""


def _write_board_files(ctx: Path, task_id: str | None, written: list[str]) -> None:
    """把洞察板 HTML 原样拷进工作区 / Copy board HTML into context/boards/.

    【基线而非重建】拷的是消毒后实际展示的字节（board_html_load 的落盘版本），
    不是 CLI 提交的原文：应用侧清洗（on*/危险 scheme/禁用标签）会改字节，
    所以下一轮共创必须看到与用户所看一致的那一版，否则每轮都是从零重写。

    走**文件**而非 prompt 注入：工作区文件模式对 token 预算宽松（insights.md 全量不截断
    即为既有证据），板不进 brief，由 CLI 按需 Read——边际成本只在真打开时发生。
    超上限只留 index.md 并标 truncated=true，不允许静默截断。
    已删除的板不得残留：每次先清空 boards/ 再写。
    """
    if not task_id:
        return
    try:  # 局部 import：避免 core.cli_engine 模块级依赖洞察板
        from core.insight_board import BOARD_HTML_CAP, board_html_load, boards_manifest
    except Exception:  # noqa: BLE001 - 洞察板模块缺席不阻断其余上下文导出
        return
    boards_dir = ctx / "boards"
    try:
        if boards_dir.is_dir():
            for stale in boards_dir.iterdir():
                if stale.is_file():
                    stale.unlink()
    except OSError:
        pass
    try:
        manifest = boards_manifest(task_id)
    except Exception:  # noqa: BLE001
        return
    boards = manifest.get("boards") or []
    lines = [
        "# 洞察板清单（基线索引）",
        "",
        "> 本目录下的 `.html` 与 `data/tasks/` 展示版本逐字节一致：那就是用户当前看到的板。",
        "> 修订前先 Read 对应文件拿到基线，落盘时把读到的 revision 原样填到",
        "> revise_insight_board(board_id, html, expected_revision)；收到 `stale_baseline`",
        "> 说明基线已过期，重读后再改，不要硬写覆盖。",
        "> 版式（含 `<style>` / 硬编码色 / `<script>`）完全由你负责；",
        "> 图片与字体资源必须 data URI 内联，相对路径在渲染出口不保证可解析。",
        "> 建板权属于用户：需要新板请先向用户提议（create_insight_board），不要直接写新 board_id。",
        "",
        "| board_id | 标题 | revision | 字节数 | 更新时间 | 已拷贝 | truncated |",
        "|---|---|---|---|---|---|---|",
    ]
    for b in boards:
        bid = str(b.get("board_id") or "")
        title = str(b.get("title") or "").replace("|", "\\|").replace("\n", " ")
        rev = int(b.get("revision") or 0)
        upd = b.get("updated_at") or "-"
        artifact = board_html_load(task_id, bid) or {}
        html = artifact.get("html") or ""
        n_bytes = len(html.encode("utf-8")) if html else 0
        copied, truncated = False, False
        if html and n_bytes <= BOARD_HTML_CAP:
            try:
                boards_dir.mkdir(parents=True, exist_ok=True)
                (boards_dir / f"{bid}.html").write_text(html, encoding="utf-8")
                copied = True
                written.append(f"context/boards/{bid}.html")
            except OSError as e:
                logger.warning("[CLI引擎] 洞察板拷贝失败 task=%s board=%s: %s", task_id, bid, e)
        elif html:
            truncated = True
        lines.append(f"| {bid} | {title} | {rev} | {n_bytes} | {upd} | "
                     f"{'是' if copied else '否'} | {'true' if truncated else 'false'} |")
    if not boards:
        lines.append("| （尚无板） | | | | | | |")
    try:
        (ctx / "boards").mkdir(parents=True, exist_ok=True)
        (ctx / "boards" / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append("context/boards/index.md")
    except OSError as e:
        logger.warning("[CLI引擎] 洞察板清单写入失败 task=%s: %s", task_id, e)


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


def _slim_meetings(meetings: list[dict]) -> list[dict]:
    """机器索引的会议级瘦身条目：够反查定位即可，不带正文类数据。"""
    return [{"task_id": m.get("task_id"), "title": m.get("title"),
             "meeting_date": m.get("meeting_date"),
             "workspace_path": m.get("workspace_path"),
             "has_summary": m.get("has_summary")} for m in meetings]


def _rebuild_global_index() -> None:
    """重建全局索引：从各项目会议索引反查 project_id，不再依赖目录名。
    含会议级条目——单场会议 AGENTS.md 让 agent 查它当全局索引，查不到就是废索引。"""
    PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    projects: list[dict] = []
    standalone_meetings: list[dict] = []
    try:
        for entry in sorted(PREVIEW_ROOT.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.name == "_standalone":
                # 按索引计数：目录数会把 未识别会议 归档目录也算进去
                standalone_meetings = _slim_meetings(
                    read_meetings_index(entry).get("meetings", []))
                continue
            if entry.name.startswith("_"):
                continue
            mi = read_meetings_index(entry)
            if not mi:
                continue
            pid = mi.get("project_id") or ""
            if not _UUID_RE.match(pid):
                continue  # 归属非法（如被误标 _standalone）不入全局列表
            projects.append({
                "project_id": pid,
                "project_name": mi.get("project_name") or _project_display_name(pid),
                "meeting_count": len(mi.get("meetings", [])),
                "meetings": _slim_meetings(mi.get("meetings", [])),
                "path": entry.name,
                "last_updated": _now_iso(),
            })
    except Exception:  # noqa: BLE001
        pass
    _write_global_index({
        "version": 1,
        "generated_at": _now_iso(),
        "projects": projects,
        "standalone_count": len(standalone_meetings),
        "standalone_meetings": standalone_meetings,
    })


def update_workspace_index(task_id: str, project_id: str | None, task: dict,
                           workspace_name: str | None = None) -> None:
    """增量更新项目级 .oms/meetings.json，并重建全局 .oms/index.json。"""
    proj_dir = project_preview_dir(project_id)
    index: dict = read_meetings_index(proj_dir)
    if not index:
        index = {"project_id": project_id or "_standalone",
                 "project_name": _project_display_name(project_id),
                 "version": 1, "generated_at": _now_iso(), "meetings": []}
    index["project_id"] = project_id or "_standalone"
    index["project_name"] = _project_display_name(project_id)

    ws = (proj_dir / workspace_name) if workspace_name else _find_meeting_dir(proj_dir, task_id)
    ctx_dir = (ws / "context") if ws else (proj_dir / task_id / "context")
    meetings = [m for m in index.get("meetings", []) if m.get("task_id") != task_id]
    meetings.append({
        "task_id": task_id,
        "title": task.get("title") or task.get("audio_name") or "未命名",
        "meeting_date": task.get("meeting_date") or "",
        "workspace_path": f"{ws.name}/" if ws else f"{task_id}/",
        "has_transcript": (ctx_dir / "transcript.md").exists(),
        "has_summary": (ctx_dir / "summary.md").exists(),
        "has_notes": (ctx_dir / "notes.md").exists(),
        "has_insights": (ctx_dir / "insights.md").exists(),
        "decision_count": len(task.get("decisions") or []),
        "speaker_count": _speaker_count(task),
        "last_updated": _now_iso(),
    })
    index["meetings"] = meetings
    index["generated_at"] = _now_iso()
    write_meetings_index(proj_dir, index)
    _rebuild_global_index()


def _project_members(project_id: str) -> list[dict]:
    """按日期倒序取项目内会议（任务库为空时先从磁盘加载）。"""
    _ensure_tasks_loaded()
    from app.store import tasks
    members = [t for t in tasks.values()
               if t.get("project_id") == project_id and t.get("task_id")]
    members.sort(key=lambda t: (t.get("meeting_date") or t.get("created_at") or ""), reverse=True)
    return members


def _decision_rows(members: list[dict], names: dict,
                   project_label: str | None = None) -> list[str]:
    """决策行生成；project_label 提供时输出全局六列（项目 | 日期 | 会议 | 节点 | 状态 | 负责人），
    否则五列（无项目列，供单作用域台账用）。"""
    from core.decision_flow import status_of
    out: list[str] = []
    for task in members:
        date = (task.get("meeting_date") or task.get("created_at") or "")[:10]
        title = (task.get("title") or task.get("audio_name") or "未命名").replace("|", "/")
        for decision in (task.get("decisions") or []):
            if not isinstance(decision, dict):
                continue
            text = (decision.get("title") or decision.get("text") or "").replace("|", "/").strip()
            if not text:
                continue
            sid = status_of(decision)
            state = names.get(sid, sid)
            assignee = (decision.get("assignee") or "未分配").replace("|", "/")
            if project_label:
                out.append(f"| {project_label} | {date} | {title} | {text} | {state} | {assignee} |")
            else:
                out.append(f"| {date} | {title} | {text} | {state} | {assignee} |")
    return out


def _decision_lines(members: list[dict]) -> list[str]:
    """跨会议决策台账：会议 / 节点 / 状态 / 负责人。"""
    from core.decision_status import load_statuses
    try:
        names = {s["id"]: s.get("name") or s["id"] for s in load_statuses()}
    except Exception:  # noqa: BLE001
        names = {}
    return (["| 日期 | 会议 | 决策 | 状态 | 负责人 |", "| --- | --- | --- | --- | --- |"]
            + _decision_rows(members, names))


def _write_global_decisions(projects_idx: list[dict], standalone_members: list[dict],
                            written: list[str]) -> None:
    """根级决策台账：聚合全部项目与独立会议（六列带项目归属）。
    根级规则文案「决策与决策见 _DECISIONS.md」必须有真实落点，不能悬空。"""
    from core.decision_status import load_statuses
    try:
        names = {s["id"]: s.get("name") or s["id"] for s in load_statuses()}
    except Exception:  # noqa: BLE001
        names = {}
    rows = ["| 项目 | 日期 | 会议 | 决策 | 状态 | 负责人 |",
            "| --- | --- | --- | --- | --- | --- |"]
    for item in projects_idx:
        pid = item["index"].get("project_id")
        if not pid or not _UUID_RE.match(pid):
            continue
        label = item["index"].get("project_name") or _project_display_name(pid)
        rows.extend(_decision_rows(_project_members(pid), names, label))
    if standalone_members:
        rows.extend(_decision_rows(standalone_members, names, "独立会议"))
    body = ("# 跨项目决策台账\n\n"
            "> 聚合全部知识库项目与独立会议的决策节点；项目内明细见各项目目录 `_DECISIONS.md`。\n\n"
            + "\n".join(rows) + "\n")
    _write_md_with_meta(PREVIEW_ROOT, "_DECISIONS.md",
                        {"generated_at": _now_iso(), "source": "decisions"},
                        body)
    written.append("_DECISIONS.md")


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _ensure_tasks_loaded() -> None:
    """任务库为空时从磁盘加载一次。索引/迁移以任务库为全量基准，
    服务进程启动时已加载，CLI/测试进程按需补载。"""
    from app.store import tasks as task_store
    if task_store:
        return
    try:
        from app.task_store import load_tasks_from_disk
        load_tasks_from_disk()
    except Exception as e:  # noqa: BLE001 - 加载失败按空库处理，不阻断导出
        logger.warning("[CLI引擎] 任务库加载失败: %s", e)


def _store_members(project_id: str | None) -> dict[str, dict]:
    """某范围（项目/独立会议）的全量任务，task_id → task。"""
    from app.store import tasks as task_store
    _ensure_tasks_loaded()
    if project_id:
        items = [t for t in task_store.values()
                 if t.get("project_id") == project_id and t.get("task_id")]
    else:
        items = [t for t in task_store.values()
                 if not t.get("project_id") and t.get("task_id")]
    return {t["task_id"]: t for t in items}


def _migrate_meeting_dirs(proj_dir: Path, project_id: str | None = None) -> None:
    """把遗留 <task_id> 目录批量改成可读名，并按任务库重建完整索引。
    此前索引只记录导出过的会议，历史会议既不被改名也不计数——这里以任务库为准全量对齐。
    不在任务库中的 UUID 目录视为孤儿，归档为 未识别会议__<短ID>。"""
    by_id = _store_members(project_id)

    # 1) 磁盘遗留 UUID 目录 → 可读名 / 孤儿归档
    if proj_dir.is_dir():
        for entry in sorted(proj_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            if not _UUID_RE.match(entry.name):
                continue
            task = by_id.get(entry.name)
            if task is not None:
                target = proj_dir / _meeting_dir_name(task, entry.name)
            else:
                # 与本范围对不上：旧版可能把项目会议错放进独立区，搬回所属项目；
                # 彻底无主才归档为 未识别会议__<短ID>
                from app.store import tasks as task_store
                owner = task_store.get(entry.name)
                if owner and owner.get("project_id"):
                    target = (project_preview_dir(owner["project_id"])
                              / _meeting_dir_name(owner, entry.name))
                else:
                    target = proj_dir / f"未识别会议__{entry.name[:8].lower()}"
            if target.exists():
                # 同任务已有正式工作区：旧目录是残留副本，缺失子项并入后清掉，防 ID 撞车脏副本
                _merge_dir_into(entry, target)
                continue
            try:
                entry.rename(target)
            except OSError as e:  # noqa: BLE001 - 单目录失败不阻断整体迁移
                logger.warning("[CLI引擎] 历史目录迁移失败 %s: %s", entry.name, e)

        # 1.5) 撞车归档清理：未识别会议__<key> 的 key 已命中任务库且真实工作区存在
        # → 当年是误归档的脏副本，缺失子项并入真实工作区后收掉（评估 2026-10-26 P0-4）
        from app.store import tasks as task_store
        by_key: dict[str, dict] = {}
        for tid, t in task_store.items():
            by_key.setdefault(_short_key(tid), t)
        for entry in sorted(proj_dir.iterdir()):
            if not entry.is_dir() or not entry.name.startswith("未识别会议__"):
                continue
            owner = by_key.get(entry.name.split("__", 1)[1])
            if owner is None:
                continue  # 真无主，保留归档待人工辨认
            pid = owner.get("project_id")
            pd = (PREVIEW_ROOT / _project_dir_name(pid) if pid and _UUID_RE.match(str(pid))
                  else PREVIEW_ROOT / "_standalone")
            real = (_find_meeting_dir(pd, owner["task_id"])
                    if pd.is_dir() else None)
            if real is not None:
                _merge_dir_into(entry, real)
                logger.info("[CLI引擎] 撞车归档已并入真实工作区 %s → %s", entry.name, real.name)

    # 2) 以任务库为准重建索引（历史会议只有导出过才入索引，是数量偏少的根因）
    old = {m.get("task_id"): m
           for m in read_meetings_index(proj_dir).get("meetings", [])}
    meetings = []
    for tid, task in by_id.items():
        ws = _find_meeting_dir(proj_dir, tid)
        ctx = (ws / "context") if ws else None
        meetings.append({
            "task_id": tid,
            "title": task.get("title") or task.get("audio_name") or "未命名",
            "meeting_date": task.get("meeting_date") or task.get("created_at") or "",
            "workspace_path": f"{ws.name}/" if ws else "",
            "has_transcript": bool(ctx and (ctx / "transcript.md").exists()),
            "has_summary": bool(ctx and (ctx / "summary.md").exists()),
            "has_notes": bool(ctx and (ctx / "notes.md").exists()),
            "has_insights": bool(ctx and (ctx / "insights.md").exists()),
            "decision_count": len(task.get("decisions") or []),
            "speaker_count": _speaker_count(task),
            "last_updated": old.get(tid, {}).get("last_updated") or _now_iso(),
        })
    meetings.sort(key=lambda m: m.get("meeting_date") or "", reverse=True)
    proj_id = project_id or "_standalone"
    write_meetings_index(proj_dir, {
        "project_id": proj_id,
        "project_name": "独立会议" if proj_id == "_standalone" else _project_display_name(proj_id),
        "version": 1,
        "generated_at": _now_iso(),
        "meetings": meetings,
    })


def _infer_project_id_from_dir(proj_dir: Path) -> str | None:
    """按目录内会议反查归属项目（索引 project_id 被污染时的自愈路径）。"""
    from app.store import tasks as task_store
    owners: set[str] = set()
    for m in read_meetings_index(proj_dir).get("meetings", []):
        t = task_store.get(m.get("task_id") or "")
        pid = (t or {}).get("project_id")
        if pid and _UUID_RE.match(pid):
            owners.add(pid)
    return owners.pop() if len(owners) == 1 else None


def _speaker_count(task: dict | None) -> int:
    """发言人数：dialogue 内实名去重（空名不计）。
    任务库 task.speaker_count 是导入时的对话条数，口径不对，索引一律现算。"""
    names = (normalize_speaker_name(d.get("speaker_name"))
             for d in (task or {}).get("dialogue") or [])
    return len({n for n in names if n})


def _sweep_junk_files() -> None:
    """清扫 Finder/同步工具留下的噪声文件（.DS_Store 等），保持工作区纯净。"""
    if not PREVIEW_ROOT.is_dir():
        return
    for path in PREVIEW_ROOT.rglob(".DS_Store"):
        try:
            path.unlink()
        except OSError:
            pass


def _migrate_all_dirs() -> None:
    """打开全部会议前批量迁移：所有项目与独立会议的旧目录一次性改名。
    目录归属只认任务库与合法 project_id，绝不给非独立目录盖 standalone 章——
    项目目录缺索引时若误标，会把独立会议灌进项目索引并连锁清空独立区。"""
    _ensure_tasks_loaded()
    _sweep_junk_files()
    if not PREVIEW_ROOT.is_dir():
        return
    for entry in sorted(PREVIEW_ROOT.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name == "_standalone":
            _migrate_meeting_dirs(entry, None)
            continue
        if entry.name.startswith("_"):
            continue
        pid = read_meetings_index(entry).get("project_id")
        if pid and not _UUID_RE.match(pid):
            pid = _infer_project_id_from_dir(entry)  # 被污染的归属，反查自愈
        if not pid and _UUID_RE.match(entry.name):
            pid = entry.name  # 旧版项目目录以 task_id 命名
        if not pid:
            pid = _infer_project_id_from_dir(entry)
        if not pid:
            logger.warning("[CLI引擎] 跳过无法识别归属的目录 %s", entry.name)
            continue
        _migrate_meeting_dirs(project_preview_dir(pid), pid)


def _write_scope_indexes(scope_dir: Path, scope_id: str, scope_name: str,
                         members: list[dict], written: list[str],
                         archive_note: bool = False) -> None:
    """写作用域级 `_INDEX.md`（会议清单）与 `_DECISIONS.md`（跨会议决策台账）。
    项目级与独立会议区共用——「决策与决策见 _DECISIONS.md」的指引必须在每个作用域有落点。"""
    rows = ["| 日期 | 会议 | 一句话结论 | 决策 | 目录 |", "| --- | --- | --- | --- | --- |"]
    for task in members:
        ws = _find_meeting_dir(scope_dir, task["task_id"])
        if not ws:
            continue
        date = (task.get("meeting_date") or task.get("created_at") or "")[:10]
        title = (task.get("title") or task.get("audio_name") or "未命名").replace("|", "/")
        has_summary = (ws / "context" / "summary.md").exists()
        summary = _summary_line(task).replace("|", "/")
        decision_count = len(task.get("decisions") or [])
        rows.append(f"| {date} | {title} | {summary or ('—' if has_summary else '（无纪要）')} "
                    f"| {decision_count} | `{ws.name}/` |")
    index_body = (f"# 会议索引：{scope_name}\n\n> 共 {len(members)} 场，按日期倒序。"
                  "先在这里定位，再进入目录读 context/。\n\n" + "\n".join(rows) + "\n")
    if archive_note:
        index_body += ("\n> 注：磁盘上的 `未识别会议__*` 目录是无主遗留归档，不属于任务库，"
                       "不列入本索引。\n")
    _write_md_with_meta(scope_dir, "_INDEX.md",
                        {"project_id": scope_id, "project_name": scope_name,
                         "generated_at": _now_iso(), "source": "index",
                         "meeting_count": len(members)}, index_body)
    written.append("_INDEX.md")

    decision_body = (f"# 跨会议决策台账：{scope_name}\n\n"
                     "> 只列本范围内会议产生的决策节点，状态取软件内决策字典。\n\n"
                     + "\n".join(_decision_lines(members)) + "\n")
    _write_md_with_meta(scope_dir, "_DECISIONS.md",
                        {"project_id": scope_id, "generated_at": _now_iso(), "source": "decisions"},
                        decision_body)
    written.append("_DECISIONS.md")


def export_project_context(project_id: str, ide_id: str | None = None) -> dict:
    """导出项目级上下文根：AGENTS.md + _INDEX.md + _DECISIONS.md。
    单场目录按需补齐（只生成缺失的），已存在的保留用户/IDE 改动。"""
    if not project_id or not _UUID_RE.match(project_id):
        raise ValueError(f"invalid project_id: {project_id!r}")
    proj_dir = project_preview_dir(project_id)
    _migrate_meeting_dirs(proj_dir, project_id)
    name = _project_display_name(project_id)
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
    PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
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
        for entry in sorted(PREVIEW_ROOT.iterdir()):
            if not entry.is_dir() or entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            mi = read_meetings_index(entry)
            if mi:
                projects_idx.append({"dir": entry, "index": mi})
        si = read_meetings_index(PREVIEW_ROOT / "_standalone")
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
    _write_scope_indexes(PREVIEW_ROOT / "_standalone", "_standalone", "独立会议",
                         standalone_members, written, archive_note=True)
    _write_global_decisions(projects_idx, standalone_members, written)

    proj_rows = ["| 项目 | 会议数 | 目录 |", "| --- | --- | --- |"]
    for item in projects_idx:
        pid = item["index"].get("project_id")
        if not pid or not _UUID_RE.match(pid):
            continue
        mi = read_meetings_index(item["dir"]) or item["index"]
        proj_rows.append(f"| {mi.get('project_name') or _project_display_name(pid)} "
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
    _write_md_with_meta(PREVIEW_ROOT, "_INDEX.md",
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
    written.extend(_write_agent_rules(PREVIEW_ROOT, agents_body,
                                      "本目录为全部会议知识库，含多个项目。",
                                      ide_id=ide_id))

    logger.info("[CLI引擎] 全局上下文导出 ws=%s projects=%d", PREVIEW_ROOT, len(projects_idx))
    return {"workspace": str(PREVIEW_ROOT), "file_count": len(written),
            "project_count": len(projects_idx), "scope": "all"}


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
