<template>
  <div class="ai-feed ai-context-feed">
    <!-- 空状态引导 / Empty state guidance -->
    <div v-if="isEmpty" class="ctx-empty">
      <div class="ctx-empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
      </div>
      <h4>{{ t('ai-panel.context.empty_title') }}</h4>
      <p>{{ t('ai-panel.context.empty_desc') }}</p>
      <div class="ctx-empty-actions">
        <button class="ctx-empty-action" @click="$emit('generateSummary')" :title="t('ai-panel.context.action_generate_summary')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <span>{{ t('ai-panel.context.action_generate_summary') }}</span>
          <span class="shortcut">⌘G</span>
        </button>
        <button class="ctx-empty-action" @click="$emit('goProject')" :title="t('ai-panel.context.action_link_meeting')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          <span>{{ t('ai-panel.context.action_go_kb') }}</span>
          <span class="shortcut">U</span>
        </button>
        <button class="ctx-empty-action" @click="$emit('linkMeeting')" :title="t('ai-panel.context.action_link_meeting')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <span>{{ t('ai-panel.context.action_link_meeting') }}</span>
          <span class="shortcut">L</span>
        </button>
      </div>
    </div>

    <template v-else>
      <!-- 引导横幅 / Guide banner -->
      <div v-if="!heroDismissed" class="ctx-hero">
        <div class="ctx-hero-inner">
          <div class="ctx-hero-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          </div>
          <div class="ctx-hero-text">
            <h3>{{ t('ai-panel.context.hero_title') }}</h3>
            <p>{{ t('ai-panel.context.hero_desc') }}</p>
          </div>
        </div>
        <button class="ctx-hero-dismiss" @click="heroDismissed = true; $emit('dismissHero')" :title="t('ai-panel.context.hero_dismiss')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>

      <!-- 概览统计 / Overview stats -->
      <div class="ctx-overview">
        <div v-if="stats.transcript > 0" class="ctx-stat"><div class="ctx-stat-num">{{ stats.transcript }}</div><div class="ctx-stat-label">{{ t('ai-panel.context.stat_transcript') }}</div></div>
        <div v-if="stats.summary > 0" class="ctx-stat"><div class="ctx-stat-num">{{ stats.summary }}</div><div class="ctx-stat-label">{{ t('ai-panel.context.stat_summary') }}</div></div>
        <div v-if="stats.todos > 0" class="ctx-stat"><div class="ctx-stat-num">{{ stats.todos }}</div><div class="ctx-stat-label">{{ t('ai-panel.context.stat_todos') }}</div></div>
        <div v-if="stats.files > 0" class="ctx-stat"><div class="ctx-stat-num">{{ stats.files }}</div><div class="ctx-stat-label">{{ t('ai-panel.context.stat_files') }}</div></div>
        <div v-if="relatedMeetingCount > 0" class="ctx-stat"><div class="ctx-stat-num">{{ relatedMeetingCount }}</div><div class="ctx-stat-label">{{ t('ai-panel.context.stat_related') }}</div></div>
      </div>

      <!-- 会议产出 / Meeting output -->
      <div class="ctx-section" :class="{ 'is-collapsed': !sections.meeting }">
        <div class="ctx-section-header" @click="sections.meeting = !sections.meeting">
          <div class="ctx-section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <h4><span v-if="panelMounted" v-for="(ch, i) in sectionTitleChars.meeting" :key="i" class="ctx-title-char" :style="{ animationDelay: `${i * 0.06}s` }">{{ ch }}</span></h4>
          </div>
          <div class="ctx-section-header-right">
            <span class="ctx-section-count">{{ meetingOutputCount }} 项</span>
            <svg class="ctx-chevron" :class="{ 'is-collapsed': !sections.meeting }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
        </div>
        <div class="ctx-section-body">
          <div class="ctx-item" @click="$emit('goTranscript')" :title="t('ai-panel.context.transcript_title')">
            <div class="ctx-item-icon type-transcript"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg></div>
            <div class="ctx-item-body"><div class="ctx-item-title">{{ t('ai-panel.context.transcript_title') }}</div><div class="ctx-item-meta"><span>{{ currentTaskDuration }}</span><span class="dot"></span><span>{{ speakerCount }} {{ t('ai-panel.context.speakers_unit') }}</span></div></div>
            <span class="ctx-item-tag">{{ t('ai-panel.context.tag_transcript') }}</span>
          </div>
          <div class="ctx-item" @click="$emit('goSummary')" :title="t('ai-panel.context.summary_title')">
            <div class="ctx-item-icon type-summary"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="10" y2="17"/><polyline points="10 9 9 9 8 9"/></svg></div>
            <div class="ctx-item-body"><div class="ctx-item-title">{{ t('ai-panel.context.summary_title') }}</div><div class="ctx-item-meta"><span>{{ t('ai-panel.context.auto_generated') }}</span><span class="dot"></span><span>{{ chapterCount }} {{ t('ai-panel.context.chapters_unit') }}</span></div></div>
            <span :class="['status-tag', hasSummary ? 'is-ok' : 'is-warn']">{{ hasSummary ? t('ai-panel.context.status_generated') : t('ai-panel.context.status_pending') }}</span>
          </div>
          <div class="ctx-item" @click="$emit('goTodos')" :title="t('ai-panel.context.todo_title', { count: todoCount })">
            <div class="ctx-item-icon type-todo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></div>
            <div class="ctx-item-body"><div class="ctx-item-title">{{ t('ai-panel.context.todo_title_simple') }}</div><div class="ctx-item-meta"><span>{{ todoPending }} {{ t('ai-panel.context.todo_pending') }}</span><span class="dot"></span><span>{{ todoDone }} {{ t('ai-panel.context.todo_done_label') }}</span></div></div>
            <span :class="['status-tag', todoDone > 0 ? (todoPending > 0 ? 'is-warn' : 'is-ok') : 'is-muted']">{{ todoDone > 0 ? (todoPending > 0 ? t('ai-panel.context.status_in_progress') : t('ai-panel.context.status_completed')) : t('ai-panel.context.status_pending') }}</span>
          </div>
        </div>
      </div>

      <!-- 关联知识库 / Linked knowledge base -->
      <div class="ctx-section" :class="{ 'is-collapsed': !sections.files }">
        <div class="ctx-section-header" @click="sections.files = !sections.files">
          <div class="ctx-section-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg><h4><span v-if="panelMounted" v-for="(ch, i) in sectionTitleChars.files" :key="i" class="ctx-title-char" :style="{ animationDelay: `${i * 0.06}s` }">{{ ch }}</span></h4></div>
          <div class="ctx-section-header-right"><span v-if="linkedProject" class="ctx-section-count">1 个</span><svg class="ctx-chevron" :class="{ 'is-collapsed': !sections.files }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg></div>
        </div>
        <div class="ctx-section-body">
          <div v-if="!linkedProject" class="ctx-empty-section">
            <p>{{ t('ai-panel.context.no_files') }}</p>
          </div>
          <div v-else class="ctx-item" @click="$emit('goProject')">
            <div class="ctx-item-icon type-file"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></div>
            <div class="ctx-item-body"><div class="ctx-item-title" :title="linkedProject.name">{{ linkedProject.name }}</div><div class="ctx-item-meta"><span>{{ linkedProject.fileCount }} {{ t('ai-panel.context.kb_file_count') }}</span></div></div>
            <span class="ctx-item-tag">{{ t('ai-panel.context.kb_tag') }}</span>
          </div>
        </div>
      </div>

      <!-- 相关会议 / Related meetings -->
      <div class="ctx-section" :class="{ 'is-collapsed': !sections.related }">
        <div class="ctx-section-header" @click="sections.related = !sections.related">
          <div class="ctx-section-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg><h4><span v-if="panelMounted" v-for="(ch, i) in sectionTitleChars.related" :key="i" class="ctx-title-char" :style="{ animationDelay: `${i * 0.06}s` }">{{ ch }}</span></h4></div>
          <div class="ctx-section-header-right"><span class="ctx-section-count">{{ relatedMeetingCount }} 项</span><svg class="ctx-chevron" :class="{ 'is-collapsed': !sections.related }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg></div>
        </div>
        <div class="ctx-section-body">
          <div v-if="relatedMeetings.length === 0" class="ctx-empty-section"><p>{{ t('ai-panel.context.no_related') }}</p></div>
          <div v-for="meeting in visibleRelatedMeetings" :key="meeting.id" class="ctx-item" @click="$emit('goMeeting', meeting.id)">
            <div class="ctx-item-icon type-meeting"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
            <div class="ctx-item-body"><div class="ctx-item-title" :title="meeting.title">{{ meeting.title }}</div><div class="ctx-item-meta"><span>{{ meeting.date }}</span><span class="dot"></span><span>{{ meeting.duration }}</span></div></div>
            <span class="ctx-item-tag">{{ meeting.tag }}</span>
          </div>
          <button v-if="relatedMeetings.length > MAX_VISIBLE_MEETINGS" class="ctx-show-more" @click="$emit('showAllMeetings')">{{ t('ai-panel.context.show_more', { count: relatedMeetings.length - MAX_VISIBLE_MEETINGS }) }}</button>
        </div>
      </div>

      <!-- 拖拽上传提示（功能开发中） / Drag-to-upload hint (feature in development) -->
      <div class="ctx-drop-hint" style="display: none;">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>
        {{ t('ai-panel.context.drop_hint') }}
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// 分区标题逐字显现触发 / Section title character-by-character reveal trigger
const panelMounted = ref(false)
onMounted(() => { setTimeout(() => { panelMounted.value = true }, 200) })
const sectionTitleChars = computed(() => ({
  meeting: t('ai-panel.context.section_meeting').split(''),
  files: t('ai-panel.context.section_files').split(''),
  related: t('ai-panel.context.section_related').split(''),
}))

defineProps<{
  isEmpty: boolean
  stats: { transcript: number; summary: number; todos: number; files: number }
  meetingOutputCount: number
  currentTaskDuration: string
  speakerCount: number
  chapterCount: number
  hasSummary: boolean
  todoCount: number
  todoPending: number
  todoDone: number
  linkedProject: { id: string; name: string; fileCount: number } | null
  relatedMeetings: Array<{ id: string; title: string; date: string; duration: string; tag: string }>
  visibleRelatedMeetings: Array<{ id: string; title: string; date: string; duration: string; tag: string }>
  relatedMeetingCount: number
}>()

defineEmits<{
  (e: 'generateSummary'): void
  (e: 'linkMeeting'): void
  (e: 'dismissHero'): void
  (e: 'goTranscript'): void
  (e: 'goSummary'): void
  (e: 'goTodos'): void
  (e: 'goProject'): void
  (e: 'goMeeting', meetingId: string): void
  (e: 'showAllMeetings'): void
}>()

const MAX_VISIBLE_MEETINGS = 5
const heroDismissed = ref(localStorage.getItem('ctx_hero_dismissed') === '1')
const sections = ref({ meeting: true, files: true, related: true })
</script>
