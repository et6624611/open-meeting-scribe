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
  /** 回显字段按链路而异：byok/自动改用等链路可能只回 model，usage 整体或部分缺失 */
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number }
  finish_reason?: string
  id?: string
  /** 智能体模式引擎标识（回显与多轮恢复判定用） */
  engine?: string
  /** 完成护栏（模式即权限 §5.4）：本轮写工具是否成功落过盘（仅智能体链路携带） */
  rewritten?: boolean
  /** 本轮实际发生过的写工具（剥 mcp__ 前缀的裸名，去重后升序） */
  rewritten_tools?: string[]
  /** 本轮标识：写回快照的关联键，传此 id 可整轮回滚（§5.4 恢复入口） */
  turn_id?: string
  /** 本轮写回发生的会议 id */
  task_id?: string
  /** 本轮实际落档（readonly|workspace_write|full_task） */
  auth_tier?: string
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
  /** 本轮实际消费方与计费回显（REQ-EXPERT-MODE §2.3，与 routing 判定一致） */
  modelUsage?: ModelUsage
  /** 发送时快照（编辑再发送回填用）：模式 + 问答模型 + 智能体引擎模型 */
  sendOptions?: SendSnapshot
  /** 用户本轮 @附件 上传的附件（仅用户消息） / Attachments uploaded with this turn (user messages only) */
  attachments?: AttachmentMeta[]
}

/** AI 会话附件元数据 / AI chat attachment metadata */
export interface AttachmentMeta {
  id: string
  filename: string
  size: number
  content_type: string
}

/** 用户消息发送时的参数快照 / Snapshot of options when the user message was sent */
export interface SendSnapshot {
  mode: 'qa' | 'agent'
  /** 问答模式 LLM 模型（'' = 跟随详情） */
  model?: string
  /** 智能体模式 CLI 引擎模型（'' = 引擎默认） */
  agentModel?: string
}

/** 回复尾部使用回显：模型 · 算力来源 · 计费口径 */
export interface ModelUsage {
  model: string
  source: 'trial' | 'byok' | 'local_endpoint' | 'local' | ''
  route: string
  billing: 'platform_quota' | 'own_key' | 'none' | ''
  auto_switched: boolean
}

/** Agent 思考阶段 / Agent thinking stage */
export interface AgentStage {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'generating'
  label: string
  icon?: string
  status: 'running' | 'done' | 'error'
  detail?: string
  /** 工具调用 id（智能体模式并行工具按此配对，不靠数组下标） */
  id?: string
  /** 工具原始名（含 mcp__ 前缀）：完成护栏按名定性与 tool_result 不带 name 时回溯用 */
  name?: string
  /** 英文标签（CLI 引擎工具调用双语，按当前 locale 选取） */
  label_en?: string
  /** 后端 i18n 键（ai-panel 命名空间；智能体引擎文案不硬嵌中文） */
  hint_key?: string
  hint_params?: Record<string, unknown>
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
  /** 引擎路由：undefined=内置链路；'agent'=本地 CLI（auto 规则分流已退役：AI 算力入口治理 §1） */
  engine?: 'agent'
  /** 本轮流标识，供 /api/chat/cancel 真取消（§3.9-5） */
  stream_id?: string
  /** 本轮授权档覆盖（readonly|workspace_write|full_task），缺省取设置 */
  auth_tier?: string
  /** 是否恢复上一 CLI 会话（多轮深度对话） */
  resume_session?: boolean
  /** 面板会话标签 id，令 CLI 会话与面板会话对齐（同标签多轮自然延续） */
  chat_session_id?: string
  /** 智能体轮级 CLI 模型覆盖（编辑再发送），缺省后端读 chat_engine.model */
  agentModel?: string
  /** 当前轮 @附件 引用，仅当前轮展开 / Attachments for this turn only */
  attachments?: AttachmentMeta[]
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
    model: options?.model || undefined, // 缺省不写死：后端跟随详情 llm.model（REQ-EXPERT-MODE §2.3）
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
  onStage: (stage: { stage: string; label: string; label_en?: string; hint_key?: string; hint_params?: Record<string, unknown> }) => void
  onToolCall: (tool: { name: string; label: string; label_en?: string; icon: string; args: Record<string, unknown>; id?: string }) => void
  onToolResult: (result: { name: string; summary: string; success: boolean; tool_use_id?: string }) => void
  /** 智能体模式路由回显（§3.9-1）：本次由哪个引擎/授权档执行，含 auto 自动选中标记 */
  onEngineRoute?: (info: { engine: string; display_name: string; name_key?: string; auth_tier: string; session_id?: string; auto_selected?: boolean }) => void
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
    /** 引擎标识（智能体模式回显） */
    engine?: string
    /** 本轮消费方/计费回显（与 core/routing 实际判定一致） */
    model_usage?: ModelUsage
    /** 完成护栏：写回事实（仅智能体链路；问答路径无此字段） */
    rewritten?: boolean
  }) => void
  onError: (error: string, extra?: { hint_key?: string; hint_params?: Record<string, unknown> }) => void
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
      model: options?.model || undefined, // 缺省不写死：后端跟随详情 llm.model（REQ-EXPERT-MODE §2.3）
      current_page: options?.current_page,
      role: options?.role,
      current_diagram: options?.current_diagram,
      engine: options?.engine,
      stream_id: options?.stream_id,
      auth_tier: options?.auth_tier,
      resume_session: options?.resume_session,
      chat_session_id: options?.chat_session_id,
      agent_model: options?.agentModel,
      attachments: options?.attachments,
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
          } else if (event.type === 'engine_route') {
            callbacks?.onEngineRoute?.(event)
          } else if (event.type === 'done') {
            callbacks?.onDone(event)
          } else if (event.type === 'error') {
            callbacks?.onError(event.content || 'Unknown error',
              { hint_key: event.hint_key, hint_params: event.hint_params })
          }
        } catch {
          // Skip malformed JSON lines
        }
      }
    }
  }
}

