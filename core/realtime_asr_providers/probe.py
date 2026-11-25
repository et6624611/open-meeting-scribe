"""core/realtime_asr_providers/probe.py — 实时 ASR 连通性探测（不传音频）。"""

from __future__ import annotations

import asyncio
import logging
import time

import requests

from .registry import get_spec

logger = logging.getLogger(__name__)


def probe_realtime_asr(provider: str, credentials: dict, model: str = "",
                       base_url: str = "") -> dict:
    """返回 {ok, message|error, latency_ms}；不消耗音频、不回显密钥。"""
    if provider == "dashscope":
        return _probe_dashscope(credentials.get("api_key", ""), base_url)
    if provider == "volcengine":
        return _probe_volcengine(credentials, model, base_url)
    return {"ok": False, "error": f"暂不支持探测厂商: {provider}"}


def _probe_dashscope(api_key: str, base_url: str = "") -> dict:
    if not api_key:
        return {"ok": False, "error": "未配置 API Key"}
    url = (base_url or "https://dashscope.aliyuncs.com").rstrip("/") + "/api/v1/uploads"
    started = time.perf_counter()
    try:
        resp = requests.get(
            url,
            params={"action": "getPolicy", "model": "paraformer-v2"},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        latency = int((time.perf_counter() - started) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "message": "连接成功", "latency_ms": latency}
        if resp.status_code == 401:
            return {"ok": False, "error": "API Key 无效（401）"}
        if resp.status_code == 403:
            return {"ok": False, "error": "无语音服务权限（403）"}
        return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:120]}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "连接超时（10s）"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "无法连接到服务地址"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _probe_volcengine(credentials: dict, model: str, base_url: str) -> dict:
    if not credentials.get("api_key"):
        return {"ok": False, "error": "未配置 API Key"}

    from .volcengine import VolcengineProvider

    provider = VolcengineProvider(
        credentials=credentials,
        model=model or "bigmodel",
        options={"base_url": base_url or "", "enable_speaker": False},
    )
    started = time.perf_counter()

    async def _run() -> dict:
        import websockets

        async with websockets.connect(
            provider.ws_url(),
            additional_headers=provider.ws_headers(),
            max_size=None,
            open_timeout=10,
        ) as ws:
            await provider.on_open(ws)
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
            except asyncio.TimeoutError:
                return {"ok": True, "message": "连接成功", "latency_ms": int((time.perf_counter() - started) * 1000)}
            for event in provider.decode_message(raw):
                if event.get("type") == "error":
                    return {"ok": False, "error": event.get("message", "服务端返回错误")[:200]}
            return {"ok": True, "message": "连接成功", "latency_ms": int((time.perf_counter() - started) * 1000)}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        text = str(exc)
        # 握手阶段可能带签名/密钥信息，只保留前 160 字且去掉 query
        text = text.split("?")[0][:160]
        return {"ok": False, "error": f"连接失败: {text}"}


def capabilities_for(provider: str, model: str) -> dict:
    spec = get_spec(provider)
    return spec.capabilities_for(model) if spec else {}
