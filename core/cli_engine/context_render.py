"""
core/cli_engine/context_render.py — 上下文模板拼装与渲染（从 context_export.py 拆出）
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from core.speakers import normalize_speaker_name

logger = logging.getLogger(__name__)

from .context_paths import (
    _IDE_RULE_FILES,
    _MAX_HISTORY_CHARS,
    _MAX_HISTORY_TURNS,
    _MAX_NOTES_CHARS,
    _MAX_SUMMARY_CHARS,
    _MAX_TRANSCRIPT_CHARS,
)


def _ce():
    import core.cli_engine.context_export as ce
    return ce


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
        from core import realtime_store  # 同进程内存只读，与 chat 内置链路同一事实源
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
    f = _ce().INSIGHTS_TASKS_DIR / f"{task_id}.insights.json"
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
