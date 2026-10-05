/**
 * 决策状态字典 API / Decision status dictionary API
 *
 * 契约事实源：docs/API_CONTRACTS.md §12.4（REQ-DECISION-CENTER-R2 · DC-R2-c · 裁决 D6/D7）。
 * 系统锚点仅 active / done（不可改名不可删）；其余状态用户可维护（改名/标色/闭档位/排序/删除）。
 */
import client from './client'

export interface DecisionStatusItem {
  id: string
  /** 显示名（中文语境） */
  name: string
  /** 英文语境显示名：仅内置状态有独立值，自定义状态与 name 同值 */
  name_en: string
  /** 颜色：CSS 变量表达式（var(--x)）或十六进制色值，前端内联使用 */
  color: string
  /** 是否算「完成类」：闭档状态默认视图隐藏并沉底（D7） */
  closing: boolean
  /** 系统锚点：不可改名、不可删除（D6） */
  system: boolean
  created_at?: string
  updated_at?: string
}

/** 可选色板：前四项沿用主题令牌（随明暗切换），其余为固定色值 */
export const STATUS_PALETTE = [
  'var(--st-done)', 'var(--accent)', 'var(--st-confirm)', 'var(--st-decide)',
  '#2563eb', '#0d9488', '#d97706', '#dc2626', '#7c3aed', '#64748b',
]

export async function fetchStatuses(): Promise<DecisionStatusItem[]> {
  const { data } = await client.get<{ statuses: DecisionStatusItem[]; total: number }>('/api/decision-statuses')
  return data.statuses || []
}

export async function createStatus(payload: { name: string; color?: string; closing?: boolean }): Promise<DecisionStatusItem> {
  const { data } = await client.post<{ status: DecisionStatusItem }>('/api/decision-statuses', payload)
  return data.status
}

export async function updateStatus(id: string, patch: { name?: string; color?: string; closing?: boolean }): Promise<DecisionStatusItem> {
  const { data } = await client.put<{ status: DecisionStatusItem }>(`/api/decision-statuses/${id}`, patch)
  return data.status
}

/** 删除自定义状态：引用该状态的决策由后端回落到 active，返回影响条数 */
export async function deleteStatus(id: string): Promise<{ removed: string; reassigned: number }> {
  const { data } = await client.delete<{ ok: boolean; removed: string; reassigned: number }>(`/api/decision-statuses/${id}`)
  return { removed: data.removed, reassigned: data.reassigned ?? 0 }
}

export async function reorderStatuses(order: string[]): Promise<DecisionStatusItem[]> {
  const { data } = await client.post<{ statuses: DecisionStatusItem[] }>('/api/decision-statuses/reorder', { order })
  return data.statuses || []
}

/** 当前语言下的状态显示名：内置状态走双语名，自定义状态一律用本体名 */
export function statusLabel(item: DecisionStatusItem, locale: string): string {
  return locale.startsWith('en') ? (item.name_en || item.name) : item.name
}
