/**
 * 洞察台 — 状态管理 composable / Insight Deck — state management composable
 *
 * 管理洞察台功能的消息列表、未读计数。 / Manages Insight Deck message list, unread count.
 * 用户手动触发分析，无自动扫描。 / User-triggered analysis only, no auto scanning.
 */
import { ref, computed, type Ref } from 'vue'
import { tt } from '@/i18n'
import { runInsightAnalysis, loadInsightMessages, saveInsightMessages } from '@/api/insights'
import { buildDiagramCaption } from '@/utils/mermaidCaption'

/** 洞察消息结构 / Insight message structure */
export interface InsightMessage {
  id: string
  /** 消息标题 / Message title */
  title: string
  /** 消息正文（支持 HTML） / Message body (supports HTML) */
  body: string
  /** 操作按钮 / Action buttons */
  actions: InsightAction[]
  /** 时间戳 / Timestamp */
  timestamp: number
  /** 触发来源：user = 用户手动触发 / Trigger source: user = manually triggered */
  source: 'user' | 'system'
  /** 是否已读 / Whether read */
  read: boolean
  /** 消息分类标签 / Category label */
  category: string
  /** AI 建议的解决方案（展开后显示） / AI-suggested solution (shown when expanded) */
  solution: string
  /** 是否已展开 / Whether expanded */
  expanded: boolean
  /** 是否已确认 / Whether acknowledged */
  acknowledged: boolean
  /** Mermaid 图语法（可选） / Mermaid diagram syntax (optional) */
  diagram?: string
}

export interface InsightAction {
  key: string
  label: string
  primary?: boolean
}

const STORAGE_KEY = 'ai_insights_enabled'
const LEGACY_STORAGE_KEY = 'ai_proactive_enabled'

/* ─── 全局单例状态 / Global singleton state ─── */
const insightsEnabled = ref<boolean>(
  (localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY)) !== '0'
)

/** 当前会议 ID（引擎运行时绑定） / Current meeting ID (bound at engine runtime) */
const currentTaskId = ref<string>('')
/** 按会议隔离的消息存储：taskId → InsightMessage[] / Meeting-isolated message storage: taskId → InsightMessage[] */
const messagesByTask = ref<Record<string, InsightMessage[]>>({})
/** 当前会议的洞察消息（计算属性，自动跟随 currentTaskId 切换） / Insight messages for current meeting (computed, auto-follows currentTaskId) */
const insightMessages = computed<InsightMessage[]>(() => {
  const tid = currentTaskId.value
  if (!tid) return []
  if (!messagesByTask.value[tid]) messagesByTask.value[tid] = []
  return messagesByTask.value[tid]
})

let _idSeq = 0
function nextId(): string {
  return `insight-${Date.now()}-${++_idSeq}`
}

/* ─── 消息持久化 / Message persistence ─── */

/** 将指定会议的洞察消息持久化到后端 / Persist insight messages for a meeting to backend */
async function persistMessages(taskId: string) {
  if (!taskId) return
  const msgs = messagesByTask.value[taskId]
  if (!msgs) return
  try {
    await saveInsightMessages(taskId, msgs)
  } catch (e) {
    // 持久化失败不阻断用户体验 / Persist failure does not block user experience
  }
}

/** 设置当前会议 ID（切换会议时调用，加载对应洞察消息） / Set current meeting ID (called when switching meetings; loads corresponding insight messages) */
async function setCurrentTask(taskId: string) {
  // 先保存当前会议的消息（如果有） / Save current meeting messages first (if any)
  if (currentTaskId.value && currentTaskId.value !== taskId) {
    await persistMessages(currentTaskId.value)
  }
  currentTaskId.value = taskId
  // 从后端加载该会议的洞察消息 / Load insight messages for this meeting from backend
  if (taskId && !messagesByTask.value[taskId]) {
    try {
      const result = await loadInsightMessages(taskId)
      messagesByTask.value[taskId] = result.messages || []
    } catch {
      messagesByTask.value[taskId] = []
    }
  }
}

/* ─── 消息管理 / Message management ─── */

/** 添加一条洞察消息 / Add an insight message */
function addInsightMessage(
  title: string,
  body: string,
  actions: InsightAction[],
  source: 'user' | 'system' = 'user',
  category = '',
  solution = '',
  diagram = ''
): string {
  if (!insightsEnabled.value) return ''
  const id = nextId()
  insightMessages.value.push({
    id,
    title,
    body,
    actions,
    timestamp: Date.now(),
    source,
    read: false,
    category,
    solution,
    expanded: false,
    acknowledged: false,
    diagram: diagram || undefined,
  })
  // 实时持久化 / Realtime persist
  if (currentTaskId.value) persistMessages(currentTaskId.value)
  return id
}

