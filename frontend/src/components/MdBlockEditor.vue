<template>
  <div class="md-preview md-block-editor">
    <!-- 快捷键提示入口（置于顶部，配合 float 定位右上角） / Shortcut hint entry (placed at top, positioned at top-right via float) -->
    <div class="md-shortcut-hint" ref="shortcutBtnRef" @click="toggleShortcuts">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <rect x="2" y="4" width="20" height="16" rx="2"/>
        <line x1="6" y1="8" x2="6.01" y2="8"/>
        <line x1="10" y1="8" x2="10.01" y2="8"/>
        <line x1="14" y1="8" x2="14.01" y2="8"/>
        <line x1="18" y1="8" x2="18.01" y2="8"/>
        <line x1="8" y1="12" x2="16" y2="12"/>
        <line x1="8" y1="16" x2="16" y2="16"/>
      </svg>
    </div>
    <!-- 快捷键列表 Popover / Shortcut list popover -->
    <div v-if="showShortcuts" class="md-shortcut-popover" :style="popoverStyle" @click.stop>
      <div class="md-shortcut-row" v-for="s in shortcutItems" :key="s.key">
        <kbd>{{ s.key }}</kbd>
        <span>{{ s.label }}</span>
      </div>
    </div>
    <div
      v-for="(block, idx) in blocks"
      :key="idx"
      class="md-block"
      :data-block-index="idx"
      :class="{
        'is-editing': editingIndex === idx,
        'is-ai-generated': block.isAi,
        [`md-block-${block.type}`]: true,
      }"
      @dblclick="onBlockClick(idx)"
    >
      <!-- 编辑模式 / Edit mode -->
      <textarea
        v-if="editingIndex === idx"
        ref="textareaRefs"
        class="md-block-textarea"
        :value="editSource"
        :rows="Math.max(editSource.split('\n').length, 1)"
        spellcheck="false"
        @input="onTextareaInput"
        @blur="onBlur"
        @keydown="onKeydown"
      />
      <!-- 预览模式 / Preview mode -->
      <template v-else>
        <div class="md-block-render" v-html="renderBlock(block)"></div>
        <!-- 行间编辑 diff 视图 / Inline edit diff view -->
        <div v-if="inlineDiffBlockIndex === idx && inlineDiffOriginal" class="md-inline-diff">
          <div class="md-diff-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="14" height="14"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            <span>{{ t('common.inline_edit_diff_title') }}</span>
          </div>
          <div class="md-diff-body">
            <p class="md-diff-line"><span class="diff-del">{{ shortDiffText(inlineDiffOriginal) }}</span></p>
            <p v-if="inlineDiffEdited" class="md-diff-line"><span class="diff-add">{{ shortDiffText(inlineDiffEdited) }}</span></p>
          </div>
          <div class="md-diff-actions">
            <IconButton class="diff-accept-btn" :label="t('common.inline_edit_accept')" show-label @click="$emit('accept-diff')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
            </IconButton>
            <button class="diff-reject-btn" @click="$emit('reject-diff')">{{ t('common.inline_edit_reject') }}</button>
          </div>
        </div>
        <!-- hover 操作按钮 / Hover action buttons -->
        <button class="md-block-action-btn" @click.stop="toggleBlockMenu(idx)">
          <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
        </button>
        <!-- 块操作菜单 / Block action menu -->
        <div v-if="blockMenuIdx === idx" class="md-block-menu" @click.stop>
          <button class="md-block-menu-item" @click="onMenuAction('edit', idx)">
            <span class="md-block-menu-icon">✎</span>
            <span>{{ t('generating.block_menu.edit') }}</span>
          </button>
          <button v-if="block.type !== 'heading'" class="md-block-menu-item" @click="onMenuAction('heading', idx)">
            <span class="md-block-menu-icon">H</span>
            <span>{{ t('generating.block_menu.to_heading') }}</span>
          </button>
          <button v-if="block.type !== 'list'" class="md-block-menu-item" @click="onMenuAction('list', idx)">
            <span class="md-block-menu-icon">☰</span>
            <span>{{ t('generating.block_menu.to_list') }}</span>
          </button>
          <button v-if="block.type !== 'paragraph'" class="md-block-menu-item" @click="onMenuAction('paragraph', idx)">
            <span class="md-block-menu-icon">¶</span>
            <span>{{ t('generating.block_menu.to_paragraph') }}</span>
          </button>
          <div class="md-block-menu-sep"></div>
          <button class="md-block-menu-item md-block-menu-danger" @click="onMenuAction('delete', idx)">
            <span class="md-block-menu-icon">✕</span>
            <span>{{ t('generating.block_menu.delete') }}</span>
          </button>
        </div>
      </template>
    </div>
    <div v-if="blocks.length === 0" class="md-block-empty" @dblclick="createFirstBlock">
      <span>{{ emptyText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBlockEditor } from '@/composables/useBlockEditor'
import IconButton from '@/components/common/IconButton.vue'

const { t } = useI18n()

const props = defineProps<{
  markdown: string
  readonly?: boolean
  emptyText?: string
  /** 行间编辑 diff 目标块索引 / Inline edit diff target block index */
  inlineDiffBlockIndex?: number
  /** 行间编辑原文 / Inline edit original text */
  inlineDiffOriginal?: string
  /** 行间编辑改写结果 / Inline edit edited text */
  inlineDiffEdited?: string
}>()

const emit = defineEmits<{
  (e: 'change', md: string): void
  (e: 'accept-diff'): void
  (e: 'reject-diff'): void
}>()

const { blocks, editingIndex, loadMarkdown, getMarkdown, enterEdit, exitEdit, cancelEdit, updateBlock, replaceTextInBlock, insertAfter, removeBlock, convertBlock, renderBlock } = useBlockEditor(
  (md) => emit('change', md)
)

const editSource = ref('')
const textareaRefs = ref<HTMLTextAreaElement[]>([])

/** 截断 diff 文本 / Truncate diff text for display */
function shortDiffText(text: string | undefined): string {
  if (!text) return ''
  return text.length > 200 ? text.slice(0, 200) + '…' : text
}

// 块间切换时阻止旧 textarea 的 blur 事件干扰 / Block inter-block transitions to prevent old textarea blur interference
let isTransitioning = false

// ── 快捷键提示 / Shortcut hints ──
const showShortcuts = ref(false)
const shortcutBtnRef = ref<HTMLElement | null>(null)
const popoverStyle = ref<Record<string, string>>({})

function toggleShortcuts() {
  showShortcuts.value = !showShortcuts.value
  if (showShortcuts.value && shortcutBtnRef.value) {
    const rect = shortcutBtnRef.value.getBoundingClientRect()
    popoverStyle.value = {
      top: `${rect.bottom + 4}px`,
      right: `${window.innerWidth - rect.right}px`,
    }
  }
}

const shortcutItems = computed(() => [
  { key: t('generating.block_editor.shortcut.dblclick'), label: t('generating.block_editor.shortcut.edit') },
  { key: 'Enter', label: t('generating.block_editor.shortcut.new_block') },
  { key: '⇧Enter', label: t('generating.block_editor.shortcut.line_break') },
  { key: '↑ / ↓', label: t('generating.block_editor.shortcut.navigate') },
  { key: '⌘Enter', label: t('generating.block_editor.shortcut.confirm') },
  { key: 'Esc', label: t('generating.block_editor.shortcut.cancel') },
  { key: '⌫', label: t('generating.block_editor.shortcut.delete') },
])

function onDocClick(e: MouseEvent) {
  if (showShortcuts.value && !shortcutBtnRef.value?.contains(e.target as Node)) {
    showShortcuts.value = false
  }
  // 点击菜单外部时关闭块菜单 / Close block menu on outside click
  if (blockMenuIdx.value !== null) {
    const menu = document.querySelector('.md-block-menu')
    const btn = document.querySelector('.md-block-action-btn')
    if (menu && !menu.contains(e.target as Node) && btn && !btn.contains(e.target as Node)) {
      blockMenuIdx.value = null
    }
  }
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

// ── 块操作菜单 / Block action menu ──
const blockMenuIdx = ref<number | null>(null)

function toggleBlockMenu(idx: number) {
  blockMenuIdx.value = blockMenuIdx.value === idx ? null : idx
}

function onMenuAction(action: string, idx: number) {
  blockMenuIdx.value = null
  if (action === 'edit') {
    onBlockClick(idx)
  } else if (action === 'delete') {
    removeBlock(idx)
  } else if (action === 'heading' || action === 'list' || action === 'paragraph') {
    convertBlock(idx, action as 'heading' | 'list' | 'paragraph')
  }
}

watch(() => props.markdown, (md) => {
  if (md !== undefined && md !== null) {
    // 跳过由内部 onChange 回写到父组件再传回的 prop 变化， / Skip prop changes caused by internal onChange write-back to parent,
    // 仅响应真正的外部变更（AI 注入、API 加载等） / only respond to genuine external changes (AI injection, API loading, etc.)
    if (md === getMarkdown()) return
    loadMarkdown(md)
  }
}, { immediate: true })

function createFirstBlock() {
  if (blocks.value.length > 0) return
  insertAfter(-1)
  editSource.value = ''
  enterEdit(0)
  focusTextareaAt(0, 'end')
}

function onBlockClick(idx: number) {
  if (props.readonly) return
  if (editingIndex.value !== null) return
  const block = blocks.value[idx]
  if (!block) return
  editSource.value = block.source
  enterEdit(idx)
}

function onTextareaInput(e: Event) {
  const textarea = e.target as HTMLTextAreaElement
  editSource.value = textarea.value
  textarea.style.height = 'auto'
  textarea.style.height = textarea.scrollHeight + 'px'
}

function onBlur() {
  if (isTransitioning) return
  if (editingIndex.value === null) return
  exitEdit(editingIndex.value, editSource.value)
}

// ── 光标是否在 textarea 首行 / 末行 / Cursor on first/last line of textarea ──
function isCursorOnFirstLine(ta: HTMLTextAreaElement): boolean {
  const pos = ta.selectionStart
  const textBefore = ta.value.substring(0, pos)
  return !textBefore.includes('\n')
}

function isCursorOnLastLine(ta: HTMLTextAreaElement): boolean {
  const pos = ta.selectionEnd
  const textAfter = ta.value.substring(pos)
  return !textAfter.includes('\n')
}

/** 滚动容器使 textarea 出现在可视区域底部往上 1/3 处 / Scroll container to position textarea at lower 1/3 of viewport */
function scrollTextareaIntoView(ta: HTMLElement) {
  // 查找最近的滚动容器（overflow-y: auto/scroll 的祖先） / Find nearest scroll container (ancestor with overflow-y: auto/scroll)
  let container: HTMLElement | null = ta.parentElement
  while (container && container !== document.body) {
    const style = getComputedStyle(container)
    if (style.overflowY === 'auto' || style.overflowY === 'scroll') break
    container = container.parentElement
  }
  if (!container || container === document.body) {
    // 兑底：使用 window / Fallback: use window
    ta.scrollIntoView({ block: 'end', behavior: 'smooth' })
    return
  }

  const taRect = ta.getBoundingClientRect()
  const containerRect = container.getBoundingClientRect()
  // textarea 在容器内容中的位置 / textarea position in container content
  const taTopInContent = taRect.top - containerRect.top + container.scrollTop
  // 目标：textarea 出现在容器可视区域 2/3 高度处 / Target: textarea appears at 2/3 height of container viewport
  const desiredViewportPos = container.clientHeight * 2 / 3
  const targetScroll = taTopInContent - desiredViewportPos
  container.scrollTo({ top: Math.max(0, targetScroll), behavior: 'smooth' })
}

function focusTextareaAt(_idx: number, position: 'start' | 'end') {
  nextTick(async () => {
    await nextTick()
    const ta = document.querySelector('.md-block.is-editing textarea') as HTMLTextAreaElement | null
    if (!ta) return
    ta.focus()
    scrollTextareaIntoView(ta)
    if (position === 'end') {
      ta.setSelectionRange(ta.value.length, ta.value.length)
    } else {
      ta.setSelectionRange(0, 0)
    }
    ta.style.height = 'auto'
    ta.style.height = ta.scrollHeight + 'px'
  })
}

function onKeydown(e: KeyboardEvent) {
  const ta = e.target as HTMLTextAreaElement

  if (e.key === 'Escape') {
    e.preventDefault()
    cancelEdit()
    return
  }

  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    if (editingIndex.value !== null) exitEdit(editingIndex.value, editSource.value)
    return
  }

  // Enter → 保存当前块，新建空块并进入编辑 / Enter → save current block, create new empty block and enter edit
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (editingIndex.value === null) return
    const curIdx = editingIndex.value
    isTransitioning = true
    exitEdit(curIdx, editSource.value)
    const newIdx = insertAfter(curIdx)
    editSource.value = ''
    enterEdit(newIdx)
    focusTextareaAt(newIdx, 'end')
    nextTick(() => { isTransitioning = false })
    return
  }

  // Shift+Enter → 块内换行（textarea 原生行为，不拦截） / Shift+Enter → line break within block (native textarea behavior, not intercepted)

  // ↑ 光标在首行 → 跳到上一个块 / ↑ Cursor on first line → jump to previous block
  if (e.key === 'ArrowUp' && isCursorOnFirstLine(ta)) {
    e.preventDefault()
    if (editingIndex.value !== null && editingIndex.value > 0) {
      const curIdx = editingIndex.value
      isTransitioning = true
      exitEdit(curIdx, editSource.value)
      const prevIdx = curIdx - 1
      editSource.value = blocks.value[prevIdx].source
      enterEdit(prevIdx)
      focusTextareaAt(prevIdx, 'end')
      nextTick(() => { isTransitioning = false })
    }
    return
  }

  // ↓ 光标在末行 → 跳到下一个块 / ↓ Cursor on last line → jump to next block
  if (e.key === 'ArrowDown' && isCursorOnLastLine(ta)) {
    e.preventDefault()
    if (editingIndex.value !== null && editingIndex.value < blocks.value.length - 1) {
      const curIdx = editingIndex.value
      isTransitioning = true
      exitEdit(curIdx, editSource.value)
      const nextIdx = curIdx + 1
      editSource.value = blocks.value[nextIdx].source
      enterEdit(nextIdx)
      focusTextareaAt(nextIdx, 'start')
      nextTick(() => { isTransitioning = false })
    }
    return
  }

  // Backspace 全选文字 → 删除整个块并跳回上一块 / Backspace with all text selected → delete entire block and jump to previous
  if (e.key === 'Backspace' && ta.selectionStart === 0 && ta.selectionEnd === ta.value.length && ta.value.length > 0) {
    e.preventDefault()
    if (editingIndex.value === null) return
    const curIdx = editingIndex.value
    isTransitioning = true
    const prevIdx = removeBlock(curIdx)
    editingIndex.value = null
    editSource.value = blocks.value[prevIdx]?.source ?? ''
    if (blocks.value.length > 0) {
      enterEdit(prevIdx)
      focusTextareaAt(prevIdx, 'end')
    }
    nextTick(() => { isTransitioning = false })
    return
  }

  // Backspace 空块 → 删除并跳回上一块 / Backspace on empty block → delete and jump to previous
  if (e.key === 'Backspace' && editSource.value === '' && ta.selectionStart === 0) {
    e.preventDefault()
    if (editingIndex.value === null) return
    const curIdx = editingIndex.value
    isTransitioning = true
    const prevIdx = removeBlock(curIdx)
    editingIndex.value = null
    editSource.value = blocks.value[prevIdx]?.source ?? ''
    if (blocks.value.length > 0) {
      enterEdit(prevIdx)
      focusTextareaAt(prevIdx, 'end')
    }
    nextTick(() => { isTransitioning = false })
    return
  }
}

nextTick(() => {
  watch(editingIndex, async (idx) => {
    if (idx !== null) {
      await nextTick()
      const ta = textareaRefs.value?.[0]
      if (ta) {
        ta.focus()
        scrollTextareaIntoView(ta)
        ta.setSelectionRange(ta.value.length, ta.value.length)
        ta.style.height = 'auto'
        ta.style.height = ta.scrollHeight + 'px'
      }
    }
  })
})

defineExpose({
  getMarkdown,
  loadMarkdown,
  updateBlock,
  replaceTextInBlock,
  isEditing: () => editingIndex.value !== null,
})
</script>
