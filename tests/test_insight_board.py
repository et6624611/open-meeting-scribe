"""
tests/test_insight_board.py — 洞察板 HTML 产物引擎与端点单测
Insight Board (HTML artifact) engine & endpoint unit tests

「洞察共创 · 会话驱动（HTML 产物版）」：板是一份 AI 直出的自包含 HTML，
覆盖 / Covers:
1. sanitize_board_html：script/on*/危险 URL 剥离、style/svg 保留、剥离项计数
2. board_html_save/load：revision 自增、读写往返、非法输入不落盘、目录不存在自动建
3. invoke_revise_board：读写双语义（不带 html 读基线 / 带 html 落盘）
4. GET /api/insights/board/{task_id}：返回 {html, revision, updated_at}
5. board_html_meta / ?meta=1：只回版本不回正文（洞察 Tab 轮询比对版用）

旧 Board Spec v0.3 的校验器/ops 合并/run_board_analysis 用例已随契约退役删除
（core/insight_board.py 中对应代码保留供追溯，不再被测）。
"""

import pytest
from fastapi.testclient import TestClient

from app.server import app
from core import insight_board as ib


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tmp_board_dir(tmp_path, monkeypatch):
    """把板存储目录指向临时路径，隔离真实 data/tasks / Point board storage at a temp dir."""
    d = tmp_path / "tasks"
    d.mkdir()
    monkeypatch.setattr(ib, "BOARD_TASKS_DIR", d)
    return d


# ============================================================
# 1. 安全清洗
# ============================================================

class TestSanitize:
    def test_strips_script_event_and_dangerous_url(self):
        src = ('<div onclick="evil()"><script>alert(1)</script>'
               '<a href="javascript:x()">l</a><iframe src="u"></iframe></div>')
        out, removed = ib.sanitize_board_html(src)
        assert "<script" not in out and "onclick" not in out
        assert "javascript:" not in out and "<iframe" not in out
        assert any("script" in r for r in removed)
        assert any("on*" in r for r in removed)

    def test_keeps_style_and_inline_svg(self):
        src = '<style>.a{color:red}</style><svg viewBox="0 0 8 8"><rect width="8" height="8"/></svg>'
        out, removed = ib.sanitize_board_html(src)
        assert "<style>" in out and "<svg" in out and "<rect" in out
        assert removed == []

    def test_seek_anchor_preserved(self):
        src = '<a data-seek-ms="84000">跳到 1:24</a>'
        out, _ = ib.sanitize_board_html(src)
        assert 'data-seek-ms="84000"' in out

    def test_strips_global_css_and_doc_wrappers_keeps_component_rules(self):
        # 主题污染根因：AI 吐整份文档 + :root 硬编码浅色令牌；应剥除全局块、保留组件样式
        src = ('<!DOCTYPE html><html><head><style>'
               ':root{--surface:#fff;--surface-alt:#f7f8fa} *{box-sizing:border-box}'
               'body{background:var(--surface-alt)} .card{color:var(--fg)}'
               '</style></head><body><div class="card">hi</div></body></html>')
        out, removed = ib.sanitize_board_html(src)
        assert ':root' not in out and 'box-sizing' not in out
        assert 'body{' not in out.replace(' ', '')
        assert '.card{color:var(--fg)}' in out.replace(' ', '')
        assert 'DOCTYPE' not in out and '<body>' not in out
        assert any(r.startswith('css:') for r in removed)


# ============================================================
# 2. 落盘与读取
# ============================================================

class TestSaveLoad:
    def test_first_save_creates_and_returns_rev1(self, tmp_board_dir):
        res = ib.board_html_save("t-1", "<p>初版</p>")
        assert res["ok"] is True and res["revision"] == 1
        loaded = ib.board_html_load("t-1")
        assert loaded["html"] == "<p>初版</p>" and loaded["revision"] == 1
        assert loaded["updated_at"]

    def test_second_save_increments_revision(self, tmp_board_dir):
        ib.board_html_save("t-1", "<p>v1</p>")
        res = ib.board_html_save("t-1", "<p>v2</p>")
        assert res["revision"] == 2
        assert ib.board_html_load("t-1")["html"] == "<p>v2</p>"

    def test_empty_html_not_saved(self, tmp_board_dir):
        assert ib.board_html_save("t-1", "   ")["ok"] is False
        assert ib.board_html_load("t-1") is None

    def test_purely_unsafe_html_empty_after_sanitize(self, tmp_board_dir):
        res = ib.board_html_save("t-1", "<script>x</script>")
        assert res["ok"] is False and res["error"] == "html_empty_after_sanitize"
        assert ib.board_html_load("t-1") is None

    def test_over_cap_rejected(self, tmp_board_dir):
        big = "<p>" + "x" * (ib.BOARD_HTML_CAP + 10) + "</p>"
        assert ib.board_html_save("t-1", big)["ok"] is False

    def test_traversal_task_id_rejected(self, tmp_board_dir):
        assert ib.board_html_save("../evil", "<p>x</p>")["ok"] is False
        assert ib.board_html_load("../evil") is None

    def test_load_absent_returns_none(self, tmp_board_dir):
        assert ib.board_html_load("nope") is None


