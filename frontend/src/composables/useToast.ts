/**
 * Toast 通知 composable — 全局轻量反馈 / Toast notification composable — global lightweight feedback
 * 移植自旧版 showToast(msg, variant) / Ported from legacy showToast(msg, variant)
 */
import { ref } from 'vue'

export type ToastVariant = 'warn' | 'success' | 'error' | 'info'

const message = ref('')
const variant = ref<ToastVariant | ''>('')
const visible = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

export function showToast(msg: string, v?: ToastVariant) {
  message.value = msg
  variant.value = v || ''
  visible.value = true

  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    visible.value = false
  }, 3000)
}

// 挂载到 window 以便非 Vue 上下文也能调用 / Mount to window so non-Vue contexts can also call
if (typeof window !== 'undefined') {
  (window as any).showToast = showToast
}

export function useToast() {
  return { toastMessage: message, toastVariant: variant, toastVisible: visible, showToast }
}