/** 真取消（智能体模式）：kill 后端 CLI 进程组，fetch abort 不足以终止任务（§3.9-5） */
export async function cancelStream(streamId: string): Promise<boolean> {
  try {
    const { data } = await client.post<{ cancelled: boolean }>('/api/chat/cancel', { stream_id: streamId })
    return !!data.cancelled
  } catch {
    return false
  }
}

/** 删除面板会话时联动清理其智能体工作区（方案 D5：数据留痕不只进不出） */
export async function cleanupAgentWorkspace(chatSessionId: string, taskId?: string): Promise<boolean> {
  try {
    await client.post('/api/agent-tools/cleanup', { chat_session_id: chatSessionId, task_id: taskId })
    return true
  } catch {
    return false
  }
}

/** 会话自动命名（AI 命名，仅此一种来源）：首轮完成后后台调用。
 *  失败/异常静默回空串，调用方保留默认名，不打断用户。 */
export async function generateChatTitle(firstMessage: string, reply: string): Promise<string> {
  try {
    const { data } = await client.post<{ ok: boolean; title: string }>('/api/chat/title', {
      first_message: firstMessage,
      reply,
    })
    return data.ok ? (data.title || '') : ''
  } catch {
    return ''
  }
}

/** @附件：上传本地文件与图片，返回服务端元数据 / Upload local files & images for @附件 */
export async function uploadChatAttachments(files: File[]): Promise<AttachmentMeta[]> {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  const { data } = await client.post<{ attachments: AttachmentMeta[] }>(
    '/api/chat/attachments', form,
    { headers: { 'Content-Type': 'multipart/form-data' } })
  return data.attachments
}

/** @附件：预览/下载地址 / Attachment preview or download URL */
export function attachmentUrl(meta: AttachmentMeta, download = false): string {
  const base = (client.defaults as { baseURL?: string }).baseURL || ''
  return `${base}/api/chat/attachments/${meta.id}${download ? '?download=1' : ''}`
}

/** 行间编辑响应 / Inline edit response */
export interface InlineEditResponse {
  ok: boolean
  original: string
  edited: string
  /** 执行回显（AI 算力入口治理 §3）：面板外函数类操作的实际消费方/计费口径 */
  model_usage?: ModelUsage
}

/** 行间编辑：根据用户指令对选中文本进行 AI 改写 / Inline edit: rewrite selected text based on user instruction */
export async function inlineEdit(
  text: string,
  instruction: string,
  model?: string,
): Promise<InlineEditResponse> {
  // 仅在显式指定时才发送 model，否则后端使用设置中的配置默认値
  const body: { text: string; instruction: string; model?: string } = { text, instruction }
  if (model) body.model = model
  const { data } = await client.post<InlineEditResponse>('/api/inline-edit', body)
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
