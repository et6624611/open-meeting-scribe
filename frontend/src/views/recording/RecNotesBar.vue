<template>
  <div class="rec-notes-bar">
    <button class="marker-toggle-btn" :class="{ active: markerMode }" @click="$emit('update:markerMode', !markerMode)" :title="t('recording.marker.title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
        <line x1="4" y1="22" x2="4" y2="15"/>
      </svg>
      <span>{{ t('recording.marker.label') }}</span>
      <span class="marker-count" v-if="noteCount > 0">{{ noteCount }}</span>
    </button>
    <textarea ref="textareaRef" class="rec-notes-input" rows="1" :placeholder="t('recording.notes.placeholder')" :value="noteText" @input="$emit('update:noteText', ($event.target as HTMLTextAreaElement).value)" @keydown.enter.exact.prevent="$emit('sendNote')"></textarea>
    <button class="rec-notes-bar-send" :disabled="!noteText.trim()" @click="$emit('sendNote')" :aria-label="t('recording.notes.send')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  markerMode: boolean
  noteText: string
  noteCount: number
}>()

defineEmits<{
  (e: 'update:markerMode', val: boolean): void
  (e: 'update:noteText', val: string): void
  (e: 'sendNote'): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
defineExpose({ textareaRef })
</script>
