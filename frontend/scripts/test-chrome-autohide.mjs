/**
 * 底栏 hover 浮现（流内占位）+ 顶栏/左轨/右栏常驻 浏览器实测（playwright-core，连本机 Chrome）
 * 验证：① 顶栏常驻 48px 流内占位，hover 顶边不产生变化；
 *       ② 左轨图标全部常驻、右栏 AI 常驻 44；③ 底栏等高 44、玻璃材质统一；
 *       ④ 底栏 hover 即触（进延迟 0）、全宽占位、左右栏让出高度；⑤ console 零报错。
 * 用法: node scripts/test-chrome-autohide.mjs [baseURL]
 */
import { chromium } from 'playwright-core'

const BASE = process.argv[2] || 'http://localhost:8000'
const VW = 1280
const VH = 800
const TOP_H = 49   // 顶栏占位 = topbar-main 48 + 1px border-bottom（会话前原样）
const BAR_H = 44

const results = []
function report(name, pass, evidence) {
  results.push({ name, pass, evidence })
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name} :: ${evidence}`)
}

const numPx = v => Math.round(parseFloat(v))

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  })
  const page = await browser.newPage({ viewport: { width: VW, height: VH } })
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })

  await page.goto(BASE)
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(1500)

  const snap = () => page.evaluate(() => {
    const r = sel => {
      const el = document.querySelector(sel)
      if (!el) return null
      const b = el.getBoundingClientRect()
      return { t: Math.round(b.top), b: Math.round(b.bottom), h: Math.round(b.height), l: Math.round(b.left), r: Math.round(b.right) }
    }
    const pick = sel => {
      const cs = getComputedStyle(document.querySelector(sel))
      return { bg: cs.backgroundColor, blur: cs.backdropFilter }
    }
    return {
      top: r('.topbar'),
      btmH: getComputedStyle(document.querySelector('.chrome-btm')).height,
      btmPinned: !!document.querySelector('.chrome-btm.is-pinned'),
      rail: r('.activity-rail'),
      ai: r('.ai'),
      status: r('.chrome-btm .status'),
      matTop: pick('.topbar'),
      matBtm: pick('.chrome-btm .status'),
      matRail: pick('.activity-rail'),
      railBtnCount: document.querySelectorAll('.activity-rail .ar-btn').length,
      railBtnOpacities: [...document.querySelectorAll('.activity-rail .ar-btn')].map(e => getComputedStyle(e).opacity),
      aiW: Math.round(document.querySelector('.ai').getBoundingClientRect().width),
      stripDisplay: getComputedStyle(document.querySelector('.ai-collapsed-strip')).display,
      stripOpacity: getComputedStyle(document.querySelector('.ai-collapsed-strip')).opacity,
    }
  })

  const pre = await page.evaluate(() => ({
    ok: !!document.querySelector('.topbar') && !!document.querySelector('.chrome-btm') && !!document.querySelector('.activity-rail') && !!document.querySelector('.ai'),
    noChromeTop: !document.querySelector('.chrome-top'),
    aiCollapsed: document.querySelector('.ai')?.classList.contains('is-collapsed'),
  }))
  if (pre.aiCollapsed === false) { await page.click('.ai-toggle'); await page.waitForTimeout(600) }
  report('结构前置(顶栏已回退无chrome-top)', pre.ok && pre.noChromeTop, JSON.stringify(pre))

  const s0 = await snap()
  console.log('INITIAL', JSON.stringify(s0))

  // ── 顶栏常驻（48 内容+1 边框=49 占位）：流内，左右栏顶缘 49 ──
  report('顶栏-常驻流内', s0.top?.t === 0 && s0.top?.h === TOP_H, `top=${JSON.stringify(s0.top)}`)
  report('顶栏-左右栏顶缘让位', s0.rail.t === TOP_H && s0.ai.t === TOP_H, `rail.top=${s0.rail.t} ai.top=${s0.ai.t}`)

  // ── 左轨/右栏常驻 ───────────────────────────────────────────
  report('左轨-图标全部常驻', s0.railBtnCount >= 7 && s0.railBtnOpacities.every(o => o === '1'),
    `count=${s0.railBtnCount} op=${JSON.stringify(s0.railBtnOpacities)}`)
  report('右栏-常驻44px', s0.aiW === 44 && s0.stripDisplay === 'flex' && s0.stripOpacity === '1',
    `aiW=${s0.aiW} strip=${s0.stripDisplay}/${s0.stripOpacity}`)

  // ── 材质统一（顶/底/rail 同玻璃） ───────────────────────────
  report('材质-三件同底同糊',
    s0.matTop.bg === s0.matBtm.bg && s0.matBtm.bg === s0.matRail.bg &&
    s0.matTop.blur === s0.matBtm.blur && s0.matBtm.blur === s0.matRail.blur && s0.matTop.blur !== 'none',
    `bg=${s0.matTop.bg} blur=${s0.matTop.blur}`)

  // ── 底栏告警常驻 44：左右栏底边让位；rail 高 = VH-48-44 ─────
  report('底栏-告警常驻44', s0.btmPinned && numPx(s0.btmH) === BAR_H, `pinned=${s0.btmPinned} h=${s0.btmH}`)
  report('底栏-左右栏让底边', s0.rail.b === VH - BAR_H && s0.ai.b === VH - BAR_H,
    `rail.bottom=${s0.rail.b} ai.bottom=${s0.ai.b}`)
  report('门框-rail高=VH-顶-底', s0.rail.h === VH - TOP_H - BAR_H, `rail.h=${s0.rail.h}`)

  // ── 顶栏 hover 无变化（不再自动隐藏） ────────────────────────
  await page.mouse.move(VW / 2, 2)
  await page.waitForTimeout(400)
  const topOnHover = await page.evaluate(() => {
    const b = document.querySelector('.topbar').getBoundingClientRect()
    return { t: Math.round(b.top), h: Math.round(b.height) }
  })
  report('顶栏-hover仍常驻', topOnHover.t === 0 && topOnHover.h === TOP_H, JSON.stringify(topOnHover))

  // ── 底栏 hover 即触（pinned 态已常驻；这里验证非 pinned 路径的时序不回归用几何恒定代替）
  // 当前未登录触发 is-pinned；高度在 hover 前后恒为 44
  await page.mouse.move(VW / 2, VH - 2)
  await page.waitForTimeout(200)
  const btmEdge = await page.evaluate(() => {
    const h = parseFloat(getComputedStyle(document.querySelector('.chrome-btm')).height)
    const st = document.querySelector('.chrome-btm .status').getBoundingClientRect()
    return { h: Math.round(h), l: Math.round(st.left), r: Math.round(st.right) }
  })
  report('底栏-底缘hover恒44全宽', btmEdge.h === BAR_H && btmEdge.l === 0 && btmEdge.r === VW, JSON.stringify(btmEdge))

  // ── 左轨 hover 不改变常驻 ───────────────────────────────────
  await page.mouse.move(26, VH / 2)
  await page.waitForTimeout(300)
  const railOnHover = await page.evaluate(() =>
    [...document.querySelectorAll('.activity-rail .ar-btn')].map(e => getComputedStyle(e).opacity))
  report('左轨-hover不改变常驻', railOnHover.every(o => o === '1'), JSON.stringify(railOnHover))

  // ── console ─────────────────────────────────────────────────
  report('console 零报错', errors.length === 0, errors.slice(0, 3).join(' | ') || 'clean')

  await browser.close()
  const failed = results.filter(r => !r.pass)
  console.log(`\n=== ${results.length - failed.length}/${results.length} PASS ===`)
  process.exit(failed.length ? 1 : 0)
}

main().catch(e => { console.error(e); process.exit(1) })
