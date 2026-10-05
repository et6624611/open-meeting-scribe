/**
 * 洞察台 — 状态管理 composable / Insight Deck — state management composable
 *
 * 管理洞察台消息列表（会话共创产物的卡片后备流）与按会议持久化。
 * Manages the Insight Deck message list (card fallback for co-created artifacts)
 * and per-meeting persistence.
 */
import { ref, computed } from 'vue'
import { tt } from '@/i18n'
import { loadInsightMessages, saveInsightMessages } from '@/api/insights'
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
  /** 消息来源 / Trigger source */
  source: 'user' | 'system'
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
  /** 【已退役·历史兼容】产生阶段：旧版会后补分析写入，新链路不再产出 /
      Legacy phase from the retired post-meeting supplement; retained for reloaded history */
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

/* ─── 全局单例状态 / Global singleton state ─── */

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
    const resp = await saveInsightMessages(taskId, msgs)
    // 后端写盘前按系数重排并回传全量列表：以重拉语义替换本地，避免陈旧内存下次整体覆盖
    // Backend rebalances before persisting and returns the full list; adopt it to keep local state fresh
    if (Array.isArray(resp.messages)) {
      messagesByTask.value[taskId] = resp.messages as InsightMessage[]
    }
  } catch {
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
  const id = nextId()
  insightMessages.value.push({
    id,
    title,
    body,
    actions,
    timestamp: Date.now(),
    source,
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

/* ─── 图交互状态（跨组件共享） / Diagram interaction state (cross-component shared) ─── */

/** 当前可见的图源码（展开卡片时自动更新，用于 AI 对话图修改上下文） / Current visible diagram source (auto-updated on card expand, used for AI chat diagram modification context) */
const lastViewedDiagram = ref<string>('')

/** 图编辑请求（“在对话中编辑”按钮触发，AIPanel 监听后预填输入框） / Diagram edit request (triggered by "Edit in Chat" button, AIPanel watches and pre-fills input) */
const diagramEditPending = ref<string>('')

export function useAiInsights() {
  /** 确认消息：折叠卡片 / Acknowledge message: collapse card */
  function acknowledgeMessage(id: string) {
    const msg = insightMessages.value.find(m => m.id === id)
    if (msg) {
      msg.acknowledged = true
      msg.expanded = false
      if (currentTaskId.value) persistMessages(currentTaskId.value)
    }
  }

  /** 切换消息展开/折叠（同时更新 lastViewedDiagram） / Toggle message expand/collapse (also updates lastViewedDiagram) */
  function toggleExpanded(id: string) {
    const msg = insightMessages.value.find(m => m.id === id)
    if (msg) {
      msg.expanded = !msg.expanded
      if (msg.expanded && msg.diagram) {
        // 展开时记录当前图源码，供 AI 对话图修改使用 / Track diagram source on expand for AI chat diagram modification
        lastViewedDiagram.value = msg.diagram
      }
    }
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
    if (!diagram) return
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
    insightMessages,
    // 操作 / Actions
    acknowledgeMessage,
    toggleExpanded,
    // 会议绑定 / Meeting binding
    setCurrentTask,
    persistMessages,
    reloadTaskMessages,
    // 对话图形化 / Chat diagram
    setChatDiagram,
    // 图交互状态 / Diagram interaction state
    lastViewedDiagram,
    diagramEditPending,
  }
}
