<template>
  <!-- 随记面板 / Quick notes panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <!-- 随记改写提案（propose_notes）提示条：与纪要提案同一交互语义——改动在哪就在哪确认 -->
    <div class="gen-prop-bar" v-if="proposal && !previewMode">
      <svg class="gen-prop-bar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      <span class="gen-prop-bar-text">{{ t('generating.notes.proposal_pending', { hunks: statsSafe.hunks, added: statsSafe.added, removed: statsSafe.removed }) }}</span>
      <button class="gen-prop-bar-btn" @click="emit('open-preview')">{{ t('generating.notes.proposal_view') }}</button>
    </div>
    <!-- 原位 diff 预览态：IDE 式锁定编辑，接受/拒绝在文内操作条完成；
         随记是用户原创区，未经点「接受」不会写入任何内容 -->
    <div class="gen-prop-preview" v-if="proposal && previewMode">
      <div class="gen-prop-preview-header">
        <span class="gen-prop-preview-title">{{ t('generating.notes.proposal_label') }}</span>
        <span class="gen-prop-preview-stats">{{ t('generating.notes.proposal_stats', { hunks: statsSafe.hunks, added: statsSafe.added, removed: statsSafe.removed }) }}</span>
      </div>
      <div class="gen-prop-diff">
        <template v-for="seg in segments" :key="seg.key">
          <button v-if="seg.kind === 'gap'" class="gen-prop-gap" @click="emit('toggle-gap', seg.gapKey!)">
            {{ t('generating.notes.proposal_show_lines', { count: seg.gapCount }) }}
          </button>
          <template v-else>
            <div v-for="line in seg.lines" :key="line.key" class="gen-prop-line" :class="line.type === 'add' ? 'is-add' : (line.type === 'del' ? 'is-del' : 'is-same')">{{ line.text || '\u00A0' }}</div>
          </template>
        </template>
      </div>
      <div class="gen-prop-suggestion-bar">
        <span class="gen-prop-hint">{{ t('generating.notes.proposal_hint') }}</span>
        <div class="gen-prop-actions">
          <button class="diff-accept-btn" @click="emit('accept')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
            {{ t('generating.notes.proposal_accept') }}
          </button>
          <button class="diff-reject-btn" @click="emit('reject')">{{ t('generating.notes.proposal_reject') }}</button>
        </div>
      </div>
    </div>
    <!-- 编辑器工具栏 / Editor toolbar（预览态下隐去，避免两套操作入口并存） -->
    <div class="gen-ta-toolbar" v-if="!(proposal && previewMode)">
      <button v-if="!isEditing" class="gen-ta-edit-btn" @click="startEdit">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        {{ t('generating.toolbar.edit') }}
      </button>
      <template v-else>
        <button class="gen-ta-save-btn" @click="finishEdit">{{ t('common.action.save') }}</button>
        <button class="gen-ta-cancel-btn" @click="cancelEdit">{{ t('common.action.cancel') }}</button>
      </template>
    </div>
    <!-- Markdown textarea 编辑器 / Markdown textarea editor -->
    <div class="gen-textarea-wrap" v-if="!(proposal && previewMode)">
      <textarea
        ref="textareaEl"
        class="gen-textarea-editor"
        :class="{ 'is-readonly': !isEditing }"
        :value="displayContent"
        :readonly="!isEditing"
        :placeholder="showNotesEmpty ? '' : t('generating.notes.placeholder')"
        spellcheck="false"
        @input="onInput"
        @mouseup="onSelectionChange"
        @keyup="onSelectionChange"
      ></textarea>
      <!-- 空内容引导：透明热区铺满编辑区（点击任意处进编辑态），视觉卡片收缩为内容宽并居中；
           开始输入后随编辑态消失 -->
      <div v-if="showNotesEmpty" class="notes-empty-sheet" @click="startEdit">
        <div class="notes-empty-guide">
          <div class="neg-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          </div>
          <div class="neg-title">{{ t('generating.notes.empty_title') }}</div>
          <div class="neg-body">{{ t('generating.notes.empty_body') }}</div>
          <div class="neg-foot">{{ t('generating.notes.empty_foot') }}</div>
        </div>
      </div>
    </div>
    <span class="task-notes-saved" :class="{ show: notesSaved }">{{ t('generating.notes.saved') }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DiffSegment } from '@/composables/useSummaryProposal'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  markdown: string
  notesSaved: boolean
  /** 随记改写提案（propose_notes，未落盘）：baseline=当前随记，proposed=AI 建议全文 */
  proposal?: { baseline: string; proposed: string } | null
  /** 原位 diff 预览态（锁定编辑） */
  previewMode?: boolean
  /** diff 渲染段（由 useNotesProposal 派生，与纪要预览同一构造器） */
  segments?: DiffSegment[]
  /** 提案规模摘要（变更块数 + 增/删行数） */
  stats?: { hunks: number; added: number; removed: number }
}>()

const emit = defineEmits<{
  (e: 'change', md: string): void
  (e: 'open-preview'): void
  (e: 'accept'): void
  (e: 'reject'): void
  (e: 'toggle-gap', gapKey: number): void
}>()

// ── textarea 编辑状态 / textarea editing state ──
/** 提案规模默认零值：stats 为可选 prop，模板不能直接取不存在的字段 */
const statsSafe = computed(() => props.stats || { hunks: 0, added: 0, removed: 0 })

const textareaEl = ref<HTMLTextAreaElement | null>(null)
const isEditing = ref(false)
const editBuffer = ref('')
const displayContent = computed(() => isEditing.value ? editBuffer.value : props.markdown)
/** 空内容引导：非编辑态且内容为空白时才浮在编辑器内；进编辑态（开始输入）立即消失 */
const showNotesEmpty = computed(() => !isEditing.value && displayContent.value.trim().length === 0)

function startEdit() {
  editBuffer.value = props.markdown
  isEditing.value = true
  nextTick(() => {
    textareaEl.value?.focus()
    autoGrow()
  })
}

function finishEdit() {
  isEditing.value = false
  if (editBuffer.value !== props.markdown) {
    emit('change', editBuffer.value)
  }
}

function cancelEdit() {
  isEditing.value = false
  editBuffer.value = props.markdown
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

// 外部 markdown 变化时同步编辑缓冲 / Sync edit buffer when external markdown changes
watch(() => props.markdown, (val) => {
  if (isEditing.value) editBuffer.value = val
  nextTick(autoGrow)
})

// 面板可见时自适应高度 / Auto-grow when panel becomes visible
watch(() => props.visible, (v) => { if (v) nextTick(autoGrow) })

// ── 选区追踪（行间编辑用） / Selection tracking (for inline edit) ──
function onSelectionChange() {
  const el = textareaEl.value
  if (!el || el.selectionStart === el.selectionEnd) return
}

// ── 行间编辑接口 / Inline edit interface ──
function replaceRange(start: number, end: number, newText: string) {
  const content = isEditing.value ? editBuffer.value : props.markdown
  const updated = content.slice(0, start) + newText + content.slice(end)
  editBuffer.value = updated
  emit('change', updated)
}

defineExpose({
  replaceRange,
  textareaEl,
})
</script>
