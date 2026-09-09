<template>
  <div class="md-preview md-block-editor">
    <div
      v-for="(block, idx) in blocks"
      :key="idx"
      class="md-block"
      :class="{
        'is-editing': editingIndex === idx,
        'is-ai-generated': block.isAi,
        [`md-block-${block.type}`]: true,
      }"
      @dblclick="onBlockClick(idx)"
    >
      <!-- 编辑模式 -->
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
      <!-- 预览模式 -->
      <div v-else class="md-block-render" v-html="renderBlock(block)"></div>
    </div>
    <div v-if="blocks.length === 0" class="md-block-empty">
      <span>{{ emptyText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useBlockEditor } from '@/composables/useBlockEditor'

const props = defineProps<{
  markdown: string
  readonly?: boolean
  emptyText?: string
}>()

const emit = defineEmits<{
  (e: 'change', md: string): void
}>()

const { blocks, editingIndex, loadMarkdown, getMarkdown, enterEdit, exitEdit, cancelEdit, updateBlock, renderBlock } = useBlockEditor(
  (md) => emit('change', md)
)

const editSource = ref('')
const textareaRefs = ref<HTMLTextAreaElement[]>([])

watch(() => props.markdown, (md) => {
  if (md !== undefined && md !== null) loadMarkdown(md)
}, { immediate: true })

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
  if (editingIndex.value === null) return
  exitEdit(editingIndex.value, editSource.value)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    cancelEdit()
  } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    if (editingIndex.value !== null) {
      exitEdit(editingIndex.value, editSource.value)
    }
  }
}

nextTick(() => {
  watch(editingIndex, async (idx) => {
    if (idx !== null) {
      await nextTick()
      const ta = textareaRefs.value?.[0]
      if (ta) {
        ta.focus()
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
  isEditing: () => editingIndex.value !== null,
})
</script>
