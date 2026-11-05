"""core/llm.py 单元测试：超时包装、HTTP 错误包装、未配置 API Key 报错。

全部 mock，不打真实 API，离线可跑。
"""
from __future__ import annotations

import pytest
import requests

from core import llm


# ── 辅助：构造一个假的 HTTP response ────────────────────────────────


def _fake_response(json_data, status_code=200):
    """mock requests.Response。"""
    import json as _json
    class _Resp:
        def __init__(self):
            self._json = json_data
            self.status_code = status_code
            self.text = _json.dumps(json_data)

        def raise_for_status(self):
            if 400 <= self.status_code < 600:
                resp = requests.Response()
                resp.status_code = self.status_code
                raise requests.exceptions.HTTPError(
                    f"{self.status_code} Error", response=resp
                )

        def json(self):
            return self._json

        @property
        def content(self):
            return self.text.encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def iter_lines(self):
            return iter([])

    return _Resp()


@pytest.fixture()
def _no_cloud(monkeypatch):
    """所有同步测试都走 direct 路径（云端路径单独测）。"""
    monkeypatch.setattr(llm, "_should_use_cloud", lambda: False)
    # _get_base_url 和 _get_headers 在 direct 路径内部调用
    monkeypatch.setattr(llm, "_get_base_url", lambda: "https://example.com/v1")
    monkeypatch.setattr(llm, "_get_api_key", lambda: "sk-test-123")


# ── chat_completion 成功路径 ───────────────────────────────────────


def test_chat_completion_success(monkeypatch, _no_cloud):
    fake_json = {
        "choices": [{"message": {"content": "好的，会议纪要已生成。"}, "finish_reason": "stop"}],
        "model": "qwen-plus",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "id": "chatcmpl-test",
    }
    monkeypatch.setattr(requests, "post", lambda *a, **kw: _fake_response(fake_json))

    result = llm.chat_completion([{"role": "user", "content": "你好"}])
    assert result == "好的，会议纪要已生成。"


# ── 超时包装 ──────────────────────────────────────────────────────


def test_chat_completion_timeout_wrapped(monkeypatch, _no_cloud):
    def _raise_timeout(*a, **kw):
        raise requests.exceptions.Timeout("Read timed out. (read timeout=120)")

    monkeypatch.setattr(requests, "post", _raise_timeout)

    with pytest.raises(RuntimeError, match="LLM 调用超时"):
        llm.chat_completion([{"role": "user", "content": "hello"}])


