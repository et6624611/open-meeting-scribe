<template>
  <nav class="activity-rail">
    <!-- 顶部：Sidebar 折叠/展开 / Top: Sidebar collapse/expand -->
    <div class="ar-top">
      <!-- 企业形态空间切换器（P1-WP1，UI 规格 §1.1：侧栏顶部常驻） -->
      <SpaceSwitcher v-if="isEnterprise" />
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
      <!-- 企业形态隐藏（产品 cmsg_01m63m8f1zb261meqx14xsqs9k：无服务端承接，不渲染不解释） -->
      <IconButton
        v-if="!isEnterprise"
        class="ar-btn"
        :class="{ 'is-active': route.name === 'projects' }"
        :label="t('sidebar.rail_projects')"
        tip-position="right"
        @click="navigate('/projects')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
      </IconButton>
      <!-- 词表解禁批（窗口 D 后，PM 排程）：段五端点已在服——团队空间热词=共享词表（§5.3），
           发言人=U4 裁决维持只读窗口不升共享级；两入口恢复渲染 -->
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
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5h6l5 5v11a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5z"/><path d="M14 5v6h6"/></svg>
      </IconButton>
      <!-- 个人版=本地决策面板；企业形态=团队空间决策聚合（P1-WP-3 承接"决策面板回归"；私有空间不渲染） -->
      <IconButton
        v-if="!isEnterprise || space.isTeamSpace"
        class="ar-btn"
        :class="{ 'is-active': route.name === 'decisions' }"
        :label="t('sidebar.rail_decisions')"
        tip-position="right"
        @click="navigate('/decisions')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M8 21h8"/><path d="M5 7h14"/><path d="M5 7 2.5 13a3 3 0 0 0 5 0L5 7z"/><path d="M19 7l-2.5 6a3 3 0 0 0 5 0L19 7z"/><path d="M12 3l7 4"/><path d="M12 3 5 7"/></svg>
      </IconButton>
      <!-- 团队空间：变更记录（全员可见的轻量操作记录，规格 §7/Q4 信任透明） -->
      <IconButton
        v-if="isEnterprise && space.isTeamSpace"
        class="ar-btn"
        :class="{ 'is-active': route.name === 'changes' }"
        :label="t('sidebar.rail_changes')"
        tip-position="right"
        @click="navigate('/changes')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/></svg>
      </IconButton>
      <!-- 团队空间·管理员：成员管理（规格 §3 可编辑成员无此入口=不渲染不解释） -->
      <IconButton
        v-if="isEnterprise && space.isTeamSpace && space.isTeamAdmin"
        class="ar-btn"
        :class="{ 'is-active': route.name === 'members' }"
        :label="t('sidebar.rail_members')"
        tip-position="right"
        @click="navigate('/members')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6"/><path d="M22 11h-6"/></svg>
      </IconButton>
      <!-- 企业形态隐藏（产品 cmsg_01m63m8f1zb261meqx14xsqs9k：无服务端承接，不渲染不解释） -->
      <IconButton
        v-if="!isEnterprise"
        class="ar-btn"
        :class="{ 'is-active': route.name === 'agents' }"
        :label="t('sidebar.rail_agents')"
        tip-position="right"
        @click="navigate('/agents')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3z"/></svg>
      </IconButton>
    </div>

    <!-- 底部：设置 / Bottom: settings（规格 §1.2：设置=设备属性，团队空间不出现） -->
    <div class="ar-bottom">
      <!-- 设置按钮（tooltip 含版本号） / Settings button (tooltip includes version) -->
      <IconButton
        v-if="!isEnterprise || !space.isTeamSpace"
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
import { isEnterprise } from '@/edition'
import { useSpaceStore } from '@/stores/space'
import { useI18n } from 'vue-i18n'
import { useLayoutStore } from '@/stores/layout'
import IconButton from '@/components/common/IconButton.vue'
import SpaceSwitcher from '@/components/layout/SpaceSwitcher.vue'
import { modKey } from '@/utils/platform'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const layout = useLayoutStore()
const space = useSpaceStore()

/** 应用版本号（与 Sidebar 原版本号一致） / App version (consistent with Sidebar version) */
const appVersion = 'v2.0.0'

/** Rail navigation pages that should record origin before navigating / Rail 导航页（跳转前需记录来源） */
const RAIL_NAV_PAGES = new Set(['/library', '/projects', '/speakers', '/hotwords', '/agents', '/decisions', '/changes', '/members', '/settings'])

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
