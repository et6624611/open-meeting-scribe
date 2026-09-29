/**
 * 洞察台 — 状态管理 composable / Insight Deck — state management composable
 *
 * 管理洞察台功能的消息列表、未读计数。 / Manages Insight Deck message list, unread count.
 * 用户手动触发分析，无自动扫描。 / User-triggered analysis only, no auto scanning.
 */
import { ref, computed, type Ref } from 'vue'
import { tt } from '@/i18n'
import { runInsightAnalysis, loadInsightMessages, saveInsightMessages, runPostMeetingAnalysis as apiRunPostMeetingAnalysis } from '@/api/insights'
import { buildDiagramCaption } from '@/utils/mermaidCaption'
import { cardSlots, normalizeFactor } from '@/utils/pageBudget'

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
  /** 备查注释层（展开后显示，退可忽略/进可查看） / Note layer (shown when expanded; skippable yet answerable) */
  note?: string
  /** 是否已展开 / Whether expanded */
  expanded: boolean
  /** 是否已确认 / Whether acknowledged */
  acknowledged: boolean
  /** Mermaid 图语法（可选） / Mermaid diagram syntax (optional) */
  diagram?: string
  /** 产生阶段：会中（缺省）/ 会后补分析 / Phase: in-meeting (default) or post-meeting supplement */
  phase?: 'meeting' | 'post_meeting'
  /** 一页纸系数预算降级标记：超位旧卡进折叠「历史观察」层，不删除不消失（后端写盘前统一重排）
   *  Deferred by the one-page card-slot budget: overflow cards fold into the history layer (never deleted) */
  deferred?: boolean
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

/* 【已退役】定时自动分析引擎（autoFreq/maybeAutoAnalyze/内部游标）随
   「洞察共创 · 会话驱动」下线：洞察生成/修订改由会话面板中人与 AI 共创驱动。 */

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

/** 当前会议的一页纸系数（洞察面）：由宿主视图从 task.one_page.insights 同步；缺省 1
    Current meeting's one-page factor for the Insight Deck; synced by the host view from task JSON */
const onePageInsights = ref<number>(1)

/** 设置当前会议的洞察面系数（角标改档/切会时调用） / Set the meeting's insight-side factor */
function setOnePageInsights(factor: number | null | undefined) {
  onePageInsights.value = normalizeFactor(factor)
}

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
    const resp = await saveInsightMessages(taskId, msgs)
    // 后端写盘前按系数重排并回传全量列表：以重拉语义替换本地，避免陈旧内存下次整体覆盖
    // Backend rebalances before persisting and returns the full list; adopt it to keep local state fresh
    if (Array.isArray(resp.messages)) {
      messagesByTask.value[taskId] = resp.messages as InsightMessage[]
    }
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

/** 强制重拉指定会议的洞察消息 / Force-reload a meeting's insight messages from backend.
 *
 * 文本回溯修正（POST /api/tasks/{id}/correct-text）在后端改写了 insights.json，而这里有一份
 * 按会议隔离的内存缓存。不重拉就会出现「洞察卡片仍写旧词、洞察板已是新词」的分裂视图；
 * 更糟的是切会议时的 persistMessages 会把这份陈旧数组整体写回，覆盖刚落盘的修正。
 * A retroactive correction rewrites insights.json on disk while this module keeps an
 * in-memory copy; skipping the reload both shows stale text and lets the next
 * persistMessages overwrite the fresh correction with the stale array. */
async function reloadTaskMessages(taskId: string) {
  if (!taskId) return
  loadedTasks.delete(taskId)
  await ensureTaskLoaded(taskId)
}

/** 设置当前会议 ID（切换会议时调用，加载对应洞察消息） / Set current meeting ID (called when switching meetings; loads corresponding insight messages) */
async function setCurrentTask(taskId: string) {
  // 先保存当前会议的消息（如果有） / Save current meeting messages first (if any)
  if (currentTaskId.value && currentTaskId.value !== taskId) {
    await persistMessages(currentTaskId.value)
  }
  currentTaskId.value = taskId
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
  diagram = '',
  note = ''
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
    note: note || undefined,
  })
  // 实时持久化 / Realtime persist
  if (currentTaskId.value) persistMessages(currentTaskId.value)
  return id
}

/* ─── 分析（手动触发 + 自动触发共用核心） / Analysis (shared core for manual + auto trigger) ─── */

/** 手动分析加载状态 / Manual analysis loading state */
const manualAnalyzing: Ref<boolean> = ref(false)

type TranscriptLineInput = Array<{ text: string; speaker_id: number; begin_time: number }>

/* 已有洞察摘要预算（只读累进 Phase 1）：与后端截断预算对等，前端先行控制规模
   Existing-insight digest budget (read-only progressive Phase 1): mirrors backend caps, frontend trims first */
const DIGEST_MAX_ITEMS = 8
const DIGEST_BODY_CHARS = 120
const DIGEST_MAX_CHARS = 1800

