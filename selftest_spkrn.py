# REQ-SPK-RN T2 前端自测取证脚本：Playwright + 全量 /api mock（零真实后端接触）
# 证据输出: qa-evidence/req-spk-rn-t2/
# 断言面：AC-1(H1 全站无占位串)/AC-2(真名一致)/AC-3(筛选可用)/AC-7(空名不建档)/AC-8(双侧同正则)
import json
import os
import re

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5199"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-evidence", "req-spk-rn-t2")
os.makedirs(OUT, exist_ok=True)

FAILS = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name} {detail}")
    if not cond:
        FAILS.append(name)


def shot(page, name):
    page.screenshot(path=os.path.join(OUT, name + ".png"))
    print(f"[shot] {name}")


# ── 测试数据：一条含四种占位形态 + 一真名的已完成任务 ──
TASK_ID = "t1-spkrn-task"
DIALOGUE = [
    {"speaker_id": 0, "text": "预算维持120万", "sentences": [
        {"sentence_id": 0, "speaker_id": 0, "text": "预算维持120万", "begin_time": 0, "end_time": 5000}]},
    {"speaker_id": 1, "text": "我同意该安排", "sentences": [
        {"sentence_id": 1, "speaker_id": 1, "text": "我同意该安排", "begin_time": 5000, "end_time": 9000}]},
    {"speaker_id": 2, "text": "需要再确认", "sentences": [
        {"sentence_id": 2, "speaker_id": 2, "text": "需要再确认", "begin_time": 9000, "end_time": 12000}]},
    {"speaker_id": 3, "text": "供应商那边我去谈", "sentences": [
        {"sentence_id": 3, "speaker_id": 3, "text": "供应商那边我去谈", "begin_time": 12000, "end_time": 16000}]},
    {"speaker_id": 4, "text": "好", "sentences": [
        {"sentence_id": 4, "speaker_id": 4, "text": "好", "begin_time": 16000, "end_time": 18000}]},
]
TASK = {
    "task_id": TASK_ID,
    "title": "实名化验收会",
    "audio_name": "spkrn.wav",
    "status": "completed",
    "progress": 100,
    "summary": "## 一、主要结论\n会议明确了预算安排。",
    "dialogue": DIALOGUE,
    "chapters": [],
    "speaker_mapping": {"0": "Speaker 1", "1": "张三", "2": "说话人2", "3": "Speaker One", "4": "发言人 3"},
    "speaker_uuid_mapping": {},
    "speaker_count": 5,
    "audio_duration": 18,
    "meeting_date": "2026-09-25",
    "created_at": "2026-09-25T09:00:00",
    "source": "upload",
    "archived": False,
}
SPEAKERS = [
    {"id": "spk-real", "name": "李四", "role": "财务", "linked_user_id": None},
    {"id": "spk-polluted", "name": "Speaker 5", "role": "", "linked_user_id": None},
]


def handle(route):
    url = route.request.url
    path = url.split("?")[0].replace(BASE, "")
    m = route.request.method
    # 精确 mock 面
    if path == "/api/tasks" and m == "GET":
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"tasks": [TASK]}, ensure_ascii=False))
    if path == f"/api/tasks/{TASK_ID}" and m == "GET":
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(TASK, ensure_ascii=False))
    if path == "/api/speakers" and m == "GET":
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"speakers": SPEAKERS}, ensure_ascii=False))
    if path == "/api/projects" and m == "GET":
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"projects": []}))
    if path.startswith("/api/tasks/") and "/sync-status" in path:
        return route.fulfill(status=200, content_type="application/json", body='{"can_sync": false}')
    # 其余一律 404 吞掉——绝不 fallback，防穿透真实后端（DC-R2-a 教训条款）
    return route.fulfill(status=404, content_type="application/json", body='{"detail":"mocked"}')


# ── AC-8：前端判定器与后端正则 同源比对（import 真实 pattern + 钉死矩阵） ──
import sys
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
from core.speakers import PLACEHOLDER_NAME_RE as BE_RE  # 后端真实编译产物

WORDS = "One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten"
expected_be = rf"^\s*(?:Speaker\s+\d+|Speaker\s+(?:{WORDS})|说话人\s*\d+|发言人\s*\d+)\s*$"
check("AC-8 后端正则=钉死口径", BE_RE.pattern == expected_be, BE_RE.pattern[:60])
ts_src = open(os.path.join(_ROOT, "frontend/src/utils/speakerDisplay.ts"), encoding="utf-8").read()
# 前端模板串与后端同构：同源词表 + 同一字符序列（\s+ 严格空格）
ts_ok = ("PLACEHOLDER_WORDS = 'One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten'" in ts_src
         and r"Speaker\\s+\\d+" in ts_src and r"说话人\\s*\\d+" in ts_src and r"发言人\\s*\\d+" in ts_src)
