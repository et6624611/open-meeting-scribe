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
        <button class="update-badge" id="updateBadge" title="有新版本可用">
          <span class="ub-dot"></span>
          <span>更新可用</span>
        </button>
        <!-- 全局播放 pill：不在会议纪要页时承接音频控制（借鉴录音 pill 形态） -->
        <div class="player-pill" :class="{ 'is-paused': !player.playing }" v-if="showPlayerPill">
          <PlayingEq :playing="player.playing" />
          <span class="pp-title" :title="playerTaskTitle" @click="openPlayerTask">{{ playerTaskTitle }}</span>
          <span class="pp-time">{{ player.timeStr }}</span>
          <div class="pp-progress" title="点击跳转进度" @click="onSeekPlayer">
            <div class="pp-progress-fill" :style="{ width: player.progress + '%' }"></div>
          </div>
          <button class="pp-btn" @click.stop="player.toggle()" :title="player.playing ? '暂停' : '播放'">
            <svg v-if="!player.playing" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
          </button>
          <button class="pp-btn pp-speed" @click.stop="player.cycleSpeed()" title="播放速度">{{ player.speed }}×</button>
          <button class="pp-btn" @click.stop="openPlayerTask" title="打开会议纪要">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
          <button class="pp-btn" @click.stop="player.stop()" title="停止播放">
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
          <!-- 计时器（点击跳转到录音页） -->
          <span class="rec-timer" @click="jumpBackToRecording" title="点击返回录音纪要">{{ recElapsed }}</span>
          <!-- 暂停/恢复按钮（药丸形，与底部控制栏一致） -->
          <button class="rec-pause-btn" @click.stop="onToggleRecPause" :title="isRecPaused ? '恢复录音' : '暂停录音'">
            <svg v-if="!isRecPaused" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
            <span class="rec-pause-text">{{ isRecPaused ? '恢复' : '暂停' }}</span>
          </button>
          <!-- 结束按钮 -->
          <button class="rec-end-btn" @click.stop="onStopRecording" title="结束录音">结束</button>
          <!-- 更多操作菜单 -->
          <div class="rec-more-wrap">
            <button ref="recMoreBtn" class="rec-more-btn" @click="toggleRecMore" title="更多操作" aria-haspopup="menu" aria-label="录音更多操作">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
            </button>
            <div ref="recDropdown" class="rec-more-dropdown" :class="{ 'is-open': showRecMore }" role="menu">
              <button class="rec-more-item" @click="jumpBackToRecording" role="menuitem">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
                打开录音纪要
              </button>
              <div style="height:1px;background:var(--border);margin:4px 0"></div>
              <button class="rec-more-item danger" @click="closeRecMore(); showAbandon = true" role="menuitem">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                放弃录音
              </button>
            </div>
          </div>
        </div>

        <!-- 放弃录音确认弹窗 -->
        <div class="abandon-overlay" :class="{ 'is-open': showAbandon }" v-if="showAbandon">
          <div class="abandon-dialog">
            <div class="abandon-dialog-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </div>
            <div class="abandon-dialog-title">放弃本次录音？</div>
            <div class="abandon-dialog-desc">录音将被终止，所有数据将永久删除，无法恢复。</div>
            <div class="abandon-dialog-info">已录制时长：{{ recElapsed }}</div>
            <div class="abandon-dialog-actions">
              <button class="btn-cancel" @click="showAbandon = false">取消</button>
              <button class="btn-confirm-abandon" @click="onAbandonRecording">确认放弃</button>
            </div>
          </div>
        </div>
        <button
          class="topbar-new-btn"
          :class="{ 'is-hidden': isStartRoute, 'is-disabled': hasRecordingTask }"
          :title="hasRecordingTask ? `已有录音进行中 (${recElapsed})，点击跳转到录音页` : '新建会议'"
          @click="hasRecordingTask ? jumpBackToRecording() : router.push('/')"
        >
          <svg v-if="hasRecordingTask" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>{{ hasRecordingTask ? '返回录音' : '新建会议' }}</span>
        </button>
        <button class="lang-btn" id="langBtn" title="识别语言" disabled>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          <span>中文</span>
        </button>

        <!-- 主题切换器 -->
        <div class="theme-switcher">
          <IconButton class="theme-switcher-btn" label="切换主题" tip-position="bottom" @click="showThemeMenu = !showThemeMenu">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>
            </svg>
          </IconButton>
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
          <IconButton class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'full' }" label="全视图" tip-position="bottom" :active="layout.viewMode === 'full'" data-view="full" @click="layout.setViewMode('full')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <rect x="1.5" y="2.5" width="3.5" height="11" rx="1"/><rect x="6.25" y="2.5" width="3.5" height="11" rx="1"/><rect x="11" y="2.5" width="3.5" height="11" rx="1"/>
            </svg>
          </IconButton>
          <IconButton class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'left' }" label="资源视图" tip-position="bottom" :active="layout.viewMode === 'left'" data-view="left" @click="layout.setViewMode('left')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <rect x="1.5" y="2.5" width="4.5" height="11" rx="1" fill="currentColor" opacity="0.12"/><rect x="1.5" y="2.5" width="4.5" height="11" rx="1"/>
              <line x1="8.5" y1="5" x2="14.5" y2="5" opacity="0.3"/><line x1="8.5" y1="8" x2="13" y2="8" opacity="0.3"/><line x1="8.5" y1="11" x2="14.5" y2="11" opacity="0.3"/>
            </svg>
          </IconButton>
          <IconButton class="view-switcher-btn" :class="{ 'is-active': layout.viewMode === 'right' }" label="对话视图" tip-position="bottom" :active="layout.viewMode === 'right'" data-view="right" @click="layout.setViewMode('right')">
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
import { useThemeStore, type ThemeId } from '@/stores/theme'
import { useTaskStore } from '@/stores/task'
import { useUserStore } from '@/stores/user'
import { useLayoutStore } from '@/stores/layout'
import { usePlayerStore } from '@/stores/player'
import IconButton from '@/components/common/IconButton.vue'
import PlayingEq from '@/components/common/PlayingEq.vue'
import { usePopMenu } from '@/composables/usePopMenu'

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
  const t = taskStore.tasks.find(t => t.task_id === player.taskId)
  return t?.title || t?.audio_name || '会议纪要'
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

