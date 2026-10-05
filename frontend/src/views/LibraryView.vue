<template>
  <div class="lib-page" ref="libPageRef" :class="widthClass">
    <!-- 整合标题区与搜索框 / Integrated title bar and search box -->
    <div class="lib-header-bar">
      <div class="lib-title-group">
        <h1>{{ t('library.title') }}</h1>
        <span v-if="hasLibFilter" class="lib-count">{{ t('library.count_matched', { matched: libCountDisplay, total: libTabTotal }) }}</span>
        <span v-else class="lib-count">{{ t('library.count', { count: libCountDisplay }) }}</span>
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

    <!-- Tab 切换：全部 / 已归档 / Tab switch: Active / Archived -->
    <div class="lib-tabs">
      <button class="lib-tab" :class="{ active: !taskStore.showArchived }" @click="switchTab(false)">
        {{ t('library.tab_active') }}
        <span class="lib-tab-count">{{ activeTabCount }}</span>
      </button>
      <button class="lib-tab" :class="{ active: taskStore.showArchived }" @click="switchTab(true)">
        {{ t('library.tab_archived') }}
        <span class="lib-tab-count">{{ archivedTabCount }}</span>
      </button>
    </div>

    <!-- 筛选工具栏：日期范围 + 说话人 / Filter toolbar: date range + speaker -->
    <div class="lib-filter-bar" :class="{ 'is-active': hasActiveFilter }">
      <div class="lib-filter-group lib-date-group">
        <label class="lib-filter-label">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
        </label>
        <input type="date" v-model="dateFrom" class="lib-date-input" :title="t('library.filter_date_from')" />
        <span class="lib-date-sep">–</span>
        <input type="date" v-model="dateTo" class="lib-date-input" :title="t('library.filter_date_to')" />
        <span class="lib-filter-divider"></span>
        <button class="lib-filter-chip" @click="setQuickDateRange(7)">{{ t('library.filter_week') }}</button>
        <button class="lib-filter-chip" @click="setQuickDateRange(30)">{{ t('library.filter_30days') }}</button>
      </div>
      <div class="lib-filter-group">
        <label class="lib-filter-label">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        </label>
        <button
          ref="speakerTriggerRef"
          type="button"
          class="lib-speaker-select lib-speaker-trigger"
          v-bind="speakerTriggerAttrs"
          @click="toggleSpeakerMenu"
        >
          <span class="lib-speaker-trigger-text" :class="{ 'is-placeholder': !filterSpeakerId }">
            {{ speakerTriggerLabel }}
          </span>
          <svg class="lib-speaker-caret" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <Teleport to="body">
          <div
            v-if="speakerMenuVisible"
            ref="speakerMenuRef"
            v-bind="speakerMenuAttrs"
            class="pop-menu lib-speaker-menu"
          >
            <div class="lib-speaker-search">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input
                ref="speakerSearchRef"
                v-model="speakerSearchQuery"
                type="text"
                class="lib-speaker-search-input"
                :placeholder="t('library.filter_speaker_search')"
              />
            </div>
            <div class="lib-speaker-list">
              <button
                type="button"
                role="menuitem"
                class="lib-speaker-item"
                :class="{ 'is-active': filterSpeakerId === '' }"
                @click="selectSpeaker('')"
              >
                {{ t('library.filter_speaker_all') }}
              </button>
              <button
                v-for="name in filteredSpeakerNames"
                :key="name"
                type="button"
                role="menuitem"
                class="lib-speaker-item"
                :class="{ 'is-active': filterSpeakerId === name }"
                @click="selectSpeaker(name)"
              >
                {{ name }}
              </button>
              <button
                v-if="libraryHasUnidentified && unidVisible"
                type="button"
                role="menuitem"
                class="lib-speaker-item"
                :class="{ 'is-active': filterSpeakerId === UNID_FILTER }"
                @click="selectSpeaker(UNID_FILTER)"
              >
                {{ t('library.filter_speaker_unidentified') }}
              </button>
              <div v-if="!filteredSpeakerNames.length && !unidVisible" class="lib-speaker-empty">
                {{ t('library.filter_speaker_empty') }}
              </div>
            </div>
          </div>
        </Teleport>
      </div>
      <div v-if="hasActiveFilter" class="lib-filter-actions">
        <button class="lib-filter-clear" @click="clearAllFilters">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          {{ t('library.filter_clear') }}
        </button>
      </div>
    </div>

    <!-- 表格容器 / Table container -->
    <div v-if="libGroupedTasks.length > 0 && !taskStore.loadError" class="table-container" role="table" aria-colcount="7">
      <!-- 列标题（仅在第一个分组上方显示一次） / Column headers (shown only above first group) -->
      <div class="table-head" role="row">
        <div class="cell-checkbox" role="columnheader">
          <button
            type="button"
            class="row-checkbox"
            role="checkbox"
            :class="{ checked: isAllSelected, indeterminate: isIndeterminate }"
            :aria-checked="isAllSelected ? 'true' : isIndeterminate ? 'mixed' : 'false'"
            :aria-label="t('library.select_all')"
            @click.stop="toggleSelectAll"
          ></button>
        </div>
        <div class="col-header sortable" role="columnheader" :aria-sort="ariaSort('title')" :class="{ sorted: sortKey === 'title' }">
          <button type="button" class="col-header-btn" :aria-label="t('library.sort_by', { col: t('library.col_name') })" @click="toggleSort('title')">
            <span>{{ t('library.col_name') }}</span>
            <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
          </button>
        </div>
        <div class="col-header sortable" role="columnheader" :aria-sort="ariaSort('status')" :class="{ sorted: sortKey === 'status' }">
          <button type="button" class="col-header-btn" :aria-label="t('library.sort_by', { col: t('library.col_status') })" @click="toggleSort('status')">
            <span>{{ t('library.col_status') }}</span>
            <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
          </button>
        </div>
        <div class="col-header sortable" role="columnheader" :aria-sort="ariaSort('duration')" :class="{ sorted: sortKey === 'duration' }">
          <button type="button" class="col-header-btn" :aria-label="t('library.sort_by', { col: t('library.col_duration') })" @click="toggleSort('duration')">
            <span>{{ t('library.col_duration') }}</span>
            <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
          </button>
        </div>
        <div class="col-header" role="columnheader">{{ t('library.col_speakers') }}</div>
        <div class="col-header sortable" role="columnheader" :aria-sort="ariaSort('created_at')" :class="{ sorted: sortKey === 'created_at' }">
          <button type="button" class="col-header-btn" :aria-label="t('library.sort_by', { col: t('library.col_time') })" @click="toggleSort('created_at')">
            <span>{{ t('library.col_time') }}</span>
            <svg class="sort-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 10 12 6 16 10"/><polyline points="8 14 12 18 16 14"/></svg>
          </button>
        </div>
        <div class="col-header" role="columnheader"></div>
      </div>

      <!-- 按日期分组的表格内容 / Table content grouped by date -->
      <div class="table-body" role="rowgroup">
        <template v-for="group in libGroupedTasks" :key="group.label">
          <div class="table-group-header" role="row"><span role="cell" :aria-colspan="7">{{ group.label }}</span></div>
          <div
            v-for="task in sortGroupTasks(group.tasks)"
            :key="task.task_id"
            class="table-row" role="row"
            tabindex="0"
            :aria-label="task.title || task.audio_name || t('common.untitled')"
            :class="{ selected: selectedIds.has(task.task_id), 'is-playing': player.taskId === task.task_id }"
            @click="openTask(task)"
            @keydown.enter.prevent="openTask(task)"
          >
            <div class="cell-checkbox" role="cell">
              <button
                type="button"
                class="row-checkbox"
                role="checkbox"
                :class="{ checked: selectedIds.has(task.task_id) }"
                :aria-checked="selectedIds.has(task.task_id)"
                :aria-label="t('library.select_row', { name: task.title || task.audio_name || t('common.untitled') })"
                @click.stop="toggleSelect(task, $event)"
              ></button>
            </div>
            <div class="cell-title" role="cell">
              <PlayingEq v-if="player.taskId === task.task_id" :playing="player.playing" />
              <span class="cell-title-text" v-html="highlightLibTitle(task)"></span>
              <span v-if="isContentOnlyMatch(task)" class="lib-src-badge" :title="t('library.source_content_hint')">{{ t('library.source_content') }}</span>
            </div>
            <div class="cell-status" role="cell">
              <span class="status-dot" :class="statusDotClass(task.status)"></span>
              <span>{{ taskStore.getStatusLabel(task.status) }}</span>
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

    <!-- 加载失败态（优先于空态：失败 ≠ 没有会议） / Load-failure state, ahead of empty -->
    <div v-if="taskStore.loadError && !taskStore.loading" class="lib-error" role="alert">
      <span class="lib-error-text">{{ taskStore.loadError }}</span>
      <button type="button" class="lib-error-retry" @click="taskStore.loadTasks()">{{ t('common.error.retry') }}</button>
    </div>

    <!-- 空状态 / Empty state -->
    <div v-else-if="libGroupedTasks.length === 0 && !taskStore.loading" class="empty-state">
      {{ taskStore.searchQuery ? t('library.empty_search') : (taskStore.showArchived ? t('library.empty_archived') : t('library.empty')) }}
    </div>

    <!-- 批量操作栏 / Batch action bar -->
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

    <!-- 批量删除确认弹窗 / Batch delete confirm dialog -->
    <ConfirmDialog
      v-model="showBatchDeleteConfirm"
      :title="t('library.confirm_delete_title')"
      :message="t('library.confirm_delete', { count: selectedIds.size })"
      @confirm="onConfirmBatchDelete"
    />

    <!-- 批量导出格式选择弹窗（DEF-QA-R1-02，替换 alert 占位） / Batch export format dialog (replaces alert placeholder) -->
    <Teleport to="body">
      <div v-show="showExportDialog" class="export-overlay" data-vue-overlay :class="{ 'is-open': showExportDialog }" @click.self="showExportDialog = false">
        <div ref="exportDialogRef" class="export-dialog" role="dialog" aria-modal="true" aria-labelledby="libExportTitle">
          <div class="export-header">
            <h3 id="libExportTitle">{{ t('library.export_dialog_title') }}</h3>
            <button class="export-close" :aria-label="t('common.action.close')" @click="showExportDialog = false">
              <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
            </button>
          </div>
          <div class="export-body">
            <p class="export-desc">{{ t('library.export_dialog_desc', { count: exportableSelected.length }) }}</p>
            <div class="export-formats" role="radiogroup" :aria-label="t('library.export_format_label')">
              <label class="export-format" :class="{ 'is-active': exportFormat === 'docx' }">
                <input type="radio" value="docx" v-model="exportFormat" />
                <span class="export-format-text">
                  <span class="export-format-name">{{ t('library.export_format_docx') }}</span>
                  <span class="export-format-desc">{{ t('library.export_format_docx_desc') }}</span>
                </span>
              </label>
              <label class="export-format" :class="{ 'is-active': exportFormat === 'md' }">
                <input type="radio" value="md" v-model="exportFormat" />
                <span class="export-format-text">
                  <span class="export-format-name">{{ t('library.export_format_md') }}</span>
                  <span class="export-format-desc">{{ t('library.export_format_md_desc') }}</span>
                </span>
              </label>
            </div>
          </div>
          <div class="export-footer">
            <button class="export-cancel" @click="showExportDialog = false">{{ t('library.export_cancel') }} <kbd>ESC</kbd></button>
            <button class="export-confirm" @click="onConfirmExport">{{ t('library.export_confirm', { count: exportableSelected.length }) }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { usePlayerStore } from '@/stores/player'
import PlayingEq from '@/components/common/PlayingEq.vue'
import DurationDial from '@/components/common/DurationDial.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { getSpeakerColor } from '@/utils/speakerColors'
import { isPlaceholderName, hasUnidentified, normalizeSpeakerName } from '@/utils/speakerDisplay'
import { useContainerSize } from '@/composables/useContainerSize'
import { usePageBack } from '@/composables/usePageBack'
import { useDialog } from '@/composables/useDialog'
import { showToast } from '@/composables/useToast'
import { usePopMenu } from '@/composables/usePopMenu'
import { downloadSummaryUrl, type SummaryFormat } from '@/api/tasks'
import { matchTask, matchesTitle, highlightText } from '@/utils/search'
import type { Task, TaskStatus } from '@/api/types'

const { t } = useI18n()
const router = useRouter()
const taskStore = useTaskStore()
const player = usePlayerStore()

// ESC 返回上一页（删除确认弹窗打开时会先消费事件，不会触发返回） / ESC goes back (batch-delete confirm dialog consumes the event first)
usePageBack()

// ─── 宽度档位（统一 composable 驱动） / Width tier (unified composable driven) ───
const libPageRef = ref<HTMLElement | null>(null)
const { widthClass } = useContainerSize(libPageRef)

// ─── 日期范围筛选 / Date range filter ───
const dateFrom = ref('')
const dateTo = ref('')

// ─── 说话人筛选 / Speaker filter ───
const filterSpeakerId = ref('')

/** 人员下拉菜单：搜索 + 选择 / Speaker dropdown: search + select */
const speakerTriggerRef = ref<HTMLElement | null>(null)
const speakerMenuRef = ref<HTMLElement | null>(null)
const speakerSearchRef = ref<HTMLInputElement | null>(null)
const speakerSearchQuery = ref('')
const {
  visible: speakerMenuVisible,
  toggle: toggleSpeakerMenu,
  close: closeSpeakerMenu,
  triggerAttrs: speakerTriggerAttrs,
  menuAttrs: speakerMenuAttrs,
} = usePopMenu(speakerMenuRef, speakerTriggerRef, { align: 'start' })

/** 触发按钮文案 / Trigger button label */
const speakerTriggerLabel = computed(() => {
  if (!filterSpeakerId.value) return t('library.filter_speaker_all')
  if (filterSpeakerId.value === UNID_FILTER) return t('library.filter_speaker_unidentified')
  return filterSpeakerId.value
})

/** 搜索后过滤的人员列表（不含「全部人员」与「未识别」特殊项） / Filtered names excluding special items */
const filteredSpeakerNames = computed(() => {
  const q = speakerSearchQuery.value.trim().toLowerCase()
  if (!q) return allSpeakerNames.value
  return allSpeakerNames.value.filter(n => n.toLowerCase().includes(q))
})

/** 「未识别」项是否应出现在当前搜索结果中 / Whether the unidentified item passes the search filter */
const unidVisible = computed(() => {
  const q = speakerSearchQuery.value.trim().toLowerCase()
  if (!q) return true
  return t('library.filter_speaker_unidentified').toLowerCase().includes(q)
})

function selectSpeaker(value: string) {
  filterSpeakerId.value = value
  closeSpeakerMenu()
}

/** 打开菜单时聚焦搜索框并重置查询 / Focus search input and reset query when menu opens */
watch(speakerMenuVisible, async (v) => {
  if (v) {
    speakerSearchQuery.value = ''
    await nextTick()
    speakerSearchRef.value?.focus()
  }
})

/** 从全部任务中收集去重的说话人名称列表 / Collect deduplicated speaker names from all tasks
 *  REQ-SPK-RN Q2/D6：仅枚举真名，占位名一律不入选项；未绑定走「未识别」特殊项（设计稿 §4） */
const allSpeakerNames = computed(() => {
  const names = new Set<string>()
  for (const task of taskStore.tasks) {
    const mapping = task.speaker_mapping
    if (mapping) {
      for (const name of Object.values(mapping)) {
        if (!isPlaceholderName(name)) names.add((name as string).trim())
      }
    }
  }
  return Array.from(names).sort((a, b) => a.localeCompare(b))
})

/** 「未识别」布尔聚合筛选项（库级不加总人数，设计稿 §3.1） */
const UNID_FILTER = '__unidentified__'
const libraryHasUnidentified = computed(() => taskStore.tasks.some(tk => hasUnidentified(tk.speaker_mapping)))

/** 是否有任意筛选条件激活 / Whether any filter is active */
const hasActiveFilter = computed(() => !!dateFrom.value || !!dateTo.value || !!filterSpeakerId.value)

function clearAllFilters() {
  dateFrom.value = ''
  dateTo.value = ''
  filterSpeakerId.value = ''
}

function setQuickDateRange(days: number) {
  const now = new Date()
  const from = new Date(now)
  from.setDate(from.getDate() - days)
  dateFrom.value = from.toISOString().slice(0, 10)
  dateTo.value = now.toISOString().slice(0, 10)
  filterSpeakerId.value = ''
}

// ─── 选择状态 / Selection state ───
const selectedIds = ref<Set<string>>(new Set())
const lastSelectedId = ref<string | null>(null)
const showBatchDeleteConfirm = ref(false)

function switchTab(showArchived: boolean) {
  taskStore.showArchived = showArchived
  clearSelection()
  ;(window as any).__omsUpdatePhilosophy?.(showArchived ? 'archived' : 'active')
}

/** 会议库共用过滤：对给定数据源依次叠加「文本搜索 + 日期 + 说话人」筛选 / Shared library filter: overlay text search + date + speaker on a given source */
function applyLibFilters(source: Task[]): Task[] {
  const q = taskStore.searchQuery.trim().toLowerCase()
  const dFrom = dateFrom.value
  const dTo = dateTo.value
  const spk = filterSpeakerId.value

  // 文本搜索（多维度） / Text search (multi-dimension)
  let filtered = q ? source.filter(t => matchTask(t, q)) : source

  // 日期范围筛选（AND 组合） / Date range filter (AND combination)
  if (dFrom || dTo) {
    const fromTs = dFrom ? new Date(dFrom + 'T00:00:00').getTime() : -Infinity
    const toTs = dTo ? new Date(dTo + 'T23:59:59').getTime() : Infinity
    filtered = filtered.filter(t => {
      const dateStr = t.meeting_date || t.created_at?.slice(0, 10) || ''
      if (!dateStr) return false
      const ts = new Date(dateStr + 'T00:00:00').getTime()
      return ts >= fromTs && ts <= toTs
    })
  }

  // 说话人筛选（AND 组合） / Speaker filter (AND combination)
  if (spk) {
    filtered = filtered.filter(t => {
      const mapping = t.speaker_mapping
      if (!mapping) return false
      // D5/Q2：「未识别」特殊项命中含任意占位/空名的任务；真名按归一后等值匹配
      if (spk === UNID_FILTER) return hasUnidentified(mapping)
      return Object.values(mapping).some(name => normalizeSpeakerName(name) === spk)
    })
  }

  return filtered
}

/** 是否存在任意检索/筛选条件（含搜索词）：决定计数是否切换为「匹配口径」 */
const hasLibFilter = computed(
  () => !!taskStore.searchQuery.trim() || !!dateFrom.value || !!dateTo.value || !!filterSpeakerId.value,
)

/** 当前 Tab 过滤后的可见任务（供分组与计数复用） */
const libFilteredTasks = computed(() =>
  applyLibFilters(taskStore.showArchived ? taskStore.archivedTasks : taskStore.activeTasks),
)

/** 当前 Tab 的全量任务数（未过滤） / Unfiltered total for the current tab */
const libTabTotal = computed(() =>
  (taskStore.showArchived ? taskStore.archivedTasks : taskStore.activeTasks).length,
)

/** 顶部「N 个会议」计数：有筛选时展示匹配数，否则展示当前 Tab 全量 */
const libCountDisplay = computed(() =>
  hasLibFilter.value ? libFilteredTasks.value.length : libTabTotal.value,
)

/** 「全部」Tab 计数：搜索/筛选时展示该 Tab 的匹配数 / Active tab count: matched when filtering */
const activeTabCount = computed(() =>
  hasLibFilter.value ? applyLibFilters(taskStore.activeTasks).length : taskStore.activeTasks.length,
)

/** 「已归档」Tab 计数 / Archived tab count */
const archivedTabCount = computed(() =>
  hasLibFilter.value ? applyLibFilters(taskStore.archivedTasks).length : taskStore.archivedTasks.length,
)

/** 是否靠「非标题」维度命中（用于给转写/纪要命中的行加来源标识） */
function isContentOnlyMatch(task: Task): boolean {
  const q = taskStore.searchQuery.trim().toLowerCase()
  if (!q) return false
  return !matchesTitle(task, q)
}

/** 会议库专用分组：基于过滤后的任务按日期分组 / Library grouping: group the filtered tasks by date */
const libGroupedTasks = computed(() => {
  const filtered = libFilteredTasks.value

  // 复用 store 的分组逻辑（通过临时替换 filteredTasks 的数据源） / Reuse store grouping logic
  // 这里直接按 meeting_date 分组，与 store 保持一致 / Group by meeting_date directly, consistent with store
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const dayOfWeek = (now.getDay() + 6) % 7
  const thisWeekStart = new Date(today.getTime() - dayOfWeek * 86400000)
  const lastWeekStart = new Date(thisWeekStart.getTime() - 7 * 86400000)
  const thisMonthStart = new Date(now.getFullYear(), now.getMonth(), 1)
  const lastMonthStart = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  const groupOrder = ['today', 'yesterday', 'this_week', 'last_week', 'this_month', 'last_month', 'earlier']
  const labelKey: Record<string, string> = {
    today: 'sidebar.date_today',
    yesterday: 'sidebar.date_yesterday',
    this_week: 'sidebar.date_this_week',
    last_week: 'sidebar.date_last_week',
    this_month: 'sidebar.date_this_month',
    last_month: 'sidebar.date_last_month',
    earlier: 'sidebar.date_earlier',
  }
  const groups = new Map<string, { key: string; label: string; tasks: Task[]; isToday: boolean; sortKey: number }>()

  for (const task of filtered) {
    const dateStr = task.meeting_date || task.created_at?.slice(0, 10) || 'unknown'
    const taskDate = new Date(dateStr + 'T00:00:00')
    const taskDay = new Date(taskDate.getFullYear(), taskDate.getMonth(), taskDate.getDate())
    const ts = taskDay.getTime()
    let key: string
    let isToday = false
    if (ts === today.getTime()) { key = 'today'; isToday = true }
    else if (ts === yesterday.getTime()) { key = 'yesterday' }
    else if (ts >= thisWeekStart.getTime()) { key = 'this_week' }
    else if (ts >= lastWeekStart.getTime()) { key = 'last_week' }
    else if (ts >= thisMonthStart.getTime()) { key = 'this_month' }
    else if (ts >= lastMonthStart.getTime()) { key = 'last_month' }
    else { key = 'earlier' }
    if (!groups.has(key)) {
      groups.set(key, { key, label: t(labelKey[key]), tasks: [], isToday, sortKey: groupOrder.indexOf(key) })
    }
    groups.get(key)!.tasks.push(task)
  }
  for (const group of groups.values()) {
    group.tasks.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
  }
  return Array.from(groups.values()).filter(g => g.tasks.length > 0).sort((a, b) => a.sortKey - b.sortKey)
})

// 当前分组内所有可见的 task id 列表（用于 Shift 范围选择） / All visible task ids in current group (for Shift range selection)
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
    // Shift + 点击：范围选择 / Shift + click: range selection
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

// ─── 排序 / Sorting ───
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

/** 读屏播报列的排序方向；非当前排序列返回 none
    Lets AT announce which column drives ordering, and that the others don't */
function ariaSort(key: SortKey): 'ascending' | 'descending' | 'none' {
  if (sortKey.value !== key) return 'none'
  return sortAsc.value ? 'ascending' : 'descending'
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

// ─── 批量操作 / Batch operations ───
// 批量导出（DEF-QA-R1-02）：弹窗选择 docx/md 格式后逐个触发浏览器下载，替换原 alert 占位。
// Batch export: pick docx/md in a dialog, then trigger sequential browser downloads (was an alert placeholder).
const showExportDialog = ref(false)
const exportFormat = ref<SummaryFormat>('docx')
const { dialogRef: exportDialogRef } = useDialog(showExportDialog, () => { showExportDialog.value = false })

/** 已选中且已完成、有纪要文件的任务（其余状态无 output_path，后端会 404，直接跳过）
 *  Selected tasks that are completed with a summary file; other states have no output_path and would 404, so skip them. */
const exportableSelected = computed(() =>
  taskStore.tasks.filter(tk => selectedIds.value.has(tk.task_id) && tk.status === 'completed' && !!tk.output_path)
)

function batchExport() {
  if (!selectedIds.value.size) return
  if (!exportableSelected.value.length) {
    showToast(t('library.export_none'), 'warn')
    return
  }
  exportFormat.value = 'docx'
  showExportDialog.value = true
}

/** 隐藏 <a download> 触发浏览器下载 / Trigger a browser download via a hidden <a download> */
function triggerDownload(url: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

async function onConfirmExport() {
  const targets = exportableSelected.value
  const format = exportFormat.value
  showExportDialog.value = false
  for (let i = 0; i < targets.length; i++) {
    triggerDownload(downloadSummaryUrl(targets[i].task_id, format))
    // 错峰触发，规避浏览器对连续自动下载的拦截 / Stagger to avoid the browser's automatic-download blocking
    if (i < targets.length - 1) await new Promise(r => setTimeout(r, 400))
  }
  const skipped = selectedIds.value.size - targets.length
  if (skipped > 0) showToast(t('library.export_skipped', { exported: targets.length, skipped }), 'info')
  else showToast(t('library.export_started', { count: targets.length }), 'success')
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

function batchDelete() {
  if (!selectedIds.value.size) return
  showBatchDeleteConfirm.value = true
}

async function onConfirmBatchDelete() {
  for (const id of selectedIds.value) {
    try {
      await taskStore.removeTask(id)
    } catch (e) {
      console.error(`delete meeting ${id} failed:`, e)
    }
  }
  clearSelection()
}

// ─── 导航 / Navigation ───
function openTask(task: Task) {
  taskStore.selectTask(task.task_id)
  // 录音中（含暂停）任务进入录音页，其余进入纪要页（中间状态由 GeneratingView 内联处理） / Recording/paused tasks go to recording view, others to generating view
  if (task.status === 'recording' || task.status === 'paused') {
    router.push({ name: 'recording', params: { taskId: task.task_id } })
  } else {
    router.push({ name: 'generating', params: { taskId: task.task_id } })
  }
}

// ─── 格式化 / Formatting ───
function statusDotClass(status: TaskStatus): string {
  if (status === 'completed') return 'is-done'
  if (status === 'failed') return 'is-failed'
  if (status === 'paused') return 'is-paused'
  if (['recording', 'processing', 'transcribing', 'summarizing'].includes(status)) return 'is-processing'
  return 'is-pending'
}

/** 会议库表格标题高亮 / Library table title highlight */
function highlightLibTitle(task: Task): string {
  const title = task.title || task.audio_name || t('common.untitled')
  const q = taskStore.searchQuery.trim().toLowerCase()
  return q ? highlightText(title, q) : title
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

/** 说话人列最多展示条数：超出以 +N 折叠，保证 ≤2 行不超出 52px 行高 / Max speakers shown in column: overflow collapsed as +N, ≤2 rows within 52px */
const SPK_MAX_SHOWN = 4

function visibleSpeakers(task: Task): SpeakerInfo[] {
  const list = getSpeakerList(task)
  return list.length > SPK_MAX_SHOWN ? list.slice(0, SPK_MAX_SHOWN - 1) : list
}

function extraSpeakerCount(task: Task): number {
  const n = getSpeakerList(task).length
  return n > SPK_MAX_SHOWN ? n - (SPK_MAX_SHOWN - 1) : 0
}

/** 从 task 中提取说话人列表（含颜色、名称、时长、占比） / Extract speaker list from task (with color, name, duration, percentage) */
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

  // 从 dialogue 计算每位说话人的时长与总时长 / Calculate per-speaker duration and total from dialogue
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

  const list: SpeakerInfo[] = Object.entries(mapping)
    .filter(([, name]) => !isPlaceholderName(name)) // D5/H1：占位/空名不逐个展示
    .map(([id, name]) => {
      const dur = durMap[id] || 0
      return {
        id,
        name: (name as string).trim(),
        color: getSpeakerColor(id),
        duration: dur,
        pct: total > 0 ? Math.round((dur / total) * 100) : 0,
      }
    })

  // 尾聚合项：未识别作为一个项计入（含折叠计数），不展开 N 个、不带编号
  const unidEntries = Object.entries(mapping).filter(([, name]) => isPlaceholderName(name))
  if (unidEntries.length > 0) {
    const unidDur = unidEntries.reduce((acc, [id]) => acc + (durMap[id] || 0), 0)
    list.push({
      id: UNID_FILTER,
      name: t('library.filter_speaker_unidentified'),
      color: 'var(--muted, var(--subtle))',
      duration: unidDur,
      pct: total > 0 ? Math.round((unidDur / total) * 100) : 0,
    })
  }
  return list
}
</script>

<style scoped>
.lib-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--s-5) var(--s-5) var(--s-6);
}

/* ─── 整合标题栏与搜索框 / Integrated title bar and search box ─── */
.lib-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
  margin-bottom: var(--s-5);
}

.lib-title-group {
  display: flex;
  align-items: center;
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
  border: none; border-bottom: 1px solid var(--border);
  border-radius: 0; background: transparent; font-size: 14px;
  outline: none; transition: border-color 0.15s, box-shadow 0.15s;
}
.lib-search-input:focus {
  border-bottom-color: var(--accent);
  box-shadow: 0 1px 0 0 var(--accent);
}

/* ─── Tab 切换 / Tab switch ─── */
.lib-tabs {
  display: flex;
  gap: 0;
  margin-bottom: var(--s-4);
  border-bottom: 1px solid var(--border);
}

.lib-tab {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) var(--s-4);
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.lib-tab:hover {
  background: transparent;
  color: var(--fg);
}

.lib-tab.active {
  background: transparent;
  color: var(--accent);
  font-weight: 600;
  border-bottom-color: var(--accent);
  box-shadow: none;
}

.lib-tab-count {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--surface-2);
  color: var(--subtle);
  line-height: 1.4;
}

