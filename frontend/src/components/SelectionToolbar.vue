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
    <!-- 保留操作按钮：仅「引用到 AI」——改写/总结/提取决策已下架，
         其能力依赖 AI 且路径单一，由用户在「引用到 AI」中自行达成目的
         Kept action: quote-to-AI only; rewrite/summarize/extract were retired -->
    <button class="sel-tool-btn" @click="onQuoteToAi" :title="t('common.selection_toolbar.quote_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
      {{ t('common.selection_toolbar.quote_to_ai') }}
    </button>
    <!-- AI 书面化选区（WP-3）：仅当选区覆盖转写句时出现；任务未完成（会中/处理中）禁用
         Formalize selection (WP-3): shown only when the selection covers transcript sentences; disabled before completion -->
    <button
      v-if="selectedSentenceIds.length > 0"
      class="sel-tool-btn sel-formal-btn"
      :disabled="!formalizeEnabled"
      :title="formalizeEnabled ? t('common.selection_toolbar.formalize_title') : t('common.selection_toolbar.formalize_disabled_title')"
      @click="onFormalizeSelection"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15z"/></svg>
      {{ t('common.selection_toolbar.formalize_selection', { n: selectedSentenceIds.length }) }}
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
import { getDockBounds, positionAroundAnchor } from '@/utils/popoverPosition'

const { t } = useI18n()

const props = defineProps<{
  containerSelector?: string
  /** 可划词的 textarea 选择器列表：由宿主页面传入，覆盖小结/备注/决策卡等编辑区
   *  Selectable textarea selectors supplied by the host view (summary/notes/decision cards) */
  textareaSelectors?: string[]
  /** 选区书面化是否可用（仅会后 completed 任务；WP-3）/ Whether selection formalize is available (post-meeting only) */
  formalizeEnabled?: boolean
}>()

// 缺省仍只认小结/备注编辑器；决策卡正文与行内编辑区由 GeneratingView 显式接入
const DEFAULT_TEXTAREA_SELECTORS = ['textarea.gen-textarea-editor']

const emit = defineEmits<{
  (e: 'action', action: string, text: string, source: string, blockIndex: number, replacement?: string, createdMapping?: boolean): void
  /** 选区书面化：携带选区覆盖的 sentence_id 集合（WP-3）/ Formalize the sentences covered by the selection */
  (e: 'formalize-selection', sentenceIds: number[]): void
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
/** 选区覆盖的转写句 id（WP-3；空数组＝选区不在转写区）/ Sentence ids covered by the selection (empty = not in transcript) */
const selectedSentenceIds = ref<number[]>([])
let sourceLabel = ''
let blockIndex = -1

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

  // Step 3: 统一走浮层定位真源：上方居中、空间不足翻下方、左右避让停靠栏。
  // Position via the shared helper: above/centered, flip below, dock-aware clamps.
  const { x, y } = positionAroundAnchor(anchor, w, h, getDockBounds())
  toolbarStyle.value = { top: `${y}px`, left: `${x}px` }

  // Step 4: 定位完成，移除 measuring 触发入场动画 / Positioning done, remove measuring to trigger animation
  measuring.value = false
}

function onMouseUp(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (toolbarEl.value?.contains(target)) return

  // ── textarea 选区检测（小结/备注编辑器 + 宿主页面配置的决策卡等） ──
  // textarea selection detection (summary/notes editors + host-configured areas)
  const selectors = props.textareaSelectors?.length ? props.textareaSelectors : DEFAULT_TEXTAREA_SELECTORS
  let textareaEl: HTMLTextAreaElement | null = null
  for (const sel of selectors) {
    textareaEl = target.closest(sel) as HTMLTextAreaElement | null
    if (textareaEl) break
  }
  if (textareaEl) {
    const start = textareaEl.selectionStart
    const end = textareaEl.selectionEnd
    if (start === null || start === end) { visible.value = false; return }
    const text = textareaEl.value.slice(start, end).trim()
    if (!text) { visible.value = false; return }
    selectedTextRef.value = text
    selectedSentenceIds.value = []
    showMappingInput.value = false
    mappingTarget.value = ''
    // 决策卡内的划词标注来源为「决策」，其余编辑器沿用「纪要」
    sourceLabel = textareaEl.closest('.db-node')
      ? t('common.selection_toolbar.source_decision')
      : t('common.selection_toolbar.source_minutes')
    blockIndex = -1
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
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || !sel.toString().trim()) {
    visible.value = false
    selectedSentenceIds.value = []
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
    const range = sel.getRangeAt(0)
    selectedSentenceIds.value = collectSentenceIds(range, container)
    const selRect = range.getBoundingClientRect()
    positionAndShow({ top: selRect.top, left: selRect.left, width: selRect.width, height: selRect.height })
  } catch {
    visible.value = false
  }
}

