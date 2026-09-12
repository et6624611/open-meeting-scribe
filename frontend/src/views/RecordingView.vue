<template>
  <div class="rec-main" :class="{ 'is-ending': ending }">
    <!-- 顶栏 -->
    <RecControlBar
      :paused="recPaused"
      :display-speaker-count="displaySpeakerCount"
      :speaker-count-updated="speakerCountUpdated"
      :projects="projects"
      :project-id="task?.project_id"
      :project-name="currentProjectName"
      :show-project-dropdown="showProjectDropdown"
      :is-focus-mode="isFocusMode"
      @toggle-project-dropdown="showProjectDropdown = !showProjectDropdown"
      @select-project="onSelectProject"
      @toggle-focus="onFocusMode"
    />

    <!-- 内容区 -->
    <div class="rec-content-area" :class="{ 'tab-summary': recTab === 'summary' }">
      <!-- Tab 切换 -->
      <div class="rec-tab-bar">
        <button class="rec-tab" :class="{ active: recTab === 'transcript' }" @click="recTab = 'transcript'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          {{ t('recording.tab.transcript') }}
        </button>
        <button class="rec-tab" :class="{ active: recTab === 'summary' }" @click="recTab = 'summary'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="21" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="3" y2="18"/></svg>
          {{ t('recording.tab.summary') }}
        </button>
      </div>

      <!-- 音量警告 -->
      <div class="rec-volume-warning" v-if="ws.volumeWarning.value">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>
        <span>{{ t('recording.volume_warning') }}</span>
        <button class="rec-volume-dismiss" @click="ws.volumeWarning.value = ''">&times;</button>
      </div>

      <!-- 存在性警告（温和） -->
      <div class="rec-presence-warning" v-if="ws.presenceWarning.value && ws.presenceWarning.value.level === 'gentle'">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span>{{ t('recording.presence_warning.gentle_text', { minutes: ws.presenceWarning.value.silent_minutes }) }}</span>
        <div class="rec-presence-actions">
          <button class="rec-presence-btn rec-presence-btn-continue" @click="onPresenceContinue">{{ t('recording.presence_warning.continue_recording') }}</button>
          <button class="rec-presence-btn rec-presence-btn-stop" @click="onPresenceStop">{{ t('recording.presence_warning.stop_recording') }}</button>
        </div>
      </div>

      <!-- 存在性警告（紧急） -->
      <div class="rec-presence-overlay" v-if="ws.presenceWarning.value && ws.presenceWarning.value.level === 'urgent'">
        <div class="rec-presence-dialog">
          <div class="rec-presence-dialog-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div>
          <div class="rec-presence-dialog-title">{{ t('recording.presence_warning.urgent_title') }}</div>
          <div class="rec-presence-dialog-desc">{{ t('recording.presence_warning.urgent_text', { minutes: ws.presenceWarning.value.silent_minutes, countdown: ws.presenceWarning.value.countdown_seconds }) }}</div>
          <div class="rec-presence-dialog-actions">
            <button class="rec-presence-btn rec-presence-btn-continue" @click="onPresenceContinue">{{ t('recording.presence_warning.continue_recording') }}</button>
            <button class="rec-presence-btn rec-presence-btn-stop" @click="onPresenceStop">{{ t('recording.presence_warning.stop_and_save') }}</button>
          </div>
        </div>
      </div>

      <!-- 总结进度条 -->
      <div class="rec-summary-progress" v-if="recTab === 'summary' && summaryCountdown > 0 && !summaryPaused">
        <div class="rec-summary-progress-bar" :class="{ 'is-warning': summaryCountdown <= 10 }" :style="{ width: summaryProgressPercent + '%' }"></div>
      </div>

      <!-- 结束过渡遮罩 -->
      <div class="rec-ending-overlay" v-if="ending">
        <template v-if="stopFailed">
          <div class="rec-ending-icon" style="margin-bottom:4px"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--rec)" stroke-width="2" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div>
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

      <!-- 左栏：转写原文 -->
      <RecTranscriptPanel
        ref="transcriptRef"
        :is-visible="recTab === 'transcript'"
        :lines="wsLines"
        :partial-text="wsPartial"
        :chapters="wsChapters"
        :show-transcript="showTranscript"
        :marker-mode="markerMode"
        :notes-by-line="notes.notesByLine.value"
        :compressed-count="compressedCount"
        :expanded-chapters="recExpandedChapters"
        :locate-id="locateSpeakerId"
        :show-jump-btn="showJumpBtn"
        :get-speaker-name="getSpeakerDisplayName"
        :is-me="isMeSpeaker"
        :has-note-at="hasNoteAt"
        :get-chapter-start="getChapterStartInfo"
        @update:show-transcript="showTranscript = $event"
        @update:marker-mode="markerMode = $event"
        @toggle-chapter="toggleChapterExpand"
        @open-bind="openBindPopover"
        @toggle-locate="toggleLocateSpeaker"
        @delete-note="notes.deleteNote"
        @jump-latest="jumpToLatest"
      />

      <!-- 右栏：实时总结 -->
      <RecSummaryPanel
        :is-active="recTab === 'summary'"
        :summary-html="summaryHtml"
        :paused="summaryPaused"
        :status-text="summaryStatusText"
        :countdown="summaryCountdown"
        :progress-percent="summaryProgressPercent"
        :interval="summaryInterval"
        @toggle-pause="onToggleSummaryPause"
        @stop-summary="onStopSummary"
        @set-frequency="onSetFrequency"
      />
    </div>

    <!-- 随记输入栏 -->
    <RecNotesBar
      ref="notesBarRef"
      :marker-mode="markerMode"
      :note-text="noteText"
      :note-count="notes.noteCount.value"
      @update:marker-mode="markerMode = $event"
      @update:note-text="noteText = $event"
      @send-note="onSendNote"
    />

    <!-- 底部控制栏 -->
    <div class="rec-control-bar">
      <div class="ctrl-info-group">
        <div class="waveform" :class="{ 'is-paused': recPaused }"><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div><div class="wbar"></div></div>
        <span class="ctrl-timer">{{ recorder.formatElapsed() }}</span>
        <span class="ctrl-status-text" :class="{ 'is-paused': recPaused }">{{ recPaused ? t('recording.status.paused') : t('recording.status.identifying') }}</span>
      </div>
      <div class="ctrl-actions-group">
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
    </div>

    <!-- 说话人绑定弹窗 -->
    <RecSpeakerBind
      :visible="bindPopover.visible"
      :asr-id="bindPopover.asrId"
      :popover-style="bindPopover.style"
      :speakers="speakers"
      :bindings="realtimeSpeakerBindings"
      v-model="bindSearch"
      @bind="onBindSpeaker"
      @create-and-bind="onCreateAndBind"
    />

    <!-- 放弃录音确认弹窗 -->
    <div class="abandon-overlay" :class="{ 'is-open': showAbandon }" v-if="showAbandon">
      <div class="abandon-dialog">
        <div class="abandon-dialog-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></div>
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
import { usePresenceDetection } from '@/composables/usePresenceDetection'
import { useRecordingNotes } from '@/composables/useRecordingNotes'
import { fetchSpeakers, createSpeaker, type Speaker } from '@/api/speakers'
import { fetchProjects, type Project } from '@/api/projects'
import { updateTask } from '@/api/tasks'
import { pauseSummary, resumeSummary, stopSummary, setSummaryInterval, bindSpeaker } from '@/api/record'
import RecControlBar from './recording/RecControlBar.vue'
import RecTranscriptPanel from './recording/RecTranscriptPanel.vue'
import RecSummaryPanel from './recording/RecSummaryPanel.vue'
import RecNotesBar from './recording/RecNotesBar.vue'
import RecSpeakerBind from './recording/RecSpeakerBind.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const recorder = useRecorder()
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

