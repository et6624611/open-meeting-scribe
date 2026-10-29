"""
core/insight_board.py — 洞察板引擎 / Insight Board engine

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-28
更新 / Updated: 2026-09-28
版本 / Version: 1.0.0

洞察板（Insight Board）核心模块。当前模式 / Current mode：
「洞察共创 · 会话驱动（HTML 产物版）」——AI 在会话面板中直出一份自包含 HTML 文档，
后端基础安全清洗后整份落盘 data/tasks/<task_id>.board.html；
无 schema 校验、无整批丢弃、无失败归因，共创靠「读当前 HTML → 增量改 → 落盘」循环。

【已退役】Board Spec v0.3 结构化契约（ops/zone/cell 校验、原子合并、LLM 生成端点）
随共创 HTML 模式下线；以下旧段代码保留供追溯（同 intent.py 先例），不再被任何入口接线：
1. Board Spec 校验（validate_board/_validate_zone/_validate_cell/_infer_cell_kind）
2. zone patch 操作的原子合并（apply_ops，整批 ops 合法才应用）
3. 板 JSON 持久化（<task_id>.board.json）
4. 板生成分析 run_board_analysis（LLM 输出 zone patch ops 而非单卡）

设计要点 / Design notes:
- 新模式下版式所有权移交 AI（自包含 HTML），应用侧只做安全清洗与呈现容器；
- 样式建议用本应用 CSS 变量以适配主题，转写跳转用 data-seek-ms 锚点约定；
- 与卡片管线（core/insights.py）并行共存，互不写入对方的存储。
"""

import copy
import json
import logging
import re
import time
from html import unescape as _html_unescape
from pathlib import Path

from core.fs_atomic import atomic_write_json, atomic_write_text
from core.llm import async_chat_completion

logger = logging.getLogger(__name__)

SPEC_VERSION = "0.3"
MAX_ZONES = 7
BOARD_TASKS_DIR = Path("data/tasks")

# 字段长度预算 / Field length caps（超限即校验失败，防生成物失控膨胀）
CAP_TITLE = 60
CAP_SUMMARY = 200
CAP_LABEL = 30
CAP_TEXT = 300
CAP_DIAGRAM_SOURCE = 2000

ZONE_STATUS = {"open", "evolving", "settled"}
ZONE_MATURITY = {"draft", "forming", "confirmed"}
VISUAL_KINDS = {"flow", "map", "diagram"}
TEXT_KINDS = {"gaps", "actions", "note"}
CELL_KINDS = VISUAL_KINDS | TEXT_KINDS
OP_KINDS = {"upsert_zone", "replace_cells", "settle_zone"}


# ============================================================
# 【已退役】Board Spec v0.3：校验 / ops 合并 / LLM 生成
# （随「洞察共创 · 会话驱动（HTML 产物版）」下线，代码保留供追溯）
# ============================================================


class BoardValidationError(ValueError):
    """【已退役】Board Spec / ops 校验失败，携带可读错误列表 / Raised with a human-readable error list."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors)[:400])


# ============================================================
# 基础清洗工具 / Sanitizing helpers
# ============================================================

def _clean_text(value, cap: int) -> str:
    """标量文本清洗：非字符串拒绝、去首尾空白、截断 / Scalar text: reject non-str, trim, cap."""
    if not isinstance(value, str):
        raise BoardValidationError([f"期望字符串，实际为 {type(value).__name__}"])
    return value.strip()[:cap]


def _opt_ms(value):
    """begin_time 归一：None/非法 → None，数字 → int 毫秒 / Normalize begin_time to int ms or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return None


# ============================================================
# Cell 校验 / Cell validation
# ============================================================

def _infer_cell_kind(cell: dict) -> str | None:
    """kind 缺失时的结构反推（宽容解析不降标准）：各 kind 字段集互斥，反推失败仍报错。

    背景：实测 qwen-plus 与 qwen3:8b 均会在同一位置漏写 cell.kind（提示词未显式要求该字段），
    整批丢弃对用户是不可解释的失败；这里按内容结构唯一性地补回类型。
    """
    if isinstance(cell.get("stages"), list):
        return "flow"
    if isinstance(cell.get("nodes"), list) and isinstance(cell.get("edges"), list):
        return "map"
    if cell.get("format") == "mermaid" or (isinstance(cell.get("source"), str) and cell.get("source")):
        return "diagram"
    items = cell.get("items")
    if isinstance(items, list) and items:
        first = items[0] if isinstance(items[0], dict) else {}
        if "question" in first or "resolved" in first:
            return "gaps"
        if "text" in first or "owner" in first:
            return "actions"
        return None
    if isinstance(cell.get("text"), str) and cell.get("text"):
        return "note"
    return None


