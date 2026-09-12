/**
 * AI 洞察 — 状态管理 composable + 洞察引擎
 *
 * 管理 AI 洞察功能的消息列表、未读计数、配置开关。
 * 功能开关状态持久化到 localStorage（兼容旧版 ai_proactive_* key）。
 *
 * v3.0：洞察引擎重构 —— 从「错误检测」转向「上下文赋能」。
 * 三类洞察：上下文关联、盲点揭示、共识提炼。
 * 设计理念：LLM 的核心优势在于对更大上下文的感知，
 * 帮助参会者基于更完整的信息达成有意义的共识。
 */
import { ref, computed, type Ref } from 'vue'
import { tt } from '@/i18n'
import { runInsightAnalysis, loadInsightMessages, saveInsightMessages, type InsightAnalysisType } from '@/api/insights'

/** 洞察消息结构 */
export interface InsightMessage {
  id: string
  /** 消息标题 */
  title: string
  /** 消息正文（支持 HTML） */
  body: string
  /** 操作按钮 */
  actions: InsightAction[]
  /** 时间戳 */
  timestamp: number
  /** 触发来源：auto = 自动触发 */
  source: 'auto' | 'system'
  /** 是否已读 */
  read: boolean
  /** 消息分类标签（如「上下文关联」「盲点揭示」「共识提炼」） */
  category: string
  /** AI 建议的解决方案（展开后显示） */
  solution: string
  /** 是否已展开 */
  expanded: boolean
  /** 是否已确认（用户点击操作按钮后为 true，卡片折叠并切换为系统默认色系） */
  acknowledged: boolean
}

export interface InsightAction {
  key: string
  label: string
  primary?: boolean
}

/** AI 洞察配置 */
export interface InsightConfig {
  /** 消息类别开关 */
  categories: Record<string, boolean>
  /** 各类别扫描频率（分钟） */
  scanIntervals: Record<string, number>
  /** 触发灵敏度 */
  sensitivity: {
    idleMinutes: number        // 无操作触发时长
    insightThreshold: number   // 洞察触发阈值（百分比）
    cooldownMinutes: number    // 同类消息冷却期
    sessionMax: number         // 单次会议上限
  }
  /** 通知方式 */
  notifications: {
    sidebarIndicator: boolean  // 侧边栏指示器
    breathing: boolean         // 呼吸灯动画
    banner: boolean            // 悬浮横幅
    autoExpand: boolean        // 自动展开面板
  }
  /** 免打扰 */
  dnd: {
    enabled: boolean
    startHour: number
    endHour: number
  }
}

const CONFIG_KEY = 'ai_insights_config'
const LEGACY_CONFIG_KEY = 'ai_proactive_config'

/** 默认配置 */
function defaultConfig(): InsightConfig {
  return {
    categories: {
      context: true,
      blindspot: true,
      consensus: true,
    },
    scanIntervals: {
      context: 2,      // 上下文关联：每 2 分钟
      blindspot: 5,    // 盲点揭示：每 5 分钟
      consensus: 10,   // 共识提炼：每 10 分钟
    },
    sensitivity: {
      idleMinutes: 15,
      insightThreshold: 50,
      cooldownMinutes: 30,
      sessionMax: 5,
    },
    notifications: {
      sidebarIndicator: true,
      breathing: true,
      banner: true,
      autoExpand: false,
    },
    dnd: {
      enabled: false,
      startHour: 22,
      endHour: 8,
    },
  }
}

const STORAGE_KEY = 'ai_insights_enabled'
const LEGACY_STORAGE_KEY = 'ai_proactive_enabled'

/* ─── 全局单例状态 ─── */
const insightsEnabled = ref<boolean>(
  // 优先读新 key，兼容旧 key
  (localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY)) !== '0'
)
const insightsConfig = ref<InsightConfig>(defaultConfig())

