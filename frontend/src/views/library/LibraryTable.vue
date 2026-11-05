<template>
  <div v-if="groupedTasks.length > 0 && !loadError" class="table-container" role="table" aria-colcount="7">
    <!-- 列标题 -->
    <div class="table-head" role="row">
      <div class="cell-checkbox" role="columnheader">
        <button
          type="button" class="row-checkbox" role="checkbox"
          :class="{ checked: isAllSelected, indeterminate: isIndeterminate }"
          :aria-checked="isAllSelected ? 'true' : isIndeterminate ? 'mixed' : 'false'"
          :aria-label="t('library.select_all')"
          @click.stop="toggleSelectAll()"
        ></button>
      </div>
      <div class="col-header sortable" role="columnheader" :aria-sort="sortAria('title')" :class="{ sorted: sortKey === 'title' }">
        <button type="button" class="col-header-btn" :aria-label="t('library.sort_by', { col: t('library.col_name') })" @click="$emit('toggleSort', 'title')">
          <span>{{ t('library.col_name') }}</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </button>
      </div>
      <div class="col-header sortable" role="columnheader" :aria-sort="sortAria('status')" :class="{ sorted: sortKey === 'status' }">
        <button type="button" class="col-header-btn" :aria-label="t('library.sort_by', { col: t('library.col_status') })" @click="$emit('toggleSort', 'status')">
          <span>{{ t('library.col_status') }}</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </button>
      </div>
      <div class="col-header sortable" role="columnheader" :aria-sort="sortAria('duration')" :class="{ sorted: sortKey === 'duration' }">
        <button type="button" class="col-header-btn" :aria-label="t('library.sort_by', { col: t('library.col_duration') })" @click="$emit('toggleSort', 'duration')">
          <span>{{ t('library.col_duration') }}</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </button>
      </div>
      <div class="col-header" role="columnheader">{{ t('library.col_speakers') }}</div>
      <div class="col-header sortable" role="columnheader" :aria-sort="sortAria('created_at')" :class="{ sorted: sortKey === 'created_at' }">
        <button type="button" class="col-header-btn" :aria-label="t('library.sort_by', { col: t('library.col_time') })" @click="$emit('toggleSort', 'created_at')">
          <span>{{ t('library.col_time') }}</span>
          <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
        </button>
      </div>
      <div class="col-header" role="columnheader"></div>
    </div>

    <!-- 按日期分组的表格内容 -->
    <div class="table-body" role="rowgroup">
      <template v-for="group in groupedTasks" :key="group.label">
        <div class="table-group-header" role="row"><span role="cell" :aria-colspan="7">{{ group.label }}</span></div>
        <div
          v-for="task in sortGroupTasks(group.tasks)"
          :key="task.task_id"
          class="table-row" role="row" tabindex="0"
          :aria-label="task.title || task.audio_name || t('common.untitled')"
          :class="{ selected: selectedIds.has(task.task_id), 'is-playing': playingTaskId === task.task_id }"
          @click="openTask(task)"
          @keydown.enter.prevent="openTask(task)"
        >
          <div class="cell-checkbox" role="cell">
            <button
              type="button" class="row-checkbox" role="checkbox"
              :class="{ checked: selectedIds.has(task.task_id) }"
              :aria-checked="selectedIds.has(task.task_id)"
              :aria-label="t('library.select_row', { name: task.title || task.audio_name || t('common.untitled') })"
              @click.stop="toggleSelect(task, $event)"
            ></button>
          </div>
          <div class="cell-title" role="cell">
            <PlayingEq v-if="playingTaskId === task.task_id" :playing="playing" />
            <span class="cell-title-text" v-html="highlightLibTitle(task)"></span>
            <span v-if="isContentOnlyMatch(task)" class="lib-src-badge" :title="t('library.source_content_hint')">{{ t('library.source_content') }}</span>
          </div>
          <div class="cell-status" role="cell">
            <span class="status-dot" :class="statusDotClass(task.status)"></span>
            <span>{{ getStatusLabel(task.status) }}</span>
          </div>
          <div class="cell-duration" role="cell">
            <DurationDial v-if="task.audio_duration" :seconds="task.audio_duration" />
            <span v-else class="cell-muted">—</span>
          </div>
          <div class="cell-speakers" role="cell">
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
          <div class="cell-time" role="cell">{{ formatDateTime(task.created_at) }}</div>
          <div class="cell-actions" role="cell">
            <button class="cell-actions-btn" @click.stop="openTask(task)" :title="t('library.open_title')">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PlayingEq from '@/components/common/PlayingEq.vue'
import DurationDial from '@/components/common/DurationDial.vue'
import type { SortKey } from '@/composables/useLibraryFilters'
import type { SpeakerInfo } from '@/composables/useLibrarySelection'
import type { Task, TaskStatus } from '@/api/types'

const { t } = useI18n()

defineProps<{
  groupedTasks: Array<{ key: string; label: string; tasks: Task[]; isToday: boolean; sortKey: number }>
  loadError: string | null
  selectedIds: Set<string>
  isAllSelected: boolean
  isIndeterminate: boolean
  playingTaskId: string | null
  playing: boolean
  sortKey: SortKey
  sortAria: (key: SortKey) => 'ascending' | 'descending' | 'none'
  sortGroupTasks: (tasks: Task[]) => Task[]
  toggleSelect: (task: Task, event: MouseEvent) => void
  toggleSelectAll: () => void
  openTask: (task: Task) => void
  statusDotClass: (status: TaskStatus) => string
  highlightLibTitle: (task: Task) => string
  formatDuration: (sec: number | null) => string
  formatDateTime: (dateStr: string | null) => string
  visibleSpeakers: (task: Task) => SpeakerInfo[]
  extraSpeakerCount: (task: Task) => number
  getSpeakerList: (task: Task) => SpeakerInfo[]
  isContentOnlyMatch: (task: Task) => boolean
  getStatusLabel: (status: TaskStatus) => string
}>()

