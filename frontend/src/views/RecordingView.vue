<template>
  <div class="rec-main" :class="{ 'is-ending': ending }">
    <!-- 顶栏 -->
    <div class="rec-header">
      <div class="rec-header-left">
        <span class="rec-title" id="recTitle">{{ t('recording.title') }}</span>
        <span class="rec-status" id="recStatus">{{ recPaused ? t('recording.status.paused') : t('recording.status.identifying') }}</span>
        <span class="rec-speaker-count" :class="{ 'has-update': speakerCountUpdated }" v-if="displaySpeakerCount > 0" :title="t('recording.speaker.count_title')">
          <span class="sc-dot"></span>
          <span>{{ t('recording.speaker.count', { count: displaySpeakerCount }) }}</span>
        </span>
        <!-- 项目关联 chip -->
        <span class="rec-project-chip-wrap" v-if="projects.length > 0">
          <span class="gen-meta-project-chip" :class="{ 'is-unbound': !task?.project_id, 'is-bound': !!task?.project_id }" role="button" tabindex="0" @click.stop="showProjectDropdown = !showProjectDropdown">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
            <span>{{ currentProjectName }}</span>
          </span>
          <div class="gen-meta-proj-dropdown" :class="{ hidden: !showProjectDropdown }">
            <button v-for="p in projects" :key="p.id" class="gen-meta-proj-item" :class="{ 'is-selected': task?.project_id === p.id }" @click="onSelectProject(p.id)">
              {{ p.name }}
            </button>
            <div class="gen-meta-proj-divider"></div>
            <button class="gen-meta-proj-item" :class="{ 'is-selected': !task?.project_id }" @click="onSelectProject('')">
              {{ t('generating.meta.no_project') }}
            </button>
          </div>
        </span>
      </div>
      <div class="rec-header-right">
        <button class="btn-translate" :title="t('common.action.translate')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
          {{ t('common.action.translate') }}
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <button v-if="isFocusMode" class="btn-exit-focus" @click="onFocusMode" :title="t('recording.focus.exit_title')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
          {{ t('recording.focus.exit') }}
        </button>
        <button v-else class="rec-summary-btn" @click="onFocusMode" :title="t('recording.focus.enter_title')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
        </button>
      </div>
    </div>

    <!-- 内容区：原文 + 实时总结 -->
    <div class="rec-content-area" :class="{ 'tab-summary': recTab === 'summary' }" id="recContentArea">
      <!-- Tab 切换栏 -->
      <div class="rec-tab-bar" id="recTabBar">
        <button class="rec-tab" :class="{ active: recTab === 'transcript' }" @click="recTab = 'transcript'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          {{ t('recording.tab.transcript') }}
        </button>
        <button class="rec-tab" :class="{ active: recTab === 'summary' }" @click="recTab = 'summary'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="21" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="3" y2="18"/></svg>
          {{ t('recording.tab.summary') }}
        </button>
      </div>

      <!-- 音量过低警告 -->
      <div class="rec-volume-warning" v-if="ws.volumeWarning.value">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>
        <span>{{ t('recording.volume_warning') }}</span>
        <button class="rec-volume-dismiss" @click="ws.volumeWarning.value = ''">&times;</button>
      </div>

      <!-- 存在性警告（温和横幅） -->
      <div class="rec-presence-warning" v-if="ws.presenceWarning.value && ws.presenceWarning.value.level === 'gentle'">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span>{{ t('recording.presence_warning.gentle_text', { minutes: ws.presenceWarning.value.silent_minutes }) }}</span>
        <div class="rec-presence-actions">
          <button class="rec-presence-btn rec-presence-btn-continue" @click="onPresenceContinue">{{ t('recording.presence_warning.continue_recording') }}</button>
          <button class="rec-presence-btn rec-presence-btn-stop" @click="onPresenceStop">{{ t('recording.presence_warning.stop_recording') }}</button>
        </div>
      </div>

      <!-- 存在性警告（紧急模态框） -->
      <div class="rec-presence-overlay" v-if="ws.presenceWarning.value && ws.presenceWarning.value.level === 'urgent'">
        <div class="rec-presence-dialog">
          <div class="rec-presence-dialog-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          </div>
          <div class="rec-presence-dialog-title">{{ t('recording.presence_warning.urgent_title') }}</div>
          <div class="rec-presence-dialog-desc">{{ t('recording.presence_warning.urgent_text', { minutes: ws.presenceWarning.value.silent_minutes, countdown: ws.presenceWarning.value.countdown_seconds }) }}</div>
          <div class="rec-presence-dialog-actions">
            <button class="rec-presence-btn rec-presence-btn-continue" @click="onPresenceContinue">{{ t('recording.presence_warning.continue_recording') }}</button>
            <button class="rec-presence-btn rec-presence-btn-stop" @click="onPresenceStop">{{ t('recording.presence_warning.stop_and_save') }}</button>
          </div>
        </div>
      </div>

      <!-- 总结进度条（始终可见，在 Tab 栏下方；暂停时隐藏） -->
      <div class="rec-summary-progress" v-if="recTab === 'summary' && summaryCountdown > 0 && !summaryPaused">
        <div class="rec-summary-progress-bar" :class="{ 'is-warning': summaryCountdown <= 10 }" :style="{ width: summaryProgressPercent + '%' }"></div>
      </div>

      <!-- 结束过渡遮罩 -->
      <div class="rec-ending-overlay" v-if="ending">
        <template v-if="stopFailed">
          <div class="rec-ending-icon" style="margin-bottom:4px">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--rec)" stroke-width="2" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </div>
          <div class="rec-ending-text" style="color:var(--fg)">{{ t('recording.stop_failed.text') }}</div>
          <div class="rec-ending-sub">{{ stopErrorMsg }}</div>
          <button class="btn-force-quit" @click="onForceQuit" style="margin-top:12px;padding:8px 20px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--fg);font-size:13px;cursor:pointer">{{ t('recording.stop_failed.force_quit') }}</button>
        </template>
        <template v-else>
          <div class="rec-ending-spinner"></div>
          <div class="rec-ending-text">{{ t('recording.ending.text') }}</div>
          <div class="rec-ending-sub">{{ t('recording.ending.sub') }}</div>
        </template>
      </div>

      <!-- 左栏：原文 -->
      <div class="rec-transcript" id="recTranscript" v-show="recTab === 'transcript'">
        <div class="rec-transcript-header">
          <div class="rec-transcript-title">{{ t('recording.tab.transcript') }}</div>
          <div class="rec-transcript-actions">
            <button class="transcript-toggle" :class="{ 'is-active': showTranscript }" @click="showTranscript = !showTranscript" :title="showTranscript ? t('recording.transcript.hide_title') : t('recording.transcript.show_title')">
              <svg class="toggle-icon-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
              <svg class="toggle-icon-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
              </svg>
              <span class="toggle-label">{{ showTranscript ? t('recording.transcript.hide') : t('recording.transcript.show') }}</span>
            </button>
          </div>
        </div>
        <!-- 章节条 -->
        <div class="rec-chapter-strip" v-if="wsChapters.length > 0">
          <div class="rec-chapter-dots">
            <span v-for="(_ch, i) in wsChapters" :key="i" class="rec-ch-dot" :class="{ 'is-current': i === wsChapters.length - 1 }"></span>
          </div>
          <div class="rec-chapter-current">
            <span class="rec-chapter-num">{{ wsChapters.length }}</span>
            <span class="rec-chapter-title">{{ wsChapters[wsChapters.length - 1]?.title || t('recording.chapter.discussing') }}</span>
          </div>
        </div>
        <div class="rec-transcript-body" id="recTranscriptBody" ref="transcriptBody">
          <!-- 原文隐藏指示条 -->
          <div v-if="!showTranscript" class="rec-hidden-indicator">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
            </svg>
            <span>{{ t('recording.transcript.hidden_indicator', { count: wsLines.length }) }}</span>
            <button class="rec-hidden-show-btn" @click="showTranscript = true">{{ t('recording.transcript.show') }}</button>
          </div>
          <!-- 标记模式压缩指示器 -->
          <div v-if="markerMode && compressedCount > 0" class="rec-marker-compressed">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
            {{ t('recording.marker.compressed', { count: compressedCount }) }}
            <button class="rec-marker-expand-btn" @click="markerMode = false">{{ t('recording.marker.expand_all') }}</button>
          </div>
          <template v-for="(line, i) in visibleLines" :key="i">
            <!-- 章节内联分隔卡片（与 GeneratingView 对齐） -->
            <div v-if="getChapterStartInfo(i)" class="chapter-divider" :class="{ 'is-current': getChapterStartInfo(i)!.chapterIdx === wsChapters.length - 1, 'is-expanded': recExpandedChapters.has(getChapterStartInfo(i)!.chapterIdx) }" @click="toggleChapterExpand(getChapterStartInfo(i)!.chapterIdx)">
              <div class="chapter-header">
                <div class="chapter-number">{{ wsChapters[getChapterStartInfo(i)!.chapterIdx].id || getChapterStartInfo(i)!.chapterIdx + 1 }}</div>
                <div class="chapter-info">
                  <div class="chapter-title">{{ getChapterStartInfo(i)!.title }}</div>
                  <div class="chapter-meta">
                    <span>{{ formatRecTimeMs(wsChapters[getChapterStartInfo(i)!.chapterIdx].start_ms) }}</span>
                    <template v-if="wsChapters[getChapterStartInfo(i)!.chapterIdx].end_ms">
                      <span class="sep">–</span>
                      <span>{{ formatRecTimeMs(wsChapters[getChapterStartInfo(i)!.chapterIdx].end_ms) }}</span>
                    </template>
                    <template v-if="(wsChapters[getChapterStartInfo(i)!.chapterIdx].key_points || []).length">
                      <span class="sep">·</span>
                      <span>{{ t('recording.chapter.key_points_count', { count: (wsChapters[getChapterStartInfo(i)!.chapterIdx].key_points || []).length }) }}</span>
                    </template>
                  </div>
                  <div v-if="wsChapters[getChapterStartInfo(i)!.chapterIdx].summary" class="chapter-summary-text">{{ wsChapters[getChapterStartInfo(i)!.chapterIdx].summary }}</div>
                </div>
                <div class="chapter-chevron">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
                </div>
              </div>
              <div class="chapter-body">
                <div class="chapter-body-inner">
                  <div class="chapter-key-points" v-if="wsChapters[getChapterStartInfo(i)!.chapterIdx].key_points?.length">
                    <div class="chapter-key-points-title">{{ t('recording.chapter.key_points') }}</div>
                    <div v-for="(p, pi) in wsChapters[getChapterStartInfo(i)!.chapterIdx].key_points" :key="pi" class="chapter-key-point">{{ p }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div class="rec-line" v-show="showTranscript" :class="{ 'rec-line-hidden': markerMode && !hasNoteAt(i), 'is-me': isMeSpeaker(line.speaker_id), 'is-located': locateSpeakerId === line.speaker_id, 'is-dimmed': locateSpeakerId !== null && locateSpeakerId !== line.speaker_id }">
              <div class="rec-line-head">
                <span class="rec-line-speaker" :style="speakerStyle(line.speaker_id)" @click.stop="openBindPopover(line.speaker_id)">
                  {{ getSpeakerDisplayName(line) }}
                </span>
                <button v-if="!locateSpeakerId || locateSpeakerId === line.speaker_id" class="rec-line-locate-btn" @click.stop="toggleLocateSpeaker(line.speaker_id)" :title="t('recording.speaker.locate')">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                </button>
              </div>
              <div class="rec-line-body">
                <span class="rec-line-text">{{ line.text }}</span>
              </div>
              <!-- 内联随记标记 -->
              <div v-if="notesByLine[i]" class="note-inline-card">
                <span class="note-inline-text">{{ notesByLine[i] }}</span>
                <button class="note-inline-delete" @click.stop="onDeleteNote(i)" :title="t('recording.notes.delete')">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>
          </template>
          <div v-if="wsPartial" class="rec-line rec-line-partial" v-show="showTranscript">
            <div class="rec-line-head">
              <span class="rec-line-speaker">
                …
              </span>
            </div>
            <div class="rec-line-body">
              <span class="rec-line-text">{{ wsPartial }}</span>
            </div>
          </div>
          <div v-if="visibleLines.length === 0 && !wsPartial" class="rec-empty">
            <p>{{ t('recording.transcript.empty') }}</p>
            <p class="rec-empty-hint">{{ t('recording.transcript.empty_hint') }}</p>
          </div>
        </div>
        <button class="rec-jump-latest" :class="{ 'is-visible': showJumpBtn }" @click="jumpToLatest" :title="t('recording.jump_latest')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="4" x2="12" y2="20"/><polyline points="18 14 12 20 6 14"/></svg>
          {{ t('recording.jump_latest') }}
        </button>
      </div>

      <!-- 右栏：实时总结（宽屏并排显示，窄屏由 tab-summary class 控制） -->
      <div class="rec-summary-panel" id="recSummaryPanel" :class="{ 'is-hidden-narrow': recTab !== 'summary' }">
        <div class="rec-summary-header">
          <div class="rec-summary-title">
            <!-- 倒计时环形进度（暂停时隐藏） -->
            <div class="rec-summary-countdown-ring" v-if="summaryCountdown > 0 && !summaryPaused">
              <svg width="28" height="28" viewBox="0 0 28 28">
                <circle class="ring-bg" cx="14" cy="14" r="11"/>
                <circle
                  class="ring-fg" :class="{ 'is-warning': summaryCountdown <= 10 }" cx="14" cy="14" r="11"
                  :stroke-dasharray="69.115" :stroke-dashoffset="69.115 * (1 - summaryProgressPercent / 100)"
                />
              </svg>
              <span class="ring-text" :class="{ 'is-warning': summaryCountdown <= 10 }">{{ summaryCountdown }}</span>
            </div>
            {{ t('recording.summary.title') }}
            <span class="rec-summary-status">{{ summaryStatusText }}</span>
          </div>
          <div class="rec-summary-actions">
            <button class="rec-summary-btn" @click="onToggleSummaryPause" :title="summaryPaused ? t('recording.summary.resume_title') : t('recording.summary.pause_title')">
              <svg v-if="!summaryPaused" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
            </button>
            <div class="more-menu-wrap">
              <button ref="summaryMoreBtn" class="rec-summary-btn" @click="toggleSummaryMore" :title="t('common.action.more')" aria-haspopup="menu" :aria-label="t('common.action.more')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
              </button>
              <div ref="summaryDropdown" class="more-menu-dropdown" :class="{ 'is-open': showSummaryMore }" role="menu">
                <button class="more-menu-item" @click="onStopSummary" role="menuitem">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
                  {{ t('recording.summary.stop') }}
                </button>
                <div style="height:1px;background:var(--border);margin:4px 0"></div>
                <div style="padding:4px 6px;font-size:11px;color:var(--muted);font-weight:500">{{ t('recording.summary.frequency') }}</div>
                <button v-for="f in freqOptions" :key="f" class="more-menu-item summary-interval-item" :class="{ 'is-selected': summaryInterval === f }" @click="onSetFrequency(f)" role="menuitem">
                  <span class="opt-check">
                    <svg v-if="summaryInterval === f" class="ic ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                  </span>
                  {{ f }}s <span class="opt-hint">{{ getFreqHint(f) }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="rec-summary-body" id="recSummaryBody">
          <div class="rec-summary-content" v-html="summaryHtml"></div>
        </div>
      </div>
    </div>

    <!-- 全宽随记输入栏（重新设计） -->
    <div class="rec-notes-bar" id="recNotesBar">
      <button class="marker-toggle-btn" :class="{ active: markerMode }" @click="markerMode = !markerMode" :title="t('recording.marker.title')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
          <line x1="4" y1="22" x2="4" y2="15"/>
        </svg>
        <span>{{ t('recording.marker.label') }}</span>
        <span class="marker-count" v-if="noteCount > 0">{{ noteCount }}</span>
      </button>
      <textarea class="rec-notes-input" id="recNotesInput" rows="1" :placeholder="t('recording.notes.placeholder')" v-model="noteText" @keydown.enter.exact.prevent="onSendNote"></textarea>
      <button class="rec-notes-bar-send" :disabled="!noteText.trim()" @click="onSendNote" :aria-label="t('recording.notes.send')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </div>

    <!-- 底部控制栏 -->
    <div class="rec-control-bar">
      <div class="waveform" id="waveform" :class="{ 'is-paused': recPaused }">
        <div class="wbar"></div><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div>
      </div>
      <span class="ctrl-timer" id="recTimer">{{ recorder.formatElapsed() }}</span>
      <button class="btn-pause" @click="onTogglePause" :title="recPaused ? t('recording.control.resume_title') : t('recording.control.pause_title')">
        <svg v-if="!recPaused" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
        <span class="btn-pause-text">{{ recPaused ? t('recording.control.resume') : t('recording.control.pause') }}</span>
      </button>
      <button class="btn-end-rec" @click="onStop">{{ t('recording.control.end') }}</button>
      <div class="more-menu-wrap">
        <button ref="recMoreBtn" class="more-menu-btn" @click="toggleRecMore" :title="t('common.action.more')" aria-haspopup="menu" :aria-label="t('common.action.more')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
        </button>
        <div ref="recDropdown" class="more-menu-dropdown" :class="{ 'is-open': showRecMore }" role="menu">
          <button class="more-menu-item danger" @click="closeRecMore(); showAbandon = true" role="menuitem">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            {{ t('recording.control.abandon') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 说话人绑定弹窗 -->
    <div class="rec-bind-popover" v-if="bindPopover.visible" :style="bindPopover.style" @click.stop>
      <div class="bind-title">{{ t('recording.speaker.bind_title') }}</div>
      <div class="bind-search">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input v-model="bindSearch" :placeholder="t('recording.speaker.search_placeholder')" @input="onBindSearch"/>
      </div>
      <div class="bind-list">
        <div
          v-for="spk in filteredSpeakers" :key="spk.id"
          class="bind-option" :class="{ 'is-selected': bindPopover.asrId !== null && currentBinding(spk.id) === String(bindPopover.asrId) }"
          @click="onBindSpeaker(spk)"
        >
          <span class="bind-name" :style="{ color: speakerColor(spk.id) }">{{ spk.name }}{{ spk.is_me ? t('recording.speaker.me_suffix') : '' }}</span>
        </div>
        <div v-if="filteredSpeakers.length === 0" class="bind-empty">{{ t('recording.speaker.no_match') }}</div>
      </div>
      <div class="bind-divider"></div>
      <div class="bind-footer">
        <div class="bind-new" @click="onCreateAndBind" v-if="bindSearch.trim()">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          {{ t('recording.speaker.create_and_bind', { name: bindSearch.trim() }) }}
        </div>
      </div>
    </div>

    <!-- 放弃录音确认弹窗 -->
    <div class="abandon-overlay" :class="{ 'is-open': showAbandon }" v-if="showAbandon">
      <div class="abandon-dialog">
        <div class="abandon-dialog-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </div>
        <div class="abandon-dialog-title">{{ t('recording.abandon_dialog.title') }}</div>
        <div class="abandon-dialog-desc">{{ t('recording.abandon_dialog.desc') }}</div>
        <div class="abandon-dialog-info">{{ t('recording.abandon_dialog.recorded_duration', { duration: recorder.formatElapsed() }) }}</div>
        <div class="abandon-dialog-actions">
          <button class="btn-cancel" @click="showAbandon = false">{{ t('common.action.cancel') }}</button>
          <button class="btn-confirm-abandon" @click="onAbandon">{{ t('recording.abandon_dialog.confirm') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useRecorder } from '@/composables/useRecorder'
import { useWebSocketTranscript, type TranscriptLine } from '@/composables/useWebSocket'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { useUserStore } from '@/stores/user'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { usePopMenu } from '@/composables/usePopMenu'
import { getSpeakerColor } from '@/utils/speakerColors'
import { fetchSpeakers, createSpeaker, type Speaker } from '@/api/speakers'
import { fetchProjects, type Project } from '@/api/projects'
import { updateTask } from '@/api/tasks'
import {
  pauseSummary, resumeSummary, stopSummary, setSummaryInterval, bindSpeaker
} from '@/api/record'

const NOTES_LS_KEY = 'oms_rec_timestamped_notes'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const recorder = useRecorder()
// 模板不会解包普通对象内嵌套的 ref，必须提升为顶层绑定才能响应式渲染
const recPaused = recorder.isPaused
const ws = useWebSocketTranscript()
const wsLines = ws.lines
const wsPartial = ws.partialText
const wsSummary = ws.summary
const wsChapters = ws.chapters
const taskStore = useTaskStore()
const userStore = useUserStore()
const layout = useLayoutStore()
const { registerNotesAppender, registerSummaryAppender } = useQuoteRef()

const taskId = computed(() => route.params.taskId as string)
const task = computed(() => taskStore.tasks.find(t => t.task_id === taskId.value) ?? null)

// 项目关联
const projects = ref<Project[]>([])
const showProjectDropdown = ref(false)
const currentProjectName = computed(() => {
  if (!task.value?.project_id) return t('generating.meta.link_project')
  const p = projects.value.find(p => p.id === task.value?.project_id)
  return p?.name || t('generating.meta.link_project')
})

async function onSelectProject(projectId: string) {
  showProjectDropdown.value = false
  try {
    await updateTask(taskId.value, { project_id: projectId || undefined })
    taskStore.patchTaskLocal(taskId.value, { project_id: projectId || null })
  } catch (e) {
    console.error('update project link failed:', e)
  }
}

const recTab = ref<'transcript' | 'summary'>('transcript')
const noteText = ref('')

// ─── 存在性检测（静默检测第三层）───
// 详见 docs/design/SILENCE_DETECTION.md
const PRESENCE_SCORE_MAX = 100
const PRESENCE_DECAY_PER_SEC = 1
const HEARTBEAT_INTERVAL_SEC = 30

const presenceScore = ref(PRESENCE_SCORE_MAX)
let presenceDecayTimer: ReturnType<typeof setInterval> | null = null
let heartbeatTimer: ReturnType<typeof setInterval> | null = null

/** 用户交互事件：重置存在性评分 */
function onUserInteraction() {
  presenceScore.value = PRESENCE_SCORE_MAX
}

/** 页面可见性变化 */
function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    // 页面切回可见，评分回升
    presenceScore.value = Math.min(PRESENCE_SCORE_MAX, presenceScore.value + 80)
  } else {
    // 页面切到后台，评分大幅衰减
    presenceScore.value = Math.floor(presenceScore.value * 0.3)
  }
}

/** 窗口失焦/获焦 */
function onWindowBlur() {
  presenceScore.value = Math.floor(presenceScore.value * 0.5)
}
function onWindowFocus() {
  presenceScore.value = Math.min(PRESENCE_SCORE_MAX, presenceScore.value + 60)
}

/** 启动存在性检测 */
function startPresenceDetection() {
  // 注册事件监听
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('blur', onWindowBlur)
  window.addEventListener('focus', onWindowFocus)
  // 用户交互事件（在录音页面范围内）
  document.addEventListener('click', onUserInteraction)
  document.addEventListener('keydown', onUserInteraction)
  document.addEventListener('scroll', onUserInteraction)

  // 评分衰减定时器（每秒 -1）
  presenceDecayTimer = setInterval(() => {
    if (presenceScore.value > 0) {
      presenceScore.value = Math.max(0, presenceScore.value - PRESENCE_DECAY_PER_SEC)
    }
  }, 1000)

  // 心跳定时器（每 30 秒发送）
  heartbeatTimer = setInterval(() => {
    ws.sendHeartbeat(presenceScore.value)
  }, HEARTBEAT_INTERVAL_SEC * 1000)

  // 立即发送一次心跳（连接建立时）
  ws.sendHeartbeat(presenceScore.value)
}

/** 停止存在性检测 */
function stopPresenceDetection() {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('blur', onWindowBlur)
  window.removeEventListener('focus', onWindowFocus)
  document.removeEventListener('click', onUserInteraction)
  document.removeEventListener('keydown', onUserInteraction)
  document.removeEventListener('scroll', onUserInteraction)

  if (presenceDecayTimer) {
    clearInterval(presenceDecayTimer)
    presenceDecayTimer = null
  }
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

// Restore saved tab from localStorage
onMounted(() => {
  const saved = localStorage.getItem('oms_rec_active_tab')
  if (saved && (saved === 'transcript' || saved === 'summary')) {
    recTab.value = saved
  }

  // 注册 AI 面板的插入回调
  registerNotesAppender((markdown: string) => {
    noteText.value = noteText.value ? noteText.value + '\n\n' + markdown : markdown
  })

  registerSummaryAppender((markdown: string) => {
    // 录音页的总结是只读的（来自 WS），追加到笔记输入框
    noteText.value = noteText.value ? noteText.value + '\n\n' + markdown : markdown
  })

  // 监听转写区滚动，控制"回到底部"按钮显隐
  const el = transcriptBody.value
  if (el) {
    el.addEventListener('scroll', onTranscriptScroll)
  }

  // 加载项目列表
  fetchProjects().then(list => { projects.value = list }).catch(() => {})

  // 注册说话人绑定更新回调：同步 realtimeSpeakerBindings
  ws.onSpeakerBound((speakerId: number, speakerUuid: string, _speakerName: string) => {
    realtimeSpeakerBindings.value[speakerId] = speakerUuid
  })

  // 启动存在性检测（静默检测第三层）
  startPresenceDetection()
})

onUnmounted(() => {
  const el = transcriptBody.value
  if (el) {
    el.removeEventListener('scroll', onTranscriptScroll)
  }
  // 停止存在性检测
  stopPresenceDetection()
})

function onTranscriptScroll() {
  const el = transcriptBody.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  showJumpBtn.value = !atBottom
}
const recMoreBtn = ref<HTMLElement | null>(null)

// ─── 章节展开状态 ───
const recExpandedChapters = reactive(new Set<number>())
const recAutoExpandedCount = ref(0)

/** 自动展开新出现的章节 */
watch(() => wsChapters.value.length, (newLen) => {
  // 自动展开超过初始数量的新章节
  for (let c = recAutoExpandedCount.value; c < newLen; c++) {
    recExpandedChapters.add(c)
  }
  recAutoExpandedCount.value = newLen
})
const recDropdown = ref<HTMLElement | null>(null)
const { visible: showRecMore, toggle: toggleRecMore, close: closeRecMore } = usePopMenu(recDropdown, recMoreBtn)
const summaryMoreBtn = ref<HTMLElement | null>(null)
const summaryDropdown = ref<HTMLElement | null>(null)
const { visible: showSummaryMore, toggle: toggleSummaryMore, close: closeSummaryMore } = usePopMenu(summaryDropdown, summaryMoreBtn)
const showAbandon = ref(false)
const ending = ref(false)
const stopFailed = ref(false)
const stopErrorMsg = ref('')
const showJumpBtn = ref(false)

const transcriptBody = ref<HTMLElement | null>(null)

// 转写原文显示/隐藏
const showTranscript = ref(true)

// 笔记标记模式
const markerMode = ref(false)

// 笔记持久化结构
interface PersistedNote { id: string; time: number; text: string }
const userNotes = ref<{ id: string; text: string; lineIndex: number; time: number }[]>([])

// 总结倒计时 — 优先使用 WS 推送
const summaryInterval = ref(60)
const summaryCountdown = ref(0)
// 总结暂停状态由后端 summary_status WebSocket 消息驱动（支持录音联动自动暂停/恢复）
const summaryPaused = computed(() => ws.summaryPaused.value)
const summaryStatusText = computed(() => {
  if (summaryPaused.value) return t('recording.summary.paused')
  if (!wsSummary.value) return t('recording.summary.waiting')
  return t('recording.summary.countdown', { count: summaryCountdown.value })
})
/** 总结区 HTML：有内容时渲染 Markdown，无内容时显示翻译后的占位提示 */
const summaryHtml = computed(() => {
  if (wsSummary.value) return renderMd(wsSummary.value)
  return `<p style="color:var(--subtle)">${t('recording.summary.waiting_content')}</p>`
})

const summaryProgressPercent = computed(() => {
  if (summaryInterval.value <= 0) return 0
  return Math.max(0, Math.min(100, ((summaryInterval.value - summaryCountdown.value) / summaryInterval.value) * 100))
})
const freqOptions = [30, 60, 120, 300]

let fallbackTimer: ReturnType<typeof setInterval> | null = null

// 说话人
const speakers = ref<Speaker[]>([])
const bindSearch = ref('')
const bindPopover = ref<{ visible: boolean; asrId: number | null; style: Record<string, string> }>({
  visible: false, asrId: null, style: {}
})
// 独立绑定映射表（不依赖 lines 中的 name）
const realtimeSpeakerBindings = ref<Record<number, string>>({})
const speakerCountUpdated = ref(false)
let speakerCountFlashTimer: ReturnType<typeof setTimeout> | null = null

// 聚焦模式
const isFocusMode = ref(false)
// 记录进入聚焦模式前的视图模式，退出时恢复
let preFocusViewMode: import('@/stores/layout').ViewMode = 'full'

// 说话人定位高亮
const locateSpeakerId = ref<number | null>(null)

function toggleLocateSpeaker(id: number) {
  if (locateSpeakerId.value === id) {
    locateSpeakerId.value = null
  } else {
    locateSpeakerId.value = id
  }
}

// WS 推送的说话人数量优先，回退到本地推算
const displaySpeakerCount = computed(() => {
  if (ws.speakerCount.value > 0) return ws.speakerCount.value
  return speakerIds.value.size
})

const filteredSpeakers = computed(() => {
  const q = bindSearch.value.trim().toLowerCase()
  if (!q) return speakers.value
  return speakers.value.filter(s => s.name.toLowerCase().includes(q))
})

function currentBinding(speakerUuid: string): string | undefined {
  for (const [asrId, uuid] of Object.entries(realtimeSpeakerBindings.value)) {
    if (uuid === speakerUuid) return asrId
  }
  return undefined
}

const speakerIds = computed(() => {
  const ids = new Set<number>()
  for (const l of wsLines.value) ids.add(l.speaker_id)
  return ids
})

const noteCount = computed(() => userNotes.value.length)

const notesByLine = computed(() => {
  const map: Record<number, string> = {}
  for (const n of userNotes.value) {
    if (n.lineIndex >= 0) map[n.lineIndex] = n.text
  }
  return map
})

// 标记模式下被压缩的行数
const compressedCount = computed(() => {
  if (!markerMode.value) return 0
  return wsLines.value.length - wsLines.value.filter((_, i) => hasNoteAt(i)).length
})

// 可见行列表（标记模式下隐藏无标记行）
const visibleLines = computed(() => {
  if (!markerMode.value) return wsLines.value
  return wsLines.value.filter((_, i) => hasNoteAt(i))
})

function hasNoteAt(idx: number): boolean {
  return userNotes.value.some(n => n.lineIndex === idx)
}

function speakerColor(sid: string | number): string {
  return getSpeakerColor(sid)
}

function speakerStyle(sid: string | number) {
  return { '--spk-color': getSpeakerColor(sid) }
}

function getSpeakerDisplayName(line: TranscriptLine): string {
  // 优先查本地绑定映射表（realtimeSpeakerBindings）
  const binding = realtimeSpeakerBindings.value[line.speaker_id]
  if (binding) {
    const spk = speakers.value.find(s => s.id === binding)
    if (spk) return spk.name
  }
  // 其次用 WebSocket 推送的 speaker_name（后端在推送时已解析绑定姓名）
  if (line.speaker_name) return line.speaker_name
  // 兜底：i18n 默认名
  return t('recording.speaker.default_name', { id: line.speaker_id + 1 })
}

function isMeSpeaker(speakerId: number): boolean {
  const binding = realtimeSpeakerBindings.value[speakerId]
  if (!binding) return false
  const spk = speakers.value.find(s => s.id === binding)
  if (!spk?.linked_user_id || !userStore.user?.id) return false
  return spk.linked_user_id === userStore.user.id
}

function getChapterStartInfo(lineIdx: number): { title: string; chapterIdx: number } | null {
  if (wsChapters.value.length === 0) return null
  const line = wsLines.value[lineIdx]
  if (!line || !line.begin_time) return null
  for (let c = wsChapters.value.length - 1; c >= 0; c--) {
    const ch = wsChapters.value[c]
    if (line.begin_time >= ch.start_ms && (c === 0 || line.begin_time < wsChapters.value[c - 1].start_ms || lineIdx === 0)) {
      if (lineIdx === 0 || (wsLines.value[lineIdx - 1]?.begin_time || 0) < ch.start_ms) {
        return { title: ch.title, chapterIdx: c }
      }
    }
  }
  return null
}

function toggleChapterExpand(idx: number) {
  if (recExpandedChapters.has(idx)) recExpandedChapters.delete(idx)
  else recExpandedChapters.add(idx)
}

function formatRecTimeMs(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function renderMd(md: string): string {
  if (!md) return ''
  return md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^- \[ \] (.+)$/gm, '<li style="list-style:none;display:flex;align-items:center;gap:4px">☐ $1</li>')
    .replace(/^- \[x\] (.+)$/gm, '<li style="list-style:none;display:flex;align-items:center;gap:4px">☑ $1</li>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
    .replace(/^---$/gm, '<hr>')
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
}

// ── localStorage 笔记持久化 ──

function saveNotesToStorage() {
  try {
    const data: PersistedNote[] = userNotes.value.map(n => ({ id: n.id, time: n.time, text: n.text }))
    localStorage.setItem(NOTES_LS_KEY, JSON.stringify(data))
  } catch { /* 忽略 */ }
}

function restoreNotesFromStorage() {
  try {
    const saved = localStorage.getItem(NOTES_LS_KEY)
    if (!saved) return
    const data: PersistedNote[] = JSON.parse(saved)
    if (!Array.isArray(data) || data.length === 0) return
    // 合理录音时长上限：24 小时（毫秒）；超出视为旧版 Date.now() 脏数据，重置为 0
    const MAX_REASONABLE_MS = 24 * 60 * 60 * 1000
    let dirty = false
    userNotes.value = data.map(n => {
      const time = (n.time > MAX_REASONABLE_MS) ? (dirty = true, 0) : n.time
      return {
        id: n.id || crypto.randomUUID(),
        text: n.text,
        lineIndex: -1, // 恢复时无法精确匹配行号，后续 sentence 到来时自动关联
        time,
      }
    })
    // 写回清洗后的数据
    if (dirty) saveNotesToStorage()
  } catch { /* 忽略 */ }
}

function clearNotesStorage() {
  try { localStorage.removeItem(NOTES_LS_KEY) } catch { /* 忽略 */ }
}

// ── 笔记操作 ──

function onSendNote() {
  const text = noteText.value.trim()
  if (!text) return
  const lineIndex = wsLines.value.length > 0 ? wsLines.value.length - 1 : 0
  // 用 ?? 而非 ||，避免 begin_time=0（录音起始句）被误判为 falsy 而回退到 elapsed
  const time = wsLines.value[lineIndex]?.begin_time ?? (recorder.elapsed.value * 1000)
  const id = crypto.randomUUID()
  userNotes.value.push({ id, text, lineIndex, time })
  noteText.value = ''
  saveNotesToStorage()
}

function onDeleteNote(idx: number) {
  userNotes.value = userNotes.value.filter(n => n.lineIndex !== idx)
  saveNotesToStorage()
}

// ── 自动滚动 ──

function scrollIfAtBottom() {
  const el = transcriptBody.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  if (atBottom) el.scrollTop = el.scrollHeight
  else showJumpBtn.value = true
}

watch(() => wsLines.value.length, async () => {
  await nextTick()
  scrollIfAtBottom()
})

watch(wsPartial, async () => {
  await nextTick()
  scrollIfAtBottom()
})

// ── 总结倒计时：优先 WS 推送，回退本地计时器 ──

watch(() => ws.summaryCountdownSec.value, (remaining) => {
  if (remaining >= 0) {
    summaryCountdown.value = remaining
  }
})

// 总结暂停时清零倒计时，恢复时重置为间隔值（WS 会很快推送精确值）
watch(summaryPaused, (paused) => {
  if (paused) {
    summaryCountdown.value = 0
  } else {
    summaryCountdown.value = summaryInterval.value
  }
})

watch(wsSummary, () => {
  summaryCountdown.value = summaryInterval.value
})

function startFallbackTimer() {
  if (fallbackTimer) clearInterval(fallbackTimer)
  summaryCountdown.value = summaryInterval.value
  fallbackTimer = setInterval(() => {
    // 仅当 WS 未推送倒计时时使用本地计时
    if (ws.summaryCountdownSec.value < 0 && !summaryPaused.value && summaryCountdown.value > 0) {
      summaryCountdown.value--
    }
  }, 1000)
}

function jumpToLatest() {
  const el = transcriptBody.value
  if (el) { el.scrollTop = el.scrollHeight; showJumpBtn.value = false }
}

// ── 说话人绑定 ──

function openBindPopover(asrId: number) {
  bindSearch.value = ''
  bindPopover.value = {
    visible: true,
    asrId,
    style: { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
  }
}

function closeBindPopover() {
  bindPopover.value.visible = false
}

function onBindSearch() {
  // 搜索已由 computed 自动处理
}

async function onBindSpeaker(spk: Speaker) {
  const asrId = bindPopover.value.asrId
  if (asrId === null) return
  try {
    await bindSpeaker(taskId.value, asrId, spk.id)
    realtimeSpeakerBindings.value[asrId] = spk.id
    for (const line of wsLines.value) {
      if (line.speaker_id === asrId) {
        line.speaker_name = spk.name
      }
    }
    closeBindPopover()
  } catch (e) {
    console.error('bind speaker failed:', e)
  }
}

async function onCreateAndBind() {
  const name = bindSearch.value.trim()
  if (!name) return
  const asrId = bindPopover.value.asrId
  if (asrId === null) return
  try {
    const spk = await createSpeaker(name)
    speakers.value.push(spk)
    await bindSpeaker(taskId.value, asrId, spk.id)
    realtimeSpeakerBindings.value[asrId] = spk.id
    for (const line of wsLines.value) {
      if (line.speaker_id === asrId) {
        line.speaker_name = spk.name
      }
    }
    closeBindPopover()
  } catch (e) {
    console.error('create and bind speaker failed:', e)
  }
}

async function onSetFrequency(f: number) {
  summaryInterval.value = f
  summaryCountdown.value = f
  closeSummaryMore()
  try {
    await setSummaryInterval(f)
  } catch (e) {
    console.error('set summary frequency failed:', e)
  }
}

function getFreqHint(f: number): string {
  const hints: Record<number, string> = {
    30: t('recording.summary.freq_frequent'),
    60: t('recording.summary.freq_default'),
    120: t('recording.summary.freq_moderate'),
    300: t('recording.summary.freq_economical'),
  }
  return hints[f] || ''
}

async function onStopSummary() {
  closeSummaryMore()
  try {
    await stopSummary()
    // 状态由 WebSocket summary_status 消息同步，无需手动设置
  } catch (e) {
    console.error('stop summary failed:', e)
  }
}

async function onToggleSummaryPause() {
  try {
    if (summaryPaused.value) {
      await resumeSummary()
    } else {
      await pauseSummary()
    }
    // 状态由 WebSocket summary_status 消息同步，无需手动设置
  } catch (e) {
    console.error('toggle summary pause failed:', e)
  }
}

// ── 暂停/恢复 ──

async function onTogglePause() {
  const paused = recPaused.value
  console.log('[RecordingView] 切换暂停状态, 当前 isPaused:', paused)
  try {
    if (paused) {
      // 恢复：先调 API，再连 WebSocket
      console.log('[RecordingView] 恢复录音...')
      const result = await recorder.resumeRecording() as { summary_resumed?: boolean } | undefined
      // 根据 API 返回值同步总结暂停状态（WebSocket 断开期间无法收到推送）
      if (result?.summary_resumed) {
        ws.summaryPaused.value = false
      }
      console.log('[RecordingView] API 恢复成功, 连接 WebSocket...')
      ws.connect(taskId.value)
      console.log('[RecordingView] 恢复完成')
    } else {
      // 暂停：先断 WebSocket，再调 API
      console.log('[RecordingView] 暂停录音, 先断开 WebSocket...')
      ws.disconnect()
      console.log('[RecordingView] WebSocket 已断开, 调用 API...')
      const result = await recorder.pauseRecording() as { summary_paused?: boolean } | undefined
      // 根据 API 返回值同步总结暂停状态（WebSocket 已断开，无法收到推送）
      if (result?.summary_paused) {
        ws.summaryPaused.value = true
      }
      console.log('[RecordingView] 暂停完成')
    }
  } catch (e) {
    console.error('[RecordingView] 暂停/恢复失败:', e)
    // 如果暂停失败，尝试重新连接 WebSocket
    if (!recPaused.value && !ws.connected.value) {
      console.log('[RecordingView] 暂停失败, 重新连接 WebSocket...')
      ws.connect(taskId.value)
    }
  }
}

// ── 聚焦模式 ──

function onFocusMode() {
  isFocusMode.value = !isFocusMode.value
  if (isFocusMode.value) {
    // 进入聚焦模式：记住当前视图模式，折叠两侧边栏
    preFocusViewMode = layout.viewMode
    layout.setViewMode('center')
  } else {
    // 退出聚焦模式：恢复之前的视图模式
    layout.setViewMode(preFocusViewMode)
  }
}

// ── 结束录音 ──

async function onStop() {
  ending.value = true
  stopFailed.value = false
  ws.disconnect()
  if (fallbackTimer) clearInterval(fallbackTimer)

  // 笔记通过 stop body 一次性提交（避免双重请求）
  const notesText = userNotes.value.length > 0
    ? userNotes.value.map(n => `[${formatNoteTime(n.lineIndex, n.time)}] ${n.text}`).join('\n')
    : undefined

  try {
    const result = await recorder.stopRecording(notesText)
    clearNotesStorage()
    // 2 秒结束过渡动画
    await new Promise(r => setTimeout(r, 2000))
    // [状态同步] 停止录音后刷新任务列表
    await taskStore.loadTasks()
    const tid = result?.task_id || recorder.taskId.value
    if (tid) router.push({ name: 'generating', params: { taskId: tid } })
  } catch (e: unknown) {
    stopFailed.value = true
    stopErrorMsg.value = e instanceof Error ? e.message : t('common.status.unknown_error')
  }
}

function onForceQuit() {
  // 强制退出：移除结束状态，直接跳转
  ending.value = false
  stopFailed.value = false
  clearNotesStorage()
  const tid = recorder.taskId.value
  // [状态同步] 停止录音后刷新任务列表
  taskStore.loadTasks().then(() => {
    if (tid) router.push({ name: 'generating', params: { taskId: tid } })
    else router.push('/')
  })
}

// ── 存在性警告处理 ──

/** 用户确认继续录制：重置评分，发送确认心跳，清除警告 */
function onPresenceContinue() {
  presenceScore.value = PRESENCE_SCORE_MAX
  ws.sendHeartbeat(presenceScore.value, true)  // user_ack = true
  ws.clearPresenceWarning()
}

/** 用户选择停止录制：调用现有 onStop 流程 */
function onPresenceStop() {
  ws.clearPresenceWarning()
  onStop()
}

async function onAbandon() {
  showAbandon.value = false
  ws.disconnect()
  if (fallbackTimer) clearInterval(fallbackTimer)
  clearNotesStorage()
  await recorder.abandonRecording()
  // [状态同步] 放弃录音后刷新任务列表
  await taskStore.loadTasks()
  router.push('/')
}

function formatNoteTime(lineIdx: number, fallbackTimeMs: number): string {
  const line = lineIdx >= 0 ? wsLines.value[lineIdx] : null
  // 用 ?? 而非 ||，避免 begin_time=0（录音起始句）被误判为 falsy
  const timeMs = line?.begin_time ?? fallbackTimeMs
  if (!timeMs) return '00:00'
  const sec = Math.floor(timeMs / 1000)
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ── 说话人数量闪烁 ──

watch(() => ws.speakerCount.value, (newCount, oldCount) => {
  if (newCount > oldCount && newCount > 0) {
    speakerCountUpdated.value = true
    if (speakerCountFlashTimer) clearTimeout(speakerCountFlashTimer)
    speakerCountFlashTimer = setTimeout(() => { speakerCountUpdated.value = false }, 2000)
  }
})

// ── 暂停状态同步 WebSocket ──

watch(recPaused, async (paused) => {
  console.log('[RecordingView] isPaused 变化:', paused, 'WebSocket 状态:', ws.connected.value)
  if (paused && ws.connected.value) {
    // 暂停但 WebSocket 还连着，强制断开
    console.warn('[RecordingView] 暂停状态下 WebSocket 仍连接, 强制断开')
    ws.disconnect()
  } else if (!paused && !ws.connected.value && taskId.value) {
    // 恢复但未连接，重新连接
    console.log('[RecordingView] 恢复状态下 WebSocket 未连接, 重新连接')
    ws.connect(taskId.value)
  }
})

// Persist tab selection to localStorage
watch(recTab, (tab) => {
  localStorage.setItem('oms_rec_active_tab', tab)
})

// ── 生命周期 ──

onMounted(async () => {
  const tid = taskId.value
  if (tid) {
    recorder.taskId.value = tid
    await recorder.checkStatus()
    ws.connect(tid)
    try {
      speakers.value = await fetchSpeakers()
    } catch (e) {
      console.error('load speakers failed:', e)
    }
    startFallbackTimer()
    restoreNotesFromStorage()
  }
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  ws.disconnect()
  if (fallbackTimer) clearInterval(fallbackTimer)
  if (speakerCountFlashTimer) clearTimeout(speakerCountFlashTimer)
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKeydown)
})

function onDocClick(e: Event) {
  if (bindPopover.value.visible) {
    const target = e.target as HTMLElement
    if (!target.closest('.rec-bind-popover')) {
      closeBindPopover()
    }
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isFocusMode.value) {
    onFocusMode()
  }
}
</script>

<style scoped>
/* 转写行气泡样式 */
.rec-line-body {
  display: flex;
  width: 100%;
}
.rec-line-text {
  display: inline-block;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--radius-lg);
  color: var(--fg);
  max-width: 85%;
}

/* "我说的" 右对齐气泡对话框风格（还原 1.0 版本） */
.rec-line.is-me {
  align-items: flex-end;
  background: transparent;
  border: none;
  border-radius: 0;
  padding: var(--s-1) 0;
  margin: var(--s-1) 0;
}
.rec-line.is-me .rec-line-head {
  flex-direction: row-reverse;
  justify-content: flex-start;
}
.rec-line.is-me .rec-line-body {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}
.rec-line.is-me .rec-line-text {
  display: inline-block;
  background: var(--mine-soft);
  border: 1px solid var(--mine);
  padding: var(--s-2) var(--s-3);
  border-radius: 12px;
  color: var(--fg);
  text-align: left;
  max-width: 70%;
}
.rec-line.is-me .rec-line-speaker {
  color: var(--mine);
}

/* 说话人定位高亮 */
.rec-line.is-located {
  opacity: 1 !important;
}

.rec-line.is-dimmed {
  opacity: 0.2;
}

/* 定位按钮 */
.rec-line-locate-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-left: 6px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--subtle);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.rec-line-locate-btn:hover {
  background: var(--border);
  color: var(--fg);
}
</style>
