"""EP1-BE 第三段：发布/撤回/副本编辑/删除→恢复闭环 集成测试。

契约基线：v1.0 §3/§8.2/§8.3/§8.4；冻结必含项①（409 latest）与裁决③闭环（QA 四步 E2E）。
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

SRC_TASK = "tsk_src_publish"
D1 = {"id": "dec_1", "text": "决策一", "status": "open"}
D2 = {"id": "dec_2", "text": "决策二", "status": "done"}


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


def create_member(client, account: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"account": "13373013103", "password": "Admin-Pw-001"})
    c = client.post("/api/v1/admin/users", json={"display_name": account, "account": account}, cookies=r.cookies)
    act = client.post("/api/v1/auth/activate", json={"invite_code": c.json()["invite_code"], "password": f"Passw0rd-{account}"})
    return {"cookies": act.cookies, "user_id": act.json()["user_id"]}


def make_source_task(client, cookies) -> None:
    payload = {
        "meta": {"title": "发布演练会", "meeting_time": "2026-11-02T09:00:00+00:00", "participants_text": "甲乙"},
        "formal": "逐字稿：甲说……乙说……（永不进团队）",
        "summary": "纪要正文",
        "decisions": [dict(D1), dict(D2)],
        "notes": "笔记",
        "insights_html": "<div>洞察板</div>",
    }
    r = client.put(
        f"/api/v1/context/tasks/{SRC_TASK}/snapshot", json=payload,
        headers={"Idempotency-Key": "mut-src1", "If-Match-Rev": "0"}, cookies=cookies,
    )
    assert r.status_code == 201, r.text


def setup_team(client, alice, bob):
    tid = client.post("/api/v1/teams", json={"name": "空间组"}, cookies=alice["cookies"]).json()["team_id"]
    r = client.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [bob["user_id"]], "role": "editor"},
                    cookies=alice["cookies"])
    assert r.status_code == 201
    return tid


def publish(client, cookies, team_id, mode="task", decision_id=None):
    body = {"team_id": team_id, "mode": mode}
    if decision_id:
        body["decision_id"] = decision_id
    return client.post(f"/api/v1/context/tasks/{SRC_TASK}/publish", json=body, cookies=cookies)


# ---------------- 发布 happy path + 裁决⑤结构性排除 ----------------


def test_publish_carries_whitelist_and_excludes_formal(env):
    c, _ = env
    alice, bob = create_member(c, "puba"), create_member(c, "pubb")
    make_source_task(c, alice["cookies"])
    tid = setup_team(c, alice, bob)
    r = publish(c, alice["cookies"], tid)
    assert r.status_code == 201, r.text
    copy = r.json()
    assert copy["visibility"] == "team" and copy["source_task_id"] == SRC_TASK
    assert "formal" not in copy, "逐字稿泄漏进团队副本"
    assert copy["summary"] == "纪要正文" and copy["insights_html"] == "<div>洞察板</div>"  # 裁决⑤洞察板随入
    assert {d["id"] for d in copy["decisions"]} == {"dec_1", "dec_2"}
    lst = c.get(f"/api/v1/context/teams/{tid}/tasks", cookies=bob["cookies"]).json()["tasks"]
    assert [t["task_id"] for t in lst] == [copy["task_id"]]
    # 团队副本 blob 物理面也不含 formal（存储层不可达，非 UI 隐藏）
    got = c.get(f"/api/v1/context/teams/{tid}/tasks/{copy['task_id']}", cookies=bob["cookies"]).json()
    assert "formal" not in got and "audio" not in str(got)
    # 副本 PUT 携带 formal/音频 → 422 白名单拒收（422 兜底）
    bad = c.put(f"/api/v1/context/teams/{tid}/tasks/{copy['task_id']}/snapshot",
                json={"summary": "s", "formal": "偷渡逐字稿"},
                headers={"Idempotency-Key": "mut-bad1", "If-Match-Rev": "1"}, cookies=bob["cookies"])
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "payload_not_allowed"
    bad2 = c.put(f"/api/v1/context/teams/{tid}/tasks/{copy['task_id']}/snapshot",
                 json={"summary": "s", "audio_base64": "..."},
                 headers={"Idempotency-Key": "mut-bad2", "If-Match-Rev": "1"}, cookies=bob["cookies"])
    assert bad2.status_code == 422


# ---------------- 副本编辑：editor 可写、actor 记录、viewer 403、必含项① 409 latest ----------------


def test_team_snapshot_edit_and_409_latest(env):
    c, store = env
    alice, bob = create_member(c, "edi_a"), create_member(c, "edi_b")
    make_source_task(c, alice["cookies"])
    tid = setup_team(c, alice, bob)
    carol = create_member(c, "edi_c")
    c.post(f"/api/v1/teams/{tid}/members", json={"user_ids": [carol["user_id"]], "role": "viewer"},
           cookies=alice["cookies"])
    copy_id = publish(c, alice["cookies"], tid).json()["task_id"]
    # viewer 写 → 403 明示
    v = c.put(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/snapshot", json={"summary": "v"},
              headers={"Idempotency-Key": "mut-v1", "If-Match-Rev": "1"}, cookies=carol["cookies"])
    assert v.status_code == 403 and v.json()["error"]["code"] == "team_role_required"
    # bob（editor，非发布人）编辑成功——副本时间线独立于原件
    b = c.put(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/snapshot", json={"summary": "Bob 改过的纪要"},
              headers={"Idempotency-Key": "mut-b1", "If-Match-Rev": "1"}, cookies=bob["cookies"])
    assert b.status_code == 200 and b.json()["server_rev"] == 2
    src_now = c.get(f"/api/v1/context/tasks/{SRC_TASK}", cookies=alice["cookies"]).json()
    assert src_now["summary"] == "纪要正文" and src_now["server_rev"] == 1  # 原件不受影响（§3.2 不双向同步）
    # 写作者归属：rev2 的 actor=bob（§6B owner/actor 拆分）
    row = store.conn.execute(
        "SELECT owner_user_id, actor_user_id FROM ctx_revisions WHERE task_id=? AND rev=2", (copy_id,)
    ).fetchone()
    assert row["actor_user_id"] == bob["user_id"]
    assert row["owner_user_id"] == alice["user_id"], "D011：owner 必须保持行归属人=发布人，不得写为本次写作者"
    # bob 用过期 base_rev 再写 → 409 含 current_rev + latest 全文（必含项①，QA TA2-7）
    conf = c.put(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/snapshot", json={"summary": "串位"},
                 headers={"Idempotency-Key": "mut-b2", "If-Match-Rev": "1"}, cookies=bob["cookies"])
    assert conf.status_code == 409
    err = conf.json()["error"]
    assert err["code"] == "rev_conflict" and err["current_rev"] == 2
    assert err["latest"]["summary"] == "Bob 改过的纪要" and "formal" not in err["latest"]
    # 个人面 409 保持 P0 形态（无 latest，单向兼容）
    pconf = c.put(f"/api/v1/context/tasks/{SRC_TASK}/snapshot", json={"summary": "x"},
                  headers={"Idempotency-Key": "mut-p2", "If-Match-Rev": "9"}, cookies=alice["cookies"])
    assert pconf.status_code == 409 and "latest" not in pconf.json()["error"]
    # 历史版本可读（diff/恢复数据面）
    rev1 = c.get(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/revisions/1", cookies=carol["cookies"])
    assert rev1.status_code == 200 and rev1.json()["payload"]["summary"] == "纪要正文"


# ---------------- 裁决①多团队独立副本 + K2 重复发布形态 ----------------


def test_multi_team_and_republish(env):
    c, _ = env
    alice = create_member(c, "multi_a")
    make_source_task(c, alice["cookies"])
    t1 = c.post("/api/v1/teams", json={"name": "T1"}, cookies=alice["cookies"]).json()["team_id"]
    t2 = c.post("/api/v1/teams", json={"name": "T2"}, cookies=alice["cookies"]).json()["team_id"]
    c1 = publish(c, alice["cookies"], t1)
    c2 = publish(c, alice["cookies"], t2)
    assert c1.status_code == 201 and c2.status_code == 201
    assert c1.json()["task_id"] != c2.json()["task_id"]  # 每团队独立副本行
    # K2：同团队重复发布 = 刷新既有副本（republished，200，rev+1），不产生第二份
    src_rev0 = c.get(f"/api/v1/context/tasks/{SRC_TASK}", cookies=alice["cookies"]).json()["server_rev"]
    put = c.put(f"/api/v1/context/tasks/{SRC_TASK}/snapshot", json={
        "meta": {"title": "发布演练会"}, "summary": "纪要 v2", "decisions": [dict(D1), dict(D2),
        {"id": "dec_3", "text": "决策三", "status": "open"}], "notes": "笔记"},
        headers={"Idempotency-Key": "mut-src2", "If-Match-Rev": str(src_rev0)}, cookies=alice["cookies"])
    assert put.status_code == 200
    rp = publish(c, alice["cookies"], t1)
    assert rp.status_code == 200 and rp.json()["republished"] is True
    assert rp.json()["task_id"] == c1.json()["task_id"] and rp.json()["server_rev"] == 2
    # t2 时间线不受影响（独立）
    assert c2.json()["server_rev"] == 1 and c.get(f"/api/v1/context/teams/{t2}/tasks", cookies=alice["cookies"]).json()["tasks"][0]["current_rev"] == 1
    # 单条决策粒度发布（依赖 2）
    dp = publish(c, alice["cookies"], t2, mode="decision", decision_id="dec_3")
    assert dp.status_code == 201
    dcopy = dp.json()
    assert [d["id"] for d in dcopy["decisions"]] == ["dec_3"] and "summary" not in dcopy
    assert publish(c, alice["cookies"], t2, mode="decision", decision_id="不存在").status_code == 404
    assert publish(c, alice["cookies"], t2, mode="weird").status_code == 422
    assert publish(c, alice["cookies"], "").status_code == 422


# ---------------- 撤回语义（§3.3）+ 归档团队（裁决④） ----------------


def test_withdraw_and_archived_rules(env):
    c, store = env
    alice, bob = create_member(c, "wd_a"), create_member(c, "wd_b")
    make_source_task(c, alice["cookies"])
    tid = setup_team(c, alice, bob)
    copy_id = publish(c, alice["cookies"], tid).json()["task_id"]
    # bob 撤 alice 发布的副本 → 403（需 admin）
    w = c.delete(f"/api/v1/context/teams/{tid}/tasks/{copy_id}", cookies=bob["cookies"])
    assert w.status_code == 403 and w.json()["error"]["code"] == "team_role_required"
    # 归档团队：新写入 409 team_archived，但既有副本仍可撤回（裁决④中项）
    arch = c.put(f"/api/v1/teams/{tid}/archive", cookies=alice["cookies"])
    assert arch.status_code == 200
    w2 = c.put(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/snapshot", json={"summary": "归档后新写"},
               headers={"Idempotency-Key": "mut-arch1", "If-Match-Rev": "1"}, cookies=bob["cookies"])
    assert w2.status_code == 409 and w2.json()["error"]["code"] == "team_archived"
    w3 = c.delete(f"/api/v1/context/teams/{tid}/tasks/{copy_id}", cookies=alice["cookies"])
    assert w3.status_code == 200 and w3.json()["withdrawn"] is True
    # 撤回后列表消失、原件健在、留痕 withdraw
    assert c.get(f"/api/v1/context/teams/{tid}/tasks", cookies=alice["cookies"]).json()["tasks"] == []
    assert c.get(f"/api/v1/context/tasks/{SRC_TASK}", cookies=alice["cookies"]).status_code == 200
    feed = c.get(f"/api/v1/teams/{tid}/audit", cookies=bob["cookies"]).json()["items"]
    assert feed[0]["action"] == "withdraw" and "publish" in [i["action"] for i in feed]
    # 局外人访问团队副本 → 404（防枚举）
    out = create_member(c, "wd_out")
    assert c.get(f"/api/v1/context/teams/{tid}/tasks/{copy_id}", cookies=out["cookies"]).status_code == 404


# ---------------- 发布态读面（规格 §4.3 角标+逐团队撤回；拍板二定版：内嵌原件 DTO） ----------------


def test_published_copies_read_surface(env):
    c, _ = env
    alice, bob = create_member(c, "ps_a"), create_member(c, "ps_b")
    make_source_task(c, alice["cookies"])
    t1 = setup_team(c, alice, bob)
    t2 = c.post("/api/v1/teams", json={"name": "第二队"}, cookies=alice["cookies"]).json()["team_id"]
    copy1 = publish(c, alice["cookies"], t1).json()
    copy2 = publish(c, alice["cookies"], t2).json()
    src = c.get(f"/api/v1/context/tasks/{SRC_TASK}", cookies=alice["cookies"]).json()
    pcs = src["published_copies"]
    assert len(pcs) == 2
    by_team = {p["team_id"]: p for p in pcs}
    assert by_team[t1]["copy_task_id"] == copy1["task_id"] and by_team[t1]["granularity"] == "task"
    assert by_team[t2]["team_name"] == "第二队"
    # 列表面同样内嵌（角标在列表也要渲染）
    lst = c.get("/api/v1/context/tasks", cookies=alice["cookies"]).json()["tasks"]
    row = next(t for t in lst if t["task_id"] == SRC_TASK)
    assert "published_copies" in row and len(row["published_copies"]) == 2
    # 决策粒度发布 → 第三条行 granularity=decision（角标 N 团队按 distinct team 归并，FE 侧职责）
    publish(c, alice["cookies"], t2, mode="decision", decision_id="dec_1")
    src2 = c.get(f"/api/v1/context/tasks/{SRC_TASK}", cookies=alice["cookies"]).json()
    assert len(src2["published_copies"]) == 3
    assert sum(1 for p in src2["published_copies"] if p["granularity"] == "decision") == 1
    # 逐团队撤回 → 对应行消失、其余保留（撤回面即读面闭环）
    c.delete(f"/api/v1/context/teams/{t1}/tasks/{copy1['task_id']}", cookies=alice["cookies"])
    src3 = c.get(f"/api/v1/context/tasks/{SRC_TASK}", cookies=alice["cookies"]).json()
    assert {p["team_id"] for p in src3["published_copies"]} == {t2}


# ---------------- 删除→恢复闭环（裁决③，QA 四步 E2E 的服务端承载） ----------------


def test_decision_delete_restore_closure(env):
    c, store = env
    alice, bob = create_member(c, "cl_a"), create_member(c, "cl_b")
    make_source_task(c, alice["cookies"])
    tid = setup_team(c, alice, bob)
    copy_id = publish(c, alice["cookies"], tid).json()["task_id"]
    # bob（editor）删 alice 副本里的决策——裁决③能删
    d = c.delete(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/decisions/dec_1", cookies=bob["cookies"])
    assert d.status_code == 200, d.text
    pre_rev = d.json()["pre_delete_rev"]
    # 留痕①：decision_delete 携 target_ref + pre_delete_rev
    feed = c.get(f"/api/v1/teams/{tid}/audit", cookies=alice["cookies"]).json()["items"]
    dele = next(i for i in feed if i["action"] == "decision_delete")
    assert dele["target_ref"] == "dec_1" and dele["pre_delete_rev"] == pre_rev
    # 副本现内容已无该决策
    now = c.get(f"/api/v1/context/teams/{tid}/tasks/{copy_id}", cookies=alice["cookies"]).json()
    assert [x["id"] for x in now["decisions"]] == ["dec_2"]
    # 恢复（任意 editor+，UI"恢复"按钮按留痕参数重推）
    r = c.post(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/decisions/dec_1/restore",
               json={"from_rev": pre_rev}, cookies=alice["cookies"])
    assert r.status_code == 200, r.text
    after = c.get(f"/api/v1/context/teams/{tid}/tasks/{copy_id}", cookies=bob["cookies"]).json()
    restored = next(x for x in after["decisions"] if x["id"] == "dec_1")
    assert restored == D1  # 恢复后内容=删除前 rev 内容（QA 断言）
    # 留痕②：恢复本身是新留痕 decision_restore
    feed2 = c.get(f"/api/v1/teams/{tid}/audit", cookies=bob["cookies"]).json()["items"]
    assert any(i["action"] == "decision_restore" and i["target_ref"] == "dec_1" for i in feed2)
    # 重复恢复 → 409 already_present；恢复不存在的决策 → 404
    assert c.post(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/decisions/dec_1/restore",
                  json={"from_rev": pre_rev}, cookies=bob["cookies"]).status_code == 409
    assert c.post(f"/api/v1/context/teams/{tid}/tasks/{copy_id}/decisions/nope/restore",
                  json={"from_rev": pre_rev}, cookies=bob["cookies"]).status_code == 404
