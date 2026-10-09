/**
 * useRecordingNotes.ts — 录音随记持久化与自动关联 / Recording notes persistence and auto-association
 *
 * 从 RecordingView.vue 拆分而来。 / Split from RecordingView.vue.
 * 管理随记的 localStorage 持久化、笔记-转写行自动关联、笔记 CRUD。 / Manages notes localStorage persistence, note-transcript line auto-association, notes CRUD.
 */

import { ref, computed, watch } from 'vue'
import type { Ref } from 'vue'
import type { TranscriptLine } from '@/composables/useWebSocket'
import { saveNotes } from '@/api/notes'

const NOTES_LS_KEY = 'oms_rec_timestamped_notes'

interface PersistedNote {
  id: string
  time: number
  text: string
}

export interface RecordingNote {
  id: string
  text: string
  lineIndex: number
  time: number
}

export function useRecordingNotes(
  wsLines: Ref<TranscriptLine[]>,
  elapsedMs: Ref<number>,
  taskId?: Ref<string | null>,
) {
  const userNotes = ref<RecordingNote[]>([])
  const noteCount = computed(() => userNotes.value.length)

  const notesByLine = computed(() => {
    const map: Record<number, string> = {}
    for (const n of userNotes.value) {
      if (n.lineIndex >= 0) map[n.lineIndex] = n.text
    }
    return map
  })

  // ── localStorage 持久化 / localStorage persistence ──

  function saveToStorage() {
    try {
      const data: PersistedNote[] = userNotes.value.map(n => ({ id: n.id, time: n.time, text: n.text }))
      localStorage.setItem(NOTES_LS_KEY, JSON.stringify(data))
    } catch { /* 忽略 / ignore */ }
  }

  function restoreFromStorage() {
    try {
      const saved = localStorage.getItem(NOTES_LS_KEY)
      if (!saved) return
      const data: PersistedNote[] = JSON.parse(saved)
      if (!Array.isArray(data) || data.length === 0) return
      const MAX_REASONABLE_MS = 24 * 60 * 60 * 1000
      let dirty = false
      userNotes.value = data.map(n => {
        const time = (n.time > MAX_REASONABLE_MS) ? (dirty = true, 0) : n.time
        return { id: n.id || crypto.randomUUID(), text: n.text, lineIndex: -1, time }
      })
      if (dirty) saveToStorage()
    } catch { /* 忽略 / ignore */ }
  }

  function clearStorage() {
    try { localStorage.removeItem(NOTES_LS_KEY) } catch { /* 忽略 / ignore */ }
  }

  // ── 后端实时同步（防抖 1s）/ Backend realtime sync (1s debounce) ──
  // 自动关停（heartbeat_timeout）时前端不会走手动 stop 流程，随记只存在 localStorage。
  // 必须在每次笔记变更时同步后端，否则 auto_stop_recording 收不到随记、会后丢失。
  let syncTimer: ReturnType<typeof setTimeout> | null = null

  function _formatForBackend(): string {
    if (userNotes.value.length === 0) return ''
    return userNotes.value
      .map(n => `[${_formatNoteTime(n.lineIndex, n.time)}] ${n.text}`)
      .join('\n')
  }

  function _scheduleSync() {
    if (!taskId?.value) return
    if (syncTimer) clearTimeout(syncTimer)
    syncTimer = setTimeout(() => {
      syncTimer = null
      const tid = taskId.value
      if (!tid) return
      const text = _formatForBackend()
      saveNotes(tid, text).catch(() => { /* 静默失败，下次变更会重试 */ })
    }, 1000)
  }

  /** 立即同步后端（取消挂起的防抖计时器）/ Flush pending debounce and sync immediately */
  function flushSync(): void {
    if (syncTimer) { clearTimeout(syncTimer); syncTimer = null }
    if (!taskId?.value) return
    const text = _formatForBackend()
    saveNotes(taskId.value, text).catch(() => { /* */ })
  }

  // ── 笔记操作 / Note operations ──

  function addNote(text: string) {
    const lineIndex = wsLines.value.length > 0 ? wsLines.value.length - 1 : 0
    const time = wsLines.value[lineIndex]?.begin_time ?? elapsedMs.value
    const id = crypto.randomUUID()
    userNotes.value.push({ id, text, lineIndex, time })
    saveToStorage()
    _scheduleSync()
  }

  function deleteNote(idx: number) {
    userNotes.value = userNotes.value.filter(n => n.lineIndex !== idx)
    saveToStorage()
    _scheduleSync()
  }

  // ── 自动关联：新行出现时匹配未关联笔记 / Auto-associate: match unassociated notes when new lines appear ──

  function autoAssociate() {
    const TIME_TOLERANCE_MS = 500
    let changed = false
    for (const note of userNotes.value) {
      if (note.lineIndex !== -1) continue
      for (let i = 0; i < wsLines.value.length; i++) {
        const line = wsLines.value[i]
        if (line?.begin_time && Math.abs(note.time - line.begin_time) <= TIME_TOLERANCE_MS) {
          note.lineIndex = i
          changed = true
          break
        }
      }
    }
    if (changed) { saveToStorage(); _scheduleSync() }
  }

  // 监听新行出现时自动关联 / Watch for new lines to auto-associate
  watch(() => wsLines.value.length, () => { autoAssociate() })

  /** 格式化笔记时间戳 / Format note timestamp */
  function _formatNoteTime(lineIdx: number, fallbackTimeMs: number): string {
    const line = lineIdx >= 0 ? wsLines.value[lineIdx] : null
    const timeMs = line?.begin_time ?? fallbackTimeMs
    if (!timeMs) return '00:00'
    const sec = Math.floor(timeMs / 1000)
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  /** 格式化笔记时间戳（公开别名）/ Format note timestamp (public alias) */
  const formatNoteTime = _formatNoteTime

  /** 获取所有笔记的格式化文本（用于结束录音时提交） / Get formatted text of all notes (for submission when recording ends) */
  function getNotesText(): string | undefined {
    const text = _formatForBackend()
    return text || undefined
  }

  return {
    userNotes,
    noteCount,
    notesByLine,
    addNote,
    deleteNote,
    restoreFromStorage,
    clearStorage,
    getNotesText,
    formatNoteTime,
    flushSync,
  }
}
