<template>
  <div class="start-page" id="startPage">
    <div class="start-page-bg">
      <svg class="start-page-svg" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice">
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-1" d="M 80 180 C 200 160, 280 280, 380 260" style="--path-len: 400" stroke-dasharray="400" />
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-2" d="M 380 260 C 480 240, 520 380, 620 350" style="--path-len: 380" stroke-dasharray="380" />
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-3" d="M 620 350 C 720 320, 780 200, 900 220" style="--path-len: 420" stroke-dasharray="420" />
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-4" d="M 150 550 C 280 520, 350 620, 480 580" style="--path-len: 440" stroke-dasharray="440" />
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-5" d="M 480 580 C 600 540, 680 650, 820 600" style="--path-len: 460" stroke-dasharray="460" />
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-6" d="M 380 260 C 420 380, 440 480, 480 580" style="--path-len: 380" stroke-dasharray="380" />
        <path class="ctx-line ctx-line-solid ctx-draw ctx-draw-7" d="M 620 350 C 660 440, 740 520, 820 600" style="--path-len: 400" stroke-dasharray="400" />
        <path class="ctx-line ctx-line-dashed ctx-flow" d="M 900 220 C 960 300, 1020 400, 980 520" stroke-dasharray="5 7" />
        <path class="ctx-line ctx-line-dashed ctx-flow" d="M 80 180 C 120 300, 100 440, 150 550" stroke-dasharray="5 7" />
        <path class="ctx-line ctx-line-dashed ctx-flow" d="M 900 220 C 1000 180, 1080 250, 1100 360" stroke-dasharray="5 7" />
        <circle class="ctx-node ctx-node-anim ctx-node-1" cx="80" cy="180" r="6" />
        <circle class="ctx-node ctx-node-anim ctx-node-2" cx="380" cy="260" r="7" />
        <circle class="ctx-node ctx-node-anim ctx-node-3" cx="620" cy="350" r="6" />
        <circle class="ctx-node ctx-node-anim ctx-node-4" cx="900" cy="220" r="7" />
        <circle class="ctx-node ctx-node-anim ctx-node-5" cx="480" cy="580" r="6" />
        <circle class="ctx-node ctx-node-anim ctx-node-6" cx="820" cy="600" r="7" />
        <circle class="ctx-node-dot ctx-node-anim ctx-node-1" cx="80" cy="180" r="2.5" />
        <circle class="ctx-node-dot ctx-node-anim ctx-node-2" cx="380" cy="260" r="2.5" />
        <circle class="ctx-node-dot ctx-node-anim ctx-node-3" cx="620" cy="350" r="2.5" />
        <circle class="ctx-node-dot ctx-node-anim ctx-node-4" cx="900" cy="220" r="2.5" />
        <circle class="ctx-node-dot ctx-node-anim ctx-node-5" cx="480" cy="580" r="2.5" />
        <circle class="ctx-node-dot ctx-node-anim ctx-node-6" cx="820" cy="600" r="2.5" />
      </svg>
    </div>
    <div class="start-page-content">
      <div class="start-logo">O</div>
      <h2 class="start-title">开始新的会议</h2>
      <p class="start-subtitle">上传音频文件或开始实时录制，AI 将自动完成转写与分析</p>
      <div class="start-actions">
        <button class="start-btn start-btn-primary" type="button" @click="onStartRecord">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M12 2a4 4 0 014 4v6a4 4 0 01-8 0V6a4 4 0 014-4z"/>
            <path d="M19 10v2a7 7 0 01-14 0v-2"/>
            <line x1="12" y1="19" x2="12" y2="22"/>
          </svg>
          麦克风录音
        </button>
        <button class="start-btn start-btn-secondary" type="button" @click="onUploadClick">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          上传音频文件
        </button>
      </div>
    </div>
    <!-- 最近会议 -->
    <div class="start-recent-section" v-if="recentTasks.length > 0">
      <div class="start-divider">最近会议</div>
      <div class="start-recent" id="startRecentList">
        <div class="start-recent-list">
          <button v-for="task in recentTasks" :key="task.task_id" class="start-recent-item" @click="openTask(task)">
            <div class="start-recent-item-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
            </div>
            <div class="start-recent-item-info">
              <div class="start-recent-item-title">{{ task.title || task.audio_name || '未命名' }}</div>
              <div class="start-recent-item-meta">
                <span>{{ formatDate(task) }}</span>
                <span class="sep">·</span>
                <span>{{ formatDuration(task.audio_duration) }}</span>
              </div>
            </div>
          </button>
          <button v-if="taskStore.tasks.length > 5" class="start-recent-more" @click="router.push('/library')">
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
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { useRecorder } from '@/composables/useRecorder'
import { submitTranscribe } from '@/api/tasks'
import type { Task } from '@/api/types'

const router = useRouter()
const taskStore = useTaskStore()
const recorder = useRecorder()

const fileInputRef = ref<HTMLInputElement | null>(null)

/** 最近 5 个已完成会议 */
const recentTasks = computed(() =>
  taskStore.tasks.filter(t => t.status === 'completed').slice(0, 5)
)

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
  router.push({ name: 'generating', params: { taskId: task.task_id } })
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
</script>
