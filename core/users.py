"""
core/users.py — 用户信息数据管理

职责：
  1. 用户信息读写（姓名、头像颜色、OAuth 绑定）
  2. 用户与说话人的绑定关系管理
  3. 数据持久化到 data/users.json

数据结构：
  {
    "users": [
      {
        "id": "uuid",
        "provider": "github",
        "provider_id": "12345",
        "name": "xxx",
        "avatar_url": "https://...",
        "email": "user@example.com",
        "role": "personal",
        "prefs": {"avatar_color": "#4A90D9", ...},
        "created_at": "2026-09-06T00:00:00Z",
        "last_login": "2026-09-06T12:00:00Z"
      }
    ],
    "current_user_id": "uuid",
    "speaker_bindings": {"<task_id>": {"<speaker_id>": "<speaker_uuid>"}}
  }

向后兼容：
  - 旧版 current_user 字段在读取时自动迁移为 users 数组
"""

import contextvars
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 用户数据文件
USERS_FILE = Path("data/users.json")

# 默认用户数据
DEFAULT_USER_DATA = {
    "users": [],
    "current_user_id": None,
    "speaker_bindings": {},
}


def _load_user_data() -> dict:
    """从磁盘加载用户数据，自动迁移旧格式"""
    if not USERS_FILE.exists():
        return dict(DEFAULT_USER_DATA)
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 旧格式迁移：current_user → users 数组
        if "current_user" in data and "users" not in data:
            old_user = data.pop("current_user", None)
            data["users"] = []
            data["current_user_id"] = None
            if old_user and old_user.get("name"):
                migrated = {
                    "id": str(uuid.uuid4()),
                    "provider": "local",
                    "provider_id": "",
                    "name": old_user["name"],
                    "avatar_url": "",
                    "email": "",
                    "role": "personal",
                    "prefs": {"avatar_color": old_user.get("avatar_color", "#4A90D9")},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_login": datetime.now(timezone.utc).isoformat(),
                }
                data["users"].append(migrated)
                data["current_user_id"] = migrated["id"]
            _save_user_data(data)
            logger.info("用户数据已从旧格式迁移")
        return data
    except Exception as e:
        logger.error(f"加载用户数据失败: {e}")
        return dict(DEFAULT_USER_DATA)


def _save_user_data(data: dict) -> None:
    """保存用户数据到磁盘"""
    try:
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存用户数据失败: {e}")


# ── 请求级用户身份（从 JWT cookie 解析，中间件设置）──
_request_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    '_request_user_id', default=None
)


def set_request_user_id(user_id: str | None) -> None:
    """设置当前请求的用户 ID（由中间件调用）"""
    _request_user_id.set(user_id)


def get_request_user_id() -> str | None:
    """获取当前请求的用户 ID"""
    return _request_user_id.get()


# ── 用户信息 ──

def get_current_user() -> dict | None:
    """获取当前登录用户信息。

    优先级：
      1. 请求级 ContextVar（从 JWT cookie 解析，多用户互不干扰）
      2. 回退到 current_user_id（兼容后台任务等无请求上下文的场景）

    未登录返回 None。
    """
    data = _load_user_data()
    # 优先从请求级 ContextVar 获取（HTTP 请求场景，按会话区分）
    user_id = _request_user_id.get()
    if not user_id:
        # 回退到全局 current_user_id（后台任务等非请求场景）
        user_id = data.get("current_user_id")
    if not user_id:
        return None
    for user in data.get("users", []):
        if user["id"] == user_id:
            return user
    return None


def get_user_by_id(user_id: str) -> dict | None:
    """按 ID 查找用户"""
    data = _load_user_data()
    for user in data.get("users", []):
        if user["id"] == user_id:
            return user
    return None


def find_user_by_oauth(provider: str, provider_id: str) -> dict | None:
    """按 OAuth provider + provider_id 查找用户"""
    data = _load_user_data()
    for user in data.get("users", []):
        if user.get("provider") == provider and user.get("provider_id") == provider_id:
            return user
    return None


def find_or_create_oauth_user(
    provider: str,
    provider_id: str,
    name: str,
    avatar_url: str = "",
    email: str = "",
) -> dict:
    """
    OAuth 登录后查找或创建用户记录。

    如果已存在相同 provider + provider_id 的用户，更新其信息和最后登录时间；
    否则创建新用户并设为当前登录用户。

    Returns:
        用户记录字典
    """
    data = _load_user_data()
    now = datetime.now(timezone.utc).isoformat()

    # 查找已有用户
    for user in data.get("users", []):
        if user.get("provider") == provider and user.get("provider_id") == provider_id:
            # 更新信息
            user["name"] = name
            if avatar_url:
                user["avatar_url"] = avatar_url
            if email:
                user["email"] = email
            user["last_login"] = now
            data["current_user_id"] = user["id"]
            _save_user_data(data)
            logger.info(f"OAuth 用户登录: {provider}/{provider_id} ({name})")
            return user

    # 创建新用户
    new_user = {
        "id": str(uuid.uuid4()),
        "provider": provider,
        "provider_id": provider_id,
        "name": name,
        "avatar_url": avatar_url,
        "email": email,
        "role": "personal",
        "prefs": {"avatar_color": "#4A90D9"},
        "subscription": {"tier": "free"},
        "created_at": now,
        "last_login": now,
    }
    data.setdefault("users", []).append(new_user)
    data["current_user_id"] = new_user["id"]
    _save_user_data(data)
    logger.info(f"OAuth 新用户: {provider}/{provider_id} ({name})")
    return new_user


