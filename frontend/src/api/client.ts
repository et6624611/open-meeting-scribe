/**
 * axios 实例 — 统一配置 + 错误处理
 *
 * JWT 认证通过 httpOnly cookie 自动携带，无需手动拦截。
 * 仅处理 JSON 响应的错误格式化。
 */
import axios from 'axios'

const client = axios.create({
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// 响应拦截：统一错误格式
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (axios.isAxiosError(err)) {
      const status = err.response?.status
      const detail = err.response?.data?.detail || err.message
      // 401 未登录 → 由 user store 处理跳转
      if (status === 401) {
        // 不弹错误提示，静默交给 user store
        return Promise.reject(err)
      }
      console.error(`[API] ${status ?? 'NETWORK'}: ${detail}`)
    }
    return Promise.reject(err)
  },
)

export default client
