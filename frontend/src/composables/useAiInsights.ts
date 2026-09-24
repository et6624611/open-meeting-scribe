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
  /** 旧版结构化知识图谱（仅历史消息重载时存在，新分析不再产出）
      Legacy structured graph (only on reloaded historical messages; new analyses never emit it) */
  graph?: unknown
}

export interface InsightAction {
  key: string
  label: string
  primary?: boolean
}

const STORAGE_KEY = 'ai_insights_enabled'
const LEGACY_STORAGE_KEY = 'ai_proactive_enabled'

/** 自动分析频率档位 / Auto-analysis frequency level */
export type AutoFreq = 'off' | 'low' | 'normal' | 'high'
const FREQ_STORAGE_KEY = 'ai_insights_auto_freq'
/** 各档位对应的最小触发间隔（毫秒）；off 表示纯手动 / Min trigger interval (ms) per level; off = manual only */
const FREQ_INTERVAL_MS: Record<AutoFreq, number> = {
  off: 0,
  low: 300_000,
  normal: 180_000,
  high: 90_000,
}
/** 自动触发所需的最小新增转写行数（避免重复画同一张图） / Min new transcript lines required for auto trigger */
const AUTO_MIN_NEW_LINES = 8

function _loadAutoFreq(): AutoFreq {
  const v = localStorage.getItem(FREQ_STORAGE_KEY)
  return v === 'off' || v === 'low' || v === 'normal' || v === 'high' ? v : 'normal'
}

/* ─── 全局单例状态 / Global singleton state ─── */
const insightsEnabled = ref<boolean>(
  (localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY)) !== '0'
)
/** 自动分析频率（唯一暴露给用户的旋钮） / Auto-analysis frequency (the only user-facing knob) */
const autoFreq = ref<AutoFreq>(_loadAutoFreq())
/** 当前频率档对应的最小间隔 / Min interval for current frequency level */
const autoIntervalMs = computed(() => FREQ_INTERVAL_MS[autoFreq.value])

/* ─── 自动引擎内部游标（不暴露给用户） / Auto-engine internal cursors (not user-facing) ─── */
const autoAnalyzing: Ref<boolean> = ref(false)
let lastAnalyzedAt = 0
let lastAnalyzedLineCount = 0

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

/** 已从后端加载过消息的会议集合：区分「加载为空」与「未加载」，避免重复拉取
    Tasks whose messages were loaded from backend: distinguishes "loaded empty" vs "not loaded" */
const loadedTasks = new Set<string>()

/** 确保指定会议的洞察消息已从后端加载（未加载时拉取一次）
    Ensure insight messages for a task are loaded from backend (fetch once if missing) */
async function ensureTaskLoaded(taskId: string) {
  if (!taskId || loadedTasks.has(taskId)) return
  loadedTasks.add(taskId)
  try {
    const result = await loadInsightMessages(taskId)
    messagesByTask.value[taskId] = result.messages || []
  } catch {
    loadedTasks.delete(taskId)
    messagesByTask.value[taskId] = []
  }
}

/** 设置当前会议 ID（切换会议时调用，加载对应洞察消息） / Set current meeting ID (called when switching meetings; loads corresponding insight messages) */
async function setCurrentTask(taskId: string) {
  // 先保存当前会议的消息（如果有） / Save current meeting messages first (if any)
  if (currentTaskId.value && currentTaskId.value !== taskId) {
    await persistMessages(currentTaskId.value)
  }
  currentTaskId.value = taskId
  // 切换会议时重置自动引擎游标，避免跨会议误触发 / Reset auto-engine cursors on meeting switch to avoid cross-meeting misfire
  lastAnalyzedAt = 0
  lastAnalyzedLineCount = 0
  // 从后端加载该会议的洞察消息 / Load insight messages for this meeting from backend
  await ensureTaskLoaded(taskId)
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

/* ─── 分析（手动触发 + 自动触发共用核心） / Analysis (shared core for manual + auto trigger) ─── */

/** 手动分析加载状态 / Manual analysis loading state */
const manualAnalyzing: Ref<boolean> = ref(false)

type TranscriptLineInput = Array<{ text: string; speaker_id: number; begin_time: number }>

/**
 * 洞察分析核心：调用后端产出图卡片。手动/自动共用。
 * @param silentNoFinding 无发现时是否静默（自动路径 true，避免刷屏；手动路径 false，给正面反馈）
 * Core insight analysis: call backend to produce a diagram card. Shared by manual/auto.
 */
async function runAnalysis(
  recentLines: TranscriptLineInput,
  chapterTitles: string[],
  source: 'user' | 'system',
  analyzing: Ref<boolean>,
  silentNoFinding: boolean
) {
  analyzing.value = true
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
        source,
        tt('ai-panel.insights.cat_insight'),
        result.solution,
        result.diagram
      )
    } else if (!silentNoFinding) {
      // 手动触发且无发现 → 给出正面反馈 / Manual trigger with no finding → positive feedback
      addInsightMessage(
        tt('ai-panel.insights.manual_check_ok_title'),
        tt('ai-panel.insights.manual_check_ok_body'),
        [],
        'system',
        tt('ai-panel.insights.cat_insight')
      )
    }
  } catch {
    // API 调用失败静默忽略 / Silently ignore API call failures
  } finally {
    analyzing.value = false
  }
}

