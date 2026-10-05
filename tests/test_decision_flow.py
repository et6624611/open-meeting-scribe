"""
tests/test_decision_flow.py — DC-UNIFY-01 单一决策流回归（2026-09-27 项目方裁决）

契约事实源：docs/API_CONTRACTS.md §12（DC-UNIFY-01 修订）。
覆盖口径：
  1. 纪要「主要结论」自动解析 → 决策流节点（todos），统一落「待决策」态
  2. 重新生成合并：只覆盖 auto、保留手动/注入、墓碑防复活、文本去重
  3. 节点级 CRUD：状态字典校验、done 跟随 closing、title/owner_id 承接三要素
  4. 跨会议聚合：数据源为 todos、过滤/分组/状态元信息随行、未知状态降级
  5. 注入联动：todo 与 decision 类型同写决策流
  6. 状态字典：三态默认集、锚点仅 done、旧结构自动迁移、删除回落 todos

旧 decision 对象的回归（test_decision_center / test_dc_r2_b / test_dc_r2_be /
test_dc_r2_c）随对象下线一并移除，其仍有效的断言已并入本文件。
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.server import app
from app.store import tasks
from core.summarize import (
    decision_text_key,
    merge_flow_after_regen,
    parse_decisions_with_status,
    split_decision_title,
)

SUMMARY = """# 会议纪要

## 一、会议概要
讨论了方案选型与排期。

## 二、主要结论
1. **方案选型**：项目采用方案A推进
2. [待确认] 预算需财务复核
3. 上线时间定在10月1日

## 三、待办事项
- [ ] **张三**：出排期（本周五前）
"""

SUMMARY_NEGATIVE = """## 二、主要结论
本次会议未形成明确结论

## 三、待办事项
无明确待办事项
"""


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def task_factory():
    """创建内存任务并在用例后清理 / in-memory task with cleanup."""
    created: list[str] = []

    def _make(**overrides) -> str:
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "status": "completed",
            "progress": 100,
            "title": "测试会议",
            "meeting_date": "2026-09-20",
            "created_at": "2026-09-20T10:00:00",
        }
        task.update(overrides)
        tasks[task_id] = task
        created.append(task_id)
        return task_id

    yield _make
    for tid in created:
        tasks.pop(tid, None)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """状态字典文件隔离到临时目录 / isolate the status dictionary file."""
    import core.decision_status as ds
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(ds, "DATA_DIR", data_dir)
    monkeypatch.setattr(ds, "STATUSES_FILE", data_dir / "decision_statuses.json")
    yield ds


# ============================================================
# 1. 自动解析：结论 → 决策流节点（待确认）
# ============================================================

def test_conclusions_parse_into_flow_nodes_pending_confirmation():
    nodes, degrade = parse_decisions_with_status(SUMMARY)
    assert degrade is None
    assert len(nodes) == 3
    for n in nodes:
        # 节点形状 = todos：有 text/assignee/status/how，不再有 owner_name/superseded_by
        assert {"id", "text", "assignee", "owner_id", "done", "status", "how", "source"} <= set(n)
        assert n["status"] == "to_decide" and n["source"] == "auto" and n["done"] is False
    # 「**标题**：正文」拆出 title，正文不含 [待确认] 前缀
    assert nodes[0]["title"] == "方案选型" and nodes[0]["text"] == "项目采用方案A推进"
    assert nodes[1]["title"] == "" and nodes[1]["pending_confirmation"] is True


def test_negative_conclusion_is_normal_empty_not_degradation():
    nodes, degrade = parse_decisions_with_status(SUMMARY_NEGATIVE)
    assert nodes == [] and degrade is None


def test_missing_section_reports_degradation():
    nodes, degrade = parse_decisions_with_status("# 纪要\n没有结论章节")
    assert nodes == [] and degrade == "missing_section"


# ---- DEBRISH-F1：[待确认] 与加粗标题混写的解析（模板 v1.3.0 实测碎屑回归） ----

SUMMARY_PENDING_MIXED = """## 二、主要结论
1. **控制系统与报表分离**：清洗单据不得写入控制系统
2. **[待确认] 预算复核**：需财务复核后定案
3. **[待确认] 版本管理规则**：留存策略尚未敲定
"""


def test_split_decision_title_handles_pending_markers():
    # 内层写法（v1.3.0 实测产出）：标记被正则消费，不丢 ** 碎片
    assert split_decision_title("**[待确认] 版本管理规则**：留存策略尚未敲定") == ("版本管理规则", "留存策略尚未敲定")
    # 外层写法：仍正常拆分
    assert split_decision_title("[待确认] **预算复核**：需财务复核") == ("预算复核", "需财务复核")
    # 普通两要素 / 裸行：既有行为不变
    assert split_decision_title("**方案选型**：采用方案A") == ("方案选型", "采用方案A")
    assert split_decision_title("裸行叙述不拆分")[0] == ""


def test_pending_marker_inside_bold_parsed_with_title_and_flag():
    nodes, degrade = parse_decisions_with_status(SUMMARY_PENDING_MIXED)
    assert degrade is None and len(nodes) == 3
    assert nodes[0]["title"] == "控制系统与报表分离" and nodes[0]["pending_confirmation"] is False
    # 两种前缀写法都必须：拆出干净标题（无 ** 碎片）+ pending 态正确
    assert nodes[1]["title"] == "预算复核" and nodes[1]["pending_confirmation"] is True
    assert nodes[2]["title"] == "版本管理规则" and nodes[2]["pending_confirmation"] is True
    for n in nodes[1:]:
        assert "**" not in n["text"] and "待确认" not in n["title"]


def test_dedup_distinguishes_pending_from_decided():
    # 同文不同态：已定结论与待确认提案不互相吞并（待确认用外层裸前缀写法）
    summary = """## 二、主要结论
