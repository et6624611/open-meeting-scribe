"""
core/llm.py — LLM provider（OpenAI 兼容端点）

作者：Yongliang Wang
创建：2026-09-03
版本：1.0.0

职责：
  1. 调用 OpenAI 兼容的 chat/completions 端点
  2. 支持流式/非流式输出
  3. 用于纪要生成、AI 对话等

Provider 配置从 settings.json 动态读取（app.store.get_llm_config），
支持 DashScope / OpenAI / DeepSeek / Moonshot 等任意兼容端点。
回退到环境变量 DASHSCOPE_API_KEY。

提供同步（requests）和异步（httpx）两种调用方式：
  - 同步版 chat_completion：供后台线程（管线、实时总结）使用
  - 异步版 async_chat_completion：供 FastAPI async 端点使用，不阻塞事件循环
"""

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Generator

import httpx
import requests

logger = logging.getLogger(__name__)

# 异步 HTTP 客户端（连接池复用，避免每次请求重建连接）
_async_client: httpx.AsyncClient | None = None


def _get_async_client() -> httpx.AsyncClient:
    """获取/创建全局异步 HTTP 客户端（连接池复用）"""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _async_client


async def close_async_client() -> None:
    """关闭异步 HTTP 客户端（应用关闭时调用）"""
    global _async_client
    if _async_client and not _async_client.is_closed:
        await _async_client.aclose()
        _async_client = None


def _get_config() -> dict:
    """获取当前 LLM 配置（base_url + api_key + model），优先从 settings 读取"""
    from app.store import get_llm_config
    return get_llm_config()


def _get_api_key() -> str:
    """获取当前生效的 API Key（排除占位符）。
    Get currently active API Key (excluding placeholders).
    """
    from app.store import get_active_api_key
    key = get_active_api_key()
    if not key or _is_placeholder_key(key):
        raise RuntimeError("未设置 API Key，请在设置页面配置或通过 .env 配置 DASHSCOPE_API_KEY")
    return key


def _is_placeholder_key(key: str) -> bool:
    """检测 API Key 是否为模板占位符值。
    Detect whether an API key is a template placeholder value.
    """
    if not key:
        return True
    k = key.lower()
    return (
        "xxxx" in k
        or "sk-xxx" in k
        or k.startswith("your-")
        or "your_api_key" in k
        or "your-api-key" in k
        or len(k) < 20  # 真实 Key 通常较长 / Real keys are usually longer
    )


def _should_use_cloud() -> bool:
    """判断是否应走云端代理（无本地 API Key 或 Key 为占位符，且云端可用）。
    Check if cloud proxy should be used (no local API key or key is placeholder, and cloud is enabled).

    用户偏好 prefer_subscription 开启时，即使有本地 Key 也优先走云端代理消耗订阅配额。
    When prefer_subscription is enabled, prefer cloud proxy to consume subscription quota.
    """
    # 用户偏好覆盖：优先使用订阅流量 / User preference override: prefer subscription quota
    try:
        from core.users import get_current_user
        from core.metering import TIER_QUOTAS
        user = get_current_user()
        if user and user.get("prefs", {}).get("prefer_subscription", False):
            subscription = user.get("subscription", {})
            if subscription.get("tier") in TIER_QUOTAS:
                try:
                    from core.cloud_client import is_cloud_enabled
                    if is_cloud_enabled():
                        return True
                except Exception:
                    pass
    except Exception:
        pass

    try:
        from app.store import get_active_api_key
        key = get_active_api_key()
        if key and not _is_placeholder_key(key):
            return False  # 有有效本地 Key，用本地 / Have valid local key, use local
    except Exception:
        pass
    try:
        from core.cloud_client import is_cloud_enabled
        return is_cloud_enabled()
    except Exception:
        return False


def _get_cloud_user_id() -> str:
    """获取当前用户 ID（供云端配额检查） / Get current user ID for cloud quota check."""
    try:
        from core.users import get_current_user
        user = get_current_user()
        if user:
            return user.get("id", "")
    except Exception:
        pass
    return ""


def _try_cloud_llm(messages, model, temperature, max_tokens) -> str:
    """尝试通过云端代理调用 LLM，返回生成的文本。失败抛出 RuntimeError。
    Try cloud LLM proxy; returns generated text. Raises RuntimeError on failure.
    """
    from core.cloud_client import cloud_llm_chat, is_cloud_enabled
    user_id = _get_cloud_user_id()
    logger.info(f"LLM 无本地 Key，尝试云端代理: user={user_id[:8] if user_id else 'anon'}")
    result = cloud_llm_chat(messages, model, temperature, max_tokens, user_id)
    if result is None:
        # 区分：云端未启用 vs 云端调用失败 / Distinguish: cloud not enabled vs cloud call failed
        if not is_cloud_enabled():
            raise RuntimeError(
                "AI 功能未配置。请在设置中配置 API Key，或连接云端服务器。"
            )
        raise RuntimeError(
            "云端 AI 服务调用失败。可能原因：\n"
            "1. 云端 AI 端点未部署（/api/cloud/llm/chat/completions 不存在）\n"
            "2. 网络连接异常\n"
            "3. 请在设置中配置自己的 API Key"
        )
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content


