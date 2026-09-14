/**
 * 用量 API 封装 / Usage API wrapper
 */
import client from './client'

export interface UsageSummary {
  metered: boolean
  message?: string
  tier?: string
  tier_name?: string
  month?: string
  quota?: number
  used?: number
  remaining?: number
  percentage?: number
}

export interface UsageHistoryItem {
  date: string
  minutes: number
  tasks: number
}

export interface UsageHistory {
  history: UsageHistoryItem[]
}

export async function fetchUsageSummary(): Promise<UsageSummary> {
  const { data } = await client.get<UsageSummary>('/api/usage/summary')
  return data
}

export async function fetchUsageHistory(days = 30): Promise<UsageHistory> {
  const { data } = await client.get<UsageHistory>('/api/usage/history', { params: { days } })
  return data
}
