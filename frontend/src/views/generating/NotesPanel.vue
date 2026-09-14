<template>
  <!-- 随记面板 / Quick notes panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <MdBlockEditor
      :markdown="markdown"
      @change="emit('change', $event)"
      ref="editor"
      :empty-text="t('generating.notes.placeholder')"
      :inline-diff-block-index="inlineDiffBlockIndex"
      :inline-diff-original="inlineDiffOriginal"
      :inline-diff-edited="inlineDiffEdited"
      @accept-diff="emit('accept-diff')"
      @reject-diff="emit('reject-diff')"
    />
    <span class="task-notes-saved" :class="{ show: notesSaved }">{{ t('generating.notes.saved') }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import MdBlockEditor from '@/components/MdBlockEditor.vue'

const { t } = useI18n()

defineProps<{
  visible: boolean
  markdown: string
  notesSaved: boolean
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

const editor = ref<InstanceType<typeof MdBlockEditor> | null>(null)

defineExpose({
  updateBlock: (blockIndex: number, newSource: string) => editor.value?.updateBlock(blockIndex, newSource),
  replaceTextInBlock: (blockIndex: number, oldText: string, newText: string) => editor.value?.replaceTextInBlock(blockIndex, oldText, newText),
})
</script>