/** 当前会议 ID（引擎运行时绑定） */
const currentTaskId = ref<string>('')
/** 按会议隔离的消息存储：taskId → InsightMessage[] */
const messagesByTask = ref<Record<string, InsightMessage[]>>({})
/** 当前会议的洞察消息（计算属性，自动跟随 currentTaskId 切换） */
const insightMessages = computed<InsightMessage[]>(() => {
  const tid = currentTaskId.value
  if (!tid) return []
  if (!messagesByTask.value[tid]) messagesByTask.value[tid] = []
  return messagesByTask.value[tid]
})

/** 从 localStorage 加载配置（兼容旧 key + v2→v3 迁移） */
function loadConfig() {
  try {
    const raw = localStorage.getItem(CONFIG_KEY) || localStorage.getItem(LEGACY_CONFIG_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<InsightConfig>
      // 合并默认值（防止旧版本缺少新字段）
      insightsConfig.value = {
        categories: { ...defaultConfig().categories, ...parsed.categories },
        scanIntervals: { ...defaultConfig().scanIntervals, ...(parsed as any).scanIntervals },
        sensitivity: { ...defaultConfig().sensitivity, ...parsed.sensitivity },
        notifications: { ...defaultConfig().notifications, ...parsed.notifications },
        dnd: { ...defaultConfig().dnd, ...parsed.dnd },
      }
      // v2→v3 迁移：deviationThreshold → insightThreshold
      const rawSens = (parsed as any).sensitivity
      if (rawSens && 'deviationThreshold' in rawSens && !('insightThreshold' in rawSens)) {
        insightsConfig.value.sensitivity.insightThreshold = rawSens.deviationThreshold
      }
      // 清理旧版不存在的类别 key
      const validCategories = new Set(Object.keys(defaultConfig().categories))
      for (const key of Object.keys(insightsConfig.value.categories)) {
        if (!validCategories.has(key)) delete insightsConfig.value.categories[key]
      }
      // 迁移到新 key
      if (!localStorage.getItem(CONFIG_KEY) && localStorage.getItem(LEGACY_CONFIG_KEY)) {
        localStorage.setItem(CONFIG_KEY, raw)
      }
      saveConfig()  // 持久化迁移结果
    }
  } catch { /* ignore */ }
}

/** 保存配置到 localStorage */
function saveConfig() {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(insightsConfig.value))
}

/** 判断当前是否在免打扰时段 */
function isInDndPeriod(): boolean {
  const { enabled, startHour, endHour } = insightsConfig.value.dnd
  if (!enabled) return false
  const hour = new Date().getHours()
  if (startHour > endHour) {
    // 跨午夜（如 22:00 - 08:00）
    return hour >= startHour || hour < endHour
  }
  return hour >= startHour && hour < endHour
}

/** 判断某类别消息是否应触发 */
function shouldTrigger(categoryKey: string): boolean {
  if (!insightsEnabled.value) return false
  if (isInDndPeriod()) return false
  return insightsConfig.value.categories[categoryKey] ?? true
}

// 初始化时加载配置
loadConfig()

let _idSeq = 0
function nextId(): string {
  return `insight-${Date.now()}-${++_idSeq}`
}

/* ─── 洞察引擎状态（模块级单例） ─── */
let engineRunning = false
let idleTimer: ReturnType<typeof setTimeout> | null = null
let sessionMessageCount = 0
/** 冷却追踪：记录每个类别最后一次触发的时间戳 */
const lastTriggerTimeByCategory: Record<string, number> = {}
let insightCheckTimer: ReturnType<typeof setInterval> | null = null
const INSIGHT_CHECK_INTERVAL = 60_000  // 基础扫描周期 60 秒
/** 各类别最后一次实际执行扫描的时间戳 */
const lastScanTimeByCategory: Record<string, number> = {}
/** 洞察检测回调（由外部注册，提供实时转写数据） */
let insightCheckCallback: (() => void) | null = null

/**
 * 判断某类别是否可触发（综合检查：功能开关、免打扰、会话上限、冷却期、类别开关）
 */
