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
        from core.errors import classify_error, is_transient_error
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

    def test_proxy_4xx_business_failure_surfaces_message(self, monkeypatch):
        """回归：代理返回 400（验证码错误/已过期）应透传真实原因，
        而非被 check_verify_code 吞成"验证服务异常"。
        """
        import io
        import json
        import urllib.error
        from core import sms

        monkeypatch.setattr(sms, "SMS_PROXY_URL", "https://sms.test")
        monkeypatch.setattr(sms, "SMS_PROXY_TOKEN", "testtoken")

        body = json.dumps({"success": False, "message": "验证码错误或已过期"}).encode()

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                url="https://sms.test/sms/verify", code=400, msg="Bad Request",
                hdrs=None, fp=io.BytesIO(body),
            )

        monkeypatch.setattr(sms.urllib.request, "urlopen", fake_urlopen)
        passed, reason = sms.check_verify_code("13312343103", "000000")
        assert passed is False
        assert reason == "验证码错误或已过期"


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
        assert "variants" in data
        assert isinstance(data["variants"], dict)

    def test_variants_contain_zh_and_en(self, client):
        resp = client.get("/api/philosophy/random")
        data = resp.json()
        variants = data["variants"]
        assert "zh" in variants
        assert "en" in variants

    def test_lang_param_selects_en(self, client):
        resp = client.get("/api/philosophy/random?lang=en")
        data = resp.json()
        # text 应与 en 变体一致
        assert data["text"] == data["variants"].get("en", data["variants"].get("zh", ""))


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
            realtime_last_heartbeat,
            realtime_last_sentence,
            realtime_presence_scores,
            realtime_silence_monitors,
            realtime_silence_warnings,
        )
        assert isinstance(realtime_last_heartbeat, dict)
        assert isinstance(realtime_last_sentence, dict)
        assert isinstance(realtime_presence_scores, dict)
        assert isinstance(realtime_silence_warnings, dict)
        assert isinstance(realtime_silence_monitors, dict)


# ============================================================
# CORS 预检回归测试 / CORS preflight regression test
# ============================================================


class TestCorsPreflightWithAuth:
    """CORS 预检请求在 REQUIRE_AUTH=true 时不被认证中间件拦截

    回归背景：CORSMiddleware 注册顺序使其成为最内层中间件，enforce_auth_middleware
    在最外层。REQUIRE_AUTH=true 时浏览器 OPTIONS 预检请求先经过认证中间件，
    因无 JWT 被返回 401（且无 ACAO 头），跨域部署完全不可用。
    """

    def test_options_preflight_passes_auth(self, client, monkeypatch):
        """REQUIRE_AUTH=true 时，带 Origin 的 OPTIONS /api/tasks 应返回 200/204 且含 ACAO 头"""
        import app.server as server_mod

        monkeypatch.setattr(server_mod, "_REQUIRE_AUTH", True)

        resp = client.options(
            "/api/tasks",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # 预检请求不应被认证拦截 / Preflight must not be blocked by auth
        assert resp.status_code in (200, 204), (
            f"OPTIONS preflight returned {resp.status_code}, expected 200 or 204"
        )
        # 响应必须包含 CORS 头 / Response must include CORS headers
        assert "access-control-allow-origin" in resp.headers, (
            "OPTIONS preflight response missing Access-Control-Allow-Origin header"
        )

    def test_non_preflight_still_requires_auth(self, client, monkeypatch):
        """REQUIRE_AUTH=true 时，非 OPTIONS 的 GET 请求无 JWT 仍返回 401"""
        import app.server as server_mod

        monkeypatch.setattr(server_mod, "_REQUIRE_AUTH", True)

        resp = client.get("/api/tasks")
        assert resp.status_code == 401


# ============================================================
# 云端用户服务（cloud_client + cloud_api）
# ============================================================


class TestCloudClientDisabled:
    """云端客户端未配置时行为"""

    def test_cloud_disabledled_by_default(self, monkeypatch):
        """未配置环境变量时 is_cloud_enabled() 返回 False"""
        from core import cloud_client

        monkeypatch.setattr(cloud_client, "CLOUD_API_URL", "")
        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "")
        assert cloud_client.is_cloud_enabled() is False

    def test_cloud_disabled_with_url_only(self, monkeypatch):
        """仅配置 URL 无 token 时仍返回 False"""
        from core import cloud_client

        monkeypatch.setattr(cloud_client, "CLOUD_API_URL", "http://example.com")
        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "")
        assert cloud_client.is_cloud_enabled() is False

    def test_sync_returns_none_when_disabled(self, monkeypatch):
        """云端未启用时 sync_user_to_cloud 返回 None"""
        from core import cloud_client

        monkeypatch.setattr(cloud_client, "CLOUD_API_URL", "")
        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "")
        assert cloud_client.sync_user_to_cloud("user-123", "13312345678", "test") is None

    def test_report_usage_returns_none_when_disabled(self, monkeypatch):
        """云端未启用时 report_usage_to_cloud 返回 None"""
        from core import cloud_client

        monkeypatch.setattr(cloud_client, "CLOUD_API_URL", "")
        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "")
        assert cloud_client.report_usage_to_cloud("user-123", "asr_batch", 300) is None

    def test_check_quota_returns_none_when_disabled(self, monkeypatch):
        """云端未启用时 check_quota_from_cloud 返回 None"""
        from core import cloud_client

        monkeypatch.setattr(cloud_client, "CLOUD_API_URL", "")
        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "")
        assert cloud_client.check_quota_from_cloud("user-123") is None


