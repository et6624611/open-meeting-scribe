<template>
  <!-- 随记面板 / Quick notes panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <MdBlockEditor
      :markdown="markdown"
      @change="emit('change', $event)"
      ref="editor"
      :empty-text="t('generating.notes.placeholder')"
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
}>()

const emit = defineEmits<{
  (e: 'change', md: string): void
}>()

const editor = ref<InstanceType<typeof MdBlockEditor> | null>(null)

defineExpose({
  updateBlock: (blockIndex: number, newSource: string) => editor.value?.updateBlock(blockIndex, newSource),
})
</script>
