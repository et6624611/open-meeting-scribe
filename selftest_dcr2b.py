# REQ-DECISION-CENTER-R2 DC-R2-b（决策三要素）浏览器点验脚本
# Playwright 无头 1440×900 + /api/** 全量有状态 mock（零真实后端接触，无 route.fallback）
# 证据输出: qa-evidence/req-decision-r2b/
import json
import os

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-evidence", "req-decision-r2b")
os.makedirs(OUT, exist_ok=True)

FAILS = []
REQUESTS = []   # [(method, path, body_dict)]


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAILS.append(name)


# ───────────────────────── 有状态 mock 数据 ─────────────────────────
TASKS = [
    {"task_id": "t-alpha", "title": "投委会 · Q4 预算终审", "audio_name": "a.mp3", "status": "completed",
     "progress": 100, "meeting_date": "2026-09-24", "created_at": "2026-09-24T10:00:00", "project_id": "kb-1"},
    {"task_id": "t-beta", "title": "OMS 双周迭代复盘", "audio_name": "b.mp3", "status": "completed",
     "progress": 100, "meeting_date": "2026-09-22", "created_at": "2026-09-22T10:00:00", "project_id": "kb-2"},
]

DECISIONS = {
    # 三要素齐备（新形态）
    "d1": {"id": "d1", "task_id": "t-alpha", "title": "Q4 预算冻结", "text": "市场预算维持 120 万，其中 40% 用于行业展会。",
           "owner_id": "spk-wyl", "owner_name": "王永亮", "status": "active", "pending_confirmation": False,
           "source": "auto", "created_at": "2026-09-24T10:00:00", "updated_at": "2026-09-24T10:00:00",
           "superseded_by": None, "related_todo_ids": []},
    # 存量形态：无标题、无执行人（读取侧降级）
    "d2": {"id": "d2", "task_id": "t-alpha", "title": "", "text": "存量决策既没有标题也没有执行人。",
           "owner_id": None, "owner_name": "", "status": "active", "pending_confirmation": False,
           "source": "backfill", "created_at": "2026-09-24T09:00:00", "updated_at": "2026-09-24T09:00:00",
           "superseded_by": None, "related_todo_ids": []},
    "d3": {"id": "d3", "task_id": "t-beta", "title": "执行人归属", "text": "由产品委员会牵头推进，人选会后敲定。",
           "owner_id": "spk-zcc", "owner_name": "张丛丛", "status": "active", "pending_confirmation": True,
           "source": "manual", "created_at": "2026-09-22T10:00:00", "updated_at": "2026-09-22T10:00:00",
           "superseded_by": None, "related_todo_ids": []},
}

SPEAKERS = [
    {"speaker_id": "spk-wyl", "name": "王永亮", "role": "本公司"},
    {"speaker_id": "spk-zcc", "name": "张丛丛", "role": ""},
    # 占位档案名：不得作为执行人候选（REQ-SPK-RN 口径同源）
    {"speaker_id": "spk-ph", "name": "Speaker 3", "role": ""},
]

