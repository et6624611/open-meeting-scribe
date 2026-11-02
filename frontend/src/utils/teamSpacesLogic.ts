/**
 * 团队面纯逻辑层（P1-WP-3）：K1 十二值留痕文案映射 + 决策聚合摊平。
 * 单测先钉（同 P0 惯例：纯函数先行，组件随批次）；未知枚举回退显原文不崩（兜底纪律）。
 */
import type { ContextTaskDetail, PublishedCopy } from '@/api/context'
import type { TeamTaskSummary } from '@/api/teams'

/** K1 留痕 action → i18n 键映射（契约 §8.4 十二值逐字；未知值回退显原文） */
const AUDIT_KEYS: Record<string, string> = {
  publish: 'audit.act_publish',
  edit: 'audit.act_edit',
  withdraw: 'audit.act_withdraw',
  decision_publish: 'audit.act_decision_publish',
  decision_withdraw: 'audit.act_decision_withdraw',
  decision_delete: 'audit.act_decision_delete',
  decision_restore: 'audit.act_decision_restore',
  member_add: 'audit.act_member_add',
  member_role_change: 'audit.act_member_role_change',
  member_remove: 'audit.act_member_remove',
  role_transfer: 'audit.act_role_transfer',
  team_archive: 'audit.act_team_archive',
}

export const K1_ACTIONS = Object.keys(AUDIT_KEYS)

/** 返回 i18n 键；未知枚举原样回退（渲染侧以原文呈现，不崩不猜） */
export function auditLabelKey(action: string): string {
  return AUDIT_KEYS[action] ?? ''
}

/** 聚合决策条目（团队决策视图行源；仅摊平在位副本详情，不请求资产层——零消费红线）。
 *  排序锚=K4 定版"公开时刻"published_at（编辑不顶序）；旧部署态缺键回退 updated_at 兼容 */
export interface AggregatedDecision {
  decisionId: string
  text: string
  statusText: string
  teamTaskId: string
  taskTitle: string
  publishAnchor: string
}

export function aggregateDecisions(rows: Array<{ summary: TeamTaskSummary; detail: ContextTaskDetail | null }>): AggregatedDecision[] {
  const out: AggregatedDecision[] = []
  for (const { summary, detail } of rows) {
    if (!detail) continue
    const anchor = summary.published_at ?? summary.updated_at
    for (const raw of detail.decisions ?? []) {
      if (!raw || typeof raw !== 'object') continue
      const d = raw as { id?: string; text?: string; status_text?: string }
      if (!d.id) continue
      out.push({
        decisionId: d.id,
        text: d.text ?? '',
        statusText: d.status_text ?? '',
        teamTaskId: summary.task_id,
        taskTitle: summary.title || summary.task_id,
        publishAnchor: anchor,
      })
    }
  }
  // 按公开时间倒序（规格 §5.2 + K4 定版：排序锚=公开时刻，编辑不顶序）
  return out.sort((a, b) => (a.publishAnchor < b.publishAnchor ? 1 : -1))
}

/** 副本行是否已被撤回（读面即真相：published_copies 不含即撤；本批私有角标数据源回归钉用） */
export function copyCount(copies: PublishedCopy[] | undefined): number {
  return new Set((copies ?? []).map((c) => c.team_id)).size
}
