/**
 * 说话人发言时长 / Speaker talk time
 *
 * 列表视图（view=list）不携带 dialogue，时长占比由后端 speaker_share（秒）下发；
 * 详情页或旧数据缺失该字段时回退遍历 dialogue（句级时间码为毫秒）。
 */
import type { Task } from '@/api/types'

export interface SpeakerSeconds {
  /** speaker_id -> 累计秒数 */
  seconds: Record<string, number>
  /** 全部说话人累计秒数 */
  total: number
}

/** 解析任务的说话人时长：优先后端 speaker_share，缺失时回退 dialogue */
export function resolveSpeakerSeconds(task: Pick<Task, 'speaker_share' | 'dialogue'>): SpeakerSeconds {
  const share = task.speaker_share
  if (share && Object.keys(share).length > 0) {
    const seconds: Record<string, number> = {}
    let total = 0
    for (const [sid, sec] of Object.entries(share)) {
      const value = Number(sec) || 0
      seconds[sid] = value
      total += value
    }
    return { seconds, total }
  }

  const millis: Record<string, number> = {}
  let totalMillis = 0
  for (const line of task.dialogue || []) {
    const sid = String(line.speaker_id)
    for (const s of line.sentences || []) {
      const d = (s.end_time ?? 0) - (s.begin_time ?? 0)
      millis[sid] = (millis[sid] || 0) + d
      totalMillis += d
    }
  }
  const seconds: Record<string, number> = {}
  for (const [sid, ms] of Object.entries(millis)) seconds[sid] = ms / 1000
  return { seconds, total: totalMillis / 1000 }
}

/** 某说话人时长占比（四舍五入到整数百分比） */
export function speakerPct(seconds: Record<string, number>, total: number, sid: string): number {
  if (!total) return 0
  return Math.round(((seconds[sid] || 0) / total) * 100)
}