/* ─── 手动分析（用户主动触发） / Manual analysis (user-triggered) ─── */

/** 手动分析加载状态 / Manual analysis loading state */
const manualAnalyzing: Ref<boolean> = ref(false)

/**
 * 用户主动触发综合洞察分析 / User-triggered unified insight analysis
 * 数据不足时也会给出反馈，避免用户点击后无响应产生困扰。 / Provides feedback even when data is insufficient.
 */
async function runManualAnalysis(
  recentLines: Array<{ text: string; speaker_id: number; begin_time: number }>,
  chapterTitles: string[]
) {
  if (!insightsEnabled.value) return
  if (manualAnalyzing.value) return

  // 数据不足时给出反馈 / Provide feedback when data is insufficient
  if (recentLines.length < 5 || chapterTitles.length === 0) {
    const reasons: string[] = []
    if (recentLines.length < 5) reasons.push(tt('ai-panel.insights.manual_check_need_transcript'))
    if (chapterTitles.length === 0) reasons.push(tt('ai-panel.insights.manual_check_need_chapters'))
    addInsightMessage(
      tt('ai-panel.insights.manual_check_insufficient_title'),
      reasons.join(''),
      [],
      'system',
      tt('ai-panel.insights.cat_context')
    )
    return
  }

  manualAnalyzing.value = true
  try {
    const result = await runInsightAnalysis({
      recent_lines: recentLines.slice(-20),
      chapter_titles: chapterTitles,
    })

    if (result.has_finding && result.title) {
      addInsightMessage(
        result.title,
        result.body,
        [{ key: 'acknowledge', label: tt('ai-panel.insights.action_acknowledge'), primary: true }],
        'user',
        tt('ai-panel.insights.cat_context'),
        result.solution,
        result.diagram
      )
    } else {
      // 手动触发且无发现 → 给出正面反馈 / Manual trigger with no finding → positive feedback
      addInsightMessage(
        tt('ai-panel.insights.manual_check_ok_title'),
        tt('ai-panel.insights.manual_check_ok_body'),
        [],
        'system',
        tt('ai-panel.insights.cat_context')
      )
    }
  } catch {
    // API 调用失败静默忽略 / Silently ignore API call failures
  } finally {
    manualAnalyzing.value = false
  }
}

/* ─── 预设场景 / Preset scenarios ─── */

/**
 * 场景 A：会议结束后，主动推送待办提取提醒 / Scenario A: After meeting ends, proactively push todo extraction reminder
 */
function triggerMeetingEndTodos(todoList: Array<{ text: string; assignee?: string; deadline?: string }>) {
  if (!insightsEnabled.value) return ''
  const items = todoList.map(todo => {
    let line = `<li><strong>${todo.text}</strong>`
    const meta: string[] = []
    if (todo.deadline) meta.push(tt('ai-panel.insights.todo_deadline', { deadline: todo.deadline }))
    if (todo.assignee) meta.push(tt('ai-panel.insights.todo_assignee', { name: todo.assignee }))
    if (meta.length) line += ` — ${meta.join(' · ')}`
    line += '</li>'
    return line
  }).join('')

  const bodyHtml = tt('ai-panel.insights.scene_meeting_end_body_pre')
    + `<strong>${todoList.length}${tt('ai-panel.insights.scene_meeting_end_body_unit')}</strong>`
    + `<ul>${items}</ul>`

  return addInsightMessage(
    tt('ai-panel.insights.scene_meeting_end_title'),
    bodyHtml,
    [
      { key: 'view', label: tt('ai-panel.insights.action_view'), primary: true },
      { key: 'sync', label: tt('ai-panel.insights.action_sync') },
      { key: 'later', label: tt('ai-panel.insights.action_later') },
    ]
  )
}

/** 获取当前正在录音的任务 ID（供侧边栏洞察按钮导航使用） / Get currently recording task ID (for sidebar insight button navigation) */
function getActiveRecordingTaskId(): string {
  if (currentTaskId.value) return currentTaskId.value
  return ''
}

/* ─── 图交互状态（跨组件共享） / Diagram interaction state (cross-component shared) ─── */

/** 当前可见的图源码（展开卡片时自动更新，用于 AI 对话图修改上下文） / Current visible diagram source (auto-updated on card expand, used for AI chat diagram modification context) */
const lastViewedDiagram = ref<string>('')

/** 图编辑请求（“在对话中编辑”按钮触发，AIPanel 监听后预填输入框） / Diagram edit request (triggered by "Edit in Chat" button, AIPanel watches and pre-fills input) */
const diagramEditPending = ref<string>('')

