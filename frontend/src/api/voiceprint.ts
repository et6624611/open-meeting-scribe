/**
 * 声纹 API 封装
 */
import client from './client'

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
