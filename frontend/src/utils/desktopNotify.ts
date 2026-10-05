/**
 * 桌面系统通知能力桥（REQ-TRANSCRIBE-PROGRESS R2 / Q5）
 * Desktop system-notification bridge.
 *
 * Q5 工程结论（2026-09-24 实测，pywebview 6.2.1 + WKWebView）：
 *  - pywebview 无内建系统通知/点击回调 API；
 *  - 壳内 Web Notification API 存在但权限恒为 denied（requestPermission 同步返回 denied）；
 *  - NSUserNotification 已废弃、裸 Python 进程投递不可靠，且需引入新依赖，P0 禁用。
 * ⇒ P0 按裁决降级为「仅站内提醒」；本模块保留标准 Notification API 通道：
 *  仅当宿主（如浏览器 Web 版）已授予权限时发送，绝不主动索权（AC-8）；
 *  系统通知完整版转 P1（UNUserNotificationCenter / pywebview JS bridge）。
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
