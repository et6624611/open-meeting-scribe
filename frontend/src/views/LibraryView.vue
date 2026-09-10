<template>
  <div class="lib-page">
    <!-- 整合标题区与搜索栏 -->
    <div class="lib-header-bar">
      <div class="lib-title-group">
        <h1>全部会议</h1>
        <span class="lib-count">{{ taskStore.tasks.length }} 个会议</span>
      </div>
      <div class="lib-search-wrap">
        <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input
          v-model="taskStore.searchQuery"
          class="lib-search-input"
          type="text"
          placeholder="搜索会议标题或内容…"
        />
      </div>
    </div>

    <!-- 表格容器 -->
    <div v-if="taskStore.groupedTasks.length > 0" class="table-container">
      <!-- 列标题（仅在第一个分组上方显示一次） -->
      <div class="table-head">
        <div class="cell-checkbox">
          <div
            class="row-checkbox"
            :class="{ checked: isAllSelected, indeterminate: isIndeterminate }"
            @click.stop="toggleSelectAll"
          ></div>
        </div>
        <div class="col-header sortable" :class="{ sorted: sortKey === 'title' }" @click="toggleSort('title')">
          <span>会议名称</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </div>
        <div class="col-header sortable" :class="{ sorted: sortKey === 'status' }" @click="toggleSort('status')">
          <span>状态</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </div>
        <div class="col-header sortable" :class="{ sorted: sortKey === 'duration' }" @click="toggleSort('duration')">
          <span>时长</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </div>
        <div class="col-header">说话人</div>
        <div class="col-header sortable" :class="{ sorted: sortKey === 'created_at' }" @click="toggleSort('created_at')">
          <span>创建时间</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </div>
        <div class="col-header"></div>
      </div>

      <!-- 按日期分组的表格内容 -->
      <div class="table-body">
        <template v-for="group in taskStore.groupedTasks" :key="group.label">
          <div class="table-group-header">{{ group.label }}</div>
          <div
            v-for="task in sortGroupTasks(group.tasks)"
            :key="task.task_id"
            class="table-row"
            :class="{ selected: selectedIds.has(task.task_id), 'is-playing': player.taskId === task.task_id }"
            @click="openTask(task)"
          >
            <div class="cell-checkbox">
              <div
                class="row-checkbox"
                :class="{ checked: selectedIds.has(task.task_id) }"
                @click.stop="toggleSelect(task, $event)"
              ></div>
            </div>
            <div class="cell-title">
              <PlayingEq v-if="player.taskId === task.task_id" :playing="player.playing" />
              <span class="cell-title-text">{{ task.title || task.audio_name || '未命名' }}</span>
            </div>
            <div class="cell-status">
              <span class="status-dot" :class="statusDotClass(task.status)"></span>
              <span>{{ taskStore.getStatusLabel(task.status) }}</span>
            </div>
            <div class="cell-duration">{{ formatDuration(task.audio_duration) }}</div>
            <div class="cell-speakers">{{ task.speaker_count ? task.speaker_count + ' 位' : '—' }}</div>
            <div class="cell-time">{{ formatTime(task.created_at) }}</div>
            <div class="cell-actions">
              <button class="cell-actions-btn" @click.stop="openTask(task)" title="打开">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="taskStore.groupedTasks.length === 0 && !taskStore.loading" class="empty-state">
      {{ taskStore.searchQuery ? '没有匹配的会议' : '暂无会议记录' }}
    </div>

    <!-- 批量操作栏 -->
    <div class="batch-bar" :class="{ visible: selectedIds.size > 0 }">
      <span class="batch-count">已选 {{ selectedIds.size }} 项</span>
      <div class="batch-spacer"></div>
      <button class="batch-btn" @click="batchExport">导出</button>
      <button class="batch-btn" @click="batchArchive">归档</button>
      <button class="batch-btn danger" @click="batchDelete">删除</button>
      <button class="batch-close" @click="clearSelection" title="取消选择">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { usePlayerStore } from '@/stores/player'
import PlayingEq from '@/components/common/PlayingEq.vue'
import type { Task, TaskStatus } from '@/api/types'

const router = useRouter()
const taskStore = useTaskStore()
const player = usePlayerStore()

// ─── 选择状态 ───
const selectedIds = ref<Set<string>>(new Set())
const lastSelectedId = ref<string | null>(null)

// 当前分组内所有可见的 task id 列表（用于 Shift 范围选择）
const allVisibleIds = computed(() => {
  const ids: string[] = []
  for (const group of taskStore.groupedTasks) {
    for (const task of group.tasks) {
      ids.push(task.task_id)
    }
  }
  return ids
})

const isAllSelected = computed(() =>
  allVisibleIds.value.length > 0 && selectedIds.value.size === allVisibleIds.value.length,
)