def _validate_cell(cell, where: str) -> dict:
    if not isinstance(cell, dict):
        raise BoardValidationError([f"{where}: cell 必须是对象"])
    kind = cell.get("kind")
    if kind not in CELL_KINDS:
        inferred = _infer_cell_kind(cell)
        if inferred:
            logger.warning("[洞察板] %s: 缺失 cell.kind(%r)，已按结构反推为 %s", where, kind, inferred)
            cell = {**cell, "kind": inferred}
            kind = inferred
        else:
            raise BoardValidationError([f"{where}: 未知 cell.kind {kind!r}"])

    if kind == "flow":
        stages = cell.get("stages")
        if not isinstance(stages, list) or not (1 <= len(stages) <= 5):
            raise BoardValidationError([f"{where} flow: stages 需为 1-5 个"])
        out_stages = []
        for i, st in enumerate(stages):
            steps = st.get("steps") if isinstance(st, dict) else None
            if not isinstance(steps, list) or not (1 <= len(steps) <= 4):
                raise BoardValidationError([f"{where} flow.stages[{i}]: steps 需为 1-4 个"])
            out_stages.append({
                "name": _clean_text(st.get("name", ""), CAP_LABEL),
                "steps": [{
                    "label": _clean_text(s.get("label", ""), CAP_LABEL),
                    "begin_time": _opt_ms(s.get("begin_time")),
                    **({"pending": True} if s.get("pending") is True else {}),
                } for s in steps],
            })
        return {"kind": "flow", "stages": out_stages}

    if kind == "map":
        nodes = cell.get("nodes")
        edges = cell.get("edges")
        if not isinstance(nodes, list) or not (2 <= len(nodes) <= 8):
            raise BoardValidationError([f"{where} map: nodes 需为 2-8 个"])
        if not isinstance(edges, list) or not (1 <= len(edges) <= 10):
            raise BoardValidationError([f"{where} map: edges 需为 1-10 条"])
        ids = set()
        out_nodes = []
        for n in nodes:
            nid = _clean_text(n.get("id", ""), CAP_LABEL)
            if not nid or nid in ids:
                raise BoardValidationError([f"{where} map: 节点 id 为空或重复: {nid!r}"])
            ids.add(nid)
            out_nodes.append({"id": nid, "label": _clean_text(n.get("label", ""), CAP_LABEL),
                              "begin_time": _opt_ms(n.get("begin_time"))})
        out_edges = []
        for e in edges:
            if e.get("from") not in ids or e.get("to") not in ids:
                raise BoardValidationError([f"{where} map: 边端点未引用有效节点 id"])
            if e.get("kind") not in {"broken", "link", "dashed"}:
                raise BoardValidationError([f"{where} map: edge.kind 需为 broken/link/dashed"])
            out_edges.append({"from": e["from"], "to": e["to"],
                              "label": _clean_text(e.get("label", ""), CAP_LABEL), "kind": e["kind"]})
        return {"kind": "map", "nodes": out_nodes, "edges": out_edges}

    if kind == "diagram":
        if cell.get("format") != "mermaid":
            raise BoardValidationError([f"{where} diagram: format 仅支持 mermaid"])
        source = _clean_text(cell.get("source", ""), CAP_DIAGRAM_SOURCE)
        if not source:
            raise BoardValidationError([f"{where} diagram: source 为空"])
        return {"kind": "diagram", "format": "mermaid", "source": source}

    if kind == "gaps":
        items = cell.get("items")
        if not isinstance(items, list) or not (1 <= len(items) <= 8):
            raise BoardValidationError([f"{where} gaps: items 需为 1-8 条"])
        return {"kind": "gaps", "items": [{
            "question": _clean_text(it.get("question", ""), CAP_TEXT),
            "begin_time": _opt_ms(it.get("begin_time")),
            "resolved": it.get("resolved") is True,
        } for it in items]}

    if kind == "actions":
        items = cell.get("items")
        if not isinstance(items, list) or not (1 <= len(items) <= 8):
            raise BoardValidationError([f"{where} actions: items 需为 1-8 条"])
        return {"kind": "actions", "items": [{
            "text": _clean_text(it.get("text", ""), CAP_TEXT),
            "owner": _clean_text(it.get("owner", ""), CAP_LABEL) or None,
        } for it in items]}

    # note
    return {"kind": "note", "text": _clean_text(cell.get("text", ""), CAP_TEXT)}


# ============================================================
# Zone / Board 校验
# ============================================================

def _validate_zone(zone, where: str = "zone") -> dict:
    if not isinstance(zone, dict):
        raise BoardValidationError([f"{where}: 必须是对象"])
    zid = _clean_text(zone.get("id", ""), CAP_LABEL)
    if not zid:
        raise BoardValidationError([f"{where}: id 为空"])
    status = zone.get("status", "open")
    if status not in ZONE_STATUS:
        raise BoardValidationError([f"{where} {zid}: status 需为 {sorted(ZONE_STATUS)}"])
    maturity = zone.get("maturity", "draft")
    if maturity not in ZONE_MATURITY:
        raise BoardValidationError([f"{where} {zid}: maturity 需为 {sorted(ZONE_MATURITY)}"])
    cells = zone.get("cells")
    if not isinstance(cells, list) or not (1 <= len(cells) <= 8):
        raise BoardValidationError([f"{where} {zid}: cells 需为 1-8 个"])
    out_cells = [_validate_cell(c, f"{where} {zid}.cells[{i}]") for i, c in enumerate(cells)]
    if not any(c["kind"] in VISUAL_KINDS for c in out_cells):
        raise BoardValidationError([f"{where} {zid}: 缺少主视觉 cell（flow/map/diagram 至少一个）"])
    origin = zone.get("origin")
    out_origin = [str(o)[:64] for o in origin if isinstance(o, str)][:20] if isinstance(origin, list) else []
    return {
        "id": zid,
        "title": _clean_text(zone.get("title", ""), CAP_TITLE),
        "status": status,
        "maturity": maturity,
        "summary": _clean_text(zone.get("summary", ""), CAP_SUMMARY),
        "cells": out_cells,
        "origin": out_origin,
        "updated_at": zone.get("updated_at") if isinstance(zone.get("updated_at"), (int, float)) else None,
    }


