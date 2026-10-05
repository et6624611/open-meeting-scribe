<template>
  <div class="start-page" id="startPage">
    <div class="start-page-bg">
      <svg class="start-page-svg" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice">
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-1" d="M 80 180 C 200 160, 280 280, 380 260" style="--path-len: 400" stroke-dasharray="400" />
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-2" d="M 380 260 C 480 240, 520 380, 620 350" style="--path-len: 380" stroke-dasharray="380" />
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-3" d="M 620 350 C 720 320, 780 200, 900 220" style="--path-len: 420" stroke-dasharray="420" />
        <circle class="ctx-node ctx-node-anim ctx-node-1" cx="380" cy="260" r="7" />
        <circle class="ctx-node ctx-node-anim ctx-node-2" cx="620" cy="350" r="6" />
        <circle class="ctx-node-dot ctx-node-anim ctx-node-1" cx="380" cy="260" r="2.5" />
        <circle class="ctx-node-dot ctx-node-anim ctx-node-2" cx="620" cy="350" r="2.5" />
      </svg>
    </div>
    <div class="start-page-content">
      <div class="start-logo">
        <svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="4" y="4" width="48" height="48" rx="16" fill="var(--fg)"/>
          <circle cx="28" cy="28" r="13" stroke="var(--bg)" stroke-width="7" fill="none"/>
        </svg>
      </div>
      <h2 class="start-title">{{ t('start.title') }}</h2>
      <div class="start-actions">
        <ResponsiveButtonGroup
          :buttons="actionButtons"
          :icon-threshold="480"
          :mixed-threshold="600"
        />
      </div>
    </div>
    <!-- 最近会议 / Recent meetings -->
    <div class="start-recent-section" v-show="recentTasks.length > 0">
      <div class="start-divider">{{ t('start.recent') }}</div>
      <div class="start-recent" id="startRecentList">
        <div class="start-recent-list">
          <button v-for="(task, index) in recentTasks" :key="task.task_id" class="start-recent-item" :class="{ 'is-latest': index === 0 }" :title="task.title || task.audio_name" @click="openTask(task)">
            <div class="start-recent-item-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/></svg>
            </div>
            <div class="start-recent-item-info">
              <div class="start-recent-item-title">{{ task.title || task.audio_name || t('common.untitled') }}</div>
              <div class="start-recent-item-meta">
                <span>{{ formatDate(task) }}</span>
                <span class="sep">·</span>
                <span v-if="task.status !== 'completed'" class="start-recent-status" :class="`status-${task.status}`">{{ formatStatus(task.status) }}</span>
                <span v-else>{{ formatDuration(task.audio_duration) }}</span>
              </div>
            </div>
          </button>
          <button v-if="taskStore.tasks.length > 3" class="start-recent-more" @click="router.push('/library')">
            {{ t('start.view_all', { count: taskStore.tasks.length }) }}
          </button>
        </div>
      </div>
    </div>
    <!-- 导入弹窗 / Import dialog -->
    <ImportDialog
      :visible="showImportDialog"
      @close="showImportDialog = false"
      @imported="onImported"
      @open-existing="onOpenExistingTask"
    />

    <!-- 隐私同意弹窗（首次录音/上传时强制显示，确认后不再出现） / Privacy consent dialog (forced on first record/upload, hidden after confirmation) -->
    <Teleport to="body">
      <div class="privacy-overlay" v-if="showConsentDialog" @click.self="cancelConsent">
        <div class="privacy-dialog">
          <div class="privacy-dialog-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          </div>
          <div class="privacy-dialog-title">{{ t('start.privacy.disclaimer_title') }}</div>
          <div class="privacy-dialog-body">
            <div class="privacy-dialog-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              {{ t('start.privacy.disclaimer_local') }}
            </div>
            <div class="privacy-dialog-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>
              {{ t('start.privacy.disclaimer_cloud') }}
            </div>
            <div class="privacy-dialog-warn">{{ t('start.privacy.disclaimer_warn') }}</div>
            <div class="privacy-dialog-region">{{ t('start.privacy.disclaimer_region') }}</div>
            <div class="privacy-dialog-prohibit">{{ t('start.privacy.disclaimer_prohibit') }}</div>
            <div class="privacy-dialog-checklist">
              <label class="privacy-dialog-check-item privacy-dialog-check-label">
                <input type="checkbox" v-model="participantConfirmed" />
                <span>{{ t('start.privacy.check_participants') }}</span>
              </label>
            </div>
            <div class="privacy-dialog-detail">{{ t('start.privacy.disclaimer_detail') }}</div>
          </div>
          <div class="privacy-dialog-actions">
            <button class="privacy-dialog-btn-cancel" @click="cancelConsent">{{ t('common.action.cancel') }}</button>
            <button class="privacy-dialog-btn-primary" :disabled="!participantConfirmed" @click="confirmConsent">{{ t('start.privacy.disclaimer_acknowledge') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, h, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useRecorder } from '@/composables/useRecorder'
import { usePrivacyDisclaimer } from '@/composables/usePrivacyDisclaimer'
import { getRecordStatus } from '@/api/record'
import { extractErrorMessage } from '@/api/client'
import type { Task } from '@/api/types'
import ResponsiveButtonGroup from '@/components/common/ResponsiveButtonGroup.vue'
import ImportDialog from '@/components/common/ImportDialog.vue'
import { useEscClose } from '@/composables/useEscClose'
import { modKey } from '@/utils/platform'

const { t } = useI18n()
const router = useRouter()
const taskStore = useTaskStore()
const recorder = useRecorder()
const { acknowledged, acknowledge, init: initPrivacy } = usePrivacyDisclaimer()

const showImportDialog = ref(false)
const showConsentDialog = ref(false)
const participantConfirmed = ref(false)
let pendingAction: (() => void) | null = null

useEscClose(showConsentDialog, () => { cancelConsent() })

function cancelConsent() {
  showConsentDialog.value = false
  pendingAction = null
  participantConfirmed.value = false
}

async function confirmConsent() {
  showConsentDialog.value = false
  participantConfirmed.value = false
  await acknowledge()
  if (pendingAction) {
    const action = pendingAction
    pendingAction = null
    action()
  }
}

/** 检查同意状态，未同意则弹窗并暂存操作 / Check consent status; if not consented, show dialog and stash action */
function requireConsent(action: () => void): boolean {
  if (acknowledged.value) return true
  pendingAction = action
  showConsentDialog.value = true
  return false
}

// ─── 图标组件 / Icon components ───
const MicIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round' }, [
      h('path', { d: 'M12 2a4 4 0 014 4v6a4 4 0 01-8 0V6a4 4 0 014-4z' }),
      h('path', { d: 'M19 10v2a7 7 0 01-14 0v-2' }),
      h('line', { x1: '12', y1: '19', x2: '12', y2: '22' }),
    ])
  },
}

const LockIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round' }, [
      h('rect', { x: '3', y: '11', width: '18', height: '11', rx: '2', ry: '2' }),
      h('path', { d: 'M7 11V7a5 5 0 0 1 10 0v4' }),
    ])
  },
}

const ImportIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
      h('path', { d: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4' }),
      h('polyline', { points: '7 10 12 15 17 10' }),
      h('line', { x1: '12', y1: '15', x2: '12', y2: '3' }),
    ])
  },
}

// ── 操作按钮配置 / Action button config ───
const actionButtons = computed(() => [
  {
    key: 'record',
    label: hasRecordingTask.value ? t('start.return_record') : t('start.record'),
    icon: hasRecordingTask.value ? LockIcon : MicIcon,
    variant: 'primary' as const,
    shortcut: hasRecordingTask.value ? undefined : `${modKey}R`,
    onClick: () => hasRecordingTask.value ? jumpToRecording() : onStartRecord(),
  },
  {
    key: 'import',
    label: t('start.import.title'),
    icon: ImportIcon,
    variant: 'secondary' as const,
    shortcut: `${modKey}U`,
    onClick: onImportClick,
  },
])

/** 最近 3 个会议（含所有状态，与侧边栏排序一致） / Latest 3 meetings (all statuses, consistent with sidebar sort) */
const recentTasks = computed(() =>
  taskStore.tasks.slice(0, 3)
)