const isIndeterminate = computed(() =>
  selectedIds.value.size > 0 && selectedIds.value.size < allVisibleIds.value.length,
)

function toggleSelect(task: Task, event: MouseEvent) {
  const newSet = new Set(selectedIds.value)

  if (event.shiftKey && lastSelectedId.value) {
    // Shift + 点击：范围选择
    const ids = allVisibleIds.value
    const lastIdx = ids.indexOf(lastSelectedId.value)
    const curIdx = ids.indexOf(task.task_id)
    if (lastIdx >= 0 && curIdx >= 0) {
      const [from, to] = [Math.min(lastIdx, curIdx), Math.max(lastIdx, curIdx)]
      for (let i = from; i <= to; i++) {
        newSet.add(ids[i])
      }
    }
  } else if (newSet.has(task.task_id)) {
    newSet.delete(task.task_id)
  } else {
    newSet.add(task.task_id)
  }

  selectedIds.value = newSet
  lastSelectedId.value = task.task_id
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(allVisibleIds.value)
  }
}

function clearSelection() {
  selectedIds.value = new Set()
  lastSelectedId.value = null
}

// ─── 排序 ───
type SortKey = 'title' | 'status' | 'duration' | 'created_at'
const sortKey = ref<SortKey>('created_at')
const sortAsc = ref(false)

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = true
  }
}

function sortGroupTasks(tasks: Task[]): Task[] {
  const sorted = [...tasks]
  const dir = sortAsc.value ? 1 : -1

  sorted.sort((a, b) => {
    switch (sortKey.value) {
      case 'title': {
        const ta = (a.title || a.audio_name || '').toLowerCase()
        const tb = (b.title || b.audio_name || '').toLowerCase()
        return ta.localeCompare(tb) * dir
      }
      case 'status':
        return a.status.localeCompare(b.status) * dir
      case 'duration':
        return ((a.audio_duration || 0) - (b.audio_duration || 0)) * dir
      case 'created_at':
        return (a.created_at || '').localeCompare(b.created_at || '') * dir
      default:
        return 0
    }
  })

  return sorted
}

// ─── 批量操作 ───
function batchExport() {
  alert(`导出 ${selectedIds.value.size} 个会议（功能待实现）`)
}

function batchArchive() {
  alert(`归档 ${selectedIds.value.size} 个会议（功能待实现）`)
}

async function batchDelete() {
  const count = selectedIds.value.size
  if (!confirm(`确定删除 ${count} 个会议？此操作不可撤销。`)) return

  for (const id of selectedIds.value) {
    try {
      await taskStore.removeTask(id)
    } catch (e) {
      console.error(`删除会议 ${id} 失败:`, e)
    }
  }
  clearSelection()
}

// ─── 导航 ───
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

// ─── 格式化 ───
function statusDotClass(status: TaskStatus): string {
  if (status === 'completed') return 'is-done'
  if (status === 'failed') return 'is-failed'
  if (status === 'paused') return 'is-paused'
  if (['recording', 'transcribing', 'summarizing'].includes(status)) return 'is-processing'
  return 'is-pending'
}

function formatDuration(sec: number | null): string {
  if (!sec) return '—'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  if (m < 60) return `${m}:${String(s).padStart(2, '0')}`
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
}

function formatTime(dateStr: string | null): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}
</script>

<style scoped>
.lib-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* ─── 整合标题栏与搜索框 ─── */
.lib-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
  margin-bottom: var(--s-5);
}

.lib-title-group {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
  flex-shrink: 0;
}

.lib-title-group h1 {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.01em;
}

.lib-count {
  font-size: 13px;
  color: var(--subtle);
}

.lib-search-wrap {
  position: relative;
  flex: 1;
  max-width: 480px;
}
.lib-search-wrap .search-icon {
  position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
  color: var(--subtle); pointer-events: none;
}
.lib-search-input {
  width: 100%; padding: 10px var(--s-4); padding-left: 38px;
  border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--surface); font-size: 14px;
  outline: none; transition: border-color 0.15s, box-shadow 0.15s;
}
.lib-search-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in oklch, var(--accent) 12%, transparent);
}

