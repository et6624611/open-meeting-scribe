/**
 * 认证 API 封装
 */
import client from './client'
import type { User } from './types'

/** 获取当前登录用户（未登录时抛 401） */
export async function fetchMe(): Promise<User> {
  const { data } = await client.get<User>('/auth/me')
  return data
}

/** 登出 */
export async function logout(): Promise<void> {
  await client.post('/auth/logout')
}

/** 发送短信验证码 */
export async function smsSend(phone: string): Promise<{ success: boolean; message?: string }> {
  const { data } = await client.post<{ success: boolean; message?: string }>('/auth/sms/send', { phone })
  return data
}

/** 短信验证码核验并登录 */
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

/** GitHub OAuth 登录 — 直接跳转，不走 axios */
export function githubLogin(): void {
  window.location.href = '/auth/github'
}
