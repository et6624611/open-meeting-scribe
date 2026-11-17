import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { showToast } from '@/composables/useToast'
import { downloadSummaryUrl, type SummaryFormat } from '@/api/tasks'
import { getSpeakerColor } from '@/utils/speakerColors'
import { isPlaceholderName } from '@/utils/speakerDisplay'
import { resolveSpeakerSeconds, speakerPct } from '@/utils/speakerShare'
import { highlightText } from '@/utils/search'
import type { Task, TaskStatus } from '@/api/types'

export interface SpeakerInfo {
  id: string
  name: string
  color: string
  duration: number
  pct: number
}

export function useLibrarySelection() {
  const router = useRouter()
  const { t } = useI18n()
  const taskStore = useTaskStore()

  // ─── Selection State ───
  const selectedIds = ref<Set<string>>(new Set())
  const lastSelectedId = ref<string | null>(null)

  // 响应式的 groupedTasks 注入入口（父组件 watch libGroupedTasks 后赋值）
  const groupedTasks = ref<Array<{ tasks: Task[] }>>([])

  const allVisibleIds = computed(() => {
    const ids: string[] = []
    for (const group of groupedTasks.value) {
      for (const task of group.tasks) {
        ids.push(task.task_id)
      }
    }
    return ids
  })

  const isAllSelected = computed(() =>
    allVisibleIds.value.length > 0 && allVisibleIds.value.every(id => selectedIds.value.has(id))
  )
  const isIndeterminate = computed(() => {
    if (!allVisibleIds.value.length) return false
    const selCount = allVisibleIds.value.filter(id => selectedIds.value.has(id)).length
    return selCount > 0 && selCount < allVisibleIds.value.length
  })

  function toggleSelect(task: Task, event: MouseEvent) {
    const newSet = new Set(selectedIds.value)
    const id = task.task_id
    if (newSet.has(id)) newSet.delete(id)
    else {
      // shift-click range selection
      if (event.shiftKey && lastSelectedId.value) {
        const ids = allVisibleIds.value
        const lastIdx = ids.indexOf(lastSelectedId.value)
        const curIdx = ids.indexOf(id)
        if (lastIdx >= 0 && curIdx >= 0) {
          const [from, to] = [Math.min(lastIdx, curIdx), Math.max(lastIdx, curIdx)]
          for (let i = from; i <= to; i++) newSet.add(ids[i])
        }
      }
      newSet.add(id)
    }
    selectedIds.value = newSet
    lastSelectedId.value = id
  }

  function toggleSelectAll() {
    const ids = allVisibleIds.value
    const allSel = ids.length > 0 && ids.every(id => selectedIds.value.has(id))
    if (allSel) {
      selectedIds.value = new Set()
    } else {
      selectedIds.value = new Set(ids)
    }
  }

  function clearSelection() {
    selectedIds.value = new Set()
    lastSelectedId.value = null
  }

  // ─── Batch Operations ───
  const showBatchDeleteConfirm = ref(false)

  const showExportDialog = ref(false)
  const exportFormat = ref<SummaryFormat>('docx')

  const exportableSelected = computed(() =>
    taskStore.tasks.filter(tk => selectedIds.value.has(tk.task_id) && tk.status === 'completed' && !!tk.output_path)
  )

  function batchExport() {
    if (!selectedIds.value.size) return
    if (!exportableSelected.value.length) {
      showToast(t('library.export_none'), 'warn')
      return
    }
    exportFormat.value = 'docx'
    showExportDialog.value = true
  }

  function triggerDownload(url: string) {
    const a = document.createElement('a')
    a.href = url
    a.download = ''
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  async function onConfirmExport() {
    const targets = exportableSelected.value
    const format = exportFormat.value
    showExportDialog.value = false
    for (let i = 0; i < targets.length; i++) {
      triggerDownload(downloadSummaryUrl(targets[i].task_id, format))
      if (i < targets.length - 1) await new Promise(r => setTimeout(r, 400))
    }
    const skipped = selectedIds.value.size - targets.length
    if (skipped > 0) showToast(t('library.export_skipped', { exported: targets.length, skipped }), 'info')
    else showToast(t('library.export_started', { count: targets.length }), 'success')
  }

  function batchArchive() {
    const ids = Array.from(selectedIds.value)
    if (!ids.length) return
    for (const id of ids) {
      taskStore.archiveTask(id).catch(e => console.error(`archive ${id} failed:`, e))
    }
    clearSelection()
  }

  async function batchUnarchive() {
    const ids = Array.from(selectedIds.value)
    if (!ids.length) return
    for (const id of ids) {
      taskStore.unarchiveTask(id).catch(e => console.error(`unarchive ${id} failed:`, e))
    }
    clearSelection()
  }

  function batchDelete() {
    if (!selectedIds.value.size) return
    showBatchDeleteConfirm.value = true
  }

  async function onConfirmBatchDelete() {
    for (const id of selectedIds.value) {
      try {
        await taskStore.removeTask(id)
      } catch (e) {
        console.error(`delete meeting ${id} failed:`, e)
      }
    }
    clearSelection()
  }

  // ─── Navigation ───
  function openTask(task: Task) {
    taskStore.selectTask(task.task_id)
    if (task.status === 'recording' || task.status === 'paused') {
      router.push({ name: 'recording', params: { taskId: task.task_id } })
    } else {
      router.push({ name: 'generating', params: { taskId: task.task_id } })
    }
  }

  // ─── Formatting Helpers ───
  function statusDotClass(status: TaskStatus): string {
    if (status === 'completed') return 'is-done'
    if (status === 'failed') return 'is-failed'
    if (status === 'paused') return 'is-paused'
    if (['recording', 'processing', 'transcribing', 'summarizing'].includes(status)) return 'is-processing'
    return 'is-pending'
  }

  function highlightLibTitle(task: Task): string {
    const title = task.title || task.audio_name || t('common.untitled')
    const q = taskStore.searchQuery.trim().toLowerCase()
    return q ? highlightText(title, q) : title
  }

  function formatDuration(sec: number | null): string {
    if (!sec) return '—'
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    if (m < 60) return `${m}:${String(s).padStart(2, '0')}`
    return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
  }

  function formatDateTime(dateStr: string | null): string {
    if (!dateStr) return '—'
    const d = new Date(dateStr)
    const y = d.getFullYear()
    const mo = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const h = String(d.getHours()).padStart(2, '0')
    const m = String(d.getMinutes()).padStart(2, '0')
    return `${y}-${mo}-${day} ${h}:${m}`
  }

  const SPK_MAX_SHOWN = 4

  function visibleSpeakers(task: Task): SpeakerInfo[] {
    const list = getSpeakerList(task)
    return list.length > SPK_MAX_SHOWN ? list.slice(0, SPK_MAX_SHOWN - 1) : list
  }

  function extraSpeakerCount(task: Task): number {
    const n = getSpeakerList(task).length
    return n > SPK_MAX_SHOWN ? n - (SPK_MAX_SHOWN - 1) : 0
  }

  // ─── 手工参会人（与音频绑定人区分展示） / Manual roster participants ───
  const MANUAL_MAX_SHOWN = 2

  /** 手工添加的参会人：排除已绑定到音频的名字与重复项 / Manual roster names excluding bound and duplicates */
  function getManualSpeakerNames(task: Task): string[] {
    const bound = new Set(
      Object.values(task.speaker_mapping || {})
        .map(v => String(v).trim())
        .filter(n => n && !isPlaceholderName(n))
    )
    const seen = new Set<string>()
    const list: string[] = []
    for (const raw of task.roster || []) {
      const name = String(raw).trim()
      if (!name || bound.has(name) || seen.has(name)) continue
      seen.add(name)
      list.push(name)
    }
    return list
  }

  function visibleManualSpeakers(task: Task): string[] {
    return getManualSpeakerNames(task).slice(0, MANUAL_MAX_SHOWN)
  }

  function extraManualCount(task: Task): number {
    const n = getManualSpeakerNames(task).length
    return n > MANUAL_MAX_SHOWN ? n - MANUAL_MAX_SHOWN : 0
  }

  function getSpeakerList(task: Task): SpeakerInfo[] {
    const mapping = task.speaker_mapping
    if (!mapping || Object.keys(mapping).length === 0) return []

    // 列表视图无 dialogue：时长占比取后端 speaker_share（秒），缺失时回退转写
    const { seconds, total } = resolveSpeakerSeconds(task)

    const UNID_FILTER = '__unidentified__'

    const list: SpeakerInfo[] = Object.entries(mapping)
      .filter(([, name]) => !isPlaceholderName(name))
      .map(([id, name]) => {
        const dur = seconds[id] || 0
        return {
          id,
          name: (name as string).trim(),
          color: getSpeakerColor(id),
          duration: dur,
          pct: speakerPct(seconds, total, id),
        }
      })

    const unidEntries = Object.entries(mapping).filter(([, name]) => isPlaceholderName(name))
    if (unidEntries.length > 0) {
      const unidDur = unidEntries.reduce((acc, [id]) => acc + (seconds[id] || 0), 0)
      list.push({
        id: UNID_FILTER,
        name: t('library.filter_speaker_unidentified'),
        color: 'var(--muted, var(--subtle))',
        duration: unidDur,
        pct: total > 0 ? Math.round((unidDur / total) * 100) : 0,
      })
    }
    return list
  }

  return {
    // refs
    groupedTasks,
    selectedIds, lastSelectedId,
    showBatchDeleteConfirm, showExportDialog, exportFormat,
    // computed
    isAllSelected, isIndeterminate, allVisibleIds,
    exportableSelected,
    // funcs
    toggleSelect, toggleSelectAll, clearSelection,
    batchExport, onConfirmExport, batchArchive, batchUnarchive, batchDelete, onConfirmBatchDelete,
    openTask,
    statusDotClass, highlightLibTitle, formatDuration, formatDateTime,
    visibleSpeakers, extraSpeakerCount, getSpeakerList,
    visibleManualSpeakers, extraManualCount,
  }
}
