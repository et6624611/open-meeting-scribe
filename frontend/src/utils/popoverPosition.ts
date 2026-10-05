/**
 * 浮层定位单一真源 / Single source of truth for popover positioning
 *
 * 历史教训：fixed 浮层只夹视口边，侧栏折叠后正文左缘只剩 ~65px，靠左触发的
 * 浮层会横压常驻导航轨（rail 52px / AI 折叠竖条 44px），而 z-popover(500) >
 * rail 的层级导致图标被盖住且点击被吞——rail 图标「点了没反应」已因此复发四次
 * （横幅占位 / 右键菜单 / divider 状态机 / 划词工具栏）。
 * Lesson: popovers that only clamp to the viewport can cover the persistent
 * docks (activity rail / collapsed AI strip) and swallow their clicks. Every
 * floating layer MUST position through these helpers so the dock safe-zones
 * are respected; the rail z-index is the last-resort layer guarantee.
 *
 * 纯函数不触碰 DOM，可直接被 node:test 导入；getDockBounds() 负责读真实布局。
 * The math functions are DOM-free so node:test can import them directly.
 */

export interface ViewRect {
  top: number
  left: number
  width: number
  height: number
}

export interface DockBounds {
  /** 视口宽高 / Viewport size */
  vw: number
  vh: number
  /** 左停靠栏（.activity-rail）右缘；无停靠栏时为 0 / Right edge of left dock */
  railRight: number
  /** 右停靠栏（.ai，含折叠竖条）左缘；无停靠栏时为 vw / Left edge of right dock */
  aiLeft: number
}

/** 浮层与视口/停靠栏的最小间距 / Minimum gap to viewport edge and docks */
export const POPOVER_MARGIN = 8
export const DOCK_GAP = 8

/**
 * 读取左右停靠栏的安全边界 / Read the dock safe-zones from live layout.
 * display:none 或零宽的停靠栏视为不存在（视图切换时 AI 面板可能被隐藏）。
 * Zero-size / display:none docks count as absent.
 */
export function getDockBounds(): DockBounds {
  const vw = window.innerWidth
  const vh = window.innerHeight

  let railRight = 0
  const rail = document.querySelector<HTMLElement>('.activity-rail')
  if (rail) {
    const r = rail.getBoundingClientRect()
    if (r.width > 0 && r.height > 0) railRight = Math.max(0, Math.round(r.right))
  }

  let aiLeft = vw
  const ai = document.querySelector<HTMLElement>('.ai')
  if (ai) {
    const r = ai.getBoundingClientRect()
    if (r.width > 0 && r.height > 0 && r.left >= 0 && r.left < vw) {
      aiLeft = Math.round(r.left)
    }
  }

  return { vw, vh, railRight, aiLeft }
}

/**
 * 水平夹取：以 centerX 为理想中点，限制在左右停靠栏之间。
 * Clamp horizontally: ideal center, bounded by both docks.
 * 可用区比浮层窄时退化为视口夹取（极端小窗的最后手段；此时 rail 的高层级
 * 仍保证图标可点）。
 * When the popover is wider than the available area, fall back to viewport
 * clamping; the rail's higher z-index keeps dock clicks alive.
 */
export function clampHorizontal(
  centerX: number,
  width: number,
  bounds: DockBounds,
  margin = POPOVER_MARGIN,
  gap = DOCK_GAP,
): number {
  const minX = bounds.railRight + gap
  const maxX = bounds.aiLeft - gap - width
  if (maxX >= minX) {
    return Math.min(Math.max(centerX - width / 2, minX), maxX)
  }
  const fallbackMin = margin
  const fallbackMax = Math.max(margin, bounds.vw - margin - width)
  return Math.min(Math.max(centerX - width / 2, fallbackMin), fallbackMax)
}

/** 垂直夹取：结果不得超出 [margin, vh-margin-h] / Clamp vertically into viewport */
function clampVertical(y: number, height: number, vh: number, margin: number): number {
  const maxY = vh - margin - height
  if (y > maxY) return Math.max(margin, maxY)
  return Math.max(margin, y)
}

/**
 * 锚点浮动定位（划词工具栏等）：优先在锚点上方居中，上方空间不足翻到下方，
 * 水平按停靠栏夹取。
 * Anchor-based float (selection toolbar): centered, prefer above the anchor,
 * flip below when there isn't room; horizontally dock-aware.
 */
export function positionAroundAnchor(
  anchor: ViewRect,
  width: number,
  height: number,
  bounds: DockBounds,
  margin = POPOVER_MARGIN,
  gap = DOCK_GAP,
): { x: number; y: number } {
  let y = anchor.top - height - gap
  if (y < margin) y = anchor.top + anchor.height + gap
  y = clampVertical(y, height, bounds.vh, margin)
  const x = clampHorizontal(anchor.left + anchor.width / 2, width, bounds, margin, gap)
  return { x, y }
}

/**
 * 下拉菜单定位（usePopMenu）：默认向下弹出，下方空间不足或上方更宽裕时向上；
 * 对齐触发按钮 start/end 侧，水平按停靠栏夹取。
 * Dropdown menu positioning: prefer opening below, flip up when tight;
 * align to trigger start/end; horizontally dock-aware.
 */
export function positionDropdown(
  trigger: ViewRect,
  width: number,
  height: number,
  bounds: DockBounds,
  options: { gap?: number; margin?: number; align?: 'start' | 'end' } = {},
): { x: number; y: number } {
  const { gap = 4, margin = POPOVER_MARGIN, align = 'end' } = options
  const triggerBottom = trigger.top + trigger.height
  const spaceBelow = bounds.vh - triggerBottom
  const spaceAbove = trigger.top

  let y: number
  if (spaceBelow >= height + gap || spaceBelow >= spaceAbove) {
    y = triggerBottom + gap
  } else {
    y = trigger.top - height - gap
  }
  y = clampVertical(y, height, bounds.vh, margin)

  const idealX = align === 'start' ? trigger.left : trigger.left + trigger.width - width
  const minX = Math.max(margin, bounds.railRight + gap)
  const maxX = bounds.aiLeft - gap - width
  let x: number
  if (maxX >= minX) {
    x = Math.min(Math.max(idealX, minX), maxX)
  } else {
    x = Math.min(Math.max(margin, idealX), Math.max(margin, bounds.vw - margin - width))
  }
  return { x, y }
}
