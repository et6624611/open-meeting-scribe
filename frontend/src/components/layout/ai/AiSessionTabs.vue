<template>
  <div class="ai-session-tabs">
    <div class="ai-session-tabs-scroll">
      <button
        v-for="s in visibleSessions" :key="s.id"
        class="ai-session-seg" :class="{ 'is-active': s.id === activeSessionId }"
        :title="s.name || t('ai-panel.session_default')"
        @click="$emit('switch', s.id)"
        @mouseenter="segHover = s.id"
        @mouseleave="segHover = null"
      >
        <input
          v-if="renamingId === s.id"
          ref="renameInputRef"
          class="ai-session-seg-input"
          :value="renameInput" @input="$emit('update:renameInput', ($event.target as HTMLInputElement).value)"
          @keydown="onRenameKey"
          @blur="$emit('confirmRename')"
          @click.stop
          :aria-label="t('ai-panel.rename_session')"
        />
        <span v-else class="ai-session-seg-label">{{ s.name }}</span>
        <span class="ai-session-seg-dot"></span>
        <span v-if="segHover === s.id && s.id !== activeSessionId && renamingId !== s.id" class="ai-session-seg-actions">
          <IconButton class="ai-session-seg-action" :label="t('ai-panel.rename')" @click.stop="$emit('startRename', s.id)">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
          </IconButton>
          <IconButton class="ai-session-seg-action is-close" :label="t('ai-panel.delete')" @click.stop="$emit('delete', s.id)">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
          </IconButton>
        </span>
      </button>
    </div>
    <div v-if="overflowSessions.length > 0" class="ai-session-overflow">
      <IconButton
        class="ai-session-overflow-btn"
        :class="{ 'is-active': showOverflowMenu }"
        :label="t('ai-panel.more_sessions', { count: overflowSessions.length })"
        @click.stop="showOverflowMenu = !showOverflowMenu"
      >
        <svg viewBox="0 0 16 16" fill="currentColor"><circle cx="3.5" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="12.5" cy="8" r="1.2"/></svg>
      </IconButton>
      <div v-if="showOverflowMenu" class="ai-session-overflow-menu" @click.stop>
        <div
          v-for="s in overflowSessions" :key="s.id"
          class="ai-session-overflow-item"
          :class="{ 'is-active': s.id === activeSessionId }"
          @click="$emit('switch', s.id); showOverflowMenu = false"
        >
          <span class="ai-session-overflow-item-label">{{ s.name }}</span>
          <span class="ai-session-overflow-item-actions">
            <IconButton class="ai-session-seg-action" :label="t('ai-panel.rename')" @click.stop="$emit('startRename', s.id)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
            </IconButton>
            <IconButton class="ai-session-seg-action is-close" :label="t('ai-panel.delete')" @click.stop="$emit('delete', s.id); showOverflowMenu = false">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
            </IconButton>
          </span>
        </div>
      </div>
    </div>
    <IconButton class="ai-session-add" :label="t('ai-panel.new_session')" show-label @click="$emit('newSession')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
    </IconButton>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'

const { t } = useI18n()

const props = defineProps<{
  sessions: Array<{ id: string; name: string }>
  activeSessionId: string
  renamingId: string | null
  renameInput: string
}>()

defineEmits<{
  (e: 'switch', id: string): void
  (e: 'newSession'): void
  (e: 'startRename', id: string): void
  (e: 'delete', id: string): void
  (e: 'confirmRename'): void
  (e: 'cancelRename'): void
  (e: 'renameKey', ev: KeyboardEvent): void
  (e: 'update:renameInput', val: string): void
}>()

const MAX_VISIBLE_SESSIONS = 3
const showOverflowMenu = ref(false)
const segHover = ref<string | null>(null)
const renameInputRef = ref<HTMLInputElement | HTMLInputElement[] | null>(null)

const visibleSessions = computed(() => props.sessions.slice(0, MAX_VISIBLE_SESSIONS))
const overflowSessions = computed(() => props.sessions.slice(MAX_VISIBLE_SESSIONS))

function onRenameKey(e: KeyboardEvent) {
  if (e.key === 'Enter') { e.preventDefault(); /* parent handles confirm */ }
  else if (e.key === 'Escape') { e.preventDefault(); /* parent handles cancel */ }
}

defineExpose({ renameInputRef, showOverflowMenu })
</script>
