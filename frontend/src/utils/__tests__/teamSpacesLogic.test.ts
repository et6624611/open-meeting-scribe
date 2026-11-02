/**
 * WP-3 团队面纯逻辑回归：K1 十二值映射完整性（契约 §8.4 逐字对名）+ 未知值回退
 * + 决策聚合摊平/排序（规格 §5.2 倒序）。
 */
import { describe, expect, it } from 'vitest'
import { K1_ACTIONS, aggregateDecisions, auditLabelKey } from '@/utils/teamSpacesLogic'

const CONTRACT_K1 = ['publish', 'edit', 'withdraw', 'decision_publish', 'decision_withdraw',
  'decision_delete', 'decision_restore', 'member_add', 'member_role_change', 'member_remove',
  'role_transfer', 'team_archive'] as const

describe('auditLabelKey · K1 十二值（契约 §8.4 逐字）', () => {
  it('契约十二值全部有映射，无多无少（新增枚举值=先改契约再改此处，防漂移）', () => {
    expect([...K1_ACTIONS].sort()).toEqual([...CONTRACT_K1].sort())
  })

  it('每值可解析出键（消费侧 t() 不再落空）', () => {
    for (const a of CONTRACT_K1) {
      expect(auditLabelKey(a)).toMatch(/^audit\.act_/)
    }
  })

  it('未知枚举回退空串→渲染侧显原文不崩', () => {
    expect(auditLabelKey('pending_approval')).toBe('')
    expect(auditLabelKey('')).toBe('')
  })
})

describe('aggregateDecisions · 决策聚合摊平', () => {
  const rows = [
    {
      summary: { task_id: 'c1', title: '评审会', updated_at: '2026-11-01T10:00:00Z', published_at: '2026-10-30T09:00:00Z', current_rev: 3, content_hash: 'h', source_task_id: 'p1', publisher_user_id: 'u1', visibility: 'team' as const },
      detail: { decisions: [{ id: 'd1', text: '选 A 方案', status_text: '已确认' }, { text: '无 id 条目跳过' }, null] } as never,
    },
    {
      summary: { task_id: 'c2', title: '周会', updated_at: '2026-10-01T10:00:00Z', published_at: '2026-11-02T10:00:00Z', current_rev: 1, content_hash: 'h', source_task_id: 'p2', publisher_user_id: 'u2', visibility: 'team' as const },
      detail: { decisions: [{ id: 'd2', text: '上线 WP-3' }] } as never,
    },
    {
      summary: { task_id: 'c3', title: '详情失败的会', updated_at: '2026-11-03T10:00:00Z', current_rev: 1, content_hash: 'h', source_task_id: null, publisher_user_id: 'u2', visibility: 'team' as const },
      detail: null,
    },
  ]

  it('摊平+按公开时刻倒序（规格 §5.2 + K4 定版：编辑不顶序——c1 编辑时间更新但公开更早，位次在后）；无 id 条目与详情缺失行跳过', () => {
    const out = aggregateDecisions(rows)
    expect(out.map((r) => r.decisionId)).toEqual(['d2', 'd1'])
    expect(out[0]?.taskTitle).toBe('周会')
    expect(out[1]?.statusText).toBe('已确认')
    expect(out[1]?.publishAnchor).toBe('2026-10-30T09:00:00Z')
  })

  it('旧部署态缺 published_at 键：回退 updated_at 排序不崩（兼容锚）', () => {
    const anchorless = [{ summary: { ...rows[0]!.summary, published_at: undefined }, detail: rows[0]!.detail }]
    const out = aggregateDecisions(anchorless)
    expect(out[0]?.publishAnchor).toBe('2026-11-01T10:00:00Z') // updated_at 回退
  })
})
