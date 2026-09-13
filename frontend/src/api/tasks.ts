/**
 * 任务 API 封装
 */
import client from './client'
import type { Task } from './types'

/** 获取任务列表 */
export async function fetchTasks(): Promise<Task[]> {
  const { data } = await client.get<{ tasks: Task[] }>('/api/tasks')
  return data.tasks
}

/** 获取单个任务详情 */
export async function fetchTask(taskId: string): Promise<Task> {
  const { data } = await client.get<Task>(`/api/tasks/${taskId}`)
  return data
}

/** 更新任务（标题/日期/项目关联） */
export async function updateTask(
  taskId: string,
  patch: { title?: string; meeting_date?: string; project_id?: string },
): Promise<Task> {
  const { data } = await client.patch<Task>(`/api/tasks/${taskId}`, patch)
  return data
}

/** 删除任务 */
export async function deleteTask(taskId: string): Promise<void> {
  await client.delete(`/api/tasks/${taskId}`)
}

/** 重新转写 */
export async function retranscribe(taskId: string): Promise<void> {
  await client.post(`/api/tasks/${taskId}/retranscribe`)
}

/** 重新生成纪要 */
export async function retrySummary(taskId: string): Promise<void> {
  await client.post(`/api/tasks/${taskId}/retry-summary`)
}

/** 上传音频并提交转写 */
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

/** 归档任务 */
export async function archiveTask(taskId: string): Promise<Task> {
  const { data } = await client.post<Task>(`/api/tasks/${taskId}/archive`)
  return data
}

/** 取消归档 */
export async function unarchiveTask(taskId: string): Promise<Task> {
  const { data } = await client.post<Task>(`/api/tasks/${taskId}/unarchive`)
  return data
}

/** 批量归档 */
export async function batchArchiveTasks(taskIds: string[]): Promise<{ archived: number }> {
  const { data } = await client.post<{ archived: number }>('/api/tasks/batch-archive', { task_ids: taskIds })
  return data
}