def set_current_user_id(user_id: str) -> None:
    """设置当前登录用户 ID"""
    data = _load_user_data()
    data["current_user_id"] = user_id
    _save_user_data(data)


def _mask_phone(phone: str) -> str:
    """将手机号中间 4 位替换为 ****（如 133****3103）"""
    if len(phone) == 11:
        return phone[:3] + "****" + phone[7:]
    return phone


def find_or_create_sms_user(phone: str) -> dict:
    """
    手机号登录后查找或创建用户记录。

    provider="sms"，provider_id=phone，name 默认为掩码手机号（如 133****3103）。
    如果已存在相同手机号的用户，更新最后登录时间；否则创建新用户。

    Returns:
        用户记录字典
    """
    data = _load_user_data()
    now = datetime.now(timezone.utc).isoformat()

    # 查找已有用户
    for user in data.get("users", []):
        if user.get("provider") == "sms" and user.get("provider_id") == phone:
            user["last_login"] = now
            data["current_user_id"] = user["id"]
            _save_user_data(data)
            logger.info(f"SMS 用户登录: {phone[:3]}****{phone[-4:]}")
            return user

    # 创建新用户
    masked = _mask_phone(phone)
    new_user = {
        "id": str(uuid.uuid4()),
        "provider": "sms",
        "provider_id": phone,
        "name": masked,
        "avatar_url": "",
        "email": "",
        "role": "personal",
        "prefs": {"avatar_color": "#4A90D9"},
        "subscription": {"tier": "free"},
        "created_at": now,
        "last_login": now,
    }
    data.setdefault("users", []).append(new_user)
    data["current_user_id"] = new_user["id"]
    _save_user_data(data)
    logger.info(f"SMS 新用户: {phone[:3]}****{phone[-4:]}")
    return new_user


def clear_current_user() -> None:
    """清除当前登录用户（登出）"""
    data = _load_user_data()
    data["current_user_id"] = None
    _save_user_data(data)
    logger.info("用户已登出")


def update_user_prefs(user_id: str, prefs: dict) -> dict | None:
    """更新用户偏好设置"""
    data = _load_user_data()
    for user in data.get("users", []):
        if user["id"] == user_id:
            user.setdefault("prefs", {}).update(prefs)
            _save_user_data(data)
            return user
    return None


def set_current_user(name: str, avatar_color: str = "#4A90D9") -> dict:
    """
    设置/更新当前用户信息（向后兼容）。
    如果当前已有 OAuth 用户，更新其名称和偏好；
    否则创建本地用户。
    """
    data = _load_user_data()
    now = datetime.now(timezone.utc).isoformat()
    user_id = data.get("current_user_id")

    # 更新已有用户
    if user_id:
        for user in data.get("users", []):
            if user["id"] == user_id:
                user["name"] = name.strip()
                user.setdefault("prefs", {})["avatar_color"] = avatar_color
                user["last_login"] = now
                _save_user_data(data)
                logger.info(f"用户信息已更新: {name}")
                return user

    # 创建新的本地用户
    new_user = {
        "id": str(uuid.uuid4()),
        "provider": "local",
        "provider_id": "",
        "name": name.strip(),
        "avatar_url": "",
        "email": "",
        "role": "personal",
        "prefs": {"avatar_color": avatar_color},
        "subscription": {"tier": "free"},
        "created_at": now,
        "last_login": now,
    }
    data.setdefault("users", []).append(new_user)
    data["current_user_id"] = new_user["id"]
    _save_user_data(data)
    logger.info(f"用户信息已更新: {name}")
    return new_user


# ── 说话人绑定 ──

def get_speaker_bindings(task_id: str | None = None) -> dict:
    """
    获取说话人绑定关系。

    Args:
        task_id: 指定任务 ID 则只返回该任务的绑定；None 返回全部

    Returns:
        {task_id: {speaker_id: speaker_uuid}} 或 {speaker_id: speaker_uuid}
    """
    data = _load_user_data()
    bindings = data.get("speaker_bindings", {})
    if task_id:
        return bindings.get(task_id, {})
    return bindings


def bind_speaker(task_id: str, speaker_id: str, speaker_uuid: str) -> None:
    """
    绑定说话人：将某任务的某 speaker_id 关联到 speakers.json 中的 uuid。

    Args:
        task_id: 任务 ID
        speaker_id: ASR 输出的说话人编号（"0", "1", ...）
        speaker_uuid: speakers.json 中的说话人 UUID
    """
    data = _load_user_data()
    bindings = data.setdefault("speaker_bindings", {})
    task_bindings = bindings.setdefault(task_id, {})
    task_bindings[speaker_id] = speaker_uuid
    _save_user_data(data)
    logger.info(f"说话人绑定: task={task_id[:8]}, speaker={speaker_id} → {speaker_uuid[:8]}")


