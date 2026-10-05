"""
app/routers/auth.py — 认证路由 / Authentication routes

职责 / Responsibilities:
  1. GitHub OAuth 登录流程（发起 → 回调 → 签发 JWT） / GitHub OAuth login flow (initiate → callback → issue JWT)
  2. 手机号短信验证码登录（发送 → 核验 → 签发 JWT） / SMS verification code login (send → verify → issue JWT)
  3. 当前用户信息查询 / Current user info query
  4. 登出 / Logout

端点 / Endpoints:
  GET  /auth/github      — 发起 GitHub OAuth，重定向到 GitHub 授权页 / Initiate GitHub OAuth, redirect to GitHub authorization
  GET  /auth/callback    — OAuth 回调，换 token → 创建/查找用户 → 签发 JWT / OAuth callback; exchange token → create/find user → issue JWT
  POST /auth/sms/send    — 发送短信验证码 / Send SMS verification code
  POST /auth/sms/verify  — 核验验证码并登录 / Verify code and login
  GET  /auth/me          — 获取当前登录用户信息 / Get current logged-in user info
  POST /auth/logout      — 登出（清除 cookie） / Logout (clear cookie)
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from core.auth import (
    create_jwt,
    create_oauth_state,
    exchange_github_code,
    fetch_github_user_info,
    get_github_authorize_url,
    verify_jwt,
    verify_oauth_state,
)
from core.i18n import _
from core.sms import can_send, check_verify_code, send_verify_code, validate_phone
from core.users import (
    clear_current_user,
    find_or_create_oauth_user,
    find_or_create_sms_user,
    get_current_user,
    get_privacy_consent_at,
    get_user_by_id,
    record_privacy_consent,
)

logger = logging.getLogger(__name__)

# Cookie Secure 标志：HTTPS 部署时设为 true，本地开发保持 false / Cookie Secure flag: true for HTTPS deployment; false for local dev
_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

router = APIRouter(prefix="/auth", tags=["认证"])

# JWT cookie 名称 / JWT cookie name
SESSION_COOKIE = "oms_session"


@router.get("/github")
def github_login(request: Request):
    """
    发起 GitHub OAuth 登录 / Initiate GitHub OAuth login.
    生成 state 后重定向到 GitHub 授权页 / Generate state then redirect to GitHub authorization page.
    """
    state = create_oauth_state()
    authorize_url = get_github_authorize_url(state)
    logger.info(f"GitHub OAuth 发起: state={state[:8]}...")
    return RedirectResponse(url=authorize_url)


@router.get("/callback")
async def oauth_callback(request: Request, code: str = "", state: str = ""):
    """
    OAuth 回调端点 / OAuth callback endpoint.

    流程 / Flow:
    1. 验证 state（CSRF 防护） / Verify state (CSRF protection)
    2. 用 code 换 access_token / Exchange code for access_token
    3. 用 access_token 获取用户信息 / Fetch user info with access_token
    4. 在本地创建/查找用户记录 / Create/find local user record
    5. 签发 JWT，设置 httpOnly cookie / Issue JWT; set httpOnly cookie
    6. 重定向到首页 / Redirect to home page
    """
    # 检查错误参数 / Check error params
    error = request.query_params.get("error")
    if error:
        error_desc = request.query_params.get("error_description", "未知错误")
        logger.warning(f"OAuth 回调错误: {error} - {error_desc}")
        raise HTTPException(400, _("OAuth authorization failed: {err}").format(err=error_desc))

    # 验证 state / Verify state
    if not state or not verify_oauth_state(state):
        logger.warning("OAuth state 验证失败（可能过期或 CSRF 攻击）")
        raise HTTPException(400, _("Security verification failed, please log in again"))

    # 检查 code / Check code
    if not code:
        raise HTTPException(400, _("Missing authorization code"))

    # 用 code 换 access_token / Exchange code for access_token
    try:
        access_token = await exchange_github_code(code)
    except ValueError as e:
        logger.error(f"换取 access_token 失败: {e}")
        raise HTTPException(400, _("Authorization code exchange failed: {err}").format(err=e))

    # 获取用户信息 / Get user info
    try:
        user_info = await fetch_github_user_info(access_token)
    except ValueError as e:
        logger.error(f"获取用户信息失败: {e}")
        raise HTTPException(400, _("Failed to get user info: {err}").format(err=e))

    # 创建/查找本地用户 / Create/find local user
    display_name = user_info.name or user_info.login
    user = find_or_create_oauth_user(
        provider="github",
        provider_id=user_info.id,
        name=display_name,
        avatar_url=user_info.avatar_url,
        email=user_info.email or "",
    )

    # 签发 JWT / Issue JWT
    jwt_token = create_jwt(
        user_id=user["id"],
        name=user["name"],
        role=user.get("role", "personal"),
    )

    logger.info(f"用户登录成功: {display_name} (github/{user_info.id})")

    # 重定向到首页，同时设置 httpOnly cookie / Redirect to home; set httpOnly cookie
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=jwt_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=7 * 24 * 3600,  # 7 天 / 7 days
        path="/",
    )
    return response


@router.get("/me")
def get_me(request: Request):
    """
    获取当前登录用户信息 / Get current logged-in user info.
    从 cookie 中的 JWT 解析用户 ID，再查本地数据 / Parse user ID from JWT in cookie; look up local data.
    若无 JWT，回退到 current_user_id（本地用户） / If no JWT, fallback to current_user_id (local user).
    """
    token = request.cookies.get(SESSION_COOKIE)
    user_id = None

    if token:
        payload = verify_jwt(token)
        if payload:
            user_id = payload.get("sub")

    # 回退到 current_user_id（本地用户场景） / Fallback to current_user_id (local user scenario)
    if not user_id:
        from core.users import _load_user_data
        data = _load_user_data()
        user_id = data.get("current_user_id")

    if not user_id:
        raise HTTPException(401, _("Not logged in"))

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(401, _("User not found"))

    return {
        "id": user["id"],
        "name": user["name"],
        "avatar_url": user.get("avatar_url", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "personal"),
        "provider": user.get("provider", ""),
        "prefs": user.get("prefs", {}),
        "subscription": user.get("subscription", {"tier": "free"}),
        "privacy_consent_at": user.get("privacy_consent_at"),
    }


@router.post("/logout")
def logout(request: Request):
    """登出：清除 cookie 和本地登录状态 / Logout: clear cookie and local login state."""
    clear_current_user()
    response = JSONResponse({"message": _("Logged out")})
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    logger.info("用户已登出")
    return response


# ============================================================
# 隐私同意留痕 / Privacy Consent Record
# ============================================================


@router.get("/privacy-consent")
def get_consent():
    """
    查询当前用户隐私同意状态 / Query current user privacy consent status.

    Returns:
        {"consented": bool, "consented_at": str|null, "need_server_consent": bool}
    """
    user = get_current_user()
    if not user:
        return {"consented": False, "consented_at": None, "need_server_consent": False}
    consented_at = get_privacy_consent_at(user["id"])
    return {
        "consented": consented_at is not None,
        "consented_at": consented_at,
        "need_server_consent": user.get("provider") == "sms",
    }


@router.post("/privacy-consent")
def post_consent():
    """
    记录用户隐私同意 / Record user privacy consent.

    仅对 SMS 用户写入服务端留痕（与实名记录绑定，用于免责举证） / Server-side record for SMS users only (bound to real-name record; for liability evidence).
    其他用户（自带 Key / 本地）不经手数据，无需服务端留痕 / Other users (self-hosted key / local) do not need server-side record.
    """
    user = get_current_user()
    if not user:
        raise HTTPException(401, _("Not logged in"))
    recorded = record_privacy_consent(user["id"])
    return {
        "recorded": recorded,
        "consented_at": get_privacy_consent_at(user["id"]),
    }


# ============================================================
# 手机号短信验证码登录 / SMS Verification Code Login
# ============================================================

from pydantic import BaseModel, Field


class SmsSendRequest(BaseModel):
    phone: str = Field(..., description="国内 11 位手机号")


class SmsVerifyRequest(BaseModel):
    phone: str = Field(..., description="国内 11 位手机号")
    code: str = Field(..., description="用户输入的验证码")


@router.post("/sms/send")
def sms_send(req: SmsSendRequest):
    """
    发送短信验证码 / Send SMS verification code.

    流程 / Flow:
    1. 校验手机号格式 / Validate phone number format
    2. 检查频率限制（60 秒冷却 + 每天 10 次） / Check rate limit (60s cooldown + 10/day)
    3. 调用阿里云 PNVS SendSmsVerifyCode / Call Alibaba Cloud PNVS SendSmsVerifyCode
    """
    phone = req.phone.strip()

    # 格式校验 / Format validation
    if not validate_phone(phone):
        return JSONResponse(status_code=400, content={"success": False, "message": _("Please enter a valid phone number")})

    # 频率限制 / Rate limiting
    allowed, reason = can_send(phone)
    if not allowed:
        return JSONResponse(status_code=400, content={"success": False, "message": reason})

    # 发送验证码 / Send verification code
    try:
        result = send_verify_code(phone)
        return result
    except RuntimeError as e:
        logger.error(f"短信发送失败: {e}")
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})


@router.post("/sms/verify")
def sms_verify(req: SmsVerifyRequest):
    """
    核验短信验证码并登录 / Verify SMS code and login.

    流程 / Flow:
    1. 调用阿里云 PNVS CheckSmsVerifyCode 核验 / Call Alibaba Cloud PNVS CheckSmsVerifyCode
    2. 核验通过 → 创建/查找 SMS 用户 → 签发 JWT → 设置 httpOnly cookie / Verified → create/find SMS user → issue JWT → set httpOnly cookie
    """
    phone = req.phone.strip()
    code = req.code.strip()

    if not validate_phone(phone):
        return JSONResponse(status_code=400, content={"success": False, "message": _("Please enter a valid phone number")})

    if not code:
        return JSONResponse(status_code=400, content={"success": False, "message": _("Please enter the verification code")})

    # 核验验证码 / Verify code
    passed, reason = check_verify_code(phone, code)
    if not passed:
        return JSONResponse(status_code=400, content={"success": False, "message": reason})

    # 创建/查找用户 / Create/find user
    user = find_or_create_sms_user(phone)

    # 云端同步：将用户同步到云端服务器 / Cloud sync: sync user to cloud server
    from core.cloud_client import sync_user_to_cloud
    cloud_info = sync_user_to_cloud(user["id"], phone, user["name"])
    if cloud_info:
        logger.info(f"用户已同步到云端: {phone[:3]}****{phone[-4:]}")

    # 签发 JWT / Issue JWT
    jwt_token = create_jwt(
        user_id=user["id"],
        name=user["name"],
        role=user.get("role", "personal"),
    )

    logger.info(f"SMS 用户登录成功: {phone[:3]}****{phone[-4:]}")

    # 设置 cookie 并返回 / Set cookie and return
    response = JSONResponse({"success": True})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=jwt_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/",
    )
    return response
