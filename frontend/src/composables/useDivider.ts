/**
 * 分隔条拖拽 composable — 调整侧边栏/AI面板宽度
 * 移植自旧版 initLayoutDividers()
 */
import { onMounted, onUnmounted } from 'vue'

const SB_MIN = 140, SB_MAX = 400
const AI_MIN = 240, AI_MAX = 600

export function useDivider() {
  let sidebar: HTMLElement | null = null
  let aiPanel: HTMLElement | null = null
  let leftDivider: HTMLElement | null = null
  let rightDivider: HTMLElement | null = null

  let dragging: 'left' | 'right' | null = null
  let startX = 0
  let startWidth = 0

  function getWidth(el: HTMLElement) { return el.getBoundingClientRect().width }

  function setSidebarWidth(w: number, persist = true) {
    w = Math.max(SB_MIN, Math.min(SB_MAX, w))
    if (sidebar) sidebar.style.flex = `0 0 ${w}px`
    if (persist) try { localStorage.setItem('oms_sb_width', String(Math.round(w))) } catch { /* */ }
  }

  function setAiWidth(w: number, persist = true) {
    w = Math.max(AI_MIN, Math.min(AI_MAX, w))
    if (aiPanel) aiPanel.style.flex = `0 0 ${w}px`
    if (persist) try { localStorage.setItem('oms_ai_width', String(Math.round(w))) } catch { /* */ }
  }

  function onMouseDown(e: MouseEvent, side: 'left' | 'right') {
    e.preventDefault()
    dragging = side
    startX = e.clientX
    startWidth = side === 'left' ? getWidth(sidebar!) : getWidth(aiPanel!)
    document.body.classList.add('is-divider-dragging')
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  function onMouseMove(e: MouseEvent) {
    if (!dragging) return
    const delta = e.clientX - startX
    if (dragging === 'left') {
      setSidebarWidth(startWidth + delta, false)
    } else {
      setAiWidth(startWidth - delta, false)
    }
  }

  function onMouseUp() {
    if (!dragging) return
    // 持久化最终宽度
    if (dragging === 'left' && sidebar) setSidebarWidth(getWidth(sidebar))
    if (dragging === 'right' && aiPanel) setAiWidth(getWidth(aiPanel))
    dragging = null
    document.body.classList.remove('is-divider-dragging')
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  onMounted(() => {
    sidebar = document.querySelector('.sidebar')
    aiPanel = document.querySelector('.ai')
    leftDivider = document.querySelector('.layout-divider-left')
    rightDivider = document.querySelector('.layout-divider-right')

    // 恢复已保存的宽度
    try {
      const sw = localStorage.getItem('oms_sb_width')
      const aw = localStorage.getItem('oms_ai_width')
      if (sw && sidebar) sidebar.style.flex = `0 0 ${sw}px`
      if (aw && aiPanel) aiPanel.style.flex = `0 0 ${aw}px`
    } catch { /* */ }

    leftDivider?.addEventListener('mousedown', (e) => onMouseDown(e, 'left'))
    rightDivider?.addEventListener('mousedown', (e) => onMouseDown(e, 'right'))
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  })

  onUnmounted(() => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  })
}
