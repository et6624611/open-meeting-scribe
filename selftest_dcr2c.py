# REQ-DECISION-CENTER-R2 DC-R2-c（决策状态字典）浏览器点验脚本
# Playwright 无头 1440×900 + /api/** 全量有状态 mock（零真实后端接触，无 route.fallback）
# 证据输出: qa-evidence/req-decision-r2c/
import json
import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-evidence", "req-decision-r2c")
os.makedirs(OUT, exist_ok=True)

FAILS = []
REQUESTS = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAILS.append(name)


# ───────────────────────── 有状态 mock：状态字典 + 决策 ─────────────────────────
STATUSES = [
    {"id": "active", "name": "生效中", "name_en": "Active", "color": "var(--st-done)", "closing": False, "system": True},
    {"id": "done", "name": "完成", "name_en": "Done", "color": "var(--accent)", "closing": True, "system": True},
    {"id": "superseded", "name": "已被取代", "name_en": "Superseded", "color": "var(--st-decide)", "closing": True, "system": False},
    {"id": "revoked", "name": "已撤销", "name_en": "Revoked", "color": "var(--error)", "closing": True, "system": False},
]

DECISIONS = {
    "d-active": {"id": "d-active", "task_id": "t1", "title": "预算冻结", "text": "Q4 市场预算维持 120 万。",
                 "owner_id": None, "owner_name": "", "status": "active", "pending_confirmation": False,
                 "source": "auto", "created_at": "2026-09-24T10:00:00", "updated_at": "2026-09-24T10:00:00",
                 "superseded_by": None, "related_todo_ids": []},
    "d-done": {"id": "d-done", "task_id": "t1", "title": "供应商切换", "text": "下季度切换到新供应商。",
               "owner_id": None, "owner_name": "", "status": "done", "pending_confirmation": False,
               "source": "manual", "created_at": "2026-09-23T10:00:00", "updated_at": "2026-09-23T10:00:00",
               "superseded_by": None, "related_todo_ids": []},
    # 存量 superseded 数据 + 悬空取代引用：迁移后必须仍可读、不白屏
    "d-legacy": {"id": "d-legacy", "task_id": "t1", "title": "", "text": "历史被取代的旧方案。",
                 "owner_id": None, "owner_name": "", "status": "superseded", "pending_confirmation": False,
                 "source": "backfill", "created_at": "2026-09-20T10:00:00", "updated_at": "2026-09-20T10:00:00",
                 "superseded_by": {"task_id": "gone", "decision_id": "gone"}, "related_todo_ids": []},
}

_seq = {"n": 0}


def rows():
    meta = {s["id"]: s for s in STATUSES}
    out = []
    for d in DECISIONS.values():
        m = meta.get(d["status"])
        out.append({**d, "meeting_title": "投委会 · Q4 预算终审", "meeting_date": "2026-09-24",
                    "kb_id": None, "kb_name": None,
                    "status_name": (m or {}).get("name", d["status"]),
                    "status_name_en": (m or {}).get("name_en", d["status"]),
                    "status_color": (m or {}).get("color", "var(--muted)"),
                    "status_closing": bool((m or {}).get("closing", d["status"] != "active"))})
    return out


def fulfill(route, payload, status=200):
    return route.fulfill(status=status, content_type="application/json",
                         body=json.dumps(payload, ensure_ascii=False))