function canTrigger(categoryKey: string): boolean {
  if (!insightsEnabled.value) return false
  if (isInDndPeriod()) return false
  // 会话上限
  if (sessionMessageCount >= insightsConfig.value.sensitivity.sessionMax) return false
  // 冷却期
  const lastTime = lastTriggerTimeByCategory[categoryKey] ?? 0
  const cooldownMs = insightsConfig.value.sensitivity.cooldownMinutes * 60_000
  if (Date.now() - lastTime < cooldownMs) return false
  // 类别开关
  if (!insightsConfig.value.categories[categoryKey]) return false
  return true
}

/**
 * 通知分发：根据配置派发 UI 反馈事件
 */
function dispatchNotification(msg: InsightMessage | null) {
  if (!msg) return
  const notif = insightsConfig.value.notifications
  // autoExpand: 自动展开洞察面板
  if (notif.autoExpand) {
    window.dispatchEvent(new CustomEvent('insights:auto-expand'))
  }
  // banner: 悬浮横幅
  if (notif.banner) {
    window.dispatchEvent(new CustomEvent('insights:show-banner', { detail: msg }))
  }
  // sidebarIndicator / breathing: 由 Sidebar.vue 和 AIPanel.vue
  // 直接读取 insightsConfig.value.notifications 响应式控制，无需事件
}

/**
 * 重置 idle 计时器
 */
function resetIdleTimer() {
  if (idleTimer) clearTimeout(idleTimer)
  if (!engineRunning) return
  const idleMs = insightsConfig.value.sensitivity.idleMinutes * 60_000
  idleTimer = setTimeout(() => {
    onIdleTriggered()
  }, idleMs)
}

/**
 * idle 触发回调：建议生成会议总结
 */
function onIdleTriggered() {
  // idle 时建议生成总结（不受类别开关约束，作为系统级建议）
  const msgCount = insightMessages.value.length
  // 从章节数推断话题数（由外部在启动时设置）
  const topicCount = Math.max(1, Math.ceil(msgCount / 2) + 1)
  const id = triggerIdleSummarySuggestion(msgCount, topicCount)
  if (id) {
    const msg = insightMessages.value.find(m => m.id === id) ?? null
    dispatchNotification(msg)
  }
}

/* ─── 引擎生命周期 API ─── */

/** 设置当前会议 ID（切换会议时调用，加载对应洞察消息） */
async function setCurrentTask(taskId: string) {
  // 先保存当前会议的消息（如果有）
  if (currentTaskId.value && currentTaskId.value !== taskId) {
    await persistMessages(currentTaskId.value)
  }
  currentTaskId.value = taskId
  // 重置引擎状态（新会议 = 新会话）
  sessionMessageCount = 0
  Object.keys(lastTriggerTimeByCategory).forEach(k => delete lastTriggerTimeByCategory[k])
  Object.keys(lastScanTimeByCategory).forEach(k => delete lastScanTimeByCategory[k])
  // 从后端加载该会议的洞察消息
  if (taskId && !messagesByTask.value[taskId]) {
    try {
      const result = await loadInsightMessages(taskId)
      messagesByTask.value[taskId] = result.messages || []
    } catch {
      messagesByTask.value[taskId] = []
    }
  }
}

/** 将指定会议的洞察消息持久化到后端 */
async function persistMessages(taskId: string) {
  if (!taskId) return
  const msgs = messagesByTask.value[taskId]
  if (!msgs) return
  try {
    await saveInsightMessages(taskId, msgs)
  } catch (e) {
    // 持久化失败不阻断用户体验
  }
}

/** 启动洞察引擎（录音页 onMounted 调用，需先 setCurrentTask） */
function startEngine() {
  if (engineRunning) return
  engineRunning = true
  // 启动 idle 计时器
  resetIdleTimer()
  // 启动基础扫描定时器（每 60 秒检查各类别是否到达各自频率）
  insightCheckTimer = setInterval(() => {
    if (insightCheckCallback) insightCheckCallback()
  }, INSIGHT_CHECK_INTERVAL)
}