// ── 录音中指示 pill（更多菜单）───
const recMoreBtn = ref<HTMLElement | null>(null)
const recDropdown = ref<HTMLElement | null>(null)
const { visible: showRecMore, toggle: toggleRecMore, close: closeRecMore } = usePopMenu(recDropdown, recMoreBtn)
const showAbandon = ref(false)

// ─── 录音中指示 pill ───
// 会议相关路由的状态由页面自身承载（录音页头部/控制栏），顶栏不叠加录音中胶囊
const MEETING_ROUTES = ['recording', 'processing', 'generating']

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

const showRecPill = computed(() =>
  hasRecordingTask.value && !MEETING_ROUTES.includes(route.name as string)
)

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

function tickRecTimer() {
  recElapsedSec++
  const h = Math.floor(recElapsedSec / 3600)
  const m = Math.floor((recElapsedSec % 3600) / 60)
  const s = recElapsedSec % 60
  recElapsed.value = h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function startRecTimer() {
  if (recTimer) return
  recTimer = setInterval(tickRecTimer, 1000)
}

function stopRecTimer() {
  if (recTimer) { clearInterval(recTimer); recTimer = null }
}

watch(recTask, (task) => {
  if (task) {
    if (task.status === 'paused') stopRecTimer()
    else startRecTimer()
  } else {
    stopRecTimer(); recElapsedSec = 0; recElapsed.value = '00:00'
  }
}, { immediate: true })

watch(isRecPaused, (paused) => {
  if (paused) stopRecTimer()
  else if (recTask.value) startRecTimer()
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
      await taskStore.loadTasks()
      router.push({ name: 'generating', params: { taskId: recTask.task_id } })
    } catch (e) {
      console.error('结束录音失败:', e)
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
      await taskStore.loadTasks()
    } catch (e) {
      console.error('放弃录音失败:', e)
    }
  }
}

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

/** 只在会议相关路由显示任务信息 */
const showTaskInfo = computed(() => MEETING_ROUTES.includes(route.name as string) && !!taskStore.currentTask)
/** 录音中状态不在顶栏重复显示：录音页由视图头部/控制栏承载，非会议页由右上角 rec-pill 承载 */
const showStatePill = computed(() => {
  const s = taskStore.currentTask?.status
  return showTaskInfo.value && s !== 'recording' && s !== 'paused'
})

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
    recording: 'is-rec', paused: 'is-rec', transcribing: 'is-proc', summarizing: 'is-proc',
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


onUnmounted(() => {
  stopRecTimer()
})

document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement
  if (!target.closest('.theme-switcher')) showThemeMenu.value = false
  if (!target.closest('.user-avatar-wrapper')) showUserMenu.value = false
})
</script>
