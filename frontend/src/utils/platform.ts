/**
 * 平台检测工具 / Platform detection utility
 *
 * 根据操作系统返回对应的修饰键符号，用于快捷键提示展示。 / Returns modifier key symbol based on OS, for keyboard shortcut hints.
 * macOS → ⌘    Windows/Linux → Ctrl
 */

const isMac = typeof navigator !== 'undefined'
  && /Mac|iPod|iPhone|iPad/.test(navigator.platform)

/** 修饰键显示符号：macOS 为 ⌘，其他平台为 Ctrl / Modifier key symbol: ⌘ on macOS, Ctrl on other platforms */
export const modKey = isMac ? '⌘' : 'Ctrl'