def test_chat_completion_custom_timeout_arg_forwarded(monkeypatch, _no_cloud):
    captured = {}

    def _post(*a, **kw):
        captured["timeout"] = kw.get("timeout")
        return _fake_response({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(requests, "post", _post)
    llm.chat_completion([{"role": "user", "content": "hi"}], timeout=5.0)
    assert captured["timeout"] == 5.0

    # 缺省走 llm_timeout_seconds()
    llm.chat_completion([{"role": "user", "content": "hi"}])
    assert captured["timeout"] == 120.0  # 默认


# ── HTTP 错误包装 ──────────────────────────────────────────────────


@pytest.mark.parametrize("status,expected", [
    (401, "HTTP 401"),
    (403, "HTTP 403"),
    (429, "HTTP 429"),
    (500, "HTTP 500"),
])
def test_chat_completion_http_error_wrapped(monkeypatch, _no_cloud, status, expected):
    def _raise_http(*a, **kw):
        resp = requests.Response()
        resp.status_code = status
        raise requests.exceptions.HTTPError(f"{status} Error", response=resp)

    monkeypatch.setattr(requests, "post", _raise_http)

    with pytest.raises(RuntimeError, match=expected):
        llm.chat_completion([{"role": "user", "content": "hello"}])


def test_chat_completion_other_exception_wrapped(monkeypatch, _no_cloud):
    def _boom(*a, **kw):
        raise OSError("Network unreachable")

    monkeypatch.setattr(requests, "post", _boom)
    with pytest.raises(RuntimeError, match="Network unreachable"):
        llm.chat_completion([{"role": "user", "content": "hello"}])


# ── 未配置 API Key ─────────────────────────────────────────────────


def test_chat_completion_no_api_key_raises(monkeypatch):
    monkeypatch.setattr(llm, "_should_use_cloud", lambda: False)
    monkeypatch.setattr(llm, "_get_base_url", lambda: "https://dashscope.aliyuncs.com")

    def _no_key():
        raise RuntimeError("未设置 API Key，请在设置页面配置或通过 .env 配置 DASHSCOPE_API_KEY")

    monkeypatch.setattr(llm, "_get_api_key", _no_key)

    with pytest.raises(RuntimeError, match="未设置 API Key"):
        llm.chat_completion([{"role": "user", "content": "hi"}])


def test_chat_completion_unconfigured_route_raises(monkeypatch):
    """路由未配置时 _should_use_cloud 直接抛错。"""
    def _unconfigured():
        raise RuntimeError("AI 纪要来源未设置，请在「设置 > API 配置」选择算力来源")

    monkeypatch.setattr(llm, "_should_use_cloud", _unconfigured)

    with pytest.raises(RuntimeError, match="未设置"):
        llm.chat_completion([{"role": "user", "content": "hi"}])


# ── chat_completion_full（完整版返回 metadata）─────────────────────


def test_chat_completion_full_returns_metadata(monkeypatch, _no_cloud):
    fake_json = {
        "choices": [
            {"message": {"content": "摘要"}, "finish_reason": "stop"},
        ],
        "model": "qwen-plus",
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        "id": "cmpl-xyz",
    }
    monkeypatch.setattr(requests, "post", lambda *a, **kw: _fake_response(fake_json))

    result = llm.chat_completion_full([{"role": "user", "content": "总结"}])
    assert result.content == "摘要"
    assert result.model == "qwen-plus"
    assert result.usage["total_tokens"] == 15
    assert result.finish_reason == "stop"
    assert result.id == "cmpl-xyz"


# ── localhost 自持端点允许空 API Key ────────────────────────────────


def test_is_localhost_base_url():
    assert llm.is_localhost_base_url("http://localhost:11434")
    assert llm.is_localhost_base_url("http://127.0.0.1:8080")
    assert llm.is_localhost_base_url("http://[::1]:8000")
    assert llm.is_localhost_base_url("http://0.0.0.0:9090")
    assert not llm.is_localhost_base_url("https://dashscope.aliyuncs.com")
    assert not llm.is_localhost_base_url("")
    assert not llm.is_localhost_base_url("https://api.deepseek.com")


def test_headers_localhost_omits_authorization(monkeypatch):
    """localhost 端点且无有效 Key 时，请求头省略 Authorization。"""
    monkeypatch.setattr(llm, "_should_use_cloud", lambda: False)
    monkeypatch.setattr(llm, "_get_base_url", lambda: "http://localhost:11434")
    monkeypatch.setattr("app.store.get_active_api_key", lambda: "")

    headers = llm._get_headers()
    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"


def test_headers_remote_requires_api_key(monkeypatch):
    """远端端点必须有有效 Key，否则抛错。"""
    monkeypatch.setattr(llm, "_should_use_cloud", lambda: False)
    monkeypatch.setattr(llm, "_get_base_url", lambda: "https://dashscope.aliyuncs.com")

    def _no_key():
        raise RuntimeError("未设置 API Key")

    monkeypatch.setattr(llm, "_get_api_key", _no_key)

    with pytest.raises(RuntimeError, match="未设置"):
        llm._get_headers()


# ── _cloud_safe_model 云端模型守护 ─────────────────────────────────


@pytest.mark.parametrize("model,expected", [
    (None, "qwen-plus"),
    ("", "qwen-plus"),
    ("qwen3:8b", "qwen-plus"),     # 本地 tag → 回退
    ("ollama:llama3", "qwen-plus"), # 本地 tag → 回退
    ("qwen-plus", "qwen-plus"),    # 云端模型 → 透传
    ("deepseek-chat", "deepseek-chat"), # 云端模型 → 透传
    ("gpt-4o", "gpt-4o"),          # 云端模型 → 透传
])
def test_cloud_safe_model(model, expected):
    assert llm._cloud_safe_model(model) == expected


# ── 流式版（基础结构测试）────────────────────────────────────────


def test_chat_completion_stream_yields_content(monkeypatch, _no_cloud):
    import json

    class _StreamResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter([
                b'data: ' + json.dumps({"choices": [{"delta": {"content": "你"}}]}).encode(),
                b'data: ' + json.dumps({"choices": [{"delta": {"content": "好"}}]}).encode(),
                b'data: [DONE]',
            ])

    monkeypatch.setattr(requests, "post", lambda *a, **kw: _StreamResp())

    parts = list(llm.chat_completion_stream([{"role": "user", "content": "say hi"}]))
    assert parts == ["你", "好"]


# ── llm_timeout_seconds 超时可配（D018a）─────────────────────────


def test_timeout_env_default(monkeypatch):
    monkeypatch.delenv("OMS_LLM_TIMEOUT_SECONDS", raising=False)
    assert llm.llm_timeout_seconds() == 120.0

    monkeypatch.setenv("OMS_LLM_TIMEOUT_SECONDS", "30")
    assert llm.llm_timeout_seconds() == 30.0

    monkeypatch.setenv("OMS_LLM_TIMEOUT_SECONDS", "abc")
    assert llm.llm_timeout_seconds() == 120.0

    monkeypatch.setenv("OMS_LLM_TIMEOUT_SECONDS", "-1")
    assert llm.llm_timeout_seconds() == 120.0

    monkeypatch.delenv("OMS_LLM_SUMMARY_RETRY_TIMEOUT_SECONDS", raising=False)
    assert llm.summary_retry_timeout_seconds() == 180.0
