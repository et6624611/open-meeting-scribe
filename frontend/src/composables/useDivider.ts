/**
 * 缝隙拉手拖拽 composable — 调整侧边栏 / AI 面板宽度 / Gap handle drag composable — adjust sidebar / AI panel width
 * 拉手（Sidebar .sb-toggle、AIPanel .ai-toggle）通过 beginResize 实现双手势： / Handles implement dual gesture via beginResize:
 * 水平位移 ≤ CLICK_THRESHOLD 判为点击（触发 onClick 折叠/展开），超过判为拖拽调宽 / Horizontal ≤ CLICK_THRESHOLD = click (toggle); beyond = drag resize
 * 分隔缝（.layout-divider）为纯视觉元素，不再响应任何鼠标事件 / Gap divider (.layout-divider) is purely visual; no longer responds to mouse events
 *
 * 状态按 side 各自持有：旧实现把 dragging/moved/onClick 放在模块级共享变量上，
 * 左（Sidebar）右（AIPanel）两颗拉手互相覆盖，且 mouseup 一旦丢失（窗口外松手、
 * 原生对话框/右键菜单抢走事件）状态就永久残留，之后的拉手点击会被静默吞掉。
 * State now lives per side; a lost pointer release can no longer swallow the
 * next click, because every entry point (mousedown / mouseup / blur / hide)
 * reconciles the machine before doing its own work.
 */
import { onMounted, onUnmounted } from 'vue'

const SB_MIN = 140, SB_MAX = 400
/* AI_MIN 与 ai-panel.css 中 .ai 的 min-width 保持一致（320px），
   保证拖拽调宽能真实触达并停在实际生效的最小宽度，不与 CSS 夹取打架 */
const AI_MIN = 320, AI_MAX = 600
const CLICK_THRESHOLD = 4

export type DividerSide = 'left' | 'right'

function panelOf(side: DividerSide): HTMLElement | null {
  return document.querySelector(side === 'left' ? '.sidebar' : '.ai')
}

function getWidth(el: HTMLElement) { return el.getBoundingClientRect().width }

export function setSidebarWidth(w: number, persist = true) {
  w = Math.max(SB_MIN, Math.min(SB_MAX, w))
  const el = panelOf('left')
  if (el) el.style.flex = `0 0 ${w}px`
  if (persist) try { localStorage.setItem('oms_sb_width', String(Math.round(w))) } catch { /* */ }
}

export function setAiWidth(w: number, persist = true) {
  w = Math.max(AI_MIN, Math.min(AI_MAX, w))
  const el = panelOf('right')
  if (el) el.style.flex = `0 0 ${w}px`
  if (persist) try { localStorage.setItem('oms_ai_width', String(Math.round(w))) } catch { /* */ }
}

interface DragState {
  active: boolean
  startX: number
  startWidth: number
  maxDelta: number
  moved: boolean
  resizable: boolean
  onClick: (() => void) | null
}

const idleDrag = (): DragState => ({ active: false, startX: 0, startWidth: 0, maxDelta: 0, moved: false, resizable: true, onClick: null })

/** 每个面板一份独立状态 / One state record per panel */
const drag: Record<DividerSide, DragState> = { left: idleDrag(), right: idleDrag() }

/** 当前活跃拖拽（同一时刻只允许一个）/ The one currently active drag */
let activeSide: DividerSide | null = null

function beginDragState(side: DividerSide, e: MouseEvent, opts: { onClick?: () => void; resizable?: boolean }) {
  const panel = panelOf(side)
  if (!panel) return false
  const s = drag[side]
  s.active = true
  s.startX = e.clientX
  s.startWidth = getWidth(panel)
  s.maxDelta = 0
  s.moved = false
  s.resizable = opts.resizable !== false
  s.onClick = opts.onClick ?? null
  activeSide = side
  document.body.classList.add('is-divider-dragging')
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  return true
}

