<script setup lang="ts">
/**
 * 原文面板右侧说话人列表 / Transcript speaker side panel
 *
 * 纯展示与交互转发：搜索、筛选、定位、折叠。数据与查询逻辑在父级 useSpeakerPanel。
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

export interface PanelSpeakerItem {
  speakerId: number
  name: string
  role: string
  isMe: boolean
  color: string
  durationStr: string
  turns: number
}

const props = defineProps<{
  visible: boolean
  searchExpanded: boolean
  search: string
  speakers: PanelSpeakerItem[]
  totalDuration: string
  totalTurns: number
  filterSet: Set<number>
  locateSpeakerId: number | null
  playingSpeakerId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:search', value: string): void
  (e: 'toggle-search'): void
  (e: 'toggle-panel'): void
  (e: 'toggle-speaker', speakerId: number): void
  (e: 'toggle-locate', speakerId: number): void
  (e: 'search-blur'): void
}>()

const { t } = useI18n()

const searchInputEl = ref<HTMLInputElement | null>(null)

const searchVal = computed({
  get: () => props.search,
  set: (v: string) => emit('update:search', v),
})

defineExpose({ searchInputEl })
</script>

<template>
  <!-- 右侧说话人面板 / Right speaker panel -->
  <div class="spk-panel" v-if="props.visible">
    <div class="spk-panel-head">
      <span class="spk-panel-title">
        {{ t('generating.speaker_panel.title') }}
      </span>
      <div class="spk-panel-head-actions">
        <button class="spk-panel-btn spk-search-trigger" :class="{ 'is-active': props.searchExpanded }" @click="emit('toggle-search')" :title="t('generating.speaker_panel.search')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </button>
        <button class="spk-panel-btn" :title="t('generating.speaker_panel.collapse')" @click="emit('toggle-panel')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </div>
    </div>
    <div class="spk-search" v-show="props.searchExpanded || props.search">
      <div class="spk-search-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" class="spk-search-input" :placeholder="t('generating.speaker_panel.search_placeholder')" v-model="searchVal" @blur="emit('search-blur')" ref="searchInputEl">
      </div>
    </div>
    <div class="spk-list">
      <div
        v-for="sp in props.speakers" :key="sp.speakerId"
        class="spk-item"
        :class="{ 'is-on': props.filterSet.has(sp.speakerId), 'is-active': props.locateSpeakerId === sp.speakerId, 'is-playing': props.playingSpeakerId === sp.speakerId }"
        @click="emit('toggle-speaker', sp.speakerId)"
      >
        <div class="spk-item-check">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <div class="spk-item-info">
          <span class="spk-item-name" :style="{ color: sp.color }">{{ sp.name }}</span>
          <span class="spk-item-role" :class="{ 'is-me-label': sp.isMe }">{{ sp.isMe ? t('generating.speaker_panel.me_label') : (sp.role || '') }}</span>
          <button
            class="spk-item-locate"
            :class="{ 'is-active': props.locateSpeakerId === sp.speakerId }"
            @click.stop="emit('toggle-locate', sp.speakerId)"
            :title="props.locateSpeakerId === sp.speakerId ? t('generating.speaker_solo.exit_focus_all') : t('generating.binding.locate')"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/></svg>
          </button>
        </div>
        <div class="spk-item-stats">
          <span class="spk-item-dur">{{ sp.durationStr }}</span>
          <span class="spk-item-sep">|</span>
          <span class="spk-item-turns">{{ sp.turns }}</span>
        </div>
      </div>
    </div>
    <div class="spk-panel-footer">
      <span class="spk-footer-summary">
        {{ t('generating.speaker_panel.total', { duration: props.totalDuration, turns: props.totalTurns }) }}
      </span>
    </div>
  </div>

  <!-- 面板收起时的展开按钮 / Expand button when panel is collapsed -->
  <button class="spk-panel-toggle" v-if="!props.visible" @click="emit('toggle-panel')" :title="t('generating.speaker_panel.expand')">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
    <span>{{ t('generating.speaker_panel.expand') }}</span>
  </button>
</template>