class TestCloudClientHmacSign:
    """云端客户端 HMAC 签名生成"""

    def test_sign_is_hex_string(self, monkeypatch):
        """签名结果应为十六进制字符串"""
        from core import cloud_client

        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "test-secret-token")
        sign = cloud_client._make_sign("1700000000")
        assert isinstance(sign, str)
        assert len(sign) == 64  # SHA-256 = 32 bytes = 64 hex chars

    def test_sign_deterministic(self, monkeypatch):
        """相同输入产生相同签名"""
        from core import cloud_client

        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "test-secret-token")
        sign1 = cloud_client._make_sign("1700000000")
        sign2 = cloud_client._make_sign("1700000000")
        assert sign1 == sign2

    def test_sign_differs_for_different_timestamps(self, monkeypatch):
        """不同时间戳产生不同签名"""
        from core import cloud_client

        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "test-secret-token")
        sign1 = cloud_client._make_sign("1700000000")
        sign2 = cloud_client._make_sign("1700000001")
        assert sign1 != sign2


class TestCloudApiAuth:
    """云端 API 端点认证"""

    def test_sync_requires_auth(self, client, monkeypatch):
        """用户同步端点需要签名认证"""
        from app.routers import cloud_api as cloud_api_mod

        monkeypatch.setattr(cloud_api_mod, "CLOUD_API_TOKEN", "test-token")
        resp = client.post("/api/cloud/users/sync", json={
            "user_id": "test-id",
            "phone": "13312345678",
        })
        assert resp.status_code == 401

    def test_report_requires_auth(self, client, monkeypatch):
        """用量上报端点需要签名认证"""
        from app.routers import cloud_api as cloud_api_mod

        monkeypatch.setattr(cloud_api_mod, "CLOUD_API_TOKEN", "test-token")
        resp = client.post("/api/cloud/usage/report", json={
            "user_id": "test-id",
            "service": "asr_batch",
            "duration_seconds": 300,
        })
        assert resp.status_code == 401

    def test_quota_requires_auth(self, client, monkeypatch):
        """配额查询端点需要签名认证"""
        from app.routers import cloud_api as cloud_api_mod

        monkeypatch.setattr(cloud_api_mod, "CLOUD_API_TOKEN", "test-token")
        resp = client.get("/api/cloud/usage/quota?user_id=test-id")
        assert resp.status_code == 401


class TestRecordUsageLocalFallback:
    """云端不可达时 record_usage 本地降级"""

    def test_record_usage_writes_local_when_cloud_disabled(self, monkeypatch, tmp_path):
        """云端未启用时 record_usage 正常写入本地 JSONL"""
        from core import cloud_client, metering

        monkeypatch.setattr(cloud_client, "CLOUD_API_URL", "")
        monkeypatch.setattr(cloud_client, "CLOUD_API_TOKEN", "")
        monkeypatch.setattr(metering, "USAGE_DIR", tmp_path)

        # 确保用户存在
        test_user = {
            "id": "test-user-id",
            "provider": "sms",
            "provider_id": "13312345678",
            "name": "133****5678",
            "subscription": {"tier": "free"},
        }
        monkeypatch.setattr(metering, "_get_user_quota", lambda uid: 300)

        result = metering.record_usage(
            user_id="test-user-id",
            service="asr_batch",
            duration_seconds=300.0,
        )

        assert result["minutes"] == 5.0
        assert result["quota"] == 300
        assert "remaining" in result
        assert "cumulative_monthly" in result
