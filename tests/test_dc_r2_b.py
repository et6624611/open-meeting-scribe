"""
tests/test_dc_r2_b.py — DC-R2-b 决策三要素化回归（REQ-DECISION-CENTER-R2 §11-D4/D5）

覆盖：
  1. 两要素拆分 split_decision_title（正例/裸行/仅标题/待确认前缀组合）
  2. 纪要解析产出 title / owner 字段（auto 决策 owner 留空合法）
  3. CRUD：补录带标题 + 执行人（说话人档案为权威，改名全局跟随；空串清空指派）
  4. 聚合：决策 title 与 meeting_title 双轨不串位；owner 读侧解析；q 命中标题
  5. 存量兼容：无 title/owner 键的历史决策不报错
"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.server import app
from core.summarize import parse_decisions_with_status, split_decision_title


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c

# ============================================================
# 1. 两要素拆分
# ============================================================

@pytest.mark.parametrize("raw,title,content", [
    ("**Q4 预算冻结**：市场预算维持 120 万，其中 40% 用于展会。",
     "Q4 预算冻结", "市场预算维持 120 万，其中 40% 用于展会。"),
    ("**人选待定**：由产品委员会牵头推进。", "人选待定", "由产品委员会牵头推进。"),
    ("这条决策没有加粗标题，整句作为内容。", "", "这条决策没有加粗标题，整句作为内容。"),
    # 仅标题无正文 → 整体归入内容，不丢条目
    ("**只有标题**：", "", "**只有标题**："),
    # 冒号在标题内部（非两段式）不误拆
    ("说明：时间 12:00 截止", "", "说明：时间 12:00 截止"),
])
def test_split_decision_title(raw, title, content):
    assert split_decision_title(raw) == (title, content)


def test_split_decision_title_tolerates_none_and_blank():
    assert split_decision_title("") == ("", "")
    assert split_decision_title(None) == ("", "")  # type: ignore[arg-type]


# ============================================================
# 2. 纪要解析
# ============================================================

SUMMARY_TWO_ELEMENTS = """## 一、会议概要
略

## 二、主要结论

1. **Q4 预算冻结**：市场预算维持 120 万，其中 40% 用于行业展会。
2. **迭代范围收敛**：v2.1 只交付转写进度与决策中心两条主线。
3. [待确认] **执行人归属**：由产品委员会牵头，具体人选会后敲定。
4. 这条是无序写法的裸结论，没有加粗标题。

## 三、待办事项
- [ ] 张三：出方案（09-30）
"""


def test_parser_yields_title_and_empty_owner_for_auto():
    decisions, degrade = parse_decisions_with_status(SUMMARY_TWO_ELEMENTS)
    assert degrade is None
    assert len(decisions) == 4
    first = decisions[0]
    assert first["title"] == "Q4 预算冻结"
    assert first["text"] == "市场预算维持 120 万，其中 40% 用于行业展会。"
    # D4/D5：auto 决策不指派执行人，键位存在且为空
    assert first["owner_id"] is None
    assert first["owner_name"] == ""
    assert first["source"] == "auto"


def test_parser_pending_prefix_with_title():
    decisions, _ = parse_decisions_with_status(SUMMARY_TWO_ELEMENTS)
    pending = decisions[2]
    assert pending["pending_confirmation"] is True
    assert pending["title"] == "执行人归属"
    assert "待确认" not in pending["text"]
    assert "待确认" not in pending["title"]


def test_parser_plain_item_keeps_empty_title_without_loss():
    decisions, _ = parse_decisions_with_status(SUMMARY_TWO_ELEMENTS)
    bare = decisions[3]
    assert bare["title"] == ""
    assert bare["text"] == "这条是无序写法的裸结论，没有加粗标题。"


def test_parser_dedup_uses_content_after_title_split():
    summary = """## 二、主要结论

