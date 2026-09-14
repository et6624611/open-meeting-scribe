"""
app/routers/config.py — 客户端远程配置拉取接口 / Client remote config fetch API

职责 / Responsibilities:
  1. 客户端启动时拉取当前有效的公告/横幅消息 / Client fetches active announcements/banners on startup
  2. 根据用户登录状态和订阅档位过滤消息 / Filter messages by login status and subscription tier
  3. 无需登录即可调用（匿名返回 guest 可见消息） / No login required (anonymous returns guest-visible messages)

端点 / Endpoints:
  GET /api/config/announcements  — 获取当前有效消息列表 / Get current active message list
  GET /api/config/version        — 获取配置版本号（用于增量刷新判断） / Get config version (for incremental refresh)
"""

import logging

from fastapi import APIRouter, Request

from core import remote_config
from core.auth import verify_jwt
from core.users import get_user_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["远程配置"])

SESSION_COOKIE = "oms_session"


def _resolve_user_context(request: Request) -> tuple[bool, str]:
    """
    从请求中解析用户登录状态和订阅档位 / Parse user login status and subscription tier from request.

    Returns:
        (logged_in: bool, tier: str)
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False, "free"

    payload = verify_jwt(token)
    if not payload:
        return False, "free"

    user_id = payload.get("sub")
    user = get_user_by_id(user_id)
    if not user:
        return False, "free"

    tier = user.get("subscription", {}).get("tier", "free")
    return True, tier


@router.get("/announcements")
def get_announcements(request: Request):
    """
    获取当前有效的公告消息 / Get currently active announcements.

    根据用户登录状态过滤 target，按 priority 降序返回 / Filter by target based on login status; sorted by priority descending.
    无需登录即可调用 / No login required.
    """
    logged_in, tier = _resolve_user_context(request)
    messages = remote_config.get_active_messages(
        user_logged_in=logged_in,
        user_tier=tier,
    )
    return {
        "messages": messages,
        "logged_in": logged_in,
    }


@router.get("/version")
def get_version():
    """
    获取配置版本号 / Get config version number.

    客户端可定期轮询此接口，若版本号变化则重新拉取 announcements / Client can periodically poll; re-fetch announcements if version changes.
    """
    return {"version": remote_config.get_config_version()}
