<template>
  <!-- 顶栏 / Top bar -->
  <div class="rec-header">
    <div class="rec-header-left">
      <span class="rec-title" id="recTitle">{{ t('recording.title') }}</span>
      <span class="rec-status" id="recStatus">{{ paused ? t('recording.status.paused') : t('recording.status.identifying') }}</span>
      <span class="rec-speaker-count" :class="{ 'has-update': speakerCountUpdated }" v-if="displaySpeakerCount > 0" :title="t('recording.speaker.count_title')">
        <span class="sc-dot"></span>
        <span>{{ t('recording.speaker.count', { count: displaySpeakerCount }) }}</span>
      </span>
      <!-- 参会人指示器 / Roster indicator -->
      <span class="rec-roster-wrap">
        <button class="rec-roster-chip" @click.stop="$emit('toggleRoster')" :title="t('recording.roster.title')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          <span>{{ t('recording.roster.count', { count: rosterCount }) }}</span>
        </button>
        <div v-if="showRosterDropdown" ref="rosterDropdownRef" class="rec-roster-dropdown" @click.stop>
          <div class="rec-roster-search">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              ref="rosterSearchRef"
              :value="rosterSearch"
              @input="$emit('update:rosterSearch', ($event.target as HTMLInputElement).value)"
              :placeholder="t('recording.roster.add_placeholder')"
              autocomplete="off"
              @keydown="$emit('roster-keydown', $event)"
            />
          </div>
          <!-- 当前参会人列表 / Current roster -->
          <div class="rec-roster-list" v-if="roster.length > 0">
            <div v-for="(name, idx) in roster" :key="'r'+idx" class="rec-roster-item">
              <span class="rec-roster-name">{{ normalizeSpeakerName(name) || t('recording.speaker.default_name') }}</span>
              <button class="rec-roster-remove" :title="t('recording.roster.remove')" @click="$emit('rosterRemove', idx)">
                <svg width="8" height="8" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3l6 6M9 3l-6 6"/></svg>
              </button>
            </div>
          </div>
          <div v-else class="rec-roster-empty">{{ t('recording.roster.empty') }}</div>
          <!-- 搜索结果 / Search results -->
          <div class="rec-roster-results" v-if="filteredRosterSpeakers.length > 0">
            <div
              v-for="(s, idx) in filteredRosterSpeakers" :key="s.id"
              class="rec-roster-result"
              :class="{ 'is-focused': rosterFocusIdx === idx }"
              @click="$emit('rosterSelect', s)"
            >
              <span class="rec-roster-dot" :style="{ background: getSpeakerColor(s.id) }"></span>
              <span>{{ normalizeSpeakerName(s.name) || t('recording.speaker.default_name') }}</span>
            </div>
          </div>
          <!-- 新建入口 / Create entry -->
          <div v-if="rosterSearch && filteredRosterSpeakers.length === 0" class="rec-roster-create" @click="$emit('rosterCreate')">
            {{ t('recording.roster.create_hint', { name: rosterSearch }) }}
          </div>
        </div>
      </span>
      <span class="rec-project-chip-wrap">
        <span class="gen-meta-project-chip" :class="{ 'is-unbound': !projectId, 'is-bound': !!projectId }" role="button" tabindex="0" :title="projectId ? t('generating.meta.linked_kb_tip') : t('generating.meta.link_kb_tip')" @click.stop="$emit('toggleProjectDropdown')" @keydown.enter.prevent="$emit('toggleProjectDropdown')" @keydown.space.prevent="$emit('toggleProjectDropdown')">
          <svg v-if="projectId" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" fill-opacity="0.15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
          <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
          <span>{{ projectName }}</span>
          <svg v-if="!projectId" class="chip-tail-icon chip-tail-add" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <svg v-else class="chip-tail-icon chip-tail-remove" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </span>
        <div ref="projDropdownRef" class="gen-meta-proj-dropdown" :class="{ hidden: !showProjectDropdown }">
          <template v-if="projects.length > 0">
            <button v-for="p in projects" :key="p.id" data-dd-item class="gen-meta-proj-item" :class="{ 'is-selected': projectId === p.id }" @click="$emit('selectProject', p.id)">{{ p.name }}</button>
            <div class="gen-meta-proj-divider"></div>
            <button data-dd-item class="gen-meta-proj-item" :class="{ 'is-selected': !projectId }" @click="$emit('selectProject', '')">{{ t('generating.meta.no_project') }}</button>
          </template>
          <button v-else data-dd-item class="gen-meta-proj-item gen-meta-proj-cta" @click="$router.push({ name: 'projects' })">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            {{ t('generating.meta.create_kb') }}
          </button>
        </div>
      </span>
    </div>
    <div class="rec-header-right">
      <button v-if="isFocusMode" class="btn-exit-focus" @click="$emit('toggleFocus')" :title="t('recording.focus.exit_title')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
        {{ t('recording.focus.exit') }}
      </button>
      <button v-else class="rec-summary-btn" @click="$emit('toggleFocus')" :title="t('recording.focus.enter_title')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Project } from '@/api/projects'
import type { Speaker } from '@/api/speakers'
import { getSpeakerColor } from '@/utils/speakerColors'
import { normalizeSpeakerName } from '@/utils/speakerDisplay'
import { useDropdownPopup } from '@/composables/useDropdownPopup'

const { t } = useI18n()

const props = defineProps<{
  paused: boolean
  displaySpeakerCount: number
  speakerCountUpdated: boolean
  projects: Project[]
  projectId: string | null | undefined
  projectName: string
  showProjectDropdown: boolean
  isFocusMode: boolean
  // 参会人 / Roster
  rosterCount: number
  showRosterDropdown: boolean
  roster: string[]
  rosterSearch: string
  filteredRosterSpeakers: Speaker[]
  rosterFocusIdx: number
}>()

const emit = defineEmits<{
  (e: 'toggleProjectDropdown'): void
  (e: 'selectProject', id: string): void
  (e: 'closeProjectDropdown'): void
  (e: 'toggleFocus'): void
  // 参会人 / Roster
  (e: 'toggleRoster'): void
  (e: 'update:rosterSearch', value: string): void
  (e: 'roster-keydown', event: KeyboardEvent): void
  (e: 'rosterRemove', index: number): void
  (e: 'rosterSelect', speaker: Speaker): void
  (e: 'rosterCreate'): void
  (e: 'closeRoster'): void
}>()

// ── 弹出交互统一规范（useDropdownPopup）：点击外部关闭 + 键盘导航 / Unified popup spec: click-outside + keyboard nav ──
const projDropdownRef = ref<HTMLElement | null>(null)
useDropdownPopup({
  isOpen: () => props.showProjectDropdown,
  close: () => emit('closeProjectDropdown'),
  root: projDropdownRef,
})

// 参会人下拉已有完整键盘导航（父级 onRosterKeydown），此处仅补「点击外部关闭」与焦点保持
// Roster dropdown already has full keyboard nav (parent onRosterKeydown); add click-outside + focus-keeping only
const rosterDropdownRef = ref<HTMLElement | null>(null)
useDropdownPopup({
  isOpen: () => props.showRosterDropdown,
  close: () => emit('closeRoster'),
  root: rosterDropdownRef,
  keyboard: false,
})
</script>
