/**
 * 管理面 API（契约 §1.3，server plane，仅 admin 角色） / Admin-plane API
 * 越权一律 403；不提供任何员工内容读取通道（裁决 QA Q2）。
 */
import client from './client'

/** 实测列表项（BE c23b247 校准）：account 字段名为 login_account；无 last_used_at（P0 以 updated_at 呈现"最近变化"） */
export interface AdminUser {
  user_id: string
  display_name: string
  login_account: string
  phone?: string | null
  role: 'admin' | 'member' | string
  /** active=正常 disabled=已停用 pending=待接受邀请 */
  status: 'active' | 'disabled' | 'pending' | string
  created_at: string
  updated_at: string
}

export interface InviteCodeResult {
  user_id?: string
  invite_code: string
}

export interface AdminUserList {
  users: AdminUser[]
}

export async function adminListUsers(): Promise<AdminUser[]> {
  const { data } = await client.get<AdminUserList>('/api/v1/admin/users')
  return data.users
}

/** 建号 = 占位账号 + 一次性邀请码（明文仅返回一次，无密码经手） */
export async function adminCreateUser(displayName: string, account: string): Promise<InviteCodeResult> {
  const { data } = await client.post<InviteCodeResult>('/api/v1/admin/users', {
    display_name: displayName,
    account,
  })
  return data
}

export async function adminSetUserStatus(userId: string, status: 'active' | 'disabled'): Promise<void> {
  await client.put(`/api/v1/admin/users/${encodeURIComponent(userId)}/status`, { status })
}

/** 重置密码 = 作废旧会话 + 重发邀请码（仍不经手新密码） */
export async function adminResetUser(userId: string): Promise<InviteCodeResult> {
  const { data } = await client.post<InviteCodeResult>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/reset`, {})
  return data
}

/** 整包删除该账号服务端数据（破坏性：二次确认 + 输入账号名，UI 规格 §4） */
export async function adminDeleteUserData(userId: string): Promise<void> {
  await client.delete(`/api/v1/admin/users/${encodeURIComponent(userId)}/data`)
}

export async function adminServiceOpen(open: boolean): Promise<void> {
  await client.post(`/api/v1/admin/instance/${open ? 'open' : 'close'}`, {})
}

/** 实测形状（BE aba84fb/c23b247 校准）：GET 扁平返回且 api_key 永不回显 */
export interface AiSettings {
  enabled: boolean
  base_url: string | null
  model: string | null
  egress_allowlist?: string[]
}

/** PUT 请求体（扁平；api_key 只写不回显，空则不改动已存 Key） */
export interface AiSettingsUpdate {
  enabled: boolean
  base_url?: string
  model?: string
  api_key?: string
}

export async function adminGetAi(): Promise<AiSettings> {
  const { data } = await client.get<AiSettings>('/api/v1/admin/instance/ai')
  return data
}

/** 开启时后端按 base_url 域名逐域加白名单，服务端网络层强制（§1.7） */
export async function adminPutAi(settings: AiSettingsUpdate): Promise<void> {
  await client.put('/api/v1/admin/instance/ai', settings)
}
