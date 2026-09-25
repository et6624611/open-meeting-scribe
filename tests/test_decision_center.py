"""
tests/test_decision_center.py — REQ-DECISION-CENTER B1 回归（R1 抽取 / R2 API / R4 回填）

依据 docs/REQUIREMENT-DECISION-CENTER.md v0.2.0 §7 与
docs/API_CONTRACTS.md §12。覆盖派工单 DC-DEC-B1 验收映射：
- AC-1 抽取正例（3 条编号结论含 1 条 [待确认]）
- AC-2 抽取负例（"未形成明确结论" → 空数组，非降级）
- AC-3 解析失败降级（章节缺失 → 置空 + joblog warning + 任务不失败）
- AC-4 重新生成保护（auto 替换，manual/injection/backfill 保留）
- AC-5/6/10 任务级 CRUD、supersede、脏检测时间戳
- AC-5 聚合 API（日期/知识库/状态/关键词过滤、分组、404/422）
- AC-7 回填幂等（连跑两次；user_summary 优先；backfill 来源）
- AC-9 兼容硬约束（旧任务无 decisions 字段按空数组，不报错）
"""

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.server import app
from app.store import tasks
from core.summarize import (
    merge_decisions_after_regen,
    parse_decisions_from_summary,
    parse_decisions_with_status,
)

ROOT = Path(__file__).resolve().parent.parent

