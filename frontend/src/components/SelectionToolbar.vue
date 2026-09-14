<template>
  <div class="selection-toolbar" :class="{ 'is-visible': visible }" :style="toolbarStyle" ref="toolbarEl">
    <button class="sel-tool-btn is-primary" @click="onQuoteToAi" :title="t('common.selection_toolbar.quote_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
      {{ t('common.selection_toolbar.quote_to_ai') }}
    </button>
    <span class="sel-tool-sep"></span>
    <button class="sel-tool-btn" @click="onAction('rewrite')" :title="t('common.selection_toolbar.rewrite_title')">
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
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuoteRef } from '@/composables/useQuoteRef'

const { t } = useI18n()

const props = defineProps<{
  containerSelector?: string
}>()

const emit = defineEmits<{
  (e: 'action', action: string, text: string, source: string, blockIndex: number): void
}>()

const { setQuote } = useQuoteRef()

const visible = ref(false)
const toolbarStyle = ref({ top: '0px', left: '0px' })
const toolbarEl = ref<HTMLElement | null>(null)
let selectedText = ''
let sourceLabel = ''
let blockIndex = -1

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

  selectedText = sel.toString().trim()
  if (!selectedText) { visible.value = false; return }

  const blockEl = (sel.anchorNode as Element)?.closest?.('.md-block')
  if (blockEl) {
    blockIndex = parseInt(blockEl.getAttribute('data-block-index') || '-1')
    const isAi = blockEl.classList.contains('is-ai-generated')
    sourceLabel = isAi ? t('common.selection_toolbar.source_ai') : t('common.selection_toolbar.source_minutes')
  } else {
    sourceLabel = t('common.selection_toolbar.source_minutes')
    blockIndex = -1
  }

  const range = sel.getRangeAt(0)
  const rect = range.getBoundingClientRect()
  const toolbarWidth = 320
  const toolbarHeight = 40
  let top = rect.top - toolbarHeight - 8
  let left = rect.left + rect.width / 2 - toolbarWidth / 2

  if (top < 0) top = rect.bottom + 8
  if (left < 8) left = 8
  if (left + toolbarWidth > window.innerWidth - 8) left = window.innerWidth - toolbarWidth - 8

  toolbarStyle.value = { top: top + 'px', left: left + 'px' }
  visible.value = true
}

function onMouseDown(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (toolbarEl.value?.contains(target)) return
  visible.value = false
}

function onScrollCollapse() {
  visible.value = false
}

function onQuoteToAi() {
  setQuote(selectedText, sourceLabel, blockIndex)
  visible.value = false
  window.getSelection()?.removeAllRanges()
  window.dispatchEvent(new CustomEvent('quote-to-ai'))
}

function onAction(action: string) {
  emit('action', action, selectedText, sourceLabel, blockIndex)
  visible.value = false
  window.getSelection()?.removeAllRanges()
}

onMounted(() => {
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
