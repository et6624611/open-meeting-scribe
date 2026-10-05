/**
 * 任务状态管理 / Task state management
 *
 * 职责 / Responsibilities:
 *  - 维护任务列表（从 /api/tasks 拉取） / Maintain task list (fetched from /api/tasks)
 *  - 当前选中任务 / Current selected task
 *  - 按时间分组（供侧边栏使用） / Time-based grouping (for sidebar)
 *  - 搜索/筛 / Search / filter
 */
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { fetchTasks, deleteTask as apiDeleteTask, archiveTask as apiArchiveTask, unarchiveTask as apiUnarchiveTask } from '@/api/tasks'
import client, { extractErrorMessage } from '@/api/client'
import type { Task, TaskStatus } from '@/api/types'
import { matchTask } from '@/utils/search'
import { mergeTaskLists } from '@/utils/taskListMerge'
import { useI18n } from 'vue-i18n'

export const useTaskStore = defineStore('task', () => {
  const { t } = useI18n()
  // ─── 状态 / State ───
  const tasks = ref<Task[]>([])
  const currentTaskId = ref<string | null>(null)
  /** 任务列表加载错误（此前失败只写 console，界面停留在空态，用户看到的是「没有会议」而非「加载失败」）
      Load error surfaced to the UI; previously it only reached the console, so a
      failed fetch rendered as "no meetings" instead of "failed to load". */
  const loadError = ref<string | null>(null)
  const loading = ref(false)
  const searchQuery = ref('')
  /** 侧边栏专用搜索词（与 Library 的 searchQuery 互不干扰） / Sidebar-only search query (independent from Library's searchQuery) */
  const sidebarSearchQuery = ref('')
  /** 是否查看已归档任务（会议库 Tab 切换用） / Whether viewing archived tasks (for library tab toggle) */
  const showArchived = ref(false)
  /**
   * 「处理完成待查看」角标（REQ-TRANSCRIBE-PROGRESS R2 站内提醒）。
   * 后台检测到任务完成且用户不在该会议页时打标；进入会议页即清除。localStorage 持久化跨刷新。
   * In-app completion badges: marked when a task finishes while the user is away
   * from that meeting page; cleared on visit. Persisted across refreshes.
   */
  const COMPLETED_UNSEEN_KEY = 'oms_completed_unseen'
  const completedUnseen = ref<string[]>(loadCompletedUnseen())

  function loadCompletedUnseen(): string[] {
    try {
      const raw = localStorage.getItem(COMPLETED_UNSEEN_KEY)
      const arr = raw ? JSON.parse(raw) : []
      return Array.isArray(arr) ? arr.filter(x => typeof x === 'string') : []
    } catch { return [] }
  }
  function persistCompletedUnseen() {
    try { localStorage.setItem(COMPLETED_UNSEEN_KEY, JSON.stringify(completedUnseen.value)) } catch { /* 存储满时静默 */ }
  }
  function markCompletedUnseen(taskId: string) {
    if (completedUnseen.value.includes(taskId)) return
    completedUnseen.value = [...completedUnseen.value, taskId]
    persistCompletedUnseen()
  }
  function clearCompletedUnseen(taskId: string) {
    if (!completedUnseen.value.includes(taskId)) return
    completedUnseen.value = completedUnseen.value.filter(id => id !== taskId)
    persistCompletedUnseen()
  }
  /** 防抖后的搜索词（300ms），避免每次按键都触发全量过滤 / Debounced search query (300ms) to avoid full filter on every keystroke */
  const debouncedQuery = ref('')
  /** 侧边栏专用防抖搜索词 / Sidebar-only debounced search query */
  const debouncedSidebarQuery = ref('')
  let _debounceTimer: ReturnType<typeof setTimeout> | null = null
  let _sidebarDebounceTimer: ReturnType<typeof setTimeout> | null = null
  watch(searchQuery, (val) => {
    if (_debounceTimer) clearTimeout(_debounceTimer)
    _debounceTimer = setTimeout(() => { debouncedQuery.value = val }, 300)
  })
  watch(sidebarSearchQuery, (val) => {
    if (_sidebarDebounceTimer) clearTimeout(_sidebarDebounceTimer)
    _sidebarDebounceTimer = setTimeout(() => { debouncedSidebarQuery.value = val }, 300)
  })

  // ─── 计算属性 / Computed ───
  const currentTask = computed(() =>
    tasks.value.find(t => t.task_id === currentTaskId.value) ?? null,
  )

  /** 未归档任务（侧边栏 + 会议库默认视图） / Non-archived tasks (sidebar + library default view) */
  const activeTasks = computed(() => tasks.value.filter(t => !t.archived_at))

  /** 已归档任务 / Archived tasks */
  const archivedTasks = computed(() => tasks.value.filter(t => !!t.archived_at))

  /** 按搜索词过滤后的未归档任务列表（侧边栏专用，始终基于 activeTasks） / Filtered non-archived tasks by search query (sidebar-only, always based on activeTasks) */
  const filteredTasks = computed(() => {
    const q = debouncedSidebarQuery.value.trim().toLowerCase()
    if (!q) return activeTasks.value
    return activeTasks.value.filter(t => matchTask(t, q))
  })

  /**
   * 渐进式时间分组（侧边栏时间轴用） / Progressive time grouping (for sidebar timeline)
   * 今天 → 昨天 → 本周 → 上周 → 本月 → 上个月 → 更早 / Today → Yesterday → This week → Last week → This month → Last month → Earlier
   * 空组自动隐藏（如周一时“本周”为空） / Empty groups auto-hidden (e.g. "This week" empty on Monday)
   */
  const groupedTasks = computed(() => {
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 86400000)

    const dayOfWeek = (now.getDay() + 6) % 7
    const thisWeekStart = new Date(today.getTime() - dayOfWeek * 86400000)
    const lastWeekStart = new Date(thisWeekStart.getTime() - 7 * 86400000)
    const thisMonthStart = new Date(now.getFullYear(), now.getMonth(), 1)
    const lastMonthStart = new Date(now.getFullYear(), now.getMonth() - 1, 1)

    const groupOrder = ['today', 'yesterday', 'this_week', 'last_week', 'this_month', 'last_month', 'earlier']
    const labelKey: Record<string, string> = {
      today: 'sidebar.date_today',
      yesterday: 'sidebar.date_yesterday',
      this_week: 'sidebar.date_this_week',
      last_week: 'sidebar.date_last_week',
      this_month: 'sidebar.date_this_month',
      last_month: 'sidebar.date_last_month',
      earlier: 'sidebar.date_earlier',
    }
    const groups = new Map<string, { key: string; label: string; tasks: Task[]; isToday: boolean; sortKey: number }>()

    for (const task of filteredTasks.value) {
      const dateStr = task.meeting_date || task.created_at?.slice(0, 10) || 'unknown'
      const taskDate = new Date(dateStr + 'T00:00:00')
      const taskDay = new Date(taskDate.getFullYear(), taskDate.getMonth(), taskDate.getDate())
      const ts = taskDay.getTime()

      let key: string
      let isToday = false

      if (ts === today.getTime()) {
        key = 'today'
        isToday = true
      } else if (ts === yesterday.getTime()) {
        key = 'yesterday'
      } else if (ts >= thisWeekStart.getTime()) {
        key = 'this_week'
      } else if (ts >= lastWeekStart.getTime()) {
        key = 'last_week'
      } else if (ts >= thisMonthStart.getTime()) {
        key = 'this_month'
      } else if (ts >= lastMonthStart.getTime()) {
        key = 'last_month'
      } else {
        key = 'earlier'
      }

      if (!groups.has(key)) {
        groups.set(key, { key, label: t(labelKey[key]), tasks: [], isToday, sortKey: groupOrder.indexOf(key) })
      }
      groups.get(key)!.tasks.push(task)
    }

    for (const group of groups.values()) {
      group.tasks.sort((a, b) =>
        (b.created_at || '').localeCompare(a.created_at || ''),
      )
    }

    return Array.from(groups.values())
      .filter(g => g.tasks.length > 0)
      .sort((a, b) => a.sortKey - b.sortKey)
  })

  // ─── 操作 / Actions ───

  /**
   * 从后端拉取任务列表 / Fetch task list from backend
   * @param lite 仅合并状态字段（完成侦测器高频轮询）；不全量替换、不删任务、不翻 loading
   *             lite: merge status fields only for frequent watcher polling
   */
  async function loadTasks(lite = false) {
    if (!lite) loading.value = true
    try {
      const incoming = await fetchTasks(lite)
      tasks.value = mergeTaskLists(tasks.value, incoming, lite)
      loadError.value = null
    } catch (e) {
      // 失败必须落到界面上：只写 console 会让「加载失败」被用户读作「没有会议」
      // A failed fetch must reach the UI, or it reads as "no meetings".
      console.error('[TaskStore] 加载任务列表失败:', e)
      loadError.value = extractErrorMessage(e) || t('common.error.load_failed')
    } finally {
      if (!lite) loading.value = false
    }
  }

  /** 选中任务 / Select task */
  function selectTask(taskId: string | null) {
    currentTaskId.value = taskId
  }

  /** 删除任务 / Delete task */
  async function removeTask(taskId: string) {
    try {
      await apiDeleteTask(taskId)
      tasks.value = tasks.value.filter(t => t.task_id !== taskId)
      clearCompletedUnseen(taskId)
      if (currentTaskId.value === taskId) {
        currentTaskId.value = null
      }
    } catch (e) {
      console.error('[TaskStore] 删除任务失败:', e)
      throw e
    }
  }

  /** 归档任务 / Archive task */
  async function archiveTask(taskId: string) {
    await apiArchiveTask(taskId)
    patchTaskLocal(taskId, { archived_at: new Date().toISOString() })
  }

  /** 取消归档 / Unarchive */
  async function unarchiveTask(taskId: string) {
    await apiUnarchiveTask(taskId)
    patchTaskLocal(taskId, { archived_at: null })
  }

  /** 更新本地任务数据（乐观更新，不请求后端）；任务不存在时自动添加 / Update local task data (optimistic, no backend request); auto-adds if task not found */
  function patchTaskLocal(taskId: string, patch: Partial<Task>) {
    const idx = tasks.value.findIndex(t => t.task_id === taskId)
    if (idx >= 0) {
      tasks.value[idx] = { ...tasks.value[idx], ...patch }
    } else {
      tasks.value.push({ task_id: taskId, ...patch } as Task)
    }
  }

  /** 暂停录音（全局可用，不依赖 RecordingView） / Pause recording (globally available, not dependent on RecordingView) */
  async function pauseRecording() {
    try {
      await client.post('/api/record/pause')
      const rec = tasks.value.find(t => t.status === 'recording')
      if (rec) rec.status = 'paused'
    } catch (e) {
      console.error('[TaskStore] 暂停录音失败:', e)
      throw e
    }
  }

  /** 恢复录音（全局可用，不依赖 RecordingView） / Resume recording (globally available, not dependent on RecordingView) */
  async function resumeRecording() {
    try {
      await client.post('/api/record/resume')
      const rec = tasks.value.find(t => t.status === 'paused')
      if (rec) rec.status = 'recording'
    } catch (e) {
      console.error('[TaskStore] 恢复录音失败:', e)
      throw e
    }
  }

  /** 放弃录音（删除任务并清理数据） / Abandon recording (delete task and clean up data) */
  async function abandonRecording(taskId: string) {
    try {
      await apiDeleteTask(taskId)
      tasks.value = tasks.value.filter(t => t.task_id !== taskId)
      if (currentTaskId.value === taskId) {
        currentTaskId.value = null
      }
    } catch (e) {
      console.error('[TaskStore] 放弃录音失败:', e)
      throw e
    }
  }

  /** 结束录音（正常停止，进入识别流程） / Stop recording (normal stop, enters recognition pipeline) */
  async function stopRecording(taskId: string) {
    try {
      await client.post('/api/record/stop', { task_id: taskId })
      const rec = tasks.value.find(t => t.task_id === taskId)
      if (rec) rec.status = 'transcribing'
    } catch (e) {
      console.error('[TaskStore] 结束录音失败:', e)
      throw e
    }
  }

  /** 获取任务的状态文本 / Get status label for task */
  function getStatusLabel(status: TaskStatus): string {
    const map: Record<TaskStatus, string> = {
      recording: '录音中',
      paused: '已暂停',
      pending: '等待处理',
      processing: '处理中',
      transcribing: '识别中',
      awaiting_mapping: '待关联身份',
      summarizing: '生成纪要',
      completed: '已完成',
      failed: '处理失败',
    }
    return map[status] || status
  }

  return {
    tasks, currentTaskId, loading, loadError, searchQuery, sidebarSearchQuery, showArchived,
    completedUnseen, markCompletedUnseen, clearCompletedUnseen,
    currentTask, filteredTasks, groupedTasks, activeTasks, archivedTasks,
    loadTasks, selectTask, removeTask, patchTaskLocal, archiveTask, unarchiveTask,
    pauseRecording, resumeRecording, abandonRecording, stopRecording, getStatusLabel,
  }
})
