/**
 * AI 聊天核心逻辑 / AI chat core logic
 *
 * 消息发送、动作执行、停止生成、跟进建议、数据注入。 / Message sending, action execution, stop generation, follow-up suggestions, data injection.
 * 消息持久化由 aiSessions store 管理。 / Message persistence managed by aiSessions store.
 */
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { sendMessageStream, injectItems } from '@/api/chat'
import type { ChatAction, ChatExtractedItem, ChatMessage, AgentStage } from '@/api/chat'
import { useTaskStore } from '@/stores/task'
import { useRealtimeStore } from '@/stores/realtime'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { useAgentStore } from '@/stores/agent'
import { useAiInsights } from '@/composables/useAiInsights'
import { showToast } from '@/composables/useToast'
import { tt } from '@/i18n'

const AI_MAX_CONTEXT = 20

interface FollowUpSuggestion {
  text: string
  icon: string
}

interface VerifiedChange {
  op: string
  todo_id: string
  field: string
  old: unknown
  new: unknown
  verified: boolean
}

const ICON_PLUS = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 8h8M8 4v8"/></svg>'
const ICON_LIST = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4h8M4 8h6M4 12h7"/></svg>'
const ICON_SEARCH = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7" cy="7" r="4"/><path d="M10 10l3.5 3.5"/></svg>'
const ICON_CLOCK = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 5v3l2 1"/></svg>'

/** 默认建议（原快捷命令），对话有内容但无 AI 推断建议时展示 / Default suggestions (original quick commands); shown when chat has content but no AI-inferred suggestions */
const DEFAULT_SUGGESTIONS: FollowUpSuggestion[] = [
  { text: '生成会议纪要', icon: ICON_LIST },
  { text: '提取待办事项', icon: ICON_PLUS },
  { text: '分析发言要点', icon: ICON_SEARCH },
]

