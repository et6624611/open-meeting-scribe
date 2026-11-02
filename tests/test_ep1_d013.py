"""D013 修复批：私有空间读/写面恒排除 team 副本行（空间语义承诺回归钉）.

缺陷原态：团队副本（owner=发布人）混入个人列表/详情/删除/快照 PUT 面，可二次发布。
修复口径（PM 拍板 cmsg_01m6d9hhdw00q9045ktzahmkfq + QA 建议面）：
个人面四个入口（列表/详情/快照 PUT/删除）一律只认 scope='personal' 行，
team 行落统一 404（"非本空间"语义，防枚举同尺）；published_copies 内嵌读面不受影响。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.config import DataRoot
from app.db.dao import EnterpriseStore
from app.db.database import migrate
from app.db.security import hash_password
from app.routers import enterprise_api

SRC = "tsk_d013_src"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = tmp_path / "ENTERPRISE_DATA"
    monkeypatch.setenv("OMS_DATA_ROOT", str(root))
    enterprise_api.reset_store_cache()
    store = EnterpriseStore(DataRoot(root=root))
    migrate(store.conn)
    now = "2026-10-29T00:00:00+00:00"
    with store.conn:
        store.conn.execute(
            "INSERT INTO users(user_id, login_account, display_name, password_hash, role, status, created_at, updated_at)"
            " VALUES ('usr_admin','13373013103','管理员',?,'admin','active',?,?)",
            (hash_password("Admin-Pw-001"), now, now),
        )
    app = FastAPI()
    enterprise_api.register_enterprise_routes(app)
    c = TestClient(app)
    yield c, store
    enterprise_api.reset_store_cache()
    store.close()


def member(client, account):
    r = client.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-001"})
    uc = client.post("/api/v1/admin/users", json={"display_name": account, "account": account}, cookies=r.cookies)
    act = client.post("/api/v1/auth/activate", json={"invite_code": uc.json()["invite_code"], "password": f"Passw0rd-{account}"})
    return {"cookies": act.cookies, "user_id": act.json()["user_id"]}


def test_private_plane_never_shows_team_copies(env):
    c, _ = env
    alice = member(c, "d013_a")
    payload = {
        "meta": {"title": "D013 演练会"},
        "formal": "逐字稿", "summary": "纪要", "decisions": [{"id": "x1", "text": "甲"}], "notes": "n",
    }
    assert c.put(f"/api/v1/context/tasks/{SRC}/snapshot", json=payload,
                 headers={"Idempotency-Key": "mut-d0", "If-Match-Rev": "0"},
                 cookies=alice["cookies"]).status_code == 201
    tid = c.post("/api/v1/teams", json={"name": "甲团队"}, cookies=alice["cookies"]).json()["team_id"]
    copy = c.post(f"/api/v1/context/tasks/{SRC}/publish", json={"team_id": tid},
                  cookies=alice["cookies"]).json()
    copy_id = copy["task_id"]

    # ① 私有列表：仅原件，无副本卡（缺陷原态=4 卡混排）
    ids = [t["task_id"] for t in c.get("/api/v1/context/tasks", cookies=alice["cookies"]).json()["tasks"]]
    assert ids == [SRC], f"D013 复现：私有列表混入 {set(ids) - {SRC}}"
    # ② 个人详情端点对副本=404（非本空间；与不存在同码防枚举）
    assert c.get(f"/api/v1/context/tasks/{copy_id}", cookies=alice["cookies"]).status_code == 404
    # ③ 个人快照 PUT 打副本=404（二次发布链从个人面封死，团队编辑必须走团队端点）
    w = c.put(f"/api/v1/context/tasks/{copy_id}/snapshot", json={"summary": "绕道"},
              headers={"Idempotency-Key": "mut-d1", "If-Match-Rev": "1"}, cookies=alice["cookies"])
    assert w.status_code == 404
    # ④ 个人删除端点打副本=404（撤回唯一入口=团队面 DELETE）
    assert c.delete(f"/api/v1/context/tasks/{copy_id}", cookies=alice["cookies"]).status_code == 404
    # ⑤ published_copies 内嵌角标数据面不受影响（拍板：读面不动）
    src = c.get(f"/api/v1/context/tasks/{SRC}", cookies=alice["cookies"]).json()
    assert [p["team_id"] for p in src["published_copies"]] == [tid]
    # ⑥ 团队面读写不回归：成员仍可从团队端点读副本并编辑
    tc = c.get(f"/api/v1/context/teams/{tid}/tasks/{copy_id}", cookies=alice["cookies"])
    assert tc.status_code == 200 and tc.json()["task_id"] == copy_id
    tw = c.put(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/snapshot", json={"summary": "团队面编辑"},
               headers={"Idempotency-Key": "mut-d2", "If-Match-Rev": "1"}, cookies=alice["cookies"])
    assert tw.status_code == 200 and tw.json()["server_rev"] == 2
    # ⑦ 助手同步面同守：同一副本走个人 PUT 仍 404（P0 sync 队列污染风险封堵）
    # ⑧ 原件删除仍正常（scope 过滤不误伤 personal 行）
    assert c.delete(f"/api/v1/context/tasks/{SRC}", cookies=alice["cookies"]).status_code == 200
