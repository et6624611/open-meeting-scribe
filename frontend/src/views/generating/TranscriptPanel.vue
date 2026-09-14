<template>
  <!-- 原文面板 / Transcript panel -->
  <div class="gen-panel spk-layout-active" :class="{ hidden: !visible }">
    <div class="spk-transcript-layout">
      <div class="spk-transcript-area">
        <div class="spk-transcript-scroll" ref="transcriptAreaEl">
        <!-- 章节生成中提示 / Chapter generation in progress hint -->
        <div class="chapter-loading" v-if="taskStatus === 'completed' && !chapters.length">
          <div class="chapter-loading-spinner"></div>
          <span>{{ t('generating.chapter.dividing') }}</span>
        </div>

        <!-- 聚焦模式横幅 / Focus mode banner -->
        <div class="spk-solo-banner" v-if="speakerFilterSet.size === 1 && focusSpeaker">
          <div class="spk-solo-id">
            <span class="spk-solo-name" :style="{ color: focusSpeaker.color }">{{ focusSpeaker.name }}</span>
            <span class="spk-solo-count">{{ t('generating.speaker_solo.turns', { count: focusSpeaker.turns }) }}</span>
          </div>
          <div class="spk-solo-sep"></div>
          <div class="spk-solo-nav">
            <button class="spk-solo-nav-btn" :title="t('generating.speaker_solo.prev')" @click="emit('nav-focus', -1)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"/></svg>
            </button>
            <span class="spk-solo-pos">{{ focusLineIdx + 1 }} / {{ focusSpeaker.turns }}</span>
            <button class="spk-solo-nav-btn" :title="t('generating.speaker_solo.next')" @click="emit('nav-focus', 1)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </div>
          <div class="spk-solo-sep"></div>
          <button class="spk-solo-close" :title="t('generating.speaker_solo.exit_focus')" @click="emit('clear-filter')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <!-- 原文隐藏提示条 / Hidden transcript indicator bar -->
        <div class="gen-hidden-indicator" v-if="visibleChapterIndices.size === 0 && flatTranscript.length">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
            <line x1="1" y1="1" x2="23" y2="23"/>
          </svg>
          <span>{{ t('generating.transcript.hidden_indicator', { count: flatTranscript.length }) }}</span>
          <button class="gen-hidden-show-btn" @click="emit('show-all-chapters')">{{ t('generating.transcript.show') }}</button>
        </div>

        <div class="gen-loading" v-if="!flatTranscript.length && taskStatus && ['recording', 'processing', 'transcribing', 'summarizing'].includes(taskStatus)">
          <div class="gen-loading-hint"><div class="gen-loading-spinner"></div>{{ t('generating.transcript.loading') }}</div>
          <div class="gen-skeleton"><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div></div>
        </div>
        <div class="gen-empty" v-else-if="!flatTranscript.length && taskStatus === 'pending'">
          <div class="gen-empty-hint">{{ t('generating.transcript.pending') }}</div>
        </div>
        <div class="gen-transcript-list" v-else-if="flatTranscript.length" ref="transcriptListEl">
          <template v-for="item in transcriptItems" :key="item.type === 'chapter' ? 'ch-' + item.chapterIdx : 'line-' + item.lineIdx">
            <!-- 章节分隔卡片 / Chapter divider card -->
            <div v-if="item.type === 'chapter'" class="chapter-divider" :class="{ 'is-current': item.chapterIdx === activeChapterIdx, 'is-expanded': expandedChapters.has(item.chapterIdx) }" :data-chapter="item.chapterIdx">
              <div class="chapter-header" @click="emit('toggle-chapter', item.chapterIdx)">
                <div class="chapter-number">{{ chapters[item.chapterIdx].id }}</div>
                <div class="chapter-info">
                  <div class="chapter-title">{{ chapters[item.chapterIdx].title }}</div>
                  <div class="chapter-meta">
                    <span>{{ formatTimeMs(chapters[item.chapterIdx].start_ms) }} – {{ formatTimeMs(chapters[item.chapterIdx].end_ms) }}</span>
                    <span class="sep">·</span>
                    <span>{{ t('generating.chapter.key_points_count', { count: (chapters[item.chapterIdx].key_points || []).length }) }}</span>
                  </div>
                  <div v-if="chapters[item.chapterIdx].summary" class="chapter-summary-text">{{ chapters[item.chapterIdx].summary }}</div>
                </div>
                <div class="chapter-chevron">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
                </div>
              </div>
              <div class="chapter-progress-bar">
                <div class="chapter-progress-fill" :style="{ width: chapterProgress(item.chapterIdx) + '%' }"></div>
              </div>
              <div class="chapter-body">
                <div class="chapter-body-inner">
                  <div class="chapter-key-points" v-if="chapters[item.chapterIdx].key_points?.length">
                    <div class="chapter-key-points-title">{{ t('generating.chapter.key_points') }}</div>
                    <div v-for="(p, pi) in chapters[item.chapterIdx].key_points" :key="pi" class="chapter-key-point">{{ p }}</div>
                  </div>
                  <!-- 展开的章节卡片内始终显示原文显隐切换按钮 / Always show transcript toggle button inside expanded chapter card -->
                  <button
                    v-if="expandedChapters.has(item.chapterIdx)"
                    class="chapter-view-transcript-btn"
                    :class="{ 'is-active': visibleChapterIndices.has(item.chapterIdx) }"
                    @click="emit('toggle-chapter-transcript', item.chapterIdx)"
                  >
                    <svg class="toggle-icon-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                    <svg class="toggle-icon-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                      <line x1="1" y1="1" x2="23" y2="23"/>
                    </svg>
                    {{ visibleChapterIndices.has(item.chapterIdx) ? t('generating.chapter.hide_transcript') : t('generating.chapter.view_transcript') }}
                  </button>
                </div>
              </div>
            </div>
            <!-- 转写行 / Transcript line -->
            <div
              v-else class="ts-line" v-show="isChapterVisible(getChapterIdxAtTime(chapters, flatTranscript[item.lineIdx].begin_time))"
              :class="{ 
                'is-me': isMeSpeakerId(flatTranscript[item.lineIdx].speaker_id),
                'is-located': isLineLocated(flatTranscript[item.lineIdx].speaker_id),
                'is-dimmed': isLineDimmed(flatTranscript[item.lineIdx].speaker_id),
                'is-playing': item.lineIdx === playingLineIdx
              }"
              :data-begin-time="flatTranscript[item.lineIdx].begin_time"
              :data-line-idx="item.lineIdx"
              @click="emit('seek', flatTranscript[item.lineIdx].begin_time)"
            >
              <div class="ts-line-avatar" :style="{ background: getSpeakerColor(String(flatTranscript[item.lineIdx].speaker_id)) }">{{ avatarInitial(getBindingSpeakerName(flatTranscript[item.lineIdx].speaker_id), flatTranscript[item.lineIdx].speaker_id) }}</div>
              <div class="ts-line-content">
                <div class="ts-line-head">
                  <span class="spk-wrapper" @click.stop>
                    <span
                      class="spk"
                      :class="[
                        getBindingSpeakerName(flatTranscript[item.lineIdx].speaker_id) ? 'spk-bound' : 'spk-unbound',
                        { 'spk-bindable': canBind }
                      ]"
                      :style="{ color: getSpeakerColor(String(flatTranscript[item.lineIdx].speaker_id)) }"
                      @click="emit('speaker-label-click', $event, flatTranscript[item.lineIdx].speaker_id)"
                    >
                      {{ getBindingSpeakerName(flatTranscript[item.lineIdx].speaker_id) || t('generating.speaker_default', { id: flatTranscript[item.lineIdx].speaker_id + 1 }) }}
                    </span>
                    <button
                      class="spk-locate-btn"
                      :class="{ 'is-active': locateSpeakerId === flatTranscript[item.lineIdx].speaker_id }"
                      v-if="!canBind"
                      @click.stop="emit('toggle-locate', flatTranscript[item.lineIdx].speaker_id)"
                      :title="locateSpeakerId === flatTranscript[item.lineIdx].speaker_id ? t('generating.speaker_solo.exit_focus_all') : t('generating.speaker_solo.focus_speaker')"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                    <span class="spk-bind-arrow" v-if="canBind">▾</span>
                  </span>
                  <span class="ts" @click.stop="emit('seek', flatTranscript[item.lineIdx].begin_time)">{{ formatTimeMs(flatTranscript[item.lineIdx].begin_time) }}</span>
                </div>
                <div class="ts-line-body">
                  <span class="txt">{{ flatTranscript[item.lineIdx].text }}</span>
                </div>
              </div>
            </div>
          </template>
        </div>
        </div>

        <!-- 底部音频播放条 / Bottom audio playback bar -->
        <div class="gen-panel-audio-footer" v-if="audioUrl">
          <div class="gen-audio-progress-section">
            <div class="gen-audio-progress" @click="emit('seek-audio', $event)">
              <div class="gen-audio-progress-fill" :style="{ width: audioProgress + '%' }"></div>
            </div>
            <div class="gen-audio-time-row">
              <span class="gen-audio-time-current">{{ audioCurrentTimeStr }}</span>
              <span class="gen-audio-time-remaining">{{ audioRemainingTimeStr }}</span>
            </div>
          </div>
          <div class="gen-audio-controls-group">
            <div class="gen-audio-waveform" :class="{ 'is-paused': !audioPlaying }"><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div></div>
            <button class="gen-audio-skip" @click="emit('skip-audio', -15)" :title="t('generating.transcript.skip_back')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="11,17 6,12 11,7"/><polyline points="18,17 13,12 18,7"/></svg>
            </button>
            <button class="gen-audio-play-btn" @click="emit('toggle-audio')" :title="audioPlaying ? t('generating.transcript.pause_title') : t('generating.transcript.play_title')" :aria-label="audioPlaying ? t('generating.transcript.pause_title') : t('generating.transcript.play_title')">
              <svg v-if="!audioPlaying" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><polygon points="8,5 20,12 8,19"/></svg>
              <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>
            </button>
            <button class="gen-audio-skip" @click="emit('skip-audio', 15)" :title="t('generating.transcript.skip_forward')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="13,17 18,12 13,7"/><polyline points="6,17 11,12 6,7"/></svg>
            </button>
            <button class="gen-audio-speed" @click="emit('cycle-speed')">{{ audioSpeed }}×</button>
          </div>
        </div>
      </div>

      <!-- 播放跟随恢复按钮 / Resume follow playback button -->
      <button
        class="ts-follow-btn" :class="{ 'is-visible': playerPlaying && !followPlayback }"
        @click="emit('resume-follow')" :title="t('generating.speaker_solo.back_to_playback_title')" :aria-label="t('generating.speaker_solo.back_to_playback_title')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polygon points="10,8 16,12 10,16" fill="currentColor" stroke="none"/></svg>
        {{ t('generating.speaker_solo.back_to_playback') }}
      </button>

      <!-- 右侧说话人面板 / Right speaker panel -->
      <div class="spk-panel" v-if="speakerPanelVisible">
        <div class="spk-panel-head">
          <span class="spk-panel-title">
            {{ t('generating.speaker_panel.title') }}
          </span>
          <div class="spk-panel-head-actions">
            <button class="spk-panel-btn spk-search-trigger" :class="{ 'is-active': searchExpanded }" @click="emit('toggle-search')" :title="t('generating.speaker_panel.search')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            </button>
            <button class="spk-panel-btn" :title="t('generating.speaker_panel.collapse')" @click="emit('toggle-panel')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
        </div>
        <div class="spk-search" v-show="searchExpanded || speakerPanelSearch">
          <div class="spk-search-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" class="spk-search-input" :placeholder="t('generating.speaker_panel.search_placeholder')" v-model="speakerPanelSearchVal" @blur="emit('search-blur')" ref="searchInputEl">
          </div>
        </div>
        <div class="spk-list">
          <div
            v-for="sp in panelSpeakerList" :key="sp.speakerId"
            class="spk-item"
            :class="{ 'is-on': speakerFilterSet.has(sp.speakerId), 'is-active': locateSpeakerId === sp.speakerId, 'is-playing': playingSpeakerId === sp.speakerId }"
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
                :class="{ 'is-active': locateSpeakerId === sp.speakerId }"
                @click.stop="emit('toggle-locate', sp.speakerId)"
                :title="locateSpeakerId === sp.speakerId ? t('generating.speaker_solo.exit_focus_all') : t('generating.binding.locate')"
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
            {{ t('generating.speaker_panel.total', { duration: panelTotalDuration, turns: panelTotalTurns }) }}
          </span>
        </div>
      </div>

      <!-- 面板收起时的展开按钮 / Expand button when panel is collapsed -->
      <button class="spk-panel-toggle" v-if="!speakerPanelVisible" @click="emit('toggle-panel')" :title="t('generating.speaker_panel.expand')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
        <span>{{ t('generating.speaker_panel.expand') }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { getSpeakerColor } from '@/utils/speakerColors'
import type { FlatTranscriptLine, Chapter } from '@/api/types'
import type { Speaker } from '@/api/speakers'

const { t } = useI18n()
const userStore = useUserStore()

type TranscriptItem = { type: 'chapter'; chapterIdx: number } | { type: 'line'; lineIdx: number }

const props = defineProps<{
  visible: boolean
  transcriptItems: TranscriptItem[]
  chapters: Chapter[]
  expandedChapters: Set<number>
  visibleChapterIndices: Set<number>
  activeChapterIdx: number
  flatTranscript: FlatTranscriptLine[]
  taskStatus: string | undefined
  canBind: boolean
  speakerFilterSet: Set<number>
  focusSpeaker: { speakerId: number; name: string; color: string; turns: number } | null
  focusLineIdx: number
  locateSpeakerId: number | null
  playingLineIdx: number
  playingSpeakerId: number | null
  playerPlaying: boolean
  followPlayback: boolean
  speakerPanelVisible: boolean
  speakerPanelSearch: string
  searchExpanded: boolean
  panelSpeakerList: Array<{
    speakerId: number; name: string; role: string; isMe: boolean
    color: string; durationStr: string; turns: number
  }>
  panelTotalDuration: string
  panelTotalTurns: number
  currentBindingMapping: Record<number, string>
  speakers: Speaker[]
  audioUrl: string
  audioPlaying: boolean
  audioProgress: number
  audioTimeStr: string
  audioCurrentTimeStr: string
  audioRemainingTimeStr: string
  audioSpeed: number
  audioCurrentTime: number
}>()

const emit = defineEmits<{
  (e: 'toggle-chapter', idx: number): void
  (e: 'toggle-chapter-transcript', idx: number): void
  (e: 'seek', ms: number): void
  (e: 'speaker-label-click', event: MouseEvent, speakerId: number): void
  (e: 'toggle-locate', speakerId: number): void
  (e: 'toggle-speaker', speakerId: number): void
  (e: 'clear-filter'): void
  (e: 'nav-focus', delta: number): void
  (e: 'toggle-panel'): void
  (e: 'toggle-search'): void
  (e: 'search-blur'): void
  (e: 'update:speakerPanelSearch', value: string): void
  (e: 'resume-follow'): void
  (e: 'show-all-chapters'): void
  (e: 'scroll-to-chapter', idx: number): void
  (e: 'toggle-audio'): void
  (e: 'seek-audio', event: MouseEvent): void
  (e: 'skip-audio', seconds: number): void
  (e: 'cycle-speed'): void
}>()

// 模板 refs / Template refs
const transcriptAreaEl = ref<HTMLElement | null>(null)
const transcriptListEl = ref<HTMLElement | null>(null)
const searchInputEl = ref<HTMLInputElement | null>(null)

// v-model for speaker panel search
const speakerPanelSearchVal = computed({
  get: () => props.speakerPanelSearch,
  set: (val) => emit('update:speakerPanelSearch', val),
})

// ─── 工具函数 / Utility functions ───

function formatTimeMs(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function getChapterIdxAtTime(chs: Chapter[], ms: number): number {
  for (let i = chs.length - 1; i >= 0; i--) {
    if (ms >= chs[i].start_ms) return i
  }
  return -1
}

function isChapterVisible(chapterIdx: number): boolean {
  if (chapterIdx < 0) return true
  return props.visibleChapterIndices.has(chapterIdx)
}

function chapterProgress(idx: number): number {
  const ch = props.chapters[idx]
  if (!ch || !props.flatTranscript.length) return 0
  const linesInChapter = props.flatTranscript.filter(l =>
    l.begin_time >= ch.start_ms && l.begin_time <= ch.end_ms
  )
  return linesInChapter.length > 0 ? 100 : 0
}

function getBindingSpeakerName(speakerId: number): string {
  const uuid = props.currentBindingMapping[speakerId]
  if (!uuid) return ''
  const spk = props.speakers.find(s => s.id === uuid)
  return spk?.name || ''
}

/** 头像首字：取名称首字符，无名则用编号 / Avatar initial: first char of name, fallback to ID */
function avatarInitial(name: string, speakerId: number): string {
  if (name && name.trim()) return name.trim()[0]
  return String(speakerId + 1)
}

function isMeSpeakerId(speakerId: number): boolean {
  const uuid = props.currentBindingMapping[speakerId]
  if (!uuid) return false
  const spk = props.speakers.find(s => s.id === uuid)
  if (!spk?.linked_user_id || !userStore.user?.id) return false
  return spk.linked_user_id === userStore.user.id
}

function isLineLocated(speakerId: number): boolean {
  if (props.speakerFilterSet.size > 0) return props.speakerFilterSet.has(speakerId)
  return props.locateSpeakerId !== null && speakerId === props.locateSpeakerId
}

function isLineDimmed(speakerId: number): boolean {
  if (props.speakerFilterSet.size > 0) return !props.speakerFilterSet.has(speakerId)
  return props.locateSpeakerId !== null && speakerId !== props.locateSpeakerId
}

// 暴露 refs 供父组件使用 / Expose refs for parent component
defineExpose({
  transcriptAreaEl,
  transcriptListEl,
  searchInputEl,
})
</script>
