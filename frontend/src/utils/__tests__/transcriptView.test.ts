import { describe, it, expect } from 'vitest'
import { formatTimeMs, getChapterIdxAtTime } from '@/utils/transcriptView'
import type { Chapter } from '@/api/types'

function chapter(startMs: number): Chapter {
  return { id: 0, title: 'c', start_ms: startMs, end_ms: startMs + 1000 } as Chapter
}

describe('formatTimeMs', () => {
  it('零值显示为 00:00', () => {
    expect(formatTimeMs(0)).toBe('00:00')
  })

  it('不足十分钟补零', () => {
    expect(formatTimeMs(5_000)).toBe('00:05')
    expect(formatTimeMs(65_000)).toBe('01:05')
  })

  it('超过一小时按累计分钟显示，不引入小时位', () => {
    expect(formatTimeMs(3_665_000)).toBe('61:05')
  })

  it('毫秒向下取整', () => {
    expect(formatTimeMs(1_999)).toBe('00:01')
  })
})

describe('getChapterIdxAtTime', () => {
  it('空章节返回 -1', () => {
    expect(getChapterIdxAtTime([], 1000)).toBe(-1)
  })

  it('早于首章起点返回 -1', () => {
    expect(getChapterIdxAtTime([chapter(1000), chapter(5000)], 999)).toBe(-1)
  })

  it('落在章节起点时归入该章', () => {
    expect(getChapterIdxAtTime([chapter(1000), chapter(5000)], 1000)).toBe(0)
    expect(getChapterIdxAtTime([chapter(1000), chapter(5000)], 5000)).toBe(1)
  })

  it('落在章节之间沿用前一章', () => {
    expect(getChapterIdxAtTime([chapter(1000), chapter(5000)], 4999)).toBe(0)
  })

  it('晚于末章起点归入末章', () => {
    expect(getChapterIdxAtTime([chapter(1000), chapter(5000)], 99_999)).toBe(1)
  })
})
