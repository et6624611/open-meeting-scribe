/**
 * 项目 API 封装 / Project API wrapper
 */
import client from './client'

export interface Project {
  id: string
  name: string
  folders: string[]
  created_at: string
  file_count?: number
}

export interface FilesystemEntry {
  path: string
  name: string
  is_dir: boolean
}

export async function fetchProjects(): Promise<Project[]> {
  const { data } = await client.get<{ projects: Project[] }>('/api/projects')
  return data.projects || []
}

export async function createProject(name: string): Promise<Project> {
  const { data } = await client.post<Project>('/api/projects', { name })
  return data
}

export async function deleteProject(id: string): Promise<void> {
  await client.delete(`/api/projects/${id}`)
}

export async function addFolder(projectId: string, path: string): Promise<void> {
  await client.post(`/api/projects/${projectId}/folders`, { path })
}

export async function removeFolder(projectId: string, path: string): Promise<void> {
  await client.delete(`/api/projects/${projectId}/folders`, { data: { path } })
}

export async function browseFilesystem(path?: string): Promise<FilesystemEntry[]> {
  const params = path ? { path } : {}
  const { data } = await client.get<FilesystemEntry[]>('/api/filesystem/browse', { params })
  return data
}

export async function getProjectFiles(projectId: string): Promise<unknown[]> {
  const { data } = await client.get(`/api/projects/${projectId}/files`)
  return data.files || []
}
