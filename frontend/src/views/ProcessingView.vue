<template>
  <div>
    <div class="main-head">
      <h1>{{ task ? task.title || task.audio_name : '处理中' }}</h1>
      <p class="sub">{{ statusText }}</p>
    </div>

    <!-- 处理进度（spinner + 日志） -->
    <div class="proc-progress">
      <div class="proc-spinner"></div>
      <div class="proc-log" id="procLog">{{ statusText }}</div>
    </div>

    <!-- 管线进度 -->
    <div class="pipe">
      <div class="pipe-step" :class="stepClass('upload')">
        <div class="ico">✓</div>
        <div class="info">
          <div class="lbl">上传</div>
          <div class="sub">完成</div>
        </div>
      </div>
      <div class="pipe-conn is-done"></div>
      <div class="pipe-step" :class="stepClass('transcribe')">
        <div class="ico">{{ stepIcon('transcribe') }}</div>
        <div class="info">
          <div class="lbl">识别</div>
          <div class="sub">{{ stepSub('transcribe') }}</div>
        </div>
      </div>
      <div class="pipe-conn" :class="{ 'is-done': isStageDone('transcribe') }"></div>
      <div class="pipe-step" :class="stepClass('summary')">
        <div class="ico">{{ stepIcon('summary') }}</div>
        <div class="info">
          <div class="lbl">纪要</div>
          <div class="sub">{{ stepSub('summary') }}</div>
        </div>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-bar">
      <span :style="{ width: progress + '%' }"></span>
    </div>

    <!-- 错误信息 -->
    <div v-if="task?.status === 'failed'" class="error-card">
      <p class="error-title">处理失败</p>
      <p class="error-msg">{{ task?.error || '未知错误' }}</p>
      <div class="error-actions">
        <button class="btn btn-secondary" @click="onRetry">重试</button>
        <button class="btn btn-secondary" @click="router.push('/')">返回首页</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { usePolling } from '@/composables/usePolling'
import { fetchTask, retranscribe } from '@/api/tasks'

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()

const taskId = route.params.taskId as string
const task = computed(() =>
  taskStore.tasks.find(t => t.task_id === taskId) ?? null,
)

const progress = computed(() => task.value?.progress ?? 0)

const statusText = computed(() => {
  if (!task.value) return '加载中…'
  const s = task.value.status
  if (s === 'pending') return '等待处理…'
  if (s === 'transcribing') return '正在识别录音…'
  if (s === 'summarizing') return '正在生成纪要…'
  if (s === 'completed') return '处理完成！'
  if (s === 'failed') return '处理失败'
  return task.value.message || '处理中…'
})

function isStageDone(stage: string): boolean {
  if (!task.value) return false
  const s = task.value.status
  if (stage === 'transcribe') return ['summarizing', 'completed', 'awaiting_mapping'].includes(s)
  if (stage === 'summary') return s === 'completed'
  return false
}

function stepClass(stage: string): string {
  if (!task.value) return ''
  const s = task.value.status
  if (stage === 'upload') return 'is-done'
  if (stage === 'transcribe') {
    if (isStageDone('transcribe')) return 'is-done'
    if (s === 'transcribing') return 'is-active'
  }
  if (stage === 'summary') {
    if (s === 'completed') return 'is-done'
    if (s === 'summarizing') return 'is-active'
  }
  return ''
}

function stepIcon(stage: string): string {
  if (isStageDone(stage)) return '✓'
  if (stepClass(stage) === 'is-active') return '…'
  return String(stage === 'transcribe' ? 2 : 3)
}

function stepSub(stage: string): string {
  if (isStageDone(stage)) return '完成'
  if (stepClass(stage) === 'is-active') return '进行中…'
  return '等待中'
}

// 轮询任务状态
const { start, stop } = usePolling(async () => {
  const updated = await fetchTask(taskId)
  taskStore.patchTaskLocal(taskId, updated)

  if (updated.status === 'completed' || updated.status === 'awaiting_mapping') {
    stop()
    router.push({ name: 'generating', params: { taskId } })
  } else if (updated.status === 'failed') {
    stop()
  }
}, 3000)

onMounted(async () => {
  // 首次加载任务数据
  if (!task.value) {
    try {
      const t = await fetchTask(taskId)
      taskStore.patchTaskLocal(taskId, t)
    } catch { /* ignore */ }
  }

  // 如果已完成或待绑定，直接跳转
  if (task.value?.status === 'completed' || task.value?.status === 'awaiting_mapping') {
    router.push({ name: 'generating', params: { taskId } })
    return
  }

  start()
})

onUnmounted(stop)

async function onRetry() {
  try {
    await retranscribe(taskId)
    await taskStore.loadTasks()
  } catch (e) {
    console.error('重试失败:', e)
  }
}
</script>

<style scoped>
.pipe { margin-bottom: var(--s-6); }
.error-card {
  padding: var(--s-5); border: 1px solid var(--border);
  border-radius: var(--radius-lg); background: var(--surface); margin-top: var(--s-6);
}
.error-title { font-size: 16px; font-weight: 600; color: var(--rec); margin: 0 0 var(--s-2); }
.error-msg { font-size: 13px; color: var(--muted); margin: 0 0 var(--s-4); line-height: 1.6; }
.error-actions { display: flex; gap: var(--s-2); }
</style>
