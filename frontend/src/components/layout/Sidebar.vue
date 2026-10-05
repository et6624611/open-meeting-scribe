<template>
  <aside class="sidebar" :class="{ 'is-narrow': isNarrow }" ref="sidebarRef">
    <!-- 缝隙拉手：点击 = 折叠/展开，水平拖拽 = 调整宽度 / Resize handle: click = collapse/expand, horizontal drag = resize width -->
    <button
      class="sb-toggle"
      :title="(layout.sidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')) + ` (${modKey}B)`"
      :aria-label="layout.sidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')"
      :aria-expanded="!layout.sidebarCollapsed"
      @mousedown="onToggleDown($event)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    </button>
    <!-- 头部：折叠/展开全部 + 筛选 / Header: Collapse/expand all + filter -->
    <div class="sb-header">
      <div class="sb-header-actions">
        <button class="sb-text-btn" id="sbCollapseAllBtn" :title="layout.timelineAllCollapsed ? t('common.action.expand_all') : t('common.action.collapse_all')" @click="layout.toggleTimelineCollapseAll()">
          <svg class="ico-fold" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="M8 13 4 17l4 4"/><path d="M4 17h16"/></svg>
          <svg class="ico-expand" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 13 4 4-4 4"/><path d="M20 17H4"/></svg>
          <span>{{ layout.timelineAllCollapsed ? t('common.action.expand_all') : t('common.action.collapse_all') }}</span>
        </button>
        <button class="sb-text-btn" :class="{ 'is-active': showFilter }" :title="t('common.action.filter') + ` (${modKey}K)`" @click="toggleFilter">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span>{{ t('common.action.filter') }}</span>
          <kbd class="sb-filter-kbd">{{ modKey }}K</kbd>
        </button>
      </div>
    </div>

    <!-- 搜索栏（默认隐藏，点击筛选按钮展开） / Search bar (hidden by default, expands on filter button click) -->
    <div class="sb-filter-row" :class="{ 'is-open': showFilter || taskStore.sidebarSearchQuery }">
      <div class="sb-search-wrap">
        <svg class="sb-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          ref="searchInputRef"
          class="sb-search-input"
          type="text"
          :placeholder="t('sidebar.search_placeholder')"
          :value="taskStore.sidebarSearchQuery"
          @input="taskStore.sidebarSearchQuery = ($event.target as HTMLInputElement).value"
        />
        <button
          v-if="taskStore.sidebarSearchQuery"
          class="sb-search-clear is-visible"
          @click="taskStore.sidebarSearchQuery = ''"
        >✕</button>
      </div>
      <IconButton class="sb-filter-reset" :label="t('common.action.reset')" @click="onResetSearch">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
      </IconButton>
    </div>

    <!-- 时间轴（会议列表） / Timeline (meeting list) -->
    <div class="sb-history">
      <TaskList />
    </div>

    <!-- 孤儿录音恢复横幅 / Orphan recording recovery banner -->
    <div v-if="showOrphanBanner" class="sb-orphan-banner">
      <div class="sb-orphan-content">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="sb-orphan-icon"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span class="sb-orphan-text">{{ t('sidebar.orphan_detected') }}</span>
      </div>
      <div class="sb-orphan-actions">
        <button class="sb-orphan-btn" @click="onRecover">{{ t('sidebar.orphan_recover') }}</button>
        <button class="sb-orphan-dismiss" @click="dismissBanner" :title="t('sidebar.orphan_close')">×</button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import TaskList from '@/components/task/TaskList.vue'
import IconButton from '@/components/common/IconButton.vue'
import { beginResize } from '@/composables/useDivider'
import { useEscClose } from '@/composables/useEscClose'
import { useContainerSize } from '@/composables/useContainerSize'
import { getRecordStatus, recoverRecord } from '@/api/record'
import { modKey } from '@/utils/platform'

const { t } = useI18n()
const taskStore = useTaskStore()
const layout = useLayoutStore()

const sidebarRef = ref<HTMLElement | null>(null)
const { isNarrow } = useContainerSize(sidebarRef, { breakpoints: { md: 200 } })

function onToggleDown(e: MouseEvent) {
  beginResize(e, 'left', { onClick: () => layout.toggleSidebar(), resizable: !layout.sidebarCollapsed })
}

/** 点击侧边栏外部区域：仅关闭筛选行，不再折叠整个侧边栏
   Outside click now only dismisses the filter row, never the whole sidebar.
   旧行为会把 layout.sidebarCollapsed 直接置 true 且绕过 persist()，导致 TopBar
   视图切换器的高亮在用户没有操作的情况下从 full 跳到 right，也让「时间轴 +
   正文」无法对照查看。折叠仍由拉手 / ⌘B / rail / 视图切换器负责。
   The old path mutated sidebarCollapsed without persist(), silently moving the
   TopBar view-switcher highlight from full to right with no user action. */
function onDocClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  // 隐式收起：点击外部关闭筛选行 / Implicit collapse: close filter row on outside click
  if (showFilter.value && !target.closest('.sb-filter-row') && !target.closest('.sb-text-btn')) {
    showFilter.value = false
  }
}

const showFilter = ref(false)
/** ESC 关闭筛选行并同步状态（此前只被全局剥 class，showFilter 仍为 true）
    ESC now closes the filter row through state, not a stripped class. */
useEscClose(showFilter, () => { showFilter.value = false })
const searchInputRef = ref<HTMLInputElement | null>(null)
const showOrphanBanner = ref(false)

function toggleFilter() {
  showFilter.value = !showFilter.value
  if (showFilter.value) {
    nextTick(() => searchInputRef.value?.focus())
  }
}

onMounted(() => {
  window.addEventListener('global-sidebar-search', onGlobalSidebarSearch)
  document.addEventListener('click', onDocClickOutside)
  // 检查是否有孤儿录音 / Check for orphan recordings
  checkOrphanStatus()
  
  // 监听侧边栏宽度变化，窄幅态自动切换单行截断（由 useContainerSize composable 驱动） / Watch sidebar width changes, auto-switch to single-line truncation in narrow mode (driven by useContainerSize composable)
})

async function checkOrphanStatus() {
  try {
    const status = await getRecordStatus()
    if (status.orphaned) {
      showOrphanBanner.value = true
    }
  } catch (e) {
    console.error('Failed to check orphan status:', e)
  }
}

async function onRecover() {
  try {
    await recoverRecord()
    // 恢复成功后刷新任务列表 / Refresh task list after successful recovery
    await taskStore.loadTasks()
    // 隐藏横幅 / Hide banner
    showOrphanBanner.value = false
  } catch (e) {
    console.error('Failed to recover recording:', e)
    alert(t('sidebar.orphan_recover_failed'))
  }
}

function dismissBanner() {
  showOrphanBanner.value = false
}

onBeforeUnmount(() => {
  window.removeEventListener('global-sidebar-search', onGlobalSidebarSearch)
  document.removeEventListener('click', onDocClickOutside)
})

function onGlobalSidebarSearch() {
  showFilter.value = true
  nextTick(() => {
    searchInputRef.value?.focus()
    searchInputRef.value?.select()
  })
}

function onResetSearch() {
  taskStore.sidebarSearchQuery = ''
}


</script>
