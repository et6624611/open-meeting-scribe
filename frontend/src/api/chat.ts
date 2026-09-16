/**
 * AI 对话 API 封装 / AI chat API wrapper
 */
import client from './client'

/** 项目引用来源 / Project source reference */
export interface SourceFile {
  title: string
  path: string
  name: string
}

/** LLM 响应元数据 / LLM response metadata */
export interface LlmMetadata {
  model: string
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  finish_reason: string
  id: string
}

/** 消息性能指标 / Message performance metrics */
export interface MessagePerformance {
  latency_ms: number
  char_count: number
  context_block_count: number
  message_count: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
  metadata?: LlmMetadata
  sources?: SourceFile[]
  performance?: MessagePerformance
  /** Agent 思考阶段列表 / Agent thinking stages */
  stages?: AgentStage[]
}

/** Agent 思考阶段 / Agent thinking stage */
export interface AgentStage {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'generating'
  label: string
  icon?: string
  status: 'running' | 'done' | 'error'
  detail?: string
}

export interface ChatAction {
  name: string
  data: Record<string, unknown>
}

export interface ChatExtractedItem {
  type: string
  content: string
}

export interface ChatResponse {
  reply: string
  /** Mermaid 图语法（画图意图触发时返回） / Mermaid diagram syntax (returned when diagram intent detected) */
  diagram?: string
  /** LLM 响应元数据（tokens、model、finish_reason 等） / LLM response metadata */
  metadata?: LlmMetadata
  /** 引用来源文件列表 / Referenced source files */
  sources?: SourceFile[]
  /** LLM 调用耗时（毫秒） / LLM call latency in ms */
  latency_ms?: number
  /** 注入的上下文块数 / Number of injected context blocks */
  context_block_count?: number
  /** 发送给 LLM 的消息数 / Number of messages sent to LLM */
  message_count?: number
  /** 后端实际返回的动作（单数对象） / Actual action returned by backend (singular object) */
  action?: {
    name: string | null
    success: boolean | null
    data: Record<string, unknown> | null
  }
  /** 兼容：部分场景可能返回数组 / Compat: some scenarios may return an array */
  actions?: ChatAction[]
  extracted_items?: ChatExtractedItem[]
  follow_ups?: string[]
  verified_changes?: Array<{
    op: string
    todo_id: string
    field: string
    old: unknown
    new: unknown
    verified: boolean
  }>
}

export interface ChatOptions {
  task_id?: string
  project_id?: string
  history?: ChatMessage[]
  realtime_transcripts?: Array<{
    text: string
    speaker_id: number
    begin_time: number
    end_time: number
  }> | null
  mode?: string
  model?: string
  /** 前端当前页面路由名，用于注入差异化上下文 / Current frontend route name, injected for differentiated context */
  current_page?: string
  /** Agent 角色标识，用于加载不同角色定义 / Agent role identifier for loading different role definitions */
  role?: string
  /** 当前可见的 Mermaid 图源码，用于图修改上下文 / Current visible Mermaid diagram source, for diagram modification context */
  current_diagram?: string
  signal?: AbortSignal
}

export async function sendMessage(
  message: string,
  options?: ChatOptions,
): Promise<ChatResponse> {
  const { data } = await client.post<ChatResponse>('/api/chat', {
    message,
    task_id: options?.task_id,
    project_id: options?.project_id,
    history: options?.history,
    realtime_transcripts: options?.realtime_transcripts,
    mode: options?.mode || 'agent',
    model: options?.model || 'qwen-plus',
    current_page: options?.current_page,
    role: options?.role,
    current_diagram: options?.current_diagram,
  }, {
    signal: options?.signal,
  })
  return data
}

/** 流式 SSE 事件回调 / Streaming SSE event callbacks */
export interface StreamCallbacks {
  onToken: (token: string) => void
  onStage: (stage: { stage: string; label: string }) => void
  onToolCall: (tool: { name: string; label: string; icon: string; args: Record<string, unknown> }) => void
  onToolResult: (result: { name: string; summary: string; success: boolean }) => void
  onDone: (data: {
    metadata?: LlmMetadata
    latency_ms?: number
    sources?: SourceFile[]
    extracted_items?: ChatExtractedItem[]
    context_block_count?: number
    message_count?: number
    agent_iterations?: number
    /** Mermaid 图语法 / Mermaid diagram syntax */
    diagram?: string
  }) => void
  onError: (error: string) => void
}

/** 流式发送消息（SSE） / Send message with streaming via SSE */
export async function sendMessageStream(
  message: string,
  options?: ChatOptions,
  callbacks?: StreamCallbacks,
): Promise<void> {
  const baseURL = (client.defaults as { baseURL?: string }).baseURL || ''
  const resp = await fetch(`${baseURL}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      task_id: options?.task_id,
      project_id: options?.project_id,
      history: options?.history,
      realtime_transcripts: options?.realtime_transcripts,
      mode: options?.mode || 'agent',
      model: options?.model || 'qwen-plus',
      current_page: options?.current_page,
      role: options?.role,
      current_diagram: options?.current_diagram,
    }),
    signal: options?.signal,
  })

  if (!resp.ok) {
    let errText = ''
    try {
      const errData = await resp.json()
      const detail = errData.detail || errData.detail?.message || errData.message || errData.error
      errText = typeof detail === 'string' ? detail : `HTTP ${resp.status}`
    } catch {
      errText = `HTTP ${resp.status}`
    }
    callbacks?.onError(errText)
    return
  }

  const reader = resp.body?.getReader()
  if (!reader) {
    callbacks?.onError('Streaming not supported')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const dataStr = line.slice(6)
        try {
          const event = JSON.parse(dataStr)
          if (event.type === 'token') {
            callbacks?.onToken(event.content)
          } else if (event.type === 'stage') {
            callbacks?.onStage(event)
          } else if (event.type === 'tool_call') {
            callbacks?.onToolCall(event)
          } else if (event.type === 'tool_result') {
            callbacks?.onToolResult(event)
          } else if (event.type === 'done') {
            callbacks?.onDone(event)
          } else if (event.type === 'error') {
            callbacks?.onError(event.content || 'Unknown error')
          }
        } catch {
          // Skip malformed JSON lines
        }
      }
    }
  }
}

/** 行间编辑响应 / Inline edit response */
export interface InlineEditResponse {
  ok: boolean
  original: string
  edited: string
}

/** 行间编辑：根据用户指令对选中文本进行 AI 改写 / Inline edit: rewrite selected text based on user instruction */
export async function inlineEdit(
  text: string,
  instruction: string,
  model?: string,
): Promise<InlineEditResponse> {
  const { data } = await client.post<InlineEditResponse>('/api/inline-edit', {
    text,
    instruction,
    model: model || 'qwen-plus',
  })
  return data
}

/** 注入提取内容到会议纪要 / Inject extracted items into meeting summary */
export async function injectItems(
  taskId: string,
  items: ChatExtractedItem[],
): Promise<void> {
  for (const item of items) {
    await client.post(`/api/tasks/${taskId}/inject`, {
      type: item.type,
      content: item.content,
      source_message: '',
    })
  }
}
