<template>
  <!-- 纪要面板 / Summary panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <div class="gen-loading" v-if="loading">
      <div class="gen-loading-hint"><div class="gen-loading-spinner"></div>{{ t('generating.summary.loading') }}</div>
      <div class="gen-skeleton"><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div></div>
    </div>
    <div class="gen-empty" v-else-if="pending">
      <div class="gen-empty-hint">{{ t('generating.summary.pending') }}</div>
    </div>
    <template v-else>
      <!-- 编辑器工具栏 / Editor toolbar -->
      <div class="gen-ta-toolbar" v-if="hasSummary">
        <button v-if="!isEditing" class="gen-ta-edit-btn" @click="startEdit">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          {{ t('generating.toolbar.edit') }}
        </button>
        <template v-else>
          <button class="gen-ta-save-btn" @click="finishEdit">{{ t('common.save') }}</button>
          <button class="gen-ta-cancel-btn" @click="cancelEdit">{{ t('common.cancel') }}</button>
        </template>
      </div>
      <!-- Markdown textarea 编辑器 / Markdown textarea editor -->
      <div class="gen-textarea-wrap">
        <textarea
          ref="textareaEl"
          class="gen-textarea-editor"
          :class="{ 'is-readonly': !isEditing }"
          :value="displayContent"
          :readonly="!isEditing"
          :placeholder="t('generating.summary.placeholder')"
          spellcheck="false"
          @input="onInput"
          @mouseup="onSelectionChange"
          @keyup="onSelectionChange"
        ></textarea>
      </div>
    </template>
    <!-- 章节回顾卡片 / Chapter review card -->
    <div class="sum-section" v-if="hasSummary && chapters.length > 0">
      <div class="sum-section-label">{{ t('generating.chapter.review') }}</div>
      <div
        v-for="(ch, idx) in chapters" :key="'sum-ch-' + idx"
        class="sum-chapter-card"
        :class="{ 'is-open': expandedChapters.has(idx) }"
      >
        <button class="sum-chapter-header" @click="emit('toggle-chapter', idx)" :title="ch.title">
          <div class="sum-chapter-num">{{ ch.id || idx + 1 }}</div>
          <div class="sum-chapter-info">
            <div class="sum-chapter-title">{{ ch.title }}</div>
            <div class="sum-chapter-meta">
              <span>{{ formatTimeMs(ch.start_ms) }} – {{ formatTimeMs(ch.end_ms) }}</span>
              <span class="sep">·</span>
              <span>{{ t('generating.chapter.key_points_count', { count: (ch.key_points || []).length }) }}</span>
            </div>
          </div>
          <div class="sum-chapter-chevron">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
        </button>
        <ul class="sum-chapter-points" v-if="ch.key_points?.length">
          <li v-for="(p, pi) in ch.key_points" :key="pi">{{ p }}</li>
        </ul>
      </div>
    </div>
    <!-- 决策入口 / Decisions entry -->
    <div class="sum-section" v-if="hasSummary">
      <div class="sum-section-label">{{ t('generating.summary.action_items') }}</div>
      <button class="sum-todos-link" @click="emit('switch-tab', 'todos')" :title="t('generating.summary.view_todos')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
        <span>{{ t('generating.summary.todos_stat', { total: todosCount || '—', done: todosDoneCount || '0' }) }}</span>
        <span class="go">{{ t('generating.summary.view_todos') }}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Chapter } from '@/api/types'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  summaryMd: string
  chapters: Chapter[]
  expandedChapters: Set<number>
  /** 任务状态是否在处理中（loading 态） / Whether task status is processing (loading state) */
  processing: boolean
  /** 任务状态是否为 pending / Whether task status is pending */
  pending: boolean
  /** 是否有纪要内容 / Whether summary content exists */
  hasSummary: boolean
  todosCount: number
  todosDoneCount: number
}>()

const emit = defineEmits<{
  (e: 'change', md: string): void
  (e: 'toggle-chapter', idx: number): void
  (e: 'switch-tab', tabId: string): void
}>()

function formatTimeMs(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const loading = computed(() => props.processing)

// ── textarea 编辑状态 / textarea editing state ──
const textareaEl = ref<HTMLTextAreaElement | null>(null)
const isEditing = ref(false)
const editBuffer = ref('')
const displayContent = computed(() => isEditing.value ? editBuffer.value : props.summaryMd)

function startEdit() {
  editBuffer.value = props.summaryMd
  isEditing.value = true
  nextTick(() => {
    textareaEl.value?.focus()
    autoGrow()
  })
}

function finishEdit() {
  isEditing.value = false
  if (editBuffer.value !== props.summaryMd) {
    emit('change', editBuffer.value)
  }
}

function cancelEdit() {
  isEditing.value = false
  editBuffer.value = props.summaryMd
}

function onInput(e: Event) {
  const val = (e.target as HTMLTextAreaElement).value
  editBuffer.value = val
  autoGrow()
}

function autoGrow() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

// 外部 summaryMd 变化时同步编辑缓冲 / Sync edit buffer when external summaryMd changes
watch(() => props.summaryMd, (val) => {
  if (isEditing.value) editBuffer.value = val
  nextTick(autoGrow)
})

// 面板可见时自适应高度 / Auto-grow when panel becomes visible
watch(() => props.visible, (v) => { if (v) nextTick(autoGrow) })

// ── 选区追踪（行间编辑用） / Selection tracking (for inline edit) ──
function onSelectionChange() {
  const el = textareaEl.value
  if (!el || el.selectionStart === el.selectionEnd) return
  // 选区信息可由外部通过 textareaEl 读取 / Selection info readable externally via textareaEl
}

// ── 行间编辑接口 / Inline edit interface ──
function replaceRange(start: number, end: number, newText: string) {
  const content = isEditing.value ? editBuffer.value : props.summaryMd
  const updated = content.slice(0, start) + newText + content.slice(end)
  editBuffer.value = updated
  emit('change', updated)
}

defineExpose({
  replaceRange,
  /** textarea 元素引用，供 SelectionToolbar 定位 / textarea element ref for SelectionToolbar positioning */
  textareaEl,
})
</script>
