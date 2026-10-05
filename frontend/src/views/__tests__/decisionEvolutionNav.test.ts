import { describe, expect, it } from 'vitest'
import { meetingNodeLink, parseAnchorTodoId, parseTopicKey, topicCenterLink } from '../decisionEvolutionNav'

describe('decisionEvolutionNav 演变链路由锚点', () => {
  it('meetingNodeLink 带齐 tab/todo/from 三个定位参数', () => {
    expect(meetingNodeLink('task-1', 'todo-9')).toEqual({
      name: 'generating',
      params: { taskId: 'task-1' },
      query: { tab: 'todos', todo: 'todo-9', from: 'evolution' },
    })
  })

  it('topicCenterLink 强制议题视图并携带 topic key', () => {
    expect(topicCenterLink('abc-key')).toEqual({
      name: 'decisions',
      query: { view: 'topic', topic: 'abc-key' },
    })
  })

  it('parseAnchorTodoId 只接受字符串，数组/空值安全降级', () => {
    expect(parseAnchorTodoId({ todo: 'x1' })).toBe('x1')
    expect(parseAnchorTodoId({ todo: ['x1', 'x2'] })).toBe('')
    expect(parseAnchorTodoId({})).toBe('')
    expect(parseAnchorTodoId({ todo: null })).toBe('')
  })

  it('parseTopicKey 同口径解析议题 key', () => {
    expect(parseTopicKey({ view: 'topic', topic: 'k' })).toBe('k')
    expect(parseTopicKey({ view: 'topic', topic: ['k'] })).toBe('')
    expect(parseTopicKey({})).toBe('')
  })
})
