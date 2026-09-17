/**
 * 录音控制 API 封装 / Recording control API wrapper
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

// 实时说话人绑定 / Realtime speaker binding
export async function bindSpeaker(taskId: string, speakerId: number, speakerUuid: string): Promise<void> {
  await client.post('/api/record/bind-speaker', {
    task_id: taskId,
    speaker_id: speakerId,
    speaker_uuid: speakerUuid,
  })
}

// ── 录音设备管理 / Recording device management ──

export interface AudioDevice {
  index: number
  name: string
  type: string
}

export interface AudioDevicesResult {
  devices: AudioDevice[]
  current_device: string
  platform: string
  auto_detect: boolean
  ffmpeg_available: boolean
}

/** 获取可用音频输入设备列表 / Get available audio input devices */
export async function fetchAudioDevices(): Promise<AudioDevicesResult> {
  const { data } = await client.get<AudioDevicesResult>('/api/record/devices')
  return data
}

/** 设置录音设备 / Set recording device */
export async function setRecordDevice(device: string): Promise<{ device: string; auto_detect: boolean }> {
  const { data } = await client.post<{ device: string; auto_detect: boolean }>('/api/record/device', { device })
  return data
}
