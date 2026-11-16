import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import type { Task } from '@/api/types'
import { hasUnidentified } from '@/utils/speakerDisplay'

export type SortKey = 'title' | 'status' | 'duration' | 'created_at'

export function useLibraryFilters() {
  const { t } = useI18n()
  const taskStore = useTaskStore()

  // ─── Tab / Active vs Archived ───
  function switchTab(showArchived: boolean) {
    taskStore.showArchived = showArchived
  }

  const activeTabCount = computed(() => taskStore.activeTasks.length)
  const archivedTabCount = computed(() => taskStore.archivedTasks.length)
  const libTabTotal = computed(() => taskStore.showArchived ? archivedTabCount.value : activeTabCount.value)

  // ─── Date Filter ───
  const dateFrom = ref('')
  const dateTo = ref('')
  const hasActiveFilter = computed(() => !!dateFrom.value || !!dateTo.value)

  function clearAllFilters() {
    dateFrom.value = ''
    dateTo.value = ''
    filterSpeakerId.value = ''
  }

  function setQuickDateRange(days: number) {
    const now = new Date()
    const from = new Date(now)
    from.setDate(from.getDate() - days)
    dateFrom.value = from.toISOString().slice(0, 10)
    dateTo.value = now.toISOString().slice(0, 10)
  }

  // ─── Speaker Filter (业务态，UI 层含 usePopMenu 下沉到 LibraryToolbar) ───
  const filterSpeakerId = ref('')
  const speakerSearchQuery = ref('')

  const speakerTriggerLabel = computed(() => {
    if (!filterSpeakerId.value) return t('library.filter_speaker_all')
    if (filterSpeakerId.value === UNID_FILTER) return t('library.filter_speaker_unidentified')
    return filterSpeakerId.value
  })

  const filteredSpeakerNames = computed(() => {
    const q = speakerSearchQuery.value.trim().toLowerCase()
    return allSpeakerNames.value.filter(n => q ? n.toLowerCase().includes(q) : true)
  })

  const unidVisible = computed(() => {
    const q = speakerSearchQuery.value.trim().toLowerCase()
    return !q || t('library.filter_speaker_unidentified').toLowerCase().includes(q)
  })

  function selectSpeaker(value: string) {
    filterSpeakerId.value = value
  }

  const allSpeakerNames = computed(() => {
    const names = new Set<string>()
    for (const task of taskStore.tasks) {
      const mapping = task.speaker_mapping
      if (mapping) {
        for (const name of Object.values(mapping)) {
          const trimmed = String(name).trim()
          if (trimmed) names.add(trimmed)
        }
      }
      // 手工添加的参会人（roster）与音频关联人员一并纳入筛选 / Include manually added roster participants
      for (const name of task.roster || []) {
        const trimmed = String(name).trim()
        if (trimmed) names.add(trimmed)
      }
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b))
  })

  // ─── Constants ───
  const UNID_FILTER = '__unidentified__'
  const libraryHasUnidentified = computed(() => taskStore.tasks.some((tk: Task) => hasUnidentified(tk.speaker_mapping)))

  // ─── Filter + Group Pipeline ───
  function applyLibFilters(source: Task[]): Task[] {
    const q = taskStore.searchQuery.trim().toLowerCase()
    const dFrom = dateFrom.value
    const dTo = dateTo.value
    const spk = filterSpeakerId.value

    return source.filter((t: Task) => {
      // archived tab
      if (taskStore.showArchived ? !t.archived_at : !!t.archived_at) return false

      // date range
      if (dFrom || dTo) {
        const fromTs = dFrom ? new Date(dFrom + 'T00:00:00').getTime() : -Infinity
        const toTs = dTo ? new Date(dTo + 'T23:59:59').getTime() : Infinity
        const dateStr = t.meeting_date || t.created_at?.slice(0, 10) || ''
        const ts = new Date(dateStr + 'T00:00:00').getTime()
        if (ts < fromTs || ts > toTs) return false
      }

      // speaker filter
      if (spk) {
        const mapping = t.speaker_mapping
        if (spk === UNID_FILTER) {
          if (!mapping || !hasUnidentified(mapping)) return false
        } else {
          const boundNames = mapping ? Object.values(mapping).map(v => String(v).trim()) : []
          const rosterNames = (t.roster || []).map(v => String(v).trim())
          if (!boundNames.includes(spk) && !rosterNames.includes(spk)) return false
        }
      }

      // search query
      if (q) {
        const title = (t.title || t.audio_name || '').toLowerCase()
        if (!title.includes(q)) return false
      }

      return true
    })
  }

  const hasLibFilter = computed(
    () => !!dateFrom.value || !!dateTo.value || !!filterSpeakerId.value || !!taskStore.searchQuery.trim()
  )
  const libFilteredTasks = computed(() => {
    const source = taskStore.showArchived ? taskStore.archivedTasks : taskStore.activeTasks
    return applyLibFilters(source)
  })

  const libCountDisplay = computed(() => libFilteredTasks.value.length)

  // ─── Grouping (by date buckets) ───
  const libGroupedTasks = computed(() => {
    const filtered = libFilteredTasks.value
    if (!filtered.length) return []

    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 86400000)
    const dayOfWeek = (now.getDay() + 6) % 7
    const thisWeekStart = new Date(today.getTime() - dayOfWeek * 86400000)
    const lastWeekStart = new Date(thisWeekStart.getTime() - 7 * 86400000)
    const thisMonthStart = new Date(now.getFullYear(), now.getMonth(), 1)
    const lastMonthStart = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    const groupOrder = ['today', 'yesterday', 'this_week', 'last_week', 'this_month', 'last_month', 'earlier']
    const labelKey: Record<string, string> = {
      today: 'library.group.today',
      yesterday: 'library.group.yesterday',
      this_week: 'library.group.this_week',
      last_week: 'library.group.last_week',
      this_month: 'library.group.this_month',
      last_month: 'library.group.last_month',
      earlier: 'library.group.earlier',
    }

    const groups = new Map<string, { key: string; label: string; tasks: Task[]; isToday: boolean; sortKey: number }>()
    for (const key of groupOrder) {
      groups.set(key, { key, label: t(labelKey[key]), tasks: [], isToday: key === 'today', sortKey: 0 })
    }

    for (const task of filtered) {
      const dateStr = task.meeting_date || task.created_at?.slice(0, 10) || 'unknown'
      const taskDate = new Date(dateStr + 'T00:00:00')
      const taskDay = new Date(taskDate.getFullYear(), taskDate.getMonth(), taskDate.getDate())
      const ts = taskDay.getTime()

      let groupKey: string
      if (ts === today.getTime()) groupKey = 'today'
      else if (ts === yesterday.getTime()) groupKey = 'yesterday'
      else if (ts >= thisWeekStart.getTime()) groupKey = 'this_week'
      else if (ts >= lastWeekStart.getTime()) groupKey = 'last_week'
      else if (ts >= thisMonthStart.getTime()) groupKey = 'this_month'
      else if (ts >= lastMonthStart.getTime()) groupKey = 'last_month'
      else groupKey = 'earlier'

      groups.get(groupKey)!.tasks.push(task)
    }

    const result: Array<{ key: string; label: string; tasks: Task[]; isToday: boolean; sortKey: number }> = []
    for (const key of groupOrder) {
      const g = groups.get(key)!
      if (g.tasks.length) result.push(g)
    }
    return result
  })

  // ─── Sort ───
  const sortKey = ref<SortKey>('created_at')
  const sortAsc = ref(false)

  function toggleSort(key: SortKey) {
    if (sortKey.value === key) sortAsc.value = !sortAsc.value
    else { sortKey.value = key; sortAsc.value = (key === 'title') }
  }

  function ariaSort(key: SortKey): 'ascending' | 'descending' | 'none' {
    if (sortKey.value !== key) return 'none'
    return sortAsc.value ? 'ascending' : 'descending'
  }

  function sortGroupTasks(tasks: Task[]): Task[] {
    const sorted = [...tasks]
    const dir = sortAsc.value ? 1 : -1
    sorted.sort((a: Task, b: Task) => {
      let va: string | number
      let vb: string | number
      if (sortKey.value === 'title') {
        va = (a.title || a.audio_name || '').toLowerCase()
        vb = (b.title || b.audio_name || '').toLowerCase()
      } else if (sortKey.value === 'status') {
        va = a.status
        vb = b.status
      } else if (sortKey.value === 'duration') {
        va = a.audio_duration || 0
        vb = b.audio_duration || 0
      } else {
        va = a.created_at || ''
        vb = b.created_at || ''
      }
      if (va === vb) return 0
      return (va > vb ? 1 : -1) * dir
    })
    return sorted
  }

  function isContentOnlyMatch(task: Task): boolean {
    const q = taskStore.searchQuery.trim().toLowerCase()
    if (!q) return false
    const title = (task.title || task.audio_name || '').toLowerCase()
    return !title.includes(q)
  }

  return {
    dateFrom, dateTo, filterSpeakerId, speakerSearchQuery,
    sortKey, sortAsc,
    UNID_FILTER,
    hasActiveFilter, speakerTriggerLabel, filteredSpeakerNames, unidVisible,
    allSpeakerNames, libraryHasUnidentified,
    hasLibFilter, libGroupedTasks, libCountDisplay, libTabTotal,
    activeTabCount, archivedTabCount,
    switchTab, clearAllFilters, setQuickDateRange, selectSpeaker,
    toggleSort, ariaSort, sortGroupTasks, isContentOnlyMatch,
  }
}
