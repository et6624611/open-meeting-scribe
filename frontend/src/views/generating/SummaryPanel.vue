<template>
  <!-- 纪要面板 / Summary panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <!-- 统一进度面板（REQ-TRANSCRIBE-PROGRESS R1）：与原文面板消费同一 task 数据源 / Unified panel sharing the same task source -->
    <div class="gen-loading" v-if="loading">
      <div v-if="task?.status === 'recording'" class="gen-loading-hint"><div class="gen-loading-spinner"></div>{{ t('generating.summary.loading') }}</div>
      <ProgressDialog v-else :task="task" />
    </div>
    <div class="gen-empty" v-else-if="pending">
      <div class="gen-empty-hint">{{ t('generating.summary.pending') }}</div>
    </div>
    <template v-else>
      <!-- 提案待确认横幅：预览已关闭但提案仍在（侧栏可重新起跳） / Proposal banner: preview closed but proposal pending -->
      <div class="gen-prop-bar" v-if="proposal && !previewMode">
        <svg class="gen-prop-bar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        <span class="gen-prop-bar-text">{{ t('generating.summary.proposal_pending', { hunks: stats.hunks, added: stats.added, removed: stats.removed }) }}</span>
        <button class="gen-prop-bar-btn" @click="emit('open-preview')">{{ t('generating.summary.proposal_view') }}</button>
      </div>
      <!-- 原位 diff 预览态（Layer 1）：IDE 式锁定编辑，接受/拒绝在文内操作条完成 /
           In-place diff preview: editing locked like IDE diff views, accept/reject on the sticky bar -->
      <div class="gen-prop-preview" v-if="proposal && previewMode">
        <div class="gen-prop-preview-header">
          <span class="gen-prop-preview-title">{{ t('generating.summary.proposal_label') }}</span>
          <span class="gen-prop-preview-stats">{{ t('generating.summary.proposal_stats', { hunks: stats.hunks, added: stats.added, removed: stats.removed }) }}</span>
        </div>
        <div class="gen-prop-diff">
          <template v-for="seg in segments" :key="seg.key">
            <button v-if="seg.kind === 'gap'" class="gen-prop-gap" @click="emit('toggle-gap', seg.gapKey!)">
              {{ t('generating.summary.proposal_show_lines', { count: seg.gapCount }) }}
            </button>
            <template v-else>
              <div v-for="line in seg.lines" :key="line.key" class="gen-prop-line" :class="line.type === 'add' ? 'is-add' : (line.type === 'del' ? 'is-del' : 'is-same')">{{ line.text || '\u00A0' }}</div>
            </template>
          </template>
        </div>
        <div class="gen-prop-suggestion-bar">
          <span class="gen-prop-hint">{{ t('generating.summary.proposal_hint') }}</span>
          <div class="gen-prop-actions">
            <button class="diff-accept-btn" @click="emit('accept')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
              {{ t('generating.summary.proposal_accept') }}
            </button>
            <button class="diff-reject-btn" @click="emit('reject')">{{ t('generating.summary.proposal_reject') }}</button>
          </div>
        </div>
      </div>
      <!-- 编辑器工具栏 / Editor toolbar（非预览态与正文框并存，不能是预览的 else 分支） -->
      <div class="gen-ta-toolbar" v-if="hasSummary && !(proposal && previewMode)">
        <button v-if="!isEditing" class="gen-ta-edit-btn" @click="startEdit">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          {{ t('generating.toolbar.edit') }}
        </button>
        <template v-else>
          <button class="gen-ta-save-btn" @click="finishEdit">{{ t('common.action.save') }}</button>
          <button class="gen-ta-cancel-btn" @click="cancelEdit">{{ t('common.action.cancel') }}</button>
        </template>
        <!-- 一页纸系数角标：纪要面预算，改档后下次生成时生效 / One-page badge (summary surface): takes effect on next generation -->
        <PageBudgetBadge
          v-if="taskId"
          class="gen-ta-budget"
          :task-id="taskId"
          surface="summary"
          :factor="task?.one_page?.summary"
        />
      </div>
      <!-- Markdown textarea 编辑器 / Markdown textarea editor（预览态隐去，其余情况始终渲染正文） -->
      <div class="gen-textarea-wrap" v-if="!(proposal && previewMode)">
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
    <!-- 章节回顾卡片 / Chapter review card（预览态隐去，聚焦 diff / hidden while previewing） -->
    <div class="sum-section" v-if="hasSummary && chapters.length > 0 && !(proposal && previewMode)">
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
    <!-- 决策入口 / Decisions entry（预览态隐去 / hidden while previewing） -->
    <div class="sum-section" v-if="hasSummary && !(proposal && previewMode)">
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
import ProgressDialog from './ProgressDialog.vue'
import PageBudgetBadge from '@/components/common/PageBudgetBadge.vue'
import { buildDiffSegments, useSummaryProposal as useSharedSummaryProposal, type DiffSegment, type SummaryProposal } from '@/composables/useSummaryProposal'
import { diffLines, diffStats } from '@/utils/textDiff'
import type { Chapter, Task } from '@/api/types'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  summaryMd: string
  chapters: Chapter[]
  expandedChapters: Set<number>
  /** 完整任务对象：统一进度面板数据源 / Full task for the unified progress panel */
  task: Task | null | undefined
  /** 任务状态是否在处理中（loading 态） / Whether task status is processing (loading state) */
  processing: boolean
  /** 任务状态是否为 pending / Whether task status is pending */
  pending: boolean
  /** 是否有纪要内容 / Whether summary content exists */
  hasSummary: boolean
  todosCount: number
  todosDoneCount: number
  /** 待确认的纪要改写提案（共享单例，由 GeneratingView 透传） / Pending summary proposal (shared singleton, passed down) */
  proposal: SummaryProposal | null
  /** 原位 diff 预览态 / In-place diff preview mode */
  previewMode: boolean
}>()

