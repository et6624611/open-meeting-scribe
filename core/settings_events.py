"""
core/settings_events.py — 设置侧本地事件记录 / Local settings event log

REQ-SETTINGS-IA §3.5（Q3 终裁）：体验配额「自动改用」每次发生必须落本地事件记录，
用于账单争议追溯（L1/L2/L3 三级提示的数据源之一）。

存储：data/settings_events.json（原子写入，环形截断保留最近 MAX_EVENTS 条）。
事件为只增审计记录，不参与路由判定；消费方通过
GET /api/settings/routing 的 recent_events 摘要回显。
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from core.fs_atomic import atomic_write_json

logger = logging.getLogger(__name__)

EVENTS_FILE = Path("data/settings_events.json")
MAX_EVENTS = 200


def record_event(event_type: str, **fields) -> dict:
    """追加一条事件记录并持久化。返回写入的事件体。

    event_type 枚举（当前）：
      - "auto_switch"  配额耗尽 / Key 缺失导致的明示自动改用（§3.5）
    """
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "type": event_type,
        **{k: v for k, v in fields.items() if v is not None},
    }
    try:
        events = []
        if EVENTS_FILE.exists():
            import json
            try:
                events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
                if not isinstance(events, list):
                    events = []
            except Exception:
                events = []
        events.append(event)
        if len(events) > MAX_EVENTS:
            events = events[-MAX_EVENTS:]
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(EVENTS_FILE, events)
    except Exception as e:
        logger.warning(f"[设置事件] 记录失败（不影响主流程）: {e}")
    return event


def recent_events(limit: int = 20) -> list[dict]:
    """读取最近 N 条事件（缺文件/损坏返回空列表，绝不抛异常）。"""
    if not EVENTS_FILE.exists():
        return []
    import json
    try:
        events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        if isinstance(events, list):
            return events[-limit:]
    except Exception:
        pass
    return []
