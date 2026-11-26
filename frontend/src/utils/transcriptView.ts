/**
 * 转写显示工具 / Transcript view helpers
 *
 * 录音页与会后纪要页共用，避免两套实现随时间漂移。
 */
import type { Chapter } from '@/api/types'

/**
 * 毫秒 → `mm:ss`。
 * 不引入小时位：与历史显示保持一致，避免改造改变界面文案。
 */
export function formatTimeMs(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/**
 * 时间点落在第几章（章节按 start_ms 升序）。
 * 早于首章起点返回 -1。
 */
export function getChapterIdxAtTime(chapters: Chapter[], ms: number): number {
  for (let i = chapters.length - 1; i >= 0; i--) {
    if (ms >= chapters[i].start_ms) return i
  }
  return -1
}