def validate_board(data) -> dict:
    """校验并归一化整板；不合 schema 抛 BoardValidationError / Validate & normalize a whole board."""
    if not isinstance(data, dict):
        raise BoardValidationError(["board 必须是对象"])
    if data.get("kind") != "insight-board":
        raise BoardValidationError([f"kind 需为 insight-board，实际 {data.get('kind')!r}"])
    zones = data.get("zones")
    if not isinstance(zones, list) or not (1 <= len(zones) <= MAX_ZONES):
        raise BoardValidationError([f"zones 需为 1-{MAX_ZONES} 个"])
    out_zones = [_validate_zone(z, f"zones[{i}]") for i, z in enumerate(zones)]
    ids = [z["id"] for z in out_zones]
    if len(ids) != len(set(ids)):
        raise BoardValidationError(["zone id 存在重复"])
    header = data.get("header") if isinstance(data.get("header"), dict) else {}
    # revision 允许 0（骨架板）：不能用 or 强转，0 是合法值 / revision 0 is valid (skeleton board)
    raw_rev = data.get("revision")
    revision = int(raw_rev) if isinstance(raw_rev, (int, float)) and not isinstance(raw_rev, bool) and raw_rev >= 0 else 1
    return {
        "kind": "insight-board",
        "spec_version": str(data.get("spec_version") or SPEC_VERSION),
        "task_id": str(data.get("task_id") or ""),
        "revision": revision,
        "phase": data.get("phase") if data.get("phase") in {"meeting", "post_meeting"} else "meeting",
        "header": {
            "title": _clean_text(header.get("title", ""), CAP_TITLE),
            "meeting_date": _clean_text(header.get("meeting_date", ""), 20),
            "summary": _clean_text(header.get("summary", ""), CAP_SUMMARY),
        },
        "zones": out_zones,
    }


# ============================================================
# zone patch 操作：原子合并 / Atomic ops application
# ============================================================

def apply_ops(board: dict, ops: list, now_ms: int | None = None) -> dict:
    """
    将 ops 应用到板的副本；任一 op 非法即抛错、原板不受影响（原子语义）。
    Apply ops to a deep copy; any invalid op aborts the whole batch (board keeps last revision).
    返回新板（revision +1，被触碰 zone 打 updated 标记）。
    """
    if not isinstance(ops, list) or not ops:
        raise BoardValidationError(["ops 需为非空数组"])
    new_board = copy.deepcopy(board)
    zones = new_board["zones"]
    index = {z["id"]: i for i, z in enumerate(zones)}
    touched: set[str] = set()

    for i, op in enumerate(ops):
        if not isinstance(op, dict) or op.get("op") not in OP_KINDS:
            raise BoardValidationError([f"ops[{i}]: op 类型非法"])
        kind = op["op"]
        where = f"ops[{i}] {kind}"
        if kind == "upsert_zone":
            zone = _validate_zone(op.get("zone"), where)
            if now_ms is not None:
                zone["updated_at"] = now_ms
            if zone["id"] in index:
                old = zones[index[zone["id"]]]
                # 收敛更新保留来源合并：origin 取并集 / Merge origin on upsert
                zone["origin"] = list(dict.fromkeys(old.get("origin", []) + zone["origin"]))[:20]
                zones[index[zone["id"]]] = zone
            else:
                if len(zones) >= MAX_ZONES:
                    raise BoardValidationError([f"{where}: zone 数已达上限 {MAX_ZONES}，应先合并主题"])
                zones.append(zone)
                index[zone["id"]] = len(zones) - 1
            touched.add(zone["id"])
        elif kind == "replace_cells":
            zid = _clean_text(op.get("zone_id", ""), CAP_LABEL)
            if zid not in index:
                raise BoardValidationError([f"{where}: zone {zid!r} 不存在"])
            cells = op.get("cells")
            if not isinstance(cells, list) or not (1 <= len(cells) <= 8):
                raise BoardValidationError([f"{where}: cells 需为 1-8 个"])
            out_cells = [_validate_cell(c, f"{where}.cells[{j}]") for j, c in enumerate(cells)]
            if not any(c["kind"] in VISUAL_KINDS for c in out_cells):
                raise BoardValidationError([f"{where} {zid}: 缺少主视觉 cell"])
            zone = zones[index[zid]]
            zone["cells"] = out_cells
            if now_ms is not None:
                zone["updated_at"] = now_ms
            touched.add(zid)
        else:  # settle_zone
            zid = _clean_text(op.get("zone_id", ""), CAP_LABEL)
            if zid not in index:
                raise BoardValidationError([f"{where}: zone {zid!r} 不存在"])
            zones[index[zid]]["status"] = "settled"
            if now_ms is not None:
                zones[index[zid]]["updated_at"] = now_ms
            touched.add(zid)

    new_board["revision"] = int(new_board.get("revision") or 1) + 1
    new_board["touched"] = sorted(touched)
    return new_board


# ============================================================
# 持久化 / Persistence
# ============================================================

def board_path(task_id: str, base: Path | None = None) -> Path:
    return (base or BOARD_TASKS_DIR) / f"{task_id}.board.json"


def load_board(task_id: str, base: Path | None = None) -> dict | None:
    """读取板；文件缺失/损坏返回 None（三态：有板/无板/坏板按无板处理） / Load board, None on missing/corrupt."""
    if not task_id:
        return None
    f = board_path(task_id, base)
    if not f.exists():
        return None
    try:
        return validate_board(json.loads(f.read_text(encoding="utf-8")))
    except Exception as e:
        logger.warning("[洞察板] 板文件损坏 task=%s: %s", task_id, e)
        return None


def save_board(board: dict, base: Path | None = None) -> None:
    f = board_path(board.get("task_id", ""), base)
    f.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(f, board)


def new_board(task_id: str, title: str, meeting_date: str = "") -> dict:
    """空白板骨架 / Empty board skeleton（占位 flow 主视觉，满足每区必有视觉 cell 的契约）"""
    return validate_board({
        "kind": "insight-board", "task_id": task_id, "revision": 0, "phase": "meeting",
        "header": {"title": title, "meeting_date": meeting_date, "summary": ""},
        "zones": [{"id": "z-init", "title": "开场", "status": "open", "maturity": "draft",
                   "summary": "板已建立，等待首轮洞察。",
                   "cells": [{"kind": "flow", "stages": [
                       {"name": "待生成", "steps": [{"label": "等待首轮洞察", "pending": True}]}]}],
                   "origin": []}],
    })


