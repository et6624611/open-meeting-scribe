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


def _cloud_request(path: str, payload: dict | None = None, method: str = "POST", timeout: int = _REQUEST_TIMEOUT) -> dict | None:
    """向云端 API 发送请求 / Send request to cloud API.

    Args:
        path: API 路径（如 /api/cloud/users/sync） / API path
        payload: 请求体（POST 时） / Request body (for POST)
        method: HTTP 方法 / HTTP method
        timeout: 超时秒数，默认 5 秒 / Timeout in seconds, default 5

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

        with urllib.request.urlopen(req, timeout=timeout) as resp:
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


# ============================================================
# LLM 代理 / LLM Proxy
# ============================================================


def cloud_llm_chat(
    messages: list[dict],
    model: str = "qwen-plus",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    user_id: str = "",
) -> dict | None:
    """通过云端代理调用 LLM / Call LLM via cloud proxy.

    桌面端无本地 API Key 时，通过云端服务器转发到 DashScope。
    When desktop client has no local API key, forward to DashScope via cloud server.

    Args:
        messages: 对话消息列表 / Chat messages
        model: 模型名 / Model name
        temperature: 温度 / Temperature
        max_tokens: 最大 token 数 / Max tokens
        user_id: 用户 ID（用于配额检查） / User ID for quota check

    Returns:
        DashScope 格式的响应 dict，失败返回 None / DashScope-format response dict; None on failure
    """
    if not is_cloud_enabled():
        return None

    result = _cloud_request("/api/cloud/llm/chat/completions", {
        "messages": messages,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "user_id": user_id,
    }, timeout=120)

    if result:
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = result.get("usage", {})
        logger.info(
            f"云端 LLM 调用成功: user={user_id[:8] if user_id else 'anon'}, "
            f"model={model}, tokens={usage.get('total_tokens', 0)}, "
            f"content_len={len(content)}"
        )
    return result


def cloud_llm_chat_stream(
    messages: list[dict],
    model: str = "qwen-plus",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    user_id: str = "",
):
    """通过云端代理流式调用 LLM / Stream LLM via cloud proxy.

    与 cloud_llm_chat 相同，但使用 stream=True 逐 token 返回。
    Same as cloud_llm_chat but uses stream=True to yield tokens one by one.

    Yields:
        逐块生成的文本 / Generated text chunks
    """
    if not is_cloud_enabled():
        return

    timestamp = str(int(time.time()))
    sign = _make_sign(timestamp)
    url = f"{CLOUD_API_URL}/api/cloud/llm/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "X-Cloud-Timestamp": timestamp,
        "X-Cloud-Sign": sign,
    }
    payload = {
        "messages": messages,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "user_id": user_id,
    }

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    except Exception as e:
        logger.warning(f"云端 LLM 流式调用失败: {e}")


# ============================================================
# ASR 代理 / ASR Proxy
# ============================================================


def _cloud_upload_file(path: str, file_path: str, params: dict | None = None) -> dict | None:
    """向云端 API 上传文件 / Upload file to cloud API.

    使用 multipart/form-data 格式上传，带 HMAC 签名认证。
    Upload using multipart/form-data format with HMAC signature auth.

    Args:
        path: API 路径 / API path
        file_path: 本地文件路径 / Local file path
        params: 额外查询参数 / Additional query parameters

    Returns:
        响应 JSON dict；连接级失败（URLError 等）返回 None / Response JSON dict; None on connection-level failure (URLError etc.)

    Raises:
        RuntimeError: 服务端返回业务错误（HTTPError），携带真实 detail（如 转写任务失败: SUCCESS_WITH_NO_VALID_FRAGMENT），
        供上层 classify_error 生成可读提示 / Server returned business error (HTTPError) with real detail, for readable classification upstream.
    """
    if not is_cloud_enabled():
        return None

    from pathlib import Path
    import urllib.parse

    # 拼接查询参数 / Build query string
    if params:
        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        full_path = f"{path}?{query}"
    else:
        full_path = path

    timestamp = str(int(time.time()))
    sign = _make_sign(timestamp)

    url = f"{CLOUD_API_URL}{full_path}"
    headers = {
        "X-Cloud-Timestamp": timestamp,
        "X-Cloud-Sign": sign,
    }

    file_name = Path(file_path).name
    content_type = "audio/wav"

    try:
        # 使用 urllib 构建 multipart/form-data 请求
        # Build multipart/form-data request using urllib
        boundary = f"----CloudBoundary{int(time.time() * 1000)}"

        with open(file_path, "rb") as f:
            file_data = f.read()

        body_parts = []
        # 文件字段 / File field
        body_parts.append(f"--{boundary}".encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"'.encode()
        )
        body_parts.append(f"Content-Type: {content_type}".encode())
        body_parts.append(b"")
        body_parts.append(file_data)
        body_parts.append(f"--{boundary}--".encode())

        body = b"\r\n".join(body_parts)

        req_headers = {
            **headers,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")

        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode())

    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
            msg = err_body.get("detail", str(e))
        except Exception:
            msg = f"HTTP {e.code}"
        # 服务端业务错误（如 SUCCESS_WITH_NO_VALID_FRAGMENT）必须向上透传真实 detail，
        # 否则上层会用通用文案覆盖，导致 classify_error 无法命中可读提示。
        # Server business errors must propagate the real detail; otherwise upstream replaces it
        # with a generic message and classify_error can't produce a readable suggestion.
        logger.warning(f"云端文件上传失败: {path} → {msg}")
        raise RuntimeError(msg)

    except urllib.error.URLError as e:
        logger.warning(f"云端文件连接失败: {path} → {e.reason}")
        return None

    except Exception as e:
        logger.warning(f"云端文件上传异常: {path} → {e}")
        return None


def cloud_transcribe(audio_file_path: str, user_id: str = "", model: str = "paraformer-v2") -> dict | None:
    """通过云端代理提交音频转写 / Submit audio for transcription via cloud proxy.

    Args:
        audio_file_path: 本地音频文件路径 / Local audio file path
        user_id: 用户 ID / User ID
        model: ASR 模型名 / ASR model name

    Returns:
        转写结果 dict，失败返回 None / Transcription result dict; None on failure
    """
    if not is_cloud_enabled():
        return None

    from pathlib import Path

    logger.info(
        f"云端 ASR 转写: user={user_id[:8] if user_id else 'anon'}, "
        f"file={Path(audio_file_path).name}, model={model}"
    )

    params = {
        "user_id": user_id,
        "model": model,
        "diarization_enabled": "true",
    }

    result = _cloud_upload_file("/api/cloud/asr/transcribe", audio_file_path, params)

    if result:
        dialogue = result.get("dialogue", [])
        logger.info(
            f"云端 ASR 转写成功: user={user_id[:8] if user_id else 'anon'}, "
            f"dialogue_blocks={len(dialogue)}"
        )
    return result
