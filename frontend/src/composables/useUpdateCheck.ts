/**
 * 版本检查 composable / Version check composable
 *
 * 职责 / Responsibilities:
 *  - 启动时静默检查新版本（受 featureFlags.update_check 控制） / Silently check for updates on startup (controlled by featureFlags.update_check)
 *  - 提供手动检查入口 / Provide manual check entry point
 *  - 管理更新提示状态 / Manage update notification state
 *  - 根据用户 OS 匹配平台下载链接 / Match platform download URL based on user OS
 */
import { ref, computed } from 'vue'
import { checkForUpdate, fetchCurrentVersion } from '@/api/update'
import type { VersionCheckResult } from '@/api/update'
import { getDownloadPlatform } from '@/utils/platform'

const updateResult = ref<VersionCheckResult | null>(null)
const checking = ref(false)
const dismissed = ref(false)

// 从 localStorage 恢复关闭状态 / Restore dismissed state from localStorage
if (typeof localStorage !== 'undefined') {
  dismissed.value = localStorage.getItem('update_dismissed') === '1'
}

let initialized = false

export function useUpdateCheck() {
  const hasUpdate = computed(() => !!updateResult.value?.update_available)
  const latestVersion = computed(() => updateResult.value?.latest_version || '')
  const currentVersion = computed(() => updateResult.value?.current_version || '')
  const releaseUrl = computed(() => updateResult.value?.release_url || '')
  const checkError = computed(() => updateResult.value?.error || '')

  /**
   * 根据当前用户 OS 匹配对应的下载链接，回退到 release_url / Match download URL by current OS; fallback to release_url.
   */
  const downloadUrl = computed(() => {
    const downloads = updateResult.value?.downloads
    if (downloads) {
      const platform = getDownloadPlatform()
      if (platform && downloads[platform]) {
        return downloads[platform]
      }
    }
    return releaseUrl.value
  })

  /**
   * 当前平台下载按钮显示文字：'Windows' | 'macOS' | '' / Platform label for download button.
   */
  const downloadPlatformLabel = computed(() => {
    const downloads = updateResult.value?.downloads
    if (!downloads) return ''
    const platform = getDownloadPlatform()
    if (platform === 'macos') return 'macOS'
    if (platform === 'windows') return 'Windows'
    return ''
  })

  /**
   * 启动时静默检查（仅当 update_check 开启且未关闭过提示时） /
   * Silent startup check (only when update_check is enabled and notification hasn't been dismissed)
   */
  async function startupCheck(enabled: boolean) {
    if (!enabled || dismissed.value) return
    if (initialized) return
    initialized = true

    try {
      const result = await checkForUpdate(false)
      updateResult.value = result
    } catch {
      // 静默降级，不影响应用使用 / Silent degradation; doesn't affect app usage
    }
  }

  /**
   * 手动检查（强制刷新缓存） / Manual check (force refresh cache)
   */
  async function manualCheck(): Promise<VersionCheckResult> {
    checking.value = true
    try {
      const result = await checkForUpdate(true)
      updateResult.value = result
      return result
    } catch {
      const fallback: VersionCheckResult = {
        current_version: updateResult.value?.current_version || '',
        latest_version: null,
        update_available: false,
        release_url: '',
        downloads: {},
        changelog: '',
        published_at: '',
        checked_at: Date.now() / 1000,
        error: 'network_error',
      }
      updateResult.value = fallback
      return fallback
    } finally {
      checking.value = false
    }
  }

  /**
   * 加载当前版本号（不触发远端检查） / Load current version only (no remote check)
   */
  async function loadCurrentVersion(): Promise<string> {
    try {
      const ver = await fetchCurrentVersion()
      if (!updateResult.value) {
        updateResult.value = {
          current_version: ver,
          latest_version: null,
          update_available: false,
          release_url: '',
          downloads: {},
          changelog: '',
          published_at: '',
          checked_at: 0,
          error: null,
        }
      }
      return ver
    } catch {
      return ''
    }
  }

  function dismiss() {
    dismissed.value = true
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('update_dismissed', '1')
    }
  }

  function resetDismiss() {
    dismissed.value = false
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('update_dismissed')
    }
  }

  return {
    updateResult,
    checking,
    hasUpdate,
    latestVersion,
    currentVersion,
    releaseUrl,
    downloadUrl,
    downloadPlatformLabel,
    checkError,
    dismissed,
    startupCheck,
    manualCheck,
    loadCurrentVersion,
    dismiss,
    resetDismiss,
  }
}
