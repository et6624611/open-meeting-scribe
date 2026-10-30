/**
 * 企业版账号面 API（契约 §1.2 / §1.6，v1.0 冻结） / Enterprise account API
 *
 * 服务端命名空间 /api/v1/*；会话为 httpOnly JWT cookie（复用现有 client 的相对路径直连）。
 * 错误体统一 { error: { code, message } }；机器码是 UI 分支的判定依据。
 */
import client from './client'

/** 契约内账号面机器码 / Machine error codes defined by the frozen contract */
export type EnterpriseAuthErrorCode =
  | 'password_not_set'
  | 'service_closed'
  | 'account_disabled'
  | 'bad_credentials'
  | 'unauthenticated'
  | 'invite_invalid'
  | 'activation_failed'
  | 'bootstrap_loopback_only'
  | 'bootstrap_done'
  | 'invalid_admin'
  | string

/** /me 全量返回；login/activate 响应实测仅 {user_id, display_name, role}——其余字段可选（2026-10-29 联调校准） */
export interface EnterpriseMe {
  user_id: string
  display_name: string
  role: 'admin' | 'member' | string
  status?: 'active' | 'disabled' | 'pending' | string
  tenant_id?: string | null
}

export interface InstanceInfo {
  product: string
  version: string
  service_open: boolean
  ai_enabled: boolean
  needs_bootstrap: boolean
}

/** 从 axios 错误中提取契约机器码；无契约错误体时返回 null / Extract contract error code, null if absent */
export function authErrorCode(err: unknown): EnterpriseAuthErrorCode | null {
  const data = (err as { response?: { data?: { error?: { code?: string } } } })?.response?.data
  return data?.error?.code ?? null
}

/** 账号密码登录 / Login with account + password */
export async function enterpriseLogin(account: string, password: string): Promise<EnterpriseMe> {
  const { data } = await client.post<EnterpriseMe>('/api/v1/auth/login', { account, password })
  return data
}

/** 邀请码自助设密码 + 激活 + 建会话（无初始密码环节，裁决插单③） */
export async function enterpriseActivate(inviteCode: string, password: string): Promise<EnterpriseMe> {
  const { data } = await client.post<EnterpriseMe>('/api/v1/auth/activate', {
    invite_code: inviteCode,
    password,
  })
  return data
}

/** 当前用户 / Current user */
export async function enterpriseFetchMe(): Promise<EnterpriseMe> {
  const { data } = await client.get<EnterpriseMe>('/api/v1/auth/me')
  return data
}

/** 清会话 / Logout */
export async function enterpriseLogout(): Promise<void> {
  await client.post('/api/v1/auth/logout')
}

/** 主动改密（验证旧密码） / Change password with old-password check */
export async function enterpriseChangePassword(oldPassword: string, newPassword: string): Promise<void> {
  await client.post('/api/v1/auth/change-password', { old_password: oldPassword, new_password: newPassword })
}

/**
 * 首个管理员产品内 bootstrap（D005 契约 34ed119）：仅服务器本机回环 + 零 admin 实例可用；
 * 建 pending admin + 一次性邀请码，密码由本人经 activate 自设（无密码下发纪律不变）。
 * 完成即 409 bootstrap_done 永久关闭；X05 纪律：界面不得出现命令行引导。
 */
export interface BootstrapResult {
  user_id: string
  invite_code: string
  next?: string
}

export async function bootstrapCreateAdmin(input: { display_name: string; account: string }): Promise<BootstrapResult> {
  const { data } = await client.post<BootstrapResult>('/api/v1/auth/bootstrap', input)
  return data
}

/** 免登录实例信息（登录页服务暂停拦截横幅与 AI 开关态依赖，§1.6） */
export async function fetchInstanceInfo(): Promise<InstanceInfo> {
  const { data } = await client.get<InstanceInfo>('/api/v1/instance/info')
  return data
}
