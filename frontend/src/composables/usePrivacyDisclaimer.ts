/**
 * 隐私免责声明确认状态管理（双层留痕） / Privacy disclaimer consent state management (dual-layer record)
 *
 * - localStorage 作为通用快速缓存（所有用户），避免每次启动都请求后端 / localStorage as universal fast cache (all users); avoids backend request on every startup
 * - SMS 用户（共享 proxy 体验期）额外写入服务端 users.json，与实名记录绑定 / SMS users (shared proxy trial) also write to server users.json, bound to real-name record
 * - 自带 Key / 本地用户仅 localStorage，因为服务端不经手其音频数据 / BYOK / local users: localStorage only; server doesn't handle their audio data
 */
import { ref } from 'vue'
import { fetchPrivacyConsent, recordPrivacyConsent } from '@/api/auth'

const STORAGE_KEY = 'oms_privacy_ack'

/** 用户是否已确认隐私免责声明（初始为 localStorage 缓存值） / Whether user has acknowledged privacy disclaimer (initially from localStorage cache) */
const acknowledged = ref(localStorage.getItem(STORAGE_KEY) === '1')

/** 服务端是否已记录同意（SMS 用户） / Whether server has recorded consent (SMS users) */
const serverConsented = ref(false)

/** 初始化：对 SMS 用户检查服务端留痕状态 / Init: check server-side record for SMS users */
async function init() {
  // localStorage 未确认 → 无需查服务端，直接等用户操作时弹窗 / localStorage not confirmed → no need to check server; wait for user action to show modal
  if (!acknowledged.value) return
  try {
    const res = await fetchPrivacyConsent()
    if (res.consented) {
      serverConsented.value = true
    } else if (res.need_server_consent) {
      // SMS 用户但服务端无记录（可能清过数据库） → 重置状态，下次操作时重新弹窗 / SMS user but no server record (DB may have been cleared) → reset; re-show modal on next action
      acknowledged.value = false
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // 未登录或网络异常 → 仅依赖 localStorage / Not logged in or network error → rely on localStorage only
  }
}

/** 标记已确认并持久化（SMS 用户写入服务端，其他用户仅 localStorage） / Mark acknowledged and persist (SMS users write to server; others localStorage only) */
async function acknowledge() {
  acknowledged.value = true
  localStorage.setItem(STORAGE_KEY, '1')
  try {
    const res = await recordPrivacyConsent()
    if (res.recorded) {
      serverConsented.value = true
    }
  } catch {
    // 非 SMS 用户或服务端异常 → localStorage 已足够 / Non-SMS user or server error → localStorage is sufficient
  }
}

export function usePrivacyDisclaimer() {
  return { acknowledged, serverConsented, init, acknowledge }
}
