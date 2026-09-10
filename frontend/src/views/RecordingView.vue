<template>
  <div class="rec-main" :class="{ 'is-ending': ending }">
    <!-- 顶栏 -->
    <div class="rec-header">
      <div class="rec-header-left">
        <span class="rec-title" id="recTitle">录音纪要</span>
        <span class="rec-status" id="recStatus">{{ recPaused ? '已暂停' : '识别中...' }}</span>
        <span class="rec-speaker-count" :class="{ 'has-update': speakerCountUpdated }" v-if="displaySpeakerCount > 0" title="当前识别到的说话人">
          <span class="sc-dot"></span>
          <span class="sc-num">{{ displaySpeakerCount }}</span>
          <span>位说话人</span>
        </span>
      </div>
      <div class="rec-header-right">
        <button class="btn-translate" title="翻译">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
          翻译
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <button v-if="isFocusMode" class="btn-exit-focus" @click="onFocusMode" title="退出聚焦模式 (Esc)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
          退出聚焦 Esc
        </button>
        <button v-else class="rec-summary-btn" @click="onFocusMode" title="聚焦模式 — 折叠两侧边栏">
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
          原文
        </button>
        <button class="rec-tab" :class="{ active: recTab === 'summary' }" @click="recTab = 'summary'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="21" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="3" y2="18"/></svg>
          实时总结
        </button>
      </div>

      <!-- 总结进度条（始终可见，在 Tab 栏下方） -->
      <div class="rec-summary-progress" v-if="recTab === 'summary' && summaryCountdown > 0">
        <div class="rec-summary-progress-bar" :class="{ 'is-warning': summaryCountdown <= 10 }" :style="{ width: summaryProgressPercent + '%' }"></div>
      </div>

      <!-- 结束过渡遮罩 -->
      <div class="rec-ending-overlay" v-if="ending">
        <template v-if="stopFailed">
          <div class="rec-ending-icon" style="margin-bottom:4px">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--rec)" stroke-width="2" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </div>
          <div class="rec-ending-text" style="color:var(--fg)">无法结束录音</div>
          <div class="rec-ending-sub">{{ stopErrorMsg }}</div>
          <button class="btn-force-quit" @click="onForceQuit" style="margin-top:12px;padding:8px 20px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--fg);font-size:13px;cursor:pointer">强制退出</button>
        </template>
        <template v-else>
          <div class="rec-ending-spinner"></div>
          <div class="rec-ending-text">录音已结束</div>
          <div class="rec-ending-sub">正在整理录音内容...</div>
        </template>
      </div>

      <!-- 左栏：原文 -->
      <div class="rec-transcript" id="recTranscript" v-show="recTab === 'transcript'">
        <div class="rec-transcript-header">
          <div class="rec-transcript-title">原文</div>
          <div class="rec-transcript-actions">
            <button class="btn-translate" @click="showTranscript = !showTranscript" :title="showTranscript ? '隐藏原文' : '显示原文'">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path v-if="showTranscript" d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle v-if="showTranscript" cx="12" cy="12" r="3"/><path v-else d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line v-if="!showTranscript" x1="1" y1="1" x2="23" y2="23"/></svg>
              {{ showTranscript ? '隐藏原文' : '显示原文' }}
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
            <span class="rec-chapter-title">{{ wsChapters[wsChapters.length - 1]?.title || '讨论中' }}</span>
          </div>
        </div>
        <div class="rec-transcript-body" id="recTranscriptBody" ref="transcriptBody">
          <!-- 原文隐藏指示条 -->
          <div v-if="!showTranscript" class="rec-hidden-indicator">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            已隐藏 {{ wsLines.length }} 条原文
            <button class="rec-hidden-show-btn" @click="showTranscript = true">显示原文</button>
          </div>
          <!-- 标记模式压缩指示器 -->
          <div v-if="markerMode && compressedCount > 0" class="rec-marker-compressed">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
            已压缩 {{ compressedCount }} 条无标记对话
            <button class="rec-marker-expand-btn" @click="markerMode = false">展开全部</button>
          </div>
          <template v-for="(line, i) in visibleLines" :key="i">
            <!-- 章节内联分隔线 -->
            <div v-if="getChapterStart(i)" class="chapter-divider" @click="toggleChapterExpand(i)">
              <span class="chapter-divider-label">{{ getChapterStart(i) }}</span>
            </div>
            <div class="rec-line" :class="{ 'rec-line-hidden': markerMode && !hasNoteAt(i), 'is-me': isMeSpeaker(line.speaker_id), 'is-located': locateSpeakerId === line.speaker_id, 'is-dimmed': locateSpeakerId !== null && locateSpeakerId !== line.speaker_id }">
              <div class="rec-line-head">
                <span class="rec-line-speaker" :style="speakerStyle(line.speaker_id)" @click.stop="openBindPopover(line.speaker_id)">
                  {{ getSpeakerDisplayName(line) }}
                </span>
                <button v-if="!locateSpeakerId || locateSpeakerId === line.speaker_id" class="rec-line-locate-btn" @click.stop="toggleLocateSpeaker(line.speaker_id)" title="定位此说话人">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                </button>
              </div>
              <div class="rec-line-body" v-show="showTranscript">
                <span class="rec-line-text">{{ line.text }}</span>
              </div>
              <!-- 内联随记标记 -->
              <div v-if="notesByLine[i]" class="note-inline-card">
                <span class="note-inline-text">{{ notesByLine[i] }}</span>
                <button class="note-inline-delete" @click.stop="onDeleteNote(i)" title="删除随记">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>
          </template>
          <div v-if="wsPartial" class="rec-line rec-line-partial">
            <div class="rec-line-head">
              <span class="rec-line-speaker">
                …
              </span>
            </div>
            <div class="rec-line-body" v-show="showTranscript">
              <span class="rec-line-text">{{ wsPartial }}</span>
            </div>
          </div>
          <div v-if="visibleLines.length === 0 && !wsPartial" class="rec-empty">
            <p>等待识别结果…</p>
            <p class="rec-empty-hint">开始说话后，识别内容将实时显示在这里</p>
          </div>
        </div>
        <button class="rec-jump-latest" :class="{ 'is-visible': showJumpBtn }" @click="jumpToLatest" title="回到最新内容">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="4" x2="12" y2="20"/><polyline points="18 14 12 20 6 14"/></svg>
          回到底部
        </button>
      </div>

      <!-- 右栏：实时总结（宽屏并排显示，窄屏由 tab-summary class 控制） -->
      <div class="rec-summary-panel" id="recSummaryPanel" :class="{ 'is-hidden-narrow': recTab !== 'summary' }">
        <div class="rec-summary-header">
          <div class="rec-summary-title">
            <!-- 倒计时环形进度 -->
            <div class="rec-summary-countdown-ring" v-if="summaryCountdown > 0">
              <svg width="28" height="28" viewBox="0 0 28 28">
                <circle class="ring-bg" cx="14" cy="14" r="11"/>
                <circle class="ring-fg" :class="{ 'is-warning': summaryCountdown <= 10 }" cx="14" cy="14" r="11"
                  :stroke-dasharray="69.115" :stroke-dashoffset="69.115 * (1 - summaryProgressPercent / 100)"/>
              </svg>
              <span class="ring-text" :class="{ 'is-warning': summaryCountdown <= 10 }">{{ summaryCountdown }}</span>
            </div>
            实时总结
            <span class="rec-summary-status">{{ summaryStatusText }}</span>
          </div>
          <div class="rec-summary-actions">
            <button class="rec-summary-btn" @click="onToggleSummaryPause" :title="summaryPaused ? '恢复总结' : '暂停总结'">
              <svg v-if="!summaryPaused" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
            </button>
            <div class="more-menu-wrap">
              <button ref="summaryMoreBtn" class="rec-summary-btn" @click="toggleSummaryMore" title="更多" aria-haspopup="menu" aria-label="总结更多操作">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
              </button>
              <div ref="summaryDropdown" class="more-menu-dropdown" :class="{ 'is-open': showSummaryMore }" role="menu">
                <button class="more-menu-item" @click="onStopSummary" role="menuitem">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
                  停止总结
                </button>
                <div style="height:1px;background:var(--border);margin:4px 0"></div>
                <div style="padding:4px 6px;font-size:11px;color:var(--muted);font-weight:500">刷新频率</div>
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
          <div class="rec-summary-content" v-html="wsSummary ? renderMd(wsSummary) : '<p style=\'color:var(--subtle)\'>等待足够对话内容后自动生成总结…</p>'"></div>
        </div>
      </div>
    </div>

    <!-- 全宽随记输入栏 -->
    <div class="rec-notes-bar" id="recNotesBar">
      <span class="rec-notes-bar-icon" aria-hidden="true">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      </span>
      <button class="marker-toggle-btn" :class="{ active: markerMode }" @click="markerMode = !markerMode" title="标记模式 — 压缩无标记对话">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        标记 {{ noteCount > 0 ? noteCount : '' }}
      </button>
      <textarea class="rec-notes-input" id="recNotesInput" rows="1" placeholder="记录随记... Enter 发送，Shift+Enter 换行" v-model="noteText" @keydown.enter.exact.prevent="onSendNote"></textarea>
      <button class="rec-notes-bar-send" :disabled="!noteText.trim()" @click="onSendNote" aria-label="发送随记">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </div>

    <!-- 底部控制栏 -->
    <div class="rec-control-bar">
      <div class="waveform" id="waveform" :class="{ 'is-paused': recPaused }">
        <div class="wbar"></div><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div>
      </div>
      <span class="ctrl-timer" id="recTimer">{{ recorder.formatElapsed() }}</span>
      <button class="btn-pause" @click="onTogglePause" :title="recPaused ? '恢复录音' : '暂停录音'">
        <svg v-if="!recPaused" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
        <span class="btn-pause-text">{{ recPaused ? '恢复' : '暂停' }}</span>
      </button>
      <button class="btn-end-rec" @click="onStop">结束</button>
      <div class="more-menu-wrap">
        <button ref="recMoreBtn" class="more-menu-btn" @click="toggleRecMore" title="更多" aria-haspopup="menu" aria-label="更多操作">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
        </button>
        <div ref="recDropdown" class="more-menu-dropdown" :class="{ 'is-open': showRecMore }" role="menu">
          <button class="more-menu-item danger" @click="closeRecMore(); showAbandon = true" role="menuitem">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            放弃录音
          </button>
        </div>
      </div>
    </div>

    <!-- 说话人绑定弹窗 -->
    <div class="rec-bind-popover" v-if="bindPopover.visible" :style="bindPopover.style" @click.stop>
      <div class="bind-title">绑定说话人身份</div>
      <div class="bind-search">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input v-model="bindSearch" placeholder="搜索说话人..." @input="onBindSearch"/>
      </div>
      <div class="bind-list">
        <div v-for="spk in filteredSpeakers" :key="spk.id"
          class="bind-option" :class="{ 'is-selected': bindPopover.asrId !== null && currentBinding(spk.id) === String(bindPopover.asrId) }"
          @click="onBindSpeaker(spk)">
          <span class="bind-name" :style="{ color: speakerColor(spk.id) }">{{ spk.name }}{{ spk.is_me ? '（我）' : '' }}</span>
        </div>
        <div v-if="filteredSpeakers.length === 0" class="bind-empty">无匹配结果</div>
      </div>
      <div class="bind-divider"></div>
      <div class="bind-footer">
        <div class="bind-new" @click="onCreateAndBind" v-if="bindSearch.trim()">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建「{{ bindSearch.trim() }}」并绑定
        </div>
      </div>
    </div>

    <!-- 放弃录音确认弹窗 -->
    <div class="abandon-overlay" :class="{ 'is-open': showAbandon }" v-if="showAbandon">
      <div class="abandon-dialog">
        <div class="abandon-dialog-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </div>
        <div class="abandon-dialog-title">放弃本次录音？</div>
        <div class="abandon-dialog-desc">录音将被终止，所有数据将永久删除，无法恢复。</div>
        <div class="abandon-dialog-info">已录制时长：{{ recorder.formatElapsed() }}</div>
        <div class="abandon-dialog-actions">
          <button class="btn-cancel" @click="showAbandon = false">取消</button>
          <button class="btn-confirm-abandon" @click="onAbandon">确认放弃</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRecorder } from '@/composables/useRecorder'
