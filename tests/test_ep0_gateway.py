"""EP0 网关与企业形态鉴权面回归（2026-10-30 DevOps 现场发现的两缺口）。

缺口②：REQUIRE_AUTH=true 强制形态下 /api/v1 登录面被个人版网关 401 自锁；
缺口③（连带暴露）：REQUIRE_AUTH=false 误配下，企业实例上挂载的个人版 /api/* 业务路由裸奔无鉴权。
修复口径：企业形态网关以 oms_e_session 为唯一有效凭据，/api/v1 由端点层自守卫（契约 §1.2）。
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.db.dao import NotFoundError
from app.routers import enterprise_api


def _boot_env(monkeypatch, tmp_path, require_auth: str):
    root = tmp_path / "GATEWAY_ENT"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    monkeypatch.setenv("OMS_EDITION", "enterprise")
    monkeypatch.setenv("REQUIRE_AUTH", require_auth)
    enterprise_api.reset_store_cache()
    import app.server as srv

    srv = importlib.reload(srv)
    c = TestClient(srv.app)
    store = enterprise_api.get_store()
    res = store.bootstrap_admin(display_name="管理员", login_account="13373013103", phone="13373013103")
    uid, code = res["user_id"], res["invite_code"]
    store.activate_invite(invite_code=code, password="Admin-Pw-0001")
    return c, store, uid


def test_gateway_require_auth_true_login_plane_open(tmp_path, monkeypatch):
    """缺口②：REQUIRE_AUTH=true 真起——登录/免登录预取可达，业务面仍受守卫。"""
    c, store, uid = _boot_env(monkeypatch, tmp_path, "true")
    assert c.get("/api/v1/instance/info").status_code == 200
    r = c.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-0001"})
    assert r.status_code == 200 and r.json()["role"] == "admin"  # 修复前=401 Authentication required
    c.cookies.clear()
    assert c.get("/api/v1/context/tasks").status_code == 401
    assert c.get("/api/v1/context/tasks", cookies=r.cookies).status_code == 200
    enterprise_api.reset_store_cache()


def test_gateway_require_auth_false_enterprise_still_gated(tmp_path, monkeypatch):
    """缺口③：误配 REQUIRE_AUTH=false 时企业形态仍强制——个人版业务路由不再裸奔。"""
    c, store, uid = _boot_env(monkeypatch, tmp_path, "false")
    assert c.get("/api/v1/instance/info").status_code == 200
    blocked = c.get("/api/tasks")  # 个人版业务路由
    assert blocked.status_code == 401 and blocked.json()["error"]["code"] == "unauthenticated"
    login = c.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-0001"})
    ok = c.get("/api/tasks", cookies=login.cookies)
    assert ok.status_code != 401  # 有效企业会话可过网关（业务结果本身走个人 store，非本用例断言面）
    enterprise_api.reset_store_cache()


def test_bootstrap_http_rejects_non_loopback(tmp_path, monkeypatch):
    """HTTP bootstrap 通道：非本机回环来源一律 403（外部经反代建号不可能）。"""
    root = tmp_path / "NB"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    monkeypatch.setenv("OMS_EDITION", "enterprise")
    enterprise_api.reset_store_cache()
    from fastapi import FastAPI

    app = FastAPI()
    enterprise_api.register_enterprise_routes(app)
    c = TestClient(app)  # TestClient 源 host=testclient（非回环）
    assert c.get("/api/v1/instance/info").json()["needs_bootstrap"] is True
    r = c.post("/api/v1/auth/bootstrap", json={"account": "13373013103", "display_name": "A"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "bootstrap_loopback_only"
    assert c.get("/api/v1/instance/info").json()["needs_bootstrap"] is True  # 零写入
    enterprise_api.reset_store_cache()


def test_bootstrap_channel_zero_admin_only(tmp_path, monkeypatch):
    root = tmp_path / "BOOT"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    from app.db.config import DataRoot
    from app.db.dao import EnterpriseStore
    from app.db.database import migrate

    store = EnterpriseStore(DataRoot(root=root))
    migrate(store.conn)
    first = store.bootstrap_admin(display_name="张三", login_account="13373013103")
    assert first["reentered"] is False
    # W-D005-B 重入语义：激活前 bootstrap 可重入（首装中途关浏览器不再死循环）
    second = store.bootstrap_admin(display_name="李四", login_account="13373013103")
    assert second["reentered"] is True
    assert second["user_id"] == first["user_id"]  # 同账号不重建
    assert second["display_name"] == "张三"  # 显示名保留用户第一次输入（裁决原文）
    # 旧码作废：撤未用旧邀请码
    with pytest.raises(NotFoundError):
        store.activate_invite(invite_code=first["invite_code"], password="Old-Code-Pw-1")
    # 新码激活 + verify
    assert store.activate_invite(invite_code=second["invite_code"], password="First-Admin-Pw") == first["user_id"]
    assert store.verify_login(login_account="13373013103", password="First-Admin-Pw") == first["user_id"]
    # 激活完成后通道永久关闭（X05-3 断言语义不变）
    with pytest.raises(RuntimeError):
        store.bootstrap_admin(display_name="王五", login_account="13900000000")
    # bootstrap_done 状态位=激活完成时置位（非第一步）
    assert store.get_instance_config("bootstrap_done", default=None) is True
    store.close()


def test_bootstrap_done_flag_not_set_at_step_one(tmp_path, monkeypatch):
    """第一步建号后（未激活）bootstrap_done 必须为假——needs_bootstrap 与通道状态自洽。"""
    root = tmp_path / "BD"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    from app.db.config import DataRoot
    from app.db.dao import EnterpriseStore
    from app.db.database import migrate

    store = EnterpriseStore(DataRoot(root=root))
    migrate(store.conn)
    store.bootstrap_admin(display_name="A", login_account="13373013103")
    assert store.get_instance_config("bootstrap_done", default=None) is None
    store.close()
