/**
 * 用户命名空间本地存储 / User-namespaced localStorage
 *
 * 企业版多用户共享同一浏览器：登录态相关缓存必须按 user_id 隔离，
 * 登出时清空该用户命名空间 + 全部用户数据键（档位①清态，UI 规格 §1「登出必须清空」走查硬项）。
 * New enterprise code writes user-relevant data via scopedKey(); legacy global user-data keys
 * are enumerated below and purged on logout until their owners migrate.
 */

/** 命名空间前缀 / Namespaced key builder */
export function scopedKey(userId: string, key: string): string {
  return `oms.u.${userId}.${key}`
}

export function scopedGet(userId: string, key: string): string | null {
  try { return localStorage.getItem(scopedKey(userId, key)) } catch { return null }
}

export function scopedSet(userId: string, key: string, value: string): void {
  try { localStorage.setItem(scopedKey(userId, key), value) } catch { /* 存储满时静默 */ }
}

/** 遗留全局键中"含用户数据"的清单（迁移前由登出清态兜底） / Legacy global keys carrying user data */
export const LEGACY_USER_DATA_KEYS = [
  'oms_completed_unseen',
  'oms_gen_active_tab',
  'oms_rec_active_tab',
  'oms_chat_model',
  'ai_chat_mode',
] as const

/** 遗留全局键前缀清单（动态键，如 oms_bind_bar_dismissed:<task_id>） / Legacy dynamic-key prefixes */
export const LEGACY_USER_DATA_PREFIXES = [
  'oms_bind_bar_dismissed:',
] as const

/** 清态时一并扫掉的命名空间前缀 / Scoped namespace prefix purged on logout */
export const SCOPED_NAMESPACE_PREFIX = 'oms.u.'

/**
 * 登出清态：删除该用户命名空间下全部键 + 全部遗留用户数据键。
 * 设备级偏好（主题/语言/窗宽）不清——属于"这台电脑"，不属于"这个人"。
 * Purge user-scoped + legacy user-data keys on logout; device prefs (theme/locale/width) stay.
 */
export function purgeUserScopedData(userId: string | null): void {
  const doomed: string[] = []
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i)
    if (!k) continue
    if (userId && k.startsWith(`${SCOPED_NAMESPACE_PREFIX}${userId}.`)) { doomed.push(k); continue }
    if ((LEGACY_USER_DATA_KEYS as readonly string[]).includes(k)) { doomed.push(k); continue }
    if (LEGACY_USER_DATA_PREFIXES.some((p) => k.startsWith(p))) doomed.push(k)
  }
  doomed.forEach((k) => { try { localStorage.removeItem(k) } catch { /* */ } })
}
