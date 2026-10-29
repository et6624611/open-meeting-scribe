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
6. detect_recap_floor：会议复述型板整份拒收（board_is_recap），解法型板通过

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
    def test_keeps_script_style_link_meta_and_drops_escape_tags(self):
        # 版式归 CLI：script/style/link/meta 保留；仅容器级逃逸标签被剥
        src = ('<div onclick="evil()"><script>alert(1)</script>'
               '<link rel="stylesheet" href="a.css"><meta name="viewport">'
               '<a href="javascript:x()">l</a><iframe src="u"></iframe>'
               '<form action="/x"></form></div>')
        out, removed = ib.sanitize_board_html(src)
        assert "<script" in out and "<style" not in removed          # script 不再被剥
        assert "<iframe" not in out and "<form" not in out            # 容器级逃逸标签仍剥
        assert "onclick" not in out                                    # on* 仍剥（纵深防御）
        assert "javascript:" not in out                                # 危险 scheme 仍处理
        assert any("iframe" in r for r in removed)
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

    def test_doc_shell_and_global_css_preserved(self):
        # 【回归原始 HTML】剥壳已撤：doctype/html/head/body/:root 与硬编码色完整保留
        src = ('<!DOCTYPE html><html><head><style>'
               ':root{--surface:#fff} *{box-sizing:border-box}'
               'body{background:#123456} .card{color:var(--fg)}'
               '</style></head><body><div class="card">hi</div></body></html>')
        out, removed = ib.sanitize_board_html(src)
        assert 'DOCTYPE' in out and '<body>' in out and '</html>' in out
        assert ':root{--surface:#fff}' in out and 'box-sizing' in out
        assert 'background:#123456' in out
        # removed 里不得出现 doctype / css:* 项（旧剥壳会记这些）
        assert not any(r.startswith('css:') for r in removed)
        assert 'doctype' not in removed


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
        # 只剩容器级逃逸标签（script 已不剥）：iframe 被剔后空内容不落盘
        res = ib.board_html_save("t-1", "<iframe>x</iframe>")
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

_TWO_SEC = ('<section data-ib-id="s1" data-ib-title="甲"><h2>甲</h2>'
            '<div class="ib-visual"><div class="ib-flow"><div class="ib-node">x</div></div></div></section>'
            '<section data-ib-id="s2" data-ib-title="乙"><h2>乙</h2></section>')


class TestSaveSection:
    def test_replaces_only_target_section(self, tmp_board_dir):
        ib.board_html_save("t-1", _TWO_SEC)
        before = ib.board_html_load("t-1")["html"]
        res = ib.board_html_save_section(
            "t-1", "s1",
            '<section data-ib-id="s1"><h2>甲改</h2>'
            '<div class="ib-visual"><div class="ib-flow"><div class="ib-node">y</div></div></div></section>')
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
# 2c. 内容底线：会议复述型板拒收（board_is_recap）
# ============================================================

# 真实事故板的精简复刻：决策清单 + 议题归类 + 决策分工 + 风险罗列，零解法
_RECAP_BOARD = """
<section data-ib-id="s-overview" data-ib-title="会议全景">
  <div class="ib-card"><h3>某系统协同机制</h3>
  <div class="ib-stats">
    <div class="ib-stat"><span class="ib-stat-value">5</span><span class="ib-stat-label">待确认决策</span></div>
    <div class="ib-stat"><span class="ib-stat-value">4</span><span class="ib-stat-label">议题归类</span></div>
    <div class="ib-stat"><span class="ib-stat-value">4</span><span class="ib-stat-label">决策事项</span></div>
  </div></div>
</section>
<section data-ib-id="s-decisions" data-ib-title="决策流（待确认）">
  <div class="ib-card">
    <p><strong>DC-1</strong> 同步口径以某字段为关键区分维度</p>
    <p class="ib-muted">依据：说话人1 03:22；说话人2 12:45 提出一对一，但未确认命名</p>
    <p><strong>DC-2</strong> 控制主体明确，但执行数据需反向回传</p>
    <p class="ib-muted">依据：说话人1 18:10；说话人3 25:33 提问，未明确技术路径</p>
  </div>
</section>
<section data-ib-id="s-topics" data-ib-title="议题归类">
  <div class="ib-card"><p><strong>议题1</strong> 数据同步与维度对齐</p><p><strong>议题2</strong> 权责与技术实现</p></div>
</section>
<section data-ib-id="s-decisions" data-ib-title="决策追踪">
  <div class="ib-card"><ul>
    <li><strong>Speaker 3 / Speaker 4</strong>：整理字段字典，3 个工作日内共享 <span>截止 2026-10-03</span></li>
    <li><strong>Speaker 1 / Speaker 2</strong>：牵头组织功能说明会 <span>截止 2026-10-07</span></li>
  </ul></div>
</section>
<section data-ib-id="s-risks" data-ib-title="风险与未决">
  <div class="ib-card"><ul><li>技术路径未定</li><li>字段规范缺失</li></ul></div>
</section>
"""