export function useAiInsights() {
  /** 未读消息数 / Unread message count */
  const unreadCount = computed(() =>
    insightMessages.value.filter(m => !m.read).length
  )

  /** 最新的未读消息（用于横幅展示） / Latest unread message (for banner display) */
  const latestUnread = computed(() =>
    insightMessages.value.find(m => !m.read) ?? null
  )

  /** 切换功能开关 / Toggle feature on/off */
  function toggleEnabled() {
    insightsEnabled.value = !insightsEnabled.value
    localStorage.setItem(STORAGE_KEY, insightsEnabled.value ? '1' : '0')
    if (!insightsEnabled.value) {
      if (currentTaskId.value) messagesByTask.value[currentTaskId.value] = []
    }
  }

  /** 设置功能开关 / Set feature on/off */
  function setEnabled(val: boolean) {
    insightsEnabled.value = val
    localStorage.setItem(STORAGE_KEY, val ? '1' : '0')
    if (!val) {
      if (currentTaskId.value) messagesByTask.value[currentTaskId.value] = []
    }
  }

  /** 标记消息已读 / Mark message as read */
  function markAsRead(id: string) {
    const msg = insightMessages.value.find(m => m.id === id)
    if (msg) msg.read = true
  }

  /** 确认消息：折叠卡片 / Acknowledge message: collapse card */
  function acknowledgeMessage(id: string) {
    const msg = insightMessages.value.find(m => m.id === id)
    if (msg) {
      msg.acknowledged = true
      msg.expanded = false
      msg.read = true
      if (currentTaskId.value) persistMessages(currentTaskId.value)
    }
  }

  /** 切换消息展开/折叠（同时更新 lastViewedDiagram） / Toggle message expand/collapse (also updates lastViewedDiagram) */
  function toggleExpanded(id: string) {
    const msg = insightMessages.value.find(m => m.id === id)
    if (msg) {
      msg.expanded = !msg.expanded
      if (msg.expanded) {
        msg.read = true
        // 展开时记录当前图源码，供 AI 对话图修改使用 / Track diagram source on expand for AI chat diagram modification
        if (msg.diagram) lastViewedDiagram.value = msg.diagram
      }
    }
  }

  /** 获取第一条未读消息 / Get first unread message */
  function getFirstUnread(): InsightMessage | null {
    return insightMessages.value.find(m => !m.read) ?? null
  }

  /** 标记全部已读 / Mark all as read */
  function markAllRead() {
    insightMessages.value.forEach(m => { m.read = true })
  }

  /** 移除消息 / Remove message */
  function dismissInsightMessage(id: string) {
    const idx = insightMessages.value.findIndex(m => m.id === id)
    if (idx >= 0) insightMessages.value.splice(idx, 1)
  }

  /** 清空当前会议的洞察消息 / Clear insight messages for current meeting */
  function clearInsightMessages() {
    if (currentTaskId.value) messagesByTask.value[currentTaskId.value] = []
  }

  /**
   * 接收来自 AI 对话的图形化内容，创建洞察消息并渲染。
   * 卡片 body 为从 Mermaid 代码解析的结构图例，而非对话回复全文——
   * 散文解释留在对话侧，避免两处内容重复。
   * Receive diagram from AI chat, create insight message and render.
   * Card body is a structural legend parsed from the Mermaid code, not the full chat reply —
   * prose stays in chat to avoid duplication.
   */
  function setChatDiagram(diagram: string) {
    if (!diagram || !insightsEnabled.value) return
    addInsightMessage(
      tt('ai-panel.insights.diagram_card_title'),
      buildDiagramCaption(diagram, tt),
      [{ key: 'acknowledge', label: tt('ai-panel.insights.action_acknowledge'), primary: true }],
      'user',
      tt('ai-panel.insights.cat_context'),
      '',  // solution
      diagram
    )
  }

  return {
    // 状态 / State
    insightsEnabled,
    insightMessages,
    unreadCount,
    latestUnread,
    // 操作 / Actions
    toggleEnabled,
    setEnabled,
    addInsightMessage,
    markAsRead,
    acknowledgeMessage,
    markAllRead,
    dismissInsightMessage,
    clearInsightMessages,
    toggleExpanded,
    getFirstUnread,
    // 预设场景 / Preset scenarios
    triggerMeetingEndTodos,
    // 会议绑定 / Meeting binding
    setCurrentTask,
    persistMessages,
    // 手动分析 / Manual analysis
    manualAnalyzing,
    runManualAnalysis,
    // 导航辅助 / Navigation helper
    getActiveRecordingTaskId,
    // 对话图形化 / Chat diagram
    setChatDiagram,
    // 图交互状态 / Diagram interaction state
    lastViewedDiagram,
    diagramEditPending,
  }
}
