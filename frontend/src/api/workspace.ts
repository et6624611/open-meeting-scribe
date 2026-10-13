/**
 * 工作区 API 封装 / Workspace API wrapper
 *
 * 对应后端 app/routers/workspace.py 的 9 个端点。
 * 工作区是「会议上下文物化成的本地文件夹」，可用于：
 *   - 在软件内浏览文件树 / 预览文本
 *   - 一键在外部 IDE（VSCode/Cursor/Zed/Windsurf/Trae/Claude Code）打开
 *   - 在系统文件管理器中打开
 *   - 跨项目/跨会议浏览索引
 *   - 把外部 IDE 在 .md 里做的修改 propose 回会议纪要
 */
import client from './client'

// ── 类型 / Types ──

export interface WorkspaceNode {
  name: string
  type: 'dir' | 'file'
  rel_path: string
  size: number
  children?: WorkspaceNode[]
}

export interface WorkspaceTree {
  path: string
  nodes: WorkspaceNode[]
  exists: boolean
}

export interface WorkspaceFile {
  content: string
  truncated: boolean
  size: number
  path: string
}

export interface IdeInfo {
  ide_id: string
  display_name: string
  available: boolean
  path: string
}

export interface WorkspaceProject {
  project_id: string
  project_name: string
  meeting_count: number
  last_updated?: string
}

export interface WorkspaceIndex {
  projects: WorkspaceProject[]
  standalone_count: number
  exists: boolean
}

export interface ProjectMeeting {
  task_id: string
  title: string
  meeting_date?: string
  audio_duration?: number
  status?: string
  workspace_path: string
}

export interface ProjectMeetingsIndex {
  meetings: ProjectMeeting[]
  exists: boolean
}

export interface WorkspacePreviewResult {
  workspace: string
  file_count: number
  [k: string]: unknown
}

export interface WorkspaceRefreshResult {
  workspace: string
  file_count: number
  [k: string]: unknown
}

export interface WorkspaceImportResult {
  imported: boolean
  summary_changes?: number
  notes_changes?: number
  message?: string
  [k: string]: unknown
}

export interface OpenResult {
  opened: boolean
  path: string
  [k: string]: unknown
}

export interface IdeLaunchResult {
  launched: boolean
  cmd: string
  error?: string
  [k: string]: unknown
}

// ── 端点封装 / Endpoint wrappers ──

/** 获取工作区文件树 / Get workspace file tree */
export async function fetchWorkspaceTree(taskId: string): Promise<WorkspaceTree> {
  const { data } = await client.get<WorkspaceTree>('/api/workspace/tree', { params: { task_id: taskId } })
  return data
}

/** 获取工作区文件内容（只读文本预览） / Get workspace file content (read-only text) */
export async function fetchWorkspaceFile(taskId: string, relPath: string): Promise<WorkspaceFile> {
  const { data } = await client.get<WorkspaceFile>('/api/workspace/file', {
    params: { task_id: taskId, rel_path: relPath },
  })
  return data
}

/** 预生成工作区（进会议页时调用） / Pre-generate workspace (on entering meeting page) */
export async function generatePreview(taskId: string): Promise<WorkspacePreviewResult> {
  const { data } = await client.get<WorkspacePreviewResult>('/api/workspace/preview', {
    params: { task_id: taskId },
  })
  return data
}

/** 刷新工作区（从软件数据重新生成） / Refresh workspace from app data */
export async function refreshWorkspace(taskId: string): Promise<WorkspaceRefreshResult> {
  const { data } = await client.post<WorkspaceRefreshResult>('/api/workspace/refresh', { task_id: taskId })
  return data
}

/** 从工作区导入 summary/notes 变更（走 propose 通道） / Import changes from workspace */
export async function importFromWorkspace(taskId: string): Promise<WorkspaceImportResult> {
  const { data } = await client.post<WorkspaceImportResult>('/api/workspace/import', { task_id: taskId })
  return data
}

/** 在系统文件管理器中打开工作区 / Open workspace in system file manager */
export async function openInFinder(taskId: string): Promise<OpenResult> {
  const { data } = await client.post<OpenResult>('/api/workspace/open-finder', { task_id: taskId })
  return data
}

/** 启动 IDE 打开工作区 / Launch IDE to open workspace */
export async function openInIde(taskId: string, ideId: string): Promise<IdeLaunchResult> {
  const { data } = await client.post<IdeLaunchResult>('/api/workspace/open-ide', {
    task_id: taskId,
    ide_id: ideId,
  })
  return data
}

/** 列出系统已安装的 IDE / List installed IDEs */
export async function listIdes(): Promise<{ ides: IdeInfo[] }> {
  const { data } = await client.get<{ ides: IdeInfo[] }>('/api/workspace/ides')
  return data
}

/** 获取全局工作区索引 / Get global workspace index */
export async function listWorkspaceProjects(): Promise<WorkspaceIndex> {
  const { data } = await client.get<WorkspaceIndex>('/api/workspace/projects')
  return data
}

/** 获取项目内会议索引 / Get project meetings index */
export async function listProjectMeetings(projectId: string): Promise<ProjectMeetingsIndex> {
  const { data } = await client.get<ProjectMeetingsIndex>(
    `/api/workspace/project/${encodeURIComponent(projectId)}/meetings`,
  )
  return data
}
