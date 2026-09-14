/**
 * axios 实例 — 统一配置 + 错误处理 / Axios instance — unified config + error handling
 *
 * JWT 认证通过 httpOnly cookie 自动携带，无需手动拦截。 / JWT auth auto-sent via httpOnly cookie, no manual interceptor needed.
 * 请求拦截：自动携带 Accept-Language 头（与 i18n locale 同步）。 / Request interceptor: auto-attach Accept-Language header (synced with i18n locale).
 * 仅处理 JSON 响应的错误格式化。 / Only formats errors for JSON responses.
 */
import axios from 'axios'
import { getLocale } from '@/i18n'

const client = axios.create({
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

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
        // 不弹错误提示，静默交给 user store / No error toast; silently delegate to user store
        return Promise.reject(err)
      }
      console.error(`[API] ${status ?? 'NETWORK'}: ${detail}`)
    }
    return Promise.reject(err)
  },
)

export default client