# 合规板：困境 → 主视觉 → 外部解法 → 落地，不搬运会议记录
_SOLUTION_BOARD = """
<section data-ib-id="s1" data-ib-title="执行数据实时回传">
  <div class="ib-card">
    <h3>回传实时性与系统耦合的两难</h3>
    <div class="ib-visual"><div class="ib-flow">
      <div class="ib-node is-bad">报销单落库<small>人工表单</small></div>
      <div class="ib-arrow">→</div>
      <div class="ib-node is-new is-auto">CDC 捕获</div>
      <div class="ib-arrow">→</div>
      <div class="ib-node is-hub">事件总线</div>
      <div class="ib-arrow">→</div>
      <div class="ib-node is-good">预算幂等占用</div>
    </div></div>
    <p>会上在接口、读库、表单之间犹豫。本方案给出外部成熟实践。</p>
    <p><strong>外部最优解法：</strong>采用 CDC（变更数据捕获）订阅报销单表变更，经事件总线推送至预算服务，
       参考 Debezium + Kafka 的标准架构；预算侧以幂等消费维护累计占用，避免双写分布式事务。</p>
    <p><strong>落地步骤：</strong>第一周部署 CDC 连接器并对齐字段映射；第二周上线消费端与对账作业。
       <strong>取舍：</strong>引入中间件成本，但比读库方案耦合更低、比人工表单时效高一个数量级。</p>
  </div>
</section>
<section data-ib-id="s2" data-ib-title="历史单据迁移连续性">
  <div class="ib-card">
    <h3>年初至今累计占用如何初始化</h3>
    <div class="ib-visual"><div class="ib-flow is-stack">
      <div class="ib-node is-new">切换日汇总快照</div>
      <div class="ib-arrow is-down">→</div>
      <div class="ib-node is-new is-auto">账实核对</div>
      <div class="ib-arrow is-down">→</div>
      <div class="ib-node is-good">CDC 增量接管</div>
    </div></div>
    <p><strong>外部最优解法：</strong>以「快照 + 增量回放」双轨初始化——先静态导入切换日前的汇总快照，
       上线日做一次账实核对，之后 CDC 增量接管；这是财务系统切换的业界标准做法。</p>
    <p><strong>落地步骤：</strong>导出历史单据 → 按专项维度聚合 → 试算平衡 → 正式导入并冻结人工入口。</p>
  </div>
</section>
"""

# 文字墙板：内容是解法但零图形（真实事故形态：h3/p/ol/ul 堆叠）
_TEXT_WALL_BOARD = """
<section data-ib-id="s1" data-ib-title="审核阻塞">
  <h3>财务审核卡点导致仓库停摆</h3>
  <p>退货单未审导致库存无法回补。</p>
  <h4>外部最优解法：异常驱动审核</h4>
  <ol><li>字段继承自动比对过账</li><li>仓库有条件放行</li><li>SLA 超时升级</li></ol>
</section>
<section data-ib-id="s2" data-ib-title="成本畸高">
  <h3>暂估差异全压剩余库存</h3>
  <p>980kg 入库 979kg 领用，差异计入 1kg。</p>
  <h4>外部最优解法：标准成本法 + 差异账户</h4>
  <ol><li>标准成本卡</li><li>价格差异科目</li><li>阈值告警</li></ol>
</section>
"""


