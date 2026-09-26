# AM-F1 前端自测取证脚本：Playwright + 有状态 mock（模拟 AM-B1 未合入窗口）
# 证据输出: qa-evidence/req-access-mode-f1/
import json, os, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-evidence", "req-access-mode-f1")
os.makedirs(OUT, exist_ok=True)

# ─── 有状态 mock（等价 main 后端：无 /api/settings/routing，settings 白名单合并） ───
st = {
    "engine_mode": None,          # 未配置 → access_mode 惰性推导 null → 触发引导
    "local_ready": False,
    "logged_in": False,
    "prefer_subscription": False,
    "llm": {"provider": "", "base_url": "", "api_key": "", "api_key_set": False, "model": ""},
    "asr": {"mode": "proxy", "provider": "Cloud AI", "model": "paraformer-v2", "api_key_set": False},
    "voiceprint": {"provider": "auto", "cloud_base_url": "", "cloud_api_key_set": False},
}
log_lines = []
def log(msg):
    print(msg); log_lines.append(msg)

def settings_payload():
    p = {"llm": dict(st["llm"]), "asr": dict(st["asr"]), "voiceprint": dict(st["voiceprint"]),
         "feature_flags": {"realtime_chapters": True, "realtime_summary": True, "update_check": False, "voiceprint_auto_match": False},
         "prefer_subscription": st["prefer_subscription"], "output_dir": "data/output/",
         "storage": {"auto_clean_intermediate": True, "auto_archive_days": 0},
         "diarization": {"subscription_tier": "free", "local_diarization": True, "effective": "local", "can_toggle": False},
         "disabled_commands": [], "active_agent": "meeting-minutes", "llm_provider_presets": [],
         "asr_provider_presets": []}
    if st["engine_mode"]:
        p["engine"] = {"mode": st["engine_mode"], "local": {"ready": st["local_ready"]}}
    return p

def handle(route):
    url = route.request.url
    path = url.split("?")[0].replace(BASE, "")
    method = route.request.method
    def json_ok(body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body, ensure_ascii=False))
    try:
        if path == "/api/settings/routing":
            return json_ok({"detail": "Not Found"}, 404)  # AM-B1 未合入
        if path == "/api/settings/probe-local-engine":
            return json_ok({"ok": True, "probed_at": 0, "timeout_seconds": 2, "engines": [], "detected": []})
        if path == "/api/settings" and method == "GET":
            return json_ok(settings_payload())
        if path == "/api/settings" and method == "POST":
            body = json.loads(route.request.post_data or "{}")
            acc = body.get("access_mode")
            if acc == "local": st["engine_mode"] = "local"
            elif acc == "hosted": st["engine_mode"] = "proxy"; st["asr"]["mode"] = "proxy"
            elif acc == "byok": st["engine_mode"] = "direct"; st["asr"]["mode"] = "direct"
            elif body.get("engine", {}).get("mode"): st["engine_mode"] = body["engine"]["mode"]
            if body.get("local_ready_force") is not None:
                st["local_ready"] = body["local_ready_force"]
            return json_ok({"ok": True})
        if path == "/api/engine/status":
            return json_ok({"mode": st["engine_mode"] or "proxy", "models_ready": st["local_ready"],
                            "process_running": False, "pid": None, "missing_models": [], "tampered_models": [],
                            "can_manage": True})
        if path == "/api/engine/models":
            return json_ok({"model_dir": "/tmp/models", "disk_free_bytes": 500 * 1024**3,
                            "total_size_all_bytes": 20 * 1024**3, "total_size_required_bytes": 8 * 1024**3,
                            "models": [], "downloads": []})
        if path.startswith("/api/engine/"):
            return json_ok({"ok": True})
        if path == "/api/health":
            return json_ok({"status": "ok", "auth": {"logged_in": st["logged_in"]}})
        if path == "/auth/me":
            if st["logged_in"]:
                return json_ok({"id": 1, "name": "测试用户", "phone": "", "provider": "local", "role": "user"})
            return json_ok({"detail": "unauthorized"}, 401)
        if path == "/api/usage/summary":
            return json_ok({"metered": st["logged_in"], "tier": "free", "quota": 300, "used": 20,
                            "remaining": 280, "month": "2026-09", "percentage": 6.7})
        if path == "/api/usage/history":
            return json_ok({"history": []})
        if path == "/api/tasks":
            return json_ok({"tasks": []})
        if path == "/api/storage/usage":
            dir_usage = {"size_bytes": 1024, "file_count": 1}
            return json_ok({"recordings": dir_usage, "uploads": dir_usage, "tasks": dir_usage,
                            "output": dir_usage,
                            "intermediate": {"normalized_files": dir_usage, "raw_files": dir_usage,
                                             "duplicate_normalized": dir_usage},
                            "total_bytes": 4096, "reclaimable_bytes": 3072})
        if path == "/api/models":
            return json_ok({"asr": ["paraformer-v2"], "llm": ["qwen-plus"]})
        if path == "/api/record/status":
            return json_ok({"recording": False, "task_id": None})
        return route.fallback()  # 其余请求放行到本机 :8000 后端（只读 GET 为主，写端点均已拦截）
    except Exception as e:
        log(f"[mock-error] {method} {path}: {e}")
        json_ok({})

