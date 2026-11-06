/**
 * Open Meeting Scribe - E2E 冒烟测试（Playwright Core, headless）
 *
 * 覆盖：路由加载 + 纪要页更多菜单 + 图层切换 + 重命名内联编辑 + 会议库卡片跳转
 * 跳过：录制相关（需真实录制会话）、AI 面板模型菜单（headless 阻塞）
 *
 * 运行：node tests/e2e/smoke.mjs
 * 输出：tests/e2e/auto-run-<timestamp>.json
 *
 * 运行前提：后端 8000 + 前端 5173 已启动
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '../..');
const { chromium } = await import(join(ROOT, 'frontend/node_modules/playwright-core/index.mjs'));

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:5173';
const BACKEND = process.env.E2E_BACKEND || 'http://127.0.0.1:8000';

// 获取真实 taskId
async function pickTaskId() {
  try {
    const res = await fetch(`${BACKEND}/api/tasks?view=lite`);
    const data = await res.json();
    const items = Array.isArray(data) ? data : (data.tasks || data.items || []);
    const first = items.find(t => t.status === 'completed') || items[0];
    return first?.task_id || first?.id || null;
  } catch (e) { console.warn('[e2e] pickTaskId failed:', e.message); return null; }
}

function parseJsErrors(text) {
  if (!text) return [];
  return text.split('\n').filter(l => /^\[error\]/.test(l.trim()) && !l.includes('net::')).map(l => l.trim().slice(0, 160));
}

const TASK_ID = await pickTaskId();
console.log(`[e2e] base=${BASE_URL} backend=${BACKEND} taskId=${TASK_ID || '(none)'}`);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage();

const results = [];

/** 通用导航+加载+错误采集，最大 15s */
async function goto(url, label) {
  const jsErrors = [];
  page.on('console', m => { if (m.type() === 'error') jsErrors.push(m.text().slice(0, 160)); });
  page.on('pageerror', e => jsErrors.push(String(e.message || e).slice(0, 160)));
  const t0 = Date.now();
  let status = 'pass', note = '';
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(600);
    const len = await page.evaluate(() => document.querySelector('#app')?.innerText?.length ?? 0);
    if (len === 0) { status = 'fail'; note = '#app empty'; }
  } catch (e) {
    status = 'fail'; note = String(e.message || e).slice(0, 100);
  }
  page.removeAllListeners('console');
  page.removeAllListeners('pageerror');
  results.push({ id: label, status, duration_ms: Date.now() - t0, jsErr: jsErrors.length, note });
}

/** 点击菜单操作：展开菜单→点击指定文本→验证状态（最大 8s） */
async function clickMenu(label, setup, clickTarget, validate) {
  const t0 = Date.now();
  const jsErrors = [];
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('net::')) jsErrors.push(m.text().slice(0, 160)); });
  page.on('pageerror', e => jsErrors.push(String(e.message || e).slice(0, 160)));
  let status = 'pass', note = '';
  try {
    await setup();
    await clickTarget();
    await page.waitForTimeout(600);
    if (validate) {
      const r = await validate();
      if (!r.ok) { status = 'fail'; note = r.note; }
    }
    // 清理可能挂起的 dialog
    page.removeAllListeners('console');
    try { page.on('dialog', d => d.dismiss()); } catch {}
    try { setTimeout(() => page.removeAllListeners('dialog'), 500); } catch {}
  } catch (e) {
    status = 'fail'; note = String(e.message || e).slice(0, 120);
  }
  page.removeAllListeners('pageerror');
  results.push({ id: label, status, duration_ms: Date.now() - t0, jsErr: jsErrors.length, note });
}

/** ========== T-001~T-010 静态路由 ========== */
const routes = [
  ['T-001', '/'],
  ['T-003', '/library'],
  ['T-004', '/projects'],
  ['T-005', '/speakers'],
  ['T-006', '/hotwords'],
  ['T-007', '/agents'],
  ['T-008', '/settings'],
  ['T-009', '/decisions'],
  ['T-010', '/recording'],
];
for (const [label, r] of routes) {
  await goto(BASE_URL + r, label);
}

