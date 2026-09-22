/**
 * 说话人 API 封装 / Speaker API wrapper
 */
import client from './client'

export interface Speaker {
  id: string
  name: string
  role?: string
  note?: string
  alias?: string
  is_me?: boolean
  meeting_count?: number
  total_duration?: number
  created_at?: string
  linked_user_id?: string | null
}

function mapSpeaker(raw: Record<string, unknown>): Speaker {
  return {
    id: (raw.speaker_id as string) || (raw.id as string) || '',
    name: (raw.name as string) || '',
    role: (raw.role as string) || '',
    note: (raw.note as string) || '',
    alias: (raw.role as string) || '',
    is_me: (raw.is_me as boolean) || false,
    meeting_count: (raw.meeting_count as number) || 0,
    total_duration: (raw.total_duration as number) || 0,
    created_at: (raw.created_at as string) || '',
    linked_user_id: (raw.linked_user_id as string) || null,
  }
}

export async function fetchSpeakers(): Promise<Speaker[]> {
  const { data } = await client.get<{ speakers: Record<string, unknown>[] }>('/api/speakers')
  return (data.speakers || []).map(mapSpeaker)
}

export async function createSpeaker(name: string): Promise<Speaker> {
  const { data } = await client.post<Record<string, unknown>>('/api/speakers', { name })
  return mapSpeaker(data)
}

export async function updateSpeaker(id: string, patch: { name?: string; alias?: string }): Promise<void> {
  await client.put(`/api/speakers/${id}`, { name: patch.name, role: patch.alias })
}

export async function deleteSpeaker(id: string): Promise<void> {
  await client.delete(`/api/speakers/${id}`)
}

export async function setSpeakerAsMe(id: string): Promise<void> {
  await client.put(`/api/speakers/${id}/set-as-me`)
}

/** 提交说话人映射，触发 Stage 2 纪要生成 / Submit speaker mapping, triggers Stage 2 summary generation */
export async function submitSpeakerMapping(taskId: string, mapping: Record<string, string>): Promise<void> {
  await client.post(`/api/tasks/${taskId}/speaker-mapping`, { mapping })
}

/** 增量保存说话人映射（不触发重新生成） / Incrementally save speaker mapping (no regeneration triggered) */
export async function saveSpeakerMapping(taskId: string, mapping: Record<string, string>): Promise<void> {
  await client.put(`/api/tasks/${taskId}/speaker-mapping`, { mapping })
}

export interface ApplySpeakerNamesResult {
  status: string
  summary: string | null
  user_summary?: string | null
  dialogue?: unknown[]
  speaker_mapping?: Record<string, string>
  speaker_uuid_mapping?: Record<string, string>
  todos?: unknown[]
}

/** 确认关联时按真实姓名原地替换纪要/原文/待办中的通用说话人标签（不重跑 LLM） /
 *  On confirm-binding, in-place replace generic speaker labels with real names (no LLM re-run) */
export async function applySpeakerNames(taskId: string, mapping: Record<string, string>): Promise<ApplySpeakerNamesResult> {
  const { data } = await client.post<ApplySpeakerNamesResult>(`/api/tasks/${taskId}/apply-speaker-names`, { mapping })
  return data
}

/** 更新参会人名单（独立于说话人绑定） / Update meeting roster (independent of speaker binding) */
export async function updateRoster(taskId: string, roster: string[]): Promise<{ roster: string[] }> {
  const { data } = await client.put<{ roster: string[] }>(`/api/tasks/${taskId}/roster`, { roster })
  return data
}