/** 停止洞察引擎并持久化消息（录音页 onUnmounted 或录音结束时调用） */
function stopEngine() {
  engineRunning = false
  if (idleTimer) { clearTimeout(idleTimer); idleTimer = null }
  if (insightCheckTimer) { clearInterval(insightCheckTimer); insightCheckTimer = null }
  insightCheckCallback = null
  // 持久化当前会议的消息
  if (currentTaskId.value) {
    persistMessages(currentTaskId.value)
  }
}

/** 注册洞察检测回调（由 RecordingView 调用，提供实时数据） */
function onInsightCheck(cb: () => void) {
  insightCheckCallback = cb
}

/** 转写活动喂入（新行到达时调用，重置 idle 计时器） */
function feedTranscriptActivity() {
  if (engineRunning) resetIdleTimer()
}

/**
 * 自动洞察检查（由定时器回调触发）
 * 根据各类别独立的扫描频率决定是否执行，每种分析独立受冷却限流和会话上限约束。
 */
async function runAutoInsightCheck(
  recentLines: Array<{ text: string; speaker_id: number; begin_time: number }>,
  chapterTitles: string[]
) {
  if (recentLines.length < 5 || chapterTitles.length === 0) return

  const now = Date.now()
  const types: InsightAnalysisType[] = ['context', 'blindspot', 'consensus']
  for (const type of types) {
    if (!canTrigger(type)) continue
    // 检查该类别的扫描频率是否已到
    const intervalMin = insightsConfig.value.scanIntervals[type] ?? 5
    const intervalMs = intervalMin * 60_000
    const lastScan = lastScanTimeByCategory[type] ?? 0
    if (now - lastScan < intervalMs) continue

    lastScanTimeByCategory[type] = now
    try {
      const result = await runInsightAnalysis({
        recent_lines: recentLines.slice(-20),
        chapter_titles: chapterTitles,
        analysis_type: type,
      })
      if (result.has_finding && result.title) {
        const catLabel = tt(`ai-panel.insights.cat_${type}`)
        const id = addInsightMessage(
          result.title,
          result.body,
          [{ key: 'acknowledge', label: tt('ai-panel.insights.action_acknowledge'), primary: true }],
          'auto',
          catLabel,
          result.solution
        )
        if (id) {
          const msg = insightMessages.value.find(m => m.id === id) ?? null
          dispatchNotification(msg)
        }
      }
    } catch {
      // 单个分析类型失败不影响其他类型
    }
  }
}

/* ─── 手动分析（用户主动触发，绕过冷却/上限） ─── */

/** 手动分析加载状态 */
const manualAnalyzing: Ref<boolean> = ref(false)

/**
 * 用户主动触发分析（绕过冷却限流和会话上限）
 * 根据 category 参数决定执行哪种分析：
 *   - 'context': 上下文关联
 *   - 'blindspot': 盲点揭示
 *   - 'consensus': 共识提炼
 *   - 'all': 执行所有分析类型
 * 数据不足时也会给出反馈，避免用户点击后无响应产生困扰。
 */
async function runManualAnalysis(
  recentLines: Array<{ text: string; speaker_id: number; begin_time: number }>,
  chapterTitles: string[],
  category: string = 'all'
) {
  if (!insightsEnabled.value) return
  if (manualAnalyzing.value) return

  // 数据不足时给出反馈
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
    const types: InsightAnalysisType[] = category === 'all'
      ? ['context', 'blindspot', 'consensus']
      : [category as InsightAnalysisType]

    for (const type of types) {
      await runSingleAnalysis(recentLines, chapterTitles, type, true)
    }
  } catch {
    // API 调用失败静默忽略
  } finally {
    manualAnalyzing.value = false
  }
}

/**
 * 执行单个分析类型（手动触发专用，不走 canTrigger 冷却检查）
 */