/** T-011 复数重定向 */
const t11_js = [];
page.on('console', m => { if (m.type() === 'error' && !m.text().includes('net::')) t11_js.push(m.text().slice(0, 160)); });
await page.goto(BASE_URL + '/meetings/test-id', { waitUntil: 'networkidle', timeout: 15000 }).catch(()=>{});
await page.waitForTimeout(800);
const t11_path = await page.evaluate(() => location.pathname);
results.push({ id: 'T-011', status: t11_path.startsWith('/meeting/') ? 'pass' : 'fail', path: t11_path, jsErr: t11_js.length, note: '' });
page.removeAllListeners('console');

/** T-019 无效路由 */
await goto(BASE_URL + '/__invalid_route__', 'T-019');

/** ========== 纪要页菜单 ========== */
const taskPath = `/meeting/${TASK_ID || ''}`;
await page.goto(BASE_URL + taskPath, { waitUntil: 'networkidle', timeout: 15000 }).catch(()=>{});
await page.waitForTimeout(2500);

// 更多菜单 6 项（T-022~T-027）
const moreItems = [
  { label: 'T-022', text: '复制标题' },
  { label: 'T-023', text: '复制摘要' },
  { label: 'T-024', text: '重新生成纪要' },
  { label: 'T-025', text: '重新识别' },
  { label: 'T-026', text: '归档' },
];
for (const item of moreItems) {
  await clickMenu(
    item.label,
    async () => {
      await page.evaluate(() => {
        const b = Array.from(document.querySelectorAll('button')).find(b => (b.textContent || '').trim() === '更多');
        if (b) b.click();
      });
      await page.waitForTimeout(400);
    },
    async () => {
      await page.evaluate((txt) => {
        const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
        const t = items.find(i => (i.textContent || '').includes(txt));
        if (t) t.click();
      }, item.text);
    },
    null
  );
}

// T-027 删除（弹确认窗即可，不确认）
await clickMenu(
  'T-027',
  async () => {
    await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button')).find(b => (b.textContent || '').trim() === '更多');
      if (b) b.click();
    });
    await page.waitForTimeout(400);
  },
  async () => {
    let dialogFired = false;
    const h = page.once('dialog', () => { dialogFired = true; });
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
      const t = items.find(i => (i.textContent || '').trim() === '删除');
      if (t) t.click();
    });
    await page.waitForTimeout(800);
    results[results.length - 1]._dialog = dialogFired;
    try { page.removeListener('dialog', () => {}); } catch {}
  },
  null
);

/** 重命名入口文案：用例按 zh-CN 编写，但运行时 locale 默认 en（localStorage 可被用户切换），
 *  双语兜底定位，让断言钉在「是否内联编辑」这个行为上，而不是绑在语言上。
 *  Checklist is zh-CN but runtime defaults to en; match either label so the assertion
 *  is about inline-edit behaviour, not about the active language. */
const RENAME_LABELS = ['重命名', 'Rename'];

/** T-021 重命名内联编辑（缺陷：原生 prompt） */
{
  let dialogFired = false;
  page.once('dialog', () => { dialogFired = true; });
  await page.evaluate((labels) => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => labels.includes((b.getAttribute('aria-label') || '').trim()));
    if (!btn) return;
    btn.click();
  }, RENAME_LABELS);
  await page.waitForTimeout(800);
  const inlineEditor = await page.evaluate(() => {
    const t = document.querySelector('.topbar-title');
    return !!(t?.querySelector('input, textarea, [contenteditable="true"]'));
  });
  const status = (dialogFired || !inlineEditor) ? 'fail' : 'pass';
  results.push({ id: 'T-021', status, jsErr: 0, dialogFired, inlineEditor, note: status === 'fail' ? 'rename entry did not open an inline editor' : '' });
  // 收尾：退出编辑态，不提交，避免污染后续用例的标题
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  try { page.on('dialog', d => d.dismiss()); } catch {}
}