def build_board_digest(board: dict | None) -> str:
    """板的紧凑摘要（供生成侧携带全局视角 / digest injected into board analysis prompt）"""
    if not board:
        return "（尚无板——本轮生成建立初始 zone）"
    lines = []
    for z in board["zones"]:
        kinds = ",".join(c["kind"] for c in z["cells"])
        lines.append(f"- [{z['status']}/{z['maturity']}] {z['id']}「{z['title']}」{z['summary']}（cells: {kinds}）")
    return "\n".join(lines)


# ============================================================
# 板生成提示词与分析入口 / Board generation prompt & entry
# ============================================================

BOARD_ANALYSIS_PROMPT = """你是一位资深会议顾问，负责维护一块随会议演化的「洞察板」（Insight Board）。
你的输出不是新卡片，而是对板的**区域级修订操作（ops）**。

## 板模型
- 板按主题分区（zone），3-7 个 zone；zone 顺序即叙事序。
- 每个 zone 恰好一个主视觉 cell（flow 阶段流程 / map 关系结构 / diagram Mermaid 图），其余为文本 cell（gaps 盲点问题 / actions 行动建议 / note 图注提问）。
- 图主导：主视觉承载全局结构，文本只是折叠细节。

## 修订纪律（最重要）
1. 对照「当前板摘要」：本轮讨论若与既有 zone 同主题，必须 upsert_zone 更新该 zone（保留其 id），禁止新建近似主题的 zone。
2. 仅当出现真正的新主题时才追加 zone；zone 总数不得超过 7。
3. 已被讨论清楚的 zone 用 settle_zone 收敛；有实质推进的用 upsert_zone 提升 maturity（draft→forming→confirmed）。
4. 每条信息尽量携带 begin_time（毫秒，取对应转写行的时间戳；无法对应则 null）。

## cell 书写规范
⚠️ 每个 cell 对象**必须包含 "kind" 字段**（取值 flow|map|diagram|gaps|actions|note 之一），只写内容字段不带 kind 会被整批丢弃。
- flow：1-5 个 stage，每 stage 1-4 个 step；step label ≤14 字，待确认节点标 "pending": true；
- map：2-8 个 node、1-10 条 edge，edge.kind ∈ broken|link|dashed，edge label ≤14 字（断裂与缺环优先表达）；
- diagram：Mermaid 语法字符串（flowchart/mindmap/sequenceDiagram 等），format 固定 "mermaid"；
- gaps：question 为启发式提问（不替用户下结论），resolved 表示已解决；
- actions：text 为可执行动作，能识别责任方则填 owner；
- note：1-3 句图注/提问，指出主视觉里最关键的盲区。

## 返回 JSON（仅 JSON，不要代码块标记）
{"ops": [
  {"op": "upsert_zone", "zone": {"id": "z-xxx", "title": "≤12字", "status": "open|evolving|settled", "maturity": "draft|forming|confirmed", "summary": "≤60字", "cells": [...], "origin": []}},
  {"op": "replace_cells", "zone_id": "z-xxx", "cells": [...]},
  {"op": "settle_zone", "zone_id": "z-xxx"}
]}
无可修订内容时返回 {"ops": []}。zone id 用 z- 前缀小写短横线命名。"""


def _fmt_ms(ms: int) -> str:
    """毫秒转 mm:ss 展示格式 / Format milliseconds as mm:ss display."""
    total_sec = int(ms) // 1000
    return f"{total_sec // 60:02d}:{total_sec % 60:02d}"


def _build_board_user_message(recent_lines, chapter_titles, digest: str) -> str:
    transcript = "\n".join(
        f"[说话人{ln.get('speaker_id', 0) + 1}] ({_fmt_ms(ln.get('begin_time', 0))}) {ln.get('text', '')}"
        for ln in recent_lines
    )
    titles = "\n".join(f"- {t}" for t in chapter_titles)
    return (
        f"## 会议章节主题\n{titles}\n\n"
        f"## 当前板摘要（全局视角，修订时对照它）\n{digest}\n\n"
        f"## 最近讨论内容（{len(recent_lines)} 条）\n{transcript}\n\n"
        "请输出本轮对板的修订 ops。"
    )


