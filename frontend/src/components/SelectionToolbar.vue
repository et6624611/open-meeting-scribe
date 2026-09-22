<template>
  <div class="selection-toolbar" :class="{ 'is-visible': visible, 'is-measuring': measuring }" :style="toolbarStyle" ref="toolbarEl">
    <!-- 热词状态区 / Hotword status area -->
    <template v-if="selectedTextRef">
      <!-- 分支A：已是热词 / Branch A: already a hotword -->
      <span v-if="isAlreadyHotword" class="sel-hw-tag is-existing">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M16 14H8a4 4 0 0 0-4 4v2h16v-2a4 4 0 0 0-4-4z"/></svg>
        {{ t('common.selection_toolbar.is_hotword') }}
      </span>
      <!-- 分支B：匹配到映射 source / Branch B: matches mapping source -->
      <template v-else-if="matchedMapping">
        <span class="sel-hw-tag is-mapping">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
          {{ t('common.selection_toolbar.misrecognized') }}
        </span>
        <button class="sel-tool-btn is-correct" @click="onApplyCorrection" :title="t('common.selection_toolbar.apply_correction_title')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="20,6 9,17 4,12"/></svg>
          {{ matchedMapping.target }}
        </button>
      </template>
      <!-- 分支C：全新词 / Branch C: new word -->
      <template v-else>
        <button class="sel-tool-btn" @click="onAddHotword" :title="t('common.selection_toolbar.add_hotword_title')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M16 14H8a4 4 0 0 0-4 4v2h16v-2a4 4 0 0 0-4-4z"/></svg>
          {{ t('common.selection_toolbar.add_hotword') }}
        </button>
        <button class="sel-tool-btn" @click="toggleMappingInput" :title="t('common.selection_toolbar.create_mapping_title')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
          {{ t('common.selection_toolbar.create_mapping') }}
        </button>
      </template>
      <span class="sel-tool-sep"></span>
    </template>
    <!-- 映射内联输入 / Inline mapping input -->
    <div v-if="showMappingInput" class="sel-mapping-row">
      <span class="sel-mapping-source">{{ selectedTextRef }}</span>
      <span class="sel-mapping-arrow">→</span>
      <input ref="mappingInputEl" class="sel-mapping-input" v-model="mappingTarget" :placeholder="t('common.selection_toolbar.mapping_target_placeholder')" @keydown.enter="confirmMapping" @keydown.escape="cancelMapping" @mousedown.stop />
      <button class="sel-tool-btn sel-mapping-confirm" @click="confirmMapping">✓</button>
      <button class="sel-tool-btn sel-mapping-cancel" @click="cancelMapping">✕</button>
    </div>
    <!-- 原有操作按钮 / Original action buttons -->
    <button class="sel-tool-btn is-primary" @click="onQuoteToAi" :title="t('common.selection_toolbar.quote_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
      {{ t('common.selection_toolbar.quote_to_ai') }}
    </button>
    <span class="sel-tool-sep"></span>
    <button class="sel-tool-btn" @click="onInlineEdit" :title="t('common.selection_toolbar.rewrite_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
      {{ t('common.selection_toolbar.rewrite') }}
    </button>
    <button class="sel-tool-btn" @click="onAction('summarize')" :title="t('common.selection_toolbar.summarize_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>
      {{ t('common.selection_toolbar.summarize') }}
    </button>
    <button class="sel-tool-btn" @click="onAction('extract-todo')" :title="t('common.selection_toolbar.extract_todo_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9,11 12,14 22,4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
      {{ t('common.selection_toolbar.extract_todo') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useHotwords } from '@/composables/useHotwords'
import { showToast } from '@/composables/useToast'
import { useEscClose } from '@/composables/useEscClose'

const { t } = useI18n()

const props = defineProps<{
  containerSelector?: string
}>()

const emit = defineEmits<{
  (e: 'action', action: string, text: string, source: string, blockIndex: number, replacement?: string): void
  (e: 'inline-edit', text: string, source: string, blockIndex: number, range?: { start: number; end: number }): void
}>()

const { setQuote } = useQuoteRef()
const hw = useHotwords()

const visible = ref(false)
// ESC 收起浮动工具栏落到状态上；全局兜底只剥 class 会让 visible 卡在 true，
// 下一次选区变化时又被重新显示
// Clear state on ESC; the global class-only fallback left `visible` stuck at true.
useEscClose(visible, () => { visible.value = false })
const measuring = ref(false)
const toolbarStyle = ref({ top: '0px', left: '0px' })
const toolbarEl = ref<HTMLElement | null>(null)
const mappingInputEl = ref<HTMLInputElement | null>(null)
const selectedTextRef = ref('')
const showMappingInput = ref(false)
const mappingTarget = ref('')
let sourceLabel = ''
let blockIndex = -1
let textareaRange: { start: number; end: number } | null = null

// ── 热词匹配计算 / Hotword matching computed ──
const isAlreadyHotword = computed(() =>
  hw.items.value.some(it => it.type === 'word' && it.content === selectedTextRef.value)
)

const matchedMapping = computed(() =>
  hw.items.value.find(it => it.type === 'mapping' && it.content === selectedTextRef.value) || null
)

// ── Mirror div 计算 textarea 内选区坐标 / Calculate selection rect inside textarea via mirror div ──
function getTextareaSelectionRect(
  textarea: HTMLTextAreaElement, start: number, end: number
): { top: number; left: number; width: number; height: number } | null {
  const cs = getComputedStyle(textarea)
  const mirror = document.createElement('div')
  Object.assign(mirror.style, {
    position: 'fixed', top: '0', left: '0',
    visibility: 'hidden', pointerEvents: 'none',
    overflow: 'hidden', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    width: cs.width, boxSizing: cs.boxSizing,
    fontFamily: cs.fontFamily, fontSize: cs.fontSize,
    fontWeight: cs.fontWeight, fontStyle: cs.fontStyle,
    lineHeight: cs.lineHeight, letterSpacing: cs.letterSpacing,
    textTransform: cs.textTransform, padding: cs.padding,
    border: cs.border,
  })
  // 构建镜像内容：选区前文本 + 标记 span / Build mirror content: text before selection + marker span
  mirror.textContent = textarea.value.substring(0, start)
  const marker = document.createElement('span')
  marker.textContent = textarea.value.substring(start, end) || '\u200b'
  mirror.appendChild(marker)
  document.body.appendChild(mirror)

  const mirrorRect = mirror.getBoundingClientRect()
  const markerRect = marker.getBoundingClientRect()
  const relTop = markerRect.top - mirrorRect.top
  const relLeft = markerRect.left - mirrorRect.left
  const h = markerRect.height || parseFloat(cs.lineHeight) || 20
  const w = markerRect.width
  document.body.removeChild(mirror)

  // 转换为视口坐标（减去 textarea 滚动偏移）/ Convert to viewport coords (subtract textarea scroll)
  const taRect = textarea.getBoundingClientRect()
  const top = taRect.top + relTop - textarea.scrollTop
  const left = taRect.left + relLeft - textarea.scrollLeft
  return { top, left, width: w, height: h }
}

// ── 统一定位并显示（消除闪烁）/ Unified position-and-show (flicker-free) ──
async function positionAndShow(anchor: { top: number; left: number; width: number; height: number }) {
  // Step 1: 渲染但不可见 / Render but invisible
  measuring.value = true
  visible.value = true
  await nextTick()

  // Step 2: 测量工具栏实际尺寸 / Measure actual toolbar dimensions
  const w = toolbarEl.value?.offsetWidth || 400
  const h = toolbarEl.value?.offsetHeight || 40
  const anchorBottom = anchor.top + anchor.height

  // Step 3: 计算位置——优先选区上方居中 / Calculate position — prefer centered above selection
  let top = anchor.top - h - 8
  let left = anchor.left + anchor.width / 2 - w / 2

  // 上方溢出 → 翻到下方 / Top overflow → flip below
  if (top < 8) top = anchorBottom + 8
  // 左右边界保护 / Left-right boundary protection
  if (left < 8) left = 8
  if (left + w > window.innerWidth - 8) left = window.innerWidth - w - 8

  toolbarStyle.value = { top: `${top}px`, left: `${left}px` }

  // Step 4: 定位完成，移除 measuring 触发入场动画 / Positioning done, remove measuring to trigger animation
  measuring.value = false
}

function onMouseUp(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (toolbarEl.value?.contains(target)) return

  // ── textarea 选区检测 / textarea selection detection ──
  const textareaEl = target.closest('textarea.gen-textarea-editor') as HTMLTextAreaElement | null
  if (textareaEl) {
    const start = textareaEl.selectionStart
    const end = textareaEl.selectionEnd
    if (start === null || start === end) { visible.value = false; return }
    const text = textareaEl.value.slice(start, end).trim()
    if (!text) { visible.value = false; return }
    selectedTextRef.value = text
    showMappingInput.value = false
    mappingTarget.value = ''
    sourceLabel = t('common.selection_toolbar.source_minutes')
    blockIndex = -1
    textareaRange = { start, end }
    // 使用 mirror div 精确计算选区坐标 / Use mirror div for precise selection coordinates
    const selRect = getTextareaSelectionRect(textareaEl, start, end)
    if (selRect) {
      positionAndShow(selRect)
    } else {
      // Fallback: 定位到 textarea 顶部 / Fallback: position at textarea top
      const rect = textareaEl.getBoundingClientRect()
      positionAndShow({ top: rect.top, left: rect.left, width: rect.width, height: 0 })
    }
    return
  }

  // ── DOM Selection 检测（转写原文面板） / DOM Selection detection (transcript panel) ──
  textareaRange = null
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || !sel.toString().trim()) {
    visible.value = false
    return
  }

  const container = props.containerSelector
    ? document.querySelector(props.containerSelector)
    : document.querySelector('.gen-content')
  if (container && !container.contains(sel.anchorNode)) {
    visible.value = false
    return
  }

  const text = sel.toString().trim()
  if (!text) { visible.value = false; return }

  selectedTextRef.value = text
  showMappingInput.value = false
  mappingTarget.value = ''

  const blockEl = (sel.anchorNode as Element)?.closest?.('.md-block')
  if (blockEl) {
    blockIndex = parseInt(blockEl.getAttribute('data-block-index') || '-1')
    const isAi = blockEl.classList.contains('is-ai-generated')
    sourceLabel = isAi ? t('common.selection_toolbar.source_ai') : t('common.selection_toolbar.source_minutes')
  } else {
    sourceLabel = t('common.selection_toolbar.source_minutes')
    blockIndex = -1
  }

  // 获取选区矩形并一步定位 / Get selection rect and position in one step
  try {
    const selRect = sel.getRangeAt(0).getBoundingClientRect()
    positionAndShow({ top: selRect.top, left: selRect.left, width: selRect.width, height: selRect.height })
  } catch {
    visible.value = false
  }
}

