<template>
  <div ref="rootRef" class="rec-bind-popover" v-if="visible" :style="popoverStyle" @click.stop>
    <div class="bind-title">{{ t('recording.speaker.bind_title') }}</div>
    <div class="bind-search">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input ref="searchInputRef" v-model="searchQuery" :placeholder="t('recording.speaker.search_placeholder')" />
    </div>
    <div class="bind-list">
      <div
        v-for="spk in filteredSpeakers" :key="spk.id"
        data-dd-item
        class="bind-option" :class="{ 'is-selected': asrId !== null && currentBinding(spk.id) === String(asrId) }"
        @click="$emit('bind', spk)"
      >
        <span class="bind-name" :style="{ color: speakerColor(spk.id) }">{{ normalizeSpeakerName(spk.name) || t('recording.speaker.default_name') }}{{ spk.is_me ? t('recording.speaker.me_suffix') : '' }}</span>
      </div>
      <div v-if="filteredSpeakers.length === 0" class="bind-empty">{{ t('recording.speaker.no_match') }}</div>
    </div>
    <div class="bind-divider"></div>
    <div class="bind-footer">
      <div class="bind-new" data-dd-item @click="$emit('createAndBind')" v-if="searchQuery.trim()">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t('recording.speaker.create_and_bind', { name: searchQuery.trim() }) }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSpeakerColor } from '@/utils/speakerColors'
import { normalizeSpeakerName } from '@/utils/speakerDisplay'
import { useDropdownPopup } from '@/composables/useDropdownPopup'
import type { Speaker } from '@/api/speakers'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  asrId: number | null
  popoverStyle: Record<string, string>
  speakers: Speaker[]
  bindings: Record<number, string>
}>()

const emit = defineEmits<{
  (e: 'bind', spk: Speaker): void
  (e: 'createAndBind'): void
  (e: 'close'): void
}>()

const searchQuery = defineModel<string>({ default: '' })

const filteredSpeakers = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return props.speakers
  return props.speakers.filter(s => s.name.toLowerCase().includes(q))
})

// ── 弹出交互统一规范：点击外部关闭 + ↑↓/Enter 键盘导航 + 焦点保持在检索框 / Unified popup spec ──
const rootRef = ref<HTMLElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)
const { resetNav } = useDropdownPopup({
  isOpen: () => props.visible,
  close: () => emit('close'),
  root: rootRef,
  autoFocus: searchInputRef,
})
// 检索过滤后候选集合已变，重置键盘高亮 / Reset nav highlight when the filter changes the option set
watch(searchQuery, () => resetNav())

function currentBinding(speakerUuid: string): string | undefined {
  for (const [asrId, uuid] of Object.entries(props.bindings)) {
    if (uuid === speakerUuid) return asrId
  }
  return undefined
}

function speakerColor(sid: string | number): string {
  return getSpeakerColor(sid)
}
</script>
