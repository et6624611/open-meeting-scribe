import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { effectScope, ref, type EffectScope } from 'vue'
import { useAiChat } from '../useAiChat'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { sendMessageStream, generateChatTitle, type StreamCallbacks, type ChatOptions } from '@/api/chat'
import { showToast } from '@/composables/useToast'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ name: 'start' }) }))
vi.mock('@/i18n', () => ({ tt: (key: string) => key, getLocale: () => 'zh-CN' }))
vi.mock('@/api/chat', () => ({ sendMessageStream: vi.fn(), generateChatTitle: vi.fn(async () => ''), cancelStream: vi.fn(), injectItems: vi.fn() }))
vi.mock('@/api/settings', () => ({
  fetchChatEngineStatus: vi.fn(async () => ({})), fetchChatEngineModels: vi.fn(async () => ({ models: [] })),
  fetchSettings: vi.fn(async () => ({})), probeLocalEngine: vi.fn(async () => ({ engines: [] })), saveSettings: vi.fn(),
}))
vi.mock('@/stores/task', () => ({ useTaskStore: () => ({ currentTaskId: null }) }))
vi.mock('@/stores/realtime', () => ({ useRealtimeStore: () => ({ getSnapshot: () => null }) }))
vi.mock('@/stores/agent', () => ({ useAgentStore: () => ({ activeAgent: null }) }))
vi.mock('@/stores/engine', () => ({ useEngineStore: () => ({ sessionModel: '', setSessionModel: vi.fn() }) }))
vi.mock('@/composables/useAiInsights', () => ({ useAiInsights: () => ({ lastViewedDiagram: ref(null) }) }))
vi.mock('@/composables/useSummaryProposal', () => ({ useSummaryProposal: () => ({ summaryProposal: ref(null) }) }))
vi.mock('@/composables/useNotesProposal', () => ({ useNotesProposal: () => ({ notesProposal: ref(null) }) }))
vi.mock('@/api/notes', () => ({ fetchNotes: vi.fn() }))
vi.mock('@/composables/useToast', () => ({ showToast: vi.fn() }))

let scope: EffectScope
let chat: ReturnType<typeof useAiChat>
let store: ReturnType<typeof useAiSessionsStore>
const stream = vi.mocked(sendMessageStream)
const call = (id: string, name = 'Read') => ({ id, name, label: '读取文件', icon: 'file-text', args: { path: `${id}.md`, options: { lines: [1, 2] } } })
function result(id: string, success = true, output = '完整结果') {
  return { tool_use_id: id, name: 'Read', success, summary: output.slice(0, 200), output }
}
function runEvents(fn: (cb: StreamCallbacks, options: ChatOptions) => void | Promise<void>) {
  stream.mockImplementation(async (_text, options, cb) => { await fn(cb!, options!) })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  setActivePinia(createPinia())
  scope = effectScope()
  chat = scope.run(() => useAiChat())!
  store = useAiSessionsStore()
})
afterEach(() => { scope.stop(); vi.restoreAllMocks() })

