"""
tests/test_insight_board.py — 单份 Markdown 洞察板引擎与端点单测

新契约：一场会议固定一份 data/tasks/{task_id}.insight.md。
覆盖 front-matter、安全清洗、revision 乐观锁、复述/文字墙防线、
会话工具读写、HTTP 端点、旧 HTML 自动迁移，以及已退役的多板接口。
"""

import json

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
    """把板存储目录指向临时路径，隔离真实 data/tasks。"""
    d = tmp_path / "tasks"
    d.mkdir()
    monkeypatch.setattr(ib, "BOARD_TASKS_DIR", d)
    return d


def _solution_section(sec_id: str, title: str, *, visual: bool = True) -> str:
    diagram = (
        "```mermaid\n"
        "flowchart LR\n"
        "  A[人工同步] --> B[CDC 捕获]\n"
        "  B --> C[事件总线]\n"
        "```"
        if visual else ""
    )
    return f"""<!-- section-id: {sec_id} section-title: {title} -->
## {title}

困境：人工同步造成数据延迟与口径漂移。

{diagram}

外部最优解法：采用 CDC 订阅变更，经事件总线推送并由消费端幂等处理。
落地步骤：先对齐字段映射，再上线消费端与对账作业。
取舍：引入中间件成本，换取更低耦合与更高时效。"""


_SOLUTION_BOARD = (
    _solution_section("s1", "执行数据实时回传")
    + "\n\n"
    + _solution_section("s2", "历史单据迁移连续性")
)
_TEXT_WALL_BOARD = (
    _solution_section("s1", "审核阻塞", visual=False)
    + "\n\n"
    + _solution_section("s2", "成本畸高", visual=False)
)
_RECAP_BOARD = """
<!-- section-id: s1 section-title: 会议全景 -->
## 会议全景

- 待确认决策：5
- 议题归类：4
- 决策事项：4

<!-- section-id: s2 section-title: 决策清单 -->
## 决策清单

- DC-1 同步口径以某字段为关键区分维度。依据：说话人1 03:22。
- DC-2 控制主体明确，执行数据需要反向回传。依据：说话人2 12:45。

<!-- section-id: s3 section-title: 议题归类 -->
## 议题归类

- 议题1 数据同步与维度对齐
- 议题2 权责与技术实现

<!-- section-id: s4 section-title: 待办追踪 -->
## 待办追踪

- Speaker 3 整理字段字典，截止 10 月 3 日。
- Speaker 4 组织功能说明会，截止 10 月 7 日。
"""


# ============================================================
# 1. Front-matter 与 Markdown 安全清洗
# ============================================================

class TestFrontMatter:
    def test_parse_typed_values_and_body(self):
        meta, body = ib.parse_front_matter(
            '---\nboard_id: main\ntitle: "供应链: 洞察"\nrevision: 7\n---\n# 正文\n'
        )
        assert meta == {"board_id": "main", "title": "供应链: 洞察", "revision": 7}
        assert body == "# 正文\n"

    def test_without_front_matter_returns_original(self):
        assert ib.parse_front_matter("# 正文") == ({}, "# 正文")

    def test_dump_round_trip_standard_fields(self):
        raw = ib.dump_front_matter(
            {"board_id": "main", "title": "主看板", "revision": 3,
             "updated_at": 123, "migrated_from": "html"},
            "## 正文",
        )
        meta, body = ib.parse_front_matter(raw)
        assert meta == {"board_id": "main", "title": "主看板", "revision": 3, "updated_at": 123}
        assert body == "## 正文"
        assert "migrated_from" not in raw


