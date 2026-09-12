"""
tests/test_misc.py — 杂项域冒烟测试

覆盖 SMS 认证、GitHub OAuth、版本更新、用量查询、管理后台、
远程配置、理念传播、错误分类、静默检测配置等。
从 test_smoke.py 拆分而来。

运行方式：
  pytest tests/test_misc.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture
def client():
    """创建测试客户端"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_client():
    """创建管理后台测试客户端"""
    from app.admin_server import admin_app
    with TestClient(admin_app) as c:
        yield c


# ============================================================
# 错误分类域
# ============================================================

class TestErrorClassification:
    """core.errors 错误分类模块"""

    def test_module_imports(self):
        from core.errors import is_transient_error, classify_error
        assert callable(is_transient_error)
        assert callable(classify_error)

    def test_transient_error_detection(self):
        from core.errors import is_transient_error
        # 网络超时
        assert is_transient_error(TimeoutError("connection timed out")) is True
        assert is_transient_error(ConnectionError("connection refused")) is True
        # 关键词匹配
        assert is_transient_error(RuntimeError("Too many requests")) is True
        assert is_transient_error(RuntimeError("HTTP 429 rate limit")) is True
        assert is_transient_error(RuntimeError("503 Service Unavailable")) is True
        # 永久错误
        assert is_transient_error(FileNotFoundError("file not found")) is False
        assert is_transient_error(ValueError("invalid value")) is False

    def test_error_classification(self):
        from core.errors import classify_error
        # 瞬时错误
        result = classify_error(TimeoutError("timed out"))
        assert result["category"] == "transient"
        assert "建议" in result or "suggestion" in result

        # 音频错误
        result = classify_error(FileNotFoundError("音频文件不存在"))
        assert result["category"] == "audio"

        # API 配置错误
        result = classify_error(RuntimeError("未设置 DASHSCOPE_API_KEY"))
        assert result["category"] == "api_config"

        # 未知错误
        result = classify_error(RuntimeError("something weird happened"))
        assert result["category"] == "unknown"


# ============================================================
# 手机号短信认证域
# ============================================================

