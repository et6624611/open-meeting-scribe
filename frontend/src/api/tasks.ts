/**
 * 任务 API 封装 / Task API wrapper
 */
import client from './client'
import type { Task } from './types'

/**
 * 获取任务列表 / Fetch task list
 * @param lite 仅状态字段（完成侦测器高频轮询用，响应体小） / status fields only (small payload for watcher polling)
 */
export async function fetchTasks(lite = false): Promise<Task[]> {
  const { data } = await client.get<{ tasks: Task[] }>('/api/tasks', {
    params: lite ? { view: 'lite' } : undefined,
  })
  return data.tasks
}

/** 获取单个任务详情 / Fetch single task detail */
export async function fetchTask(taskId: string): Promise<Task> {
  const { data } = await client.get<Task>(`/api/tasks/${taskId}`)
  return data
}

/** 更新任务（标题/日期/项目关联/一页纸系数） / Update task (title/date/project association/one-page factors) */
export async function updateTask(
  taskId: string,
  patch: { title?: string; meeting_date?: string; project_id?: string; one_page?: { summary?: number; insights?: number } },
): Promise<Task> {
  const { data } = await client.patch<Task>(`/api/tasks/${taskId}`, patch)
  return data
}

/** 删除任务 / Delete task */
export async function deleteTask(taskId: string): Promise<void> {
  await client.delete(`/api/tasks/${taskId}`)
}

/** 重新转写 / Re-transcribe
 *  AC-4（QA-R1 DEF-04）：engineOverride='cloud' 时显式请求切云端重跑，
 *  仅在用户对「数据上云」显式确认后调用，绝不静默上云（PRD R7）。
 *  AC-4: engineOverride='cloud' explicitly re-runs via cloud, only after user confirmation. */
export async function retranscribe(taskId: string, options?: { engineOverride?: 'cloud' }): Promise<void> {
  await client.post(
    `/api/tasks/${taskId}/retranscribe`,
    options?.engineOverride ? { engine_override: options.engineOverride } : undefined,
  )
}

/** 文本回溯修正结果 / Retroactive text-correction result */
export interface CorrectTextResult {
  ok: boolean
  old: string
  new: string
  /** 全部产物的总命中数 / Total hits across every artifact */
  replaced: number
  hits: { task: number; insights: number; board: number; export_md: number }
  /** 任务对象内按键名分布的命中数 / Per-key hit distribution inside the task payload */
  fields: Record<string, number>
  /** 改写后仍残留的处数；> 0 说明后端白名单需补录 / Leftovers: backend whitelist needs a new entry */
  residual: number
  warnings: string[]
}

/** 把一条「误识别→正确文本」映射全量回溯应用到本场会议
 *  Apply one wrong→correct mapping across this meeting (transcript/summary/notes/decisions/board/export). */
export async function correctTaskText(
  taskId: string,
  oldText: string,
  newText: string,
): Promise<CorrectTextResult> {
  const { data } = await client.post<CorrectTextResult>(`/api/tasks/${taskId}/correct-text`, {
    old: oldText,
    new: newText,
  })
  return data
}

/** 纪要下载格式 / Summary export formats */
export type SummaryFormat = 'docx' | 'md'

/** 构造纪要下载 URL（带格式参数，DEF-QA-R1-02）；用于 <a download> 触发浏览器下载
 *  Build summary download URL with format param (DEF-QA-R1-02), for browser download via <a download>. */
export function downloadSummaryUrl(taskId: string, format: SummaryFormat = 'md'): string {
  return `/api/download/${taskId}?format=${format}`
}

/** 重新生成纪要 / Retry summary generation */
export async function retrySummary(taskId: string): Promise<void> {
  await client.post(`/api/tasks/${taskId}/retry-summary`)
}

/** 上传音频并提交转写 / Upload audio and submit transcription */
export async function submitTranscribe(
  file: File,
  options?: { speaker_count?: number; speaker_mapping?: Record<string, string> },
): Promise<Task> {
  const form = new FormData()
  form.append('file', file)
  if (options?.speaker_count) {
    form.append('speaker_count', String(options.speaker_count))
  }
  if (options?.speaker_mapping) {
    form.append('speaker_mapping', JSON.stringify(options.speaker_mapping))
  }
  const { data } = await client.post<Task>('/api/transcribe', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** 归档任务 / Archive task */
export async function archiveTask(taskId: string): Promise<Task> {
  const { data } = await client.post<Task>(`/api/tasks/${taskId}/archive`)
  return data
}

/** 取消归档 / Unarchive */
export async function unarchiveTask(taskId: string): Promise<Task> {
  const { data } = await client.post<Task>(`/api/tasks/${taskId}/unarchive`)
  return data
}

/** 批量归档 / Batch archive */
export async function batchArchiveTasks(taskIds: string[]): Promise<{ archived: number }> {
  const { data } = await client.post<{ archived: number }>('/api/tasks/batch-archive', { task_ids: taskIds })
  return data
}

// ─── 知识库同步 / Knowledge base sync ───

export interface SyncStatus {
  can_sync: boolean
  reason?: string
  project_name?: string
  folders?: Array<{ path: string; subfolder: string; content_types: string[] }>
  is_dirty?: boolean
  last_synced_at?: string | null
  last_modified_at?: string | null
}

export interface SyncResult {
  synced: boolean
  files?: string[]
  message?: string
}

/** 查询任务同步状态 / Query task sync status */
export async function fetchSyncStatus(taskId: string): Promise<SyncStatus> {
  const { data } = await client.get<SyncStatus>(`/api/tasks/${taskId}/sync-status`)
  return data
}

/** 手动触发同步到知识库 / Manually trigger sync to knowledge base */
export async function syncTaskToProject(taskId: string): Promise<SyncResult> {
  const { data } = await client.post<SyncResult>(`/api/tasks/${taskId}/sync-to-project`)
  return data
}
