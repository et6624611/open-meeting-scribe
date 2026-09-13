<template>
  <!-- 随记面板 -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <div class="md-toolbar">
      <button class="md-toolbar-btn" @click="emit('insert-md', 'bold')" :title="t('generating.md_toolbar.bold')"><strong>B</strong></button>
      <button class="md-toolbar-btn" @click="emit('insert-md', 'italic')" :title="t('generating.md_toolbar.italic')"><em>I</em></button>
      <button class="md-toolbar-btn" @click="emit('insert-md', 'code')" :title="t('generating.md_toolbar.code')">&lt;/&gt;</button>
      <span class="md-toolbar-sep"></span>
      <button class="md-toolbar-btn" @click="emit('insert-md', 'heading')" :title="t('generating.md_toolbar.heading')">H</button>
      <button class="md-toolbar-btn" @click="emit('insert-md', 'list')" :title="t('generating.md_toolbar.list')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
      </button>
      <button class="md-toolbar-btn" @click="emit('insert-md', 'quote')" :title="t('generating.md_toolbar.quote')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V21z"/><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3z"/></svg>
      </button>
      <span class="md-toolbar-hint">{{ t('generating.md_toolbar.hint') }}</span>
    </div>
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
  (e: 'insert-md', type: string): void
}>()

const editor = ref<InstanceType<typeof MdBlockEditor> | null>(null)

defineExpose({
  updateBlock: (blockIndex: number, newSource: string) => editor.value?.updateBlock(blockIndex, newSource),
})
</script>
