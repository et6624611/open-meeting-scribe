/**
 * 录音助手本地状态 API（契约 §1.8 v1.1 助手面，local plane，需有效 local_token）
 * 仅 assistant 形态进程挂载；企业浏览器经 OriginRegistry 连本机助手查询。
 */
import { planeClient, ensureLocalPlane, localPlaneError } from './origins'

export interface AssistantState {
  paired: boolean
  server_url: string | null
  paired_user_id: string | null
  device_id: string | null
}

/**
 * W4-03 规则：设备面动作前判助手可达，不发注定 404 的请求。
 * 返回 null = 助手不在场/不可达（调用方呈现引导态）。
 */
export async function getLocalState(): Promise<AssistantState | null> {
  await ensureLocalPlane()
  if (localPlaneError()) return null
  try {
    const { data } = await planeClient('local').get<AssistantState>('/api/local/state')
    return data
  } catch {
    return null
  }
}
