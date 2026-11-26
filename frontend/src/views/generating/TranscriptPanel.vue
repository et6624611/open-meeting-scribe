<template>
  <!-- 原文面板 / Transcript panel -->
  <div class="gen-panel spk-layout-active" :class="{ hidden: !visible }">
    <div class="spk-transcript-layout">
      <div class="spk-transcript-area">
        <!-- 三层视图（书面版/清理版/原文）选择器在 tab 栏右侧下拉（GeneratingView），本面板只消费 layerView -->
        <!-- 书面版状态卡（WP-2）/ Formal-version state card -->
        <FormalVersionCard
          v-if="layerView === 'formal'"
          :state="formalState"
          :progress="formalProgress"
          :percent="formalPercent"
          :version="formalVersion"
          :starting="formalStarting"
          :action-error="formalActionError"
          :auto-enabled="autoFormalEnabled"
          :estimated-tokens="estimatedTokens"
          :cost-note="costNote"
          :tone-count="toneCount"
          @start="startFormal()"
          @toggle-auto="onToggleAutoFormal"
        />
        <template v-if="layerView !== 'formal' || formalState === 'done'">
          <!-- 章节导航条（放在 transcript-area 内部，宽度跟随说话人面板展开/折叠） / Chapter overview bar (inside transcript-area, width adapts to speaker panel) -->
          <div class="chapter-overview" v-if="chapterOverviewVisible" id="chapterOverview">
            <span class="chapter-overview-label">{{ t('generating.chapter.overview_label') }}</span>
            <div class="chapter-nav-dots" id="chapterNavDots">
              <div v-for="(ch, i) in chapters" :key="i" class="chapter-nav-dot" :class="{ 'is-active': activeChapterIdx === i, 'is-done': i < activeChapterIdx }" :data-tip="ch.title" @click="emit('scroll-to-chapter', i)">
              </div>
            </div>
            <div class="chapter-current-info">
              <span>{{ t('generating.chapter.index_prefix') }}</span>
              <span class="ch-name">{{ activeChapterIdx + 1 }}</span>
              <span>{{ t('generating.chapter.index_suffix', { count: chapters.length }) }}</span>
            </div>
            <button class="chapter-transcript-toggle" :class="{ 'is-active': allChaptersVisible }" :title="t('generating.chapter.toggle_all_transcripts')" @click="emit('toggle-all-transcript')">
              <svg class="toggle-icon-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              <svg class="toggle-icon-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            </button>
          </div>
          <div class="spk-transcript-scroll" ref="transcriptAreaEl">
            <!-- 章节生成中提示（有转写内容但章节未生成）：统一进度面板 backfill 态 / Chapter generation hint — unified progress panel (backfill variant) -->
            <div class="chapter-loading is-panel" v-if="taskStatus === 'completed' && !chapters.length && flatTranscript.length > 0">
              <ProgressDialog :task="task" backfill />
            </div>
            <!-- 手动记录空态（无音频源，用户补录决策/随记） / Manual notes empty state (no audio source) -->
            <div class="chapter-loading is-empty" v-else-if="taskStatus === 'completed' && !chapters.length && flatTranscript.length === 0 && task?.source === 'manual'">
              <span>{{ t('generating.chapter.manual_notes_hint') }}</span>
            </div>
            <!-- 空转写提示（completed 但无任何转写内容） / Empty transcript hint (completed but no transcript) -->
            <div class="chapter-loading is-empty" v-else-if="taskStatus === 'completed' && !chapters.length && flatTranscript.length === 0">
              <span>{{ t('generating.chapter.empty_transcript') }}</span>
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

            <!-- 统一进度面板（REQ-TRANSCRIBE-PROGRESS R1）：替代静态 spinner；录音态沿用轻量加载提示 / Unified progress panel replaces static spinner; recording keeps light hint -->
            <div class="gen-loading" v-if="!flatTranscript.length && taskStatus && ['processing', 'transcribing', 'summarizing', 'awaiting_mapping'].includes(taskStatus)">
              <ProgressDialog :task="task" />
            </div>
            <div class="gen-loading" v-else-if="!flatTranscript.length && taskStatus === 'recording'">
              <div class="gen-loading-hint"><div class="gen-loading-spinner"></div>{{ t('generating.transcript.loading') }}</div>
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
                  :data-sentence-id="flatTranscript[item.lineIdx].sentence_id"
                  @click="emit('seek', flatTranscript[item.lineIdx].begin_time)"
                >
                  <div class="ts-line-avatar" :style="{ background: getSpeakerColor(String(flatTranscript[item.lineIdx].speaker_id)) }">{{ avatarInitial(getBindingSpeakerName(flatTranscript[item.lineIdx].speaker_id), t('generating.speaker_unid_initial')) }}</div>
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
                          {{ getBindingSpeakerName(flatTranscript[item.lineIdx].speaker_id) || t('generating.speaker_default') }}
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
                      <!-- 书面版：语气存疑警示标 / Formal view: weakened-tone marker -->
                      <span
                        v-if="isFormalView(flatTranscript[item.lineIdx]) && isToneFlagged(flatTranscript[item.lineIdx])"
                        class="gen-formal-tone-tag"
                        :title="t('generating.layer.formal_tone_warn')"
                      >{{ t('generating.layer.formal_tone_tag') }}</span>
                      <!-- 书面版：对照原文入口 / Formal view: compare-with-verbatim entry -->
                      <button
                        v-if="isFormalView(flatTranscript[item.lineIdx])"
                        type="button"
                        class="rec-line-clean-tag gen-formal-compare-tag"
                        :aria-expanded="peeked.has(item.lineIdx)"
                        @click.stop="togglePeek(item.lineIdx)"
                      >{{ t('generating.layer.formal_tag_compare') }}</button>
                      <!-- 清理视图：已清理行的原文回览入口 / Clean view: peek-verbatim entry -->
                      <button
                        v-if="isCleanedView(flatTranscript[item.lineIdx])"
                        type="button"
                        class="rec-line-clean-tag"
                        :aria-expanded="peeked.has(item.lineIdx)"
                        :title="t('generating.layer.tag_cleaned_title')"
                        @click.stop="togglePeek(item.lineIdx)"
                      >{{ t('generating.layer.tag_cleaned') }}</button>
                    </div>
                    <div class="ts-line-body">
                      <span class="txt" :class="{ 'is-tone': isFormalView(flatTranscript[item.lineIdx]) && isToneFlagged(flatTranscript[item.lineIdx]) }">{{ displayText(flatTranscript[item.lineIdx]) }}</span>
                    </div>
                    <!-- 书面版对照块：书面句 + 只读原文 + 语气警示 / Formal compare block -->
                    <div v-if="isFormalView(flatTranscript[item.lineIdx]) && peeked.has(item.lineIdx)" class="rec-peek gen-peek gen-formal-peek">
                      <div class="rec-peek-label">{{ t('generating.layer.formal_compare_label') }}</div>
                      <div v-if="isToneFlagged(flatTranscript[item.lineIdx])" class="gen-formal-peek-warn">
                        {{ t('generating.layer.formal_tone_warn') }}
                      </div>
                      <div class="gen-formal-peek-row">
                        <span class="gen-formal-peek-k">{{ t('generating.layer.formal_compare_formal') }}</span>
                        <span class="gen-formal-peek-v">{{ formalItem(flatTranscript[item.lineIdx])?.text }}</span>
                      </div>
                      <div class="gen-formal-peek-row">
                        <span class="gen-formal-peek-k">{{ t('generating.layer.formal_compare_raw') }}</span>
                        <span class="gen-formal-peek-v">{{ flatTranscript[item.lineIdx].text }}</span>
                      </div>
                    </div>
                    <!-- 原文回览块（只读原文 + 清理明细）/ Verbatim peek block -->
                    <div v-if="isCleanedView(flatTranscript[item.lineIdx]) && peeked.has(item.lineIdx)" class="rec-peek gen-peek">
                      <div class="rec-peek-label">{{ t('generating.layer.peek_label') }}</div>
                      <div class="rec-peek-text">{{ flatTranscript[item.lineIdx].text }}</div>
                      <div v-if="cleanupRuleText(flatTranscript[item.lineIdx].clean_ops)" class="rec-peek-rule">{{ cleanupRuleText(flatTranscript[item.lineIdx].clean_ops) }}</div>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>

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

      <TranscriptSpeakerPanel
        ref="speakerPanelRef"
        :visible="speakerPanelVisible"
        :search-expanded="searchExpanded"
        v-model:search="speakerPanelSearchVal"
        :speakers="panelSpeakerList"
        :total-duration="panelTotalDuration"
        :total-turns="panelTotalTurns"
        :filter-set="speakerFilterSet"
        :locate-speaker-id="locateSpeakerId"
        :playing-speaker-id="playingSpeakerId"
        @toggle-search="emit('toggle-search')"
        @toggle-panel="emit('toggle-panel')"
        @toggle-speaker="(id) => emit('toggle-speaker', id)"
        @toggle-locate="(id) => emit('toggle-locate', id)"
        @search-blur="emit('search-blur')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { getSpeakerColor } from '@/utils/speakerColors'
