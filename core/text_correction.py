"""
core/text_correction.py — 会议文本回溯修正 / Retroactive term correction for one meeting

职责 / Responsibilities:
  把一条「误识别 → 正确文本」映射全量落到**已存会议**的全部产物上：
  任务对象（转写原文 / 纪要 / 随记 / 决策 / 章节）+ 洞察消息 JSON + 洞察板 HTML + 导出纪要 md。
  Apply one wrong→correct mapping across every artifact of an existing meeting:
  the task object (transcript / summary / notes / decisions / chapters), the insights
  JSON, the insight board HTML and the exported minutes markdown.

为什么需要它 / Why this exists:
  热词映射（core.hotwords.apply_hotword_mappings）的设计边界是「转写时刻的后处理」——
  它只改写正在产生的识别结果，从不回溯已落盘的任务。因此用户在划词工具栏里新建映射后，
  本场会议的旧文本依旧保持误识别原样，与「我已经纠正过这个词」的直觉相悖。
  本模块就是那条回溯路径的落地端，由 POST /api/tasks/{task_id}/correct-text 调用。

匹配规则 / Matching rule:
  与转写链路**完全一致**（复用 core.hotwords.sub_term 与 ascii_term_pattern）：纯 ASCII 词按
  ASCII 邻接边界匹配（大小写不敏感），含中文的串走子串替换。否则 ES→EAS 这类映射会咬穿 FILES。
  计数侧 count_term 必须共用同一个 pattern：旧实现里它与替换侧同用 `\\b`，对紧贴中文的
  「与ES」双双失效，导致 residual 残扫报 0、漏改完全不可见。

改写范围 / Rewrite scope:
  按**键名白名单**（REWRITE_KEYS）递归改写，而不是按路径枚举 —— 新增一个名为 text 的
  字段会自动被覆盖，同时天然避开 task_id / audio_path / *_at / speaker_id 等标识与路径字段。
  代价：白名单之外的新文本字段会漏改。因此每次修正都会对**全部产物做一次残留扫描**，
  把残余命中数放进响应的 residual 字段，漏改不会静默。
"""

import json
import logging
from pathlib import Path

from core.fs_atomic import atomic_write_json, atomic_write_text
from core.hotwords import _is_ascii_word, ascii_term_pattern, sub_term

logger = logging.getLogger(__name__)

TASKS_DIR = Path("data/tasks")

# 可改写的键名白名单：只放「承载会议内容」的字段名。
# 判定标准是「这个键的值会不会被用户读到」——标识符、路径、时间戳、枚举状态一律不进。
REWRITE_KEYS = frozenset({
    "text",              # 转写句 / 决策正文 / 导出段落
    "title",             # 会议标题 / 章节标题 / 洞察标题
    "summary",           # 纪要 / 章节小结
    "user_summary",      # 用户手工编辑过的纪要
    "realtime_summary",  # 实时摘要
    "user_notes",        # 随记
    "body",              # 洞察正文
    "solution",          # 洞察建议
    "why",               # 决策依据
    "how",               # 决策进展（list[str]）
    "key_points",        # 章节要点（list[str]）
    "assignee",          # 决策执行人
    "speaker_name",      # 实时转写的说话人名
    "label",             # 洞察图节点标签 / 动作标签
    "diagram",           # Mermaid 源码（节点标签内嵌其中）
})


def count_term(text: str, term: str) -> int:
    """按 sub_term 的同一匹配规则统计命中数 / Count hits with the same rule as sub_term.

    与 sub_term 共用 ascii_term_pattern 是底线：两边规则一旦分叉，residual 残扫就会
    在真正漏改的位置报 0（就是本次问题的第二层原因）。
    """
    if not text or not term:
        return 0
    if _is_ascii_word(term):
        return len(ascii_term_pattern(term).findall(text))
    return text.count(term)


def _rewrite_node(node, old: str, new: str, tally: dict[str, int]) -> bool:
    """递归改写 dict 节点内白名单键的文本，返回是否发生变化。

    Recurse a dict node, rewriting whitelisted text fields in place.
    只在 dict 上递归（键名就是白名单判定的依据）；list 交给 _rewrite_list 并带上键名语境。
    """
    if not isinstance(node, dict):
        return _rewrite_list(node, None, old, new, tally)
    changed = False
    for key in list(node.keys()):
        value = node[key]
        if isinstance(value, str):
            if key in REWRITE_KEYS:
                replaced, hits = sub_term(value, old, new)
                if hits:
                    node[key] = replaced
                    tally[key] = tally.get(key, 0) + hits
                    changed = True
        elif isinstance(value, dict):
            changed = _rewrite_node(value, old, new, tally) or changed
        elif isinstance(value, list):
            changed = _rewrite_list(value, key, old, new, tally) or changed
    return changed


def _rewrite_list(items, key: str | None, old: str, new: str, tally: dict[str, int]) -> bool:
    """递归改写数组：字符串元素需父键在白名单内，对象元素继续下钻。

    A bare list[str] is only rewritten when its owning key is whitelisted — otherwise
    we would risk touching enum values (status/source/owner_type all live in arrays too).
    """
    if not isinstance(items, list):
        return False
    changed = False
    for idx, item in enumerate(items):
        if isinstance(item, str):
            if key and key in REWRITE_KEYS:
                replaced, hits = sub_term(item, old, new)
                if hits:
                    items[idx] = replaced
                    bucket = f"{key}[]"
                    tally[bucket] = tally.get(bucket, 0) + hits
                    changed = True
        elif isinstance(item, dict):
            changed = _rewrite_node(item, old, new, tally) or changed
        elif isinstance(item, list):
            changed = _rewrite_list(item, key, old, new, tally) or changed
    return changed


