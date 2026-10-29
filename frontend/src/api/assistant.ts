/**
 * 录音助手本地状态 API（契约 §1.8 v1.1 助手面 + §7.1 第9条数据目录，local plane，需有效 local_token）
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

// ─── 数据目录（契约 v1.1 §7.1 第9条，commit 77765aa） ───

export interface LocalStorageInfo {
  data_dir: string
  total_bytes: number
  recordings_bytes: number
  tasks_files: number
  writable: boolean
  disk_free_bytes: number
}

export interface MigrateResult {
  status: 'migrated' | 'skip_identical' | string
  activation?: string
  [k: string]: unknown
}

export async function getLocalStorage(): Promise<LocalStorageInfo | null> {
  await ensureLocalPlane()
  if (localPlaneError()) return null
  try {
    const { data } = await planeClient('local').get<LocalStorageInfo>('/api/local/storage')
    return data
  } catch {
    return null
  }
}

/** 复制-校验-保留源，幂等重跑 skip_identical；嵌套目录/同目录 422 migrate_rejected。
 *  边界（后端如实披露）：迁移完成后真正切换=重启助手进程注入 OMS_DATA_ROOT——界面按
 *  "迁移完成，重启助手后生效"呈现，不写成即时切换（措辞终稿待产品经理裁决）。 */
export async function migrateLocalStorage(targetDir: string): Promise<MigrateResult> {
  const { data } = await planeClient('local').post<MigrateResult>('/api/local/storage/migrate', { target_dir: targetDir })
  return data
}
