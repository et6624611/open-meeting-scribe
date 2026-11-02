import { describe, expect, it } from 'vitest'
import { groupByRecency, recencyOf } from '../recencyGroup'

// 固定 now=2026-11-02 15:00 本地
const NOW = new Date(2026, 10, 2, 15, 0, 0).getTime()
const iso = (y: number, m: number, d: number, ...rest: number[]) => new Date(y, m, d, ...rest).getTime()
const toISO = (ms: number) => new Date(ms).toISOString()

describe('recencyOf（B1 日期分组边界）', () => {
  it('当日=今天；昨日日历日=昨天；8~7 天=近7天；更久=更早', () => {
    expect(recencyOf(toISO(iso(2026, 10, 2, 0, 30)), NOW)).toBe('today')
    expect(recencyOf(toISO(iso(2026, 10, 2, 23, 59)), NOW)).toBe('today')
    expect(recencyOf(toISO(iso(2026, 10, 1)), NOW)).toBe('yesterday')
    expect(recencyOf(toISO(iso(2026, 9, 26)), NOW)).toBe('week') // 10-26：距 11-02 整 7 天
    expect(recencyOf(toISO(iso(2026, 9, 25)), NOW)).toBe('earlier') // 8 天
  })
  it('未来漂移归今天；无效时间戳返回 null（消费侧归更早，不丢卡）', () => {
    expect(recencyOf(toISO(NOW + 3600_000), NOW)).toBe('today')
    expect(recencyOf('not-a-date', NOW)).toBeNull()
  })
})

describe('groupByRecency（组序稳定+组内保序+空组不占位）', () => {
  it('四组齐全时按 今天>昨天>近7天>更早 出组，组内保持传入序', () => {
    const items = [
      { id: 1, updated_at: toISO(iso(2026, 10, 2)) },
      { id: 2, updated_at: toISO(iso(2026, 10, 1)) },
      { id: 3, updated_at: toISO(iso(2026, 9, 28)) },
      { id: 4, updated_at: toISO(iso(2026, 9, 1)) },
      { id: 5, updated_at: toISO(iso(2026, 10, 2, 8)) },
    ]
    const groups = groupByRecency(items, NOW)
    expect(groups.map((g) => g.key)).toEqual(['today', 'yesterday', 'week', 'earlier'])
    expect(groups[0]!.items.map((i) => i.id)).toEqual([1, 5])
  })
  it('无效 updated_at 归更早；空列表空分组', () => {
    const groups = groupByRecency([{ id: 1, updated_at: 'broken' }, { id: 2, updated_at: toISO(iso(2026, 10, 2)) }], NOW)
    expect(groups.map((g) => g.key)).toEqual(['today', 'earlier'])
    expect(groups[1]!.items.map((i) => i.id)).toEqual([1])
    expect(groupByRecency([], NOW)).toEqual([])
  })
})