class TestSanitizeMarkdown:
    def test_strips_raw_html_and_dangerous_markdown_url(self):
        src = (
            "# 标题\n<script>alert(1)</script>\n"
            "<div onclick=\"evil()\">正文保留</div>\n"
            "[危险链接](javascript:alert(1))"
        )
        out, removed = ib.sanitize_board_md(src)
        assert "<script" not in out and "<div" not in out
        assert "onclick" not in out and "javascript:" not in out
        assert "正文保留" in out
        assert any(item.startswith("html-tags-stripped") for item in removed)
        assert any(item.startswith("dangerous-url") for item in removed)

    def test_preserves_section_anchor_seek_anchor_and_br(self):
        src = (
            "<!-- section-id: s1 section-title: 审核阻塞 -->\n"
            "## 审核阻塞\n"
            '<a data-seek-ms="84000">跳到 1:24</a><br>\n'
            "正文"
        )
        out, _ = ib.sanitize_board_md(src)
        assert "<!-- section-id: s1 section-title: 审核阻塞 -->" in out
        assert '<a data-seek-ms="84000">跳到 1:24</a>' in out
        assert "<br>" in out

    def test_seek_anchor_strips_event_and_dangerous_href(self):
        src = '<a href="javascript:evil()" data-seek-ms="84000" onclick="evil()">跳到 1:24</a>'
        out, removed = ib.sanitize_board_md(src)
        assert 'data-seek-ms="84000"' in out and 'href="#"' in out
        assert "onclick" not in out and "javascript:" not in out
        assert any(item.startswith("on*") for item in removed)

    def test_non_anchor_html_comment_is_removed(self):
        out, _ = ib.sanitize_board_md("正文<!-- secret -->\n<!-- section-id: s1 -->")
        assert "secret" not in out
        assert "<!-- section-id: s1 -->" in out


# ============================================================
# 2. 单文件落盘、读取与 revision 乐观锁
# ============================================================

class TestMarkdownSaveLoad:
    def test_first_save_creates_single_markdown_file(self, tmp_board_dir):
        res = ib.board_md_save("t-1", _SOLUTION_BOARD)
        assert res["ok"] is True and res["revision"] == 1 and res["board_id"] == "main"
        assert (tmp_board_dir / "t-1.insight.md").exists()
        assert not list(tmp_board_dir.glob("t-1.board*.html"))
        loaded = ib.board_md_load("t-1")
        assert loaded["markdown"] == _SOLUTION_BOARD.strip()
        assert loaded["revision"] == 1 and loaded["updated_at"]

    def test_disk_front_matter_is_not_duplicated_in_body(self, tmp_board_dir):
        ib.board_md_save("t-1", _SOLUTION_BOARD)
        raw = (tmp_board_dir / "t-1.insight.md").read_text(encoding="utf-8")
        assert raw.startswith("---\nboard_id: main\n")
        assert "revision: 1" in raw and "updated_at:" in raw
        loaded = ib.board_md_load("t-1")
        assert not loaded["markdown"].startswith("---")
        assert loaded["meta"]["revision"] == 1

    def test_second_save_increments_revision(self, tmp_board_dir):
        ib.board_md_save("t-1", _SOLUTION_BOARD)
        updated = _SOLUTION_BOARD.replace("CDC 订阅变更", "变更数据捕获订阅")
        res = ib.board_md_save("t-1", updated)
        assert res["revision"] == 2
        assert ib.board_md_load("t-1")["markdown"] == updated.strip()

    def test_front_matter_title_kept_but_revision_regenerated(self, tmp_board_dir):
        src = "---\ntitle: 供应链专项\nrevision: 99\n---\n" + _SOLUTION_BOARD
        res = ib.board_md_save("t-1", src)
        loaded = ib.board_md_load("t-1")
        assert res["revision"] == 1
        assert loaded["title"] == "供应链专项" and loaded["revision"] == 1
        assert loaded["markdown"] == _SOLUTION_BOARD.strip()

    def test_h1_supplies_default_title(self, tmp_board_dir):
        ib.board_md_save("t-1", "# 供应链洞察\n\n" + _SOLUTION_BOARD)
        assert ib.board_md_load("t-1")["title"] == "供应链洞察"

    def test_empty_markdown_not_saved(self, tmp_board_dir):
        assert ib.board_md_save("t-1", "   ")["error"] == "empty_markdown"
        assert ib.board_md_load("t-1") is None

    def test_empty_after_sanitize_not_saved(self, tmp_board_dir):
        res = ib.board_md_save("t-1", "<div><script></script></div>", content_floor=False)
        assert res["ok"] is False and res["error"] == "markdown_empty_after_sanitize"
        assert ib.board_md_load("t-1") is None

    def test_over_cap_rejected(self, tmp_board_dir):
        big = "x" * (ib.BOARD_MD_CAP + 1)
        assert ib.board_md_save("t-1", big, content_floor=False)["ok"] is False

    def test_traversal_task_id_rejected(self, tmp_board_dir):
        assert ib.board_md_save("../evil", "x", content_floor=False)["error"] == "invalid_task_id"
        assert ib.board_md_load("../evil") is None
        assert ib.board_md_meta("../evil")["exists"] is False

    def test_load_absent_returns_none(self, tmp_board_dir):
        assert ib.board_md_load("nope") is None

    def test_stale_baseline_does_not_overwrite(self, tmp_board_dir):
        ib.board_md_save("t-1", _SOLUTION_BOARD)
        updated = _SOLUTION_BOARD.replace("CDC", "变更捕获")
        res = ib.board_md_save("t-1", updated, expected_revision=99)
        assert res["ok"] is False and res["error"] == "stale_baseline"
        assert res["current_revision"] == 1
        assert ib.board_md_load("t-1")["markdown"] == _SOLUTION_BOARD.strip()
        ok = ib.board_md_save("t-1", updated, expected_revision=1)
        assert ok["ok"] is True and ok["revision"] == 2

    def test_invalid_expected_revision_rejected(self, tmp_board_dir):
        res = ib.board_md_save("t-1", _SOLUTION_BOARD, expected_revision="abc")
        assert res["ok"] is False and res["error"] == "invalid_expected_revision"
        assert ib.board_md_load("t-1") is None


