/**
 * 页面级「返回上一页」composable
 *
 * 提供 goBack() 函数：优先 router.back()，history 为空时兜底到首页。
 * 同时注册 window 级 ESC 键监听，按 ESC 触发返回。
 * 组件卸载时自动清理监听器。
 */
import { useRouter } from 'vue-router'
import { onMounted, onUnmounted } from 'vue'

export function usePageBack() {
  const router = useRouter()

  function goBack() {
    // 导航前让触发元素失焦，避免浏览器恢复焦点时激活 :focus-visible 轮廓
    ;(document.activeElement as HTMLElement)?.blur?.()
    if (window.history.length > 1) {
      router.back()
    } else {
      router.push('/')
    }
  }

  const onEscKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') goBack()
  }

  onMounted(() => window.addEventListener('keydown', onEscKey))
  onUnmounted(() => window.removeEventListener('keydown', onEscKey))

  return { goBack }
}
