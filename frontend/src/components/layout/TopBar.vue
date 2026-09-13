<template>
  <header class="topbar">
    <div class="topbar-main">
      <div class="topbar-left">
        <div class="brand" @click="router.push('/')">
          <div class="brand-mark">
            <svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="4" y="4" width="48" height="48" rx="16" fill="var(--fg)"/>
              <circle cx="28" cy="28" r="13" stroke="var(--bg)" stroke-width="7" fill="none"/>
            </svg>
          </div>
          <span>Open Meeting Scribe</span>
        </div>
        <template v-if="showTaskInfo">
          <div class="topbar-divider"></div>
          <div class="topbar-title"><strong id="currentTaskTitle">{{ taskTitle }}</strong></div>
          <span v-if="showStatePill" class="state-pill" :class="statePillClass"><span class="pip"></span><span>{{ stateText }}</span></span>
        </template>
      </div>
      <div class="topbar-right">
        <button class="update-badge" id="updateBadge" :title="t('common.update.title')">
          <span class="ub-dot"></span>
          <span>{{ t('common.update.available') }}</span>
        </button>
        <!-- 全局播放 pill：不在会议纪要页时承接音频控制（借鉴录音 pill 形态） -->
        <div class="player-pill" :class="{ 'is-paused': !player.playing }" v-if="showPlayerPill">
          <PlayingEq :playing="player.playing" />
          <span class="pp-title" :title="playerTaskTitle" @click="openPlayerTask">{{ playerTaskTitle }}</span>
          <span class="pp-time">{{ player.timeStr }}</span>
          <div class="pp-progress" :title="t('topbar.player_seek')" @click="onSeekPlayer">
            <div class="pp-progress-fill" :style="{ width: player.progress + '%' }"></div>
          </div>
          <button class="pp-btn" @click.stop="player.toggle()" :title="player.playing ? t('topbar.player_pause') : t('topbar.player_play')">
            <svg v-if="!player.playing" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
          </button>
          <button class="pp-btn pp-speed" @click.stop="player.cycleSpeed()" :title="t('topbar.player_speed')">{{ player.speed }}×</button>
          <button class="pp-btn" @click.stop="openPlayerTask" :title="t('topbar.player_open')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
          <button class="pp-btn" @click.stop="player.stop()" :title="t('topbar.player_stop')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="rec-pill" :class="{ 'is-visible': showRecPill, 'is-paused': isRecPaused }" v-if="showRecPill">
          <!-- 波形动画 -->
          <div class="rec-waveform" @click.stop>
            <span class="rw-bar"></span>
            <span class="rw-bar"></span>
            <span class="rw-bar"></span>
          </div>
          <!-- 计时器 -->
          <span class="rec-timer">{{ recElapsed }}</span>
          <!-- 暂停/恢复按钮（药丸形，与底部控制栏一致） -->
          <button class="rec-pause-btn" @click.stop="onToggleRecPause" :title="isRecPaused ? t('topbar.rec_resume_title') : t('topbar.rec_pause_title')">
            <svg v-if="!isRecPaused" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
            <span class="rec-pause-text">{{ isRecPaused ? t('topbar.rec_resume') : t('topbar.rec_pause') }}</span>
          </button>
          <!-- 结束按钮 -->
          <button class="rec-end-btn" @click.stop="onStopRecording" :title="t('topbar.rec_end_title')">{{ t('topbar.rec_end') }}</button>
          <!-- 更多操作菜单 -->
          <div class="rec-more-wrap">
            <button ref="recMoreBtn" class="rec-more-btn" @click="toggleRecMore" :title="t('topbar.rec_more')" aria-haspopup="menu" :aria-label="t('topbar.rec_more_label')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
            </button>
            <div ref="recDropdown" class="rec-more-dropdown" :class="{ 'is-open': showRecMore }" role="menu">
              <button class="rec-more-item danger" @click="closeRecMore(); showAbandon = true" role="menuitem">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                {{ t('topbar.rec_abandon') }}
              </button>
            </div>
          </div>
        </div>

        <!-- 放弃录音确认弹窗 -->
        <div class="abandon-overlay" data-vue-overlay :class="{ 'is-open': showAbandon }" v-if="showAbandon">
          <div class="abandon-dialog">
            <div class="abandon-dialog-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </div>
            <div class="abandon-dialog-title">{{ t('topbar.abandon_title') }}</div>
            <div class="abandon-dialog-desc">{{ t('topbar.abandon_desc') }}</div>
            <div class="abandon-dialog-info">{{ t('topbar.abandon_duration', { elapsed: recElapsed }) }}</div>
            <div class="abandon-dialog-actions">
              <button class="btn-cancel" @click="showAbandon = false">{{ t('topbar.abandon_cancel') }}</button>
              <button class="btn-confirm-abandon" @click="onAbandonRecording">{{ t('topbar.abandon_confirm') }}</button>
            </div>
          </div>
        </div>
        <button
          class="topbar-new-btn"
          :class="{ 'is-hidden': isStartRoute || showRecPill, 'is-disabled': hasRecordingTask }"
          :title="hasRecordingTask ? t('topbar.recording_in_progress', { elapsed: recElapsed }) : t('topbar.new_meeting')"
          @click="hasRecordingTask ? jumpBackToRecording() : router.push('/')"
        >
          <svg v-if="hasRecordingTask" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>{{ hasRecordingTask ? t('topbar.return_record') : t('topbar.new_meeting') }}</span>
        </button>
        <div class="lang-switcher">
          <button class="lang-btn" id="langBtn" :title="t('topbar.lang_switch')" @click="showLangMenu = !showLangMenu">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            <span>{{ currentLangLabel }}</span>
            <svg class="lang-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div class="lang-dropdown" :class="{ 'is-open': showLangMenu }" role="listbox">
            <button v-for="lang in langOptions" :key="lang.code" class="lang-option" :class="{ 'is-active': currentLocale === lang.code }" role="option" :aria-selected="currentLocale === lang.code" @click="onSwitchLang(lang.code); showLangMenu = false">
              {{ lang.label }}
              <svg v-if="currentLocale === lang.code" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            </button>
          </div>
        </div>

        <!-- 主题切换器 -->
        <div class="theme-switcher">
          <IconButton class="theme-switcher-btn" :label="t('common.theme.switch')" tip-position="bottom" @click="showThemeMenu = !showThemeMenu">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>
            </svg>
          </IconButton>
          <div class="theme-dropdown" :class="{ 'is-open': showThemeMenu }" role="listbox">
            <button v-for="theme in themeOptions" :key="theme.id" class="theme-option" :class="{ 'is-active': themeStore.current === theme.id }" :title="theme.label" @click="selectTheme(theme.id)">
              <span class="theme-swatch" :style="{ background: theme.swatch }"></span>
              <span class="theme-option-label">{{ theme.label }}</span>
              <svg v-if="themeStore.current === theme.id" class="theme-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </button>
          </div>
        </div>

        <!-- 用户头像 -->
        <div class="user-avatar-wrapper" style="position:relative">
          <button v-if="userStore.isLoggedIn" class="user-avatar-btn" @click="showUserMenu = !showUserMenu" :title="t('topbar.user_menu')">
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
              {{ t('topbar.logout') }}
            </button>
          </div>
        </div>

        <!-- 视图模式切换器 -->
        <div class="view-switcher" role="toolbar">
          <IconButton class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'full' }" :label="t('common.view_mode.full')" tip-position="bottom" :active="layout.viewMode === 'full'" data-view="full" @click="layout.setViewMode('full')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <rect x="1.5" y="2.5" width="3.5" height="11" rx="1"/><rect x="6.25" y="2.5" width="3.5" height="11" rx="1"/><rect x="11" y="2.5" width="3.5" height="11" rx="1"/>
            </svg>
          </IconButton>
          <IconButton class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'left' }" :label="t('common.view_mode.left')" tip-position="bottom" :active="layout.viewMode === 'left'" data-view="left" @click="layout.setViewMode('left')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <rect x="1.5" y="2.5" width="4.5" height="11" rx="1" fill="currentColor" opacity="0.12"/><rect x="1.5" y="2.5" width="4.5" height="11" rx="1"/>
              <line x1="8.5" y1="5" x2="14.5" y2="5" opacity="0.3"/><line x1="8.5" y1="8" x2="13" y2="8" opacity="0.3"/><line x1="8.5" y1="11" x2="14.5" y2="11" opacity="0.3"/>
            </svg>
          </IconButton>
          <IconButton class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'right' }" :label="t('common.view_mode.right')" tip-position="bottom" :active="layout.viewMode === 'right'" data-view="right" @click="layout.setViewMode('right')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <line x1="1.5" y1="5" x2="7.5" y2="5" opacity="0.3"/><line x1="1.5" y1="8" x2="6" y2="8" opacity="0.3"/><line x1="1.5" y1="11" x2="7.5" y2="11" opacity="0.3"/>
              <rect x="10" y="2.5" width="4.5" height="11" rx="1" fill="currentColor" opacity="0.12"/><rect x="10" y="2.5" width="4.5" height="11" rx="1"/>
            </svg>
          </IconButton>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useThemeStore, type ThemeId } from '@/stores/theme'