import { useWebSocketTranscript, type TranscriptLine } from '@/composables/useWebSocket'
import { useTaskStore } from '@/stores/task'
import { useUserStore } from '@/stores/user'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { usePopMenu } from '@/composables/usePopMenu'
import { getSpeakerColor } from '@/utils/speakerColors'
import { fetchSpeakers, createSpeaker, type Speaker } from '@/api/speakers'
import {
  pauseSummary, resumeSummary, stopSummary, setSummaryInterval, bindSpeaker
} from '@/api/record'

const NOTES_LS_KEY = 'oms_rec_timestamped_notes'

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
const { registerNotesAppender, registerSummaryAppender } = useQuoteRef()

const taskId = computed(() => route.params.taskId as string)

const recTab = ref<'transcript' | 'summary'>('transcript')
const noteText = ref('')

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
})

onUnmounted(() => {
  const el = transcriptBody.value
  if (el) {
    el.removeEventListener('scroll', onTranscriptScroll)
  }
})

function onTranscriptScroll() {
  const el = transcriptBody.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  showJumpBtn.value = !atBottom
}
const recMoreBtn = ref<HTMLElement | null>(null)
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
const summaryPaused = ref(false)
const summaryStatusText = computed(() => {
  if (summaryPaused.value) return '已暂停'
  if (!wsSummary.value) return '等待中'
  return `距下次刷新 ${summaryCountdown.value}s`
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
  const binding = realtimeSpeakerBindings.value[line.speaker_id]
  if (binding) {
    const spk = speakers.value.find(s => s.id === binding)
    if (spk) return spk.name
  }
  return line.speaker_name || `说话人${line.speaker_id + 1}`
}

function isMeSpeaker(speakerId: number): boolean {
  const binding = realtimeSpeakerBindings.value[speakerId]
  if (!binding) return false
  const spk = speakers.value.find(s => s.id === binding)
  if (!spk?.linked_user_id || !userStore.user?.id) return false
  return spk.linked_user_id === userStore.user.id
}

function getChapterStart(lineIdx: number): string | null {
  if (wsChapters.value.length === 0) return null
  const line = wsLines.value[lineIdx]
  if (!line || !line.begin_time) return null
  for (let c = wsChapters.value.length - 1; c >= 0; c--) {
    const ch = wsChapters.value[c]
    if (line.begin_time >= ch.start_time && (c === 0 || line.begin_time < wsChapters.value[c - 1].start_time || lineIdx === 0)) {
      if (lineIdx === 0 || (wsLines.value[lineIdx - 1]?.begin_time || 0) < ch.start_time) {
        return ch.title
      }
    }
  }
  return null
}

function toggleChapterExpand(_idx: number) {
  // 章节展开/收起（预留）
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
    userNotes.value = data.map(n => ({
      id: n.id || crypto.randomUUID(),
      text: n.text,
      lineIndex: -1, // 恢复时无法精确匹配行号，后续 sentence 到来时自动关联
      time: n.time,
    }))
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
  const time = wsLines.value[lineIndex]?.begin_time || Date.now()
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
    console.error('绑定说话人失败:', e)
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
    console.error('创建并绑定说话人失败:', e)
  }
}

