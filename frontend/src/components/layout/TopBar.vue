<template>
  <header class="topbar">
    <div class="topbar-main">
      <div class="topbar-left">
        <div class="brand" @click="router.push('/')">
          <div class="brand-mark">O</div>
          <span>Open Meeting Scribe</span>
        </div>
        <div class="topbar-divider"></div>
        <div class="topbar-title"><strong id="currentTaskTitle">{{ taskTitle }}</strong></div>
        <span class="state-pill" :class="statePillClass"><span class="pip"></span><span>{{ stateText }}</span></span>
      </div>
      <div class="topbar-right">
        <button class="update-badge" id="updateBadge" title="有新版本可用">
          <span class="ub-dot"></span>
          <span>更新可用</span>
        </button>
        <span class="rec-pill" :class="{ 'is-visible': showRecPill }" title="返回录音" @click="jumpBackToRecording">
          <span class="pip"></span><span>录音中</span>
        </span>
        <button class="topbar-new-btn" :class="{ 'is-hidden': isStartRoute }" @click="router.push('/')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>新建会议</span>
        </button>
        <button class="lang-btn" id="langBtn" title="转写语言" disabled>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          <span>中文</span>
        </button>

        <!-- 主题切换器 -->
        <div class="theme-switcher">
          <button class="theme-switcher-btn" @click="showThemeMenu = !showThemeMenu" title="切换主题">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>
            </svg>
          </button>
          <div class="theme-dropdown" :class="{ 'is-open': showThemeMenu }" role="listbox">
            <button v-for="t in themeOptions" :key="t.id" class="theme-option" :class="{ 'is-active': themeStore.current === t.id }" @click="selectTheme(t.id)">
              <span class="theme-swatch" :style="{ background: t.swatch }"></span>
              <span class="theme-option-label">{{ t.label }}</span>
              <svg v-if="themeStore.current === t.id" class="theme-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </button>
          </div>
        </div>

        <!-- 用户头像 -->
        <div class="user-avatar-wrapper" style="position:relative">
          <button v-if="userStore.isLoggedIn" class="user-avatar-btn" @click="showUserMenu = !showUserMenu" title="用户菜单">
            <span v-if="!userStore.user?.avatar_url">{{ userStore.avatarLetter }}</span>
            <img v-else :src="userStore.user.avatar_url" :alt="userStore.user.name" style="width:100%;height:100%;border-radius:50%;object-fit:cover">
          </button>
          <div class="user-menu" :class="{ 'is-open': showUserMenu }" role="menu">
            <div class="user-menu-header">
              <div class="user-menu-name">{{ userStore.displayName }}</div>
              <div class="user-menu-email">{{ userStore.user?.email || '' }}</div>
            </div>
            <button class="user-menu-item danger" @click="onLogout">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              退出登录
            </button>
          </div>
        </div>

        <!-- 视图模式切换器 -->
        <div class="view-switcher" role="toolbar">
          <button class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'full' }" data-view="full" title="全视图" @click="layout.setViewMode('full')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <rect x="1.5" y="2.5" width="3.5" height="11" rx="1"/><rect x="6.25" y="2.5" width="3.5" height="11" rx="1"/><rect x="11" y="2.5" width="3.5" height="11" rx="1"/>
            </svg>
          </button>
          <button class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'left' }" data-view="left" title="资源视图" @click="layout.setViewMode('left')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <rect x="1.5" y="2.5" width="4.5" height="11" rx="1" fill="currentColor" opacity="0.12"/><rect x="1.5" y="2.5" width="4.5" height="11" rx="1"/>
              <line x1="8.5" y1="5" x2="14.5" y2="5" opacity="0.3"/><line x1="8.5" y1="8" x2="13" y2="8" opacity="0.3"/><line x1="8.5" y1="11" x2="14.5" y2="11" opacity="0.3"/>
            </svg>
          </button>
          <button class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'right' }" data-view="right" title="对话视图" @click="layout.setViewMode('right')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <line x1="1.5" y1="5" x2="7.5" y2="5" opacity="0.3"/><line x1="1.5" y1="8" x2="6" y2="8" opacity="0.3"/><line x1="1.5" y1="11" x2="7.5" y2="11" opacity="0.3"/>
              <rect x="10" y="2.5" width="4.5" height="11" rx="1" fill="currentColor" opacity="0.12"/><rect x="10" y="2.5" width="4.5" height="11" rx="1"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 注册引导横幅（远程配置，未登录时显示） -->
    <div class="reg-guidance-banner" :class="{ 'is-hidden': !showRegBanner }">
      <div class="reg-guidance-content">
        <svg class="reg-guidance-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
        <span class="reg-guidance-text" v-html="regBannerContent"></span>
        <button v-if="regBannerCta" class="reg-guidance-cta" @click="onRegBannerCta">{{ regBannerCta }}</button>
        <button class="reg-guidance-dismiss" @click="dismissRegBanner" title="关闭提示">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useThemeStore, type ThemeId } from '@/stores/theme'
