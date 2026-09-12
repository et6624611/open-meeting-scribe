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
    <!-- 最近会议 -->
    <div class="start-recent-section" v-if="recentTasks.length > 0">
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
    <!-- 隐藏的文件输入 -->
    <input type="file" ref="fileInputRef" accept="audio/*,video/*" style="display:none" @change="onFileSelected">

    <!-- 首次启动隐私声明弹窗 -->
    <Teleport to="body">
      <div class="privacy-overlay" v-if="!acknowledged">
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
            <div class="privacy-dialog-detail">{{ t('start.privacy.disclaimer_detail') }}</div>
          </div>
          <div class="privacy-dialog-actions">
            <button class="privacy-dialog-btn-primary" @click="acknowledge">{{ t('start.privacy.disclaimer_acknowledge') }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 录音前确认弹窗 -->
    <Teleport to="body">
      <div class="privacy-overlay" v-if="showRecordConfirm" @click.self="showRecordConfirm = false">
        <div class="privacy-dialog">
          <div class="privacy-dialog-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          </div>
          <div class="privacy-dialog-title">{{ t('start.privacy.record_confirm_title') }}</div>
          <div class="privacy-dialog-desc">{{ t('start.privacy.record_confirm_desc') }}</div>
          <div class="privacy-dialog-checklist-title">{{ t('start.privacy.record_confirm_checklist_title') }}</div>
          <div class="privacy-dialog-checklist">
            <div class="privacy-dialog-check-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
              {{ t('start.privacy.check_state_secrets') }}
            </div>
            <div class="privacy-dialog-check-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
              {{ t('start.privacy.check_trade_secrets') }}
            </div>
            <div class="privacy-dialog-check-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
              {{ t('start.privacy.check_personal_privacy') }}
            </div>
          </div>
          <div class="privacy-dialog-actions">
            <button class="privacy-dialog-btn-cancel" @click="showRecordConfirm = false">{{ t('common.action.cancel') }}</button>
            <button class="privacy-dialog-btn-primary" @click="confirmStartRecord">{{ t('start.privacy.confirm_start') }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 文件上传确认弹窗 -->
    <Teleport to="body">
      <div class="privacy-overlay" v-if="showUploadConfirm" @click.self="showUploadConfirm = false">
        <div class="privacy-dialog">
          <div class="privacy-dialog-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          </div>
          <div class="privacy-dialog-title">{{ t('start.privacy.upload_confirm_title') }}</div>
          <div class="privacy-dialog-desc">{{ t('start.privacy.upload_confirm_desc') }}</div>
          <div class="privacy-dialog-actions">
            <button class="privacy-dialog-btn-cancel" @click="showUploadConfirm = false">{{ t('common.action.cancel') }}</button>
            <button class="privacy-dialog-btn-primary" @click="confirmUpload">{{ t('start.privacy.confirm_upload') }}</button>
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
import { submitTranscribe } from '@/api/tasks'
import { getRecordStatus } from '@/api/record'
import type { Task } from '@/api/types'
import ResponsiveButtonGroup from '@/components/common/ResponsiveButtonGroup.vue'

const { t } = useI18n()
const router = useRouter()
const taskStore = useTaskStore()
const recorder = useRecorder()
const { acknowledged, acknowledge } = usePrivacyDisclaimer()

const fileInputRef = ref<HTMLInputElement | null>(null)
const showRecordConfirm = ref(false)
const showUploadConfirm = ref(false)

// ─── 图标组件 ───
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

const UploadIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round' }, [
      h('path', { d: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4' }),
      h('polyline', { points: '17 8 12 3 7 8' }),
      h('line', { x1: '12', y1: '3', x2: '12', y2: '15' }),
    ])
  },
}

// ── 操作按钮配置 ───
const actionButtons = computed(() => [
  {
    key: 'record',
    label: hasRecordingTask.value ? t('start.return_record') : t('start.record'),
    icon: hasRecordingTask.value ? LockIcon : MicIcon,
    variant: 'primary' as const,
    shortcut: hasRecordingTask.value ? undefined : '⌘R',
    onClick: () => hasRecordingTask.value ? jumpToRecording() : onStartRecord(),
  },
  {
    key: 'upload',
    label: t('start.upload'),
    icon: UploadIcon,
    variant: 'secondary' as const,
    shortcut: '⌘U',
    onClick: onUploadClick,
  },
])

/** 最近 3 个会议（含所有状态，与侧边栏排序一致） */
const recentTasks = computed(() =>
  taskStore.tasks.slice(0, 3)
)

/** 是否存在录音中的任务 */
const recTask = computed(() => {
  // 只认为 status 为 recording/paused 且 created_at 在最近 24 小时内的任务是"正在录音"
  // 避免旧任务的残留状态误导用户
  const now = new Date()
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  
  return taskStore.tasks.find(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    // 如果任务创建时间超过 24 小时，不认为是"正在录音"
    const createdAt = t.created_at ? new Date(t.created_at) : null
    if (createdAt && createdAt < oneDayAgo) return false
    return true
  }) ?? null
})
const hasRecordingTask = computed(() => !!recTask.value)

/** 录音计时器（与 TopBar 同步） */
const recElapsed = ref('00:00')
let recTimer: ReturnType<typeof setInterval> | null = null
let recElapsedSec = 0

function tickRecTimer() {
  recElapsedSec++
  const h = Math.floor(recElapsedSec / 3600)
  const m = Math.floor((recElapsedSec % 3600) / 60)
  const s = recElapsedSec % 60
  recElapsed.value = h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

watch(recTask, (task) => {
  if (task && task.status !== 'paused') {
    if (!recTimer) recTimer = setInterval(tickRecTimer, 1000)
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
  showRecordConfirm.value = true
}

async function confirmStartRecord() {
  showRecordConfirm.value = false
  try {
    const data = await recorder.startRecording()
    if (data?.task_id) {
      // [状态同步] 录音成功后刷新任务列表，否则侧边栏不显示新录音
      await taskStore.loadTasks()
      router.push({ name: 'recording', params: { taskId: data.task_id } })
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string }; status?: number } }
    // 后端提示"已在录制中"时，自动导航到已有录音页
    if (err.response?.status === 400) {
      try {
        const status = await getRecordStatus()
        if (status.recording && status.task_id) {
          // [状态同步] 恢复活跃录音时刷新任务列表
          await taskStore.loadTasks()
          taskStore.selectTask(status.task_id)
          router.push({ name: 'recording', params: { taskId: status.task_id } })
          return
        }
      } catch { /* 静默 */ }
    }
    alert(err.response?.data?.detail || t('start.errors.start_failed'))
  }
}

function onUploadClick() {
  showUploadConfirm.value = true
}

function confirmUpload() {
  showUploadConfirm.value = false
  fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  try {
    const task = await submitTranscribe(file)
    // [状态同步] 上传成功后刷新任务列表
    await taskStore.loadTasks()
    router.push({ name: 'generating', params: { taskId: task.task_id } })
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    alert(err.response?.data?.detail || t('start.errors.upload_failed'))
  } finally {
    input.value = ''
  }
}

function openTask(task: Task) {
  taskStore.selectTask(task.task_id)
  // 所有非录音任务统一进入纪要页（中间状态由 GeneratingView 内联处理）
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

// ── 全局快捷键事件（由 useKeyboardShortcuts 分发） ───
onMounted(() => {
  window.addEventListener('global-start-record', onStartRecord)
  window.addEventListener('global-start-upload', onUploadClick)
})

onUnmounted(() => {
  window.removeEventListener('global-start-record', onStartRecord)
  window.removeEventListener('global-start-upload', onUploadClick)
})
</script>
