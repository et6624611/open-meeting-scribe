/**
 * 按更新时间做"今天/昨天/近 7 天/更早"日历分组（B1 会议库日期分组，个人版 LibraryView 同款语言）
 *
 * 纯函数+可注入 now（测试确定性）；分组序=组内保持传入序（列表侧已按 updated_at 倒序）。
 * 边界=本地日历日（与用户体感一致），非 24h 滚动窗。
 */
export type RecencyKey = 'today' | 'yesterday' | 'week' | 'earlier'

export interface RecencyGroup<T> { key: RecencyKey; items: T[] }

function dayStart(ms: number): number {
  const d = new Date(ms)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

export function recencyOf(iso: string, now = Date.now()): RecencyKey | null {
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return null
  const days = Math.round((dayStart(now) - dayStart(ts)) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days <= 7) return 'week'
  return 'earlier'
}

export function groupByRecency<T extends { updated_at: string }>(items: T[], now = Date.now()): RecencyGroup<T>[] {
  const buckets = new Map<RecencyKey, T[]>()
  const ORDER: RecencyKey[] = ['today', 'yesterday', 'week', 'earlier']
  for (const it of items) {
    // 无效时间戳归更早（不猜日期，不丢卡片）
    const key = recencyOf(it.updated_at, now) ?? 'earlier'
    const arr = buckets.get(key)
    if (arr) arr.push(it)
    else buckets.set(key, [it])
  }
  return ORDER.filter((k) => buckets.has(k)).map((key) => ({ key, items: buckets.get(key)! }))
}
