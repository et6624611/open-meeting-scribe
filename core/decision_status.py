"""
core/decision_status.py — 决策状态字典 / Decision status dictionary

作者：Yongliang Wang
创建：2026-09-25
版本：1.0.0

职责（REQ-DECISION-CENTER-R2 · DC-R2-c · 裁决 D6/D7 → DC-UNIFY-01 收敛为单一决策流 → 2026-09-28 精简为三态）：
  1. 决策状态是**用户可维护的状态字典**（改名 / 新增 / 删除 / 排序 / 标色）
  2. 字典的默认集合 = **决策流三态**（待决策 / 进行中 / 已完成），
     因为决策流（`task["todos"]`）是唯一的决策对象；系统锚点只有 `done`（已完成），
     不可改名不可删除，其余两态用户可自由维护（D6 口径：只固定完成为系统保底）
  3. 每个状态携带 `closing` 布尔（是否算「完成类」）：闭档状态在默认视图隐藏并沉底（D7），
     同时驱动 todo.done 旧字段同步（兼容只认布尔的读侧）
  4. 一次性迁移：剪除未被用户改过名的旧遗留态（active/superseded/revoked）与已退役的五态
     （to_start/to_confirm），补齐缺失的三态种子；残留携带退役态的节点由读侧降级到首个开放态

存储：data/decision_statuses.json（用户数据，已 gitignore），原子写。
"""

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from core.fs_atomic import atomic_write_json

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
STATUSES_FILE = DATA_DIR / "decision_statuses.json"

# 系统锚点：不可改名、不可删除（done=保底完成态；superseded=被新决策替代的闭档态，
# 由决策演变链「标记已被替代」动作写入——语义独立于完成，不可被用户字典删改导致动作断链）
SYSTEM_ANCHORS = ("done", "superseded")

# 新建决策流节点的默认状态（开放首态）
DEFAULT_STATUS_ID = "to_decide"

# 被新决策替代的系统闭档态（决策演变链「标记已被替代」动作写入）
SUPERSEDED_STATUS_ID = "superseded"

# 决策流状态种子：id 沿用历史枚举值，保证存量 task JSON 的 todo.status 零迁移合法
FLOW_STATUS_IDS = ("to_decide", "in_progress", "done", "superseded")

# 五态精简为三态后退役的历史态：这些 id 只可能由系统种子产生（用户自建态 id 形如 st-xxxx），
# 故按 id 无条件剪除；携带这些态的存量节点由读侧降级到首个开放态（to_decide）
RETIRED_FLOW_STATUS_IDS = ("to_start", "to_confirm")

# 旧版（decision 对象时代）的遗留态：未被用户改过名则在迁移时剪除
LEGACY_STATUS_NAMES = {
    "active": "生效中",
    "superseded": "已被取代",
    "revoked": "已撤销",
}

STATUS_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,32}$")
NAME_MAX = 20

# 旧色板硬编码 hex → 主题语义令牌的归一表。
# 这些 hex 本就是系统色板提供的选项，归一为令牌后随 10 套主题（含暗色）联动；
# 用户自行输入的其他 hex 不在表内，保持原样（尊重用户显式选择）。
HEX_COLOR_ALIASES = {
    "#2563eb": "var(--info)",
    "#0d9488": "var(--mine)",
    "#d97706": "var(--warn)",
    "#dc2626": "var(--error)",
    "#7c3aed": "var(--purple)",
    "#64748b": "var(--subtle)",
}


def _normalize_color(color: object) -> str:
    """颜色值归一：表内 hex（大小写不敏感）映射为令牌，其余原样返回。"""
    value = str(color or "").strip()
    return HEX_COLOR_ALIASES.get(value.lower(), value)


class StatusError(ValueError):
    """状态字典校验失败（路由层转 400/422）。"""


