/**
 * 上下文数据面 API（server plane，契约 §1.4/§1.5，v1.0 冻结） / Context data-plane API
 *
 * 服务端权威存储"定稿文本包"；所有实体固定携带 visibility/sync_status/server_rev/content_hash。
 * P0 visibility 恒 "personal"（UI 徽标组件依赖此字段存在性，UI 规格 §5）。
 * 快照上传带 Idempotency-Key + If-Match-Rev（离线队列重传幂等基础，§1.4）。
 */
import client from './client'
import { planeClient } from './origins'

export type Visibility = 'personal' // P0 恒 personal；P1 扩展时此处加枚举
export type ServerSyncStatus = 'synced' | 'stale'
export type QueueSyncStatus = 'pending' | 'syncing' | 'synced' | 'error'

/** 发布态副本行（P1 契约 §6.5 补漏注，BE ffcb709 定版：原件 DTO/列表项内嵌，仅计 active 副本；
 *  撤回即从数组消失。列表端点不返回时缺省=无副本） */
export interface PublishedCopy {
  team_id: string
  team_name: string
  copy_task_id: string
  granularity: 'task' | 'decision' | string
  current_rev: number
  updated_at: string
}

/** 列表项（实测对齐 2026-10-29 联调：list 用 current_rev/scope，detail 用 server_rev） */
export interface ContextTaskSummary {
  task_id: string
  title: string
  scope?: string
  visibility: Visibility
  sync_status: ServerSyncStatus
  current_rev: number
  content_hash: string
  updated_at: string
  published_copies?: PublishedCopy[]
}

export interface ContextTaskMeta {
  title: string
  meeting_time: string | null
  participants_text: string
  source: 'client' | 'web_import' | string
  legacy_id?: string | null
}

/** 详情（§1.4）：定稿全文 + 元数据 + server_rev；insights_html null 时可能缺省 */
export interface ContextTaskDetail {
  task_id: string
  visibility: Visibility
  sync_status: ServerSyncStatus
  server_rev: number
  content_hash: string
  meta: ContextTaskMeta
  updated_at: string
  formal: string
  summary: string
  decisions: unknown[]
  notes: string
  insights_html?: string | null
}

export interface SnapshotResult {
  server_rev: number
  content_hash: string
  stored_at: string
  idempotent_replay?: boolean
}

export interface SnapshotPayload {
  meta: {
    title: string
    meeting_time?: string | null
    participants_text?: string
    source: 'client' | 'web_import'
    legacy_id?: string | null
  }
  formal: string
  summary: string
  decisions: unknown[]
  notes: string
  insights_html: string | null
  content_hash: string
}

/** 本人可见 task 列表（分页 + since 增量，§1.4） */
export async function listContextTasks(params: { limit?: number; since?: string } = {}): Promise<ContextTaskSummary[]> {
  const { data } = await client.get<{ tasks: ContextTaskSummary[] }>('/api/v1/context/tasks', { params })
  return data.tasks
}

/** task 定稿全文 + 元数据 + server_rev（§1.4） */
export async function getContextTask(taskId: string): Promise<ContextTaskDetail> {
  const { data } = await client.get<ContextTaskDetail>(`/api/v1/context/tasks/${encodeURIComponent(taskId)}`)
  return data
}

/**
 * 上传/更新定稿快照（§1.4 幂等契约）：
 *  - Idempotency-Key = 客户端 outbox 记录全局唯一 ID（重传不变）
 *  - If-Match-Rev = 所基于的 server_rev；首传 0；409 携带 current_rev → 调用方拉新合并后以新 mutation_id 重推
 */
export async function putContextSnapshot(
  taskId: string,
  payload: SnapshotPayload,
  headers: { idempotencyKey: string; baseRev: number },
): Promise<SnapshotResult> {
  const { data } = await client.put<SnapshotResult>(
    `/api/v1/context/tasks/${encodeURIComponent(taskId)}/snapshot`,
    payload,
    { headers: { 'Idempotency-Key': headers.idempotencyKey, 'If-Match-Rev': String(headers.baseRev) } },
  )
  return data
}

/** owner 删除（软删 30 天回收站，§1.4 + QA-Q3 裁决） */
export async function deleteContextTask(taskId: string): Promise<void> {
  await client.delete(`/api/v1/context/tasks/${encodeURIComponent(taskId)}`)
}

/** 409 rev 冲突判定：current_rev 随错误体下发（§1.1 错误体约定） */
export function snapshotConflictRev(err: unknown): number | null {
  const data = (err as { response?: { status?: number; data?: { error?: { current_rev?: number } } } })?.response
  if (data?.status !== 409) return null
  return data.data?.error?.current_rev ?? null
}

// ─── 个人资产（§1.5）：仅白名单文本字段；声纹 embedding 出现即 422 拒收 ───
// 实测信封（BE aba84fb/dao.get_asset）：无数据时 current_rev=0、payload=null（非 404）

export interface AssetEnvelope<T> {
  kind: string
  visibility: Visibility
  current_rev: number
  content_hash: string | null
  payload: T | null
}

export interface HotwordsPayload { hotwords: string }
export interface SpeakerAliasesPayload { aliases: Record<string, string> }

export async function getHotwordsAsset(): Promise<AssetEnvelope<HotwordsPayload>> {
  const { data } = await client.get<AssetEnvelope<HotwordsPayload>>('/api/v1/context/assets/hotwords')
  return data
}

export async function putHotwordsAsset(payload: HotwordsPayload, headers: { idempotencyKey: string; baseRev: number }): Promise<SnapshotResult> {
  const { data } = await client.put<SnapshotResult>('/api/v1/context/assets/hotwords', payload, {
    headers: { 'Idempotency-Key': headers.idempotencyKey, 'If-Match-Rev': String(headers.baseRev) },
  })
  return data
}

export async function getSpeakerAliasesAsset(): Promise<AssetEnvelope<SpeakerAliasesPayload>> {
  const { data } = await client.get<AssetEnvelope<SpeakerAliasesPayload>>('/api/v1/context/assets/speaker-aliases')
  return data
}

export async function putSpeakerAliasesAsset(payload: SpeakerAliasesPayload, headers: { idempotencyKey: string; baseRev: number }): Promise<SnapshotResult> {
  const { data } = await client.put<SnapshotResult>('/api/v1/context/assets/speaker-aliases', payload, {
    headers: { 'Idempotency-Key': headers.idempotencyKey, 'If-Match-Rev': String(headers.baseRev) },
  })
  return data
}

// ─── 同步队列（local plane，契约 §1.4 队列侧权威态；"待同步到公司服务器"提示的数据源） ───

export interface SyncQueueItem {
  task_id: string
  mutation_id?: string
  status: QueueSyncStatus
  queued_at: string
  last_error: string | null
  retry_after: string | null
}

/** 实测响应（BE c23b247）：{queue:[...]}；未配对时 409 assistant_not_paired（调用方按引导态处理） */
export async function getSyncQueue(): Promise<SyncQueueItem[]> {
  const { data } = await planeClient('local').get<{ queue: SyncQueueItem[] }>('/api/sync/queue')
  return data.queue
}