class TestRecapFloor:
    def test_recap_board_detected(self):
        reasons = ib.detect_recap_floor(_RECAP_BOARD)
        assert reasons  # 非空 = 应拒收
        assert any("节标题" in r for r in reasons)
        assert any("DC" in r for r in reasons)

    def test_solution_board_passes(self):
        assert ib.detect_recap_floor(_SOLUTION_BOARD) == []

    def test_single_weak_signal_does_not_reject(self):
        # 仅一节旧标题未改、正文已是解法：单一弱信号放行，避免误伤
        html = ('<section data-ib-id="s1" data-ib-title="决策追踪">'
                '<div><h3>用 CDC 事件流替代人工跟进</h3>'
                '<p>解法：接入变更数据捕获，异常事件自动派单，SLA 状态由看板实时呈现。</p></div></section>')
        assert ib.detect_recap_floor(html) == []

    def test_solution_flavoured_title_exempt(self):
        html = ('<section data-ib-id="s1" data-ib-title="风险与解法对照表">'
                '<div><p>风险一……对应解法：熔断 + 降级队列。</p></div></section>')
        assert ib.detect_recap_floor(html) == []

    def test_recap_save_rejected_and_keeps_old_board(self, tmp_board_dir):
        # 先存一块合规矩的旧版
        ib.board_html_save("t-1", _SOLUTION_BOARD)
        res = ib.board_html_save("t-1", _RECAP_BOARD)
        assert res["ok"] is False and res["error"] == "board_is_recap"
        assert res["reasons"] and res["guidance"]
        # 旧板保持不动（原子语义：拒收即不写盘、不增 revision）
        meta = ib.board_html_meta("t-1")
        assert meta["revision"] == 1
        loaded = ib.board_html_load("t-1")
        assert "CDC" in loaded["html"]

    def test_recap_rejection_surfaced_via_tool(self, tmp_board_dir):
        res = ib.invoke_revise_board("t-1", {"html": _RECAP_BOARD})
        assert res["ok"] is False and res["error"] == "board_is_recap"
        assert isinstance(res["reasons"], list) and res["reasons"]
        assert "最优解法" in res["guidance"]


# ============================================================
# 2d. 图形化底线：纯文字墙拒收（board_is_text_wall）
# ============================================================

