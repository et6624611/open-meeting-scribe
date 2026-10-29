import { describe, expect, it } from 'vitest'
import type { DecisionItem } from '@/api/types'
import { statusOf } from '../decisionFlowLogic'

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
