/**
 * 统一进度面板卡片化 浏览器实测（playwright-core，连本机 Chrome）
 * mock /api/tasks/{id} 三态：processing 进行态卡片 / failed compact 行 / backfill 章节补生成卡片
 * 用法: node scripts/test-progress-card.mjs
 */
import { chromium } from 'playwright-core'

const TASK_ID = 'mock-progress-card'
const BASE = 'http://localhost:5173'

function mockTask(overrides) {
  return {
    task_id: TASK_ID,
    status: 'processing',
    progress: 75,
    message: '',
    audio_name: 'mock.m4a',
    audio_path: '',
    audio_duration: 600,
    speaker_count: 2,
    summary: null,
    output_path: null,
    created_at: new Date().toISOString(),
    meeting_date: null,
    error: null,
    error_category: null,
    error_suggestion: null,
    failed_stage: null,
    retry_count: 0,
    speaker_mapping: {},
    dialogue: [],
    normalized_path: null,
    voiceprint_match: [],
    voiceprint_auto_mapping: {},
    speaker_uuid_mapping: {},
    roster: [],
    title: '进度卡片实测',
    todos: [],
    chapters: [],
    project_id: null,
    archived_at: null,
    ...overrides,
  }
}

async function snap(page, name) {
  await page.screenshot({ path: `/tmp/progress-card-${name}.png` })
}

async function main() {
  const browser = await chromium.launch({
    headless: false,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  })
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })

  let scenario = 'processing'
  await page.route(`**/api/tasks/${TASK_ID}**`, route => {
    if (scenario === 'processing') {
      route.fulfill({ json: mockTask({ status: 'processing', progress: 75 }) })
    } else if (scenario === 'failed') {
      route.fulfill({ json: mockTask({ status: 'failed', progress: 87, failed_stage: 'summarize', error: 'mock llm error', error_category: 'transient', error_suggestion: '稍后重试' }) })
    } else {
      // backfill: completed、有转写、无章节
      route.fulfill({ json: mockTask({
        status: 'completed', progress: 100,
        dialogue: [
          { speaker_id: 1, text: '第一句', sentences: [{ sentence_id: 1, begin_time: 0, end_time: 1000, text: '第一句', speaker_id: 1 }] },
          { speaker_id: 2, text: '第二句', sentences: [{ sentence_id: 2, begin_time: 1000, end_time: 2000, text: '第二句', speaker_id: 2 }] },
        ],
        speaker_mapping: { '1': '张三', '2': '李四' },
      }) })
    }
  })

  // ── 场景 1：processing 进行态卡片 ──
  await page.goto(`${BASE}/meeting/${TASK_ID}`)
  await page.waitForLoadState('load')
  await page.waitForTimeout(2500)

  const s1 = await page.evaluate(() => {
    const panel = document.querySelector('.tp-panel')
    if (!panel) return { ok: false }
    return {
      ok: true,
      hasCardBase: panel.classList.contains('rec-formal-lock'),
      hasSpinner: !!panel.querySelector('.gen-formal-spinner'),
      title: panel.querySelector('.rec-formal-lock-title')?.textContent?.trim() || null,
      desc: panel.querySelector('.tp-meta-row')?.textContent?.replace(/\s+/g, ' ').trim() || null,
      hasBar: !!panel.querySelector('.tp-bar[role="progressbar"]'),
      barIsThin: !!panel.querySelector('.gen-formal-bar'),
      noOldStepper: !document.querySelector('.tp-steps'),
      reassure: panel.querySelector('.tp-reassure')?.textContent?.trim() || null,
    }
  })
  console.log('S1 processing card:', JSON.stringify(s1, null, 2))
  await snap(page, 's1-processing')
  if (!s1.ok || !s1.hasCardBase || !s1.hasSpinner || !s1.noOldStepper || !s1.barIsThin) throw new Error('S1 assertion failed')
  if (!s1.desc || !/Step 2 of 4|第 2\/4 步/.test(s1.desc)) throw new Error('S1 step text missing')

  // ── 场景 2：failed 整页失败卡片 + compact 行 ──
  scenario = 'failed'
  await page.goto(`${BASE}/meeting/${TASK_ID}`)
  await page.waitForLoadState('load')
  await page.waitForTimeout(2000)

  const s2 = await page.evaluate(() => ({
    compactCaption: document.querySelector('.tp-compact-caption')?.textContent?.replace(/\s+/g, ' ').trim() || null,
    failureTitle: document.querySelector('.gen-failure-title')?.textContent?.trim() || null,
    noFullPanel: !document.querySelector('.tp-panel'),
  }))
  console.log('S2 failed compact:', JSON.stringify(s2, null, 2))
  await snap(page, 's2-failed')
  if (!s2.compactCaption) throw new Error('S2 compact caption missing')

  // ── 场景 3：backfill 章节补生成卡片 ──
  scenario = 'backfill'
  await page.goto(`${BASE}/meeting/${TASK_ID}`)
  await page.waitForLoadState('load')
  await page.waitForTimeout(2500)
  // 切到转写 tab
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.gen-tab')]
    const target = btns.find(b => /转写|Transcript/i.test(b.textContent || ''))
    if (target) target.click()
  })
  await page.waitForTimeout(1500)

  const s3 = await page.evaluate(() => {
    const wrap = document.querySelector('.chapter-loading.is-panel')
    const panel = wrap?.querySelector('.tp-panel')
    return {
      wrapperPlain: !!wrap,
      hasPanel: !!panel,
      title: panel?.querySelector('.rec-formal-lock-title')?.textContent?.trim() || null,
      hasSpinner: !!panel?.querySelector('.gen-formal-spinner'),
      noBar: !panel?.querySelector('.tp-bar'),
    }
  })
  console.log('S3 backfill card:', JSON.stringify(s3, null, 2))
  await snap(page, 's3-backfill')
  if (!s3.wrapperPlain || !s3.hasPanel || !s3.hasSpinner) throw new Error('S3 assertion failed')

  console.log('CONSOLE ERRORS:', errors.length ? errors.slice(0, 5) : 'none')
  console.log('ALL PASS')
  await browser.close()
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1) })
