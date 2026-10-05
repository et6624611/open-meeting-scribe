/**
 * 平台检测工具 / Platform detection utility
 *
 * 根据操作系统返回平台相关信息，用于快捷键提示和下载链接匹配。 /
 * Returns OS-related info for keyboard shortcut hints and download link matching.
 * macOS → ⌘    Windows/Linux → Ctrl
 */

const _platform = typeof navigator !== 'undefined' ? navigator.platform : ''

/** 是否为 macOS / Is macOS */
export const isMac = /Mac|iPod|iPhone|iPad/.test(_platform)

/** 是否为 Windows / Is Windows */
export const isWindows = /Win/.test(_platform)

/** 修饰键显示符号：macOS 为 ⌘，其他平台为 Ctrl / Modifier key symbol: ⌘ on macOS, Ctrl on other platforms */
export const modKey = isMac ? '⌘' : 'Ctrl'

/**
 * 返回当前平台对应的下载平台标识 / Return download platform key for current OS.
 * 'macos' | 'windows' | '' (未知平台 / unknown platform)
 */
export function getDownloadPlatform(): 'macos' | 'windows' | '' {
  if (isMac) return 'macos'
  if (isWindows) return 'windows'
  return ''
}
