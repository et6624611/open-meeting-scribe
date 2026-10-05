/**
 * 声纹 API 封装 / Voiceprint API wrapper
 */
import client from './client'
import type { VoiceprintMatchItem } from './types'

export interface VoiceprintMatchResponse {
  task_id: string
  results: VoiceprintMatchItem[]
  auto_mapping: Record<string, string>
  summary: string
}

/** 对会议执行声纹自动识别（后端落盘并返回明细） / Run voiceprint auto-match for a meeting */
export async function runVoiceprintMatch(taskId: string): Promise<VoiceprintMatchResponse> {
  const { data } = await client.post<VoiceprintMatchResponse>(
    `/api/voiceprint/tasks/${taskId}/match`, {},
  )
  return data
}

/** 忽略某说话人的声纹建议（本场不再显示，重跑识别自动清空） / Dismiss a voiceprint suggestion */
export async function dismissVoiceprintSuggestion(taskId: string, speakerId: number): Promise<void> {
  await client.post(`/api/voiceprint/tasks/${taskId}/dismiss`, { speaker_id: speakerId })
}

export interface VoiceprintStatus {
  speaker_uuid: string
  has_voiceprint: boolean
  registered_at?: string
  updated_at?: string
  sample_count: number
  total_sample_duration: number
}

export async function getVoiceprintStatus(uuid: string): Promise<VoiceprintStatus> {
  const { data } = await client.get<VoiceprintStatus>(`/api/voiceprint/status/${uuid}`)
  return data
}

export async function rebuildVoiceprint(
  uuid: string,
): Promise<{ message: string; meeting_count: number; duration_sec: number }> {
  const { data } = await client.post(`/api/voiceprint/rebuild/${uuid}`)
  return data
}

export async function deleteVoiceprint(uuid: string): Promise<void> {
  await client.delete(`/api/voiceprint/${uuid}`)
}

/** 获取声纹注册表，返回已注册声纹的说话人 ID 集合 / Fetch voiceprint registry; returns set of registered speaker UUIDs */
export async function fetchVoiceprintRegistry(): Promise<Set<string>> {
  const { data } = await client.get<{ voiceprints: Array<{ speaker_uuid: string }> }>('/api/voiceprint/registry')
  return new Set((data.voiceprints || []).map(v => v.speaker_uuid))
}
