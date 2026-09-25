# DC-R2-a 前端自测取证脚本：Playwright + VITE_DECISIONS_MOCK=1 mock 通道
# 证据输出: qa-evidence/req-decision-r2a/
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-evidence", "req-decision-r2a")
os.makedirs(OUT, exist_ok=True)

FAILS = []
def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name} {detail}")
    if not cond:
        FAILS.append(name)

PROJECTS = [
    {"id": "kb-1", "name": "产品委员会", "folders": [], "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
    {"id": "kb-2", "name": "研发管理", "folders": [], "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
    {"id": "kb-3", "name": "市场部", "folders": [], "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
]

def handle_route(route):
    url = route.request.url
    path = url.split("?")[0]
    if path == BASE + "/api/projects":
        return route.fulfill(status=200, content_type="application/json", body='{"projects": ' + __import__("json").dumps([{"id": p["id"], "name": p["name"], "folders": [], "created_at": p["created_at"], "updated_at": p["updated_at"]} for p in PROJECTS], ensure_ascii=False) + "}")
    if path == BASE + "/api/tasks":
        return route.fulfill(status=200, content_type="application/json", body='{"tasks": []}')
    return route.fallback()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("localStorage.setItem('locale','zh-CN')")
    ctx.route(BASE + "/api/**", handle_route)
    page = ctx.new_page()
    page.goto(BASE + "/decisions", wait_until="networkidle")
    page.wait_for_selector(".dc-card", timeout=15000)

    # ── AC2：无「平铺/分组」切换器，固定按会议分组 ──
    seg_texts = page.locator(".dc-seg-btn").all_inner_texts()
    check("AC2 视图切换器已移除", not any(("平铺" in t or "分组视图" in t) for t in seg_texts), str(seg_texts))
    groups = page.locator(".dc-group-head")
    check("AC2 固定按会议分组", groups.count() >= 2, f"groups={groups.count()}")
    page.screenshot(path=f"{OUT}/AC2_grouped_no_toggle.png", full_page=True)

    # ── AC1：组内卡片 meta 不重复组头会议名；跳转能力保留 ──
    first_title = page.locator(".dc-group-title").first.inner_text()
    dup = 0
    for i in range(min(groups.count(), 3)):
        gt = page.locator(".dc-group-title").nth(i).inner_text()
        card_texts = page.locator(".dc-group").nth(i).locator(".dc-card .dc-meta").all_inner_texts()
        dup += sum(1 for ct in card_texts if gt and gt in ct)
    check("AC1 组内卡片不重复会议名", dup == 0, f"dup={dup}")
    jump = page.locator(".dc-meta-jump").first
    check("AC1 跳转纪要图标在位", jump.is_visible())
    check("AC1 日期徽标已移除(与组头重复)", page.locator(".dc-meta-date").count() == 0)
    jump.click()
    page.wait_for_url("**/meeting/**", timeout=8000)
    check("AC1 点击跳转账号纪要页", "/meeting/mock-task-" in page.url and "tab=summary" in page.url, page.url)
    page.screenshot(path=f"{OUT}/AC1_jump_to_minutes.png")
    page.go_back()
    page.wait_for_selector(".dc-card", timeout=15000)

    # ── AC3a：行内编辑 ──
    card1 = page.locator(".dc-card").first
    orig_text = card1.locator(".dc-text").inner_text()
    card1.hover()
    card1.locator(".dc-action-btn").click()
    menu = card1.locator(".dc-menu")
    check("AC3 菜单含编辑+删除项", menu.locator("text=编辑决策文本").count() == 1 and menu.locator("text=删除决策").count() == 1)
    page.screenshot(path=f"{OUT}/AC3a_menu_edit_delete.png")
    menu.locator("text=编辑决策文本").click()
    area = card1.locator("textarea.dc-edit-area")
    area.wait_for(state="visible", timeout=5000)
    check("AC3 编辑预填原文本", area.input_value() == orig_text, repr(area.input_value()[:30]))
    new_text = orig_text + "（DC-R2-a 自测改）"
    area.fill(new_text)
    page.screenshot(path=f"{OUT}/AC3a_inline_editing.png")
    card1.locator(".dc-edit-btn.is-primary").click()
    page.wait_for_selector(".toast.is-visible", timeout=5000)
    check("AC3 编辑成功 toast", "决策已更新" in page.locator(".toast").first.inner_text())
    page.wait_for_function(
        "document.querySelector('.dc-card .dc-text') && document.querySelectorAll('.dc-card').length>0 && [...document.querySelectorAll('.dc-card .dc-text')].some(el=>el.textContent.includes('DC-R2-a 自测改'))",
        timeout=8000,
    )
    page.screenshot(path=f"{OUT}/AC3a_after_save.png")
    check("AC3 卡片呈现新文本", True)
    page.wait_for_function("!document.querySelector('.toast.is-visible')", timeout=10000)

    # ── AC3b：行内删除（二次确认） ──
    before = page.locator(".dc-card").count()
    card2 = page.locator(".dc-card").nth(1)
    del_text = card2.locator(".dc-text").inner_text()
    card2.hover()
    card2.locator(".dc-action-btn").click()
    card2.locator(".dc-menu").get_by_text("删除决策", exact=True).click()
    confirm = card2.locator(".dc-del-confirm")
    confirm.wait_for(state="visible", timeout=5000)
    check("AC3 删除需二次确认", "删除后不可恢复" in confirm.inner_text())
    page.screenshot(path=f"{OUT}/AC3b_delete_confirm.png")
    confirm.locator(".is-danger-solid").click()
    page.wait_for_selector(".toast.is-visible", timeout=5000)
    check("AC3 删除成功 toast", "决策已删除" in page.locator(".toast").first.inner_text())
    page.wait_for_timeout(1200)  # mock 通道 reload 后断言
    after = page.locator(".dc-card").count()
    gone = page.locator(".dc-card").filter(has_text=del_text[:20]).count() == 0
    check("AC3 删除后卡片消失", gone and after < before, f"before={before} after={after}")
    page.screenshot(path=f"{OUT}/AC3b_after_delete.png")

    # ── AC4：知识库可检索 combobox ──
    trigger = page.locator(".kb-combo-trigger")
    check("AC4 select 已升级为 combobox", trigger.count() == 1 and page.locator("select.dc-select").count() == 0)
    check("AC4 初始为「全部知识库」", "全部知识库" in trigger.inner_text(), trigger.inner_text())
    trigger.click()
    search = page.locator(".kb-combo-search")
    search.wait_for(state="visible", timeout=5000)
    opts_before = page.locator(".kb-combo-opt").all_inner_texts()
    check("AC4 特殊项保留", "全部知识库" in opts_before and "未关联知识库" in opts_before, str(opts_before))
    search.fill("研发")
    opts_filtered = page.locator(".kb-combo-opt").all_inner_texts()
    check("AC4 键入即过滤", "研发管理" in opts_filtered and "产品委员会" not in opts_filtered and "市场部" not in opts_filtered, str(opts_filtered))
    page.screenshot(path=f"{OUT}/AC4_combo_typing_filter.png")
    # 键盘选中：当前列表 = [全部, 未关联, 研发管理]，三次 ArrowDown 落到「研发管理」后回车
    search.press("ArrowDown"); search.press("ArrowDown"); search.press("ArrowDown")
    focused = page.locator(".kb-combo-opt.is-focused").inner_text()
    check("AC4 键盘导航焦点项", focused == "研发管理", focused)
    search.press("Enter")
    page.wait_for_timeout(1200)
    check("AC4 选中后触发器回显", "研发管理" in trigger.inner_text(), trigger.inner_text())
    kb_badges = page.locator(".dc-card .dc-meta-kb").all_inner_texts()
    check("AC4 过滤生效仅见研发管理", len(kb_badges) > 0 and all(b == "研发管理" for b in kb_badges), str(kb_badges[:5]))
    page.screenshot(path=f"{OUT}/AC4_kb_filtered_result.png")
    # 键盘入口回归：Escape 关闭 + 「未关联」特殊项
    trigger.click(); page.keyboard.press("Escape")
    check("AC4 ESC 关闭弹层", not page.locator(".kb-combo-pop").is_visible())

    browser.close()

print("\n==== RESULT:", "ALL PASSED" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}")
raise SystemExit(0 if not FAILS else 1)
