"""
core/remote_config.py — 远程配置管理 / Remote configuration management

职责 / Responsibilities:
  1. 管理 data/remote_config.json 的读写 / Manage data/remote_config.json read/write
  2. 消息 CRUD（创建、更新、删除、启用/禁用） / Message CRUD (create, update, delete, enable/disable)
  3. 客户端消息过滤（按 target、有效期、enabled 过滤） / Client-side message filtering (by target, validity, enabled)

数据模型 / Data model:
  {
    "messages": [ ... ],
    "feature_flags": [
      {
        "id": "ff_xxx",
        "name": "realtime_asr",     // 标识名（唯一） / Identifier (unique)
        "description": "实时 ASR",   // 描述 / Description
        "enabled": true,
        "target": "all",            // all | tier:free | tier:personal | tier:pro | tier:team | users
        "target_users": [],         // target=users 时存放具体 user_id 列表 / User ID list when target=users
        "created_at": "...",
        "updated_at": "..."
      }
    ],
    "version": 1
  }
"""

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_FILE = Path("data/remote_config.json")


def _load_config() -> dict:
    """读取远程配置文件，不存在则返回空结构 / Read remote config file; return empty structure if not found."""
    if not CONFIG_FILE.exists():
        return {"messages": [], "feature_flags": [], "version": 0}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        # 兼容旧结构（无 feature_flags 字段） / Backward compat (no feature_flags field)
        data.setdefault("feature_flags", [])
        return data
    except Exception as e:
        logger.error(f"读取远程配置失败: {e}")
        return {"messages": [], "feature_flags": [], "version": 0}


def _save_config(data: dict) -> None:
    """写入远程配置文件 / Write remote config file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _generate_id() -> str:
    """生成消息 ID / Generate message ID."""
    return f"msg_{secrets.token_hex(4)}"


def _generate_ff_id() -> str:
    """生成功能开关 ID / Generate feature flag ID."""
    return f"ff_{secrets.token_hex(4)}"


def _now_iso() -> str:
    """当前 UTC 时间 ISO 格式 / Current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# CRUD 操作（管理后台调用） / CRUD Operations (admin backend calls)
# ============================================================


def list_messages() -> list[dict]:
    """返回所有消息（含已禁用的），按 priority 降序 / Return all messages (including disabled), sorted by priority descending."""
    data = _load_config()
    messages = data.get("messages", [])
    messages.sort(key=lambda m: m.get("priority", 0), reverse=True)
    return messages


def get_message(message_id: str) -> dict | None:
    """按 ID 获取单条消息 / Get single message by ID."""
    data = _load_config()
    for msg in data.get("messages", []):
        if msg["id"] == message_id:
            return msg
    return None


def create_message(
    msg_type: str = "banner",
    title: str = "",
    content: str = "",
    cta_text: str = "",
    cta_url: str = "",
    target: str = "guest",
    priority: int = 10,
    enabled: bool = True,
    dismiss_mode: str = "delayed",
    dismiss_delay_days: int = 7,
    schedule_start: str | None = None,
    schedule_end: str | None = None,
) -> dict:
    """创建新消息 / Create new message."""
    data = _load_config()

    now = _now_iso()
    msg = {
        "id": _generate_id(),
        "type": msg_type,
        "title": title,
        "content": content,
        "cta_text": cta_text,
        "cta_url": cta_url,
        "target": target,
        "priority": priority,
        "enabled": enabled,
        "dismiss_policy": {
            "mode": dismiss_mode,
            "delay_days": dismiss_delay_days,
        },
        "schedule": {
            "start": schedule_start or now,
            "end": schedule_end,
        },
        "created_at": now,
        "updated_at": now,
    }

    data["messages"].append(msg)
    data["version"] = data.get("version", 0) + 1
    _save_config(data)

    logger.info(f"远程配置：创建消息 {msg['id']} ({msg_type})")
    return msg