defineEmits<{
  (e: 'toggleSort', key: SortKey): void
}>()
</script>

<style scoped>
.table-container {
  flex: 1; background: transparent; overflow: hidden;
  display: flex; flex-direction: column; min-height: 0;
}
.table-head {
  display: grid;
  grid-template-columns: 40px minmax(180px, 1fr) 110px 100px 140px 140px 40px;
  align-items: center; padding: 0 var(--s-4); height: 40px;
  background: transparent; border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: var(--muted);
  user-select: none; flex-shrink: 0;
}
.col-header { display: flex; align-items: center; gap: var(--s-1); }
.col-header.sortable { cursor: pointer; }
.col-header.sortable:hover { color: var(--fg); }
.col-header-btn { display: flex; align-items: center; gap: var(--s-1); font: inherit; color: inherit; background: transparent; border: 0; padding: 0; cursor: pointer; width: 100%; text-align: left; }
.col-header .sort-icon { opacity: 0.4; transition: opacity 0.15s; }
.col-header.sorted .sort-icon { opacity: 1; color: var(--accent); }

/* checkbox */
.row-checkbox { width: 16px; height: 16px; border: 1.5px solid var(--border-strong); border-radius: 4px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.15s; background: var(--surface); flex-shrink: 0; position: relative; }
.row-checkbox::before { content: ''; position: absolute; inset: -12px; }
.row-checkbox:hover { border-color: var(--accent); }
.row-checkbox.checked { background: var(--accent); border-color: var(--accent); }
.row-checkbox.checked::after { content: ''; width: 8px; height: 5px; border-left: 2px solid #fff; border-bottom: 2px solid #fff; transform: rotate(-45deg) translateY(-1px); }
.row-checkbox.indeterminate { background: var(--accent); border-color: var(--accent); }
.row-checkbox.indeterminate::after { content: ''; width: 8px; height: 2px; background: #fff; border-radius: 1px; }

.table-body { flex: 1; overflow-y: auto; }
.table-group-header { padding: var(--s-2) var(--s-4); background: var(--bg); border-bottom: 1px solid var(--border); font-size: 12px; font-weight: 600; color: var(--subtle); text-transform: uppercase; letter-spacing: 0.05em; position: sticky; top: 0; z-index: 1; }

.table-row {
  display: grid;
  grid-template-columns: 40px minmax(180px, 1fr) 110px 100px 140px 140px 40px;
  align-items: center; padding: 0 var(--s-4); height: 52px;
  border-bottom: none; cursor: pointer; transition: background 0.1s;
}
.table-row:hover { background: var(--surface-2); }
.table-row.selected { background: color-mix(in oklch, var(--accent) 8%, transparent); }

.cell-checkbox { display: flex; align-items: center; justify-content: center; cursor: pointer; }
.cell-title { display: flex; align-items: center; gap: var(--s-2); font-size: 14px; font-weight: 500; color: var(--fg); min-width: 0; padding-right: var(--s-3); }
.cell-title-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lib-src-badge { flex-shrink: 0; font-size: 11px; line-height: 1.4; padding: 1px 6px; border-radius: var(--radius-pill); background: var(--surface-2); color: var(--subtle); border: 1px solid var(--border); white-space: nowrap; }
.table-row.is-playing .cell-title { color: var(--accent); }
.cell-status { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--muted); }
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.status-dot.is-done { background: var(--ok); }
.status-dot.is-failed { background: var(--error); }
.status-dot.is-processing { background: var(--accent); animation: blink 1.2s ease-in-out infinite; }
.status-dot.is-paused { background: var(--warn); }
.status-dot.is-pending { background: var(--subtle); }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.cell-duration, .cell-speakers, .cell-time { font-size: 13px; color: var(--muted); display: flex; align-items: center; gap: 4px; }
.cell-muted { color: var(--subtle); }
.cell-speakers { flex-wrap: wrap; gap: 4px 10px; align-content: center; }
.lib-spk-label { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; white-space: nowrap; }
.lib-spk-name { font-size: var(--fs-12); font-weight: 500; max-width: 60px; overflow: hidden; text-overflow: ellipsis; }
.lib-spk-bar { display: block; width: 44px; height: 3px; border-radius: 2px; background: var(--border); overflow: hidden; }
.lib-spk-bar-fill { display: block; height: 100%; border-radius: 2px; }
.lib-spk-more { align-self: center; font-size: 11px; color: var(--subtle); font-family: var(--font-mono); }
.cell-actions { display: flex; align-items: center; justify-content: center; }
.cell-actions-btn { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius); color: var(--subtle); transition: all 0.15s; }
.cell-actions-btn:hover { background: var(--border); color: var(--fg); }

/* responsive — these override the grid tracks */
@media (max-width: 1000px) {
  .table-head, .table-row { grid-template-columns: 40px minmax(160px, 1fr) 110px 100px 140px 40px; }
  .table-head .col-header:nth-child(5), .table-row .cell-speakers { display: none; }
}
@media (max-width: 768px) {
  .table-head, .table-row { grid-template-columns: 40px minmax(140px, 1fr) 110px 130px 40px; }
  .table-head .col-header:nth-child(4), .table-row .cell-duration { display: none; }
}
@media (max-width: 600px) {
  .table-head, .table-row { grid-template-columns: 36px minmax(120px, 1fr) 110px 36px; }
  .table-head .col-header:nth-child(6), .table-row .cell-time { display: none; }
}
</style>
