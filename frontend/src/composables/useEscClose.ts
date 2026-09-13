/**
 * ESC 键关闭弹窗 composable
 *
 * 在 window 上监听 keydown 事件，当弹窗可见时按 ESC 触发关闭回调。
 * 比模板 @keydown.esc 更可靠——不依赖 overlay div 获焦。
 *
 * @param visible - 控制弹窗可见性的 Ref<boolean>
 * @param close   - 关闭回调
 */
import { watch, onUnmounted, type Ref } from 'vue'

export function useEscClose(visible: Ref<boolean>, close: () => void) {
  const handler = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && visible.value) {
      e.stopPropagation()
      close()
    }
  }

  watch(visible, (v) => {
    if (v) {
      window.addEventListener('keydown', handler)
    } else {
      window.removeEventListener('keydown', handler)
    }
  }, { immediate: true })

  onUnmounted(() => {
    window.removeEventListener('keydown', handler)
  })
}
