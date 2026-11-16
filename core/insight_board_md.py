"""
core/insight_board_md.py — 洞察板 Markdown 产物读写与内容底线

取代 insight_board_html.py：洞察板从自包含 HTML 改为**单份 Markdown 文件**
（每场会议一份，不再多板、不再会中实时）。

职责：
- parse_front_matter / dump_front_matter — YAML front-matter 轻量解析
- board_md_load / board_md_save — 主入口，含 revision 乐观锁
- sanitize_board_md — Markdown 安全清洗（禁 HTML 注入、禁危险链接）
- detect_recap_floor / detect_text_wall — 迁到 md 形态下的复述/文字墙防线
- migrate_legacy_html_to_md — 存量 .board.html / .boards.json 合并为 insight.md

文件契约 / File contract
─────────────────────────
文件路径：data/tasks/{task_id}.insight.md  （每场会议固定一份，不再多板 manifest）

front-matter 字段：
  board_id   : 固定 "main"
  title      : 洞察板标题
  revision   : 整数，每次落盘 +1
  updated_at : ms 时间戳
  migrated_from : 迁移标记（内部用，迁移完成后可删）

正文 GFM + 自定义：
  - 每个节前置 HTML 注释锚点 <!-- section-id: s1 --> <!-- section-title: 审核阻塞 -->
    （GFM 里不可见但 AI 能写、后端 regex 能抓、前端渲染前能扫）
  - 主视觉：mermaid 必须写在 ```mermaid fence 里（不再 <pre>）
  - 转写跳转锚点保留 <a data-seek-ms="毫秒"> （前端接线不变）
  - 安全：禁原始 HTML（保留 <a data-seek-ms> 白名单 + 锚点注释）、禁 javascript:
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

BOARD_MD_CAP = 300_000  # 单份 insight.md 字节上限

# ── Front-matter 轻量解析 ──
_FM_OPEN = re.compile(r"^---\s*$", re.MULTILINE)
_SECTION_ANCHOR_RE = re.compile(
    r"<!--\s*section-id:\s*([\w-]{1,64})\s*"
    r"(?:section-title:\s*([^\-]{1,120}?)\s*)?-->",
    re.IGNORECASE,
)


def parse_front_matter(text: str) -> tuple[dict, str]:
    """返回 (meta_dict, body_without_fence)。无 fence 时 meta={} body=原文。"""
    if not text.startswith("---"):
        return {}, text
    # 找第二个 ---
    idx = text.find("\n---", 3)
    if idx < 0:
        return {}, text
    fm_raw = text[3:idx].strip()
    body = text[idx + 4:].lstrip("\n")
    meta: dict = {}
    # 极简 YAML 解析（只支持 "key: value" 一行一条，足够我们用的四个字段）
    for line in fm_raw.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        # 去引号
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        # 类型猜测
        if v.lstrip("-").isdigit():
            meta[k] = int(v)
        elif v.lower() in ("true", "false"):
            meta[k] = v.lower() == "true"
        else:
            meta[k] = v
    return meta, body


def dump_front_matter(meta: dict, body: str) -> str:
    """front-matter 序列化。只写入标准字段（不 dump 空值）。"""
    keys_order = ("board_id", "title", "revision", "updated_at")
    lines = ["---"]
    for k in keys_order:
        v = meta.get(k)
        if v is None or v == "":
            continue
        if isinstance(v, int):
            lines.append(f"{k}: {v}")
        else:
            # 含冒号/引号时加双引号
            s = str(v)
            if ":" in s or '"' in s or s.startswith(" ") or s.endswith(" "):
                esc = s.replace('"', '\\"')
                lines.append(f'{k}: "{esc}"')
            else:
                lines.append(f"{k}: {s}")
    lines.append("---")
    # body 前保证一个空行
    body = body.lstrip("\n")
    return "\n".join(lines) + "\n\n" + (body if body else "")


# ── 合法 task_id ──
def _valid_task_id(task_id: str) -> bool:
    return bool(task_id) and "/" not in task_id and "\\" not in task_id and ".." not in task_id


def _board_md_path(task_id: str) -> Path:
    """单份板固定路径：{task_id}.insight.md"""
    import core.insight_board as ib
    return ib.BOARD_TASKS_DIR / f"{task_id}.insight.md"


# ── 读取 ──
def board_md_load(task_id: str) -> dict | None:
    """读完整板（meta + body）。不存在返回 None。"""
    if not _valid_task_id(task_id):
        return None
    path = _board_md_path(task_id)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.warning("[洞察板] insight.md 读取失败 task=%s", task_id)
        return None
    meta, body = parse_front_matter(raw)
    return {
        "markdown": body,
        "meta": meta,
        "revision": int(meta.get("revision") or 0),
        "updated_at": meta.get("updated_at"),
        "board_id": meta.get("board_id") or "main",
        "title": meta.get("title") or "主看板",
    }


def board_md_meta(task_id: str) -> dict:
    """轻量版本探测（不读 body）。用于轮询比对。"""
    if not _valid_task_id(task_id):
        return {"revision": 0, "updated_at": None, "exists": False, "board_id": "main"}
    path = _board_md_path(task_id)
    if not path.exists():
        return {"revision": 0, "updated_at": None, "exists": False, "board_id": "main"}
    # 只读 head 部分
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return {"revision": 0, "updated_at": None, "exists": False, "board_id": "main"}
    meta, _ = parse_front_matter(head)
    return {
        "revision": int(meta.get("revision") or 0),
        "updated_at": meta.get("updated_at"),
        "exists": True,
        "board_id": meta.get("board_id") or "main",
        "title": meta.get("title") or "主看板",
    }


# ── 写入 ──
def board_md_save(
    task_id: str,
    markdown: str,
    *,
    content_floor: bool = True,
    expected_revision: int | str | None = None,
) -> dict:
    """覆盖写完整板，含乐观锁 + 安全清洗 + 内容底线。"""
    if not _valid_task_id(task_id):
        return {"ok": False, "error": "invalid_task_id"}
    if not isinstance(markdown, str) or not markdown.strip():
        return {"ok": False, "error": "empty_markdown"}
    if len(markdown) > BOARD_MD_CAP:
        return {"ok": False, "error": f"markdown_too_large(>{BOARD_MD_CAP} chars)"}

    prev = board_md_load(task_id)
    prev_revision = int((prev or {}).get("revision") or 0)

    # 乐观锁
    if expected_revision is not None and not isinstance(expected_revision, bool):
        try:
            exp = int(expected_revision)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_expected_revision"}
        if exp != prev_revision:
            logger.info("[洞察板] 基线过期 task=%s expected=%s current=%s",
                        task_id, exp, prev_revision)
            return {"ok": False, "error": "stale_baseline",
                    "current_revision": prev_revision,
                    "hint": "你读到的基线已不是最新版，重新读回后再改"}

    cleaned, removed = sanitize_board_md(markdown)
    if not cleaned.strip():
        return {"ok": False, "error": "markdown_empty_after_sanitize", "removed": removed}

    if content_floor:
        recap_reasons = detect_recap_floor(cleaned)
        if recap_reasons:
            logger.info("[洞察板·md] 复述底线拒收 task=%s: %s", task_id, recap_reasons)
            return {"ok": False, "error": "board_is_recap", "reasons": recap_reasons,
                    "guidance": _RECAP_GUIDANCE_MD, "removed": removed}
        total_sec, visual_sec = detect_text_wall(cleaned)
        if total_sec and visual_sec < (1 if total_sec == 1 else total_sec - 1):
            logger.info("[洞察板·md] 文字墙拒收 task=%s sections=%d visuals=%d",
                        task_id, total_sec, visual_sec)
            return {"ok": False, "error": "board_is_text_wall",
                    "reasons": [f"{total_sec} 个节中仅 {visual_sec} 个含主视觉（mermaid fence 等）"],
                    "guidance": _TEXT_WALL_GUIDANCE_MD, "removed": removed}

    revision = prev_revision + 1
    now_ms = int(time.time() * 1000)

    # 保留旧 meta 里的 title（如果 AI 没写 front-matter，我们从旧 meta 继承）
    base_title = (prev or {}).get("title") or "主看板"
    new_meta, _ = parse_front_matter(cleaned)
    # 从正文的第一个 h1 也能猜 title
    if not new_meta.get("title"):
        h1_m = re.search(r"^#\s+(.+)$", cleaned, re.MULTILINE)
        if h1_m:
            base_title = h1_m.group(1).strip()[:60]

    meta = {
        "board_id": "main",
        "title": new_meta.get("title") or base_title,
        "revision": revision,
        "updated_at": now_ms,
    }
    body_clean = _strip_front_matter(cleaned)
    out = dump_front_matter(meta, body_clean)

    from core.fs_atomic import atomic_write_text
    atomic_write_text(_board_md_path(task_id), out)
    logger.info("[洞察板·md] Markdown 落盘 task=%s rev=%s chars=%d removed=%s",
                task_id, revision, len(out), removed or "-")
    return {"ok": True, "revision": revision, "removed": removed,
            "board_id": "main", "updated_at": now_ms}


def _strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        idx = text.find("\n---", 3)
        if idx > 0:
            return text[idx + 4:].lstrip("\n")
    return text


# ── Markdown 安全清洗 ──
# 允许 HTML 注释锚点 <!-- section-id: xxx section-title: yyy -->
# 允许 <a data-seek-ms="毫秒"> 跳转锚点
# 允许 <br>（GFM 常见）
# 禁其他所有原始 HTML（防脚本注入）
_ALLOWED_HTML_TAGS = ("br",)
_ALLOWED_HTML_ATTRS = {
    "a": ("data-seek-ms",),
}


def sanitize_board_md(md: str) -> tuple[str, list[str]]:
    """Markdown 安全清洗，返回 (cleaned, removed_list)。

    - 保留 <!-- section-id... --> 注释锚点、<a data-seek-ms="...">、<br>
    - 剥掉所有其他 HTML 标签（<script>/<iframe>/<div>/<span>/<style>/<pre>/on* 等）
    - javascript: / data:text/html 链接 → #
    """
    removed: list[str] = []
    out = md or ""

    # 1. 先保护白名单（注释锚点、data-seek 锚点）——用占位符替换
    class _Placeholder:
        def __init__(self):
            self._map: list[str] = []

        def save(self, s: str) -> str:
            self._map.append(s)
            return f"\x00PH{len(self._map) - 1}\x00"

        def restore(self, m: re.Match) -> str:
            idx = int(m.group(1))
            return self._map[idx]

    ph = _Placeholder()
    # HTML 注释（仅保护合法的 section 锚点，含带连字符的 section-title 字段名）
    out = _SECTION_ANCHOR_RE.sub(lambda m: ph.save(m.group(0)), out)
    # data-seek 锚点
    SEEK_A = re.compile(r'<a\s+([^>]*?data-seek-ms\s*=\s*"[^"]*"[^>]*)>(.*?)</a>',
                        re.IGNORECASE | re.DOTALL)
    out = SEEK_A.sub(lambda m: ph.save(m.group(0)), out)
    # <br>
    out = re.sub(r"<br\s*/?>", lambda m: ph.save(m.group(0)), out, flags=re.IGNORECASE)

    # 2. 剥所有剩下来的 HTML 标签
    html_tag = re.compile(r"<[^>]+>")
    before = len(out)
    out = html_tag.sub("", out)
    removed.append(f"html-tags-stripped×{(before - len(out))}")

    # 3. 还原占位符
    out = re.sub(r"\x00PH(\d+)\x00", ph.restore, out)

    # 4. 危险链接清洗：Markdown 与带引号的 HTML 属性分开处理，避免 URL 中括号残留
    n_url = 0
    url_patterns = (
        (r"(\[[^\]]*\]\()\s*(?:javascript:[^)]*|data:text/html[^)]*)(\))", r"\1#\2"),
        (r"(\s(?:href|src)\s*=\s*[\"'])\s*(?:javascript:[^\"']*|data:text/html[^\"']*)([\"'])", r"\1#\2"),
    )
    for pattern, replacement in url_patterns:
        out, count = re.subn(pattern, replacement, out, flags=re.IGNORECASE)
        n_url += count
    if n_url:
        removed.append(f"dangerous-url×{n_url}")

    # 5. 内联事件 on*（HTML 标签已被剥，但锚点里可能还剩）
    out, n_on = re.subn(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "",
                       out, flags=re.IGNORECASE)
    if n_on:
        removed.append(f"on*×{n_on}")

    # 6. 清理可能因剥标签产生的连续空行
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip(), removed if removed != ["html-tags-stripped×0"] else []


# ── 复述底线 ──
_RECAP_TITLE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"决策流|待确认决策|决策清单|决议事项"), "决策清单（决策中心已承载）"),
    (re.compile(r"议题归类|议题梳理|议题清单"), "议题归类（纪要章节已承载）"),
    (re.compile(r"待办追踪|待办事项|行动项清单|任务分工|人员分工"), "待办/分工清单（决策中心已承载）"),
    (re.compile(r"会议全景|会议纪要|会议总结|会议摘要"), "会议全景/纪要复述"),
    (re.compile(r"风险清单|风险梳理|未决事项"), "风险罗列式节（困境必须紧跟解法）"),
)
_SOLUTION_HINT = re.compile(r"解法|解决方案|对策|破局|锦囊|最优方案")
_DC_CODE_RE = re.compile(r"DC[-－\s]*\d", re.IGNORECASE)
_TOPIC_CODE_RE = re.compile(r"议题\s*[0-9０-９]")
_SPEAKER_REF_RE = re.compile(r"说话人\s*[0-9０-９]|Speaker\s*[0-9]", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"依据[：:][^。；\n]{0,40}(?:说话人|Speaker)", re.IGNORECASE)
_DEADLINE_RE = re.compile(r"截止|deadline|\d{1,2}\s*月\s*\d{1,2}\s*日", re.IGNORECASE)
_RECAP_STAT_LABELS = ("待确认决策", "议题归类", "决策事项", "待办事项")


def _extract_sections(md: str) -> tuple[list[str], list[str]]:
    """按 <!-- section-id 注释或 h2/h3 标题切节。返回 (bodies, titles)。"""
    # 先按注释锚点切
    bodies: list[str] = []
    titles: list[str] = []
    ancs = list(_SECTION_ANCHOR_RE.finditer(md))
    if ancs:
        for i, m in enumerate(ancs):
            start = m.end()
            end = ancs[i + 1].start() if i + 1 < len(ancs) else len(md)
            sec_body = md[start:end].strip()
            bodies.append(sec_body)
            t = m.group(2) or ""
            if not t:
                # 从 body 第一个 h2/h3 猜
                h = re.search(r"^(#{1,4})\s+(.+)$", sec_body, re.MULTILINE)
                if h:
                    t = h.group(2).strip()
            titles.append(t)
    else:
        # 按 h2 切
        for m in re.finditer(r"^(##\s+.+)$", md, re.MULTILINE):
            pass
        splits = re.split(r"(?=^##\s+)", md, flags=re.MULTILINE)
        for s in splits:
            s = s.strip()
            if not s:
                continue
            bodies.append(s)
            h = re.match(r"^##\s+(.+)$", s, re.MULTILINE)
            titles.append(h.group(1).strip() if h else "")
    return bodies, titles


def detect_recap_floor(md: str) -> list[str]:
    score = 0
    reasons: list[str] = []
    bodies, titles = _extract_sections(md)
    text = re.sub(r"\s+", " ", md or "")

    bad_titles: list[str] = []
    for t in titles:
        if not t or _SOLUTION_HINT.search(t):
            continue
        for pat, label in _RECAP_TITLE_PATTERNS:
            if pat.search(t):
                bad_titles.append(f"「{t[:20]}」={label}")
                break
    if bad_titles:
        score += 1
        reasons.append("复述型节标题 " + "；".join(dict.fromkeys(bad_titles))[:300])

    if len(_DC_CODE_RE.findall(text)) >= 2 or len(_TOPIC_CODE_RE.findall(text)) >= 2:
        score += 1
        reasons.append("DC/议题编号罗列（决策与纪要已有各自编号体系）")

    stat_hits = [w for w in _RECAP_STAT_LABELS if w in text]
    if len(stat_hits) >= 2:
        score += 1
        reasons.append("决策/议题/待办统计徽标：" + "、".join(stat_hits))

    speaker_hits = len(_SPEAKER_REF_RE.findall(text))
    evidence_hits = len(_EVIDENCE_RE.findall(text))
    if speaker_hits + evidence_hits >= 4:
        score += 1
        reasons.append(
            f"密集记录发言人（说话人/Speaker 引用 {speaker_hits} 处、依据句 {evidence_hits} 处）"
            "——板不应记录谁说了什么")

    if speaker_hits >= 3 and _DEADLINE_RE.search(text):
        score += 1
        reasons.append("按人派活+截止日期的决策分工表")

    return reasons if score >= 2 else []


# ── 文字墙检测 ──
_MERMAID_FENCE_RE = re.compile(r"^```mermaid\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_MERMAID_TYPES = ("flowchart", "graph", "sequenceDiagram", "stateDiagram-v2",
                  "stateDiagram", "mindmap", "timeline", "gantt", "classDiagram", "erDiagram")
_MERMAID_DIRECTIVE_RE = re.compile(r"^%%\{.*\}%%\s*$")
# 非 mermaid 但也可算主视觉
_IMAGE_LINE_RE = re.compile(r"^!\[.*\]\(([^)]+)\)", re.MULTILINE)


def _body_has_visual(body: str) -> bool:
    # mermaid fence
    for m in _MERMAID_FENCE_RE.finditer(body):
        inner = m.group(1)
        for raw in inner.splitlines():
            line = raw.strip()
            if not line or _MERMAID_DIRECTIVE_RE.match(line):
                continue
            word = line.split()[0] if line.split() else ""
            if word in _MERMAID_TYPES:
                return True
            break
    # data URI 图片
    if _IMAGE_LINE_RE.search(body) and "data:image" in body:
        return True
    # 纯 HTML 内联 SVG（已在上游被剥，这里兜底）
    if "<svg" in body.lower():
        return True
    return False


def detect_text_wall(md: str) -> tuple[int, int]:
    bodies, _ = _extract_sections(md or "")
    if not bodies:
        return 0, 0
    visual = sum(1 for b in bodies if _body_has_visual(b))
    return len(bodies), visual


# ── Guidance ──
_RECAP_GUIDANCE_MD = (
    "洞察板唯一任务：针对本场会议暴露的困境，给出会上没人想到的 AI 最优解法。"
    "禁止入板：决策清单（含 DC 编号）、议题归类、决策分工（谁做什么、截止日期）、"
    "参会人立场与「谁说了什么」、带说话人/时间戳的依据流水、会议概览与摘要复述。"
    "每节按「困境一句话界定 → 外部最优解法（可执行） → 落地步骤 → 取舍」组织。"
)
_TEXT_WALL_GUIDANCE_MD = (
    "洞察板是图不是文章：每个困境一节，先画后主文。"
    "每节必须有一个按**形态**识别的主视觉，优先 ```mermaid fence（首词必须是 "
    "flowchart/graph/sequenceDiagram/mindmap/timeline 等图类型关键字）；"
    "节点文字≤12字、每图≤10节点；禁 < > &（用中文替代）；禁 click 语句。"
    "也可用 data URI 内联的 ![图](data:image/...) 图片。"
    "纯段落/列表组成的节会被拒收。"
)


# ── Legacy 迁移 ──
def migrate_legacy_html_to_md(task_id: str) -> bool:
    """把存量 {task_id}.board.html + .boards.json 合并为 {task_id}.insight.md。
    只迁移主板（main），多板其他内容合并为正文 section。成功返回 True。"""
    import core.insight_board as ib
    tasks_dir = ib.BOARD_TASKS_DIR

    md_path = _board_md_path(task_id)
    if md_path.exists():
        return False  # 已是 md，无需再迁

    manifest_path = tasks_dir / f"{task_id}.boards.json"
    manifest: dict = {}
    boards: list[dict] = []
    if manifest_path.exists():
        try:
            manifest = json_load_safe(manifest_path) or {}
            boards = list(manifest.get("boards") or [])
        except Exception:
            boards = []
    if not boards:
        # 兜底：找 legacy .board.html
        legacy = tasks_dir / f"{task_id}.board.html"
        if legacy.exists():
            boards = [{"board_id": "main", "title": "主看板", "file": "main"}]

    if not boards:
        return False  # 没有任何可迁移的东西

    # 按 manifest 顺序拼 md body
    body_parts: list[str] = []
    for b in boards:
        bid = str(b.get("board_id") or "main")
        title = str(b.get("title") or bid)
        # 找对应 html
        html_path = tasks_dir / f"{task_id}.board.{bid}.html"
        if not html_path.exists():
            html_path = tasks_dir / f"{task_id}.board.html"  # legacy
            if not html_path.exists():
                continue
        try:
            html = html_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        md_body = html_to_markdown(html)
        body_parts.append(f"<!-- section-id: {bid} section-title: {title} -->")
        body_parts.append(f"## {title}")
        body_parts.append(md_body)
        body_parts.append("")

    if not body_parts:
        return False

    # 读 metadata（取 revision 最大的那份）
    max_rev = 0
    max_title = "主看板"
    max_updated = None
    for b in boards:
        r = int(b.get("revision") or 0)
        if r > max_rev:
            max_rev = r
            max_title = str(b.get("title") or "主看板")
            max_updated = b.get("updated_at")

    meta = {
        "board_id": "main",
        "title": max_title,
        "revision": max_rev,
        "updated_at": max_updated or int(time.time() * 1000),
        "migrated_from": "html",
    }
    out = dump_front_matter(meta, "\n".join(body_parts).strip())
    from core.fs_atomic import atomic_write_text
    atomic_write_text(md_path, out)
    logger.info("[洞察板·md] 迁移完成 task=%s boards=%s rev=%s",
                task_id, len(boards), max_rev)
    return True


def json_load_safe(path: Path) -> dict:
    import json as _json
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── HTML → Markdown 极简转换（迁移用，不追求完美） ──
def html_to_markdown(html: str) -> str:
    """把旧 HTML 板粗略转成 Markdown。保留 mermaid pre 源码、保留 section 层级。

    不是通用转换器——仅服务于 insight.html 的已知结构（section > h2-h4 > p/ul/ol/pre/table）。
    转换损失可接受（反正洞察板主要价值在文字和 mermaid 图，CSS 全部丢弃）。
    """
    import html as html_mod

    out = html or ""

    # 1. 把 <pre> 包成 ```mermaid（洞察板里 <pre> 都是 mermaid）
    def _pre_to_mermaid(m: re.Match) -> str:
        inner = m.group(1).strip()
        if inner.startswith("flowchart") or inner.startswith("graph") or inner.startswith("sequenceDiagram") \
                or inner.startswith("stateDiagram") or inner.startswith("mindmap") or inner.startswith("timeline") \
                or inner.startswith("gantt") or inner.startswith("classDiagram") or inner.startswith("erDiagram"):
            return f"\n```mermaid\n{inner}\n```\n"
        # 普通代码块
        return f"\n```\n{inner}\n```\n"
    out = re.sub(r"<pre\b[^>]*>(.*?)</pre>", _pre_to_mermaid, out, flags=re.DOTALL | re.IGNORECASE)

    # 2. heading：标题与后续正文必须分行，避免合并成「## 标题正文」
    out = re.sub(r"<h1\b[^>]*>(.*?)</h1>", r"\n# \1\n", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<h2\b[^>]*>(.*?)</h2>", r"\n## \1\n", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<h3\b[^>]*>(.*?)</h3>", r"\n### \1\n", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<h4\b[^>]*>(.*?)</h4>", r"\n#### \1\n", out, flags=re.DOTALL | re.IGNORECASE)

    # 3. 段落
    out = re.sub(r"</p>", "\n\n", out, flags=re.IGNORECASE)
    out = re.sub(r"<p\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<br\s*/?>", "\n", out, flags=re.IGNORECASE)

    # 4. <a data-seek-ms="..."> —— 先用占位符保护，避免第 6 步剥标签时丢失
    seek_anchors: list[str] = []

    def _preserve_seek(m: re.Match) -> str:
        seek_anchors.append(f'<a data-seek-ms="{m.group(1)}">{m.group(2)}</a>')
        return f"\x00SEEK{len(seek_anchors) - 1}\x00"

    out = re.sub(
        r'<a\s+[^>]*data-seek-ms\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        _preserve_seek, out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 5. ul/li
    out = re.sub(r"<li\b[^>]*>(.*?)</li>", r"\n- \1", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"</?ul\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"</?ol\b[^>]*>", "", out, flags=re.IGNORECASE)

    # 6. 剥所有剩下来的 HTML 标签（section/div/span/style/script/card 等）
    out = re.sub(r"<[^>]+>", "", out)

    # 7. 解码 HTML entities
    out = html_mod.unescape(out)

    # 8. 清理连续空行；不压缩行内空格，避免破坏 mermaid 缩进
    out = re.sub(r"\n{3,}", "\n\n", out)
    # 还原 seek 白名单锚点
    out = re.sub(r"\x00SEEK(\d+)\x00", lambda m: seek_anchors[int(m.group(1))], out)

    return out.strip()
