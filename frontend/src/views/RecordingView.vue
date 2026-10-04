<template>
  <div class="rec-main" :class="{ 'is-ending': ending }">
    <!-- 顶栏 / Top bar -->
    <RecControlBar
      :paused="recPaused"
      :display-speaker-count="displaySpeakerCount"
      :speaker-count-updated="speakerCountUpdated"
      :projects="projects"
      :project-id="task?.project_id"
      :project-name="currentProjectName"
      :show-project-dropdown="showProjectDropdown"
      :is-focus-mode="isFocusMode"
      :roster-count="rosterComposable.roster.value.length"
      :show-roster-dropdown="showRosterDropdown"
      :roster="rosterComposable.roster.value"
      :roster-search="rosterSearch"
      :filtered-roster-speakers="filteredRosterSpeakers"
      :roster-focus-idx="rosterFocusIdx"
      @toggle-project-dropdown="showProjectDropdown = !showProjectDropdown; showRosterDropdown = false"
      @select-project="onSelectProject"
      @close-project-dropdown="showProjectDropdown = false"
      @toggle-focus="onFocusMode"
      @toggle-roster="toggleRosterDropdown"
      @update:roster-search="rosterSearch = $event"
      @roster-keydown="onRosterKeydown"
      @roster-remove="rosterComposable.removeMember($event)"
      @roster-select="onRosterSelect"
      @roster-create="onRosterCreate"
      @close-roster="showRosterDropdown = false"
    />

    <!-- 内容区 / Content area -->
    <div class="rec-content-area" :class="{ 'tab-insights': recTab === 'insights', 'insights-expanded': insightsExpanded }">
      <!-- Tab 切换 / Tab switcher -->
      <div class="rec-tab-bar">
        <button class="rec-tab" :class="{ active: recTab === 'transcript' }" @click="recTab = 'transcript'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          {{ t('recording.tab.transcript') }}
        </button>
        <button class="rec-tab" :class="{ active: recTab === 'insights' }" @click="recTab = 'insights'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
          {{ t('recording.tab.insights') }}
        </button>
      </div>

      <!-- 音量警告 / Volume warning -->
      <div class="rec-volume-warning" v-if="ws.volumeWarning.value">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>
        <span>{{ t('recording.volume_warning') }}</span>
        <button class="rec-volume-dismiss" @click="ws.volumeWarning.value = ''">&times;</button>
      </div>

      <!-- 存在性警告（温和） / Presence warning (gentle) -->
      <div class="rec-presence-warning" v-if="ws.presenceWarning.value && ws.presenceWarning.value.level === 'gentle'">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span>{{ t('recording.presence_warning.gentle_text', { minutes: ws.presenceWarning.value.silent_minutes }) }}</span>
        <div class="rec-presence-actions">
          <button class="rec-presence-btn rec-presence-btn-continue" @click="onPresenceContinue">{{ t('recording.presence_warning.continue_recording') }}</button>
          <button class="rec-presence-btn rec-presence-btn-stop" @click="onPresenceStop">{{ t('recording.presence_warning.stop_recording') }}</button>
        </div>
      </div>

      <!-- 存在性警告（紧急） / Presence warning (urgent) -->
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

      <!-- 结束过渡遮罩 / End transition overlay -->
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

      <!-- 左栏：转写原文（宽屏并排，窄屏由 CSS tab-insights 切换） / Left: transcript (side-by-side on wide, CSS tab on narrow) -->
      <RecTranscriptPanel
        :lines="wsLines"
        :listening="ws.listening.value"
        :chapters="wsChapters"
        :show-transcript="showTranscript"
        :marker-mode="markerMode"
        :notes-by-line="notes.notesByLine.value"
        :compressed-count="compressedCount"
        :expanded-chapters="recExpandedChapters"
        :locate-id="locateSpeakerId"
        :total-duration-ms="elapsedMs"
        :current-time-ms="elapsedMs"
        :get-speaker-name="getSpeakerDisplayName"
        :is-me="isMeSpeaker"
        :has-note-at="hasNoteAt"
        :chapter-start-map="chapterStartMap"
        :translation-map="translation.translationMap.value"
        :translation-display="translation.displayMode.value"
        :translate-enabled="translation.enabled.value"
        :target-lang="translation.targetLang.value"
        :target-lang-label="translation.targetLangLabel.value"
        :supported-languages="translation.supportedLanguages"
        @toggle-translate="translation.toggle()"
        @set-translate-lang="translation.setTargetLang($event)"
        @update:show-transcript="showTranscript = $event"
        @update:marker-mode="markerMode = $event"
        @toggle-chapter="toggleChapterExpand"
        @open-bind="openBindPopover"
        @toggle-locate="toggleLocateSpeaker"
        @delete-note="notes.deleteNote"
      />

      <!-- 右栏：洞察台（宽屏并排，窄屏由 CSS tab-insights 切换） / Right: Insight Deck (side-by-side on wide, CSS tab on narrow) -->
      <RecInsightsPanel
        :messages="insights.insightMessages.value"
        :acted-actions="actedActions"
        :expanded="insightsExpanded"
        :task-id="taskId"
        :one-page-factor="task?.one_page?.insights"
        @toggle-message="insights.toggleExpanded($event)"
        @action="onInsightAction"
        @toggle-expand="insightsExpanded = !insightsExpanded"
        @seek-to="player.seekToMs($event)"
      />
    </div>

    <!-- 随记输入栏 / Quick note input bar -->
    <RecNotesBar
      ref="notesBarRef"
      :marker-mode="markerMode"
      :note-text="noteText"
      :note-count="notes.noteCount.value"
      @update:marker-mode="markerMode = $event"
      @update:note-text="noteText = $event"
      @send-note="onSendNote"
    />

    <!-- 底部控制栏 / Bottom control bar -->
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
          <button ref="recMoreBtn" class="more-menu-btn" v-bind="recMoreTriggerAttrs" @click="toggleRecMore" :title="t('common.action.more')" :aria-label="t('common.action.more')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
          </button>
          <div ref="recDropdown" class="more-menu-dropdown" v-bind="recMoreMenuAttrs" :class="{ 'is-open': showRecMore }">
            <button class="more-menu-item danger" @click="closeRecMore(); showAbandon = true" role="menuitem">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              {{ t('recording.control.abandon') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 说话人绑定弹窗 / Speaker binding dialog -->
    <RecSpeakerBind
      :visible="bindPopover.visible"
      :asr-id="bindPopover.asrId"
      :popover-style="bindPopover.style"
      :speakers="speakers"
      :bindings="realtimeSpeakerBindings"
      v-model="bindSearch"
      @bind="onBindSpeaker"
      @create-and-bind="onCreateAndBind"
      @close="closeBindPopover"
    />

    <!-- 放弃录音确认弹窗 / Abandon recording confirmation dialog -->
    <div class="abandon-overlay" data-vue-overlay :class="{ 'is-open': showAbandon }" v-if="showAbandon">
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
import { normalizeSpeakerName } from '@/utils/speakerDisplay'
import { useRecorder } from '@/composables/useRecorder'
import { useWebSocketTranscript, type TranscriptLine } from '@/composables/useWebSocket'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { useUserStore } from '@/stores/user'
import { usePlayerStore } from '@/stores/player'
import { usePopMenu } from '@/composables/usePopMenu'
import { useEscClose } from '@/composables/useEscClose'
import { usePresenceDetection } from '@/composables/usePresenceDetection'
import { useRecordingNotes } from '@/composables/useRecordingNotes'
import { useMeetingRoster } from '@/composables/useMeetingRoster'
import { useTranslation } from '@/composables/useTranslation'
import { fetchSpeakers, createSpeaker, type Speaker } from '@/api/speakers'
import { fetchProjects, type Project } from '@/api/projects'
import { updateTask } from '@/api/tasks'
import { bindSpeaker } from '@/api/record'
import RecControlBar from './recording/RecControlBar.vue'
import RecTranscriptPanel from './recording/RecTranscriptPanel.vue'
import RecInsightsPanel from './recording/RecInsightsPanel.vue'
import { useAiInsights } from '@/composables/useAiInsights'
import type { InsightMessage, InsightAction } from '@/composables/useAiInsights'
import RecNotesBar from './recording/RecNotesBar.vue'
import RecSpeakerBind from './recording/RecSpeakerBind.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const recorder = useRecorder()
const recPaused = recorder.isPaused
const ws = useWebSocketTranscript()
const wsLines = ws.lines
const wsChapters = ws.chapters
const translation = useTranslation(ws)
const taskStore = useTaskStore()
const userStore = useUserStore()
const player = usePlayerStore()
const layout = useLayoutStore()

const taskId = computed(() => route.params.taskId as string)
const task = computed(() => taskStore.tasks.find(t => t.task_id === taskId.value) ?? null)

// ── Composables ──
const presence = usePresenceDetection((score, ack) => ws.sendHeartbeat(score, ack))
const elapsedMs = computed(() => recorder.elapsed.value * 1000)
const notes = useRecordingNotes(wsLines, elapsedMs)
const rosterComposable = useMeetingRoster(taskId.value, task)

// ── 本地状态 / Local state ──
const recTab = ref<'transcript' | 'insights'>('transcript')
const noteText = ref('')
const notesBarRef = ref<InstanceType<typeof RecNotesBar> | null>(null)
const showTranscript = ref(true)
const markerMode = ref(false)
const locateSpeakerId = ref<number | null>(null)
const isFocusMode = ref(false)
let preFocusViewMode: import('@/stores/layout').ViewMode = 'full'

// 项目关联 / Project linking
const projects = ref<Project[]>([])
const showProjectDropdown = ref(false)
const currentProjectName = computed(() => {
  if (!task.value?.project_id) return t('generating.meta.link_project')
  return projects.value.find(p => p.id === task.value?.project_id)?.name || t('generating.meta.link_project')
})

// 参会人 / Roster
const showRosterDropdown = ref(false)
const rosterSearch = ref('')
const rosterFocusIdx = ref(-1)
const rosterSearchRef = ref<HTMLInputElement | null>(null)

const filteredRosterSpeakers = computed(() => {
  const q = rosterSearch.value.toLowerCase().trim()
  let list = speakers.value.filter(s => !rosterComposable.roster.value.includes(s.name))
  if (q) list = list.filter(s => s.name.toLowerCase().includes(q) || (s.role || '').toLowerCase().includes(q))
  return list
})

function toggleRosterDropdown() {
  showRosterDropdown.value = !showRosterDropdown.value
  showProjectDropdown.value = false
  if (showRosterDropdown.value) {
    rosterSearch.value = ''
    rosterFocusIdx.value = -1
    nextTick(() => rosterSearchRef.value?.focus())
  }
}

function onRosterSelect(s: Speaker) {
  rosterComposable.addMember(s.name)
  rosterSearch.value = ''
  rosterFocusIdx.value = -1
}

async function onRosterCreate() {
  const name = rosterSearch.value.trim()
  if (!name) return
  try {
    await createSpeaker(name)
    rosterComposable.addMember(name)
    rosterSearch.value = ''
    rosterFocusIdx.value = -1
  } catch (e) {
    console.error('create speaker failed:', e)
  }
}

function onRosterKeydown(e: KeyboardEvent) {
  const items = filteredRosterSpeakers.value
  const hasCreate = rosterSearch.value.trim() && items.length === 0
  const total = hasCreate ? 1 : items.length
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    rosterFocusIdx.value = total > 0 ? (rosterFocusIdx.value + 1) % total : 0
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    rosterFocusIdx.value = total > 0 ? (rosterFocusIdx.value <= 0 ? total - 1 : rosterFocusIdx.value - 1) : 0
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (hasCreate && rosterFocusIdx.value === 0) onRosterCreate()
    else if (rosterFocusIdx.value >= 0 && rosterFocusIdx.value < items.length) onRosterSelect(items[rosterFocusIdx.value])
  } else if (e.key === 'Escape') {
    e.preventDefault()
    showRosterDropdown.value = false
  }
}

// 说话人 / Speakers
const speakers = ref<Speaker[]>([])
const bindSearch = ref('')
const bindPopover = ref<{ visible: boolean; asrId: number | null; style: Record<string, string> }>({ visible: false, asrId: null, style: {} })
const realtimeSpeakerBindings = ref<Record<number, string>>({})
const speakerCountUpdated = ref(false)
let speakerCountFlashTimer: ReturnType<typeof setTimeout> | null = null

// 章节展开 / Chapter expansion
const recExpandedChapters = reactive(new Set<number>())
const recAutoExpandedCount = ref(0)

// 洞察台 / Insight Deck
const insights = useAiInsights()
const actedActions = reactive<Record<string, boolean>>({})
const insightsExpanded = ref(false)

// 结束/放弃 / End/Abandon
const ending = ref(false)
const stopFailed = ref(false)
const stopErrorMsg = ref('')
const showAbandon = ref(false)
useEscClose(showAbandon, () => { showAbandon.value = false })

// 弹出菜单 / Popover menu
const recMoreBtn = ref<HTMLElement | null>(null)
const recDropdown = ref<HTMLElement | null>(null)
const { visible: showRecMore, toggle: toggleRecMore, close: closeRecMore, triggerAttrs: recMoreTriggerAttrs, menuAttrs: recMoreMenuAttrs } = usePopMenu(recDropdown, recMoreBtn)

// ── 计算属性 / Computed ──
const displaySpeakerCount = computed(() => ws.speakerCount.value > 0 ? ws.speakerCount.value : new Set(wsLines.value.map(l => l.speaker_id)).size)
const compressedCount = computed(() => markerMode.value ? wsLines.value.length - wsLines.value.filter((_, i) => notes.notesByLine.value[i] !== undefined).length : 0)

function hasNoteAt(idx: number): boolean { return notes.notesByLine.value[idx] !== undefined }

function getSpeakerDisplayName(line: TranscriptLine): string {
  const binding = realtimeSpeakerBindings.value[line.speaker_id]
  if (binding) {
    const spk = speakers.value.find(s => s.id === binding)
    // REQ-SPK-RN：存量占位档案名同样收敛（H1），未绑定态走中性文案无编号
    if (spk) return normalizeSpeakerName(spk.name) || t('recording.speaker.default_name')
  }
  const ln = normalizeSpeakerName(line.speaker_name)
  if (ln) return ln
  return t('recording.speaker.default_name')
}

function isMeSpeaker(speakerId: number): boolean {
  const binding = realtimeSpeakerBindings.value[speakerId]
  if (!binding) return false
  const spk = speakers.value.find(s => s.id === binding)
  return !!spk?.linked_user_id && !!userStore.user?.id && spk.linked_user_id === userStore.user.id
}

// ── 章节起始映射（预计算，避免模板内重复调用） / Chapter start mapping (precomputed) ──
const chapterStartMap = computed(() => {
  const map = new Map<number, { title: string; chapterIdx: number }>()
  if (wsChapters.value.length === 0 || wsLines.value.length === 0) return map
  for (let i = 0; i < wsLines.value.length; i++) {
    const line = wsLines.value[i]
    if (!line?.begin_time) continue
    for (let c = wsChapters.value.length - 1; c >= 0; c--) {
      const ch = wsChapters.value[c]
      if (line.begin_time >= ch.start_ms) {
        if (i === 0 || (wsLines.value[i - 1]?.begin_time ?? 0) < ch.start_ms) {
          map.set(i, { title: ch.title, chapterIdx: c })
        }
        break
      }
    }
  }
  return map
})

function toggleChapterExpand(idx: number) { recExpandedChapters.has(idx) ? recExpandedChapters.delete(idx) : recExpandedChapters.add(idx) }

// ── 操作回调 / Action callbacks ──
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

// 洞察台回调 / Insight Deck callbacks
function onInsightAction(msg: InsightMessage, act: InsightAction) {
  const key = msg.id + ':' + act.key
  if (actedActions[key]) return
  actedActions[key] = true
  // 确认消息：折叠卡片 + 切换为系统默认色系 / Acknowledge: collapse card + reset to default color
  insights.acknowledgeMessage(msg.id)
  // 差异化处理
  switch (act.key) {
    case 'adjust':
      recTab.value = 'transcript'
      break
    case 'generate':
      // 切换到洞察面板查看总结建议 / Switch to insights panel for summary suggestions
      recTab.value = 'insights'
      break
    case 'view':
      // 滚动到洞察面板查看消息详情 / Scroll to insights panel for message details
      recTab.value = 'insights'
      break
  }
}

// 【已退役】onInsightManualCheck：会中手动分析触发入口随「洞察共创 · 会话驱动」下线

// 存在性警告 / Presence warning
function onPresenceContinue() { presence.acknowledge(); ws.clearPresenceWarning() }
function onPresenceStop() { ws.clearPresenceWarning(); onStop() }

// 暂停/恢复 / Pause/Resume
async function onTogglePause() {
  try {
    if (recPaused.value) { const r = await recorder.resumeRecording() as any; if (r?.summary_resumed) ws.summaryPaused.value = false; ws.connect(taskId.value); taskStore.patchTaskLocal(taskId.value, { status: 'recording' }) }
    else { ws.disconnect(); const r = await recorder.pauseRecording() as any; if (r?.summary_paused) ws.summaryPaused.value = true; taskStore.patchTaskLocal(taskId.value, { status: 'paused' }) }
  } catch (e) { if (!recPaused.value && !ws.connected.value) ws.connect(taskId.value) }
}

// 结束录音 / End recording
async function onStop() {
  ending.value = true; stopFailed.value = false; ws.disconnect()
  translation.reset()    // 重置翻译状态 / Reset translation state
  try {
    const result = await recorder.stopRecording(notes.getNotesText())
    notes.clearStorage()
    await new Promise(r => setTimeout(r, 2000))
    await taskStore.loadTasks()
    const tid = result?.task_id || recorder.taskId.value
    if (tid) router.push({ name: 'generating', params: { taskId: tid } })
  } catch (e: unknown) {
    stopFailed.value = true
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    stopErrorMsg.value = err.response?.data?.detail || err.message || t('common.status.unknown_error')
  }
}

function onForceQuit() { ending.value = false; stopFailed.value = false; notes.clearStorage(); const tid = recorder.taskId.value; taskStore.loadTasks().then(() => { if (tid) router.push({ name: 'generating', params: { taskId: tid } }); else router.push('/') }) }

async function onAbandon() { showAbandon.value = false; ws.disconnect(); notes.clearStorage(); await recorder.abandonRecording(); await taskStore.loadTasks(); router.push('/') }

// ── Watchers ── / ── Watchers ──
watch(() => wsChapters.value.length, (n) => { for (let c = recAutoExpandedCount.value; c < n; c++) recExpandedChapters.add(c); recAutoExpandedCount.value = n })
// 【已退役】洞察台定时自动触发（watch wsLines.length → maybeAutoAnalyze）随「洞察共创 · 会话驱动」下线：
// 洞察生成/修订改由会话面板中人与 AI 共创驱动，不再由时钟无人值守触发。
watch(() => ws.speakerCount.value, (n, o) => { if (n > o && n > 0) { speakerCountUpdated.value = true; if (speakerCountFlashTimer) clearTimeout(speakerCountFlashTimer); speakerCountFlashTimer = setTimeout(() => speakerCountUpdated.value = false, 2000) } })
watch(recPaused, (p) => { if (p && ws.connected.value) ws.disconnect(); else if (!p && !ws.connected.value && taskId.value) ws.connect(taskId.value) })
watch(recTab, (tab) => {
  localStorage.setItem('oms_rec_active_tab', tab)
  ;(window as any).__omsUpdatePhilosophy?.(tab)
})
watch(noteText, () => { nextTick(() => { const el = notesBarRef.value?.textareaRef; if (!el) return; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' }) })

// ── 生命周期 / Lifecycle ──
onMounted(async () => {
  const saved = localStorage.getItem('oms_rec_active_tab')
  if (saved === 'transcript' || saved === 'insights') recTab.value = saved
  fetchProjects().then(l => { projects.value = l }).catch(() => {})
  ws.onSpeakerBound((id: number, uuid: string) => { realtimeSpeakerBindings.value[id] = uuid })
  // 注册翻译回调 / Register translation callbacks
  ws.onTranslationUpdate(translation.handleTranslationUpdate)
  ws.onTranslationStatus(translation.handleTranslationStatus)
  translation.loadPreferences()
  presence.start()
  const tid = taskId.value
  // [状态同步] 进入录音页即绑定当前会议：新建录音的成功路径只做了乐观更新 + 路由跳转，
  // 未调用 selectTask，导致右侧 AI 会话面板（依 currentTaskId 建立会话/注入上下文）没有路由到正在录制的会议。
  // 在挂载时统一绑定，覆盖新建录音 / 刷新 / 直达 URL / 侧栏进入等所有路径。
  // Bind the current task on mount so the AI chat panel routes to the recording meeting on every entry path.
  if (tid) taskStore.selectTask(tid)
  if (tid) { recorder.taskId.value = tid; await recorder.checkStatus(); ws.connect(tid); try { speakers.value = await fetchSpeakers() } catch {}; notes.restoreFromStorage() }
  document.addEventListener('keydown', onKeydown)
  // 绑定当前会议，加载已有洞察消息 / Bind current task, load existing insights
  await insights.setCurrentTask(taskId.value)
})

onUnmounted(() => {
  presence.stop(); ws.disconnect()
  if (speakerCountFlashTimer) clearTimeout(speakerCountFlashTimer)
  document.removeEventListener('keydown', onKeydown)
})

// 说话人绑定弹窗的「点击外部关闭」已由 RecSpeakerBind 内 useDropdownPopup 统一接管
// Click-outside close for the speaker-bind popover is handled by useDropdownPopup inside RecSpeakerBind
function onKeydown(e: KeyboardEvent) { if (e.key === 'Escape' && isFocusMode.value) onFocusMode() }

</script>

<style scoped>
/* 转写行气泡样式已迁移至 recording-view.css 全局样式 / Transcript bubble styles migrated to recording-view.css global styles */
</style>