class TestTextWallFloor:
    def test_counts_sections_and_visuals(self):
        assert ib.detect_text_wall(_TEXT_WALL_BOARD) == (2, 0)
        assert ib.detect_text_wall(_SOLUTION_BOARD) == (2, 2)

    def test_non_section_fragment_not_blocked(self):
        # 非节式自由片段（如 <p> 通知）不参与图形判定
        assert ib.detect_text_wall("<p>板已刷新，请展开查看</p>") == (0, 0)

    def test_single_section_without_visual_rejected_on_save(self, tmp_board_dir):
        one = '<section data-ib-id="s1"><h3>标题</h3><p>只有文字</p></section>'
        res = ib.board_html_save("t-1", one)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"
        assert res["reasons"] and "主视觉" in res["guidance"]
        assert ib.board_html_load("t-1") is None

    def test_mermaid_pre_counts_as_visual(self, tmp_board_dir):
        html = ('<section data-ib-id="s1"><h3>t</h3><div class="ib-visual">'
                '<pre class="ib-mermaid">flowchart LR\n  A -->|标签| B</pre>'
                '</div><p>外部最优解法：……</p></section>')
        assert ib.board_html_save("t-1", html)["ok"] is True

    def test_empty_mermaid_pre_rejected(self, tmp_board_dir):
        html = ('<section data-ib-id="s1"><h3>t</h3><div class="ib-visual">'
                '<pre class="ib-mermaid">   </pre></div><p>外部最优解法：……</p></section>')
        res = ib.board_html_save("t-1", html)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"

    def test_non_whitelist_mermaid_pre_rejected(self, tmp_board_dir):
        # 首词非图类型关键字（如模型写了段说明文字）不计主视觉
        html = ('<section data-ib-id="s1"><h3>t</h3><div class="ib-visual">'
                '<pre class="ib-mermaid">foo bar baz</pre></div>'
                '<p>外部最优解法：……</p></section>')
        res = ib.board_html_save("t-1", html)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"

    def test_multi_section_allows_one_without_visual(self, tmp_board_dir):
        # n=2：允许恰好 1 节无图（容错）；n=3 仅 1 图则拒收
        two = ('<section data-ib-id="s1"><div class="ib-visual"><div class="ib-flow">'
               '<div class="ib-node">a</div></div></div></section>'
               '<section data-ib-id="s2"><p>此节确不适合成图</p></section>')
        assert ib.board_html_save("t-1", two)["ok"] is True

        three = two + '<section data-ib-id="s3"><p>第三节也没图</p></section>'
        res = ib.board_html_save("t-2", three)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"

    def test_inline_svg_counts_as_visual(self, tmp_board_dir):
        html = ('<section data-ib-id="s1"><div class="ib-visual">'
                '<svg viewBox="0 0 10 10"><circle r="5"/></svg></div></section>')
        assert ib.board_html_save("t-1", html)["ok"] is True

    def test_text_wall_rejected_and_keeps_old_board(self, tmp_board_dir):
        ib.board_html_save("t-1", _SOLUTION_BOARD)
        res = ib.board_html_save("t-1", _TEXT_WALL_BOARD)
        assert res["ok"] is False and res["error"] == "board_is_text_wall"
        # 旧板保留，revision 不前进
        assert ib.board_html_meta("t-1")["revision"] == 1
        assert "ib-flow" in ib.board_html_load("t-1")["html"]

    def test_text_wall_surfaced_via_tool(self, tmp_board_dir):
        res = ib.invoke_revise_board("t-1", {"html": _TEXT_WALL_BOARD})
        assert res["ok"] is False and res["error"] == "board_is_text_wall"
        assert "主视觉" in res["guidance"]


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
        # 多板后返回体新增 board_id/title 寻址字段
        assert {"html", "revision", "updated_at", "board_id", "title"} == set(r.json())


# ============================================================
# 5. 版本探测（board_html_meta / ?meta=1）
#    洞察板自动同步的“版本通道”：轮询只花几十字节就能发现别的窗口写了新板
# ============================================================

class TestBoardMeta:
    def test_absent_board_meta_zero_not_exists(self, tmp_board_dir):
        m = ib.board_html_meta("t-1")
        # 多板口径：meta 额外携带 boards[]/default_board_id/board_id
        assert m["revision"] == 0 and m["updated_at"] is None and m["exists"] is False

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
        assert "html" not in body
        assert {"revision", "updated_at", "exists", "board_id", "boards", "default_board_id"} == set(body)
        assert body["revision"] == 1 and body["exists"] is True

    def test_endpoint_without_meta_returns_body(self, client, tmp_board_dir):
        ib.board_html_save("t-meta", "<p>正文</p>")
        body = client.get("/api/insights/board/t-meta").json()
        assert "<p>正文</p>" in body["html"] and body["revision"] == 1


# ============================================================
# 6. 多板：manifest / 建板权 / 版本协议（R3 + R2）
# ============================================================

