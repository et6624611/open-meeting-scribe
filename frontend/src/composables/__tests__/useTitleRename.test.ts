import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useTitleRename } from '../useTitleRename'
import { updateTask } from '@/api/tasks'
import { showToast } from '@/composables/useToast'

vi.mock('@/i18n', () => ({ tt: (key: string) => key }))
vi.mock('@/api/tasks', () => ({ updateTask: vi.fn() }))
vi.mock('@/composables/useToast', () => ({ showToast: vi.fn() }))
// task store 在 setup 里调 useI18n()，单测无 i18n 实例；本用例只关心 patchTaskLocal 的入参
// vi.mock 会被提升到导入之前，故外部引用需走 vi.hoisted
const { mockPatchTaskLocal } = vi.hoisted(() => ({ mockPatchTaskLocal: vi.fn() }))
vi.mock('@/stores/task', () => ({ useTaskStore: () => ({ patchTaskLocal: mockPatchTaskLocal }) }))

const mockedUpdate = vi.mocked(updateTask)
const T = 'task-1'

/** 模块级单例：用例之间必须显式清场，否则上一条的编辑态会污染下一条 */
function resetSession() {
  useTitleRename().cancel()
}

describe('useTitleRename', () => {
  beforeEach(() => {
    mockedUpdate.mockReset()
    mockPatchTaskLocal.mockReset()
    vi.mocked(showToast).mockReset()
    resetSession()
  })

  it('编辑器只归属发起的表面，另一面不渲染', () => {
    const r = useTitleRename()
    r.start(T, '原标题', 'topbar')
    expect(r.owns('topbar', T)).toBe(true)
    expect(r.owns('card', T)).toBe(false)
    // 同一任务改由卡片发起 → 归属权整体移交，避免两个输入框并存互相触发 blur
    r.start(T, '原标题', 'card')
    expect(r.owns('topbar', T)).toBe(false)
    expect(r.owns('card', T)).toBe(true)
  })

  it('非编辑面实时回显未保存的草稿', () => {
    const r = useTitleRename()
    r.start(T, '原标题', 'topbar')
    expect(r.displayTitle(T, '原标题')).toBe('原标题')
    r.draft.value = '改到一半'
    expect(r.displayTitle(T, '原标题')).toBe('改到一半')
    // 其它任务不受影响
    expect(r.displayTitle('other-task', '别的标题')).toBe('别的标题')
  })

  it('空标题或未改动直接取消，不打后端', async () => {
    const r = useTitleRename()
    r.start(T, '原标题', 'card')
    r.draft.value = '   '
    await r.commit()
    expect(mockedUpdate).not.toHaveBeenCalled()
    expect(r.isRenaming(T)).toBe(false)

    r.start(T, '原标题', 'card')
    r.draft.value = '原标题'
    await r.commit()
    expect(mockedUpdate).not.toHaveBeenCalled()
    expect(r.isRenaming(T)).toBe(false)
  })

  it('提交成功走 PATCH、增量 patch 本地 store 并退出编辑态', async () => {
    const r = useTitleRename()
    r.start(T, '原标题', 'topbar')
    r.draft.value = '  新会议标题  '
    mockedUpdate.mockResolvedValue({ title: '新会议标题' } as never)

    await r.commit()

    expect(mockedUpdate).toHaveBeenCalledWith(T, { title: '新会议标题' })
    expect(mockPatchTaskLocal).toHaveBeenCalledWith(T, { title: '新会议标题' })
    expect(r.isRenaming(T)).toBe(false)
    expect(r.draft.value).toBe('')
  })

  it('提交失败保留编辑态以便原地重试', async () => {
    const r = useTitleRename()
    r.start(T, '原标题', 'card')
    r.draft.value = '新标题'
    mockedUpdate.mockRejectedValue(new Error('boom'))

    await r.commit()

    expect(vi.mocked(showToast)).toHaveBeenCalledTimes(1)
    expect(mockPatchTaskLocal).not.toHaveBeenCalled()
    expect(r.owns('card', T)).toBe(true)
    expect(r.draft.value).toBe('新标题')
  })

  it('Enter 与随后 blur 双触发只发一次 PATCH', async () => {
    const r = useTitleRename()
    r.start(T, '原标题', 'topbar')
    r.draft.value = '新标题'
    let release: (v: unknown) => void = () => {}
    mockedUpdate.mockReturnValue(new Promise(resolve => { release = resolve }) as never)

    const first = r.commit()
    const second = r.commit() // 模拟元素卸载前冒出来的 blur
    release({ title: '新标题' })
    await Promise.all([first, second])

    expect(mockedUpdate).toHaveBeenCalledTimes(1)
    expect(r.isRenaming(T)).toBe(false)
  })
})
