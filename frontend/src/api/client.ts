/**
 * axios 实例 — 统一配置 + 错误处理 / Axios instance — unified config + error handling
 *
 * JWT 认证通过 httpOnly cookie 自动携带，无需手动拦截。 / JWT auth auto-sent via httpOnly cookie, no manual interceptor needed.
 * 请求拦截：自动携带 Accept-Language 头（与 i18n locale 同步）。 / Request interceptor: auto-attach Accept-Language header (synced with i18n locale).
 * 仅处理 JSON 响应的错误格式化。 / Only formats errors for JSON responses.
 */
import axios from 'axios'
import { getLocale } from '@/i18n'
import { isEnterprise } from '@/edition'

const client = axios.create({
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * 企业版会话过期处理（UI 规格 §1）：已登录状态下 API 返回 401
 * → 清登录态并跳登录页（带 expired 提示）。
 * 仅在 user store 判定已登录时触发，避免启动期 /me 探测的 401 造成误跳。
 * Enterprise session-expiry: 401 while logged in → clear state and go to /login?expired=1.
 */
function handleEnterprise401() {
  void (async () => {
    try {
      const { useUserStore } = await import('@/stores/user')
      const userStore = useUserStore()
      if (!userStore.isLoggedIn) return
      userStore.user = null
      userStore.checked = false
      if (!window.location.pathname.startsWith('/login')) {
        window.location.assign('/login?expired=1')
      }
    } catch { /* pinia 未就绪等场景静默 */ }
  })()
}

// 请求拦截：自动携带当前语言偏好 / Request interceptor: auto-attach current language preference
client.interceptors.request.use((config) => {
  config.headers['Accept-Language'] = getLocale().replace('_', '-')
  return config
})

// 响应拦截：统一错误格式 / Response interceptor: unified error format
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (axios.isAxiosError(err)) {
      const status = err.response?.status
      const detail = err.response?.data?.detail || err.message
      // 401 未登录 → 由 user store 处理跳转 / 401 not logged in → handled by user store for redirect
      if (status === 401) {
        // 企业版：已登录态下的 401 = 会话过期，走统一过期跳转（个人版静默交 user store，行为不变）
        if (isEnterprise) handleEnterprise401()
        // 不弹错误提示，静默交给 user store / No error toast; silently delegate to user store
        return Promise.reject(err)
      }
      console.error(`[API] ${status ?? 'NETWORK'}: ${detail}`)
    }
    return Promise.reject(err)
  },
)

export default client

/**
 * 从 API 错误中提取可读消息 / Extract readable message from API error
 *
 * 后端某些端点（如配额不足 402）的 detail 是对象而非字符串，
 * 直接 alert/toast 会显示 [object Object]。此函数统一处理两种格式。
 * Some backend endpoints (e.g. quota exhausted 402) return detail as an object
 * instead of a string; direct alert/toast would show [object Object].
 */
export function extractErrorMessage(err: unknown, fallback = '操作失败'): string {
  const e = err as { response?: { data?: { detail?: unknown; message?: string }; status?: number }; message?: string }
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail !== null) {
    // 配额错误格式：{ error, message, remaining } / Quota error format
    if ('message' in detail && typeof (detail as Record<string, unknown>).message === 'string') {
      return (detail as Record<string, string>).message
    }
  }
  return e?.response?.data?.message || e?.message || fallback
}
