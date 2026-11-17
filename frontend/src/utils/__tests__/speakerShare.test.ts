import { describe, it, expect } from 'vitest'
import { resolveSpeakerSeconds, speakerPct } from '@/utils/speakerShare'
import type { Task } from '@/api/types'

function makeTask(over: Partial<Task>): Task {
  return {
    task_id: 't1',
    status: 'completed',
    progress: 100,
    ...over,
  } as Task
}

describe('resolveSpeakerSeconds', () => {
  it('优先使用后端 speaker_share（秒）', () => {
    const task = makeTask({ speaker_share: { '0': 4, '2': 6 } })
    const { seconds, total } = resolveSpeakerSeconds(task)
    expect(seconds).toEqual({ '0': 4, '2': 6 })
    expect(total).toBe(10)
  })

  it('缺失 speaker_share 时回退 dialogue（毫秒转秒）', () => {
    const task = makeTask({
      dialogue: [
        {
          speaker_id: 0,
          text: 'a',
          sentences: [
            { begin_time: 0, end_time: 4000, text: 'a', sentence_id: 1, speaker_id: 0 },
          ],
        },
      ] as Task['dialogue'],
    })
    const { seconds, total } = resolveSpeakerSeconds(task)
    expect(seconds).toEqual({ '0': 4 })
    expect(total).toBe(4)
  })

  it('无数据时返回空', () => {
    const { seconds, total } = resolveSpeakerSeconds(makeTask({}))
    expect(seconds).toEqual({})
    expect(total).toBe(0)
  })
})

describe('speakerPct', () => {
  it('按占比四舍五入', () => {
    const seconds = { '0': 1, '1': 2 }
    expect(speakerPct(seconds, 3, '0')).toBe(33)
    expect(speakerPct(seconds, 3, '1')).toBe(67)
  })

  it('总量为 0 时返回 0（不产生 NaN）', () => {
    expect(speakerPct({}, 0, '0')).toBe(0)
  })
})
