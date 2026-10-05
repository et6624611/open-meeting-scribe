/**
 * 说话人统计 — 从任务列表聚合会议/发言/待办数据 / Speaker stats — aggregates meeting/utterance/todo data from task list
 */
import { ref, computed, type ComputedRef, type Ref } from 'vue'
import { fetchTasks } from '@/api/tasks'
import type { Task, FlatTranscriptLine, TodoItem } from '@/api/types'

export interface MeetingStat {
  task_id: string
  title: string
  date: string
  duration: number
  utteranceCount: number
  totalUtterances: number
  excerpt: string
  utterances: FlatTranscriptLine[]
}

export interface TodoStat extends TodoItem {
  fromTaskId: string
  fromTaskTitle: string
}

export interface SpeakerStats {
  meetings: MeetingStat[]
  totalDuration: number
  utteranceCount: number
  todos: TodoStat[]
}

const statsCache = ref<Record<string, SpeakerStats>>({})
const allTasks = ref<Task[]>([])
const isLoading = ref(false)

/** 加载所有任务并计算统计 */
export async function loadSpeakerStats(speakerIds: string[]) {
  isLoading.value = true
  try {
    allTasks.value = await fetchTasks()
    computeStats(speakerIds)
  } catch (e) {
    console.error('[speakerStats] 加载失败:', e)
  } finally {
    isLoading.value = false
  }
}

/** 将 dialogue.sentences 展开为扁平列表 */
function flattenDialogue(task: Task): FlatTranscriptLine[] {
  const all: FlatTranscriptLine[] = []
  for (const d of task.dialogue || []) {
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
}

/** 从任务列表计算每个说话人的统计 */
function computeStats(speakerIds: string[]) {
  const stats: Record<string, SpeakerStats> = {}

  // 初始化
  speakerIds.forEach(id => {
    stats[id] = { meetings: [], totalDuration: 0, utteranceCount: 0, todos: [] }
  })

  // 遍历已完成的任务
  allTasks.value.forEach(task => {
    if (task.status !== 'completed' && task.status !== 'awaiting_mapping') return

    const taskId = task.task_id
    const taskTitle = task.title || task.audio_name || '未命名'
    const taskDate = task.created_at
    const taskDuration = task.audio_duration || 0
    const speakerMapping = task.speaker_uuid_mapping || {}

    // 展开 dialogue 为扁平列表
    const flatLines = flattenDialogue(task)
    const totalLineCount = flatLines.length

    // 按 speaker_id 分组发言
    const utterancesBySpeaker: Record<string, FlatTranscriptLine[]> = {}
    flatLines.forEach(d => {
      const sid = String(d.speaker_id)
      if (!utterancesBySpeaker[sid]) utterancesBySpeaker[sid] = []
      utterancesBySpeaker[sid].push(d)
    })

    // 映射到 UUID
    Object.entries(utterancesBySpeaker).forEach(([sid, utterances]) => {
      const uuid = speakerMapping[sid]
      if (!uuid || !stats[uuid]) return

      const s = stats[uuid]
      s.meetings.push({
        task_id: taskId,
        title: taskTitle,
        date: taskDate,
        duration: taskDuration,
        utteranceCount: utterances.length,
        totalUtterances: totalLineCount,
        excerpt: utterances.slice(0, 2).map(u => u.text).join(' '),
        utterances,
      })
      s.utteranceCount += utterances.length
      if (totalLineCount > 0) {
        s.totalDuration += (utterances.length / totalLineCount) * taskDuration
      }
    })

    // 收集待办
    if (task.todos?.length) {
      task.todos.forEach(todo => {
        const assignee = todo.assignee
        if (!assignee) return
        // assignee 可能是 speaker_id（数字字符串），需要映射到 UUID
        const uuid = speakerMapping[assignee] || assignee
        if (stats[uuid]) {
          stats[uuid].todos.push({
            ...todo,
            fromTaskId: taskId,
            fromTaskTitle: taskTitle,
          })
        }
      })
    }
  })

  statsCache.value = stats
}

/** 获取指定说话人的统计 */
export function useSpeakerStat(speakerId: ComputedRef<string> | Ref<string> | string) {
  const stat = computed(() => {
    const id = typeof speakerId === 'string' ? speakerId : speakerId.value
    return statsCache.value[id] || {
      meetings: [],
      totalDuration: 0,
      utteranceCount: 0,
      todos: [],
    }
  })

  return { stat, isLoading }
}

export { statsCache, allTasks, isLoading }
