/**
 * useDropdownPopup — 弹出类选择组件统一交互规范 / Unified interaction spec for dropdown popups
 *
 * 规范来源：docs/design/DESIGN_DECISIONS.md「弹出菜单统一规范」的选择类补充（2026-09-24 用户反馈 C1/C2）。
 * Spec source: selection-popup supplement to the popup spec (user feedback C1/C2, 2026-09-24).
 *
 * 与 usePopMenu 的分工：usePopMenu 服务 role="menu" 的动作菜单（自带定位）；
 * 本 composable 服务「选择类」下拉/浮层（列表选择、可带检索输入框），不接管定位。
 * Division of labor: usePopMenu is for action menus; this one is for selection
 * dropdowns/popovers (option lists, optionally with a search input) and does not position.
 *
 * 落地的规范 / Enforced spec:
 * 1. 点击外部关闭：弹层与触发元素以外的点击自动关闭。 / Click-outside closes.
 * 2. 键盘导航：↑↓ 循环高亮候选项，Enter 激活高亮项（无高亮时激活第一项），Esc 关闭。
 *    Keyboard: ↑↓ cycle highlight, Enter activates highlighted (or first) item, Esc closes.
 * 3. 检索后焦点保持在输入框：高亮用 class 而非焦点迁移；弹层内 mousedown 不抢焦点。
 *    Focus stays in the search input: highlight via class, mousedown inside never steals focus.
 * 4. 过滤自适应：候选项被检索过滤后高亮索引自动失效重算，无需消费方干预。
 *    Filtering-safe: stale highlight index is revalidated against the live DOM on each key.
 *
 * 用法 / Usage:
 *   - 弹层容器绑定 ref="root"，候选项加 data-dd-item 属性。
 *     Bind root ref on the popup container; mark options with data-dd-item.
 *   - 自带 Enter 语义的输入框（如就地新建）加 data-dd-enter="native"，本 composable 不劫持其 Enter。
 *     Inputs with their own Enter semantics opt out via data-dd-enter="native".
 *   - 已有完整键盘导航的弹层可传 keyboard: false，仅补点击外部关闭。
 *     Popups that already implement keyboard nav pass keyboard: false for click-outside only.
 */
import { nextTick, onUnmounted, watch, type Ref } from 'vue'

export interface DropdownPopupOptions {
  /** 弹层是否打开（消费方持有状态） / Whether the popup is open (state owned by consumer) */
  isOpen: () => boolean
  /** 关闭弹层（点击外部 / Esc 时调用） / Close the popup (called on outside click / Esc) */
  close: () => void
  /** 弹层容器 / Popup container element */
  root: Ref<HTMLElement | null>
  /** 触发元素：其上的点击不算「外部」（触发元素自带 @click.stop 时可省略）
      Trigger element: clicks on it are not "outside" (omit when trigger already stops propagation) */
  trigger?: Ref<HTMLElement | null>
  /** 打开后自动聚焦的元素（通常为检索输入框） / Element auto-focused on open (usually the search input) */
  autoFocus?: Ref<HTMLElement | null>
  /** 候选项选择器，默认 '[data-dd-item]' / Option selector, default '[data-dd-item]' */
  itemSelector?: string
  /** 高亮 class，默认 'is-nav-active'（全局样式见 shared-list.css） / Highlight class (global style in shared-list.css) */
  activeClass?: string
  /** 是否接管键盘导航，默认 true；已有自有导航的弹层传 false / Own keyboard nav? default true */
  keyboard?: boolean
}

