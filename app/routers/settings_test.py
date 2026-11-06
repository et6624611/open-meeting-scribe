"""app/routers/settings_test.py — API 连接测试（ASR / LLM）。

端点：
  POST /api/settings/test      — 测试 API 连接（service_type 区分 asr/llm）
  POST /api/settings/test-llm  — LLM 连通性测试（PRD R4，返回 error_code）

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 settings.py 拆分）
"""

import logging
import os
import time

import requests
from fastapi import APIRouter

from core import settings_store
from core.i18n import _
from core.llm import is_localhost_base_url

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/settings/test")
def test_api_connection(data: dict = None):
    """
    测试 API 连接 / Test API connection.

    通过 service_type 区分测试目标 / Distinguish test target via service_type:
    - "asr"：测试语音转写服务连接 / Test ASR service connection
    - "llm"（默认）：测试纪要生成服务连接 / Test LLM service connection (default)
    """
    if not data:
        data = {}

    service_type = data.get("service_type", "llm")

    if service_type == "asr":
        return _test_asr_connection(data.get("asr"))
    else:
        return _test_ll_connection(data.get("llm"))


def _test_asr_connection(asr_data: dict | None) -> dict:
    """测试 ASR 服务连接（支持代理模式和直连模式） / Test ASR service connection (proxy and direct modes)."""
    cfg = settings_store.get_asr_config()
    mode = cfg.get("mode", "proxy")

    # 若前端传入了新配置，使用传入值覆盖 / Override with incoming config if provided
    if asr_data:
        mode = asr_data.get("mode", mode)

    if mode == "direct":
        return _test_asr_direct(asr_data)
    else:
        return _test_asr_proxy()


def _test_asr_proxy() -> dict:
    """测试 ASR 代理服务连接 / Test ASR proxy service connection."""
    cfg = settings_store.get_asr_config()
    proxy_url = cfg.get("proxy_url", "")

    if not proxy_url:
        return {"ok": False, "error": _("ASR proxy URL not configured")}

    # 调用代理健康检查端点 / Call proxy health check endpoint
    url = f"{proxy_url.rstrip('/')}/health"

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("dashscope_configured"):
                return {"ok": True, "message": _("ASR proxy service connected")}
            else:
                return {"ok": False, "error": _("Proxy server has no DASHSCOPE_API_KEY configured")}
        elif resp.status_code == 401:
            return {"ok": False, "error": _("Proxy signature verification failed")}
        else:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": _("Connection timeout (15s), please check network")}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": _("Cannot connect to proxy service, please check the address")}
    except Exception as e:
        return {"ok": False, "error": _("Test failed: {err}").format(err=str(e)[:200])}


def _test_asr_direct(asr_data: dict | None) -> dict:
    """测试直连模式 ASR 连接 / Test direct-mode ASR connection (submit minimal task to DashScope)."""
    if asr_data:
        base_url = asr_data.get("base_url", "")
        api_key = asr_data.get("api_key", "")
    else:
        cfg = settings_store.get_asr_config()
        base_url = cfg.get("base_url", "")
        api_key = cfg.get("api_key", "")

    if not api_key or "****" in api_key:
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": _("ASR API Key not configured")}
    if not base_url:
        base_url = "https://dashscope.aliyuncs.com"

    # 通过获取上传凭证来验证 API Key 有效性 / Verify API Key via upload credential (lightweight; no actual upload)
    url = f"{base_url.rstrip('/')}/api/v1/uploads"
    params = {"action": "getPolicy", "model": "paraformer-v2"}
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            return {"ok": True, "message": _("ASR direct connection successful")}
        elif resp.status_code == 401:
            return {"ok": False, "error": _("Invalid ASR API Key (401 Unauthorized)")}
        elif resp.status_code == 403:
            return {"ok": False, "error": _("No permission to access ASR service (403 Forbidden)")}
        else:
            error_msg = resp.text[:200]
            return {"ok": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": _("Connection timeout (15s), please check network")}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": _("Cannot connect to {url}, please check the address").format(url=base_url)}
    except Exception as e:
        return {"ok": False, "error": _("Test failed: {err}").format(err=str(e)[:200])}


def _test_ll_connection(llm_data: dict | None) -> dict:
    """测试 LLM（纪要生成）服务连接 / Test LLM (summary generation) service connection."""
    if llm_data:
        base_url = llm_data.get("base_url", "")
        api_key = llm_data.get("api_key", "")
        model = llm_data.get("model", "qwen-plus")
    else:
        cfg = settings_store.get_llm_config()
        base_url = cfg["base_url"]
        api_key = cfg["api_key"]
        model = cfg["model"]

    if not api_key or "****" in api_key:
        api_key = settings_store.get_active_api_key()

    if not api_key:
        return {"ok": False, "error": _("LLM API Key not configured")}
    if not base_url:
        return {"ok": False, "error": _("LLM API Base URL not configured")}

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        if resp.status_code == 200:
            return {"ok": True, "message": _("Connection successful, model {model} responding").format(model=model)}
        elif resp.status_code == 401:
            return {"ok": False, "error": _("Invalid LLM API Key (401 Unauthorized)")}
        elif resp.status_code == 403:
            return {"ok": False, "error": _("No permission to access LLM service (403 Forbidden)")}
        elif resp.status_code == 404:
            return {"ok": False, "error": _("Endpoint or model not found (404). Please check Base URL and model name")}
        elif resp.status_code == 429:
            return {"ok": False, "error": _("Too many requests (429 Rate Limited), the Key itself is valid")}
        else:
            error_msg = resp.text[:200]
            return {"ok": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": _("Connection timeout (15s), please check network or Base URL")}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": _("Cannot connect to {url}, please check the address").format(url=base_url)}
    except Exception as e:
        return {"ok": False, "error": _("Test failed: {err}").format(err=str(e)[:200])}