check("AC-8 前端判定器=同源超集", ts_ok, "speakerDisplay.ts 结构一致")
# 行为级：后端真实正则对钉死矩阵逐条判定（含空串前置判定，与 is_unnamed_speaker 语义对齐）
AC8_MATRIX = {
    "Speaker 1": False, "Speaker Two": False, "SPEAKER nine": False,
    "说话人5": False, "发言人 12": False, "": False, "  ": False,
    "王五": True, "Speaker 4 王五": True, "发言人2（待确认）": True,
}


def be_is_named(s):
    from core.speakers import is_unnamed_speaker
    return not is_unnamed_speaker(s)


mism = [s for s, is_named in AC8_MATRIX.items() if be_is_named(s) != is_named]
check("AC-8 后端对钉死矩阵判定无漂移", not mism, str(mism))

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    # 钉住应用 locale=zh-CN（仅首次；en 段自行覆盖后导航不重置）
    ctx.add_init_script("try{if(!localStorage.getItem('locale'))localStorage.setItem('locale','zh-CN')}catch(e){}")
    # 只拦真实 API 前缀（BASE+/api/），不碰 vite 源码模块 /src/api/*.ts
    ctx.route(BASE + "/api/**", handle)
    page = ctx.new_page()
    # H1 违例串：同一行内（水平空白）的编号占位；排除「说话人\n2」这类标题+独立计数跨行拼接版式
    H1_RE = re.compile(r"Speaker[ \u3000]*\d+|Speaker[ \u3000]+(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\b|说话人[ \u3000]*\d+|发言人[ \u3000]*\d+", re.IGNORECASE)

    # ── 1. 会议库页：H1 扫描 + 下拉口径 + TaskCard 区 ──
    page.goto(BASE + "/library", wait_until="networkidle")
    page.wait_for_timeout(1200)
    body = page.inner_text("body")
    hits = H1_RE.findall(body)
    check("AC-1/H1 库页 body 无占位串", not hits, str(hits[:5]))
    check("AC-2 库页真名「张三」正常显示", "张三" in body)
    opts = page.locator(".lib-speaker-select option").all_inner_texts()
    check("AC-3 下拉含「未识别」特殊项", "未识别" in opts, str(opts))
    check("AC-3 下拉枚举真名", "张三" in opts, str(opts))
    check("AC-3/H1 下拉零占位项", not [o for o in opts if H1_RE.search(o)], str(opts))
    # 选「未识别」→ 任务命中
    page.select_option(".lib-speaker-select", label="未识别")
    page.wait_for_timeout(600)
    check("AC-3 「未识别」筛选命中含占位任务", page.locator(".lib-spk-label, .cell-speakers").count() > 0 and "实名化验收会" in page.inner_text("body"))
    shot(page, "01_library_unid_filter")

    # ── 2. 会议详情页：转写行首 + 说话人区聚合 ──
    page.goto(BASE + f"/meeting/{TASK_ID}", wait_until="networkidle")
    page.wait_for_timeout(1500)
    body2 = page.inner_text("body")
    hits2 = H1_RE.findall(body2)
    check("AC-1/H1 会议页无占位串", not hits2, str(hits2[:5]))
    check("AC-2 会议页真名在位", "张三" in body2)
    check("AC-1 转写行首未识别态", "未识别" in body2)
    shot(page, "02_meeting_page")

    # ── 3. 说话人管理页：占位档案灰标「未识别」，真名不受影响 ──
    page.goto(BASE + "/speakers", wait_until="networkidle")
    page.wait_for_timeout(1200)
    body3 = page.inner_text("body")
    check("AC-1/H1 管理页无占位串露出", not H1_RE.findall(body3), str(H1_RE.findall(body3)[:3]))
    check("L5 占位档案显示「未识别」", "未识别" in body3 and "李四" in body3)
    check("L5 占位档案灰标 class", page.locator(".spk-name.is-unid").count() >= 1)
    shot(page, "03_speakers_gray_label")

    # ── 4. 英文 locale：无编号占位、Unidentified 在位 ──
    page.evaluate("() => localStorage.setItem('locale','en')")
    page.goto(BASE + "/library", wait_until="domcontentloaded")
    page.goto(BASE + "/library", wait_until="networkidle")
    page.wait_for_timeout(1000)
    body_en = page.inner_text("body")
    check("AC-5 en 库页无占位串", not H1_RE.findall(body_en), str(H1_RE.findall(body_en)[:3]))
    opts_en = page.locator(".lib-speaker-select option").all_inner_texts()
    check("AC-5 en「Unidentified」在位", "Unidentified" in opts_en, str(opts_en))
    shot(page, "04_library_en")
    browser.close()

# ── 5. AC-7 源头守护：createAndBind 空名守卫（源码 grep 级） ──
binding_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend/src/composables/useSpeakerBinding.ts"), encoding="utf-8").read()
check("AC-7 空名建档必填守卫", "name_required" in binding_src and "if (!name || normalizeSpeakerName(name) === '')" in binding_src)

with open(os.path.join(OUT, "selftest-run.log"), "w") as f:
    f.write(json.dumps({"fails": FAILS}, ensure_ascii=False))

print(f"\n==== RESULT: {'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + str(FAILS)}")
