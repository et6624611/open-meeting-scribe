<template>
  <div class="lib-page" ref="libPageRef" :class="widthClass">
    <!-- 整合标题区与搜索框 -->
    <div class="lib-header-bar">
      <div class="lib-title-group">
        <h1>{{ t('library.title') }}</h1>
        <span class="lib-count">{{ t('library.count', { count: taskStore.tasks.length }) }}</span>
      </div>
      <div class="lib-search-wrap">
        <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input
          v-model="taskStore.searchQuery"
          class="lib-search-input"
          type="text"
          :placeholder="t('library.search_placeholder')"
        />
      </div>
    </div>

    <!-- Tab 切换：全部 / 已归档 -->
    <div class="lib-tabs">
      <button class="lib-tab" :class="{ active: !taskStore.showArchived }" @click="switchTab(false)">
        {{ t('library.tab_active') }}
        <span class="lib-tab-count">{{ taskStore.activeTasks.length }}</span>
      </button>
      <button class="lib-tab" :class="{ active: taskStore.showArchived }" @click="switchTab(true)">
        {{ t('library.tab_archived') }}
        <span class="lib-tab-count">{{ taskStore.archivedTasks.length }}</span>
      </button>
    </div>

    <!-- 表格容器 -->
    <div v-if="libGroupedTasks.length > 0" class="table-container">
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
          <span>{{ t('library.col_name') }}</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </div>
        <div class="col-header sortable" :class="{ sorted: sortKey === 'status' }" @click="toggleSort('status')">
          <span>{{ t('library.col_status') }}</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </div>
        <div class="col-header sortable" :class="{ sorted: sortKey === 'duration' }" @click="toggleSort('duration')">
          <span>{{ t('library.col_duration') }}</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </div>
        <div class="col-header">{{ t('library.col_speakers') }}</div>
        <div class="col-header sortable" :class="{ sorted: sortKey === 'created_at' }" @click="toggleSort('created_at')">
          <span>{{ t('library.col_time') }}</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </div>
        <div class="col-header"></div>
      </div>

      <!-- 按日期分组的表格内容 -->
      <div class="table-body">
        <template v-for="group in libGroupedTasks" :key="group.label">
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
              <span class="cell-title-text">{{ task.title || task.audio_name || t('common.untitled') }}</span>
            </div>
            <div class="cell-status">
              <span class="status-dot" :class="statusDotClass(task.status)"></span>
              <span>{{ taskStore.getStatusLabel(task.status) }}</span>
            </div>
            <div class="cell-duration">
              <DurationDial v-if="task.audio_duration" :seconds="task.audio_duration" />
              <span v-else class="cell-muted">—</span>
            </div>
            <div class="cell-speakers">
              <template v-if="getSpeakerList(task).length > 0">
                <span
                  v-for="sp in visibleSpeakers(task)"
                  :key="sp.id"
                  class="lib-spk-label"
                  :title="`${sp.name} · ${formatDuration(sp.duration)}`"
                >
                  <span class="lib-spk-name" :style="{ color: sp.color }">{{ sp.name }}</span>
                  <span class="lib-spk-bar"><span class="lib-spk-bar-fill" :style="{ width: sp.pct + '%', background: sp.color }"></span></span>
                </span>
                <span v-if="extraSpeakerCount(task) > 0" class="lib-spk-more">+{{ extraSpeakerCount(task) }}</span>
              </template>
              <span v-else class="cell-muted">—</span>
            </div>
            <div class="cell-time">{{ formatDateTime(task.created_at) }}</div>
            <div class="cell-actions">
              <button class="cell-actions-btn" @click.stop="openTask(task)" :title="t('library.open_title')">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="libGroupedTasks.length === 0 && !taskStore.loading" class="empty-state">
      {{ taskStore.searchQuery ? t('library.empty_search') : (taskStore.showArchived ? t('library.empty_archived') : t('library.empty')) }}
    </div>

    <!-- 批量操作栏 -->
    <div class="batch-bar" :class="{ visible: selectedIds.size > 0 }">
      <span class="batch-count">{{ t('library.batch_count', { count: selectedIds.size }) }}</span>
      <div class="batch-spacer"></div>
      <button class="batch-btn" @click="batchExport">{{ t('library.batch_export') }}</button>
      <button v-if="!taskStore.showArchived" class="batch-btn" @click="batchArchive">{{ t('library.batch_archive') }}</button>
      <button v-else class="batch-btn" @click="batchUnarchive">{{ t('library.batch_unarchive') }}</button>
      <button class="batch-btn danger" @click="batchDelete">{{ t('library.batch_delete') }}</button>
      <button class="batch-close" @click="clearSelection" :title="t('library.batch_close')">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { usePlayerStore } from '@/stores/player'
