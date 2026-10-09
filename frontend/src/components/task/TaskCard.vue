<template>
  <div
    class="sb-tl-item"
    :class="{ 'is-active': isActive, 'is-latest': isLatest, 'is-playing': player.taskId === task.task_id }"
    @click="$emit('select', task.task_id)"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <!-- 标题 / Title -->
    <div class="sb-tl-title">
      <PlayingEq v-if="player.taskId === task.task_id" :playing="player.playing" />
      <span v-if="searchQuery" v-html="highlightedTitle"></span>
      <span v-else>{{ displayTitle }}</span>
      <!-- 完成待查看角标（REQ-TRANSCRIBE-PROGRESS R2 站内提醒）；置于标题行以兼容窄栏 meta 隐藏态 -->
      <span v-if="isUnseenDone" class="sb-tl-new">{{ t('processing.badge_new') }}</span>
    </div>

    <!-- 元数据：时间 + 状态 + 时长 / Metadata: time + status + duration -->
    <div class="sb-tl-meta">
      <span v-if="timeStr" class="sb-tl-time">{{ timeStr }}</span>
      <span class="sb-tl-dot" :class="dotClass"></span>
      <span class="sb-tl-status">{{ statusLabel }}</span>
      <DurationDial v-if="task.audio_duration" class="sb-tl-dur" :seconds="task.audio_duration" />
    </div>

    <!-- 主要讲话人 / Main speakers（D5：仅真名逐个，未绑定聚合为中性计数 chip，不露编号） -->
    <div v-if="topSpeakers.length > 0 || unidentifiedCount > 0" class="sb-tl-speakers">
      <div
        v-for="sp in topSpeakers"
        :key="sp.id"
        class="sb-tl-spk-item"
        :title="`${sp.name} · ${sp.pct}%`"
      >
        <span class="sb-tl-spk-name" :style="{ color: sp.color }">{{ sp.name }}</span>
        <div class="sb-tl-spk-bar"><div class="sb-tl-spk-bar-fill" :style="{ width: sp.pct + '%', background: sp.color }"></div></div>
      </div>
      <span
        v-if="unidentifiedCount > 0"
        class="sb-tl-spk-unid"
        :title="t('task.speakers_unid_title', { count: unidentifiedCount })"
      >{{ t('task.speakers_unidentified', { count: unidentifiedCount }) }}</span>
      <span v-if="extraSpeakerCount > 0" class="sb-tl-spk-more">
        …{{ t('task.speakers_more', { count: extraSpeakerCount }) }} · {{ t('task.speakers_total', { count: task.speaker_count || 0 }) }}
      </span>
      <span v-else-if="task.speaker_count" class="sb-tl-spk-total">{{ t('task.speakers_total', { count: task.speaker_count }) }}</span>
    </div>

    <!-- 失败详情 / Failure details -->
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

    <!-- 更多按钮 / More button -->
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

    <!-- 任务上下文菜单（独立组件，贴侧边栏右边缘定位） / Task context menu (standalone component, aligned to sidebar right edge) -->
    <TaskContextMenu
      :task="task"
      :open="showContextMenu"
      :sidebar-el="sidebarEl"
      :button-rect="buttonRect"
      @close="closeMenu"
      @hover-enter="onMenuHoverEnter"
      @rename="onRename"
      @regenerate="onRegenerate"
      @retranscribe="onRetranscribe"
      @archive="onArchive"
      @unarchive="onUnarchive"
      @delete="onDelete"
    />

    <!-- 悬停知识卡片 / Hover knowledge card -->
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

    <!-- 删除确认弹窗 / Delete confirm dialog -->
    <ConfirmDialog
      v-model="showDeleteConfirm"
      :title="t('task.confirm_delete_title')"
      :message="t('task.confirm_delete')"
      @confirm="onConfirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Task } from '@/api/types'
import { STATUS_CONFIG } from '@/api/types'
import { isPlaceholderName, countUnidentified } from '@/utils/speakerDisplay'
import { usePlayerStore } from '@/stores/player'
import { useTaskStore } from '@/stores/task'
import PlayingEq from '@/components/common/PlayingEq.vue'
import DurationDial from '@/components/common/DurationDial.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import TaskContextMenu from './TaskContextMenu.vue'
import { highlightText } from '@/utils/search'
import { getSpeakerColor } from '@/utils/speakerColors'

const { t } = useI18n()
const player = usePlayerStore()
const taskStore = useTaskStore()

