/**
 * 版本更新 API / Version update API
 *
 * 对接后端 /api/update/* / Backed by /api/update/*
 */
import client from './client'

export interface VersionCheckResult {
  current_version: string
  latest_version: string | null
  update_available: boolean
  release_url: string
  /** 多平台下载链接（自建中转服务器） / Multi-platform download URLs (self-hosted relay) */
  downloads: Record<string, string>
  changelog: string
  published_at: string
  checked_at: number
  error: string | null
}

/** 获取当前版本号 / Get current software version */
export async function fetchCurrentVersion(): Promise<string> {
  const { data } = await client.get<{ version: string }>('/api/update/version')
  return data.version
}

/** 检查是否有新版本 / Check if new version is available */
export async function checkForUpdate(force = false): Promise<VersionCheckResult> {
  const { data } = await client.get<VersionCheckResult>('/api/update/check', {
    params: { force },
  })
  return data
}