/* ─── 表格容器 ─── */
.table-container {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 列标题 */
.table-head {
  display: grid;
  grid-template-columns: 40px 1fr 120px 100px 100px 120px 40px;
  align-items: center;
  padding: 0 var(--s-4);
  height: 40px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  user-select: none;
  flex-shrink: 0;
}
.col-header {
  display: flex;
  align-items: center;
  gap: var(--s-1);
}
.col-header.sortable { cursor: pointer; }
.col-header.sortable:hover { color: var(--fg); }
.col-header .sort-icon { opacity: 0.4; transition: opacity 0.15s; }
.col-header.sorted .sort-icon { opacity: 1; color: var(--accent); }

/* 复选框 */
.row-checkbox {
  width: 16px; height: 16px;
  border: 1.5px solid var(--border-strong);
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
  background: var(--surface); flex-shrink: 0;
}
.row-checkbox:hover { border-color: var(--accent); }
.row-checkbox.checked {
  background: var(--accent); border-color: var(--accent);
}
.row-checkbox.checked::after {
  content: ''; width: 8px; height: 5px;
  border-left: 2px solid #fff; border-bottom: 2px solid #fff;
  transform: rotate(-45deg) translateY(-1px);
}
.row-checkbox.indeterminate {
  background: var(--accent); border-color: var(--accent);
}
.row-checkbox.indeterminate::after {
  content: ''; width: 8px; height: 2px;
  background: #fff; border-radius: 1px;
}

/* 表格内容区 */
.table-body { flex: 1; overflow-y: auto; }

.table-group-header {
  padding: var(--s-2) var(--s-4);
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: var(--subtle);
  text-transform: uppercase; letter-spacing: 0.05em;
  position: sticky; top: 0; z-index: 1;
}

.table-row {
  display: grid;
  grid-template-columns: 40px 1fr 120px 100px 100px 120px 40px;
  align-items: center;
  padding: 0 var(--s-4);
  height: 52px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.1s;
}
.table-row:hover { background: var(--surface-2); }
.table-row.selected { background: color-mix(in oklch, var(--accent) 8%, transparent); }
.table-row:last-child { border-bottom: none; }

/* 单元格 */
.cell-checkbox { display: flex; align-items: center; justify-content: center; }
.cell-title {
  display: flex; align-items: center; gap: var(--s-2);
  font-size: 14px; font-weight: 500; color: var(--fg);
  min-width: 0; padding-right: var(--s-3);
}
.cell-title-text {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.table-row.is-playing .cell-title { color: var(--accent); }
.cell-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--muted);
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.status-dot.is-done { background: var(--ok); }
.status-dot.is-failed { background: var(--rec); }
.status-dot.is-processing { background: var(--accent); animation: blink 1.2s ease-in-out infinite; }
.status-dot.is-paused { background: var(--warn); }
.status-dot.is-pending { background: var(--warn); }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.cell-duration, .cell-speakers, .cell-time { font-size: 13px; color: var(--muted); }
.cell-actions {
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.15s;
}
.table-row:hover .cell-actions { opacity: 1; }
.cell-actions-btn {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius); color: var(--subtle); transition: all 0.15s;
}
.cell-actions-btn:hover { background: var(--border); color: var(--fg); }

/* ─── 批量操作栏 ─── */
.batch-bar {
  height: 48px;
  background: var(--fg);
  color: #fff;
  display: flex; align-items: center;
  padding: 0 var(--s-4); gap: var(--s-3);
  flex-shrink: 0;
  transform: translateY(100%);
  transition: transform 0.2s ease;
}
.batch-bar.visible { transform: translateY(0); }
.batch-count { font-size: 13px; font-weight: 500; opacity: 0.8; }
.batch-spacer { flex: 1; }
.batch-btn {
  padding: 6px 14px; border-radius: var(--radius);
  font-size: 13px; font-weight: 500;
  color: #fff; background: rgba(255,255,255,0.12);
  transition: background 0.15s; border: none; cursor: pointer;
}
.batch-btn:hover { background: rgba(255,255,255,0.2); }
.batch-btn.danger { background: rgba(239,68,68,0.2); color: #fca5a5; }
.batch-btn.danger:hover { background: rgba(239,68,68,0.3); }
.batch-close {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius); color: rgba(255,255,255,0.6);
  transition: all 0.15s; border: none; cursor: pointer; background: none;
}
.batch-close:hover { background: rgba(255,255,255,0.1); color: #fff; }

/* ─── 空状态 ─── */
.empty-state { text-align: center; padding: var(--s-9) var(--s-7); color: var(--muted); font-size: 13px; }

/* ─── 响应式 ─── */
@media (max-width: 920px) {
  .table-head, .table-row {
    grid-template-columns: 40px 1fr 100px 80px 40px;
  }
  .table-head .col-header:nth-child(5),
  .table-head .col-header:nth-child(6),
  .table-row .cell-speakers,
  .table-row .cell-time { display: none; }
  .lib-search-wrap { max-width: 360px; }
}

@media (max-width: 768px) {
  .lib-header-bar {
    flex-direction: column;
    align-items: stretch;
    gap: var(--s-3);
  }
  .lib-title-group { justify-content: space-between; }
  .lib-search-wrap { max-width: 100%; }
}

@media (max-width: 600px) {
  .table-head, .table-row {
    grid-template-columns: 36px 1fr 80px 36px;
  }
  .table-head .col-header:nth-child(4),
  .table-row .cell-duration { display: none; }
}
</style>
