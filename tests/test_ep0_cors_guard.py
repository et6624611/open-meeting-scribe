"""T-001 复发修复回归：企业面跨源写守卫同源判定（浏览器形态组合面）。

根因：v10 cross_origin_write_guard 的 _cors_origins 白名单只含个人版宿主端口，
企业实例部署在任意 LAN ip:port ⇒ 浏览器 Origin 必不命中 ⇒ /api/v1 全部浏览器写请求 403。
TestClient/curl 无 Origin 头历史上从未触发该路径——"浏览器形态≠工具形态"第三次踩坑。
"""
from __future__ import annotations

import pytest


def test_same_origin_helper_semantics():
    from app.server import _same_origin_for_enterprise as f

    assert f("http://10.0.0.7:8010", "10.0.0.7:8010") is True
    assert f("https://intranet.corp", "intranet.corp") is True
    assert f("http://localhost:8010", "localhost:8010") is True
    # 外部 origin / 伪造不匹配 / 沙箱 null / 非 http scheme / 缺失——全部保持拒绝（CSRF 语义不放宽）
    assert f("http://evil.example", "localhost:8010") is False
    assert f("http://localhost:8011", "localhost:8010") is False
    assert f("null", "localhost:8010") is False
    assert f("file://", "localhost:8010") is False
    assert f("", "localhost:8010") is False
    assert f("http://localhost:8010", None) is False


def test_guard_enterprise_prefix_same_origin_allowed():
    """同源 Origin 的 /api/v1 写请求穿过守卫（到端点层后按各自语义响应，不再是 403 cross_origin_write_blocked）。"""
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/v1/context/tasks/tsk_g/snapshot", json={}, headers={"Origin": "http://testserver"})
    body = getattr(r, "json", lambda: {})()
    assert body.get("detail") != "cross_origin_write_blocked", r.text
    # 穿透守卫后的任一非守卫状态均合法（404/405=未挂载企业路由；401/422=端点层语义），唯独不允许守卫 403
    assert r.status_code in (401, 404, 405, 422)


def test_guard_enterprise_prefix_external_origin_still_blocked():
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/v1/context/tasks/tsk_g/snapshot", json={}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403 and r.json()["detail"] == "cross_origin_write_blocked"
    sandbox = c.post("/api/v1/auth/login", json={}, headers={"Origin": "null"})
    assert sandbox.status_code == 403 and sandbox.json()["detail"] == "cross_origin_write_blocked"


def test_guard_personal_prefix_zero_change():
    """个人版面守卫行为不变：同源 Origin 也不豁免（个人版口径是 _cors_origins 白名单）。"""
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/tasks", json={}, headers={"Origin": "http://testserver"})
    assert r.status_code == 403 and r.json()["detail"] == "cross_origin_write_blocked"