def _defaults() -> list[dict]:
    """内置决策流状态：两个可编辑开放态 + 两个系统保底闭档态（完成 / 已替代）。

    颜色允许 CSS 变量表达式（前端内联使用，随主题联动）或十六进制色值。
    """
    now = datetime.now().isoformat()
    items = [
        {"id": "to_decide", "name": "待决策", "name_en": "To decide", "color": "var(--st-decide)", "closing": False, "system": False},
        {"id": "in_progress", "name": "进行中", "name_en": "In progress", "color": "var(--st-progress)", "closing": False, "system": False},
        {"id": "superseded", "name": "已替代", "name_en": "Superseded", "color": "var(--subtle)", "closing": True, "system": True},
        {"id": "done", "name": "已完成", "name_en": "Done", "color": "var(--st-done)", "closing": True, "system": True},
    ]
    return [{**i, "created_at": now, "updated_at": now} for i in items]


def _sanitize(raw: object) -> list[dict]:
    """把磁盘数据收敛为合法列表；缺锚点/结构异常即整体回退默认（宁可回默认不可留脏态）。"""
    if not isinstance(raw, list) or not raw:
        return _defaults()
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()[:NAME_MAX]
        if not sid or not name or sid in seen:
            continue
        seen.add(sid)
        out.append({
            "id": sid,
            "name": name,
            "name_en": str(item.get("name_en") or name)[:NAME_MAX],
            "color": str(item.get("color") or "var(--muted)"),
            "closing": bool(item.get("closing", False)),
            # system 位以常量表为准，避免磁盘被改写后锚点失守
            "system": sid in SYSTEM_ANCHORS,
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
        })
    # 只把「连保底完成态都没有」视为脏结构整体回退；其余锚点（如 superseded）缺失
    # 交由 _seed_flow_statuses 补种子，避免为补系统态而丢弃用户自定义状态
    if not out or "done" not in seen:
        logger.info("决策状态字典缺少保底锚点 done，回退默认集合")
        return _defaults()
    return out


def _seed_flow_statuses(items: list[dict]) -> tuple[list[dict], bool]:
    """一次性迁移：剪除未改名的旧遗留态与已退役的五态 + 补齐缺失的决策流三态种子。

    返回 (列表, 是否发生变更)；变更时由调用方落盘，保证下次启动幂等。
    """
    changed = False
    kept: list[dict] = []
    for s in items:
        if s["id"] in LEGACY_STATUS_NAMES and s["name"] == LEGACY_STATUS_NAMES[s["id"]]:
            changed = True   # 旧 decision 时代的遗留态，且用户从未改过名 → 不再占位
            continue
        if s["id"] in RETIRED_FLOW_STATUS_IDS:
            changed = True   # 五态→三态退役：to_start/to_confirm 由系统种子产生，直接剪除
            continue
        kept.append(s)
    have = {s["id"] for s in kept}
    missing = [d for d in _defaults() if d["id"] not in have]
    if missing:
        changed = True
        # 插到第一个闭档状态之前，保住「完成」沉底的阅读直觉；无闭档则追加尾部
        at = next((i for i, s in enumerate(kept) if s["closing"]), len(kept))
        kept[at:at] = missing
    return kept, changed


def _normalize_hex_aliases(items: list[dict]) -> tuple[list[dict], bool]:
    """把旧色板 hex 归一为主题令牌；返回 (新列表, 是否发生变更)。"""
    changed = False
    out: list[dict] = []
    for s in items:
        old_color = str(s.get("color") or "")
        new_color = _normalize_color(old_color)
        if new_color != old_color.strip():
            changed = True
        out.append({**s, "color": new_color})
    return out, changed


