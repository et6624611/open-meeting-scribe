/**
 * 设备配对 API（契约 §1.8 v1.1，server plane 用户自助面）
 * 档⑦「本机录音助手」状态卡/配对引导/设备管理的数据源。
 */
import client from './client'

/** 实测响应（BE c23b247）：pairing_code + 分钟数口径 */
export interface PairingResult {
  pairing_code: string
  expires_in_minutes: number
}

export interface DeviceInfo {
  device_id: string
  device_name: string
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

/** Web 端发起配对：生成一次性短效配对码（助手在 127.0.0.1 面兑换 device token） */
export async function createPairing(): Promise<PairingResult> {
  const { data } = await client.post<PairingResult>('/api/v1/pairings', {})
  return data
}

/** 本人已绑定设备列表 */
export async function listDevices(): Promise<DeviceInfo[]> {
  const { data } = await client.get<{ devices: DeviceInfo[] }>('/api/v1/devices')
  return data.devices
}

/** 吊销设备（其 outbox 后续重传将 403 device_revoked） */
export async function deleteDevice(deviceId: string): Promise<void> {
  await client.delete(`/api/v1/devices/${encodeURIComponent(deviceId)}`)
}