1. **同一议题**：采用方案A
2. [待确认] **同一议题**：采用方案A
"""
    nodes, _ = parse_decisions_with_status(summary)
    assert len(nodes) == 2
    assert {n["pending_confirmation"] for n in nodes} == {True, False}


# ============================================================
# 2. 重新生成合并：只覆盖 auto + 墓碑 + 去重
# ============================================================

def test_merge_keeps_manual_and_replaces_auto():
    existing = [
        {"id": "m1", "text": "手动记录", "source": "manual"},
        {"id": "a1", "text": "旧结论", "source": "auto"},
    ]
    parsed = [{"id": "a2", "text": "新结论", "source": "auto"}]
    merged = merge_flow_after_regen(existing, parsed)
    texts = [t["text"] for t in merged]
    assert texts == ["手动记录", "新结论"]


def test_merge_drops_tombstoned_auto_nodes():
    parsed = [{"id": "a1", "text": "被删过的结论", "source": "auto"}]
    tombstones = [{"text_key": decision_text_key("被删过的结论")}]
    assert merge_flow_after_regen([], parsed, tombstones) == []


def test_merge_dedupes_against_kept_nodes():
    existing = [{"id": "m1", "text": "同一句话", "source": "manual"}]
    parsed = [{"id": "a1", "text": "同一句话", "source": "auto"}]
    merged = merge_flow_after_regen(existing, parsed)
    assert [t["id"] for t in merged] == ["m1"]


# ============================================================
# 3. 节点级 CRUD
# ============================================================

def test_create_node_carries_title_and_resolves_owner_from_archive(client, task_factory, monkeypatch):
    import core.decision_flow as flow
    monkeypatch.setattr(flow, "get_speaker_name_map", lambda: {"sp-1": "李四"})
    tid = task_factory()
    resp = client.post(f"/api/tasks/{tid}/todos", json={
        "text": "采用方案A", "title": "方案选型", "owner_id": "sp-1",
    })
    assert resp.status_code == 200
    node = resp.json()["todo"]
    assert node["title"] == "方案选型"
    assert node["assignee"] == "李四" and node["owner_id"] == "sp-1"
    # 手动添加落默认开放态（待决策），而非退役的待确认态
    assert node["status"] == "to_decide" and node["source"] == "manual"


def test_status_must_exist_in_dictionary(client, task_factory, store):
    store.load_statuses()
    tid = task_factory(todos=[])
    ok = client.put(f"/api/tasks/{tid}/todos/x", json={"status": "in_progress"})
    assert ok.status_code == 404  # 节点不存在，但状态校验通过（未 422）
    bad = client.post(f"/api/tasks/{tid}/todos", json={"text": "一条决策", "status": "not-a-status"})
    assert bad.status_code == 422


def test_done_follows_closing_flag(client, task_factory, store):
    store.load_statuses()
    tid = task_factory(todos=[])
    created = client.post(f"/api/tasks/{tid}/todos", json={"text": "上线时间定在10月1日"}).json()["todo"]
    done = client.put(f"/api/tasks/{tid}/todos/{created['id']}", json={"status": "done"}).json()["todo"]
    assert done["done"] is True
    reopened = client.put(f"/api/tasks/{tid}/todos/{done['id']}", json={"status": "in_progress"}).json()["todo"]
    assert reopened["done"] is False and reopened["status"] == "in_progress"


def test_delete_auto_node_writes_tombstone(client, task_factory):
    tid = task_factory(todos=[{"id": "a1", "text": "自动结论", "source": "auto", "status": "to_decide", "done": False}])
    assert client.delete(f"/api/tasks/{tid}/todos/a1").status_code == 200
    tombstones = tasks[tid].get("decision_deletions") or []
    assert [t["text_key"] for t in tombstones] == [decision_text_key("自动结论")]


def test_get_todos_carries_status_dictionary_meta(client, task_factory, store):
    store.load_statuses()
    tid = task_factory(todos=[{"id": "t1", "text": "决策", "status": "in_progress", "done": False}])
    node = client.get(f"/api/tasks/{tid}/todos").json()["todos"][0]
    assert node["status_name"] == "进行中" and node["status_closing"] is False
    assert node["meeting_title"] == "测试会议"


# ============================================================
# 4. 跨会议聚合（决策中心数据源）
# ============================================================

def test_aggregation_reads_decision_flow(client, task_factory, store):
    store.load_statuses()
    tid = task_factory(todos=[
        {"id": "n1", "title": "方案选型", "text": "采用方案A", "status": "in_progress",
         "source": "auto", "done": False, "created_at": "2026-09-20T10:00:00"},
    ])
    rows = client.get("/api/decisions").json()["decisions"]
    row = next(r for r in rows if r["id"] == "n1")
    assert row["task_id"] == tid and row["meeting_title"] == "测试会议"
    assert row["title"] == "方案选型"          # 决策自身标题，不与会议标题混用
    assert row["status_name"] == "进行中" and row["status_color"]

    # 旧 decision 对象不再被任何读路径消费
    task_factory(decisions=[{"id": "legacy", "text": "已下线的 decision 记录", "status": "active"}])
    assert all(r["id"] != "legacy" for r in client.get("/api/decisions").json()["decisions"])


def test_aggregation_filters_and_groups(client, task_factory, store):
    store.load_statuses()
    # 真实环下会加载数百个存量任务，因此用唯一 kb/日期隔离断言范围
    kb_a, kb_b = f"kb-{uuid.uuid4().hex[:8]}-a", f"kb-{uuid.uuid4().hex[:8]}-b"
    t1 = task_factory(title="甲会议", meeting_date="2026-09-20", project_id=kb_a,
                      todos=[{"id": "x1", "text": "甲会议决策", "status": "in_progress", "done": False}])
    task_factory(title="乙会议", meeting_date="2026-08-01", project_id=kb_b,
                 todos=[{"id": "x2", "text": "乙会议决策", "status": "done", "done": True}])

    assert {r["id"] for r in client.get("/api/decisions", params={"kb_id": kb_a}).json()["decisions"]} == {"x1"}
    assert {r["id"] for r in client.get("/api/decisions", params={"kb_id": kb_b}).json()["decisions"]} == {"x2"}
    assert {r["id"] for r in client.get("/api/decisions", params={"status": "in_progress", "kb_id": kb_a}).json()["decisions"]} == {"x1"}
    assert client.get("/api/decisions", params={"status": "nope"}).status_code == 422
    assert {r["id"] for r in client.get("/api/decisions", params={"q": "甲会议决策"}).json()["decisions"]} == {"x1"}
    assert {r["id"] for r in client.get("/api/decisions", params={"task_id": t1}).json()["decisions"]} == {"x1"}

    groups = client.get("/api/decisions", params={"kb_id": kb_a, "group_by": "meeting"}).json()["groups"]
    g = next(x for x in groups if x["task_id"] == t1)
    assert g["label"] == "甲会议" and [d["id"] for d in g["decisions"]] == ["x1"]


def test_aggregation_degrades_unknown_status_to_open_state(client, task_factory, store):
    store.load_statuses()
    task_factory(todos=[{"id": "z1", "text": "历史状态节点", "status": "deleted-custom-state", "done": False}])
    row = next(r for r in client.get("/api/decisions").json()["decisions"] if r["id"] == "z1")
    # 字典外的历史值 → 降级到首个开放态（待决策），不抛错不丢行
    assert row["status"] == "to_decide" and row["status_name"] == "待决策"


def test_legacy_task_without_status_derives_from_done(client, task_factory, store):
    store.load_statuses()
    task_factory(todos=[{"id": "old1", "text": "无状态字段的历史节点", "done": True}])
    row = next(r for r in client.get("/api/decisions").json()["decisions"] if r["id"] == "old1")
    assert row["status"] == "done" and row["status_closing"] is True


# ============================================================
# 5. 注入联动：todo 与 decision 同写决策流
# ============================================================

def test_decision_injection_joins_the_flow(client, task_factory):
    tid = task_factory()
    resp = client.post(f"/api/tasks/{tid}/inject", json={
        "type": "decision", "content": "**预算**：Q4 预算封顶 80 万", "source_message": "m1",
    })
    assert resp.status_code == 200
    assert "decisions" not in tasks[tid]           # 不再产生第二套对象
    node = tasks[tid]["todos"][0]
    assert node["title"] == "预算" and node["text"] == "Q4 预算封顶 80 万"
    assert node["status"] == "to_decide" and node["source"] == "injection"

    inj_id = resp.json()["item"]["id"]
    client.delete(f"/api/tasks/{tid}/injections/{inj_id}")
    assert tasks[tid]["todos"] == []


# ============================================================
# 6. 状态字典：默认状态 / 锚点 / 旧结构迁移 / 删除回落
# ============================================================

def test_dictionary_seeds_flow_statuses_with_two_closing_anchors(store):
    ids = [s["id"] for s in store.load_statuses()]
    assert ids == ["to_decide", "in_progress", "superseded", "done"]
    by_id = {s["id"]: s for s in store.load_statuses()}
    assert by_id["done"]["system"] is True and by_id["done"]["closing"] is True
    assert by_id["superseded"]["system"] is True and by_id["superseded"]["closing"] is True
    assert all(not by_id[k]["system"] for k in ("to_decide", "in_progress"))
    assert store.SYSTEM_ANCHORS == ("done", "superseded")


def test_legacy_dictionary_is_migrated_once_and_persisted(store):
    legacy = [
        {"id": "active", "name": "生效中", "name_en": "Active", "color": "var(--st-done)", "closing": False, "system": True},
        {"id": "done", "name": "完成", "name_en": "Done", "color": "var(--accent)", "closing": True, "system": True},
        {"id": "superseded", "name": "已被取代", "name_en": "Superseded", "color": "var(--st-decide)", "closing": True, "system": False},
    ]
    store.STATUSES_FILE.write_text(json.dumps(legacy), encoding="utf-8")
    ids = [s["id"] for s in store.load_statuses()]
    # 未改名的遗留态被剪除（active、旧 superseded），默认种子补齐；
    # superseded 以新系统锚点「已替代」补回，排在开放态之后、完成之前
    assert "active" not in ids
    assert ids == ["to_decide", "in_progress", "superseded", "done"]
    by_id = {s["id"]: s for s in store.load_statuses()}
    assert by_id["superseded"]["name"] == "已替代" and by_id["superseded"]["system"] is True
    on_disk = json.loads(store.STATUSES_FILE.read_text(encoding="utf-8"))
    assert [s["id"] for s in on_disk] == ids


def test_user_renamed_legacy_status_survives_migration(store):
    legacy = [
        {"id": "active", "name": "已定案", "name_en": "Active", "color": "var(--ok)", "closing": False, "system": True},
        {"id": "done", "name": "完成", "name_en": "Done", "color": "var(--accent)", "closing": True, "system": True},
    ]
    store.STATUSES_FILE.write_text(json.dumps(legacy), encoding="utf-8")
    ids = [s["id"] for s in store.load_statuses()]
    assert "active" in ids          # 被用户改过名 → 保留，不静默丢失
    assert "to_decide" in ids       # 三态种子照样补齐


def test_legacy_hex_colors_normalize_to_theme_tokens(store):
    """旧色板 hex 一次性归一为主题令牌；非表内 hex 保留；再读幂等不重复回写。"""
    legacy = [
        {"id": "to_decide", "name": "待决策", "name_en": "To decide", "color": "var(--st-decide)", "closing": False},
        {"id": "in_progress", "name": "进行中", "name_en": "In progress", "color": "var(--accent)", "closing": False},
        {"id": "done", "name": "已完成", "name_en": "Done", "color": "var(--st-done)", "closing": True, "system": True},
        {"id": "st-blocked", "name": "阻塞中", "name_en": "阻塞中", "color": "#D97706", "closing": False},
        {"id": "st-custom", "name": "自定义", "name_en": "自定义", "color": "#123456", "closing": False},
    ]
    store.STATUSES_FILE.write_text(json.dumps(legacy), encoding="utf-8")
    by_id = {s["id"]: s for s in store.load_statuses()}
    # 大写 hex 大小写不敏感命中归一；非系统色板 hex 原样保留
    assert by_id["st-blocked"]["color"] == "var(--warn)"
    assert by_id["st-custom"]["color"] == "#123456"
    on_disk = {s["id"]: s for s in json.loads(store.STATUSES_FILE.read_text(encoding="utf-8"))}
    assert on_disk["st-blocked"]["color"] == "var(--warn)"

    # 幂等：归一完成后 mtime 内容不再变化
    before = store.STATUSES_FILE.read_text(encoding="utf-8")
    store.load_statuses()
    assert store.STATUSES_FILE.read_text(encoding="utf-8") == before


def test_anchor_protection_and_custom_status_crud(client, store):
    with pytest.MonkeyPatch.context() as mp:
        import core.decision_status as ds
        mp.setattr(ds, "STATUSES_FILE", store.STATUSES_FILE)
        mp.setattr(ds, "DATA_DIR", store.STATUSES_FILE.parent)
        with TestClient(app) as c:
            assert c.put("/api/decision-statuses/done", json={"name": "结项"}).status_code == 400
            assert c.delete("/api/decision-statuses/done").status_code == 400
            created = c.post("/api/decision-statuses", json={"name": "阻塞中", "color": "#d97706"}).json()["status"]
            assert created["id"].startswith("st-") and created["closing"] is False
            assert c.put(f"/api/decision-statuses/{created['id']}", json={"closing": True}).status_code == 200
            assert c.delete(f"/api/decision-statuses/{created['id']}").json()["ok"] is True


def test_backfill_script_writes_flow_and_is_idempotent():
    """R4 回填：存量纪要的结论合入决策流（backfill/待决策），连跑两次不重复。"""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("backfill_decisions", root / "scripts" / "backfill_decisions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    task = {
        "task_id": "bf-1", "status": "completed", "title": "存量会议", "summary": SUMMARY,
        "todos": [{"id": "keep", "text": "手动记录的决策", "source": "manual", "status": "in_progress", "done": False}],
    }
    category, added, _ = mod.backfill_task(task)
    assert category == "backfilled" and added == 3
    assert task["todos"][0]["id"] == "keep"                     # 手动节点保留
    backfilled = [t for t in task["todos"] if t.get("source") == "backfill"]
    assert len(backfilled) == 3 and all(t["status"] == "to_decide" for t in backfilled)

    # 幂等：第二次直接跳过，不重复入流
    assert mod.backfill_task(task) == ("skipped_has_decisions", 0, "")
    assert len([t for t in task["todos"] if t.get("source") == "backfill"]) == 3


def test_delete_status_reassigns_flow_nodes(client, task_factory, store, monkeypatch):
    import app.routers.decision_statuses as dst
    import core.decision_status as ds
    monkeypatch.setattr(ds, "STATUSES_FILE", store.STATUSES_FILE)
    monkeypatch.setattr(ds, "DATA_DIR", store.STATUSES_FILE.parent)
    monkeypatch.setattr(dst, "STATUSES_FILE", store.STATUSES_FILE, raising=False)
    store.load_statuses()
    # 新增一个自定义状态并让节点引用它
    ds.create_status("阻塞中", "#d97706", False)
    custom = next(s for s in ds.load_statuses() if s["name"] == "阻塞中")
    tid = task_factory(todos=[{"id": "b1", "text": "被阻塞的决策", "status": custom["id"], "done": False}])

    resp = client.delete(f"/api/decision-statuses/{custom['id']}")
    assert resp.status_code == 200 and resp.json()["reassigned"] == 1
    # 被删状态下的节点回落到删后字典的首个开放态
    assert tasks[tid]["todos"][0]["status"] == "to_decide"


# ============================================================
# 7. 跨会议议题归并（DEBRISH-P2 全局视角）
# ============================================================

def _flow_row(nid, title, kb, task_id, ts):
    return {"id": nid, "title": title, "text": title, "kb_id": kb,
            "task_id": task_id, "meeting_title": "M", "meeting_date": ts[:10],
            "status_closing": False, "created_at": ts, "updated_at": ts}


def test_cluster_topics_merges_cross_meeting_same_topic():
    from core.decision_topic import cluster_topics
    # 同知识库、跨会议的同议题重述（措辞详略不同）应归为一簇
    rows = [
        _flow_row("a", "差旅预算调整流程需重构以支持组织变更场景", "kb1", "tA", "2026-09-10T10:00:00"),
        _flow_row("b", "差旅预算调整流程归属", "kb1", "tB", "2026-09-20T10:00:00"),
        # 弱相关议题不主动归入
        _flow_row("c", "上线时间定在下季度", "kb1", "tC", "2026-09-21T10:00:00"),
    ]
    groups = cluster_topics(rows)
    ab = [g for g in groups if {m["id"] for m in [g["main"], *g["history"]]} >= {"a", "b"}]
    assert len(ab) == 1
    g = ab[0]
    assert g["size"] == 2 and g["meeting_count"] == 2
    assert g["main"]["id"] == "b"              # 最新记录作主记录
    assert g["confidence"] >= 0.6
    assert "c" not in {m["id"] for m in [g["main"], *g["history"]]}


def test_cluster_topics_isolates_different_kb():
    from core.decision_topic import cluster_topics
    same_text = "预提科目体系需重构为一级费用科目结构"
    rows = [
        _flow_row("a", same_text, "kb1", "tA", "2026-09-10T10:00:00"),
        _flow_row("b", same_text, "kb2", "tB", "2026-09-20T10:00:00"),
    ]
    groups = cluster_topics(rows)
    # 同文本但跨知识库：不合并，各自单簇
    assert len(groups) == 2 and all(g["size"] == 1 for g in groups)


def test_aggregation_group_by_topic(client, task_factory, store):
    store.load_statuses()
    kb = "proj-shared"
    task_factory(project_id=kb, todos=[
        {"id": "x1", "title": "预算调整需支持跨组织跨期间", "text": "预算调整需支持跨组织跨期间",
         "source": "auto", "status": "in_progress", "created_at": "2026-09-05T10:00:00"},
    ])
    task_factory(project_id=kb, todos=[
        {"id": "x2", "title": "预算调整功能必须支持跨组织、跨期间操作", "text": "预算调整功能必须支持跨组织、跨期间操作",
         "source": "auto", "status": "to_decide", "created_at": "2026-09-25T10:00:00"},
    ])
    data = client.get("/api/decisions", params={"group_by": "topic"}).json()
    assert "topics" in data
    hit = [g for g in data["topics"] if {g["main"]["id"], *(m["id"] for m in g["history"])} >= {"x1", "x2"}]
    assert len(hit) == 1 and hit[0]["meeting_count"] == 2
    # 主记录为更新的一条（x2），演变链挂 x1
    assert hit[0]["main"]["id"] == "x2" and hit[0]["history"][0]["id"] == "x1"


# ============================================================
# 7. 决策演变链：标记/撤销「已被替代」 + 单任务演变归属
# ============================================================

def _evolution_pair(task_factory, *, old_status="to_decide"):
    """两场会议、同 kb、同议题的一对节点（x1 旧 / x2 新）。

    标题带用例唯一 token：写盘的任务会被后续用例 TestClient startup 重载，
    同标题会跨用例吸附成大簇，token 保证聚类只发生在本对之间。
    """
    token = uuid.uuid4().hex[:8]
    kb = f"proj-evo-{token}"
    t1 = task_factory(
        project_id=kb, title="旧会议", meeting_date="2026-09-05",
        todos=[{"id": "x1", "title": f"{token}预算调整需支持跨组织跨期间",
                "text": f"{token}预算调整需支持跨组织跨期间", "source": "auto",
                "status": old_status, "done": old_status == "done",
                "created_at": "2026-09-05T10:00:00"}])
    t2 = task_factory(project_id=kb, title="新会议", meeting_date="2026-09-25",
                      todos=[{"id": "x2", "title": f"{token}预算调整功能必须支持跨组织、跨期间操作",
                              "text": f"{token}预算调整功能必须支持跨组织、跨期间操作", "source": "auto",
                              "status": "to_decide", "created_at": "2026-09-25T10:00:00"}])
    return t1, t2


def test_supersede_marks_closing_with_snapshot_and_changes_main(client, task_factory, store):
    store.load_statuses()
    t1, t2 = _evolution_pair(task_factory, old_status="in_progress")

    resp = client.post(f"/api/tasks/{t1}/todos/x1/supersede",
                       json={"by_task_id": t2, "by_todo_id": "x2"})
    assert resp.status_code == 200
    node = resp.json()["todo"]
    assert node["status"] == "superseded" and node["done"] is True
    link = node["superseded_by"]
    assert link["task_id"] == t2 and link["todo_id"] == "x2"
    assert link["prev_status"] == "in_progress" and link["marked_at"]
    assert "预算调整功能" in link["title"] and link["meeting_title"] == "新会议"

    # 任务级读侧随行带出关系
    got = client.get(f"/api/tasks/{t1}/todos").json()["todos"]
    assert got[0]["superseded_by"]["todo_id"] == "x2"
    assert got[0]["status_closing"] is True

    # 议题主记录仍是新节点；旧节点闭档沉在演变链
    data = client.get("/api/decisions", params={"group_by": "topic"}).json()
    hit = [g for g in data["topics"] if g["main"]["id"] == "x2"][0]
    assert hit["history"][0]["id"] == "x1"
    assert hit["history"][0]["status_closing"] is True


def test_supersede_conflicts(client, task_factory, store):
    store.load_statuses()
    t1, t2 = _evolution_pair(task_factory)

    # 自身不能替代自身
    assert client.post(f"/api/tasks/{t1}/todos/x1/supersede",
                       json={"by_task_id": t1, "by_todo_id": "x1"}).status_code == 422
    # 目标不存在
    assert client.post(f"/api/tasks/{t1}/todos/x1/supersede",
                       json={"by_task_id": t2, "by_todo_id": "nope"}).status_code == 404
    # 节点不存在
    assert client.post(f"/api/tasks/{t1}/todos/nope/supersede",
                       json={"by_task_id": t2, "by_todo_id": "x2"}).status_code == 404

    ok = client.post(f"/api/tasks/{t1}/todos/x1/supersede",
                     json={"by_task_id": t2, "by_todo_id": "x2"})
    assert ok.status_code == 200
    # 重复标记 → 409 契约 {code, reason}
    again = client.post(f"/api/tasks/{t1}/todos/x1/supersede",
                        json={"by_task_id": t2, "by_todo_id": "x2"})
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "already_superseded"


def test_revert_supersede_restores_prev_status(client, task_factory, store):
    store.load_statuses()
    t1, t2 = _evolution_pair(task_factory, old_status="in_progress")
    client.post(f"/api/tasks/{t1}/todos/x1/supersede",
                json={"by_task_id": t2, "by_todo_id": "x2"})

    resp = client.delete(f"/api/tasks/{t1}/todos/x1/supersede")
    assert resp.status_code == 200
    node = resp.json()["todo"]
    assert node["status"] == "in_progress" and node["done"] is False
    assert "superseded_by" not in node

    # 非替代态撤销 → 409
    conflict = client.delete(f"/api/tasks/{t1}/todos/x1/supersede")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "not_superseded"


def test_task_evolution_reports_cluster_membership(client, task_factory, store):
    store.load_statuses()
    t1, t2 = _evolution_pair(task_factory)

    evo_old = client.get("/api/decisions/evolution", params={"task_id": t1}).json()["evolution"]
    assert evo_old["x1"]["role"] == "history"
    assert evo_old["x1"]["meeting_count"] == 2
    assert evo_old["x1"]["latest"]["task_id"] == t2
    assert evo_old["x1"]["latest"]["todo_id"] == "x2"

    evo_new = client.get("/api/decisions/evolution", params={"task_id": t2}).json()["evolution"]
    assert evo_new["x2"]["role"] == "main"

    # 未知任务 404
    assert client.get("/api/decisions/evolution", params={"task_id": "nope"}).status_code == 404


def test_revert_supersede_falls_back_when_prev_status_deleted(client, task_factory, store):
    """原状态在替代期间被用户从字典删除 → 撤销降级 to_decide，不复活非法状态。"""
    store.load_statuses()
    # 自定义开放态
    created = client.post("/api/decision-statuses", json={"name": "复核中"})
    assert created.status_code == 200
    custom_id = created.json()["status"]["id"]

    t1, t2 = _evolution_pair(task_factory)
    put = client.put(f"/api/tasks/{t1}/todos/x1", json={"status": custom_id})
    assert put.status_code == 200

    client.post(f"/api/tasks/{t1}/todos/x1/supersede",
                json={"by_task_id": t2, "by_todo_id": "x2"})
    # 替代期间用户删掉原状态（节点当前为 superseded，不被删除联动重指派）
    gone = client.delete(f"/api/decision-statuses/{custom_id}")
    assert gone.status_code == 200

    resp = client.delete(f"/api/tasks/{t1}/todos/x1/supersede")
    assert resp.status_code == 200
    node = resp.json()["todo"]
    assert node["status"] == "to_decide" and node["done"] is False
    assert "superseded_by" not in node


def test_evolution_main_shifts_when_main_node_superseded(client, task_factory, store):
    """把簇内主记录标为被旧节点替代 → 选主跳过闭档自动前移，evolution 角色随之反转。"""
    store.load_statuses()
    t1, t2 = _evolution_pair(task_factory)

    # 反向标记：新节点（当前 main）被旧节点替代（手动路径不做时序限制）
    resp = client.post(f"/api/tasks/{t2}/todos/x2/supersede",
                       json={"by_task_id": t1, "by_todo_id": "x1"})
    assert resp.status_code == 200

    # 聚合视图主记录前移为 x1，x2 闭档沉入演变链
    data = client.get("/api/decisions", params={"group_by": "topic"}).json()
    hit = [g for g in data["topics"] if {g["main"]["id"], *(m["id"] for m in g["history"])} >= {"x1", "x2"}]
    assert len(hit) == 1
    assert hit[0]["main"]["id"] == "x1"
    assert hit[0]["history"][0]["id"] == "x2"
    assert hit[0]["history"][0]["status"] == "superseded"

    # 归属角色同步反转：latest 指向旧会议节点
    evo_new = client.get("/api/decisions/evolution", params={"task_id": t2}).json()["evolution"]
    assert evo_new["x2"]["role"] == "history"
    assert evo_new["x2"]["latest"]["todo_id"] == "x1"
    evo_old = client.get("/api/decisions/evolution", params={"task_id": t1}).json()["evolution"]
    assert evo_old["x1"]["role"] == "main"
