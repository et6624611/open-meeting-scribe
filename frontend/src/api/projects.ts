/**
 * 项目 API 封装 / Project API wrapper
 */
import client from './client'

export interface ProjectFolder {
  path: string
  added_at: string
  sync_enabled?: boolean
  sync_content_types?: string[]
  sync_subfolder_name?: string
}

export interface Project {
  id: string
  name: string
  folders: ProjectFolder[]
  created_at: string
  updated_at?: string
  file_count?: number
  indexed_at?: string | null
}

export interface ProjectMeeting {
  task_id: string
  title: string
  status: string
  meeting_date: string
  created_at: string
  audio_duration: number
  speaker_count: number
}

export interface ProjectDetail extends Project {
  meetings: ProjectMeeting[]
}

export interface IndexedFile {
  path: string
  relative_path: string
  name: string
  type: string
  title: string
  summary: string
  keywords: string[]
  size: number
  modified_at: string
  text_length: number
}

export interface FilesystemBrowseResult {
  current_path: string
  parent_path: string | null
  home_path: string
  directories: Array<{
    name: string
    path: string
    has_children: boolean
  }>
}

export async function fetchProjects(): Promise<Project[]> {
  const { data } = await client.get<{ projects: Project[] }>('/api/projects')
  return data.projects || []
}

export async function fetchProjectDetail(projectId: string): Promise<ProjectDetail> {
  const { data } = await client.get<ProjectDetail>(`/api/projects/${projectId}`)
  return data
}

export async function createProject(name: string): Promise<Project> {
  const { data } = await client.post<Project>('/api/projects', { name })
  return data
}

export async function updateProject(projectId: string, name: string): Promise<Project> {
  const { data } = await client.put<Project>(`/api/projects/${projectId}`, { name })
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

export async function updateFolderSync(
  projectId: string,
  params: { path: string; enabled?: boolean; content_types?: string[]; subfolder_name?: string },
): Promise<void> {
  await client.put(`/api/projects/${projectId}/folders/sync`, params)
}

export async function triggerSync(projectId: string): Promise<{ synced: number; files: string[]; message: string }> {
  const { data } = await client.post(`/api/projects/${projectId}/sync`)
  return data
}

export async function triggerScan(projectId: string): Promise<{ status: string; message: string }> {
  const { data } = await client.post(`/api/projects/${projectId}/scan`)
  return data
}

export async function getProjectFiles(projectId: string): Promise<{ files: IndexedFile[]; indexed_at: string | null; total_files: number }> {
  const { data } = await client.get(`/api/projects/${projectId}/files`)
  return data
}

export async function searchProjectFiles(
  projectId: string,
  query: string,
  limit = 10,
): Promise<{ results: IndexedFile[]; total: number }> {
  const { data } = await client.post(`/api/projects/${projectId}/search`, { query, limit })
  return data
}

export async function browseFilesystem(path?: string): Promise<FilesystemBrowseResult> {
  const params = path ? { path } : {}
  const { data } = await client.get<FilesystemBrowseResult>('/api/filesystem/browse', { params })
  return data
}

export async function openFolderInFinder(path: string): Promise<{ opened: boolean; path: string }> {
  const { data } = await client.post('/api/folders/open', { path })
  return data
}
