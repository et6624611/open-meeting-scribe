// 日期快捷插入工具单测 / Date shortcut expansion unit test
// 运行：node --experimental-strip-types scripts/test-date-shortcuts.mjs
import test from 'node:test'
import assert from 'node:assert'
import { handleDateShortcut } from '../src/utils/dateShortcuts.ts'
import {
  detectSlashQuery, filterDateMenuItems, DATE_MENU_ITEMS,
} from '../src/utils/dateShortcuts.ts'

// 最小 textarea 替身：只需 value/selectionStart/setSelectionRange/dispatchEvent
function makeEl(value, caret) {
  const el = {
    value,
    selectionStart: caret,
    selectionEnd: caret,
    setSelectionRange(s, e) { this.selectionStart = s; this.selectionEnd = e },
    dispatchEvent() { /* 展开后由调用方读取 el.value 断言，无需真实重放 */ },
  }
  return el
}

function expand(value, caret) {
  const el = makeEl(value, caret)
  handleDateShortcut({ target: el })
  return { value: el.value, caret: el.selectionStart }
}

const fmt = (d) => {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
const day = (offset) => { const d = new Date(); d.setDate(d.getDate() + offset); return fmt(d) }

test('/today + 空格 → 今天', () => {
  const r = expand('截止 /today ', 10)
  assert.strictEqual(r.value, `截止 ${day(0)} `)
})

test('/tomorrow 在句中也展开，保留触发空格', () => {
  const r = expand('/tomorrow 复审', 10)
  assert.strictEqual(r.value, `${day(1)} 复审`)
  assert.strictEqual(r.caret, day(1).length + 1)
})

test('/+7d 相对偏移', () => {
  const r = expand('上线 /+7d ', 8)
  assert.strictEqual(r.value, `上线 ${day(7)} `)
})

test('/-2w 向前偏移', () => {
  const r = expand('/-2w', 4)
  // 光标前最后字符须为空白才触发，这里补一个空格触发
  const r2 = expand('/-2w ', 5)
  assert.ok(r.value === '/-2w' && r2.value === `${day(-14)} `)
})

test('回车触发：展开且不保留换行', () => {
  const r = expand('- 复盘 /today\n', 12)
  assert.strictEqual(r.value, `- 复盘 ${day(0)}`)
})

test('/now → 日期+时刻', () => {
  const r = expand('/now ', 5)
  assert.match(r.value, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2} $/)
})

test('非触发词不展开（/teams）', () => {
  const r = expand('用 /teams 沟通 ', 10)
  assert.strictEqual(r.value, '用 /teams 沟通 ')
})

test('URL 中的 /today 不触发（前面是单词字符）', () => {
  const r = expand('https://x.com/today ', 19)
  assert.strictEqual(r.value, 'https://x.com/today ')
})

test('无触发空白不展开', () => {
  const r = expand('/today', 6)
  assert.strictEqual(r.value, '/today')
})

test('已展开的日期再次输入空格不二次触发（幂等）', () => {
  const once = expand('计划 /today ', 10)
  const twice = expand(once.value, once.caret)
  assert.strictEqual(twice.value, once.value)
})

// ── 斜杠菜单：query 检测与前缀过滤 ──

test('detectSlashQuery：行首斜杠空 query', () => {
  assert.deepStrictEqual(detectSlashQuery('/', 1), { start: 0, query: '' })
})

test('detectSlashQuery：空白后部分词', () => {
  assert.deepStrictEqual(detectSlashQuery('截止 /to', 6), { start: 3, query: 'to' })
})

test('detectSlashQuery：URL 中不触发（前面是单词字符）', () => {
  assert.strictEqual(detectSlashQuery('https://x/to', 12), null)
})

test('detectSlashQuery：非法字符不触发', () => {
  assert.strictEqual(detectSlashQuery('/to day', 7), null)
})

test('detectSlashQuery：超长（>8）不触发', () => {
  assert.strictEqual(detectSlashQuery('/abcdefghij', 11), null)
})

test('filterDateMenuItems：空前缀返回全部', () => {
  assert.strictEqual(filterDateMenuItems('').length, DATE_MENU_ITEMS.length)
})

test('filterDateMenuItems：/to 只剩 today/tomorrow', () => {
  const keys = filterDateMenuItems('to').map(it => it.key)
  assert.deepStrictEqual(keys, ['today', 'tomorrow'])
})

test('filterDateMenuItems：+7 只剩 plus7d', () => {
  const keys = filterDateMenuItems('+7').map(it => it.key)
  assert.deepStrictEqual(keys, ['plus7d'])
})

test('filterDateMenuItems：大小写不敏感', () => {
  assert.deepStrictEqual(filterDateMenuItems('TODAY').map(it => it.key), ['today'])
})