async def run_board_analysis(
    recent_lines: list[dict],
    chapter_titles: list[str],
    existing_board: dict | None,
    role_name: str | None = None,
) -> dict:
    """
    执行板生成分析：LLM 输出 ops → 校验合并 → 返回新板或错误。
    返回 / Returns: {"ok": bool, "board": dict|None, "errors": [str], "raw_ops": list, "failure_class": str}
    ok=False 时 board 为 None 或原板，调用方不得落盘（原子容错语义）。
    failure_class（AI 算力入口治理：失败按因分流提示）：
      input=数据不足 / schema=格式崩了整批丢弃（模型能力问题） /
      connect=服务连接或超时（环境问题，重试即可） / unknown=其它
    """
    empty = {"ok": False, "board": None, "errors": ["insufficient_input"], "raw_ops": [], "failure_class": "input"}
    if not recent_lines or not chapter_titles:
        return empty

    system_prompt = BOARD_ANALYSIS_PROMPT
    if role_name:
        from core.agent_workspace import get_role_insight_prompt
        role_prompt = get_role_insight_prompt(role_name)
        if role_prompt:
            # 角色视角叠加但不覆盖板契约（输出格式由板管线独占） / Role view appends, contract stays ours
            system_prompt = f"{system_prompt}\n\n## 角色视角补充\n{role_prompt}"
    from core.model_tier import get_tier_prompt_guard
    system_prompt += get_tier_prompt_guard()

    digest = build_board_digest(existing_board)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _build_board_user_message(recent_lines, chapter_titles, digest)},
    ]
    try:
        reply = await async_chat_completion(messages, model=None, temperature=0.3, max_tokens=2500)
        cleaned = reply.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(ln for ln in cleaned.split("\n") if not ln.strip().startswith("```")).strip()
        payload = json.loads(cleaned)
        ops = payload.get("ops") if isinstance(payload, dict) else None
        if ops == []:
            logger.info("[洞察板] 本轮无需修订（ops 为空）")
            return {"ok": True, "board": existing_board, "errors": [], "raw_ops": []}
        if not existing_board:
            raise BoardValidationError(["无板时首轮必须输出至少一个 upsert_zone"])
        new_board = apply_ops(existing_board, ops)
        logger.info("[洞察板] 修订成功 rev=%s touched=%s",
                    new_board["revision"], new_board.get("touched"))
        return {"ok": True, "board": new_board, "errors": [], "raw_ops": ops, "failure_class": ""}
    except BoardValidationError as e:
        logger.warning("[洞察板] ops 校验失败，整次丢弃: %s", e.errors)
        return {"ok": False, "board": None, "errors": e.errors, "raw_ops": [], "failure_class": "schema"}
    except json.JSONDecodeError:
        logger.warning("[洞察板] 板分析返回非 JSON")
        return {"ok": False, "board": None, "errors": ["llm_output_not_json"], "raw_ops": [], "failure_class": "schema"}
    except Exception as e:
        from core.errors import is_transient_error
        cls = "connect" if is_transient_error(e) else "unknown"
        logger.warning("[洞察板] 板分析失败(%s): %s", cls, e)
        return {"ok": False, "board": None, "errors": [str(e)[:200]], "raw_ops": [], "failure_class": cls}


# ============================================================
# 洞察共创 HTML 产物模型（当前模式：会话驱动、AI 直出整份 HTML）
# ============================================================

BOARD_HTML_CAP = 300_000  # 单份板 HTML 字节上限，防失控膨胀 / Board HTML size cap

# 剥离清单：仅容器级逃逸标签整体移除（含内容）。
# 【版式归 CLI】script/link/meta/style 已解禁：呈现容器是 sandbox iframe（opaque origin），
# 板内的全局作用器只影响板自己文档；安全边界见 frontend InsightBoard.vue 的 BOARD_SANDBOX
# 与 app/server.py 的写请求 Origin 守卫，而非此处正则。on* 与危险 scheme 仍剥（纵深防御），
# 但被剥项必须经 removed 回执如实上报——不允许出现「既没落盘也没上报」的静默变异。
# 继续禁的五个都是内容级逃逸面：板内再套 iframe 指回站内端点、object/embed 插件、
# base 劫持相对地址、form 提交（sandbox 同时不给 allow-forms）。
_DROP_TAGS = ("iframe", "object", "embed", "base", "form")


def _valid_task_id(task_id: str) -> bool:
    """task_id 为 uuid 形态；拒绝路径穿越字符 / Reject traversal chars in task_id."""
    return bool(task_id) and "/" not in task_id and "\\" not in task_id and ".." not in task_id