import { normalizeSpeakerName, avatarInitial } from '@/utils/speakerDisplay'
import { formatTimeMs, getChapterIdxAtTime } from '@/utils/transcriptView'
import ProgressDialog from './ProgressDialog.vue'
import FormalVersionCard from './FormalVersionCard.vue'
import TranscriptSpeakerPanel from './TranscriptSpeakerPanel.vue'
import { useFormalVersion } from './useFormalVersion'
import type { FlatTranscriptLine, Chapter, Task } from '@/api/types'
import type { Speaker } from '@/api/speakers'
import { cleanupRuleText as formatCleanupRule } from '@/utils/transcriptLayers'
import type { LayerView } from '@/utils/transcriptLayers'

const { t } = useI18n()
const userStore = useUserStore()

// ── 转写三层视图（PLAN-TRANSCRIPT-LAYERING WP-1） ──
// 会后：清理版按 get_task 响应信封 transcript_layers.cleanup 决定可用性；书面版 WP-2 才生成
// layerView 真源在 GeneratingView（tab 栏右侧下拉选择器），此处 prop 读 + emit 写
const peeked = ref<Set<number>>(new Set())

function isCleanedView(line: FlatTranscriptLine): boolean {
  return layerView.value === 'clean' && cleanupAvailable.value && typeof line.clean_text === 'string'
}
function displayText(line: FlatTranscriptLine): string {
  if (isFormalView(line)) return formalItem(line)?.text ?? (typeof line.clean_text === 'string' ? line.clean_text : line.text)
  if (isCleanedView(line)) return line.clean_text as string
  return line.text
}
function togglePeek(idx: number) {
  const next = new Set(peeked.value)
  if (next.has(idx)) next.delete(idx)
  else next.add(idx)
  peeked.value = next
}
function cleanupRuleText(ops?: FlatTranscriptLine['clean_ops']): string {
  return formatCleanupRule(t, ops, 'generating')
}

