<template>
  <!-- 顶栏 -->
  <div class="rec-header">
    <div class="rec-header-left">
      <span class="rec-title" id="recTitle">{{ t('recording.title') }}</span>
      <span class="rec-status" id="recStatus">{{ paused ? t('recording.status.paused') : t('recording.status.identifying') }}</span>
      <span class="rec-speaker-count" :class="{ 'has-update': speakerCountUpdated }" v-if="displaySpeakerCount > 0" :title="t('recording.speaker.count_title')">
        <span class="sc-dot"></span>
        <span>{{ t('recording.speaker.count', { count: displaySpeakerCount }) }}</span>
      </span>
      <span class="rec-project-chip-wrap" v-if="projects.length > 0">
        <span class="gen-meta-project-chip" :class="{ 'is-unbound': !projectId, 'is-bound': !!projectId }" role="button" tabindex="0" @click.stop="$emit('toggleProjectDropdown')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          <span>{{ projectName }}</span>
        </span>
        <div class="gen-meta-proj-dropdown" :class="{ hidden: !showProjectDropdown }">
          <button v-for="p in projects" :key="p.id" class="gen-meta-proj-item" :class="{ 'is-selected': projectId === p.id }" @click="$emit('selectProject', p.id)">{{ p.name }}</button>
          <div class="gen-meta-proj-divider"></div>
          <button class="gen-meta-proj-item" :class="{ 'is-selected': !projectId }" @click="$emit('selectProject', '')">{{ t('generating.meta.no_project') }}</button>
        </div>
      </span>
    </div>
    <div class="rec-header-right">
      <button class="btn-translate" :title="t('common.action.translate')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        {{ t('common.action.translate') }}
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
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
import { useI18n } from 'vue-i18n'
import type { Project } from '@/api/projects'

const { t } = useI18n()

defineProps<{
  paused: boolean
  displaySpeakerCount: number
  speakerCountUpdated: boolean
  projects: Project[]
  projectId: string | null | undefined
  projectName: string
  showProjectDropdown: boolean
  isFocusMode: boolean
}>()

defineEmits<{
  (e: 'toggleProjectDropdown'): void
  (e: 'selectProject', id: string): void
  (e: 'toggleFocus'): void
}>()
</script>
