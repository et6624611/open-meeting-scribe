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
      <h2 class="start-title">开始新的会议</h2>
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
      <div class="start-divider">最近会议</div>
      <div class="start-recent" id="startRecentList">
        <div class="start-recent-list">
          <button v-for="(task, index) in recentTasks" :key="task.task_id" class="start-recent-item" :class="{ 'is-latest': index === 0 }" @click="openTask(task)">
            <div class="start-recent-item-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/></svg>
            </div>
            <div class="start-recent-item-info">
              <div class="start-recent-item-title">{{ task.title || task.audio_name || '未命名' }}</div>
              <div class="start-recent-item-meta">
                <span>{{ formatDate(task) }}</span>
                <span class="sep">·</span>
                <span v-if="task.status !== 'completed'" class="start-recent-status" :class="`status-${task.status}`">{{ formatStatus(task.status) }}</span>
                <span v-else>{{ formatDuration(task.audio_duration) }}</span>
              </div>
            </div>
          </button>
          <button v-if="taskStore.tasks.length > 3" class="start-recent-more" @click="router.push('/library')">
            查看全部 {{ taskStore.tasks.length }} 个会议 →
          </button>
        </div>
      </div>
    </div>
    <!-- 隐藏的文件输入 -->
    <input type="file" ref="fileInputRef" accept="audio/*,video/*" style="display:none" @change="onFileSelected">
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, h, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { useRecorder } from '@/composables/useRecorder'
import { submitTranscribe } from '@/api/tasks'
import type { Task } from '@/api/types'
import ResponsiveButtonGroup from '@/components/common/ResponsiveButtonGroup.vue'

const router = useRouter()
const taskStore = useTaskStore()
const recorder = useRecorder()

const fileInputRef = ref<HTMLInputElement | null>(null)

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
    label: hasRecordingTask.value ? '返回录音' : '麦克风录音',
    icon: hasRecordingTask.value ? LockIcon : MicIcon,
    variant: 'primary' as const,
    shortcut: hasRecordingTask.value ? undefined : '⌘R',
    onClick: () => hasRecordingTask.value ? jumpToRecording() : onStartRecord(),
  },
  {
    key: 'upload',
    label: '上传音频文件',
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

async function onStartRecord() {
  try {
    const data = await recorder.startRecording()
    if (data?.task_id) {
      router.push({ name: 'recording', params: { taskId: data.task_id } })
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    alert(err.response?.data?.detail || '开始录音失败')
  }
}

function onUploadClick() {
  fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  try {
    const task = await submitTranscribe(file)
    await taskStore.loadTasks()
    router.push({ name: 'processing', params: { taskId: task.task_id } })
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    alert(err.response?.data?.detail || '上传失败')
  } finally {
    input.value = ''
  }
}

function openTask(task: Task) {
  taskStore.selectTask(task.task_id)
  if (task.status === 'recording' || task.status === 'paused') {
    router.push({ name: 'recording', params: { taskId: task.task_id } })
  } else if (task.status === 'completed') {
    router.push({ name: 'generating', params: { taskId: task.task_id } })
  } else {
    router.push({ name: 'processing', params: { taskId: task.task_id } })
  }
}

function formatDate(task: Task): string {
  const d = task.meeting_date || task.created_at?.slice(0, 10) || ''
  if (!d) return ''
  const date = new Date(d + 'T00:00:00')
  return date.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
}

function formatDuration(sec: number | null): string {
  if (!sec) return '未知时长'
  const m = Math.round(sec / 60)
  return m < 60 ? `${m}分钟` : `${Math.floor(m / 60)}小时${m % 60}分`
}

const statusLabels: Record<string, string> = {
  recording: '录音中',
  paused: '已暂停',
  pending: '等待处理',
  transcribing: '转写中',
  summarizing: '总结中',
  awaiting_mapping: '等待确认',
  failed: '处理失败',
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
