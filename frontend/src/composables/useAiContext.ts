/**
 * useAiContext.ts — AI 面板上下文 Tab 数据管理 / AI panel context tab data management
 *
 * 从 AIPanel.vue 拆分而来，管理上下文 Tab 的本地状态： / Split from AIPanel.vue; manages local state for context tab:
 * 项目文件、相关会议、统计概览、分区折叠等。 / Project files, related meetings, stats overview, section collapsing, etc.
 */

import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useRealtimeStore } from '@/stores/realtime'
import { useLayoutStore } from '@/stores/layout'
import { showToast } from '@/composables/useToast'
import { fetchProjectDetail } from '@/api/projects'
import router from '@/router'

export function useAiContext() {
  const { t } = useI18n()
  const taskStore = useTaskStore()
  const layoutStore = useLayoutStore()
  const realtimeStore = useRealtimeStore()

  // ── 对话数据源（内联，原 useAiAnalysis 逻辑） / Dialogue data source (inlined, former useAiAnalysis logic) ──
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
    const SPAN = 600000 // 10 分钟 / 10 minutes
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

  // ── 本地状态 / Local state ──
  const linkedProject = ref<{ id: string; name: string; fileCount: number } | null>(null)
  const relatedMeetings = ref<Array<{ id: string; title: string; date: string; duration: string; tag: string }>>([])

  // ── 监听当前会议关联的知识库变化，加载知识库名称与关联会议 / Watch current task's linked knowledge base and load name + related meetings ──
  watch(
    () => taskStore.currentTask?.project_id ?? null,
    async (projectId) => {
      if (!projectId) {
        linkedProject.value = null
        relatedMeetings.value = []
        return
      }
      try {
        const detail = await fetchProjectDetail(projectId)
        linkedProject.value = {
          id: detail.id,
          name: detail.name,
          fileCount: detail.file_count || 0,
        }
        // 填充关联会议列表（排除当前会议自身） / Populate related meetings (exclude current task)
        const currentTaskId = taskStore.currentTask?.task_id
        relatedMeetings.value = (detail.meetings || [])
          .filter((m) => m.task_id !== currentTaskId && m.status === 'completed')
          .map((m) => ({
            id: m.task_id,
            title: m.title || '未命名会议',
            date: m.meeting_date || m.created_at?.slice(0, 10) || '',
            duration: m.audio_duration ? formatDuration(m.audio_duration) : '',
            tag: m.status === 'completed' ? '已完成' : m.status,
          }))
      } catch {
        linkedProject.value = null
        relatedMeetings.value = []
      }
    },
    { immediate: true },
  )
  const showAllMeetings = ref(false)

  const ctxSections = ref({
    meeting: true,
    files: true,
    related: true,
  })

  const MAX_VISIBLE_MEETINGS = 5

  // ── 随记 / Quick notes ──
  // task 快照本身携带 user_notes（/api/tasks 返回完整任务对象），无需额外回拉。
  // AI 侧三条读路径（工作区 context/notes.md、get_meeting_notes、问答注入块）已接入，
  // 上下文清单必须同步列出，否则展示层比实际能力少报一项。
  const notesText = computed(() => {
    const raw = (taskStore.currentTask as unknown as { user_notes?: string } | null)?.user_notes
    return typeof raw === 'string' ? raw.trim() : ''
  })
  const hasNotes = computed(() => notesText.value.length > 0)
  const notesCharCount = computed(() => notesText.value.length)

  // ── 计算属性 / Computed ──
  const visibleRelatedMeetings = computed(() =>
    showAllMeetings.value ? relatedMeetings.value : relatedMeetings.value.slice(0, MAX_VISIBLE_MEETINGS)
  )

  const contextStats = computed(() => ({
    transcript: taskStore.currentTask && dialogueLines.value.length > 0 ? 1 : 0,
    summary: taskStore.currentTask?.summary ? 1 : 0,
    notes: hasNotes.value ? 1 : 0,
    todos: todoStats.value?.total || 0,
    files: linkedProject.value ? 1 : 0,
  }))

  const contextResourceCount = computed(() =>
    contextStats.value.transcript +
    contextStats.value.summary +
    contextStats.value.notes +
    contextStats.value.todos +
    contextStats.value.files +
    relatedMeetings.value.length
  )

  const meetingOutputCount = computed(() =>
    contextStats.value.transcript + contextStats.value.summary +
    contextStats.value.notes + (contextStats.value.todos > 0 ? 1 : 0)
  )

  const relatedMeetingCount = computed(() => relatedMeetings.value.length)

  // 上下文归属的会议（currentTask 是全局选中态，在非会议页时用于向用户标明上下文来源）
  // The meeting the context belongs to; currentTask is global, so on other pages we show the source
  const contextSource = computed(() => {
    const task = taskStore.currentTask
    if (!task) return null
    return { taskId: task.task_id, title: task.title || t('ai-panel.context.source_untitled') }
  })

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
    contextStats.value.notes === 0 &&
    contextStats.value.todos === 0 &&
    !linkedProject.value &&
    relatedMeetings.value.length === 0
  )

  // ── 方法 / Methods ──
  function generateSummary(sendRaw: (text: string) => void, switchTab: (tab: string) => void) {
    sendRaw(t('ai-panel.context.action_generate_summary_text'))
    switchTab('chat')
  }

  function linkRelatedMeeting() {
    showToast(t('ai-panel.context.toast_link_meeting'), 'info')
  }

  function goToTranscript() {
    if (taskStore.currentTask?.task_id) {
      layoutStore.pendingGenTab = 'transcript'
    }
  }

  function goToSummary() {
    if (taskStore.currentTask?.task_id) {
      layoutStore.pendingGenTab = 'summary'
    }
  }

  function goToNotes() {
    if (taskStore.currentTask?.task_id) {
      layoutStore.pendingGenTab = 'notes'
    }
  }

  function goToTodos() {
    if (taskStore.currentTask?.task_id) {
      layoutStore.pendingGenTab = 'todos'
    }
  }

  function goToProject() {
    if (linkedProject.value) {
      router.push({ name: 'projects' })
    }
  }

  function goToMeeting(meetingId: string) {
    if (meetingId) {
      router.push({ name: 'generating', params: { taskId: meetingId } })
    }
  }

  function formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    if (mins < 60) return `${mins}分钟`
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return m > 0 ? `${h}小时${m}分钟` : `${h}小时`
  }

  return {
    // 状态 / State
    linkedProject,
    relatedMeetings,
    showAllMeetings,
    ctxSections,
    MAX_VISIBLE_MEETINGS,
    // 计算 / Computed
    visibleRelatedMeetings,
    contextStats,
    contextResourceCount,
    meetingOutputCount,
    relatedMeetingCount,
    contextSource,
    currentTaskDuration,
    speakerCount: speakerCountDisplay,
    chapterCount: chapterCountDisplay,
    hasSummary,
    hasNotes,
    notesCharCount,
    todoCount,
    todoPending,
    todoDone,
    isContextEmpty,
    // 方法 / Methods
    generateSummary,
    linkRelatedMeeting,
    goToTranscript,
    goToSummary,
    goToNotes,
    goToTodos,
    goToProject,
    goToMeeting,
  }
}
