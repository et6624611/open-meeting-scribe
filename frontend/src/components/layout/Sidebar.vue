<template>
  <aside class="sidebar" :class="{ 'is-narrow': isNarrow }" ref="sidebarRef">
    <!-- 缝隙拉手：点击 = 折叠/展开，水平拖拽 = 调整宽度 -->
    <button
      class="sb-toggle"
      :title="layout.sidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')"
      :aria-label="layout.sidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')"
      :aria-expanded="!layout.sidebarCollapsed"
      @mousedown="onToggleDown($event)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    </button>
    <!-- 折叠态：Logo + 展开按钮 -->
    <div class="sb-logo-area">
      <IconButton class="sb-expand-btn" :label="t('sidebar.expand')" @click="layout.toggleSidebar()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <line x1="9" y1="3" x2="9" y2="21"/>
          <polyline points="13 8 17 12 13 16"/>
        </svg>
      </IconButton>
    </div>
    <!-- 头部：筛选（LibraryView 中由页面自身提供搜索功能） -->
    <div class="sb-header" v-if="route.name !== 'library'">
      <div class="sb-header-actions">
        <button class="sb-text-btn" id="sbCollapseAllBtn" :title="layout.timelineAllCollapsed ? t('common.action.expand_all') : t('common.action.collapse_all')" @click="layout.toggleTimelineCollapseAll()">
          <svg class="ico-fold" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="M8 13 4 17l4 4"/><path d="M4 17h16"/></svg>
          <svg class="ico-expand" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 13 4 4-4 4"/><path d="M20 17H4"/></svg>
          <span>{{ layout.timelineAllCollapsed ? t('common.action.expand_all') : t('common.action.collapse_all') }}</span>
        </button>
        <button class="sb-text-btn" :class="{ 'is-active': showFilter }" :title="t('common.action.filter')" @click="toggleFilter">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span>{{ t('common.action.filter') }}</span>
        </button>
      </div>
    </div>

    <!-- 折叠态功能图标条 -->
    <div class="sb-collapsed-icons">
      <IconButton class="sb-collapsed-btn" :label="t('sidebar.all_meetings')" @click="router.push('/library')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
      </IconButton>
    </div>

    <!-- 搜索栏（默认隐藏，点击筛选按钮展开；LibraryView 中由页面自身提供搜索功能） -->
    <div class="sb-filter-row" v-if="route.name !== 'library'" :class="{ 'is-open': showFilter || taskStore.searchQuery }">
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
          :value="taskStore.searchQuery"
          @input="taskStore.searchQuery = ($event.target as HTMLInputElement).value"
        />
        <button
          v-if="taskStore.searchQuery"
          class="sb-search-clear is-visible"
          @click="taskStore.searchQuery = ''"
        >✕</button>
      </div>
      <IconButton class="sb-filter-reset" :label="t('common.action.reset')" @click="onResetSearch">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
      </IconButton>
    </div>

    <!-- 时间轴（会议列表） -->
    <div class="sb-history">
      <TaskList />
    </div>

    <!-- 孤儿录音恢复横幅 -->
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
    
    <!-- 底部向上展开面板（版本号 + 菜单按钮合一） -->
    <div class="sb-bottom-panel" :class="{ 'is-open': showBottomPanel }">
      <!-- 展开区域（向上弹出） -->
      <div class="sbp-content">
        <!-- 账户 -->
        <div class="sbp-section">
          <div class="sbp-group-label">{{ t('sidebar.menu_account') }}</div>
          <template v-if="userStore.isLoggedIn">
            <div class="sbp-user-info">
              <span class="sbp-avatar">{{ userStore.avatarLetter }}</span>
              <span class="sbp-name">{{ userStore.displayName }}</span>
            </div>
            <button class="sbp-item" @click="onLogout">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              {{ t('sidebar.menu_logout') }}
            </button>
          </template>
          <template v-else>
            <button class="sbp-item" @click="onLogin">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
              {{ t('sidebar.menu_login') }}
            </button>
          </template>
        </div>
        <div class="sbp-sep"></div>
        <!-- 管理 -->
        <div class="sbp-section">
          <div class="sbp-group-label">{{ t('sidebar.menu_management') }}</div>
          <button class="sbp-item" :class="{ 'is-active': route.name === 'projects' }" @click="navigate('/projects')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            {{ t('sidebar.menu_projects') }}
          </button>
          <button class="sbp-item" :class="{ 'is-active': route.name === 'speakers' }" @click="navigate('/speakers')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            {{ t('sidebar.menu_speakers') }}
          </button>
          <button class="sbp-item" :class="{ 'is-active': route.name === 'hotwords' }" @click="navigate('/hotwords')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5h6l5 5v11a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5z"/><path d="M14 5v6h6"/></svg>
            {{ t('sidebar.menu_hotwords') }}
          </button>
        </div>
        <div class="sbp-sep"></div>
        <!-- 系统 -->
        <div class="sbp-section">
          <div class="sbp-group-label">{{ t('sidebar.menu_system') }}</div>
          <button class="sbp-item" :class="{ 'is-active': route.name === 'settings' }" @click="navigate('/settings')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1.1a1.7 1.7 0 0 0-1.8.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1.1a2 2 0 1 1 2.8 2.8l.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>
            {{ t('sidebar.menu_settings') }}
          </button>
        </div>
      </div>
      <!-- 触发栏：版本号 + 主动AI指示器 + 菜单按钮 -->
      <div class="sbp-bar">
        <div class="sbp-version" :title="t('sidebar.version_check')" role="button" tabindex="0">
          <span>{{ t('sidebar.version') }}</span>
          <span id="sbVersionNumber">v2.0.0</span>
          <span class="sb-version-dot" id="sbVersionDot" :title="t('sidebar.version_update')"></span>
        </div>
        <button
          v-if="proactive.proactiveEnabled.value"
          class="sb-proactive-indicator"
          :class="{
            'is-enabled': proactive.unreadCount.value === 0,
            'has-unread': proactive.unreadCount.value > 0,
          }"
          :title="proactive.unreadCount.value > 0 ? t('ai-panel.proactive.sidebar_indicator_tip', { count: proactive.unreadCount.value }) : t('ai-panel.proactive.sidebar_indicator')"
          :aria-label="t('ai-panel.proactive.sidebar_indicator')"
          @click.stop="onProactiveClick"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          </svg>
          <span v-if="proactive.unreadCount.value > 0" class="sb-proactive-badge">{{ proactive.unreadCount.value }}</span>
        </button>
        <IconButton class="sbp-menu-btn" :label="t('sidebar.menu')" @click.stop="toggleBottomPanel">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>
          </svg>
        </IconButton>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useUserStore } from '@/stores/user'
