/**
 * AI 分析面板 — 从当前任务数据中计算发言统计、议题分布、待办完成率
 * 录制中时从 realtime store 读取实时转写数据
 */
import { computed } from 'vue'
import { useTaskStore } from '@/stores/task'
import { useRealtimeStore } from '@/stores/realtime'
import type { FlatTranscriptLine } from '@/api/types'

interface SpeakerStat {
  name: string
  lines: number
  chars: number
  percent: number
}

interface ChapterStat {
  title: string
  lineCount: number
  speakers: Set<string>
}

export function useAiAnalysis() {
  const taskStore = useTaskStore()
  const realtimeStore = useRealtimeStore()

  const task = computed(() => taskStore.currentTask)
  const isRecording = computed(() => task.value?.status === 'recording')

  /**
   * 统一的对话数据源：录制中用 realtime store，否则从 task.dialogue.sentences 展开
   */
  const dialogueLines = computed<FlatTranscriptLine[]>(() => {
    if (isRecording.value && realtimeStore.entries.length > 0) {
      return realtimeStore.entries.map(e => ({
        begin_time: e.begin_time,
        end_time: e.end_time,
        text: e.text,
        speaker_id: e.speaker_id,
        sentence_id: 0,
      }))
    }
    // 从 dialogue.sentences 展开
    const all: FlatTranscriptLine[] = []
    const dialogue = task.value?.dialogue ?? []
    for (const d of dialogue) {
      if (!d.sentences) continue
      for (const s of d.sentences) {
        all.push({
          begin_time: s.begin_time,
          end_time: s.end_time,
          text: s.text,
          speaker_id: s.speaker_id,
          sentence_id: s.sentence_id,
        })
      }
    }
    all.sort((a, b) => a.begin_time - b.begin_time)
    return all
  })

  const hasData = computed(() => dialogueLines.value.length > 0)

  /** 各说话人发言统计 */
  const speakerStats = computed<SpeakerStat[]>(() => {
    const lines = dialogueLines.value
    if (!lines.length) return []

    const map = new Map<string, { lines: number; chars: number }>()
    let totalChars = 0

    for (const d of lines) {
      const name = `说话人 ${d.speaker_id + 1}`
      const entry = map.get(name) || { lines: 0, chars: 0 }
      entry.lines++
      entry.chars += d.text.length
      totalChars += d.text.length
      map.set(name, entry)
    }

    return Array.from(map.entries())
      .map(([name, s]) => ({
        name,
        lines: s.lines,
        chars: s.chars,
        percent: totalChars > 0 ? Math.round((s.chars / totalChars) * 100) : 0,
      }))
      .sort((a, b) => b.chars - a.chars)
  })

  /** 章节概览 — 按时间分段，每 10 分钟一个章节 */
  const chapters = computed<ChapterStat[]>(() => {
    const lines = dialogueLines.value
    if (!lines.length) return []

    const CHAPTER_SPAN_MS = 600000 // 10 分钟（毫秒）
    const result: ChapterStat[] = []
    let chapterStart = lines[0].begin_time
    let current: ChapterStat = { title: '', lineCount: 0, speakers: new Set() }

    for (const d of lines) {
      const beginTime = d.begin_time
      if (beginTime - chapterStart >= CHAPTER_SPAN_MS && current.lineCount > 0) {
        result.push(current)
        chapterStart = beginTime
        current = { title: '', lineCount: 0, speakers: new Set() }
      }
      current.lineCount++
      current.speakers.add(`说话人 ${d.speaker_id + 1}`)
    }
    if (current.lineCount > 0) result.push(current)

    result.forEach((ch, i) => {
      const minutes = Math.floor((i * CHAPTER_SPAN_MS) / 60000)
      ch.title = minutes < 60 ? `第 ${i + 1} 段（${minutes}分钟起）` : `第 ${i + 1} 段（${Math.floor(minutes / 60)}小时${minutes % 60}分钟起）`
    })

    return result
  })

  /** 待办统计 */
  const todoStats = computed(() => {
    const t = task.value
    if (!t?.todos?.length) return null
    const total = t.todos.length
    const done = t.todos.filter(td => td.done).length
    return { total, done, pending: total - done }
  })

  /** 基础信息 */
  const overview = computed(() => {
    const t = task.value
    if (!t) return null

    const lines = dialogueLines.value
    const dialogueCount = lines.length
    const speakerCount = new Set(
      lines.map(d => `说话人 ${d.speaker_id + 1}`)
    ).size
    const duration = t.audio_duration
      ? `${Math.floor(t.audio_duration / 60)}分${Math.round(t.audio_duration % 60)}秒`
      : isRecording.value ? '录制中…' : '未知'
    const wordCount = lines.reduce((sum, d) => sum + d.text.length, 0)

    return {
      title: t.title || t.audio_name || '未命名会议',
      status: t.status,
      date: t.meeting_date || t.created_at?.slice(0, 10) || '未知',
      duration,
      speakerCount,
      dialogueCount,
      wordCount,
    }
  })

  return {
    hasData,
    speakerStats,
    chapters,
    todoStats,
    overview,
  }
}
