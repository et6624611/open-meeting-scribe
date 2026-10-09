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
        <!-- 引擎/接入状态已统一收敛至底部状态栏 footer.status（单处显示，避免顶栏与底部两处并存且表达不一致） -->
        <button class="update-badge" id="updateBadge" :title="t('common.update.title')">
          <span class="ub-dot"></span>
          <span>{{ t('common.update.available') }}</span>
        </button>
        <!-- 全局播放 pill：不在会议纪要页时承接音频控制（借鉴录音 pill 形态） / Global player pill: takes over audio control when not on meeting minutes page (borrowed from recording pill form) -->
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
        <!-- 录音状态胶囊（方案 A：极简胶囊 + 展开面板） / Recording status pill (Plan A: minimal pill + expandable panel) -->
        <div class="rec-pill" :class="{ 'is-visible': showRecPill, 'is-paused': isRecPaused, 'is-expanded': showRecPanel }" v-if="showRecPill">
          <!-- 触发按钮：脉冲点 + 计时 + 展开箭头 / Trigger: pulse dot + timer + chevron -->
          <button ref="recPillTrigger" class="rec-pill-trigger" v-bind="recPanelTriggerAttrs" @click="toggleRecPanel" :title="t('topbar.rec_panel_toggle')">
            <span class="rec-pulse-dot"></span>
            <span class="rec-pill-timer">{{ recElapsed }}</span>
            <svg class="rec-pill-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <!-- 展开面板：状态头 + 导航/切换 + 终止类操作 / Expandable panel: status header + nav/toggle + termination actions -->
          <div ref="recPanelEl" class="rec-pill-panel" v-bind="recPanelMenuAttrs" :class="{ 'is-open': showRecPanel }">
            <div class="rec-panel-header">
              <span class="rec-pulse-dot"></span>
              <span class="rec-panel-label">{{ isRecPaused ? t('topbar.rec_paused_label') : t('topbar.rec_status_label') }}</span>
              <span class="rec-panel-timer">{{ recElapsed }}</span>
            </div>
            <div class="rec-panel-actions">
              <button class="rec-panel-btn" @click="closeRecPanel(); jumpBackToRecording()" role="menuitem">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14l-4-4 4-4"/><path d="M5 10h11a4 4 0 0 1 0 8h-1"/></svg>
                {{ t('topbar.rec_return_page') }}
              </button>
              <button class="rec-panel-btn" @click="closeRecPanel(); onToggleRecPause()" role="menuitem">
                <svg v-if="!isRecPaused" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
                <svg v-else viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
                {{ isRecPaused ? t('topbar.rec_resume_title') : t('topbar.rec_pause_title') }}
              </button>
              <div class="rec-panel-separator"></div>
              <button class="rec-panel-btn" @click="closeRecPanel(); onStopRecording()" role="menuitem">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
                {{ t('topbar.rec_end_title') }}
              </button>
              <button class="rec-panel-btn danger" @click="closeRecPanel(); showAbandon = true" role="menuitem">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                {{ t('topbar.rec_abandon') }}
              </button>
            </div>
          </div>
        </div>

        <!-- 放弃录音确认弹窗 / Abandon recording confirmation dialog -->
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
          :class="{ 'is-hidden': isStartRoute || showRecPill || isOnRecTaskPage }"
          :title="t('topbar.new_meeting') + ` (${modKey}N)`"
          @click="router.push('/')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>{{ t('topbar.new_meeting') }}</span>
          <kbd class="topbar-shortcut-kbd">{{ modKey }}N</kbd>
        </button>
        <div class="lang-switcher">
          <button class="lang-btn" id="langBtn" :title="t('topbar.lang_switch')" :aria-expanded="showLangMenu" aria-haspopup="listbox" @click="showLangMenu = !showLangMenu">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          </button>
          <div class="lang-dropdown" :class="{ 'is-open': showLangMenu }" role="listbox">
            <button v-for="lang in langOptions" :key="lang.code" class="lang-option" :class="{ 'is-active': currentLocale === lang.code }" role="option" :aria-selected="currentLocale === lang.code" @click="onSwitchLang(lang.code); showLangMenu = false">
              {{ lang.label }}
              <svg v-if="currentLocale === lang.code" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            </button>
          </div>
        </div>

        <!-- 主题切换器 / Theme switcher -->
        <div class="theme-switcher">
          <IconButton class="theme-switcher-btn" :label="t('common.theme.switch')" tip-position="bottom" :aria-expanded="showThemeMenu" aria-haspopup="listbox" @click="showThemeMenu = !showThemeMenu">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>
            </svg>
          </IconButton>
          <div class="theme-dropdown" :class="{ 'is-open': showThemeMenu }" role="listbox" @mouseleave="themeStore.restoreTheme()">
            <div class="theme-group-label">{{ t('common.theme.group_standard') }}</div>
            <button v-for="theme in standardThemes" :key="theme.id" class="theme-option" :class="{ 'is-active': themeStore.current === theme.id }" :title="theme.label" @mouseenter="themeStore.previewTheme(theme.id)" @focus="themeStore.previewTheme(theme.id)" @click="selectTheme(theme.id)">
              <span class="theme-swatch" :style="{ background: theme.swatch }"></span>
              <span class="theme-option-label">{{ theme.label }}</span>
              <svg v-if="themeStore.current === theme.id" class="theme-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </button>
            <div class="theme-group-divider"></div>
            <div class="theme-group-label">{{ t('common.theme.group_nature') }}</div>
            <button v-for="theme in natureThemes" :key="theme.id" class="theme-option" :class="{ 'is-active': themeStore.current === theme.id }" :title="theme.label" @mouseenter="themeStore.previewTheme(theme.id)" @focus="themeStore.previewTheme(theme.id)" @click="selectTheme(theme.id)">
              <span class="theme-swatch" :style="{ background: theme.swatch }"></span>
              <span class="theme-option-label">{{ theme.label }}</span>
              <svg v-if="themeStore.current === theme.id" class="theme-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </button>
          </div>
        </div>

        <!-- 视图模式切换器 / View mode switcher -->
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
import { useLayoutStore } from '@/stores/layout'
import { usePlayerStore } from '@/stores/player'
import IconButton from '@/components/common/IconButton.vue'
import PlayingEq from '@/components/common/PlayingEq.vue'
import { usePopMenu } from '@/composables/usePopMenu'
import { useEscClose } from '@/composables/useEscClose'
import { showToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import { setI18nLocale, getLocale, type SupportedLocale } from '@/i18n'
import { getRecordStatus } from '@/api/record'
import { modKey } from '@/utils/platform'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const themeStore = useThemeStore()
const taskStore = useTaskStore()
const layout = useLayoutStore()
const player = usePlayerStore()

// ─── 全局播放 pill（会议纪要页自带音频条，不叠加） / Global player pill (minutes page has its own audio bar, no overlap) ───
const showPlayerPill = computed(() => !!player.taskId && player.playing && route.name !== 'generating')
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
const showLangMenu = ref(false)
// ESC 走状态而非剥 class，否则 aria-expanded 会与真实状态长期不一致
// Close through state so aria-expanded cannot drift from the visible surface.
useEscClose(showThemeMenu, () => { showThemeMenu.value = false })
useEscClose(showLangMenu, () => { showLangMenu.value = false })

// ─── 语言切换 / Language switching ───
const currentLocale = computed(() => getLocale())
const langOptions: { code: SupportedLocale; label: string }[] = [
  { code: 'zh-CN', label: '中文' },
  { code: 'en', label: 'English' },
]
async function onSwitchLang(locale: SupportedLocale) {
  await setI18nLocale(locale)
}

// ─── 录音状态胶囊面板（方案 A：usePopMenu 统一管理展开/定位/关闭） / Recording pill panel (Plan A: usePopMenu manages expand/position/close) ───
const recPillTrigger = ref<HTMLElement | null>(null)
const recPanelEl = ref<HTMLElement | null>(null)
const { visible: showRecPanel, toggle: toggleRecPanel, close: closeRecPanel, triggerAttrs: recPanelTriggerAttrs, menuAttrs: recPanelMenuAttrs } = usePopMenu(recPanelEl, recPillTrigger)
const showAbandon = ref(false)
useEscClose(showAbandon, () => { showAbandon.value = false })

// ─── 录音中指示 pill / Recording indicator pill ───
// 会议相关路由的状态由页面自身承载（录音页头部/控制栏），顶栏不叠加录音中胶囊 / Meeting route states are handled by pages themselves (recording page header/control bar), top bar doesn't add recording pill
const MEETING_ROUTES = ['recording', 'generating']

/** 录音中的任务（24 小时内创建且状态为 recording/paused）——全局唯一数据源，其他计算/方法均复用它 / The recording task (created within 24h, status recording/paused) — single source of truth reused by all other computeds/methods */
const recTask = computed(() => {
  const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000)
  return taskStore.tasks.find(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    const createdAt = t.created_at ? new Date(t.created_at) : null
    if (createdAt && createdAt < oneDayAgo) return false
    return true
  }) ?? null
})
const isRecPaused = computed(() => recTask.value?.status === 'paused')