.lib-tab:hover .lib-tab-count {
  background: var(--surface-2);
}

.lib-tab.active .lib-tab-count {
  background: var(--accent-soft);
  color: var(--accent);
}

/* ─── 筛选工具栏 / Filter toolbar ─── */
.lib-filter-bar {
  display: flex;
  align-items: center;
  gap: var(--s-4);
  margin-bottom: var(--s-4);
  padding: var(--s-2) var(--s-3);
  background: transparent;
  transition: border-color 0.15s;
  flex-wrap: wrap;
}
.lib-filter-bar.is-active {
  border-bottom-color: var(--accent);
}
.lib-filter-group {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.lib-date-group {
  flex-wrap: wrap;
}
.lib-filter-divider {
  width: 1px;
  height: 16px;
  background: var(--border);
  margin: 0 2px;
  flex-shrink: 0;
}
.lib-filter-label {
  color: var(--subtle);
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.lib-date-input {
  border: none; border-bottom: 1px solid var(--border);
  border-radius: 0; padding: 4px 8px;
  font-size: 12px; background: transparent;
  color: var(--fg); outline: none; transition: border-color 0.12s;
}
.lib-date-input:focus {
  border-bottom-color: var(--accent);
  box-shadow: 0 1px 0 0 var(--accent);
}
.lib-date-sep {
  color: var(--subtle);
  font-size: 12px;
}
.lib-speaker-select {
  border: none; border-bottom: 1px solid var(--border);
  border-radius: 0; padding: 4px 8px;
  font-size: 12px; background: transparent;
  color: var(--fg); outline: none; cursor: pointer;
  transition: border-color 0.12s; min-width: 120px;
}
.lib-speaker-select:focus {
  border-bottom-color: var(--accent);
  box-shadow: 0 1px 0 0 var(--accent);
}
/* 触发按钮 / Trigger button */
.lib-speaker-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.lib-speaker-trigger-text.is-placeholder {
  color: var(--muted);
}
.lib-speaker-caret {
  flex-shrink: 0;
  color: var(--muted);
  transition: transform 0.15s;
}
/* 下拉菜单 / Dropdown menu */
.lib-speaker-menu {
  position: fixed;
  z-index: var(--z-popover);
  min-width: 200px;
  max-width: 280px;
  background: var(--popover-bg, var(--bg));
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.lib-speaker-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--muted);
}
.lib-speaker-search-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--fg);
  font-size: 13px;
  outline: none;
  min-width: 0;
}
.lib-speaker-search-input::placeholder {
  color: var(--subtle);
}
.lib-speaker-list {
  max-height: 240px;
  overflow-y: auto;
  padding: 4px 0;
}
.lib-speaker-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--fg);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.1s;
}
.lib-speaker-item:hover,
.lib-speaker-item:focus-visible {
  background: var(--hover-bg, rgba(128, 128, 128, 0.12));
  outline: none;
}
.lib-speaker-item.is-active {
  color: var(--accent);
  font-weight: 500;
}
.lib-speaker-empty {
  padding: 16px 12px;
  text-align: center;
  color: var(--muted);
  font-size: 12px;
}
.lib-filter-actions {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-left: auto;
}
.lib-filter-chip {
  padding: 3px 10px; border-radius: 4px;
  font-size: 11px; border: none;
  background: transparent; color: var(--muted);
  cursor: pointer; transition: all 0.12s;
}
.lib-filter-chip:hover {
  background: var(--surface-2); color: var(--fg);
}
.lib-filter-clear {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 11px;
  background: transparent;
  color: var(--subtle);
  cursor: pointer;
  transition: color 0.12s;
}
.lib-filter-clear:hover {
  color: var(--fg);
}

