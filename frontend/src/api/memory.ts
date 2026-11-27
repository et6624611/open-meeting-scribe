/**
 * 长期记忆 API 封装 / Long-term memory API wrapper
 */
import client from './client'

export type MemoryStatus = 'proposed' | 'active' | 'archived' | 'deleted'
export type MemoryView = 'open' | 'closed' | 'proposed' | 'archived'
export type MemoryKind = 'preference' | 'fact' | 'decision' | 'correction' | 'habit' | 'glossary'

export interface MemorySource {
  task_id?: string
  quote?: string
  anchor?: { dialogue_index?: number; sentence_index?: number }
  manual?: boolean
}

export interface MemoryItem {
  id: string
  namespace: string
  kind: MemoryKind
  subject: string
  relation: string
  object: string
  text: string
  tags: string[]
  valid_from: string
  valid_to: string | null
  time_confidence: string
  recorded_at: string
  source: MemorySource | null
  status: MemoryStatus
  invalidated_by: string | null
  importance: number
  confidence: number
  last_used_at: string | null
  use_count: number
}

export interface MemoryStats {
  open: number
  closed: number
  proposed: number
  archived: number
  deleted: number
  total: number
}

export interface MemoryListParams {
  view?: MemoryView
  namespace?: string
  kind?: MemoryKind | ''
  q?: string
  cursor?: string | null
  limit?: number
}

export interface MemoryListResult {
  items: MemoryItem[]
  next_cursor: string | null
}

export interface MemoryCreatePayload {
  text: string
  kind: MemoryKind
  namespace: string
  subject?: string
  relation?: string
  object?: string
  tags?: string[]
  importance?: number
}

export async function fetchMemoryStats(): Promise<MemoryStats> {
  const { data } = await client.get<MemoryStats>('/api/memory/stats')
  return data
}

export async function listMemory(params: MemoryListParams = {}): Promise<MemoryListResult> {
  const query: Record<string, string | number> = {}
  if (params.view) query.view = params.view
  if (params.namespace) query.namespace = params.namespace
  if (params.kind) query.kind = params.kind
  if (params.q) query.q = params.q
  if (params.cursor) query.cursor = params.cursor
  if (params.limit) query.limit = params.limit
  const { data } = await client.get<MemoryListResult>('/api/memory', { params: query })
  return data
}

export async function createMemory(payload: MemoryCreatePayload): Promise<MemoryItem> {
  const { data } = await client.post<MemoryItem>('/api/memory', payload)
  return data
}

export async function updateMemory(id: string, patch: Partial<MemoryItem>): Promise<MemoryItem> {
  const { data } = await client.patch<MemoryItem>(`/api/memory/${id}`, patch)
  return data
}

export async function closeMemory(id: string, body?: { valid_to?: string; invalidated_by?: string; reason?: string }): Promise<MemoryItem> {
  const { data } = await client.post<MemoryItem>(`/api/memory/${id}/close`, body || {})
  return data
}

export async function reopenMemory(id: string): Promise<MemoryItem> {
  const { data } = await client.post<MemoryItem>(`/api/memory/${id}/reopen`)
  return data
}

export async function deleteMemory(id: string): Promise<MemoryItem> {
  const { data } = await client.delete<MemoryItem>(`/api/memory/${id}`)
  return data
}

export async function acceptMemory(id: string): Promise<MemoryItem> {
  const { data } = await client.post<MemoryItem>(`/api/memory/${id}/accept`)
  return data
}

export async function rejectMemory(id: string): Promise<MemoryItem> {
  const { data } = await client.post<MemoryItem>(`/api/memory/${id}/reject`)
  return data
}

export async function exportMemory(): Promise<{ blob: Blob; filename: string }> {
  const res = await client.get('/api/memory/export', { responseType: 'blob' })
  const disposition = String(res.headers['content-disposition'] || '')
  const match = disposition.match(/filename="?([^";]+)"?/)
  return {
    blob: res.data as Blob,
    filename: match?.[1] || 'memory-export.json',
  }
}
