/**
 * 录音控制 API 封装
 */
import client from './client'

export interface RecordStartResult {
  task_id: string
  status: string
}

export interface RecordStatusResult {
  recording: boolean
  task_id: string | null
  paused: boolean
  elapsed: number
  orphaned?: boolean
}

export async function startRecord(): Promise<RecordStartResult> {
  const { data } = await client.post<RecordStartResult>('/api/record/start')
  return data
}

export async function stopRecord(notes?: string): Promise<{ task_id: string }> {
  const { data } = await client.post('/api/record/stop', notes ? { notes } : {})
  return data
}

export async function pauseRecord(): Promise<void> {
  await client.post('/api/record/pause')
}

export async function resumeRecord(): Promise<void> {
  await client.post('/api/record/resume')
}

export async function abandonRecord(): Promise<void> {
  await client.post('/api/record/abandon')
}

export async function getRecordStatus(): Promise<RecordStatusResult> {
  const { data } = await client.get<RecordStatusResult>('/api/record/status')
  return data
}

export interface RecoverResult {
  task_id: string
  status: string
}

export async function recoverRecord(): Promise<RecoverResult> {
  const { data } = await client.post<RecoverResult>('/api/record/recover')
  return data
}

// 实时说话人绑定
export async function bindSpeaker(taskId: string, speakerId: number, speakerUuid: string): Promise<void> {
  await client.post('/api/record/bind-speaker', {
    task_id: taskId,
    speaker_id: speakerId,
    speaker_uuid: speakerUuid,
  })
}
