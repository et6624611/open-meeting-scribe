<template>
  <div class="selection-toolbar" :class="{ 'is-visible': visible }" :style="toolbarStyle" ref="toolbarEl">
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
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useHotwordGroups } from '@/composables/useHotwordGroups'
import { showToast } from '@/composables/useToast'

const { t } = useI18n()

const props = defineProps<{
  containerSelector?: string
}>()

const emit = defineEmits<{
  (e: 'action', action: string, text: string, source: string, blockIndex: number, replacement?: string): void
  (e: 'inline-edit', text: string, source: string, blockIndex: number): void
}>()

const { setQuote } = useQuoteRef()
const hw = useHotwordGroups()

const visible = ref(false)
const toolbarStyle = ref({ top: '0px', left: '0px' })
const toolbarEl = ref<HTMLElement | null>(null)
const mappingInputEl = ref<HTMLInputElement | null>(null)
const selectedTextRef = ref('')
const showMappingInput = ref(false)
const mappingTarget = ref('')
let sourceLabel = ''
let blockIndex = -1

// ── 热词匹配计算 / Hotword matching computed ──
const isAlreadyHotword = computed(() =>
  hw.items.value.some(it => it.type === 'word' && it.content === selectedTextRef.value)
)

const matchedMapping = computed(() =>
  hw.items.value.find(it => it.type === 'mapping' && it.content === selectedTextRef.value) || null
)

// 工具栏尺寸动态测量 / Dynamic toolbar size measurement
watch(visible, async (v) => {
  if (v) {
    await nextTick()
    const w = toolbarEl.value?.offsetWidth || 400
    const h = toolbarEl.value?.offsetHeight || 40
    const rect = window.getSelection()?.getRangeAt(0)?.getBoundingClientRect()
    if (!rect) return
    let top = rect.top - h - 8
    let left = rect.left + rect.width / 2 - w / 2
    if (top < 0) top = rect.bottom + 8
    if (left < 8) left = 8
    if (left + w > window.innerWidth - 8) left = window.innerWidth - w - 8
    toolbarStyle.value = { top: top + 'px', left: left + 'px' }
  }
})

function onMouseUp(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (toolbarEl.value?.contains(target)) return

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

  // 先用固定位置显示，watch 会在 visible 变化后重新定位
  toolbarStyle.value = { top: (rect_top(sel) - 48) + 'px', left: '8px' }
  visible.value = true
}

/** 辅助：获取选区 top 坐标 / Helper: get selection rect top */
function rect_top(sel: Selection) {
  try { return sel.getRangeAt(0).getBoundingClientRect().top } catch { return 0 }
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

function onAction(action: string) {
  emit('action', action, selectedTextRef.value, sourceLabel, blockIndex)
  visible.value = false
  window.getSelection()?.removeAllRanges()
}

/** 行间编辑：emit inline-edit 事件，由父组件处理 / Inline edit: emit inline-edit event, handled by parent */
function onInlineEdit() {
  emit('inline-edit', selectedTextRef.value, sourceLabel, blockIndex)
  visible.value = false
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
  hw.addItem('mapping', selectedTextRef.value, mappingTarget.value.trim())
  // 引导用户将 target 也加入热词 / Guide user to also add target as hotword
  const targetIsHotword = hw.items.value.some(it => it.type === 'word' && it.content === mappingTarget.value.trim())
  if (!targetIsHotword) {
    hw.addItem('word', mappingTarget.value.trim())
    showToast(t('common.selection_toolbar.mapping_created_with_hotword', { text: mappingTarget.value.trim() }), 'success')
  } else {
    showToast(t('common.selection_toolbar.mapping_created'), 'success')
  }
  hw.scheduleSave()
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