async function onSetFrequency(f: number) {
  summaryInterval.value = f
  summaryCountdown.value = f
  closeSummaryMore()
  try {
    await setSummaryInterval(f)
  } catch (e) {
    console.error('设置总结频率失败:', e)
  }
}

function getFreqHint(f: number): string {
  const hints: Record<number, string> = { 30: '频繁', 60: '默认', 120: '适中', 300: '省量' }
  return hints[f] || ''
}

async function onStopSummary() {
  closeSummaryMore()
  try {
    await stopSummary()
    summaryPaused.value = true
  } catch (e) {
    console.error('停止总结失败:', e)
  }
}

async function onToggleSummaryPause() {
  try {
    if (summaryPaused.value) {
      await resumeSummary()
      summaryPaused.value = false
    } else {
      await pauseSummary()
      summaryPaused.value = true
    }
  } catch (e) {
    console.error('切换总结暂停失败:', e)
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
      await recorder.resumeRecording()
      console.log('[RecordingView] API 恢复成功, 连接 WebSocket...')
      ws.connect(taskId.value)
      console.log('[RecordingView] 恢复完成')
    } else {
      // 暂停：先断 WebSocket，再调 API
      console.log('[RecordingView] 暂停录音, 先断开 WebSocket...')
      ws.disconnect()
      console.log('[RecordingView] WebSocket 已断开, 调用 API...')
      await recorder.pauseRecording()
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
  document.querySelector('.body')?.classList.toggle('focus-mode', isFocusMode.value)
}

// ── 结束录音 ──

async function onStop() {
  ending.value = true
  stopFailed.value = false
  ws.disconnect()
  if (fallbackTimer) clearInterval(fallbackTimer)

  // 笔记通过 stop body 一次性提交（避免双重请求）
  const notesText = userNotes.value.length > 0
    ? userNotes.value.map(n => `[${formatNoteTime(n.lineIndex)}] ${n.text}`).join('\n')
    : undefined

  try {
    const result = await recorder.stopRecording(notesText)
    clearNotesStorage()
    // 2 秒结束过渡动画
    await new Promise(r => setTimeout(r, 2000))
    await taskStore.loadTasks()
    const tid = result?.task_id || recorder.taskId.value
    if (tid) router.push({ name: 'generating', params: { taskId: tid } })
  } catch (e: unknown) {
    stopFailed.value = true
    stopErrorMsg.value = e instanceof Error ? e.message : '未知错误'
  }
}

function onForceQuit() {
  // 强制退出：移除结束状态，直接跳转
  ending.value = false
  stopFailed.value = false
  clearNotesStorage()
  const tid = recorder.taskId.value
  taskStore.loadTasks().then(() => {
    if (tid) router.push({ name: 'generating', params: { taskId: tid } })
    else router.push('/')
  })
}

async function onAbandon() {
  showAbandon.value = false
  ws.disconnect()
  if (fallbackTimer) clearInterval(fallbackTimer)
  clearNotesStorage()
  await recorder.abandonRecording()
  await taskStore.loadTasks()
  router.push('/')
}

function formatNoteTime(lineIdx: number): string {
  const line = wsLines.value[lineIdx]
  if (!line?.begin_time) return '00:00'
  const sec = Math.floor(line.begin_time / 1000)
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
      console.error('加载说话人列表失败:', e)
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
