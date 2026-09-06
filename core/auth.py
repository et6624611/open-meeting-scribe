"""
core/auth.py — 认证核心模块

职责：
  1. OAuth 2.0 提供者管理（GitHub）
  2. JWT 签发与验证
  3. OAuth state 管理（CSRF 防护）

设计：
  - OAuth 流程纯服务端，前端只做跳转
  - JWT 存 httpOnly cookie，前端不直接操作
  - state 用内存字典存储（单实例足够）
"""

import os
import time
import uuid
import secrets
import logging
from dataclasses import dataclass

import httpx
import jwt

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

GITHUB_CLIENT_ID = os.getenv("OAUTH_GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("OAUTH_GITHUB_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
APP_URL = os.getenv("APP_URL", "http://127.0.0.1:8000")

# GitHub OAuth 端点
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

# OAuth state 存储（CSRF 防护，内存字典，单实例够用）
_oauth_states: dict[str, float] = {}
STATE_TTL = 600  # state 有效期 10 分钟


# ============================================================
# OAuth State 管理
# ============================================================

def create_oauth_state() -> str:
    """生成并存储一个 OAuth state（CSRF 防护令牌）"""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    return state


def verify_oauth_state(state: str) -> bool:
    """验证 OAuth state，验证后立即销毁（一次性）"""
    created = _oauth_states.pop(state, None)
    if created is None:
        return False
    if time.time() - created > STATE_TTL:
        return False
    return True


def cleanup_expired_states():
    """清理过期的 state 条目（可定期调用）"""
    now = time.time()
    expired = [s for s, t in _oauth_states.items() if now - t > STATE_TTL]
    for s in expired:
        del _oauth_states[s]


# ============================================================
# GitHub OAuth 提供者
# ============================================================

@dataclass
class GitHubUserInfo:
    """GitHub 返回的用户信息"""
    id: str
    login: str
    name: str | None
    avatar_url: str
    email: str | None


def get_github_authorize_url(state: str) -> str:
    """
    构造 GitHub OAuth 授权 URL。

    Args:
        state: CSRF 防护令牌

    Returns:
        完整的授权跳转 URL
    """
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": f"{APP_URL}/auth/callback",
        "scope": "read:user user:email",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GITHUB_AUTHORIZE_URL}?{query}"


async def exchange_github_code(code: str) -> str:
    """
    用授权码换取 GitHub access_token。

    Args:
        code: GitHub 回调携带的授权码

    Returns:
        GitHub access_token

    Raises:
        ValueError: 换取失败时
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{APP_URL}/auth/callback",
            },
            timeout=15,
        )
        result = resp.json()

    if "error" in result:
        raise ValueError(f"GitHub OAuth 错误: {result['error']} - {result.get('error_description', '')}")

    token = result.get("access_token")
    if not token:
        raise ValueError("GitHub 未返回 access_token")
    return token


async def fetch_github_user_info(access_token: str) -> GitHubUserInfo:
    """
    用 access_token 获取 GitHub 用户信息。

    Args:
        access_token: GitHub access_token

    Returns:
        GitHubUserInfo 数据对象

    Raises:
        ValueError: 获取失败时
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient() as client:
        # 获取基本信息
        user_resp = await client.get(GITHUB_USER_URL, headers=headers, timeout=15)
        if user_resp.status_code != 200:
            raise ValueError(f"获取 GitHub 用户信息失败: {user_resp.status_code}")
        user_data = user_resp.json()

        # 获取邮箱（可能不在基本信息中）
        email = user_data.get("email")
        if not email:
            try:
                emails_resp = await client.get(GITHUB_EMAILS_URL, headers=headers, timeout=15)
                if emails_resp.status_code == 200:
                    emails = emails_resp.json()
                    # 优先取主邮箱
                    for e in emails:
                        if e.get("primary") and e.get("verified"):
                            email = e["email"]
                            break
                    # 退而求其次取第一个已验证邮箱
                    if not email:
                        for e in emails:
                            if e.get("verified"):
                                email = e["email"]
                                break
            except Exception as e:
                logger.warning(f"获取 GitHub 邮箱失败: {e}")

    return GitHubUserInfo(
        id=str(user_data["id"]),
        login=user_data.get("login", ""),
        name=user_data.get("name"),
        avatar_url=user_data.get("avatar_url", ""),
        email=email,
    )


# ============================================================
# JWT 管理
# ============================================================

def create_jwt(user_id: str, name: str, role: str = "personal") -> str:
    """
    签发 JWT token。

    Args:
        user_id: 用户 ID
        name: 用户名称（用于前端展示）
        role: 用户角色（personal / team_admin）

    Returns:
        签发的 JWT 字符串
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "name": name,
        "role": role,
        "iat": now,
        "exp": now + JWT_EXPIRE_DAYS * 86400,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_jwt(token: str) -> dict | None:
    """
    验证 JWT token。

    Args:
        token: JWT 字符串

    Returns:
        解码后的 payload 字典，验证失败返回 None
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.info("JWT 已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"JWT 验证失败: {e}")
        return None


# ============================================================
# 认证依赖（FastAPI Depends 用）
# ============================================================

def get_current_user_from_token(token: str) -> dict | None:
    """从 JWT token 解析用户，返回用户信息字典或 None"""
    return verify_jwt(token)
