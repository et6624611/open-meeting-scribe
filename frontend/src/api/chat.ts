/**
 * AI 对话 API 封装
 */
import client from './client'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
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
  }, {
    signal: options?.signal,
  })
  return data
}

/** 注入提取内容到会议纪要 */
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
