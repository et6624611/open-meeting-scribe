<template>
  <!-- 原文面板 / Transcript panel -->
  <div class="gen-panel spk-layout-active" :class="{ hidden: !visible }">
    <div class="spk-transcript-layout">
      <div class="spk-transcript-area">
        <!-- 三层视图（书面版/清理版/原文）选择器在 tab 栏右侧下拉（GeneratingView），本面板只消费 layerView -->
        <!-- 书面版状态卡（WP-2）/ Formal-version state card -->
        <div v-if="layerView === 'formal'" class="gen-formal-panel">
          <!-- 生成中 / Running -->
          <div v-if="formalState === 'running'" class="rec-formal-lock gen-formal-card is-running">
            <div class="gen-formal-spinner"></div>
            <div class="rec-formal-lock-title">{{ t('generating.layer.formal_running_title') }}</div>
            <div class="rec-formal-lock-desc">{{ t('generating.layer.formal_progress', { done: formalProgress.done, total: formalProgress.total }) }}</div>
            <div class="gen-formal-bar"><div class="gen-formal-bar-fill" :style="{ width: formalPercent + '%' }"></div></div>
          </div>
          <!-- 失败 / Error -->
          <div v-else-if="formalState === 'error'" class="rec-formal-lock gen-formal-card is-error">
            <div class="rec-formal-lock-title">{{ t('generating.layer.formal_error_title') }}</div>
            <div class="rec-formal-lock-desc">{{ formalVersion?.error || 'error' }}</div>
            <button type="button" class="gen-formal-btn" @click="() => startFormal()">{{ t('generating.layer.formal_retry') }}</button>
          </div>
          <!-- 失效 / Stale -->
          <div v-else-if="formalState === 'stale'" class="rec-formal-lock gen-formal-card is-stale">
            <div class="rec-formal-lock-title">{{ t('generating.layer.formal_stale_title') }}</div>
            <div class="rec-formal-lock-desc">{{ t('generating.layer.formal_stale_desc') }}</div>
            <button type="button" class="gen-formal-btn" @click="() => startFormal()">{{ t('generating.layer.formal_regenerate') }}</button>
          </div>
          <!-- 未生成 / Absent -->
          <template v-else-if="formalState === 'absent'">
            <div class="rec-formal-lock gen-formal-idle">
              <div class="rec-formal-lock-title">{{ t('generating.layer.formal_idle_title') }}</div>
              <div class="rec-formal-lock-desc">{{ t('generating.layer.formal_idle_desc') }}</div>
              <div class="gen-formal-estimate">
                {{ t('generating.layer.formal_estimate', { tokens: estimatedTokens }) }}
                <span class="gen-formal-cost-note">{{ costNote }}</span>
              </div>
              <div v-if="formalActionError" class="gen-formal-action-err" role="alert">{{ formalActionError }}</div>
              <button type="button" class="gen-formal-btn is-primary" :disabled="formalStarting" @click="() => startFormal()">
                {{ formalStarting ? t('generating.layer.formal_starting') : t('generating.layer.formal_generate') }}
              </button>
            </div>
            <label class="gen-formal-auto">
              <input type="checkbox" :checked="autoFormalEnabled" @change="onToggleAutoFormal" />
              <span>{{ t('generating.layer.formal_auto') }}</span>
            </label>
          </template>
          <!-- 完成留痕条 / Done meta bar -->
          <div v-else-if="formalState === 'done'" class="gen-formal-meta">
            <span class="gen-formal-meta-item">{{ formalVersion?.model || 'AI' }}</span>
            <span class="gen-formal-meta-sep">·</span>
            <span class="gen-formal-meta-item">{{ t('generating.layer.formal_meta_tokens', { tokens: formalVersion?.usage.total_tokens ?? 0 }) }}</span>
            <span class="gen-formal-meta-sep">·</span>
            <span class="gen-formal-meta-item">{{ formatFormalTime(formalVersion?.finished_at) }}</span>
            <template v-if="toneCount > 0">
              <span class="gen-formal-meta-sep">·</span>
              <span class="gen-formal-meta-tone">{{ t('generating.layer.formal_tone_count', { n: toneCount }) }}</span>
            </template>
            <button type="button" class="gen-formal-regen" :disabled="formalStarting" @click="() => startFormal()">{{ t('generating.layer.formal_regenerate') }}</button>
            <label class="gen-formal-auto is-inline">
              <input type="checkbox" :checked="autoFormalEnabled" @change="onToggleAutoFormal" />
              <span>{{ t('generating.layer.formal_auto_short') }}</span>
            </label>
          </div>
          <div v-if="formalActionError && formalState !== 'absent'" class="gen-formal-action-err is-banner" role="alert">{{ formalActionError }}</div>
        </div>
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
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { getSpeakerColor } from '@/utils/speakerColors'
import { normalizeSpeakerName } from '@/utils/speakerDisplay'
import ProgressDialog from './ProgressDialog.vue'
import type { FlatTranscriptLine, Chapter, Task, FormalVersion } from '@/api/types'
import type { Speaker } from '@/api/speakers'
import { cleanupRuleText as formatCleanupRule } from '@/utils/transcriptLayers'
import { getFormal, formalize } from '@/api/transcriptLayers'
import { fetchSettings, saveSettings } from '@/api/settings'

const { t } = useI18n()
const userStore = useUserStore()

// ── 转写三层视图（PLAN-TRANSCRIPT-LAYERING WP-1） ──
// 会后：清理版按 get_task 响应信封 transcript_layers.cleanup 决定可用性；书面版 WP-2 才生成
// layerView 真源在 GeneratingView（tab 栏右侧下拉选择器），此处 prop 读 + emit 写
import type { LayerView } from '@/utils/transcriptLayers'
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

