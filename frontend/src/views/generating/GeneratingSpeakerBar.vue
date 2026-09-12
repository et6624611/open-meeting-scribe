<template>
  <!-- 说话人身份关联横幅 -->
  <div class="gen-binding-bar" :class="{ hidden: !visible }">
    <div class="gbb-main">
      <div class="gbb-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      </div>
      <div class="gbb-body">
        <div class="gbb-title">{{ t('generating.binding.title') }}</div>
        <div class="gbb-desc">
          {{ t('generating.binding.detected', { count: legend.length }) }}<span v-if="unboundCount > 0" class="gbb-unbound-hint">{{ t('generating.binding.unbound_hint', { count: unboundCount }) }}</span>
        </div>
        <div class="gbb-legend" v-if="legend.length > 0">
          <div
            v-for="item in legend" :key="item.sid"
            class="binding-legend-item"
            :class="{ 'is-bound': item.bound }"
            :style="{ background: getSpeakerBg(item.sid) }"
            @click="emit('open-dropdown', $event, item.sid)"
          >
            <span class="bl-name" :style="{ color: item.color }" :class="{ 'bl-unbound': !item.bound }">{{ item.name || t('generating.speaker_default', { id: item.sid + 1 }) }}</span>
            <span class="bl-locate" :title="t('generating.binding.locate')" @click.stop="emit('locate-speaker', item.sid)">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/></svg>
            </span>
          </div>
        </div>
      </div>
      <div class="gbb-actions">
        <a class="gbb-skip" href="javascript:void(0)" @click="emit('skip')">{{ t('generating.binding.skip') }}</a>
        <button class="btn btn-primary btn-sm" @click="emit('confirm')">{{ t('generating.binding.confirm') }}</button>
        <button class="gbb-close" @click="emit('close')" :title="t('generating.binding.close')">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>
    </div>
    <div class="gbb-hint-bar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      <span>{{ t('generating.binding.hint') }}</span>
    </div>
  </div>

  <!-- 绑定下拉框（Teleport 到 body） -->
  <Teleport to="body">
    <div v-if="dropdown.visible" class="bt-dropdown" :style="{ left: dropdown.x + 'px', top: dropdown.y + 'px' }" @click.stop>
      <div class="bt-dd-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" :placeholder="t('generating.binding.search_placeholder')" autocomplete="off" :value="dropdown.search" @input="emit('update:dropdown-search', ($event.target as HTMLInputElement).value)" @keydown="emit('dropdown-keydown', $event)">
      </div>
      <div class="bt-dd-list">
        <!-- 不关联选项（无搜索词时显示） -->
        <template v-if="!dropdown.search">
          <div class="bt-dropdown-item" :class="{ 'is-selected': !currentMapping[dropdown.speakerId] }" @click="emit('select', dropdown.speakerId, '')">
            <span class="bt-di-name">{{ t('generating.binding.no_bind') }}</span>
          </div>
          <div class="bt-dd-sep"></div>
        </template>
        <!-- 说话人列表 -->
        <template v-if="filteredSpeakers.length > 0">
          <div
            v-for="(s, idx) in filteredSpeakers" :key="s.id"
            class="bt-dropdown-item"
            :class="{ 'is-selected': currentMapping[dropdown.speakerId] === s.id, 'is-focused': dropdown.focusIdx === idx }"
            @click="emit('select', dropdown.speakerId, s.id)"
          >
            <span class="bt-di-name" :style="{ color: currentMapping[dropdown.speakerId] === s.id ? getSpeakerColor(String(dropdown.speakerId)) : undefined }">{{ s.name }}<span v-if="s.role" class="bt-di-role">({{ s.role }})</span></span>
          </div>
        </template>
        <div v-else class="bt-dd-empty">{{ t('generating.binding.no_match') }}</div>
      </div>
      <div class="bt-dd-footer" v-if="dropdown.search && filteredSpeakers.length === 0">
        <div class="bt-dropdown-item" :class="{ 'is-focused': dropdown.focusIdx === 0 }" @click="emit('create-and-bind', dropdown.speakerId, dropdown.search)" style="color: var(--accent)">
          <span style="font-weight: 500">{{ t('generating.binding.create_named') }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { getSpeakerColor } from '@/utils/speakerColors'
import type { Speaker } from '@/api/speakers'

const { t } = useI18n()

defineProps<{
  visible: boolean
  legend: Array<{ sid: number; pct: number; color: string; name: string; bound: boolean }>
  unboundCount: number
  currentMapping: Record<number, string>
  dropdown: {
    visible: boolean
    speakerId: number
    x: number
    y: number
    search: string
    focusIdx: number
  }
  filteredSpeakers: Speaker[]
}>()

const emit = defineEmits<{
  (e: 'open-dropdown', event: MouseEvent, speakerId: number): void
  (e: 'locate-speaker', speakerId: number): void
  (e: 'skip'): void
  (e: 'confirm'): void
  (e: 'close'): void
  (e: 'select', speakerId: number, uuid: string): void
  (e: 'create-and-bind', speakerId: number, name: string): void
  (e: 'dropdown-keydown', event: KeyboardEvent): void
  (e: 'update:dropdown-search', value: string): void
}>()

function getSpeakerBg(speakerId: number): string {
  const color = getSpeakerColor(String(speakerId))
  return `${color}18`
}
</script>
