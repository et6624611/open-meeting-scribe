"""
app/routers/cloud_api.py — 云端用户服务 API / Cloud user service API

职责 / Responsibilities:
  1. 接收桌面客户端的用户同步请求（SMS 登录后上报） / Receive desktop client user sync requests (after SMS login)
  2. 接收桌面客户端的用量上报 / Receive desktop client usage reports
  3. 提供配额查询接口 / Provide quota query endpoint
  4. LLM 代理：桌面端无本地 Key 时通过云端转发 DashScope / LLM proxy: forward to DashScope when client has no local key
  5. ASR 代理：桌面端通过云端转发到同机 ASR 代理 / ASR proxy: forward to local ASR proxy

认证方式 / Authentication:
  - HMAC-SHA256 签名（与 SMS 代理同一模式） / HMAC-SHA256 signature (same pattern as SMS proxy)
  - 请求头：X-Cloud-Timestamp + X-Cloud-Sign / Headers: X-Cloud-Timestamp + X-Cloud-Sign
  - 密钥由 CLOUD_API_TOKEN 环境变量配置 / Secret configured via CLOUD_API_TOKEN env var
  - timestamp 超过 TTL（默认 5 分钟）视为过期 / timestamp beyond TTL (default 5 min) treated as expired

端点 / Endpoints:
  POST /api/cloud/users/sync           — 桌面端 SMS 登录后同步用户 / Sync user after desktop SMS login
  POST /api/cloud/usage/report         — 上报一次用量事件 / Report a usage event
  GET  /api/cloud/usage/quota          — 查询用户配额 / Query user quota
  POST /api/cloud/llm/chat/completions — LLM 代理转发 / LLM proxy to DashScope
  POST /api/cloud/asr/transcribe       — ASR 代理转发 / ASR proxy to local ASR service
  WS   /api/cloud/asr/ws               — ASR 实时转写 WebSocket 代理 / ASR realtime WebSocket proxy
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time

import httpx
import requests
import websockets

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.i18n import _
from core.metering import DEFAULT_QUOTA, get_daily_history, get_monthly_usage, record_usage
from core.users import get_user_by_id


# ============================================================
# 辅助函数 / Helper Functions
# ============================================================


def _find_or_create_sms_user_with_id(
    phone: str,
    desktop_user_id: str,
    name: str = "",
) -> dict:
    """查找或创建 SMS 用户，使用桌面端提供的 user_id 保持一致。
    Find or create SMS user, using desktop-provided user_id for consistency.

    优先级 / Priority:
      1. 按桌面 user_id 查找已有用户 / Find existing user by desktop user_id
      2. 按手机号查找已有用户，更新 ID 为桌面 user_id / Find by phone, update ID to desktop user_id
      3. 创建新用户，使用桌面 user_id / Create new user with desktop user_id
    """
    from core.users import _load_user_data, _save_user_data, _mask_phone
    from datetime import datetime, timezone

    data = _load_user_data()
    now = datetime.now(timezone.utc).isoformat()
    users = data.get("users", [])

    # 1. 按桌面 user_id 查找 / Find by desktop user_id
    for user in users:
        if user.get("id") == desktop_user_id:
            user["last_login"] = now
            if name and user.get("name") != name:
                user["name"] = name
            data["current_user_id"] = user["id"]
            _save_user_data(data)
            return user

    # 2. 按手机号查找 / Find by phone
    for user in users:
        if user.get("provider") == "sms" and user.get("provider_id") == phone:
            # 更新 ID 为桌面端 user_id，保持后续 API 调用一致
            # Update ID to desktop user_id for subsequent API call consistency
            old_id = user["id"]
            user["id"] = desktop_user_id
            user["last_login"] = now
            if name and user.get("name") != name:
                user["name"] = name
            data["current_user_id"] = desktop_user_id
            _save_user_data(data)
            logger.info(f"用户 ID 已同步: {old_id[:8]} → {desktop_user_id[:8]} (phone={phone[:3]}****)")
            return user

    # 3. 创建新用户 / Create new user
    masked = _mask_phone(phone)
    new_user = {
        "id": desktop_user_id,
        "provider": "sms",
        "provider_id": phone,
        "name": name or masked,
        "avatar_url": "",
        "email": "",
        "role": "personal",
        "prefs": {"avatar_color": "#4A90D9"},
        "subscription": {"tier": "free"},
        "created_at": now,
        "last_login": now,
    }
    users.append(new_user)
    data["current_user_id"] = desktop_user_id
    _save_user_data(data)
    logger.info(f"云端新用户: phone={phone[:3]}****, user_id={desktop_user_id[:8]}")
    return new_user

logger = logging.getLogger(__name__)

# ============================================================
# 配置 / Configuration
# ============================================================

CLOUD_API_TOKEN = os.getenv("CLOUD_API_TOKEN", "").strip()
CLOUD_SIGN_TTL = int(os.getenv("CLOUD_SIGN_TTL", "300"))  # 签名有效期（秒） / Signature validity (seconds)

# DashScope LLM 代理配置 / DashScope LLM proxy config
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
).rstrip("/")

# ASR 本地代理配置（云端服务器与 ASR 代理同机部署） / Local ASR proxy config (co-located)
ASR_PROXY_LOCAL_URL = os.getenv("ASR_PROXY_LOCAL_URL", "http://127.0.0.1:8200").rstrip("/")
ASR_PROXY_LOCAL_TOKEN = os.getenv("ASR_PROXY_LOCAL_TOKEN", "").strip()

router = APIRouter(prefix="/api/cloud", tags=["云端用户服务"])


# ============================================================
# 签名校验 / Signature Verification
# ============================================================


def _verify_signature(timestamp: str, sign: str) -> bool:
    """校验请求签名 / Verify request signature.

    Args:
        timestamp: 请求时间戳（Unix 秒） / Request timestamp (Unix seconds)
        sign: 请求签名 / Request signature

    Returns:
        校验通过返回 True / True if verification passes
    """
    if not CLOUD_API_TOKEN:
        return False

    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    now = int(time.time())
    if abs(now - ts) > CLOUD_SIGN_TTL:
        logger.warning(f"云端 API 签名过期: timestamp={timestamp}, now={now}, ttl={CLOUD_SIGN_TTL}")
        return False

    expected = hmac.new(
        CLOUD_API_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(sign, expected)


def _check_cloud_auth(request: Request) -> None:
    """校验请求的 HMAC 签名，失败时抛出 HTTPException / Verify HMAC signature; raise HTTPException on failure."""
    if not CLOUD_API_TOKEN:
        raise HTTPException(500, _("Cloud API not configured (CLOUD_API_TOKEN)"))

    timestamp = request.headers.get("X-Cloud-Timestamp", "")
    sign = request.headers.get("X-Cloud-Sign", "")

    if not timestamp or not sign:
        raise HTTPException(401, _("Missing auth headers X-Cloud-Timestamp / X-Cloud-Sign"))

    if not _verify_signature(timestamp, sign):
        raise HTTPException(401, _("Signature verification failed"))


# ============================================================
# 请求模型 / Request Models
# ============================================================


class SyncUserRequest(BaseModel):
    """桌面端 SMS 登录后同步用户 / Sync user after desktop SMS login."""
    user_id: str = Field(..., description="桌面端生成的用户 ID / Desktop-generated user ID")
    phone: str = Field(..., description="手机号 / Phone number")
    name: str = Field(default="", description="用户名称 / User name")
    created_at: str = Field(default="", description="用户创建时间 / User creation time")


class ReportUsageRequest(BaseModel):
    """上报用量事件 / Report usage event."""
    user_id: str = Field(..., description="用户 ID / User ID")
    service: str = Field(..., description="服务类型: asr_batch / asr_realtime / llm_summary / Service type")
    duration_seconds: float = Field(..., description="音频时长（秒） / Audio duration (seconds)")
    task_id: str = Field(default=None, description="关联任务 ID / Associated task ID")


# ============================================================
# 端点 / Endpoints
# ============================================================


@router.post("/users/sync")
def cloud_sync_user(req: SyncUserRequest, request: Request):
    """
    桌面端 SMS 登录后同步用户到云端 / Sync user to cloud after desktop SMS login.

    在服务器 data/users.json 中创建或更新用户记录，使管理后台可见。
    Create or update user record in server's data/users.json; makes user visible to admin panel.

    桌面端提供自己的 user_id，服务器端保持一致，确保后续 API 调用（配额查询、LLM 等）
    能通过该 ID 找到用户。 / Desktop provides its own user_id; server keeps it consistent
    so subsequent API calls (quota, LLM, etc.) can find the user by that ID.
    """
    _check_cloud_auth(request)

    phone = req.phone.strip()
    if not phone:
        raise HTTPException(400, "phone is required")

    # 使用桌面端提供的 user_id 创建/查找用户
    # Use desktop-provided user_id to create/find user
    user = _find_or_create_sms_user_with_id(
        phone=phone,
        desktop_user_id=req.user_id,
        name=req.name,
    )

    # 返回配额信息 / Return quota info
    quota = user.get("quota", DEFAULT_QUOTA)
    tier = user.get("subscription", {}).get("tier", "free")

    month_key = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m")
    used = get_monthly_usage(user["id"], month_key)
    remaining = max(0, quota - used)

    logger.info(
        f"云端用户同步: phone={phone[:3]}****{phone[-4:]}, "
        f"user_id={user['id'][:8]}, used={used}min, remaining={remaining}min"
    )

    return {
        "user_id": user["id"],
        "tier": tier,
        "quota": quota,
        "used": round(used, 1),
        "remaining": round(remaining, 1),
    }


@router.post("/usage/report")
def cloud_report_usage(req: ReportUsageRequest, request: Request):
    """
    桌面端上报用量事件 / Desktop client reports usage event.

    写入服务器 data/usage/ JSONL，作为权威用量记录。
    Write to server's data/usage/ JSONL as authoritative usage record.
    """
    _check_cloud_auth(request)

    user = get_user_by_id(req.user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    # 调用已有的 record_usage 写入服务器 JSONL / Use existing record_usage to write to server JSONL
    result = record_usage(
        user_id=req.user_id,
        service=req.service,
        duration_seconds=req.duration_seconds,
        task_id=req.task_id,
    )

    logger.info(
        f"云端用量上报: user={req.user_id[:8]}, service={req.service}, "
        f"+{result['minutes']}min, 月累计={result['cumulative_monthly']}min, "
        f"剩余={result['remaining']}min"
    )

    return {
        "minutes": result["minutes"],
        "cumulative": result["cumulative_monthly"],
        "remaining": result["remaining"],
        "quota": result["quota"],
    }


@router.get("/usage/quota")
def cloud_check_quota(
    request: Request,
    user_id: str = Query(..., description="用户 ID / User ID"),
    estimated_minutes: float = Query(0, description="预估消耗（可选） / Estimated consumption (optional)"),
):
    """
    桌面端查询用户配额 / Desktop client queries user quota.

    返回云端权威的配额信息（含逐日用量明细）。
    Return cloud-authoritative quota info (incl. daily usage details).
    """
    _check_cloud_auth(request)

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    quota = user.get("quota", DEFAULT_QUOTA)

    # 配额为 0 的用户直接拒绝 / Users with zero quota are rejected
    if quota <= 0:
        return {
            "allowed": False,
            "used": 0,
            "remaining": 0,
            "quota": 0,
            "daily_history": [],
        }

    month_key = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m")
    used = get_monthly_usage(user_id, month_key)
    remaining = max(0, quota - used)
    allowed = remaining > estimated_minutes

    # 最近 7 天用量明细 / Last 7 days usage details
    daily = get_daily_history(user_id, days=7)

    return {
        "allowed": allowed,
        "used": round(used, 1),
        "remaining": round(remaining, 1),
        "quota": quota,
        "daily_history": daily,
    }


# ============================================================
# LLM 代理 / LLM Proxy
# ============================================================


class CloudLLMRequest(BaseModel):
    """桌面端通过云端代理调用 LLM / Desktop client calls LLM via cloud proxy."""
    messages: list[dict] = Field(..., description="对话消息列表 / Chat messages")
    model: str = Field(default="qwen-plus", description="模型名 / Model name")
    temperature: float = Field(default=0.7, description="温度 / Temperature")
    max_tokens: int = Field(default=4096, description="最大 token 数 / Max tokens")
    stream: bool = Field(default=False, description="是否流式 / Whether to stream")
    user_id: str = Field(default="", description="用户 ID（用于配额检查） / User ID for quota check")


def _check_user_quota(user_id: str, estimated_minutes: float = 0.1) -> dict:
    """检查用户配额是否充足 / Check if user quota is sufficient.

    Returns:
        {"allowed": True, "remaining": ...} 或抛出 HTTPException
    """
    if not user_id:
        return {"allowed": True, "remaining": -1}

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, _("User not found"))

    quota = user.get("quota", DEFAULT_QUOTA)

    # 配额为 0 的用户直接拒绝 / Users with zero quota are rejected
    if quota <= 0:
        raise HTTPException(402, _("Quota exhausted"))

    from datetime import datetime, timezone
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    used = get_monthly_usage(user_id, month_key)
    remaining = max(0, quota - used)

    if remaining <= estimated_minutes:
        raise HTTPException(
            402,
            {
                "error": "quota_exhausted",
                "remaining": round(remaining, 1),
                "message": f"配额已用尽（剩余 {remaining:.1f} 分钟）。请在设置中配置自己的 API Key。",
            },
        )

    return {"allowed": True, "remaining": round(remaining, 1)}


@router.post("/llm/chat/completions")
def cloud_llm_proxy(req: CloudLLMRequest, request: Request):
    """
    LLM 代理端点：桌面端无本地 API Key 时，通过云端转发到 DashScope。
    LLM proxy: when desktop client has no local API key, forward to DashScope via cloud.

    流程 / Flow:
      1. 验证 HMAC 签名 / Verify HMAC signature
      2. 检查用户配额 / Check user quota
      3. 用服务器的 DASHSCOPE_API_KEY 转发到 DashScope / Forward using server's DASHSCOPE_API_KEY
      4. 返回 DashScope 原始响应 / Return DashScope's raw response
      5. 后台上报用量 / Report usage in background
    """
    _check_cloud_auth(request)

    if not DASHSCOPE_API_KEY:
        raise HTTPException(500, "LLM proxy not configured (DASHSCOPE_API_KEY missing)")

    # 配额检查 / Quota check
    quota_info = _check_user_quota(req.user_id, estimated_minutes=0.1)

    # 构建 DashScope 请求 / Build DashScope request
    dashscope_url = f"{DASHSCOPE_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": req.model,
        "messages": req.messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "stream": req.stream,
    }

    logger.info(
        f"LLM 代理: user={req.user_id[:8] if req.user_id else 'anon'}, "
        f"model={req.model}, messages={len(req.messages)}, stream={req.stream}"
    )

    if req.stream:
        # 流式响应：逐块转发 / Streaming: forward chunks
        def _stream_generator():
            try:
                with requests.post(dashscope_url, headers=headers, json=body, timeout=120, stream=True) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if line:
                            yield line + b"\n"
            except Exception as e:
                logger.error(f"LLM 代理流式转发失败: {e}")
                error_data = json.dumps({"error": str(e)}).encode()
                yield f"data: {error_data.decode()}\n\n".encode()

        return StreamingResponse(_stream_generator(), media_type="text/event-stream")

    # 非流式响应 / Non-streaming response
    try:
        resp = requests.post(dashscope_url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        result = resp.json()
    except requests.exceptions.Timeout:
        raise HTTPException(504, "LLM proxy timeout")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        detail = e.response.text if e.response is not None else str(e)
        logger.error(f"LLM 代理转发失败: HTTP {status}, {detail[:200]}")
        raise HTTPException(status, f"LLM proxy error: {detail[:500]}")
    except Exception as e:
        logger.error(f"LLM 代理转发异常: {e}")
        raise HTTPException(502, f"LLM proxy error: {e}")

    # 后台上报用量（按 token 数折算） / Report usage in background (by token count)
    if req.user_id:
        usage = result.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        # 粗略折算：1000 tokens ≈ 1 分钟 / Rough conversion: 1000 tokens ≈ 1 minute
        minutes = max(0.1, total_tokens / 1000.0)
        try:
            record_usage(
                user_id=req.user_id,
                service="llm_cloud_proxy",
                duration_seconds=minutes * 60,
            )
        except Exception as e:
            logger.warning(f"LLM 代理用量上报失败（不影响响应）: {e}")

    return result


# ============================================================
# ASR 实时转写 WebSocket 代理 / ASR Realtime WebSocket Proxy
# ============================================================


@router.websocket("/asr/ws")
async def cloud_asr_ws_proxy(
    websocket: WebSocket,
    timestamp: str = "",
    sign: str = "",
    model: str = "qwen-audio-3.0-asr-flash-streaming",
    sample_rate: int = 16000,
    language_hints: str = "zh,en",
    vocabulary_id: str = "",
    user_id: str = "",
):
    """
    实时转写 WebSocket 代理：桌面端通过云端转发到同机 ASR 代理。
    Realtime transcription WebSocket proxy: forward to co-located ASR proxy.

    认证通过查询参数 timestamp + sign（云 HMAC）。
    Auth via query params timestamp + sign (cloud HMAC).
    """
    # 校验云端签名 / Verify cloud signature
    if not CLOUD_API_TOKEN:
        await websocket.close(code=1011, reason="Cloud API not configured")
        return

    if not _verify_signature(timestamp, sign):
        await websocket.close(code=1008, reason="Cloud signature verification failed")
        return

    await websocket.accept()
    logger.info(f"[ASR WS Cloud] 客户端已连接: model={model}, user={user_id[:8] if user_id else 'anon'}")

    # 构建到本地 ASR 代理的 WebSocket URL / Build upstream WebSocket URL to local ASR proxy
    if not ASR_PROXY_LOCAL_TOKEN:
        await websocket.send_json({"type": "error", "message": "ASR proxy not configured on server"})
        await websocket.close(code=1011, reason="ASR proxy not configured")
        return

    upstream_ts = str(int(time.time()))
    upstream_sign = _make_asr_local_sign(upstream_ts)

    from urllib.parse import urlencode
    upstream_params = {
        "timestamp": upstream_ts,
        "sign": upstream_sign,
        "model": model,
        "sample_rate": sample_rate,
        "language_hints": language_hints,
    }
    if vocabulary_id:
        upstream_params["vocabulary_id"] = vocabulary_id

    upstream_ws = f"{ASR_PROXY_LOCAL_URL}/asr/ws?{urlencode(upstream_params)}"
    # http → ws
    upstream_ws = upstream_ws.replace("http://", "ws://").replace("https://", "wss://")

    upstream_ws_conn = None
    try:
        upstream_ws_conn = await websockets.connect(upstream_ws, open_timeout=10)
        logger.info(f"[ASR WS Cloud] 已连接本地 ASR 代理: {ASR_PROXY_LOCAL_URL}")

        # 双向中继 / Bidirectional relay
        async def relay_client_to_upstream():
            """客户端 → 上游 ASR 代理（支持文本+二进制）"""
            try:
                while True:
                    msg = await websocket.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    if msg["type"] == "websocket.receive":
                        data = msg.get("bytes") or msg.get("text")
                        if data is not None:
                            await upstream_ws_conn.send(data)
            except Exception as e:
                logger.debug(f"[ASR WS Cloud] client→upstream 结束: {e}")

        async def relay_upstream_to_client():
            """上游 ASR 代理 → 客户端"""
            try:
                async for message in upstream_ws_conn:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                logger.debug(f"[ASR WS Cloud] upstream→client 结束: {e}")

        # 同时运行两个中继方向 / Run both relay directions concurrently
        done, pending = await asyncio.wait(
            [
                asyncio.create_task(relay_client_to_upstream()),
                asyncio.create_task(relay_upstream_to_client()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except Exception as e:
        logger.error(f"[ASR WS Cloud] 代理失败: {e}")
        try:
            await websocket.send_json({"type": "error", "message": f"ASR proxy connection failed: {e}"})
        except Exception:
            pass
    finally:
        if upstream_ws_conn:
            try:
                await upstream_ws_conn.close()
            except Exception:
                pass
        logger.info(f"[ASR WS Cloud] 连接已关闭: user={user_id[:8] if user_id else 'anon'}")


# ============================================================
# ASR 代理 / ASR Proxy
# ============================================================


def _make_asr_local_sign(timestamp: str) -> str:
    """为本地 ASR 代理生成 HMAC 签名 / Generate HMAC signature for local ASR proxy."""
    if not ASR_PROXY_LOCAL_TOKEN:
        raise RuntimeError("ASR_PROXY_LOCAL_TOKEN not configured")
    return hmac.new(
        ASR_PROXY_LOCAL_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()


@router.post("/asr/transcribe")
def cloud_asr_proxy(
    request: Request,
    file: UploadFile = File(..., description="音频文件 / Audio file"),
    user_id: str = Query(default="", description="用户 ID / User ID"),
    model: str = Query(default="paraformer-v2", description="ASR 模型 / ASR model"),
    diarization_enabled: str = Query(default="true", description="是否启用说话人分离 / Enable diarization"),
):
    """
    ASR 代理端点：桌面端通过云端转发到同机 ASR 代理。
    ASR proxy: desktop client forwards audio to co-located ASR proxy via cloud.

    流程 / Flow:
      1. 验证 HMAC 签名 / Verify HMAC signature
      2. 检查用户配额 / Check user quota
      3. 转发到本地 ASR 代理 (localhost:8200) / Forward to local ASR proxy
      4. 返回转写结果 / Return transcription result
      5. 上报用量（按音频时长） / Report usage (by audio duration)
    """
    _check_cloud_auth(request)

    if not ASR_PROXY_LOCAL_TOKEN:
        raise HTTPException(500, "ASR proxy not configured (ASR_PROXY_LOCAL_TOKEN missing)")

    # 配额检查 / Quota check
    quota_info = _check_user_quota(user_id, estimated_minutes=1.0)

    # 读取上传的音频文件 / Read uploaded audio file
    audio_data = file.file.read()
    if not audio_data:
        raise HTTPException(400, "Empty audio file")

    logger.info(
        f"ASR 代理: user={user_id[:8] if user_id else 'anon'}, "
        f"file={file.filename}, size={len(audio_data) / 1024 / 1024:.1f}MB, model={model}"
    )

    # 构建 multipart/form-data 转发到本地 ASR 代理 / Build multipart and forward to local ASR proxy
    timestamp = str(int(time.time()))
    sign = _make_asr_local_sign(timestamp)

    asr_url = f"{ASR_PROXY_LOCAL_URL}/asr/transcribe"
    params = {
        "model": model,
        "diarization_enabled": diarization_enabled,
    }
    asr_headers = {
        "X-ASR-Timestamp": timestamp,
        "X-ASR-Sign": sign,
    }

    # 构建 multipart 请求 / Build multipart request
    files = {"file": (file.filename or "audio.wav", audio_data, file.content_type or "audio/wav")}

    try:
        resp = requests.post(
            asr_url,
            params=params,
            headers=asr_headers,
            files=files,
            timeout=600,
        )
        resp.raise_for_status()
        result = resp.json()
    except requests.exceptions.Timeout:
        raise HTTPException(504, "ASR proxy timeout")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        detail = e.response.text if e.response is not None else str(e)
        logger.error(f"ASR 代理转发失败: HTTP {status}, {detail[:200]}")
        raise HTTPException(status, f"ASR proxy error: {detail[:500]}")
    except Exception as e:
        logger.error(f"ASR 代理转发异常: {e}")
        raise HTTPException(502, f"ASR proxy error: {e}")

    # 上报用量（按音频时长） / Report usage by audio duration
    if user_id:
        # 尝试从结果中提取音频时长 / Try to extract audio duration from result
        audio_duration = result.get("audio_duration_seconds", 0)
        if not audio_duration:
            # 粗略估算：文件大小 / 比特率 / Rough estimate
            audio_duration = len(audio_data) / (16000 * 2)  # 16kHz 16bit mono
        if audio_duration > 0:
            try:
                record_usage(
                    user_id=user_id,
                    service="asr_cloud_proxy",
                    duration_seconds=audio_duration,
                )
            except Exception as e:
                logger.warning(f"ASR 代理用量上报失败（不影响响应）: {e}")

    return result