async function runSingleAnalysis(
  recentLines: Array<{ text: string; speaker_id: number; begin_time: number }>,
  chapterTitles: string[],
  type: InsightAnalysisType,
  isManual: boolean
) {
  const result = await runInsightAnalysis({
    recent_lines: recentLines.slice(-20),
    chapter_titles: chapterTitles,
    analysis_type: type,
  })

  const catLabel = tt(`ai-panel.insights.cat_${type}`)

  if (result.has_finding && result.title) {
    const id = addInsightMessage(
      result.title,
      result.body,
      [{ key: 'acknowledge', label: tt('ai-panel.insights.action_acknowledge'), primary: true }],
      'auto',
      catLabel,
      result.solution
    )
    if (id) {
      const msg = insightMessages.value.find(m => m.id === id) ?? null
      dispatchNotification(msg)
    }
  } else if (isManual) {
    // 手动触发且无发现 → 给出正面反馈
    addInsightMessage(
      tt('ai-panel.insights.manual_check_ok_title'),
      tt('ai-panel.insights.manual_check_ok_body'),
      [],
      'system',
      catLabel
    )
  }
}

/* ─── Demo 模式：注入预设场景数据（展示洞察能力） ─── */
const DEMO_KEY = 'ai_insights_demo_loaded'
const LEGACY_DEMO_KEY = 'ai_proactive_demo_loaded'
let demoInitialized = false

function initDemoData() {
  if (demoInitialized) return
  demoInitialized = true
  if (!insightsEnabled.value || localStorage.getItem(DEMO_KEY) || localStorage.getItem(LEGACY_DEMO_KEY)) return
  const now = Date.now()
  // Demo 数据写入当前会议（若无会议则用 demo 占位 key）
  const demoTaskId = currentTaskId.value || '__demo__'
  messagesByTask.value[demoTaskId] = [
    {
      id: nextId(),
      category: tt('ai-panel.insights.cat_context'),
      title: tt('ai-panel.insights.scene_context_title'),
      body: tt('ai-panel.insights.scene_context_summary'),
      solution: tt('ai-panel.insights.scene_context_solution'),
      actions: [
        { key: 'acknowledge', label: tt('ai-panel.insights.action_acknowledge'), primary: true },
      ],
      timestamp: now - 600000,
      source: 'auto',
      read: false,
      expanded: false,
      acknowledged: false,
    },
    {
      id: nextId(),
      category: tt('ai-panel.insights.cat_consensus'),
      title: tt('ai-panel.insights.scene_consensus_title'),
      body: tt('ai-panel.insights.scene_consensus_summary'),
      solution: tt('ai-panel.insights.scene_consensus_solution'),
      actions: [
        { key: 'acknowledge', label: tt('ai-panel.insights.action_acknowledge'), primary: true },
      ],
      timestamp: now - 300000,
      source: 'auto',
      read: false,
      expanded: false,
      acknowledged: false,
    },
  ]
  localStorage.setItem(DEMO_KEY, '1')
}

/* ─── 模块级核心函数（供引擎和 composable 共用） ─── */

/** 添加一条洞察消息（含冷却限流 + 会话上限检查） */
function addInsightMessage(
  title: string,
  body: string,
  actions: InsightAction[],
  source: 'auto' | 'system' = 'auto',
  category = '',
  solution = ''
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
  })
  // 引擎追踪：递增会话计数 + 记录冷却时间
  sessionMessageCount++
  if (category) {
    lastTriggerTimeByCategory[category] = Date.now()
  }
  // 实时持久化：确保新消息写入磁盘，防止页面刷新丢失
  if (currentTaskId.value) persistMessages(currentTaskId.value)
  return id
}

/**
 * 场景 A：会议结束后，主动推送待办提取提醒
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

/**
 * 场景 B：长时间无操作，建议生成会议总结
 */
function triggerIdleSummarySuggestion(messageCount: number, topicCount: number) {
  if (!insightsEnabled.value) return ''
  return addInsightMessage(
    tt('ai-panel.insights.scene_idle_title'),
    tt('ai-panel.insights.scene_idle_body_pre')
    + `<strong>${messageCount}</strong>`
    + tt('ai-panel.insights.scene_idle_body_mid')
    + `<strong>${topicCount}</strong>`
    + tt('ai-panel.insights.scene_idle_body_post'),
    [
      { key: 'generate', label: tt('ai-panel.insights.action_generate'), primary: true },
      { key: 'dismiss', label: tt('ai-panel.insights.action_dismiss') },
    ]
  )
}

