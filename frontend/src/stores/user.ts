/**
 * 用户状态管理 / User state management
 *
 * 职责 / Responsibilities:
 *  - 登录态检测（/auth/me） / Login state detection (/auth/me)
 *  - 用户信息缓存 / User info caching
 *  - 登出 / Logout
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchMe, logout as apiLogout } from '@/api/auth'
import type { User } from '@/api/types'

export const useUserStore = defineStore('user', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)
  const checked = ref(false) // 是否已完成首次检测 / Whether initial check is complete

  const isLoggedIn = computed(() => !!user.value)
  /** 管理员判定（复用 /auth/me 返回的 role 字段；引擎设置等管理员级配置用，D-R2） / Admin check (reuses role field from /auth/me; for admin-level config like engine settings, D-R2) */
  const isAdmin = computed(() => user.value?.role === 'admin')
  const displayName = computed(() => user.value?.name || '未登录')
  const avatarLetter = computed(() => {
    const name = user.value?.name || ''
    return name.charAt(0).toUpperCase() || '?'
  })

  /** 检测登录态（应用启动时调用一次） / Check login state (called once on app startup) */
  async function checkAuth() {
    loading.value = true
    try {
      user.value = await fetchMe()
    } catch {
      user.value = null
    } finally {
      loading.value = false
      checked.value = true
    }
  }

  /** 登出 / Logout */
  async function logout() {
    try {
      await apiLogout()
    } catch {
      // 即使后端失败，也清除本地状态 / Clear local state even if server fails
    }
    user.value = null
  }

  return { user, loading, checked, isLoggedIn, isAdmin, displayName, avatarLetter, checkAuth, logout }
})