import { useTaskStore } from '@/stores/task'
import { useUserStore } from '@/stores/user'
import { useLayoutStore } from '@/stores/layout'
import { usePlayerStore } from '@/stores/player'
import IconButton from '@/components/common/IconButton.vue'
import PlayingEq from '@/components/common/PlayingEq.vue'
import { usePopMenu } from '@/composables/usePopMenu'
import { useEscClose } from '@/composables/useEscClose'
import { setI18nLocale, getLocale, type SupportedLocale } from '@/i18n'
import { getRecordStatus } from '@/api/record'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const themeStore = useThemeStore()
const taskStore = useTaskStore()
const userStore = useUserStore()
const layout = useLayoutStore()
const player = usePlayerStore()

// ─── 全局播放 pill（会议纪要页自带音频条，不叠加）───
const showPlayerPill = computed(() => !!player.taskId && route.name !== 'generating')
const playerTaskTitle = computed(() => {
  const task = taskStore.tasks.find(item => item.task_id === player.taskId)
  return task?.title || task?.audio_name || t('topbar.player_default_title')
})

function openPlayerTask() {
  if (player.taskId) router.push({ name: 'generating', params: { taskId: player.taskId } })
}

function onSeekPlayer(e: MouseEvent) {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  player.seekPercent(((e.clientX - rect.left) / rect.width) * 100)
}