export function useAiChat() {
  const router = useRouter()
  const route = useRoute()
  const taskStore = useTaskStore()
  const realtimeStore = useRealtimeStore()
  const aiSessions = useAiSessionsStore()
  const agentStore = useAgentStore()
  const insights = useAiInsights()

  const isLoading = ref(false)
  const isStreaming = ref(false)
  const abortController = ref<AbortController | null>(null)
  const followUps = ref<FollowUpSuggestion[]>([])
  const thinkingStartTime = ref(0)
  const stages = ref<AgentStage[]>([])

  /** 思考耗时（秒），流式期间实时更新，完成后归零 / Thinking elapsed seconds; live during streaming, resets after done */
  const thinkingElapsed = computed(() => {
    if (!thinkingStartTime.value) return 0
    return Math.floor((Date.now() - thinkingStartTime.value) / 1000)
  })

  /** 统一建议：对话为空或 AI 正在回复时隐藏；有推断建议时用推断，否则用默认 / Unified suggestions: hidden when chat is empty or AI is replying; use inferred suggestions when available, otherwise defaults */
  const displaySuggestions = computed(() => {
    if (messages.value.length === 0) return []
    if (isLoading.value) return []
    return followUps.value.length > 0 ? followUps.value : DEFAULT_SUGGESTIONS
  })
  const injectPrompt = ref<{ items: ChatExtractedItem[]; desc: string } | null>(null)
  const verifiedChanges = ref<VerifiedChange[]>([])

  const messages = computed(() => aiSessions.activeMessages)

  watch(() => taskStore.currentTaskId, (taskId) => {
    aiSessions.setChatKey(taskId)
    followUps.value = []
    injectPrompt.value = null
  }, { immediate: true })

  const canSend = computed(() => !isLoading.value)

  /** 发送原始文本消息（流式输出） / Send raw text message (streaming output) */
  async function sendRaw(text: string) {
    if (!text || isLoading.value) return

    const msgs = aiSessions.activeMessages
    msgs.push({ role: 'user', content: text, timestamp: new Date().toISOString() })
    if (msgs.length > AI_MAX_CONTEXT * 2) {
      aiSessions.activeMessages = msgs.slice(-AI_MAX_CONTEXT * 2)
    }

    isLoading.value = true
    isStreaming.value = false
    thinkingStartTime.value = Date.now()
    followUps.value = []
    injectPrompt.value = null
    stages.value = []

    const ctrl = new AbortController()
    abortController.value = ctrl

    const loadingIdx = aiSessions.activeMessages.length
    const assistantMsg: ChatMessage = { role: 'assistant', content: '', timestamp: new Date().toISOString() }
    aiSessions.activeMessages.push(assistantMsg)

    try {
      const histSlice = aiSessions.activeMessages.slice(-AI_MAX_CONTEXT)

      await sendMessageStream(text, {
        task_id: taskStore.currentTaskId || undefined,
        history: histSlice,
        realtime_transcripts: realtimeStore.getSnapshot(),
        current_page: (route.name as string) || undefined,
        role: agentStore.activeAgent || undefined,
        current_diagram: insights.lastViewedDiagram.value || undefined,
        signal: ctrl.signal,
      }, {
        onToken(token: string) {
          assistantMsg.content += token
          isStreaming.value = true
          // 不在首个 token 时清空 stages，保留到完成后折叠 / Keep stages visible during streaming, collapse after done
        },
        onStage(stageData) {
          // 更新或添加思考阶段 / Update or add thinking stage
          const existing = stages.value.find(s => s.type === stageData.stage)
          if (existing) {
            existing.label = stageData.label
          } else if (stageData.stage === 'thinking' || stageData.stage === 'generating') {
            // 将之前的 running 阶段标记为 done / Mark previous running stages as done
            stages.value.forEach(s => {
              if (s.status === 'running') s.status = 'done'
            })
            stages.value.push({
              type: stageData.stage as 'thinking' | 'generating',
              label: stageData.label,
              status: 'running',
            })
          }
        },
        onToolCall(tool) {
          // 将之前的 running 阶段标记为 done / Mark previous running stages as done
          stages.value.forEach(s => {
            if (s.status === 'running') s.status = 'done'
          })
          stages.value.push({
            type: 'tool_call',
            label: tool.label,
            icon: tool.icon,
            status: 'running',
            detail: Object.values(tool.args || {}).join(', '),
          })
        },
        onToolResult(result) {
          // 找到对应的 tool_call 并更新状态 / Find matching tool_call and update status
          const toolStage = [...stages.value].reverse().find(
            s => s.type === 'tool_call' && s.label === stages.value.find(st => st.type === 'tool_call')?.label
          )
          if (toolStage) {
            toolStage.status = result.success ? 'done' : 'error'
            toolStage.detail = result.summary
          }
        },
        onDone(data) {
          assistantMsg.timestamp = new Date().toISOString()
          if (data.metadata) assistantMsg.metadata = data.metadata
          if (data.sources) assistantMsg.sources = data.sources
          if (data.latency_ms != null) {
            assistantMsg.performance = {
              latency_ms: data.latency_ms,
              char_count: assistantMsg.content.length,
              context_block_count: data.context_block_count ?? 0,
              message_count: data.message_count ?? 0,
            }
          }
          // 保存思考阶段到消息（完成后折叠显示） / Save stages to message (collapsed after done)
          if (stages.value.length > 0) {
            assistantMsg.stages = [...stages.value]
            stages.value.forEach(s => { s.status = 'done' })
          }
          aiSessions.persist()

          if (data.extracted_items?.length) {
            showInjectPrompt(data.extracted_items)
          }
          // 图形化内容转发到洞察面板 / Forward diagram to insights panel
          if (data.diagram) {
            insights.setChatDiagram(data.diagram)
          }
          followUps.value = generateFollowUps(assistantMsg.content)
        },
        onError(error: string) {
          if (!assistantMsg.content) {
            aiSessions.activeMessages.splice(loadingIdx, 1)
            aiSessions.activeMessages.push({ role: 'assistant', content: `抱歉，出了点问题：${error}` })
          }
          aiSessions.persist()
        },
      })
    } catch (e: unknown) {
      if (assistantMsg.content) {
        // 已有部分内容，保留已生成的文本 / Already have partial content, keep it
        aiSessions.persist()
      } else {
        aiSessions.activeMessages.splice(loadingIdx, 1)
      }
      if (e instanceof Error && e.name === 'AbortError') {
        if (assistantMsg.content) {
          aiSessions.persist()
        } else {
          aiSessions.activeMessages.push({ role: 'assistant', content: '已停止生成。' })
          aiSessions.persist()
        }
      } else if (!assistantMsg.content) {
        const err = e as { response?: { data?: unknown }; message?: string }
        const data = err.response?.data
        let detail = '请求失败'
        if (data && typeof data === 'object') {
          const d = data as Record<string, unknown>
          if (typeof d.detail === 'string') {
            detail = d.detail
          } else if (d.detail && typeof d.detail === 'object') {
            const dd = d.detail as Record<string, unknown>
            if (typeof dd.message === 'string') detail = dd.message
            else if (typeof dd.error === 'string') detail = dd.error
            else if (typeof dd.hint === 'string') detail = dd.hint
          } else if (typeof d.message === 'string') {
            detail = d.message
          } else if (typeof d.error === 'string') {
            detail = d.error
          }
        } else if (err.message) {
          detail = err.message
        }
        aiSessions.activeMessages.push({ role: 'assistant', content: `抱歉，出了点问题：${detail}` })
        aiSessions.persist()
      }
    } finally {
      isLoading.value = false
      isStreaming.value = false
      thinkingStartTime.value = 0
      abortController.value = null
      // 延迟清空 stages，让 UI 有时间看到最终状态 / Delay clearing stages for UI
      setTimeout(() => { stages.value = [] }, 300)
    }
  }

  /** 发送用户输入（含引用内容） / Send user input (with quoted content) */
  async function sendWithQuote(text: string, quoteText: string, quoteSource: string) {
    if ((!text.trim() && !quoteText) || isLoading.value) return

    let fullText = text
    if (quoteText) {
      const ctx = `[用户引用了一段内容${quoteSource ? '（' + quoteSource + '）' : ''}]:\n"""${quoteText}"""\n`
      fullText = text ? ctx + '\n用户指令: ' + text : ctx + '\n请帮我处理这段引用内容'
    }

    await sendRaw(fullText)
  }

  /** 停止生成 / Stop generation */
  function stopGeneration() {
    abortController.value?.abort()
  }

  /** 执行后端返回的动作 / Execute action returned by backend */
  async function executeAction(action: ChatAction) {
    const d = action.data || {}

    switch (action.name) {
      case 'record_start': {
        const tid = d.task_id as string
        if (!tid) break
        if (taskStore.currentTaskId && (taskStore.currentTask?.status === 'recording' || taskStore.currentTask?.status === 'paused') && taskStore.currentTaskId !== tid) {
          showToast(tt('ai-panel.chat.duplicate_record'), 'warn')
        } else {
          // [状态同步] AI 触发录音后刷新任务列表 / [State Sync] Refresh task list after AI triggers recording
          await taskStore.loadTasks()
          taskStore.selectTask(tid)
          router.push(`/recording/${tid}`)
        }
        break
      }
      case 'record_stop':
      case 'record_pause':
      case 'record_resume': {
        // [状态同步] AI 触发录音操作后刷新任务列表 / [State Sync] Refresh task list after AI triggers recording operations
        taskStore.loadTasks()
        break
      }
      case 'retranscribe': {
        const tid = d.task_id as string
        if (tid) {
          taskStore.selectTask(tid)
          router.push(`/processing/${tid}`)
        }
        break
      }
      case 'retry_summary': {
        const tid = d.task_id as string
        if (tid) {
          taskStore.selectTask(tid)
          router.push(`/meeting/${tid}`)
        }
        break
      }
      case 'create_theme': {
        const name = d.theme_name as string || tt('ai-panel.chat.custom_theme')
        const hue = d.accent_hue as number || 255
        showToast(tt('ai-panel.chat.theme_created', { name, hue }), 'success')
        break
      }
    }
  }

  /** 显示数据注入提示 / Show data injection prompt */
  function showInjectPrompt(items: ChatExtractedItem[]) {
    const typeCounts: Record<string, number> = {}
    const typeLabels: Record<string, string> = {
      todo: tt('ai-panel.chat.type_todo'),
      conclusion: tt('ai-panel.chat.type_conclusion'),
      decision: tt('ai-panel.chat.type_decision'),
    }
    items.forEach(i => { typeCounts[i.type] = (typeCounts[i.type] || 0) + 1 })
    const desc = Object.entries(typeCounts)
      .map(([type, c]) => tt('ai-panel.chat.type_count', { count: c, type: typeLabels[type] || type }))
      .join(tt('ai-panel.chat.type_join'))
    injectPrompt.value = { items, desc }
  }

  /** 执行注入 / Execute injection */
  async function doInjectAll() {
    if (!injectPrompt.value || !taskStore.currentTaskId) return
    const items = injectPrompt.value.items
    try {
      await injectItems(taskStore.currentTaskId, items)
      showToast(tt('ai-panel.chat.injected', { count: items.length }), 'success')
      injectPrompt.value = null
    } catch {
      showToast(tt('ai-panel.chat.inject_failed'), 'error')
    }
  }

  /** 生成跟进建议 / Generate follow-up suggestions */
  function generateFollowUps(text: string): FollowUpSuggestion[] {
    const t = (text || '').toLowerCase()
    const suggestions: FollowUpSuggestion[] = []

    if (/待办|任务|行动|跟进|todo|action/.test(t)) {
      suggestions.push({ text: '展开某个待办事项的详情', icon: ICON_PLUS })
      suggestions.push({ text: '按责任人分类这些待办', icon: ICON_LIST })
    }
    if (/结论|决策|决定|达成|consensus|decision/.test(t)) {
      suggestions.push({ text: '展开讨论细节', icon: ICON_SEARCH })
      suggestions.push({ text: '还有哪些未达成共识的议题？', icon: ICON_CLOCK })
    }
    if (/风险|问题|挑战|隐患|risk|issue/.test(t)) {
      suggestions.push({ text: '如何规避这些风险？', icon: ICON_PLUS })
      suggestions.push({ text: '风险优先级排序', icon: ICON_LIST })
    }
    if (/总结|摘要|纪要|summary/.test(t)) {
      suggestions.push({ text: '生成会议纪要文档', icon: ICON_LIST })
      suggestions.push({ text: '还有哪些遗漏的信息？', icon: ICON_SEARCH })
    }
    if (/发言|说话|占比|speaker/.test(t)) {
      suggestions.push({ text: '各发言人的核心观点分别是什么？', icon: ICON_SEARCH })
      suggestions.push({ text: '谁的观点存在分歧？', icon: ICON_PLUS })
    }
    if (suggestions.length === 0) {
      suggestions.push({ text: '展开说说细节', icon: ICON_SEARCH })
      suggestions.push({ text: '帮我生成会议纪要', icon: ICON_LIST })
      suggestions.push({ text: '还有哪些值得深入探讨的？', icon: ICON_PLUS })
    }
    return suggestions.slice(0, 3)
  }

  /** 生成校验变化的可读描述 / Generate readable description of verified changes */
  function formatChangeDescription(change: VerifiedChange): string {
    const fieldLabels: Record<string, string> = {
      title: '标题',
      content: '内容',
      assignee: '责任人',
      deadline: '截止时间',
      status: '状态',
      priority: '优先级',
    }
    const label = fieldLabels[change.field] || change.field
    const oldVal = change.old ?? '空'
    const newVal = change.new ?? '空'
    return `${label}「${oldVal}」→「${newVal}」`
  }

  /** 清除对话 / Clear conversation */
  function clearConversation() {
    aiSessions.clearCurrentSession()
    followUps.value = []
    injectPrompt.value = null
    verifiedChanges.value = []
  }

  /** 重试最后一条消息 / Retry last message */
  async function retryLast(originalText: string) {
    await sendRaw(originalText)
  }

  return {
    messages, isLoading, isStreaming, thinkingElapsed, stages, followUps, displaySuggestions, injectPrompt, verifiedChanges, canSend, formatChangeDescription,
    sendRaw, sendWithQuote, stopGeneration, executeAction,
    doInjectAll, clearConversation, retryLast,
  }
}