class TestMultiBoardManifest:
    def test_first_save_targets_default_main(self, tmp_board_dir):
        res = ib.board_html_save("t-1", "<p>v</p>")
        assert res["ok"] is True and res["board_id"] == "main"
        m = ib.boards_manifest("t-1")
        assert m["default_board_id"] == "main"
        assert [b["board_id"] for b in m["boards"]] == ["main"]
        assert m["boards"][0]["exists"] is True

    def test_legacy_single_file_migrated_to_main(self, tmp_board_dir):
        # 存量旧单文件板 → 首次读取就地重命名为 main
        (tmp_board_dir / "t-old.board.html").write_text("<p>旧板</p>", encoding="utf-8")
        loaded = ib.board_html_load("t-old")
        assert loaded and loaded["html"] == "<p>旧板</p>" and loaded["board_id"] == "main"
        assert not (tmp_board_dir / "t-old.board.html").exists()
        assert (tmp_board_dir / "t-old.board.main.html").exists()
        assert (tmp_board_dir / "t-old.boards.json").exists()

    def test_unknown_board_id_rejected_never_implicit_create(self, tmp_board_dir):
        ib.board_html_save("t-1", "<p>main</p>")
        res = ib.board_html_save("t-1", "<p>new</p>", board_id="ghost")
        assert res["ok"] is False and res["error"] == "unknown_board_id"
        # 不建板 + 不产生文件 + 回执列出候选板
        assert not (tmp_board_dir / "t-1.board.ghost.html").exists()
        assert [b["board_id"] for b in res["boards"]] == ["main"]
        assert res["hint"]

    def test_save_section_unknown_board_rejected(self, tmp_board_dir):
        ib.board_html_save("t-1", '<section data-ib-id="s1"><svg/></section>')
        res = ib.board_html_save_section("t-1", "s1", '<section data-ib-id="s1"><canvas></canvas></section>', "ghost")
        assert res["ok"] is False and res["error"] == "unknown_board_id"

    def test_stale_baseline_not_saved(self, tmp_board_dir):
        ib.board_html_save("t-1", "<p>v1</p>")  # rev 1
        res = ib.board_html_save("t-1", "<p>v2</p>", expected_revision=99)
        assert res["ok"] is False and res["error"] == "stale_baseline"
        assert res["current_revision"] == 1
        assert ib.board_html_load("t-1")["html"] == "<p>v1</p>"  # 未覆盖
        # 带对版本号则放行
        ok = ib.board_html_save("t-1", "<p>v2</p>", expected_revision=1)
        assert ok["ok"] is True and ok["revision"] == 2


class TestCreateBoard:
    def test_create_only_writes_manifest_entry(self, tmp_board_dir):
        ib.board_html_save("t-1", "<p>main</p>")
        res = ib.invoke_create_board("t-1", {"title": "供应链专项"})
        assert res["ok"] is True and res["board_id"] == "board-2" and res["revision"] == 0
        # 空板不产生 HTML 文件
        assert not (tmp_board_dir / "t-1.board.board-2.html").exists()
        m = ib.boards_manifest("t-1")
        assert any(b["board_id"] == "board-2" and b["title"] == "供应链专项" for b in m["boards"])
        # 建好板后可写入
        w = ib.board_html_save("t-1", "<p>第二份</p>", board_id="board-2")
        assert w["ok"] is True and w["revision"] == 1

    def test_create_requires_title(self, tmp_board_dir):
        assert ib.invoke_create_board("t-1", {"title": ""})["error"] == "title_required"

    def test_create_rejects_duplicate_id(self, tmp_board_dir):
        ib.invoke_create_board("t-1", {"title": "A", "board_id": "x1"})
        assert ib.invoke_create_board("t-1", {"title": "B", "board_id": "x1"})["error"] == "board_exists"

    def test_endpoint_create_board(self, client, tmp_board_dir):
        r = client.post("/api/insights/board/t-ep/boards",
                        json={"title": "专项分析", "source": "ui"})
        assert r.status_code == 200
        assert r.json()["board_id"] == "board-2"
        assert client.post("/api/insights/board/t-ep/boards", json={}).status_code == 400


