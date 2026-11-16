/**
 * 桌面系统通知能力桥（REQ-TRANSCRIBE-PROGRESS R2 / Q5）
 * Desktop system-notification bridge.
 *
 * 运行形态已改为浏览器模式：宿主为系统默认浏览器，标准 Notification API 可用，
 * 权限由站点授权状态决定。本模块仍只走标准 API：
 *  - 仅当权限已授予时发送，绝不主动索权（AC-8）；
 *  - 未授权/无 API 时静默返回 false，调用方有站内角标兜底。
 * 历史：原生壳（pywebview 6.2.1 + WKWebView）内 Notification.permission 恒 denied，
 * 故当时降级为仅站内提醒。
 */

/** 是否具备发送条件：API 存在且权限已被授予。不触发任何索权弹窗。 */
export function canSendDesktopNotify(): boolean {
  return typeof window !== 'undefined'
    && typeof Notification !== 'undefined'
    && Notification.permission === 'granted'
}

/**
 * 发送系统通知；点击直达会议页（title 含会议名）。
 * 无权限/无能力时静默返回 false（调用方已有站内角标兜底）。
 */
export function sendDesktopNotify(title: string, body: string, url: string): boolean {
  if (!canSendDesktopNotify()) return false
  try {
    const n = new Notification(title, { body, tag: url })
    n.onclick = () => {
      window.focus()
      window.location.href = url
      n.close()
    }
    return true
  } catch {
    return false
  }
}