class TestDeprecatedHtmlFacade:
    def test_legacy_names_forward_to_markdown(self, tmp_board_dir):
        res = ib.board_html_save("t-1", "# 兼容入口")
        assert res["ok"] is True
        loaded = ib.board_html_load("t-1")
        assert loaded["markdown"] == loaded["html"] == "# 兼容入口"
        assert (tmp_board_dir / "t-1.insight.md").exists()

    def test_multi_board_and_section_writes_are_deprecated(self, tmp_board_dir):
        assert ib.invoke_create_board("t-1", {"title": "专项"})["error"] == "multi_board_deprecated"
        assert ib.board_html_save_section("t-1", "s1", "x")["error"] == "section_save_deprecated"

    def test_manifest_is_fixed_single_main(self, tmp_board_dir):
        ib.board_md_save("t-1", _SOLUTION_BOARD)
        manifest = ib.boards_manifest("t-1")
        assert manifest["default_board_id"] == "main"
        assert [b["board_id"] for b in manifest["boards"]] == ["main"]
        assert manifest["boards"][0]["exists"] is True


# ============================================================
# 3. 内容底线：复述拒收与文字墙拒收
# ============================================================

class TestRecapFloor:
    def test_recap_board_detected(self):
        reasons = ib.detect_recap_floor(_RECAP_BOARD)
        assert any("节标题" in reason for reason in reasons)
        assert any("DC" in reason for reason in reasons)

    def test_solution_board_passes(self):
        assert ib.detect_recap_floor(_SOLUTION_BOARD) == []

    def test_single_weak_signal_does_not_reject(self):
        md = _solution_section("s1", "决策追踪")
        assert ib.detect_recap_floor(md) == []

    def test_solution_flavoured_title_exempt(self):
        md = _solution_section("s1", "风险与解法对照表")
        assert ib.detect_recap_floor(md) == []

    def test_recap_save_rejected_and_keeps_old_board(self, tmp_board_dir):
        ib.board_md_save("t-1", _SOLUTION_BOARD)
        res = ib.board_md_save("t-1", _RECAP_BOARD)
        assert res["ok"] is False and res["error"] == "board_is_recap"
        assert res["reasons"] and res["guidance"]
        assert ib.board_md_meta("t-1")["revision"] == 1
        assert ib.board_md_load("t-1")["markdown"] == _SOLUTION_BOARD.strip()

    def test_recap_rejection_surfaced_via_tool(self, tmp_board_dir):
        res = ib.invoke_revise_board("t-1", {"markdown": _RECAP_BOARD})
        assert res["ok"] is False and res["error"] == "board_is_recap"
        assert "最优解法" in res["guidance"]