const showThemeMenu = ref(false)
const showUserMenu = ref(false)
const showLangMenu = ref(false)

// ─── 语言切换 ───
const currentLocale = computed(() => getLocale())
const langOptions: { code: SupportedLocale; label: string }[] = [
  { code: 'zh-CN', label: '中文' },
  { code: 'en', label: 'English' },
]
const currentLangLabel = computed(() => langOptions.find(l => l.code === currentLocale.value)?.label ?? '中文')
async function onSwitchLang(locale: SupportedLocale) {
  await setI18nLocale(locale)
}

// ─ 录音中指示 pill（更多菜单）───
const recMoreBtn = ref<HTMLElement | null>(null)
const recDropdown = ref<HTMLElement | null>(null)
const { visible: showRecMore, toggle: toggleRecMore, close: closeRecMore } = usePopMenu(recDropdown, recMoreBtn)
const showAbandon = ref(false)
useEscClose(showAbandon, () => { showAbandon.value = false })

// ─── 录音中指示 pill ───
// 会议相关路由的状态由页面自身承载（录音页头部/控制栏），顶栏不叠加录音中胶囊
const MEETING_ROUTES = ['recording', 'generating']

/** 是否存在录音中的任务（24 小时内创建且状态为 recording/paused） */
const hasRecordingTask = computed(() => {
  const now = new Date()
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  
  return taskStore.tasks.some(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    const createdAt = t.created_at ? new Date(t.created_at) : null
    if (createdAt && createdAt < oneDayAgo) return false
    return true
  })
})

const showRecPill = computed(() => {
  if (!hasRecordingTask.value) return false
  // 仅在「正在录音的那个任务」自身的页面中隐藏（页面已承载完整 UI）
  // 查看其他任务的纪要/转写时，rec-pill 仍需显示以提示录音进行中
  const currentTaskId = route.params.taskId as string | undefined
  return !currentTaskId || currentTaskId !== recTask.value?.task_id
})

function jumpBackToRecording() {
  const recTask = taskStore.tasks.find(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    const createdAt = t.created_at ? new Date(t.created_at) : null
    const now = new Date()
    const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)
    if (createdAt && createdAt < oneDayAgo) return false
    return true
  })
  if (recTask) {
    taskStore.selectTask(recTask.task_id)
    router.push({ name: 'recording', params: { taskId: recTask.task_id } })
  }
}

// ─── 录音计时器（独立于 RecordingView，离开录音页后仍运行）───
const recElapsed = ref('00:00')
let recTimer: ReturnType<typeof setInterval> | null = null
let recElapsedSec = 0

const recTask = computed(() => {
  const now = new Date()
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  
  return taskStore.tasks.find(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    const createdAt = t.created_at ? new Date(t.created_at) : null
    if (createdAt && createdAt < oneDayAgo) return false
    return true
  }) ?? null
})
const isRecPaused = computed(() => recTask.value?.status === 'paused')

