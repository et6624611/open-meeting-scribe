/**
 * usePopMenu — 弹出菜单统一封装 / usePopMenu — unified popup menu wrapper
 *
 * 规范来源：docs/design/DESIGN_DECISIONS.md「弹出菜单统一规范」 / Spec source: docs/design/DESIGN_DECISIONS.md "Popup menu unified spec"
 *
 * 职责 / Responsibilities:
 * 1. 智能定位：默认向下弹出；底部空间不足时向上翻转；左右溢出时回缩； / Smart positioning: defaults to downward; flips up when space is insufficient; retracts on left/right overflow;
 *    始终保持 8px 视口边距，任何触发位置都不允许溢出视口。 / Always maintains 8px viewport margin; never overflows viewport.
 * 2. 点击外部关闭：菜单打开期间点击菜单与触发按钮以外的区域自动关闭。 / Click-outside close: clicking outside menu and trigger auto-closes.
 * 3. Esc 关闭。 / Esc close.
 * 4. 打开期间窗口滚动 / 缩放时重新定位，跟随触发按钮。 / Repositions on window scroll/resize while open, follows trigger button.
 * 5. 图层：菜单元素使用 var(--z-popover)，禁止各处自定义 z-index。 / Layer: menu elements use var(--z-popover); no custom z-index allowed.
 *
 * 用法 / Usage:
 *   const menuEl = ref<HTMLElement | null>(null)
 *   const btnEl = ref<HTMLElement | null>(null)
 *   const { visible, toggle, close } = usePopMenu(menuEl, btnEl)
 *   模板 / Template: <button ref="btnEl" @click="toggle">…</button>
 *         <div ref="menuEl" class="pop-menu" :class="{ 'is-open': visible }">…</div>
 */
import { ref, onUnmounted, type Ref } from 'vue'

export interface PopMenuOptions {
  /** 菜单对齐触发按钮的哪一侧，默认 'end'（右对齐，更多按钮的惯例） / Which side to align with trigger; default 'end' (right-aligned, common for action buttons) */
  align?: 'end' | 'start'
  /** 与触发按钮的间距，默认 4px / Gap from trigger button; default 4px */
  gap?: number
  /** 距视口最小边距，默认 8px / Minimum viewport margin; default 8px */
  margin?: number
}

export function usePopMenu(
  menu: Ref<HTMLElement | null>,
  trigger: Ref<HTMLElement | null>,
  options: PopMenuOptions = {},
) {
  const visible = ref(false)
  const gap = options.gap ?? 4
  const margin = options.margin ?? 8

  /** 计算菜单位置：空间不足翻转 + 左右回缩，禁止溢出视口 / Position menu: flip when space insufficient + retract left/right; never overflow viewport */
  function position() {
    const el = menu.value
    const btn = trigger.value
    if (!el || !btn) return
    // nextTick 只等 Vue DOM 更新，不等浏览器布局；必须等 rAF 后测量才可靠 / nextTick only waits for Vue DOM update, not browser layout; must wait for rAF for reliable measurement
    requestAnimationFrame(() => {
      const vw = window.innerWidth
      const vh = window.innerHeight
      const tr = btn.getBoundingClientRect()
      const mw = el.offsetWidth
      const mh = el.offsetHeight
      const spaceBelow = vh - tr.bottom
      const spaceAbove = tr.top

      let top: number
      if (spaceBelow >= mh + gap || spaceBelow >= spaceAbove) {
        top = tr.bottom + gap
      } else {
        top = Math.max(margin, tr.top - mh - gap)
      }

      let left = options.align === 'start' ? tr.left : tr.right - mw
      if (left < margin) left = margin
      if (left + mw > vw - margin) left = vw - mw - margin

      el.style.top = `${top}px`
      el.style.left = `${left}px`
    })
  }

  function onDocClick(e: Event) {
    if (!visible.value) return
    const target = e.target as Node
    if (menu.value?.contains(target) || trigger.value?.contains(target)) return
    close()
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape' && visible.value) {
      // 消费事件：避免页面级 ESC（usePageBack）将“关闭菜单”误判为“返回上一页” / Consume event so page-level ESC (usePageBack) won't mistake "close menu" for "go back"
      e.preventDefault()
      close()
    }
  }

  function onReflow() {
    if (visible.value) position()
  }

  function open() {
    if (visible.value) return
    visible.value = true
    position()
    document.addEventListener('click', onDocClick)
    document.addEventListener('keydown', onKeydown)
    window.addEventListener('scroll', onReflow, true)
    window.addEventListener('resize', onReflow)
  }

  function close() {
    if (!visible.value) return
    visible.value = false
    document.removeEventListener('click', onDocClick)
    document.removeEventListener('keydown', onKeydown)
    window.removeEventListener('scroll', onReflow, true)
    window.removeEventListener('resize', onReflow)
  }

  function toggle() {
    visible.value ? close() : open()
  }

  onUnmounted(close)

  return { visible, open, close, toggle }
}
