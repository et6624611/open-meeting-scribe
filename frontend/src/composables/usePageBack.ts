/**
 * 页面级「返回上一页」 composable / Page-level "go back" composable
 *
 * 提供 goBack() 函数：优先 router.back()，history 为空时兖底到首页。 / Provides goBack(): prefers router.back(); falls back to home when history is empty.
 * 同时注册 window 级 ESC 键监听，按 ESC 触发返回。 / Also registers window-level ESC key listener to trigger back navigation.
 * 组件卸载时自动清理监听器。 / Auto-cleans listeners on component unmount.
 *
 * ESC 优先级：浮层（对话框/下拉/弹出菜单/内联编辑）> 页内返回（intercept）> 路由返回。 / ESC priority: overlays > in-page back (intercept) > route back.
 */
import { useRouter } from 'vue-router'
import { onMounted, onUnmounted } from 'vue'

export interface PageBackOptions {
  /**
   * 在触发 router.back() 前先执行的拦截器；返回 true 表示已自行处理 ESC（如详情页先返回列表），不再路由返回。
   * Interceptor run before router.back(); return true to signal ESC was handled locally (e.g. detail → list), skipping route back.
   */
  intercept?: () => boolean
}

export function usePageBack(options: PageBackOptions = {}) {
  const router = useRouter()

  function goBack() {
    // 导航前让触发元素失焦，避免浏览器恢复焦点时激活 :focus-visible 轮廓 / Blur active element before navigation to prevent browser from restoring :focus-visible outline
    ;(document.activeElement as HTMLElement)?.blur?.()
    if (window.history.length > 1) {
      router.back()
    } else {
      router.push('/')
    }
  }

  const onEscKey = (e: KeyboardEvent) => {
    if (e.key !== 'Escape') return
    // 延迟到微任务再返回：让对话框 / 下拉菜单 / 弹出菜单 / 内联编辑等浮层的同步 ESC 处理先执行。
    // 若其中任一浮层已消费该事件（调用 preventDefault），则说明本次 ESC 意在关闭浮层而非返回上一页，跳过导航。
    // Defer to a microtask: lets dialogs / dropdowns / popmenus / inline-edit overlays handle ESC synchronously first.
    // If any overlay consumed the event (preventDefault), this ESC means "close overlay" not "go back", so skip navigation.
    Promise.resolve().then(() => {
      if (e.defaultPrevented) return
      // 详情页等页内层级优先于路由返回 / In-page hierarchy (e.g. detail view) takes precedence over route back
      if (options.intercept && options.intercept()) return
      goBack()
    })
  }

  onMounted(() => window.addEventListener('keydown', onEscKey))
  onUnmounted(() => window.removeEventListener('keydown', onEscKey))

  return { goBack }
}
