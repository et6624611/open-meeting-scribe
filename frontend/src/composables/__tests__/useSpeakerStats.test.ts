import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadSpeakerStats, statsCache } from '../useSpeakerStats'
import { fetchTasks } from '@/api/tasks'
import type { DialogueLine, Task } from '@/api/types'

vi.mock('@/api/tasks', () => ({ fetchTasks: vi.fn() }))

const mockedFetch = vi.mocked(fetchTasks)

const SPEAKERS = [
  { id: 'spk-voice', name: '张三' },
  { id: 'spk-manual', name: '李四' },
  { id: 'spk-both', name: '王五' },
]

function makeTask(patch: Partial<Task> & Pick<Task, 'task_id'>): Task {
  return {
    status: 'completed',
    audio_name: '',
    audio_duration: 600,
    created_at: '2026-11-01T10:00:00',
    speaker_uuid_mapping: {},
    roster: [],
    dialogue: [],
    decisions: [],
    ...patch,
  } as unknown as Task
}

function dialogueLine(speakerId: number, text: string): DialogueLine {
  return {
    speaker_id: speakerId,
    text,
    sentences: [{ speaker_id: speakerId, begin_time: 0, end_time: 1, text, sentence_id: 0 }],
  }
}

describe('useSpeakerStats 参与的会议聚合', () => {
  beforeEach(() => {
    mockedFetch.mockReset()
  })

  it('仅声纹标记人员的会议：按 speaker_uuid_mapping 命中', async () => {
    mockedFetch.mockResolvedValue([
      makeTask({
        task_id: 't-voice',
        speaker_uuid_mapping: { 0: 'spk-voice' },
        dialogue: [dialogueLine(0, '张三的发言')] as never,
      }),
    ])

    await loadSpeakerStats(SPEAKERS)

    expect(statsCache.value['spk-voice'].meetings.map(m => m.task_id)).toEqual(['t-voice'])
    expect(statsCache.value['spk-voice'].meetings[0].utteranceCount).toBe(1)
    expect(statsCache.value['spk-manual'].meetings).toEqual([])
  })

  it('仅手工添加人员的会议：按 roster 姓名命中，且无逐字稿也能展示', async () => {
    mockedFetch.mockResolvedValue([
      makeTask({ task_id: 't-manual', roster: ['李四'], dialogue: [] }),
    ])

    await loadSpeakerStats(SPEAKERS)

    expect(statsCache.value['spk-manual'].meetings.map(m => m.task_id)).toEqual(['t-manual'])
    expect(statsCache.value['spk-manual'].meetings[0].utteranceCount).toBe(0)
    expect(statsCache.value['spk-voice'].meetings).toEqual([])
  })

  it('两类人员同时存在：各自出现在参与的会议中', async () => {
    mockedFetch.mockResolvedValue([
      makeTask({
        task_id: 't-mixed',
        roster: ['李四'],
        speaker_uuid_mapping: { 0: 'spk-voice' },
        dialogue: [dialogueLine(0, '张三的发言')] as never,
      }),
    ])

    await loadSpeakerStats(SPEAKERS)

    expect(statsCache.value['spk-voice'].meetings.map(m => m.task_id)).toEqual(['t-mixed'])
    expect(statsCache.value['spk-manual'].meetings.map(m => m.task_id)).toEqual(['t-mixed'])
  })

  it('同一场会议命中声纹与 roster 时只登记一次，不重复', async () => {
    mockedFetch.mockResolvedValue([
      makeTask({
        task_id: 't-both',
        roster: ['王五'],
        speaker_uuid_mapping: { 0: 'spk-both' },
        dialogue: [dialogueLine(0, '王五的发言')] as never,
      }),
    ])

    await loadSpeakerStats(SPEAKERS)

    const meetings = statsCache.value['spk-both'].meetings
    expect(meetings).toHaveLength(1)
    expect(meetings[0].utteranceCount).toBe(1)
  })

  it('多个 speaker_id 绑定同一人：合并为一场，发言数累加', async () => {
    mockedFetch.mockResolvedValue([
      makeTask({
        task_id: 't-merge',
        speaker_uuid_mapping: { 0: 'spk-voice', 1: 'spk-voice' },
        dialogue: [
          dialogueLine(0, '第一段'),
          dialogueLine(1, '第二段'),
        ] as never,
      }),
    ])

    await loadSpeakerStats(SPEAKERS)

    const meetings = statsCache.value['spk-voice'].meetings
    expect(meetings).toHaveLength(1)
    expect(meetings[0].utteranceCount).toBe(2)
  })

  it('已绑定但无发言的人员仍算参与（声纹标记即出席）', async () => {
    mockedFetch.mockResolvedValue([
      makeTask({ task_id: 't-silent', speaker_uuid_mapping: { 0: 'spk-voice' } }),
    ])

    await loadSpeakerStats(SPEAKERS)

    expect(statsCache.value['spk-voice'].meetings.map(m => m.task_id)).toEqual(['t-silent'])
    expect(statsCache.value['spk-voice'].meetings[0].utteranceCount).toBe(0)
  })

  it('未完成会议不计入，保留既有状态过滤', async () => {
    mockedFetch.mockResolvedValue([
      makeTask({ task_id: 't-processing', status: 'processing', roster: ['李四'] }),
      makeTask({ task_id: 't-awaiting', status: 'awaiting_mapping', roster: ['李四'] }),
    ])

    await loadSpeakerStats(SPEAKERS)

    expect(statsCache.value['spk-manual'].meetings.map(m => m.task_id)).toEqual(['t-awaiting'])
  })
})
