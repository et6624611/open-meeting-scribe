import { describe, it, expect } from 'vitest'
import { mergeTaskLists, guardStaleFields } from '@/utils/taskListMerge'
import type { Task } from '@/api/types'

function makeTask(over: Partial<Task>): Task {
  return {
    task_id: 't1',
    status: 'completed',
    progress: 100,
    ...over,
  } as Task
}

describe('guardStaleFields', () => {
  it('终态遇进行态快照：剥离状态面与产物字段', () => {
    const current = makeTask({ status: 'completed', summary: '新纪要' })
    const stale = makeTask({
      status: 'processing', progress: 85, summary: '旧纪要', title: '旧标题',
      audio_name: 'x.wav',
    })
    const safe = guardStaleFields(stale, current)
    expect(safe.status).toBeUndefined()
    expect(safe.progress).toBeUndefined()
    expect(safe.summary).toBeUndefined()
    expect(safe.title).toBeUndefined()
    // 非保护字段保留（如元数据更新仍可生效）
    expect(safe.audio_name).toBe('x.wav')
  })

  it('进行态→终态正常放行（完成侦测依赖此跃迁）', () => {
    const current = makeTask({ status: 'processing', progress: 85 })
    const snap = makeTask({ status: 'completed', progress: 100, summary: '纪要' })
    const out = guardStaleFields(snap, current)
    expect(out.status).toBe('completed')
    expect(out.summary).toBe('纪要')
  })

  it('失败→完成等终态间更新不拦截', () => {
    const current = makeTask({ status: 'failed' })
    const snap = makeTask({ status: 'completed' })
    expect(guardStaleFields(snap, current).status).toBe('completed')
  })
})

describe('mergeTaskLists', () => {
  it('全量：过期 processing 快照不覆盖本地 completed 与产物', () => {
    const current = [makeTask({ status: 'completed', summary: '新纪要', dialogue: [] })]
    const stale = [makeTask({ status: 'processing', progress: 85, summary: '旧纪要' })]
    const merged = mergeTaskLists(current, stale, false)
    expect(merged[0].status).toBe('completed')
    expect(merged[0].summary).toBe('新纪要')
  })

  it('全量：新任务追加、已删除任务剔除、顺序以后端为准', () => {
    const current = [
      makeTask({ task_id: 'a' }),
      makeTask({ task_id: 'gone' }),
    ]
    const incoming = [
      makeTask({ task_id: 'new', title: '新会议' }),
      makeTask({ task_id: 'a', title: '改名' }),
    ]
    const merged = mergeTaskLists(current, incoming, false)
    expect(merged.map(t => t.task_id)).toEqual(['new', 'a'])
    expect(merged[1].title).toBe('改名')
  })

  it('lite：只更新已知任务，不新增不删除，不被过期快照回退', () => {
    const current = [
      makeTask({ task_id: 'a', status: 'completed', summary: '新纪要' }),
      makeTask({ task_id: 'b', status: 'processing', progress: 10 }),
    ]
    const incoming = [
      makeTask({ task_id: 'a', status: 'processing', progress: 85, summary: '旧纪要' }),
      makeTask({ task_id: 'c', status: 'completed' }),
    ]
    const merged = mergeTaskLists(current, incoming, true)
    expect(merged.map(t => t.task_id)).toEqual(['a', 'b'])
    expect(merged[0].status).toBe('completed')
    expect(merged[0].summary).toBe('新纪要')
  })

  it('lite：进行中任务正常推进到完成', () => {
    const current = [makeTask({ task_id: 'b', status: 'processing', progress: 10 })]
    const merged = mergeTaskLists(current, [makeTask({ task_id: 'b', status: 'completed', progress: 100 })], true)
    expect(merged[0].status).toBe('completed')
    expect(merged[0].progress).toBe(100)
  })
})