class TestTextWallFloor:
    def test_counts_sections_and_mermaid_visuals(self):
        assert ib.detect_text_wall(_TEXT_WALL_BOARD) == (2, 0)
        assert ib.detect_text_wall(_SOLUTION_BOARD) == (2, 2)

    def test_single_section_without_visual_rejected_on_save(self, tmp_board_dir):
        res = ib.board_md_save("t-1", _solution_section("s1", "只有文字", visual=False))
        assert res["ok"] is False and res["error"] == "board_is_text_wall"
        assert res["reasons"] and "主视觉" in res["guidance"]
        assert ib.board_md_load("t-1") is None

    def test_mermaid_fence_counts_as_visual(self, tmp_board_dir):
        assert ib.board_md_save("t-1", _solution_section("s1", "有图"))["ok"] is True

    @pytest.mark.parametrize("source", ["   ", "foo bar baz"])
    def test_empty_or_non_diagram_mermaid_rejected(self, tmp_board_dir, source):
        md = f"""<!-- section-id: s1 section-title: 伪图 -->
## 伪图

```mermaid
{source}
```

外部最优解法：采用事件驱动架构。"""
        res = ib.board_md_save("t-1", md)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"

    def test_multi_section_allows_one_without_visual(self, tmp_board_dir):
        two = _solution_section("s1", "有图") + "\n\n" + _solution_section("s2", "无图", visual=False)
        assert ib.board_md_save("t-1", two)["ok"] is True
        three = two + "\n\n" + _solution_section("s3", "仍无图", visual=False)
        res = ib.board_md_save("t-2", three)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"

    def test_data_uri_image_counts_but_relative_image_does_not(self):
        data_img = """<!-- section-id: s1 section-title: 图片 -->
## 图片
![架构](data:image/png;base64,iVBOR)"""
        relative_img = data_img.replace("data:image/png;base64,iVBOR", "a.png")
        table = """<!-- section-id: s1 section-title: 表格 -->
## 表格
| 项目 | 值 |
| --- | --- |
| 大表 | 1 |"""
        assert ib.detect_text_wall(data_img) == (1, 1)
        assert ib.detect_text_wall(relative_img) == (1, 0)
        assert ib.detect_text_wall(table) == (1, 0)

    def test_raw_svg_is_sanitized_and_does_not_pass_floor(self, tmp_board_dir):
        md = """<!-- section-id: s1 section-title: 内联 SVG -->
## 内联 SVG
<svg viewBox="0 0 10 10"><circle r="5"/></svg>
外部最优解法：采用事件驱动架构。"""
        res = ib.board_md_save("t-1", md)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"

    def test_text_wall_rejected_and_keeps_old_board(self, tmp_board_dir):
        ib.board_md_save("t-1", _SOLUTION_BOARD)
        res = ib.board_md_save("t-1", _TEXT_WALL_BOARD)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"
        assert ib.board_md_meta("t-1")["revision"] == 1
        assert ib.board_md_load("t-1")["markdown"] == _SOLUTION_BOARD.strip()

    def test_text_wall_surfaced_via_tool(self, tmp_board_dir):
        res = ib.invoke_revise_board("t-1", {"markdown": _TEXT_WALL_BOARD})
        assert res["ok"] is False and res["error"] == "board_is_text_wall"
        assert "主视觉" in res["guidance"]