def update_message(message_id: str, **kwargs) -> dict | None:
    """
    更新消息字段 / Update message fields.

    支持的 kwargs / Supported kwargs:
      title, content, cta_text, cta_url, target, priority, enabled,
      dismiss_mode, dismiss_delay_days, schedule_start, schedule_end, type
    """
    data = _load_config()

    for msg in data.get("messages", []):
        if msg["id"] == message_id:
            # 简单字段 / Simple fields
            for key in ("type", "title", "content", "cta_text", "cta_url", "target", "priority", "enabled"):
                if key in kwargs:
                    msg[key] = kwargs[key]

            # dismiss_policy 嵌套字段 / dismiss_policy nested fields
            if "dismiss_mode" in kwargs:
                msg.setdefault("dismiss_policy", {})["mode"] = kwargs["dismiss_mode"]
            if "dismiss_delay_days" in kwargs:
                msg.setdefault("dismiss_policy", {})["delay_days"] = kwargs["dismiss_delay_days"]

            # schedule 嵌套字段 / schedule nested fields
            if "schedule_start" in kwargs:
                msg.setdefault("schedule", {})["start"] = kwargs["schedule_start"]
            if "schedule_end" in kwargs:
                msg.setdefault("schedule", {})["end"] = kwargs["schedule_end"]

            msg["updated_at"] = _now_iso()
            data["version"] = data.get("version", 0) + 1
            _save_config(data)

            logger.info(f"远程配置：更新消息 {message_id}")
            return msg

    return None


def delete_message(message_id: str) -> bool:
    """删除消息 / Delete message."""
    data = _load_config()
    original_len = len(data.get("messages", []))

    data["messages"] = [
        m for m in data.get("messages", [])
        if m["id"] != message_id
    ]

    if len(data["messages"]) < original_len:
        data["version"] = data.get("version", 0) + 1
        _save_config(data)
        logger.info(f"远程配置：删除消息 {message_id}")
        return True

    return False


def toggle_message(message_id: str) -> dict | None:
    """切换消息启用/禁用状态 / Toggle message enabled/disabled state."""
    data = _load_config()

    for msg in data.get("messages", []):
        if msg["id"] == message_id:
            msg["enabled"] = not msg.get("enabled", True)
            msg["updated_at"] = _now_iso()
            data["version"] = data.get("version", 0) + 1
            _save_config(data)

            logger.info(f"远程配置：切换消息 {message_id} → {'启用' if msg['enabled'] else '禁用'}")
            return msg

    return None


# ============================================================
# 客户端查询（过滤后的有效消息） / Client queries (filtered active messages)
# ============================================================


def get_active_messages(user_logged_in: bool = False, user_tier: str = "free") -> list[dict]:
    """
    返回当前有效的消息列表（客户端调用） / Return currently active message list (client calls).

    过滤条件 / Filter conditions:
      1. enabled = true
      2. 在有效期内（schedule.start <= now < schedule.end） / Within validity period
      3. target 匹配用户身份 / target matches user identity

    按 priority 降序排列 / Sorted by priority descending.
    """
    data = _load_config()
    messages = data.get("messages", [])
    now = datetime.now(timezone.utc)

    result = []
    for msg in messages:
        # 1. 必须启用 / Must be enabled
        if not msg.get("enabled", False):
            continue

        # 2. 有效期检查 / Validity period check
        schedule = msg.get("schedule", {})
        start_str = schedule.get("start")
        end_str = schedule.get("end")

        if start_str:
            try:
                start_dt = datetime.fromisoformat(start_str)
                if now < start_dt:
                    continue
            except (ValueError, TypeError):
                pass

        if end_str:
            try:
                end_dt = datetime.fromisoformat(end_str)
                if now >= end_dt:
                    continue
            except (ValueError, TypeError):
                pass

        # 3. target 匹配 / target matching
        target = msg.get("target", "all")
        if target == "guest" and user_logged_in:
            continue
        if target == "logged_in" and not user_logged_in:
            continue
        if target.startswith("tier:") and user_logged_in:
            required_tier = target[5:]
            if user_tier != required_tier:
                continue
        if target.startswith("tier:") and not user_logged_in:
            continue

        result.append(msg)

    # 按 priority 降序 / Sort by priority descending
    result.sort(key=lambda m: m.get("priority", 0), reverse=True)
    return result


def get_config_version() -> int:
    """返回当前配置版本号（客户端用于判断是否需要刷新） / Return current config version number (client uses to check if refresh needed)."""
    data = _load_config()
    return data.get("version", 0)


# ============================================================
# 功能开关 CRUD（管理后台调用） / Feature Flag CRUD (admin backend calls)
# ============================================================


def list_feature_flags() -> list[dict]:
    """返回所有功能开关 / Return all feature flags."""
    data = _load_config()
    return data.get("feature_flags", [])


