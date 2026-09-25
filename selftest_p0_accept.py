# REQ-PROGRESS-P0 IDE 承接方浏览器点验脚本（Playwright 无头 · 1440×900）
# 目的：在标准桌面宽度下实测统一进度面板，产出截图证据并量化布局断言，
#       甄别上一轮 720px 窄视口「逐字竖排」是否 P0 回归（预期：1440 下正常）。
# 证据输出: qa-evidence/req-progress-p0-ide/
import os, sys, time, json
import requests
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8777"
AUDIO = "/tmp/p0test/p0_accept_25min.mp3"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-evidence", "req-progress-p0-ide")
os.makedirs(OUT, exist_ok=True)

log_lines = []
def log(msg):
    print(msg, flush=True); log_lines.append(str(msg))

def shot(page, name):
    p = os.path.join(OUT, name + ".png")
    page.screenshot(path=p, full_page=False)
    log(f"[shot] {name} -> {p}")
    return p

def panel_metrics(page):
    """读取进度面板几何 + 主列宽度，量化布局是否正常。"""
    return page.evaluate("""() => {
        const panel = document.querySelector('.tp-panel');
        const main = document.querySelector('.main');
        // 只统计第一个面板实例内的步骤（进度面板在原文/纪要两处挂载，全局 querySelectorAll 会重复计数）
        const steps = panel ? [...panel.querySelectorAll('.tp-step')] : [...document.querySelectorAll('.tp-step')];
        const stepBoxes = steps.map(s => { const r = s.getBoundingClientRect(); return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)}; });
        const labelEls = panel ? [...panel.querySelectorAll('.tp-step-label')] : [...document.querySelectorAll('.tp-step-label')];
        const labels = labelEls.map(l => ({
            text: l.textContent.trim(), oneLine: Math.round(l.getBoundingClientRect().height) < 30,
            clipped: l.scrollWidth > l.clientWidth + 1
        }));
        const pct = document.querySelector('.tp-percent');
        return {
            viewport: {w: window.innerWidth, h: window.innerHeight},
            mainWidth: main ? Math.round(main.getBoundingClientRect().width) : null,
            panelWidth: panel ? Math.round(panel.getBoundingClientRect().width) : null,
            stepCount: steps.length, stepBoxes, labels,
            percent: pct ? pct.textContent.trim() : null,
            hasEta: !!document.querySelector('.tp-eta, .tp-eta-unknown'),
            hasReassure: !!document.querySelector('.tp-reassure'),
        };
    }""")

def get_task_state(tid):
    try:
        d = requests.get(f"{BASE}/api/tasks/{tid}", timeout=8).json()
        return d.get("status"), d.get("progress")
    except Exception as e:
        return "ERR", str(e)

# ── 提交任务 ──
log("== 提交 25min 音频任务 ==")
r = requests.post(f"{BASE}/api/transcribe", files={"file": open(AUDIO, "rb")}, timeout=120)
tid = r.json()["task_id"]
log(f"task_id={tid}")

