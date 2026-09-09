/**
 * 设置 API 封装
 */
import client from './client'

export interface FeatureFlags {
  realtime_chapters: boolean
  realtime_summary: boolean
  realtime_summary_interval: number
  update_check: boolean
}

export interface Settings {
  api_key?: string
  asr_model?: string
  llm_model?: string
  output_dir?: string
  feature_flags?: Partial<FeatureFlags>
  [key: string]: unknown
}

export async function fetchSettings(): Promise<Settings> {
  const { data } = await client.get<Settings>('/api/settings')
  return data
}

export async function saveSettings(settings: Partial<Settings>): Promise<void> {
  await client.post('/api/settings', settings)
}

export async function testApiConnection(): Promise<{ success: boolean; message?: string }> {
  const { data } = await client.post<{ success: boolean; message?: string }>('/api/settings/test')
  return data
}

export async function fetchModels(): Promise<{ asr: string[]; llm: string[] }> {
  const { data } = await client.get('/api/models')
  return data
}
