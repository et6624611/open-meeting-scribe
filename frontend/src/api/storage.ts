/**
 * 存储管理 API 封装 / Storage management API wrapper
 */
import client from './client'

export interface DirUsage {
  size_bytes: number
  file_count: number
}

export interface IntermediateUsage {
  normalized_files: DirUsage
  raw_files: DirUsage
  duplicate_normalized: DirUsage
}

export interface StorageUsage {
  recordings: DirUsage
  uploads: DirUsage
  tasks: DirUsage
  output: DirUsage
  intermediate: IntermediateUsage
  total_bytes: number
  reclaimable_bytes: number
}

export interface CleanResult {
  cleaned: Record<string, unknown>
  freed_bytes?: number
  total_freed_bytes?: number
}

/** 获取存储用量统计 / Fetch storage usage statistics */
export async function fetchStorageUsage(): Promise<StorageUsage> {
  const { data } = await client.get<StorageUsage>('/api/storage/usage')
  return data
}

/** 清理所有中间产物（归一化 + .raw + 冗余） / Clean all intermediate files (normalized + .raw + duplicates) */
export async function cleanIntermediateFiles(): Promise<CleanResult> {
  const { data } = await client.post<CleanResult>('/api/storage/clean')
  return data
}

/** 仅清理冗余文件（_normalized_normalized* + 孤儿 .raw） / Clean only orphaned files (_normalized_normalized* + orphan .raw) */
export async function cleanOrphanedFiles(): Promise<CleanResult> {
  const { data } = await client.post<CleanResult>('/api/storage/clean-orphaned')
  return data
}
