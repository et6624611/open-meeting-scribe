"""EP1-BE 段五：members 读端点 + 团队共享词表读写（FE 读实码抓口整改批）。

背景：段二播报"teams 全族"与实码存在两族差口（第五枚组合面盲区教训，播报=实码可调用面）。
契约基线：v1.0 §4/§8（team_assets 新表归属；ctx_assets 团队行留统一资产域演进，本批按 §4 逐字落）。
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


def member(client, account, display=None):
    r = client.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-001"})
    uc = client.post("/api/v1/admin/users", json={"display_name": display or account, "account": account},
                    cookies=r.cookies)
    act = client.post("/api/v1/auth/activate", json={"invite_code": uc.json()["invite_code"], "password": f"Passw0rd-{account}"})
    return {"cookies": act.cookies, "user_id": act.json()["user_id"]}


def team_of(c, owner, name="词表队"):
    return c.post("/api/v1/teams", json={"name": name}, cookies=owner["cookies"]).json()["team_id"]


# ---------------- GET /teams/{id}/members ----------------


def test_members_endpoint(env):
    c, _ = env
    boss, ed, view = member(c, "m_boss", "组长"), member(c, "m_ed", "编辑员"), member(c, "m_view", "观察员")
    tid = team_of(c, boss)
    r = c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [ed["user_id"], view["user_id"]], "role": "editor"},
               cookies=boss["cookies"])
    assert r.status_code == 201 and len(r.json()["added"]) == 2
    m = c.get(f"/api/v1/teams/{tid}/members", cookies=ed["cookies"])
    assert m.status_code == 200
    by_id = {x["user_id"]: x for x in m.json()["members"]}
    assert by_id[boss["user_id"]]["display_name"] == "组长" and by_id[boss["user_id"]]["role"] == "admin"
    assert "joined_at" in by_id[ed["user_id"]]
    # FE"公开人"显示名数据面成立：成员表带 display_name
    out = member(c, "m_out", "局外人")
    assert c.get(f"/api/v1/teams/{tid}/members", cookies=out["cookies"]).status_code == 404
    # 停用撤权后不在 effective 名单（§2 离职撤权，行保留走审计面）
    adm = c.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-001"}).cookies
    c.put(f"/api/v1/admin/users/{view['user_id']}/status", json={"status": "disabled"}, cookies=adm)
    ids2 = {x["user_id"] for x in c.get(f"/api/v1/teams/{tid}/members", cookies=boss["cookies"]).json()["members"]}
    assert view["user_id"] not in ids2


# ---------------- 团队词表读写（§4/§8） ----------------


def test_team_assets_roundtrip(env):
    c, store = env
    boss, ed = member(c, "a_boss", "甲组长"), member(c, "a_ed", "甲编辑")
    tid = team_of(c, boss)
    c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [ed["user_id"]], "role": "editor"}, cookies=boss["cookies"])

    # 空态：rev0 payload null（FE 消费形状与个人面 get_asset 同构）
    empty = c.get("/api/v1/context/teams/{}/assets/hotwords".replace("{}", tid), cookies=boss["cookies"])
    assert empty.status_code == 200
    body = empty.json()
    assert body["current_rev"] == 0 and body["payload"] is None and body["visibility"] == "team"

    # editor 写入 → rev1；同内容重放 idempotent_replay；过期 base → 409
    w = c.put(f"/api/v1/context/teams/{tid}/assets/hotwords",
              json={"payload": {"words": ["团队词A", "团队词B"]}},
              headers={"Idempotency-Key": "mut-ta1", "If-Match-Rev": "0"}, cookies=ed["cookies"])
    assert w.status_code == 200 and w.json()["current_rev"] == 1
    replay = c.put(f"/api/v1/context/teams/{tid}/assets/hotwords",
                   json={"payload": {"words": ["团队词A", "团队词B"]}},
                   headers={"Idempotency-Key": "mut-ta2", "If-Match-Rev": "0"}, cookies=ed["cookies"])
    assert replay.json()["idempotent_replay"] is True
    stale = c.put(f"/api/v1/context/teams/{tid}/assets/hotwords",
                  json={"payload": {"words": ["冲突"]}},
                  headers={"Idempotency-Key": "mut-ta3", "If-Match-Rev": "0"}, cookies=ed["cookies"])
    assert stale.status_code == 409 and stale.json()["error"]["current_rev"] == 1

    # viewer 写 403（editor+ 才权）；未知 kind 404；float 载荷 422（复用个人面递归校验同尺）
    view = member(c, "a_view", "甲观察")
    c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [view["user_id"]], "role": "viewer"}, cookies=boss["cookies"])
    assert c.put(f"/api/v1/context/teams/{tid}/assets/hotwords", json={"payload": {"words": ["x"]}},
                 headers={"Idempotency-Key": "mut-ta4", "If-Match-Rev": "1"},
                 cookies=view["cookies"]).status_code == 403
    assert c.get(f"/api/v1/context/teams/{tid}/assets/decision-statuses", cookies=boss["cookies"]).status_code == 404
    assert c.put(f"/api/v1/context/teams/{tid}/assets/hotwords", json={"payload": {"w": 1.5}},
                 headers={"Idempotency-Key": "mut-ta5", "If-Match-Rev": "1"},
                 cookies=ed["cookies"]).status_code == 422

    # 读形状回显 + 留痕：词表编辑入变更记录（edit + target_ref=asset:hotwords）
    got = c.get(f"/api/v1/context/teams/{tid}/assets/hotwords", cookies=view["cookies"]).json()
    assert got["payload"] == {"words": ["团队词A", "团队词B"]} and got["current_rev"] == 1
    feed = c.get(f"/api/v1/teams/{tid}/audit", cookies=boss["cookies"]).json()["items"]
    asset_row = next(i for i in feed if i.get("target_ref") == "asset:hotwords")
    assert asset_row["action"] == "edit"

    # 多团队不串扰（QA TB3 口径端点面延伸）：同人第二团队词表独立
    tid2 = team_of(c, boss, "第二队")
    assert c.get(f"/api/v1/context/teams/{tid2}/assets/hotwords", cookies=boss["cookies"]).json()["payload"] is None
    c.put(f"/api/v1/context/teams/{tid2}/assets/hotwords", json={"payload": {"words": ["乙队词"]}},
          headers={"Idempotency-Key": "mut-ta6", "If-Match-Rev": "0"}, cookies=boss["cookies"])
    assert c.get(f"/api/v1/context/teams/{tid}/assets/hotwords", cookies=boss["cookies"]).json()["payload"] == {"words": ["团队词A", "团队词B"]}

    # 归档团队：词表写=409 team_archived（新写入拒绝），读照常（裁决④只读面）
    c.put(f"/api/v1/teams/{tid2}/archive", cookies=boss["cookies"])
    assert c.put(f"/api/v1/context/teams/{tid2}/assets/hotwords", json={"payload": {"words": ["归档后写"]}},
                 headers={"Idempotency-Key": "mut-ta7", "If-Match-Rev": "1"},
                 cookies=boss["cookies"]).status_code == 409
    assert c.get(f"/api/v1/context/teams/{tid2}/assets/hotwords", cookies=boss["cookies"]).status_code == 200


def test_team_assets_speaker_aliases_key(env):
    c, _ = env
    boss = member(c, "sa_boss", "发言人组长")
    tid = team_of(c, boss, "声队")
    w = c.put(f"/api/v1/context/teams/{tid}/assets/speaker-aliases",
              json={"payload": {"aliases": {"spk_1": "王工"}}},
              headers={"Idempotency-Key": "mut-sa1", "If-Match-Rev": "0"}, cookies=boss["cookies"])
    assert w.status_code == 200
    got = c.get(f"/api/v1/context/teams/{tid}/assets/speaker-aliases", cookies=boss["cookies"]).json()
    assert got["payload"] == {"aliases": {"spk_1": "王工"}}


# ---------------- K4 定版：published_at=首次公开时刻，编辑不顶序（排序锚透出） ----------------


def test_published_at_is_first_publish_moment(env):
    c, store = env
    alice, bob = member(c, "k4_a", "公开人"), member(c, "k4_b", "编辑人")
    tid = team_of(c, alice, "K4队")
    c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [bob["user_id"]], "role": "editor"},
           cookies=alice["cookies"])
    payload = {"meta": {"title": "K4 会"}, "summary": "s", "decisions": [{"id": "d1", "text": "甲"}], "notes": "n"}
    c.put("/api/v1/context/tasks/tsk_k4/snapshot", json=payload,
          headers={"Idempotency-Key": "mut-k4s", "If-Match-Rev": "0"}, cookies=alice["cookies"])
    copy = c.post("/api/v1/context/tasks/tsk_k4/publish", json={"team_id": tid},
                  cookies=alice["cookies"]).json()
    pa0 = copy["published_at"]
    assert pa0, "published_at 必须透出（K4）"
    src_copies = c.get("/api/v1/context/tasks/tsk_k4", cookies=alice["cookies"]).json()["published_copies"]
    assert next(p for p in src_copies if p["copy_task_id"] == copy["task_id"])["published_at"] == pa0
    # bob 编辑两版——rev 顶进、updated_at 变化，但 published_at 不动（编辑不顶序）
    c.put(f"/api/v1/context/teams/{tid}/tasks/{copy['task_id']}/snapshot", json={**payload, "summary": "改一"},
          headers={"Idempotency-Key": "mut-k4e1", "If-Match-Rev": "1"}, cookies=bob["cookies"])
    c.put(f"/api/v1/context/teams/{tid}/tasks/{copy['task_id']}/snapshot", json={**payload, "summary": "改二"},
          headers={"Idempotency-Key": "mut-k4e2", "If-Match-Rev": "2"}, cookies=bob["cookies"])
    again = c.get(f"/api/v1/context/teams/{tid}/tasks/{copy['task_id']}", cookies=alice["cookies"]).json()
    assert again["server_rev"] == 3 and again["published_at"] == pa0
    lst = c.get(f"/api/v1/context/teams/{tid}/tasks", cookies=alice["cookies"]).json()["tasks"]
    assert lst[0]["published_at"] == pa0
