<template>
  <div class="lib-page" ref="libPageRef" :class="widthClass">
    <LibraryToolbar
      :search-query="taskStore.searchQuery"
      :show-archived="taskStore.showArchived"
      :has-lib-filter="hasLibFilter"
      :lib-count-display="libCountDisplay"
      :lib-tab-total="libTabTotal"
      :active-tab-count="activeTabCount"
      :archived-tab-count="archivedTabCount"
      :date-from="dateFrom"
      :date-to="dateTo"
      :has-active-filter="hasActiveFilter"
      :filter-speaker-id="filterSpeakerId"
      :speaker-trigger-label="speakerTriggerLabel"
      :filtered-speaker-names="filteredSpeakerNames"
      :unid-visible="unidVisible"
      :library-has-unidentified="libraryHasUnidentified"
      :speaker-search-query="speakerSearchQuery"
      :UNID_FILTER="UNID_FILTER"
      @update:search-query="taskStore.searchQuery = $event"
      @switch-tab="switchTab"
      @update:date-from="dateFrom = $event"
      @update:date-to="dateTo = $event"
      @quick-range="setQuickDateRange"
      @select-speaker="selectSpeaker"
      @update:speaker-search-query="speakerSearchQuery = $event"
      @clear-filters="clearAllFilters"
    />

    <LibraryTable
      :grouped-tasks="libGroupedTasks"
      :load-error="taskStore.loadError"
      :selected-ids="selectedIds"
      :is-all-selected="isAllSelected"
      :is-indeterminate="isIndeterminate"
      :playing-task-id="player.taskId"
      :playing="player.playing"
      :sort-key="sortKey"
      :sort-aria="ariaSort"
      :sort-group-tasks="sortGroupTasks"
      :toggle-select="toggleSelect"
      :toggle-select-all="toggleSelectAll"
      :open-task="openTask"
      :status-dot-class="statusDotClass"
      :highlight-lib-title="highlightLibTitle"
      :format-duration="formatDuration"
      :format-date-time="formatDateTime"
      :visible-speakers="visibleSpeakers"
      :extra-speaker-count="extraSpeakerCount"
      :get-speaker-list="getSpeakerList"
      :is-content-only-match="isContentOnlyMatch"
      :get-status-label="(status) => taskStore.getStatusLabel(status)"
      @toggle-sort="toggleSort"
    />

    <!-- 加载失败态 -->
    <div v-if="taskStore.loadError && !taskStore.loading" class="lib-error" role="alert">
      <span class="lib-error-text">{{ taskStore.loadError }}</span>
      <button type="button" class="lib-error-retry" @click="taskStore.loadTasks()">{{ t('common.error.retry') }}</button>
    </div>

    <!-- 空状态 -->
    <div v-else-if="libGroupedTasks.length === 0 && !taskStore.loading" class="empty-state">
      {{ taskStore.searchQuery ? t('library.empty_search') : (taskStore.showArchived ? t('library.empty_archived') : t('library.empty')) }}
    </div>

    <LibraryBatchBar
      :selected-count="selectedIds.size"
      :show-archived="taskStore.showArchived"
      :show-export-dialog="showExportDialog"
      :export-format="exportFormat"
      :exportable-count="exportableSelected.length"
      @batch-export="batchExport"
      @batch-archive="batchArchive"
      @batch-unarchive="batchUnarchive"
      @batch-delete="batchDelete"
      @clear-selection="clearSelection"
      @update:show-export-dialog="showExportDialog = $event"
      @update:export-format="exportFormat = $event"
      @confirm-export="onConfirmExport"
    />

    <!-- 批量删除确认弹窗 -->
    <ConfirmDialog
      v-model="showBatchDeleteConfirm"
      :title="t('library.confirm_delete_title')"
      :message="t('library.confirm_delete', { count: selectedIds.size })"
      @confirm="onConfirmBatchDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { usePlayerStore } from '@/stores/player'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { useContainerSize } from '@/composables/useContainerSize'
import { useLibraryFilters } from '@/composables/useLibraryFilters'
import { useLibrarySelection } from '@/composables/useLibrarySelection'
import LibraryToolbar from '@/views/library/LibraryToolbar.vue'
import LibraryTable from '@/views/library/LibraryTable.vue'
import LibraryBatchBar from '@/views/library/LibraryBatchBar.vue'

const { t } = useI18n()
const taskStore = useTaskStore()
const player = usePlayerStore()

const libPageRef = ref<HTMLElement | null>(null)
const { widthClass } = useContainerSize(libPageRef)

// ─── Composables ───
const filters = useLibraryFilters()
const selection = useLibrarySelection()

// 桥接：filters.libGroupedTasks → selection.groupedTasks（响应式）
watch(filters.libGroupedTasks, v => selection.groupedTasks.value = v, { immediate: true })

// ─── Destructure from composables ───
const {
  dateFrom, dateTo, filterSpeakerId, speakerSearchQuery,
  sortKey,
  UNID_FILTER,
  hasActiveFilter, speakerTriggerLabel, filteredSpeakerNames, unidVisible,
  libraryHasUnidentified,
  hasLibFilter, libGroupedTasks, libCountDisplay, libTabTotal,
  activeTabCount, archivedTabCount,
  switchTab, clearAllFilters, setQuickDateRange, selectSpeaker,
  toggleSort, ariaSort, sortGroupTasks, isContentOnlyMatch,
} = filters

const {
  selectedIds, showBatchDeleteConfirm, showExportDialog, exportFormat,
  isAllSelected, isIndeterminate,
  exportableSelected,
  toggleSelect, toggleSelectAll, clearSelection,
  batchExport, onConfirmExport, batchArchive, batchUnarchive, batchDelete, onConfirmBatchDelete,
  openTask,
  statusDotClass, highlightLibTitle, formatDuration, formatDateTime,
  visibleSpeakers, extraSpeakerCount, getSpeakerList,
} = selection
</script>

<style scoped>
.lib-page { display: flex; flex-direction: column; height: 100%; padding: var(--s-5) var(--s-5) var(--s-6); }
.empty-state { text-align: center; padding: var(--s-9) var(--s-7); color: var(--muted); font-size: 13px; }
.lib-error { display: flex; align-items: center; justify-content: center; gap: var(--s-3); text-align: center; padding: var(--s-9) var(--s-7); color: var(--error); font-size: var(--fs-13); }
.lib-error-retry { padding: var(--s-2) var(--s-3); font: inherit; font-size: var(--fs-12); color: var(--error); background: transparent; border: 1px solid var(--error); border-radius: var(--radius-sm); cursor: pointer; transition: background 0.15s, color 0.15s; }
.lib-error-retry:hover { background: var(--error); color: var(--surface); }
</style>

<!-- 不带 scoped：响应式宽度档位跨子组件生效 -->
<style>
.is-compact .cell-status span:not(.status-dot) { display: none; }
.is-compact .cell-status { justify-content: center; }
.is-narrow .table-head, .is-narrow .table-row { padding: 0 var(--s-2); }
.is-xnarrow .table-row { height: 44px; }
.is-xnarrow .cell-title { font-size: 13px; }
</style>
