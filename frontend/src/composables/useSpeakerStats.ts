/**
 * 说话人统计 — 从任务列表聚合会议/发言/决策数据 / Speaker stats — aggregates meeting/utterance/decision data from task list
 */
import { ref, computed, type ComputedRef, type Ref } from 'vue'
import { fetchTasks } from '@/api/tasks'
import type { Task, FlatTranscriptLine, DecisionItem } from '@/api/types'

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

export interface DecisionStat extends DecisionItem {
  fromTaskId: string
  fromTaskTitle: string
}

export interface SpeakerStats {
  meetings: MeetingStat[]
  totalDuration: number
  utteranceCount: number
  decisions: DecisionStat[]
}

export interface SpeakerProfile {
  id: string
  name: string
}

const statsCache = ref<Record<string, SpeakerStats>>({})
const allTasks = ref<Task[]>([])
const isLoading = ref(false)

/** 加载所有任务并计算统计 */
export async function loadSpeakerStats(profiles: SpeakerProfile[]) {
  isLoading.value = true
  try {
    // 说话人页需要逐字稿流水，显式走全量视图（列表视图不含 dialogue）
    allTasks.value = await fetchTasks('full')
    computeStats(profiles)
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
function computeStats(profiles: SpeakerProfile[]) {
  const stats: Record<string, SpeakerStats> = {}
  // 姓名 → 档案 id：参会人名单（roster）只存姓名，手工添加的参会关系靠它反查
  const idsByName = new Map<string, string[]>()

  // 初始化
  profiles.forEach(({ id, name }) => {
    stats[id] = { meetings: [], totalDuration: 0, utteranceCount: 0, decisions: [] }
    const trimmed = (name || '').trim()
    if (trimmed) {
      const ids = idsByName.get(trimmed) || []
      ids.push(id)
      idsByName.set(trimmed, ids)
    }
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

    // 按 UUID 聚合发言：同一 uuid 可能被多个 speaker_id 命中，合并后只登记一场，避免重复
    const utterancesByUuid: Record<string, FlatTranscriptLine[]> = {}
    Object.entries(utterancesBySpeaker).forEach(([sid, utterances]) => {
      const uuid = speakerMapping[sid]
      if (!uuid || !stats[uuid]) return
      if (!utterancesByUuid[uuid]) utterancesByUuid[uuid] = []
      utterancesByUuid[uuid].push(...utterances)
    })

    // 参与判定①：声纹标记 / 已绑定（speaker_uuid_mapping）——含无发言的有效绑定
    const mappedUuids = Object.values(speakerMapping).filter(uuid => uuid && stats[uuid])
    const voiceprintUuids = new Set<string>([...mappedUuids, ...Object.keys(utterancesByUuid)])
    voiceprintUuids.forEach(uuid => {
      const utterances = utterancesByUuid[uuid] || []
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

    // 参与判定②：手工添加的参会人（roster 姓名）——已按声纹登记过的名字不重复计入
    const rosterNames = new Set((task.roster || []).map(n => (n || '').trim()).filter(Boolean))
    rosterNames.forEach(name => {
      for (const id of idsByName.get(name) || []) {
        if (voiceprintUuids.has(id)) continue
        stats[id].meetings.push({
          task_id: taskId,
          title: taskTitle,
          date: taskDate,
          duration: taskDuration,
          utteranceCount: 0,
          totalUtterances: totalLineCount,
          excerpt: '',
          utterances: [],
        })
      }
    })

    // 收集决策
    if (task.decisions?.length) {
      task.decisions.forEach(decision => {
        const assignee = decision.assignee
        if (!assignee) return
        // assignee 可能是 speaker_id（数字字符串），需要映射到 UUID
        const uuid = speakerMapping[assignee] || assignee
        if (stats[uuid]) {
          stats[uuid].decisions.push({
            ...decision,
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
      decisions: [],
    }
  })

  return { stat, isLoading }
}

export { statsCache, allTasks, isLoading }