PROJECTS = [
    {"id": "kb-1", "name": "产品委员会", "folders": [], "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
    {"id": "kb-2", "name": "研发管理", "folders": [], "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
]

MEETING_TITLE = {t["task_id"]: t["title"] for t in TASKS}
_seq = {"n": 0}


def aggregated_rows():
    rows = []
    for d in DECISIONS.values():
        rows.append({**d, "task_id": d["task_id"],
                     "meeting_title": MEETING_TITLE.get(d["task_id"], d["task_id"]),
                     "meeting_date": next((t["meeting_date"] for t in TASKS if t["task_id"] == d["task_id"]), None),
                     "kb_id": next((t["project_id"] for t in TASKS if t["task_id"] == d["task_id"]), None),
                     "kb_name": next((p["name"] for p in PROJECTS
                                      if p["id"] == next((t["project_id"] for t in TASKS if t["task_id"] == d["task_id"]), None)), None)})
    return rows


def fulfill(route, payload, status=200):
    return route.fulfill(status=status, content_type="application/json",
                         body=json.dumps(payload, ensure_ascii=False))


def settle(page):
    """等一次列表重拉走完：loading 骨架 (v-else-if) 会整体卸载卡片，
    在骨架未消失前做的 hover/click 均会落在即将卸载的 DOM 上。"""
    try:
        page.wait_for_selector(".dc-loading", state="detached", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(400)


def handle(route):
    req = route.request
    method, url = req.method, req.url
    path = url.split("?")[0]
    query = url.split("?")[1] if "?" in url else ""
    body = None
    if req.post_data:
        try:
            body = json.loads(req.post_data)
        except Exception:
            body = req.post_data
    REQUESTS.append((method, path.replace(BASE, ""), body))

    if path == BASE + "/api/projects":
        return fulfill(route, {"projects": PROJECTS})
    if path == BASE + "/api/tasks":
        return fulfill(route, {"tasks": TASKS})
    if path == BASE + "/api/speakers" and method == "GET":
        return fulfill(route, {"speakers": SPEAKERS})
    if path == BASE + "/api/speakers" and method == "POST":
        _seq["n"] += 1
        new = {"speaker_id": f"spk-new-{_seq['n']}", "name": (body or {}).get("name", ""), "role": ""}
        SPEAKERS.append(new)
        return fulfill(route, new)
    if path == BASE + "/api/decisions":
        rows = aggregated_rows()
        if "status=active" in query:
            rows = [r for r in rows if r["status"] == "active"]
        return fulfill(route, {"decisions": rows, "total": len(rows)})
    if path.endswith("/decisions") and method == "POST":
        tid = path.split("/api/tasks/")[1].split("/")[0]
        _seq["n"] += 1
        rec = {"id": f"new-{_seq['n']}", "task_id": tid, "title": (body or {}).get("title", ""),
               "text": (body or {}).get("text", ""), "owner_id": (body or {}).get("owner_id") or None,
               "owner_name": (body or {}).get("owner_name", ""), "status": "active",
               "pending_confirmation": (body or {}).get("pending_confirmation", False), "source": "manual",
               "created_at": "2026-09-25T10:00:00", "updated_at": "2026-09-25T10:00:00",
               "superseded_by": None, "related_todo_ids": []}
        DECISIONS[rec["id"]] = rec
        return fulfill(route, {"decision": rec})
    if "/decisions/" in path and method == "PUT":
        did = path.rsplit("/", 1)[1]
        rec = DECISIONS.get(did)
        if rec and isinstance(body, dict):
            for k in ("title", "text", "pending_confirmation", "status"):
                if k in body:
                    rec[k] = body[k]
            # 契约：空串=清空指派，未传=保持不变
            if "owner_id" in body:
                rec["owner_id"] = body["owner_id"] or None
                rec["owner_name"] = (body.get("owner_name") or "") if not body["owner_id"] else next(
                    (s["name"] for s in SPEAKERS if s["speaker_id"] == body["owner_id"]), body.get("owner_name", ""))
        return fulfill(route, {"decision": rec or {}})
    # 其余端点一律返回空对象：绝不放行到真实后端（DC-R2-a 穿透事故的防线）
    return fulfill(route, {})


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
    page.wait_for_timeout(600)

    # ── B1 三要素卡片：标题行 + 内容行 + 执行人 chip ──
    card = page.locator(".dc-card").filter(has_text="Q4 预算冻结").first
    check("B1 决策标题作为行首一级信息", card.locator(".db-title.is-title").inner_text().strip() == "Q4 预算冻结")
    check("B1 内容独立成行", "市场预算维持 120 万" in card.locator(".dc-content").inner_text())
    check("B1 执行人 chip 呈现", "王永亮" in card.locator(".dc-meta-owner").inner_text())
    shot("B1_three_element_card")

    # ── B2 存量降级：无标题 → 单行式，且不出现空内容行/undefined ──
    legacy = page.locator(".dc-card").filter(has_text="存量决策既没有标题").first
    check("B2 存量卡片无内容行", legacy.locator(".dc-content").count() == 0)
    check("B2 存量卡片行首为内容文本", "存量决策" in legacy.locator(".db-title").inner_text())
    check("B2 无 undefined/null 字面量", "undefined" not in page.inner_text("body") and "null" not in page.inner_text("body"))

    # ── B3 组头仍是会议标题（meeting_title 接线） ──
    group_titles = page.locator(".dc-group-title").all_inner_texts()
    check("B3 组头显示会议标题", "投委会 · Q4 预算终审" in group_titles, str(group_titles))
    check("B3 组头未被决策标题污染", not any("Q4 预算冻结" in g for g in group_titles))

    # ── B4 补录弹框三字段 ──
    page.click(".dc-add-btn")
    page.wait_for_selector(".ad-dialog", state="visible")
    labels = page.locator(".ad-dialog .ad-label").all_inner_texts()
    check("B4 弹框含 标题/内容/执行人 三字段", all(k in labels for k in ["归属会议", "标题", "内容", "执行人"]), str(labels))
    shot("B4_add_dialog_three_fields")

    # ── B5 执行人选人：搜索档案 + 手打即时建档 ──
    page.fill(".ad-dialog textarea", "自测决策：新增一条带三要素的决策")
    page.fill(".ad-dialog input.ad-input", "DC-R2-b 自测标题")
    page.click(".ad-dialog .own-combo-trigger")
    page.wait_for_selector(".own-combo-pop", state="visible")
    page.fill(".own-combo-search", "张丛丛")
    page.wait_for_timeout(300)
    opts = page.locator(".own-combo-opt").all_inner_texts()
    check("B5 档案可按姓名检索", any("张丛丛" in o for o in opts), str(opts))
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    check("B5 选中后触发器回显档案名", "张丛丛" in page.locator(".ad-dialog .own-combo-value").inner_text())
    # 手打不存在的人名 → 建档出口
    page.click(".ad-dialog .own-combo-trigger")
    page.wait_for_selector(".own-combo-pop", state="visible")
    page.fill(".own-combo-search", "张天雷")
    page.wait_for_timeout(300)
    create_row = page.locator(".own-combo-create")
    check("B5 无同名档案时出现即时建档出口", create_row.count() == 1 and "张天雷" in create_row.inner_text())
    shot("B5_owner_create_on_type")
    create_row.click()
    page.wait_for_timeout(500)
    posted_speaker = [r for r in REQUESTS if r[0] == "POST" and r[1] == "/api/speakers"]
    check("B5 建档调用 POST /api/speakers", len(posted_speaker) == 1 and posted_speaker[0][2].get("name") == "张天雷", str(posted_speaker))
    check("B5 建档后选人位为新人名", "张天雷" in page.locator(".ad-dialog .own-combo-value").inner_text())

    # ── B6 提交：POST 请求体携带三要素 + owner_id ──
    page.click(".ad-dialog .btn-submit")
    settle(page)
    posts = [r for r in REQUESTS if r[0] == "POST" and r[1].endswith("/decisions")]
    check("B6 提交发出一次 POST", len(posts) == 1)
    payload = posts[0][2] if posts else {}
    check("B6 请求体含 title", payload.get("title") == "DC-R2-b 自测标题", str(payload)[:160])
    check("B6 请求体含 owner_id（档案 id 而非文本）", str(payload.get("owner_id", "")).startswith("spk-new-"), str(payload.get("owner_id")))
    check("B6 请求体含 owner_name 快照", payload.get("owner_name") == "张天雷")
    check("B6 请求体含 text 内容", "自测决策" in str(payload.get("text")))
    page.wait_for_selector(".dc-card:has-text('DC-R2-b 自测标题')", timeout=8000)
    check("B6 新卡片按三要素呈现", page.locator(".dc-card").filter(has_text="DC-R2-b 自测标题").first.locator(".dc-meta-owner").count() == 1)
    shot("B6_after_create")

    # ── B7 行内编辑三字段回显 + 清空执行人下发空串 ──
    # 注意：进入编辑态后卡片 innerText 不再含标题（标题/正文均变为控件 value），
    #      因此编辑期间的断言一律走全局定位（同一时刻只有一张卡片处于编辑态）。
    page.wait_for_selector(".dc-card:has-text('Q4 预算冻结')", timeout=8000)
    card = page.locator(".dc-card").filter(has_text="Q4 预算冻结").first
    card.hover()
    card.locator(".dc-action-btn").click()
    card.locator(".dc-menu >> text=编辑决策文本").click()
    edit = page.locator(".dc-edit")
    edit.wait_for(state="visible", timeout=5000)
    check("B7 编辑态含标题输入框", edit.locator("input.dc-edit-input").input_value() == "Q4 预算冻结")
    check("B7 编辑态含内容文本域", "市场预算维持" in edit.locator("textarea.dc-edit-area").input_value())
    check("B7 编辑态含选人控件且回显现执行人", "王永亮" in edit.locator(".own-combo-value").inner_text())
    shot("B7_inline_edit_three_fields")
    # 清空指派
    edit.locator(".own-combo-trigger").click()
    page.wait_for_selector(".own-combo-pop", state="visible")
    edit.locator(".own-combo-clear").click()
    page.wait_for_timeout(300)
    check("B7 清空后选人位回到未指派", "Unassigned" in edit.locator(".own-combo-value").inner_text() or "未指派" in edit.locator(".own-combo-value").inner_text())
    edit.locator(".dc-edit-btn.is-primary").click()
    settle(page)
    puts = [r for r in REQUESTS if r[0] == "PUT"]
    check("B7 保存发出 PUT", len(puts) >= 1)
    pbody = puts[-1][2] if puts else {}
    check("B7 PUT 携带三字段", set(["title", "text", "owner_id"]).issubset(pbody.keys()), str(pbody)[:160])
    check("B7 清空执行人下发空串（非省略键）", pbody.get("owner_id") == "", str(pbody.get("owner_id")))
    page.wait_for_selector(".dc-card:has-text('Q4 预算冻结')", timeout=8000)
    check("B7 卡片执行人 chip 已消失", page.locator(".dc-card").filter(has_text="Q4 预算冻结").first.locator(".dc-meta-owner").count() == 0)
    shot("B7_after_owner_cleared")

    # ── B8 占位档案名不作为执行人候选 ──
    page.goto(BASE + "/decisions", wait_until="networkidle")
    page.click(".dc-add-btn")
    page.wait_for_selector(".ad-dialog", state="visible")
    page.click(".ad-dialog .own-combo-trigger")
    page.wait_for_selector(".own-combo-pop", state="visible")
    page.wait_for_timeout(500)
    body_text = page.locator(".own-combo-pop").inner_text()
    check("B8 Speaker 编号档案不入选人候选", "Speaker 3" not in body_text, body_text.replace("\n", " | ")[:160])
    shot("B8_placeholder_speaker_filtered")

    # ── B9 英文 locale 标签齐备、无 key 泄漏、无中文残留 ──
    page.evaluate("() => localStorage.setItem('locale','en')")
    page.goto(BASE + "/decisions", wait_until="networkidle")
    page.goto(BASE + "/decisions", wait_until="networkidle")
    page.wait_for_selector(".dc-card", timeout=15000)
    page.click(".dc-add-btn")
    page.wait_for_selector(".ad-dialog", state="visible")
    en_labels = page.locator(".ad-dialog .ad-label").all_inner_texts()
    check("B9 英文三字段标签在位", all(k in en_labels for k in ["Title", "Content", "Owner"]), str(en_labels))
    en_body = page.inner_text("body")
    check("B9 英文界面 owner 兜底文案为英文", "Unassigned" in en_body)
    check("B9 无 i18n key 泄漏", "decisions." not in en_body and "owner_create_hint" not in en_body)
    shot("B9_en_locale_labels")

    browser.close()

print("=" * 60)
print("RESULT:", "ALL ASSERTIONS PASSED" if not FAILS else f"{len(FAILS)} FAILED -> {FAILS}")
with open(os.path.join(OUT, "selftest-run.log"), "w", encoding="utf-8") as f:
    f.write("\n".join(f"{m} {u} {b}" for m, u, b in REQUESTS) + "\n\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
