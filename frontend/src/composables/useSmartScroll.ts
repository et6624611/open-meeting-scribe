/**
 * useSmartScroll —— 流式会话的智能滚动状态机
 *
 * 解决：模型持续输出期间强制滚底，导致用户无法上翻查看历史。
 *
 * 两态状态机：
 *   - 跟随态（sticky）：视图停在底部附近，新内容自动滚到底
 *   - 锁定态（locked）：用户主动向上滚动离开底部阈值后，停止自动跟随，
 *     新内容只累加未读、显示「回到底部」按钮，绝不抢滚动
 *
 * 退出锁定的唯一路径：
 *   1) 用户手动滚回到底部（distanceToBottom <= stickThreshold）
 *   2) 用户点击「回到底部」按钮 / 父层显式调用 reset()（切换会话、清空、发送后）
 *
 * 实现要点：
 *   - 程序滚动与用户滚动严格隔离：程序滚动前置 programmatic 标志，
 *     scroll 事件据此忽略本次判定，避免程序滚底被误判为「用户回到底部」
 *     或滚底动画中途误判锁定。
 *   - 用户滚动来源：wheel / touchmove / pointerdown（拖拽滚动条）/ 导航键
 *     （PageUp/ArrowUp/Home/End 等），仅这些输入后置 userInitiated 才允许
 *     进入锁定，避免程序滚动不到位等偶发情况误锁。
 *   - 滞回阈值：进入锁定用 lockThreshold（较大），退出用 stickThreshold
 *     （较小），中间区间保持原状态，消除阈值附近的抖动。
 *   - 调度合并：内容高频增长（流式 token）时用 requestAnimationFrame 合并
 *     同帧多次滚动请求，瞬时赋值 scrollTop（不用 smooth，避免与用户手势冲突）。
 */
import { onBeforeUnmount, ref } from 'vue'

export interface SmartScrollOptions {
  /** 距离底部 > lockThreshold（用户输入触发）→ 进入锁定，停止自动跟随 */
  lockThreshold?: number
  /** 距离底部 <= stickThreshold → 退出锁定，恢复跟随（滞回区间避免抖动） */
  stickThreshold?: number
}

/** 会触发容器滚动的导航键 */
const NAV_KEYS = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '])

export function useSmartScroll(
  getFeed: () => HTMLElement | null | undefined,
  opts: SmartScrollOptions = {},
) {
  const lockThreshold = opts.lockThreshold ?? 100
  const stickThreshold = opts.stickThreshold ?? 24

  /** 锁定态：用户离开底部，停止自动跟随 */
  const locked = ref(false)
  /** 锁定期间累计的新增内容次数（驱动徽标） */
  const unread = ref(0)
  /** 是否显示「回到底部」悬浮按钮 */
  const showJump = ref(false)

  let userInitiated = false // 用户输入事件标志
  let programmatic = false  // 程序滚动标志，scroll 事件据此忽略
  let rafId: number | null = null
  let pending = false       // 同帧合并标记
  let attached: HTMLElement | null = null

  const distanceToBottom = (el: HTMLElement) => el.scrollHeight - el.scrollTop - el.clientHeight

  function markUser() {
    userInitiated = true
  }

  function evaluate() {
    const el = getFeed()
    if (!el) return
    // 程序触发的滚动：不改变状态机
    if (programmatic) {
      programmatic = false
      return
    }
    const d = distanceToBottom(el)
    if (userInitiated) {
      if (!locked.value && d > lockThreshold) {
        locked.value = true
      } else if (locked.value && d <= stickThreshold) {
        // 用户手动回到底部 → 恢复跟随
        locked.value = false
        unread.value = 0
      }
    }
    showJump.value = locked.value && (unread.value > 0 || d > lockThreshold)
  }

  function onScroll() {
    // rAF 合并高频 scroll 事件
    if (rafId != null) return
    rafId = requestAnimationFrame(() => {
      rafId = null
      evaluate()
    })
  }

  function onKey(e: KeyboardEvent) {
    if (!NAV_KEYS.has(e.key)) return
    const el = getFeed()
    if (!el) return
    const ae = document.activeElement
    // 焦点在 feed 内 / feed 自身 / 无具体焦点（body）→ 视为用户滚动 feed
    if (ae && (el.contains(ae) || ae === el || ae === document.body)) markUser()
  }

  function doScroll(smooth: boolean) {
    pending = false
    const el = getFeed()
    if (!el) return
    locked.value = false
    unread.value = 0
    showJump.value = false
    programmatic = true
    if (smooth) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    else el.scrollTop = el.scrollHeight
    // 兜底：若本次未触发 scroll 事件（值未变化），复位标志避免滞留
    requestAnimationFrame(() => {
      programmatic = false
    })
  }

  function scheduleScroll() {
    if (pending) return
    pending = true
    requestAnimationFrame(() => doScroll(false))
  }

  /**
   * 内容增长（新消息 / 流式 token / 阶段变化）：
   * 跟随态 → 调度滚底；锁定态 → 只累加未读、显示按钮，绝不滚动。
   */
  function onContentGrow() {
    if (locked.value) {
      unread.value++
      showJump.value = true
      return
    }
    scheduleScroll()
  }

  /** 用户显式点击「回到底部」 */
  function jumpToBottom() {
    doScroll(true)
  }

  /** 重置：切换会话 / 清空 / 发送后 → 回到跟随态并滚底 */
  function reset() {
    locked.value = false
    unread.value = 0
    showJump.value = false
    scheduleScroll()
  }

  function attach() {
    detach()
    const el = getFeed()
    if (!el) return
    attached = el
    el.addEventListener('scroll', onScroll, { passive: true })
    el.addEventListener('wheel', markUser, { passive: true })
    el.addEventListener('touchmove', markUser, { passive: true })
    el.addEventListener('pointerdown', markUser, { passive: true })
    window.addEventListener('keydown', onKey, true)
  }

  function detach() {
    if (attached) {
      attached.removeEventListener('scroll', onScroll)
      attached.removeEventListener('wheel', markUser)
      attached.removeEventListener('touchmove', markUser)
      attached.removeEventListener('pointerdown', markUser)
      attached = null
    }
    window.removeEventListener('keydown', onKey, true)
  }

  onBeforeUnmount(() => {
    detach()
    if (rafId != null) cancelAnimationFrame(rafId)
  })

  return {
    locked,
    unread,
    showJump,
    attach,
    detach,
    onContentGrow,
    jumpToBottom,
    reset,
    scheduleScroll,
  }
}