// ── WP-2 书面版：sidecar 状态机（结果独立于 dialogue，绝不回写） ──
type FormalState = 'absent' | 'running' | 'done' | 'stale' | 'error'
const formalVersion = ref<FormalVersion | null>(null)
const formalStarting = ref(false)
const formalActionError = ref('')
const autoFormalEnabled = ref(false)
let formalTimer: number | null = null

/** 只有会后（completed）才可读写书面版 / Formal version is post-meeting only */
const formalTaskId = computed<string | null>(() =>
  props.taskStatus === 'completed' ? props.task?.task_id ?? null : null)
const formalState = computed<FormalState>(() => {
  const v = formalVersion.value
  if (!v) return 'absent'
  if (v.status === 'running') return 'running'
  if (v.status === 'stale') return 'stale'
  if (v.status === 'error') return 'error'
  return 'done'
})
const formalMap = computed(() => {
  const m = new Map<number, FormalItem>()
  for (const it of formalVersion.value?.items ?? []) m.set(it.sentence_id, it)
  return m
})
const toneCount = computed(() =>
  (formalVersion.value?.items ?? []).filter(i => i.tone_flag === 'weakened').length)
const formalProgress = computed(() => {
  const total = props.flatTranscript.length || formalVersion.value?.progress?.total || 0
  return { done: formalVersion.value?.progress?.done ?? 0, total }
})
const formalPercent = computed(() => {
  const { done, total } = formalProgress.value
  return total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
})
/** 预估值：原文字符数 / 1.6，仅作提示 / Token estimate for the cost hint only */
const estimatedTokens = computed(() => {
  const chars = props.flatTranscript.reduce((n, l) => n + l.text.length, 0)
  return Math.max(1, Math.round(chars / 1.6))
})
/** 本机算力不耗云额度（方案 §7 遗留 4）/ Local-endpoint runs do not consume cloud quota */
const costNote = computed(() =>
  formalVersion.value?.source === 'local_endpoint'
    ? t('generating.layer.formal_cost_local')
    : t('generating.layer.formal_cost_cloud'))

function formalItem(line: FlatTranscriptLine): FormalItem | undefined {
  return formalMap.value.get(line.sentence_id)
}
function isFormalView(line: FlatTranscriptLine): boolean {
  return layerView.value === 'formal' && formalState.value === 'done' && formalMap.value.has(line.sentence_id)
}
function isToneFlagged(line: FlatTranscriptLine): boolean {
  return formalItem(line)?.tone_flag === 'weakened'
}
function formatFormalTime(s: string | undefined): string {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function fetchFormal(id: string) {
  try {
    formalVersion.value = await getFormal(id)
  } catch {
    // 读取失败保持现状，不打断当前视图 / Keep current state on transient fetch errors
  }
}
async function startFormal(sentenceIds?: number[]) {
  const id = formalTaskId.value
  if (!id || formalStarting.value) return
  formalStarting.value = true
  formalActionError.value = ''
  try {
    await formalize(id, sentenceIds)
    await fetchFormal(id)
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: { reason?: string } } } })?.response?.data?.detail
    const reason = detail?.reason
    formalActionError.value = reason
      ? t('generating.layer.formal_blocked', { reason: t(`generating.layer.formal_block_reason.${reason}`, reason) })
      : t('generating.layer.formal_blocked_generic')
    await fetchFormal(id)
  } finally {
    formalStarting.value = false
  }
}
/** WP-3 选区书面化入口（SelectionToolbar → GeneratingView 转发）：切书面视图并复用同一状态机
 *  Selection-scope formalize entry: switch to formal view, reuse the same state machine */
function formalizeSelection(sentenceIds: number[]) {
  if (!formalTaskId.value || !sentenceIds.length) return
  emit('update:layerView', 'formal')
  void startFormal(sentenceIds)
}
async function onToggleAutoFormal(ev: Event) {
  const next = (ev.target as HTMLInputElement).checked
  const prev = autoFormalEnabled.value
  autoFormalEnabled.value = next
  try {
    await saveSettings({ transcript: { formal: { auto_generate: next } } })
  } catch {
    autoFormalEnabled.value = prev
  }
}

watch(formalTaskId, (id) => {
  if (id) void fetchFormal(id)
  else formalVersion.value = null
}, { immediate: true })
// 面板重新可见时拉一次（后台自动生成可能已完成）/ Refresh when panel becomes visible
watch(() => props.visible, (v) => {
  if (v && formalTaskId.value) void fetchFormal(formalTaskId.value)
})
// running 时 2s 轮询，落定即停 / Poll every 2s while running
watch(formalState, (s) => {
  if (formalTimer) { window.clearInterval(formalTimer); formalTimer = null }
  if (s === 'running') {
    formalTimer = window.setInterval(() => {
      if (formalTaskId.value) void fetchFormal(formalTaskId.value)
    }, 2000)
  }
})
onMounted(async () => {
  try {
    const s = await fetchSettings()
    autoFormalEnabled.value = s.transcript?.formal?.auto_generate === true
  } catch { /* 设置不可达时保持默认关 */ }
})
onBeforeUnmount(() => {
  if (formalTimer) window.clearInterval(formalTimer)
})

// 类型别名（与 @/api/types 的 FormalItem 同形）
type FormalItem = import('@/api/types').FormalItem

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
  // REQ-SPK-RN：存量占位档案名（speakers.json 污染）同样收敛为空，行首走未识别态
  return normalizeSpeakerName(spk?.name)
}

/** 头像首字：真名取首字符；未识别取中性符（D5：禁用编号数字） */
function avatarInitial(name: string, _speakerId: number): string {
  if (name && name.trim()) return name.trim()[0]
  return t('generating.speaker_unid_initial')
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
