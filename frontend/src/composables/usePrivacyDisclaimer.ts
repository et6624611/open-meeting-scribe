/**
 * 隐私免责声明确认状态管理（双层留痕）
 *
 * - localStorage 作为通用快速缓存（所有用户），避免每次启动都请求后端
 * - SMS 用户（共享 proxy 体验期）额外写入服务端 users.json，与实名记录绑定
 * - 自带 Key / 本地用户仅 localStorage，因为服务端不经手其音频数据
 */
import { ref } from 'vue'
import { fetchPrivacyConsent, recordPrivacyConsent } from '@/api/auth'

const STORAGE_KEY = 'oms_privacy_ack'

/** 用户是否已确认隐私免责声明（初始为 localStorage 缓存值） */
const acknowledged = ref(localStorage.getItem(STORAGE_KEY) === '1')

/** 服务端是否已记录同意（SMS 用户） */
const serverConsented = ref(false)

/** 初始化：对 SMS 用户检查服务端留痕状态 */
async function init() {
  // localStorage 未确认 → 无需查服务端，直接等用户操作时弹窗
  if (!acknowledged.value) return
  try {
    const res = await fetchPrivacyConsent()
    if (res.consented) {
      serverConsented.value = true
    } else if (res.need_server_consent) {
      // SMS 用户但服务端无记录（可能清过数据库） → 重置状态，下次操作时重新弹窗
      acknowledged.value = false
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // 未登录或网络异常 → 仅依赖 localStorage
  }
}

/** 标记已确认并持久化（SMS 用户写入服务端，其他用户仅 localStorage） */
async function acknowledge() {
  acknowledged.value = true
  localStorage.setItem(STORAGE_KEY, '1')
  try {
    const res = await recordPrivacyConsent()
    if (res.recorded) {
      serverConsented.value = true
    }
  } catch {
    // 非 SMS 用户或服务端异常 → localStorage 已足够
  }
}

export function usePrivacyDisclaimer() {
  return { acknowledged, serverConsented, init, acknowledge }
}