def handle(route):
    req = route.request
    method, url = req.method, req.url
    path = url.split("?")[0].replace(BASE, "")
    body = None
    if req.post_data:
        try:
            body = json.loads(req.post_data)
        except Exception:
            body = None
    REQUESTS.append((method, path, body))

    if path == "/api/tasks":
        return fulfill(route, {"tasks": [{"task_id": "t1", "title": "投委会 · Q4 预算终审", "audio_name": "a.mp3",
                                          "status": "completed", "progress": 100, "meeting_date": "2026-09-24",
                                          "created_at": "2026-09-24T10:00:00", "project_id": None}]})
    if path == "/api/projects":
        return fulfill(route, {"projects": []})
    if path == "/api/decision-statuses" and method == "GET":
        return fulfill(route, {"statuses": STATUSES, "total": len(STATUSES)})
    if path == "/api/decision-statuses" and method == "POST":
        _seq["n"] += 1
        item = {"id": f"st-{_seq['n']:04d}", "name": body.get("name", ""), "name_en": body.get("name", ""),
                "color": body.get("color") or "var(--muted)", "closing": bool(body.get("closing")), "system": False}
        STATUSES.append(item)
        return fulfill(route, {"status": item})
    if path.startswith("/api/decision-statuses/reorder") and method == "POST":
        order = body.get("order", [])
        by_id = {s["id"]: s for s in STATUSES}
        if set(order) != set(by_id):
            return fulfill(route, {"detail": "排序请求必须完整覆盖全部状态且不重复"}, 400)
        STATUSES[:] = [by_id[i] for i in order]
        return fulfill(route, {"statuses": STATUSES, "total": len(STATUSES)})
    if path.startswith("/api/decision-statuses/") and method == "PUT":
        sid = path.rsplit("/", 1)[1]
        target = next((s for s in STATUSES if s["id"] == sid), None)
        if target is None:
            return fulfill(route, {"detail": "unknown status"}, 404)
        if target["system"] and ("name" in body or "closing" in body):
            return fulfill(route, {"detail": "系统锚点状态不可改名或删除"}, 400)
        target.update({k: v for k, v in (body or {}).items() if v is not None})
        return fulfill(route, {"status": target})
    if path.startswith("/api/decision-statuses/") and method == "DELETE":
        sid = path.rsplit("/", 1)[1]
        target = next((s for s in STATUSES if s["id"] == sid), None)
        if target is None:
            return fulfill(route, {"detail": "unknown status"}, 404)
        if target["system"]:
            return fulfill(route, {"detail": "系统锚点状态不可删除"}, 400)
        STATUSES.remove(target)
        moved = 0
        for d in DECISIONS.values():
            if d["status"] == sid:
                d["status"] = "active"
                moved += 1
        return fulfill(route, {"ok": True, "removed": sid, "reassigned": moved})
    if path == "/api/decisions":
        return fulfill(route, {"decisions": rows(), "total": len(DECISIONS)})
    if "/decisions/" in path and method == "PUT":
        did = path.rsplit("/", 1)[1]
        rec = DECISIONS.get(did)
        if rec and isinstance(body, dict):
            for k in ("title", "text", "status", "pending_confirmation"):
                if k in body:
                    rec[k] = body[k]
        return fulfill(route, {"decision": rec or {}})
    return fulfill(route, {})