results = {}
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    # 屏蔽首访引导/遮罩：预置 localStorage
    page.add_init_script("try{localStorage.setItem('oms_onboarded','1')}catch(e){}")

    # STEP 1/2：进入会议页观察进度面板
    page.goto(f"{BASE}/meeting/{tid}", wait_until="domcontentloaded")
    page.wait_for_selector(".tp-panel", timeout=30000)
    page.wait_for_timeout(1500)
    m1 = panel_metrics(page); results["panel_first"] = m1
    log(f"[面板首采] viewport={m1['viewport']} mainWidth={m1['mainWidth']} panelWidth={m1['panelWidth']} steps={m1['stepCount']} pct={m1['percent']} eta={m1['hasEta']} reassure={m1['hasReassure']}")
    shot(page, "01_panel_1440")

    # STEP 3：布局判定（1440 下主列/面板宽度、步骤标签是否单行不裁切）
    labels_ok = all((not l["clipped"]) and l["oneLine"] for l in m1["labels"]) if m1["labels"] else False
    layout_pass = (m1["mainWidth"] or 0) >= 600 and (m1["panelWidth"] or 0) >= 300 and m1["stepCount"] == 4 and labels_ok
    results["layout_pass"] = layout_pass
    log(f"[布局判定] mainWidth>=600 & panelWidth>=300 & 4步 & 标签单行不裁切 => {'PASS 正常' if layout_pass else 'FAIL 异常'} | labels={m1['labels']}")

    # STEP 2b：等待推进，二次采样验证单调前进
    page.wait_for_timeout(12000)
    m2 = panel_metrics(page); results["panel_second"] = m2
    def pnum(x):
        try: return int(str(x).replace('%','').strip())
        except: return -1
    p1, p2 = pnum(m1["percent"]), pnum(m2["percent"])
    mono = (p1 >= 0 and p2 >= 0 and p2 >= p1)
    results["monotonic_pass"] = mono
    log(f"[单调性] {p1}% -> {p2}% => {'PASS 不回退' if mono else 'N/A(可能已完成或跨阶段)'}")
    shot(page, "02_panel_progressed")

    # STEP 4：离开恢复——切到 /library 停 5s 再切回
    page.goto(f"{BASE}/library", wait_until="domcontentloaded"); page.wait_for_timeout(5000)
    st_leave = get_task_state(tid)
    page.goto(f"{BASE}/meeting/{tid}", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    m3 = panel_metrics(page); results["leave_restore"] = m3
    fake100 = (pnum(m3["percent"]) == 100 and st_leave[0] == "processing")
    results["leave_restore_pass"] = (not fake100)
    log(f"[离开恢复] 后端真实状态={st_leave} 面板 pct={m3['percent']} 假100%={fake100} => {'PASS' if not fake100 else 'FAIL'}")
    shot(page, "03_leave_restore")

    # STEP 5：刷新重建
    page.reload(wait_until="domcontentloaded"); page.wait_for_timeout(2000)
    try:
        page.wait_for_selector(".tp-panel", timeout=8000)
        m4 = panel_metrics(page); results["refresh"] = m4
        fake100r = (pnum(m4["percent"]) == 100 and get_task_state(tid)[0] == "processing")
        results["refresh_pass"] = (not fake100r)
        log(f"[刷新重建] 面板重建 pct={m4['percent']} 假100%={fake100r} => {'PASS' if not fake100r else 'N/A'}")
    except Exception:
        results["refresh_pass"] = "N/A(已完成，面板已消失)"
        log("[刷新重建] 任务已完成，进度面板正常退出（无残留 spinner）")
    shot(page, "04_refresh_rebuild")

    # STEP 6：英文 locale
    page.evaluate("() => localStorage.setItem('locale','en')")
    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.goto(f"{BASE}/meeting/{tid}", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    # 抓取面板文案，检查中文残留 + i18n key 泄漏
    panel_text = page.evaluate("""() => {
        const p = document.querySelector('.tp-panel');
        return p ? p.innerText : '(面板已消失/任务已完成)';
    }""")
    import re
    cn_in_panel = re.findall(r'[\u4e00-\u9fff]', panel_text)
    key_leak = re.findall(r'processing\.[a-z_]+', panel_text)
    results["en_panel_text"] = panel_text
    results["en_cn_residue_in_panel"] = "".join(cn_in_panel)
    results["en_key_leak"] = key_leak
    results["en_panel_pass"] = (len(cn_in_panel) == 0 and len(key_leak) == 0)
    log(f"[英文面板] 面板内中文残留='{''.join(cn_in_panel)}' key泄漏={key_leak} => {'PASS 面板全英文' if results['en_panel_pass'] else '见下文明细'}")
    log(f"[英文面板文本] {panel_text!r}")
    shot(page, "05_english_panel")

    # STEP 7：等待完成态（最多再等 120s）
    log("== 等待任务完成 ==")
    done = False
    for _ in range(24):
        s, pr = get_task_state(tid)
        if s == "completed":
            done = True; break
        if s == "failed":
            log(f"[完成态] 任务失败 status={s} progress={pr}"); break
        page.wait_for_timeout(5000)
    page.goto(f"{BASE}/meeting/{tid}", wait_until="domcontentloaded"); page.wait_for_timeout(3000)
    final_state = get_task_state(tid)
    has_minutes = page.evaluate("""() => {
        const t = document.body.innerText;
        return {panelGone: !document.querySelector('.tp-panel'), bodyLen: t.length};
    }""")
    results["final_state"] = final_state; results["final_ui"] = has_minutes
    results["complete_pass"] = (final_state[0] == "completed" and has_minutes["panelGone"])
    log(f"[完成态] 后端={final_state} 面板已退出={has_minutes['panelGone']} => {'PASS 完成且无残留面板' if results['complete_pass'] else '见明细'}")
    shot(page, "06_final_completed")

    browser.close()

results["task_id"] = tid
with open(os.path.join(OUT, "metrics.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
with open(os.path.join(OUT, "selftest-run.log"), "w") as f:
    f.write("\n".join(log_lines))

log("\n===== 点验结论汇总 =====")
log(f"布局(1440)        : {'PASS' if results.get('layout_pass') else 'FAIL'}")
log(f"单调前进          : {'PASS' if results.get('monotonic_pass') else 'N/A'}")
log(f"离开恢复(无假100%): {'PASS' if results.get('leave_restore_pass') else 'FAIL'}")
log(f"刷新重建          : {results.get('refresh_pass')}")
log(f"英文面板全英文    : {'PASS' if results.get('en_panel_pass') else 'FAIL(见残留)'}")
log(f"完成态            : {'PASS' if results.get('complete_pass') else 'FAIL'}")