SUMMARY_WITH_DECISIONS = """# 会议纪要

## 一、会议概要
讨论了方案选型与排期。

## 二、主要结论
1. 项目采用方案A推进
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
    """创建内存任务并在用例后清理内存与磁盘 / create in-memory task, cleanup after."""
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
        for suffix in (".json", ".joblog.jsonl"):
            f = ROOT / "data" / "tasks" / f"{tid}{suffix}"
            f.unlink(missing_ok=True)


# ============================================================
# R1 — 解析器单测
# ============================================================


class TestParseDecisions:
    def test_three_numbered_items_with_pending_flag(self):
        """AC-1：3 条编号结论 → 恰 3 条决策，[待确认] 前缀正确标记且不残留在 text。"""
        decisions, status = parse_decisions_with_status(SUMMARY_WITH_DECISIONS)
        assert status is None
        assert len(decisions) == 3
        assert [d["pending_confirmation"] for d in decisions] == [False, True, False]
        assert decisions[1]["text"] == "预算需财务复核"
        for d in decisions:
            assert d["status"] == "active"
            assert d["source"] == "auto"
            assert d["superseded_by"] is None
            assert d["related_todo_ids"] == []
            assert d["id"] and d["created_at"] and d["updated_at"]

    def test_negative_conclusion_is_clean_empty(self):
        """AC-2：'未形成明确结论' → 空数组、status None（不算解析失败）。"""
        decisions, status = parse_decisions_with_status(SUMMARY_NEGATIVE)
        assert decisions == []
        assert status is None
        assert parse_decisions_from_summary(SUMMARY_NEGATIVE) == []

    def test_missing_section_degrades(self):
        """AC-3：无「主要结论」章节 → 空 + missing_section。"""
        decisions, status = parse_decisions_with_status("（对话稿为空，无法生成纪要）")
        assert decisions == []
        assert status == "missing_section"

    def test_empty_section_degrades(self):
        """AC-3：章节存在但无任何条目、又无阴性说明 → no_items。"""
        decisions, status = parse_decisions_with_status("## 二、主要结论\n\n## 三、待办事项\n")
        assert decisions == []
        assert status == "no_items"

    def test_lenient_backfill_style_parsing(self):
        """宽容解析：无序号标题、裸行、bullet、checkbox、全角【待确认】前缀。"""
        summary = (
            "## 主要结论\n"
            "- 裸条目甲\n"
            "- [ ] 裸条目乙\n"
            "【待确认】二期范围\n"
            "### 下一章节\n"
            "1. 不应被收集\n"
        )
        decisions = parse_decisions_from_summary(summary)
        assert [d["text"] for d in decisions] == ["裸条目甲", "裸条目乙", "二期范围"]
        assert decisions[2]["pending_confirmation"] is True

    def test_template_placeholder_lines_skipped(self):
        """模板占位行（整行方括号）不得被收成决策。"""
        summary = "## 二、主要结论\n[列出会议明确达成的结论或决策，每条用序号标注]\n1. 真结论"
        decisions = parse_decisions_from_summary(summary)
        assert [d["text"] for d in decisions] == ["真结论"]

    def test_duplicate_items_deduped(self):
        summary = "## 二、主要结论\n1. 结论重复\n2. 结论重复"
        assert len(parse_decisions_from_summary(summary)) == 1


class TestRF1DualSection:
    """RF-1：决策抽取须覆盖「主要结论」与「决策」双章节（默认模板决策栏数据来源）。"""

    def test_template_style_dual_section_merged_and_deduped(self):
        """模板式纪要（两节内容不同+一条逐字重复）→ 两节全收、跨节去重、[待确认] 正确。"""
        summary = (
            "# 会议纪要\n\n"
            "## 一、会议概要\n讨论了结算方案。\n\n"
            "## 二、主要结论\n"
            "1. 结算周期改为月结\n"
            "2. 供应商白名单由采购部维护\n\n"
            "## 三、决策\n"
            "1. **结算周期改为月结**\n"
            "2. [待确认] **二期范围回去敲定**\n\n"
            "## 四、议题归类\n### 议题1：结算\n略\n"
        )
        decisions, status = parse_decisions_with_status(summary)
        assert status is None
        texts = [d["text"] for d in decisions]
        # 「结算周期改为月结」跨节去重后保留首次出现（主要结论节的裸文本）
        assert texts == [
            "结算周期改为月结",
            "供应商白名单由采购部维护",
            "**二期范围回去敲定**",
        ]
        assert decisions[2]["pending_confirmation"] is True
        assert all(d["source"] == "auto" for d in decisions)

    def test_both_sections_negative_is_clean_empty_no_warn(self):
        """两节均为阴性说明 → 正常空结果（status=None），不触发降级。"""
        summary = (
            "## 二、主要结论\n本次会议未形成明确结论\n\n"
            "## 三、决策\n本次会议未形成明确决策\n\n"
            "## 四、议题归类\n略\n"
        )
        decisions, status = parse_decisions_with_status(summary)
        assert decisions == []
        assert status is None

    def test_decisions_section_only_without_conclusions(self):
        """仅有「决策」章节（主要结论节缺失）→ 正常抽取，不降级为 missing_section。"""
        summary = "## 三、决策\n1. 采用灰度发布\n2. 【待确认】回滚阈值\n"
        decisions, status = parse_decisions_with_status(summary)
        assert status is None
        assert [d["text"] for d in decisions] == ["采用灰度发布", "回滚阈值"]
        assert decisions[1]["pending_confirmation"] is True

    def test_both_sections_missing_still_degrades(self):
        """两章节均缺失 → 仍按 missing_section 降级（AC-3 语义不变）。"""
        decisions, status = parse_decisions_with_status("## 一、会议概要\n只有概要。")
        assert decisions == []
        assert status == "missing_section"


class TestRegenMerge:
    def test_only_auto_replaced(self):
        """AC-4：merge 只覆盖 auto，manual/injection/backfill 保留。"""
        existing = [
            {"id": "m", "source": "manual"},
            {"id": "a1", "source": "auto"},
            {"id": "i", "source": "injection"},
            {"id": "b", "source": "backfill"},
        ]
        merged = merge_decisions_after_regen(existing, [{"id": "a2", "source": "auto"}])
        assert [d["id"] for d in merged] == ["m", "i", "b", "a2"]

    def test_empty_existing(self):
        assert merge_decisions_after_regen([], []) == []


# ============================================================
# R1 — stage2 写回链路（打桩 LLM 调用，真实 joblog/落盘语义）
# ============================================================


class TestStage2Writeback:
    def _run_stage2(self, monkeypatch, task_id: str, summary_text: str):
        import core.projects as projects
        import core.pipeline_runner as pr

        monkeypatch.setattr(
            pr, "run_pipeline_stage2",
            lambda **kw: {"summary": summary_text, "title": "T", "output_path": "",
                          "dialogue": [], "speaker_mapping": {}, "speaker_uuid_mapping": {}, "chapters": []},
        )
        monkeypatch.setattr(projects, "sync_meeting_to_folders", lambda t: [])
        pr._run_stage2_for_task(task_id, Path("data/nonexistent.wav"), None)

    def test_extraction_happy_and_pending(self, monkeypatch, task_factory):
        """AC-1（链路级）：stage2 完成后 task["decisions"] 恰有 3 条 auto 决策。"""
        task_id = task_factory(dialogue=[{"speaker_id": 0, "text": "甲" * 10}])
        self._run_stage2(monkeypatch, task_id, SUMMARY_WITH_DECISIONS)
        decisions = tasks[task_id]["decisions"]
        assert len(decisions) == 3
        assert all(d["source"] == "auto" for d in decisions)
        assert tasks[task_id]["status"] == "completed"

    def test_broken_summary_warns_but_completes(self, monkeypatch, task_factory):
        """AC-3：格式破坏 summary → 任务不失败、decisions 置空、joblog 有 warn 事件。"""
        task_id = task_factory(dialogue=[{"speaker_id": 0, "text": "甲" * 10}])
        self._run_stage2(monkeypatch, task_id, "对话内容不足，无法生成完整纪要")
        assert tasks[task_id]["status"] == "completed"
        assert tasks[task_id]["decisions"] == []
        log_file = ROOT / "data" / "tasks" / f"{task_id}.joblog.jsonl"
        assert log_file.exists()
        events = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
        warnings = [e for e in events if e.get("level") == "warn" and "决策" in e.get("message", "")]
        assert warnings, events

    def test_regen_replaces_auto_keeps_manual(self, monkeypatch, task_factory):
        """AC-4（链路级）：重新生成后 manual/injection 保留，旧 auto 被新解析替换。"""
        task_id = task_factory(
            dialogue=[{"speaker_id": 0, "text": "甲" * 10}],
            decisions=[
                {"id": "m1", "text": "手工补充", "source": "manual"},
                {"id": "a0", "text": "旧自动决策", "source": "auto"},
            ],
        )
        self._run_stage2(monkeypatch, task_id, SUMMARY_WITH_DECISIONS)
        decisions = tasks[task_id]["decisions"]
        assert decisions[0]["id"] == "m1"
        assert "旧自动决策" not in [d["text"] for d in decisions]
        assert len(decisions) == 4  # 1 manual + 3 new auto


# ============================================================
# R2 — 任务级 CRUD / supersede / 注入联动
# ============================================================


class TestTaskDecisionCRUD:
    def test_legacy_task_without_decisions_reads_empty(self, client, task_factory):
        """AC-9：旧任务无 decisions 字段 → GET 返回空数组不报错。"""
        task_id = task_factory()
        resp = client.get(f"/api/tasks/{task_id}/decisions")
        assert resp.status_code == 200
        assert resp.json() == {"decisions": []}

    def test_post_put_delete_roundtrip(self, client, task_factory):
        """AC-5：POST（source=manual）→ PUT 局部更新 → DELETE；updated_at 前进。"""
        task_id = task_factory()
        resp = client.post(
            f"/api/tasks/{task_id}/decisions",
            json={"text": "采用 PostgreSQL", "pending_confirmation": True, "related_todo_ids": ["t1"]},
        )
        assert resp.status_code == 200
        d = resp.json()["decision"]
        assert d["source"] == "manual" and d["status"] == "active"
        assert d["pending_confirmation"] is True and d["related_todo_ids"] == ["t1"]

        resp = client.put(
            f"/api/tasks/{task_id}/decisions/{d['id']}",
            json={"text": "采用 MySQL", "status": "revoked"},
        )
        updated = resp.json()["decision"]
        assert updated["text"] == "采用 MySQL" and updated["status"] == "revoked"
        assert updated["pending_confirmation"] is True  # 未携带字段保持不变

        assert client.delete(f"/api/tasks/{task_id}/decisions/{d['id']}").json() == {"ok": True}
        assert client.get(f"/api/tasks/{task_id}/decisions").json()["decisions"] == []

    def test_write_touches_last_modified_at(self, client, task_factory):
        """AC-10：决策写操作触发 last_modified_at（知识库脏检测链路）。"""
        task_id = task_factory()
        resp = client.post(f"/api/tasks/{task_id}/decisions", json={"text": "决策甲"})
        assert tasks[task_id].get("last_modified_at")
        client.put(f"/api/tasks/{task_id}/decisions/{resp.json()['decision']['id']}",
                   json={"pending_confirmation": True})
        assert tasks[task_id]["last_modified_at"]

    def test_404_and_422(self, client, task_factory):
        """AC-5：task 不存在 404；decision 不存在 404；非法 status / 空 text 422。"""
        assert client.get("/api/tasks/no-such-task/decisions").status_code == 404
        task_id = task_factory()
        assert client.put(f"/api/tasks/{task_id}/decisions/no-such", json={"text": "x"}).status_code == 404
        assert client.delete(f"/api/tasks/{task_id}/decisions/no-such").status_code == 404
        assert client.post(f"/api/tasks/{task_id}/decisions", json={"text": ""}).status_code == 422
        assert client.post(f"/api/tasks/{task_id}/decisions", json={"text": "   "}).status_code == 422
        assert client.put(f"/api/tasks/{task_id}/decisions/x", json={"status": "bogus"}).status_code == 422

    def test_supersede_cross_task_and_errors(self, client, task_factory):
        """AC-6：跨任务 supersede 写入 status/superseded_by；取代方不存在 404；自指 400。"""
        t1 = task_factory(title="会议一")
        t2 = task_factory(title="会议二")
        r1 = client.post(f"/api/tasks/{t1}/decisions", json={"text": "旧方案"})
        r2 = client.post(f"/api/tasks/{t2}/decisions", json={"text": "新方案"})
        d1, d2 = r1.json()["decision"], r2.json()["decision"]

        resp = client.patch(
            f"/api/tasks/{t1}/decisions/{d1['id']}/supersede",
            json={"task_id": t2, "decision_id": d2["id"]},
        )
        assert resp.status_code == 200
        marked = resp.json()["decision"]
        assert marked["status"] == "superseded"
        assert marked["superseded_by"] == {"task_id": t2, "decision_id": d2["id"]}

        assert client.patch(
            f"/api/tasks/{t1}/decisions/{d1['id']}/supersede",
            json={"task_id": t2, "decision_id": "ghost"},
        ).status_code == 404
        assert client.patch(
            f"/api/tasks/{t1}/decisions/{d1['id']}/supersede",
            json={"task_id": "ghost-task", "decision_id": d2["id"]},
        ).status_code == 404
        assert client.patch(
            f"/api/tasks/{t1}/decisions/{d1['id']}/supersede",
            json={"task_id": t1, "decision_id": d1["id"]},
        ).status_code == 400

    def test_dangling_supersede_ref_still_readable(self, client, task_factory):
        """AC-6（降级）：取代方任务被删后读取不报错（引用悬空由前端降级显示）。"""
        t1 = task_factory()
        t2 = task_factory()
        d1 = client.post(f"/api/tasks/{t1}/decisions", json={"text": "旧"}).json()["decision"]
        d2 = client.post(f"/api/tasks/{t2}/decisions", json={"text": "新"}).json()["decision"]
        client.patch(f"/api/tasks/{t1}/decisions/{d1['id']}/supersede",
                     json={"task_id": t2, "decision_id": d2["id"]})
        tasks.pop(t2)
        resp = client.get(f"/api/tasks/{t1}/decisions")
        assert resp.status_code == 200
        assert resp.json()["decisions"][0]["superseded_by"]["task_id"] == t2


class TestDecisionInjection:
    def test_decision_injection_creates_item_and_cascade_delete(self, client, task_factory):
        """R1 注入：type=decision → source=injection 决策项；删注入级联删除。"""
        task_id = task_factory()
        resp = client.post(f"/api/tasks/{task_id}/inject",
                           json={"type": "decision", "content": "会上敲定的注入决策", "source_message": "x"})
        assert resp.status_code == 200
        injection_id = resp.json()["item"]["id"]

        decisions = client.get(f"/api/tasks/{task_id}/decisions").json()["decisions"]
        assert len(decisions) == 1
        d = decisions[0]
        assert d["id"] == injection_id
        assert d["source"] == "injection" and d["text"] == "会上敲定的注入决策"

        client.delete(f"/api/tasks/{task_id}/injections/{injection_id}")
        assert client.get(f"/api/tasks/{task_id}/decisions").json()["decisions"] == []


# ============================================================
# R2 — 跨任务聚合
# ============================================================


class TestAggregation:
    @pytest.fixture()
    def seeded(self, task_factory):
        t_a = task_factory(title="会议A", meeting_date="2026-09-22", project_id="kb-1",
                           decisions=[
                               {"id": "a1", "text": "甲决策", "status": "active", "source": "auto",
                                "pending_confirmation": False, "created_at": "2026-09-22T10:00:00",
                                "updated_at": "2026-09-22T10:00:00", "superseded_by": None, "related_todo_ids": []},
                               {"id": "a2", "text": "乙决策已被取代", "status": "superseded", "source": "auto",
                                "pending_confirmation": False, "created_at": "2026-09-22T09:00:00",
                                "updated_at": "2026-09-22T09:00:00",
                                "superseded_by": {"task_id": "x", "decision_id": "y"}, "related_todo_ids": []},
                           ])
        t_b = task_factory(title="会议B", meeting_date="2026-09-10", project_id="kb-2",
                           decisions=[
                               {"id": "b1", "text": "丙旧决策", "status": "active", "source": "backfill",
                                "pending_confirmation": True, "created_at": "2026-09-10T08:00:00",
                                "updated_at": "2026-09-10T08:00:00", "superseded_by": None, "related_todo_ids": []},
                           ])
        t_c = task_factory(title="会议C无日期", meeting_date=None,
                           decisions=[{"id": "c1", "text": "无日期决策", "status": "active", "source": "manual",
                                        "pending_confirmation": False, "created_at": "2026-09-01T08:00:00",
                                        "updated_at": "2026-09-01T08:00:00", "superseded_by": None, "related_todo_ids": []}])
        return t_a, t_b, t_c

    def _ids(self, rows):
        return {row["id"] for row in rows}

    def test_flat_list_enriched_fields(self, client, seeded):
        resp = client.get("/api/decisions")
        assert resp.status_code == 200
        body = resp.json()
        rows = [r for r in body["decisions"] if r["task_id"] in seeded]
        assert body["total"] >= len(rows)
        sample = next(r for r in rows if r["id"] == "a1")
        # DC-R2-b 契约修正：行内 `title` 改为决策自身标题，会议标题走 `meeting_title`
        assert sample["meeting_title"] == "会议A" and sample["meeting_date"] == "2026-09-22"
        assert sample["title"] == ""  # 存量决策无自身标题 → 空串降级
        assert sample["kb_id"] == "kb-1"  # kb_name 允许为 None（无该项目记录）
        # meeting_date 倒序：a* 在 b* 前
        dates = [r["meeting_date"] for r in rows]
        assert dates == sorted(dates, key=lambda x: x or "", reverse=True)

    def test_date_range_excludes_undated(self, client, seeded):
        rows = client.get("/api/decisions?since=2026-09-15&until=2026-09-30").json()["decisions"]
        mine = self._ids([r for r in rows if r["task_id"] in seeded])
        assert mine == {"a1", "a2"}

    def test_status_and_q_and_kb_filters_stack(self, client, seeded):
        rows = client.get("/api/decisions?status=active&kb_id=kb-2").json()["decisions"]
        assert self._ids([r for r in rows if r["task_id"] in seeded]) == {"b1"}
        rows = client.get("/api/decisions?q=乙").json()["decisions"]
        assert self._ids([r for r in rows if r["task_id"] in seeded]) == {"a2"}

    def test_group_by_meeting(self, client, seeded):
        body = client.get("/api/decisions?group_by=meeting&since=2026-09-01").json()
        groups = [g for g in body["groups"] if g["key"] in seeded]
        assert {g["key"] for g in groups} == {seeded[0], seeded[1]}
        g_a = next(g for g in groups if g["key"] == seeded[0])
        assert g_a["label"] == "会议A" and len(g_a["decisions"]) == 2

    def test_invalid_params_rejected(self, client, seeded):
        assert client.get("/api/decisions?status=bogus").status_code == 422
        assert client.get("/api/decisions?since=not-a-date").status_code == 400
        assert client.get("/api/decisions?group_by=bogus").status_code == 422

    def test_legacy_tasks_without_decisions_ignored(self, client, task_factory):
        """AC-9（聚合）：无 decisions 字段的旧任务参与聚合不报错。"""
        task_factory(title="老任务", decisions=None)  # 显式 None 模拟脏数据
        resp = client.get("/api/decisions")
        assert resp.status_code == 200


# ============================================================
# R4 — 回填脚本
# ============================================================


def _load_backfill_module():
    spec = importlib.util.spec_from_file_location(
        "backfill_decisions", ROOT / "scripts" / "backfill_decisions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_task_json(tasks_dir: Path, task_id: str, task: dict):
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / f"{task_id}.json").write_text(
        json.dumps(task, ensure_ascii=False), encoding="utf-8")


class TestBackfill:
    def _run(self, module, tmp_path, tasks_payload: dict):
        tasks_dir = tmp_path / "tasks"
        for tid, payload in tasks_payload.items():
            # 仅首次落盘：第二次运行复用已回填文件，验证真实幂等语义
            if not (tasks_dir / f"{tid}.json").exists():
                _write_task_json(tasks_dir, tid, {"task_id": tid, "status": "completed", **payload})
        module.TASKS_DIR = tasks_dir
        module.REPORT_FILE = tmp_path / "_backfill_report.json"
        assert module.main() == 0
        report = json.loads(module.REPORT_FILE.read_text(encoding="utf-8"))
        loaded = {tid: json.loads((tasks_dir / f"{tid}.json").read_text(encoding="utf-8"))
                  for tid in tasks_payload}
        return report, loaded

    def test_prefers_user_summary_and_tags_backfill_source(self, tmp_path):
        module = _load_backfill_module()
        report, loaded = self._run(module, tmp_path, {
            "t1": {
                "summary": "## 二、主要结论\n1. 自动生成版结论（旧）",
                "user_summary": SUMMARY_WITH_DECISIONS,
                "title": "会议一",
            },
        })
        decisions = loaded["t1"]["decisions"]
        assert report["backfilled"] == 1 and report["decisions_added"] == 3
        assert [d["text"] for d in decisions][:2] == ["项目采用方案A推进", "预算需财务复核"]
        assert all(d["source"] == "backfill" for d in decisions)
        assert loaded["t1"]["decisions_backfilled_at"]

    def test_idempotent_second_run_all_skip(self, tmp_path):
        """AC-7（回填幂等）：连跑两次，第二次零写入、无失败，计数互恰。"""
        module = _load_backfill_module()
        payload = {"t1": {"summary": SUMMARY_WITH_DECISIONS, "title": "A"},
                   "t2": {"summary": SUMMARY_NEGATIVE, "title": "B"}}
        report1, _ = self._run(module, tmp_path, payload)
        assert report1["backfilled"] == 1 and report1["marked_empty"] == 1
        files1 = {f.name: f.read_text(encoding="utf-8")
                  for f in (tmp_path / "tasks").glob("*.json")}

        report2, files2dict = self._run(module, tmp_path, payload)
        assert report2["backfilled"] == 0 and report2["marked_empty"] == 0
        assert report2["skipped_has_decisions"] == 1  # t1 已有 decisions
        assert report2["skipped_already_backfilled"] == 1  # t2 有 marker
        assert report2["failed"] == []
        files2 = {f.name: f.read_text(encoding="utf-8")
                  for f in (tmp_path / "tasks").glob("*.json")}
        assert files1 == files2

    def test_parse_failure_reported_without_marker(self, tmp_path):
        """解析降级任务：计入 failed + 原因，不写标记（修正后可重跑）。"""
        module = _load_backfill_module()
        report, loaded = self._run(module, tmp_path, {
            "t1": {"summary": "这不是纪要", "title": "坏格式"},
        })
        assert report["backfilled"] == 0 and report["failure_count"] == 1
        assert report["failed"][0]["task_id"] == "t1"
        assert "decisions" not in loaded["t1"]
        assert "decisions_backfilled_at" not in loaded["t1"]

    def test_legacy_no_decisions_key_tolerated(self, tmp_path):
        """AC-9（回填）：无 decisions 字段的旧任务 JSON 正常处理不报错。"""
        module = _load_backfill_module()
        report, _ = self._run(module, tmp_path, {
            "t1": {"summary": "## 二、主要结论\n1. 存量结论", "title": "旧任务"},
        })
        assert report["backfilled"] == 1 and report["failed"] == []