def load_statuses() -> list[dict]:
    """读取状态字典；文件不存在时落盘默认集合，存在旧结构时自动迁移并回写。"""
    if not STATUSES_FILE.exists():
        defaults = _defaults()
        save_statuses(defaults)
        return defaults
    try:
        import json
        raw = json.loads(STATUSES_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # 脏文件不阻断决策中心
        logger.warning(f"决策状态字典读取失败，回退默认：{exc}")
        return _defaults()
    normalized, alias_changed = _normalize_hex_aliases(_sanitize(raw))
    statuses, changed = _seed_flow_statuses(normalized)
    if alias_changed:
        changed = True
    if changed:
        logger.info("决策状态字典已迁移（结构/颜色令牌归一），已回写")
        save_statuses(statuses)
    return statuses


def save_statuses(statuses: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(STATUSES_FILE, statuses)


def get_status(sid: str) -> dict | None:
    return next((s for s in load_statuses() if s["id"] == sid), None)


def known_ids() -> set[str]:
    return {s["id"] for s in load_statuses()}


def validate_status_id(sid: object) -> str:
    """校验写入决策流节点的 status：必须是字典中存在的 id，否则 StatusError。

    存量数据里若存在字典外的历史值（例如用户删掉了自定义状态后残留），
    由调用方（聚合/读取路径）按 `DEFAULT_STATUS_ID` 降级，不在读路径抛错。
    """
    value = str(sid or "").strip()
    if not value:
        raise StatusError("status is required")
    if value not in known_ids():
        raise StatusError(f"unknown status: {value}")
    return value


def closing_ids() -> set[str]:
    return {s["id"] for s in load_statuses() if s["closing"]}


def is_closing(sid: object) -> bool:
    """某状态是否算「完成类」；字典外的未知值视为未闭档。"""
    meta = get_status(str(sid or ""))
    return bool(meta and meta["closing"])


def default_visible_ids() -> set[str]:
    """默认视图 = 全部非闭档状态（D7）。"""
    return {s["id"] for s in load_statuses() if not s["closing"]}


def create_status(name: str, color: str = "", closing: bool = False) -> dict:
    name = str(name or "").strip()[:NAME_MAX]
    if not name:
        raise StatusError("状态名称不能为空")
    existing = load_statuses()
    if any(s["name"] == name for s in existing):
        raise StatusError("已存在同名状态")
    now = datetime.now().isoformat()
    item = {
        "id": f"st-{uuid.uuid4().hex[:8]}",
        "name": name,
        "name_en": name,          # 自定义状态不参与双语内置名
        "color": _normalize_color(color) or "var(--muted)",
        "closing": bool(closing),
        "system": False,
        "created_at": now,
        "updated_at": now,
    }
    existing.append(item)
    save_statuses(existing)
    return item


def update_status(sid: str, name: object = None, color: object = None, closing: object = None) -> dict:
    """改名 / 标色 / 改闭档位。系统锚点仅允许改颜色（D6：不可改名）。"""
    statuses = load_statuses()
    target = next((s for s in statuses if s["id"] == sid), None)
    if target is None:
        raise StatusError(f"unknown status: {sid}")
    if name is not None:
        new_name = str(name).strip()[:NAME_MAX]
        if not new_name:
            raise StatusError("状态名称不能为空")
        if target["system"] and new_name != target["name"]:
            raise StatusError("系统锚点状态不可改名")
        if any(s["name"] == new_name and s["id"] != sid for s in statuses):
            raise StatusError("已存在同名状态")
        target["name"] = new_name
        if not target["system"]:
            target["name_en"] = new_name
    if color is not None:
        target["color"] = _normalize_color(color) or target["color"]
    if closing is not None:
        if target["system"] and bool(closing) != target["closing"]:
            raise StatusError("系统锚点状态的「算完成类」属性不可修改")
        target["closing"] = bool(closing)
    target["updated_at"] = datetime.now().isoformat()
    save_statuses(statuses)
    return target


def delete_status(sid: str) -> dict:
    """删除自定义状态。系统锚点不可删；被删状态下的节点由调用方回落到默认开放态。"""
    statuses = load_statuses()
    target = next((s for s in statuses if s["id"] == sid), None)
    if target is None:
        raise StatusError(f"unknown status: {sid}")
    if target["system"]:
        raise StatusError("系统锚点状态不可删除")
    save_statuses([s for s in statuses if s["id"] != sid])
    # 回落目标在删后字典里取首个开放态（默认态本身也可能被用户删掉）
    remaining = load_statuses()
    fallback = next((s["id"] for s in remaining if not s["closing"]), DEFAULT_STATUS_ID)
    return {"removed": sid, "reassign_to": fallback}


def reorder(order: list[str]) -> list[dict]:
    """按给定 id 序列重排（缺项追加在后，多项视为非法）。"""
    statuses = load_statuses()
    by_id = {s["id"]: s for s in statuses}
    wanted = [i for i in order if i in by_id]
    if len(wanted) != len(set(wanted)) or set(wanted) != set(by_id):
        raise StatusError("排序请求必须完整覆盖全部状态且不重复")
    return [by_id[i] for i in wanted]
