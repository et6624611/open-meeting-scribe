import { describe, expect, it } from 'vitest'
import type { DecisionItem } from '@/api/types'
import { partitionNodes, statusOf } from '../decisionFlowLogic'

function decision(over: Partial<DecisionItem>): DecisionItem {
  return { id: 'x', text: 't', done: false, ...over } as DecisionItem
}

describe('decisionFlowLogic 节点状态归一', () => {
  it('显式 status 优先；缺省时由 done 反推；再兜底进行中', () => {
    expect(statusOf(decision({ status: 'superseded' }))).toBe('superseded')
    expect(statusOf(decision({ status: '', done: true }))).toBe('done')
    expect(statusOf(decision({}))).toBe('in_progress')
  })
})

describe('decisionFlowLogic 开放/闭档分组', () => {
  const closing = (id?: string) => id === 'done' || id === 'superseded'

  it('闭档节点沉底到 completed，开放节点保持顺序进 active', () => {
    const nodes = [
      decision({ id: 'a', status: 'to_decide' }),
      decision({ id: 'b', status: 'superseded' }),
      decision({ id: 'c', status: 'in_progress' }),
      decision({ id: 'd', status: 'done' }),
      decision({ id: 'e' }), // 无 status → in_progress，开放
    ]
    const { active, completed } = partitionNodes(nodes, closing)
    expect(active.map(n => n.id)).toEqual(['a', 'c', 'e'])
    expect(completed.map(n => n.id)).toEqual(['b', 'd'])
  })

  it('未知状态一律视为开放（宁可露出不隐藏）', () => {
    const { active, completed } = partitionNodes(
      [decision({ id: 'u', status: 'st-unknown' })],
      closing,
    )
    expect(active.map(n => n.id)).toEqual(['u'])
    expect(completed).toEqual([])
  })

  it('空数组返回两个空组', () => {
    expect(partitionNodes([], closing)).toEqual({ active: [], completed: [] })
  })
})
