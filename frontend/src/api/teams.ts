/**
 * 团队空间契约客户端（P1 契约 §8/§9，server plane，WP-1 基座）
 *
 * 纪律两条（产品批准在案，改造方案 §0/§1）：
 * 1. TB 零暴露证据链：本模块**不实现企业资产层任何读函数**——资产层无读端点（404 by design），
 *    前端连命中它的请求代码都不存在（QA 接口扫基线）。
 * 2. 权限判断不在此层：my_role 仅透传服务端值，渲染门控一律消费 spaceStore.myRole 单点。
 * 发布/撤回端点随 WP-2 扩展（publishToTeam/unpublishFromTeam），本批不含。
 */
import client from './client'
import type { ContextTaskSummary, ContextTaskDetail } from './context'

export type TeamRole = 'admin' | 'editor' | 'viewer'

/** 切换器数据源 DTO（契约 §9.1 直用）；archived=裁决④归档只读态 */
export interface TeamSummary {
  team_id: string
  name: string
  my_role: TeamRole | string
  archived?: boolean
  member_count?: number
}

export interface TeamMember {
  user_id: string
  display_name: string
  role: TeamRole | string
  joined_at?: string | null
}

/** 我在的空间清单（含 role）——空间切换器唯一数据源 */
export async function listMyTeams(): Promise<TeamSummary[]> {
  const { data } = await client.get<{ teams: TeamSummary[] }>('/api/v1/context/teams')
  return data.teams
}

/** 团队公开面列表（§8 团队副本读；空团队=空数组，私有原件结构性不在此结果） */
export async function listTeamTasks(teamId: string): Promise<ContextTaskSummary[]> {
  const { data } = await client.get<{ tasks: ContextTaskSummary[] }>(
    `/api/v1/context/teams/${encodeURIComponent(teamId)}/tasks`,
  )
  return data.tasks
}

/** 团队副本详情（服务端按成员权解析；非成员=404 资源隐藏语义） */
export async function getTeamTask(teamId: string, taskId: string): Promise<ContextTaskDetail> {
  const { data } = await client.get<ContextTaskDetail>(
    `/api/v1/context/teams/${encodeURIComponent(teamId)}/tasks/${encodeURIComponent(taskId)}`,
  )
  return data
}

// ─── 治理面端点绑定（WP-4 消费；纯契约映射，本批无 UI） ───

export async function createTeam(input: { name: string; member_user_ids: string[] }): Promise<TeamSummary> {
  const { data } = await client.post<TeamSummary>('/api/v1/teams', input)
  return data
}

export async function renameTeam(teamId: string, name: string): Promise<void> {
  await client.put(`/api/v1/teams/${encodeURIComponent(teamId)}`, { name })
}

export async function archiveTeam(teamId: string): Promise<void> {
  await client.put(`/api/v1/teams/${encodeURIComponent(teamId)}/archive`)
}

export async function listTeamMembers(teamId: string): Promise<TeamMember[]> {
  const { data } = await client.get<{ members: TeamMember[] }>(
    `/api/v1/teams/${encodeURIComponent(teamId)}/members`,
  )
  return data.members
}

export async function addTeamMembers(teamId: string, userIds: string[]): Promise<void> {
  await client.post(`/api/v1/teams/${encodeURIComponent(teamId)}/members`, { user_ids: userIds })
}

export async function removeTeamMember(teamId: string, userId: string): Promise<void> {
  await client.delete(`/api/v1/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`)
}

export async function setMemberRole(teamId: string, userId: string, role: TeamRole): Promise<void> {
  await client.put(`/api/v1/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}/role`, { role })
}
