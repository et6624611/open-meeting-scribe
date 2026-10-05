/**
 * WP-3 选区书面化 浏览器实测（playwright-core，连本机 Chrome）
 * 验证：划词 → 工具条按钮 → 切书面 tab → 409 错误提示；以及 upsert 语义。
 * 用法: node scripts/test-wp3-selection.mjs
 */
import { chromium } from 'playwright-core'

const TASK_ID = 'fc1462c1-d95e-40ca-b397-ab2698de6d25'
const BASE = 'http://localhost:5173'

async function main() {
  const browser = await chromium.launch({
    headless: false,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  })
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })

  await page.goto(`${BASE}/meeting/${TASK_ID}`)
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  // Step 1: 切到「转写」tab
  const tabInfo = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.gen-tab')]
    const target = btns.find(b => /转写|Transcript/i.test(b.textContent || ''))
    if (target) target.click()
    return { count: btns.length, found: !!target, labels: btns.map(b => b.textContent?.trim()) }
  })
  console.log('STEP1 tabs:', JSON.stringify(tabInfo))
  await page.waitForTimeout(1500)

  const lineCount = await page.evaluate(() => document.querySelectorAll('.ts-line').length)
  console.log('STEP1 ts-line count:', lineCount)
  if (!lineCount) throw new Error('no transcript lines rendered')

  // Step 2: 模拟划词选中前 3 句
  const selInfo = await page.evaluate(() => {
    const spans = [...document.querySelectorAll('.ts-line .txt')].slice(0, 3)
    if (!spans.length) return { ok: false }
    const r = document.createRange()
    r.setStartBefore(spans[0])
    r.setEndAfter(spans[spans.length - 1])
    const s = window.getSelection()
    s.removeAllRanges()
    s.addRange(r)
    // mouseup 必须派在选区内真实元素上（handler 会用 e.target.closest）
    spans[spans.length - 1].dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    return { ok: true, chars: s.toString().length }
  })
  console.log('STEP2 selection:', JSON.stringify(selInfo))
  await page.waitForTimeout(800)

  // Step 3: 检查工具栏与书面化按钮
  const toolbar = await page.evaluate(() => {
    const tb = document.querySelector('.selection-toolbar.is-visible')
    if (!tb) return { visible: false }
    const btns = [...tb.querySelectorAll('.sel-tool-btn')].map(b => b.textContent?.trim())
    const formalBtn = tb.querySelector('.sel-formal-btn')
    return { visible: true, btns, formalText: formalBtn?.textContent?.trim() || null, disabled: formalBtn?.disabled }
  })
  console.log('STEP3 toolbar:', JSON.stringify(toolbar))
  if (!toolbar.formalText) throw new Error('formalize button missing in toolbar')

  // Step 4: 点击书面化按钮
  await page.evaluate(() => {
    const btn = document.querySelector('.selection-toolbar .sel-formal-btn')
    if (btn && !btn.disabled) btn.click()
  })
  await page.waitForTimeout(1500)

  // Step 5: 检查面板状态（三层选择器已改为 tab 栏右侧下拉，看触发钮文案）
  const panel = await page.evaluate(() => {
    const activeTab = document.querySelector('.gen-layer-trigger')?.textContent?.trim()
    const idle = !!document.querySelector('.gen-formal-idle')
    const errEl = document.querySelector('.gen-formal-action-err')
    return { activeTab, idleShown: idle, errorText: errEl?.textContent?.trim() || null }
  })
  console.log('STEP5 panel:', JSON.stringify(panel))

  // Step 6: 点「生成」按钮再确认错误
  await page.evaluate(() => {
    const b = document.querySelector('.gen-formal-btn.is-primary')
    if (b) b.click()
  })
  await page.waitForTimeout(1500)
  const panel2 = await page.evaluate(() => ({
    errorText: document.querySelector('.gen-formal-action-err')?.textContent?.trim() || null,
  }))
  console.log('STEP6 after full generate click:', JSON.stringify(panel2))

  console.log('CONSOLE ERRORS:', errors.length ? errors.slice(0, 5) : 'none')
  await browser.close()
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1) })