// ── Composables ──
const presence = usePresenceDetection((score, ack) => ws.sendHeartbeat(score, ack))
const elapsedMs = computed(() => recorder.elapsed.value * 1000)
const notes = useRecordingNotes(wsLines, elapsedMs)

// ── 本地状态 ──
const recTab = ref<'transcript' | 'summary'>('transcript')
const noteText = ref('')
const notesBarRef = ref<InstanceType<typeof RecNotesBar> | null>(null)
const transcriptRef = ref<InstanceType<typeof RecTranscriptPanel> | null>(null)
const showTranscript = ref(true)
const markerMode = ref(false)
const showJumpBtn = ref(false)
const locateSpeakerId = ref<number | null>(null)
const isFocusMode = ref(false)
let preFocusViewMode: import('@/stores/layout').ViewMode = 'full'

// 项目关联
const projects = ref<Project[]>([])
const showProjectDropdown = ref(false)
const currentProjectName = computed(() => {
  if (!task.value?.project_id) return t('generating.meta.link_project')
  return projects.value.find(p => p.id === task.value?.project_id)?.name || t('generating.meta.link_project')
})

// 说话人
const speakers = ref<Speaker[]>([])
const bindSearch = ref('')
const bindPopover = ref<{ visible: boolean; asrId: number | null; style: Record<string, string> }>({ visible: false, asrId: null, style: {} })
const realtimeSpeakerBindings = ref<Record<number, string>>({})
const speakerCountUpdated = ref(false)
let speakerCountFlashTimer: ReturnType<typeof setTimeout> | null = null

