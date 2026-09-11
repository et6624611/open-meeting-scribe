<template>
  <div
    class="sb-tl-item"
    :class="{ 'is-active': isActive, 'is-latest': isLatest, 'is-playing': player.taskId === task.task_id }"
    @click="$emit('select', task.task_id)"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <!-- 标题 -->
    <div class="sb-tl-title">
      <PlayingEq v-if="player.taskId === task.task_id" :playing="player.playing" />
      <span>{{ displayTitle }}</span>
    </div>

    <!-- 元数据：时间 + 状态 + 时长 -->
    <div class="sb-tl-meta">
      <span v-if="timeStr" class="sb-tl-time">{{ timeStr }}</span>
      <span class="sb-tl-dot" :class="dotClass"></span>
      <span class="sb-tl-status">{{ statusLabel }}</span>
      <DurationDial v-if="task.audio_duration" class="sb-tl-dur" :seconds="task.audio_duration" />
    </div>

    <!-- 失败详情 -->
    <div v-if="task.status === 'failed'" class="sb-tl-failure">
      <div class="sb-failure-icon" :class="failureInfo.iconClass">
        <svg v-if="failureInfo.icon === 'refresh'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        <svg v-else-if="failureInfo.icon === 'settings'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>
        <svg v-else-if="failureInfo.icon === 'audio'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      </div>
      <div class="sb-failure-content">
        <div class="sb-failure-message">{{ failureInfo.message }}</div>
        <div v-if="failureInfo.suggestion" class="sb-failure-suggestion">{{ failureInfo.suggestion }}</div>
      </div>
      <button class="sb-failure-action" @click.stop="failureInfo.onAction">{{ failureInfo.actionText }}</button>
    </div>

    <!-- 更多按钮 -->
    <button
      class="sb-more"
      :data-tip="showContextMenu ? '' : t('task.more')"
      @click.stop="onMenuClick"
      @mouseenter="onMoreEnter"
      @mouseleave="onMoreLeave"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
        <circle cx="12" cy="5" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="12" cy="19" r="1" />
      </svg>
    </button>

    <!-- 右键菜单 -->
    <Teleport to="body">
      <div v-if="showContextMenu" class="sb-dropdown is-open is-down" :style="menuStyle" @click.stop>
        <button @click="onRename">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          {{ t('task.rename') }}
        </button>
        <button v-if="task.status === 'failed'" @click="onRetry">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
          {{ t('task.retry') }}
        </button>
        <button class="is-danger" @click="onDelete">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
          {{ t('task.delete') }}
        </button>
      </div>
    </Teleport>

    <!-- 悬停知识卡片 -->
    <Teleport to="body">
      <div v-if="showHoverCard" class="sb-hover-card is-visible" :style="hoverStyle">
        <div class="hc-title">{{ displayTitle }}</div>
        <div class="hc-meta">
          <span>{{ hoverDate }}</span>
          <span>{{ durationStr }}</span>
        </div>
        <div v-if="task.summary" class="hc-section">
          <div class="hc-label">{{ t('task.summary_label') }}</div>
          <div class="hc-summary">{{ task.summary.slice(0, 200) }}…</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Task } from '@/api/types'
import { STATUS_CONFIG } from '@/api/types'
import { usePlayerStore } from '@/stores/player'
import PlayingEq from '@/components/common/PlayingEq.vue'
import DurationDial from '@/components/common/DurationDial.vue'

const { t } = useI18n()
const player = usePlayerStore()

const props = defineProps<{
  task: Task
  isActive: boolean
  isLatest?: boolean
}>()

const emit = defineEmits<{
  select: [taskId: string]
  menu: [taskId: string, event: MouseEvent, newName?: string]
  hover: [taskId: string, anchor: HTMLElement]
  'hover-end': []
  retry: [taskId: string]
  checkSettings: []
  reupload: [taskId: string]
  rerecord: [taskId: string]
  viewDetails: [taskId: string]
}>()

const showContextMenu = ref(false)
const showHoverCard = ref(false)
const menuStyle = ref<Record<string, string>>({})
const hoverStyle = ref<Record<string, string>>({})

const displayTitle = computed(() =>
  props.task.title || props.task.audio_name || t('task.untitled'),
)

const timeStr = computed(() => {
  // 优先用 created_at 的完整时间戳，回退到 meeting_date
  const raw = props.task.created_at || props.task.meeting_date || ''
  if (!raw) return ''
  const d = new Date(raw.length <= 10 ? raw + 'T00:00:00' : raw)
  if (isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})

const dotClass = computed(() => {
  const s = props.task.status
  if (s === 'completed') return 'is-done'
  if (s === 'recording' || s === 'processing' || s === 'transcribing' || s === 'summarizing') return 'is-processing'
  if (s === 'pending' || s === 'awaiting_mapping') return 'is-pending'
  if (s === 'failed') return 'is-failed'
  return ''
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    recording: t('task.status.recording'), pending: t('task.status.pending'), processing: t('common.processing'),
    transcribing: t('task.status.transcribing'),
    awaiting_mapping: t('task.status.awaiting_mapping'), summarizing: t('task.status.summarizing'),
    completed: t('task.status.completed'), failed: t('task.status.failed'),
  }
  return map[props.task.status] || props.task.status
})

