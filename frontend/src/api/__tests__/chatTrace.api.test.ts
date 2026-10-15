import { afterEach, describe, expect, it, vi } from 'vitest'
import { sendMessageStream } from '../chat'

vi.mock('../client', () => ({ default: { defaults: { baseURL: '' } } }))
afterEach(() => vi.unstubAllGlobals())

it('请求历史仅发送正文，不把执行详情重新发送给模型', async () => {
  const fetchMock = vi.fn(async () => new Response('', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  await sendMessageStream('继续', { history: [{
    role: 'assistant', content: '答复正文', executionId: 'trace-1', executionState: 'done',
    stages: [{ type: 'tool_call', label: '读取', status: 'done', input: '本机路径', output: '长工具记录' }],
  }] })
  const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string)
  expect(body.history).toEqual([{ role: 'assistant', content: '答复正文' }])
})

describe('详情协议透传', () => {
  it('补写状态、取消终态和错误写回元数据均透传', async () => {
    const events = [
      { type: 'stage', stage: 'board_retry', label: '正在补写', status: 'running' },
      { type: 'error', content: '后续输出超时', status: 'error', hint_key: 'cli_engine_idle_timeout',
        metadata: { rewritten: true, turn_id: 'same-turn' } },
      { type: 'done', status: 'cancelled', cancelled: true },
    ]
    vi.stubGlobal('fetch', vi.fn(async () => new Response(events.map(e => `data: ${JSON.stringify(e)}\n\n`).join(''))))
    const callbacks = { onToken: vi.fn(), onStage: vi.fn(), onToolCall: vi.fn(), onToolResult: vi.fn(), onDone: vi.fn(), onError: vi.fn() }
    await sendMessageStream('检查', {}, callbacks)
    expect(callbacks.onStage).toHaveBeenCalledWith(events[0])
    expect(callbacks.onError).toHaveBeenCalledWith('后续输出超时', expect.objectContaining({
      status: 'error', hint_key: 'cli_engine_idle_timeout', metadata: { rewritten: true, turn_id: 'same-turn' },
    }))
    expect(callbacks.onDone).toHaveBeenCalledWith(events[2])
  })
  it('SSE 工具详情与截断标记到达回调', async () => {
    const event = { type: 'tool_result', tool_use_id: 'r1', success: false, summary: '摘要', output: '结果'.repeat(400), output_truncated: true }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(`data: ${JSON.stringify(event)}\n\n`)))
    const onToolResult = vi.fn()
    await sendMessageStream('检查', {}, {
      onToken: vi.fn(), onStage: vi.fn(), onToolCall: vi.fn(), onToolResult, onDone: vi.fn(), onError: vi.fn(),
    })
    expect(onToolResult).toHaveBeenCalledWith(event)
  })
})