/* ─── 表格容器 / Table container ─── */
.table-container {
  flex: 1;
  background: transparent;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 列标题 / Column headers */
.table-head {
  display: grid;
  grid-template-columns: 40px minmax(180px, 1fr) 110px 100px 140px 140px 40px;
  align-items: center;
  padding: 0 var(--s-4);
  height: 40px;
  background: transparent;
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
/* 排序按钮承载在列标题单元格里，保持原有 flex 外观与网格轨道不变
   The sort button lives inside the header cell so the grid track is unchanged. */
.col-header-btn {
  display: flex; align-items: center; gap: var(--s-1);
  font: inherit; color: inherit; background: transparent; border: 0; padding: 0;
  cursor: pointer; width: 100%; text-align: left;
}
.col-header .sort-icon { opacity: 0.4; transition: opacity 0.15s; }
.col-header.sorted .sort-icon { opacity: 1; color: var(--accent); }

/* 复选框 / Checkbox */
.row-checkbox {
  width: 16px; height: 16px;
  border: 1.5px solid var(--border-strong);
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
  background: var(--surface); flex-shrink: 0;
  /* 视觉大小不变，通过伪元素扩展点击热区 / Keep visual size, expand hit area via pseudo-element */
  position: relative;
}
.row-checkbox::before {
  content: '';
  position: absolute;
  inset: -12px;
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

/* 表格内容区 / Table content */
.table-body { flex: 1; overflow-y: auto; }

.table-group-header {
  padding: var(--s-2) var(--s-4);
  background: var(--bg);
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
  border-bottom: none;
  cursor: pointer;
  transition: background 0.1s;
}
.table-row:hover { background: var(--surface-2); }
.table-row.selected { background: color-mix(in oklch, var(--accent) 8%, transparent); }
.table-row:last-child { border-bottom: none; }

/* 单元格 / Cell */
.cell-checkbox { display: flex; align-items: center; justify-content: center; cursor: pointer; }
.cell-title {
  display: flex; align-items: center; gap: var(--s-2);
  font-size: 14px; font-weight: 500; color: var(--fg);
  min-width: 0; padding-right: var(--s-3);
}
.cell-title-text {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.lib-src-badge {
  flex-shrink: 0;
  font-size: 11px;
  line-height: 1.4;
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--subtle);
  border: 1px solid var(--border);
  white-space: nowrap;
}
.table-row.is-playing .cell-title { color: var(--accent); }
.cell-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--muted);
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.status-dot.is-done { background: var(--ok); }
.status-dot.is-failed { background: var(--error); }
.status-dot.is-processing { background: var(--accent); animation: blink 1.2s ease-in-out infinite; }
.status-dot.is-paused { background: var(--warn); }
/* pending（排队待处理）与 paused（已暂停，需用户操作）此前同为 --warn，不可区分 */
.status-dot.is-pending { background: var(--subtle); }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.cell-duration, .cell-speakers, .cell-time {
  font-size: 13px; color: var(--muted);
  display: flex; align-items: center; gap: 4px;
}
.cell-muted { color: var(--subtle); }

/* 说话人列：彩色名称 + 占比横条，参照 .gs-chip 视觉模式 / Speaker column: colored name + ratio bar */
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
}
.cell-actions-btn {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius); color: var(--subtle); transition: all 0.15s;
}
.cell-actions-btn:hover { background: var(--border); color: var(--fg); }