/** 当前是否已在录音任务自身的页面（页面已承载完整录音 UI，无需「返回录音」入口） / Whether currently on the recording task's own page (page already has full recording UI, no need for "return to recording" entry) */
const isOnRecTaskPage = computed(() => {
  if (!recTask.value) return false
  const currentTaskId = route.params.taskId as string | undefined
  return route.name === 'recording' && currentTaskId === recTask.value.task_id
})

/** 是否显示录音胶囊：仅在「正在录音的那个任务」自身的页面中隐藏 / Whether to show rec pill: only hidden on the recording task's own page */
// 查看其他任务的纪要/转写时，rec-pill 仍需显示以提示录音进行中 / When viewing other tasks' minutes/transcript, rec-pill still shows to indicate recording in progress
const showRecPill = computed(() => {
  if (!recTask.value) return false
  const currentTaskId = route.params.taskId as string | undefined
  return !currentTaskId || currentTaskId !== recTask.value.task_id
})

/** 跳回录音页 / Jump back to recording page */
function jumpBackToRecording() {
  const task = recTask.value
  if (task) {
    taskStore.selectTask(task.task_id)
    router.push({ name: 'recording', params: { taskId: task.task_id } })
  }
}

// ─── 录音计时器（独立于 RecordingView，离开录音页后仍运行）───
const recElapsed = ref('00:00')
let recTimer: ReturnType<typeof setInterval> | null = null
let recElapsedSec = 0

