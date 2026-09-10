/**
 * 缝隙拉手拖拽 composable — 调整侧边栏 / AI 面板宽度
 * 拉手（Sidebar .sb-toggle、AIPanel .ai-toggle）通过 beginResize 实现双手势：
 * 水平位移 ≤ CLICK_THRESHOLD 判为点击（触发 onClick 折叠/展开），超过判为拖拽调宽
 * 分隔缝（.layout-divider）为纯视觉元素，不再响应任何鼠标事件
 */
import { onMounted, onUnmounted } from 'vue'

const SB_MIN = 140, SB_MAX = 400
const AI_MIN = 240, AI_MAX = 600
const CLICK_THRESHOLD = 4

export type DividerSide = 'left' | 'right'

let dragging: DividerSide | null = null
let startX = 0
let startWidth = 0
let maxDelta = 0
let moved = false
let resizable = true
let onClick: (() => void) | null = null

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

/**
 * 由缝隙拉手在 mousedown 时调用：传入 onClick 获得「点击 = 折叠/展开」，
 * 折叠态传 resizable: false（只响应点击展开，不响应拖拽调宽）
 */
export function beginResize(e: MouseEvent, side: DividerSide, opts: { onClick?: () => void; resizable?: boolean } = {}) {
  const panel = panelOf(side)
  if (!panel) return
  e.preventDefault()
  dragging = side
  startX = e.clientX
  startWidth = getWidth(panel)
  maxDelta = 0
  moved = false
  resizable = opts.resizable !== false
  onClick = opts.onClick ?? null
  document.body.classList.add('is-divider-dragging')
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onMouseMove(e: MouseEvent) {
  if (!dragging) return
  const delta = e.clientX - startX
  maxDelta = Math.max(maxDelta, Math.abs(delta))
  if (!resizable || maxDelta <= CLICK_THRESHOLD) return
  moved = true
  if (dragging === 'left') setSidebarWidth(startWidth + delta, false)
  else setAiWidth(startWidth - delta, false)
}

function onMouseUp() {
  if (!dragging) return
  const side = dragging
  dragging = null
  document.body.classList.remove('is-divider-dragging')
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  if (moved) {
    const panel = panelOf(side)
    if (panel) {
      if (side === 'left') setSidebarWidth(getWidth(panel))
      else setAiWidth(getWidth(panel))
    }
  } else if (onClick) {
    onClick()
  }
  onClick = null
}

export function useDivider() {
  onMounted(() => {
    // 恢复已保存的宽度
    try {
      const sw = Number(localStorage.getItem('oms_sb_width'))
      const aw = Number(localStorage.getItem('oms_ai_width'))
      if (Number.isFinite(sw) && sw > 0) setSidebarWidth(sw, false)
      if (Number.isFinite(aw) && aw > 0) setAiWidth(aw, false)
    } catch { /* */ }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  })

  onUnmounted(() => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  })
}
