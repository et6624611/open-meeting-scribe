/**
 * AI 聊天核心逻辑
 *
 * 消息发送、动作执行、停止生成、跟进建议、数据注入。
 * 消息持久化由 aiSessions store 管理。
 */
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { sendMessage, injectItems } from '@/api/chat'
import type { ChatAction, ChatExtractedItem, ChatResponse } from '@/api/chat'
import { useTaskStore } from '@/stores/task'
import { useRealtimeStore } from '@/stores/realtime'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { showToast } from '@/composables/useToast'

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

export function useAiChat() {
  const router = useRouter()
  const taskStore = useTaskStore()
  const realtimeStore = useRealtimeStore()
  const aiSessions = useAiSessionsStore()

  const isLoading = ref(false)
  const abortController = ref<AbortController | null>(null)
  const followUps = ref<FollowUpSuggestion[]>([])
  const injectPrompt = ref<{ items: ChatExtractedItem[]; desc: string } | null>(null)
  const verifiedChanges = ref<VerifiedChange[]>([])

  const messages = computed(() => aiSessions.activeMessages)

  watch(() => taskStore.currentTaskId, (taskId) => {
    aiSessions.setChatKey(taskId)
    followUps.value = []
    injectPrompt.value = null
  }, { immediate: true })

  const canSend = computed(() => !isLoading.value)

  /** 发送原始文本消息 */
  async function sendRaw(text: string) {
    if (!text || isLoading.value) return

    const msgs = aiSessions.activeMessages
    msgs.push({ role: 'user', content: text })
    if (msgs.length > AI_MAX_CONTEXT * 2) {
      aiSessions.activeMessages = msgs.slice(-AI_MAX_CONTEXT * 2)
    }

    isLoading.value = true
    followUps.value = []
    injectPrompt.value = null

    const ctrl = new AbortController()
    abortController.value = ctrl

    const loadingIdx = aiSessions.activeMessages.length
    aiSessions.activeMessages.push({ role: 'assistant', content: '思考中…' })

    try {
      const histSlice = aiSessions.activeMessages.slice(-AI_MAX_CONTEXT)
      const res: ChatResponse = await sendMessage(text, {
        task_id: taskStore.currentTaskId || undefined,
        history: histSlice,
        realtime_transcripts: realtimeStore.getSnapshot(),
        signal: ctrl.signal,
      })

      aiSessions.activeMessages[loadingIdx] = { role: 'assistant', content: res.reply }
      aiSessions.persist()

      if (res.verified_changes?.length) {
        verifiedChanges.value = res.verified_changes
      } else {
        verifiedChanges.value = []
      }

      if (res.actions?.length) {
        for (const action of res.actions) {
          executeAction(action)
        }
      }

      if (res.extracted_items?.length) {
        showInjectPrompt(res.extracted_items)
      }

      followUps.value = generateFollowUps(res.reply)
    } catch (e: unknown) {
      aiSessions.activeMessages.splice(loadingIdx, 1)
      if (e instanceof Error && e.name === 'AbortError') {
        aiSessions.activeMessages.push({ role: 'assistant', content: '已停止生成。' })
      } else {
        const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '请求失败'
        aiSessions.activeMessages.push({ role: 'assistant', content: `抱歉，出了点问题：${detail}` })
      }
      aiSessions.persist()
    } finally {
      isLoading.value = false
      abortController.value = null
    }
  }

  /** 发送用户输入（含引用内容） */
  async function sendWithQuote(text: string, quoteText: string, quoteSource: string) {
    if ((!text.trim() && !quoteText) || isLoading.value) return

    let fullText = text
    if (quoteText) {
      const ctx = `[用户引用了一段内容${quoteSource ? '（' + quoteSource + '）' : ''}]:\n"""${quoteText}"""\n`
      fullText = text ? ctx + '\n用户指令: ' + text : ctx + '\n请帮我处理这段引用内容'
    }

    await sendRaw(fullText)
  }

  /** 停止生成 */
  function stopGeneration() {
    abortController.value?.abort()
  }

  /** 执行后端返回的动作 */
  function executeAction(action: ChatAction) {
    const d = action.data || {}

    switch (action.name) {
      case 'record_start': {
        const tid = d.task_id as string
        if (!tid) break
        if (taskStore.currentTaskId && taskStore.currentTask?.status === 'recording' && taskStore.currentTaskId !== tid) {
          showToast('当前有任务正在进行，已忽略重复录音请求', 'warn')
        } else {
          taskStore.selectTask(tid)
          router.push(`/recording/${tid}`)
        }
        break
      }
      case 'record_stop': {
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
        const name = d.theme_name as string || '自定义主题'
        const hue = d.accent_hue as number || 255
        showToast(`主题「${name}」已创建（色相 ${hue}°）`, 'success')
        break
      }
    }
  }

  /** 显示数据注入提示 */
  function showInjectPrompt(items: ChatExtractedItem[]) {
    const typeCounts: Record<string, number> = {}
    const typeLabels: Record<string, string> = { todo: '待办', conclusion: '结论', decision: '决策' }
    items.forEach(i => { typeCounts[i.type] = (typeCounts[i.type] || 0) + 1 })
    const desc = Object.entries(typeCounts).map(([t, c]) => `${c} 条${typeLabels[t] || t}`).join('、')
    injectPrompt.value = { items, desc }
  }

  /** 执行注入 */
  async function doInjectAll() {
    if (!injectPrompt.value || !taskStore.currentTaskId) return
    const items = injectPrompt.value.items
    try {
      await injectItems(taskStore.currentTaskId, items)
      showToast(`已注入 ${items.length} 条内容`, 'success')
      injectPrompt.value = null
    } catch {
      showToast('注入失败，请重试', 'error')
    }
  }

  /** 生成跟进建议 */
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

  /** 生成校验变化的可读描述 */
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

  /** 清除对话 */
  function clearConversation() {
    aiSessions.clearCurrentSession()
    followUps.value = []
    injectPrompt.value = null
    verifiedChanges.value = []
  }

  /** 重试最后一条消息 */
  async function retryLast(originalText: string) {
    await sendRaw(originalText)
  }

  return {
    messages, isLoading, followUps, injectPrompt, verifiedChanges, canSend, formatChangeDescription,
    sendRaw, sendWithQuote, stopGeneration, executeAction,
    doInjectAll, clearConversation, retryLast,
  }
}