def rewrite_task_payload(task: dict, old: str, new: str) -> dict[str, int]:
    """就地改写任务对象中的全部文本字段，返回按键名分布的命中数。

    Rewrite every text field of the task object in place; return per-key hit counts.
    调用方负责在成功后持久化（app.store.save_task_to_disk），内存 tasks 是唯一写入源。
    """
    tally: dict[str, int] = {}
    _rewrite_node(task, old, new, tally)
    return tally


# ── 旁路产物：导出 md / 洞察 JSON / 洞察板 HTML ──
# 这三样是独立于任务 JSON 的文件，必须一并改，否则用户下载的纪要、回看的洞察卡片仍是旧词。

def _insights_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.insights.json"


def correct_task_text(task: dict, task_id: str, old: str, new: str) -> dict:
    """把一条映射全量应用到该会议的任务对象与三份旁路产物。

    Apply one mapping across the task object plus the three side artifacts.
    任务对象的改写**不在此处落盘**（内存 tasks 才是写入源，落盘由路由层调用
    save_task_to_disk 完成）；旁路产物各自原子写回。

    Returns:
        {ok, old, new, replaced, hits: {task, insights, board, export_md},
         fields: {键名: 命中数}, residual, warnings}
    """
    old, new = old.strip(), new.strip()
    warnings: list[str] = []

    fields = rewrite_task_payload(task, old, new)
    task_hits = sum(fields.values())

    insights_hits = _correct_insights_file(task_id, old, new, warnings)
    board_hits = _correct_board_file(task_id, old, new, warnings)
    export_hits = _correct_export_markdown(task, old, new, warnings)

    replaced = task_hits + insights_hits + board_hits + export_hits
    residual = _scan_residual(task, task_id, old)

    logger.info(
        "[文本修正] task=%s %s→%s 命中 task=%s insights=%s board=%s md=%s 残留=%s",
        task_id[:8], old, new, task_hits, insights_hits, board_hits, export_hits, residual,
    )
    return {
        "ok": True,
        "old": old,
        "new": new,
        "replaced": replaced,
        "hits": {
            "task": task_hits,
            "insights": insights_hits,
            "board": board_hits,
            "export_md": export_hits,
        },
        "fields": fields,
        "residual": residual,
        "warnings": warnings,
    }


def _correct_insights_file(task_id: str, old: str, new: str, warnings: list[str]) -> int:
    """修正 <task_id>.insights.json，返回命中数 / Correct the insights JSON, return hits."""
    path = _insights_path(task_id)
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        warnings.append(f"insights unreadable: {e}")
        return 0
    tally: dict[str, int] = {}
    _rewrite_node(payload, old, new, tally)
    hits = sum(tally.values())
    if hits:
        try:
            atomic_write_json(path, payload)
        except OSError as e:
            warnings.append(f"insights write failed: {e}")
            return 0
    return hits


def _correct_board_file(task_id: str, old: str, new: str, warnings: list[str]) -> int:
    """修正洞察板 HTML / Correct the board HTML.

    复用 board_html_save 走清洗 + revision+1，避免手改后绕过 XSS 防线与版本协议。
    """
    try:
        from core.insight_board import board_html_load, board_html_save
    except ImportError as e:  # 洞察板模块缺席时仅跳过旁路，任务主体仍已修正
        warnings.append(f"board module unavailable: {e}")
        return 0
    board = board_html_load(task_id)
    if not board or not board.get("html"):
        return 0
    replaced, hits = sub_term(board["html"], old, new)
    if not hits:
        return 0
    # content_floor=False：错字回溯是系统级机械改写，旧板的内容形态不应被
    # 共创期才有的复述/文字墙底线否决（否则老板会静默改不动）；安全清洗仍执行。
    result = board_html_save(task_id, replaced, content_floor=False)
    if not result.get("ok"):
        warnings.append(f"board write rejected: {result.get('error')}")
        return 0
    return hits


def _correct_export_markdown(task: dict, old: str, new: str, warnings: list[str]) -> int:
    """修正已导出的纪要 md / Correct the exported minutes markdown."""
    output_path = task.get("output_path")
    if not output_path:
        return 0
    path = Path(output_path)
    if not path.exists():
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        warnings.append(f"export md unreadable: {e}")
        return 0
    replaced, hits = sub_term(text, old, new)
    if not hits:
        return 0
    try:
        atomic_write_text(path, replaced)
    except OSError as e:
        warnings.append(f"export md write failed: {e}")
        return 0
    return hits


def _scan_residual(task: dict, task_id: str, old: str) -> int:
    """全量扫描仍残留的命中数 / Count anything the whitelist failed to rewrite.

    白名单策略的代价是新文本字段可能落在名单之外。这里对任务 JSON 全文与三份旁路产物
    做一次兜底计数：residual > 0 就是「白名单需要补条目」的明确信号，不靠人肉发现。
    """
    residual = 0
    try:
        residual += count_term(json.dumps(task, ensure_ascii=False), old)
    except (TypeError, ValueError) as e:
        logger.warning("[文本修正] 任务残留扫描失败 task=%s: %s", task_id[:8], e)
    for path in (_insights_path(task_id), TASKS_DIR / f"{task_id}.board.html", Path(task.get("output_path") or "-")):
        try:
            if path.exists():
                residual += count_term(path.read_text(encoding="utf-8", errors="replace"), old)
        except OSError:
            continue
    return residual