import PlayingEq from '@/components/common/PlayingEq.vue'
import DurationDial from '@/components/common/DurationDial.vue'
import { getSpeakerColor } from '@/utils/speakerColors'
import { useContainerSize } from '@/composables/useContainerSize'
import type { Task, TaskStatus } from '@/api/types'

const { t } = useI18n()
const router = useRouter()
const taskStore = useTaskStore()
const player = usePlayerStore()

// ─── 宽度档位（统一 composable 驱动）───
const libPageRef = ref<HTMLElement | null>(null)
const { widthClass } = useContainerSize(libPageRef)

// ─── 选择状态 ───
const selectedIds = ref<Set<string>>(new Set())
const lastSelectedId = ref<string | null>(null)

function switchTab(showArchived: boolean) {
  taskStore.showArchived = showArchived
  clearSelection()
}

/** 会议库专用分组：根据 showArchived 切换数据源，复用 store 的分组逻辑 */
const libGroupedTasks = computed(() => {
  const source = taskStore.showArchived ? taskStore.archivedTasks : taskStore.activeTasks
  const q = taskStore.searchQuery.trim().toLowerCase()
  const filtered = q
    ? source.filter(t => {
        const title = (t.title || t.audio_name || '').toLowerCase()
        const summary = (t.summary || '').toLowerCase()
        return title.includes(q) || summary.includes(q)
      })
    : source

  // 复用 store 的分组逻辑（通过临时替换 filteredTasks 的数据源）
  // 这里直接按 meeting_date 分组，与 store 保持一致
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const dayOfWeek = (now.getDay() + 6) % 7
  const thisWeekStart = new Date(today.getTime() - dayOfWeek * 86400000)
  const lastWeekStart = new Date(thisWeekStart.getTime() - 7 * 86400000)
  const thisMonthStart = new Date(now.getFullYear(), now.getMonth(), 1)
  const lastMonthStart = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  const groupOrder = ['今天', '昨天', '本周', '上周', '本月', '上个月', '更早']
  const groups = new Map<string, { label: string; tasks: Task[]; isToday: boolean; sortKey: number }>()

  for (const task of filtered) {
    const dateStr = task.meeting_date || task.created_at?.slice(0, 10) || 'unknown'
    const taskDate = new Date(dateStr + 'T00:00:00')
    const taskDay = new Date(taskDate.getFullYear(), taskDate.getMonth(), taskDate.getDate())
    const ts = taskDay.getTime()
    let label: string
    let isToday = false
    if (ts === today.getTime()) { label = '今天'; isToday = true }
    else if (ts === yesterday.getTime()) { label = '昨天' }
    else if (ts >= thisWeekStart.getTime()) { label = '本周' }
    else if (ts >= lastWeekStart.getTime()) { label = '上周' }
    else if (ts >= thisMonthStart.getTime()) { label = '本月' }
    else if (ts >= lastMonthStart.getTime()) { label = '上个月' }
    else { label = '更早' }
    if (!groups.has(label)) {
      groups.set(label, { label, tasks: [], isToday, sortKey: groupOrder.indexOf(label) })
    }
    groups.get(label)!.tasks.push(task)
  }
  for (const group of groups.values()) {
    group.tasks.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
  }
  return Array.from(groups.values()).filter(g => g.tasks.length > 0).sort((a, b) => a.sortKey - b.sortKey)
})