// ── WP-3 选区书面化 / Selection formalize (WP-3) ──
/** 收集选区相交的转写行 sentence_id（去重、按文档序排序）
 *  Collect sentence_ids of transcript lines intersecting the range (deduped, document order) */
function collectSentenceIds(range: Range, container: Element | null): number[] {
  if (!container) return []
  const ids = new Set<number>()
  for (const el of container.querySelectorAll('.ts-line[data-sentence-id]')) {
    try {
      if (range.intersectsNode(el)) {
        const v = Number(el.getAttribute('data-sentence-id'))
        if (Number.isInteger(v)) ids.add(v)
      }
    } catch { /* 节点游离时 intersectsNode 可能抛错，跳过该行 */ }
  }
  return [...ids].sort((a, b) => a - b)
}

function onFormalizeSelection() {
  if (!props.formalizeEnabled || !selectedSentenceIds.value.length) return
  emit('formalize-selection', [...selectedSentenceIds.value])
  visible.value = false
  selectedSentenceIds.value = []
  window.getSelection()?.removeAllRanges()
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
  window.getSelection()?.removeAllRanges()
  window.dispatchEvent(new CustomEvent('quote-to-ai'))
}

// 改写/总结/提取待办已随工具栏按钮下架：能力依赖 AI 程度高，
// 由用户在「引用到 AI」中自行描述目的达成
// Rewrite/summarize/extract retired with the toolbar buttons; users achieve those
// intents through quote-to-AI with an explicit instruction.

// ── 词条成形校验 / Term shape guard ──
/** 热词与映射的左值都是「词」级单位：多行或超长选区不是词。
 *  data/hotwords.txt 与 data/hotword_mappings.txt 按行解析，一条多行选区落盘后
 *  会被拆成 N 条脏记录，其中含分隔符的那行会变成一条真实生效的映射。 */
const MAX_TERM_LEN = 30
function isUsableTerm(text: string): boolean {
  if (!text.trim() || /[\r\n]/.test(text) || text.length > MAX_TERM_LEN) {
    showToast(t('common.selection_toolbar.term_not_a_word'), 'warn')
    return false
  }
  return true
}

// ── 热词操作 / Hotword actions ──
function onAddHotword() {
  if (!isUsableTerm(selectedTextRef.value)) return
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
  // 修正结果（命中几处 / 未命中）由父组件按后端回执播报：这里此前无条件报「已修正」，
  // 而旧 DOM 替换实际可能一处都没改到，是一条假成功反馈。
  // The parent reports the real hit count from the backend receipt; the unconditional
  // toast here used to claim success even when the DOM rewrite matched nothing.
  emit('action', 'correct', selectedTextRef.value, sourceLabel, blockIndex, target)
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
  const target = mappingTarget.value.trim()
  if (!target) return
  // 左值（误识别写法）来自划词选区，必须先过成形校验；右值来自单行 input，天然安全
  if (!isUsableTerm(selectedTextRef.value)) return
  hw.addItem('mapping', selectedTextRef.value, target)
  // 引导用户将 target 也加入热词 / Guide user to also add target as hotword
  const targetIsHotword = hw.items.value.some(it => it.type === 'word' && it.content === target)
  if (!targetIsHotword) {
    hw.addItem('word', target)
  }
  hw.scheduleSave()
  // 同时回溯修正本场会议已存的原文/纪要/决策/洞察/导出件 / Also correct this meeting's stored artifacts
  // createdMapping=true 让父组件的反馈同时涵盖「映射已保存」这一事实（吐司条一次只显一条）。
  emit('action', 'correct', selectedTextRef.value, sourceLabel, blockIndex, target, true)
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