function formatRecTime(totalSec: number): string {
  const s = Math.floor(totalSec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

/** 基于任务 created_at 计算已过秒数（页面刷新后仍能还原） */
function calcElapsedFromTask(task: { created_at?: string }): number {
  if (!task?.created_at) return 0
  const created = new Date(task.created_at).getTime()
  return Math.max(0, Math.floor((Date.now() - created) / 1000))
}

function tickRecTimer() {
  recElapsedSec++
  recElapsed.value = formatRecTime(recElapsedSec)
}

function startRecTimer() {
  if (recTimer) return
  recTimer = setInterval(tickRecTimer, 1000)
}

function stopRecTimer() {
  if (recTimer) { clearInterval(recTimer); recTimer = null }
}

watch(recTask, async (task) => {
  if (task) {
    // 优先从后端获取精确已过时长（已扣除暂停），失败则回退到 created_at 估算
    try {
      const status = await getRecordStatus()
      if (status.recording && status.elapsed != null) {
        recElapsedSec = Math.floor(status.elapsed)
      } else {
        recElapsedSec = calcElapsedFromTask(task)
      }
    } catch {
      recElapsedSec = calcElapsedFromTask(task)
    }
    recElapsed.value = formatRecTime(recElapsedSec)
    if (task.status === 'paused') {
      // 暂停中：冻结计时器，保留已过时长
      stopRecTimer()
    } else {
      startRecTimer()
    }
  } else {
    stopRecTimer(); recElapsedSec = 0; recElapsed.value = '00:00'
  }
}, { immediate: true })

watch(isRecPaused, (paused) => {
  if (paused) {
    // 暂停：冻结当前已过时长，停止自增
    stopRecTimer()
  } else if (recTask.value) {
    // 恢复：从冻结值继续
    startRecTimer()
  }
})

async function onToggleRecPause() {
  try {
    if (isRecPaused.value) {
      await taskStore.resumeRecording()
    } else {
      await taskStore.pauseRecording()
    }
  } catch { /* store 已打印错误 */ }
}

async function onStopRecording() {
  const recTask = taskStore.tasks.find(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    const createdAt = t.created_at ? new Date(t.created_at) : null
    const now = new Date()
    const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)
    if (createdAt && createdAt < oneDayAgo) return false
    return true
  })
  if (recTask) {
    try {
      await taskStore.stopRecording(recTask.task_id)
      // [状态同步] 停止录音后刷新任务列表
      await taskStore.loadTasks()
      router.push({ name: 'generating', params: { taskId: recTask.task_id } })
    } catch (e) {
      console.error('stop recording failed:', e)
    }
  }
}

async function onAbandonRecording() {
  showAbandon.value = false
  closeRecMore()
  const recTask = taskStore.tasks.find(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    const createdAt = t.created_at ? new Date(t.created_at) : null
    const now = new Date()
    const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)
    if (createdAt && createdAt < oneDayAgo) return false
    return true
  })
  if (recTask) {
    try {
      await taskStore.abandonRecording(recTask.task_id)
      // [状态同步] 放弃录音后刷新任务列表
      await taskStore.loadTasks()
    } catch (e) {
      console.error('abandon recording failed:', e)
    }
  }
}


const themeOptions = [
  { id: 'default' as ThemeId, label: t('common.theme.default'), swatch: 'oklch(58% 0.18 255)' },
  { id: 'dark' as ThemeId, label: t('common.theme.dark'), swatch: 'oklch(17% 0.010 250)' },
  { id: 'warm' as ThemeId, label: t('common.theme.warm'), swatch: 'oklch(62% 0.20 40)' },
  { id: 'forest' as ThemeId, label: t('common.theme.forest'), swatch: 'oklch(52% 0.14 150)' },
  { id: 'ocean' as ThemeId, label: t('common.theme.ocean'), swatch: 'oklch(56% 0.14 210)' },
  { id: 'lavender' as ThemeId, label: t('common.theme.lavender'), swatch: 'oklch(60% 0.16 285)' },
  { id: 'rose' as ThemeId, label: t('common.theme.rose'), swatch: 'oklch(60% 0.20 10)' },
]

const isStartRoute = computed(() => route.name === 'start')

/** 只在会议相关路由显示任务信息 */
const showTaskInfo = computed(() => MEETING_ROUTES.includes(route.name as string) && !!taskStore.currentTask)
/** 录音中状态不在顶栏重复显示：录音页由视图头部/控制栏承载，非会议页由右上角 rec-pill 承载 */
const showStatePill = computed(() => {
  const s = taskStore.currentTask?.status
  return showTaskInfo.value && s !== 'recording' && s !== 'paused'
})

const taskTitle = computed(() => taskStore.currentTask?.title || taskStore.currentTask?.audio_name || '')
const stateText = computed(() => {
  const task = taskStore.currentTask
  if (!task) return t('common.status.idle')
  return taskStore.getStatusLabel(task.status)
})
const statePillClass = computed(() => {
  const task = taskStore.currentTask
  if (!task) return ''
  const map: Record<string, string> = {
    recording: 'is-rec', paused: 'is-rec', processing: 'is-proc', transcribing: 'is-proc', summarizing: 'is-proc',
    completed: 'is-done', failed: 'is-fail', pending: 'is-pending',
    awaiting_mapping: 'is-map',
  }
  return map[task.status] || ''
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


onUnmounted(() => {
  stopRecTimer()
})

document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement
  if (!target.closest('.theme-switcher')) showThemeMenu.value = false
  if (!target.closest('.user-avatar-wrapper')) showUserMenu.value = false
  if (!target.closest('.lang-switcher')) showLangMenu.value = false
})
</script>