type TranscriptItem = { type: 'chapter'; chapterIdx: number } | { type: 'line'; lineIdx: number }

const props = defineProps<{
  visible: boolean
  /** 三层视图真源在父组件（tab 栏下拉选择器）/ Layer view owned by parent (tab-bar dropdown) */
  layerView: LayerView
  transcriptItems: TranscriptItem[]
  chapters: Chapter[]
  expandedChapters: Set<number>
  visibleChapterIndices: Set<number>
  activeChapterIdx: number
  flatTranscript: FlatTranscriptLine[]
  taskStatus: string | undefined
  /** 完整任务对象：统一进度面板的唯一数据源（progress/failed_stage/…） / Full task for the unified progress panel */
  task: Task | null | undefined
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
  chapterOverviewVisible: boolean
  allChaptersVisible: boolean
}>()

const layerView = computed(() => props.layerView)

// ── WP-2 书面版：状态机在 useFormalVersion，状态卡在 FormalVersionCard ──
const {
  formalVersion, formalState, formalProgress, formalPercent, toneCount,
  estimatedTokens, costNote, formalItem, isFormalView, isToneFlagged,
  formalStarting, formalActionError, autoFormalEnabled,
  startFormal, formalizeSelection, onToggleAutoFormal,
} = useFormalVersion({
  taskStatus: () => props.taskStatus,
  taskId: () => props.task?.task_id ?? null,
  lines: () => props.flatTranscript,
  layerView: () => props.layerView,
  visible: () => props.visible,
  onEnterFormal: () => emit('update:layerView', 'formal'),
})

const emit = defineEmits<{
  (e: 'update:layerView', v: LayerView): void
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
  (e: 'toggle-all-transcript'): void
  (e: 'toggle-audio'): void
  (e: 'seek-audio', event: MouseEvent): void
  (e: 'skip-audio', seconds: number): void
  (e: 'cycle-speed'): void
}>()

/** 清理版是否可用：get_task 信封声明本次响应已富化 clean_text / Whether the response carries enriched clean_text */
const cleanupAvailable = computed(() => props.task?.transcript_layers?.cleanup === true)
// 无清理富化（旧任务/开关关）时收敛到原文视图 / Fall back to verbatim when cleanup enrichment is absent
// （放在 emit 声明之后：immediate 回调会同步触发 emit）
watch(cleanupAvailable, (ok) => {
  if (!ok && layerView.value === 'clean') emit('update:layerView', 'raw')
}, { immediate: true })

// 模板 refs / Template refs
const transcriptAreaEl = ref<HTMLElement | null>(null)
const transcriptListEl = ref<HTMLElement | null>(null)
const speakerPanelRef = ref<InstanceType<typeof TranscriptSpeakerPanel> | null>(null)
/** 搜索框在子组件内，透传给父页面用于聚焦 */
const searchInputEl = computed(() => speakerPanelRef.value?.searchInputEl ?? null)

// v-model for speaker panel search
const speakerPanelSearchVal = computed({
  get: () => props.speakerPanelSearch,
  set: (val) => emit('update:speakerPanelSearch', val),
})

// ─── 工具函数 / Utility functions ───

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
  // REQ-SPK-RN：存量占位档案名（speakers.json 污染）同样收敛为空，行首走未识别态
  return normalizeSpeakerName(spk?.name)
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
  formalizeSelection,
})
</script>
