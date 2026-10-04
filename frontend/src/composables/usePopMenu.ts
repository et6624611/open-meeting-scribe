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
 * 6. 可访问性：暴露 triggerAttrs / menuAttrs 供 v-bind，提供 aria-haspopup /
 *    aria-expanded / role="menu"，并支持 ↑↓ / Home / End / Enter / Esc 键盘导航。
 *    Exposes triggerAttrs / menuAttrs for v-bind plus full keyboard navigation.
 *
 * 用法 / Usage:
 *   const menuEl = ref<HTMLElement | null>(null)
 *   const btnEl = ref<HTMLElement | null>(null)
 *   const { visible, toggle, triggerAttrs, menuAttrs } = usePopMenu(menuEl, btnEl)
 *   模板 / Template: <button ref="btnEl" v-bind="triggerAttrs" @click="toggle">…</button>
 *         <div ref="menuEl" v-bind="menuAttrs" class="pop-menu" :class="{ 'is-open': visible }">…</div>
 *   菜单项需带 role="menuitem"；非原生可聚焦元素（div）由本 composable 临时补 tabindex。
 *   Items need role="menuitem"; non-native ones get a programmatic tabindex.
 */
import { computed, onUnmounted, ref, type Ref } from 'vue'
import { getDockBounds, positionDropdown } from '@/utils/popoverPosition'

export interface PopMenuOptions {
  /** 菜单对齐触发按钮的哪一侧，默认 'end'（右对齐，更多按钮的惯例） / Which side to align with trigger; default 'end' (right-aligned, common for action buttons) */
  align?: 'end' | 'start'
  /** 与触发按钮的间距，默认 4px / Gap from trigger button; default 4px */
  gap?: number
  /** 距视口最小边距，默认 8px / Minimum viewport margin; default 8px */
  margin?: number
}

/** 实例序号，保证 aria-controls 指向的 id 全局唯一 / Instance counter so aria-controls ids stay unique */
let popMenuUid = 0

export function usePopMenu(
  menu: Ref<HTMLElement | null>,
  trigger: Ref<HTMLElement | null>,
  options: PopMenuOptions = {},
) {
  const visible = ref(false)
  const gap = options.gap ?? 4
  const margin = options.margin ?? 8
  const menuId = `oms-popmenu-${++popMenuUid}`
  /** 是否由键盘打开：决定是否移动焦点与关闭后归还 / Opened by keyboard? Drives focus move and restore */
  let lastOpenedByKeyboard = false

  /** role="menuitem" 项集合，跳过禁用与不可见项 / Visible, enabled menu items */
  function menuItems(): HTMLElement[] {
    const root = menu.value
    if (!root) return []
    return Array.from(root.querySelectorAll<HTMLElement>('[role="menuitem"]'))
      .filter(el => !el.hasAttribute('disabled') && el.getClientRects().length > 0)
  }

  /** div 等非原生可聚焦元素临时补 tabindex="-1"，无需改动消费方模板
      Give non-native items a programmatic tabindex so call sites need no change */
  function focusItem(el: HTMLElement) {
    if (!el.matches('button, a[href], input, select, textarea') && el.tabIndex < 0) el.tabIndex = -1
    el.focus()
  }

  /** 计算菜单位置：空间不足翻转 + 左右回缩，禁止溢出视口与停靠栏 / Position menu: flip when space insufficient; never overflow viewport or docks */
  function position() {
    // nextTick 只等 Vue DOM 更新，不等浏览器布局；必须等 rAF 后测量才可靠 / nextTick only waits for Vue DOM update, not browser layout; must wait rAF for reliable measurement
    requestAnimationFrame(() => {
      if (!menu.value || !trigger.value) return
      const tr = trigger.value.getBoundingClientRect()
      const { x, y } = positionDropdown(
        { top: tr.top, left: tr.left, width: tr.width, height: tr.height },
        menu.value.offsetWidth,
        menu.value.offsetHeight,
        getDockBounds(),
        { gap, margin, align: options.align ?? 'end' },
      )
      menu.value.style.top = `${y}px`
      menu.value.style.left = `${x}px`
    })
  }

  function onDocClick(e: Event) {
    if (!visible.value) return
    const target = e.target as Node
    if (menu.value?.contains(target) || trigger.value?.contains(target)) return
    close()
  }

  /** 键盘导航：单一 document 监听，避免与 Esc 处理分离造成状态不一致
      One document keydown listener shared by Esc and roving arrow navigation. */
  function onKeydown(e: KeyboardEvent) {
    if (!visible.value) return
    const list = menuItems()
    const active = document.activeElement as HTMLElement | null
    const idx = active ? list.indexOf(active) : -1

    switch (e.key) {
      case 'Escape':
        // 消费事件：避免页面级 ESC（usePageBack）将“关闭菜单”误判为“返回上一页” / Consume event so page-level ESC (usePageBack) won't mistake "close menu" for "go back"
        e.preventDefault()
        close()
        if (lastOpenedByKeyboard) trigger.value?.focus()
        return
      case 'Tab':
        close()
        return
      case 'ArrowDown':
        if (!list.length) return
        e.preventDefault()
        focusItem(list[(idx + 1) % list.length])
        return
      case 'ArrowUp':
        if (!list.length) return
        e.preventDefault()
        focusItem(list[(idx - 1 + list.length) % list.length])
        return
      case 'Home':
        if (idx < 0) return
        e.preventDefault()
        focusItem(list[0])
        return
      case 'End':
        if (idx < 0) return
        e.preventDefault()
        focusItem(list[list.length - 1])
        return
    }
  }

  function onReflow() {
    if (visible.value) position()
  }

  function open() {
    if (visible.value) return
    // 用 :focus-visible 判定键盘打开，鼠标点击不抢焦点（会在 rAF 定位后移动）
    // Detect keyboard activation via :focus-visible so mouse clicks don't steal focus
    lastOpenedByKeyboard = !!trigger.value?.matches(':focus-visible')
    visible.value = true
    position()
    if (lastOpenedByKeyboard) {
      const list = menuItems()
      if (list.length) requestAnimationFrame(() => focusItem(list[0]))
    }
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

  const triggerAttrs = computed(() => ({
    'aria-haspopup': 'menu' as const,
    'aria-expanded': visible.value,
    'aria-controls': menuId,
  }))

  const menuAttrs = computed(() => ({
    id: menuId,
    role: 'menu' as const,
  }))

  onUnmounted(close)

  return { visible, open, close, toggle, triggerAttrs, menuAttrs }
}
