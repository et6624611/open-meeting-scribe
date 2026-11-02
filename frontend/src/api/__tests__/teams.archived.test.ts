/**
 * D009 销项断言：归档判定单源映射——服务端权威 status 优先，兼容期回退 archived 布尔。
 * （QA 跨侧契约错位探针的 FE 侧固定回归，防未来再次双真相源。）
 */
import { describe, expect, it } from 'vitest'
import { isTeamArchived } from '@/api/teams'

describe('isTeamArchived · D009 单源映射', () => {
  it('status=archived 判归档（服务端权威优先）', () => {
    expect(isTeamArchived({ team_id: 't', name: 'x', my_role: 'viewer', status: 'archived' })).toBe(true)
  })

  it('status 存在时以 status 为准，忽略矛盾的 archived 布尔（不制造第二真相源）', () => {
    expect(isTeamArchived({ team_id: 't', name: 'x', my_role: 'viewer', status: 'active', archived: true })).toBe(false)
    expect(isTeamArchived({ team_id: 't', name: 'x', my_role: 'admin', status: 'archived', archived: false })).toBe(true)
  })

  it('无 status 字段（旧形态回包）回退 archived 布尔兼容读入', () => {
    expect(isTeamArchived({ team_id: 't', name: 'x', my_role: 'editor', archived: true })).toBe(true)
    expect(isTeamArchived({ team_id: 't', name: 'x', my_role: 'editor' })).toBe(false)
  })
})