function onMouseDown(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (toolbarEl.value?.contains(target)) return
  visible.value = false
  showMappingInput.value = false
}

function onScrollCollapse() {
  visible.value = false
  showMappingInput.value = false
}

// ── 原有操作 / Original actions ──
function onQuoteToAi() {
  setQuote(selectedTextRef.value, sourceLabel, blockIndex)
  visible.value = false
  textareaRange = null
  window.getSelection()?.removeAllRanges()
  window.dispatchEvent(new CustomEvent('quote-to-ai'))
}

function onAction(action: string) {
  emit('action', action, selectedTextRef.value, sourceLabel, blockIndex)
  visible.value = false
  textareaRange = null
  window.getSelection()?.removeAllRanges()
}

/** 行间编辑：emit inline-edit 事件，由父组件处理 / Inline edit: emit inline-edit event, handled by parent */
function onInlineEdit() {
  emit('inline-edit', selectedTextRef.value, sourceLabel, blockIndex, textareaRange || undefined)
  visible.value = false
  textareaRange = null
  window.getSelection()?.removeAllRanges()
}

// ── 热词操作 / Hotword actions ──
function onAddHotword() {
  hw.addItem('word', selectedTextRef.value)
  hw.scheduleSave()
  showToast(t('common.selection_toolbar.hotword_added', { text: selectedTextRef.value }), 'success')
}