function formatRecTime(totalSec: number): string {
  const s = Math.floor(totalSec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

/** 基于任务 created_at 计算已过秒数（页面刷新后仍能还原） / Calculate elapsed seconds from task created_at (can restore after page refresh) */
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
    // 优先从后端获取精确已过时长（已扣除暂停），失败则回退到 created_at 估算 / Prefer precise elapsed time from backend (pause deducted), fallback to created_at estimation
    let backendPaused = false
    try {
      const status = await getRecordStatus()
      if (status.recording && status.elapsed != null) {
        recElapsedSec = Math.floor(status.elapsed)
      } else {
        recElapsedSec = calcElapsedFromTask(task)
      }
      // 后端是唯一事实源：录音页暂停不会同步 store，这里兜底修正过期状态 / Backend is the source of truth: pausing on the recording page does not sync the store, so correct stale status here
      backendPaused = !!status.paused
      if (status.recording && status.paused && task.status === 'recording') {
        taskStore.patchTaskLocal(task.task_id, { status: 'paused' })
      }
    } catch {
      recElapsedSec = calcElapsedFromTask(task)
    }
    recElapsed.value = formatRecTime(recElapsedSec)
    if (task.status === 'paused' || backendPaused) {
      // 暂停中：冻结计时器，保留已过时长 / Paused: freeze timer, preserve elapsed time
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
    // 暂停：冻结当前已过时长，停止自增 / Pause: freeze current elapsed time, stop incrementing
    stopRecTimer()
  } else if (recTask.value) {
    // 恢复：从冻结值继续 / Resume: continue from frozen value
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
  } catch { /* store 已打印错误 / store already logged error */ }
}

async function onStopRecording() {
  const task = recTask.value
  if (!task) return
  try {
    await taskStore.stopRecording(task.task_id)
    // [状态同步] 停止录音后刷新任务列表 / [State Sync] Refresh task list after stopping recording
    await taskStore.loadTasks()
    router.push({ name: 'generating', params: { taskId: task.task_id } })
  } catch (e) {
    console.error('stop recording failed:', e)
    showToast(extractErrorMessage(e), 'error')
  }
}

async function onAbandonRecording() {
  showAbandon.value = false
  const task = recTask.value
  if (!task) return
  try {
    await taskStore.abandonRecording(task.task_id)
    // [状态同步] 放弃录音后刷新任务列表 / [State Sync] Refresh task list after abandoning recording
    await taskStore.loadTasks()
  } catch (e) {
    console.error('abandon recording failed:', e)
    showToast(extractErrorMessage(e), 'error')
  }
}


const allThemeOptions = computed(() => [
  { id: 'standard-light' as ThemeId, label: t('common.theme.standard_light'), swatch: 'oklch(65% 0.16 250)', group: 'standard' },
  { id: 'standard-dark' as ThemeId, label: t('common.theme.standard_dark'), swatch: 'oklch(21% 0.005 264)', group: 'standard' },
  { id: 'default' as ThemeId, label: t('common.theme.default'), swatch: 'oklch(72% 0.10 55)', group: 'nature' },
  { id: 'dark' as ThemeId, label: t('common.theme.dark'), swatch: 'oklch(22% 0.018 260)', group: 'nature' },
  { id: 'warm' as ThemeId, label: t('common.theme.warm'), swatch: 'oklch(66% 0.14 30)', group: 'nature' },
  { id: 'forest' as ThemeId, label: t('common.theme.forest'), swatch: 'oklch(26% 0.025 155)', group: 'nature' },
  { id: 'mist' as ThemeId, label: t('common.theme.mist'), swatch: 'oklch(58% 0.05 210)', group: 'nature' },
  { id: 'moss' as ThemeId, label: t('common.theme.moss'), swatch: 'oklch(52% 0.10 155)', group: 'nature' },
  { id: 'wheat' as ThemeId, label: t('common.theme.wheat'), swatch: 'oklch(66% 0.12 78)', group: 'nature' },
  { id: 'moonlight' as ThemeId, label: t('common.theme.moonlight'), swatch: 'oklch(74% 0.05 220)', group: 'nature' },
])

const standardThemes = computed(() => allThemeOptions.value.filter(t => t.group === 'standard'))
const natureThemes = computed(() => allThemeOptions.value.filter(t => t.group === 'nature'))

const isStartRoute = computed(() => route.name === 'start')

/** 只在会议相关路由显示任务信息 / Only show task info on meeting routes */
const showTaskInfo = computed(() => MEETING_ROUTES.includes(route.name as string) && !!taskStore.currentTask)
/** 录音中状态不在顶栏重复显示：录音页由视图头部/控制栏承载，非会议页由右上角 rec-pill 承载 / Recording status not duplicated in top bar: recording page uses view header/control bar, non-meeting pages use top-right rec-pill */
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

// ─── 全局点击外部关闭菜单（命名函数引用，供卸载时对称清理） / Global click-outside to close menus (named function reference for symmetric cleanup on unmount) ───
function onDocClick(e: Event) {
  const target = e.target as HTMLElement
  if (!target.closest('.theme-switcher')) showThemeMenu.value = false
  if (!target.closest('.lang-switcher')) showLangMenu.value = false
}
document.addEventListener('click', onDocClick)

onUnmounted(() => {
  stopRecTimer()
  document.removeEventListener('click', onDocClick)
})
</script>