function clearDragVisuals() {
  document.body.classList.remove('is-divider-dragging')
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

/** 作废本次拖拽：既不落盘也不触发 onClick（用于 mouseup 必定丢失的场景自残式自愈）
   *  Cancels the gesture: no persist, no onClick — used where the release is
   *  known to be lost (blur / page hidden), so a half-finished drag never
   *  masquerades as a click. */
function abandonDrag() {
  if (activeSide) drag[activeSide] = idleDrag()
  activeSide = null
  clearDragVisuals()
}

/**
 * 由缝隙拉手在 mousedown 时调用：传入 onClick 获得「点击 = 折叠/展开」， / Called by gap handle on mousedown: pass onClick for "click = collapse/expand",
 * 折叠态传 resizable: false（只响应点击展开，不响应拖拽调宽） / Pass resizable: false when collapsed (only responds to click expand, not drag resize)
 * 面板元素不存在时不再静默 return，而是直接执行 onClick。
 * When the panel is missing the click is no longer swallowed.
 */
export function beginResize(e: MouseEvent, side: DividerSide, opts: { onClick?: () => void; resizable?: boolean } = {}) {
  if (!panelOf(side)) {
    abandonDrag()
    opts.onClick?.()
    return
  }
  e.preventDefault()
  // 上一轮拖拽的 mouseup 若因窗口外松手/原生对话框而丢失，先复位再接手，
  // 保证这一次点击一定会被处理，而不是被残留的 moved 吃掉。
  if (activeSide) abandonDrag()
  beginDragState(side, e, opts)
}

function onMouseMove(e: MouseEvent) {
  if (!activeSide) return
  const s = drag[activeSide]
  const delta = e.clientX - s.startX
  s.maxDelta = Math.max(s.maxDelta, Math.abs(delta))
  if (!s.resizable || s.maxDelta <= CLICK_THRESHOLD) return
  s.moved = true
  if (activeSide === 'left') setSidebarWidth(s.startWidth + delta, false)
  else setAiWidth(s.startWidth - delta, false)
}

/** 松手：位移超过阈值按拖拽落盘，否则视为点击触发 onClick
   *  Release: beyond threshold = resize + persist, otherwise = click. */
function finishDrag() {
  if (!activeSide) return
  const side = activeSide
  const s = drag[side]
  const onClick = s.onClick
  drag[side] = idleDrag()
  activeSide = null
  clearDragVisuals()
  if (s.moved) {
    const panel = panelOf(side)
    if (panel) {
      if (side === 'left') setSidebarWidth(getWidth(panel))
      else setAiWidth(getWidth(panel))
    }
  } else {
    onClick?.()
  }
}

/** mouseup 可能落到任何元素上（含面板被 v-if 卸载的情况），一律监听 document。
   *  Always listen on document so a release can never be missed. */
function onDocMouseUp() {
  if (activeSide) finishDrag()
}

/** 失焦 / 页面隐藏时松手事件必定丢失，直接作废本次拖拽 / Release is never
   *  delivered on blur/hide — cancel instead of leaving the machine stuck. */
function onCancelDrag() {
  if (activeSide) abandonDrag()
}

export function useDivider() {
  onMounted(() => {
    // 恢复已保存的宽度 / Restore saved widths
    try {
      const sw = Number(localStorage.getItem('oms_sb_width'))
      const aw = Number(localStorage.getItem('oms_ai_width'))
      if (Number.isFinite(sw) && sw > 0) setSidebarWidth(sw, false)
      if (Number.isFinite(aw) && aw > 0) setAiWidth(aw, false)
    } catch { /* */ }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onDocMouseUp)
    window.addEventListener('blur', onCancelDrag)
    document.addEventListener('visibilitychange', onCancelDrag)
  })

  onUnmounted(() => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onDocMouseUp)
    window.removeEventListener('blur', onCancelDrag)
    document.removeEventListener('visibilitychange', onCancelDrag)
  })
}
