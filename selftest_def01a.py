# DEF-DEVICE-01-A 前端自测取证脚本：有状态 mock 录音设备接口，断言 POST 审计序列
# 证据输出: qa-evidence/def-device-01/
import json, os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-evidence", "def-device-01")
os.makedirs(OUT, exist_ok=True)

DEVICES = [
    {"index": 0, "name": "MicA-USB 麦克风", "type": "avfoundation"},
    {"index": 1, "name": "MicB-内置麦克风", "type": "avfoundation"},
    {"index": 2, "name": "MicC-耳机一体", "type": "avfoundation"},
]
st = {"device": ""}          # 后端「当前值」——复现现场：空串
posts = []                   # POST /api/record/device 审计（body.device 序列）

FAILS = []
def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAILS.append(name)

def js_of(page, sel):  # 当前下拉框显示值
    return page.eval_on_selector(sel, "el => el.value")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script("localStorage.setItem('locale','zh-CN')")

    def handle(route):
        url = route.request.url.split("?")[0]
        if url == BASE + "/api/record/devices":
            body = {"devices": DEVICES, "current_device": st["device"], "platform": "darwin",
                    "auto_detect": not st["device"], "ffmpeg_available": True}
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False))
        if url == BASE + "/api/record/device" and route.request.method == "POST":
            dev = json.loads(route.request.post_data or "{}").get("device", "<none>")
            posts.append(dev)
            st["device"] = dev
            return route.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"device": dev, "auto_detect": not dev}))
        if url == BASE + "/auth/me":
            return route.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"id": "selftest", "phone": "138****0000", "role": "admin", "is_admin": True, "logged_in": True}))
        if url == BASE + "/auth/privacy-consent":
            return route.fulfill(status=200, content_type="application/json", body='{"granted": true}')
        return route.fallback()

    ctx.route(BASE + "/api/**", handle)
    ctx.route(BASE + "/auth/**", handle)
    page = ctx.new_page()
    SEL = ".settings-section:has(h2:text('录音设备')) select"

    # ── 场景一（AC①+AC③）：后端当前值为空串 → 首次真实选择必须立即 POST；加载/回显零 POST ──
    page.goto(BASE + "/settings?cat=transcription", wait_until="networkidle")
    page.wait_for_selector(SEL)
    page.screenshot(path=f"{OUT}/dev01_p1_before_first_select.png")
    check("空值态加载零 POST", posts == [], str(posts))
    page.select_option(SEL, "MicA-USB 麦克风")
    page.wait_for_timeout(600)
    check("AC① 空值态首次选择即发 POST", posts == ["MicA-USB 麦克风"], str(posts))

    # 重进页面：回显=所选设备（AC① 后半）且回显赋值不触发冗余 POST（AC③）
    page.goto(BASE + "/settings?cat=transcription", wait_until="networkidle")
    page.wait_for_selector(SEL)
    page.wait_for_timeout(600)
    check("AC① 重进页面回显=所选设备", js_of(page, SEL) == "MicA-USB 麦克风", js_of(page, SEL))
    check("AC③ 回显赋值零冗余 POST", posts == ["MicA-USB 麦克风"], str(posts))
    page.screenshot(path=f"{OUT}/dev01_p2_reload_echo_ok.png")

    # ── 场景二（AC②）：连续切换每次都落 POST ──
    page.select_option(SEL, "MicB-内置麦克风"); page.wait_for_timeout(400)
    page.select_option(SEL, ""); page.wait_for_timeout(400)            # 自动检测 = 空串
    page.select_option(SEL, "MicC-耳机一体"); page.wait_for_timeout(400)
    check("AC② 连续切换每次 POST", posts == ["MicA-USB 麦克风", "MicB-内置麦克风", "", "MicC-耳机一体"], str(posts))
    page.screenshot(path=f"{OUT}/dev01_p3_multi_switch_posts.png")

    # 再重进：新逻辑下回显值再次被显式标志放行，仍零额外 POST
    page.goto(BASE + "/settings?cat=transcription", wait_until="networkidle")
    page.wait_for_timeout(600)
    check("AC③ 二次回显仍零冗余 POST", len(posts) == 4 and js_of(page, SEL) == "MicC-耳机一体", f"posts={len(posts)} val={js_of(page, SEL)}")

    # ── 场景三：手动点「刷新」按钮触发的回显赋值同样不得发 POST ──
    st["device"] = "MicB-内置麦克风"
    page.click(".settings-section:has(h2:text('录音设备')) button:has-text('刷新设备列表')")
    page.wait_for_timeout(800)
    check("刷新重载回显零 POST", len(posts) == 4, str(posts))

    browser.close()

with open(os.path.join(OUT, "post-audit.json"), "w") as f:
    json.dump({"expected_sequence": ["MicA-USB 麦克风", "MicB-内置麦克风", "", "MicC-耳机一体"], "actual_posts": posts}, f, ensure_ascii=False, indent=2)

print("\n==== RESULT:", "ALL PASSED" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}")
raise SystemExit(0 if not FAILS else 1)
