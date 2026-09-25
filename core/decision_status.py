"""
core/decision_status.py — 决策状态字典 / Decision status dictionary

作者：Yongliang Wang
创建：2026-09-25
版本：1.0.0

职责（REQ-DECISION-CENTER-R2 · DC-R2-c · 项目方裁决 D6/D7）：
  1. 决策状态从封闭枚举改为**用户可维护的状态字典**（改名 / 新增 / 删除 / 排序 / 标色）
  2. 系统锚点只有两个：`active`（生效中，新决策默认态）与 `done`（完成，唯一保底闭档态），
     二者不可改名、不可删除（D6：项目方明确「只留完成，砍掉这两项」）
  3. 每个状态携带 `closing` 布尔（是否算「完成类」）：闭档状态在默认视图隐藏并沉底（D7）
  4. 历史 `superseded` / `revoked` 两态在迁移时落为**普通可编辑状态**（默认名保留、闭档=是），
     因此存量 task JSON 的 status 值仍然合法，**零改写**（数据诚实）

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

# 系统锚点：不可改名、不可删除（D6）
SYSTEM_ANCHORS = ("active", "done")

STATUS_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,32}$")
NAME_MAX = 20


class StatusError(ValueError):
    """状态字典校验失败（路由层转 400/422）。"""


def _defaults() -> list[dict]:
    """内置四态：两个系统锚点 + 两个由历史枚举迁移而来的可编辑状态。

    颜色允许 CSS 变量表达式（前端内联使用，随主题联动）或十六进制色值。
    """
    now = datetime.now().isoformat()
    items = [
        {"id": "active", "name": "生效中", "name_en": "Active", "color": "var(--st-done)", "closing": False, "system": True},
        {"id": "done", "name": "完成", "name_en": "Done", "color": "var(--accent)", "closing": True, "system": True},
        # 取代/撤销不再是系统行为（D6），但历史数据仍带这两个值 → 保留为可改名可删除的普通状态
        {"id": "superseded", "name": "已被取代", "name_en": "Superseded", "color": "var(--st-decide)", "closing": True, "system": False},
        {"id": "revoked", "name": "已撤销", "name_en": "Revoked", "color": "var(--error)", "closing": True, "system": False},
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
    if not out or not set(SYSTEM_ANCHORS).issubset(seen):
        logger.info("决策状态字典缺少系统锚点，回退默认集合")
        return _defaults()
    return out


def load_statuses() -> list[dict]:
    """读取状态字典；文件不存在时落盘默认集合（首次迁移）。"""
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
    return _sanitize(raw)


def save_statuses(statuses: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(STATUSES_FILE, statuses)


def get_status(sid: str) -> dict | None:
    return next((s for s in load_statuses() if s["id"] == sid), None)


def known_ids() -> set[str]:
    return {s["id"] for s in load_statuses()}


def validate_status_id(sid: object) -> str:
    """校验写入决策的 status：必须是字典中存在的 id，否则 StatusError。

    存量数据里若存在字典外的历史值（例如用户删掉了自定义状态后残留），
    由调用方（聚合/读取路径）按 active 降级，不在读路径抛错。
    """
    value = str(sid or "").strip()
    if not value:
        raise StatusError("status is required")
    if value not in known_ids():
        raise StatusError(f"unknown status: {value}")
    return value


def closing_ids() -> set[str]:
    return {s["id"] for s in load_statuses() if s["closing"]}


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
        "color": color or "var(--muted)",
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
        target["color"] = str(color).strip() or target["color"]
    if closing is not None:
        if target["system"] and bool(closing) != target["closing"]:
            raise StatusError("系统锚点状态的「算完成类」属性不可修改")
        target["closing"] = bool(closing)
    target["updated_at"] = datetime.now().isoformat()
    save_statuses(statuses)
    return target


def delete_status(sid: str) -> dict:
    """删除自定义状态。系统锚点不可删；被删状态下的决策由调用方回落到 active。"""
    statuses = load_statuses()
    target = next((s for s in statuses if s["id"] == sid), None)
    if target is None:
        raise StatusError(f"unknown status: {sid}")
    if target["system"]:
        raise StatusError("系统锚点状态不可删除")
    save_statuses([s for s in statuses if s["id"] != sid])
    return {"removed": sid, "reassign_to": "active"}


def reorder(order: list[str]) -> list[dict]:
    """按给定 id 序列重排（缺项追加在后，多项视为非法）。"""
    statuses = load_statuses()
    by_id = {s["id"]: s for s in statuses}
    wanted = [i for i in order if i in by_id]
    if len(wanted) != len(set(wanted)) or set(wanted) != set(by_id):
        raise StatusError("排序请求必须完整覆盖全部状态且不重复")
    return [by_id[i] for i in wanted]