def _get_base_url() -> str:
    """获取当前 LLM 的 Base URL"""
    cfg = _get_config()
    url = cfg.get("base_url", "")
    if not url:
        url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    return url.rstrip("/")


def _build_request_body(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> dict:
    """构建请求体（同步/异步共用）"""
    if model is None:
        cfg = _get_config()
        model = cfg.get("model", "qwen-plus")
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def _get_headers() -> dict:
    """构建请求头（同步/异步共用）"""
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


def _extract_content(data: dict) -> str:
    """从响应中提取生成内容"""
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


@dataclass
class LlmResult:
    """LLM 调用完整结果（含元数据） / Full LLM call result with metadata."""
    content: str
    model: str
    usage: dict          # {prompt_tokens, completion_tokens, total_tokens}
    finish_reason: str   # "stop" | "length" | "content_filter"
    id: str              # 请求唯一标识 / Request unique ID


def _extract_full_result(data: dict) -> LlmResult:
    """从 API 响应中提取完整结果（含元数据） / Extract full result from API response."""
    choice = data.get("choices", [{}])[0]
    usage = data.get("usage", {})
    return LlmResult(
        content=choice.get("message", {}).get("content", ""),
        model=data.get("model", ""),
        usage={
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
        finish_reason=choice.get("finish_reason", ""),
        id=data.get("id", ""),
    )


# ============================================================
# 同步版（供后台线程使用）
# ============================================================


def chat_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    同步调用 LLM（供后台线程使用）。

    安全守卫：若从 asyncio 事件循环线程直接调用，自动委托到线程池，
    防止阻塞事件循环。后台线程（管线、Timer）中仍同步执行。
    """
    # 安全守卫：检测是否从事件循环线程调用（会阻塞事件循环）
    # FastAPI/Uvicorn 的事件循环始终在主线程中运行
    _in_loop_thread = False
    try:
        asyncio.get_running_loop()
        _in_loop_thread = threading.current_thread() is threading.main_thread()
    except RuntimeError:
        pass  # 无运行中的事件循环，正常同步执行
    if _in_loop_thread:
        logger.warning(
            "chat_completion 从事件循环线程调用，自动委托到线程池以避免阻塞。"
            "调用方应改用 async_chat_completion_safe 或 asyncio.to_thread。"
        )
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                _chat_completion_raw, messages, model, temperature, max_tokens
            )
            return future.result()

    return _chat_completion_raw(messages, model, temperature, max_tokens)


# ============================================================
# 异步安全包装（供实时模块的 Timer 线程使用）
# ============================================================


async def async_chat_completion_safe(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    异步安全包装：将同步 LLM 调用委托到线程池执行。

    使用 asyncio.to_thread，不阻塞 asyncio 事件循环。
    供 realtime_summary / realtime_chapters 等模块的定时器线程
    通过 run_coroutine_threadsafe 调度使用。
    """
    return await asyncio.to_thread(
        _chat_completion_raw,
        messages, model, temperature, max_tokens,
    )


def _chat_completion_raw(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """同步 LLM 调用的实际执行体（无事件循环守卫，供线程池委托使用）"""
    # 云端代理回退 / Cloud proxy fallback
    if _should_use_cloud():
        return _try_cloud_llm(messages, model, temperature, max_tokens)

    base_url = _get_base_url()
    headers = _get_headers()
    body = _build_request_body(messages, model, temperature, max_tokens)

    logger.info(f"调用 LLM（同步）: url={base_url}, model={body['model']}, messages={len(messages)}")

    start = time.perf_counter()
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        content = _extract_content(resp.json())
        elapsed = time.perf_counter() - start
        logger.info(f"[PERF] LLM 同步调用: {elapsed:.3f}s, {len(content)} 字符")
        return content

    except requests.exceptions.Timeout:
        elapsed = time.perf_counter() - start
        logger.warning(f"[PERF] LLM 同步调用超时: {elapsed:.3f}s")
        raise RuntimeError("LLM 调用超时")
    except requests.exceptions.HTTPError as e:
        elapsed = time.perf_counter() - start
        status = e.response.status_code if e.response is not None else "?"
        logger.warning(f"[PERF] LLM 同步调用失败: HTTP {status}, {elapsed:.3f}s")
        raise RuntimeError(f"LLM 调用失败: HTTP {status}")
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.warning(f"[PERF] LLM 同步调用异常: {elapsed:.3f}s")
        raise RuntimeError(f"LLM 调用失败: {e}")


# ============================================================
# 异步版（供 FastAPI async 端点使用，不阻塞事件循环）
# ============================================================


async def async_chat_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    异步调用 LLM（供 FastAPI async 端点使用）。

    使用 httpx.AsyncClient，不阻塞 asyncio 事件循环。
    无本地 Key 时自动走云端代理。 / Auto-fallback to cloud proxy when no local key.
    """
    # 云端代理回退 / Cloud proxy fallback
    if _should_use_cloud():
        return await asyncio.to_thread(
            _try_cloud_llm, messages, model, temperature, max_tokens
        )

    base_url = _get_base_url()
    client = _get_async_client()
    headers = _get_headers()
    body = _build_request_body(messages, model, temperature, max_tokens)

    logger.info(f"调用 LLM（异步）: url={base_url}, model={body['model']}, messages={len(messages)}")

    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        content = _extract_content(resp.json())
        elapsed = time.perf_counter() - start
        logger.info(f"[PERF] LLM 异步调用: {elapsed:.3f}s, {len(content)} 字符")
        return content

    except httpx.TimeoutException:
        elapsed = time.perf_counter() - start
        logger.warning(f"[PERF] LLM 异步调用超时: {elapsed:.3f}s")
        raise RuntimeError("LLM 调用超时")
    except httpx.HTTPStatusError as e:
        elapsed = time.perf_counter() - start
        logger.warning(f"[PERF] LLM 异步调用失败: HTTP {e.response.status_code}, {elapsed:.3f}s")
        raise RuntimeError(f"LLM 调用失败: HTTP {e.response.status_code}")
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.warning(f"[PERF] LLM 异步调用异常: {elapsed:.3f}s")
        raise RuntimeError(f"LLM 调用失败: {e}")


# ============================================================
# 异步完整版（含元数据，供 chat 端点使用）
# ============================================================


async def async_chat_completion_full(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LlmResult:
    """
    异步调用 LLM 并返回完整结果（含元数据）。

    供 /api/chat 端点使用，返回 usage、finish_reason 等信息供前端展示。
    使用 httpx.AsyncClient，不阻塞 asyncio 事件循环。
    无本地 Key 时自动走云端代理。 / Auto-fallback to cloud proxy when no local key.
    """
    # 云端代理回退 / Cloud proxy fallback
    if _should_use_cloud():
        content = await asyncio.to_thread(
            _try_cloud_llm, messages, model, temperature, max_tokens
        )
        return LlmResult(
            content=content,
            model=model or "qwen-plus",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            finish_reason="stop",
            id="cloud-proxy",
        )

    base_url = _get_base_url()
    client = _get_async_client()
    headers = _get_headers()
    body = _build_request_body(messages, model, temperature, max_tokens)

    logger.info(f"调用 LLM（异步-完整）: url={base_url}, model={body['model']}, messages={len(messages)}")

    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        result = _extract_full_result(resp.json())
        elapsed = time.perf_counter() - start
        logger.info(
            f"[PERF] LLM 异步调用(完整): {elapsed:.3f}s, {len(result.content)} 字符, "
            f"tokens={result.usage.get('total_tokens', 0)}"
        )
        return result

    except httpx.TimeoutException:
        elapsed = time.perf_counter() - start
        logger.warning(f"[PERF] LLM 异步调用超时: {elapsed:.3f}s")
        raise RuntimeError("LLM 调用超时")
    except httpx.HTTPStatusError as e:
        elapsed = time.perf_counter() - start
        logger.warning(f"[PERF] LLM 异步调用失败: HTTP {e.response.status_code}, {elapsed:.3f}s")
        raise RuntimeError(f"LLM 调用失败: HTTP {e.response.status_code}")
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.warning(f"[PERF] LLM 异步调用异常: {elapsed:.3f}s")
        raise RuntimeError(f"LLM 调用失败: {e}")


# ============================================================
# 流式版（同步，供 CLI 或后台线程使用）
# ============================================================


def chat_completion_stream(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Generator[str, None, None]:
    """
    流式调用 LLM。

    Yields:
        逐块生成的文本
    """
    base_url = _get_base_url()
    headers = _get_headers()
    body = _build_request_body(messages, model, temperature, max_tokens)
    body["stream"] = True

    resp = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=body,
        timeout=120,
        stream=True,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            import json
            data = json.loads(data_str)
            delta = data.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                yield content
