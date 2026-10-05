/**
 * 右侧说话人面板 — 筛选、聚焦、搜索、导航 / Right speaker panel — filter, focus, search, navigation
 */
import { ref, computed, reactive, nextTick, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { getSpeakerColor } from '@/utils/speakerColors'
import { normalizeSpeakerName } from '@/utils/speakerDisplay'
import type { FlatTranscriptLine, Task } from '@/api/types'
import type { Speaker } from '@/api/speakers'

export function useSpeakerPanel(
  task: ComputedRef<Task | null>,
  flatTranscript: ComputedRef<FlatTranscriptLine[]>,
  speakers: Ref<Speaker[]>,
  currentBindingMapping: Record<number, string>,
  transcriptPanelRef: Ref<any>,
) {
  const { t } = useI18n()
  const userStore = useUserStore()

  const speakerPanelVisible = ref(true)
  const speakerPanelSearch = ref('')
  const searchExpanded = ref(false)
  const speakerFilterSet = reactive(new Set<number>())
  const focusLineIdx = ref(0)
  const locateSpeakerId = ref<number | null>(null)

  function toggleSearch() {
    searchExpanded.value = !searchExpanded.value
    if (searchExpanded.value) nextTick(() => transcriptPanelRef.value?.searchInputEl?.focus())
  }

  function onSearchBlur() { if (!speakerPanelSearch.value) searchExpanded.value = false }

  function onDocClickCloseSearch(e: MouseEvent) {
    if (!searchExpanded.value) return
    const target = e.target as HTMLElement
    if (!target.closest('.spk-search') && !target.closest('.spk-search-trigger')) searchExpanded.value = false
  }

  const panelSpeakerList = computed(() => {
    const lines = flatTranscript.value
    if (!lines.length) return []
    const q = speakerPanelSearch.value.toLowerCase()
    const speakerMap = new Map<number, { durMs: number; turns: number }>()
    for (const l of lines) {
      const cur = speakerMap.get(l.speaker_id) || { durMs: 0, turns: 0 }
      cur.durMs += l.end_time - l.begin_time; cur.turns += 1
      speakerMap.set(l.speaker_id, cur)
    }
    return Array.from(speakerMap.entries())
      .sort((a, b) => b[1].durMs - a[1].durMs)
      .map(([sid, stats]) => {
        const uuid = currentBindingMapping[sid] || task.value?.speaker_uuid_mapping?.[String(sid)]
        const spk = uuid ? speakers.value.find(s => s.id === uuid) : null
        const name = normalizeSpeakerName(spk?.name) || t('generating.speaker_default')
        const role = spk?.role || ''
        const isMe = spk?.linked_user_id ? spk.linked_user_id === userStore.user?.id : false
        const m = Math.floor(stats.durMs / 60000)
        const s = Math.floor((stats.durMs % 60000) / 1000)
        return { speakerId: sid, name, role, isMe, color: getSpeakerColor(String(sid)), durationStr: `${m}:${String(s).padStart(2, '0')}`, turns: stats.turns }
      })
      .filter(item => !q || item.name.toLowerCase().includes(q) || item.role.toLowerCase().includes(q))
  })

  const panelTotalDuration = computed(() => {
    const lines = flatTranscript.value
    if (!lines.length) return '00:00'
    const totalMs = lines.reduce((sum, l) => sum + (l.end_time - l.begin_time), 0)
    const m = Math.floor(totalMs / 60000), s = Math.floor((totalMs % 60000) / 1000)
    return `${m}:${String(s).padStart(2, '0')}`
  })

  const panelTotalTurns = computed(() => flatTranscript.value.length)

  const focusSpeaker = computed(() => {
    if (speakerFilterSet.size !== 1) return null
    const sid = Array.from(speakerFilterSet)[0]
    return panelSpeakerList.value.find(sp => sp.speakerId === sid) || null
  })

  const focusLines = computed(() => {
    if (speakerFilterSet.size !== 1) return []
    const sid = Array.from(speakerFilterSet)[0]
    return flatTranscript.value.map((l, i) => ({ ...l, idx: i })).filter(l => l.speaker_id === sid)
  })

  function toggleSpeakerFilter(id: number) {
    if (speakerFilterSet.has(id)) speakerFilterSet.delete(id)
    else speakerFilterSet.add(id)
    focusLineIdx.value = 0
    locateSpeakerId.value = speakerFilterSet.size === 1 ? Array.from(speakerFilterSet)[0] : null
  }

  function clearSpeakerFilter() { speakerFilterSet.clear(); locateSpeakerId.value = null; focusLineIdx.value = 0 }

  function navFocusLine(delta: number) {
    const lines = focusLines.value
    if (!lines.length) return
    focusLineIdx.value = (focusLineIdx.value + delta + lines.length) % lines.length
    const targetLine = lines[focusLineIdx.value]
    nextTick(() => {
      const el = transcriptPanelRef.value?.transcriptListEl?.querySelector(`[data-begin-time="${targetLine.begin_time}"]`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }

  function toggleLocateSpeaker(id: number) {
    if (locateSpeakerId.value === id) clearSpeakerFilter()
    else { locateSpeakerId.value = id; speakerFilterSet.clear(); speakerFilterSet.add(id); focusLineIdx.value = 0 }
  }

  return {
    speakerPanelVisible, speakerPanelSearch, searchExpanded,
    speakerFilterSet, focusLineIdx, locateSpeakerId,
    panelSpeakerList, panelTotalDuration, panelTotalTurns,
    focusSpeaker, focusLines,
    toggleSearch, onSearchBlur, onDocClickCloseSearch,
    toggleSpeakerFilter, clearSpeakerFilter, navFocusLine, toggleLocateSpeaker,
  }
}
