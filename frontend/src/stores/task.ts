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
   * 按日期分组（侧边栏时间轴用）
   * 返回: [{ dateLabel: '今天' | '昨天' | '9月5日' | '2026年8月', tasks: Task[], isToday: boolean }]
   */
  const groupedTasks = computed(() => {
    const groups = new Map<string, { label: string; tasks: Task[]; isToday: boolean; date: Date }>()
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 86400000)

    for (const task of filteredTasks.value) {
      const dateStr = task.meeting_date || task.created_at?.slice(0, 10) || 'unknown'
      const taskDate = new Date(dateStr + 'T00:00:00')
      const taskDay = new Date(taskDate.getFullYear(), taskDate.getMonth(), taskDate.getDate())

      let label: string
      let isToday = false

      if (taskDay.getTime() === today.getTime()) {
        label = '今天'
        isToday = true
      } else if (taskDay.getTime() === yesterday.getTime()) {
        label = '昨天'
      } else if (taskDate.getFullYear() === now.getFullYear()) {
        label = `${taskDate.getMonth() + 1}月${taskDate.getDate()}日`
      } else {
        label = `${taskDate.getFullYear()}年${taskDate.getMonth() + 1}月`
      }

      if (!groups.has(label)) {
        groups.set(label, { label, tasks: [], isToday, date: taskDate })
      }
      groups.get(label)!.tasks.push(task)
    }

    return Array.from(groups.values()).sort((a, b) => b.date.getTime() - a.date.getTime())
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

  /** 获取任务的状态文本 */
  function getStatusLabel(status: TaskStatus): string {
    const map: Record<TaskStatus, string> = {
      recording: '录音中',
      pending: '等待处理',
      transcribing: '转写中',
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
    loadTasks, selectTask, removeTask, patchTaskLocal, getStatusLabel,
  }
})