// 当前分组内所有可见的 task id 列表（用于 Shift 范围选择）
const allVisibleIds = computed(() => {
  const ids: string[] = []
  for (const group of libGroupedTasks.value) {
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
  alert(t('library.export_todo', { count: selectedIds.value.size }))
}

function batchArchive() {
  const ids = Array.from(selectedIds.value)
  if (!ids.length) return
  for (const id of ids) {
    taskStore.archiveTask(id).catch(e => console.error(`archive ${id} failed:`, e))
  }
  clearSelection()
}

async function batchUnarchive() {
  const ids = Array.from(selectedIds.value)
  if (!ids.length) return
  for (const id of ids) {
    taskStore.unarchiveTask(id).catch(e => console.error(`unarchive ${id} failed:`, e))
  }
  clearSelection()
}

async function batchDelete() {
  const count = selectedIds.value.size
  if (!confirm(t('library.confirm_delete', { count }))) return

  for (const id of selectedIds.value) {
    try {
      await taskStore.removeTask(id)
    } catch (e) {
      console.error(`delete meeting ${id} failed:`, e)
    }
  }
  clearSelection()
}

// ─── 导航 ───
function openTask(task: Task) {
  taskStore.selectTask(task.task_id)
  // 录音中（含暂停）任务进入录音页，其余进入纪要页（中间状态由 GeneratingView 内联处理）
  if (task.status === 'recording' || task.status === 'paused') {
    router.push({ name: 'recording', params: { taskId: task.task_id } })
  } else {
    router.push({ name: 'generating', params: { taskId: task.task_id } })
  }
}

// ─── 格式化 ───
function statusDotClass(status: TaskStatus): string {
  if (status === 'completed') return 'is-done'
  if (status === 'failed') return 'is-failed'
  if (status === 'paused') return 'is-paused'
  if (['recording', 'processing', 'transcribing', 'summarizing'].includes(status)) return 'is-processing'
  return 'is-pending'
}

function formatDuration(sec: number | null): string {
  if (!sec) return '—'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  if (m < 60) return `${m}:${String(s).padStart(2, '0')}`
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${mo}-${day} ${h}:${m}`
}

/** 说话人列最多展示条数：超出以 +N 折叠，保证 ≤2 行不超出 52px 行高 */
const SPK_MAX_SHOWN = 4

function visibleSpeakers(task: Task): SpeakerInfo[] {
  const list = getSpeakerList(task)
  return list.length > SPK_MAX_SHOWN ? list.slice(0, SPK_MAX_SHOWN - 1) : list
}

function extraSpeakerCount(task: Task): number {
  const n = getSpeakerList(task).length
  return n > SPK_MAX_SHOWN ? n - (SPK_MAX_SHOWN - 1) : 0
}

/** 从 task 中提取说话人列表（含颜色、名称、时长、占比） */
interface SpeakerInfo {
  id: string
  name: string
  color: string
  duration: number
  pct: number
}

function getSpeakerList(task: Task): SpeakerInfo[] {
  const mapping = task.speaker_mapping
  if (!mapping || Object.keys(mapping).length === 0) return []

  // 从 dialogue 计算每位说话人的时长与总时长
  const durMap: Record<string, number> = {}
  let total = 0
  if (task.dialogue) {
    for (const line of task.dialogue) {
      const sid = String(line.speaker_id)
      for (const s of line.sentences) {
        const d = s.end_time - s.begin_time
        durMap[sid] = (durMap[sid] || 0) + d
        total += d
      }
    }
  }

  return Object.entries(mapping)
    .filter(([, name]) => name) // 过滤空名称
    .map(([id, name]) => {
      const dur = durMap[id] || 0
      return {
        id,
        name,
        color: getSpeakerColor(id),
        duration: dur,
        pct: total > 0 ? Math.round((dur / total) * 100) : 0,
      }
    })
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

/* ─── Tab 切换 ─── */
.lib-tabs {
  display: flex;
  gap: var(--s-1);
  margin-bottom: var(--s-4);
}

.lib-tab {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) var(--s-4);
  border: none;
  border-radius: var(--radius);
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.lib-tab:hover {
  background: var(--surface-2);
  color: var(--fg);
}

.lib-tab.active {
  background: var(--surface);
  color: var(--fg);
  font-weight: 600;
  box-shadow: 0 1px 3px color-mix(in oklch, var(--fg) 8%, transparent);
}

.lib-tab-count {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--surface-2);
  color: var(--subtle);
  line-height: 1.4;
}

.lib-tab.active .lib-tab-count {
  background: var(--accent-soft);
  color: var(--accent);
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
  grid-template-columns: 40px minmax(180px, 1fr) 110px 100px 140px 140px 40px;
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
  grid-template-columns: 40px minmax(180px, 1fr) 110px 100px 140px 140px 40px;
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
.cell-duration, .cell-speakers, .cell-time {
  font-size: 13px; color: var(--muted);
  display: flex; align-items: center; gap: 4px;
}
.cell-muted { color: var(--subtle); }

/* 说话人列：彩色名称 + 占比横条，参照 .gen-spk-label 视觉模式 */
.cell-speakers {
  flex-wrap: wrap;
  gap: 4px 10px;
  align-content: center;
}
.lib-spk-label {
  display: flex; flex-direction: column; align-items: flex-start; gap: 3px;
  white-space: nowrap;
}
.lib-spk-name {
  font-size: var(--fs-12); font-weight: 500;
  max-width: 60px; overflow: hidden; text-overflow: ellipsis;
}
.lib-spk-bar {
  display: block; width: 44px; height: 3px; border-radius: 2px;
  background: var(--border); overflow: hidden;
}
.lib-spk-bar-fill {
  display: block; height: 100%; border-radius: 2px;
}
.lib-spk-more {
  align-self: center;
  font-size: 11px; color: var(--subtle);
  font-family: var(--font-mono);
}
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

/* ─── 响应式：视口级 @media 渐进隐藏次要列 ─── */

/* ≤1000px：隐藏说话人列 */
@media (max-width: 1000px) {
  .table-head, .table-row {
    grid-template-columns: 40px minmax(160px, 1fr) 110px 100px 140px 40px;
  }
  .table-head .col-header:nth-child(5),
  .table-row .cell-speakers { display: none; }
  .lib-search-wrap { max-width: 380px; }
}

/* ≤768px：标题区与搜索框纵向排列 + 隐藏时长列 */
@media (max-width: 768px) {
  .lib-header-bar {
    flex-direction: column;
    align-items: stretch;
    gap: var(--s-3);
  }
  .lib-title-group { justify-content: space-between; }
  .lib-search-wrap { max-width: 100%; }
  .table-head, .table-row {
    grid-template-columns: 40px minmax(140px, 1fr) 110px 130px 40px;
  }
  .table-head .col-header:nth-child(4),
  .table-row .cell-duration { display: none; }
}

/* ≤600px：隐藏时间列，仅保留 复选框 + 标题 + 状态 + 操作 */
@media (max-width: 600px) {
  .table-head, .table-row {
    grid-template-columns: 36px minmax(120px, 1fr) 110px 36px;
  }
  .table-head .col-header:nth-child(6),
  .table-row .cell-time { display: none; }
}

/* ─── 组件级宽度档位（ResizeObserver 驱动） ─── */

/* is-compact (≤860px)：状态列文字隐藏，仅保留状态圆点 */
.lib-page.is-compact .cell-status span:not(.status-dot) {
  display: none;
}
.lib-page.is-compact .cell-status {
  justify-content: center;
}

/* is-narrow (≤640px)：在视口隐藏说话人基础上，进一步收紧间距 */
.lib-page.is-narrow .table-head,
.lib-page.is-narrow .table-row {
  padding: 0 var(--s-2);
}

/* is-xnarrow (≤480px)：隐藏状态文字 + 缩短行高 */
.lib-page.is-xnarrow .table-row {
  height: 44px;
}
.lib-page.is-xnarrow .cell-title {
  font-size: 13px;
}
</style>