def get_feature_flag(flag_id: str) -> dict | None:
    """按 ID 获取单个功能开关 / Get single feature flag by ID."""
    data = _load_config()
    for ff in data.get("feature_flags", []):
        if ff["id"] == flag_id:
            return ff
    return None


def get_feature_flag_by_name(name: str) -> dict | None:
    """按标识名获取功能开关（用于业务代码查询） / Get feature flag by name (for business code queries)."""
    data = _load_config()
    for ff in data.get("feature_flags", []):
        if ff["name"] == name:
            return ff
    return None


def create_feature_flag(
    name: str,
    description: str = "",
    enabled: bool = True,
    target: str = "all",
    target_users: list[str] | None = None,
) -> dict:
    """创建新功能开关 / Create new feature flag."""
    data = _load_config()

    # 标识名唯一性检查 / Name uniqueness check
    for ff in data.get("feature_flags", []):
        if ff["name"] == name:
            raise ValueError(f"标识名 '{name}' 已存在")

    now = _now_iso()
    flag = {
        "id": _generate_ff_id(),
        "name": name,
        "description": description,
        "enabled": enabled,
        "target": target,
        "target_users": target_users or [],
        "created_at": now,
        "updated_at": now,
    }

    data["feature_flags"].append(flag)
    data["version"] = data.get("version", 0) + 1
    _save_config(data)

    logger.info(f"远程配置：创建功能开关 {flag['id']} ({name})")
    return flag


def update_feature_flag(flag_id: str, **kwargs) -> dict | None:
    """
    更新功能开关字段 / Update feature flag fields.

    支持的 kwargs / Supported kwargs: name, description, enabled, target, target_users
    """
    data = _load_config()

    for ff in data.get("feature_flags", []):
        if ff["id"] == flag_id:
            # name 唯一性检查 / name uniqueness check
            if "name" in kwargs and kwargs["name"] != ff["name"]:
                for other in data.get("feature_flags", []):
                    if other["id"] != flag_id and other["name"] == kwargs["name"]:
                        raise ValueError(f"标识名 '{kwargs['name']}' 已被使用")

            for key in ("name", "description", "enabled", "target", "target_users"):
                if key in kwargs:
                    ff[key] = kwargs[key]

            ff["updated_at"] = _now_iso()
            data["version"] = data.get("version", 0) + 1
            _save_config(data)

            logger.info(f"远程配置：更新功能开关 {flag_id}")
            return ff

    return None


def delete_feature_flag(flag_id: str) -> bool:
    """删除功能开关 / Delete feature flag."""
    data = _load_config()
    original_len = len(data.get("feature_flags", []))

    data["feature_flags"] = [
        ff for ff in data.get("feature_flags", [])
        if ff["id"] != flag_id
    ]

    if len(data["feature_flags"]) < original_len:
        data["version"] = data.get("version", 0) + 1
        _save_config(data)
        logger.info(f"远程配置：删除功能开关 {flag_id}")
        return True

    return False


def toggle_feature_flag(flag_id: str) -> dict | None:
    """切换功能开关启用/禁用状态 / Toggle feature flag enabled/disabled state."""
    data = _load_config()

    for ff in data.get("feature_flags", []):
        if ff["id"] == flag_id:
            ff["enabled"] = not ff.get("enabled", True)
            ff["updated_at"] = _now_iso()
            data["version"] = data.get("version", 0) + 1
            _save_config(data)

            logger.info(f"远程配置：切换功能开关 {flag_id} → {'启用' if ff['enabled'] else '禁用'}")
            return ff

    return None


def is_feature_enabled(name: str, user_id: str = "", user_tier: str = "free") -> bool:
    """
    业务代码调用：判断某功能对某用户是否开启 / Business code API: check if a feature is enabled for a user.

    规则 / Rules:
      1. 开关不存在 → 默认关闭 / Flag not found → default off
      2. 开关 enabled=false → 关闭 / Flag enabled=false → off
      3. target=all → 开启 / target=all → on
      4. target=tier:xxx → 用户档位匹配则开启 / target=tier:xxx → on if user tier matches
      5. target=users → user_id 在 target_users 列表中则开启 / target=users → on if user_id in target_users list
    """
    flag = get_feature_flag_by_name(name)
    if not flag or not flag.get("enabled", False):
        return False

    target = flag.get("target", "all")
    if target == "all":
        return True
    if target.startswith("tier:"):
        required_tier = target[5:]
        return user_tier == required_tier
    if target == "users":
        return user_id in flag.get("target_users", [])

    return False