const emit = defineEmits<{
  (e: 'change', md: string): void
  (e: 'toggle-chapter', idx: number): void
  (e: 'switch-tab', tabId: string): void
  (e: 'open-preview', payload?: undefined): void
  (e: 'accept', payload?: undefined): void
  (e: 'reject', payload?: undefined): void
  (e: 'toggle-gap', gapKey: number): void
}>()

// ── 原位 diff 预览（Layer 1） / In-place diff preview ──
// 共享单例的展开状态直接消费（只读 UI 态，不跨组件传递 props）
const shared = useSharedSummaryProposal()

/** 提案规模摘要：变更块数 + 增/删行数（与侧栏入口卡同一口径） */
const stats = computed(() => {
  const p = props.proposal
  if (!p) return { hunks: 0, added: 0, removed: 0 }
  const lines = diffLines(p.baseline, p.proposed)
  const { added, removed } = diffStats(lines)
  let hunks = 0
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].type !== 'same' && (i === 0 || lines[i - 1].type === 'same')) hunks++
  }
  return { hunks, added, removed }
})

/** 渲染段：hunk + 可展开的无操作区间（随展开状态重算） */
const segments = computed<DiffSegment[]>(() => {
  const p = props.proposal
  if (!p) return []
  return buildDiffSegments(diffLines(p.baseline, p.proposed), 3, shared.expandedGaps.value)
})

function formatTimeMs(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const loading = computed(() => props.processing)

/** 角标从属的任务 ID / Task id the one-page badge belongs to */
const taskId = computed(() => props.task?.task_id ?? '')

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

// textarea 重挂载时重新自适应：loading/预览态切换会卸载正文框（v-if/v-else），
// 挂载后无任何时机触发 autoGrow，高度停在默认值出现滚动条（重新生成纪要后必现）
// Re-run autoGrow when the textarea remounts: loading/preview toggles unmount it via
// v-if/v-else, and no hook fires after remount — height stays at the CSS default.
watch(textareaEl, (el) => { if (el) nextTick(autoGrow) })

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