# ============================================================
# LLM 连通性测试（R4 / WP-A） / LLM connectivity test (R4 / WP-A)
# ============================================================

# PRD R4 边界：测试超时 10s / Test timeout per PRD R4
TEST_LLM_TIMEOUT_SECONDS = 10


@router.post("/api/settings/test-llm")
def test_llm_connection(data: dict = None):
    """
    LLM 连通性测试（PRD R4） / LLM connectivity test (PRD R4).

    发送一条最小 chat 请求，返回延迟与模型可达性；失败返回可行动排错文案
    （error_code: invalid_config / missing_key / service_down / model_not_pulled /
    auth_failed / rate_limited / timeout / http_error）。
    localhost 端点允许空 Key；非 localhost 的 http:// 端点返回显式安全警告。
    """
    incoming = (data or {}).get("llm") or data or {}
    cfg = settings_store.get_llm_config()

    base_url = (incoming.get("base_url") or cfg.get("base_url") or "").strip()
    model = (incoming.get("model") or cfg.get("model") or "").strip()
    # PRD R4 口径：显式传入空串 = 本次测试「无 Key」，不回填存量 Key（DEF-RETEST-03/04）；
    # 仅字段缺失或为脱敏占位（含 ****）时才沿用已存配置。
    # Explicit empty string means "test without a key" (PRD R4); only a missing or
    # masked (****) field falls back to the stored config.
    raw_key = incoming.get("api_key")
    if raw_key is None or "****" in raw_key:
        api_key = cfg.get("api_key") or ""
    else:
        api_key = raw_key.strip()

    if not base_url:
        return {
            "ok": False,
            "error_code": "invalid_config",
            "error": _("LLM API Base URL not configured"),
        }

    localhost = is_localhost_base_url(base_url)
    if not localhost and not api_key and raw_key is None:
        # 未显式传 Key 时才兜底旧版全局 Key；显式空串按「无 Key」处理返回 missing_key
        api_key = settings_store.get_active_api_key()
    if not api_key and not localhost:
        return {
            "ok": False,
            "error_code": "missing_key",
            "error": _("LLM API Key not configured"),
        }

    # R4 边界：非 localhost 端点要求 https，否则显式警告 / Non-localhost endpoints should use https
    warning = None
    if not localhost and base_url.startswith("http://"):
        warning = _("Non-localhost endpoint is not using HTTPS; the API Key will be sent in plaintext")

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model or "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
        "stream": False,
    }

    start = time.perf_counter()
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=TEST_LLM_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        return _test_llm_fail(
            "timeout",
            _("Connection timed out after {sec}s; the service may be overloaded or the model is still loading").format(sec=TEST_LLM_TIMEOUT_SECONDS),
            warning=warning,
        )
    except requests.exceptions.ConnectionError:
        if localhost:
            return _test_llm_fail(
                "service_down",
                _("Cannot connect to the local LLM service. Please make sure Ollama / LM Studio is running and listening on the configured port; if you call the endpoint directly from a browser, also check its CORS settings (for Ollama set OLLAMA_ORIGINS)"),
                warning=warning,
            )
        return _test_llm_fail(
            "service_down",
            _("Cannot connect to {url}; please check the address, network, and firewall settings").format(url=base_url),
            warning=warning,
        )
    except Exception as e:
        return _test_llm_fail("http_error", _("Test failed: {err}").format(err=str(e)[:200]), warning=warning)

    latency_ms = int((time.perf_counter() - start) * 1000)
    resp_text = (resp.text or "")[:500]
    resp_lower = resp_text.lower()

    if resp.status_code == 200:
        result = {
            "ok": True,
            "latency_ms": latency_ms,
            "model": model,
            "message": _("Connection successful, model {model} responding in {latency}ms").format(model=model, latency=latency_ms),
        }
        if warning:
            result["warning"] = warning
        return result

    # 模型未拉取/未加载：Ollama 404 "try pulling it first"；LM Studio 400/404 "model not found"
    model_missing_markers = ("not found", "pull", "does not exist", "no model", "load the model")
    if resp.status_code in (400, 404) and any(m in resp_lower for m in model_missing_markers):
        return _test_llm_fail(
            "model_not_pulled",
            _("Model '{model}' is not available on the server. Pull or load it first (for Ollama: `ollama pull {model}`; for LM Studio: load the model in the app), then retry").format(model=model),
            warning=warning,
        )
    if resp.status_code == 404:
        return _test_llm_fail(
            "invalid_config",
            _("Endpoint or model not found (404). Please check that Base URL ends with /v1 and the model name is correct"),
            warning=warning,
        )
    if resp.status_code in (401, 403):
        return _test_llm_fail(
            "auth_failed",
            _("Authentication failed (HTTP {code}). Please check the API Key").format(code=resp.status_code),
            warning=warning,
        )
    if resp.status_code == 429:
        return _test_llm_fail(
            "rate_limited",
            _("Too many requests (429 Rate Limited); the endpoint itself is reachable"),
            warning=warning,
        )
    return _test_llm_fail(
        "http_error",
        _("HTTP {code}: {detail}").format(code=resp.status_code, detail=resp_text[:200]),
        warning=warning,
    )


def _test_llm_fail(error_code: str, error: str, warning: str | None = None) -> dict:
    """构造 test-llm 失败响应 / Build test-llm failure response."""
    result = {"ok": False, "error_code": error_code, "error": error}
    if warning:
        result["warning"] = warning
    return result
