/**
 * AI 多会话管理 store / AI multi-session management store
 *
 * 按 taskId 分桶存储会话，每个桶内支持多会话 CRUD。 / Bucket storage by taskId; each bucket supports multi-session CRUD.
 * localStorage 持久化，兼容旧版单数组格式迁移。 / localStorage persistence; compatible with legacy single-array format migration.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatMessage } from '@/api/chat'
import { tt } from '@/i18n'

const STORAGE_KEY = 'oms_ai_chat'
const DEFAULT_KEY = '__default__'
const MAX_PERSIST_MESSAGES = 20

export interface AiSession {
  id: string
  name: string
  createdAt: number
  messages: ChatMessage[]
  /** Agent 角色标识 / Agent role identifier */
  role?: string
  /** 会话开始时锁定的授权档快照（会话级，档位下沉面板后唯一生效口径） */
  authTier?: string
  /** 自动命名三态：undefined=未被命名过（默认序号名，可被 AI 命名）；
   *  true=名字来自 AI 生成；false=用户手动改过名，AI 命名永久让位 */
  autoTitled?: boolean
}

interface SessionBucket {
  sessions: AiSession[]
  activeSessionId: string
}

interface PersistedData {
  historyMap: Record<string, SessionBucket>
  activeKey: string
  projectId: string | null
  ts: number
}

function createSession(index: number): AiSession {
  return {
    id: `sess_${Date.now()}_${index}`,
    name: tt('ai-panel.session_name', { index }),
    createdAt: Date.now(),
    messages: [],
  }
}

function migrateLegacy(data: Record<string, unknown>): Record<string, SessionBucket> {
  const result: Record<string, SessionBucket> = {}
  for (const [key, value] of Object.entries(data)) {
    if (value && typeof value === 'object' && 'sessions' in value) {
      result[key] = value as SessionBucket
    } else if (Array.isArray(value)) {
      const session = createSession(1)
      session.messages = value as ChatMessage[]
      result[key] = { sessions: [session], activeSessionId: session.id }
    }
  }
  return result
}

export const useAiSessionsStore = defineStore('aiSessions', () => {
  const historyMap = ref<Record<string, SessionBucket>>({})
  const activeKey = ref(DEFAULT_KEY)

  const currentBucket = computed(() => {
    const key = activeKey.value
    if (!historyMap.value[key]) {
      const session = createSession(1)
      historyMap.value[key] = { sessions: [session], activeSessionId: session.id }
    }
    return historyMap.value[key]
  })

  const activeSession = computed(() => {
    const bucket = currentBucket.value
    return bucket.sessions.find(s => s.id === bucket.activeSessionId) || bucket.sessions[0]
  })

  const activeMessages = computed({
    get: () => activeSession.value?.messages ?? [],
    set: (val: ChatMessage[]) => {
      const session = activeSession.value
      if (session) session.messages = val
    },
  })

  const sessions = computed(() => currentBucket.value.sessions)

  function setChatKey(taskId: string | null) {
    activeKey.value = taskId || DEFAULT_KEY
    if (!historyMap.value[activeKey.value]) {
      const session = createSession(1)
      historyMap.value[activeKey.value] = { sessions: [session], activeSessionId: session.id }
    }
  }

  /** 新建会话并锁定授权档快照（档位：会中改档只对待生效值负责，新会话才应用） */
  function createNewSession(authTier?: string): AiSession {
    const bucket = currentBucket.value
    const idx = bucket.sessions.length + 1
    const session = createSession(idx)
    if (authTier) session.authTier = authTier
    bucket.sessions.push(session)
    bucket.activeSessionId = session.id
    persist()
    return session
  }

  /** 给历史会话补盖快照戳（首次使用时按当前待生效档锁定，只盖一次） */
  function stampActiveSessionTier(authTier: string): boolean {
    const session = activeSession.value
    if (!session || session.authTier) return false
    session.authTier = authTier
    persist()
    return true
  }

  /** 会中改档：覆盖当前会话锁定档（改完即生效，下一轮起用新档） */
  function updateActiveSessionTier(authTier: string): boolean {
    const session = activeSession.value
    if (!session) return false
    session.authTier = authTier
    persist()
    return true
  }

  function switchTo(sessionId: string) {
    const bucket = currentBucket.value
    if (!bucket.sessions.find(s => s.id === sessionId)) return
    bucket.activeSessionId = sessionId
    persist()
  }

  function deleteSession(sessionId: string) {
    const bucket = currentBucket.value
    if (bucket.sessions.length <= 1) {
      bucket.sessions[0].messages = []
      persist()
      return
    }
    const idx = bucket.sessions.findIndex(s => s.id === sessionId)
    if (idx < 0) return
    bucket.sessions.splice(idx, 1)
    if (bucket.activeSessionId === sessionId) {
      bucket.activeSessionId = bucket.sessions[Math.max(0, idx - 1)].id
    }
    persist()
  }

  function renameSession(sessionId: string, name: string) {
    const bucket = currentBucket.value
    const session = bucket.sessions.find(s => s.id === sessionId)
    if (!session) return
    const trimmed = name.trim()
    if (trimmed) {
      session.name = trimmed
      // 用户命名权最高：改名后 AI 自动命名永久让位
      session.autoTitled = false
      persist()
    }
  }

  /** AI 自动命名落名（仅当会话从未被命名过：autoTitled 为 undefined）。
   *  接收会话对象本身而非 id：命名请求跨桶在途返回时仍落在正确的会话上。 */
  function applyAutoTitle(session: AiSession, title: string) {
    if (session.autoTitled !== undefined) return
    const trimmed = title.trim()
    if (!trimmed) return
    session.name = trimmed
    session.autoTitled = true
    persist()
  }

  function persist() {
    try {
      const trimmed: Record<string, SessionBucket> = {}
      for (const [key, data] of Object.entries(historyMap.value)) {
        if (data?.sessions) {
          trimmed[key] = {
            sessions: data.sessions.map(s => ({
              ...s,
              messages: s.messages.slice(-MAX_PERSIST_MESSAGES),
            })),
            activeSessionId: data.activeSessionId,
          }
        }
      }
      const payload: PersistedData = {
        historyMap: trimmed,
        activeKey: activeKey.value,
        projectId: null,
        ts: Date.now(),
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      // quota exceeded → 静默 / quota exceeded → silent
    }
  }

  function restore() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const data: PersistedData = JSON.parse(raw)
      if (data.historyMap) {
        historyMap.value = migrateLegacy(data.historyMap)
      }
      if (data.activeKey) {
        activeKey.value = data.activeKey
      }
    } catch {
      // corrupt data → 忽略 / corrupt data → ignore
    }
  }

  function clearCurrentSession() {
    const session = activeSession.value
    if (session) {
      session.messages = []
      persist()
    }
  }

  restore()

  return {
    activeKey, historyMap,
    sessions, activeSession, activeMessages, currentBucket,
    setChatKey, createNewSession, stampActiveSessionTier, updateActiveSessionTier, switchTo, deleteSession, renameSession, applyAutoTitle,
    persist, restore, clearCurrentSession,
  }
})
