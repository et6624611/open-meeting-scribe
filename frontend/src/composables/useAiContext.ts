/**
 * useAiContext.ts — AI 面板上下文 Tab 数据管理
 *
 * 从 AIPanel.vue 拆分而来，管理上下文 Tab 的本地状态：
 * 项目文件、相关会议、统计概览、分区折叠等。
 */

import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useRealtimeStore } from '@/stores/realtime'
import { showToast } from '@/composables/useToast'

export function useAiContext() {
  const { t } = useI18n()
  const taskStore = useTaskStore()
  const realtimeStore = useRealtimeStore()

  // ── 对话数据源（内联，原 useAiAnalysis 逻辑） ──
  const isRecording = computed(() => {
    const s = taskStore.currentTask?.status
    return s === 'recording' || s === 'paused'
  })

  const dialogueLines = computed(() => {
    if (isRecording.value && realtimeStore.entries.length > 0) {
      return realtimeStore.entries.map(e => ({
        begin_time: e.begin_time,
        speaker_id: e.speaker_id,
        text: e.text,
      }))
    }
    const all: Array<{ begin_time: number; speaker_id: number; text: string }> = []
    const dialogue = taskStore.currentTask?.dialogue ?? []
    for (const d of dialogue) {
      if (!d.sentences) continue
      for (const s of d.sentences) {
        all.push({ begin_time: s.begin_time, speaker_id: s.speaker_id, text: s.text })
      }
    }
    all.sort((a, b) => a.begin_time - b.begin_time)
    return all
  })

  const speakerCount = computed(() => {
    const lines = dialogueLines.value
    if (!lines.length) return 0
    return new Set(lines.map(d => d.speaker_id)).size
  })

  const chapterCount = computed(() => {
    const lines = dialogueLines.value
    if (!lines.length) return 0
    const SPAN = 600000 // 10 分钟
    let count = 1
    let chapterStart = lines[0].begin_time
    for (const d of lines) {
      if (d.begin_time - chapterStart >= SPAN) {
        count++
        chapterStart = d.begin_time
      }
    }
    return count
  })

  const todoStats = computed(() => {
    const t = taskStore.currentTask
    if (!t?.todos?.length) return null
    const total = t.todos.length
    const done = t.todos.filter(td => td.done).length
    return { total, done }
  })

  // ── 本地状态 ──
  const projectFiles = ref<Array<{ id: string; name: string; size: string; date: string; type: string }>>([])
  const relatedMeetings = ref<Array<{ id: string; title: string; date: string; duration: string; tag: string }>>([])
  const showAllFiles = ref(false)
  const showAllMeetings = ref(false)
  const heroDismissed = ref(localStorage.getItem('ctx_hero_dismissed') === '1')

  const ctxSections = ref({
    meeting: true,
    files: true,
    related: true,
  })

  const MAX_VISIBLE_FILES = 5
  const MAX_VISIBLE_MEETINGS = 5

  // ── 计算属性 ──
  const visibleProjectFiles = computed(() =>
    showAllFiles.value ? projectFiles.value : projectFiles.value.slice(0, MAX_VISIBLE_FILES)
  )

  const visibleRelatedMeetings = computed(() =>
    showAllMeetings.value ? relatedMeetings.value : relatedMeetings.value.slice(0, MAX_VISIBLE_MEETINGS)
  )

  const contextStats = computed(() => ({
    transcript: taskStore.currentTask && dialogueLines.value.length > 0 ? 1 : 0,
    summary: taskStore.currentTask?.summary ? 1 : 0,
    todos: todoStats.value?.total || 0,
    files: projectFiles.value.length,
  }))

  const contextResourceCount = computed(() =>
    contextStats.value.transcript +
    contextStats.value.summary +
    contextStats.value.todos +
    contextStats.value.files +
    relatedMeetings.value.length
  )

  const meetingOutputCount = computed(() =>
    contextStats.value.transcript + contextStats.value.summary + (contextStats.value.todos > 0 ? 1 : 0)
  )

  const projectFileCount = computed(() => projectFiles.value.length)
  const relatedMeetingCount = computed(() => relatedMeetings.value.length)

  const currentTaskDuration = computed(() => {
    const task = taskStore.currentTask
    if (!task?.audio_duration) return '—'
    const mins = Math.floor(task.audio_duration / 60)
    const secs = Math.floor(task.audio_duration % 60)
    return `${mins}min ${secs.toString().padStart(2, '0')}s`
  })

  const speakerCountDisplay = computed(() => speakerCount.value)
  const chapterCountDisplay = computed(() => chapterCount.value)
  const hasSummary = computed(() => !!taskStore.currentTask?.summary)
  const todoCount = computed(() => todoStats.value?.total || 0)
  const todoPending = computed(() => {
    const ts = todoStats.value
    return ts ? ts.total - ts.done : 0
  })
  const todoDone = computed(() => todoStats.value?.done || 0)

  const isContextEmpty = computed(() =>
    contextStats.value.transcript === 0 &&
    contextStats.value.summary === 0 &&
    contextStats.value.todos === 0 &&
    contextStats.value.files === 0 &&
    relatedMeetings.value.length === 0
  )

  // ── 方法 ──
  function dismissHero() {
    heroDismissed.value = true
    localStorage.setItem('ctx_hero_dismissed', '1')
  }

  function generateSummary(sendRaw: (text: string) => void, switchTab: (tab: string) => void) {
    sendRaw(t('ai-panel.context.action_generate_summary_text'))
    switchTab('chat')
  }

  function linkRelatedMeeting() {
    showToast(t('ai-panel.context.toast_link_meeting'), 'info')
  }

  function goToTranscript() {
    const task = taskStore.currentTask
    if (task?.task_id) {
      showToast(t('ai-panel.context.toast_transcript'), 'info')
    }
  }

  function goToSummary() {
    const task = taskStore.currentTask
    if (task?.task_id) {
      showToast(t('ai-panel.context.toast_summary'), 'info')
    }
  }

  function goToTodos() {
    const task = taskStore.currentTask
    if (task?.task_id) {
      showToast(t('ai-panel.context.toast_todos'), 'info')
    }
  }

  function addProjectFile() {
    showToast(t('ai-panel.context.toast_upload'), 'info')
  }

  return {
    // 状态
    projectFiles,
    relatedMeetings,
    showAllFiles,
    showAllMeetings,
    heroDismissed,
    ctxSections,
    MAX_VISIBLE_FILES,
    MAX_VISIBLE_MEETINGS,
    // 计算
    visibleProjectFiles,
    visibleRelatedMeetings,
    contextStats,
    contextResourceCount,
    meetingOutputCount,
    projectFileCount,
    relatedMeetingCount,
    currentTaskDuration,
    speakerCount: speakerCountDisplay,
    chapterCount: chapterCountDisplay,
    hasSummary,
    todoCount,
    todoPending,
    todoDone,
    isContextEmpty,
    // 方法
    dismissHero,
    generateSummary,
    linkRelatedMeeting,
    goToTranscript,
    goToSummary,
    goToTodos,
    addProjectFile,
  }
}
