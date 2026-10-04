/**
 * 转写分层 API（PLAN-TRANSCRIPT-LAYERING WP-2 书面版）/ Transcript-layering API
 */
import client from './client'
import type { FormalVersion } from './types'

/** 读取书面版 sidecar；从未生成返回 null（404）/ Fetch formal version; null when never generated */
export async function getFormal(taskId: string): Promise<FormalVersion | null> {
  try {
    const { data } = await client.get<FormalVersion>(`/api/tasks/${taskId}/formal`)
    return data
  } catch (e: unknown) {
    if (typeof e === 'object' && e !== null && 'response' in e
      && (e as { response?: { status?: number } }).response?.status === 404) {
      return null
    }
    throw e
  }
}

/** 触发书面化（sentenceIds 省略＝整场；WP-3 选区复用同一端点）/ Start formalization */
export async function formalize(taskId: string, sentenceIds?: number[]): Promise<{ status: string; scope: string }> {
  const { data } = await client.post<{ status: string; scope: string }>(
    `/api/tasks/${taskId}/formalize`,
    sentenceIds ? { sentence_ids: sentenceIds } : {},
  )
  return data
}
