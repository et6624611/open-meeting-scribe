<template>
  <Teleport to="body">
    <div
      v-if="open"
      ref="menuRef"
      class="sb-ctx-menu"
      :style="menuPosition"
      @click.stop
    >
      <!-- 顶部：分享 / 复制 -->
      <div class="sb-ctx-section">
        <button @click="onCopy('title')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          <span>{{ t('task.copy_title') }}</span>
          <span v-if="copied === 'title'" class="sb-ctx-copied">{{ t('task.copied') }}</span>
        </button>
        <button v-if="task.summary" @click="onCopy('summary')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
          <span>{{ t('task.copy_summary') }}</span>
          <span v-if="copied === 'summary'" class="sb-ctx-copied">{{ t('task.copied') }}</span>
        </button>
      </div>

      <div class="sb-ctx-sep"></div>

      <!-- 中部：操作 -->
      <div class="sb-ctx-section">
        <button @click="emit('rename')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
            <path d="M12 20h9"/>
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
          </svg>
          {{ t('task.rename') }}
        </button>
        <button v-if="task.status === 'failed'" @click="emit('retry')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          {{ t('task.retry') }}
        </button>
        <button class="is-danger" @click="emit('delete')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6"/>
            <path d="M14 11v6"/>
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
          </svg>
          {{ t('task.delete') }}
        </button>
      </div>

      <div class="sb-ctx-sep"></div>

      <!-- 底部：统计信息 -->
      <div class="sb-ctx-section sb-ctx-stats">
        <div v-if="task.speaker_count != null" class="sb-ctx-stat">
          <span class="sb-ctx-stat-label">{{ t('task.stat_speakers') }}</span>
          <span class="sb-ctx-stat-value">{{ task.speaker_count }}</span>
        </div>
        <div v-if="task.audio_duration" class="sb-ctx-stat">
          <span class="sb-ctx-stat-label">{{ t('task.stat_duration') }}</span>
          <span class="sb-ctx-stat-value">{{ durationDisplay }}</span>
        </div>
        <div class="sb-ctx-stat">
          <span class="sb-ctx-stat-label">{{ t('task.stat_created') }}</span>
          <span class="sb-ctx-stat-value">{{ dateDisplay }}</span>
        </div>
        <div v-if="task.source" class="sb-ctx-stat">
          <span class="sb-ctx-stat-label">{{ t('task.stat_source') }}</span>
          <span class="sb-ctx-stat-value">{{ task.source === 'record' ? t('task.source_record') : t('task.source_upload') }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Task } from '@/api/types'

const { t } = useI18n()

const props = defineProps<{
  task: Task
  open: boolean
  sidebarEl: HTMLElement | null
  buttonRect: DOMRect | null
}>()

const emit = defineEmits<{
  close: []
  rename: []
  retry: []
  delete: []
}>()

const menuRef = ref<HTMLElement | null>(null)
const menuPosition = ref<Record<string, string>>({})
const copied = ref<string | null>(null)

/** 根据侧边栏右边缘 + 按钮垂直位置计算菜单坐标 */
function updatePosition() {
  if (!props.sidebarEl || !props.buttonRect) return
  const sidebarRect = props.sidebarEl.getBoundingClientRect()
  const menuWidth = 220
  const gap = 8

  nextTick(() => {
    const left = sidebarRect.right - menuWidth - gap
    let top = props.buttonRect!.top

    // 防止底部溢出视口
    const menuHeight = menuRef.value?.offsetHeight ?? 280
    if (top + menuHeight > window.innerHeight - 8) {
      top = window.innerHeight - menuHeight - 8
    }
    // 防止顶部溢出
    if (top < 8) top = 8

    menuPosition.value = {
      position: 'fixed',
      left: left + 'px',
      top: top + 'px',
      width: menuWidth + 'px',
    }
  })
}

watch(() => props.open, (val) => {
  if (val) {
    updatePosition()
    setTimeout(() => document.addEventListener('click', onClickOutside, { once: true }), 0)
  } else {
    copied.value = null
  }
})

function onClickOutside() {
  emit('close')
}

// ─── 复制 ───

async function onCopy(type: string) {
  const text = getCopyText(type)
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = type
    setTimeout(() => { if (copied.value === type) copied.value = null }, 1500)
  } catch { /* 剪贴板不可用时静默降级 */ }
}

function getCopyText(type: string): string {
  switch (type) {
    case 'title': return props.task.title || props.task.audio_name || ''
    case 'summary': return props.task.summary || ''
    default: return ''
  }
}

// ─── 统计展示 ───

const dateDisplay = computed(() => {
  const raw = props.task.created_at || props.task.meeting_date || ''
  if (!raw) return '—'
  const d = new Date(raw.length <= 10 ? raw + 'T00:00:00' : raw)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
})

const durationDisplay = computed(() => {
  const dur = props.task.audio_duration
  if (!dur) return '—'
  const mins = Math.round(dur / 60)
  if (mins < 60) return t('task.duration.minutes', { m: mins })
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m > 0 ? t('task.duration.hours_minutes', { h, m }) : t('task.duration.hours', { h })
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside)
})
</script>