/**
 * 用户主动触发综合洞察分析 / User-triggered unified insight analysis
 * 数据不足时也会给出反馈，避免用户点击后无响应产生困扰。 / Provides feedback even when data is insufficient.
 * @param totalLineCount 当前转写总行数（可选），用于同步自动引擎游标，避免刚手动完又自动触发
 */
async function runManualAnalysis(
  recentLines: TranscriptLineInput,
  chapterTitles: string[],
  totalLineCount?: number
) {
  if (!insightsEnabled.value) return
  if (manualAnalyzing.value || autoAnalyzing.value) return

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
      tt('ai-panel.insights.cat_insight')
    )
    return
  }

  // 手动分析后刷新自动引擎游标，冷却从此刻重新计时 / Refresh auto-engine cursors after manual analysis
  lastAnalyzedAt = Date.now()
  if (typeof totalLineCount === 'number') lastAnalyzedLineCount = totalLineCount

  await runAnalysis(recentLines, chapterTitles, 'user', manualAnalyzing, false)
}

/**
 * 自动触发入口：由 RecordingView 监听转写增长时调用，内部按频率/冷却/门槛节流。
 * Auto trigger entry: called by RecordingView on transcript growth; throttled internally by frequency/cooldown/threshold.
 * @param totalLineCount 当前转写总行数，用于判断新增行阈值 / Current total transcript line count for new-line threshold
 */
async function maybeAutoAnalyze(
  recentLines: TranscriptLineInput,
  chapterTitles: string[],
  totalLineCount: number
) {
  if (!insightsEnabled.value) return
  if (autoFreq.value === 'off') return
  if (manualAnalyzing.value || autoAnalyzing.value) return
  // 数据门槛：无章节或转写太少不触发（静默） / Data gate: skip silently without chapters or too few lines
  if (chapterTitles.length === 0 || recentLines.length < 5) return
  // 冷却：距上次分析不足间隔不触发 / Cooldown: skip if interval not elapsed
  const now = Date.now()
  if (now - lastAnalyzedAt < autoIntervalMs.value) return
  // 新增行阈值：内容增长不足不重复画图 / New-line threshold: skip if not enough growth
  if (totalLineCount - lastAnalyzedLineCount < AUTO_MIN_NEW_LINES) return

  lastAnalyzedAt = now
  lastAnalyzedLineCount = totalLineCount
  await runAnalysis(recentLines, chapterTitles, 'system', autoAnalyzing, true)
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
    setEnabled(!insightsEnabled.value)
  }

  /** 设置功能开关：停用仅隐藏不清数据，重新启用后历史洞察原样恢复；
      内存缺失时从后端兜底重拉（B2 修复：停用→启用内容丢失）。
      Set feature on/off: disabling only hides (never clears); re-enabling restores
      history, with a backend reload as safety net when memory is missing. */
  function setEnabled(val: boolean) {
    insightsEnabled.value = val
    localStorage.setItem(STORAGE_KEY, val ? '1' : '0')
    if (val && currentTaskId.value) void ensureTaskLoaded(currentTaskId.value)
  }

  /** 设置自动分析频率 / Set auto-analysis frequency */
  function setAutoFreq(val: AutoFreq) {
    autoFreq.value = val
    localStorage.setItem(FREQ_STORAGE_KEY, val)
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
      tt('ai-panel.insights.cat_insight'),
      '',  // solution
      diagram
    )
  }

  return {
    // 状态 / State
    insightsEnabled,
    autoFreq,
    autoIntervalMs,
    insightMessages,
    unreadCount,
    latestUnread,
    // 操作 / Actions
    toggleEnabled,
    setEnabled,
    setAutoFreq,
    addInsightMessage,
    markAsRead,
    acknowledgeMessage,
    markAllRead,
    dismissInsightMessage,
    clearInsightMessages,
    toggleExpanded,
    getFirstUnread,
    // 会议绑定 / Meeting binding
    setCurrentTask,
    persistMessages,
    // 手动分析 / Manual analysis
    manualAnalyzing,
    runManualAnalysis,
    // 自动分析 / Auto analysis
    autoAnalyzing,
    maybeAutoAnalyze,
    // 导航辅助 / Navigation helper
    getActiveRecordingTaskId,
    // 对话图形化 / Chat diagram
    setChatDiagram,
    // 图交互状态 / Diagram interaction state
    lastViewedDiagram,
    diagramEditPending,
  }
}
