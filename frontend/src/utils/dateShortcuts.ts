/**
 * 决策文本输入的日期快捷插入（方案 A：键入触发式自动展开）
 *
 * 在 textarea 中键入 /today、/tomorrow、/yesterday、/now 或 /+3d、/-1w、/+2m 等触发词，
 * 紧随其后的空格/回车即将其展开为格式化日期；纯文本落盘，Markdown 渲染端零改动。
 * 幂等：展开结果是普通文本，再次编辑不会二次触发。
 */

const TOKEN_RE = /^\/(today|tomorrow|yesterday|now|([+-])(\d{1,3})([dwm]))$/i

const UNIT_DAYS: Record<string, number> = { d: 1, w: 7, m: 30 }

/** 解析单个触发词；非法返回 null。now → 日期+时刻，其余 → 'YYYY-MM-DD' */
export function expandToken(token: string): string | null {
  const m = TOKEN_RE.exec(token)
  if (!m) return null
  const base = new Date()
  if (m[1].toLowerCase() === 'now') return formatDateTime(base)
  if (m[2]) {
    // 相对偏移：/+7d、/-2w、/+1m（月按 30 日近似，决策场景够用且保持纯 Date 实现）
    const n = Number(m[3]) * (m[4] === 'm' ? 30 : UNIT_DAYS[m[4]])
    base.setDate(base.getDate() + (m[2] === '-' ? -n : n))
  } else if (m[1].toLowerCase() === 'tomorrow') {
    base.setDate(base.getDate() + 1)
  } else if (m[1].toLowerCase() === 'yesterday') {
    base.setDate(base.getDate() - 1)
  }
  return formatDate(base)
}

/** 补零取 YYYY-MM-DD（本地时区）；中文语境与 ISO 检索友好，两种 locale 统一格式 */
function parts(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function formatDate(d: Date): string {
  return parts(d)
}

function formatDateTime(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${parts(d)} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/** 从 caret 前文本定位触发词起点：/ 须位于行首或空白后，前面是单词字符则不触发（保护 URL 等） */
export function findTokenStart(before: string): number {
  const idx = before.lastIndexOf('/')
  if (idx < 0) return -1
  const prev = idx === 0 ? '' : before[idx - 1]
  if (prev && /[\w+\-]/.test(prev)) return -1
  return idx
}

// ── 斜杠菜单：候选项、query 检测与前缀过滤 ──

/** 菜单规范项：与 TOKEN_RE 一一对应的 7 个常用触发词（token 含前导 /，key 供 i18n 取名） */
export const DATE_MENU_ITEMS: { token: string; key: string }[] = [
  { token: '/today', key: 'today' },
  { token: '/tomorrow', key: 'tomorrow' },
  { token: '/yesterday', key: 'yesterday' },
  { token: '/now', key: 'now' },
  { token: '/+7d', key: 'plus7d' },
  { token: '/+1m', key: 'plus1m' },
  { token: '/-1w', key: 'minus1w' },
]

/**
 * 检测光标前是否处于「/query」输入态：返回斜杠起点与已键入的 query（不含 /）。
 * query 仅允许 [A-Za-z0-9+-]、长度 ≤8；不合法（非法字符/超长/无斜杠）返回 null。
 */
export function detectSlashQuery(value: string, caret: number): { start: number; query: string } | null {
  const before = value.slice(0, caret)
  const start = findTokenStart(before)
  if (start < 0) return null
  const query = before.slice(start + 1)
  if (query.length > 8) return null
  if (!/^[A-Za-z0-9+\-]*$/.test(query)) return null
  return { start, query }
}

/** 按 query 前缀过滤规范项（query 为空返回全部；大小写不敏感） */
export function filterDateMenuItems(query: string) {
  const q = query.toLowerCase()
  return DATE_MENU_ITEMS.filter(it => it.token.slice(1).toLowerCase().startsWith(q))
}

/**
 * textarea 插件事件处理器：命中触发词则就地展开并还原光标。
 * 未命中时不做任何事，调用方正常走 v-model / input 同步。
 */
export function handleDateShortcut(e: Event): void {
  const el = e.target as HTMLTextAreaElement | HTMLInputElement
  const caret = el.selectionStart ?? el.value.length
  const before = el.value.slice(0, caret)
  // 仅当最后键入的是空白/换行符才触发（光标前紧邻字符）
  if (!before || !/\s$/.test(before)) return
  const start = findTokenStart(before.slice(0, -1))
  if (start < 0) return
  const tokenStart = start + (caret - before.length) // 修正选区偏移（通常无选区，为 0）
  const token = before.slice(0, -1).slice(start)
  const dateText = expandToken(token)
  if (!dateText) return
  // 保留触发空白（回车除外——换行已由按键产生，展开后不再补），光标落在日期之后
  const trigger = before[before.length - 1]
  const keep = trigger === '\n' ? '' : trigger
  const next = before.slice(0, tokenStart) + dateText + keep + el.value.slice(caret)
  el.value = next
  const pos = tokenStart + dateText.length + keep.length
  el.setSelectionRange(pos, pos)
  // 触发 input 事件，让 v-model / :value+@input 两种绑定都能同步组件状态
  el.dispatchEvent(new Event('input', { bubbles: true }))
}
