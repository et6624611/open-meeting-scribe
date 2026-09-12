/**
 * 隐私免责声明确认状态管理
 *
 * 管理用户是否已阅读并确认数据安全须知。
 * 确认状态持久化到 localStorage（oms_privacy_ack），刷新后保持。
 */
import { ref } from 'vue'

const STORAGE_KEY = 'oms_privacy_ack'

/** 用户是否已确认隐私免责声明 */
const acknowledged = ref(localStorage.getItem(STORAGE_KEY) === '1')

/** 标记已确认并持久化 */
function acknowledge() {
  acknowledged.value = true
  localStorage.setItem(STORAGE_KEY, '1')
}

export function usePrivacyDisclaimer() {
  return { acknowledged, acknowledge }
}