// 章节展开
const recExpandedChapters = reactive(new Set<number>())
const recAutoExpandedCount = ref(0)

// 总结
const summaryInterval = ref(60)
const summaryCountdown = ref(0)
const summaryPaused = computed(() => ws.summaryPaused.value)
const summaryStatusText = computed(() => {
  if (summaryPaused.value) return t('recording.summary.paused')
  if (!wsSummary.value) return t('recording.summary.waiting')
  return t('recording.summary.countdown', { count: summaryCountdown.value })
})
const summaryHtml = computed(() => {
  if (wsSummary.value) return renderMd(wsSummary.value)
  return `<p style="color:var(--subtle)">${t('recording.summary.waiting_content')}</p>`
})
const summaryProgressPercent = computed(() => summaryInterval.value <= 0 ? 0 : Math.max(0, Math.min(100, ((summaryInterval.value - summaryCountdown.value) / summaryInterval.value) * 100)))
let fallbackTimer: ReturnType<typeof setInterval> | null = null

// 结束/放弃
const ending = ref(false)
const stopFailed = ref(false)
const stopErrorMsg = ref('')
const showAbandon = ref(false)

// 弹出菜单
const recMoreBtn = ref<HTMLElement | null>(null)
const recDropdown = ref<HTMLElement | null>(null)
const { visible: showRecMore, toggle: toggleRecMore, close: closeRecMore } = usePopMenu(recDropdown, recMoreBtn)

// ── 计算属性 ──
const displaySpeakerCount = computed(() => ws.speakerCount.value > 0 ? ws.speakerCount.value : new Set(wsLines.value.map(l => l.speaker_id)).size)
const compressedCount = computed(() => markerMode.value ? wsLines.value.length - wsLines.value.filter((_, i) => notes.notesByLine.value[i] !== undefined).length : 0)

function hasNoteAt(idx: number): boolean { return notes.notesByLine.value[idx] !== undefined }

function getSpeakerDisplayName(line: TranscriptLine): string {
  const binding = realtimeSpeakerBindings.value[line.speaker_id]
  if (binding) { const spk = speakers.value.find(s => s.id === binding); if (spk) return spk.name }
  if (line.speaker_name) return line.speaker_name
  return t('recording.speaker.default_name', { id: line.speaker_id + 1 })
}

function isMeSpeaker(speakerId: number): boolean {
  const binding = realtimeSpeakerBindings.value[speakerId]
  if (!binding) return false
  const spk = speakers.value.find(s => s.id === binding)
  return !!spk?.linked_user_id && !!userStore.user?.id && spk.linked_user_id === userStore.user.id
}

function getChapterStartInfo(lineIdx: number): { title: string; chapterIdx: number } | null {
  if (wsChapters.value.length === 0) return null
  const line = wsLines.value[lineIdx]
  if (!line?.begin_time) return null
  for (let c = wsChapters.value.length - 1; c >= 0; c--) {
    const ch = wsChapters.value[c]
    if (line.begin_time >= ch.start_ms && (c === 0 || line.begin_time < wsChapters.value[c - 1].start_ms || lineIdx === 0)) {
      if (lineIdx === 0 || (wsLines.value[lineIdx - 1]?.begin_time || 0) < ch.start_ms) return { title: ch.title, chapterIdx: c }
    }
  }
  return null
}

function toggleChapterExpand(idx: number) { recExpandedChapters.has(idx) ? recExpandedChapters.delete(idx) : recExpandedChapters.add(idx) }

function renderMd(md: string): string {
  return md.replace(/^### (.+)$/gm, '<h3>$1</h3>').replace(/^## (.+)$/gm, '<h2>$1</h2>').replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>').replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^- \[ \] (.+)$/gm, '<li style="list-style:none;display:flex;align-items:center;gap:4px">☐ $1</li>')
    .replace(/^- \[x\] (.+)$/gm, '<li style="list-style:none;display:flex;align-items:center;gap:4px">☑ $1</li>')
    .replace(/^- (.+)$/gm, '<li>$1</li>').replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>').replace(/^---$/gm, '<hr>').replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>')
}