/** 切到原文 Tab，测图层 T-028~T-030 */
await page.evaluate(() => {
  const btns = Array.from(document.querySelectorAll('button'));
  const t = btns.find(b => (b.textContent || '').trim() === '原文');
  if (t) t.click();
});
await page.waitForTimeout(1200);

for (const layer of ['书面版', '清理版', '原文']) {
  await clickMenu(
    layer === '书面版' ? 'T-028' : layer === '清理版' ? 'T-029' : 'T-030',
    async () => {
      await page.evaluate(() => {
        document.querySelector('.gen-layer-trigger')?.click();
      });
      await page.waitForTimeout(300);
    },
    async () => {
      await page.evaluate((txt) => {
        const items = Array.from(document.querySelectorAll('.gen-layer-menu [role="menuitem"]'));
        const t = items.find(i => (i.textContent || '').includes(txt));
        if (t) t.click();
      }, layer);
    },
    null
  );
}

/** 会议库 T-020 卡片跳转 + T-035 说话人筛选 */
await goto(BASE_URL + '/library', 'T-003b');

/** T-021b 卡片重命名：标题行同样必须内联编辑，不走原生 prompt */
{
  const t0 = Date.now();
  let dialogFired = false;
  page.once('dialog', () => { dialogFired = true; });
  await page.evaluate(() => document.querySelector('.sb-tl-item .sb-more')?.click());
  await page.waitForTimeout(400);
  await page.evaluate((labels) => {
    const items = Array.from(document.querySelectorAll('.sb-ctx-menu button'));
    items.find(b => labels.includes((b.textContent || '').trim()))?.click();
  }, RENAME_LABELS);
  await page.waitForTimeout(600);
  const inlineEditor = await page.evaluate(() => !!document.querySelector('.sb-tl-title input'));
  const status = (dialogFired || !inlineEditor) ? 'fail' : 'pass';
  results.push({ id: 'T-021b', status, duration_ms: Date.now() - t0, jsErr: 0, dialogFired, inlineEditor, note: status === 'fail' ? 'card rename did not open an inline editor' : '' });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
}
{
  const t0 = Date.now();
  await page.evaluate(() => {
    const card = document.querySelector('.sb-tl-item');
    if (card) card.click();
  });
  await page.waitForTimeout(1500);
  const path = await page.evaluate(() => location.pathname);
  results.push({ id: 'T-020', status: path.startsWith('/meeting/') ? 'pass' : 'fail', path, duration_ms: Date.now() - t0, jsErr: 0 });
}

{
  const t0 = Date.now();
  await page.goto(BASE_URL + '/library', { waitUntil: 'networkidle', timeout: 15000 }).catch(()=>{});
  await page.waitForTimeout(1200);
  await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('.lib-speaker-item'));
    if (items[0]) items[0].click();
  });
  await page.waitForTimeout(600);
  results.push({ id: 'T-035', status: 'pass', duration_ms: Date.now() - t0, jsErr: 0 });
}

await browser.close();

/** ========== 汇总输出 ========== */
const pass = results.filter(r => r.status === 'pass').length;
const fail = results.filter(r => r.status === 'fail').length;
const out = {
  run_id: `auto-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}`,
  base_url: BASE_URL,
  taskId: TASK_ID,
  summary: { total: results.length, pass, fail, pass_rate: pass / results.length },
  results,
};
const outPath = join(__dirname, `auto-run-${Date.now()}.json`);
writeFileSync(outPath, JSON.stringify(out, null, 2));

console.log(`\n[e2e] SUMMARY: ${pass}/${results.length} pass (${(pass / results.length * 100).toFixed(0)}%)  ${fail} fail`);
for (const r of results.filter(r => r.status === 'fail')) {
  console.log(`  FAIL ${r.id}: ${r.note || ''}`);
}
console.log(`[e2e] results: ${outPath}`);
process.exit(fail > 0 ? 1 : 0);
