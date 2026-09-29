/**
 * useSlashDateMenu — 决策文本输入的斜杠日期候选菜单核心逻辑
 *
 * 键入 `/`（行首或空白后）在光标处弹出日期候选列表，随后续输入按前缀过滤，
 * ↑↓/Home/End 移动高亮、Enter/Tab 选中并在光标处插入展开后的日期、ESC 仅关菜单。
 * 与 dateShortcuts 的空格自动展开并存：完整触发词 + 空格仍即时展开（token 被消费后菜单自然关闭）。
 *
 * 宿主用法 / Host usage:
 *   const menu = useSlashDateMenu(() => textareaEl)
 *   <div class="slash-host" style="position:relative">
 *     <textarea @input="...; menu.onInput()" @keydown="menu.onKeydown" @blur="menu.onBlur">
 *     <SlashDateMenu v-bind="menu" @select="menu.select" />
 *   </div>
 */
import { computed, nextTick, onUnmounted, ref } from 'vue'
import {
  detectSlashQuery,
  expandToken,
  filterDateMenuItems,
} from '@/utils/dateShortcuts'
import { getCaretCoordinates } from '@/utils/textareaCaret'

export interface SlashMenuItem { token: string; key: string; preview: string }

// 菜单行高估算（用于上翻判定，无需测量真实 DOM）/ row height estimate for flip decision
const ROW_H = 30
const MENU_PAD = 12

export function useSlashDateMenu(getEl: () => HTMLTextAreaElement | null) {
  const open = ref(false)
  const query = ref('')
  const activeIndex = ref(0)
  // 菜单位置（相对最近定位祖先 = textarea 的父容器）
  const pos = ref({ left: 0, top: 0 })
  let tokenStart = -1 // 斜杠在 value 中的下标

  const items = computed<SlashMenuItem[]>(() =>
    filterDateMenuItems(query.value).map(it => ({ ...it, preview: expandToken(it.token) ?? '' })))

  function close() {
    open.value = false
    query.value = ''
    activeIndex.value = 0
    tokenStart = -1
  }

  /** 依据 textarea 光标坐标重算菜单落位（含底部空间不足时上翻） */
  function reposition() {
    const el = getEl()
    const wrapper = el?.parentElement
    if (!el || !wrapper) return
    const caretIdx = el.selectionStart ?? el.value.length
    const caret = getCaretCoordinates(el, caretIdx)
    const elRect = el.getBoundingClientRect()
    const wrapRect = wrapper.getBoundingClientRect()
    const style = window.getComputedStyle(el)
    const lineH = parseFloat(style.lineHeight) || parseFloat(style.fontSize) || 18
    const left = (elRect.left - wrapRect.left) + caret.left
    const caretTop = (elRect.top - wrapRect.top) + caret.top
    const menuH = items.value.length * ROW_H + MENU_PAD
    // 默认向下（贴当前行下方）；若溢出视口底部且上方空间更大则上翻到光标行上方
    const spaceBelow = window.innerHeight - (elRect.top + caretTop + lineH)
    let top = caretTop + lineH
    if (spaceBelow < menuH + 8 && caretTop > menuH) {
      top = caretTop - menuH
    }
    pos.value = { left, top }
  }

  /** input 后重新检测是否处于 /query 输入态并刷新菜单（在 handleDateShortcut 之后调用） */
  function onInput() {
    const el = getEl()
    if (!el) { close(); return }
    const caret = el.selectionStart ?? el.value.length
    const det = detectSlashQuery(el.value, caret)
    if (!det) { close(); return }
    tokenStart = det.start
    query.value = det.query
    const filtered = filterDateMenuItems(det.query)
    if (filtered.length === 0) { open.value = false; return }
    if (activeIndex.value >= filtered.length) activeIndex.value = 0
    open.value = true
    void nextTick(reposition)
  }

  function move(delta: number) {
    const n = items.value.length
    if (n === 0) return
    activeIndex.value = (activeIndex.value + delta + n) % n
  }

  /** 选中第 idx 项：删除光标前的 /query，替换为展开后的日期 */
  function select(idx: number) {
    const el = getEl()
    const item = items.value[idx]
    if (!el || !item || tokenStart < 0) return
    const dateText = expandToken(item.token)
    if (!dateText) { close(); return }
    const caret = el.selectionStart ?? el.value.length
    el.value = el.value.slice(0, tokenStart) + dateText + el.value.slice(caret)
    const posAfter = tokenStart + dateText.length
    el.focus()
    el.setSelectionRange(posAfter, posAfter)
    // 触发 input 让宿主 v-model / :value+@input 同步（本次不再构成 /query，菜单关闭）
    el.dispatchEvent(new Event('input', { bubbles: true }))
    close()
  }

  function onKeydown(e: KeyboardEvent) {
    if (!open.value) return
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); move(1); break
      case 'ArrowUp': e.preventDefault(); move(-1); break
      case 'Home': e.preventDefault(); activeIndex.value = 0; break
      case 'End': e.preventDefault(); activeIndex.value = Math.max(0, items.value.length - 1); break
      case 'Tab': e.preventDefault(); select(activeIndex.value); break
      case 'Enter':
        // 带修饰键（Cmd/Ctrl）的 Enter 属保存链路，放行不拦截
        if (e.metaKey || e.ctrlKey) return
        e.preventDefault()
        select(activeIndex.value)
        break
      case 'Escape':
        // 消费事件：仅关菜单，不外溢到 useEscClose(editing) / 页面级返回
        e.preventDefault()
        e.stopPropagation()
        close()
        break
      default:
    }
  }

  function onBlur() {
    // 菜单项用 mousedown.prevent 抢在 blur 前选中，故此处 blur 即真正离开，安全关闭
    close()
  }

  /** 鼠标悬停同步高亮（仅菜单可见时） */
  function setActive(idx: number) {
    if (open.value) activeIndex.value = idx
  }

  onUnmounted(close)

  return {
    open, items, activeIndex, pos,
    onInput, onKeydown, onBlur, select, close, setActive,
  }
}
