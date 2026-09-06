"""
core/llm.py — LLM provider（OpenAI 兼容端点）

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

import os
import logging
import requests

import httpx

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
    """获取当前生效的 API Key"""
    from app.store import get_active_api_key
    key = get_active_api_key()
    if not key:
        raise RuntimeError("未设置 API Key，请在设置页面配置或通过 .env 配置 DASHSCOPE_API_KEY")
    return key


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

    注意：不要在 async 函数中直接调用此版本，会阻塞事件循环。
    async 端点请使用 async_chat_completion。
    """
    base_url = _get_base_url()
    headers = _get_headers()
    body = _build_request_body(messages, model, temperature, max_tokens)

    logger.info(f"调用 LLM（同步）: url={base_url}, model={body['model']}, messages={len(messages)}")

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        content = _extract_content(resp.json())
        logger.info(f"LLM 生成完成: {len(content)} 字符")
        return content

    except requests.exceptions.Timeout:
        raise RuntimeError("LLM 调用超时")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        raise RuntimeError(f"LLM 调用失败: HTTP {status}")
    except Exception as e:
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
    """
    base_url = _get_base_url()
    client = _get_async_client()
    headers = _get_headers()
    body = _build_request_body(messages, model, temperature, max_tokens)

    logger.info(f"调用 LLM（异步）: url={base_url}, model={body['model']}, messages={len(messages)}")

    try:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        content = _extract_content(resp.json())
        logger.info(f"LLM 异步生成完成: {len(content)} 字符")
        return content

    except httpx.TimeoutException:
        raise RuntimeError("LLM 调用超时")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"LLM 调用失败: HTTP {e.response.status_code}")
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}")


# ============================================================
# 流式版（同步，供 CLI 或后台线程使用）
# ============================================================


def chat_completion_stream(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
):
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