const props = defineProps<{
  task: Task
  isActive: boolean
  isLatest?: boolean
  searchQuery?: string
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

/** 后台完成但用户尚未查看（角标） / Finished in background, not yet opened (badge) */
const isUnseenDone = computed(() =>
  taskStore.completedUnseen.includes(props.task.task_id),
)

const showContextMenu = ref(false)
const showHoverCard = ref(false)
const showDeleteConfirm = ref(false)
const sidebarEl = ref<HTMLElement | null>(null)
const buttonRect = ref<DOMRect | null>(null)
const hoverStyle = ref<Record<string, string>>({})

const displayTitle = computed(() =>
  props.task.title || props.task.audio_name || t('task.untitled'),
)

/** 搜索高亮标题（HTML） / Search highlighted title (HTML) */
const highlightedTitle = computed(() => {
  const title = displayTitle.value
  if (!props.searchQuery) return title
  return highlightText(title, props.searchQuery)
})

const timeStr = computed(() => {
  // 优先用 created_at 的完整时间戳，回退到 meeting_date / Prefer full created_at timestamp, fallback to meeting_date
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

/** 主要讲话人：从 dialogue 计算时长，取前 3 / Main speakers: calculate duration from dialogue, take top 3 */
interface CardSpeakerInfo { id: string; name: string; color: string; pct: number }

/** 未绑定说话人聚合计数（REQ-SPK-RN D5：占位/空名一律计入，不逐个露出） */
const unidentifiedCount = computed(() => countUnidentified(props.task.speaker_mapping))

const topSpeakers = computed((): CardSpeakerInfo[] => {
  const mapping = props.task.speaker_mapping
  if (!mapping || Object.keys(mapping).length === 0) return []
  if (props.task.status !== 'completed' || !props.task.dialogue) return []

  const durMap: Record<string, number> = {}
  let total = 0
  for (const line of props.task.dialogue) {
    const sid = String(line.speaker_id)
    for (const s of line.sentences) {
      const d = s.end_time - s.begin_time
      durMap[sid] = (durMap[sid] || 0) + d
      total += d
    }
  }
  if (total === 0) return []

  return Object.entries(mapping)
    .filter(([, name]) => !isPlaceholderName(name))  // D5/H1：占位名不逐个展示
    .map(([id, name]) => ({
      id,
      name: (name as string).trim(),
      color: getSpeakerColor(id),
      pct: Math.round((durMap[id] || 0) / total * 100),
    }))
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 3)
})

const extraSpeakerCount = computed(() => {
  const mapping = props.task.speaker_mapping
  if (!mapping) return 0
  return Math.max(0, Object.keys(mapping).filter(k => mapping[k]).length - 3)
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

// 悬停知识卡片 / Hover knowledge card
let hoverTimer: ReturnType<typeof setTimeout> | null = null

function onMouseEnter(e: MouseEvent) {
  // 冲突修复：鼠标位于“更多”按钮上，或右键菜单已打开时，不弹悬停卡片 / Conflict resolution: suppress hover card when cursor is on "more" button or context menu is open
  const target = e.target as HTMLElement
  if (showContextMenu.value || target.closest('.sb-more')) return
  const el = e.currentTarget as HTMLElement
  hoverTimer = setTimeout(() => {
    // 定时到期时再次检查：若期间打开了菜单或移到更多按钮，则不显示 / Recheck when timer expires: skip if menu opened or moved to more button
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

// 更多按钮互斥：光标在按钮上时取消悬停卡片，离开后恢复 / More button mutex: cancel hover card on enter, restore on leave
let menuHoverTimer: ReturnType<typeof setTimeout> | null = null
function onMoreEnter() {
  if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null }
  showHoverCard.value = false
  if (menuHoverTimer) { clearTimeout(menuHoverTimer); menuHoverTimer = null }
}
function onMoreLeave() {
  // 离开按钮 → 延迟关闭菜单（给用户从按钮移向 Teleport 出去的菜单留过渡时间）
  if (showContextMenu.value) {
    menuHoverTimer = setTimeout(() => closeMenu(), 250)
  }
}
function onMenuHoverEnter() {
  if (menuHoverTimer) { clearTimeout(menuHoverTimer); menuHoverTimer = null }
}

const hoverDate = computed(() => {
  const d = props.task.meeting_date || props.task.created_at?.slice(0, 10) || ''
  if (!d) return ''
  return new Date(d + 'T00:00:00').toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
})

// 失败信息分类 / Failure info categorization
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
      // 细分：无有效语音 vs 其他音频问题 / Subcategory: no valid speech vs other audio issues
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

// 右键菜单 / Context menu
function onMenuClick(e: MouseEvent) {
  e.preventDefault()
  // 打开菜单时立即隐藏悬停卡片并取消待触发的定时器 / Hide hover card and cancel pending timer when menu opens
  if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null }
  showHoverCard.value = false
  const btn = e.currentTarget as HTMLElement
  buttonRect.value = btn.getBoundingClientRect()
  sidebarEl.value = btn.closest('.sidebar')
  showContextMenu.value = true
}

function closeMenu() { showContextMenu.value = false }

function onRename() {
  closeMenu()
  const newName = prompt(t('task.rename_prompt'), props.task.title || props.task.audio_name || '')
  if (newName && newName.trim()) {
    emit('menu', props.task.task_id, new MouseEvent('rename'), newName.trim())
  }
}

function onRegenerate() {
  closeMenu()
  emit('menu', props.task.task_id, new MouseEvent('retry_summary'))
}

function onRetranscribe() {
  closeMenu()
  emit('menu', props.task.task_id, new MouseEvent('retranscribe'))
}

function onArchive() {
  closeMenu()
  emit('menu', props.task.task_id, new MouseEvent('archive'))
}

function onUnarchive() {
  closeMenu()
  emit('menu', props.task.task_id, new MouseEvent('unarchive'))
}

function onDelete() {
  closeMenu()
  showDeleteConfirm.value = true
}

function onConfirmDelete() {
  emit('menu', props.task.task_id, new MouseEvent('delete'))
}

// 引用 STATUS_CONFIG 避免 unused 警告 / Reference STATUS_CONFIG to avoid unused warning
void STATUS_CONFIG
</script>
