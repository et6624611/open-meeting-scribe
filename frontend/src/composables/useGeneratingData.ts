/**
 * 会议纪要页核心数据层
 *
 * 管理任务数据、章节、转写原文、元信息、Tab 切换、工具栏操作、轮询及生命周期。
 */
import { ref, computed, onMounted, onUnmounted, watch, reactive, nextTick, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { usePlayerStore } from '@/stores/player'
import { usePolling } from '@/composables/usePolling'
import { fetchTask, updateTask } from '@/api/tasks'
import { fetchNotes, fetchTodos } from '@/api/notes'
import { fetchSpeakers, type Speaker } from '@/api/speakers'
import { fetchProjects, type Project } from '@/api/projects'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { getSpeakerColor } from '@/utils/speakerColors'
import type { DialogueLine, TodoItem, Chapter, FlatTranscriptLine } from '@/api/types'

export function useGeneratingData(
  transcriptPanelRef: Ref<any>,
  summaryPanelRef: Ref<any>,
  notesPanelRef: Ref<any>,
) {
  const { t } = useI18n()
  const route = useRoute()
  const taskStore = useTaskStore()
  const player = usePlayerStore()
  const taskId = route.params.taskId as string

  // ─── 任务核心 ───
  const task = computed(() => taskStore.tasks.find(t => t.task_id === taskId) ?? null)
  const dialogue = computed<DialogueLine[]>(() => task.value?.dialogue ?? [])
  const audioUrl = computed(() => task.value ? `/api/audio/${task.value.task_id}` : '')
  const chapters = computed<Chapter[]>(() => task.value?.chapters ?? [])

  // ─── 转写原文 ───
  const flatTranscript = computed<FlatTranscriptLine[]>(() => {
    const all: FlatTranscriptLine[] = []
    for (const d of dialogue.value) {
      if (!d.sentences) continue
      for (const s of d.sentences) {
        all.push({ begin_time: s.begin_time, end_time: s.end_time, text: s.text, speaker_id: s.speaker_id, sentence_id: s.sentence_id })
      }
    }
    all.sort((a, b) => a.begin_time - b.begin_time)
    return all
  })

  type TranscriptItem = { type: 'chapter'; chapterIdx: number } | { type: 'line'; lineIdx: number }

  const transcriptItems = computed<TranscriptItem[]>(() => {
    const items: TranscriptItem[] = []
    const lines = flatTranscript.value
    if (!lines.length) return items
    const chs = chapters.value
    let lastChIdx = -2
    for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
      const lineMs = lines[lineIdx].begin_time
      const chIdx = getChapterIdxAtTime(chs, lineMs)
      if (chs.length > 0 && chIdx !== lastChIdx && chIdx >= 0) {
        items.push({ type: 'chapter', chapterIdx: chIdx })
        lastChIdx = chIdx
      }
      items.push({ type: 'line', lineIdx })
    }
    return items
  })

  function getChapterIdxAtTime(chs: Chapter[], ms: number): number {
    for (let i = chs.length - 1; i >= 0; i--) {
      if (ms >= chs[i].start_ms) return i
    }
    return -1
  }

  // ─── 章节状态 ───
  const visibleChapterIndices = reactive(new Set<number>())
  const activeChapterIdx = ref(0)
  const expandedChapters = reactive(new Set<number>())
  const summaryExpandedChapters = reactive(new Set<number>())

  watch(chapters, (chs) => {
    if (chs.length > 0 && visibleChapterIndices.size === 0) {
      chs.forEach((_, idx) => visibleChapterIndices.add(idx))
    }
  }, { immediate: true })

  function toggleChapterExpand(idx: number) {
    if (expandedChapters.has(idx)) expandedChapters.delete(idx)
    else expandedChapters.add(idx)
  }

  function toggleSummaryChapter(idx: number) {
    if (summaryExpandedChapters.has(idx)) summaryExpandedChapters.delete(idx)
    else summaryExpandedChapters.add(idx)
  }

  function scrollToChapter(idx: number) {
    activeChapterIdx.value = idx
    nextTick(() => {
      const el = transcriptPanelRef.value?.transcriptListEl?.querySelector(`.chapter-divider[data-chapter="${idx}"]`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  function toggleChapterTranscript(idx: number) {
    if (idx < 0) return
    if (visibleChapterIndices.has(idx)) visibleChapterIndices.delete(idx)
    else visibleChapterIndices.add(idx)
    nextTick(() => {
      const el = transcriptPanelRef.value?.transcriptListEl?.querySelector(`.chapter-divider[data-chapter="${idx}"]`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  function showAllChapters() { chapters.value.forEach((_, idx) => visibleChapterIndices.add(idx)) }

  const allChaptersVisible = computed(() => {
    if (chapters.value.length === 0) return true
    return visibleChapterIndices.size === chapters.value.length
  })

  // ─── Tab 切换 ───
  const TABS = computed(() => [
    { id: 'transcript', label: t('generating.tabs.transcript'), icon: '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/>' },
    { id: 'notes', label: t('generating.tabs.notes'), icon: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>' },
    { id: 'summary', label: t('generating.tabs.summary'), icon: '<path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="13" y2="16"/>' },
    { id: 'todos', label: t('generating.tabs.todos'), icon: '<polyline points="9,11 12,14 22,4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>' },
  ])

  const activeTab = ref('transcript')

  function switchTab(tabId: string) {
    activeTab.value = tabId
    localStorage.setItem('oms_gen_active_tab', tabId)
  }

  function dotClass(tabId: string): string {
    if (!task.value) return ''
    if (tabId === 'summary' && task.value.summary) return 'is-done'
    if (tabId === 'todos' && todos.value.length > 0) return 'is-done'
    return ''
  }

  // ─── 元信息 ───
  const metaDateShort = computed(() => task.value?.meeting_date || task.value?.created_at?.slice(0, 10) || '')
  const metaDuration = computed(() => {
    const sec = task.value?.audio_duration
    if (!sec || sec <= 0) return '00:00'
    const m = Math.floor(sec / 60), s = Math.floor(sec % 60)
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  })

  // speakerStats 需要 speakers 和 currentBindingMapping，由外部注入
  function computeSpeakerStats(speakers: Speaker[], currentBindingMapping: Record<number, string>) {
    const mapping = task.value?.speaker_mapping
    if (!mapping) return []
    const lines = flatTranscript.value
    if (!lines.length) return []
    const totalMs = lines.reduce((sum, l) => sum + (l.end_time - l.begin_time), 0)
    if (totalMs <= 0) return []
    const speakerIds = Object.keys(mapping).sort((a, b) => Number(a) - Number(b))
    return speakerIds.map((sid) => {
      const sidNum = Number(sid)
      const uuid = currentBindingMapping[sidNum]
      const boundSpk = uuid ? speakers.find(s => s.id === uuid) : null
      const name = boundSpk?.name || mapping[sid] || t('generating.speaker_default', { id: sidNum + 1 })
      const durMs = lines.filter(l => String(l.speaker_id) === sid)
        .reduce((sum, l) => sum + (l.end_time - l.begin_time), 0)
      const pct = Math.round((durMs / totalMs) * 100)
      return { name, pct, color: getSpeakerColor(sid) }
    })
  }

  // ─── 面包屑 ───
  const breadcrumbTitle = computed(() => task.value?.title || task.value?.audio_name || t('generating.breadcrumb.default_title'))

  function computeBreadcrumbs(projects: Project[]) {
    const pid = task.value?.project_id
    const proj = pid ? projects.find(p => p.id === pid) : null
    if (proj) {
      return [
        { label: t('generating.breadcrumb.project'), icon: 'folder' as const, to: { name: 'projects' } },
        { label: proj.name, icon: null, to: { name: 'projects' } },
      ]
    }
    return [{ label: t('generating.breadcrumb.library'), icon: 'list' as const, to: { name: 'library' } }]
  }

  function computeCurrentProjectName(projects: Project[]) {
    if (!task.value?.project_id) return t('generating.meta.link_project')
    const p = projects.find(p => p.id === task.value?.project_id)
    return p?.name || t('generating.meta.link_project')
  }

  // ─── 工具栏操作 ───
  function onCopy() {
    const md = summaryMd.value || task.value?.summary
    if (md) navigator.clipboard.writeText(md)
  }
  function onExport() { window.open(`/api/download/${taskId}`, '_blank') }
  function onFullscreen() {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen()
    else document.exitFullscreen()
  }

  // ─── 随记 & 待办 ───
  const notesContent = ref('')
  const notesSaved = ref(false)
  const summaryMd = ref('')
  const todos = ref<TodoItem[]>([])

  watch(() => task.value?.summary, (s) => { if (s) summaryMd.value = s }, { immediate: true })

  async function loadNotes() { notesContent.value = await fetchNotes(taskId) }
  async function loadTodos() { todos.value = await fetchTodos(taskId) }

  // ─── 音频 ───
  watch(audioUrl, (url) => { if (url) player.load(taskId, url) }, { immediate: true })

  function seekAudio(e: MouseEvent) {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    player.seekPercent(((e.clientX - rect.left) / rect.width) * 100)
  }

  // ─── 项目关联 ───
  const projects = ref<Project[]>([])
  const showProjectDropdown = ref(false)

  async function onSelectProject(projectId: string) {
    showProjectDropdown.value = false
    try {
      await updateTask(taskId, { project_id: projectId || undefined })
      taskStore.patchTaskLocal(taskId, { project_id: projectId || null })
    } catch (e) { console.error('update project link failed:', e) }
  }

  function openDatePicker() {
    const input = document.createElement('input')
    input.type = 'date'
    input.value = task.value?.meeting_date || task.value?.created_at?.slice(0, 10) || new Date().toISOString().slice(0, 10)
    input.style.position = 'absolute'; input.style.opacity = '0'; input.style.pointerEvents = 'none'
    document.body.appendChild(input)
    input.showPicker?.()
    input.addEventListener('change', async () => {
      const newDate = input.value
      if (newDate && newDate !== (task.value?.meeting_date || task.value?.created_at?.slice(0, 10))) {
        try { await updateTask(taskId, { meeting_date: newDate }); taskStore.patchTaskLocal(taskId, { meeting_date: newDate }) }
        catch (e) { console.error('save date failed:', e) }
      }
      input.remove()
    })
    input.addEventListener('blur', () => { setTimeout(() => input.remove(), 200) })
  }

  // ─── 轮询 ───
  const { start: startPolling, stop: stopPolling } = usePolling(async () => {
    const updated = await fetchTask(taskId)
    taskStore.patchTaskLocal(taskId, updated)
    if (updated.status === 'completed') { stopPolling(); window.location.reload() }
    else if (updated.status === 'failed') { stopPolling() }
  }, 3000)

  const { start: startChapterPolling, stop: stopChapterPolling } = usePolling(async () => {
    const updated = await fetchTask(taskId)
    taskStore.patchTaskLocal(taskId, updated)
    if (updated.chapters?.length) stopChapterPolling()
  }, 3000)

  // ─── AI 引用 ───
  const { setQuote, startRewrite, rewritePending, registerBlockUpdater, registerSummaryAppender, registerNotesAppender } = useQuoteRef()

  // ─── 说话人列表 ───
  const speakers = ref<Speaker[]>([])

  // ─── 归档 ───
  const showArchiveDialog = ref(false)
  async function onArchive() {
    showArchiveDialog.value = false
    console.log('archive task:', taskId)
  }

  // ─── 生命周期 ───
  onMounted(async () => {
    const saved = localStorage.getItem('oms_gen_active_tab')
    if (saved) activeTab.value = saved

    try { const t = await fetchTask(taskId); taskStore.patchTaskLocal(taskId, t) } catch { /* */ }
    taskStore.selectTask(taskId)
    if (task.value && !['completed', 'failed'].includes(task.value.status)) startPolling()
    if (task.value?.status === 'completed' && !task.value?.chapters?.length) startChapterPolling()
    try { speakers.value = await fetchSpeakers() } catch { /* */ }
    try { projects.value = await fetchProjects() } catch { /* */ }

    // AI 引用注册
    registerBlockUpdater((blockIndex: number, newSource: string) => {
      const source = rewritePending.value?.source || '纪要'
      if (source === '随记' && notesPanelRef.value) notesPanelRef.value.updateBlock(blockIndex, newSource)
      else if (summaryPanelRef.value) summaryPanelRef.value.updateBlock(blockIndex, newSource)
    })
    registerSummaryAppender((markdown: string) => {
      const current = summaryMd.value
      summaryMd.value = current ? current + '\n\n' + markdown : markdown
    })
    registerNotesAppender((markdown: string) => {
      const current = notesContent.value
      notesContent.value = current ? current + '\n\n' + markdown : markdown
    })
  })

  onUnmounted(() => { stopPolling(); stopChapterPolling() })

  return {
    // 任务核心
    taskId, task, dialogue, audioUrl, chapters, flatTranscript, transcriptItems,
    getChapterIdxAtTime,
    // 章节
    visibleChapterIndices, activeChapterIdx, expandedChapters, summaryExpandedChapters,
    toggleChapterExpand, toggleSummaryChapter, scrollToChapter, toggleChapterTranscript,
    showAllChapters, allChaptersVisible,
    // Tab
    TABS, activeTab, switchTab, dotClass,
    // 元信息
    metaDateShort, metaDuration, computeSpeakerStats, breadcrumbTitle, computeBreadcrumbs, computeCurrentProjectName,
    // 工具栏
    onCopy, onExport, onFullscreen,
    // 随记 & 待办
    notesContent, notesSaved, summaryMd, todos, loadNotes, loadTodos,
    // 音频
    player, seekAudio,
    // 项目
    projects, showProjectDropdown, onSelectProject, openDatePicker,
    // 轮询
    startPolling, stopPolling,
    // AI 引用
    setQuote, startRewrite, rewritePending, registerBlockUpdater,
    // 说话人
    speakers,
    // 归档
    showArchiveDialog, onArchive,
  }
}