def sanitize_board_html(html: str) -> tuple[str, list[str]]:
    """安全清洗：返回 (净化后文本, 被改动的字节项列表)。

    1. 整体移除 _DROP_TAGS 标签（含配对内容）；未配对的裸闭合标签一并剪掉
    2. 移除 on* 内联事件属性（含 SVG 动画触发器）
    3. href/src 中的 javascript: / data:text/html 置为 #
    文档外壳（DOCTYPE/html/head/body）、`<script>`、`<style>` 与 :root/html/body/* 全局
    选择器**一律原样保留**——版式所有权属于 CLI，应用不再代行排版权。
    不做白名单全重建——共创模式的作者是本机 AI 而非不可信第三方，这里只做纵深防御底线；
    真正的执行边界在浏览器侧（sandbox iframe / raw 端点的 CSP sandbox）。
    """
    removed: list[str] = []
    out = html or ""
    for tag in _DROP_TAGS:
        pattern = re.compile(
            rf"<{tag}\b[^>]*>.*?</{tag}>|<{tag}\b[^>]*/?>|</{tag}>",
            re.DOTALL | re.IGNORECASE,
        )
        out, n = pattern.subn("", out)
        if n:
            removed.append(f"<{tag}>×{n}")
    out, n_on = re.subn(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", out, flags=re.IGNORECASE)
    if n_on:
        removed.append(f"on*×{n_on}")
    out, n_url = re.subn(
        r"""((?:href|src)\s*=\s*["'])(?:\s*(?:javascript|data:text/html)[^"']*)(["'])""",
        r"\1#\2", out, flags=re.IGNORECASE,
    )
    if n_url:
        removed.append(f"dangerous-url×{n_url}")
    return out, removed


# ============================================================
# 内容底线：退化为会议复述即拒收 / Recap floor
# ============================================================
#
# 洞察板唯一任务是「针对会议暴露的困境给出 AI 最优解法」；决策清单、议题归类、
# 决策分工、谁说了什么已由逐字稿、纪要页、决策中心承载。模型的保守倾向是把
# 会议内容结构化再抄一遍，故落盘前做启发式兜底：命中复述骨架即整份拒收，
# 理由经工具结果回传 AI 形成自纠循环；旧板不动（拒收不写盘，原子语义）。

# (节标题命中模式, 人话解释) / (bad section-title pattern, human label)
_RECAP_TITLE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"决策流|待确认决策|决策清单|决策列表|决议事项|决议清单"), "决策清单（决策中心已承载）"),
    (re.compile(r"议题归类|议题梳理|议题清单|议题列表|讨论议题"), "议题归类（纪要章节已承载）"),
    (re.compile(r"决策追踪|决策事项|决策清单|决策列表|待办追踪|待办事项|待办清单|待办列表|行动项清单|任务分工|人员分工|分工表"), "决策/分工清单（纪要决策已承载）"),
    (re.compile(r"会议全景|会议概览|会议纪要|纪要概览|会议总结|会议摘要"), "会议全景/纪要复述"),
    (re.compile(r"风险与未决|风险清单|风险梳理|未决事项"), "风险罗列式节（困境必须紧跟解法，不许只罗列）"),
)
# 标题含解法向信号时豁免标题扣分（如「风险与解法」）/ Solution-flavoured titles are exempt
_SOLUTION_TITLE_HINT = re.compile(r"解法|解决方案|对策|破局|锦囊|最优方案")
_TITLE_ATTR_RE = re.compile(r'data-ib-title=["\']([^"\']+)["\']', re.IGNORECASE)
_HEADING_RE = re.compile(r"<h[1-4]\b[^>]*>(.*?)</h[1-4]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_DC_CODE_RE = re.compile(r"DC[-－\s]*\d", re.IGNORECASE)
_TOPIC_CODE_RE = re.compile(r"议题\s*[0-9０-９]")
_SPEAKER_REF_RE = re.compile(r"说话人\s*[0-9０-９]|Speaker\s*[0-9]", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"依据[：:][^。；\n]{0,40}(?:说话人|Speaker)", re.IGNORECASE)
_DEADLINE_RE = re.compile(r"截止|deadline|\d{1,2}\s*月\s*\d{1,2}\s*日", re.IGNORECASE)
_RECAP_STAT_LABELS = ("待确认决策", "议题归类", "决策事项", "待办事项")

# 文字墙检测：顶层节与其主视觉标记 / Section + diagram-marker extraction
_SECTION_RE = re.compile(r"<section\b[^>]*\bdata-ib-id\b[^>]*>(.*?)</section>",
                         re.IGNORECASE | re.DOTALL)
# 主视觉判据按**形态**而非类名（版权归 CLI，应用只守内容底线）：
# 内联 SVG / canvas / data URI 图片三项无争议；table 与纯 CSS 条形不计入——
# 把结构化文字当图等于把门槛降到形同虚设。
# 相对路径的 <img> 不计图：srcdoc 与 raw 端点两处出口的 base 解析不一致（见 4.5-4）。
# 末尾的 .ib-* 类名为 legacy 识别，仅为存量板保留一个版本周期。
_VISUAL_MARK_RE = re.compile(
    r"""<svg\b|<canvas\b|<img\b[^>]*\bsrc=\s*"?data:image|"""
    r"""class=["'][^"']*\b(?:ib-flow|ib-tree|ib-compare|ib-grid|ib-visual)\b""",
    re.IGNORECASE)

# 主视觉载体之一：mermaid 源码 pre（不认类名——任意 <pre> 只要首词命中图类型即计图，
# 前端显示时由桥接渲染；落盘存源码，AI 读基线时看到的也是源码）
_MERMAID_PRE_RE = re.compile(r"<pre\b[^>]*>(.*?)</pre>", re.IGNORECASE | re.DOTALL)
# mermaid 首词白名单：flowchart/graph 流程、sequenceDiagram 时序、stateDiagram 状态、
# mindmap/timeline 兜底形态；首词不在列 = 模型没写真图，不计主视觉
_MERMAID_TYPES = ("flowchart", "graph", "sequenceDiagram", "stateDiagram-v2",
                  "stateDiagram", "mindmap", "timeline")
_MERMAID_DIRECTIVE_RE = re.compile(r"^%%\{.*\}%%\s*$")

_TEXT_WALL_GUIDANCE = (
    "洞察板是图不是文章：每个困境一节，先画后主文，纯文字段落/列表组成的节不允许落盘。"
    "请为每个节补一个主视觉，形态任选其一："
    "① 内联 <svg>（自己画图，资源一律 data URI 内联）；"
    "② mermaid 形态的 <pre>（首词必须是 flowchart/graph/sequenceDiagram/stateDiagram/mindmap/timeline 等图类型关键字）；"
    "③ <canvas>；④ src 为 data URI 的 <img>。"
    "mermaid 边标签是标配：A -->|标签| B；节点文字≤12 字、每图≤10 节点；"
    "源码内禁写 < > &（用「小于」「与」等中文替代，防止截断 HTML）、禁 click 语句。"
    "表格、div 条块不计主视觉。版式与样式由你自己负责，改完整份重新提交。"
)


def _mermaid_pre_ok(inner: str) -> bool:
    """mermaid pre 内容是否有效：非空白且首个非指令行以图类型白名单开头。"""
    for raw in (inner or "").splitlines():
        line = raw.strip()
        if not line or _MERMAID_DIRECTIVE_RE.match(line):
            continue
        return line.split()[0] in _MERMAID_TYPES if line.split() else False
    return False


def _section_has_visual(body: str) -> bool:
    """节是否含有效主视觉。

    节内出现 pre.ib-mermaid 即切换到严格判定（空 pre / 首词非图类型不计图），
    否则走旧标记超集（ib-flow 等 legacy 组件与内联 <svg>），向后兼容旧板
    在单节共创 merge 后的整板校验。
    """
    pres = _MERMAID_PRE_RE.findall(body)
    if pres:
        return any(_mermaid_pre_ok(inner) for inner in pres)
    return bool(_VISUAL_MARK_RE.search(body))

_RECAP_GUIDANCE = (
    "洞察板的唯一任务是针对本场会议暴露的困境，给出会上没人想到的 AI 最优解法"
    "（你被授权调用外部行业知识、标准实践、成熟架构来构造解法），而不是整理会议内容。"
    "请重做整份 HTML：每节按「困境（一句话界定）→ 外部最优解法（具体可执行，附原理或出处）→ 落地步骤与取舍」组织；"
    "删除决策清单（含 DC 编号）、议题/章节归类、决策分工（谁做什么、截止日期）、参会人立场与「谁说了什么」、"
    "带说话人/时间戳的依据流水、会议概览与摘要复述——这些逐字稿、纪要页、决策中心已经承载；"
    "风险与未决项每条必须紧跟一个可落地解法，不许只罗列问题。"
    "若读取到的旧基线本身就是复述结构，直接推倒重做为解法结构，不受版式继承条款约束。"
)


def _board_text_and_titles(board_html: str) -> tuple[str, list[str]]:
    """提取板纯文本与节标题（data-ib-title 属性 + h1-h4）/ Plain text + section titles."""
    titles = [m.strip() for m in _TITLE_ATTR_RE.findall(board_html) if m.strip()]
    for raw in _HEADING_RE.findall(board_html):
        t = _TAG_RE.sub("", raw).strip()
        if t:
            titles.append(t)
    text = _html_unescape(_TAG_RE.sub(" ", board_html))
    return re.sub(r"\s+", " ", text), titles


def detect_recap_floor(board_html: str) -> list[str]:
    """启发式检测板是否退化为会议复述；返回拒收理由（空列表 = 通过）。
    Detect meeting-recap degeneration; non-empty reasons reject the save.

    五类互相独立的复述信号各计 1 分，≥2 分才拒收：单一弱信号（如一节标题
    起得像决策、正文却是解法）不阻断，避免误伤真正的解法型板。
    """
    text, titles = _board_text_and_titles(board_html or "")
    score = 0
    reasons: list[str] = []

    bad_titles: list[str] = []
    for t in titles:
        if _SOLUTION_TITLE_HINT.search(t):
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
        reasons.append("DC/议题编号罗列（DC-1、议题1 等——决策与纪要已有各自编号体系）")

    stat_hits = [w for w in _RECAP_STAT_LABELS if w in text]
    if len(stat_hits) >= 2:
        score += 1
        reasons.append("决策/议题/决策统计徽标：" + "、".join(stat_hits))

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


def detect_text_wall(board_html: str) -> tuple[int, int]:
    """检测板是否退化为纯文字墙；返回 (节总数, 含主视觉的节数)。

    仅统计顶层 <section data-ib-id> 节（节不嵌套是共创契约）。判定阈值由调用方
    持有：n==0（自由片段，非节式板）不阻断；n==1 该节必须有图；n>=2 允许
    至多 1 节无图（内容确不适合成图时的容错），否则拒收。
    """
    sections = _SECTION_RE.findall(board_html or "")
    if not sections:
        return 0, 0
    visual = sum(1 for body in sections if _section_has_visual(body))
    return len(sections), visual


# ============================================================
# 板存储模型：一场会议多份板（manifest 为唯一权威）
# ============================================================
#
# 文件命名 `data/tasks/<task_id>.board.<board_id>.html`；per-board 版本信息内联在
# manifest `<task_id>.boards.json` 里（少一次读盘；前端轮询一次请求拿全部 revision）。
# 【硬不变量】板只在 manifest 内存在才可写：未知 board_id 一律拒，绝不隐式建板——
# 只要「写个不存在的 board_id 就顺手建出来」还成立，“仅用户显式新建”就只是一句文案。
# 建板因此只剩两条通道：用户点「＋ 新建板」（POST）或 AI 提案被用户接受（同一个 POST）。

DEFAULT_BOARD_ID = "main"  # 存量迁移目标与缺省板
DEFAULT_BOARD_TITLE = "主看板"
BOARD_TITLE_MAX = 60
_BOARD_ID_RE = re.compile(r"^[\w-]{1,48}$")


def _valid_board_id(board_id: str) -> bool:
    """board_id 可入文件名且无穿越面 / Safe board id for filenames."""
    return bool(board_id) and bool(_BOARD_ID_RE.match(board_id))


def _legacy_html_path(task_id: str) -> Path:
    return BOARD_TASKS_DIR / f"{task_id}.board.html"


def _manifest_path(task_id: str) -> Path:
    return BOARD_TASKS_DIR / f"{task_id}.boards.json"


def _board_file_path(task_id: str, board_id: str) -> Path:
    return BOARD_TASKS_DIR / f"{task_id}.board.{board_id}.html"


def _migrate_legacy_board(task_id: str, manifest: dict) -> dict:
    """旧单文件板就地重命名为 main 并生成 manifest（一次性、幂等、不复制不丢版本）。

    不留「老文件名也认」的双读分支——那条分支会让 manifest、错字回溯、上下文导出、
    测试清理等每处消费者各背一份兼容代码。
    """
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
                (BOARD_TASKS_DIR / f"{task_id}.board.meta.json").read_text(encoding="utf-8"))
            rev, upd = int(legacy_meta.get("revision") or 0), legacy_meta.get("updated_at")
        except (OSError, ValueError, TypeError):
            rev, upd = 1, int(time.time() * 1000)
    else:
        rev, upd = 0, None  # 目标已存在：旧文件只清理，不覆盖已有版本
    try:
        (BOARD_TASKS_DIR / f"{task_id}.board.meta.json").unlink()
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
    """读 manifest；缺文件时先尝试存量迁移，再返回内存态骶架（不落盘，建板才落）。

    板数 = 0（既无 manifest 又无旧文件）时自动包含 revision=0 的 main 条目，
    否则首版共创会被 unknown_board_id 拦住——用户无需为「第一份板」点新建。
    """
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
    """对外只读视图 / Public manifest view.

    Returns: {boards: [{board_id, title, revision, updated_at, exists}], default_board_id}。
    exists 区分「已建板但尚未写 HTML」（提案/新建后 revision=0）与真无板。
    """
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
    """服务端生成缺省 board_id：board-2、board-3… / Auto board id sequence."""
    used = {str(b.get("board_id") or "") for b in manifest.get("boards") or []}
    n = 2
    while f"board-{n}" in used:
        n += 1
    return f"board-{n}"