# ============================================================
# 2b. 单节补丁（按 data-ib-id 只替那一节）
# ============================================================

_TWO_SEC = ('<section data-ib-id="s1" data-ib-title="甲"><h2>甲</h2></section>'
            '<section data-ib-id="s2" data-ib-title="乙"><h2>乙</h2></section>')


class TestSaveSection:
    def test_replaces_only_target_section(self, tmp_board_dir):
        ib.board_html_save("t-1", _TWO_SEC)
        before = ib.board_html_load("t-1")["html"]
        res = ib.board_html_save_section("t-1", "s1", '<section data-ib-id="s1"><h2>甲改</h2></section>')
        assert res["ok"] is True and res["revision"] == 2
        after = ib.board_html_load("t-1")["html"]
        # 目标节已变，另一节逐字节不变
        assert "甲改" in after and "<h2>甲</h2>" not in after
        assert '<section data-ib-id="s2" data-ib-title="乙"><h2>乙</h2></section>' in after
        assert before != after

    def test_normalizes_missing_id(self, tmp_board_dir):
        ib.board_html_save("t-1", _TWO_SEC)
        # 新节未带 data-ib-id → 归一补回，保证下次仍可寻址
        res = ib.board_html_save_section("t-1", "s2", "<section><h2>乙新</h2></section>")
        assert res["ok"] is True
        assert 'data-ib-id="s2"' in ib.board_html_load("t-1")["html"]

    def test_section_not_found(self, tmp_board_dir):
        ib.board_html_save("t-1", _TWO_SEC)
        res = ib.board_html_save_section("t-1", "s9", "<section data-ib-id=\"s9\">x</section>")
        assert res["ok"] is False and res["error"] == "section_not_found"

    def test_no_board_errors(self, tmp_board_dir):
        res = ib.board_html_save_section("t-1", "s1", "<section data-ib-id=\"s1\">x</section>")
        assert res["ok"] is False and res["error"] == "no_board"

    def test_invalid_section_id_rejected(self, tmp_board_dir):
        ib.board_html_save("t-1", _TWO_SEC)
        assert ib.board_html_save_section("t-1", "../x", "<section>x</section>")["ok"] is False


# ============================================================
# 3. 工具唯一实现 invoke_revise_board（读写双语义）
# ============================================================

class TestInvokeReviseBoard:
    def test_read_without_html_returns_baseline(self, tmp_board_dir):
        ib.board_html_save("t-1", "<p>base</p>")
        res = ib.invoke_revise_board("t-1", {})
        assert res["ok"] is True and res["html"] == "<p>base</p>" and res["revision"] == 1

    def test_read_absent_board_hint(self, tmp_board_dir):
        res = ib.invoke_revise_board("t-1", {})
        assert res["ok"] is True and res["html"] is None and res["revision"] == 0

    def test_write_html_saves_new_revision(self, tmp_board_dir):
        res = ib.invoke_revise_board("t-1", {"html": "<p>new</p>"})
        assert res["ok"] is True and res["revision"] == 1
        assert ib.board_html_load("t-1")["html"] == "<p>new</p>"


# ============================================================
# 4. GET 端点
# ============================================================

class TestGetBoardEndpoint:
    def test_absent_board_returns_null_html(self, client):
        r = client.get("/api/insights/board/ghost-task-no-board")
        assert r.status_code == 200
        body = r.json()
        assert body["html"] is None and body["revision"] == 0

    def test_endpoint_contract_shape(self, client):
        r = client.get("/api/insights/board/x")
        assert set(r.json()) == {"html", "revision", "updated_at"}


# ============================================================
# 5. 版本探测（board_html_meta / ?meta=1）
#    洞察板自动同步的“版本通道”：轮询只花几十字节就能发现别的窗口写了新板
# ============================================================

class TestBoardMeta:
    def test_absent_board_meta_zero_not_exists(self, tmp_board_dir):
        m = ib.board_html_meta("t-1")
        assert m == {"revision": 0, "updated_at": None, "exists": False}

    def test_meta_tracks_revision_without_reading_html(self, tmp_board_dir):
        ib.board_html_save("t-1", "<p>v1</p>")
        m = ib.board_html_meta("t-1")
        assert m["revision"] == 1 and m["exists"] is True and m["updated_at"]
        assert "html" not in m  # 探测不搬正文
        ib.board_html_save("t-1", "<p>v2</p>")
        assert ib.board_html_meta("t-1")["revision"] == 2

    def test_invalid_task_id_returns_none(self, tmp_board_dir):
        assert ib.board_html_meta("../evil") is None

    def test_endpoint_meta_mode_shape_without_html(self, client, tmp_board_dir):
        ib.board_html_save("t-meta", "<p>正文不应出现</p>")
        r = client.get("/api/insights/board/t-meta", params={"meta": "1"})
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"revision", "updated_at", "exists"}
        assert body["revision"] == 1 and body["exists"] is True

    def test_endpoint_without_meta_returns_body(self, client, tmp_board_dir):
        ib.board_html_save("t-meta", "<p>正文</p>")
        body = client.get("/api/insights/board/t-meta").json()
        assert "<p>正文</p>" in body["html"] and body["revision"] == 1