/**
 * 构建已有洞察卡片的 title/body 结构化摘要（只读累进上下文）。
 * Build a structured title/body digest of existing insight cards.
 * 仅收录 AI 产出的实质洞察（手动/自动卡、含图或建议的卡），排除系统占位提示；
 * 取最近 N 条并截断总量。 / Keeps only substantive AI insight cards (user-triggered/auto, or
 * system cards carrying diagram/solution), excludes placeholder prompts; latest N under a char cap.
 */
function buildExistingDigest(): Array<{ title: string; body: string }> {
  const meaningful = insightMessages.value.filter(
    m => m.title.trim() && (m.source === 'user' || m.diagram || m.solution)
  )
  const picked: Array<{ title: string; body: string }> = []
  let used = 0
  for (const m of meaningful.slice(-DIGEST_MAX_ITEMS)) {
    const title = m.title.trim()
    const body = m.body.trim().slice(0, DIGEST_BODY_CHARS)
    const cost = title.length + body.length + 1
    if (used + cost > DIGEST_MAX_CHARS) break
    picked.push({ title, body })
    used += cost
  }
  return picked
}

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
    const existingInsights = buildExistingDigest()
    const result = await runInsightAnalysis({
      recent_lines: recentLines.slice(-20),
      chapter_titles: chapterTitles,
      // 只读累进（Phase 1）：携带已有卡片摘要，使模型获得全局视角、避免重复创建
      ...(existingInsights.length ? { existing_insights: existingInsights } : {}),
      // 一页纸系数：携带有效卡位，后端据此注入生成侧预算块
      card_slots: cardSlots(onePageInsights.value),
    })

    if (result.has_finding && result.title) {
      addInsightMessage(
        result.title,
        result.body,
        [{ key: 'acknowledge', label: tt('ai-panel.insights.action_acknowledge'), primary: true }],
        source,
        tt('ai-panel.insights.cat_insight'),
        result.solution,
        result.diagram,
        result.note || ''
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
 * 用户主动触发综合洞察分析（保留的分析能力，当前无 UI 触发入口；
 * 洞察的日常生成/修订已改由会话面板入共创） / User-triggered unified insight analysis.
 * 数据不足时也会给出反馈，避免用户点击后无响应产生困扰。 / Provides feedback even when data is insufficient.
 */
async function runManualAnalysis(
  recentLines: TranscriptLineInput,
  chapterTitles: string[],
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
      tt('ai-panel.insights.cat_insight')
    )
    return
  }

  await runAnalysis(recentLines, chapterTitles, 'user', manualAnalyzing, false)
}

/* 【已退役】maybeAutoAnalyze 定时自动触发入口随「洞察共创 · 会话驱动」下线 */

/* ─── 会后补分析（纪要页触发，服务端基于全文） / Post-meeting supplement (from summary page, server-side full content) ─── */

/** 会后补分析加载状态 / Post-meeting analysis loading state */
const postAnalyzing: Ref<boolean> = ref(false)

/**
 * 触发会后补分析：服务端读取完整 dialogue + 章节跑一轮洞察，有发现时后端已落盘。
 * Trigger post-meeting analysis: server reads full dialogue + chapters, appends + persists on finding.
 * 成功后以重拉语义用响应 messages 替换本地列表，规避前端全量覆盖竞态。
 * On success replaces local list with response messages (reload semantics), avoiding the full-overwrite race.
 * @returns 分析结果 result（含 has_finding）；并发/空 taskId 时返回 null。
 */
async function runPostMeetingSupplement(taskId: string) {
  if (!taskId || postAnalyzing.value) return null
  postAnalyzing.value = true
  try {
    const { result, messages } = await apiRunPostMeetingAnalysis(taskId)
    messagesByTask.value[taskId] = (messages || []) as InsightMessage[]
    loadedTasks.add(taskId)
    return result
  } finally {
    postAnalyzing.value = false
  }
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
  /** 未读消息数（仅计有效层，降级卡不产生噪声） / Unread count (active layer only; deferred cards never ping) */
  const unreadCount = computed(() =>
    insightMessages.value.filter(m => !m.read && !m.deferred).length
  )

  /** 最新的未读消息（用于横幅展示，仅有效层） / Latest unread message (active layer only) */
  const latestUnread = computed(() =>
    insightMessages.value.find(m => !m.read && !m.deferred) ?? null
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

  /** 获取第一条未读消息（仅有效层） / Get first unread message (active layer only) */
  function getFirstUnread(): InsightMessage | null {
    return insightMessages.value.find(m => !m.read && !m.deferred) ?? null
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
    insightMessages,
    unreadCount,
    latestUnread,
    onePageInsights,
    setOnePageInsights,
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
    // 会议绑定 / Meeting binding
    setCurrentTask,
    persistMessages,
    reloadTaskMessages,
    // 手动分析（能力保留，无 UI 触发入口；日常共创走会话面板）
    manualAnalyzing,
    runManualAnalysis,
    // 会后补分析 / Post-meeting supplement
    postAnalyzing,
    runPostMeetingSupplement,
    // 导航辅助 / Navigation helper
    getActiveRecordingTaskId,
    // 对话图形化 / Chat diagram
    setChatDiagram,
    // 图交互状态 / Diagram interaction state
    lastViewedDiagram,
    diagramEditPending,
  }
}