describe('执行过程留痕', () => {
  it('并行工具保持运行状态，乱序回传后分别保留参数、结果和失败状态', async () => {
    const output = '会议记录\n'.repeat(80) + '结尾证据'
    runEvents(cb => {
      cb.onStage({ stage: 'thinking', label: '准备读取' })
      cb.onToolCall(call('a'))
      cb.onToolCall(call('b'))
      expect(chat.stages.value.map(s => s.status)).toEqual(['done', 'running', 'running'])
      cb.onToolResult(result('b', false, '文件不存在'))
      cb.onToolResult(result('a', true, output))
      cb.onToken('答复')
      cb.onDone({})
    })
    await chat.sendRaw('查看文件')
    const msg = store.activeMessages[1]!
    expect(msg.executionState).toBe('done')
    expect(msg.stages!.map(s => s.status)).toEqual(['done', 'done', 'error'])
    expect(JSON.parse(msg.stages![1]!.input!).options.lines).toEqual([1, 2])
    expect(msg.stages![1]!.output).toBe(output)
    expect(msg.stages![2]!.output).toBe('文件不存在')
    expect(chat.stages.value).toEqual([])
    store.restore()
    expect(store.activeMessages[1]!.stages).toEqual(msg.stages)
  })

  it('未授权工具即使最终正常答复也不能变为成功', async () => {
    runEvents(cb => {
      cb.onToolCall(call('search', 'WebSearch'))
      cb.onToolResult(result('search', false, 'Error: Allow searching the web?'))
      cb.onDone({})
    })
    await chat.sendRaw('搜索')
    expect(store.activeMessages[1]!.stages![0]!.status).toBe('denied')
  })

  it('仅在终帧报告的权限拒绝也随消息保留', async () => {
    runEvents(cb => {
      cb.onToolCall(call('write', 'Write'))
      cb.onDone({ permission_denials: [{ tool_use_id: 'write', tool_name: 'Write', decision_reason: 'needs approval' }] })
    })
    await chat.sendRaw('写入')
    expect(store.activeMessages[1]!.stages![0]!.status).toBe('denied')
  })

  it('停止时保留成功步骤与未完成步骤，不丢失空正文的消息', async () => {
    runEvents(cb => {
      cb.onToolCall(call('a'))
      cb.onToolResult(result('a'))
      cb.onToolCall(call('b'))
      chat.stopGeneration()
      throw new DOMException('停止', 'AbortError')
    })
    await chat.sendRaw('测试停止')
    expect(store.activeMessages).toHaveLength(2)
    expect(store.activeMessages[1]!.executionState).toBe('stopped')
    expect(store.activeMessages[1]!.stages!.map(s => s.status)).toEqual(['done', 'stopped'])
    store.restore()
    expect(store.activeMessages[1]!.stages).toHaveLength(2)
  })

  it.each(['事件错误', '网络异常'])('%s 保留已有答复和工具记录', async kind => {
    runEvents(cb => {
      cb.onToolCall(call('a'))
      cb.onToken('部分答复')
      if (kind === '事件错误') cb.onError('连接失败')
      else throw new Error('连接失败')
    })
    await chat.sendRaw('测试错误')
    expect(store.activeMessages[1]!.content).toBe('部分答复')
    expect(store.activeMessages[1]!.executionState).toBe('error')
    expect(store.activeMessages[1]!.stages!.map(s => s.status)).toEqual(['interrupted', 'error'])
  })

  it('正常完成但没有工具结果时显示未确认；无终帧 EOF 也不能假报成功', async () => {
    runEvents(cb => { cb.onToolCall(call('a')); cb.onDone({}) })
    await chat.sendRaw('没有结果')
    expect(store.activeMessages[1]!.stages![0]!.status).toBe('interrupted')
    runEvents(cb => { cb.onToolCall(call('b')) })
    await chat.sendRaw('没有终帧')
    expect(store.activeMessages[3]!.executionState).toBe('interrupted')
    expect(store.activeMessages[1]!.stages![0]!.id).toBe('a')
  })

  it('切换会话后，流式内容和执行结果仍落在发起会话', async () => {
    const original = store.activeSession!
    runEvents(cb => {
      cb.onToolCall(call('a'))
      store.createNewSession()
      cb.onToolResult(result('a'))
      cb.onToken('原会话答复')
      cb.onDone({})
    })
    await chat.sendRaw('跨会话')
    expect(store.activeMessages).toEqual([])
    expect(original.messages[1]!.content).toBe('原会话答复')
    expect(original.messages[1]!.stages![0]!.status).toBe('done')
    store.switchTo(original.id)
    expect(store.activeMessages[1]!.stages![0]!.input).toContain('a.md')
  })

  it('旧后端结果摘要不会伪装成完整输出', async () => {
    runEvents(cb => {
      cb.onToolCall(call('a'))
      cb.onToolResult({ name: 'Read', tool_use_id: 'a', summary: '旧摘要', success: true })
      cb.onDone({})
    })
    await chat.sendRaw('兼容')
    expect(store.activeMessages[1]!.stages![0]!.output).toBeUndefined()
    expect(store.activeMessages[1]!.stages![0]!.detail).toBe('旧摘要')
  })

  it('超长输入和结果有明确截断标记', async () => {
    runEvents(cb => {
      cb.onToolCall({ ...call('a'), args: { content: '中'.repeat(17000) } })
      cb.onToolResult(result('a', true, '文'.repeat(17000)))
      cb.onDone({})
    })
    await chat.sendRaw('长记录')
    const stage = store.activeMessages[1]!.stages![0]!
    expect(stage.input).toHaveLength(16000)
    expect(stage.output).toHaveLength(16000)
    expect(stage.inputTruncated && stage.outputTruncated).toBe(true)
  })

  it('刷新运行中快照后标记未确认，异常不覆盖', () => {
    store.activeMessages.push({ role: 'assistant', content: '', executionState: 'running', stages: [
      { type: 'tool_call', label: '读文件', status: 'running' },
      { type: 'tool_call', label: '搜索', status: 'denied' },
    ] })
    store.persist()
    store.restore()
    expect(store.activeMessages[0]!.executionState).toBe('interrupted')
    expect(store.activeMessages[0]!.stages!.map(s => s.status)).toEqual(['interrupted', 'denied'])
  })

  it('旧 error → done 不覆盖失败，也不触发成功后的命名和建议', async () => {
    runEvents(cb => {
      cb.onToken('部分答复')
      cb.onError('等待后续输出超时')
      cb.onDone({ status: 'completed' })
    })
    await chat.sendRaw('检查超时')
    expect(store.activeMessages[1]!.executionState).toBe('error')
    expect(store.activeMessages[1]!.stages!.at(-1)!.status).toBe('error')
    expect(generateChatTitle).not.toHaveBeenCalled()
    store.restore()
    expect(store.activeMessages[1]!.executionState).toBe('error')
  })

  it.each([
    [{ cancelled: true }, 'stopped'],
    [{ status: 'cancelled' as const }, 'stopped'],
    [{ status: 'incomplete' as const }, 'interrupted'],
    [{ status: 'error' as const }, 'error'],
    [{ error: '部分输出后失败' }, 'error'],
  ])('非成功 done %j 不走成功终态', async (terminal, expected) => {
    runEvents(cb => { cb.onToolCall(call('a')); cb.onDone(terminal) })
    await chat.sendRaw('终态测试')
    expect(store.activeMessages[1]!.executionState).toBe(expected)
    expect(store.activeMessages[1]!.stages![0]!.status).not.toBe('done')
    expect(generateChatTitle).not.toHaveBeenCalled()
  })

  it('补写进度持续到明确结果，成功写入后的超时仍保留失败与写回事实', async () => {
    runEvents(cb => {
      cb.onToken('主轮答复')
      cb.onStage({ stage: 'board_retry', label: '正在补写', status: 'running' })
      cb.onStage({ stage: 'thinking', label: '准备写入' })
      cb.onToolCall({ ...call('board-retry:c1', 'revise_insight_board'), args: { html: '<section>洞察</section>' } })
      expect(chat.stages.value.find(s => s.type === 'board_retry')!.status).toBe('running')
      cb.onToolResult({ name: 'revise_insight_board', tool_use_id: 'board-retry:c1', success: true, summary: 'revision=1' })
      cb.onStage({ stage: 'board_retry', label: '补写已落盘', status: 'done' })
      cb.onError('等待后续输出超时', { status: 'error', metadata: {
        model: 'test', rewritten: true, rewritten_tools: ['revise_insight_board'], turn_id: 'same-turn',
      } })
    })
    await chat.sendRaw('补写洞察板')
    const msg = store.activeMessages[1]!
    expect(msg.content).toBe('主轮答复')
    expect(msg.executionState).toBe('error')
    expect(msg.metadata!.rewritten).toBe(true)
    expect(msg.metadata!.turn_id).toBe('same-turn')
    expect(msg.stages!.find(s => s.type === 'board_retry')).toMatchObject({ status: 'done', label: '补写已落盘' })
    expect(msg.stages!.find(s => s.id === 'board-retry:c1')!.status).toBe('done')
    store.restore()
    expect(store.activeMessages[1]!.stages).toEqual(msg.stages)
  })

  it('补写失败和后端未确认结束不会成为成功', async () => {
    runEvents(cb => {
      cb.onStage({ stage: 'board_retry', label: '正在补写', status: 'running' })
      cb.onError('未收到完成结果', { status: 'incomplete' })
    })
    await chat.sendRaw('补写')
    expect(store.activeMessages[1]!.executionState).toBe('interrupted')
    expect(store.activeMessages[1]!.stages![0]!.status).toBe('interrupted')
  })

  it('存储失败提示一次，不能静默丢失记录', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('空间不足', 'QuotaExceededError') })
    store.persist()
    store.persist()
    expect(showToast).toHaveBeenCalledTimes(1)
    expect(showToast).toHaveBeenCalledWith('ai-panel.execution.persist_failed', 'warn')
  })
})