const durationStr = computed(() => {
  const dur = props.task.audio_duration
  if (!dur) return ''
  const mins = Math.round(dur / 60)
  if (mins < 60) return t('task.duration.minutes', { m: mins })
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m > 0 ? t('task.duration.hours_minutes', { h, m }) : t('task.duration.hours', { h })
})

// 悬停知识卡片
let hoverTimer: ReturnType<typeof setTimeout> | null = null

function onMouseEnter(e: MouseEvent) {
  // 冲突修复：鼠标位于“更多”按钮上，或右键菜单已打开时，不弹悬停卡片
  const target = e.target as HTMLElement
  if (showContextMenu.value || target.closest('.sb-more')) return
  const el = e.currentTarget as HTMLElement
  hoverTimer = setTimeout(() => {
    // 定时到期时再次检查：若期间打开了菜单或移到更多按钮，则不显示
    if (showContextMenu.value) return
    const moreBtn = el.querySelector('.sb-more')
    if (moreBtn && moreBtn.matches(':hover')) return
    const rect = el.getBoundingClientRect()
    hoverStyle.value = {
      left: (rect.right + 8) + 'px',
      top: Math.max(8, rect.top - 20) + 'px',
    }
    showHoverCard.value = true
  }, 600)
}

function onMouseLeave() {
  if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null }
  showHoverCard.value = false
}

// 更多按钮互斥：光标在按钮上时取消悬停卡片，离开后恢复
function onMoreEnter() {
  if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null }
  showHoverCard.value = false
}
function onMoreLeave() {
  // 光标离开更多按钮但仍在卡片内时，重新触发悬停检测
  // 由父元素的 @mouseenter 自然处理，这里不做额外操作
}

const hoverDate = computed(() => {
  const d = props.task.meeting_date || props.task.created_at?.slice(0, 10) || ''
  if (!d) return ''
  return new Date(d + 'T00:00:00').toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
})

// 失败信息分类
const failureInfo = computed(() => {
  const category = props.task.error_category
  const errorText = props.task.error || t('task.failure.unknown')
  
  switch (category) {
    case 'transient':
      return {
        icon: 'refresh',
        iconClass: 'is-transient',
        message: t('task.failure.transient'),
        suggestion: '',
        actionText: t('task.failure.transient_action'),
        onAction: () => emit('retry', props.task.task_id),
      }
    case 'api_config':
      return {
        icon: 'settings',
        iconClass: 'is-api-config',
        message: t('task.failure.api_config'),
        suggestion: '',
        actionText: t('task.failure.api_config_action'),
        onAction: () => emit('checkSettings'),
      }
    case 'audio':
      // 细分：无有效语音 vs 其他音频问题
      const isRecord = props.task.source === 'record' || (props.task.audio_path || '').includes('recordings')
      if (errorText.toLowerCase().includes('no_valid_fragment') ||
          errorText.toLowerCase().includes('no valid fragment')) {
        return {
          icon: 'audio',
          iconClass: 'is-audio',
          message: t('task.failure.no_speech'),
          suggestion: t('task.failure.no_speech_hint'),
          actionText: isRecord ? t('task.failure.rerecord_action') : t('task.failure.audio_action'),
          onAction: () => { isRecord ? emit('rerecord', props.task.task_id) : emit('reupload', props.task.task_id) },
        }
      }
      return {
        icon: 'audio',
        iconClass: 'is-audio',
        message: t('task.failure.audio'),
        suggestion: '',
        actionText: isRecord ? t('task.failure.rerecord_action') : t('task.failure.audio_action'),
        onAction: () => { isRecord ? emit('rerecord', props.task.task_id) : emit('reupload', props.task.task_id) },
      }
    default:
      return {
        icon: 'alert',
        iconClass: 'is-unknown',
        message: errorText,
        suggestion: '',
        actionText: t('task.failure.default_action'),
        onAction: () => emit('viewDetails', props.task.task_id),
      }
  }
})

// 右键菜单
function onMenuClick(e: MouseEvent) {
  e.preventDefault()
  // 打开菜单时立即隐藏悬停卡片并取消待触发的定时器
  if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null }
  showHoverCard.value = false
  const btn = e.currentTarget as HTMLElement
  const rect = btn.getBoundingClientRect()
  menuStyle.value = {
    position: 'fixed',
    left: rect.left + 'px',
    top: (rect.bottom + 4) + 'px',
  }
  showContextMenu.value = true
  // 点击外部关闭
  setTimeout(() => document.addEventListener('click', closeMenu, { once: true }), 0)
}

function closeMenu() { showContextMenu.value = false }

function onRename() {
  closeMenu()
  const newName = prompt(t('task.rename_prompt'), props.task.title || props.task.audio_name || '')
  if (newName && newName.trim()) {
    emit('menu', props.task.task_id, new MouseEvent('rename'), newName.trim())
  }
}

function onRetry() {
  closeMenu()
  emit('menu', props.task.task_id, new MouseEvent('retry'))
}

function onDelete() {
  closeMenu()
  if (confirm(t('task.confirm_delete'))) {
    emit('menu', props.task.task_id, new MouseEvent('delete'))
  }
}

// 引用 STATUS_CONFIG 避免 unused 警告
void STATUS_CONFIG
</script>
