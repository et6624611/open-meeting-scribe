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
  /** UI 选中的条目值（空串=自动，__system__=系统内录，否则是设备名）/ Entry value currently selected in the UI */
  current_entry: string
  /** 生效来源：settings / env / platform-default / Where the effective device came from */
  effective_source: string
  platform: string
  auto_detect: boolean
  ffmpeg_available: boolean
  /** 模态框候选条目列表 / Candidate entries for the modal list UI */
  entries: EntryItem[]
}

export interface EntryItem {
  value: string
  label: 'auto' | 'system' | 'device'
  title: string
  subtitle: string
  platform: string | null
}

/** 获取可用音频输入设备列表 + 当前配置 + 候选条目 / Get audio devices + current config + UI entries */
export async function fetchAudioDevices(): Promise<AudioDevicesResult> {
  const { data } = await client.get<AudioDevicesResult>('/api/record/devices')
  return data
}

/**
 * 设置录音来源。device 可以是设备名字符串，也可以是保留值：
 * "" = 自动选择，"__system__" = macOS 系统内录。
 * Set recording source. Device may be a concrete device name or a sentinel value:
 * "" = auto-select, "__system__" = macOS system audio capture.
 */
export async function setRecordDevice(
  device: string,
): Promise<{ device: string; entry: string; auto_detect: boolean }> {
  const { data } = await client.post<{ device: string; entry: string; auto_detect: boolean }>(
    '/api/record/device',
    { device },
  )
  return data
}
