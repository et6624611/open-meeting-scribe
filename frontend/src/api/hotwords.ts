/**
 * 热词 API 封装 / Hotwords API wrapper
 */
import client from './client'

export async function fetchHotwords(): Promise<string> {
  const { data } = await client.get<{ hotwords: string[] | string }>('/api/hotwords')
  const raw = data.hotwords
  if (Array.isArray(raw)) return raw.join('\n')
  return (raw as string) || ''
}

export async function saveHotwords(hotwords: string): Promise<void> {
  await client.post('/api/hotwords', { hotwords })
}

export async function fetchHotwordMappings(): Promise<string> {
  const { data } = await client.get<{ mappings: { from: string; to: string }[] | string }>('/api/hotword-mappings')
  const raw = data.mappings
  if (Array.isArray(raw)) {
    return raw.map((m: { from: string; to: string }) => `${m.from}→${m.to}`).join('\n')
  }
  return (raw as string) || ''
}

export async function saveHotwordMappings(mappings: string): Promise<void> {
  await client.post('/api/hotword-mappings', { mappings })
}