import { useTaskStore } from '@/stores/task'
import { useUserStore } from '@/stores/user'
import { useLayoutStore } from '@/stores/layout'
import { fetchAnnouncements, type Announcement } from '@/api/announcements'

const router = useRouter()
const route = useRoute()
const themeStore = useThemeStore()
const taskStore = useTaskStore()
const userStore = useUserStore()
const layout = useLayoutStore()

const showThemeMenu = ref(false)
const showUserMenu = ref(false)

// ─── 录音中指示 pill ───
const recordingTaskIds = computed(() =>
  taskStore.tasks.filter(t => t.status === 'recording').map(t => t.task_id)
)
const showRecPill = computed(() =>
  recordingTaskIds.value.length > 0 && route.name !== 'recording'
)

function jumpBackToRecording() {
  const recTask = taskStore.tasks.find(t => t.status === 'recording')
  if (recTask) {
    taskStore.selectTask(recTask.task_id)
    router.push({ name: 'recording', params: { taskId: recTask.task_id } })
  }
}

// ─── 注册引导横幅 ───
const showRegBanner = ref(false)
const regBannerContent = ref('')
const regBannerCta = ref('')
const regBannerUrl = ref('')
let currentRemoteMessage: Announcement | null = null

async function loadRegBanner() {
  if (userStore.isLoggedIn) {
    showRegBanner.value = false
    return
  }
  try {
    const messages = await fetchAnnouncements()
    const bannerMsg = messages.find(m => m.type === 'banner')
    if (!bannerMsg) {
      showRegBanner.value = false
      return
    }
    // 检查是否已被用户关闭（session 级别）
    if (sessionStorage.getItem('reg_banner_dismissed_' + bannerMsg.id)) {
      showRegBanner.value = false
      return
    }
    currentRemoteMessage = bannerMsg
    regBannerContent.value = bannerMsg.content || ''
    regBannerCta.value = bannerMsg.cta_text || ''
    regBannerUrl.value = bannerMsg.cta_url || ''
    showRegBanner.value = true
  } catch {
    showRegBanner.value = false
  }
}

function dismissRegBanner() {
  showRegBanner.value = false
  if (currentRemoteMessage) {
    sessionStorage.setItem('reg_banner_dismissed_' + currentRemoteMessage.id, '1')
  }
}

function onRegBannerCta() {
  if (regBannerUrl.value) {
    let url = regBannerUrl.value.trim()
    if (url && !/^https?:\/\//i.test(url)) url = 'https://' + url
    window.open(url, '_blank')
  }
}

watch(() => userStore.isLoggedIn, loadRegBanner)

const themeOptions = [
  { id: 'default' as ThemeId, label: '默认', swatch: 'oklch(58% 0.18 255)' },
  { id: 'dark' as ThemeId, label: '夜色', swatch: 'oklch(17% 0.010 250)' },
  { id: 'warm' as ThemeId, label: '暖阳', swatch: 'oklch(62% 0.20 40)' },
  { id: 'forest' as ThemeId, label: '森林', swatch: 'oklch(52% 0.14 150)' },
  { id: 'ocean' as ThemeId, label: '海洋', swatch: 'oklch(56% 0.14 210)' },
  { id: 'lavender' as ThemeId, label: '薰衣草', swatch: 'oklch(60% 0.16 285)' },
  { id: 'rose' as ThemeId, label: '玫瑰', swatch: 'oklch(60% 0.20 10)' },
]

const isStartRoute = computed(() => route.name === 'start')
const taskTitle = computed(() => taskStore.currentTask?.title || taskStore.currentTask?.audio_name || '')
const stateText = computed(() => {
  const t = taskStore.currentTask
  if (!t) return '空闲'
  return taskStore.getStatusLabel(t.status)
})
const statePillClass = computed(() => {
  const t = taskStore.currentTask
  if (!t) return ''
  const map: Record<string, string> = {
    recording: 'is-rec', transcribing: 'is-proc', summarizing: 'is-proc',
    completed: 'is-done', failed: 'is-fail', pending: 'is-pending',
    awaiting_mapping: 'is-map',
  }
  return map[t.status] || ''
})

function selectTheme(id: ThemeId) {
  themeStore.setTheme(id)
  showThemeMenu.value = false
}

async function onLogout() {
  showUserMenu.value = false
  await userStore.logout()
  router.push('/')
}

// 点击外部关闭菜单
onMounted(() => {
  loadRegBanner()
})

document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement
  if (!target.closest('.theme-switcher')) showThemeMenu.value = false
  if (!target.closest('.user-avatar-wrapper')) showUserMenu.value = false
})
</script>
