/**
 * AI 主动消息 — 状态管理 composable
 *
 * 管理 AI 主动发起会话的功能开关、消息列表、未读计数。
 * 功能开关状态持久化到 localStorage。
 */
import { ref, computed } from 'vue'
import { tt } from '@/i18n'

/** 主动消息结构 */
export interface ProactiveMessage {
  id: string
  /** 消息标题 */
  title: string
  /** 消息正文（支持 HTML） */
  body: string
  /** 操作按钮 */
  actions: ProactiveAction[]
  /** 时间戳 */
  timestamp: number
  /** 触发来源：auto = 自动触发 */
  source: 'auto' | 'system'
  /** 是否已读 */
  read: boolean
  /** 消息分类标签（如「偏离提醒」「矛盾检测」「遗漏议题」） */
  category: string
  /** AI 建议的解决方案（展开后显示） */
  solution: string
  /** 是否已展开 */
  expanded: boolean
}

export interface ProactiveAction {
  key: string
  label: string
  primary?: boolean
}

/** 主动 AI 配置 */
export interface ProactiveConfig {
  /** 消息类别开关 */
  categories: Record<string, boolean>
  /** 触发灵敏度 */
  sensitivity: {
    idleMinutes: number        // 无操作触发时长
    deviationThreshold: number // 偏离检测阈值（百分比）
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

const CONFIG_KEY = 'ai_proactive_config'

/** 默认配置 */
function defaultConfig(): ProactiveConfig {
  return {
    categories: {
      deviation: true,
      contradiction: true,
      missing_topic: true,
      todo_extract: true,
      summary_suggest: true,
      stuck: true,
    },
    sensitivity: {
      idleMinutes: 15,
      deviationThreshold: 35,
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

const STORAGE_KEY = 'ai_proactive_enabled'

/* ─── 全局单例状态 ─── */
const proactiveEnabled = ref<boolean>(
  localStorage.getItem(STORAGE_KEY) !== '0'
)
const proactiveMessages = ref<ProactiveMessage[]>([])
const proactiveConfig = ref<ProactiveConfig>(defaultConfig())

/** 从 localStorage 加载配置 */
function loadConfig() {
  try {
    const raw = localStorage.getItem(CONFIG_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ProactiveConfig>
      // 合并默认值（防止旧版本缺少新字段）
      proactiveConfig.value = {
        categories: { ...defaultConfig().categories, ...parsed.categories },
        sensitivity: { ...defaultConfig().sensitivity, ...parsed.sensitivity },
        notifications: { ...defaultConfig().notifications, ...parsed.notifications },
        dnd: { ...defaultConfig().dnd, ...parsed.dnd },
      }
    }
  } catch { /* ignore */ }
}

/** 保存配置到 localStorage */
function saveConfig() {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(proactiveConfig.value))
}

/** 判断当前是否在免打扰时段 */
function isInDndPeriod(): boolean {
  const { enabled, startHour, endHour } = proactiveConfig.value.dnd
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
  if (!proactiveEnabled.value) return false
  if (isInDndPeriod()) return false
  return proactiveConfig.value.categories[categoryKey] ?? true
}

// 初始化时加载配置
loadConfig()

let _idSeq = 0
function nextId(): string {
  return `proactive-${Date.now()}-${++_idSeq}`
}

/* ─── Demo 模式：注入预设场景数据（AI 偏差/异常检测） ─── */
const DEMO_KEY = 'ai_proactive_demo_loaded'
let demoInitialized = false

function initDemoData() {
  if (demoInitialized) return
  demoInitialized = true
  if (!proactiveEnabled.value || localStorage.getItem(DEMO_KEY)) return
  const now = Date.now()
  proactiveMessages.value = [
    {
      id: nextId(),
      category: tt('ai-panel.proactive.cat_deviation'),
      title: tt('ai-panel.proactive.scene_deviation_title'),
      body: tt('ai-panel.proactive.scene_deviation_summary'),
      solution: tt('ai-panel.proactive.scene_deviation_solution'),
      actions: [
        { key: 'adjust', label: tt('ai-panel.proactive.action_adjust'), primary: true },
        { key: 'ignore', label: tt('ai-panel.proactive.action_ignore') },
      ],
      timestamp: now - 600000,
      source: 'auto',
      read: false,
      expanded: false,
    },
    {
      id: nextId(),
      category: tt('ai-panel.proactive.cat_contradiction'),
      title: tt('ai-panel.proactive.scene_contradiction_title'),
      body: tt('ai-panel.proactive.scene_contradiction_summary'),
      solution: tt('ai-panel.proactive.scene_contradiction_solution'),
      actions: [
        { key: 'clarify', label: tt('ai-panel.proactive.action_clarify'), primary: true },
        { key: 'ignore', label: tt('ai-panel.proactive.action_ignore') },
      ],
      timestamp: now - 300000,
      source: 'auto',
      read: false,
      expanded: false,
    },
  ]
  localStorage.setItem(DEMO_KEY, '1')
}

export function useAiProactive() {
  // 延迟初始化 demo 数据（确保 i18n 已就绪）
  initDemoData()

  /** 未读消息数 */
  const unreadCount = computed(() =>
    proactiveMessages.value.filter(m => !m.read).length
  )

  /** 最新的未读消息（用于横幅展示） */
  const latestUnread = computed(() =>
    proactiveMessages.value.find(m => !m.read) ?? null
  )

  /** 切换功能开关 */
  function toggleEnabled() {
    proactiveEnabled.value = !proactiveEnabled.value
    localStorage.setItem(STORAGE_KEY, proactiveEnabled.value ? '1' : '0')
    // 关闭时清除未读状态
    if (!proactiveEnabled.value) {
      proactiveMessages.value = []
    }
  }

  /** 设置功能开关 */
  function setEnabled(val: boolean) {
    proactiveEnabled.value = val
    localStorage.setItem(STORAGE_KEY, val ? '1' : '0')
    if (!val) {
      proactiveMessages.value = []
    }
  }

  /** 添加一条主动消息 */
  function addProactiveMessage(
    title: string,
    body: string,
    actions: ProactiveAction[],
    source: 'auto' | 'system' = 'auto',
    category = '',
    solution = ''
  ): string {
    if (!proactiveEnabled.value) return ''
    const id = nextId()
    proactiveMessages.value.push({
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
    })
    return id
  }

  /** 标记消息已读 */
  function markAsRead(id: string) {
    const msg = proactiveMessages.value.find(m => m.id === id)
    if (msg) msg.read = true
  }

  /** 切换消息展开/折叠 */
  function toggleExpanded(id: string) {
    const msg = proactiveMessages.value.find(m => m.id === id)
    if (msg) {
      msg.expanded = !msg.expanded
      if (msg.expanded) msg.read = true
    }
  }

  /** 获取第一条未读消息 */
  function getFirstUnread(): ProactiveMessage | null {
    return proactiveMessages.value.find(m => !m.read) ?? null
  }

  /** 标记全部已读 */
  function markAllRead() {
    proactiveMessages.value.forEach(m => { m.read = true })
  }

  /** 移除消息 */
  function dismissProactiveMessage(id: string) {
    const idx = proactiveMessages.value.findIndex(m => m.id === id)
    if (idx >= 0) proactiveMessages.value.splice(idx, 1)
  }

  /** 清空所有主动消息 */
  function clearProactiveMessages() {
    proactiveMessages.value = []
  }

  /* ─── 预设场景触发器 ─── */

  /**
   * 场景 A：会议结束后，主动推送待办提取提醒
   */
  function triggerMeetingEndTodos(todoList: Array<{ text: string; assignee?: string; deadline?: string }>) {
    if (!proactiveEnabled.value) return ''
    const items = todoList.map(todo => {
      let line = `<li><strong>${todo.text}</strong>`
      const meta: string[] = []
      if (todo.deadline) meta.push(tt('ai-panel.proactive.todo_deadline', { deadline: todo.deadline }))
      if (todo.assignee) meta.push(tt('ai-panel.proactive.todo_assignee', { name: todo.assignee }))
      if (meta.length) line += ` — ${meta.join(' · ')}`
      line += '</li>'
      return line
    }).join('')

    const bodyHtml = tt('ai-panel.proactive.scene_meeting_end_body_pre')
      + `<strong>${todoList.length}${tt('ai-panel.proactive.scene_meeting_end_body_unit')}</strong>`
      + `<ul>${items}</ul>`

    return addProactiveMessage(
      tt('ai-panel.proactive.scene_meeting_end_title'),
      bodyHtml,
      [
        { key: 'view', label: tt('ai-panel.proactive.action_view'), primary: true },
        { key: 'sync', label: tt('ai-panel.proactive.action_sync') },
        { key: 'later', label: tt('ai-panel.proactive.action_later') },
      ]
    )
  }

  /**
   * 场景 B：长时间无操作，建议生成会议总结
   */
  function triggerIdleSummarySuggestion(messageCount: number, topicCount: number) {
    if (!proactiveEnabled.value) return ''
    return addProactiveMessage(
      tt('ai-panel.proactive.scene_idle_title'),
      tt('ai-panel.proactive.scene_idle_body_pre')
      + `<strong>${messageCount}</strong>`
      + tt('ai-panel.proactive.scene_idle_body_mid')
      + `<strong>${topicCount}</strong>`
      + tt('ai-panel.proactive.scene_idle_body_post'),
      [
        { key: 'generate', label: tt('ai-panel.proactive.action_generate'), primary: true },
        { key: 'dismiss', label: tt('ai-panel.proactive.action_dismiss') },
      ]
    )
  }

  return {
    // 状态
    proactiveEnabled,
    proactiveMessages,
    proactiveConfig,
    unreadCount,
    latestUnread,
    // 操作
    toggleEnabled,
    setEnabled,
    addProactiveMessage,
    markAsRead,
    markAllRead,
    dismissProactiveMessage,
    clearProactiveMessages,
    toggleExpanded,
    getFirstUnread,
    loadConfig,
    saveConfig,
    shouldTrigger,
    isInDndPeriod,
    // 预设场景
    triggerMeetingEndTodos,
    triggerIdleSummarySuggestion,
  }
}