def settle(page):
    try:
        page.wait_for_selector(".dc-loading", state="detached", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(350)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    ctx.add_init_script("try{if(!localStorage.getItem('locale'))localStorage.setItem('locale','zh-CN')}catch(e){}")
    ctx.route(BASE + "/api/**", handle)
    page = ctx.new_page()

    def shot(name):
        page.screenshot(path=os.path.join(OUT, name + ".png"), full_page=True)
        print(f"[shot] {name}")

    page.goto(BASE + "/decisions", wait_until="networkidle")
    page.wait_for_selector(".dc-card", timeout=15000)
    settle(page)

    # ── C1 状态 chips 字典驱动 + 默认只按下非闭档项 ──
    chips = page.locator(".dc-filter-group .dc-chip").all_inner_texts()
    on_chips = page.locator(".dc-filter-group .dc-chip.on").all_inner_texts()
    check("C1 状态 chips 来自字典（含历史 superseded/revoked）",
          all(any(k in c for c in chips) for k in ["生效中", "完成", "已被取代", "已撤销", "待确认", "查看全部"]), str(chips))
    check("C1 默认按下项 = 非闭档 + 待确认", on_chips == ["生效中", "待确认"], str(on_chips))

    # ── C2 卡片菜单不再出现取代/撤销两项 ──
    card = page.locator(".dc-card").filter(has_text="预算冻结").first
    card.hover()
    card.locator(".dc-action-btn").click()
    menu_items = card.locator(".db-dd-item").all_inner_texts()
    check("C2 菜单已无「已被取代/已撤销」", not any(("取代" in m or "撤销" in m) for m in menu_items), str(menu_items))
    check("C2 菜单保留编辑与删除", any("编辑" in m for m in menu_items) and any("删除" in m for m in menu_items))
    shot("C2_card_menu_no_supersede")
    page.keyboard.press("Escape")

    # ── C3 完成态默认隐藏，查看全部后出现并沉底折叠 ──
    cards_default = page.locator(".dc-card").count()
    check("C3 默认视图不含完成/闭档条目", cards_default == 1, f"cards={cards_default}")
    page.click(".dc-chip-all")
    settle(page)
    cards_all = page.locator(".dc-card").count()
    check("C3 查看全部后闭档条目出现", cards_all >= 2, f"cards={cards_all}")
    ineff_toggle = page.locator(".dc-ineff-toggle")
    check("C3 闭档条目进入组内沉底折叠区", ineff_toggle.count() >= 1)
    ineff_label = ineff_toggle.first.inner_text() if ineff_toggle.count() else ""
    check("C3 沉底区计数含完成类条目", "2" in ineff_label, ineff_label)
    ineff_toggle.first.click()
    page.wait_for_timeout(400)
    body_all = page.inner_text("body")
    check("C3 展开后完成条目可见且带状态徽标", "下季度切换到新供应商" in body_all and "完成" in body_all)
    shot("C3_view_all_with_sunk_items")

    # ── C4 颜色/徽标由字典驱动（内联色，非写死类名） ──
    done_card = page.locator(".dc-card").filter(has_text="供应商切换").first
    dot_bg = done_card.locator(".dc-dot").first.evaluate("e => getComputedStyle(e).backgroundColor")
    check("C4 色点颜色取自字典 color", bool(dot_bg) and dot_bg != "rgba(0, 0, 0, 0)", dot_bg)
    legacy_card = page.locator(".dc-card").filter(has_text="历史被取代的旧方案").first
    check("C4 存量 superseded 显示字典名而非枚举键", "已被取代" in legacy_card.locator(".dc-badge").first.inner_text())
    check("C4 悬空取代引用降级不白屏", "取代" in legacy_card.inner_text() or "失效" in legacy_card.inner_text(), legacy_card.inner_text()[:60])

    # ── C5 管理状态：新增（含闭档勾选与颜色） ──
    page.click(".dc-manage-btn")
    page.wait_for_selector(".sm-dialog", state="visible")
    anchors = page.locator(".sm-row.is-system")
    check("C5 弹层内两个锚点带系统保底标记", anchors.count() == 2)
    for i in range(anchors.count()):
        row = anchors.nth(i)
        check("C5 锚点不可改名（输入框只读/禁用）",
              row.locator(".sm-name").is_disabled() or row.locator(".sm-name").get_attribute("readonly") is not None)
        check("C5 锚点不可删除（删除按钮禁用）", row.locator(".sm-op.is-danger").is_disabled())
    shot("C5_status_manager_anchors_locked")
    page.fill(".sm-add .sm-name", "跟进中")
    page.locator(".sm-add .sm-swatch").nth(4).click()
    page.click(".sm-add .sm-submit")
    page.wait_for_timeout(900)
    post = [r for r in REQUESTS if r[0] == "POST" and r[1] == "/api/decision-statuses"]
    check("C5 新增发出 POST 且携带 name/color", len(post) == 1 and post[0][2].get("name") == "跟进中", str(post))
    rows_now = page.locator(".sm-row").count()
    check("C5 新状态进入管理列表", rows_now == 5, f"rows={rows_now}")

    # ── C6 改名 + 勾选闭档 ──
    # 新行定位靠索引（input value 不属于 innerText，has_text 无法匹配）
    new_row = page.locator(".sm-row").nth(4)
    name_input = new_row.locator(".sm-name")
    name_input.click()
    name_input.fill("推进中")
    name_input.press("Enter")   # 模板内 @keydown.enter → blur() → commitRename
    page.wait_for_timeout(900)
    puts = [r for r in REQUESTS if r[0] == "PUT" and r[1].startswith("/api/decision-statuses/")]
    check("C6 改名发出 PUT name", any((b or {}).get("name") == "推进中" for _, _, b in puts), str(puts)[-160:])
    check("C6 列表即时反映新名", page.locator(".sm-row").nth(4).locator(".sm-name").input_value() == "推进中")
    new_row = page.locator(".sm-row").nth(4)
    new_row.locator(".sm-check input[type=checkbox]").click()
    page.wait_for_timeout(900)
    closing_puts = [r[2] for r in REQUESTS if r[0] == "PUT" and r[1].startswith("/api/decision-statuses/") and isinstance(r[2], dict)]
    check("C6 勾选闭档发出 PUT closing=true", any(b.get("closing") is True for b in closing_puts), str(closing_puts)[-120:])

    # ── C7 排序：上移后发出完整 id 序列 ──
    before_order = [s["id"] for s in STATUSES]
    page.locator(".sm-row").nth(4).locator(".sm-op").nth(0).click()   # 上移
    page.wait_for_timeout(900)
    reorders = [r for r in REQUESTS if r[1].endswith("/reorder")]
    check("C7 上移发出 POST reorder", len(reorders) == 1 and set(reorders[0][2]["order"]) == set(before_order), str(reorders)[-160:])
    check("C7 行位已上移（新行现在索引 3）", page.locator(".sm-row").nth(3).locator(".sm-name").input_value() == "推进中")
    shot("C7_after_reorder")

    # ── C8 删除自定义状态：引用决策回落生效中 ──
    target_status = next(s for s in STATUSES if s["name"] == "推进中")
    DECISIONS["d-active"]["status"] = target_status["id"]  # 让新状态被一条决策引用
    page.reload(wait_until="networkidle")
    settle(page)
    page.click(".dc-manage-btn")
    page.wait_for_selector(".sm-dialog", state="visible")
    del_row = page.locator(".sm-row").nth(3)   # 上移后新行位于索引 3
    del_row.locator(".sm-op.is-danger").click()
    page.wait_for_selector(".sm-confirm", state="visible")
    check("C8 删除前给出影响说明", "生效中" in page.locator(".sm-confirm").inner_text(), page.locator(".sm-confirm").inner_text()[:80])
    page.locator(".sm-confirm .sm-op.is-danger-solid").click()
    page.wait_for_timeout(900)
    dels = [r for r in REQUESTS if r[0] == "DELETE" and r[1].startswith("/api/decision-statuses/")]
    check("C8 删除发出 DELETE", len(dels) == 1)
    check("C8 被删状态从列表消失", page.locator(".sm-row").count() == 4)
    page.locator(".sm-footer .btn-cancel").click()
    page.wait_for_timeout(500)
    settle(page)
    active_chip_texts = page.locator(".dc-filter-group .dc-chip").all_inner_texts()
    check("C8 状态 chips 已同步移除被删项", not any("推进中" in c for c in active_chip_texts), str(active_chip_texts))
    back_to_active = [d for d in DECISIONS.values() if d["status"] == "active"]
    check("C8 引用被删状态的决策回落 active", len(back_to_active) >= 1)
    check("C8 回落后的决策重新出现在默认视图", page.locator(".dc-card").filter(has_text="预算冻结").count() == 1)
    shot("C8_after_delete")

    # ── C9 决策改状态走 PUT + 字典 id（取代/撤销写回端点不再被调用） ──
    page.click(".dc-chip-all")   # 回到查看全部，便于定位卡片
    settle(page)
    page.locator(".dc-ineff-toggle").first.click()
    page.wait_for_timeout(300)
    card = page.locator(".dc-card").filter(has_text="预算冻结").first
    card.hover()
    card.locator(".dc-action-btn").click()
    card.locator(".dc-menu >> text=编辑决策文本").click()
    edit = page.locator(".dc-edit")
    edit.wait_for(state="visible", timeout=5000)
    check("C9 行内编辑仍为三字段（标题/内容/执行人）",
          edit.locator("input.dc-edit-input").count() == 1 and edit.locator("textarea").count() == 1
          and edit.locator(".own-combo-trigger").count() == 1)
    edit.locator(".dc-edit-btn.is-primary").click()
    settle(page)
    no_supersede = [r for r in REQUESTS if "supersede" in r[1]]
    check("C9 全程无 supersede 端点调用", len(no_supersede) == 0)

    # ── C10 英文界面对照 ──
    page.evaluate("() => localStorage.setItem('locale','en')")
    page.goto(BASE + "/decisions", wait_until="networkidle")
    page.goto(BASE + "/decisions", wait_until="networkidle")
    settle(page)
    en_chips = page.locator(".dc-filter-group .dc-chip").all_inner_texts()
    check("C10 英文锚点名走 name_en", any("Active" in c for c in en_chips) and any("View all" in c for c in en_chips), str(en_chips))
    page.click(".dc-manage-btn")
    page.wait_for_selector(".sm-dialog", state="visible")
    en_body = page.inner_text("body")
    check("C10 管理弹层英文在位", "Built-in" in en_body and "Counts as done" in en_body)
    check("C10 无 i18n key 泄漏", "decisions." not in en_body and "sm_" not in en_body)
    shot("C10_en_status_manager")

    browser.close()

print("=" * 60)
print("RESULT:", "ALL ASSERTIONS PASSED" if not FAILS else f"{len(FAILS)} FAILED -> {FAILS}")
with open(os.path.join(OUT, "selftest-run.log"), "w", encoding="utf-8") as f:
    f.write("\n".join(f"{m} {u} {b}" for m, u, b in REQUESTS) + "\n\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
