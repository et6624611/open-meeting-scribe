/**
 * 导入 API 封装 / Import API wrapper
 */
import client from './client'

/** 导入结果 / Import result */
export interface ImportResult {
  task_id: string
  status: string
  import_type: 'audio' | 'transcript' | 'summary' | 'unknown'
  title?: string
  speaker_count?: number
}

/** 重复检测结果 / Duplicate check result */
export interface DuplicateCheckResult {
  is_duplicate: boolean
  existing_task_id?: string
  existing_task_title?: string
  existing_task_date?: string
  existing_task_status?: string
}

/** 检查文件是否已导入过 / Check if file has already been imported */
export async function checkDuplicate(filename: string, fileSize: number): Promise<DuplicateCheckResult> {
  const { data } = await client.post<DuplicateCheckResult>('/api/import/check-duplicate', {
    filename,
    file_size: fileSize,
  })
  return data
}

/** 文件导入 / File import */
export async function importFile(
  file: File,
  options?: { title?: string; project_id?: string },
): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  if (options?.title) form.append('title', options.title)
  if (options?.project_id) form.append('project_id', options.project_id)
  const { data } = await client.post<ImportResult>('/api/import/file', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** 粘贴文字导入 / Paste text import */
export async function importText(
  content: string,
  options?: { title?: string; project_id?: string },
): Promise<ImportResult> {
  const { data } = await client.post<ImportResult>('/api/import/text', {
    content,
    title: options?.title,
    project_id: options?.project_id,
  })
  return data
}