1. **预算冻结**：Q4 市场预算维持 120 万。
2. **另一标题**：Q4 市场预算维持 120 万。
"""
    decisions, _ = parse_decisions_with_status(summary)
    # 正文相同即视为重复（跨标题去重），仅保留先见项
    assert len(decisions) == 1
    assert decisions[0]["title"] == "预算冻结"


# ============================================================
# 3. CRUD（执行人以说话人档案为权威）
# ============================================================

FAKE_SPEAKERS = {"spk-1": "王五", "spk-2": "Speaker 2"}


@pytest.fixture()
def store_patched(monkeypatch):
    """隔离 app.store：把模块内的任务表指向临时字典，不触碰真实 data/tasks/ 也不污染全局。"""
    from app.routers import decisions as dr

    fake: dict = {}
    saved = []
    monkeypatch.setattr(dr, "tasks", fake)
    monkeypatch.setattr(dr, "save_task_to_disk", lambda tid: saved.append(tid))
    monkeypatch.setattr(dr, "get_speaker_name_map", lambda: dict(FAKE_SPEAKERS))
    yield dr, saved


def test_create_with_title_and_owner_store_resolves_archive_name(store_patched):
    dr, saved = store_patched
    dr.tasks["t1"] = {"task_id": "t1", "title": "评审会", "decisions": []}
    # 快照名故意与档案名不同：以档案名为权威（改名全局跟随的写侧对应物）
    res = dr.create_task_decision("t1", dr.DecisionCreateRequest(
        text="下季度切换到新供应商", title="供应商切换",
        owner_id="spk-1", owner_name="旧快照名",
    ))["decision"]
    assert res["title"] == "供应商切换"
    assert res["owner_id"] == "spk-1"
    assert res["owner_name"] == "王五"
    assert saved == ["t1"]


def test_create_owner_placeholder_archive_name_falls_back_to_snapshot(store_patched):
    """档案名是占位串（Speaker 2）时不采信，回退调用方快照（REQ-SPK-RN 口径同源）。"""
    dr, _ = store_patched
    dr.tasks["t1"] = {"task_id": "t1", "title": "t", "decisions": []}
    res = dr.create_task_decision("t1", dr.DecisionCreateRequest(
        text="x 内容", owner_id="spk-2", owner_name="赵六",
    ))["decision"]
    assert res["owner_name"] == "赵六"


def test_create_without_owner_is_legal(store_patched):
    dr, _ = store_patched
    dr.tasks["t1"] = {"task_id": "t1", "title": "t", "decisions": []}
    res = dr.create_task_decision("t1", dr.DecisionCreateRequest(text="仅内容一条"))["decision"]
    assert res["title"] == ""
    assert res["owner_id"] is None
    assert res["owner_name"] == ""


def test_create_blank_text_still_rejected(store_patched):
    dr, _ = store_patched
    dr.tasks["t1"] = {"task_id": "t1", "title": "t", "decisions": []}
    with pytest.raises(HTTPException):
        dr.create_task_decision("t1", dr.DecisionCreateRequest(text="   "))


def test_update_title_and_clear_owner(store_patched):
    dr, _ = store_patched
    dr.tasks["t1"] = {"task_id": "t1", "title": "t", "decisions": [{
        "id": "d1", "title": "旧标题", "text": "旧内容",
        "owner_id": "spk-1", "owner_name": "王五", "status": "active",
        "pending_confirmation": False, "source": "manual",
        "created_at": "2026-09-25T09:00:00", "updated_at": "2026-09-25T09:00:00",
        "superseded_by": None, "related_todo_ids": [],
    }]}
    res = dr.update_task_decision("t1", "d1", dr.DecisionUpdateRequest(
        title="新标题", text="新内容", owner_id="", owner_name="",
    ))["decision"]
    assert res["title"] == "新标题"
    assert res["text"] == "新内容"
    assert res["owner_id"] is None
    assert res["owner_name"] == ""


def test_update_without_owner_fields_keeps_owner_untouched(store_patched):
    """未显式携带 owner 字段 = 不改指派（区别于传空串清空）。"""
    dr, _ = store_patched
    dr.tasks["t1"] = {"task_id": "t1", "title": "t", "decisions": [{
        "id": "d1", "title": "", "text": "内容", "owner_id": "spk-1", "owner_name": "王五",
        "status": "active", "pending_confirmation": False, "source": "manual",
        "created_at": "x", "updated_at": "x", "superseded_by": None, "related_todo_ids": [],
    }]}
    res = dr.update_task_decision("t1", "d1", dr.DecisionUpdateRequest(text="改文"))["decision"]
    assert res["owner_id"] == "spk-1"
    assert res["owner_name"] == "王五"


# ============================================================
# 4. 聚合：双轨 title / owner 读侧解析 / q 命中标题
# ============================================================
#
# 聚合路由参数带 FastAPI Query 默认值，不可直接函数调用（默认值非 None），一律走 HTTP 栈；
# 路由与 CRUD 共用 store_patched 的临时任务表，因此结果集只含本用例数据。

def _legacy_task():
    """历史决策：无 title/owner 键（存量 359 条形态）。"""
    return {
        "task_id": "t-legacy", "title": "旧会议", "meeting_date": "2026-09-20",
        "decisions": [{
            "id": "dl1", "text": "存量决策没有标题", "status": "active",
            "pending_confirmation": False, "source": "backfill",
            "created_at": "2026-09-20T09:00:00", "updated_at": "2026-09-20T09:00:00",
            "superseded_by": None, "related_todo_ids": [],
        }],
    }


def _new_task():
    return {
        "task_id": "t-new", "title": "新会议", "meeting_date": "2026-09-24",
        "decisions": [{
            "id": "dn1", "title": "供应商切换", "text": "下季度切换到新供应商",
            "owner_id": "spk-1", "owner_name": "旧快照名", "status": "active",
            "pending_confirmation": False, "source": "manual",
            "created_at": "2026-09-24T09:00:00", "updated_at": "2026-09-24T09:00:00",
            "superseded_by": None, "related_todo_ids": [],
        }],
    }


def test_aggregation_separates_decision_title_from_meeting_title(store_patched, client):
    dr, _ = store_patched
    dr.tasks["t-new"] = _new_task()
    rows = client.get("/api/decisions").json()["decisions"]
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "供应商切换"           # 决策标题
    assert row["meeting_title"] == "新会议"        # 会议标题另键下发


def test_aggregation_resolves_owner_from_archive(store_patched, client):
    dr, _ = store_patched
    dr.tasks["t-new"] = _new_task()
    row = client.get("/api/decisions").json()["decisions"][0]
    assert row["owner_name"] == "王五"            # 档案名覆盖快照 → 改名全局跟随


def test_aggregation_owner_snapshot_when_archive_missing(store_patched, client):
    dr, _ = store_patched
    t = _new_task()
    t["decisions"][0]["owner_id"] = "spk-gone"
    t["decisions"][0]["owner_name"] = "已删档案人"
    dr.tasks["t-new"] = t
    row = client.get("/api/decisions").json()["decisions"][0]
    assert row["owner_name"] == "已删档案人"


def test_aggregation_legacy_decision_degrades_without_error(store_patched, client):
    dr, _ = store_patched
    dr.tasks["t-legacy"] = _legacy_task()
    row = client.get("/api/decisions").json()["decisions"][0]
    assert row["title"] == ""                     # 缺键 → 空串（前端按内容首句降级）
    assert row["owner_id"] is None
    assert row["owner_name"] == ""
    assert row["meeting_title"] == "旧会议"


def test_aggregation_keyword_matches_decision_title(store_patched, client):
    dr, _ = store_patched
    dr.tasks["t-new"] = _new_task()
    dr.tasks["t-legacy"] = _legacy_task()
    hits = client.get("/api/decisions", params={"q": "供应商切换"}).json()["decisions"]
    assert [d["id"] for d in hits] == ["dn1"]
    assert client.get("/api/decisions", params={"q": "不存在的词"}).json()["decisions"] == []


def test_group_label_uses_meeting_title(store_patched, client):
    """分组 label 仍为会议标题（语义随键名迁移，不变成决策标题）。"""
    dr, _ = store_patched
    dr.tasks["t-new"] = _new_task()
    body = client.get("/api/decisions", params={"group_by": "meeting"}).json()
    assert body["groups"][0]["label"] == "新会议"


def test_aggregation_meeting_title_falls_back_to_audio_name(store_patched, client):
    dr, _ = store_patched
    t = _new_task()
    t.pop("title")
    t["audio_name"] = "rec-0924.mp3"
    dr.tasks["t-new"] = t
    row = client.get("/api/decisions").json()["decisions"][0]
    assert row["meeting_title"] == "rec-0924.mp3"
