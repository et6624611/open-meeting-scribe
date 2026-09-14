"""
core/auth.py — 认证核心模块 / Authentication core module

职责 / Responsibilities:
  1. OAuth 2.0 提供者管理（GitHub） / OAuth 2.0 provider management (GitHub)
  2. JWT 签发与验证 / JWT issuance and verification
  3. OAuth state 管理（CSRF 防护） / OAuth state management (CSRF protection)

设计 / Design:
  - OAuth 流程纯服务端，前端只做跳转 / OAuth flow is server-side only; frontend only does redirects
  - JWT 存 httpOnly cookie，前端不直接操作 / JWT stored in httpOnly cookie; frontend does not directly access
  - state 用内存字典存储（单实例足够） / State stored in memory dict (single instance sufficient)
"""

import logging
import os
import secrets
import time
from dataclasses import dataclass

import httpx
import jwt

logger = logging.getLogger(__name__)

# ============================================================
# 配置 / Configuration
# ============================================================

GITHUB_CLIENT_ID = os.getenv("OAUTH_GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("OAUTH_GITHUB_CLIENT_SECRET", "")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

# JWT 签名密钥：严禁使用空密钥（空密钥会导致 JWT 可被任意伪造） / JWT signing key: NEVER use empty key (empty key allows JWT forgery).
# 未显式配置时生成进程级随机密钥——重启后所有会话失效，仅适用于本地单用户开发 / Generate process-level random key when not explicitly configured;
#   all sessions invalidated on restart, suitable for local single-user dev only.
# 生产或多用户（REQUIRE_AUTH=true）部署必须在 .env 中设置固定的强 JWT_SECRET / Production or multi-user (REQUIRE_AUTH=true) deployments MUST set a strong fixed JWT_SECRET in .env.
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET 未配置，已生成临时随机密钥（进程重启后所有登录会话失效）。"
        "生产或多用户部署请在 .env 中设置固定的强 JWT_SECRET。"
    )
APP_URL = os.getenv("APP_URL", "http://127.0.0.1:8000")

# GitHub OAuth 端点 / GitHub OAuth endpoints
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

# OAuth state 存储（CSRF 防护，内存字典，单实例够用） / OAuth state storage (CSRF protection, in-memory dict, single instance sufficient)
_oauth_states: dict[str, float] = {}
STATE_TTL = 600  # state 有效期 10 分钟 / State validity: 10 minutes


# ============================================================
# OAuth State 管理 / OAuth State Management
# ============================================================

def create_oauth_state() -> str:
    """生成并存储一个 OAuth state（CSRF 防护令牌） / Generate and store an OAuth state (CSRF protection token)."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    return state


def verify_oauth_state(state: str) -> bool:
    """验证 OAuth state，验证后立即销毁（一次性） / Verify OAuth state; destroyed immediately after verification (one-time use)."""
    created = _oauth_states.pop(state, None)
    if created is None:
        return False
    if time.time() - created > STATE_TTL:
        return False
    return True


def cleanup_expired_states() -> None:
    """清理过期的 state 条目（可定期调用） / Clean up expired state entries (can be called periodically)."""
    now = time.time()
    expired = [s for s, t in _oauth_states.items() if now - t > STATE_TTL]
    for s in expired:
        del _oauth_states[s]


# ============================================================
# GitHub OAuth 提供者 / GitHub OAuth Provider
# ============================================================

@dataclass
class GitHubUserInfo:
    """GitHub 返回的用户信息 / User info returned by GitHub."""
    id: str
    login: str
    name: str | None
    avatar_url: str
    email: str | None


def get_github_authorize_url(state: str) -> str:
    """
    构造 GitHub OAuth 授权 URL / Construct GitHub OAuth authorization URL.

    Args:
        state: CSRF 防护令牌 / CSRF protection token

    Returns:
        完整的授权跳转 URL / Complete authorization redirect URL
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
    用授权码换取 GitHub access_token / Exchange authorization code for GitHub access_token.

    Args:
        code: GitHub 回调携带的授权码 / Authorization code from GitHub callback

    Returns:
        GitHub access_token

    Raises:
        ValueError: 换取失败时 / On exchange failure
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
    用 access_token 获取 GitHub 用户信息 / Fetch GitHub user info with access_token.

    Args:
        access_token: GitHub access_token

    Returns:
        GitHubUserInfo 数据对象 / GitHubUserInfo data object

    Raises:
        ValueError: 获取失败时 / On fetch failure
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient() as client:
        # 获取基本信息 / Fetch basic info
        user_resp = await client.get(GITHUB_USER_URL, headers=headers, timeout=15)
        if user_resp.status_code != 200:
            raise ValueError(f"获取 GitHub 用户信息失败: {user_resp.status_code}")
        user_data = user_resp.json()

        # 获取邮箱（可能不在基本信息中） / Fetch email (may not be in basic info)
        email = user_data.get("email")
        if not email:
            try:
                emails_resp = await client.get(GITHUB_EMAILS_URL, headers=headers, timeout=15)
                if emails_resp.status_code == 200:
                    emails = emails_resp.json()
                    # 优先取主邮箱 / Prefer primary email
                    for e in emails:
                        if e.get("primary") and e.get("verified"):
                            email = e["email"]
                            break
                    # 退而求其次取第一个已验证邮箱 / Fallback: first verified email
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
# JWT 管理 / JWT Management
# ============================================================

def create_jwt(user_id: str, name: str, role: str = "personal") -> str:
    """
    签发 JWT token / Issue JWT token.

    Args:
        user_id: 用户 ID / User ID
        name: 用户名称（用于前端展示） / User name (for frontend display)
        role: 用户角色（personal / team_admin） / User role (personal / team_admin)

    Returns:
        签发的 JWT 字符串 / Issued JWT token string
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
    验证 JWT token / Verify JWT token.

    Args:
        token: JWT 字符串 / JWT token string

    Returns:
        解码后的 payload 字典，验证失败返回 None / Decoded payload dict; None on verification failure
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
# 认证依赖（FastAPI Depends 用） / Authentication dependency (for FastAPI Depends)
# ============================================================

def get_current_user_from_token(token: str) -> dict | None:
    """从 JWT token 解析用户，返回用户信息字典或 None / Parse user from JWT token; return user info dict or None."""
    return verify_jwt(token)