# ============================================================
# 4. 会话工具：空参读、markdown 整板写
# ============================================================

class TestInvokeReviseBoard:
    def test_read_without_markdown_returns_baseline(self, tmp_board_dir):
        ib.board_md_save("t-1", _SOLUTION_BOARD)
        res = ib.invoke_revise_board("t-1", {})
        assert res["ok"] is True and res["markdown"] == _SOLUTION_BOARD.strip()
        assert res["revision"] == 1 and res["board_id"] == "main"
        assert "html" not in res

    def test_read_absent_board_hint(self, tmp_board_dir):
        res = ib.invoke_revise_board("t-1", {})
        assert res["ok"] is True and res["markdown"] is None and res["revision"] == 0

    def test_write_markdown_saves_new_revision(self, tmp_board_dir):
        res = ib.invoke_revise_board("t-1", {"markdown": _SOLUTION_BOARD, "expected_revision": 0})
        assert res["ok"] is True and res["revision"] == 1
        assert ib.board_md_load("t-1")["markdown"] == _SOLUTION_BOARD.strip()


# ============================================================
# 5. HTTP 端点：Markdown、固定单板、纯文本 raw
# ============================================================

class TestBoardEndpoints:
    def test_absent_board_returns_null_markdown(self, client, tmp_board_dir):
        r = client.get("/api/insights/board/ghost-task-no-board")
        assert r.status_code == 200
        assert r.json() == {
            "markdown": None, "revision": 0, "updated_at": None,
            "board_id": "main", "title": "主看板",
        }

    def test_get_board_contract_shape(self, client, tmp_board_dir):
        ib.board_md_save("t-get", _SOLUTION_BOARD)
        body = client.get("/api/insights/board/t-get").json()
        assert set(body) == {"markdown", "revision", "updated_at", "board_id", "title"}
        assert body["markdown"] == _SOLUTION_BOARD.strip() and body["revision"] == 1

    def test_meta_mode_excludes_body(self, client, tmp_board_dir):
        ib.board_md_save("t-meta", _SOLUTION_BOARD)
        body = client.get("/api/insights/board/t-meta", params={"meta": "1"}).json()
        assert set(body) == {"revision", "updated_at", "exists", "board_id", "title"}
        assert body["revision"] == 1 and body["exists"] is True

    def test_absent_meta_zero_not_exists(self, tmp_board_dir):
        meta = ib.board_md_meta("t-1")
        assert meta["revision"] == 0 and meta["updated_at"] is None and meta["exists"] is False

    def test_list_boards_is_fixed_single_main(self, client, tmp_board_dir):
        ib.board_md_save("t-list", _SOLUTION_BOARD)
        body = client.get("/api/insights/board/t-list/boards").json()
        assert body["default_board_id"] == "main"
        assert [b["board_id"] for b in body["boards"]] == ["main"]

    def test_create_board_returns_405(self, client, tmp_board_dir):
        r = client.post("/api/insights/board/t-create/boards", json={"title": "专项"})
        assert r.status_code == 405

    def test_raw_returns_plain_markdown_without_sandbox_csp(self, client, tmp_board_dir):
        ib.board_md_save("t-raw", _SOLUTION_BOARD)
        r = client.get("/api/insights/board/t-raw/raw")
        assert r.status_code == 200 and r.text == _SOLUTION_BOARD.strip()
        assert r.headers["content-type"].startswith("text/plain")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "no-store"
        assert "content-security-policy" not in r.headers

    def test_raw_revision_conflict_and_absent_404(self, client, tmp_board_dir):
        ib.board_md_save("t-raw2", _SOLUTION_BOARD)
        assert client.get("/api/insights/board/t-raw2/raw", params={"rev": "99"}).status_code == 409
        assert client.get("/api/insights/board/t-raw2/raw", params={"rev": "1"}).status_code == 200
        assert client.get("/api/insights/board/nope/raw").status_code == 404

    def test_open_points_at_single_board_viewer(self, client, monkeypatch, tmp_board_dir):
        seen = []
        monkeypatch.setattr("app.routers.insights.webbrowser.open", lambda url: seen.append(url) or True)
        ib.board_md_save("t-open", _SOLUTION_BOARD)
        r = client.post("/api/insights/board/t-open/open",
                        json={"board_id": "main", "raw_url": "http://evil.example/x"})
        assert r.status_code == 200 and r.json()["ok"] is True
        url = r.json()["url"]
        assert url.endswith("/board/t-open")
        assert "board_id" not in url and "evil.example" not in url and "/raw" not in url
        assert seen == [url]

    def test_realtime_messages_are_retired_noops(self, client, tmp_board_dir):
        assert client.get("/api/insights/messages/t-1").json() == {"messages": []}
        r = client.post("/api/insights/messages/t-1", json={"messages": [{"title": "旧"}]})
        assert r.json() == {"ok": True, "count": 0, "messages": []}


