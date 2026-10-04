/**
 * 会议纪要页核心数据层 / Meeting summary page core data layer
 *
 * 管理任务数据、章节、转写原文、元信息、Tab 切换、工具栏操作、轮询及生命周期。 / Manages task data, chapters, transcript, metadata, tab switching, toolbar actions, polling, and lifecycle.
 */
import { ref, computed, onMounted, onUnmounted, watch, reactive, nextTick, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { usePlayerStore } from '@/stores/player'
import { useLayoutStore } from '@/stores/layout'
import { usePolling } from '@/composables/usePolling'
import { fetchTask, updateTask } from '@/api/tasks'
import { fetchNotes, fetchTodos } from '@/api/notes'
import { fetchSpeakers, type Speaker } from '@/api/speakers'
import { fetchProjects, createProject, type Project } from '@/api/projects'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useAiInsights } from '@/composables/useAiInsights'
import { showToast } from '@/composables/useToast'
import type { DialogueLine, TodoItem, Chapter, FlatTranscriptLine, Task } from '@/api/types'

export function useGeneratingData(
  transcriptPanelRef: Ref<any>,
  summaryPanelRef: Ref<any>,
  notesPanelRef: Ref<any>,
) {
  const { t } = useI18n()
  const route = useRoute()
  const taskStore = useTaskStore()
  const player = usePlayerStore()
  const insightsStore = useAiInsights()
  const taskId = route.params.taskId as string

  // ─── 任务核心 / Task core ───
  const task = computed(() => taskStore.tasks.find(t => t.task_id === taskId) ?? null)
  const dialogue = computed<DialogueLine[]>(() => task.value?.dialogue ?? [])
  // 失败态守卫：避免 <audio> 加载 /api/audio/{id} 触发 404 / Failed-state guard: prevent <audio> from hitting /api/audio/{id} 404
  const isFailed = computed(() => task.value?.status === 'failed')
  const audioUrl = computed(() => (task.value && !isFailed.value) ? `/api/audio/${task.value.task_id}` : '')
  const chapters = computed<Chapter[]>(() => task.value?.chapters ?? [])

  // ─── AC-4 云端回退标志（QA-R1 DEF-04） / AC-4 cloud-fallback flags ───
  // can_fallback_cloud 仅在本地引擎失败路径由后端落盘；其他失败类别不渲染回退 UI。
  // can_fallback_cloud is persisted by backend only on the local-engine failure path; no fallback UI otherwise.
  const isLocalEngineFailure = computed(() => isFailed.value && task.value?.error_category === 'local_engine')
  /** True ⇒ 渲染「切云端重试」+ 显式确认；False ⇒ 置灰 + 纯内网原因说明 */
  const canFallbackCloud = computed(() => isLocalEngineFailure.value && task.value?.can_fallback_cloud === true)
  const cloudFallbackBlocked = computed(() => isLocalEngineFailure.value && task.value?.can_fallback_cloud !== true)

  // ─── 失败信息分类（与 TaskCard.vue 保持一致） / Failure info categorization (consistent with TaskCard.vue) ───
  // 注：纪要页失败态仅提供「重试转写 + 返回会议库」两个通用操作，不按 source 区分「重新录制/重新上传」，
  // 与侧边栏 TaskCard 的差异化操作按钮保持语义分工（侧边栏快捷操作 vs 纪要页详细展示）。
  // Note: the generating-view failure card only exposes universal "retry + back to library" actions,
  // differing from TaskCard's source-aware shortcuts (sidebar quick actions vs detail view).
  const failureInfo = computed(() => {
    const category = task.value?.error_category
    const errorText = task.value?.error || t('task.failure.unknown')
    const suggestion = task.value?.error_suggestion || ''

    switch (category) {
      case 'transient':
        return {
          icon: 'refresh' as const,
          iconClass: 'is-transient',
          message: t('task.failure.transient'),
          suggestion,
          rawError: errorText,
        }
      case 'api_config':
        return {
          icon: 'settings' as const,
          iconClass: 'is-api-config',
          message: t('task.failure.api_config'),
          suggestion,
          rawError: errorText,
        }
      case 'local_engine':
        return {
          icon: 'settings' as const,
          iconClass: 'is-api-config',
          message: t('task.failure.local_engine'),
          suggestion,
          rawError: errorText,
        }
      case 'audio': {
        // 细分：无有效语音 vs 其他音频问题 / Subcategory: no valid speech vs other audio issues
        const lower = errorText.toLowerCase()
        if (lower.includes('no_valid_fragment') || lower.includes('no valid fragment')) {
          return {
            icon: 'audio' as const,
            iconClass: 'is-audio',
            message: t('task.failure.no_speech'),
            suggestion: suggestion || t('task.failure.no_speech_hint'),
            rawError: errorText,
          }
        }
        return {
          icon: 'audio' as const,
          iconClass: 'is-audio',
          message: t('task.failure.audio'),
          suggestion,
          rawError: errorText,
        }
      }
      default:
        return {
          icon: 'alert' as const,
          iconClass: 'is-unknown',
          message: errorText,
          suggestion,
          rawError: errorText,
        }
    }
  })

  // ─── 转写原文 / Transcript ───
  const flatTranscript = computed<FlatTranscriptLine[]>(() => {
    const all: FlatTranscriptLine[] = []
    for (const d of dialogue.value) {
      if (!d.sentences) continue
      for (const s of d.sentences) {
        all.push({
          begin_time: s.begin_time, end_time: s.end_time, text: s.text,
          speaker_id: s.speaker_id, sentence_id: s.sentence_id,
          // 清理层为响应级富化字段，仅在后端实际挂键时透传 / Cleanup layer passes through only when present
          ...(typeof s.clean_text === 'string'
            ? { clean_text: s.clean_text, ...(Array.isArray(s.clean_ops) ? { clean_ops: s.clean_ops } : {}) }
            : {}),
        })
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

  // ─── 章节状态 / Chapter state ───
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

  // ─── Tab 切换 / Tab switching ───
  const TAB_IDS = ['transcript', 'notes', 'summary', 'todos', 'insights'] as const
  const TABS = computed(() => [
    { id: 'transcript', label: t('generating.tabs.transcript'), icon: '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/>' },
    { id: 'notes', label: t('generating.tabs.notes'), icon: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>' },
    { id: 'summary', label: t('generating.tabs.summary'), icon: '<path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="13" y2="16"/>' },
    { id: 'todos', label: t('generating.tabs.todos'), icon: '<polyline points="9,11 12,14 22,4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>' },
    { id: 'insights', label: t('generating.tabs.insights'), icon: '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 00-4 11.3c.6.5 1 1.3 1 2.2h6c0-.9.4-1.7 1-2.2A7 7 0 0012 2z"/>' },
  ])

  const activeTab = ref('transcript')

  function switchTab(tabId: string) {
    activeTab.value = tabId
    localStorage.setItem('oms_gen_active_tab', tabId)
    ;(window as any).__omsUpdatePhilosophy?.(tabId)
  }

  // ─── 消费 AI 面板/侧栏的 Tab 切换信号（immediate：跨页导航时新挂载也能消费到预先置入的信号）
  // Consume AI panel / sidebar tab-switch signal; immediate so a pre-set signal survives fresh mounts
  const layoutStore = useLayoutStore()
  watch(() => layoutStore.pendingGenTab, (tab) => {
    if (tab) {
      switchTab(tab)
      layoutStore.pendingGenTab = null
    }
  }, { immediate: true })

  function dotClass(tabId: string): string {
    if (!task.value) return ''
    if (tabId === 'transcript' && flatTranscript.value.length > 0) return 'is-done'
    if (tabId === 'summary' && task.value.summary) return 'is-done'
    if (tabId === 'todos' && todos.value.length > 0) return 'is-done'
    // insights 圆点不再看旧洞察消息：Tab 内容已统一为洞察板 HTML 产物，
    // 有板才亮（由 GeneratingView 依据 board artifact 合并判断）
    return ''
  }

  // ─── 元信息 / Metadata ───
  const metaDateShort = computed(() => task.value?.meeting_date || task.value?.created_at?.slice(0, 10) || '')
  const metaDuration = computed(() => {
    const sec = task.value?.audio_duration
    if (!sec || sec <= 0) return '00:00'
    const m = Math.floor(sec / 60), s = Math.floor(sec % 60)
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  })

  // ─── 面包屑 / Breadcrumb ───
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

  // ─── 工具栏操作 / Toolbar actions ───
  // 失败态守卫：output_path/summary 均为空，调用后端会返回 404，直接拦截避免用户看到原始 JSON
  // Failed-state guard: output_path/summary are null; backend would return 404, intercept to avoid raw JSON
  function onCopy() {
    if (isFailed.value) return
    const md = summaryMd.value || task.value?.summary
    if (md) navigator.clipboard.writeText(md)
  }
  function onExport() {
    if (isFailed.value) return
    window.open(`/api/download/${taskId}`, '_blank')
  }
  function onFullscreen() {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen()
    else document.exitFullscreen()
  }

  // ─── 随记 & 待办 / Notes & Todos ───
  const notesContent = ref('')
  const notesSaved = ref(false)
  const summaryMd = ref('')
  const todos = ref<TodoItem[]>([])

  watch(() => task.value, (t) => {
    if (t) {
      const us = (t as any).user_summary
      summaryMd.value = us != null ? us : (t.summary || '')
    }
  }, { immediate: true })

  async function loadNotes() { notesContent.value = await fetchNotes(taskId) }
  async function loadTodos() { todos.value = await fetchTodos(taskId) }

  // ─── 音频 / Audio ───
  watch(audioUrl, (url) => { if (url) player.load(taskId, url) }, { immediate: true })

  function seekAudio(e: MouseEvent) {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    player.seekPercent(((e.clientX - rect.left) / rect.width) * 100)
  }

  // ─── 项目关联 / Project association ───
  const projects = ref<Project[]>([])
  const showProjectDropdown = ref(false)

  // ─── 知识库检索 + 就地新建 / KB search + inline create ───
  const kbSearchQuery = ref('')
  const showKbCreateInput = ref(false)
  const kbCreateName = ref('')

  const filteredProjects = computed(() => {
    const q = kbSearchQuery.value.trim().toLowerCase()
    if (!q) return projects.value
    return projects.value.filter(p => p.name.toLowerCase().includes(q))
  })

  async function onSelectProject(projectId: string) {
    showProjectDropdown.value = false
    kbSearchQuery.value = ''
    showKbCreateInput.value = false
    kbCreateName.value = ''
    try {
      await updateTask(taskId, { project_id: projectId || undefined })
      taskStore.patchTaskLocal(taskId, { project_id: projectId || null })
    } catch (e) { console.error('update project link failed:', e) }
  }

  async function createAndLinkKb() {
    const name = kbCreateName.value.trim() || kbSearchQuery.value.trim()
    if (!name) {
      showToast(t('generating.errors.kb_name_empty'), 'error')
      return
    }
    try {
      const newProject = await createProject(name)
      // 追加到列表供后续选择 / Append to list for future selection
      projects.value.push(newProject)
      // 走与 onSelectProject 相同的持久化路径 / Same persistence path as onSelectProject
      await updateTask(taskId, { project_id: newProject.id })
      taskStore.patchTaskLocal(taskId, { project_id: newProject.id })
      // 关闭下拉、清理状态 / Close dropdown, clean up state
      showProjectDropdown.value = false
      kbSearchQuery.value = ''
      showKbCreateInput.value = false
      kbCreateName.value = ''
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || t('generating.errors.kb_create_failed')
      showToast(detail, 'error')
      // 保留输入框可编辑重试 / Keep input editable for retry
    }
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

  // ─── 轮询 / Polling ───
  /** 产物待刷新标记：生成完成时若用户正停留在随记页，推迟到离开该页再拉取，
      避免覆盖正在输入的内容 / Artifacts pending refresh — deferred while the user
      is on the notes tab so in-flight typing is never overwritten. */
  const artifactsStale = ref(false)

  const { start: startPolling, stop: stopPolling } = usePolling(async () => {
    const updated = await fetchTask(taskId)
    taskStore.patchTaskLocal(taskId, updated)
    if (updated.status === 'completed') { stopPolling(); onPipelineCompleted(updated) }
    else if (updated.status === 'failed') { stopPolling() }
  }, 3000)

  // 章节补生成轮询：最多 MAX_CHAPTER_POLLS 次，避免空转写任务无限轮询
  // Chapter backfill polling: capped at MAX_CHAPTER_POLLS to avoid infinite polling for empty transcripts.
  let chapterPollCount = 0
  const MAX_CHAPTER_POLLS = 20
  const { start: startChapterPolling, stop: stopChapterPolling } = usePolling(async () => {
    const updated = await fetchTask(taskId)
    taskStore.patchTaskLocal(taskId, updated)
    if (updated.chapters?.length) { stopChapterPolling(); return }
    chapterPollCount++
    if (chapterPollCount >= MAX_CHAPTER_POLLS) {
      stopChapterPolling()
      console.warn('[chapters] 补生成轮询达到上限，停止')
    }
  }, 3000)

  /**
   * 就地切换到完成态。原先这里是一句 window.location.reload()：
   * 整页重载会丢掉滚动位置与未保存的编辑草稿，几百毫秒白屏也被用户读作「崩溃」。
   * 改为：显式成功反馈 + 拉取新生成的随记/待办 + 补起章节轮询。
   * Switch to the completed state in place. The previous blanket reload threw away
   * scroll position and unsaved drafts, and its white flash read as a crash.
   */
  async function onPipelineCompleted(updated: Task) {
    showToast(t('generating.pipeline.completed'), 'success')
    if (!updated.chapters?.length && (updated.dialogue?.length ?? 0) > 0) startChapterPolling()
    if (todos.value.length === 0) { try { await loadTodos() } catch { /* 保留空态 */ } }
    if (activeTab.value !== 'notes') {
      try { await loadNotes() } catch { /* 保留空态 */ }
    } else {
      artifactsStale.value = true
    }
  }

  // 完成时用户正在写随记 → 离开随记页那一刻再刷新产物
  // Deferred artifact refresh: the user was editing notes when generation finished.
  watch(activeTab, (tab, prev) => {
    if (artifactsStale.value && prev === 'notes' && tab !== 'notes') {
      artifactsStale.value = false
      loadNotes().catch(() => { /* */ })
    }
  })

  // ─── AI 引用 / AI quote ───
  // 插入纪要/随记已下架（2026-09）：仅保留划词改写的块更新器
  const { setQuote, startRewrite, rewritePending, registerBlockUpdater } = useQuoteRef()

  // ─── 说话人列表 / Speaker list ───
  const speakers = ref<Speaker[]>([])

  // ─── 归档 / Archive ───
  const showArchiveDialog = ref(false)
  const isArchived = computed(() => !!task.value?.archived_at)

  async function onArchive() {
    showArchiveDialog.value = false
    try {
      if (isArchived.value) {
        await taskStore.unarchiveTask(taskId)
      } else {
        await taskStore.archiveTask(taskId)
      }
    } catch (e) {
      console.error('archive/unarchive failed:', e)
    }
  }

  // ─── 删除 / Delete ───
  const showDeleteDialog = ref(false)

  // ─── 生命周期 / Lifecycle ───
  onMounted(async () => {
    // 进入会议页即清除「已完成待查看」角标（REQ-TRANSCRIBE-PROGRESS R2 站内提醒闭环）
    taskStore.clearCompletedUnseen(taskId)
    // 洞察台：绑定当前会议并加载历史洞察（REQ-INSIGHT-DECK-POSTMEETING R1 会后回看）
    // Insight Deck: bind this meeting and load persisted insights (post-meeting review)
    void insightsStore.setCurrentTask(taskId)
    const saved = localStorage.getItem('oms_gen_active_tab')
    if (saved && (TAB_IDS as readonly string[]).includes(saved)) activeTab.value = saved

    try { const t = await fetchTask(taskId); taskStore.patchTaskLocal(taskId, t) } catch { /* */ }
    taskStore.selectTask(taskId)
    if (task.value && !['completed', 'failed'].includes(task.value.status)) startPolling()
    // 仅当 completed 且 chapters 为空、但 dialogue 非空时才轮询补生成；
    // dialogue 为空（空转写）时补生成永远不会成功，直接跳过轮询，由空态 UI 接管。
    // Only poll when completed with empty chapters but non-empty dialogue; skip for empty transcripts.
    if (task.value?.status === 'completed' && !task.value?.chapters?.length && (task.value?.dialogue?.length ?? 0) > 0) startChapterPolling()
    try { speakers.value = await fetchSpeakers() } catch { /* */ }
    try { projects.value = await fetchProjects() } catch { /* */ }

    // AI 引用注册 / AI quote registration
    registerBlockUpdater((blockIndex: number, newSource: string) => {
      const source = rewritePending.value?.source || '纪要'
      if (source === '随记' && notesPanelRef.value) notesPanelRef.value.updateBlock(blockIndex, newSource)
      else if (summaryPanelRef.value) summaryPanelRef.value.updateBlock(blockIndex, newSource)
    })
  })

  onUnmounted(() => { stopPolling(); stopChapterPolling() })

  return {
    // 任务核心 / Task core
    taskId, task, dialogue, audioUrl, chapters, flatTranscript, transcriptItems,
    getChapterIdxAtTime,
    // 失败态 / Failed state
    isFailed, failureInfo,
    // AC-4 云端回退（QA-R1 DEF-04） / AC-4 cloud fallback
    isLocalEngineFailure, canFallbackCloud, cloudFallbackBlocked,
    // 章节 / Chapters
    visibleChapterIndices, activeChapterIdx, expandedChapters, summaryExpandedChapters,
    toggleChapterExpand, toggleSummaryChapter, scrollToChapter, toggleChapterTranscript,
    showAllChapters, allChaptersVisible,
    // Tab
    TABS, activeTab, switchTab, dotClass,
    // 元信息 / Metadata
    metaDateShort, metaDuration, breadcrumbTitle, computeBreadcrumbs, computeCurrentProjectName,
    // 工具栏 / Toolbar
    onCopy, onExport, onFullscreen,
    // 随记 & 待办 / Notes & Todos
    notesContent, notesSaved, summaryMd, todos, loadNotes, loadTodos,
    // 音频 / Audio
    player, seekAudio,
    // 项目 / Project
    projects, showProjectDropdown, onSelectProject, openDatePicker,
    kbSearchQuery, filteredProjects, showKbCreateInput, kbCreateName, createAndLinkKb,
    // 轮询 / Polling
    startPolling, stopPolling,
    // AI 引用 / AI quote
    setQuote, startRewrite, rewritePending, registerBlockUpdater,
    // 说话人 / Speakers
    speakers,
    // 归档 / Archive
    showArchiveDialog, onArchive, isArchived,
    // 删除 / Delete
    showDeleteDialog,
  }
}
