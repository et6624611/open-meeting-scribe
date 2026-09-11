/**
 * 任务状态管理
 *
 * 职责：
 *  - 维护任务列表（从 /api/tasks 拉取）
 *  - 当前选中任务
 *  - 按时间分组（供侧边栏使用）
 *  - 搜索/筛选
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchTasks, deleteTask as apiDeleteTask } from '@/api/tasks'
import client from '@/api/client'
import type { Task, TaskStatus } from '@/api/types'

export const useTaskStore = defineStore('task', () => {
  // ─── 状态 ───
  const tasks = ref<Task[]>([])
  const currentTaskId = ref<string | null>(null)
  const loading = ref(false)
  const searchQuery = ref('')

  // ─── 计算属性 ───
  const currentTask = computed(() =>
    tasks.value.find(t => t.task_id === currentTaskId.value) ?? null,
  )

  /** 按搜索词过滤后的任务列表 */
  const filteredTasks = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return tasks.value
    return tasks.value.filter(t => {
      const title = (t.title || t.audio_name || '').toLowerCase()
      const summary = (t.summary || '').toLowerCase()
      return title.includes(q) || summary.includes(q)
    })
  })

  /**
   * 渐进式时间分组（侧边栏时间轴用）
   * 今天 → 昨天 → 本周 → 上周 → 本月 → 上个月 → 更早
   * 空组自动隐藏（如周一时"本周"为空）
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

    const groupOrder = ['今天', '昨天', '本周', '上周', '本月', '上个月', '更早']
    const groups = new Map<string, { label: string; tasks: Task[]; isToday: boolean; sortKey: number }>()

    for (const task of filteredTasks.value) {
      const dateStr = task.meeting_date || task.created_at?.slice(0, 10) || 'unknown'
      const taskDate = new Date(dateStr + 'T00:00:00')
      const taskDay = new Date(taskDate.getFullYear(), taskDate.getMonth(), taskDate.getDate())
      const ts = taskDay.getTime()

      let label: string
      let isToday = false

      if (ts === today.getTime()) {
        label = '今天'
        isToday = true
      } else if (ts === yesterday.getTime()) {
        label = '昨天'
      } else if (ts >= thisWeekStart.getTime()) {
        label = '本周'
      } else if (ts >= lastWeekStart.getTime()) {
        label = '上周'
      } else if (ts >= thisMonthStart.getTime()) {
        label = '本月'
      } else if (ts >= lastMonthStart.getTime()) {
        label = '上个月'
      } else {
        label = '更早'
      }

      if (!groups.has(label)) {
        groups.set(label, { label, tasks: [], isToday, sortKey: groupOrder.indexOf(label) })
      }
      groups.get(label)!.tasks.push(task)
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

  // ─── 操作 ───

  /** 从后端拉取任务列表 */
  async function loadTasks() {
    loading.value = true
    try {
      tasks.value = await fetchTasks()
    } catch (e) {
      console.error('[TaskStore] 加载任务列表失败:', e)
    } finally {
      loading.value = false
    }
  }

  /** 选中任务 */
  function selectTask(taskId: string | null) {
    currentTaskId.value = taskId
  }

  /** 删除任务 */
  async function removeTask(taskId: string) {
    try {
      await apiDeleteTask(taskId)
      tasks.value = tasks.value.filter(t => t.task_id !== taskId)
      if (currentTaskId.value === taskId) {
        currentTaskId.value = null
      }
    } catch (e) {
      console.error('[TaskStore] 删除任务失败:', e)
      throw e
    }
  }

  /** 更新本地任务数据（乐观更新，不请求后端） */
  function patchTaskLocal(taskId: string, patch: Partial<Task>) {
    const idx = tasks.value.findIndex(t => t.task_id === taskId)
    if (idx >= 0) {
      tasks.value[idx] = { ...tasks.value[idx], ...patch }
    }
  }

  /** 暂停录音（全局可用，不依赖 RecordingView） */
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

  /** 恢复录音（全局可用，不依赖 RecordingView） */
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

  /** 放弃录音（删除任务并清理数据） */
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

  /** 结束录音（正常停止，进入识别流程） */
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

  /** 获取任务的状态文本 */
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
    tasks, currentTaskId, loading, searchQuery,
    currentTask, filteredTasks, groupedTasks,
    loadTasks, selectTask, removeTask, patchTaskLocal,
    pauseRecording, resumeRecording, abandonRecording, stopRecording, getStatusLabel,
  }
})
