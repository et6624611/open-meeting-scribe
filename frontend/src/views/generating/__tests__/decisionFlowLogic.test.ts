import { describe, expect, it } from 'vitest'
import type { TodoItem } from '@/api/types'
import { partitionNodes, statusOf } from '../decisionFlowLogic'

function todo(over: Partial<TodoItem>): TodoItem {
  return { id: 'x', text: 't', done: false, ...over } as TodoItem
}

describe('decisionFlowLogic 节点状态归一', () => {
  it('显式 status 优先；缺省时由 done 反推；再兜底进行中', () => {
    expect(statusOf(todo({ status: 'superseded' }))).toBe('superseded')
    expect(statusOf(todo({ status: '', done: true }))).toBe('done')
    expect(statusOf(todo({}))).toBe('in_progress')
  })
})

describe('decisionFlowLogic 开放/闭档分组', () => {
  const closing = (id?: string) => id === 'done' || id === 'superseded'

  it('闭档节点沉底到 completed，开放节点保持顺序进 active', () => {
    const nodes = [
      todo({ id: 'a', status: 'to_decide' }),
      todo({ id: 'b', status: 'superseded' }),
      todo({ id: 'c', status: 'in_progress' }),
      todo({ id: 'd', status: 'done' }),
      todo({ id: 'e' }), // 无 status → in_progress，开放
    ]
    const { active, completed } = partitionNodes(nodes, closing)
    expect(active.map(n => n.id)).toEqual(['a', 'c', 'e'])
    expect(completed.map(n => n.id)).toEqual(['b', 'd'])
  })

  it('未知状态一律视为开放（宁可露出不隐藏）', () => {
    const { active, completed } = partitionNodes(
      [todo({ id: 'u', status: 'st-unknown' })],
      closing,
    )
    expect(active.map(n => n.id)).toEqual(['u'])
    expect(completed).toEqual([])
  })

  it('空数组返回两个空组', () => {
    expect(partitionNodes([], closing)).toEqual({ active: [], completed: [] })
  })
})
