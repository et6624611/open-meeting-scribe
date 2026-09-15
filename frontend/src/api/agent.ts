/**
 * Agent 角色工作区 API / Agent role workspace API
 *
 * 获取可用角色列表、角色详情。 / Fetch available roles and role details.
 */
import client from './client'

export interface AgentRole {
  name: string
  source: 'builtin' | 'custom'
  title: string
  description: string
  category: string
  tags: string[]
  version: string
}

export interface AgentRolesResponse {
  roles: AgentRole[]
  default: string
  active_agent: string
}

/** 获取所有可用角色列表 / Get list of all available roles */
export async function fetchRoles(): Promise<AgentRolesResponse> {
  const { data } = await client.get<AgentRolesResponse>('/api/agent/roles')
  return data
}

export interface RoleFilesResponse {
  role_name: string
  source: string
  forked_from: string | null
  files: Record<string, string>
}

/** 获取角色文件内容 / Get role file contents */
export async function fetchRoleFiles(roleName: string): Promise<RoleFilesResponse> {
  const { data } = await client.get<RoleFilesResponse>(`/api/agent/roles/${roleName}/files`)
  return data
}

/** Fork 预定义角色 / Fork a builtin role */
export async function forkRole(source: string, name: string) {
  const { data } = await client.post('/api/agent/roles/fork', { source, name })
  return data
}

/** 保存角色文件 / Save role file */
export async function saveRoleFile(roleName: string, filename: string, content: string) {
  const { data } = await client.put(`/api/agent/roles/${roleName}/files/${filename}`, { content })
  return data
}

/** 删除自定义角色 / Delete custom role */
export async function deleteRole(roleName: string) {
  const { data } = await client.delete(`/api/agent/roles/${roleName}`)
  return data
}

/** 获取当前激活的助手 / Get the currently active agent */
export async function fetchActiveAgent(): Promise<{ active_agent: string }> {
  const { data } = await client.get<{ active_agent: string }>('/api/agent/active')
  return data
}

/** 设置当前激活的助手 / Set the currently active agent */
export async function setActiveAgent(agent: string): Promise<{ active_agent: string }> {
  const { data } = await client.put<{ active_agent: string }>('/api/agent/active', { agent })
  return data
}
