<template>
  <nav class="activity-rail">
    <!-- 顶部：Sidebar 折叠/展开 / Top: Sidebar collapse/expand -->
    <div class="ar-top">
      <IconButton
        class="ar-btn ar-toggle-btn"
        :class="{ 'is-collapsed': layout.sidebarCollapsed }"
        :label="t('sidebar.rail_toggle_sidebar') + ` (${modKey}B)`"
        tip-position="right"
        @click="layout.toggleSidebar()"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline class="ar-toggle-arrow" points="15 18 9 12 15 6"/>
          <polyline class="ar-toggle-arrow" points="19 18 13 12 19 6"/>
        </svg>
      </IconButton>
    </div>

    <!-- 中部：导航图标组 / Middle: Navigation icon group -->
    <div class="ar-nav">
      <IconButton
        class="ar-btn"
        :class="{ 'is-active': route.name === 'library' }"
        :label="t('sidebar.rail_meetings')"
        tip-position="right"
        @click="navigate('/library')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
      </IconButton>
      <IconButton
        class="ar-btn"
        :class="{ 'is-active': route.name === 'projects' }"
        :label="t('sidebar.rail_projects')"
        tip-position="right"
        @click="navigate('/projects')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
      </IconButton>
      <IconButton
        class="ar-btn"
        :class="{ 'is-active': route.name === 'speakers' }"
        :label="t('sidebar.rail_speakers')"
        tip-position="right"
        @click="navigate('/speakers')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      </IconButton>
      <IconButton
        class="ar-btn"
        :class="{ 'is-active': route.name === 'hotwords' }"
        :label="t('sidebar.rail_hotwords')"
        tip-position="right"
        @click="navigate('/hotwords')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3q1 4 4 6.5t3 5.5a1 1 0 0 1-14 0 5 5 0 0 1 1-3 1 1 0 0 0 5 0c0-2-1.5-3-1.5-5q0-2 2.5-4"/></svg>
      </IconButton>
      <IconButton
        class="ar-btn"
        :class="{ 'is-active': route.name === 'decisions' }"
        :label="t('sidebar.rail_decisions')"
        tip-position="right"
        @click="navigate('/decisions')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M8 21h8"/><path d="M5 7h14"/><path d="M5 7 2.5 13a3 3 0 0 0 5 0L5 7z"/><path d="M19 7l-2.5 6a3 3 0 0 0 5 0L19 7z"/><path d="M12 3l7 4"/><path d="M12 3 5 7"/></svg>
      </IconButton>
      <IconButton
        class="ar-btn"
        :class="{ 'is-active': route.name === 'agents' }"
        :label="t('sidebar.rail_agents')"
        tip-position="right"
        @click="navigate('/agents')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
      </IconButton>
      <IconButton
        class="ar-btn"
        :class="{ 'is-active': route.name === 'memory' }"
        :label="t('sidebar.rail_memory')"
        tip-position="right"
        @click="navigate('/memory')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z"/><path d="M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z"/><path d="M16 17h4"/><path d="M4 13h4"/></svg>
      </IconButton>
    </div>

    <!-- 底部：设置 / Bottom: settings -->
    <div class="ar-bottom">
      <!-- 设置按钮（tooltip 含版本号） / Settings button (tooltip includes version) -->
      <IconButton
        class="ar-btn ar-settings"
        :class="{ 'is-active': route.name === 'settings' }"
        :label="t('sidebar.rail_settings_version', { version: appVersion })"
        tip-position="right"
        @click="navigate('/settings')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1.1a1.7 1.7 0 0 0-1.8.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1.1a2 2 0 1 1 2.8 2.8l.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>
      </IconButton>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLayoutStore } from '@/stores/layout'
import IconButton from '@/components/common/IconButton.vue'
import { modKey } from '@/utils/platform'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const layout = useLayoutStore()

/** 应用版本号（与 Sidebar 原版本号一致） / App version (consistent with Sidebar version) */
const appVersion = 'v2.0.0'

/** Rail navigation pages that should record origin before navigating / Rail 导航页（跳转前需记录来源） */
const RAIL_NAV_PAGES = new Set(['/library', '/projects', '/speakers', '/hotwords', '/agents', '/decisions', '/memory', '/settings'])

/** Origin route before entering a secondary page, for toggle-back / 进入二级管理页前的来源路径 */
const previousRoute = ref('')

/**
 * Navigate with smart toggle-back.
 * - Before entering a rail nav page, record the current route as origin.
 * - Re-clicking an active button toggles back to the origin page
 *   (recording / meeting / start), falling back to '/' if no valid origin.
 */
function navigate(path: string) {
  if (route.path === path) {
    // Toggle-back: for all rail navigation pages
    if (RAIL_NAV_PAGES.has(path)) {
      const origin = previousRoute.value
      const target = origin && (origin.startsWith('/recording') || origin.startsWith('/meeting') || origin === '/')
        ? origin
        : '/'
      // 目标与当前路径相同（重复导航）→ 视为无操作仅清理，避免静默的 NavigationDuplicated
      // Duplicate navigation would reject silently (button “does nothing”); skip it, only clear origin.
      if (target !== route.path) router.push(target).catch(() => {})
      previousRoute.value = ''
    }
    return
  }
  // Record origin before entering a rail nav page
  if (RAIL_NAV_PAGES.has(path)) {
    previousRoute.value = route.fullPath
  }
  router.push(path).catch(() => {})
}
</script>