/* ─── 批量操作栏 / Batch action bar ─── */
.batch-bar {
  display: none;
  height: 48px;
  background: var(--fg);
  color: #fff;
  align-items: center;
  padding: 0 var(--s-4); gap: var(--s-3);
  flex-shrink: 0;
}
.batch-bar.visible { display: flex; }
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

/* ─── 空状态 / Empty state ─── */
.empty-state { text-align: center; padding: var(--s-9) var(--s-7); color: var(--muted); font-size: 13px; }

/* 加载失败态 / Load-failure state */
.lib-error {
  display: flex; align-items: center; justify-content: center; gap: var(--s-3);
  text-align: center; padding: var(--s-9) var(--s-7);
  color: var(--error); font-size: var(--fs-13);
}
.lib-error-retry {
  padding: var(--s-2) var(--s-3); font: inherit; font-size: var(--fs-12);
  color: var(--error); background: transparent;
  border: 1px solid var(--error); border-radius: var(--radius-sm); cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.lib-error-retry:hover { background: var(--error); color: var(--surface); }

/* ─── 响应式：视口级 @media 渐进隐藏次要列 / Responsive: viewport @media progressive hide ─── */

/* ≤1000px：隐藏说话人列 / ≤1000px: hide speaker column */
@media (max-width: 1000px) {
  .table-head, .table-row {
    grid-template-columns: 40px minmax(160px, 1fr) 110px 100px 140px 40px;
  }
  .table-head .col-header:nth-child(5),
  .table-row .cell-speakers { display: none; }
  .lib-search-wrap { max-width: 380px; }
}

/* ≤768px：标题区与搜索框纵向排列 + 隐藏时长列 / ≤768px: stack title and search + hide duration */
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

/* ≤600px：隐藏时间列，仅保留 复选框 + 标题 + 状态 + 操作 / ≤600px: hide time, keep checkbox + title + status + actions */
@media (max-width: 600px) {
  .table-head, .table-row {
    grid-template-columns: 36px minmax(120px, 1fr) 110px 36px;
  }
  .table-head .col-header:nth-child(6),
  .table-row .cell-time { display: none; }
}

/* ─── 组件级宽度档位（ResizeObserver 驱动） / Component width tier (ResizeObserver driven) ─── */

/* is-compact (≤860px)：状态列文字隐藏，仅保留状态圆点 / is-compact (≤860px): hide status text, keep dot */
.lib-page.is-compact .cell-status span:not(.status-dot) {
  display: none;
}
.lib-page.is-compact .cell-status {
  justify-content: center;
}

/* is-narrow (≤640px)：在视口隐藏说话人基础上，进一步收紧间距 / is-narrow (≤640px): tighten spacing beyond viewport hide */
.lib-page.is-narrow .table-head,
.lib-page.is-narrow .table-row {
  padding: 0 var(--s-2);
}

/* is-xnarrow (≤480px)：隐藏状态文字 + 缩短行高 / is-xnarrow (≤480px): hide status text + reduce row height */
.lib-page.is-xnarrow .table-row {
  height: 44px;
}
.lib-page.is-xnarrow .cell-title {
  font-size: 13px;
}

/* ─── 批量导出格式选择弹窗（DEF-QA-R1-02） / Batch export format dialog ───
   视觉语言与 ConfirmDialog 保持一致（同 overlay/dialog/footer 结构），仅 body 换成格式单选组。
   Mirrors ConfirmDialog's visual language; body swapped for a format radio group. */
.export-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: var(--overlay-bg);
  display: grid;
  place-items: center;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}

