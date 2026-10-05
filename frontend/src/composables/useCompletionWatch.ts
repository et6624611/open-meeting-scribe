/**
 * 全局完成侦测 — 后台任务完成时的站内提醒（角标 + toast）与系统通知尝试
 * Global completion watcher (REQ-TRANSCRIBE-PROGRESS R2 / AC-8).
 *
 * 处理中每 5s 轻量刷新任务列表；检测到「处理中 → 已完成」跃迁时：
 *  - 用户正停留在该会议页 → 不发通知（页面自身已就地切换为完成态，避免重复打扰）；
 *  - 否则 → 会议列表角标 + 站内 toast；系统通知仅在宿主已授予权限时发送
 *    （pywebview 壳内恒不可用，按 Q5 裁决降级为仅站内，不弹索权窗）。
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { showToast } from '@/composables/useToast'
import { sendDesktopNotify } from '@/utils/desktopNotify'
import type { Task } from '@/api/types'

/** 视为「仍在处理管线中」的状态（recording/paused 属录音链路，不由本侦测负责） */
const ACTIVE = new Set(['pending', 'processing', 'transcribing', 'summarizing', 'awaiting_mapping'])

const POLL_INTERVAL_MS = 5000

export function useCompletionWatch() {
  const { t } = useI18n()
  const router = useRouter()
  const taskStore = useTaskStore()
  let timer: ReturnType<typeof setInterval> | null = null
  /** 上一次观察到的任务状态快照（task_id → status） */
  const prevStatus = new Map<string, string>()
  const watching = ref(false)

  function taskTitle(task: Task): string {
    return task.title || task.audio_name || t('generating.breadcrumb.default_title')
  }

  function onUserPage(taskId: string): boolean {
    const route = router.currentRoute.value
    return route.name === 'generating' && String(route.params.taskId ?? '') === taskId
  }

  function snapshot(tasks: Task[]) {
    prevStatus.clear()
    for (const task of tasks) prevStatus.set(task.task_id, task.status)
  }

  async function tick() {
    const before = new Map(prevStatus)
    try {
      // lite：5s 高频轮询只取状态字段（全量列表携带全部转写，曾达 35MB 并阻塞后端事件循环）
      await taskStore.loadTasks(true)
    } catch { return } // loadTasks 内部已兜底 loadError
    snapshot(taskStore.tasks)
    for (const task of taskStore.tasks) {
      const prev = before.get(task.task_id)
      if (prev && ACTIVE.has(prev) && task.status === 'completed') {
        handleCompletion(task)
      }
    }
  }

  function handleCompletion(task: Task) {
    // 用户正停留该会议页：不发任何额外提醒（页面内已就地呈现完成态）
    if (onUserPage(task.task_id)) {
      taskStore.clearCompletedUnseen(task.task_id)
      return
    }
    taskStore.markCompletedUnseen(task.task_id)
    const title = taskTitle(task)
    showToast(t('processing.completed_toast', { title }), 'success')
    // 系统通知：仅在权限已被授予时发送；pywebview 壳内为静默 no-op（Q5 降级）
    sendDesktopNotify(title, t('processing.notify_body'), `${window.location.origin}/meeting/${task.task_id}`)
  }

  const hasActive = () => taskStore.tasks.some(tk => ACTIVE.has(tk.status))

  function startInterval() {
    if (timer) return
    watching.value = true
    snapshot(taskStore.tasks)
    timer = setInterval(tick, POLL_INTERVAL_MS)
  }
  function stopInterval() {
    if (timer) { clearInterval(timer); timer = null }
    watching.value = false
  }

  onMounted(() => {
    snapshot(taskStore.tasks)
    if (hasActive()) startInterval()
    // 任务状态变化驱动启停（新任务提交 → 开始侦测；全部落定 → 停止轮询）
    watch(
      () => taskStore.tasks.map(tk => `${tk.task_id}:${tk.status}`).join('|'),
      () => { if (hasActive()) startInterval(); else stopInterval() },
    )
    // 进入会议页即清除该任务角标
    watch(
      () => router.currentRoute.value.fullPath,
      () => {
        const route = router.currentRoute.value
        if (route.name === 'generating' && route.params.taskId) {
          taskStore.clearCompletedUnseen(String(route.params.taskId))
        }
      },
      { immediate: true },
    )
  })
  onUnmounted(stopInterval)

  return { watching }
}