function onApplyCorrection() {
  if (!matchedMapping.value) return
  const target = matchedMapping.value.target || ''
  // 确保 target 也在热词表中 / Ensure target is also in hotwords
  const targetIsHotword = hw.items.value.some(it => it.type === 'word' && it.content === target)
  if (!targetIsHotword && target) {
    hw.addItem('word', target)
  }
  hw.scheduleSave()
  emit('action', 'correct', selectedTextRef.value, sourceLabel, blockIndex, target)
  showToast(t('common.selection_toolbar.correction_applied', { text: target }), 'success')
  visible.value = false
  window.getSelection()?.removeAllRanges()
}

function toggleMappingInput() {
  showMappingInput.value = !showMappingInput.value
  mappingTarget.value = ''
  if (showMappingInput.value) {
    nextTick(() => mappingInputEl.value?.focus())
  }
}

function confirmMapping() {
  if (!mappingTarget.value.trim()) return
  const target = mappingTarget.value.trim()
  hw.addItem('mapping', selectedTextRef.value, target)
  // 引导用户将 target 也加入热词 / Guide user to also add target as hotword
  const targetIsHotword = hw.items.value.some(it => it.type === 'word' && it.content === target)
  if (!targetIsHotword) {
    hw.addItem('word', target)
  }
  hw.scheduleSave()
  // 同时修正当前选区原文 / Also apply correction to the current selection
  emit('action', 'correct', selectedTextRef.value, sourceLabel, blockIndex, target)
  showToast(t('common.selection_toolbar.correction_applied', { text: target }), 'success')
  showMappingInput.value = false
  visible.value = false
  window.getSelection()?.removeAllRanges()
}

function cancelMapping() {
  showMappingInput.value = false
  mappingTarget.value = ''
}

onMounted(() => {
  // 确保热词数据已加载 / Ensure hotword data is loaded
  hw.loadAll()
  document.addEventListener('mouseup', onMouseUp)
  document.addEventListener('mousedown', onMouseDown)
  document.addEventListener('scroll', onScrollCollapse, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('mouseup', onMouseUp)
  document.removeEventListener('mousedown', onMouseDown)
  document.removeEventListener('scroll', onScrollCollapse, true)
})
</script>
