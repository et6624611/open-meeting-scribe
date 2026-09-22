/**
 * ESC 键关闭弹窗 composable / ESC key close modal composable
 *
 * 在 window 上监听 keydown 事件，当弹窗可见时按 ESC 触发关闭回调。 / Listen for keydown on window; trigger close callback when modal is visible and ESC is pressed.
 * 比模板 @keydown.esc 更可靠——不依赖 overlay div 获焦。 / More reliable than template @keydown.esc — doesn't rely on overlay div receiving focus.
 *
 * @param visible - 控制弹窗可见性的 Ref<boolean> / Ref<boolean> controlling modal visibility
 * @param close   - 关闭回调 / Close callback
 */
import { watch, onUnmounted, type Ref } from 'vue'

export function useEscClose(visible: Ref<boolean>, close: () => void) {
  const handler = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && visible.value) {
      // 消费事件：阻止 usePageBack 等页面级 ESC 处理将“关闭浮层”误判为“返回上一页” / Consume event: prevent page-level ESC handlers (usePageBack) from mistaking "close overlay" for "go back"
      e.preventDefault()
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
