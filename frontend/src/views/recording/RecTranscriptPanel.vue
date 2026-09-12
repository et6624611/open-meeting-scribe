<template>
  <div class="rec-transcript" v-show="isVisible">
    <div class="rec-transcript-header">
      <div class="rec-transcript-title">{{ t('recording.tab.transcript') }}</div>
      <div class="rec-transcript-actions">
        <button class="transcript-toggle" :class="{ 'is-active': showTranscript }" @click="$emit('update:showTranscript', !showTranscript)" :title="showTranscript ? t('recording.transcript.hide_title') : t('recording.transcript.show_title')">
          <svg class="toggle-icon-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
          <svg class="toggle-icon-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          <span class="toggle-label">{{ showTranscript ? t('recording.transcript.hide') : t('recording.transcript.show') }}</span>
        </button>
      </div>
    </div>
    <!-- 章节条 -->
    <div class="rec-chapter-strip" v-if="chapters.length > 0">
      <div class="rec-chapter-dots"><span v-for="(_, i) in chapters" :key="i" class="rec-ch-dot" :class="{ 'is-current': i === chapters.length - 1 }"></span></div>
      <div class="rec-chapter-current">
        <span class="rec-chapter-num">{{ chapters.length }}</span>
        <span class="rec-chapter-title">{{ chapters[chapters.length - 1]?.title || t('recording.chapter.discussing') }}</span>
      </div>
    </div>
    <div class="rec-transcript-body" ref="bodyRef">
      <div v-if="!showTranscript" class="rec-hidden-indicator">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
        <span>{{ t('recording.transcript.hidden_indicator', { count: lines.length }) }}</span>
        <button class="rec-hidden-show-btn" @click="$emit('update:showTranscript', true)">{{ t('recording.transcript.show') }}</button>
      </div>
      <div v-if="markerMode && compressedCount > 0" class="rec-marker-compressed">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
        {{ t('recording.marker.compressed', { count: compressedCount }) }}
        <button class="rec-marker-expand-btn" @click="$emit('update:markerMode', false)">{{ t('recording.marker.expand_all') }}</button>
      </div>
      <template v-for="(line, i) in lines" :key="i">
        <div v-if="getChapterStart(i)" class="chapter-divider" :class="{ 'is-current': getChapterStart(i)!.chapterIdx === chapters.length - 1, 'is-expanded': expandedChapters.has(getChapterStart(i)!.chapterIdx) }" @click="$emit('toggleChapter', getChapterStart(i)!.chapterIdx)">
          <div class="chapter-header">
            <div class="chapter-number">{{ chapters[getChapterStart(i)!.chapterIdx].id || getChapterStart(i)!.chapterIdx + 1 }}</div>
            <div class="chapter-info">
              <div class="chapter-title">{{ getChapterStart(i)!.title }}</div>
              <div class="chapter-meta">
                <span>{{ formatTime(chapters[getChapterStart(i)!.chapterIdx].start_ms) }}</span>
                <template v-if="chapters[getChapterStart(i)!.chapterIdx].end_ms"><span class="sep">–</span><span>{{ formatTime(chapters[getChapterStart(i)!.chapterIdx].end_ms || 0) }}</span></template>
                <template v-if="(chapters[getChapterStart(i)!.chapterIdx].key_points || []).length"><span class="sep">·</span><span>{{ t('recording.chapter.key_points_count', { count: (chapters[getChapterStart(i)!.chapterIdx].key_points || []).length }) }}</span></template>
              </div>
              <div v-if="chapters[getChapterStart(i)!.chapterIdx].summary" class="chapter-summary-text">{{ chapters[getChapterStart(i)!.chapterIdx].summary }}</div>
            </div>
            <div class="chapter-chevron"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg></div>
          </div>
          <div class="chapter-body"><div class="chapter-body-inner"><div class="chapter-key-points" v-if="chapters[getChapterStart(i)!.chapterIdx].key_points?.length"><div class="chapter-key-points-title">{{ t('recording.chapter.key_points') }}</div><div v-for="(p, pi) in chapters[getChapterStart(i)!.chapterIdx].key_points" :key="pi" class="chapter-key-point">{{ p }}</div></div></div></div>
        </div>
        <div class="rec-line" v-show="showTranscript && (!markerMode || hasNoteAt(i))" :class="{ 'rec-line-hidden': markerMode && !hasNoteAt(i), 'is-me': isMe(line.speaker_id), 'is-located': locateId === line.speaker_id, 'is-dimmed': locateId !== null && locateId !== line.speaker_id }">
          <div class="rec-line-head">
            <span class="rec-line-speaker" :style="{ '--spk-color': speakerColor(line.speaker_id) }" @click.stop="$emit('openBind', line.speaker_id)">{{ getSpeakerName(line) }}</span>
            <button v-if="!locateId || locateId === line.speaker_id" class="rec-line-locate-btn" @click.stop="$emit('toggleLocate', line.speaker_id)" :title="t('recording.speaker.locate')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></button>
          </div>
          <div class="rec-line-body"><span class="rec-line-text">{{ line.text }}</span></div>
          <div v-if="notesByLine[i]" class="note-inline-card">
            <span class="note-inline-text">{{ notesByLine[i] }}</span>
            <button class="note-inline-delete" @click.stop="$emit('deleteNote', i)" :title="t('recording.notes.delete')"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
          </div>
        </div>
      </template>
      <div v-if="partialText" class="rec-line rec-line-partial" v-show="showTranscript">
        <div class="rec-line-head"><span class="rec-line-speaker">…</span></div>
        <div class="rec-line-body"><span class="rec-line-text">{{ partialText }}</span></div>
      </div>
      <div v-if="lines.length === 0 && !partialText" class="rec-empty">
        <p>{{ t('recording.transcript.empty') }}</p>
        <p class="rec-empty-hint">{{ t('recording.transcript.empty_hint') }}</p>
      </div>
    </div>
    <button class="rec-jump-latest" :class="{ 'is-visible': showJumpBtn }" @click="$emit('jumpLatest')" :title="t('recording.jump_latest')">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="4" x2="12" y2="20"/><polyline points="18 14 12 20 6 14"/></svg>
      {{ t('recording.jump_latest') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSpeakerColor } from '@/utils/speakerColors'
import type { TranscriptLine } from '@/composables/useWebSocket'

const { t } = useI18n()

defineProps<{
  isVisible: boolean
  lines: TranscriptLine[]
  partialText: string
  chapters: Array<{ id?: number; title: string; start_ms: number; end_ms?: number; key_points?: string[]; summary?: string }>
  showTranscript: boolean
  markerMode: boolean
  notesByLine: Record<number, string>
  compressedCount: number
  expandedChapters: Set<number>
  locateId: number | null
  showJumpBtn: boolean
  getSpeakerName: (line: TranscriptLine) => string
  isMe: (speakerId: number) => boolean
  hasNoteAt: (idx: number) => boolean
  getChapterStart: (lineIdx: number) => { title: string; chapterIdx: number } | null
}>()

defineEmits<{
  (e: 'update:showTranscript', val: boolean): void
  (e: 'update:markerMode', val: boolean): void
  (e: 'toggleChapter', idx: number): void
  (e: 'openBind', asrId: number): void
  (e: 'toggleLocate', id: number): void
  (e: 'deleteNote', idx: number): void
  (e: 'jumpLatest'): void
}>()

const bodyRef = ref<HTMLElement | null>(null)
defineExpose({ bodyRef })

function speakerColor(sid: string | number): string { return getSpeakerColor(sid) }
function formatTime(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
</script>
