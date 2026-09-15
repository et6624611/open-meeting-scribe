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
  }, {
    signal: options?.signal,
  })
  return data
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
