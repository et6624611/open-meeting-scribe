"""
core/cloud_client.py — 云端用户服务客户端（桌面端调用）

职责 / Responsibilities:
  1. 桌面端 SMS 登录后同步用户到云端 / Sync user to cloud after desktop SMS login
  2. 转写完成后上报用量到云端 / Report usage to cloud after transcription
  3. 转写前从云端查询配额 / Query quota from cloud before transcription

设计 / Design:
  - 通过 HMAC-SHA256 签名认证（与 SMS 代理同一模式） / HMAC-SHA256 signature auth (same pattern as SMS proxy)
  - CLOUD_API_URL + CLOUD_API_TOKEN 均未配置时，所有函数返回 None（本地模式） / When neither CLOUD_API_URL nor CLOUD_API_TOKEN is configured, all functions return None (local mode)
  - 云端不可达时静默降级到本地模式 / Silently falls back to local mode when cloud is unreachable
  - HTTP 超时统一 5 秒 / HTTP timeout: 5 seconds uniformly
"""

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# ============================================================
# 配置 / Configuration
# ============================================================

CLOUD_API_URL = os.getenv("CLOUD_API_URL", "").rstrip("/")
CLOUD_API_TOKEN = os.getenv("CLOUD_API_TOKEN", "").strip()

# HTTP 超时（秒） / HTTP timeout (seconds)
_REQUEST_TIMEOUT = 5


# ============================================================
# 状态判断 / Status Check
# ============================================================


def is_cloud_enabled() -> bool:
    """判断云端用户服务是否可用 / Check if cloud user service is enabled.

    需要 CLOUD_API_URL 和 CLOUD_API_TOKEN 均已配置 / Both CLOUD_API_URL and CLOUD_API_TOKEN must be configured.
    """
    return bool(CLOUD_API_URL and CLOUD_API_TOKEN)


# ============================================================
# 签名与通信 / Signature & Communication
# ============================================================


def _make_sign(timestamp: str) -> str:
    """生成 HMAC-SHA256 签名 / Generate HMAC-SHA256 signature.

    Args:
        timestamp: Unix 时间戳字符串 / Unix timestamp string

    Returns:
        签名十六进制字符串 / Signature hex string
    """
    return hmac.new(
        CLOUD_API_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()


def _cloud_request(path: str, payload: dict | None = None, method: str = "POST") -> dict | None:
    """向云端 API 发送请求 / Send request to cloud API.

    Args:
        path: API 路径（如 /api/cloud/users/sync） / API path
        payload: 请求体（POST 时） / Request body (for POST)
        method: HTTP 方法 / HTTP method

    Returns:
        响应 JSON 字典，失败返回 None / Response JSON dict; None on failure
    """
    if not is_cloud_enabled():
        return None

    timestamp = str(int(time.time()))
    sign = _make_sign(timestamp)

    url = f"{CLOUD_API_URL}{path}"
    headers = {
        "Content-Type": "application/json",
        "X-Cloud-Timestamp": timestamp,
        "X-Cloud-Sign": sign,
    }

    try:
        data = json.dumps(payload).encode() if payload else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode())

    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
            msg = err_body.get("detail", str(e))
        except Exception:
            msg = f"HTTP {e.code}"
        logger.warning(f"云端 API 请求失败: {path} → {msg}")
        return None

    except urllib.error.URLError as e:
        logger.warning(f"云端 API 连接失败: {path} → {e.reason}")
        return None

    except Exception as e:
        logger.warning(f"云端 API 请求异常: {path} → {e}")
        return None


