import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只验证演变链增量端点的请求契约：方法 / URL / snake_case 请求体 / 响应解包
const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}))
vi.mock('@/api/client', () => ({ default: mocks }))

import { revertSupersede, supersedeDecision } from '@/api/notes'
import { fetchTaskEvolution } from '@/api/decisions'

beforeEach(() => vi.clearAllMocks())

describe('supersedeDecision 标记已替代', () => {
  it('POST 正确端点，驼峰入参翻成后端 snake_case，并解包 decision', async () => {
    const returned = { id: 'x1', status: 'superseded' }
    mocks.post.mockResolvedValueOnce({ data: { decision: returned } })

    const out = await supersedeDecision('t1', 'x1', { taskId: 't2', decisionId: 'x2' })

    expect(mocks.post).toHaveBeenCalledWith(
      '/api/tasks/t1/decisions/x1/supersede',
      { by_task_id: 't2', by_decision_id: 'x2' },
    )
    expect(out).toBe(returned)
  })
})

describe('revertSupersede 撤销', () => {
  it('走 DELETE 同一端点并解包恢复后的节点', async () => {
    const returned = { id: 'x1', status: 'in_progress' }
    mocks.delete.mockResolvedValueOnce({ data: { decision: returned } })

    const out = await revertSupersede('t1', 'x1')

    expect(mocks.delete).toHaveBeenCalledWith('/api/tasks/t1/decisions/x1/supersede')
    expect(out).toBe(returned)
  })
})

describe('fetchTaskEvolution 演变归属', () => {
  it('以 task_id 查询参数请求 evolution 端点并解包 evolution 映射', async () => {
    const map = { x1: { role: 'history', latest: { decision_id: 'x2' } } }
    mocks.get.mockResolvedValueOnce({ data: { task_id: 't1', evolution: map } })

    const out = await fetchTaskEvolution('t1')

    expect(mocks.get).toHaveBeenCalledWith(
      '/api/decisions/evolution',
      { params: { task_id: 't1' } },
    )
    expect(out).toBe(map)
  })

  it('后端返回缺字段时安全降级为空映射', async () => {
    mocks.get.mockResolvedValueOnce({ data: {} })
    await expect(fetchTaskEvolution('t1')).resolves.toEqual({})
  })
})
