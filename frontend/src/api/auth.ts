/**
 * 认证 API 封装 / Authentication API wrapper
 */
import client from './client'
import type { User } from './types'

/** 获取当前登录用户（未登录时抛 401） / Get current logged-in user (throws 401 if not logged in) */
export async function fetchMe(): Promise<User> {
  const { data } = await client.get<User>('/auth/me')
  return data
}

/** 登出 / Logout */
export async function logout(): Promise<void> {
  await client.post('/auth/logout')
}

/** 发送短信验证码 / Send SMS verification code */
export async function smsSend(phone: string): Promise<{ success: boolean; message?: string }> {
  const { data } = await client.post<{ success: boolean; message?: string }>('/auth/sms/send', { phone })
  return data
}

/** 短信验证码核验并登录 / Verify SMS code and log in */
export async function smsVerify(
  phone: string,
  code: string,
): Promise<{ success: boolean; message?: string }> {
  const { data } = await client.post<{ success: boolean; message?: string }>('/auth/sms/verify', {
    phone,
    code,
  })
  return data
}

/** GitHub OAuth 登录 — 直接跳转，不走 axios / GitHub OAuth login — redirect directly, bypass axios */
export function githubLogin(): void {
  window.location.href = '/auth/github'
}

/** 查询隐私同意状态 / Query privacy consent status */
export async function fetchPrivacyConsent(): Promise<{
  consented: boolean
  consented_at: string | null
  need_server_consent: boolean
}> {
  const { data } = await client.get('/auth/privacy-consent')
  return data
}

/** 记录隐私同意（SMS 用户写入服务端留痕） / Record privacy consent (SMS users, persisted server-side) */
export async function recordPrivacyConsent(): Promise<{
  recorded: boolean
  consented_at: string | null
}> {
  const { data } = await client.post('/auth/privacy-consent')
  return data
}