def _cloud_get(path: str, params: dict | None = None) -> dict | None:
    """向云端 API 发送 GET 请求 / Send GET request to cloud API.

    Args:
        path: API 路径 / API path
        params: 查询参数 / Query parameters

    Returns:
        响应 JSON 字典，失败返回 None / Response JSON dict; None on failure
    """
    if not is_cloud_enabled():
        return None

    # 拼接查询参数 / Build query string
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"{path}?{query}"

    timestamp = str(int(time.time()))
    sign = _make_sign(timestamp)

    url = f"{CLOUD_API_URL}{path}"
    headers = {
        "X-Cloud-Timestamp": timestamp,
        "X-Cloud-Sign": sign,
    }

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode())

    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
            msg = err_body.get("detail", str(e))
        except Exception:
            msg = f"HTTP {e.code}"
        logger.warning(f"云端 API 查询失败: {path} → {msg}")
        return None

    except urllib.error.URLError as e:
        logger.warning(f"云端 API 连接失败: {path} → {e.reason}")
        return None

    except Exception as e:
        logger.warning(f"云端 API 请求异常: {path} → {e}")
        return None


# ============================================================
# 业务函数 / Business Functions
# ============================================================


def sync_user_to_cloud(user_id: str, phone: str, name: str = "") -> dict | None:
    """桌面端 SMS 登录后同步用户到云端 / Sync user to cloud after desktop SMS login.

    Args:
        user_id: 本地用户 ID / Local user ID
        phone: 手机号 / Phone number
        name: 用户名称 / User name

    Returns:
        云端返回的配额信息 dict，失败返回 None / Quota info dict from cloud; None on failure
        {"user_id": "...", "tier": "free", "quota": 300, "used": 0, "remaining": 300}
    """
    if not is_cloud_enabled():
        return None

    from datetime import datetime, timezone

    result = _cloud_request("/api/cloud/users/sync", {
        "user_id": user_id,
        "phone": phone,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    if result:
        logger.info(
            f"用户已同步到云端: {phone[:3]}****{phone[-4:]}, "
            f"tier={result.get('tier')}, remaining={result.get('remaining')}min"
        )
    return result


def report_usage_to_cloud(
    user_id: str,
    service: str,
    duration_seconds: float,
    task_id: str | None = None,
) -> dict | None:
    """上报用量到云端 / Report usage to cloud.

    Args:
        user_id: 用户 ID / User ID
        service: 服务类型 / Service type (asr_batch / asr_realtime / llm_summary)
        duration_seconds: 音频时长（秒） / Audio duration (seconds)
        task_id: 关联任务 ID / Associated task ID

    Returns:
        云端返回的用量信息 dict，失败返回 None / Usage info dict from cloud; None on failure
        {"minutes": 5.0, "cumulative": 30.0, "remaining": 270.0, "quota": 300}
    """
    if not is_cloud_enabled():
        return None

    result = _cloud_request("/api/cloud/usage/report", {
        "user_id": user_id,
        "service": service,
        "duration_seconds": round(duration_seconds, 1),
        "task_id": task_id,
    })

    if result:
        logger.info(
            f"用量已上报云端: user={user_id[:8]}, service={service}, "
            f"+{result.get('minutes')}min, 剩余={result.get('remaining')}min"
        )
    return result


def check_quota_from_cloud(user_id: str, estimated_minutes: float = 0) -> dict | None:
    """从云端查询配额 / Query quota from cloud.

    Args:
        user_id: 用户 ID / User ID
        estimated_minutes: 预估消耗（可选） / Estimated consumption (optional)

    Returns:
        配额信息 dict，失败返回 None / Quota info dict; None on failure
        {"allowed": True, "used": 30.0, "remaining": 270.0, "quota": 300, "tier": "free", "daily_history": [...]}
    """
    if not is_cloud_enabled():
        return None

    result = _cloud_get("/api/cloud/usage/quota", {
        "user_id": user_id,
        "estimated_minutes": str(estimated_minutes),
    })

    if result:
        logger.info(
            f"云端配额查询: user={user_id[:8]}, "
            f"used={result.get('used')}min, remaining={result.get('remaining')}min, "
            f"allowed={result.get('allowed')}"
        )
    return result