export function useDropdownPopup(opts: DropdownPopupOptions) {
  const itemSelector = opts.itemSelector ?? '[data-dd-item]'
  const activeClass = opts.activeClass ?? 'is-nav-active'
  const keyboard = opts.keyboard ?? true
  /** 当前高亮索引（-1 = 无高亮） / Current highlight index (-1 = none) */
  let activeIndex = -1

  function items(): HTMLElement[] {
    const root = opts.root.value
    if (!root) return []
    return Array.from(root.querySelectorAll<HTMLElement>(itemSelector))
      .filter(el => !el.hasAttribute('disabled') && el.getClientRects().length > 0)
  }

  /** 校验高亮索引：检索过滤可能已移除对应节点 / Revalidate index: filtering may have removed the node */
  function validateActive(list: HTMLElement[]) {
    if (activeIndex < 0) return
    const el = list[activeIndex]
    if (!el || !el.isConnected) clearActive()
  }

  function clearActive() {
    const root = opts.root.value
    root?.querySelectorAll(`.${activeClass}`).forEach(el => el.classList.remove(activeClass))
    activeIndex = -1
  }

  function setActive(idx: number) {
    const list = items()
    if (!list.length) return
    clearActive()
    activeIndex = ((idx % list.length) + list.length) % list.length
    const el = list[activeIndex]
    el.classList.add(activeClass)
    el.scrollIntoView({ block: 'nearest' })
  }

  /** 供消费方在自有状态变化时主动清除高亮 / Consumers may clear highlight on their own state changes */
  function resetNav() { clearActive() }

  function activateCurrent(e: KeyboardEvent) {
    // 自带 Enter 语义的输入框（就地新建等）不被劫持 / Inputs with native Enter semantics are not hijacked
    const target = e.target as HTMLElement | null
    if (target?.closest('[data-dd-enter="native"]')) return
    const list = items()
    validateActive(list)
    if (!list.length) return
    e.preventDefault()
    const el = activeIndex >= 0 ? list[activeIndex] : list[0]
    clearActive()
    el?.click()
  }

  function onDocClick(e: Event) {
    if (!opts.isOpen()) return
    const target = e.target as Node
    if (opts.root.value?.contains(target) || opts.trigger?.value?.contains(target)) return
    opts.close()
  }

  function onDocKeydown(e: KeyboardEvent) {
    if (!opts.isOpen() || !keyboard) return
    switch (e.key) {
      case 'Escape':
        // 消费事件：避免页面级 ESC 把「关弹层」误判为其它动作 / Consume so page-level Esc handlers don't double-fire
        e.preventDefault()
        opts.close()
        return
      case 'Tab':
        opts.close()
        return
      case 'ArrowDown': {
        e.preventDefault()
        const list = items()
        validateActive(list)
        setActive(activeIndex + 1)
        return
      }
      case 'ArrowUp': {
        e.preventDefault()
        const list = items()
        validateActive(list)
        setActive(activeIndex - 1)
        return
      }
      case 'Enter':
        activateCurrent(e)
        return
    }
  }

  /** 弹层内 mousedown 不移动焦点：检索输入框保持焦点（规范第 3 条）；输入框自身除外
      Mousedown inside never moves focus, so the search input keeps it (spec #3); inputs exempt */
  function onRootMousedown(e: MouseEvent) {
    const target = e.target as HTMLElement | null
    if (target?.closest('input, textarea, [contenteditable="true"]')) return
    e.preventDefault()
  }

  let attached = false
  function attach() {
    if (attached) return
    attached = true
    document.addEventListener('click', onDocClick)
    if (keyboard) document.addEventListener('keydown', onDocKeydown)
    const root = opts.root.value
    root?.addEventListener('mousedown', onRootMousedown)
  }

  function detach() {
    if (!attached) return
    attached = false
    document.removeEventListener('click', onDocClick)
    document.removeEventListener('keydown', onDocKeydown)
    opts.root.value?.removeEventListener('mousedown', onRootMousedown)
    clearActive()
  }

  watch(
    () => opts.isOpen(),
    open => {
      if (open) {
        // 等 v-if 渲染出容器后再挂监听与聚焦 / Attach listeners and focus after v-if renders the container
        nextTick(() => {
          attach()
          opts.autoFocus?.value?.focus()
        })
      } else {
        detach()
      }
    },
    { immediate: true }
  )

  onUnmounted(detach)

  return { resetNav }
}
