"""
tests/test_origin_guard.py — 写请求 Origin 守卫中间件单测（洞察板放开 <script> 的同期防线）

规则：写方法（POST/PUT/PATCH/DELETE）+ 路径以 /api/ 开头 + 不在 _AUTH_EXEMPT_PREFIXES 内
⇒ Origin 缺失放行、命中 CORS 白名单放行、其余（含 sandbox 的 Origin: null）403 并落 audit.log。
"""

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tmp_board_dir(tmp_path, monkeypatch):
    import core.insight_board as ib
    d = tmp_path / "tasks"
    d.mkdir()
    monkeypatch.setattr(ib, "BOARD_TASKS_DIR", d)
    return d


class TestOriginGuard:
    def test_null_origin_write_blocked(self, client):
        r = client.post("/api/insights/board/ghost/boards",
                        json={"title": "x"}, headers={"Origin": "null"})
        assert r.status_code == 403
        assert r.json()["detail"] == "cross_origin_write_blocked"

    def test_foreign_origin_write_blocked(self, client):
        r = client.post("/api/tasks/ghost/correct-text",
                        json={"old": "a", "new": "b"},
                        headers={"Origin": "http://evil.example"})
        assert r.status_code == 403

    def test_missing_origin_write_allowed(self, client, tmp_board_dir):
        # 无头客户端（CLI/curl）不带 Origin → 放行（现状本就全放行，不构成新缺口）
        r = client.post("/api/insights/board/t-no/boards", json={"title": "标题"})
        assert r.status_code != 403

    def test_whitelisted_origin_allowed(self, client, tmp_board_dir):
        r = client.post("/api/insights/board/t-ok/boards", json={"title": "标题"},
                        headers={"Origin": "http://localhost:5173"})
        assert r.status_code != 403

    def test_get_not_guarded(self, client):
        # 读方法不受写守卫约束
        r = client.get("/api/insights/board/x", headers={"Origin": "null"})
        assert r.status_code == 200

    def test_exempt_prefix_not_guarded(self, client):
        # /api/agent-tools/* 在豁免白名单里（用进程内 bearer 另护），写守卫不拦
        r = client.post("/api/agent-tools/invoke", json={"name": "nope", "arguments": {}},
                        headers={"Origin": "null"})
        assert r.status_code != 403
