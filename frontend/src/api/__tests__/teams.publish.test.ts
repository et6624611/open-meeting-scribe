/**
 * 发布链纯逻辑回归（WP-2）：请求体序列化（契约 §9.2 终形态 {team_id, mode, decision_id?}，
 * BE ffcb709 实码逐字对齐）+ 弹窗可选团队过滤（归档不出现、已公开置灰、决策粒度不置灰依据）。
 */
import { describe, expect, it } from 'vitest'
import { buildPublishBody, selectablePublishTeams } from '@/api/teams'

describe('buildPublishBody · 契约终形态序列化', () => {
  it('task 模式不带 decision_id', () => {
    expect(buildPublishBody('t1', 'task', null)).toEqual({ team_id: 't1', mode: 'task' })
  })

  it('decision 模式携带 decision_id（§9.2 双 payload）', () => {
    expect(buildPublishBody('t1', 'decision', 'd-9')).toEqual({ team_id: 't1', mode: 'decision', decision_id: 'd-9' })
  })

  it('decision 模式缺 id 回落 task 形态（防发出非法请求，服务端 422 decision_id_required 不该由正常 UI 触发）', () => {
    expect(buildPublishBody('t1', 'decision', null)).toEqual({ team_id: 't1', mode: 'task' })
  })
})

describe('selectablePublishTeams · 弹窗团队过滤', () => {
  const teams = [
    { team_id: 'a', name: 'A', my_role: 'admin' as const },
    { team_id: 'b', name: 'B', my_role: 'editor' as const, status: 'archived' },
    { team_id: 'c', name: 'C', my_role: 'viewer' as const },
  ]

  it('归档团队不出现在选择列表（裁决④不再接受新写入）', () => {
    expect(selectablePublishTeams(teams).map((r) => r.team.team_id)).toEqual(['a', 'c'])
  })

  it('已公开团队置灰标注（重复选择无效），未公开可选', () => {
    const rows = selectablePublishTeams(teams, ['a'])
    expect(rows.find((r) => r.team.team_id === 'a')?.alreadyPublished).toBe(true)
    expect(rows.find((r) => r.team.team_id === 'c')?.alreadyPublished).toBe(false)
  })

  it('缺省发布态（无 published_copies 数据面时）全部可选——不猜键名不误禁', () => {
    expect(selectablePublishTeams(teams).every((r) => !r.alreadyPublished)).toBe(true)
  })
})