# ============================================================
# 6. 旧 HTML 自动迁移：单文件与多板都合并为 insight.md
# ============================================================

class TestLegacyMigration:
    def test_html_to_markdown_preserves_mermaid_and_seek_anchor(self):
        html = (
            "<h2>困境</h2><p>人工同步延迟</p>"
            "<pre class=\"ib-mermaid\">flowchart LR\n  A --> B</pre>"
            '<a data-seek-ms="84000">跳到 1:24</a>'
        )
        md = ib.html_to_markdown(html)
        assert "## 困境" in md
        assert "```mermaid\nflowchart LR\n  A --> B\n```" in md
        assert '<a data-seek-ms="84000">跳到 1:24</a>' in md

    def test_first_get_migrates_legacy_single_file(self, client, tmp_board_dir):
        (tmp_board_dir / "t-old.board.html").write_text(
            '<h2>旧板</h2><p>困境：人工同步</p>'
            '<pre>flowchart LR\n  A --> B</pre>'
            '<a data-seek-ms="84000">原话</a>',
            encoding="utf-8",
        )
        body = client.get("/api/insights/board/t-old").json()
        assert body["board_id"] == "main" and body["revision"] == 0
        assert "<!-- section-id: main section-title: 主看板 -->" in body["markdown"]
        assert "```mermaid" in body["markdown"]
        assert '<a data-seek-ms="84000">原话</a>' in body["markdown"]
        assert (tmp_board_dir / "t-old.insight.md").exists()
        assert ib.migrate_legacy_html_to_md("t-old") is False

    def test_multi_board_manifest_merged_into_one_file(self, tmp_board_dir):
        manifest = {
            "boards": [
                {"board_id": "main", "title": "主看板", "revision": 2, "updated_at": 100},
                {"board_id": "board-2", "title": "供应链专项", "revision": 5, "updated_at": 200},
            ]
        }
        (tmp_board_dir / "t-multi.boards.json").write_text(json.dumps(manifest), encoding="utf-8")
        (tmp_board_dir / "t-multi.board.main.html").write_text("<p>主板内容</p>", encoding="utf-8")
        (tmp_board_dir / "t-multi.board.board-2.html").write_text("<p>专项内容</p>", encoding="utf-8")
        assert ib.migrate_legacy_html_to_md("t-multi") is True
        loaded = ib.board_md_load("t-multi")
        assert loaded["revision"] == 5 and loaded["title"] == "供应链专项"
        assert "主板内容" in loaded["markdown"] and "专项内容" in loaded["markdown"]
        assert "<!-- section-id: main section-title: 主看板 -->" in loaded["markdown"]
        assert "<!-- section-id: board-2 section-title: 供应链专项 -->" in loaded["markdown"]
        assert (tmp_board_dir / "t-multi.insight.md").exists()

    def test_no_legacy_source_is_noop(self, tmp_board_dir):
        assert ib.migrate_legacy_html_to_md("none") is False
        assert not (tmp_board_dir / "none.insight.md").exists()