// ── 操作回调 ──
function onSelectProject(id: string) { showProjectDropdown.value = false; updateTask(taskId.value, { project_id: id || undefined }).then(() => taskStore.patchTaskLocal(taskId.value, { project_id: id || null })).catch(() => {}) }
function onFocusMode() { isFocusMode.value = !isFocusMode.value; isFocusMode.value ? (preFocusViewMode = layout.viewMode, layout.setViewMode('center')) : layout.setViewMode(preFocusViewMode) }
function toggleLocateSpeaker(id: number) { locateSpeakerId.value = locateSpeakerId.value === id ? null : id }
function openBindPopover(asrId: number) { bindSearch.value = ''; bindPopover.value = { visible: true, asrId, style: { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' } } }
function closeBindPopover() { bindPopover.value.visible = false }

async function onBindSpeaker(spk: Speaker) {
  const asrId = bindPopover.value.asrId; if (asrId === null) return
  try { await bindSpeaker(taskId.value, asrId, spk.id); realtimeSpeakerBindings.value[asrId] = spk.id; wsLines.value.filter(l => l.speaker_id === asrId).forEach(l => l.speaker_name = spk.name); closeBindPopover() } catch {}
}

async function onCreateAndBind() {
  const name = bindSearch.value.trim(); if (!name) return; const asrId = bindPopover.value.asrId; if (asrId === null) return
  try { const spk = await createSpeaker(name); speakers.value.push(spk); await bindSpeaker(taskId.value, asrId, spk.id); realtimeSpeakerBindings.value[asrId] = spk.id; wsLines.value.filter(l => l.speaker_id === asrId).forEach(l => l.speaker_name = spk.name); closeBindPopover() } catch {}
}

function onSendNote() { const text = noteText.value.trim(); if (!text) return; notes.addNote(text); noteText.value = '' }
function jumpToLatest() { const el = transcriptRef.value?.bodyRef; if (el) { el.scrollTop = el.scrollHeight; showJumpBtn.value = false } }

// 总结控制
async function onToggleSummaryPause() { try { summaryPaused.value ? await resumeSummary() : await pauseSummary() } catch {} }
async function onStopSummary() { try { await stopSummary() } catch {} }
async function onSetFrequency(f: number) { summaryInterval.value = f; summaryCountdown.value = f; try { await setSummaryInterval(f) } catch {} }

// 存在性警告
function onPresenceContinue() { presence.acknowledge(); ws.clearPresenceWarning() }
function onPresenceStop() { ws.clearPresenceWarning(); onStop() }

// 暂停/恢复
async function onTogglePause() {
  try {
    if (recPaused.value) { const r = await recorder.resumeRecording() as any; if (r?.summary_resumed) ws.summaryPaused.value = false; ws.connect(taskId.value) }
    else { ws.disconnect(); const r = await recorder.pauseRecording() as any; if (r?.summary_paused) ws.summaryPaused.value = true }
  } catch (e) { if (!recPaused.value && !ws.connected.value) ws.connect(taskId.value) }
}

// 结束录音
async function onStop() {
  ending.value = true; stopFailed.value = false; ws.disconnect()
  if (fallbackTimer) clearInterval(fallbackTimer)
  try {
    const result = await recorder.stopRecording(notes.getNotesText())
    notes.clearStorage()
    await new Promise(r => setTimeout(r, 2000))
    await taskStore.loadTasks()
    const tid = result?.task_id || recorder.taskId.value
    if (tid) router.push({ name: 'generating', params: { taskId: tid } })
  } catch (e: unknown) { stopFailed.value = true; stopErrorMsg.value = e instanceof Error ? e.message : t('common.status.unknown_error') }
}

function onForceQuit() { ending.value = false; stopFailed.value = false; notes.clearStorage(); const tid = recorder.taskId.value; taskStore.loadTasks().then(() => { if (tid) router.push({ name: 'generating', params: { taskId: tid } }); else router.push('/') }) }

async function onAbandon() { showAbandon.value = false; ws.disconnect(); if (fallbackTimer) clearInterval(fallbackTimer); notes.clearStorage(); await recorder.abandonRecording(); await taskStore.loadTasks(); router.push('/') }

// ── 自动滚动 ──
function scrollIfAtBottom() { const el = transcriptRef.value?.bodyRef; if (!el) return; if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) el.scrollTop = el.scrollHeight; else showJumpBtn.value = true }
function scheduleScrollCheck() { nextTick(() => requestAnimationFrame(() => scrollIfAtBottom())) }
function onTranscriptScroll() { const el = transcriptRef.value?.bodyRef; if (!el) return; showJumpBtn.value = el.scrollHeight - el.scrollTop - el.clientHeight >= 80 }

// ── 总结倒计时 ──
function startFallbackTimer() { if (fallbackTimer) clearInterval(fallbackTimer); summaryCountdown.value = summaryInterval.value; fallbackTimer = setInterval(() => { if (ws.summaryCountdownSec.value < 0 && !summaryPaused.value && summaryCountdown.value > 0) summaryCountdown.value-- }, 1000) }

// ── Watchers ──
watch(() => wsLines.value.length, () => scheduleScrollCheck())
watch(wsPartial, () => scheduleScrollCheck())
watch(() => wsChapters.value.length, (n) => { for (let c = recAutoExpandedCount.value; c < n; c++) recExpandedChapters.add(c); recAutoExpandedCount.value = n; scheduleScrollCheck() })
watch(() => ws.summaryCountdownSec.value, (r) => { if (r >= 0) summaryCountdown.value = r })
watch(summaryPaused, (p) => { summaryCountdown.value = p ? 0 : summaryInterval.value })
watch(wsSummary, () => { summaryCountdown.value = summaryInterval.value })
watch(() => ws.speakerCount.value, (n, o) => { if (n > o && n > 0) { speakerCountUpdated.value = true; if (speakerCountFlashTimer) clearTimeout(speakerCountFlashTimer); speakerCountFlashTimer = setTimeout(() => speakerCountUpdated.value = false, 2000) } })
watch(recPaused, (p) => { if (p && ws.connected.value) ws.disconnect(); else if (!p && !ws.connected.value && taskId.value) ws.connect(taskId.value) })
watch(recTab, (tab) => localStorage.setItem('oms_rec_active_tab', tab))
watch(noteText, () => { nextTick(() => { const el = notesBarRef.value?.textareaRef; if (!el) return; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; requestAnimationFrame(() => scrollIfAtBottom()) }) })

// ── 生命周期 ──
onMounted(async () => {
  const saved = localStorage.getItem('oms_rec_active_tab')
  if (saved === 'transcript' || saved === 'summary') recTab.value = saved
  registerNotesAppender((md: string) => { noteText.value = noteText.value ? noteText.value + '\n\n' + md : md })
  registerSummaryAppender((md: string) => { noteText.value = noteText.value ? noteText.value + '\n\n' + md : md })
  const bodyEl = transcriptRef.value?.bodyRef
  if (bodyEl) bodyEl.addEventListener('scroll', onTranscriptScroll)
  fetchProjects().then(l => { projects.value = l }).catch(() => {})
  ws.onSpeakerBound((id: number, uuid: string) => { realtimeSpeakerBindings.value[id] = uuid })
  presence.start()
  const tid = taskId.value
  if (tid) { recorder.taskId.value = tid; await recorder.checkStatus(); ws.connect(tid); try { speakers.value = await fetchSpeakers() } catch {}; startFallbackTimer(); notes.restoreFromStorage() }
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  const el = transcriptRef.value?.bodyRef; if (el) el.removeEventListener('scroll', onTranscriptScroll)
  presence.stop(); ws.disconnect()
  if (fallbackTimer) clearInterval(fallbackTimer)
  if (speakerCountFlashTimer) clearTimeout(speakerCountFlashTimer)
  document.removeEventListener('click', onDocClick); document.removeEventListener('keydown', onKeydown)
})

function onDocClick(e: Event) { if (bindPopover.value.visible && !(e.target as HTMLElement).closest('.rec-bind-popover')) closeBindPopover() }
function onKeydown(e: KeyboardEvent) { if (e.key === 'Escape' && isFocusMode.value) onFocusMode() }
</script>

<style scoped>
.rec-line-body { display: flex; width: 100%; }
.rec-line-text { display: inline-block; background: var(--surface); border: 1px solid var(--border-strong); padding: var(--s-2) var(--s-3); border-radius: var(--radius-lg); color: var(--fg); max-width: 85%; }
.rec-line.is-me { align-items: flex-end; background: transparent; border: none; border-radius: 0; padding: var(--s-1) 0; margin: var(--s-1) 0; }
.rec-line.is-me .rec-line-head { flex-direction: row-reverse; justify-content: flex-start; }
.rec-line.is-me .rec-line-body { display: flex; justify-content: flex-end; width: 100%; }
.rec-line.is-me .rec-line-text { display: inline-block; background: var(--mine-soft); border: 1px solid var(--mine); padding: var(--s-2) var(--s-3); border-radius: 12px; color: var(--fg); text-align: left; max-width: 70%; }
.rec-line.is-me .rec-line-speaker { color: var(--mine); }
.rec-line.is-located { opacity: 1 !important; }
.rec-line.is-dimmed { opacity: 0.2; }
.rec-line-locate-btn { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; margin-left: 6px; padding: 0; border: none; background: transparent; color: var(--subtle); cursor: pointer; border-radius: 4px; transition: all 0.2s; }
.rec-line-locate-btn:hover { background: var(--border); color: var(--fg); }
</style>
