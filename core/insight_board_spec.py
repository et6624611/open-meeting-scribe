"""
core/insight_board_spec.py — 洞察板 Board Spec v0.3（已退役，保留供追溯）

随「洞察共创 · 会话驱动（HTML 产物版）」下线：
- Board Spec 校验（validate_board / _validate_zone / _validate_cell / _infer_cell_kind）
- zone patch 操作的原子合并（apply_ops）
- 板 JSON 持久化（<task_id>.board.json）
- 板生成分析 run_board_analysis（LLM 输出 zone patch ops 而非单卡）

实现从 core/insight_board.py 拆出，保持行为零变化。
"""

import copy
import json
import logging
from pathlib import Path

from core.fs_atomic import atomic_write_json
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


class BoardValidationError(ValueError):
    """【已退役】Board Spec / ops 校验失败，携带可读错误列表 / Raised with a human-readable error list."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors)[:400])


def _clean_text(value, cap: int) -> str:
    if not isinstance(value, str):
        raise BoardValidationError([f"期望字符串，实际为 {type(value).__name__}"])
    return value.strip()[:cap]


def _opt_ms(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return None


def _infer_cell_kind(cell: dict) -> str | None:
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

    return {"kind": "note", "text": _clean_text(cell.get("text", ""), CAP_TEXT)}


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


def apply_ops(board: dict, ops: list, now_ms: int | None = None) -> dict:
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
        else:
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


def board_path(task_id: str, base: Path | None = None) -> Path:
    return (base or BOARD_TASKS_DIR) / f"{task_id}.board.json"


def load_board(task_id: str, base: Path | None = None) -> dict | None:
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
    if not board:
        return "（尚无板——本轮生成建立初始 zone）"
    lines = []
    for z in board["zones"]:
        kinds = ",".join(c["kind"] for c in z["cells"])
        lines.append(f"- [{z['status']}/{z['maturity']}] {z['id']}「{z['title']}」{z['summary']}（cells: {kinds}）")
    return "\n".join(lines)


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
    empty = {"ok": False, "board": None, "errors": ["insufficient_input"], "raw_ops": [], "failure_class": "input"}
    if not recent_lines or not chapter_titles:
        return empty

    system_prompt = BOARD_ANALYSIS_PROMPT
    if role_name:
        from core.agent_workspace import get_role_insight_prompt
        role_prompt = get_role_insight_prompt(role_name)
        if role_prompt:
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