/** 是否存在录音中的任务 / Whether there is a recording task */
const recTask = computed(() => {
  // 只认为 status 为 recording/paused 且 created_at 在最近 24 小时内的任务是“正在录音” / Only consider status recording/paused with created_at within 24h as "recording"
  // 避免旧任务的残留状态误导用户 / Avoid stale state from old tasks misleading users
  const now = new Date()
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  
  return taskStore.tasks.find(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    // 如果任务创建时间超过 24 小时，不认为是“正在录音” / If task created more than 24h ago, don't consider it "recording"
    const createdAt = t.created_at ? new Date(t.created_at) : null
    if (createdAt && createdAt < oneDayAgo) return false
    return true
  }) ?? null
})
const hasRecordingTask = computed(() => !!recTask.value)

/** 录音计时器（与 TopBar 同步） / Recording timer (synced with TopBar) */
const recElapsed = ref('00:00')
let recTimer: ReturnType<typeof setInterval> | null = null
let recElapsedSec = 0

function formatRecTime(totalSec: number): string {
  const s = Math.floor(totalSec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

/** 基于任务 created_at 计算已过秒数（页面刷新后仍能还原） / Calculate elapsed seconds from task created_at (survives page refresh) */
function calcElapsedFromTask(task: { created_at?: string }): number {
  if (!task?.created_at) return 0
  const created = new Date(task.created_at).getTime()
  return Math.max(0, Math.floor((Date.now() - created) / 1000))
}

function tickRecTimer() {
  recElapsedSec++
  recElapsed.value = formatRecTime(recElapsedSec)
}

watch(recTask, async (task) => {
  if (task) {
    // 优先从后端获取精确已过时长（已扣除暂停），失败则回退到 created_at 估算 / Prefer precise elapsed from backend (pause deducted), fallback to created_at estimate
    let backendPaused = false
    try {
      const status = await getRecordStatus()
      if (status.recording && status.elapsed != null) {
        recElapsedSec = Math.floor(status.elapsed)
      } else {
        recElapsedSec = calcElapsedFromTask(task)
      }
      // 后端是唯一事实源：录音页暂停不会同步 store，这里兜底修正过期状态 / Backend is the source of truth: pausing on the recording page does not sync the store, so correct stale status here
      backendPaused = !!status.paused
      if (status.recording && status.paused && task.status === 'recording') {
        taskStore.patchTaskLocal(task.task_id, { status: 'paused' })
      }
    } catch {
      recElapsedSec = calcElapsedFromTask(task)
    }
    recElapsed.value = formatRecTime(recElapsedSec)
    if (task.status !== 'paused' && !backendPaused) {
      if (!recTimer) recTimer = setInterval(tickRecTimer, 1000)
    } else if (recTimer) {
      // 暂停中：冻结计时器，保留已过时长 / Paused: freeze timer, keep elapsed
      clearInterval(recTimer); recTimer = null
    }
  } else {
    if (recTimer) { clearInterval(recTimer); recTimer = null }
    recElapsedSec = 0
    recElapsed.value = '00:00'
  }
}, { immediate: true })

function jumpToRecording() {
  if (recTask.value) {
    taskStore.selectTask(recTask.value.task_id)
    router.push({ name: 'recording', params: { taskId: recTask.value.task_id } })
  }
}

function onStartRecord() {
  if (!requireConsent(() => doStartRecord())) return
  doStartRecord()
}

function doStartRecord() {
  recorder.startRecording().then(async (data) => {
    if (data?.task_id) {
      // 乐观更新：立即将新任务加入本地列表，不阻塞导航 / Optimistic update: add new task to local list immediately, don't block navigation
      taskStore.patchTaskLocal(data.task_id, {
        status: 'recording',
        source: 'record',
        created_at: new Date().toISOString(),
        meeting_date: new Date().toISOString().slice(0, 10),
      } as any)
      router.push({ name: 'recording', params: { taskId: data.task_id } })
      // 后台静默刷新任务列表（不等待） / Silently refresh task list in background (don't await)
      taskStore.loadTasks()
    }
  }).catch(async (e: unknown) => {
    const err = e as { response?: { data?: { detail?: unknown }; status?: number } }
    if (err.response?.status === 400) {
      try {
        const status = await getRecordStatus()
        if (status.recording && status.task_id) {
          taskStore.selectTask(status.task_id)
          router.push({ name: 'recording', params: { taskId: status.task_id } })
          // [状态同步] 后台静默刷新任务列表 / Silently refresh task list in background
          taskStore.loadTasks()
          return
        }
      } catch { /* 静默 */ }
    }
    alert(extractErrorMessage(e, t('start.errors.start_failed')))
  })
}

function onImportClick() {
  if (!requireConsent(() => doImport())) return
  doImport()
}

function doImport() {
  showImportDialog.value = true
}

function onImported(taskId: string) {
  taskStore.loadTasks()
  router.push({ name: 'generating', params: { taskId } })
}

function onOpenExistingTask(taskId: string) {
  const task = taskStore.tasks.find(t => t.task_id === taskId)
  if (task) {
    taskStore.selectTask(taskId)
    if (task.status === 'recording' || task.status === 'paused') {
      router.push({ name: 'recording', params: { taskId } })
    } else {
      router.push({ name: 'generating', params: { taskId } })
    }
  }
}

function openTask(task: Task) {
  taskStore.selectTask(task.task_id)
  // 所有非录音任务统一进入纪要页（中间状态由 GeneratingView 内联处理） / All non-recording tasks go to generating view (intermediate states handled inline) 
  if (task.status === 'recording' || task.status === 'paused') {
    router.push({ name: 'recording', params: { taskId: task.task_id } })
  } else {
    router.push({ name: 'generating', params: { taskId: task.task_id } })
  }
}

function formatDate(task: Task): string {
  const d = task.meeting_date || task.created_at?.slice(0, 10) || ''
  if (!d) return ''
  const date = new Date(d + 'T00:00:00')
  return date.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
}

function formatDuration(sec: number | null): string {
  if (!sec) return t('common.duration.unknown')
  const m = Math.round(sec / 60)
  return m < 60 ? t('common.duration.minutes', { m }) : t('common.duration.hours_minutes', { h: Math.floor(m / 60), m: m % 60 })
}

const statusLabels: Record<string, string> = {
  recording: t('common.status.recording'),
  paused: t('common.status.paused'),
  pending: t('common.status.pending'),
  transcribing: t('common.status.transcribing'),
  summarizing: t('common.status.summarizing'),
  awaiting_mapping: t('common.status.awaiting_mapping'),
  failed: t('common.status.failed'),
}

function formatStatus(status: string): string {
  return statusLabels[status] || status
}

// ── 全局快捷键事件（由 useKeyboardShortcuts 分发） / Global shortcut events (dispatched by useKeyboardShortcuts) ───
onMounted(() => {
  initPrivacy()
  window.addEventListener('global-start-record', onStartRecord)
  window.addEventListener('global-start-upload', onImportClick)
})

onUnmounted(() => {
  window.removeEventListener('global-start-record', onStartRecord)
  window.removeEventListener('global-start-upload', onImportClick)
})
</script>
