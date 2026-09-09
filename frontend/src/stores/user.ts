/**
 * 用户状态管理
 *
 * 职责：
 *  - 登录态检测（/auth/me）
 *  - 用户信息缓存
 *  - 登出
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchMe, logout as apiLogout } from '@/api/auth'
import type { User } from '@/api/types'

export const useUserStore = defineStore('user', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)
  const checked = ref(false) // 是否已完成首次检测

  const isLoggedIn = computed(() => !!user.value)
  const displayName = computed(() => user.value?.name || '未登录')
  const avatarLetter = computed(() => {
    const name = user.value?.name || ''
    return name.charAt(0).toUpperCase() || '?'
  })

  /** 检测登录态（应用启动时调用一次） */
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

  /** 登出 */
  async function logout() {
    try {
      await apiLogout()
    } catch {
      // 即使后端失败，也清除本地状态
    }
    user.value = null
  }

  return { user, loading, checked, isLoggedIn, displayName, avatarLetter, checkAuth, logout }
})