def invoke_create_board(task_id: str, arguments: dict) -> dict:
    """建板的唯一执行点（只写 manifest 条目，不产生 HTML 文件）。

    调用方必须是“用户意志”的出口：前端「＋ 新建板」按钮，或 create_insight_board
    提案被用户点「接受」后的同一个 POST 端点。工具面不得直接调用本函数。
    空板不落 0 字节文件：HTML 留到首次 revise_insight_board 时创建。
    """
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
    """读取指定板的 HTML 产物；无板/坏板返回 None / Load board HTML artifact, None if absent.

    board_id 缺省取 manifest 的 default_board_id；revision 来自 manifest（内联版本信息）。
    刚建未写的板 manifest 有条目但无文件，此处统一返 None。
    """
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
    """只读板版本信息（不读 HTML 正文）/ Read board revision metadata only.

    返回 / Returns: {revision, updated_at, exists, board_id}；task_id 非法返回 None。
    多板下 board_id 缺省时返回 **全部板** 的 revision 列表（一次请求拿全部版本，
    供前端轮询比对）；单份呈现仍以 revision/updated_at/exists 字段为主（向后兼容）。
    """
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
    """清洗后整份落盘（revision+1）；非法输入不落盘 / Sanitize-then-save, revision+1.

    content_floor=True（默认，AI 共创路径）：额外执行复述/文字墙内容底线校验；
    content_floor=False：仅安全清洗，供系统级机械改写（如错字纠正回写）使用——
    旧板的内容形态不应在机械替换时被新规则否决。

    board_id 缺省取 manifest 的 default_board_id；**不在 manifest 内一律拒写**（unknown_board_id），
    绝不隐式建板——建板权属于用户（见 invoke_create_board）。

    expected_revision：R2 后基线可能来自上一轮导出的 `context/boards/` 快照，
    期间用户可能在另一个窗口共创过；不匹配则不落盘（stale_baseline）。
    不传（None）保持旧覆盖语义，避免一次性收紧造成大面积拒写。

    返回 / Returns: {ok, revision?, removed?, board_id?, error?, current_revision?, boards?}
    """
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
        # 内容底线：复述型板整份拒收，理由回传 AI 自纠（旧板保持不动）/ Recap floor
        recap_reasons = detect_recap_floor(cleaned)
        if recap_reasons:
            logger.info("[洞察板] 复述底线拒收 task=%s: %s", task_id, recap_reasons)
            return {"ok": False, "error": "board_is_recap", "reasons": recap_reasons,
                    "guidance": _RECAP_GUIDANCE, "removed": removed}
        # 图形化底线：节式板必须先画后主文，纯文字墙拒收 / Diagram-first floor
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