def unbind_speaker(task_id: str, speaker_id: str) -> None:
    """解除说话人绑定"""
    data = _load_user_data()
    bindings = data.get("speaker_bindings", {})
    task_bindings = bindings.get(task_id, {})
    if speaker_id in task_bindings:
        del task_bindings[speaker_id]
        _save_user_data(data)
        logger.info(f"解除绑定: task={task_id[:8]}, speaker={speaker_id}")


def bind_current_user_to_speaker(task_id: str, speaker_id: str) -> str | None:
    """
    将当前用户绑定到指定任务的某说话人。

    自动在 speakers.json 中创建/查找对应用户条目。

    Returns:
        绑定后的 speaker_uuid，用户未设置时返回 None
    """
    user = get_current_user()
    if not user:
        return None

    # 在 speakers.json 中查找或创建用户对应的说话人条目
    from core import speakers as spk_module
    user_name = user["name"]

    # 查找已有的同名说话人
    existing = spk_module.find_speaker_by_name(user_name)
    if existing:
        speaker_uuid = existing.speaker_id
    else:
        # 创建新说话人条目
        new_speaker = spk_module.add_speaker(user_name)
        speaker_uuid = new_speaker.speaker_id

    # 记录绑定关系
    bind_speaker(task_id, speaker_id, speaker_uuid)
    return speaker_uuid


# ── 授权管理 ──
# 注：JSON 字段名 "subscription" 保留以向后兼容已有 users.json 数据。
# 概念上已重定义为「授权/配额」，不再代表商业订阅。


def get_user_subscription(user_id: str | None = None) -> dict | None:
    """
    获取用户授权信息（兼容旧字段名 subscription）。

    Args:
        user_id: 用户 ID，默认当前用户

    Returns:
        {"tier": "free", "started_at": ..., "expires_at": ...}
        未登录或用户不存在返回 None
    """
    if user_id:
        user = get_user_by_id(user_id)
    else:
        user = get_current_user()
    if not user:
        return None
    # 向后兼容：无 subscription 字段视为 free
    return user.get("subscription", {"tier": "free"})


def set_user_subscription(
    user_id: str,
    tier: str,
    started_at: str | None = None,
    expires_at: str | None = None,
) -> dict | None:
    """
    设置/更新用户授权信息。

    Args:
        user_id: 用户 ID
        tier: 授权档位（当前仅 "free"）
        started_at: 授权开始时间（ISO 8601），默认当前时间
        expires_at: 到期时间（ISO 8601），free 为 None

    Returns:
        更新后的用户对象，用户不存在返回 None
    """
    data = _load_user_data()
    for user in data.get("users", []):
        if user["id"] == user_id:
            user["subscription"] = {
                "tier": tier,
                "started_at": started_at or datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at,
            }
            _save_user_data(data)
            logger.info(f"用户授权已更新: user={user_id[:8]}, tier={tier}")
            return user
    return None


# ── 隐私同意留痕 ──


def record_privacy_consent(user_id: str) -> bool:
    """记录用户隐私同意时间戳。

    仅对 SMS 用户生效（共享 proxy 场景需要服务端留痕免责）。
    其他用户（自带 Key / 本地）无需服务端留痕。

    Returns:
        True = 成功记录；False = 用户不存在或非 SMS 用户
    """
    data = _load_user_data()
    for user in data.get("users", []):
        if user["id"] == user_id:
            if user.get("provider") != "sms":
                return False
            user["privacy_consent_at"] = datetime.now(timezone.utc).isoformat()
            _save_user_data(data)
            logger.info(f"隐私同意已记录: user={user_id[:8]}")
            return True
    return False


def get_privacy_consent_at(user_id: str) -> str | None:
    """获取用户隐私同意时间戳，未同意返回 None"""
    user = get_user_by_id(user_id)
    if not user:
        return None
    return user.get("privacy_consent_at")


# ── 声纹偏好 ──


def should_use_local_diarization() -> bool:
    """判断当前用户是否应使用本地 MFCC 声纹（而非云端 CAM++）。

    规则：
      - 未登录 → True（无授权信息，强制本地）
      - free 用户 → True（体验期默认本地 MFCC，节约共享 proxy 成本）
      - 体验期用户（free）→ 检查 prefs.local_diarization，
        默认 False（使用云端 CAM++），用户可主动开启本地 MFCC

    Returns:
        True = 使用本地 MFCC 14 维；False = 使用云端 CAM++ 192 维
    """
    user = get_current_user()
    if not user:
        return True

    subscription = user.get("subscription", {"tier": "free"})
    tier = subscription.get("tier", "free")

    if tier == "free":
        return True

    prefs = user.get("prefs", {})
    return prefs.get("local_diarization", False)
