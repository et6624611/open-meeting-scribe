/**
 * 空间基座（P1-WP1）核心语义回归：切换即失效单点 + last_space 恢复/校验 + 登出清态。
 * 对应改造方案 §0 决策 2/3 的钉死行为——这几条是 P1 防串数据的骨架断言。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/edition', () => ({ EDITION: 'enterprise', isEnterprise: true }))
vi.mock('@/api/teams', () => ({
  listMyTeams: vi.fn(async () => []),
  listTeamTasks: vi.fn(async () => []),
  getTeamTask: vi.fn(),
  listTeamMembers: vi.fn(async () => []),
  putTeamSnapshot: vi.fn(),
  snapshotTeamConflict: vi.fn(() => null),
}))
vi.mock('@/api/context', () => ({
  listContextTasks: vi.fn(async () => []),
  getContextTask: vi.fn(),
  putContextSnapshot: vi.fn(),
  snapshotConflictRev: vi.fn(() => null),
  deleteContextTask: vi.fn(),
}))
// D014 回归需要：ensureReady 走真实 checkAuth（并发去重）→ mock 企业 /me 与个人 auth 面
vi.mock('@/api/enterpriseAuth', () => ({
  enterpriseFetchMe: vi.fn(async () => ({ user_id: 'u9', display_name: '测试', role: 'admin' })),
  enterpriseLogout: vi.fn(async () => {}),
}))
vi.mock('@/api/auth', () => ({
  fetchMe: vi.fn(async () => null),
  logout: vi.fn(async () => {}),
  probeSession: vi.fn(async () => false),
}))
vi.mock('@/api/origins', () => ({ setActiveUser: vi.fn() }))

import * as teamsApi from '@/api/teams'
import { listContextTasks } from '@/api/context'
import { useSpaceStore, PRIVATE_SPACE } from '@/stores/space'
import { useContextsStore } from '@/stores/contexts'
import { useUserStore } from '@/stores/user'

const TEAMS = [
  { team_id: 't1', name: '产品组', my_role: 'editor' as const },
  { team_id: 't2', name: '外部顾问小组', my_role: 'viewer' as const },
  { team_id: 't3', name: '旧项目组', my_role: 'admin' as const, status: 'archived' },
]

function seedUser(id: string) {
  const user = useUserStore()
  user.user = { id, name: '测试', avatar_url: '', email: '', role: 'member', provider: 'enterprise', prefs: {} }
}

async function flushAsync() {
  // switchSpace 的失效链为 fire-and-forget（动态 import + 异步重载）：等两拍落位
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.mocked(teamsApi.listMyTeams).mockReset().mockResolvedValue([])
  vi.mocked(teamsApi.listTeamTasks).mockReset().mockResolvedValue([])
  vi.mocked(listContextTasks).mockReset().mockResolvedValue([])
})

describe('space store · 切换即失效单点', () => {
  it('loadTeams 完成后恢复最近所在空间（scopedKey 命名空间内）', async () => {
    seedUser('u9')
    vi.mocked(teamsApi.listMyTeams).mockResolvedValue(TEAMS)
    localStorage.setItem('oms.u.u9.last_space', 't2')
    const space = useSpaceStore()
    await space.loadTeams()
    expect(space.currentId).toBe('t2')
    expect(space.myRole).toBe('viewer')
    expect(space.canEdit).toBe(false)
  })

  it('最近空间失效（已被移出团队）静默回私有，不报错', async () => {
    seedUser('u9')
    vi.mocked(teamsApi.listMyTeams).mockResolvedValue(TEAMS)
    localStorage.setItem('oms.u.u9.last_space', 'gone-team')
    const space = useSpaceStore()
    await space.loadTeams()
    expect(space.currentId).toBe(PRIVATE_SPACE)
    expect(space.isTeamSpace).toBe(false)
  })

  it('switchSpace 切换=清空缓存并按空间重载；两空间数组物理分离（D013 硬核对项：私有列表消费面与副本行互不渗入）', async () => {
    seedUser('u9')
    vi.mocked(teamsApi.listMyTeams).mockResolvedValue(TEAMS)
    const space = useSpaceStore()
    await space.loadTeams()

    const contexts = useContextsStore()
    contexts.tasks = [{ task_id: 'private-1' } as never]
    vi.mocked(teamsApi.listTeamTasks).mockResolvedValue([{ task_id: 'copy-1' } as never])

    space.switchSpace('t1')
    expect(space.currentId).toBe('t1')
    await flushAsync()
    expect(teamsApi.listTeamTasks).toHaveBeenCalledWith('t1')
    // 团队副本只进 teamTasks；tasks 被失效单点清空且不因团队加载回填
    expect(contexts.teamTasks.map((x) => x.task_id)).toEqual(['copy-1'])
    expect(contexts.tasks).toEqual([])

    vi.mocked(listContextTasks).mockResolvedValue([{ task_id: 'private-2', published_copies: [{ team_id: 't1', team_name: '产品组', copy_task_id: 'copy-1', granularity: 'task', current_rev: 1, updated_at: 'x' }] } as never])
    space.switchSpace(PRIVATE_SPACE)
    await flushAsync()
    expect(listContextTasks).toHaveBeenCalled()
    // 私有面数据源=仅原件（published_copies 角标数据随行在位=行过滤不误伤角标读面，D013 修复承诺面）
    expect(contexts.tasks.map((x) => x.task_id)).toEqual(['private-2'])
    expect(contexts.tasks[0]?.published_copies?.length).toBe(1)
    expect(contexts.teamTasks).toEqual([])
  })

  it('switchSpace 拒绝不在我团队清单里的 id（防注入/越权探测面）', async () => {
    vi.mocked(teamsApi.listMyTeams).mockResolvedValue(TEAMS)
    const space = useSpaceStore()
    await space.loadTeams()
    space.switchSpace('not-my-team')
    expect(space.currentId).toBe(PRIVATE_SPACE)
  })

  it('归档团队仍可切换进入（裁决④=只读可浏览）；archived 与 myRole 双源下发给视图', async () => {
    vi.mocked(teamsApi.listMyTeams).mockResolvedValue(TEAMS)
    const space = useSpaceStore()
    await space.loadTeams()
    space.switchSpace('t3')
    expect(space.currentId).toBe('t3')
    expect(space.currentTeam?.status).toBe('archived') // D009：服务端权威态；渲染判定单源在 teams.ts isTeamArchived
    // 角色本身不因归档反转——写入拒绝在服务端（409 team_archived），前端消费 myRole+archived 两源渲染
    expect(space.canEdit).toBe(true)
  })

  it('reset（登出清态）回私有并清列表', async () => {
    vi.mocked(teamsApi.listMyTeams).mockResolvedValue(TEAMS)
    const space = useSpaceStore()
    await space.loadTeams()
    space.switchSpace('t1')
    space.reset()
    expect(space.currentId).toBe(PRIVATE_SPACE)
    expect(space.teams).toEqual([])
    expect(space.loaded).toBe(false)
  })

  it('D014 重载首帧：ensureReady 等会话+teams 就绪后才恢复 last_space（视图首帧取数不再赌挂载顺序）', async () => {
    localStorage.setItem('oms.u.u9.last_space', 't2')
    vi.mocked(teamsApi.listMyTeams).mockResolvedValue(TEAMS)
    const space = useSpaceStore()
    // 不预置 user：走真实 checkAuth（mock /me）→ 恢复链
    await space.ensureReady()
    expect(space.currentId).toBe('t2')
    expect(space.myRole).toBe('viewer')
  })

  it('D014 失败重试：teams 首载失败后 ensureReady 再次调用可恢复（loaded 仅成功置真）', async () => {
    localStorage.setItem('oms.u.u9.last_space', 't1')
    vi.mocked(teamsApi.listMyTeams)
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue(TEAMS)
    const space = useSpaceStore()
    await space.ensureReady()
    expect(space.loaded).toBe(false)
    expect(space.currentId).toBe(PRIVATE_SPACE)
    await space.ensureReady()
    expect(space.loaded).toBe(true)
    expect(space.currentId).toBe('t1')
  })
})
