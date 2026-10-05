/**
 * 播放跟随 — 播放进度驱动原文滚动定位 / Playback follow — playback progress drives transcript scroll positioning
 */
import { ref, computed, watch, nextTick, type ComputedRef, type Ref } from 'vue'
import type { FlatTranscriptLine, Chapter } from '@/api/types'
import type { usePlayerStore } from '@/stores/player'

export function usePlaybackFollow(
  player: ReturnType<typeof usePlayerStore>,
  taskId: string,
  flatTranscript: ComputedRef<FlatTranscriptLine[]>,
  chapters: ComputedRef<Chapter[]>,
  visibleChapterIndices: Set<number>,
  transcriptPanelRef: Ref<any>,
  activeTab: Ref<string>,
  switchTab: (tabId: string) => void,
  getChapterIdxAtTime: (chs: Chapter[], ms: number) => number,
) {
  const playingLineIdx = ref(-1)
  const followPlayback = ref(true)

  const playingSpeakerId = computed<number | null>(() => {
    if (playingLineIdx.value < 0) return null
    return flatTranscript.value[playingLineIdx.value]?.speaker_id ?? null
  })

  function findLineIdxAt(ms: number): number {
    const lines = flatTranscript.value
    let lo = 0, hi = lines.length - 1, found = -1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if (lines[mid].begin_time <= ms) { found = mid; lo = mid + 1 } else { hi = mid - 1 }
    }
    return found
  }

  function scrollToPlayingLine() {
    const idx = playingLineIdx.value
    if (idx < 0) return
    const line = flatTranscript.value[idx]
    if (!line) return
    const chIdx = getChapterIdxAtTime(chapters.value, line.begin_time)
    if (chIdx >= 0 && !visibleChapterIndices.has(chIdx)) return
    nextTick(() => {
      const el = transcriptPanelRef.value?.transcriptListEl?.querySelector(`[data-line-idx="${idx}"]`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }

  function syncPlayingLine(ms: number) {
    const idx = findLineIdxAt(ms)
    if (idx === playingLineIdx.value) return
    playingLineIdx.value = idx
    if (followPlayback.value) scrollToPlayingLine()
  }

  function toggleAudio() {
    const willPlay = !player.playing
    player.toggle()
    if (!willPlay) return
    followPlayback.value = true
    if (activeTab.value !== 'transcript') switchTab('transcript')
    playingLineIdx.value = findLineIdxAt(player.currentTime * 1000)
    scrollToPlayingLine()
  }

  function resumeFollowPlayback() { followPlayback.value = true; scrollToPlayingLine() }
  function onUserScrollIntent() { if (player.playing) followPlayback.value = false }

  // 播放进度监听 / Playback progress listener
  watch(() => player.currentTime, (sec) => { if (player.taskId === taskId) syncPlayingLine(sec * 1000) })
  watch(() => player.taskId, (id) => { if (id !== taskId) playingLineIdx.value = -1 })

  return {
    playingLineIdx, followPlayback, playingSpeakerId,
    toggleAudio, resumeFollowPlayback, onUserScrollIntent, findLineIdxAt,
  }
}
