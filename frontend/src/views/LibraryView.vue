<template>
  <div>
    <div class="lib-header-row">
      <h1>全部会议</h1>
      <span class="lib-count">{{ taskStore.tasks.length }} 个会议</span>
    </div>

    <!-- 搜索栏 -->
    <div class="lib-search">
      <input
        v-model="taskStore.searchQuery"
        class="lib-search-input"
        type="text"
        placeholder="搜索会议标题或内容…"
      />
    </div>

    <!-- 按日期分组列表 -->
    <div v-for="group in taskStore.groupedTasks" :key="group.label" class="lib-group">
      <div class="lib-group-label">{{ group.label }}</div>
      <div class="lib-list">
        <div
          v-for="task in group.tasks"
          :key="task.task_id"
          class="lib-item"
          @click="openTask(task)"
        >
          <div class="lib-item-main">
            <div class="lib-item-title">{{ task.title || task.audio_name || '未命名' }}</div>
            <div class="lib-item-meta">
              <span class="lib-status-dot" :class="statusDotClass(task.status)"></span>
              <span>{{ taskStore.getStatusLabel(task.status) }}</span>
              <span class="sep">·</span>
              <span>{{ formatDuration(task.audio_duration) }}</span>
              <span v-if="task.speaker_count" class="sep">·</span>
              <span v-if="task.speaker_count">{{ task.speaker_count }} 位说话人</span>
            </div>
          </div>
          <div class="lib-item-arrow">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="taskStore.groupedTasks.length === 0 && !taskStore.loading" class="empty-state">
      {{ taskStore.searchQuery ? '没有匹配的会议' : '暂无会议记录' }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import type { Task, TaskStatus } from '@/api/types'

const router = useRouter()
const taskStore = useTaskStore()

function openTask(task: Task) {
  taskStore.selectTask(task.task_id)
  if (task.status === 'completed') {
    router.push({ name: 'generating', params: { taskId: task.task_id } })
  } else if (task.status === 'recording') {
    router.push({ name: 'recording', params: { taskId: task.task_id } })
  } else {
    router.push({ name: 'processing', params: { taskId: task.task_id } })
  }
}

function statusDotClass(status: TaskStatus): string {
  if (status === 'completed') return 'is-done'
  if (status === 'failed') return 'is-failed'
  if (['recording', 'transcribing', 'summarizing'].includes(status)) return 'is-processing'
  return 'is-pending'
}

function formatDuration(sec: number | null): string {
  if (!sec) return '未知时长'
  const m = Math.round(sec / 60)
  return m < 60 ? `${m}分钟` : `${Math.floor(m / 60)}h${m % 60}m`
}
</script>

<style scoped>
.lib-header-row { display: flex; align-items: baseline; gap: var(--s-3); margin-bottom: var(--s-4); }
.lib-header-row h1 { font-size: 24px; font-weight: 600; margin: 0; }
.lib-count { font-size: 13px; color: var(--subtle); }

.lib-search { margin-bottom: var(--s-6); }
.lib-search-input {
  width: 100%; max-width: 400px; padding: 10px var(--s-4);
  border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--surface); color: var(--fg); font-size: 14px;
  outline: none; transition: border-color 0.15s;
}
.lib-search-input:focus { border-color: var(--accent); }

.lib-group { margin-bottom: var(--s-6); }
.lib-group-label { font-size: 12px; font-weight: 600; color: var(--subtle); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: var(--s-2); }
.lib-list { display: flex; flex-direction: column; gap: var(--s-1); }
.lib-item {
  display: flex; align-items: center; gap: var(--s-3);
  padding: var(--s-3) var(--s-4); border-radius: var(--radius); border: 1px solid var(--border);
  background: var(--surface); cursor: pointer; transition: all 0.15s;
}
.lib-item:hover { border-color: var(--border-strong); background: var(--surface-2); }
.lib-item-main { flex: 1; min-width: 0; }
.lib-item-title { font-size: 14px; font-weight: 500; color: var(--fg); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lib-item-meta { font-size: 12px; color: var(--subtle); margin-top: var(--s-1); display: flex; align-items: center; gap: 6px; }
.lib-item-meta .sep { opacity: 0.4; }
.lib-status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.lib-status-dot.is-done { background: var(--ok); }
.lib-status-dot.is-failed { background: var(--rec); }
.lib-status-dot.is-processing { background: var(--accent); animation: blink 1.2s ease-in-out infinite; }
.lib-status-dot.is-pending { background: var(--warn); }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.lib-item-arrow { color: var(--subtle); flex-shrink: 0; }

.empty-state { text-align: center; padding: var(--s-9) var(--s-7); color: var(--muted); font-size: 13px; }

@media (max-width: 920px) {
  .lib-search-input { max-width: 100%; }
  .empty-state { padding: var(--s-7) var(--s-4); }
}
</style>