def shot(page, name):
    p = os.path.join(OUT, name + ".png")
    page.screenshot(path=p, full_page=False)
    log(f"[shot] {name} -> {p}")

def footer_text(page):
    return page.inner_text(".status-engine").strip()

def ensure_expert_on(page):
    """高级配置面板仅在选中「高级模式」卡片后渲染：读权威 mock 态避免 DOM 时序竞态"""
    st = page.evaluate("() => JSON.parse(localStorage.getItem('oms_access_mode') || 'null')")
    if not (st and st.get('expert_mode')):
        page.locator(".amc-expert-card").click()
        page.wait_for_timeout(500)

def set_mock_state(page, access=None, expert=False):
    val = {"access_mode": access, "expert_mode": expert, "chosen": access is not None}
    page.evaluate("([k,v]) => localStorage.setItem(k, JSON.stringify(v))", ["oms_access_mode", val])

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    ctx.route(BASE + "/api/**", handle)
    ctx.route(BASE + "/auth/**", handle)
    page = ctx.new_page()
    page.add_init_script("localStorage.setItem('locale', 'zh-CN')")
    page.goto(BASE + "/settings", wait_until="networkidle")

    # ═══ A. AC-T4① 引导头 + 四卡片（3 接入模式 + 1 高级模式）+ AC-T5① 未配置文案 ═══
    page.wait_for_selector(".amc-card", timeout=8000)
    assert page.locator(".access-guide").is_visible(), "引导头未出现"
    shot(page, "AC-T4-01_guide_onboarding")
    log(f"[A] footer={footer_text(page)}")

    # ═══ B. AC-T3① 选托管 → 持久化链（evidence ①） ═══
    page.get_by_text("托管模式", exact=True).first.click()
    page.wait_for_timeout(700)
    assert "已切换为托管模式" in page.inner_text(".access-cards")
    log(f"[B1] footer={footer_text(page)}")
    shot(page, "e1-01_select_hosted")
    page.reload(wait_until="networkidle"); page.wait_for_timeout(500)
    assert page.locator(".amc-card.is-selected").inner_text().find("托管") >= 0, "刷新后托管未持久化"
    log(f"[B2 after-reload] footer={footer_text(page)}")
    shot(page, "e1-02_hosted_persisted_after_reload")

    # ═══ C. AC-T3② 高级模式 + 离线选中 → 服务区块灰化（evidence ②）+ 离线文案 ═══
    ensure_expert_on(page)  # 高级配置面板仅在选中「高级模式」后渲染
    page.wait_for_timeout(300)
    page.get_by_text("离线模式", exact=False).first.click()
    page.wait_for_timeout(700)
    assert page.locator(".amc-services.is-takeover").is_visible()
    assert "由离线模式接管" in page.inner_text(".amc-services")
    log(f"[C] footer={footer_text(page)} (预期: 离线未就绪 · 原因文案)")
    shot(page, "e2_services_takeover_gray")
    # 模拟本地模型就绪 → 文案切「离线就绪」
    st["local_ready"] = True
    page.reload(wait_until="networkidle"); page.wait_for_timeout(500)
    log(f"[C2] footer={footer_text(page)} (预期: 离线就绪)")
    shot(page, "AC-T5-01_local_ready_status")
    assert "离线就绪" in footer_text(page)

    # ═══ D. AC-T4② 高级模式开/关两态（evidence ③）—— C 已开启，先校验开态再关闭 ═══
    ensure_expert_on(page)  # 幂等：确保处于开启态
    page.wait_for_timeout(300)
    nav_items = page.locator(".settings-nav-item").all_inner_texts()
    assert any("账户" in x for x in nav_items) and any("服务" in x for x in nav_items) and any("计算引擎" in x for x in nav_items), f"高级模式开启后旧分类未出现: {nav_items}"
    shot(page, "e3a_expert_on_old_categories")
    log(f"[D-on] nav={nav_items}")
    # 旧「服务」分类完整可用
    page.get_by_role("button", name="服务").click(); page.wait_for_timeout(300)
    shot(page, "e3a2_expert_services_view")
    page.get_by_role("button", name="接入方式").click()
    page.wait_for_timeout(200)
    # 点击「高级模式」卡片 → 关闭高级配置，旧分类隐藏
    page.locator(".amc-expert-card").click()
    page.wait_for_timeout(600)
    nav_items2 = page.locator(".settings-nav-item").all_inner_texts()
    assert not any("服务" == x.strip() for x in nav_items2), f"高级模式关闭后旧分类未隐藏: {nav_items2}"
    shot(page, "e3b_expert_off")
    log(f"[D-off] nav={nav_items2}")

    # ═══ E. AC-T5② 两处入口统一跳 ?cat=access（evidence ④） ═══
    page.goto(BASE, wait_until="networkidle"); page.wait_for_timeout(500)
    tip = page.get_attribute(".status-engine", "title")
    log(f"[E] footer hover title={tip}")
    page.locator(".status-engine").click(); page.wait_for_timeout(600)
    url_footer = page.url
    assert "cat=access" in url_footer, url_footer
    shot(page, "e4a_footer_jump_cat_access")
    page.goto(BASE, wait_until="networkidle"); page.wait_for_timeout(500)
    page.locator(".engine-badge").click(); page.wait_for_timeout(600)
    url_badge = page.url
    assert "cat=access" in url_badge, url_badge
    shot(page, "e4b_badge_jump_cat_access")
    log(f"[E] footer跳转={url_footer} | badge跳转={url_badge}")

    # ═══ F. D2 toast：byok + prefer_subscription → 路由切换显性告知一次且仅一次 ═══
    st["logged_in"] = True
    st["prefer_subscription"] = True
    st["llm"]["api_key_set"] = True
    st["engine_mode"] = "direct"
    page.goto(BASE, wait_until="networkidle")
    set_mock_state(page, "byok")
    page.reload(wait_until="networkidle")
    page.wait_for_selector(".toast.is-visible", timeout=6000)
    toast_text = page.inner_text(".toast")
    assert "平台额度" in toast_text, toast_text
    shot(page, "AC-T5-03_d2_route_override_toast")
    log(f"[F] toast=「{toast_text}」")
    page.wait_for_timeout(3400)  # toast 淡出
    page.reload(wait_until="networkidle"); page.wait_for_timeout(800)
    visible_again = page.locator(".toast.is-visible").count() > 0 and "平台额度" in page.inner_text(".toast")
    assert not visible_again, "toast 重复出现（判重失效）"
    log("[F] reload 后 toast 未再出现（一次且仅一次 ✓）")
    log(f"[F] byok footer={footer_text(page)}")

    # ═══ G. AC-T5① 托管就绪（剩余 n）文案 + 徽章节奏 ═══
    set_mock_state(page, "hosted")
    page.reload(wait_until="networkidle")
    ft = footer_text(page)
    assert "托管就绪" in ft and "剩余" in ft, ft
    log(f"[G] footer=「{ft}」")
    shot(page, "AC-T5-02_hosted_ready_remaining")
    badge = page.inner_text(".engine-badge")
    log(f"[G] topbar badge=「{badge}」")

    # ═══ H. 声纹 D3：主视图无独立「声纹服务」区块（简单模式） ═══
    page.goto(BASE + "/settings", wait_until="networkidle"); page.wait_for_timeout(500)
    body = page.inner_text("body")
    assert "声纹服务" in page.inner_text(".access-cards"), "卡片折叠区应含声纹入口"
    h2_visible = [x.strip() for x in page.locator(".settings-title").element_handles()
                  if (t := x.inner_text().strip()) and x.is_visible()]
    assert "声纹服务" not in h2_visible, f"主视图仍可见独立声纹服务入口: {h2_visible}"
    log("[H] 主视图无独立「声纹服务」区块 ✓（声纹在卡片折叠区）")

    ctx.close(); browser.close()

with open(os.path.join(OUT, "selftest-run.log"), "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines) + "\n")
print("ALL SELF-TEST ASSERTIONS PASSED")
