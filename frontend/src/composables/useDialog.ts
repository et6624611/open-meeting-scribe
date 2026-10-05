/**
 * useDialog — 模态对话框焦点管理 / Modal dialog focus management
 *
 * 在 useEscClose 的事件消费之上补齐四件事（此前项目内 8 个弹窗全部缺失）：
 *   1. 打开时把焦点移入对话框（优先第一个可聚焦元素，否则容器自身）；
 *   2. Tab / Shift+Tab 锁定在对话框内循环，不会漏到背景内容；
 *   3. 关闭时把焦点归还给打开它的元素，键盘用户不会回到页面顶部；
 *   4. 组件卸载时清理监听器。
 *
 * Builds on useEscClose's event consumption and adds what all eight dialogs in
 * this project were missing: initial focus, a Tab trap, and focus restore.
 *
 * 用法 / Usage:
 *   const { dialogRef } = useDialog(visible, close)
 *   <div class="x-overlay" data-vue-overlay>
 *     <div ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="xTitle">
 *       <h3 id="xTitle">…</h3>
 * 容器仍需自行声明 role="dialog" / aria-modal / aria-labelledby，
 * 本 composable 只管焦点，不代替语义。
 * The semantic attributes stay in the template; this composable only owns focus.
 */
import { ref, watch, nextTick, onUnmounted, type Ref } from 'vue'
import { useEscClose } from '@/composables/useEscClose'

/** 可聚焦元素集合（排除被禁用与 tabindex="-1" 的） / Focusable selector, minus disabled and programmatic-only targets */
const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])',
  'select:not([disabled])', 'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])', '[contenteditable]:not([contenteditable="false"])',
].join(',')

/** 只保留真正可见的：v-show 隐藏的分支、display:none 的元素都不应参与循环
    Keep only genuinely visible nodes — v-show and display:none branches must not join the cycle */
function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE))
    .filter(el => el.getClientRects().length > 0)
}

export function useDialog(visible: Ref<boolean>, close: () => void) {
  const dialogRef = ref<HTMLElement | null>(null)
  /** 打开对话框的触发元素，关闭时焦点回到它身上 / The element that opened the dialog */
  let opener: HTMLElement | null = null

  function onTabKeydown(e: KeyboardEvent) {
    if (e.key !== 'Tab') return
    const root = dialogRef.value
    if (!root) return
    const items = focusableIn(root)
    if (items.length === 0) {
      e.preventDefault()
      root.focus()
      return
    }
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement as HTMLElement | null
    // 焦点已漏到容器外（例如刚打开、或用鼠标点了背景）→ 直接拉回边界
    // Focus outside the container (not yet moved in, or clicked through) → pull it back
    if (!active || !root.contains(active)) {
      e.preventDefault()
      ;(e.shiftKey ? last : first).focus()
      return
    }
    if (e.shiftKey && active === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  /** v-if 型弹窗关闭时是整组件卸载，watch 收不到 open=false，
      所以焦点归还也要挂在卸载路径上。
      v-if dialogs unmount instead of flipping the ref, so restore on unmount too. */
  let isOpen = false

  watch(visible, async (open) => {
    isOpen = open
    if (open) {
      opener = (document.activeElement as HTMLElement | null) ?? null
      await nextTick()
      const root = dialogRef.value
      if (root) {
        const items = focusableIn(root)
        if (items.length > 0) {
          items[0].focus()
        } else {
          // 无交互元素的纯提示弹窗：焦点落在容器本身以便读屏定位标题
          // Informational dialogs have nothing to focus, so land on the container
          if (!root.hasAttribute('tabindex')) root.setAttribute('tabindex', '-1')
          root.focus()
        }
      }
      document.addEventListener('keydown', onTabKeydown, true)
    } else {
      document.removeEventListener('keydown', onTabKeydown, true)
      // 触发元素可能已随列表重渲染消失（v-if 行内按钮等） / The opener may have unmounted
      if (opener?.isConnected) opener.focus()
      opener = null
    }
  }, { immediate: true })

  useEscClose(visible, close)

  onUnmounted(() => {
    document.removeEventListener('keydown', onTabKeydown, true)
    if (isOpen && opener?.isConnected) opener.focus()
    opener = null
  })

  return { dialogRef }
}