class TestSmsSendValidation:
    """POST /auth/sms/send 手机号格式校验"""

    def test_invalid_phone_short(self, client):
        """短号码返回 400"""
        resp = client.post("/auth/sms/send", json={"phone": "12345"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_invalid_phone_format(self, client):
        """非手机号格式返回 400"""
        resp = client.post("/auth/sms/send", json={"phone": "abcdefghijk"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_missing_phone_field(self, client):
        """缺少 phone 字段返回 422"""
        resp = client.post("/auth/sms/send", json={})
        assert resp.status_code == 422


class TestSmsVerifyValidation:
    """POST /auth/sms/verify 验证码校验"""

    def test_invalid_phone_returns_400(self, client):
        """手机号格式错误返回 400"""
        resp = client.post("/auth/sms/verify", json={"phone": "123", "code": "123456"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_empty_code_returns_400(self, client):
        """验证码为空返回 400"""
        resp = client.post("/auth/sms/verify", json={"phone": "13312343103", "code": ""})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_missing_fields_returns_422(self, client):
        """缺少必填字段返回 422"""
        resp = client.post("/auth/sms/verify", json={"phone": "13312343103"})
        assert resp.status_code == 422


class TestSmsSendHappyPath:
    """POST /auth/sms/send 有效号码发送路径

    回归背景：短信服务改为云端代理模式后，需确保代理返回成功时正确传递结果，
    代理返回失败时正确抛出错误而非 500。
    """

    def test_valid_phone_returns_success(self, client, monkeypatch):
        """有效手机号且代理返回 success=True 时应成功"""
        from core import sms

        # 隔离频率限制与真实网络调用
        monkeypatch.setattr(sms, "_sms_rate_limits", {})
        monkeypatch.setattr(sms, "_proxy_request", lambda path, payload: {
            "success": True,
            "expire_minutes": 5,
        })

        resp = client.post("/auth/sms/send", json={"phone": "13312343103"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["expire_minutes"] == 5

    def test_proxy_error_returns_400_json(self, client, monkeypatch):
        """代理返回 success=False 时应转为 400 JSON，而非 500"""
        from core import sms

        monkeypatch.setattr(sms, "_sms_rate_limits", {})
        monkeypatch.setattr(sms, "_proxy_request", lambda path, payload: {
            "success": False,
            "message": "模板不合法",
        })

        resp = client.post("/auth/sms/send", json={"phone": "13312343103"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "模板不合法" in data["message"]


class TestSmsCheckVerifyCode:
    """core.sms.check_verify_code 代理模式核验结果解析

    回归背景：短信服务改为云端代理后，核验结果由代理返回，
    需确保 success=true/false 正确映射为通过/失败。
    """

    def _patch_proxy(self, monkeypatch, *, success=True, message=""):
        from core import sms

        def fake_proxy(path, payload):
            return {"success": success, "message": message}

        monkeypatch.setattr(sms, "_proxy_request", fake_proxy)
        return sms

    def test_proxy_success_returns_true(self, monkeypatch):
        """代理返回 success=True 应判定核验通过"""
        sms = self._patch_proxy(monkeypatch, success=True)
        passed, reason = sms.check_verify_code("13312343103", "123456")
        assert passed is True
        assert reason == ""

    def test_proxy_failure_returns_false(self, monkeypatch):
        """代理返回 success=False 应判定核验失败"""
        sms = self._patch_proxy(monkeypatch, success=False, message="验证码错误或已过期")
        passed, reason = sms.check_verify_code("13312343103", "000000")
        assert passed is False
        assert reason == "验证码错误或已过期"

    def test_proxy_connection_error_returns_service_error(self, monkeypatch):
        """代理连接失败应视为服务异常，而非核验失败"""
        from core import sms

        def fake_proxy(path, payload):
            raise RuntimeError("短信代理连接失败: Connection refused")

        monkeypatch.setattr(sms, "_proxy_request", fake_proxy)
        passed, reason = sms.check_verify_code("13312343103", "123456")
        assert passed is False
        assert reason == "验证服务异常，请稍后重试"


# ============================================================
# 认证路由（auth）
# ============================================================

class TestAuthGithubLogin:
    """GET /auth/github 重定向到 GitHub 授权页"""

    def test_redirects_to_github(self, client):
        resp = client.get("/auth/github", follow_redirects=False)
        assert resp.status_code in (302, 307)
        location = resp.headers.get("location", "")
        assert "github.com" in location or "authorize" in location


class TestAuthMeNotLoggedIn:
    """GET /auth/me 未登录时返回 401"""

    def test_me_unauthorized(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401


class TestAuthLogout:
    """POST /auth/logout 正常返回"""

    def test_logout_ok(self, client):
        resp = client.post("/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data


class TestAuthCallbackMissingCode:
    """GET /auth/callback 缺少 code 参数时返回 400"""

    def test_callback_no_code(self, client):
        resp = client.get("/auth/callback?state=fake-state")
        assert resp.status_code == 400


# ============================================================
# 版本更新路由（update）
# ============================================================

class TestUpdateVersion:
    """GET /api/update/version 返回版本号"""

    def test_version_ok(self, client):
        resp = client.get("/api/update/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


class TestUpdateCheck:
    """GET /api/update/check 返回更新检查结果"""

    def test_check_ok(self, client):
        resp = client.get("/api/update/check")
        assert resp.status_code == 200
        data = resp.json()
        # 网络不可达时静默降级，但端点本身不 500
        assert isinstance(data, dict)


# ============================================================
# 用量查询路由（usage）
# ============================================================

class TestUsageSummary:
    """GET /api/usage/summary 返回用量汇总"""

    def test_summary_ok(self, client):
        resp = client.get("/api/usage/summary")
        assert resp.status_code == 200
        data = resp.json()
        # 未登录时返回 metered=False 或提示信息
        assert isinstance(data, dict)


class TestUsageHistory:
    """GET /api/usage/history 返回用量明细"""

    def test_history_ok(self, client):
        resp = client.get("/api/usage/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert isinstance(data["history"], (list, dict))


class TestUsageCheck:
    """GET /api/usage/check 配额预检"""

    def test_quota_check_ok(self, client):
        resp = client.get("/api/usage/check")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ============================================================
# 管理后台路由（admin）
# ============================================================

class TestAdminLoginNoPassword:
    """POST /api/admin/login 未配置密码时返回 500"""

    def test_login_no_password_configured(self, admin_client, monkeypatch):
        from app.routers import admin as admin_mod
        monkeypatch.setattr(admin_mod, "ADMIN_PASSWORD", "")
        resp = admin_client.post("/api/admin/login", json={"password": "test"})
        assert resp.status_code == 500


class TestAdminLoginWrongPassword:
    """POST /api/admin/login 密码错误返回 401"""

    def test_wrong_password(self, admin_client, monkeypatch):
        from app.routers import admin as admin_mod
        monkeypatch.setattr(admin_mod, "ADMIN_PASSWORD", "correct-password")
        resp = admin_client.post("/api/admin/login", json={"password": "wrong-password"})
        assert resp.status_code == 401


class TestAdminMeUnauthorized:
    """GET /api/admin/me 未认证返回 401"""

    def test_me_unauthorized(self, admin_client):
        resp = admin_client.get("/api/admin/me")
        assert resp.status_code == 401


class TestAdminOverviewUnauthorized:
    """GET /api/admin/overview 未认证返回 401"""

    def test_overview_unauthorized(self, admin_client):
        resp = admin_client.get("/api/admin/overview")
        assert resp.status_code == 401


class TestAdminLogout:
    """POST /api/admin/logout 正常返回"""

    def test_logout_ok(self, admin_client):
        resp = admin_client.post("/api/admin/logout")
        assert resp.status_code == 200


# ============================================================
# 远程配置路由（config）
# ============================================================

class TestConfigAnnouncements:
    """GET /api/config/announcements 返回公告列表"""

    def test_announcements_ok(self, client):
        resp = client.get("/api/config/announcements")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert isinstance(data["messages"], list)


class TestConfigVersion:
    """GET /api/config/version 返回配置版本号"""

    def test_config_version_ok(self, client):
        resp = client.get("/api/config/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data


# ============================================================
# 理念传播路由（philosophy）
# ============================================================

class TestPhilosophyRandom:
    """GET /api/philosophy/random 返回随机理念"""

    def test_random_ok(self, client):
        resp = client.get("/api/philosophy/random")
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert isinstance(data["text"], str)


# ============================================================
# 静默检测配置
# ============================================================

class TestSilenceDetectionConfig:
    """静默检测配置加载"""

    def test_get_silence_detection_config_returns_defaults(self):
        """get_silence_detection_config() 应返回完整默认配置"""
        from app.store import get_silence_detection_config
        config = get_silence_detection_config()
        assert config["enabled"] is True
        assert "presence" in config
        assert "audio" in config
        assert "action" in config
        # 存在性评分参数
        assert config["presence"]["score_max"] == 100
        assert config["presence"]["heartbeat_timeout_sec"] == 90
        assert config["presence"]["threshold_warning"] == 20
        # 音频层参数
        assert config["audio"]["asr_no_sentence_timeout_sec"] == 300
        # 动作参数
        assert config["action"]["gentle_countdown_sec"] == 120
        assert config["action"]["urgent_countdown_sec"] == 60
        assert config["action"]["max_warnings_per_session"] == 2

    def test_silence_detection_state_dicts_exist(self):
        """静默检测状态字典应已初始化"""
        from app.store import (
            realtime_last_heartbeat, realtime_last_sentence,
            realtime_presence_scores, realtime_silence_warnings,
            realtime_silence_monitors,
        )
        assert isinstance(realtime_last_heartbeat, dict)
        assert isinstance(realtime_last_sentence, dict)
        assert isinstance(realtime_presence_scores, dict)
        assert isinstance(realtime_silence_warnings, dict)
        assert isinstance(realtime_silence_monitors, dict)
