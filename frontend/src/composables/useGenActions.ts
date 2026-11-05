import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { deleteTask, retranscribe, retrySummary, fetchTask } from '@/api/tasks'
import { showToast } from '@/composables/useToast'

interface GenDataLike {
  taskId: string
  showDeleteDialog: import('vue').Ref<boolean>
  showArchiveDialog: import('vue').Ref<boolean>
  onArchive: () => Promise<void>
  isArchived: import('vue').Ref<boolean>
  startPolling: () => void
  summaryMd: import('vue').Ref<string>
}

export function useGenActions(data: GenDataLike) {
  const taskStore = useTaskStore()
  const router = useRouter()
  const { t } = useI18n()

  const showCloudFallbackConfirm = ref(false)

  async function onRetrySummary() {
    taskStore.patchTaskLocal(data.taskId, {
      status: 'processing', progress: 75, error: undefined,
      error_category: undefined, error_suggestion: undefined, failed_stage: undefined,
    })
    data.startPolling()
    try {
      await retrySummary(data.taskId)
      void taskStore.loadTasks()
    } catch (e) {
      console.error('retry summary failed:', e)
      try {
        taskStore.patchTaskLocal(data.taskId, await fetchTask(data.taskId))
      } catch { /* optimistic state preserved; next polling will self-correct */ }
    }
  }

  async function onRetryFromFailure() {
    try {
      await retranscribe(data.taskId)
      taskStore.patchTaskLocal(data.taskId, { status: 'transcribing', error: undefined, error_category: undefined, error_suggestion: undefined })
      data.startPolling()
    } catch (e) { console.error('retry from failure page failed:', e) }
  }

  async function onCloudFallbackConfirm() {
    try {
      await retranscribe(data.taskId, { engineOverride: 'cloud' })
      taskStore.patchTaskLocal(data.taskId, {
        status: 'transcribing', error: undefined, error_category: undefined, error_suggestion: undefined,
        error_code: undefined, can_fallback_cloud: undefined,
      })
      showToast(t('generating.failure.cloud_retry_started'), 'success')
      data.startPolling()
    } catch (e) {
      console.error('cloud fallback retry failed:', e)
      showToast(t('generating.failure.cloud_retry_failed'), 'error')
    }
  }

  function onDelete() { data.showDeleteDialog.value = true }
  async function onDeleteConfirm() {
    data.showDeleteDialog.value = false
    await deleteTask(data.taskId); await taskStore.loadTasks(); router.push('/')
  }

  function onArchiveConfirm() { data.showArchiveDialog.value = true }
  async function onArchiveDone() {
    await data.onArchive()
    if (data.isArchived.value) router.push('/library')
  }

  async function onRetranscribe() {
    await retranscribe(data.taskId)
    router.push({ name: 'generating', params: { taskId: data.taskId } })
  }

  // 纪要重试后高亮修改段落
  function scrollToSummaryDQ(dq: string, getTextarea: () => HTMLTextAreaElement | null | undefined) {
    let attempts = 0
    const tick = () => {
      attempts += 1
      const md = data.summaryMd.value
      const el = getTextarea()
      if (md && el) {
        let idx = md.indexOf(dq)
        if (idx < 0) idx = md.indexOf(dq.slice(0, 10))
        if (idx >= 0) {
          el.focus({ preventScroll: false })
          el.setSelectionRange(idx, Math.min(idx + dq.length, md.length))
          return
        }
      }
      if (attempts < 15) window.setTimeout(tick, 250)
    }
    window.setTimeout(tick, 100)
  }

  return {
    showCloudFallbackConfirm,
    onRetrySummary, onRetryFromFailure, onCloudFallbackConfirm,
    onDelete, onDeleteConfirm, onArchiveConfirm, onArchiveDone, onRetranscribe,
    scrollToSummaryDQ,
  }
}