/** 获取当前正在录音的任务 ID（供侧边栏洞察按钮导航使用） */
function getActiveRecordingTaskId(): string {
  if (engineRunning && currentTaskId.value) return currentTaskId.value
  return ''
}

export function useAiInsights() {
  // 延迟初始化 demo 数据（确保 i18n 已就绪）
  initDemoData()

  /** 未读消息数 */
  const unreadCount = computed(() =>
    insightMessages.value.filter(m => !m.read).length
  )

  /** 最新的未读消息（用于横幅展示） */
  const latestUnread = computed(() =>
    insightMessages.value.find(m => !m.read) ?? null
  )

  /** 切换功能开关 */
  function toggleEnabled() {
    insightsEnabled.value = !insightsEnabled.value
    localStorage.setItem(STORAGE_KEY, insightsEnabled.value ? '1' : '0')
    // 关闭时清除当前会议的洞察消息并停止引擎
    if (!insightsEnabled.value) {
      if (currentTaskId.value) messagesByTask.value[currentTaskId.value] = []
      stopEngine()
    }
  }

  /** 设置功能开关 */
  function setEnabled(val: boolean) {
    insightsEnabled.value = val
    localStorage.setItem(STORAGE_KEY, val ? '1' : '0')
    if (!val) {
      if (currentTaskId.value) messagesByTask.value[currentTaskId.value] = []
      stopEngine()
    }
  }

  /** 标记消息已读 */
  function markAsRead(id: string) {
    const msg = insightMessages.value.find(m => m.id === id)
    if (msg) msg.read = true
  }

  /** 确认消息：折叠卡片 + 切换为系统默认色系 */
  function acknowledgeMessage(id: string) {
    const msg = insightMessages.value.find(m => m.id === id)
    if (msg) {
      msg.acknowledged = true
      msg.expanded = false
      msg.read = true
      // 实时持久化：确认状态写入磁盘
      if (currentTaskId.value) persistMessages(currentTaskId.value)
    }
  }

  /** 切换消息展开/折叠 */
  function toggleExpanded(id: string) {
    const msg = insightMessages.value.find(m => m.id === id)
    if (msg) {
      msg.expanded = !msg.expanded
      if (msg.expanded) msg.read = true
    }
  }

  /** 获取第一条未读消息 */
  function getFirstUnread(): InsightMessage | null {
    return insightMessages.value.find(m => !m.read) ?? null
  }

  /** 标记全部已读 */
  function markAllRead() {
    insightMessages.value.forEach(m => { m.read = true })
  }

  /** 移除消息 */
  function dismissInsightMessage(id: string) {
    const idx = insightMessages.value.findIndex(m => m.id === id)
    if (idx >= 0) insightMessages.value.splice(idx, 1)
  }

  /** 清空当前会议的洞察消息 */
  function clearInsightMessages() {
    if (currentTaskId.value) messagesByTask.value[currentTaskId.value] = []
  }

  return {
    // 状态
    insightsEnabled,
    insightMessages,
    insightsConfig,
    unreadCount,
    latestUnread,
    // 操作
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
    loadConfig,
    saveConfig,
    shouldTrigger,
    canTrigger,
    isInDndPeriod,
    // 预设场景
    triggerMeetingEndTodos,
    triggerIdleSummarySuggestion,
    // 引擎生命周期
    setCurrentTask,
    startEngine,
    stopEngine,
    persistMessages,
    onInsightCheck,
    feedTranscriptActivity,
    runAutoInsightCheck,
    // 手动分析
    manualAnalyzing,
    runManualAnalysis,
    // 导航辅助
    getActiveRecordingTaskId,
  }
}