class TestVisualFormCriteria:
    def test_canvas_and_data_uri_img_count(self, tmp_board_dir):
        canvas = '<section data-ib-id="s1"><h3>t</h3><canvas></canvas></section>'
        assert ib.board_html_save("t-1", canvas)["ok"] is True
        img = ('<section data-ib-id="s1"><h3>t</h3>'
               '<img src="data:image/png;base64,iVBOR"/></section>')
        assert ib.board_html_save("t-2", img)["ok"] is True

    def test_table_and_relative_img_not_counted(self, tmp_board_dir):
        table = '<section data-ib-id="s1"><h3>t</h3><table><tr><td>大表</td></tr></table></section>'
        assert ib.detect_text_wall(table) == (1, 0)
        rel_img = '<section data-ib-id="s1"><h3>t</h3><img src="a.png"/></section>'
        assert ib.detect_text_wall(rel_img) == (1, 0)


class TestRawEndpointCsp:
    def test_raw_returns_bytes_with_sandbox_csp(self, client, tmp_board_dir):
        ib.board_html_save("t-raw", "<h1>板正文</h1>")
        r = client.get("/api/insights/board/t-raw/raw")
        assert r.status_code == 200
        assert "<h1>板正文</h1>" in r.text
        csp = r.headers.get("content-security-policy", "")
        assert "sandbox" in csp and "allow-same-origin" not in csp
        assert r.headers.get("x-content-type-options") == "nosniff"

    def test_raw_revision_conflict(self, client, tmp_board_dir):
        ib.board_html_save("t-raw2", "<h1>a</h1>")
        assert client.get("/api/insights/board/t-raw2/raw", params={"rev": "99"}).status_code == 409
        assert client.get("/api/insights/board/t-raw2/raw", params={"rev": "1"}).status_code == 200

    def test_raw_absent_board_404(self, client, tmp_board_dir):
        assert client.get("/api/insights/board/nope/raw").status_code == 404


class TestBoardsEndpoint:
    def test_list_boards_endpoint(self, client, tmp_board_dir):
        ib.board_html_save("t-lb", "<p>x</p>")
        r = client.get("/api/insights/board/t-lb/boards")
        assert r.status_code == 200
        body = r.json()
        assert body["default_board_id"] == "main"
        assert body["boards"][0]["board_id"] == "main"


class TestOpenEndpoint:
    """「在浏览器中打开」指向独立浏览页（/board/...）而不是 raw 字节。

    raw 不跑桥接：mermaid 图不渲染、主题令牌不下发，在浏览器里只能看到源码 pre；
    浏览页复用 InsightBoard 组件，图与主题都跟站内一致。
    """

    def _capture(self, monkeypatch):
        seen: list[str] = []
        monkeypatch.setattr("app.routers.insights.webbrowser.open",
                            lambda url: seen.append(url) or True)
        return seen

    def test_open_points_at_viewer_route(self, client, monkeypatch, tmp_board_dir):
        seen = self._capture(monkeypatch)
        ib.board_html_save("t-open", "<p>x</p>")
        r = client.post("/api/insights/board/t-open/open", json={"board_id": "main"})
        assert r.status_code == 200 and r.json()["ok"] is True
        url = r.json()["url"]
        assert url.endswith("/board/t-open?board_id=main")
        assert "/api/insights/board/" not in url and "/raw" not in url
        assert seen == [url]

    def test_open_ignores_client_supplied_url(self, client, monkeypatch, tmp_board_dir):
        """不接受客户端自由指定跳转目标（防开放重定向）。"""
        self._capture(monkeypatch)
        ib.board_html_save("t-open2", "<p>x</p>")
        r = client.post("/api/insights/board/t-open2/open",
                        json={"raw_url": "http://evil.example/x", "board_id": "main"})
        assert r.json()["url"].endswith("/board/t-open2?board_id=main")
        assert "evil.example" not in r.json()["url"]

    def test_open_without_board_id_omits_query(self, client, monkeypatch, tmp_board_dir):
        self._capture(monkeypatch)
        ib.board_html_save("t-open3", "<p>x</p>")
        r = client.post("/api/insights/board/t-open3/open", json={})
        assert r.json()["url"].endswith("/board/t-open3")