.export-overlay.is-open {
  opacity: 1;
  pointer-events: auto;
}

.export-dialog {
  min-width: 420px;
  max-width: 500px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px oklch(0% 0 0 / 0.10), 0 4px 16px oklch(0% 0 0 / 0.05);
  transform: translateY(8px);
  opacity: 0;
  transition: transform 0.25s ease, opacity 0.2s ease;
}

.export-overlay.is-open .export-dialog {
  transform: translateY(0);
  opacity: 1;
}

.export-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-4) var(--s-5);
  border-bottom: 1px solid var(--border);
}

.export-header h3 {
  margin: 0;
  font-size: var(--fs-15);
  font-weight: 600;
}

.export-close {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
  border-radius: var(--radius-sm);
}

.export-close:hover {
  opacity: 1;
  background: var(--surface-2);
}

.export-close svg {
  width: 12px;
  height: 12px;
}

.export-body {
  padding: var(--s-5);
}

.export-desc {
  margin: 0 0 var(--s-4);
  color: var(--muted);
  font-size: var(--fs-13);
  line-height: 1.5;
}

.export-formats {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.export-format {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.export-format:hover {
  background: var(--surface-2);
}

.export-format.is-active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.export-format input[type="radio"] {
  margin-top: 3px;
  accent-color: var(--accent);
}

.export-format-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.export-format-name {
  font-size: var(--fs-14);
  font-weight: 500;
}

.export-format-desc {
  font-size: var(--fs-12);
  color: var(--muted);
}

.export-footer {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
  padding: var(--s-3) var(--s-4);
  border-top: 1px solid var(--border);
}

.export-cancel,
.export-confirm {
  padding: var(--s-2) var(--s-4);
  border-radius: var(--radius-sm);
  font-size: var(--fs-14);
  cursor: pointer;
  transition: all 0.2s;
}

.export-cancel {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg);
}

.export-cancel:hover {
  background: var(--surface-2);
}

.export-cancel kbd {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--subtle);
  line-height: 1.3;
  margin-left: 4px;
}

.export-confirm {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: #fff;
}

.export-confirm:hover {
  background: oklch(from var(--accent) calc(l - 0.06) c h);
}
</style>