import { useLayoutStore } from '@/stores/layout'
import TaskList from '@/components/task/TaskList.vue'
import IconButton from '@/components/common/IconButton.vue'
import { beginResize } from '@/composables/useDivider'
import { getRecordStatus, recoverRecord } from '@/api/record'
import { useAiProactive } from '@/composables/useAiProactive'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const taskStore = useTaskStore()
const userStore = useUserStore()
const layout = useLayoutStore()
const proactive = useAiProactive()

const sidebarRef = ref<HTMLElement | null>(null)
const isNarrow = ref(false)
let resizeObserver: ResizeObserver | null = null

function onToggleDown(e: MouseEvent) {
  beginResize(e, 'left', { onClick: () => layout.toggleSidebar(), resizable: !layout.sidebarCollapsed })
}

/** 点击侧边栏外部区域时自动折叠（已折叠 / 分隔条拖拽中 忽略） */
function onDocClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  // 隐式收起：点击外部关闭筛选行
  if (showFilter.value && !target.closest('.sb-filter-row') && !target.closest('.sb-text-btn')) {
    showFilter.value = false
  }
  // 侧边栏折叠
  if (layout.sidebarCollapsed) return
  if (document.body.classList.contains('is-divider-dragging')) return
  if (sidebarRef.value && !sidebarRef.value.contains(target)) {
    layout.sidebarCollapsed = true
  }
}

const showBottomPanel = ref(false)
const showFilter = ref(false)
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
  // 检查是否有孤儿录音
  checkOrphanStatus()
  
  // 监听侧边栏宽度变化，窄幅态自动切换单行截断
  if (sidebarRef.value) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const width = entry.contentRect.width
        isNarrow.value = width < 200
      }
    })
    resizeObserver.observe(sidebarRef.value)
  }
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
    // 恢复成功后刷新任务列表
    await taskStore.loadTasks()
    // 隐藏横幅
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
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})

function onGlobalSidebarSearch() {
  showFilter.value = true
  nextTick(() => {
    searchInputRef.value?.focus()
    searchInputRef.value?.select()
  })
}

function onResetSearch() {
  taskStore.searchQuery = ''
}

function toggleBottomPanel() {
  if (layout.sidebarCollapsed) {
    // 侧边栏折叠态：先展开，再打开面板
    layout.sidebarCollapsed = false
    nextTick(() => { showBottomPanel.value = true })
  } else {
    showBottomPanel.value = !showBottomPanel.value
  }
}

function onLogin() {
  showBottomPanel.value = false
  window.dispatchEvent(new CustomEvent('oms:show-login'))
}

function navigate(path: string) {
  showBottomPanel.value = false
  router.push(path)
}

async function onLogout() {
  showBottomPanel.value = false
  await userStore.logout()
  router.push('/')
}

/** 点击主动 AI 指示器：双向 toggle AI 面板，展开时滚动到未读消息 */
function onProactiveClick() {
  const wasCollapsed = layout.aiCollapsed
  layout.toggleAi()
  // 仅在展开操作时触发滚动到未读消息
  if (wasCollapsed) {
    nextTick(() => {
      window.dispatchEvent(new CustomEvent('ai-scroll-to-unread'))
    })
  }
}

// 点击外部关闭底部面板
document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement
  if (!target.closest('.sb-bottom-panel')) {
    showBottomPanel.value = false
  }
})
</script>