# 合法节锈点 id（供寻址与正则安全） / Safe section id charset
_SECTION_ID_RE = re.compile(r"^[\w-]{1,64}$")


def _section_pattern(section_id: str) -> re.Pattern:
    """定位顶层节块（约定节不嵌套，故非贪婪到首个 </section>）。"""
    return re.compile(
        r'<section\b[^>]*\bdata-ib-id=["\']' + re.escape(section_id) + r'["\'][^>]*>.*?</section>',
        re.DOTALL | re.IGNORECASE,
    )


def board_html_save_section(task_id: str, section_id: str, section_html: str,
                            board_id: str | None = None) -> dict:
    """只替换指定板内 data-ib-id 的那一节，其余节逐字节不动（硬隔离）。

    返回 / Returns: {ok, revision?, section_id?, board_id?, error?}
    前提：板已存且顶层节包为 <section data-ib-id="...">（不嵌套）。
    新节若缺 data-ib-id 会被归一补回，保证寻址稳定。
    未知 board_id 同样拒绝（建板权在用户）。
    """
    if not _valid_task_id(task_id):
        return {"ok": False, "error": "invalid_task_id"}
    if not isinstance(section_id, str) or not _SECTION_ID_RE.match(section_id):
        return {"ok": False, "error": "invalid_section_id"}
    if not isinstance(section_html, str) or not section_html.strip():
        return {"ok": False, "error": "empty_section"}
    cleaned, _removed = sanitize_board_html(section_html)
    if not cleaned.strip():
        return {"ok": False, "error": "section_empty_after_sanitize"}
    # 归一：若新节未带 data-ib-id，补上当前 id，保证下次仍可寻址
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
    # expected_revision 取刚读到的版本：单节补丁也能发现“读后被人抢先写过”
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
    """revise_insight_board 工具的唯一实现（读写双语义）。

    两处消费（防定义漂移，同 catalog 单一来源原则）：
      - core.agent_tools.impl.execute_tool（会议域工具唯一实现）
      - app.routers.agent_tools._dispatch_write（CLI 智能体经 MCP 桥回连）
    不带 html = 读（返回 manifest 摘要，让 CLI 先选目标；带 board_id 则读那份板的正文）；
    带 html = 整份清洗后落盘 rev+1。
    """
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
    # removed 原样回传：磁盘字节 = 提交内容 − removed，不允许静默变异
    return {"ok": True, "revision": res["revision"], "board_id": res["board_id"],
            "removed": res.get("removed", []),
            "info": "洞察板已更新，前端板区会自动重拉（点「刷新」可立即对齐）"}

